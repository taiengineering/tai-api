"""doc_m004_service_adapter.py — WO-TAI-DOC-M004-EXISTING-DOCUMENT-SERVICE-ADAPTER-004

세 서비스 경로(DOWNLOAD / WEB_EDIT / AUTO)의 제공 가능 여부를 반환하는 최소 Adapter.

원칙:
  - 명시적 연결이 확인된 경우에만 서비스 경로를 AVAILABLE로 반환
  - obligation_code 없이 atom_id만 있는 경우: 모든 경로 UNRESOLVED (MC-001 Gap)
  - 추정 매핑 없음. DB 쓰기 없음. 신규 테이블/엔진 없음.
  - 기존 WP-L2 resolve_binding + WP-L3 resolve_runtime_bridge 재사용

DOWNLOAD:
  obligation_code → obligation_form_mapping → form_templates.hwp_url
  hwp_url 존재 + binding NOT REVIEW_REQUIRED → AVAILABLE

WEB_EDIT / AUTO:
  WP-L3 resolve_runtime_bridge → runtime_availability == READY_FOR_EDIT → AVAILABLE
  WEB_EDIT = 수동작성, AUTO = 자동입력 — 현재 동일 스키마 기반

MC-001 Gap:
  atom_id 단독 입력 → 모든 경로 UNRESOLVED
  (inspection_sets.legal_obligation_atom_id ↔ obligation_code 브리지 없음)

운영 DB 현황 (2026-10-15):
  APPROVED schema with catalog_document_id → 0건 (WEB_EDIT/AUTO=AVAILABLE 불가)
  obligation_form_mapping → form_templates 연결 → 5건 (DOWNLOAD 경로 가능)
"""
from __future__ import annotations

from typing import Optional

from services.doc_m004_binding_adapter import (
    resolve_binding,
    REVIEW_REQUIRED as BINDING_REVIEW_REQUIRED,
)
from services.doc_m004_runtime_bridge import resolve_runtime_bridge
from services.doc_m004_dryrun import UNVERIFIED

# 서비스 경로 상태값
AVAILABLE        = "AVAILABLE"
UNRESOLVED       = "UNRESOLVED"
REVIEW_REQUIRED  = "REVIEW_REQUIRED"
PREPARING        = "PREPARING"
NO_SCHEMA        = "NO_SCHEMA"

_MC001_MSG = (
    "MC-001: obligation_code 브리지 없음 — "
    "atom_id 단독으로 서식 서비스 진입 불가"
)

_RUNTIME_STATUS_MAP = {
    "READY_FOR_EDIT":    AVAILABLE,
    "PREPARING":         PREPARING,
    "NO_SCHEMA":         NO_SCHEMA,
    "NO_CATALOG_BINDING": UNRESOLVED,
    "REVIEW_REQUIRED":   REVIEW_REQUIRED,
    UNVERIFIED:          UNRESOLVED,
}


# ── DOWNLOAD 경로 ─────────────────────────────────────────────────────────────

def _resolve_download(sb, form_code: Optional[str], binding_status: str, review_reason) -> dict:
    """form_templates.hwp_url 존재 여부로 DOWNLOAD 가능 여부 판정."""
    base: dict = {"form_code": None, "hwp_url": None}

    if binding_status == BINDING_REVIEW_REQUIRED:
        return {
            **base,
            "form_code": form_code if form_code and form_code != UNVERIFIED else None,
            "available": False,
            "status": REVIEW_REQUIRED,
            "reason": review_reason or "binding_status=REVIEW_REQUIRED",
        }

    if not form_code or form_code == UNVERIFIED:
        return {
            **base,
            "available": False,
            "status": UNRESOLVED,
            "reason": "obligation_form_mapping 연결 없음",
        }

    res = (
        sb.table("form_templates")
        .select("hwp_url")
        .eq("form_code", form_code)
        .limit(1)
        .execute()
    )
    row = (res.data or [None])[0]
    hwp_url = row.get("hwp_url") if row else None

    if hwp_url:
        return {
            "available": True,
            "form_code": form_code,
            "hwp_url": hwp_url,
            "status": AVAILABLE,
            "reason": None,
        }
    return {
        "available": False,
        "form_code": form_code,
        "hwp_url": None,
        "status": UNRESOLVED,
        "reason": "form_templates.hwp_url 없음",
    }


