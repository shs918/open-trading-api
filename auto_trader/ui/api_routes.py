# -*- coding: utf-8 -*-
"""REST API 엔드포인트.

대시보드 프론트엔드에서 호출하는 조회/제어/매뉴얼매매 API.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from auto_trader.execution.order_manager import OrderRequest, OrderSide, OrderType
from auto_trader.utils.logger import get_logger

logger = get_logger("ui.api")

router = APIRouter()


# ─── 요청 모델 ──────────────────────────────────────────────────


class TradeRequest(BaseModel):
    """매뉴얼 매매 요청."""

    ticker: str
    quantity: int
    price: int = 0  # 0 = 시장가
    order_type: str = "market"  # market / limit
    market: str = "KRX"


class CancelRequest(BaseModel):
    """주문 취소 요청."""

    order_no: str
    market: str = "KRX"


class ModeRequest(BaseModel):
    """모드 전환 요청."""

    mode: str  # "live" / "paper"


# ─── 헬퍼 ───────────────────────────────────────────────────────


def _get_trader(request: Request):
    """요청에서 AutoTrader를 가져온다."""
    trader = request.app.state.trader
    if trader is None:
        raise HTTPException(status_code=503, detail="AutoTrader 미연결")
    return trader


# ─── 시스템 상태 ─────────────────────────────────────────────────


@router.get("/status")
async def get_status(request: Request):
    """시스템 상태를 조회한다."""
    trader = _get_trader(request)
    return trader.get_status()


# ─── 마켓 레짐 ───────────────────────────────────────────────────


@router.get("/regime")
async def get_regime(request: Request):
    """현재 마켓 레짐 및 지표 점수를 조회한다."""
    trader = _get_trader(request)
    result = trader.regime_analyzer.last_result
    if result is None:
        return {"regime": "분석 전", "scores": {}, "confidence": 0}
    return {
        "regime": result.regime.value,
        "regime_kr": result.regime.label_kr,
        "confidence": result.confidence,
        "composite_score": result.composite_score,
        "scores": result.scores,
        "timestamp": result.timestamp.isoformat(),
    }


# ─── 포트폴리오 ─────────────────────────────────────────────────


@router.get("/portfolio")
async def get_portfolio(request: Request):
    """포트폴리오 현황을 조회한다."""
    trader = _get_trader(request)
    portfolio = trader.position_manager.sync_positions()
    positions = []
    for p in portfolio.positions:
        positions.append({
            "ticker": p.ticker,
            "name": p.name,
            "quantity": p.quantity,
            "avg_price": p.avg_price,
            "current_price": p.current_price,
            "eval_amount": p.eval_amount,
            "profit_loss": p.profit_loss,
            "profit_rate": p.profit_rate,
        })
    return {
        "total_eval": portfolio.total_eval,
        "total_deposit": portfolio.total_deposit,
        "total_profit_loss": portfolio.total_profit_loss,
        "total_profit_rate": portfolio.total_profit_rate,
        "cash_ratio": portfolio.cash_ratio,
        "positions": positions,
    }


@router.get("/positions")
async def get_positions(request: Request):
    """추적 포지션 상세를 조회한다."""
    trader = _get_trader(request)
    df = trader.position_manager.get_positions_df()
    if df.empty:
        return []
    return df.to_dict(orient="records")


# ─── 주문 내역 ───────────────────────────────────────────────────


@router.get("/orders")
async def get_orders(request: Request):
    """금일 주문 내역을 조회한다."""
    trader = _get_trader(request)
    orders = trader.order_manager.get_today_orders()
    return [
        {
            "ticker": o.ticker,
            "side": o.side.value,
            "quantity": o.quantity,
            "price": o.price,
            "status": o.status.value,
            "order_no": o.order_no,
            "message": o.message,
            "timestamp": o.timestamp.isoformat(),
        }
        for o in orders
    ]


@router.get("/orders/summary")
async def get_order_summary(request: Request):
    """주문 요약 통계를 조회한다."""
    trader = _get_trader(request)
    return trader.order_manager.get_order_summary()


# ─── 종목 시세 ───────────────────────────────────────────────────


@router.get("/market/{ticker}")
async def get_market_price(ticker: str, request: Request):
    """종목 현재가를 조회한다."""
    trader = _get_trader(request)
    try:
        df = trader.market_data.get_stock_price(ticker)
        if df.empty:
            raise HTTPException(status_code=404, detail="시세 데이터 없음")
        return df.iloc[0].to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/{code}")
async def get_index_price(code: str, request: Request):
    """지수 현재가를 조회한다."""
    trader = _get_trader(request)
    try:
        df = trader.market_data.get_index_current(code)
        if df.empty:
            raise HTTPException(status_code=404, detail="지수 데이터 없음")
        return df.iloc[0].to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 리스크 ──────────────────────────────────────────────────────


@router.get("/risk")
async def get_risk(request: Request):
    """리스크 상태를 조회한다."""
    trader = _get_trader(request)
    portfolio = trader.account.get_portfolio()
    return trader.risk_manager.get_risk_summary(portfolio)


# ─── 성과 ────────────────────────────────────────────────────────


@router.get("/performance")
async def get_performance(request: Request):
    """성과 요약을 조회한다."""
    trader = _get_trader(request)
    portfolio = trader.account.get_portfolio()
    order_summary = trader.order_manager.get_order_summary()
    return {
        "total_profit_loss": portfolio.total_profit_loss,
        "total_profit_rate": portfolio.total_profit_rate,
        "cash_ratio": portfolio.cash_ratio,
        "position_count": len(portfolio.positions),
        "today_orders": order_summary,
    }


# ─── 알림 로그 ───────────────────────────────────────────────────


@router.get("/notifications")
async def get_notifications(request: Request):
    """최근 알림을 조회한다."""
    trader = _get_trader(request)
    return trader.notifier.get_recent(100)


# ─── 매뉴얼 매매 ─────────────────────────────────────────────────


@router.post("/trade/buy")
async def manual_buy(trade: TradeRequest, request: Request):
    """수동 매수 주문을 실행한다."""
    trader = _get_trader(request)

    order_request = OrderRequest(
        ticker=trade.ticker,
        side=OrderSide.BUY,
        quantity=trade.quantity,
        price=trade.price,
        order_type=OrderType.MARKET if trade.price == 0 else OrderType.LIMIT,
        market=trade.market,
        reason="매뉴얼 매수",
        is_manual=True,
    )

    # 리스크 검증
    portfolio = trader.account.get_portfolio()
    risk_check = trader.risk_manager.check_order(order_request, portfolio)
    if not risk_check.passed:
        raise HTTPException(status_code=400, detail=f"리스크 검증 실패: {risk_check.reason}")

    result = trader.order_manager.place_order(order_request)
    if result.order_no:
        trader.position_manager.mark_as_manual(trade.ticker)

    return {
        "status": result.status.value,
        "order_no": result.order_no,
        "message": result.message,
    }


@router.post("/trade/sell")
async def manual_sell(trade: TradeRequest, request: Request):
    """수동 매도 주문을 실행한다."""
    trader = _get_trader(request)

    order_request = OrderRequest(
        ticker=trade.ticker,
        side=OrderSide.SELL,
        quantity=trade.quantity,
        price=trade.price,
        order_type=OrderType.MARKET if trade.price == 0 else OrderType.LIMIT,
        market=trade.market,
        reason="매뉴얼 매도",
        is_manual=True,
    )

    # 리스크 검증
    portfolio = trader.account.get_portfolio()
    risk_check = trader.risk_manager.check_order(order_request, portfolio)
    if not risk_check.passed:
        raise HTTPException(status_code=400, detail=f"리스크 검증 실패: {risk_check.reason}")

    result = trader.order_manager.place_order(order_request)
    return {
        "status": result.status.value,
        "order_no": result.order_no,
        "message": result.message,
    }


@router.post("/trade/cancel")
async def cancel_order(cancel: CancelRequest, request: Request):
    """주문을 취소한다."""
    trader = _get_trader(request)
    result = trader.order_manager.cancel_order(cancel.order_no, cancel.market)
    return {
        "status": result.status.value,
        "message": result.message,
    }


# ─── 시스템 제어 ─────────────────────────────────────────────────


@router.post("/control/pause")
async def pause_trading(request: Request):
    """자동매매를 일시정지한다."""
    trader = _get_trader(request)
    trader.pause()
    return {"paused": True}


@router.post("/control/resume")
async def resume_trading(request: Request):
    """자동매매를 재개한다."""
    trader = _get_trader(request)
    trader.resume()
    return {"paused": False}


@router.post("/control/mode")
async def change_mode(mode_req: ModeRequest, request: Request):
    """매매 모드를 전환한다."""
    trader = _get_trader(request)
    from auto_trader.config import TradingMode

    try:
        new_mode = TradingMode(mode_req.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"잘못된 모드: {mode_req.mode}")

    if new_mode == TradingMode.LIVE:
        # 실전 전환 시 검증
        if not trader.risk_manager.can_switch_to_live():
            raise HTTPException(status_code=400, detail="현재 모의투자 모드가 아닙니다")

    trader.config.mode = new_mode
    # Provider 재인증이 필요할 수 있음
    trader.provider.authenticate()
    return {"mode": new_mode.value}
