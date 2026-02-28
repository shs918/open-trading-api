# -*- coding: utf-8 -*-
"""자동 매매 솔루션 메인 진입점.

CLI 인터페이스를 제공하고, 전체 시스템을 조립·실행한다.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

from auto_trader.config import Config, TradingMode, load_config
from auto_trader.data.account_data import AccountDataCollector
from auto_trader.data.cache import HistoricalDataStore
from auto_trader.data.market_data import MarketDataCollector
from auto_trader.data.provider import DataProvider
from auto_trader.execution.order_manager import OrderManager
from auto_trader.execution.position_manager import PositionManager
from auto_trader.execution.risk_manager import RiskManager
from auto_trader.regime.analyzer import RegimeAnalyzer
from auto_trader.strategy.base import SignalType
from auto_trader.strategy.bear_strategy import BearStrategy
from auto_trader.strategy.bull_strategy import BullStrategy
from auto_trader.strategy.sideways_strategy import SidewaysStrategy
from auto_trader.strategy.stock_selector import StockSelector
from auto_trader.utils.logger import get_logger, setup_logging
from auto_trader.utils.notifier import Notifier
from auto_trader.utils.scheduler import (
    MarketState,
    TradingScheduler,
    get_market_state,
)

logger = get_logger("main")


class AutoTrader:
    """자동 매매 오케스트레이터.

    모든 컴포넌트를 조립하고 매매 루프를 관리한다.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

        # 데이터 계층
        self._provider = DataProvider(config)
        self._market_data = MarketDataCollector(self._provider)
        self._account = AccountDataCollector(self._provider)

        # 레짐 분석
        self._regime_analyzer = RegimeAnalyzer(self._market_data)

        # 전략
        self._strategies = [BullStrategy(), SidewaysStrategy(), BearStrategy()]
        self._stock_selector = StockSelector(self._market_data)

        # 실행 엔진
        self._order_manager = OrderManager(self._provider)
        self._position_manager = PositionManager(self._account, self._market_data)
        self._risk_manager = RiskManager(config, self._position_manager)

        # 유틸리티
        self._notifier = Notifier(config)
        self._scheduler = TradingScheduler(config)

        # 상태
        self._start_time = datetime.now()
        self._last_regime = None

    # ─── 컴포넌트 접근자 ────────────────────────────────────────

    @property
    def provider(self) -> DataProvider:
        return self._provider

    @property
    def market_data(self) -> MarketDataCollector:
        return self._market_data

    @property
    def account(self) -> AccountDataCollector:
        return self._account

    @property
    def regime_analyzer(self) -> RegimeAnalyzer:
        return self._regime_analyzer

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def position_manager(self) -> PositionManager:
        return self._position_manager

    @property
    def risk_manager(self) -> RiskManager:
        return self._risk_manager

    @property
    def notifier(self) -> Notifier:
        return self._notifier

    @property
    def uptime(self) -> str:
        """가동 시간 문자열."""
        delta = datetime.now() - self._start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    # ─── 초기화 ─────────────────────────────────────────────────

    def initialize(self) -> None:
        """시스템을 초기화한다."""
        logger.info("=" * 60)
        logger.info("  KIS 자동 매매 솔루션 시작")
        logger.info("  모드: %s", self.config.mode.value)
        logger.info("  시장: %s", ", ".join(self.config.markets))
        logger.info("=" * 60)

        # KIS API 인증
        if self.config.mode != TradingMode.BACKTEST:
            self._provider.authenticate()

        # 스케줄 등록
        self._register_tasks()

    def _register_tasks(self) -> None:
        """스케줄 작업을 등록한다."""
        # 레짐 분석 (정규장 5분 간격)
        self._scheduler.register(
            "레짐 분석",
            self._run_regime_analysis,
            interval_seconds=300,
            market_states=[MarketState.REGULAR_OPEN],
        )

        # 포지션 동기화 (정규장 1분 간격)
        self._scheduler.register(
            "포지션 동기화",
            self._run_position_sync,
            interval_seconds=60,
            market_states=[MarketState.REGULAR_OPEN, MarketState.NXT_PRE_MARKET],
        )

        # 매도 조건 점검 (정규장 30초 간격)
        self._scheduler.register(
            "매도 조건 점검",
            self._run_exit_check,
            interval_seconds=30,
            market_states=[MarketState.REGULAR_OPEN],
        )

        # 장 시작/종료 이벤트
        self._scheduler.on_market_open(self._on_market_open)
        self._scheduler.on_market_close(self._on_market_close)

    # ─── 매매 루프 ──────────────────────────────────────────────

    async def run(self) -> None:
        """메인 매매 루프를 시작한다."""
        self.initialize()
        await self._scheduler.start()

    async def _on_market_open(self) -> None:
        """장 시작 이벤트 처리."""
        logger.info("=== 장 시작 ===")
        await self._notifier.notify("장 시작 — 자동매매 활성화")

        # 초기 레짐 분석
        await self._run_regime_analysis()
        # 포지션 동기화
        self._run_position_sync()

    async def _on_market_close(self) -> None:
        """장 종료 이벤트 처리."""
        logger.info("=== 장 종료 ===")

        # 일간 리포트 생성
        portfolio = self._position_manager.sync_positions()
        order_summary = self._order_manager.get_order_summary()

        report = (
            f"총 평가액: {portfolio.total_eval:,.0f}원\n"
            f"일간 손익: {portfolio.total_profit_loss:,.0f}원 ({portfolio.total_profit_rate:.2f}%)\n"
            f"현금 비중: {portfolio.cash_ratio:.1f}%\n"
            f"보유 종목: {len(portfolio.positions)}개\n"
            f"금일 주문: {order_summary['total']}건 (매수 {order_summary['buys']}, 매도 {order_summary['sells']})"
        )
        await self._notifier.notify_daily_report(report)

    async def _run_regime_analysis(self) -> None:
        """레짐 분석을 실행한다."""
        try:
            result = self._regime_analyzer.analyze()

            # 레짐 변경 감지
            if self._last_regime and self._last_regime != result.regime:
                await self._notifier.notify_regime_change(
                    self._last_regime.label_kr,
                    result.regime.label_kr,
                    result.confidence,
                )

                # 레짐 변경 시 전략 재실행
                if not self.config.paused:
                    await self._run_strategy(result.regime)

            self._last_regime = result.regime

        except Exception as e:
            logger.error("레짐 분석 오류: %s", e)
            await self._notifier.notify_error(f"레짐 분석 실패: {e}")

    async def _run_strategy(self, regime) -> None:
        """레짐에 맞는 전략을 실행한다."""
        # 활성 전략 선택
        active_strategy = None
        for strategy in self._strategies:
            if strategy.is_active_for(regime):
                active_strategy = strategy
                break

        if active_strategy is None:
            logger.warning("활성 전략 없음 (레짐: %s)", regime.label_kr)
            return

        logger.info("전략 실행: %s (레짐: %s)", active_strategy.name, regime.label_kr)

        # 유니버스 생성
        universe = self._stock_selector.get_universe()

        # 매수 신호 생성
        buy_signals = active_strategy.generate_signals(regime, universe, {})

        # 포트폴리오 확인 & 리밸런싱 계산
        portfolio = self._position_manager.sync_positions()
        target_ratio = active_strategy.get_target_equity_ratio(regime)
        rebalance_orders = self._position_manager.calculate_rebalance(
            buy_signals, portfolio, target_ratio,
        )

        # 리스크 검증 후 주문 실행
        for order in rebalance_orders:
            from auto_trader.execution.order_manager import OrderRequest, OrderSide, OrderType

            request = OrderRequest(
                ticker=order.ticker,
                side=OrderSide.BUY,
                quantity=order.quantity,
                order_type=OrderType.MARKET,
                reason=order.reason,
            )

            risk_check = self._risk_manager.check_order(request, portfolio)
            if not risk_check.passed:
                logger.warning("리스크 거부: %s — %s", order.ticker, risk_check.reason)
                continue

            result = self._order_manager.place_order(request)
            if result.order_no:
                # 매도 조건 설정
                exit_cond = active_strategy.get_exit_condition(regime)
                self._position_manager.set_exit_condition(order.ticker, exit_cond)
                await self._notifier.notify_trade(
                    f"매수: {order.ticker} {order.quantity}주 ({order.reason})"
                )

    def _run_position_sync(self) -> None:
        """포지션을 동기화한다."""
        try:
            self._position_manager.sync_positions()
        except Exception as e:
            logger.error("포지션 동기화 오류: %s", e)

    async def _run_exit_check(self) -> None:
        """매도 조건을 점검한다."""
        try:
            # 긴급 정지 확인
            portfolio = self._position_manager.sync_positions()
            should_stop, reason = self._risk_manager.should_emergency_stop(portfolio)
            if should_stop:
                self.config.paused = True
                await self._notifier.notify_emergency_stop(reason)
                return

            # 매도 신호 확인
            sell_signals = self._position_manager.check_exit_conditions()
            for signal in sell_signals:
                pos = self._position_manager.get_position(signal.ticker)
                if pos is None:
                    continue

                result = self._order_manager.place_sell(
                    ticker=signal.ticker,
                    quantity=pos.quantity,
                    reason=signal.reason,
                )
                if result.order_no:
                    await self._notifier.notify_trade(
                        f"매도: {signal.ticker} ({signal.name}) {pos.quantity}주 — {signal.reason}"
                    )

        except Exception as e:
            logger.error("매도 점검 오류: %s", e)

    # ─── 시스템 제어 ────────────────────────────────────────────

    def pause(self) -> None:
        """자동매매를 일시정지한다."""
        self.config.paused = True
        logger.info("자동매매 일시정지")

    def resume(self) -> None:
        """자동매매를 재개한다."""
        self.config.paused = False
        logger.info("자동매매 재개")

    def get_status(self) -> dict:
        """시스템 상태를 반환한다."""
        last_regime = self._regime_analyzer.last_result
        return {
            "mode": self.config.mode.value,
            "paused": self.config.paused,
            "uptime": self.uptime,
            "market_state": get_market_state().value,
            "regime": last_regime.regime.label_kr if last_regime else "분석 전",
            "regime_confidence": last_regime.confidence if last_regime else 0,
            "position_count": self._position_manager.position_count,
        }


