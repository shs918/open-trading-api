# -*- coding: utf-8 -*-
"""마켓 레짐 분류 모델.

거시/미시 지표 점수를 가중 합산하여 시장 국면(레짐)을 판단한다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from auto_trader.utils.logger import get_logger

logger = get_logger("regime.model")


class MarketRegime(Enum):
    """시장 국면 분류."""

    STRONG_BULL = "strong_bull"  # 강한 상승
    BULL = "bull"  # 상승
    SIDEWAYS = "sideways"  # 횡보
    BEAR = "bear"  # 하락
    STRONG_BEAR = "strong_bear"  # 강한 하락

    @property
    def label_kr(self) -> str:
        """한국어 라벨."""
        labels = {
            "strong_bull": "강한 상승",
            "bull": "상승",
            "sideways": "횡보",
            "bear": "하락",
            "strong_bear": "강한 하락",
        }
        return labels[self.value]


@dataclass
class RegimeResult:
    """레짐 분석 결과."""

    regime: MarketRegime
    confidence: float  # 신뢰도 (0~100%)
    composite_score: float  # 복합 점수 (-2 ~ +2)
    scores: dict[str, float] = field(default_factory=dict)  # 개별 지표 점수
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# 기본 가중치 설정
DEFAULT_WEIGHTS = {
    "kospi_trend": 0.25,  # KOSPI 추세 방향
    "kospi_momentum": 0.10,  # KOSPI 모멘텀
    "foreign_flow": 0.10,  # 외국인 수급
    "institution_flow": 0.10,  # 기관 수급
    "trading_volume": 0.10,  # 거래대금
    "volatility": 0.10,  # 변동성
    "new_highlow": 0.10,  # 신고가/신저가
    "short_selling": 0.05,  # 공매도
    "disparity": 0.05,  # 이격도
    "rsi": 0.05,  # RSI
}


def classify_regime(composite_score: float) -> tuple[MarketRegime, float]:
    """복합 점수를 기반으로 레짐을 분류한다.

    Args:
        composite_score: 가중 합산 점수 (-2 ~ +2).

    Returns:
        (레짐, 신뢰도) 튜플.
    """
    if composite_score >= 1.2:
        regime = MarketRegime.STRONG_BULL
        confidence = min((composite_score - 1.2) / 0.8 * 50 + 50, 100)
    elif composite_score >= 0.4:
        regime = MarketRegime.BULL
        confidence = min((composite_score - 0.4) / 0.8 * 50 + 50, 100)
    elif composite_score >= -0.4:
        regime = MarketRegime.SIDEWAYS
        confidence = max(50 - abs(composite_score) / 0.4 * 20, 30)
    elif composite_score >= -1.2:
        regime = MarketRegime.BEAR
        confidence = min((-composite_score - 0.4) / 0.8 * 50 + 50, 100)
    else:
        regime = MarketRegime.STRONG_BEAR
        confidence = min((-composite_score - 1.2) / 0.8 * 50 + 50, 100)

    return regime, round(confidence, 1)


class RegimeModel:
    """레짐 분류 모델.

    개별 지표 점수를 가중 합산하여 시장 국면을 결정한다.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or DEFAULT_WEIGHTS.copy()

    def classify(
        self,
        macro_scores: dict[str, float],
        micro_scores: dict[str, float],
    ) -> RegimeResult:
        """거시/미시 지표를 종합하여 레짐을 결정한다.

        Args:
            macro_scores: 거시 지표 점수.
            micro_scores: 미시 지표 점수.

        Returns:
            RegimeResult.
        """
        all_scores = {**macro_scores, **micro_scores}

        # 가중 합산
        composite = 0.0
        total_weight = 0.0
        for indicator, weight in self._weights.items():
            if indicator in all_scores:
                composite += all_scores[indicator] * weight
                total_weight += weight

        # 가중치 정규화
        if total_weight > 0:
            composite = composite / total_weight

        regime, confidence = classify_regime(composite)

        result = RegimeResult(
            regime=regime,
            confidence=confidence,
            composite_score=round(composite, 3),
            scores=all_scores,
        )

        logger.info(
            "레짐 판단: %s (신뢰도 %.1f%%, 복합점수 %.3f)",
            regime.label_kr,
            confidence,
            composite,
        )
        return result
