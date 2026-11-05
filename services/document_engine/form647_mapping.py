"""FORM647 원장 조회 인프라 — LEG form647_review 스키마 접근 함수 모음.

LEG 실제 스키마 계약 (20261014044519 마이그레이션 기준):
  form_snapshots 컬럼: run_id, ek, frozen_index, api_target, frozen_name,
                       source_gate, service_sot_gate, frozen_payload, created_at
  주의: service_released 는 form_snapshots 에 없다. ingest_runs.service_released 에만
        존재하며 DB CHECK 제약(NOT service_released)으로 항상 false — 쿼리 대상 아님.

서비스 Gate:
  form_snapshots.service_sot_gate = 'BLOCKED' (DB CHECK 강제, 전체 647종)
  Gate 해제는 별도 LEG 거버넌스 승인 + 스키마 마이그레이션 필요.
  현재 _GATE_OPEN_VALUES 에 해당하는 값이 없으므로 모든 함수는 None 반환.
"""
from __future__ import annotations
import logging
import os
import re

log = logging.getLogger(__name__)

_FLSEQ_RE = re.compile(r'[?&]flSeq=(\d+)')

# FORM647 서비스 제공이 허용된 gate 상태값 (현재 해당 없음 — 647종 전체 BLOCKED)
_GATE_OPEN_VALUES = frozenset({"APPROVED", "OPEN", "RELEASED"})


def extract_flseq(file_url: str | None) -> int | None:
    """law.go.kr URL에서 flSeq 번호를 추출한다. 없으면 None."""
    if not file_url:
        return None
    m = _FLSEQ_RE.search(file_url)
    return int(m.group(1)) if m else None


def _build_leg_client():
    """LEG Supabase client 생성. 환경 변수 미설정 시 None (graceful)."""
    url = os.environ.get("LEG_SUPABASE_URL")
    key = os.environ.get("LEG_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as exc:
        log.warning("LEG client build failed: %s", exc)
        return None


def find_form647_snapshot(ek: int) -> dict | None:
    """ek에 해당하는 FORM647 form_snapshot을 조회한다.

    LEG 연결 불가 또는 미발견 시 None.
    반환 필드: ek, service_sot_gate
    """
    leg = _build_leg_client()
    if leg is None:
        return None
    try:
        res = (
            leg.schema("form647_review")
            .from_("form_snapshots")
            .select("ek, service_sot_gate")
            .eq("ek", str(ek))
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as exc:
        log.warning("form647 snapshot lookup failed ek=%s: %s", ek, exc)
        return None


def get_form647_storage_path(ek: int, file_type: str = "HWP") -> str | None:
    """source_binary_snapshots에서 private_storage_path를 조회한다.

    LEG 연결 불가 또는 미발견 시 None.
    """
    leg = _build_leg_client()
    if leg is None:
        return None
    try:
        res = (
            leg.schema("form647_review")
            .from_("source_binary_snapshots")
            .select("private_storage_path")
            .eq("ek", ek)
            .eq("file_type", file_type)
            .limit(1)
            .execute()
        )
        return res.data[0]["private_storage_path"] if res.data else None
    except Exception as exc:
        log.warning("form647 storage path lookup failed ek=%s: %s", ek, exc)
        return None


def is_form647_service_gate_open(snapshot: dict) -> bool:
    """서비스 Gate 통과 여부를 확인한다.

    현재 647종 전체 BLOCKED — 항상 False.
    Gate 해제는 LEG 거버넌스 승인 + DB 마이그레이션 후 service_sot_gate 값 변경 필요.
    service_released 는 form_snapshots 에 없으므로 확인하지 않는다.
    """
    return snapshot.get("service_sot_gate") in _GATE_OPEN_VALUES


# Storage 경로 계산에 사용하는 고정 Run ID (form647-remediation-002)
_RUN_ID = "form647-remediation-002-714df47a637e3e73"


def get_form647_detail(ek: int) -> dict | None:
    """Gate 통과 시 공개 표시용 상세 정보를 반환한다.

    LEG 연결 불가·미발견·Gate 미통과 시 None.
    반환: ek, frozen_name, api_target, file_types (["HWP"] 또는 ["HWP","PDF"])
    """
    leg = _build_leg_client()
    if leg is None:
        return None
    try:
        res = (
            leg.schema("form647_review")
            .from_("form_snapshots")
            .select("ek, service_sot_gate, frozen_name, api_target")
            .eq("ek", str(ek))
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.warning("form647 detail lookup failed ek=%s: %s", ek, exc)
        return None
    if not res.data:
        return None
    snap = res.data[0]
    if not is_form647_service_gate_open(snap):
        return None
    # licbyl(법령별) 497종은 HWP+PDF 쌍 보유, admbyl(행정규칙별) 150종은 HWP 단독
    file_types = ["HWP", "PDF"] if snap["api_target"] == "licbyl" else ["HWP"]
    return {
        "ek": snap["ek"],
        "frozen_name": snap["frozen_name"],
        "api_target": snap["api_target"],
        "file_types": file_types,
    }


def form647_storage_path(ek: int, api_target: str, file_type: str) -> str:
    """ek·api_target·file_type에서 form-originals Storage 경로를 도출한다.

    file_type: "HWP" 또는 "PDF"
    """
    stem = f"{ek}_{api_target}"   # e.g. 15267319_licbyl
    ext = "hwp" if file_type == "HWP" else "pdf"
    return f"form647/{_RUN_ID}/{ext}/{stem}.{ext}"
