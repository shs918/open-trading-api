# -*- coding: utf-8 -*-
"""시세/지수/차트 데이터 수집 모듈.

DataProvider를 활용하여 마켓 레짐 분석 및 전략에 필요한
시장 데이터를 수집/가공하는 고수준 인터페이스를 제공한다.
"""

from datetime import datetime, timedelta

import pandas as pd

from auto_trader.data.provider import DataProvider
from auto_trader.utils.logger import get_logger

logger = get_logger("data.market_data")


# 주요 지수 코드
INDEX_CODES = {
    "kospi": "0001",
    "kosdaq": "1001",
    "kospi200": "2001",
}


class MarketDataCollector:
    """시장 데이터 수집기."""

    def __init__(self, provider: DataProvider) -> None:
        self._provider = provider

    # ─── 지수 데이터 ──────────────────────────────────────────────

    def get_index_current(self, index_name: str = "kospi") -> pd.DataFrame:
        """지수 현재가를 조회한다.

        Args:
            index_name: 지수 이름 (kospi, kosdaq, kospi200).

        Returns:
            지수 현재가 DataFrame.
        """
        code = INDEX_CODES.get(index_name, index_name)
        return self._provider.get_index_price(code)

    def get_index_history(
        self,
        index_name: str = "kospi",
        days: int = 120,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """지수 히스토리컬 일봉 데이터를 조회한다.

        Args:
            index_name: 지수 이름.
            days: 조회 기간 (일).
            end_date: 종료일 (YYYYMMDD). None이면 오늘.

        Returns:
            지수 OHLCV DataFrame.
        """
        code = INDEX_CODES.get(index_name, index_name)
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        start_date = (
            datetime.strptime(end_date, "%Y%m%d") - timedelta(days=days)
        ).strftime("%Y%m%d")

        _, ohlcv = self._provider.get_index_daily_chart(
            code, start_date, end_date, period="D"
        )
        return ohlcv

    # ─── 종목 데이터 ──────────────────────────────────────────────

    def get_stock_price(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """종목 현재가를 조회한다."""
        return self._provider.get_current_price(ticker, market)

    def get_stock_history(
        self,
        ticker: str,
        days: int = 120,
        end_date: str | None = None,
        period: str = "D",
        market: str = "J",
    ) -> pd.DataFrame:
        """종목 히스토리컬 데이터를 조회한다.

        Args:
            ticker: 종목코드.
            days: 조회 기간 (일).
            end_date: 종료일 (YYYYMMDD).
            period: 기간분류 (D/W/M/Y).
            market: 시장 구분.

        Returns:
            OHLCV DataFrame.
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        start_date = (
            datetime.strptime(end_date, "%Y%m%d") - timedelta(days=days)
        ).strftime("%Y%m%d")

        _, ohlcv = self._provider.get_daily_chart(
            ticker, start_date, end_date, period, market
        )
        return ohlcv

    # ─── 수급 데이터 ──────────────────────────────────────────────

    def get_investor_data(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """투자자별 매매 동향을 조회한다."""
        return self._provider.get_investor_trends(ticker, market)

    def get_program_trading(self) -> pd.DataFrame:
        """프로그램 매매 현황을 조회한다."""
        return self._provider.get_program_trade()

    def get_short_selling(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """공매도 데이터를 조회한다."""
        return self._provider.get_short_sale(ticker, market)

    # ─── 시장 분석 지표 ────────────────────────────────────────────

    def get_market_time(self) -> pd.DataFrame:
        """장 운영 시간 정보를 조회한다."""
        return self._provider.get_market_time()

    def get_volume_power(self, market: str = "J") -> pd.DataFrame:
        """체결강도 상위 종목을 조회한다."""
        return self._provider.get_volume_power(market)

    def get_new_highlow(self, market: str = "J") -> pd.DataFrame:
        """신고가/신저가 근접 종목을 조회한다."""
        return self._provider.get_near_new_highlow(market)

    def get_disparity(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """이격도를 조회한다."""
        return self._provider.get_disparity(ticker, market)

    def get_market_cap_ranking(self, market: str = "J") -> pd.DataFrame:
        """시가총액 순위를 조회한다."""
        return self._provider.get_market_cap(market)

    # ─── 펀더멘탈 데이터 ──────────────────────────────────────────

    def get_financial_ratios(self, ticker: str, market: str = "J") -> pd.DataFrame:
        """종목 재무비율(PER, PBR, ROE 등)을 조회한다."""
        return self._provider.get_finance_ratio(ticker, market)

    # ─── 복합 데이터 수집 ─────────────────────────────────────────

    def collect_regime_data(self) -> dict[str, pd.DataFrame]:
        """마켓 레짐 분석에 필요한 데이터를 일괄 수집한다.

        Returns:
            지표명 → DataFrame 딕셔너리.
        """
        data: dict[str, pd.DataFrame] = {}

        try:
            data["kospi_current"] = self.get_index_current("kospi")
        except Exception as e:
            logger.warning("KOSPI 현재지수 수집 실패: %s", e)

        try:
            data["kospi_history"] = self.get_index_history("kospi", days=150)
        except Exception as e:
            logger.warning("KOSPI 히스토리 수집 실패: %s", e)

        try:
            data["kosdaq_history"] = self.get_index_history("kosdaq", days=150)
        except Exception as e:
            logger.warning("KOSDAQ 히스토리 수집 실패: %s", e)

        try:
            data["market_time"] = self.get_market_time()
        except Exception as e:
            logger.warning("장 운영 시간 수집 실패: %s", e)

        try:
            data["program_trade"] = self.get_program_trading()
        except Exception as e:
            logger.warning("프로그램 매매 수집 실패: %s", e)

        logger.info("레짐 분석 데이터 수집 완료 (%d건)", len(data))
        return data
