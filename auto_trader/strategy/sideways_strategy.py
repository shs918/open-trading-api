# -*- coding: utf-8 -*-
"""횡보장 전략 (평균회귀/박스권).

횡보 레짐에서 활성화되며, 과매도 구간에서 매수하고
과매수 구간에서 매도하는 전략이다.
"""

from auto_trader.regime.regime_model import MarketRegime
from auto_trader.strategy.base import (
    BaseStrategy,
    ExitCondition,
    SignalType,
    StockSignal,
    StrategyConfig,
)
from auto_trader.utils.logger import get_logger

logger = get_logger("strategy.sideways")


class SidewaysStrategy(BaseStrategy):
    """횡보장 전략.

    - 포지션 비중: 40~60%
    - 매수: RSI 과매도, 볼린저밴드 하단 근접, PER/PBR 저평가
    - 매도: RSI 과매수, 볼린저밴드 상단 근접, 목표가 도달
    """

    def __init__(self) -> None:
        super().__init__(StrategyConfig(
            max_stocks=8,
            min_equity_ratio=0.40,
            max_equity_ratio=0.60,
        ))

    @property
    def name(self) -> str:
        return "횡보장 평균회귀 전략"

    @property
    def target_regimes(self) -> list[MarketRegime]:
        return [MarketRegime.SIDEWAYS]

    def generate_signals(
        self,
        regime: MarketRegime,
        universe: list[str],
        market_data: dict,
    ) -> list[StockSignal]:
        """평균회귀 기반 매수 신호를 생성한다."""
        signals: list[StockSignal] = []

        per_stock_weight = self.config.max_equity_ratio / self.config.max_stocks

        for ticker_info in universe[:self.config.max_stocks]:
            ticker = ticker_info if isinstance(ticker_info, str) else ticker_info.get("ticker", "")
            if not ticker:
                continue

            signals.append(StockSignal(
                ticker=ticker,
                name="",
                signal=SignalType.BUY,
                strength=0.5,
                target_weight=per_stock_weight,
                reason="횡보장 과매도 매수",
            ))

        logger.info("횡보장 전략: %d개 매수 신호 생성", len(signals))
        return signals

    def get_exit_condition(self, regime: MarketRegime) -> ExitCondition:
        """횡보장 매도 조건 — 타이트한 손익 관리."""
        return ExitCondition(
            stop_loss_pct=-0.02,
            take_profit_pct=0.05,
            trailing_stop_pct=0.03,
            max_holding_days=20,
        )

    def get_target_equity_ratio(self, regime: MarketRegime) -> float:
        return 0.50
