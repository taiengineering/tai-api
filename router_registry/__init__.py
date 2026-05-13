"""TAI Router Registry v1.0.0 — Safe Loading with Module Isolation.

한 라우터 import 실패 → 해당 라우터만 스킵, 나머지 정상.
Slack #tai-alert 로 실패 알림 발송.
"""
import importlib
import logging
from typing import Any, Dict, List

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
        app: FastAPI instance
        group_name: group identifier (e.g. "legal_engine")
        router_specs: list of router specs
            [{"module": "routers.auth", "attr": "router", "prefix": "", "tags": [...]}]

    Returns:
        {"group": str, "loaded": int, "failed": int, "failed_modules": [str], "status": str}
    """
    loaded, failed = 0, 0
    failed_modules: list[str] = []

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
    logger.info(
        "[%s] loaded=%d, failed=%d, status=%s",
        group_name, loaded, failed, status,
    )
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
