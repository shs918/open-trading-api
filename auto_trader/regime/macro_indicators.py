# -*- coding: utf-8 -*-
"""거시 지표 계산 모듈.

KOSPI 추세, 외국인/기관 수급, 해외 지수 동향 등
시장 전체의 방향성을 판단하는 거시 지표를 산출한다.
"""

import numpy as np
import pandas as pd

from auto_trader.utils.logger import get_logger

logger = get_logger("regime.macro")


def calc_moving_averages(
    prices: pd.Series, windows: list[int] = None
) -> dict[int, pd.Series]:
    """이동평균선을 계산한다.

    Args:
        prices: 종가 시리즈.
        windows: 이동평균 기간 리스트.

    Returns:
        기간 → 이동평균 시리즈 딕셔너리.
    """
    if windows is None:
        windows = [5, 20, 60, 120]
    return {w: prices.rolling(window=w).mean() for w in windows}


def score_ma_arrangement(prices: pd.Series) -> float:
    """이동평균 배열 상태로 추세 점수를 산출한다.

    정배열(5>20>60>120)이면 +2, 역배열이면 -2, 그 사이는 선형 보간.

    Args:
        prices: 종가 시리즈 (최소 120개).

    Returns:
        추세 점수 (-2.0 ~ +2.0).
    """
    if len(prices) < 120:
        return 0.0

    mas = calc_moving_averages(prices)
    latest = {w: float(ma.iloc[-1]) for w, ma in mas.items() if not np.isnan(ma.iloc[-1])}

    if len(latest) < 4:
        return 0.0

    vals = [latest[5], latest[20], latest[60], latest[120]]

    # 인접 쌍 비교: 정배열이면 +1, 역배열이면 -1
    score = 0.0
    for i in range(len(vals) - 1):
        if vals[i] > vals[i + 1]:
            score += 1.0
        elif vals[i] < vals[i + 1]:
            score -= 1.0

    # -3~+3 범위를 -2~+2로 정규화
    return round(score * 2 / 3, 2)


def score_momentum(prices: pd.Series, period: int = 20) -> float:
    """ROC(Rate of Change) 기반 모멘텀 점수를 산출한다.

    Args:
        prices: 종가 시리즈.
        period: ROC 계산 기간.

    Returns:
        모멘텀 점수 (-2.0 ~ +2.0).
    """
    if len(prices) < period + 1:
        return 0.0

    roc = (float(prices.iloc[-1]) - float(prices.iloc[-period - 1])) / float(prices.iloc[-period - 1]) * 100

    # ROC를 점수로 변환: ±5% 이상이면 ±2
    score = np.clip(roc / 2.5, -2.0, 2.0)
    return round(float(score), 2)


def score_investor_flow(investor_df: pd.DataFrame) -> dict[str, float]:
    """외국인/기관 순매수 추이 점수를 산출한다.

    Args:
        investor_df: 투자자 매매 동향 DataFrame.
            frgn_ntby_qty (외국인 순매수), orgn_ntby_qty (기관 순매수) 컬럼 기대.

    Returns:
        {"foreign": 점수, "institution": 점수} 딕셔너리.
    """
    result = {"foreign": 0.0, "institution": 0.0}

    if investor_df.empty:
        return result

    # 외국인 순매수
    if "frgn_ntby_qty" in investor_df.columns:
        frgn = pd.to_numeric(investor_df["frgn_ntby_qty"], errors="coerce")
        net = frgn.sum()
        if net > 0:
            result["foreign"] = min(net / 100000, 2.0)
        else:
            result["foreign"] = max(net / 100000, -2.0)

    # 기관 순매수
    if "orgn_ntby_qty" in investor_df.columns:
        orgn = pd.to_numeric(investor_df["orgn_ntby_qty"], errors="coerce")
        net = orgn.sum()
        if net > 0:
            result["institution"] = min(net / 100000, 2.0)
        else:
            result["institution"] = max(net / 100000, -2.0)

    return result


def score_trading_volume(prices: pd.Series, volumes: pd.Series) -> float:
    """거래대금 대비 이동평균 비율로 활성도 점수를 산출한다.

    Args:
        prices: 종가 시리즈.
        volumes: 거래량 시리즈.

    Returns:
        거래 활성도 점수 (-2.0 ~ +2.0).
    """
    if len(volumes) < 20:
        return 0.0

    amount = prices * volumes
    avg_20 = amount.rolling(20).mean()
    if avg_20.iloc[-1] == 0 or np.isnan(avg_20.iloc[-1]):
        return 0.0

    ratio = float(amount.iloc[-1] / avg_20.iloc[-1])

    # ratio 1.0 = 평균 → 0점, 1.5 이상 → +2, 0.5 이하 → -2
    score = np.clip((ratio - 1.0) * 4, -2.0, 2.0)
    return round(float(score), 2)


class MacroIndicators:
    """거시 지표 계산기.

    수집된 데이터를 입력받아 각 거시 지표의 점수를 산출한다.
    """

    def calculate(self, regime_data: dict[str, pd.DataFrame]) -> dict[str, float]:
        """거시 지표 점수를 일괄 계산한다.

        Args:
            regime_data: MarketDataCollector.collect_regime_data()의 결과.

        Returns:
            지표명 → 점수 딕셔너리.
        """
        scores: dict[str, float] = {}

        # KOSPI 추세 (이동평균 배열)
        kospi_hist = regime_data.get("kospi_history", pd.DataFrame())
        if not kospi_hist.empty and "bstp_nmix_prpr" in kospi_hist.columns:
            close = pd.to_numeric(kospi_hist["bstp_nmix_prpr"], errors="coerce").dropna()
            close = close.iloc[::-1].reset_index(drop=True)  # 오래된 순서로 정렬
            scores["kospi_trend"] = score_ma_arrangement(close)
            scores["kospi_momentum"] = score_momentum(close)

            if "acml_vol" in kospi_hist.columns:
                vol = pd.to_numeric(kospi_hist["acml_vol"], errors="coerce").dropna()
                vol = vol.iloc[::-1].reset_index(drop=True)
                scores["trading_volume"] = score_trading_volume(close, vol)
        else:
            scores["kospi_trend"] = 0.0
            scores["kospi_momentum"] = 0.0
            scores["trading_volume"] = 0.0

        # 외국인/기관 수급 (별도 수집 필요 시 0으로 설정)
        scores["foreign_flow"] = 0.0
        scores["institution_flow"] = 0.0

        logger.info("거시 지표 산출 완료: %s", scores)
        return scores
