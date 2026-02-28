# -*- coding: utf-8 -*-
"""텔레그램 명령어 핸들러.

/status, /portfolio, /buy, /sell 등 사용자 명령을 처리한다.
"""

from auto_trader.telegram.formatters import (
    format_help,
    format_orders,
    format_portfolio,
    format_positions,
    format_regime,
    format_status,
)
from auto_trader.utils.logger import get_logger

logger = get_logger("telegram.handlers")


def register_handlers(app, bot) -> None:
    """명령어 핸들러를 등록한다.

    Args:
        app: telegram.ext.Application.
        bot: TelegramBot 인스턴스.
    """
    from telegram.ext import CallbackQueryHandler, CommandHandler

    app.add_handler(CommandHandler("start", _make_handler(cmd_start, bot)))
    app.add_handler(CommandHandler("help", _make_handler(cmd_help, bot)))
    app.add_handler(CommandHandler("status", _make_handler(cmd_status, bot)))
    app.add_handler(CommandHandler("portfolio", _make_handler(cmd_portfolio, bot)))
    app.add_handler(CommandHandler("positions", _make_handler(cmd_positions, bot)))
    app.add_handler(CommandHandler("regime", _make_handler(cmd_regime, bot)))
    app.add_handler(CommandHandler("orders", _make_handler(cmd_orders, bot)))
    app.add_handler(CommandHandler("price", _make_handler(cmd_price, bot)))
    app.add_handler(CommandHandler("buy", _make_handler(cmd_buy, bot)))
    app.add_handler(CommandHandler("sell", _make_handler(cmd_sell, bot)))
    app.add_handler(CommandHandler("cancel", _make_handler(cmd_cancel, bot)))
    app.add_handler(CommandHandler("pause", _make_handler(cmd_pause, bot)))
    app.add_handler(CommandHandler("resume", _make_handler(cmd_resume, bot)))

    app.add_handler(CallbackQueryHandler(_make_callback_handler(bot), pattern="^(confirm|deny)_"))

    logger.info("텔레그램 핸들러 등록 완료")


def _make_handler(func, bot):
    """핸들러 래퍼를 생성한다 (인증 + bot 주입)."""
    async def wrapper(update, context):
        if not bot.is_authorized(update.effective_chat.id):
            await update.message.reply_text("인증되지 않은 채팅방입니다.")
            return
        await func(update, context, bot)
    return wrapper


def _make_callback_handler(bot):
    """콜백 쿼리 핸들러 래퍼."""
    async def wrapper(update, context):
        if not bot.is_authorized(update.effective_chat.id):
            return
        await handle_callback(update, context, bot)
    return wrapper


# ─── 명령어 핸들러 ──────────────────────────────────────────────


async def cmd_start(update, context, bot):
    """봇 시작 환영 메시지."""
    await update.message.reply_text(
        "KIS 자동매매 봇입니다.\n/help 명령으로 사용법을 확인하세요.",
        parse_mode="Markdown",
    )


async def cmd_help(update, context, bot):
    """/help — 명령어 도움말."""
    await update.message.reply_text(format_help(), parse_mode="Markdown")


async def cmd_status(update, context, bot):
    """/status — 시스템 상태 조회."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return
    status = bot.trader.get_status()
    await update.message.reply_text(format_status(status), parse_mode="Markdown")


async def cmd_portfolio(update, context, bot):
    """/portfolio — 포트폴리오 상세."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return
    portfolio = bot.trader.account.get_portfolio()
    await update.message.reply_text(format_portfolio(portfolio), parse_mode="Markdown")


async def cmd_positions(update, context, bot):
    """/positions — 보유 종목 리스트."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return
    portfolio = bot.trader.account.get_portfolio()
    await update.message.reply_text(format_positions(portfolio.positions), parse_mode="Markdown")


async def cmd_regime(update, context, bot):
    """/regime — 마켓 레짐 상세."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return
    result = bot.trader.regime_analyzer.last_result
    await update.message.reply_text(format_regime(result), parse_mode="Markdown")


