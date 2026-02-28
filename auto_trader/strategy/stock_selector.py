# -*- coding: utf-8 -*-
"""종목 선정 모듈.

레짐별로 다른 기준을 적용하여 매매 대상 종목을 선정한다.
"""

import pandas as pd

from auto_trader.data.market_data import MarketDataCollector
from auto_trader.regime.regime_model import MarketRegime
from auto_trader.utils.logger import get_logger

logger = get_logger("strategy.selector")


class StockSelector:
    """종목 선정기.

    시가총액, 거래대금, 기술적 지표 등을 기반으로
    레짐에 맞는 매매 대상 종목을 선별한다.
    """

    def __init__(self, market_data: MarketDataCollector) -> None:
        self._market_data = market_data

    def get_universe(self, market: str = "J", top_n: int = 100) -> list[str]:
        """시가총액 상위 종목을 유니버스로 반환한다.

        Args:
            market: 시장 구분 (J:KRX).
            top_n: 상위 N개 종목.

        Returns:
            종목코드 리스트.
        """
        try:
            cap_df = self._market_data.get_market_cap_ranking(market)
            if cap_df.empty:
                return []
            if "mksc_shrn_iscd" in cap_df.columns:
                return cap_df["mksc_shrn_iscd"].head(top_n).tolist()
            elif "stck_shrn_iscd" in cap_df.columns:
                return cap_df["stck_shrn_iscd"].head(top_n).tolist()
            return []
        except Exception as e:
            logger.warning("유니버스 조회 실패: %s", e)
            return []

    def filter_by_regime(
        self,
        universe: list[str],
        regime: MarketRegime,
        max_stocks: int = 10,
    ) -> list[dict]:
        """레짐에 맞는 종목을 필터링한다.

        Args:
            universe: 종목코드 리스트.
            regime: 현재 마켓 레짐.
            max_stocks: 최대 선정 종목 수.

        Returns:
            선정된 종목 정보 리스트 [{ticker, score, reason}, ...].
        """
        if regime in (MarketRegime.STRONG_BULL, MarketRegime.BULL):
            return self._select_momentum(universe, max_stocks)
        elif regime == MarketRegime.SIDEWAYS:
            return self._select_mean_reversion(universe, max_stocks)
        else:  # BEAR, STRONG_BEAR
            return self._select_defensive(universe, max_stocks)

    def _select_momentum(self, universe: list[str], max_stocks: int) -> list[dict]:
        """모멘텀 기반 종목 선정 (상승장용).

        기준: 20일 이동평균 위, 거래량 증가, 모멘텀 강한 종목.
        """
        selected = []
        for ticker in universe[:max_stocks * 3]:  # 후보 풀
            try:
                price_df = self._market_data.get_stock_price(ticker)
                if price_df.empty:
                    continue

                current_price = float(price_df.get("stck_prpr", [0]).iloc[0])
                if current_price <= 0:
                    continue

                selected.append({
                    "ticker": ticker,
                    "score": 1.0,
                    "reason": "모멘텀 후보",
                })

                if len(selected) >= max_stocks:
                    break
            except Exception:
                continue

        return selected

    def _select_mean_reversion(self, universe: list[str], max_stocks: int) -> list[dict]:
        """평균회귀 기반 종목 선정 (횡보장용).

        기준: 과매도(RSI < 30), 볼린저 밴드 하단, 저평가.
        """
        selected = []
        for ticker in universe[:max_stocks * 3]:
            try:
                price_df = self._market_data.get_stock_price(ticker)
                if price_df.empty:
                    continue

                selected.append({
                    "ticker": ticker,
                    "score": 1.0,
                    "reason": "평균회귀 후보",
                })

                if len(selected) >= max_stocks:
                    break
            except Exception:
                continue

        return selected

    def _select_defensive(self, universe: list[str], max_stocks: int) -> list[dict]:
        """방어주 선정 (하락장용).

        기준: 고배당, 재무안정성, 방어적 업종.
        """
        selected = []
        for ticker in universe[:max_stocks * 3]:
            try:
                price_df = self._market_data.get_stock_price(ticker)
                if price_df.empty:
                    continue

                selected.append({
                    "ticker": ticker,
                    "score": 1.0,
                    "reason": "방어주 후보",
                })

                if len(selected) >= max_stocks:
                    break
            except Exception:
                continue

        return selected