# ─── CLI ────────────────────────────────────────────────────────


def run_backtest(config: Config, args) -> None:
    """백테스트를 실행한다."""
    from auto_trader.backtest.data_loader import BacktestDataLoader
    from auto_trader.backtest.engine import BacktestEngine
    from auto_trader.backtest.performance import PerformanceAnalyzer

    db_path = os.path.join(config.cache_dir, "historical.db")
    store = HistoricalDataStore(db_path)

    # API 연결이 있으면 데이터 수집 가능
    provider = DataProvider(config)
    market_data = MarketDataCollector(provider)
    try:
        provider.authenticate()
        loader = BacktestDataLoader(store, market_data)
    except Exception:
        loader = BacktestDataLoader(store)  # 캐시만 사용

    engine = BacktestEngine(loader, initial_capital=args.capital)

    # 전략 선택
    strategy_map = {
        "bull": BullStrategy(),
        "sideways": SidewaysStrategy(),
        "bear": BearStrategy(),
    }
    strategy = strategy_map.get(args.strategy, BullStrategy())

    # 유니버스 (기본: 시총 상위)
    tickers = args.tickers.split(",") if args.tickers else [
        "005930", "000660", "373220", "005380", "035420",
        "006400", "051910", "035720", "068270", "105560",
    ]

    result = engine.run(strategy, tickers, args.start, args.end)

    # 성과 분석
    analyzer = PerformanceAnalyzer()
    report = analyzer.analyze(result)
    print(PerformanceAnalyzer.format_report(report))


