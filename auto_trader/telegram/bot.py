# -*- coding: utf-8 -*-
"""텔레그램 봇 메인 모듈.

원격에서 자동매매 시스템을 모니터링하고 제어할 수 있는 텔레그램 봇.
python-telegram-bot 라이브러리 기반.
"""

import asyncio

from auto_trader.config import Config
from auto_trader.utils.logger import get_logger

logger = get_logger("telegram.bot")


class TelegramBot:
    """텔레그램 봇.

    명령어 핸들러를 등록하고, 자동 알림을 발송한다.
    """

    def __init__(self, config: Config, trader=None) -> None:
        self._config = config
        self._trader = trader
        self._app = None
        self._chat_id = config.telegram.chat_id
        self._running = False

    @property
    def trader(self):
        return self._trader

    def set_trader(self, trader) -> None:
        """AutoTrader 인스턴스를 연결한다."""
        self._trader = trader

    async def start(self) -> None:
        """봇을 시작한다 (polling 방식)."""
        if not self._config.telegram.enabled:
            logger.info("텔레그램 봇 비활성화")
            return

        token = self._config.telegram.bot_token
        if not token:
            logger.warning("텔레그램 봇 토큰 미설정")
            return

        try:
            from telegram.ext import ApplicationBuilder
        except ImportError:
            logger.error("python-telegram-bot 미설치. `uv add python-telegram-bot` 필요")
            return

        self._app = ApplicationBuilder().token(token).build()

        # 핸들러 등록
        from auto_trader.telegram.handlers import register_handlers
        register_handlers(self._app, self)

        self._running = True
        logger.info("텔레그램 봇 시작")

        # polling 시작
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self) -> None:
        """봇을 중지한다."""
        if self._app and self._running:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._running = False
            logger.info("텔레그램 봇 중지")

    # ─── 알림 발송 ──────────────────────────────────────────────

    async def send_alert(self, message: str) -> None:
        """알림 메시지를 발송한다.

        Args:
            message: 발송할 메시지 (마크다운 지원).
        """
        if not self._app or not self._chat_id:
            return

        try:
            await self._app.bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error("텔레그램 메시지 발송 실패: %s", e)

    async def send_daily_report(self) -> None:
        """장 마감 후 일간 리포트를 발송한다."""
        if not self._trader:
            return

        from auto_trader.telegram.formatters import format_daily_report

        portfolio = self._trader.account.get_portfolio()
        regime = self._trader.regime_analyzer.last_result
        orders = self._trader.order_manager.get_order_summary()

        report = format_daily_report(portfolio, regime, orders)
        await self.send_alert(report)

    # ─── 보안 ───────────────────────────────────────────────────

    def is_authorized(self, chat_id: str | int) -> bool:
        """허용된 채팅방인지 확인한다."""
        return str(chat_id) == str(self._chat_id)
