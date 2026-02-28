# -*- coding: utf-8 -*-
"""WebSocket 핸들러.

대시보드에 실시간 데이터를 푸시한다.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auto_trader.utils.logger import get_logger

logger = get_logger("ui.websocket")

router = APIRouter()

# 연결된 클라이언트 관리
_active_connections: list[WebSocket] = []


class ConnectionManager:
    """WebSocket 연결 관리자."""

    def __init__(self) -> None:
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)
        logger.info("WebSocket 연결: %d 활성", len(self.connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.connections:
            self.connections.remove(ws)
        logger.info("WebSocket 해제: %d 활성", len(self.connections))

    async def broadcast(self, data: dict) -> None:
        """모든 연결된 클라이언트에 데이터를 전송한다."""
        message = json.dumps(data, ensure_ascii=False, default=str)
        for ws in self.connections[:]:
            try:
                await ws.send_text(message)
            except Exception:
                self.connections.remove(ws)


manager = ConnectionManager()


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """대시보드 실시간 데이터 WebSocket."""
    await manager.connect(websocket)

    try:
        while True:
            trader = websocket.app.state.trader
            if trader is None:
                await websocket.send_json({"error": "AutoTrader 미연결"})
                await asyncio.sleep(5)
                continue

            try:
                # 시스템 상태
                status = trader.get_status()

                # 포트폴리오 요약
                portfolio = trader.account.get_portfolio()

                # 주문 요약
                order_summary = trader.order_manager.get_order_summary()

                # 최근 알림
                recent_notifications = trader.notifier.get_recent(10)

                data = {
                    "type": "dashboard_update",
                    "status": status,
                    "portfolio": {
                        "total_eval": portfolio.total_eval,
                        "total_deposit": portfolio.total_deposit,
                        "total_profit_loss": portfolio.total_profit_loss,
                        "total_profit_rate": portfolio.total_profit_rate,
                        "cash_ratio": portfolio.cash_ratio,
                        "position_count": len(portfolio.positions),
                    },
                    "orders": order_summary,
                    "notifications": recent_notifications[-5:],
                }

                await websocket.send_json(data)

            except Exception as e:
                logger.error("대시보드 데이터 수집 오류: %s", e)
                await websocket.send_json({"error": str(e)})

            # 수신 메시지 확인 (타임아웃 사용)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket 오류: %s", e)
        manager.disconnect(websocket)


async def broadcast_notification(data: dict) -> None:
    """모든 클라이언트에 알림을 브로드캐스트한다."""
    await manager.broadcast({"type": "notification", **data})