def main() -> None:
    """CLI 진입점."""
    parser = argparse.ArgumentParser(
        description="KIS 국내 주식 자동 매매 솔루션",
    )
    parser.add_argument(
        "--config", "-c",
        help="설정 파일 경로 (auto_trader_config.yaml)",
        default=None,
    )
    subparsers = parser.add_subparsers(dest="command", help="실행 명령")

    # trade 명령: 자동매매 실행
    trade_parser = subparsers.add_parser("trade", help="자동매매 실행")
    trade_parser.add_argument(
        "--mode", "-m",
        choices=["live", "paper"],
        default="paper",
        help="매매 모드 (기본: paper)",
    )

    # backtest 명령
    bt_parser = subparsers.add_parser("backtest", help="백테스트 실행")
    bt_parser.add_argument("--start", required=True, help="시작일 (YYYYMMDD)")
    bt_parser.add_argument("--end", required=True, help="종료일 (YYYYMMDD)")
    bt_parser.add_argument("--strategy", default="bull", help="전략 (bull/sideways/bear)")
    bt_parser.add_argument("--capital", type=float, default=100_000_000, help="초기 자본금")
    bt_parser.add_argument("--tickers", default="", help="종목코드 (쉼표 구분)")

    # status 명령
    subparsers.add_parser("status", help="시스템 상태 조회")

    args = parser.parse_args()
    config = load_config(args.config)
    setup_logging(config.log_level)

    if args.command == "backtest":
        config.mode = TradingMode.BACKTEST
        run_backtest(config, args)

    elif args.command == "trade":
        config.mode = TradingMode(args.mode)
        trader = AutoTrader(config)
        asyncio.run(trader.run())

    elif args.command == "status":
        print("자동매매 솔루션 상태 조회")
        print(f"  설정 파일: {args.config or '기본'}")
        print(f"  모드: {config.mode.value}")
        print(f"  시장: {', '.join(config.markets)}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
