# -*- coding: utf-8 -*-
"""포지션 관리 모듈.

보유 포지션 추적, 목표 비중 리밸런싱, 매도 조건 모니터링을 수행한다.
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from auto_trader.data.account_data import AccountDataCollector, Position, PortfolioSummary
from auto_trader.data.market_data import MarketDataCollector
from auto_trader.strategy.base import ExitCondition, SignalType, StockSignal
from auto_trader.utils.logger import get_logger

logger = get_logger("execution.position")


@dataclass
class TrackedPosition:
    """추적 중인 포지션 (보유 종목 + 전략 메타 정보)."""

    ticker: str
    name: str
    quantity: int
    avg_price: float
    current_price: float
    eval_amount: float
    profit_loss: float
    profit_rate: float  # %

    # 전략 메타 정보
    entry_date: datetime = field(default_factory=datetime.now)
    entry_reason: str = ""
    target_weight: float = 0.0
    exit_condition: ExitCondition = field(default_factory=ExitCondition)
    is_manual: bool = False

    # 트레일링 스탑 추적
    highest_price: float = 0.0  # 진입 이후 최고가

    @property
    def holding_days(self) -> int:
        """보유 일수."""
        return (datetime.now() - self.entry_date).days

    @property
    def trailing_drawdown(self) -> float:
        """최고가 대비 하락률."""
        if self.highest_price <= 0:
            return 0.0
        return (self.current_price - self.highest_price) / self.highest_price


@dataclass
class RebalanceOrder:
    """리밸런싱 주문 요청."""

    ticker: str
    signal: SignalType
    quantity: int
    reason: str


class PositionManager:
    """포지션 관리자.

    잔고 기반 포지션 추적, 리밸런싱 계산, 매도 조건 점검을 담당한다.
    """

    def __init__(
        self,
        account: AccountDataCollector,
        market_data: MarketDataCollector,
    ) -> None:
        self._account = account
        self._market_data = market_data
        self._tracked: dict[str, TrackedPosition] = {}

    # ─── 포지션 동기화 ──────────────────────────────────────────

    def sync_positions(self) -> PortfolioSummary:
        """KIS 잔고와 내부 추적 상태를 동기화한다.

        Returns:
            현재 PortfolioSummary.
        """
        portfolio = self._account.get_portfolio()

        # KIS 잔고에 있지만 추적 중이 아닌 종목 → 추적 시작
        kis_tickers = {p.ticker for p in portfolio.positions}
        for pos in portfolio.positions:
            if pos.ticker in self._tracked:
                # 기존 추적 종목: 현재가/수량만 갱신
                tracked = self._tracked[pos.ticker]
                tracked.quantity = pos.quantity
                tracked.current_price = pos.current_price
                tracked.eval_amount = pos.eval_amount
                tracked.profit_loss = pos.profit_loss
                tracked.profit_rate = pos.profit_rate
                # 최고가 갱신
                if pos.current_price > tracked.highest_price:
                    tracked.highest_price = pos.current_price
            else:
                # 새 종목: 추적 시작 (기존 보유 또는 매뉴얼 매매)
                self._tracked[pos.ticker] = TrackedPosition(
                    ticker=pos.ticker,
                    name=pos.name,
                    quantity=pos.quantity,
                    avg_price=pos.avg_price,
                    current_price=pos.current_price,
                    eval_amount=pos.eval_amount,
                    profit_loss=pos.profit_loss,
                    profit_rate=pos.profit_rate,
                    highest_price=max(pos.current_price, pos.avg_price),
                    is_manual=pos.is_manual,
                )

        # 추적 중이지만 KIS 잔고에 없는 종목 → 추적 제거 (매도 완료)
        for ticker in list(self._tracked.keys()):
            if ticker not in kis_tickers:
                logger.info("포지션 제거 (매도 완료): %s", ticker)
                del self._tracked[ticker]

        logger.info("포지션 동기화 완료: %d종목 추적 중", len(self._tracked))
        return portfolio

    # ─── 포지션 조회 ────────────────────────────────────────────

    @property
    def positions(self) -> dict[str, TrackedPosition]:
        """추적 중인 포지션 딕셔너리."""
        return self._tracked

    @property
    def position_count(self) -> int:
        """보유 종목 수."""
        return len(self._tracked)

    def get_position(self, ticker: str) -> TrackedPosition | None:
        """특정 종목 포지션을 반환한다."""
        return self._tracked.get(ticker)

    def has_position(self, ticker: str) -> bool:
        """특정 종목 보유 여부."""
        return ticker in self._tracked

    def get_total_eval(self) -> float:
        """보유 종목 총 평가액."""
        return sum(p.eval_amount for p in self._tracked.values())

    def get_positions_df(self) -> pd.DataFrame:
        """추적 포지션을 DataFrame으로 반환한다."""
        if not self._tracked:
            return pd.DataFrame()
        rows = []
        for p in self._tracked.values():
            rows.append({
                "ticker": p.ticker,
                "name": p.name,
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "profit_rate": p.profit_rate,
                "holding_days": p.holding_days,
                "target_weight": p.target_weight,
                "is_manual": p.is_manual,
            })
        return pd.DataFrame(rows)

    # ─── 매도 조건 점검 ─────────────────────────────────────────

    def check_exit_conditions(self) -> list[StockSignal]:
        """전체 포지션의 매도 조건을 점검한다.

        Returns:
            매도 신호 리스트.
        """
        sell_signals: list[StockSignal] = []

        for ticker, pos in self._tracked.items():
            if pos.is_manual:
                continue  # 매뉴얼 포지션은 자동 매도 제외

            ec = pos.exit_condition
            reason = ""

            # 1. 손절 (stop-loss)
            if ec.stop_loss_pct != 0 and (pos.profit_rate / 100) <= ec.stop_loss_pct:
                reason = f"손절 ({pos.profit_rate:.1f}% <= {ec.stop_loss_pct*100:.1f}%)"

            # 2. 익절 (take-profit)
            elif ec.take_profit_pct != 0 and (pos.profit_rate / 100) >= ec.take_profit_pct:
                reason = f"익절 ({pos.profit_rate:.1f}% >= {ec.take_profit_pct*100:.1f}%)"

            # 3. 트레일링 스탑
            elif ec.trailing_stop_pct != 0 and pos.trailing_drawdown <= -ec.trailing_stop_pct:
                reason = f"트레일링 스탑 ({pos.trailing_drawdown*100:.1f}%)"

            # 4. 최대 보유일 초과
            elif ec.max_holding_days > 0 and pos.holding_days >= ec.max_holding_days:
                reason = f"보유일 초과 ({pos.holding_days}일 >= {ec.max_holding_days}일)"

            if reason:
                logger.info("매도 신호 발생: %s (%s) — %s", ticker, pos.name, reason)
                sell_signals.append(StockSignal(
                    ticker=ticker,
                    name=pos.name,
                    signal=SignalType.SELL,
                    strength=1.0,
                    target_weight=0.0,
                    reason=reason,
                ))

        return sell_signals

    # ─── 리밸런싱 ───────────────────────────────────────────────

    def calculate_rebalance(
        self,
        buy_signals: list[StockSignal],
        portfolio: PortfolioSummary,
        target_equity_ratio: float,
    ) -> list[RebalanceOrder]:
        """매수 신호와 목표 비중을 바탕으로 리밸런싱 주문을 계산한다.

        Args:
            buy_signals: 매수 대상 신호.
            portfolio: 현재 포트폴리오 요약.
            target_equity_ratio: 목표 주식 비중 (0.0 ~ 1.0).

        Returns:
            리밸런싱 주문 리스트.
        """
        orders: list[RebalanceOrder] = []
        total_value = portfolio.total_eval
        if total_value <= 0:
            logger.warning("총 평가액이 0 이하 — 리밸런싱 불가")
            return orders

        target_equity_amount = total_value * target_equity_ratio
        current_equity_amount = total_value - portfolio.total_deposit

        # 신규 매수에 투입 가능한 금액
        available_for_buy = max(target_equity_amount - current_equity_amount, 0)
        available_cash = portfolio.total_deposit

        invest_amount = min(available_for_buy, available_cash)

        if invest_amount <= 0:
            logger.info("추가 매수 가능 금액 없음 (현금: %.0f, 목표 추가: %.0f)",
                        available_cash, available_for_buy)
            return orders

        # 이미 보유 중인 종목 제외
        new_signals = [s for s in buy_signals if not self.has_position(s.ticker)]
        if not new_signals:
            return orders

        per_stock_amount = invest_amount / len(new_signals)

        for signal in new_signals:
            # 현재가 조회하여 수량 계산
            try:
                price_df = self._market_data.get_stock_price(signal.ticker)
                if price_df.empty:
                    continue
                current_price = int(price_df.iloc[0].get("stck_prpr", 0))
                if current_price <= 0:
                    continue
            except Exception as e:
                logger.warning("현재가 조회 실패 (%s): %s", signal.ticker, e)
                continue

            quantity = int(per_stock_amount / current_price)
            if quantity <= 0:
                continue

            orders.append(RebalanceOrder(
                ticker=signal.ticker,
                signal=SignalType.BUY,
                quantity=quantity,
                reason=signal.reason,
            ))

        logger.info("리밸런싱 계산: %d건 매수 주문 생성 (투입 가능: %.0f원)",
                     len(orders), invest_amount)
        return orders

    # ─── 추적 메타 설정 ─────────────────────────────────────────

    def set_exit_condition(self, ticker: str, condition: ExitCondition) -> None:
        """종목의 매도 조건을 설정한다."""
        if ticker in self._tracked:
            self._tracked[ticker].exit_condition = condition

    def set_target_weight(self, ticker: str, weight: float) -> None:
        """종목의 목표 비중을 설정한다."""
        if ticker in self._tracked:
            self._tracked[ticker].target_weight = weight

    def mark_as_manual(self, ticker: str) -> None:
        """종목을 매뉴얼 매매로 표시한다 (자동 매도 제외)."""
        if ticker in self._tracked:
            self._tracked[ticker].is_manual = True
            logger.info("매뉴얼 포지션 설정: %s", ticker)
