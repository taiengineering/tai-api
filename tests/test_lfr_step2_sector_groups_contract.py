"""WO-LFR-FF07-STEP2-C6-PATCH-074 — Step2 sector_groups 반환 계약 테스트.

sector_groups가 run_diagnose_step2() 반환 dict에 올바르게 포함되는지 검증한다.
NameError 재발 방지 및 정상 sector/공종 조합 계약을 보장한다.
DB write = 0 / LEG 직접 호출 없음.
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from services.legal_engine_svc import run_diagnose_step2
from services.legal_helpers import get_sector_groups
from services.legal_rules import normalize_sector_db


def _make_body(sector: str = "CONSTRUCTION", work_types: List[str] | None = None):
    body = MagicMock()
    body.factory_id = None
    body.diagnosis_id = None
    body.sector = sector
    body.construction_work_types = work_types or []
    body.work_type_codes = []
    body.kcsc_process_ids = []
    body.processes = []
    body.construction_types = []
    return body


def _make_supabase(rules: List[Dict[str, Any]] | None = None):
    sb = MagicMock()
    result = MagicMock()
    result.data = rules or []
    sb.table.return_value.select.return_value.eq.return_value.lte.return_value.execute.return_value = result
    sb.table.return_value.select.return_value.execute.return_value = result
    return sb


# ── S1: 정상 sector (CONSTRUCTION) — sector_groups 존재 ─────────────────────

def test_S1_construction_sector_groups_present():
    body = _make_body(sector="CONSTRUCTION")
    with patch("services.legal_engine_svc.fetch_diagnosis_rules", return_value=[]):
        result = run_diagnose_step2(_make_supabase(), body, "test")
    assert "sector_groups" in result
    expected = get_sector_groups(normalize_sector_db("CONSTRUCTION"))
    assert result["sector_groups"] == expected


# ── S2: 공종 없음 — sector_groups 반환, rule_count = 0 ───────────────────────

def test_S2_no_work_types_sector_groups_present():
    body = _make_body(sector="CONSTRUCTION", work_types=[])
    with patch("services.legal_engine_svc.fetch_diagnosis_rules", return_value=[]):
        result = run_diagnose_step2(_make_supabase(), body, "test")
    assert "sector_groups" in result
    assert isinstance(result["sector_groups"], list)
    assert result["rule_count"] == 0


# ── S3: 공종 지정 — sector_groups 반환 ──────────────────────────────────────

def test_S3_with_work_types_sector_groups_present():
    body = _make_body(sector="CONSTRUCTION", work_types=["CRANE", "EXCAVATION"])
    with patch("services.legal_engine_svc.fetch_diagnosis_rules", return_value=[]):
        result = run_diagnose_step2(_make_supabase(), body, "test")
    assert "sector_groups" in result
    assert isinstance(result["sector_groups"], list)


# ── S4: NameError 없음 — sector_groups 할당 후 반환 가능 ─────────────────────

def test_S4_no_name_error_on_return():
    body = _make_body(sector="CONSTRUCTION")
    try:
        with patch("services.legal_engine_svc.fetch_diagnosis_rules", return_value=[]):
            run_diagnose_step2(_make_supabase(), body, "test")
    except NameError as e:
        pytest.fail(f"NameError 발생: {e}")
