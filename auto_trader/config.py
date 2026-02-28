# -*- coding: utf-8 -*-
"""자동 매매 솔루션 설정 관리.

모드 전환(실전/모의/백테스트), 리스크 파라미터, 텔레그램 설정 등
전체 시스템에서 사용하는 설정값을 중앙 관리한다.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml


class TradingMode(Enum):
    """매매 모드."""

    LIVE = "live"  # 실전투자 (prod 엔드포인트)
    PAPER = "paper"  # 모의투자 (vps 엔드포인트)
    BACKTEST = "backtest"  # 백테스트 (과거 데이터)


class MarketSession(Enum):
    """시장 세션."""

    PRE_MARKET_NXT = "pre_market_nxt"  # NXT 프리마켓 (08:00~08:50)
    REGULAR_KRX = "regular_krx"  # 정규장 KRX (09:00~15:30)
    AFTER_HOURS = "after_hours"  # 시간외 (15:40~16:00)


@dataclass
class RiskConfig:
    """리스크 관리 파라미터."""

    max_loss_per_trade: float = 0.02  # 건당 최대 손실 2%
    max_portfolio_loss: float = 0.05  # 포트폴리오 최대 손실 5%
    max_single_stock_weight: float = 0.10  # 단일 종목 최대 비중 10%
    trailing_stop_pct: float = 0.05  # 트레일링 스탑 5%
    max_positions: int = 20  # 최대 보유 종목 수


@dataclass
class PaperValidation:
    """모의투자 → 실전투자 전환 조건."""

    min_days: int = 30  # 모의투자 최소 운영 기간 (일)
    min_profit_rate: float = 0.0  # 모의투자 최소 수익률
    max_mdd: float = 0.15  # 모의투자 최대 MDD 허용


@dataclass
class TelegramConfig:
    """텔레그램 봇 설정."""

    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class UIConfig:
    """Web UI 설정."""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8501


@dataclass
class Config:
    """자동 매매 솔루션 전체 설정."""

    mode: TradingMode = TradingMode.PAPER
    markets: list[str] = field(default_factory=lambda: ["krx", "nxt"])
    risk: RiskConfig = field(default_factory=RiskConfig)
    paper_validation: PaperValidation = field(default_factory=PaperValidation)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    # KIS API 설정 (kis_devlp.yaml에서 로드)
    kis_config_path: str = ""

    # 데이터 캐시 경로
    cache_dir: str = ""

    # 로깅 레벨
    log_level: str = "INFO"

    # 자동매매 일시정지 상태
    paused: bool = False

    def __post_init__(self) -> None:
        if not self.kis_config_path:
            self.kis_config_path = os.path.join(
                os.path.expanduser("~"), "KIS", "config", "kis_devlp.yaml"
            )
        if not self.cache_dir:
            self.cache_dir = os.path.join(
                os.path.expanduser("~"), "KIS", "cache"
            )

    @property
    def kis_server(self) -> str:
        """KIS API 서버 구분값 반환 (prod/vps)."""
        if self.mode == TradingMode.LIVE:
            return "prod"
        return "vps"

    @property
    def is_live(self) -> bool:
        return self.mode == TradingMode.LIVE

    @property
    def is_paper(self) -> bool:
        return self.mode == TradingMode.PAPER

    @property
    def is_backtest(self) -> bool:
        return self.mode == TradingMode.BACKTEST


def load_config(config_path: str | None = None) -> Config:
    """YAML 설정 파일에서 Config를 로드한다.

    Args:
        config_path: 설정 파일 경로. None이면 기본 경로 사용.

    Returns:
        Config 인스턴스.
    """
    if config_path is None:
        config_path = os.path.join(
            Path(__file__).parent.parent, "auto_trader_config.yaml"
        )

    if not os.path.exists(config_path):
        return Config()

    with open(config_path, encoding="UTF-8") as f:
        raw = yaml.safe_load(f) or {}

    mode = TradingMode(raw.get("mode", "paper"))

    risk_raw = raw.get("risk", {})
    risk = RiskConfig(**{k: v for k, v in risk_raw.items() if k in RiskConfig.__dataclass_fields__})

    pv_raw = raw.get("paper_validation", {})
    paper_validation = PaperValidation(
        **{k: v for k, v in pv_raw.items() if k in PaperValidation.__dataclass_fields__}
    )

    tg_raw = raw.get("telegram", {})
    telegram = TelegramConfig(
        **{k: v for k, v in tg_raw.items() if k in TelegramConfig.__dataclass_fields__}
    )

    ui_raw = raw.get("ui", {})
    ui = UIConfig(**{k: v for k, v in ui_raw.items() if k in UIConfig.__dataclass_fields__})

    return Config(
        mode=mode,
        markets=raw.get("markets", ["krx", "nxt"]),
        risk=risk,
        paper_validation=paper_validation,
        telegram=telegram,
        ui=ui,
        kis_config_path=raw.get("kis_config_path", ""),
        cache_dir=raw.get("cache_dir", ""),
        log_level=raw.get("log_level", "INFO"),
    )
