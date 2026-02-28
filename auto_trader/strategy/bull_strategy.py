# -*- coding: utf-8 -*-
"""상승장 전략 (모멘텀/추세추종).

상승 레짐에서 활성화되며, 모멘텀이 강한 종목을 매수하고
추세가 꺾이면 매도하는 전략이다.
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

logger = get_logger("strategy.bull")


class BullStrategy(BaseStrategy):
    """상승장 전략.

    - 포지션 비중: 60~90%
    - 매수: 20일 이동평균 돌파, 거래량 동반 상승
    - 매도: 트레일링 스탑 5%, 손절 3%
    """

    def __init__(self) -> None:
        super().__init__(StrategyConfig(
            max_stocks=10,
            min_equity_ratio=0.60,
            max_equity_ratio=0.90,
        ))

    @property
    def name(self) -> str:
        return "상승장 모멘텀 전략"

    @property
    def target_regimes(self) -> list[MarketRegime]:
        return [MarketRegime.STRONG_BULL, MarketRegime.BULL]

    def generate_signals(
        self,
        regime: MarketRegime,
        universe: list[str],
        market_data: dict,
    ) -> list[StockSignal]:
        """모멘텀 기반 매수 신호를 생성한다."""
        signals: list[StockSignal] = []

        strength = 0.8 if regime == MarketRegime.STRONG_BULL else 0.6
        per_stock_weight = self.config.max_equity_ratio / self.config.max_stocks

        for ticker_info in universe[:self.config.max_stocks]:
            ticker = ticker_info if isinstance(ticker_info, str) else ticker_info.get("ticker", "")
            if not ticker:
                continue

            signals.append(StockSignal(
                ticker=ticker,
                name="",
                signal=SignalType.BUY,
                strength=strength,
                target_weight=per_stock_weight,
                reason="상승장 모멘텀 매수",
            ))

        logger.info("상승장 전략: %d개 매수 신호 생성", len(signals))
        return signals

    def get_exit_condition(self, regime: MarketRegime) -> ExitCondition:
        """상승장 매도 조건."""
        if regime == MarketRegime.STRONG_BULL:
            return ExitCondition(
                stop_loss_pct=-0.03,
                take_profit_pct=0.15,
                trailing_stop_pct=0.07,
            )
        return ExitCondition(
            stop_loss_pct=-0.03,
            take_profit_pct=0.10,
            trailing_stop_pct=0.05,
        )

    def get_target_equity_ratio(self, regime: MarketRegime) -> float:
        if regime == MarketRegime.STRONG_BULL:
            return 0.85
        return 0.70
