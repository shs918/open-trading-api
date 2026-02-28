# -*- coding: utf-8 -*-
"""텔레그램 메시지 포맷팅.

Markdown 형식으로 가독성 높은 메시지를 생성한다.
"""

from auto_trader.data.account_data import Position, PortfolioSummary


def format_help() -> str:
    """명령어 도움말을 포맷한다."""
    return (
        "*KIS 자동매매 봇 명령어*\n\n"
        "/status — 시스템 상태\n"
        "/portfolio — 포트폴리오 현황\n"
        "/positions — 보유 종목 리스트\n"
        "/regime — 마켓 레짐 상세\n"
        "/orders — 금일 주문 내역\n"
        "/price {종목코드} — 종목 시세 조회\n"
        "/buy {종목} {수량} {가격} — 매수 주문\n"
        "/sell {종목} {수량} {가격} — 매도 주문\n"
        "/cancel {주문번호} — 주문 취소\n"
        "/pause — 자동매매 일시정지\n"
        "/resume — 자동매매 재개\n"
    )


def format_status(status: dict) -> str:
    """시스템 상태를 포맷한다."""
    mode_icon = {"live": "🔴", "paper": "🔵", "backtest": "⚪"}.get(status.get("mode", ""), "")
    paused = "⏸ 일시정지" if status.get("paused") else "▶ 활성"

    state_map = {
        "before_market": "장 시작 전",
        "nxt_pre_market": "NXT 프리마켓",
        "regular_open": "정규장",
        "after_hours": "시간외",
        "market_closed": "장 종료",
    }
    market_state = state_map.get(status.get("market_state", ""), "-")

    return (
        f"*시스템 상태*\n\n"
        f"{mode_icon} 모드: {status.get('mode', '-').upper()}\n"
        f"상태: {paused}\n"
        f"장: {market_state}\n"
        f"레짐: {status.get('regime', '-')}\n"
        f"신뢰도: {status.get('regime_confidence', 0):.1f}%\n"
        f"보유: {status.get('position_count', 0)}종목\n"
        f"가동: {status.get('uptime', '-')}"
    )


def format_portfolio(portfolio: PortfolioSummary) -> str:
    """포트폴리오를 포맷한다."""
    sign = "+" if portfolio.total_profit_loss >= 0 else ""
    return (
        f"*포트폴리오 현황*\n\n"
        f"총 평가액: {portfolio.total_eval:,.0f}원\n"
        f"예수금: {portfolio.total_deposit:,.0f}원\n"
        f"손익: {sign}{portfolio.total_profit_loss:,.0f}원 ({sign}{portfolio.total_profit_rate:.2f}%)\n"
        f"현금비중: {portfolio.cash_ratio:.1f}%\n"
        f"보유종목: {len(portfolio.positions)}개"
    )


def format_positions(positions: list[Position]) -> str:
    """보유 종목 리스트를 포맷한다."""
    if not positions:
        return "보유 종목이 없습니다."

    lines = ["*보유 종목*\n"]
    for p in positions:
        sign = "+" if p.profit_rate >= 0 else ""
        icon = "📈" if p.profit_rate >= 0 else "📉"
        lines.append(
            f"{icon} *{p.name}* ({p.ticker})\n"
            f"   {p.quantity}주 | {int(p.current_price):,}원 | {sign}{p.profit_rate:.2f}%"
        )
    return "\n".join(lines)


def format_regime(result) -> str:
    """마켓 레짐 상세를 포맷한다."""
    if result is None:
        return "레짐 분석 전입니다."

    regime_icons = {
        "strong_bull": "🔥",
        "bull": "📈",
        "sideways": "➡️",
        "bear": "📉",
        "strong_bear": "❄️",
    }

    icon = regime_icons.get(result.regime.value, "")
    lines = [
        f"*마켓 레짐*\n",
        f"{icon} *{result.regime.label_kr}*",
        f"신뢰도: {result.confidence:.1f}%",
        f"복합점수: {result.composite_score:.2f}",
        "",
        "*지표별 점수:*",
    ]

    label_map = {
        "kospi_trend": "KOSPI 추세",
        "momentum": "모멘텀",
        "foreign_flow": "외국인",
        "institution_flow": "기관",
        "volume": "거래량",
        "new_highlow": "신고가/저가",
        "short_selling": "공매도",
        "disparity": "이격도",
        "volatility": "변동성",
    }

    for key, value in result.scores.items():
        label = label_map.get(key, key)
        bar = _score_bar(float(value))
        lines.append(f"  {label}: {bar} {float(value):.1f}")

    return "\n".join(lines)


def format_orders(orders: list) -> str:
    """주문 내역을 포맷한다."""
    if not orders:
        return "금일 주문 내역이 없습니다."

    lines = ["*금일 주문 내역*\n"]
    for o in orders:
        side_icon = "🔴" if o.side.value == "buy" else "🔵"
        side_text = "매수" if o.side.value == "buy" else "매도"
        time_str = o.timestamp.strftime("%H:%M:%S")
        lines.append(
            f"{side_icon} {time_str} | {o.ticker} | {side_text} {o.quantity}주 | {o.status.value}"
        )
    return "\n".join(lines)


def format_daily_report(portfolio: PortfolioSummary, regime_result, order_summary: dict) -> str:
    """일간 리포트를 포맷한다."""
    sign = "+" if portfolio.total_profit_loss >= 0 else ""

    regime_text = "분석 전"
    if regime_result:
        regime_text = f"{regime_result.regime.label_kr} (신뢰도 {regime_result.confidence:.1f}%)"

    return (
        f"*일간 리포트*\n\n"
        f"*포트폴리오*\n"
        f"  총 평가액: {portfolio.total_eval:,.0f}원\n"
        f"  일간 손익: {sign}{portfolio.total_profit_loss:,.0f}원 ({sign}{portfolio.total_profit_rate:.2f}%)\n"
        f"  현금비중: {portfolio.cash_ratio:.1f}%\n"
        f"  보유종목: {len(portfolio.positions)}개\n\n"
        f"*레짐*: {regime_text}\n\n"
        f"*주문*\n"
        f"  총: {order_summary.get('total', 0)}건\n"
        f"  매수: {order_summary.get('buys', 0)}건\n"
        f"  매도: {order_summary.get('sells', 0)}건\n"
        f"  성공: {order_summary.get('submitted', 0)}건\n"
        f"  실패: {order_summary.get('failed', 0)}건"
    )


def _score_bar(value: float) -> str:
    """점수를 막대 그래프 문자열로 변환한다."""
    # -2 ~ +2 범위를 0~4로 정규화
    normalized = min(max(value + 2, 0), 4)
    filled = int(normalized / 4 * 5)
    return "█" * filled + "░" * (5 - filled)
