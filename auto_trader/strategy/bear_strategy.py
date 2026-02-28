# -*- coding: utf-8 -*-
"""하락장 전략 (방어/현금확대).

하락 레짐에서 활성화되며, 방어주 위주로 보수적 포지션을 유지하고
현금 비중을 확대하는 전략이다.
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

logger = get_logger("strategy.bear")


class BearStrategy(BaseStrategy):
    """하락장 전략.

    - 포지션 비중: 0~40%
    - 매수: 고배당주, 방어적 업종 (필수소비재, 통신, 유틸리티)
    - 매도: 타이트한 손절 (2%), 빠른 이익실현
    - 강한 하락 시: 대부분 현금, 인버스 ETF 고려
    """

    def __init__(self) -> None:
        super().__init__(StrategyConfig(
            max_stocks=5,
            min_equity_ratio=0.0,
            max_equity_ratio=0.40,
        ))

    @property
    def name(self) -> str:
        return "하락장 방어 전략"

    @property
    def target_regimes(self) -> list[MarketRegime]:
        return [MarketRegime.BEAR, MarketRegime.STRONG_BEAR]

    def generate_signals(
        self,
        regime: MarketRegime,
        universe: list[str],
        market_data: dict,
    ) -> list[StockSignal]:
        """방어주 기반 매수 신호를 생성한다."""
        signals: list[StockSignal] = []

        if regime == MarketRegime.STRONG_BEAR:
            # 강한 하락: 매수 신호 최소화, 대부분 현금 보유
            max_buy = 2
            strength = 0.3
        else:
            max_buy = self.config.max_stocks
            strength = 0.4

        per_stock_weight = self.config.max_equity_ratio / max(max_buy, 1)

        for ticker_info in universe[:max_buy]:
            ticker = ticker_info if isinstance(ticker_info, str) else ticker_info.get("ticker", "")
            if not ticker:
                continue

            signals.append(StockSignal(
                ticker=ticker,
                name="",
                signal=SignalType.BUY,
                strength=strength,
                target_weight=per_stock_weight,
                reason="하락장 방어주 매수",
            ))

        logger.info("하락장 전략: %d개 매수 신호 생성 (레짐: %s)", len(signals), regime.label_kr)
        return signals

    def get_exit_condition(self, regime: MarketRegime) -> ExitCondition:
        """하락장 매도 조건 — 매우 타이트한 손절."""
        if regime == MarketRegime.STRONG_BEAR:
            return ExitCondition(
                stop_loss_pct=-0.015,
                take_profit_pct=0.03,
                trailing_stop_pct=0.02,
                max_holding_days=10,
            )
        return ExitCondition(
            stop_loss_pct=-0.02,
            take_profit_pct=0.05,
            trailing_stop_pct=0.03,
            max_holding_days=15,
        )

    def get_target_equity_ratio(self, regime: MarketRegime) -> float:
        if regime == MarketRegime.STRONG_BEAR:
            return 0.10
        return 0.30
