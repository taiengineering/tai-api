"""FORM647 원장 조회 인프라 — LEG form647_review 스키마 접근 함수 모음.

현재 연결 상태 (R3 SOURCE_IV 보정 결과):
  document_forms.file_url에 포함된 flSeq와 FORM647 ek는 별도 식별자다.
  flSeq를 ek로 직접 사용하는 크로스워크가 운영 DB에서 입증되지 않았다.
  미연결 81종 가운데 flSeq 보유 문서: 1종(DOC-FAC-019)이며,
  그 flSeq 값도 FORM647 ek와 직접 일치하지 않는다(0건).

이 모듈의 함수는 doc_id → ek 크로스워크가 별도로 확립된 이후에만
라우터에 연결한다. 현재 router에서 임포트하지 않는다.

서비스 Gate:
  form_snapshots.service_sot_gate = BLOCKED (전체 647종)
  Gate 해제는 별도 LEG 거버넌스 승인 필요.
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
    반환 필드: ek, service_sot_gate, service_released
    """
    leg = _build_leg_client()
    if leg is None:
        return None
    try:
        res = (
            leg.schema("form647_review")
            .from_("form_snapshots")
            .select("ek, service_sot_gate, service_released")
            .eq("ek", ek)
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
    Gate 해제 후 service_released=True + service_sot_gate∈GATE_OPEN_VALUES 시 True.
    """
    return (
        snapshot.get("service_released") is True
        and snapshot.get("service_sot_gate") in _GATE_OPEN_VALUES
    )
