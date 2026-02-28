# -*- coding: utf-8 -*-
"""FastAPI 웹 대시보드 앱.

자동매매 모니터링, 매뉴얼 매매, 시스템 제어 UI를 제공한다.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from auto_trader.utils.logger import get_logger

logger = get_logger("ui.app")

STATIC_DIR = str(Path(__file__).parent / "static")


def create_app(trader=None) -> FastAPI:
    """FastAPI 앱을 생성한다.

    Args:
        trader: AutoTrader 인스턴스 (None이면 앱 상태에서 나중에 설정).

    Returns:
        FastAPI 앱.
    """
    app = FastAPI(
        title="KIS 자동매매 대시보드",
        description="국내 주식 자동매매 솔루션 모니터링 및 제어",
        version="1.0.0",
    )

    # AutoTrader 인스턴스를 앱 상태에 저장
    app.state.trader = trader

    # API 라우터 등록
    from auto_trader.ui.api_routes import router as api_router
    app.include_router(api_router, prefix="/api")

    # WebSocket 핸들러 등록
    from auto_trader.ui.websocket_handler import router as ws_router
    app.include_router(ws_router)

    # 정적 파일 서빙
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # 루트 → 대시보드 페이지
    from fastapi.responses import FileResponse

    @app.get("/")
    async def root():
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "KIS 자동매매 대시보드"}

    logger.info("웹 대시보드 앱 생성 완료")
    return app


def start_server(trader, host: str = "0.0.0.0", port: int = 8501) -> None:
    """대시보드 서버를 시작한다.

    Args:
        trader: AutoTrader 인스턴스.
        host: 바인드 호스트.
        port: 바인드 포트.
    """
    import uvicorn

    app = create_app(trader)
    logger.info("대시보드 서버 시작: http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")
