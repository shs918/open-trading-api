# -*- coding: utf-8 -*-
"""미시 지표 계산 모듈.

시장 등락 비율, 체결강도, 신고가/신저가, 공매도, 변동성 등
시장 내부의 세부 상태를 판단하는 미시 지표를 산출한다.
"""

import numpy as np
import pandas as pd

from auto_trader.utils.logger import get_logger

logger = get_logger("regime.micro")


def score_new_highlow(highlow_df: pd.DataFrame) -> float:
    """신고가/신저가 비율 점수를 산출한다.

    Args:
        highlow_df: 신고가/신저가 DataFrame.

    Returns:
        점수 (-2.0 ~ +2.0). 신고가 우세 → 양수, 신저가 우세 → 음수.
    """
    if highlow_df.empty:
        return 0.0

    # 신고가/신저가 종목 수를 기반으로 점수 산출
    total = len(highlow_df)
    if total == 0:
        return 0.0

    # 일반적으로 stck_prdy_ctrt (전일 대비율)로 상승/하락 구분
    if "stck_prdy_ctrt" in highlow_df.columns:
        rates = pd.to_numeric(highlow_df["stck_prdy_ctrt"], errors="coerce").dropna()
        if len(rates) == 0:
            return 0.0
        positive = (rates > 0).sum()
        negative = (rates < 0).sum()
        total_valid = positive + negative
        if total_valid == 0:
            return 0.0
        ratio = (positive - negative) / total_valid
        return round(float(np.clip(ratio * 2, -2.0, 2.0)), 2)

    return 0.0


def score_short_selling(short_df: pd.DataFrame) -> float:
    """공매도 비율 추이 점수를 산출한다.

    공매도 비율이 높으면 부정적 (-), 낮으면 긍정적 (+).

    Args:
        short_df: 공매도 DataFrame.

    Returns:
        점수 (-2.0 ~ +2.0).
    """
    if short_df.empty:
        return 0.0

    # 공매도 비율 컬럼 존재 시
    if "ssts_cntg_smtn_rlim" in short_df.columns:
        ratio = pd.to_numeric(short_df["ssts_cntg_smtn_rlim"], errors="coerce").dropna()
        if len(ratio) == 0:
            return 0.0
        avg_ratio = ratio.mean()
        # 공매도 비율 5% 이상이면 -2, 0%이면 +1
        score = np.clip(1.0 - avg_ratio / 2.5, -2.0, 2.0)
        return round(float(score), 2)

    return 0.0


def score_disparity(disparity_df: pd.DataFrame) -> float:
    """이격도 점수를 산출한다.

    이격도 = (현재가 / 이동평균) × 100
    100 이상이면 과열(+), 100 미만이면 침체(-).

    Args:
        disparity_df: 이격도 DataFrame.

    Returns:
        점수 (-2.0 ~ +2.0).
    """
    if disparity_df.empty:
        return 0.0

    # 20일 이격도
    if "dsprt20" in disparity_df.columns:
        val = pd.to_numeric(disparity_df["dsprt20"], errors="coerce").dropna()
        if len(val) == 0:
            return 0.0
        latest = float(val.iloc[0])
        # 100 기준: 105 이상 → +2, 95 이하 → -2
        score = np.clip((latest - 100) / 2.5, -2.0, 2.0)
        return round(float(score), 2)

    return 0.0


def calc_volatility(prices: pd.Series, window: int = 20) -> float:
    """변동성을 계산한다 (일간 수익률의 표준편차 × sqrt(252)).

    Args:
        prices: 종가 시리즈.
        window: 계산 기간.

    Returns:
        연환산 변동성 (0~1 범위).
    """
    if len(prices) < window + 1:
        return 0.0

    returns = prices.pct_change().dropna()
    if len(returns) < window:
        return 0.0

    vol = float(returns.tail(window).std() * np.sqrt(252))
    return vol


def score_volatility(prices: pd.Series, window: int = 20) -> float:
    """변동성 기반 점수를 산출한다.

    저변동성 → 약간 양수 (안정적), 고변동성 → 음수 (불안정).

    Args:
        prices: 종가 시리즈.
        window: 변동성 계산 기간.

    Returns:
        점수 (-2.0 ~ +2.0).
    """
    vol = calc_volatility(prices, window)
    if vol == 0.0:
        return 0.0

    # 변동성 15% = 정상 → 0점, 30% 이상 → -2, 5% 이하 → +1
    score = np.clip((0.15 - vol) / 0.075, -2.0, 2.0)
    return round(float(score), 2)


def calc_rsi(prices: pd.Series, period: int = 14) -> float:
    """RSI (Relative Strength Index)를 계산한다.

    Args:
        prices: 종가 시리즈.
        period: RSI 기간.

    Returns:
        RSI 값 (0~100).
    """
    if len(prices) < period + 1:
        return 50.0

    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(float(100 - (100 / (1 + rs))), 2)


class MicroIndicators:
    """미시 지표 계산기."""

    def calculate(self, regime_data: dict[str, pd.DataFrame]) -> dict[str, float]:
        """미시 지표 점수를 일괄 계산한다.

        Args:
            regime_data: 수집된 시장 데이터.

        Returns:
            지표명 → 점수 딕셔너리.
        """
        scores: dict[str, float] = {}

        # 변동성 (KOSPI 히스토리에서)
        kospi_hist = regime_data.get("kospi_history", pd.DataFrame())
        if not kospi_hist.empty and "bstp_nmix_prpr" in kospi_hist.columns:
            close = pd.to_numeric(kospi_hist["bstp_nmix_prpr"], errors="coerce").dropna()
            close = close.iloc[::-1].reset_index(drop=True)
            scores["volatility"] = score_volatility(close)
            scores["rsi"] = 0.0  # RSI는 종목별로 산출
        else:
            scores["volatility"] = 0.0

        # 신고가/신저가, 공매도, 이격도는 별도 데이터 수집 후 계산
        scores["new_highlow"] = 0.0
        scores["short_selling"] = 0.0
        scores["disparity"] = 0.0

        logger.info("미시 지표 산출 완료: %s", scores)
        return scores
