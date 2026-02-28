# -*- coding: utf-8 -*-
"""스케줄러 모듈.

장 시간에 맞춰 자동매매 루프를 실행하고,
주기적 작업(레짐 분석, 포지션 점검, 리포트 등)을 관리한다.
"""

import asyncio
from datetime import datetime, time as dt_time, timedelta
from enum import Enum

from auto_trader.config import Config, MarketSession
from auto_trader.utils.logger import get_logger

logger = get_logger("utils.scheduler")


class MarketState(Enum):
    """현재 장 상태."""

    BEFORE_MARKET = "before_market"  # 장 시작 전
    NXT_PRE_MARKET = "nxt_pre_market"  # NXT 프리마켓 (08:00~08:50)
    REGULAR_OPEN = "regular_open"  # 정규장 (09:00~15:30)
    AFTER_HOURS = "after_hours"  # 시간외 (15:40~16:00)
    MARKET_CLOSED = "market_closed"  # 장 종료


# 장 시간 (KST)
NXT_START = dt_time(8, 0)
NXT_END = dt_time(8, 50)
KRX_START = dt_time(9, 0)
KRX_END = dt_time(15, 30)
AFTER_START = dt_time(15, 40)
AFTER_END = dt_time(16, 0)


def get_market_state() -> MarketState:
    """현재 장 상태를 판단한다.

    Returns:
        MarketState.
    """
    now = datetime.now().time()
    weekday = datetime.now().weekday()

    # 주말
    if weekday >= 5:
        return MarketState.MARKET_CLOSED

    if now < NXT_START:
        return MarketState.BEFORE_MARKET
    elif NXT_START <= now < NXT_END:
        return MarketState.NXT_PRE_MARKET
    elif NXT_END <= now < KRX_START:
        return MarketState.BEFORE_MARKET
    elif KRX_START <= now < KRX_END:
        return MarketState.REGULAR_OPEN
    elif AFTER_START <= now < AFTER_END:
        return MarketState.AFTER_HOURS
    else:
        return MarketState.MARKET_CLOSED


def is_trading_hours() -> bool:
    """현재 매매 가능 시간인지 확인한다."""
    state = get_market_state()
    return state in (
        MarketState.NXT_PRE_MARKET,
        MarketState.REGULAR_OPEN,
        MarketState.AFTER_HOURS,
    )


class ScheduledTask:
    """스케줄 작업."""

    def __init__(
        self,
        name: str,
        callback,
        interval_seconds: int,
        market_states: list[MarketState] | None = None,
    ) -> None:
        self.name = name
        self.callback = callback
        self.interval_seconds = interval_seconds
        self.market_states = market_states  # None이면 항상 실행
        self.last_run: datetime | None = None

    def should_run(self, current_state: MarketState) -> bool:
        """실행 시점인지 확인한다."""
        if self.market_states and current_state not in self.market_states:
            return False
        if self.last_run is None:
            return True
        elapsed = (datetime.now() - self.last_run).total_seconds()
        return elapsed >= self.interval_seconds


class TradingScheduler:
    """매매 스케줄러.

    장 시간에 맞춰 등록된 작업을 주기적으로 실행한다.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._tasks: list[ScheduledTask] = []
        self._running = False

        # 콜백 이벤트
        self._on_market_open = None
        self._on_market_close = None
        self._prev_state: MarketState | None = None

    # ─── 작업 등록 ──────────────────────────────────────────────

    def register(
        self,
        name: str,
        callback,
        interval_seconds: int,
        market_states: list[MarketState] | None = None,
    ) -> None:
        """주기 작업을 등록한다.

        Args:
            name: 작업 이름.
            callback: 실행할 함수 (동기 또는 async).
            interval_seconds: 실행 간격 (초).
            market_states: 실행 가능한 장 상태 (None=항상).
        """
        self._tasks.append(ScheduledTask(
            name=name,
            callback=callback,
            interval_seconds=interval_seconds,
            market_states=market_states,
        ))
        logger.info("스케줄 등록: %s (간격=%d초)", name, interval_seconds)

    def on_market_open(self, callback) -> None:
        """장 시작 이벤트 콜백을 등록한다."""
        self._on_market_open = callback

    def on_market_close(self, callback) -> None:
        """장 종료 이벤트 콜백을 등록한다."""
        self._on_market_close = callback

    # ─── 실행 ───────────────────────────────────────────────────

    async def start(self) -> None:
        """스케줄러를 시작한다 (async 루프)."""
        self._running = True
        logger.info("스케줄러 시작 (등록 작업: %d건)", len(self._tasks))

        while self._running:
            try:
                current_state = get_market_state()

                # 장 상태 변경 감지
                await self._handle_state_change(current_state)

                # 등록된 작업 실행
                for task in self._tasks:
                    if self._config.paused and task.market_states is not None:
                        continue  # 일시정지 시 매매 관련 작업 스킵

                    if task.should_run(current_state):
                        try:
                            if asyncio.iscoroutinefunction(task.callback):
                                await task.callback()
                            else:
                                task.callback()
                            task.last_run = datetime.now()
                        except Exception as e:
                            logger.error("작업 실행 오류 [%s]: %s", task.name, e)

                await asyncio.sleep(1)

            except Exception as e:
                logger.error("스케줄러 루프 오류: %s", e)
                await asyncio.sleep(5)

    def stop(self) -> None:
        """스케줄러를 중지한다."""
        self._running = False
        logger.info("스케줄러 중지")

    async def _handle_state_change(self, current_state: MarketState) -> None:
        """장 상태 변경 이벤트를 처리한다."""
        if self._prev_state == current_state:
            return

        old_state = self._prev_state
        self._prev_state = current_state
        logger.info("장 상태 변경: %s → %s",
                     old_state.value if old_state else "초기화",
                     current_state.value)

        # 장 시작
        if current_state == MarketState.REGULAR_OPEN and old_state != MarketState.REGULAR_OPEN:
            if self._on_market_open:
                try:
                    if asyncio.iscoroutinefunction(self._on_market_open):
                        await self._on_market_open()
                    else:
                        self._on_market_open()
                except Exception as e:
                    logger.error("장 시작 콜백 오류: %s", e)

        # 장 종료
        if current_state == MarketState.MARKET_CLOSED and old_state in (
            MarketState.REGULAR_OPEN, MarketState.AFTER_HOURS
        ):
            if self._on_market_close:
                try:
                    if asyncio.iscoroutinefunction(self._on_market_close):
                        await self._on_market_close()
                    else:
                        self._on_market_close()
                except Exception as e:
                    logger.error("장 종료 콜백 오류: %s", e)

    # ─── 유틸리티 ───────────────────────────────────────────────

    @staticmethod
    def seconds_until_market_open() -> int:
        """장 시작(09:00)까지 남은 초를 반환한다."""
        now = datetime.now()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now.time() >= KRX_START:
            target += timedelta(days=1)
        # 주말 건너뛰기
        while target.weekday() >= 5:
            target += timedelta(days=1)
        return int((target - now).total_seconds())
