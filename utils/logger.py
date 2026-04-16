"""
utils/logger.py — v1.0.0

TAI API 표준 로거.
Fly.io 콘솔 로그에서 [ERROR] / [WARNING] grep으로 알림 감지 가능.

Usage:
    from utils.logger import get_logger
    log = get_logger(__name__)
    log.error("[CONSTRUCTION] factories 자동생성 실패", exc_info=True)
    log.warning("[FCM] 점검 알림 발송 실패 (무시)")

LOG_LEVEL 환경변수로 레벨 조정 (기본: INFO).
"""
import logging
import os
import sys


def get_logger(name: str) -> logging.Logger:
    """
    TAI 표준 로거 반환.
    동일 name으로 중복 핸들러 등록 방지.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger
