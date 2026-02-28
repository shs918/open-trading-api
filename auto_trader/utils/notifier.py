# -*- coding: utf-8 -*-
"""알림 모듈.

콘솔 로깅 + 텔레그램 알림을 통합하는 노티파이어.
텔레그램 봇 모듈이 연결되면 자동으로 메시지를 전송한다.
"""

from datetime import datetime

from auto_trader.config import Config
from auto_trader.utils.logger import get_logger

logger = get_logger("utils.notifier")


class NotificationLevel:
    """알림 수준."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    TRADE = "trade"  # 매매 알림
    REGIME = "regime"  # 레짐 변경


class Notifier:
    """통합 알림 관리자.

    콘솔 로깅은 항상 수행하고,
    텔레그램 봇이 연결되면 지정 채팅방으로 메시지를 전송한다.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._telegram_sender = None  # 텔레그램 send_alert 콜백
        self._notification_history: list[dict] = []

    def set_telegram_sender(self, sender) -> None:
        """텔레그램 메시지 발송 콜백을 설정한다.

        Args:
            sender: async def send_alert(message: str) 함수.
        """
        self._telegram_sender = sender
        logger.info("텔레그램 알림 연결 완료")

    # ─── 알림 발송 ──────────────────────────────────────────────

    async def notify(self, message: str, level: str = NotificationLevel.INFO) -> None:
        """알림을 발송한다.

        콘솔 로깅 + (활성화 시) 텔레그램 전송.

        Args:
            message: 알림 메시지.
            level: 알림 수준.
        """
        # 콘솔 로깅
        if level == NotificationLevel.ERROR:
            logger.error(message)
        elif level == NotificationLevel.WARNING:
            logger.warning(message)
        else:
            logger.info(message)

        # 이력 저장
        self._notification_history.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
        })

        # 텔레그램 발송
        if self._telegram_sender and self._config.telegram.enabled:
            try:
                await self._telegram_sender(message)
            except Exception as e:
                logger.error("텔레그램 알림 발송 실패: %s", e)

    # ─── 편의 메서드 ────────────────────────────────────────────

    async def notify_trade(self, message: str) -> None:
        """매매 알림을 발송한다."""
        await self.notify(f"[매매] {message}", NotificationLevel.TRADE)

    async def notify_regime_change(self, old_regime: str, new_regime: str, confidence: float) -> None:
        """레짐 변경 알림을 발송한다."""
        msg = f"[레짐변경] {old_regime} → {new_regime} (신뢰도 {confidence:.1f}%)"
        await self.notify(msg, NotificationLevel.REGIME)

    async def notify_error(self, message: str) -> None:
        """오류 알림을 발송한다."""
        await self.notify(f"[오류] {message}", NotificationLevel.ERROR)

    async def notify_emergency_stop(self, reason: str) -> None:
        """긴급 정지 알림을 발송한다."""
        await self.notify(f"[긴급정지] {reason}", NotificationLevel.ERROR)

    async def notify_daily_report(self, report: str) -> None:
        """일간 리포트를 발송한다."""
        await self.notify(f"[일간리포트]\n{report}", NotificationLevel.INFO)

    # ─── 이력 조회 ──────────────────────────────────────────────

    @property
    def history(self) -> list[dict]:
        """알림 이력."""
        return self._notification_history

    def get_recent(self, count: int = 50) -> list[dict]:
        """최근 알림을 반환한다."""
        return self._notification_history[-count:]
