# -*- coding: utf-8 -*-
"""백테스트 엔진.

과거 데이터로 전략을 시뮬레이션하여 수익률·위험 지표를 산출한다.
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from auto_trader.backtest.data_loader import BacktestDataLoader
from auto_trader.regime.regime_model import MarketRegime
from auto_trader.strategy.base import (
    BaseStrategy,
    ExitCondition,
    SignalType,
    StockSignal,
)
from auto_trader.utils.logger import get_logger

logger = get_logger("backtest.engine")


@dataclass
class BacktestTrade:
    """백테스트 개별 거래."""

    ticker: str
    side: str  # "buy" / "sell"
    date: str  # YYYYMMDD
    price: float
    quantity: int
    reason: str = ""


@dataclass
class BacktestPosition:
    """백테스트 시뮬레이션 포지션."""

    ticker: str
    quantity: int
    avg_price: float
    entry_date: str
    exit_condition: ExitCondition = field(default_factory=ExitCondition)
    highest_price: float = 0.0

    @property
    def holding_days_from(self) -> str:
        return self.entry_date


@dataclass
class DailySnapshot:
    """일별 포트폴리오 스냅샷."""

    date: str
    total_value: float  # 총 평가액
    cash: float
    equity_value: float  # 주식 평가액
    daily_return: float = 0.0  # 일간 수익률


@dataclass
class BacktestResult:
    """백테스트 결과."""

    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    total_return: float  # 누적 수익률 (%)
    trades: list[BacktestTrade] = field(default_factory=list)
    daily_snapshots: list[DailySnapshot] = field(default_factory=list)
    strategy_name: str = ""


class BacktestEngine:
    """백테스트 엔진.

    과거 데이터를 날짜순으로 순회하면서 전략의 매매 신호를 시뮬레이션한다.
    """

    def __init__(
        self,
        data_loader: BacktestDataLoader,
        initial_capital: float = 100_000_000,  # 1억 원
    ) -> None:
        self._loader = data_loader
        self._initial_capital = initial_capital

    def run(
        self,
        strategy: BaseStrategy,
        tickers: list[str],
        start_date: str,
        end_date: str,
        benchmark_code: str = "0001",
    ) -> BacktestResult:
        """백테스트를 실행한다.

        Args:
            strategy: 실행할 전략.
            tickers: 유니버스 종목 리스트.
            start_date: 시작일 (YYYYMMDD).
            end_date: 종료일 (YYYYMMDD).
            benchmark_code: 벤치마크 지수코드 (기본 KOSPI).

        Returns:
            BacktestResult.
        """
        logger.info(
            "백테스트 시작: %s (%s ~ %s, %d종목, 자본금 %.0f)",
            strategy.name, start_date, end_date, len(tickers), self._initial_capital,
        )

        # 1. 데이터 로드
        stock_data = self._loader.preload_stocks(tickers, start_date, end_date)
        index_data = self._loader.load_index(benchmark_code, start_date, end_date)

        if not stock_data:
            logger.error("백테스트 데이터 없음")
            return BacktestResult(
                start_date=start_date,
                end_date=end_date,
                initial_capital=self._initial_capital,
                final_value=self._initial_capital,
                total_return=0.0,
                strategy_name=strategy.name,
            )

        # 2. 날짜 리스트 생성 (모든 종목의 거래일 합집합)
        all_dates = set()
        for df in stock_data.values():
            if "date" in df.columns:
                all_dates.update(df["date"].tolist())
        trading_dates = sorted(all_dates)

        if not trading_dates:
            logger.error("거래일 데이터 없음")
            return BacktestResult(
                start_date=start_date,
                end_date=end_date,
                initial_capital=self._initial_capital,
                final_value=self._initial_capital,
                total_return=0.0,
                strategy_name=strategy.name,
            )

        # 3. 시뮬레이션 상태 초기화
        cash = self._initial_capital
        positions: dict[str, BacktestPosition] = {}
        trades: list[BacktestTrade] = []
        snapshots: list[DailySnapshot] = []
        prev_total = self._initial_capital

        # 4. 날짜별 시뮬레이션
        for date in trading_dates:
            # 당일 종가 딕셔너리
            prices = self._get_prices_for_date(stock_data, date)
            if not prices:
                continue

            # 지수 기반 레짐 추정 (간소화: 지수 추세로 판단)
            regime = self._estimate_regime(index_data, date)

            # 포지션 최고가 갱신
            for ticker, pos in positions.items():
                if ticker in prices and prices[ticker] > pos.highest_price:
                    pos.highest_price = prices[ticker]

            # 매도 조건 점검
            sell_signals = self._check_exits(positions, prices, date, strategy, regime)
            for signal in sell_signals:
                pos = positions.get(signal.ticker)
                if pos is None:
                    continue
                sell_price = prices.get(signal.ticker, pos.avg_price)
                cash += sell_price * pos.quantity
                trades.append(BacktestTrade(
                    ticker=signal.ticker,
                    side="sell",
                    date=date,
                    price=sell_price,
                    quantity=pos.quantity,
                    reason=signal.reason,
                ))
                del positions[signal.ticker]

            # 매수 신호 생성 (전략이 해당 레짐에 활성화된 경우)
            if strategy.is_active_for(regime):
                available_tickers = [t for t in tickers if t not in positions and t in prices]
                buy_signals = strategy.generate_signals(regime, available_tickers, {})

                target_equity_ratio = strategy.get_target_equity_ratio(regime)
                equity_value = sum(
                    prices.get(t, p.avg_price) * p.quantity
                    for t, p in positions.items()
                )
                total_value = cash + equity_value
                target_equity_amount = total_value * target_equity_ratio
                available_for_buy = max(target_equity_amount - equity_value, 0)
                invest_per_stock = available_for_buy / max(len(buy_signals), 1)

                for signal in buy_signals:
                    if signal.signal != SignalType.BUY:
                        continue
                    price = prices.get(signal.ticker, 0)
                    if price <= 0:
                        continue
                    qty = int(min(invest_per_stock, cash) / price)
                    if qty <= 0:
                        continue

                    cost = price * qty
                    if cost > cash:
                        continue

                    cash -= cost
                    exit_cond = strategy.get_exit_condition(regime)
                    positions[signal.ticker] = BacktestPosition(
                        ticker=signal.ticker,
                        quantity=qty,
                        avg_price=price,
                        entry_date=date,
                        exit_condition=exit_cond,
                        highest_price=price,
                    )
                    trades.append(BacktestTrade(
                        ticker=signal.ticker,
                        side="buy",
                        date=date,
                        price=price,
                        quantity=qty,
                        reason=signal.reason,
                    ))

            # 일별 스냅샷
            equity_value = sum(
                prices.get(t, p.avg_price) * p.quantity
                for t, p in positions.items()
            )
            total_value = cash + equity_value
            daily_return = (total_value - prev_total) / prev_total if prev_total > 0 else 0
            snapshots.append(DailySnapshot(
                date=date,
                total_value=total_value,
                cash=cash,
                equity_value=equity_value,
                daily_return=daily_return,
            ))
            prev_total = total_value

        # 5. 최종 결과 계산
        final_value = snapshots[-1].total_value if snapshots else self._initial_capital
        total_return = ((final_value - self._initial_capital) / self._initial_capital) * 100

        logger.info(
            "백테스트 완료: 수익률 %.2f%%, 거래 %d건, 최종 자산 %.0f",
            total_return, len(trades), final_value,
        )

        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self._initial_capital,
            final_value=final_value,
            total_return=total_return,
            trades=trades,
            daily_snapshots=snapshots,
            strategy_name=strategy.name,
        )

    # ─── 내부 헬퍼 ──────────────────────────────────────────────

    @staticmethod
    def _get_prices_for_date(
        stock_data: dict[str, pd.DataFrame],
        date: str,
    ) -> dict[str, float]:
        """특정 날짜의 종목별 종가를 반환한다."""
        prices: dict[str, float] = {}
        for ticker, df in stock_data.items():
            row = df[df["date"] == date]
            if not row.empty:
                close = float(row.iloc[0].get("close", 0))
                if close > 0:
                    prices[ticker] = close
        return prices

    @staticmethod
    def _estimate_regime(index_data: pd.DataFrame, current_date: str) -> MarketRegime:
        """지수 데이터로 레짐을 간이 추정한다.

        20일 이동평균 vs 60일 이동평균 비교로 간소화.
        """
        if index_data.empty or "date" not in index_data.columns:
            return MarketRegime.SIDEWAYS

        past = index_data[index_data["date"] <= current_date].tail(60)
        if len(past) < 20:
            return MarketRegime.SIDEWAYS

        closes = pd.to_numeric(past["close"], errors="coerce")
        ma20 = closes.tail(20).mean()
        ma60 = closes.mean()

        if ma20 <= 0 or ma60 <= 0:
            return MarketRegime.SIDEWAYS

        ratio = ma20 / ma60

        if ratio > 1.03:
            return MarketRegime.STRONG_BULL
        elif ratio > 1.01:
            return MarketRegime.BULL
        elif ratio < 0.97:
            return MarketRegime.STRONG_BEAR
        elif ratio < 0.99:
            return MarketRegime.BEAR
        else:
            return MarketRegime.SIDEWAYS

    @staticmethod
    def _check_exits(
        positions: dict[str, BacktestPosition],
        prices: dict[str, float],
        current_date: str,
        strategy: BaseStrategy,
        regime: MarketRegime,
    ) -> list[StockSignal]:
        """포지션 매도 조건을 점검한다."""
        sell_signals: list[StockSignal] = []

        for ticker, pos in list(positions.items()):
            price = prices.get(ticker)
            if price is None:
                continue

            ec = pos.exit_condition
            profit_rate = (price - pos.avg_price) / pos.avg_price

            reason = ""

            # 손절
            if ec.stop_loss_pct != 0 and profit_rate <= ec.stop_loss_pct:
                reason = f"손절 ({profit_rate*100:.1f}%)"

            # 익절
            elif ec.take_profit_pct != 0 and profit_rate >= ec.take_profit_pct:
                reason = f"익절 ({profit_rate*100:.1f}%)"

            # 트레일링 스탑
            elif ec.trailing_stop_pct != 0 and pos.highest_price > 0:
                drawdown = (price - pos.highest_price) / pos.highest_price
                if drawdown <= -ec.trailing_stop_pct:
                    reason = f"트레일링 스탑 ({drawdown*100:.1f}%)"

            # 최대 보유일
            elif ec.max_holding_days > 0:
                try:
                    entry = datetime.strptime(pos.entry_date, "%Y%m%d")
                    now = datetime.strptime(current_date, "%Y%m%d")
                    if (now - entry).days >= ec.max_holding_days:
                        reason = f"보유일 초과 ({(now - entry).days}일)"
                except ValueError:
                    pass

            if reason:
                sell_signals.append(StockSignal(
                    ticker=ticker,
                    name="",
                    signal=SignalType.SELL,
                    strength=1.0,
                    target_weight=0.0,
                    reason=reason,
                ))

        return sell_signals
