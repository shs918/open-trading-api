# -*- coding: utf-8 -*-
"""구조화된 로깅 설정.

자동 매매 시스템 전체에서 사용하는 통일된 로거를 제공한다.
콘솔 + 파일 로깅을 지원하며, 모듈별 로거 생성이 가능하다.
"""

import logging
import os
import sys
from datetime import datetime


_LOG_DIR = os.path.join(os.path.expanduser("~"), "KIS", "logs")
_initialized = False


def setup_logging(level: str = "INFO", log_dir: str | None = None) -> None:
    """로깅 시스템을 초기화한다.

    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR).
        log_dir: 로그 파일 저장 경로. None이면 기본 경로 사용.
    """
    global _initialized, _LOG_DIR
    if _initialized:
        return

    if log_dir:
        _LOG_DIR = log_dir

    os.makedirs(_LOG_DIR, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.INFO)
    today = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(_LOG_DIR, f"auto_trader_{today}.log")

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    root = logging.getLogger("auto_trader")
    root.setLevel(logging.DEBUG)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    _initialized = True
    root.info("Logging initialized (level=%s, file=%s)", level, log_file)


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거를 반환한다.

    Args:
        name: 모듈 이름 (예: "data.provider", "regime.analyzer").

    Returns:
        logging.Logger 인스턴스.
    """
    return logging.getLogger(f"auto_trader.{name}")
