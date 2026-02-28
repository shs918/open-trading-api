# -*- coding: utf-8 -*-
"""계좌/잔고/손익 조회 모듈.

DataProvider를 활용하여 계좌 관련 데이터를 수집/가공한다.
"""

from dataclasses import dataclass, field

import pandas as pd

from auto_trader.data.provider import DataProvider
from auto_trader.utils.logger import get_logger

logger = get_logger("data.account_data")


@dataclass
class Position:
    """개별 포지션 정보."""

    ticker: str  # 종목코드
    name: str  # 종목명
    quantity: int  # 보유수량
    avg_price: float  # 평균매입가
    current_price: float  # 현재가
    eval_amount: float  # 평가금액
    profit_loss: float  # 평가손익
    profit_rate: float  # 수익률 (%)
    is_manual: bool = False  # 매뉴얼 매매 여부


@dataclass
class PortfolioSummary:
    """포트폴리오 요약 정보."""

    total_eval: float = 0.0  # 총 평가금액
    total_deposit: float = 0.0  # 예수금
    total_profit_loss: float = 0.0  # 총 평가손익
    total_profit_rate: float = 0.0  # 총 수익률 (%)
    cash_ratio: float = 0.0  # 현금 비중 (%)
    positions: list[Position] = field(default_factory=list)


class AccountDataCollector:
    """계좌 데이터 수집기."""

    def __init__(self, provider: DataProvider) -> None:
        self._provider = provider

    def get_portfolio(self) -> PortfolioSummary:
        """현재 포트폴리오 요약 정보를 반환한다.

        Returns:
            PortfolioSummary 인스턴스.
        """
        try:
            positions_df, summary_df = self._provider.get_balance()
        except Exception as e:
            logger.error("잔고 조회 실패: %s", e)
            return PortfolioSummary()

        positions: list[Position] = []
        if not positions_df.empty:
            for _, row in positions_df.iterrows():
                qty = int(row.get("hldg_qty", 0))
                if qty <= 0:
                    continue
                positions.append(
                    Position(
                        ticker=str(row.get("pdno", "")),
                        name=str(row.get("prdt_name", "")),
                        quantity=qty,
                        avg_price=float(row.get("pchs_avg_pric", 0)),
                        current_price=float(row.get("prpr", 0)),
                        eval_amount=float(row.get("evlu_amt", 0)),
                        profit_loss=float(row.get("evlu_pfls_amt", 0)),
                        profit_rate=float(row.get("evlu_pfls_rt", 0)),
                    )
                )

        total_eval = 0.0
        total_deposit = 0.0
        total_profit_loss = 0.0
        total_profit_rate = 0.0

        if not summary_df.empty:
            row = summary_df.iloc[0]
            total_eval = float(row.get("tot_evlu_amt", 0))
            total_deposit = float(row.get("dnca_tot_amt", 0))
            total_profit_loss = float(row.get("evlu_pfls_smtl_amt", 0))
            purchase_total = float(row.get("pchs_amt_smtl_amt", 0))
            if purchase_total > 0:
                total_profit_rate = (total_profit_loss / purchase_total) * 100

        cash_ratio = 0.0
        if total_eval > 0:
            cash_ratio = (total_deposit / total_eval) * 100

        summary = PortfolioSummary(
            total_eval=total_eval,
            total_deposit=total_deposit,
            total_profit_loss=total_profit_loss,
            total_profit_rate=total_profit_rate,
            cash_ratio=cash_ratio,
            positions=positions,
        )
        logger.info(
            "포트폴리오 조회 완료: 평가액=%.0f, 손익=%.0f(%.2f%%), 현금비중=%.1f%%",
            total_eval,
            total_profit_loss,
            total_profit_rate,
            cash_ratio,
        )
        return summary

    def get_positions_df(self) -> pd.DataFrame:
        """보유 종목을 DataFrame으로 반환한다.

        Returns:
            보유종목 DataFrame (종목코드, 종목명, 수량, 매입가, 현재가, 손익).
        """
        portfolio = self.get_portfolio()
        if not portfolio.positions:
            return pd.DataFrame()

        rows = []
        for p in portfolio.positions:
            rows.append({
                "ticker": p.ticker,
                "name": p.name,
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "eval_amount": p.eval_amount,
                "profit_loss": p.profit_loss,
                "profit_rate": p.profit_rate,
            })
        return pd.DataFrame(rows)

    def get_executed_orders(self) -> pd.DataFrame:
        """당일 체결 내역을 조회한다.

        Returns:
            체결 내역 DataFrame.
        """
        try:
            return self._provider.get_inquire_ccnl()
        except Exception as e:
            logger.error("체결 내역 조회 실패: %s", e)
            return pd.DataFrame()

    def get_buyable_amount(self, ticker: str) -> pd.DataFrame:
        """종목의 매수 가능 수량/금액을 조회한다.

        Args:
            ticker: 종목코드.

        Returns:
            매수 가능 조회 DataFrame.
        """
        try:
            return self._provider.get_psbl_order(ticker)
        except Exception as e:
            logger.error("매수가능 조회 실패 (%s): %s", ticker, e)
            return pd.DataFrame()

    def get_sellable_amount(self, ticker: str) -> pd.DataFrame:
        """종목의 매도 가능 수량을 조회한다.

        Args:
            ticker: 종목코드.

        Returns:
            매도 가능 조회 DataFrame.
        """
        try:
            return self._provider.get_psbl_sell(ticker)
        except Exception as e:
            logger.error("매도가능 조회 실패 (%s): %s", ticker, e)
            return pd.DataFrame()
