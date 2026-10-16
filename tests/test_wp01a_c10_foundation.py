"""WO-E2E2000-WP01-A-C10-FOUNDATION-001 B-2/B-3 — persist 보정 + CONSTRUCTION site_id 저장 테스트.

검증 항목:
  T01: C10 INSERT → inspection_materialization_status = 'PENDING'
  T02: canonical writer 성공 → MATERIALIZED 업데이트
  T03: canonical writer 예외 → FAILED 업데이트
  T04: legacy 차단(BLOCKED_LEGACY_ROWS) → BLOCKED_LEGACY_ROWS 업데이트
  T05: status UPDATE 실패 → PENDING 유지 (허위 MATERIALIZED 금지)
  T06: CONSTRUCTION site_id 저장 → input_data 에 site_id 포함
  T07: INDUSTRIAL → input_data 에 site_id 없음 (기존 계약 유지)
  T08: BUILDING → input_data 에 site_id 없음 (기존 계약 유지)
  T09: CONSTRUCTION site_id None → input_data 에 site_id 키 없음
  T10: finalize_saas_leg_result site_id 전달 체인
  T11: full_result EXACT 보존 (보정/변환 0)
  T12: inspection_materialization_status 컬럼 마이그레이션 파일 존재 확인

DB/network 불필요.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from unittest.mock import patch
from uuid import uuid4

import pytest

from services.saas_diagnosis_result_persistence import (
    SaasPersistError,
    finalize_saas_leg_result,
    persist_saas_full_result,
    run_saas_c10_and_materialize,
)

# ── 공통 픽스처 ────────────────────────────────────────────────────────────────

_FAC_ID = str(uuid4())
_COMPANY_ID = str(uuid4())
_SITE_ID = str(uuid4())
_DIAG_ID = str(uuid4())


def _full_result(sector: str = "INDUSTRIAL") -> Dict[str, Any]:
    return {
        "sector": sector,
        "engine_version": "leg-runtime-v3",
        "obligations_raw": [],
        "facility_used": {"worker_count": 50},
    }


class _InsertRow:
    """supabase insert() 성공 stub — 저장된 row 반환."""
    def __init__(self, diag_id: str = _DIAG_ID):
        self._diag_id = diag_id

    def execute(self):
        class _R:
            data = [{"id": self._diag_id}]
        return _R()


class _InsertFail:
    """supabase insert() data=None stub."""
    def execute(self):
        class _R:
            data = None
        return _R()


class _InsertEmpty:
    """supabase insert() data=[] stub."""
    def execute(self):
        class _R:
            data = []
        return _R()


class _UpdateCapture:
    """supabase update() 호출을 캡처하는 stub."""
    def __init__(self):
        self.called_with: Optional[dict] = None
        self._payload: Optional[dict] = None

    def update(self, payload: dict):
        self._payload = payload
        return self

    def eq(self, *_args, **_kw):
        return self

    def execute(self):
        self.called_with = self._payload
        class _R:
            data = [{}]
        return _R()


class _UpdateFail:
    """supabase update() 예외 stub."""
    def update(self, *_):
        return self

    def eq(self, *_, **__):
        return self

    def execute(self):
        raise RuntimeError("DB update failed")


class _InspectionSetsEmpty:
    """inspection_sets 에 legacy null-atom row 없음."""
    def select(self, *_):
        return self
    def eq(self, *_, **__):
        return self
    def is_(self, *_):
        return self
    def limit(self, *_):
        return self
    def execute(self):
        class _R:
            data = []
        return _R()


class _InspectionSetsLegacy:
    """inspection_sets 에 legacy null-atom row 존재 → BLOCKED."""
    def select(self, *_):
        return self
    def eq(self, *_, **__):
        return self
    def is_(self, *_):
        return self
    def limit(self, *_):
        return self
    def execute(self):
        class _R:
            data = [{"id": str(uuid4())}]
        return _R()


class _FactorySupa:
    """factories.company_id 조회 stub."""
    def __init__(self, company_id: str = _COMPANY_ID):
        self._cid = company_id

    def table(self, name: str):
        return self

    def select(self, *_):
        return self

    def eq(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        class _R:
            data = [{"company_id": self._cid}]
        return _R()


# ── 복합 stub: insert + update 분기 ──────────────────────────────────────────

class _FakeSupa:
    """table 이름으로 분기하는 복합 fake."""
    def __init__(
        self,
        *,
        diag_id: str = _DIAG_ID,
        update_stub=None,
        inspection_stub=None,
        company_id: str = _COMPANY_ID,
    ):
        self._diag_id = diag_id
        self._update = update_stub or _UpdateCapture()
        self._inspection = inspection_stub or _InspectionSetsEmpty()
        self._company_id = company_id
        self._inserted: Optional[dict] = None  # 저장된 row 캡처

    def table(self, name: str):
        if name == "anonymous_diagnosis_results":
            return _AnonDiagTable(
                diag_id=self._diag_id,
                update_stub=self._update,
                capture_ref=self,
            )
        if name == "inspection_sets":
            return self._inspection
        if name == "factories":
            return _FactorySupa(company_id=self._company_id)
        return self

    def select(self, *_): return self
    def eq(self, *_, **__): return self
    def limit(self, *_): return self
    def execute(self):
        class _R: data = []
        return _R()


class _AnonDiagTable:
    """anonymous_diagnosis_results 분기 stub."""
    def __init__(self, diag_id: str, update_stub, capture_ref: _FakeSupa):
        self._diag_id = diag_id
        self._update_stub = update_stub
        self._ref = capture_ref
        self._op = "select"

    def insert(self, row: dict):
        self._ref._inserted = row
        self._op = "insert"
        return _InsertRow(self._diag_id)

    def update(self, payload: dict):
        return self._update_stub.update(payload)

    def select(self, *_): return self
    def eq(self, *_, **__): return self
    def limit(self, *_): return self
    def execute(self):
        class _R: data = []
        return _R()


# ── T01: INSERT → PENDING ───────────────────────────────────────────────────

def test_T01_insert_sets_pending():
    """persist_saas_full_result: INSERT 시 inspection_materialization_status='PENDING'."""
    captured: Dict[str, Any] = {}

    class _Cap:
        def table(self, _):
            return self
        def insert(self, row: dict):
            captured.update(row)
            return _InsertRow()
        def execute(self):
            class _R: data = [{"id": _DIAG_ID}]
            return _R()

    persist_saas_full_result(
        _Cap(),
        factory_id=_FAC_ID,
        company_id=_COMPANY_ID,
        full_result=_full_result(),
    )
    assert captured.get("inspection_materialization_status") == "PENDING"


# ── T02: writer 성공 → MATERIALIZED ─────────────────────────────────────────

def test_T02_writer_success_updates_materialized():
    """canonical writer 성공 → MATERIALIZED 업데이트."""
    uc = _UpdateCapture()
    supa = _FakeSupa(update_stub=uc)

    with patch(
        "services.saas_diagnosis_result_persistence.materialize_saas_inspection",
        return_value={"status": "MATERIALIZED", "inserted": 3, "refreshed": 0, "skipped": 0},
    ):
        result = run_saas_c10_and_materialize(supa, _FAC_ID, _COMPANY_ID, _full_result())

    assert result["inspection_materialization"]["status"] == "MATERIALIZED"
    assert uc.called_with == {"inspection_materialization_status": "MATERIALIZED"}


# ── T03: writer 예외 → FAILED ────────────────────────────────────────────────

def test_T03_writer_exception_updates_failed():
    """canonical writer 예외 → FAILED 업데이트."""
    uc = _UpdateCapture()
    supa = _FakeSupa(update_stub=uc)

    with patch(
        "services.saas_diagnosis_result_persistence.materialize_saas_inspection",
        side_effect=RuntimeError("writer broke"),
    ):
        result = run_saas_c10_and_materialize(supa, _FAC_ID, _COMPANY_ID, _full_result())

    assert result["inspection_materialization"]["status"] == "FAILED"
    assert uc.called_with == {"inspection_materialization_status": "FAILED"}


# ── T04: legacy 차단 → BLOCKED_LEGACY_ROWS ──────────────────────────────────

def test_T04_legacy_blocked_updates_blocked():
    """BLOCKED_LEGACY_ROWS → BLOCKED_LEGACY_ROWS 업데이트."""
    uc = _UpdateCapture()
    supa = _FakeSupa(update_stub=uc)

    with patch(
        "services.saas_diagnosis_result_persistence.materialize_saas_inspection",
        return_value={"status": "BLOCKED_LEGACY_ROWS"},
    ):
        result = run_saas_c10_and_materialize(supa, _FAC_ID, _COMPANY_ID, _full_result())

    assert result["inspection_materialization"]["status"] == "BLOCKED_LEGACY_ROWS"
    assert uc.called_with == {"inspection_materialization_status": "BLOCKED_LEGACY_ROWS"}


# ── T05: status UPDATE 실패 → PENDING 유지 (허위 MATERIALIZED 금지) ────────────

def test_T05_update_failure_keeps_pending(caplog):
    """status UPDATE DB 오류 → row 가 PENDING 유지됨(허위 MATERIALIZED 방지). 예외 전파 금지."""
    uf = _UpdateFail()
    supa = _FakeSupa(update_stub=uf)

    with patch(
        "services.saas_diagnosis_result_persistence.materialize_saas_inspection",
        return_value={"status": "MATERIALIZED"},
    ), caplog.at_level(logging.ERROR, logger="services.saas_diagnosis_result_persistence"):
        # 예외가 밖으로 전파되면 안 됨
        result = run_saas_c10_and_materialize(supa, _FAC_ID, _COMPANY_ID, _full_result())

    # INSERT 시 PENDING 이므로 UPDATE 실패 → row 는 PENDING 유지
    assert result["inspection_materialization"]["status"] == "MATERIALIZED"
    assert any("status update failed" in r.message for r in caplog.records)


# ── T06: CONSTRUCTION site_id 저장 ──────────────────────────────────────────

def test_T06_construction_site_id_stored_in_input_data():
    """CONSTRUCTION + site_id → input_data['site_id'] 포함."""
    captured: Dict[str, Any] = {}

    class _Cap:
        def table(self, _):
            return self
        def insert(self, row: dict):
            captured.update(row)
            return _InsertRow()
        def execute(self):
            class _R: data = [{"id": _DIAG_ID}]
            return _R()

    fr = _full_result("CONSTRUCTION")
    persist_saas_full_result(
        _Cap(),
        factory_id=_FAC_ID,
        company_id=_COMPANY_ID,
        full_result=fr,
        site_id=_SITE_ID,
    )
    assert captured["input_data"]["site_id"] == _SITE_ID
    assert captured["input_data"]["factory_id"] == _FAC_ID
    assert captured["input_data"]["sector"] == "CONSTRUCTION"


# ── T07: INDUSTRIAL → site_id 없음 ──────────────────────────────────────────

def test_T07_industrial_no_site_id_in_input_data():
    """INDUSTRIAL: site_id 파라미터 없음 → input_data 에 site_id 키 없음."""
    captured: Dict[str, Any] = {}

    class _Cap:
        def table(self, _): return self
        def insert(self, row):
            captured.update(row)
            return _InsertRow()
        def execute(self):
            class _R: data = [{"id": _DIAG_ID}]
            return _R()

    persist_saas_full_result(
        _Cap(),
        factory_id=_FAC_ID,
        company_id=_COMPANY_ID,
        full_result=_full_result("INDUSTRIAL"),
    )
    assert "site_id" not in captured["input_data"]


# ── T08: BUILDING → site_id 없음 ────────────────────────────────────────────

def test_T08_building_no_site_id_in_input_data():
    """BUILDING: site_id=None → input_data 에 site_id 키 없음."""
    captured: Dict[str, Any] = {}

    class _Cap:
        def table(self, _): return self
        def insert(self, row):
            captured.update(row)
            return _InsertRow()
        def execute(self):
            class _R: data = [{"id": _DIAG_ID}]
            return _R()

    persist_saas_full_result(
        _Cap(),
        factory_id=_FAC_ID,
        company_id=_COMPANY_ID,
        full_result=_full_result("BUILDING"),
        site_id=None,
    )
    assert "site_id" not in captured["input_data"]


# ── T09: CONSTRUCTION site_id 빈 값 → 저장 안 함 ────────────────────────────

def test_T09_construction_empty_site_id_not_stored():
    """CONSTRUCTION + site_id='' → input_data 에 site_id 저장 안 됨."""
    captured: Dict[str, Any] = {}

    class _Cap:
        def table(self, _): return self
        def insert(self, row):
            captured.update(row)
            return _InsertRow()
        def execute(self):
            class _R: data = [{"id": _DIAG_ID}]
            return _R()

    persist_saas_full_result(
        _Cap(),
        factory_id=_FAC_ID,
        company_id=_COMPANY_ID,
        full_result=_full_result("CONSTRUCTION"),
        site_id="",
    )
    assert "site_id" not in captured["input_data"]


# ── T10: finalize_saas_leg_result site_id 전달 체인 ─────────────────────────

def test_T10_finalize_site_id_chain():
    """finalize_saas_leg_result(site_id=...) → persist 까지 site_id 전달."""
    captured: Dict[str, Any] = {}

    class _ChainSupa:
        def table(self, name):
            if name == "factories":
                return self
            if name == "anonymous_diagnosis_results":
                return _AnonCapture(captured)
            return self
        def select(self, *_): return self
        def eq(self, *_, **__): return self
        def limit(self, *_): return self
        def execute(self):
            class _R: data = [{"company_id": _COMPANY_ID}]
            return _R()

    class _AnonCapture:
        def __init__(self, cap):
            self._cap = cap
        def insert(self, row):
            self._cap.update(row)
            return _InsertRow()
        def update(self, *_): return self
        def eq(self, *_, **__): return self
        def execute(self):
            class _R: data = [{"id": _DIAG_ID}]
            return _R()

    with patch(
        "services.saas_diagnosis_result_persistence.materialize_saas_inspection",
        return_value={"status": "MATERIALIZED"},
    ), patch(
        "services.saas_diagnosis_result_persistence._record_materialization_status"
    ):
        finalize_saas_leg_result(
            _ChainSupa(),
            factory_id=_FAC_ID,
            leg_out={
                "full_result": _full_result("CONSTRUCTION"),
                "contract_version": "v1",
                "unresolved_fields": [],
            },
            site_id=_SITE_ID,
        )

    assert captured.get("input_data", {}).get("site_id") == _SITE_ID


# ── T11: full_result EXACT 보존 ──────────────────────────────────────────────

def test_T11_full_result_exact_preserved():
    """persist_saas_full_result: full_result 가 변환 없이 그대로 저장됨."""
    captured: Dict[str, Any] = {}

    class _Cap:
        def table(self, _): return self
        def insert(self, row):
            captured.update(row)
            return _InsertRow()
        def execute(self):
            class _R: data = [{"id": _DIAG_ID}]
            return _R()

    fr = {"sector": "INDUSTRIAL", "obligations_raw": [{"atom_id": "x"}], "custom_field": "keep_me"}
    persist_saas_full_result(_Cap(), factory_id=_FAC_ID, company_id=_COMPANY_ID, full_result=fr)
    assert captured["full_result"] is fr  # 동일 객체 — 복사/변환 0


# ── T12: 마이그레이션 파일 존재 확인 ─────────────────────────────────────────

def test_T12_migration_file_exists():
    """inspection_materialization_status 컬럼 추가 마이그레이션 파일이 존재한다."""
    import pathlib
    migrations_dir = pathlib.Path(__file__).parent.parent / "supabase" / "migrations"
    files = sorted(migrations_dir.glob("*_wp01a_c10_materialization_status.sql"))
    assert files, "마이그레이션 파일 없음: *_wp01a_c10_materialization_status.sql"
    content = files[0].read_text()
    assert "inspection_materialization_status" in content
    assert "TEXT" in content.upper()
