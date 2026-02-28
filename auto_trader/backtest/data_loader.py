# -*- coding: utf-8 -*-
"""백테스트용 과거 데이터 로딩/저장 모듈.

KIS API로 히스토리컬 데이터를 수집하여 SQLite에 캐싱하고,
백테스트 엔진에 일봉 데이터를 공급한다.
"""

import time
from datetime import datetime, timedelta

import pandas as pd

from auto_trader.data.cache import HistoricalDataStore
from auto_trader.data.market_data import MarketDataCollector
from auto_trader.utils.logger import get_logger

logger = get_logger("backtest.data_loader")

# KIS API 호출 간 대기 시간 (초) — 과도한 호출 방지
_API_SLEEP = 0.5


class BacktestDataLoader:
    """백테스트용 데이터 로더.

    로컬 캐시(SQLite)를 먼저 조회하고, 누락된 구간만 KIS API로 보충한다.
    """

    def __init__(
        self,
        store: HistoricalDataStore,
        market_data: MarketDataCollector | None = None,
    ) -> None:
        self._store = store
        self._market_data = market_data  # None이면 API 호출 불가 (캐시만 사용)

    # ─── 종목 데이터 ────────────────────────────────────────────

    def load_stock(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """종목 일봉 데이터를 로드한다.

        캐시에 있으면 캐시 사용, 없으면 API로 수집 후 캐싱.

        Args:
            ticker: 종목코드.
            start_date: 시작일 (YYYYMMDD).
            end_date: 종료일 (YYYYMMDD).

        Returns:
            OHLCV DataFrame (date, open, high, low, close, volume).
        """
        cached = self._store.load_stock_ohlcv(ticker, start_date, end_date)
        if not cached.empty and len(cached) > 5:
            logger.debug("캐시 사용: %s (%s ~ %s, %d건)", ticker, start_date, end_date, len(cached))
            return cached

        if self._market_data is None:
            logger.warning("API 미연결 — 캐시에 데이터 없음: %s", ticker)
            return cached

        return self._fetch_and_cache_stock(ticker, start_date, end_date)

    def _fetch_and_cache_stock(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """API로 종목 일봉을 수집하여 캐싱한다."""
        days = (datetime.strptime(end_date, "%Y%m%d") - datetime.strptime(start_date, "%Y%m%d")).days
        try:
            ohlcv = self._market_data.get_stock_history(
                ticker, days=days + 30, end_date=end_date,
            )
            if not ohlcv.empty:
                self._store.save_stock_ohlcv(ticker, ohlcv)
                return self._store.load_stock_ohlcv(ticker, start_date, end_date)
        except Exception as e:
            logger.error("종목 데이터 수집 실패 (%s): %s", ticker, e)

        return pd.DataFrame()

    # ─── 지수 데이터 ────────────────────────────────────────────

    def load_index(
        self,
        index_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """지수 일봉 데이터를 로드한다.

        Args:
            index_code: 지수코드 (0001, 1001, 2001).
            start_date: 시작일 (YYYYMMDD).
            end_date: 종료일 (YYYYMMDD).

        Returns:
            OHLCV DataFrame.
        """
        cached = self._store.load_index_ohlcv(index_code, start_date, end_date)
        if not cached.empty and len(cached) > 5:
            logger.debug("지수 캐시 사용: %s (%d건)", index_code, len(cached))
            return cached

        if self._market_data is None:
            return cached

        return self._fetch_and_cache_index(index_code, start_date, end_date)

    def _fetch_and_cache_index(
        self,
        index_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """API로 지수 일봉을 수집하여 캐싱한다."""
        # 지수 이름 매핑 (market_data에서 사용하는 키)
        name_map = {"0001": "kospi", "1001": "kosdaq", "2001": "kospi200"}
        index_name = name_map.get(index_code, index_code)

        days = (datetime.strptime(end_date, "%Y%m%d") - datetime.strptime(start_date, "%Y%m%d")).days
        try:
            ohlcv = self._market_data.get_index_history(
                index_name, days=days + 30, end_date=end_date,
            )
            if not ohlcv.empty:
                self._store.save_index_ohlcv(index_code, ohlcv)
                return self._store.load_index_ohlcv(index_code, start_date, end_date)
        except Exception as e:
            logger.error("지수 데이터 수집 실패 (%s): %s", index_code, e)

        return pd.DataFrame()

    # ─── 일괄 수집 ──────────────────────────────────────────────

    def preload_stocks(
        self,
        tickers: list[str],
        start_date: str,
        end_date: str,
    ) -> dict[str, pd.DataFrame]:
        """여러 종목의 일봉 데이터를 일괄 수집한다.

        Args:
            tickers: 종목코드 리스트.
            start_date: 시작일.
            end_date: 종료일.

        Returns:
            {종목코드: OHLCV DataFrame} 딕셔너리.
        """
        data: dict[str, pd.DataFrame] = {}
        for i, ticker in enumerate(tickers):
            df = self.load_stock(ticker, start_date, end_date)
            if not df.empty:
                data[ticker] = df
            if i < len(tickers) - 1:
                time.sleep(_API_SLEEP)

        logger.info(
            "일괄 수집 완료: %d/%d 종목 (%s ~ %s)",
            len(data), len(tickers), start_date, end_date,
        )
        return data

    def preload_indices(
        self,
        index_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> dict[str, pd.DataFrame]:
        """여러 지수의 일봉 데이터를 일괄 수집한다."""
        data: dict[str, pd.DataFrame] = {}
        for i, code in enumerate(index_codes):
            df = self.load_index(code, start_date, end_date)
            if not df.empty:
                data[code] = df
            if i < len(index_codes) - 1:
                time.sleep(_API_SLEEP)

        logger.info("지수 수집 완료: %d/%d", len(data), len(index_codes))
        return data