async def cmd_orders(update, context, bot):
    """/orders — 금일 주문 내역."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return
    orders = bot.trader.order_manager.get_today_orders()
    await update.message.reply_text(format_orders(orders), parse_mode="Markdown")


async def cmd_price(update, context, bot):
    """/price {종목코드} — 종목 현재가 조회."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return

    args = context.args
    if not args:
        await update.message.reply_text("사용법: `/price 005930`", parse_mode="Markdown")
        return

    ticker = args[0]
    try:
        df = bot.trader.market_data.get_stock_price(ticker)
        if df.empty:
            await update.message.reply_text(f"{ticker}: 데이터 없음")
            return
        row = df.iloc[0]
        name = row.get("hts_kor_isnm", ticker)
        price = int(row.get("stck_prpr", 0))
        change = float(row.get("prdy_ctrt", 0))
        sign = "+" if change >= 0 else ""
        await update.message.reply_text(
            f"*{name}* ({ticker})\n현재가: {price:,}원 ({sign}{change:.2f}%)",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"조회 실패: {e}")


async def cmd_buy(update, context, bot):
    """/buy {종목} {수량} {가격} — 매뉴얼 매수."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "사용법: `/buy 005930 10 72000`\n가격 생략 시 시장가",
            parse_mode="Markdown",
        )
        return

    ticker = args[0]
    quantity = int(args[1])
    price = int(args[2]) if len(args) >= 3 else 0

    # 확인 버튼
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    price_text = f"{price:,}원" if price > 0 else "시장가"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("확인", callback_data=f"confirm_buy_{ticker}_{quantity}_{price}"),
            InlineKeyboardButton("취소", callback_data="deny_order"),
        ]
    ])
    await update.message.reply_text(
        f"매수 주문 확인\n종목: {ticker}\n수량: {quantity}주\n가격: {price_text}",
        reply_markup=keyboard,
    )


async def cmd_sell(update, context, bot):
    """/sell {종목} {수량} {가격} — 매뉴얼 매도."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "사용법: `/sell 005930 10 75000`\n가격 생략 시 시장가",
            parse_mode="Markdown",
        )
        return

    ticker = args[0]
    quantity = int(args[1])
    price = int(args[2]) if len(args) >= 3 else 0

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    price_text = f"{price:,}원" if price > 0 else "시장가"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("확인", callback_data=f"confirm_sell_{ticker}_{quantity}_{price}"),
            InlineKeyboardButton("취소", callback_data="deny_order"),
        ]
    ])
    await update.message.reply_text(
        f"매도 주문 확인\n종목: {ticker}\n수량: {quantity}주\n가격: {price_text}",
        reply_markup=keyboard,
    )


async def cmd_cancel(update, context, bot):
    """/cancel {주문번호} — 주문 취소."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return

    args = context.args
    if not args:
        await update.message.reply_text("사용법: `/cancel 주문번호`", parse_mode="Markdown")
        return

    order_no = args[0]
    result = bot.trader.order_manager.cancel_order(order_no)
    await update.message.reply_text(
        f"주문 취소: {order_no}\n상태: {result.status.value}\n{result.message}",
    )


async def cmd_pause(update, context, bot):
    """/pause — 자동매매 일시정지."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return
    bot.trader.pause()
    await update.message.reply_text("자동매매 일시정지됨")


async def cmd_resume(update, context, bot):
    """/resume — 자동매매 재개."""
    if not bot.trader:
        await update.message.reply_text("AutoTrader 미연결")
        return
    bot.trader.resume()
    await update.message.reply_text("자동매매 재개됨")


# ─── 콜백 핸들러 (확인/취소 버튼) ──────────────────────────────


async def handle_callback(update, context, bot):
    """인라인 버튼 콜백을 처리한다."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "deny_order":
        await query.edit_message_text("주문이 취소되었습니다.")
        return

    # confirm_buy_005930_10_72000
    parts = data.split("_")
    if len(parts) < 5 or parts[0] != "confirm":
        return

    side = parts[1]  # buy / sell
    ticker = parts[2]
    quantity = int(parts[3])
    price = int(parts[4])

    if side == "buy":
        result = bot.trader.order_manager.place_buy(
            ticker=ticker,
            quantity=quantity,
            price=price,
            reason="텔레그램 매수",
            is_manual=True,
        )
    elif side == "sell":
        result = bot.trader.order_manager.place_sell(
            ticker=ticker,
            quantity=quantity,
            price=price,
            reason="텔레그램 매도",
            is_manual=True,
        )
    else:
        return

    status_text = "성공" if result.order_no else "실패"
    await query.edit_message_text(
        f"주문 {status_text}\n"
        f"종목: {ticker}\n"
        f"주문번호: {result.order_no or '-'}\n"
        f"상태: {result.status.value}\n"
        f"{result.message}",
    )
