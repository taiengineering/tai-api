"""운영 실행 게이트 서비스 (실환불·실발행 해제 절차).

Goal: G-ms5pdquz-9e76e5
- 실호출 게이트(REFUND_LIVE=이니시스 실취소, INVOICE_LIVE=팝빌 실발행)를 두 소스의 OR로 결정:
  (1) 배포 ENV 플래그(인프라 레벨 강제 on/off) 또는 (2) ops_feature_gate DB 토글(어드민 활성화).
- '준비완료 → 활성화' 절차: 어드민이 채널별 체크리스트(연동 키·SDK)를 통과해야만 DB 게이트를 켤 수 있다.
- 기본은 잠금(off). 표 미적용/조회실패는 잠금으로 폴백(보수적). 토글은 감사(admin_ops_audit_logs).
- 이 서비스는 실호출을 하지 않는다 — 실환불/실발행은 refund_svc/invoice_svc 가 게이트 통과 시 수행.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import audit_svc

log = logging.getLogger(__name__)

_GATE_TABLE = "ops_feature_gate"
_CHANNELS = ("REFUND_LIVE", "INVOICE_LIVE")


def _env_on(channel: str) -> bool:
    return os.getenv(channel, "").strip().lower() in ("1", "true", "on", "yes")


def _db_enabled(channel: str) -> bool:
    """DB 게이트 활성 여부. 표 미적용/조회실패는 False(잠금)."""
    try:
        r = (get_supabase().table(_GATE_TABLE).select("enabled")
             .eq("gate_key", channel).limit(1).execute().data)
        return bool(r and r[0].get("enabled"))
    except Exception:  # noqa: BLE001 — 표 미적용 등 → 잠금
        return False


def is_live(channel: str) -> bool:
    """실호출 허용 여부 = ENV on OR DB 게이트 on."""
    return _env_on(channel) or _db_enabled(channel)


def _gate_source(channel: str) -> str:
    if _env_on(channel):
        return "ENV"
    if _db_enabled(channel):
        return "DB"
    return "OFF"


# ── 준비완료 체크리스트 ──────────────────────────────────────────────
def _refund_checklist() -> List[Dict[str, Any]]:
    """이니시스 실취소 전제(연동 상수). payment_helpers 상수 truthiness 검사."""
    try:
        from services.payment_helpers import (
            INICIS_CLIENT_IP, INICIS_INIAPI_KEY, INICIS_MID, REFUND_URL,
        )
        return [
            {"key": "이니시스 INIAPI 키(INICIS_INIAPI_KEY)", "ok": bool(INICIS_INIAPI_KEY)},
            {"key": "상점 아이디(INICIS_MID)", "ok": bool(INICIS_MID)},
            {"key": "화이트리스트 IP(INICIS_CLIENT_IP)", "ok": bool(INICIS_CLIENT_IP)},
            {"key": "취소 API URL(REFUND_URL)", "ok": bool(REFUND_URL)},
        ]
    except Exception as e:  # noqa: BLE001
        log.warning("[GATE] refund checklist 실패: %s", e)
        return [{"key": "이니시스 설정 로드", "ok": False}]


def _invoice_checklist() -> List[Dict[str, Any]]:
    """팝빌 실발행 전제(env + SDK)."""
    link = os.getenv("POPBILL_LINK_ID", "").strip()
    sk = os.getenv("POPBILL_SECRET_KEY", "").strip()
    corp = os.getenv("TAI_CORP_NUM", "").strip()
    name = os.getenv("TAI_CORP_NAME", "").strip()
    ceo = os.getenv("TAI_CEO_NAME", "").strip()
    try:
        import popbill  # noqa: F401
        sdk_ok = True
    except Exception:  # noqa: BLE001
        sdk_ok = False
    return [
        {"key": "팝빌 LinkID(POPBILL_LINK_ID)", "ok": bool(link)},
        {"key": "팝빌 SecretKey(POPBILL_SECRET_KEY)", "ok": bool(sk)},
        {"key": "공급자 사업자번호(TAI_CORP_NUM)", "ok": bool(corp)},
        {"key": "공급자 상호(TAI_CORP_NAME)", "ok": bool(name)},
        {"key": "공급자 대표자(TAI_CEO_NAME)", "ok": bool(ceo)},
        {"key": "팝빌 SDK 설치(popbill)", "ok": sdk_ok},
    ]


def readiness() -> Dict[str, Any]:
    """채널별 체크리스트 + 준비완료 여부 + 현재 실호출 상태."""
    rc = _refund_checklist()
    ic = _invoice_checklist()
    return {
        "refund": {
            "checklist": rc,
            "ready": all(i["ok"] for i in rc),
            "live": is_live("REFUND_LIVE"),
            "source": _gate_source("REFUND_LIVE"),
            "env_forced": _env_on("REFUND_LIVE"),
        },
        "invoice": {
            "checklist": ic,
            "ready": all(i["ok"] for i in ic),
            "live": is_live("INVOICE_LIVE"),
            "source": _gate_source("INVOICE_LIVE"),
            "env_forced": _env_on("INVOICE_LIVE"),
            "is_test": os.getenv("POPBILL_IS_TEST", "true").lower() == "true",
        },
    }


class GateError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _channel_ready(channel: str) -> bool:
    r = readiness()
    if channel == "REFUND_LIVE":
        return r["refund"]["ready"]
    if channel == "INVOICE_LIVE":
        return r["invoice"]["ready"]
    return False


def set_gate(channel: str, enabled: bool, by: Optional[str] = None,
             note: Optional[str] = None) -> Dict[str, Any]:
    """DB 게이트 토글. 활성화(enabled=True)는 준비완료 통과 시에만 허용. 감사 기록."""
    channel = (channel or "").upper()
    if channel not in _CHANNELS:
        raise GateError(400, f"지원하지 않는 게이트: {channel}")

    if enabled and not _channel_ready(channel):
        raise GateError(409, "준비완료 체크리스트를 통과하지 못했습니다. 연동 설정을 먼저 완료하세요.")

    from services.payment_helpers import now_iso
    row = {
        "gate_key": channel,
        "enabled": enabled,
        "enabled_by": by if enabled else None,
        "enabled_at": now_iso() if enabled else None,
        "note": note,
        "updated_at": now_iso(),
    }
    try:
        get_supabase().table(_GATE_TABLE).upsert(row, on_conflict="gate_key").execute()
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if any(h in msg for h in ("does not exist", "relation", "42p01", "schema cache")):
            raise GateError(409, "ops_feature_gate 스키마가 아직 적용되지 않았습니다. 마이그레이션 적용 후 다시 시도하세요.")
        raise GateError(500, f"게이트 저장 실패: {e}")

    audit_svc.record(
        "GATE_ACTIVATE" if enabled else "GATE_DEACTIVATE", "ops_feature_gate",
        entity_id=channel, actor_id=by,
        after={"enabled": enabled, "note": note},
    )
    return {"gate_key": channel, "enabled": enabled, "source": _gate_source(channel)}
