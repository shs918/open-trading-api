# -*- coding: utf-8 -*-
"""리스크 관리 모듈.

주문 전 리스크 검증, 포지션 한도 관리, 모의→실전 전환 검증을 수행한다.
"""

from dataclasses import dataclass
from datetime import datetime

from auto_trader.config import Config, RiskConfig, TradingMode
from auto_trader.data.account_data import PortfolioSummary
from auto_trader.execution.order_manager import OrderRequest, OrderSide
from auto_trader.execution.position_manager import PositionManager
from auto_trader.utils.logger import get_logger

logger = get_logger("execution.risk")


@dataclass
class RiskCheckResult:
    """리스크 검증 결과."""

    passed: bool
    reason: str = ""


@dataclass
class PaperValidationResult:
    """모의투자 검증 결과."""

    passed: bool
    days_run: int = 0
    profit_rate: float = 0.0
    max_drawdown: float = 0.0
    reasons: list[str] | None = None

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []


class RiskManager:
    """리스크 관리자.

    주문 전 사전 검증, 포트폴리오 한도 확인, 모의→실전 전환 조건 판단을 수행한다.
    """

    def __init__(self, config: Config, position_manager: PositionManager) -> None:
        self._config = config
        self._risk: RiskConfig = config.risk
        self._position_mgr = position_manager

        # 세션 추적
        self._session_start = datetime.now()
        self._daily_loss: float = 0.0  # 당일 누적 실현 손실
        self._daily_order_count: int = 0

    # ─── 주문 전 리스크 검증 ────────────────────────────────────

    def check_order(
        self,
        request: OrderRequest,
        portfolio: PortfolioSummary,
    ) -> RiskCheckResult:
        """주문 전 리스크 검증을 수행한다.

        Args:
            request: 주문 요청.
            portfolio: 현재 포트폴리오 요약.

        Returns:
            RiskCheckResult.
        """
        # 매도 주문은 기본 통과 (보유 수량 내에서만 검증)
        if request.side == OrderSide.SELL:
            return self._check_sell_order(request)

        # 매수 주문 검증
        return self._check_buy_order(request, portfolio)

    def _check_buy_order(
        self,
        request: OrderRequest,
        portfolio: PortfolioSummary,
    ) -> RiskCheckResult:
        """매수 주문 리스크 검증."""

        # 1. 최대 보유 종목 수 확인
        if self._position_mgr.position_count >= self._risk.max_positions:
            return RiskCheckResult(
                passed=False,
                reason=f"최대 보유 종목 수 초과 ({self._position_mgr.position_count}/{self._risk.max_positions})",
            )

        # 2. 단일 종목 비중 한도 확인
        total_value = portfolio.total_eval
        if total_value > 0:
            order_amount = request.quantity * max(request.price, 1)
            existing = self._position_mgr.get_position(request.ticker)
            existing_amount = existing.eval_amount if existing else 0.0
            new_weight = (existing_amount + order_amount) / total_value

            if new_weight > self._risk.max_single_stock_weight:
                return RiskCheckResult(
                    passed=False,
                    reason=f"단일 종목 비중 한도 초과 ({new_weight*100:.1f}% > {self._risk.max_single_stock_weight*100:.0f}%)",
                )

        # 3. 건당 최대 손실 확인 (주문 금액 × 손절률 ≤ 포트폴리오 × max_loss_per_trade)
        if total_value > 0:
            order_amount = request.quantity * max(request.price, 1)
            potential_loss = order_amount * abs(self._risk.max_loss_per_trade)
            max_allowed_loss = total_value * self._risk.max_loss_per_trade

            if potential_loss > max_allowed_loss * 2:
                return RiskCheckResult(
                    passed=False,
                    reason=f"건당 잠재 손실 과다 (잠재손실: {potential_loss:,.0f} > 한도: {max_allowed_loss*2:,.0f})",
                )

        # 4. 포트폴리오 최대 손실 확인
        if portfolio.total_profit_rate < -(self._risk.max_portfolio_loss * 100):
            return RiskCheckResult(
                passed=False,
                reason=f"포트폴리오 최대 손실 도달 ({portfolio.total_profit_rate:.1f}%)",
            )

        # 5. 현금 잔고 확인
        order_amount = request.quantity * max(request.price, 1)
        if order_amount > portfolio.total_deposit:
            return RiskCheckResult(
                passed=False,
                reason=f"현금 부족 (주문: {order_amount:,.0f}, 예수금: {portfolio.total_deposit:,.0f})",
            )

        return RiskCheckResult(passed=True)

    def _check_sell_order(self, request: OrderRequest) -> RiskCheckResult:
        """매도 주문 리스크 검증."""
        pos = self._position_mgr.get_position(request.ticker)
        if pos is None:
            return RiskCheckResult(
                passed=False,
                reason=f"미보유 종목 매도 불가 ({request.ticker})",
            )
        if request.quantity > pos.quantity:
            return RiskCheckResult(
                passed=False,
                reason=f"매도 수량 초과 (요청: {request.quantity}, 보유: {pos.quantity})",
            )
        return RiskCheckResult(passed=True)

    # ─── 포지션 사이즈 계산 ─────────────────────────────────────

    def calculate_max_quantity(
        self,
        ticker: str,
        current_price: int,
        portfolio: PortfolioSummary,
    ) -> int:
        """종목의 최대 매수 가능 수량을 계산한다.

        리스크 한도를 고려한 최대 매수 수량을 반환한다.

        Args:
            ticker: 종목코드.
            current_price: 현재가.
            portfolio: 포트폴리오 요약.

        Returns:
            최대 매수 수량.
        """
        if current_price <= 0 or portfolio.total_eval <= 0:
            return 0

        # 단일 종목 비중 한도에 의한 최대 금액
        max_by_weight = portfolio.total_eval * self._risk.max_single_stock_weight
        existing = self._position_mgr.get_position(ticker)
        if existing:
            max_by_weight -= existing.eval_amount

        # 현금 잔고에 의한 최대 금액
        max_by_cash = portfolio.total_deposit

        # 건당 리스크에 의한 최대 금액 (손절 기준)
        max_by_risk = (portfolio.total_eval * self._risk.max_loss_per_trade) / abs(
            self._risk.max_loss_per_trade
        )

        max_amount = min(max_by_weight, max_by_cash, max_by_risk)
        max_quantity = int(max_amount / current_price)

        return max(max_quantity, 0)

    # ─── 일일 손실 추적 ─────────────────────────────────────────

    def record_realized_loss(self, amount: float) -> None:
        """실현 손실을 기록한다."""
        if amount < 0:
            self._daily_loss += abs(amount)

    def is_daily_loss_exceeded(self, portfolio: PortfolioSummary) -> bool:
        """일일 손실 한도 초과 여부를 확인한다."""
        if portfolio.total_eval <= 0:
            return False
        daily_loss_rate = self._daily_loss / portfolio.total_eval
        return daily_loss_rate >= self._risk.max_portfolio_loss

    # ─── 긴급 정지 ──────────────────────────────────────────────

    def should_emergency_stop(self, portfolio: PortfolioSummary) -> tuple[bool, str]:
        """긴급 정지 조건을 확인한다.

        Returns:
            (정지 여부, 사유).
        """
        # 포트폴리오 손실 한도 초과
        if portfolio.total_profit_rate < -(self._risk.max_portfolio_loss * 100):
            return True, f"포트폴리오 손실 한도 초과 ({portfolio.total_profit_rate:.1f}%)"

        # 일일 손실 한도 초과
        if self.is_daily_loss_exceeded(portfolio):
            daily_rate = (self._daily_loss / portfolio.total_eval * 100) if portfolio.total_eval > 0 else 0
            return True, f"일일 손실 한도 초과 ({daily_rate:.1f}%)"

        return False, ""

    # ─── 모의 → 실전 전환 검증 ──────────────────────────────────

    def validate_paper_to_live(
        self,
        paper_start_date: datetime,
        paper_profit_rate: float,
        paper_max_drawdown: float,
    ) -> PaperValidationResult:
        """모의투자 → 실전투자 전환 조건을 검증한다.

        Args:
            paper_start_date: 모의투자 시작일.
            paper_profit_rate: 모의투자 누적 수익률.
            paper_max_drawdown: 모의투자 최대 낙폭 (MDD).

        Returns:
            PaperValidationResult.
        """
        pv = self._config.paper_validation
        days_run = (datetime.now() - paper_start_date).days
        reasons: list[str] = []
        passed = True

        # 최소 운영 기간
        if days_run < pv.min_days:
            passed = False
            reasons.append(f"운영 기간 부족 ({days_run}일 / 최소 {pv.min_days}일)")

        # 최소 수익률
        if paper_profit_rate < pv.min_profit_rate:
            passed = False
            reasons.append(
                f"수익률 미달 ({paper_profit_rate:.1f}% < {pv.min_profit_rate:.1f}%)"
            )

        # 최대 MDD 확인
        if paper_max_drawdown > pv.max_mdd:
            passed = False
            reasons.append(
                f"MDD 초과 ({paper_max_drawdown*100:.1f}% > {pv.max_mdd*100:.1f}%)"
            )

        if passed:
            logger.info(
                "모의→실전 전환 검증 통과: %d일 운영, 수익률 %.1f%%, MDD %.1f%%",
                days_run,
                paper_profit_rate,
                paper_max_drawdown * 100,
            )
        else:
            logger.warning(
                "모의→실전 전환 검증 실패: %s",
                " / ".join(reasons),
            )

        return PaperValidationResult(
            passed=passed,
            days_run=days_run,
            profit_rate=paper_profit_rate,
            max_drawdown=paper_max_drawdown,
            reasons=reasons,
        )

    def can_switch_to_live(self) -> bool:
        """현재 모의투자 모드인지 확인한다."""
        return self._config.mode == TradingMode.PAPER

    # ─── 상태 조회 ──────────────────────────────────────────────

    def get_risk_summary(self, portfolio: PortfolioSummary) -> dict:
        """현재 리스크 상태 요약을 반환한다."""
        stop_needed, stop_reason = self.should_emergency_stop(portfolio)
        return {
            "mode": self._config.mode.value,
            "position_count": self._position_mgr.position_count,
            "max_positions": self._risk.max_positions,
            "portfolio_profit_rate": portfolio.total_profit_rate,
            "daily_loss": self._daily_loss,
            "max_single_weight": self._risk.max_single_stock_weight * 100,
            "trailing_stop_pct": self._risk.trailing_stop_pct * 100,
            "emergency_stop": stop_needed,
            "emergency_reason": stop_reason,
        }
