# -*- coding: utf-8 -*-
"""마켓 레짐 분석 오케스트레이터.

데이터 수집 → 거시/미시 지표 계산 → 레짐 분류를 일관된 흐름으로 실행한다.
"""

from auto_trader.data.market_data import MarketDataCollector
from auto_trader.regime.macro_indicators import MacroIndicators
from auto_trader.regime.micro_indicators import MicroIndicators
from auto_trader.regime.regime_model import RegimeModel, RegimeResult
from auto_trader.utils.logger import get_logger

logger = get_logger("regime.analyzer")


class RegimeAnalyzer:
    """마켓 레짐 분석기.

    시장 데이터를 수집하고, 거시/미시 지표를 산출한 후,
    복합 판단 모델로 현재 시장 국면을 결정한다.
    """

    def __init__(
        self,
        market_data: MarketDataCollector,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._market_data = market_data
        self._macro = MacroIndicators()
        self._micro = MicroIndicators()
        self._model = RegimeModel(weights)
        self._last_result: RegimeResult | None = None

    @property
    def last_result(self) -> RegimeResult | None:
        """마지막 분석 결과."""
        return self._last_result

    def analyze(self) -> RegimeResult:
        """마켓 레짐을 분석한다.

        데이터 수집 → 지표 계산 → 레짐 분류 순서로 실행.

        Returns:
            RegimeResult.
        """
        logger.info("마켓 레짐 분석 시작")

        # 1. 데이터 수집
        regime_data = self._market_data.collect_regime_data()

        # 2. 거시 지표 계산
        macro_scores = self._macro.calculate(regime_data)

        # 3. 미시 지표 계산
        micro_scores = self._micro.calculate(regime_data)

        # 4. 레짐 분류
        result = self._model.classify(macro_scores, micro_scores)

        self._last_result = result
        logger.info(
            "마켓 레짐 분석 완료: %s (신뢰도 %.1f%%)",
            result.regime.label_kr,
            result.confidence,
        )
        return result

    def has_regime_changed(self, new_result: RegimeResult) -> bool:
        """레짐이 이전과 변경되었는지 확인한다.

        Args:
            new_result: 새로운 분석 결과.

        Returns:
            레짐 변경 여부.
        """
        if self._last_result is None:
            return True
        return self._last_result.regime != new_result.regime