# ── WEB_EDIT / AUTO 경로 ──────────────────────────────────────────────────────

def _resolve_runtime_path(bridge: dict) -> dict:
    """WP-L3 bridge 결과 → WEB_EDIT / AUTO 공통 경로 상태."""
    runtime_avail = bridge.get("runtime_availability", UNVERIFIED)
    status = _RUNTIME_STATUS_MAP.get(runtime_avail, UNRESOLVED)
    schema_id = bridge.get("runtime_form_schema_id")
    if schema_id == UNVERIFIED:
        schema_id = None

    return {
        "available": status == AVAILABLE,
        "schema_id": schema_id if status == AVAILABLE else None,
        "status": status,
        "reason": bridge.get("review_reason") if status == REVIEW_REQUIRED else None,
    }


# ── 메인 진입점 ───────────────────────────────────────────────────────────────

def get_service_availability(
    sb,
    obligation_code: Optional[str] = None,
    atom_id: Optional[str] = None,
    official_evidence: Optional[dict] = None,
) -> dict:
    """의무 식별자로 서비스 경로별 제공 가능 여부 반환.

    Args:
        sb: Supabase 클라이언트 (READ-ONLY)
        obligation_code: 의무 코드 text — WP-L2/L3 진입점
        atom_id: inspection_sets.legal_obligation_atom_id (UUID)
                 obligation_code 없이 단독 전달 시 MC-001 UNRESOLVED
        official_evidence: {law_api_id, law_mst_no, law_version_conflict}

    Returns:
        {
          "obligation_code": str | None,
          "atom_id": str | None,
          "DOWNLOAD": {available, form_code, hwp_url, status, reason},
          "WEB_EDIT": {available, schema_id, status, reason},
          "AUTO":     {available, schema_id, status, reason},
          "overall_status": "FULLY_AVAILABLE" | "PARTIAL_AVAILABLE" | "ALL_UNRESOLVED",
          "mc001_gap": bool,
        }
    """
    def _unresolved_path(reason: str) -> dict:
        return {"available": False, "status": UNRESOLVED, "reason": reason}

    # MC-001: atom_id만 있고 obligation_code 없음
    if atom_id and not obligation_code:
        return {
            "obligation_code": None,
            "atom_id": atom_id,
            "DOWNLOAD": {**_unresolved_path(_MC001_MSG), "form_code": None, "hwp_url": None},
            "WEB_EDIT": {**_unresolved_path(_MC001_MSG), "schema_id": None},
            "AUTO":     {**_unresolved_path(_MC001_MSG), "schema_id": None},
            "overall_status": "ALL_UNRESOLVED",
            "mc001_gap": True,
        }

    # obligation_code도 atom_id도 없음
    if not obligation_code:
        empty_reason = "obligation_code 없음"
        return {
            "obligation_code": None,
            "atom_id": atom_id,
            "DOWNLOAD": {**_unresolved_path(empty_reason), "form_code": None, "hwp_url": None},
            "WEB_EDIT": {**_unresolved_path(empty_reason), "schema_id": None},
            "AUTO":     {**_unresolved_path(empty_reason), "schema_id": None},
            "overall_status": "ALL_UNRESOLVED",
            "mc001_gap": False,
        }

    # obligation_code 있음 → WP-L2 binding
    binding = resolve_binding(sb, obligation_code, official_evidence)

    # DOWNLOAD
    download = _resolve_download(
        sb,
        form_code=binding.get("form_code"),
        binding_status=binding.get("binding_status", ""),
        review_reason=binding.get("review_reason"),
    )

    # WEB_EDIT / AUTO — WP-L3
    bridge = resolve_runtime_bridge(sb, obligation_code, official_evidence)
    runtime_path = _resolve_runtime_path(bridge)
    web_edit = runtime_path
    auto = {**runtime_path}  # 현재 동일 스키마 기반

    # overall_status
    available_paths = [download["available"], web_edit["available"], auto["available"]]
    if all(available_paths):
        overall = "FULLY_AVAILABLE"
    elif any(available_paths):
        overall = "PARTIAL_AVAILABLE"
    else:
        overall = "ALL_UNRESOLVED"

    return {
        "obligation_code": obligation_code,
        "atom_id": atom_id,
        "DOWNLOAD": download,
        "WEB_EDIT": web_edit,
        "AUTO": auto,
        "overall_status": overall,
        "mc001_gap": False,
    }
