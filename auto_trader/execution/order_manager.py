# -*- coding: utf-8 -*-
"""주문 관리 모듈.

자동 매매 신호 및 매뉴얼 주문을 실행·추적·취소하는 기능을 제공한다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import pandas as pd

from auto_trader.data.provider import DataProvider
from auto_trader.strategy.base import SignalType, StockSignal
from auto_trader.utils.logger import get_logger

logger = get_logger("execution.order")


class OrderSide(Enum):
    """주문 방향."""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """주문 유형."""

    LIMIT = "00"  # 지정가
    MARKET = "01"  # 시장가
    CONDITIONAL = "02"  # 조건부지정가
    BEST_LIMIT = "03"  # 최유리지정가
    BEST_FIRST = "04"  # 최우선지정가
    PRE_MARKET = "07"  # 시간외단일가 (NXT 등)
    AFTER_MARKET = "08"  # 시간외종가


class OrderStatus(Enum):
    """주문 상태."""

    PENDING = "pending"  # 대기 (리스크 검증 전)
    SUBMITTED = "submitted"  # 제출됨 (API 전송 완료)
    FILLED = "filled"  # 체결 완료
    PARTIALLY_FILLED = "partially_filled"  # 부분 체결
    CANCELLED = "cancelled"  # 취소됨
    REJECTED = "rejected"  # 거부됨
    FAILED = "failed"  # 실패 (API 오류)


@dataclass
class OrderRequest:
    """주문 요청."""

    ticker: str
    side: OrderSide
    quantity: int
    price: int = 0  # 0 = 시장가
    order_type: OrderType = OrderType.MARKET
    market: str = "KRX"  # KRX / NXT
    reason: str = ""  # 주문 사유 (전략명, 매뉴얼 등)
    is_manual: bool = False  # 매뉴얼 주문 여부


@dataclass
class OrderResult:
    """주문 실행 결과."""

    ticker: str
    side: OrderSide
    quantity: int
    price: int
    status: OrderStatus
    order_no: str = ""  # KIS 주문번호
    message: str = ""  # 결과 메시지
    timestamp: datetime = field(default_factory=datetime.now)
    raw_response: pd.DataFrame = field(default_factory=pd.DataFrame)


class OrderManager:
    """주문 관리자.

    매매 신호를 실제 주문으로 변환하고, 주문 실행/취소/조회를 관리한다.
    """

    def __init__(self, provider: DataProvider) -> None:
        self._provider = provider
        self._order_history: list[OrderResult] = []

    # ─── 주문 실행 ──────────────────────────────────────────────

    def execute_signal(self, signal: StockSignal, quantity: int, price: int = 0) -> OrderResult:
        """전략 신호를 실제 주문으로 실행한다.

        Args:
            signal: 매매 신호.
            quantity: 주문 수량.
            price: 주문 가격 (0이면 시장가).

        Returns:
            OrderResult.
        """
        side = OrderSide.BUY if signal.signal == SignalType.BUY else OrderSide.SELL
        request = OrderRequest(
            ticker=signal.ticker,
            side=side,
            quantity=quantity,
            price=price,
            order_type=OrderType.MARKET if price == 0 else OrderType.LIMIT,
            reason=signal.reason,
        )
        return self.place_order(request)

    def place_order(self, request: OrderRequest) -> OrderResult:
        """주문을 실행한다.

        Args:
            request: 주문 요청.

        Returns:
            OrderResult.
        """
        logger.info(
            "주문 실행: %s %s %d주 @ %s (%s)",
            request.side.value,
            request.ticker,
            request.quantity,
            f"{request.price:,}" if request.price > 0 else "시장가",
            request.reason or ("매뉴얼" if request.is_manual else "자동"),
        )

        try:
            result_df = self._provider.place_order(
                ticker=request.ticker,
                side=request.side.value,
                quantity=request.quantity,
                price=request.price,
                order_type=request.order_type.value,
                market=request.market,
            )

            order_no = ""
            status = OrderStatus.SUBMITTED
            message = "주문 제출 완료"

            if not result_df.empty:
                row = result_df.iloc[0]
                order_no = str(row.get("odno", ""))
                if not order_no:
                    status = OrderStatus.FAILED
                    message = str(row.get("msg1", "주문번호 없음"))

            result = OrderResult(
                ticker=request.ticker,
                side=request.side,
                quantity=request.quantity,
                price=request.price,
                status=status,
                order_no=order_no,
                message=message,
                raw_response=result_df,
            )

        except Exception as e:
            logger.error("주문 실패 (%s %s): %s", request.side.value, request.ticker, e)
            result = OrderResult(
                ticker=request.ticker,
                side=request.side,
                quantity=request.quantity,
                price=request.price,
                status=OrderStatus.FAILED,
                message=str(e),
            )

        self._order_history.append(result)

        if result.status == OrderStatus.SUBMITTED:
            logger.info("주문 성공: %s (주문번호: %s)", request.ticker, result.order_no)
        else:
            logger.warning("주문 실패: %s — %s", request.ticker, result.message)

        return result

    def place_buy(
        self,
        ticker: str,
        quantity: int,
        price: int = 0,
        market: str = "KRX",
        reason: str = "",
        is_manual: bool = False,
    ) -> OrderResult:
        """매수 주문을 실행한다.

        Args:
            ticker: 종목코드.
            quantity: 매수 수량.
            price: 매수 가격 (0=시장가).
            market: 거래소 (KRX/NXT).
            reason: 주문 사유.
            is_manual: 매뉴얼 주문 여부.

        Returns:
            OrderResult.
        """
        return self.place_order(OrderRequest(
            ticker=ticker,
            side=OrderSide.BUY,
            quantity=quantity,
            price=price,
            order_type=OrderType.MARKET if price == 0 else OrderType.LIMIT,
            market=market,
            reason=reason,
            is_manual=is_manual,
        ))

    def place_sell(
        self,
        ticker: str,
        quantity: int,
        price: int = 0,
        market: str = "KRX",
        reason: str = "",
        is_manual: bool = False,
    ) -> OrderResult:
        """매도 주문을 실행한다.

        Args:
            ticker: 종목코드.
            quantity: 매도 수량.
            price: 매도 가격 (0=시장가).
            market: 거래소 (KRX/NXT).
            reason: 주문 사유.
            is_manual: 매뉴얼 주문 여부.

        Returns:
            OrderResult.
        """
        return self.place_order(OrderRequest(
            ticker=ticker,
            side=OrderSide.SELL,
            quantity=quantity,
            price=price,
            order_type=OrderType.MARKET if price == 0 else OrderType.LIMIT,
            market=market,
            reason=reason,
            is_manual=is_manual,
        ))

    # ─── 주문 취소 ──────────────────────────────────────────────

    def cancel_order(self, order_no: str, market: str = "KRX") -> OrderResult:
        """주문을 취소한다.

        Args:
            order_no: 원주문번호.
            market: 거래소 구분.

        Returns:
            OrderResult.
        """
        logger.info("주문 취소 요청: %s", order_no)

        try:
            result_df = self._provider.cancel_order(
                order_no=order_no,
                market=market,
            )

            status = OrderStatus.CANCELLED
            message = "취소 완료"

            if result_df.empty:
                status = OrderStatus.FAILED
                message = "취소 응답 없음"

            result = OrderResult(
                ticker="",
                side=OrderSide.SELL,
                quantity=0,
                price=0,
                status=status,
                order_no=order_no,
                message=message,
                raw_response=result_df,
            )

        except Exception as e:
            logger.error("주문 취소 실패 (%s): %s", order_no, e)
            result = OrderResult(
                ticker="",
                side=OrderSide.SELL,
                quantity=0,
                price=0,
                status=OrderStatus.FAILED,
                order_no=order_no,
                message=str(e),
            )

        return result

    # ─── 체결 내역 조회 ─────────────────────────────────────────

    def get_daily_executions(
        self,
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame:
        """일별 체결 내역을 조회한다.

        Args:
            start_date: 조회 시작일 (YYYYMMDD). 비어 있으면 오늘.
            end_date: 조회 종료일 (YYYYMMDD). 비어 있으면 오늘.

        Returns:
            체결 내역 DataFrame.
        """
        if not start_date:
            start_date = datetime.now().strftime("%Y%m%d")
        if not end_date:
            end_date = start_date

        try:
            self._provider._ensure_auth()
            from domestic_stock.inquire_daily_ccld.inquire_daily_ccld import (
                inquire_daily_ccld,
            )

            trenv = self._provider._trenv
            output1, output2 = inquire_daily_ccld(
                env_dv=self._provider._env_dv,
                pd_dv="inner",
                cano=trenv.my_acct,
                acnt_prdt_cd=trenv.my_prod,
                inqr_strt_dt=start_date,
                inqr_end_dt=end_date,
                sll_buy_dvsn_cd="00",
                ccld_dvsn="01",
                inqr_dvsn="00",
                inqr_dvsn_3="00",
            )
            return output1
        except Exception as e:
            logger.error("일별 체결 내역 조회 실패: %s", e)
            return pd.DataFrame()

    # ─── 실현 손익 ──────────────────────────────────────────────

    def get_realized_pnl(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """실현 손익을 조회한다.

        Returns:
            (종목별 실현 손익, 요약) DataFrame 튜플.
        """
        try:
            self._provider._ensure_auth()
            from domestic_stock.inquire_balance_rlz_pl.inquire_balance_rlz_pl import (
                inquire_balance_rlz_pl,
            )

            trenv = self._provider._trenv
            return inquire_balance_rlz_pl(
                cano=trenv.my_acct,
                acnt_prdt_cd=trenv.my_prod,
                afhr_flpr_yn="N",
                inqr_dvsn="02",
                unpr_dvsn="01",
                fund_sttl_icld_yn="N",
                fncg_amt_auto_rdpt_yn="N",
                prcs_dvsn="00",
            )
        except Exception as e:
            logger.error("실현 손익 조회 실패: %s", e)
            return pd.DataFrame(), pd.DataFrame()

    # ─── 주문 이력 ──────────────────────────────────────────────

    @property
    def order_history(self) -> list[OrderResult]:
        """세션 내 주문 이력."""
        return self._order_history

    def get_today_orders(self) -> list[OrderResult]:
        """오늘의 주문 이력을 반환한다."""
        today = datetime.now().date()
        return [o for o in self._order_history if o.timestamp.date() == today]

    def get_order_summary(self) -> dict:
        """주문 요약 통계를 반환한다."""
        today_orders = self.get_today_orders()
        buys = [o for o in today_orders if o.side == OrderSide.BUY]
        sells = [o for o in today_orders if o.side == OrderSide.SELL]
        submitted = [o for o in today_orders if o.status == OrderStatus.SUBMITTED]
        failed = [o for o in today_orders if o.status == OrderStatus.FAILED]
        return {
            "total": len(today_orders),
            "buys": len(buys),
            "sells": len(sells),
            "submitted": len(submitted),
            "failed": len(failed),
        }
