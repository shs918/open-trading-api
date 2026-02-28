# -*- coding: utf-8 -*-
"""데이터 캐싱 모듈.

API 호출 최소화를 위한 인메모리 + 파일 캐시.
백테스트용 히스토리컬 데이터는 SQLite로 영구 저장한다.
"""

import os
import sqlite3
import time
from dataclasses import dataclass, field

import pandas as pd

from auto_trader.utils.logger import get_logger

logger = get_logger("data.cache")


@dataclass
class CacheEntry:
    """캐시 항목."""

    data: pd.DataFrame
    timestamp: float  # time.time()
    ttl: float  # 유효 시간 (초)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl


class MemoryCache:
    """인메모리 캐시.

    API 응답을 TTL 기반으로 캐싱하여 동일 요청의 반복 호출을 방지한다.
    """

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> pd.DataFrame | None:
        """캐시에서 데이터를 조회한다.

        Args:
            key: 캐시 키.

        Returns:
            캐싱된 DataFrame 또는 None (미스/만료).
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        return entry.data

    def set(self, key: str, data: pd.DataFrame, ttl: float = 60.0) -> None:
        """데이터를 캐시에 저장한다.

        Args:
            key: 캐시 키.
            data: 저장할 DataFrame.
            ttl: 캐시 유효 시간 (초, 기본 60초).
        """
        self._store[key] = CacheEntry(data=data, timestamp=time.time(), ttl=ttl)

    def invalidate(self, key: str) -> None:
        """특정 키의 캐시를 무효화한다."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """전체 캐시를 초기화한다."""
        self._store.clear()
        logger.info("인메모리 캐시 초기화")


class HistoricalDataStore:
    """히스토리컬 데이터 영구 저장소 (SQLite).

    백테스트용 일봉/지수 데이터를 로컬 SQLite DB에 저장/조회한다.
    """

    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """DB 테이블을 초기화한다."""
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_ohlcv (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    PRIMARY KEY (ticker, date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS index_ohlcv (
                    index_code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    PRIMARY KEY (index_code, date)
                )
            """)
        logger.info("히스토리컬 DB 초기화: %s", self._db_path)

    def save_stock_ohlcv(self, ticker: str, df: pd.DataFrame) -> int:
        """종목 일봉 데이터를 저장한다.

        Args:
            ticker: 종목코드.
            df: OHLCV DataFrame (stck_bsop_date, stck_oprc, stck_hgpr, stck_lwpr, stck_clpr, acml_vol 컬럼 기대).

        Returns:
            저장된 행 수.
        """
        if df.empty:
            return 0

        col_map = {
            "stck_bsop_date": "date",
            "stck_oprc": "open",
            "stck_hgpr": "high",
            "stck_lwpr": "low",
            "stck_clpr": "close",
            "acml_vol": "volume",
        }
        mapped = df.rename(columns=col_map)
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(mapped.columns)):
            logger.warning("OHLCV 컬럼 매핑 실패: %s", list(df.columns))
            return 0

        mapped = mapped[list(required)].copy()
        mapped["ticker"] = ticker
        for col in ["open", "high", "low", "close"]:
            mapped[col] = pd.to_numeric(mapped[col], errors="coerce")
        mapped["volume"] = pd.to_numeric(mapped["volume"], errors="coerce").astype("Int64")

        with sqlite3.connect(self._db_path) as conn:
            mapped.to_sql("daily_ohlcv", conn, if_exists="replace", index=False,
                          method="multi")

        count = len(mapped)
        logger.info("종목 %s 일봉 %d건 저장", ticker, count)
        return count

    def load_stock_ohlcv(
        self, ticker: str, start_date: str = "", end_date: str = ""
    ) -> pd.DataFrame:
        """종목 일봉 데이터를 로드한다.

        Args:
            ticker: 종목코드.
            start_date: 시작일 (YYYYMMDD).
            end_date: 종료일 (YYYYMMDD).

        Returns:
            OHLCV DataFrame.
        """
        query = "SELECT * FROM daily_ohlcv WHERE ticker = ?"
        params: list = [ticker]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date"

        with sqlite3.connect(self._db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)

        return df

    def save_index_ohlcv(self, index_code: str, df: pd.DataFrame) -> int:
        """지수 일봉 데이터를 저장한다.

        Args:
            index_code: 지수코드.
            df: OHLCV DataFrame.

        Returns:
            저장된 행 수.
        """
        if df.empty:
            return 0

        col_map = {
            "stck_bsop_date": "date",
            "bstp_nmix_oprc": "open",
            "bstp_nmix_hgpr": "high",
            "bstp_nmix_lwpr": "low",
            "bstp_nmix_prpr": "close",
            "acml_vol": "volume",
        }
        mapped = df.rename(columns=col_map)
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(set(mapped.columns)):
            logger.warning("지수 OHLCV 컬럼 매핑 실패: %s", list(df.columns))
            return 0

        mapped = mapped[list(required)].copy()
        mapped["index_code"] = index_code
        for col in ["open", "high", "low", "close"]:
            mapped[col] = pd.to_numeric(mapped[col], errors="coerce")
        mapped["volume"] = pd.to_numeric(mapped["volume"], errors="coerce").astype("Int64")

        with sqlite3.connect(self._db_path) as conn:
            mapped.to_sql("index_ohlcv", conn, if_exists="replace", index=False,
                          method="multi")

        count = len(mapped)
        logger.info("지수 %s 일봉 %d건 저장", index_code, count)
        return count

    def load_index_ohlcv(
        self, index_code: str, start_date: str = "", end_date: str = ""
    ) -> pd.DataFrame:
        """지수 일봉 데이터를 로드한다.

        Args:
            index_code: 지수코드.
            start_date: 시작일.
            end_date: 종료일.

        Returns:
            OHLCV DataFrame.
        """
        query = "SELECT * FROM index_ohlcv WHERE index_code = ?"
        params: list = [index_code]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date"

        with sqlite3.connect(self._db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)

        return df
