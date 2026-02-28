# -*- coding: utf-8 -*-
"""전략 베이스 클래스.

모든 매매 전략이 상속하는 추상 인터페이스를 정의한다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from auto_trader.regime.regime_model import MarketRegime


class SignalType(Enum):
    """매매 신호 유형."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class StockSignal:
    """종목 매매 신호."""

    ticker: str
    name: str
    signal: SignalType
    strength: float  # 신호 강도 (0.0 ~ 1.0)
    target_weight: float  # 목표 비중 (0.0 ~ 1.0)
    reason: str = ""  # 신호 근거


@dataclass
class ExitCondition:
    """매도 조건."""

    stop_loss_pct: float = -0.02  # 손절 비율
    take_profit_pct: float = 0.10  # 익절 비율
    trailing_stop_pct: float = 0.05  # 트레일링 스탑
    max_holding_days: int = 0  # 최대 보유일 (0=무제한)


@dataclass
class StrategyConfig:
    """전략별 설정."""

    max_stocks: int = 10  # 최대 보유 종목 수
    min_equity_ratio: float = 0.0  # 최소 주식 비중
    max_equity_ratio: float = 1.0  # 최대 주식 비중
    rebalance_threshold: float = 0.05  # 리밸런싱 임계치


class BaseStrategy(ABC):
    """매매 전략 추상 베이스 클래스.

    모든 레짐별 전략은 이 클래스를 상속하고 핵심 메서드를 구현한다.
    """

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()

    @property
    @abstractmethod
    def name(self) -> str:
        """전략 이름."""
        ...

    @property
    @abstractmethod
    def target_regimes(self) -> list[MarketRegime]:
        """이 전략이 활성화되는 레짐 목록."""
        ...

    @abstractmethod
    def generate_signals(
        self,
        regime: MarketRegime,
        universe: list[str],
        market_data: dict,
    ) -> list[StockSignal]:
        """매매 신호를 생성한다.

        Args:
            regime: 현재 마켓 레짐.
            universe: 종목 유니버스 (종목코드 리스트).
            market_data: 시장 데이터 딕셔너리.

        Returns:
            매매 신호 리스트.
        """
        ...

    @abstractmethod
    def get_exit_condition(self, regime: MarketRegime) -> ExitCondition:
        """현재 레짐에 맞는 매도 조건을 반환한다.

        Args:
            regime: 현재 마켓 레짐.

        Returns:
            ExitCondition.
        """
        ...

    def get_target_equity_ratio(self, regime: MarketRegime) -> float:
        """레짐에 따른 목표 주식 비중을 반환한다.

        Args:
            regime: 현재 마켓 레짐.

        Returns:
            목표 비중 (0.0 ~ 1.0).
        """
        return (self.config.min_equity_ratio + self.config.max_equity_ratio) / 2

    def is_active_for(self, regime: MarketRegime) -> bool:
        """주어진 레짐에서 이 전략이 활성화되는지 확인한다."""
        return regime in self.target_regimes
