# main.py 모듈 격리 — Cursor 실행 Spec

> Issue #72 참조. 이 문서를 Cursor에 붙여넣고 실행.

## 작업 요약

main.py의 120+개 직접 import를 10개 모듈 그룹으로 분리하고,
try/except Safe Loading으로 장애 격리 구현.

## 절대 규칙

1. `/health` 엔드포인트는 항상 200 반환 (503 금지)
2. `from db.supabase_client import get_supabase` import 패턴 유지
3. 기존 라우터 파일(routers/*.py) 수정 금지 — main.py와 새 파일만 작업
4. 기존 URL 경로 100% 보존 — prefix, tags 동일하게 유지

---

## Step 1. `router_registry/__init__.py` 생성

```python
"""TAI Router Registry — Safe Loading with Module Isolation.

한 라우터 import 실패 → 해당 라우터만 스킵, 나머지 정상.
Slack #tai-alert 로 실패 알림 발송.
"""
import importlib
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI

logger = logging.getLogger("router_registry")

# 모듈별 로드 결과 저장 (health 엔드포인트에서 참조)
MODULE_STATUS: Dict[str, Dict[str, Any]] = {}


def load_module_group(
    app: FastAPI,
    group_name: str,
    router_specs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """모듈 그룹을 격리 로드.

    Args:
        app: FastAPI 인스턴스
        group_name: 그룹 이름 (e.g. "legal_engine")
        router_specs: 라우터 스펙 리스트
            [{"module": "routers.auth", "attr": "router", "prefix": "", "tags": [...]}]

    Returns:
        {"group": str, "loaded": int, "failed": int, "failed_modules": [str]}
    """
    loaded, failed = 0, 0
    failed_modules = []

    for spec in router_specs:
        module_path = spec["module"]
        attr_name = spec.get("attr", "router")

        try:
            mod = importlib.import_module(module_path)
            router_obj = getattr(mod, attr_name)

            kwargs: Dict[str, Any] = {}
            if spec.get("prefix"):
                kwargs["prefix"] = spec["prefix"]
            if spec.get("tags"):
                kwargs["tags"] = spec["tags"]

            app.include_router(router_obj, **kwargs)
            loaded += 1

        except Exception as e:
            failed += 1
            failed_modules.append(module_path)
            logger.error(
                "[%s] FAILED to load %s.%s: %s",
                group_name, module_path, attr_name, e,
                exc_info=True,
            )
            # Slack 알림 (best-effort)
            _notify_slack(group_name, module_path, str(e))

    status = "ok" if failed == 0 else "degraded"
    result = {
        "group": group_name,
        "loaded": loaded,
        "failed": failed,
        "failed_modules": failed_modules,
        "status": status,
    }
    MODULE_STATUS[group_name] = result
    logger.info("[%s] loaded=%d, failed=%d, status=%s", group_name, loaded, failed, status)
    return result


def _notify_slack(group_name: str, module_path: str, error: str):
    """Slack #tai-alert 로 로드 실패 알림 (best-effort)."""
    try:
        from services.slack_dispatcher import send_slack_sync
        send_slack_sync(
            "ROUTER_LOAD_FAILURE",
            "HIGH",
            f"라우터 로드 실패: {module_path}",
            f"그룹: {group_name} | {error[:300]}",
        )
    except Exception:
        pass


def get_all_status() -> Dict[str, Any]:
    """모든 모듈 그룹 상태 반환 (health 엔드포인트용)."""
    overall = "ok"
    for info in MODULE_STATUS.values():
        if info.get("status") == "degraded":
            overall = "degraded"
            break
    return {"overall": overall, "modules": MODULE_STATUS}
```

---

## Step 2. 모듈 그룹 파일 10개 생성

모든 파일은 `router_registry/` 디렉토리에 생성.
각 파일은 `ROUTERS` 리스트 하나만 export.

### `router_registry/saas_core.py`

```python
ROUTERS = [
    {"module": "routers.auth"},
    {"module": "routers.auth_oauth"},
    {"module": "routers.pw_reset"},
    {"module": "routers.users"},
    {"module": "routers.companies"},
    {"module": "routers.factories"},
    {"module": "routers.system_codes"},
    {"module": "routers.contacts"},
    {"module": "routers.roles"},
    {"module": "routers.teams"},
    {"module": "routers.areas"},
    {"module": "routers.buildings"},
    {"module": "routers.notifications"},
    {"module": "routers.feature_flags"},
    {"module": "routers.health"},
    {"module": "routers.alert_messages"},
    {"module": "routers.factory_process_v3"},
    {"module": "routers.process_management"},
    {"module": "routers.ksic_engine"},
    {"module": "routers.posts"},
]
```

### `router_registry/legal_engine.py`

```python
ROUTERS = [
    {"module": "routers.legal_engine"},
    {"module": "routers.legal_engine_patch"},
    {"module": "routers.engine_qa"},
    {"module": "routers.law_rule_generator"},
    {"module": "routers.engine_legal"},
    {"module": "routers.law_collector"},
    {"module": "routers.byulpyo"},
    {"module": "routers.compiler_core"},
    {"module": "routers.residual_intelligence"},
    {"module": "routers.legal_intake"},
    {"module": "routers.legal_diff"},
    {"module": "routers.deterministic_qa"},
    {"module": "routers.engine_publish"},
    {"module": "routers.integrity_monitor"},
    {"module": "routers.engine_monitoring"},
    {"module": "routers.runtime_activation"},
    {"module": "routers.runtime_chaos"},
    {"module": "routers.persistence_api"},
    {"module": "routers.runtime_evaluator_api"},
    {"module": "routers.simulation_api"},
]
```

### `router_registry/document_engine.py`

```python
ROUTERS = [
    {"module": "routers.document_engine_api"},
    {"module": "routers.engine_document"},
    {"module": "routers.report_forms"},
    {"module": "routers.document_monitoring"},
    {"module": "routers.requirement_engine"},
    {"module": "routers.diagram_proxy"},
]
```

### `router_registry/runtime_bridge.py`

```python
ROUTERS = [
    {"module": "routers.legacy_freeze"},
    {"module": "routers.runtime_bridge"},
    {"module": "routers.inspection_bridge"},
    {"module": "routers.obligation_bridge"},
    {"module": "routers.my_inspection_bridge"},
    {"module": "routers.notification_bridge"},
    {"module": "routers.review_bridge"},
    {"module": "routers.evidence_bridge"},
    {"module": "routers.submission_bridge"},
]
```

### `router_registry/inspection.py`

```python
ROUTERS = [
    {"module": "routers.inspection_sets"},
    {"module": "routers.inspection_schedule"},
    {"module": "routers.inspection_checklist"},
    {"module": "routers.inspection_setup"},
    {"module": "routers.work_schedules"},
    {"module": "routers.schedule_engine"},
    {"module": "routers.schedule_pipeline"},
    {"module": "routers.overdue_checker"},
    {"module": "routers.safety_template"},
    {"module": "routers.corrective_actions"},
]
```

### `router_registry/payment.py`

```python
ROUTERS = [
    {"module": "routers.payment"},
    {"module": "routers.payment_ops"},
    {"module": "routers.payment_billing"},
    {"module": "routers.contracts"},
    {"module": "routers.contracts_engine", "prefix": "/matching/contracts", "tags": ["계약서"]},
    {"module": "routers.quotes"},
    {"module": "routers.price_setting"},
    {"module": "routers.product_pricing"},
    {"module": "routers.price_policy"},
    {"module": "routers.connection_commission"},
    {"module": "routers.settlements", "prefix": "/settlements", "tags": ["정산"]},
]
```

### `router_registry/public.py`

```python
ROUTERS = [
    {"module": "routers.public"},
    {"module": "routers.site_public"},
    {"module": "routers.site_public", "attr": "admin_router"},
    {"module": "routers.public_admin"},
    {"module": "routers.public_pricing"},
    {"module": "routers.anonymous_diagnosis"},
    {"module": "routers.connect_registration"},
    {"module": "routers.admin_connect"},
    {"module": "routers.admin_pricing"},
    {"module": "routers.internal_inbox"},
    {"module": "routers.admin_inquiries"},
]
```

### `router_registry/diagnosis.py`

```python
ROUTERS = [
    {"module": "routers.diagnosis"},
    {"module": "routers.diagnosis_engine"},
    {"module": "routers.diagnosis_integrated"},
    {"module": "routers.diagnosis_autofill"},
    {"module": "routers.diagnosis_fields"},
    {"module": "routers.diagnosis_report"},
    {"module": "routers.diagnosis_proposal"},
    {"module": "routers.diagnosis_roi"},
    {"module": "routers.diagnosis_transform"},
    {"module": "routers.diagnosis_plan_recommend"},
    {"module": "routers.saas_setup"},
]
```

### `router_registry/construction.py`

```python
ROUTERS = [
    {"module": "routers.construction", "prefix": "/construction", "tags": ["건설안전"]},
    {"module": "routers.tbm"},
    {"module": "routers.tbm_templates"},
    {"module": "routers.safety_meetings"},
    {"module": "routers.risk_assessments"},
    {"module": "routers.worker_registry"},
    {"module": "routers.worker_check"},
    {"module": "routers.worker_home"},
    {"module": "routers.equipment_assets"},
    {"module": "routers.equipment_checkins"},
    {"module": "routers.engine_equipment"},
    {"module": "routers.engine_model"},
    {"module": "routers.education"},
    {"module": "routers.education_assign"},
    {"module": "routers.personnel"},
    {"module": "routers.safety_info"},
]
```

### `router_registry/external.py`

```python
ROUTERS = [
    {"module": "routers.weather"},
    {"module": "routers.juso"},
    {"module": "routers.building_register", "prefix": "/building-register"},
    {"module": "routers.biz_verify"},
    {"module": "routers.kosha_apis"},
    {"module": "routers.messaging"},
    {"module": "routers.fcm"},
    {"module": "routers.mail"},
    {"module": "routers.ai_copywrite"},
    {"module": "routers.event_trigger"},
    {"module": "routers.repair"},
    {"module": "routers.fix_chat"},
    {"module": "routers.fix_providers_api"},
    {"module": "routers.matching", "prefix": "/matching", "tags": ["매칭"]},
    {"module": "routers.matching_commission", "attr": "commission_router", "prefix": "/price-commission", "tags": ["수수료설정"]},
    {"module": "routers.experts", "prefix": "/experts", "tags": ["전문가"]},
    {"module": "routers.identity", "prefix": "/identity", "tags": ["본인인증"]},
    {"module": "routers.agent_service"},
    {"module": "routers.admin_review"},
    {"module": "routers.admin_stats"},
    {"module": "routers.cron_manager"},
    {"module": "routers.internal_api_registry"},
    {"module": "routers.report_api_registry"},
    {"module": "routers.fire_hazmat"},
    {"module": "routers.precedent_api"},
    {"module": "routers.contract_kmong"},
    {"module": "routers.contract_kmong"},
]
```

---

## Step 3. `main.py` 재작성

기존 main.py를 아래로 교체.

```python
# main.py — v6.0.0
# v6.0.0: Module Isolation — Safe Loading + 10 Module Groups
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


# === 모듈 그룹 로드 (격리) ===
def _load_all_modules():
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


# === Health ===
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
```

---

## Step 4. 검증

로컬에서 `uvicorn main:app --reload` 실행 후:

1. `GET /` → 모든 모듈 loaded, failed=0 확인
2. `GET /health` → 200 확인
3. 의도적 에러 주입 테스트:
   - `routers/compiler_core.py` 상단에 `raise ImportError("test")` 추가
   - 서버 재시작
   - `GET /` → legal_engine.failed=1, saas_core.status=ok 확인
   - SaaS API (auth, users 등) 정상 작동 확인
   - 에러 제거 후 원복

---

## 주의사항

- `routers/site_public.py`는 `router`와 `admin_router` 두 개를 export함
  → public 그룹에서 attr을 다르게 지정
- `routers/matching_commission.py`는 `commission_router`를 export
  → external 그룹에서 attr="commission_router" 지정
- prefix가 있는 라우터는 반드시 spec에 prefix 포함
  (building_register, experts, matching, settlements 등)
