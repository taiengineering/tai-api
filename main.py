# main.py — v6.0.0
# v6.0.0: Module Isolation — Safe Loading + 10 Module Groups
# 한 라우터 import 실패 → 해당 라우터만 스킵, 나머지 정상 작동
# /health 응답에 모듈별 상태(ok/degraded) 포함
import os
import sentry_sdk

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.1, environment="production")

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import services.health_probes  # noqa: F401

from router_registry import load_module_group, get_all_status

logger = logging.getLogger(__name__)
APP_VERSION = "6.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from scheduler import start_scheduler
        start_scheduler()
        logger.info("[STARTUP] APScheduler 시작 완료")
    except Exception as e:
        logger.error(f"[STARTUP] APScheduler 시작 실패: {e}")
    yield
    try:
        from scheduler import scheduler
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(
    title="TAI API",
    version=APP_VERSION,
    description="TAI 산업안전 플랫폼 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://taieng.co.kr", "https://www.taieng.co.kr", "https://new.taieng.co.kr",
        "https://admin.taieng.co.kr", "https://tadmin.taieng.co.kr", "https://safe.taieng.co.kr",
        "http://localhost:5500", "http://127.0.0.1:5500",
        "http://localhost:3000", "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://([a-z0-9-]+\.)*taieng\.co\.kr",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === 모듈 그룹 격리 로드 ===
def _load_all_modules():
    """10개 모듈 그룹을 격리 로드. 한 그룹 실패해도 다른 그룹 정상 작동."""
    from router_registry.saas_core import ROUTERS as SAAS
    from router_registry.legal_engine import ROUTERS as LEGAL
    from router_registry.document_engine import ROUTERS as DOC
    from router_registry.runtime_bridge import ROUTERS as BRIDGE
    from router_registry.inspection import ROUTERS as INSP
    from router_registry.payment import ROUTERS as PAY
    from router_registry.public import ROUTERS as PUB
    from router_registry.diagnosis import ROUTERS as DIAG
    from router_registry.construction import ROUTERS as CONST
    from router_registry.external import ROUTERS as EXT

    groups = [
        ("saas_core", SAAS),
        ("legal_engine", LEGAL),
        ("document_engine", DOC),
        ("runtime_bridge", BRIDGE),
        ("inspection", INSP),
        ("payment", PAY),
        ("public", PUB),
        ("diagnosis", DIAG),
        ("construction", CONST),
        ("external", EXT),
    ]
    for name, routers in groups:
        load_module_group(app, name, routers)


_load_all_modules()


# === Root / Health ===
@app.get("/")
def root():
    status_info = get_all_status()
    return {
        "status": status_info["overall"],
        "service": "TAI API",
        "version": APP_VERSION,
        "modules": {
            name: {
                "loaded": info["loaded"],
                "failed": info["failed"],
                "status": info["status"],
            }
            for name, info in status_info["modules"].items()
        },
    }
