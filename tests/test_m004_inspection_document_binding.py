"""WO-TAI-DOC-M004-PR623-SOURCE-GATE-CORR-001 — 격리 테스트 (보정판)

기존 테스트 (수정):
  T01  APPROVED 스키마 + 정상 점검 → DRAFT 생성, source_inspection_id 반영
  T02  동일 (inspection, schema) 재호출 → 기존 행 반환, INSERT 0
  T03  동시 UNIQUE 충돌 시뮬레이션 → 서비스가 23505 전파
  T04  다른 회사 점검 → 404, 쓰기 0  [FIXED: outer except Exception 제거]
  T05a 존재하지 않는 점검 → 404, 쓰기 0
  T05b assignment_id 없는 점검(legacy) → 422, 쓰기 0
  T05c factory_id 불일치(복합키 실패) → 422, 쓰기 0
  T06  CANDIDATE 스키마 → 400, 쓰기 0
  T07  source_inspection_id 없음 → 기존 수동 생성 경로 PASS
  T08a IN_PROGRESS 점검 → 허용
  T08b COMPLETED 점검 → 허용
  T08c 불명 상태(PENDING) → 차단  [FIXED: auth 패치 추가, fallback 제거]
  T09  봉인된 APPROVED_BY_HUMAN 문서 재요청 → 조회 반환, INSERT 0
  T10  기존 create_document 서비스 회귀 — source_inspection_id=None 경로
  T11  법령/FORM647/자동생성/배포 경로 코드 미존재 확인
  T12  UUID 형식 오류 → 422

신규 테스트 (C1/C2/C3 보정 검증):
  TC1  타 테넌트 점검 접근 시 resolve_inspection_record 미호출 (상태 비노출)
  TC2  is_active=False → 문서 생성 차단
  TC3  canonical resolver 예외 → fallback 없이 fail-closed 422
  TC4  멱등 재조회: 저장 문서의 company/factory 불일치 → fail-closed
  TC5  UNIQUE 충돌 후 재조회: company/factory 불일치 → 409
  TC6  사업장(factory) 권한 검사 실패 → 404

Mock/fake DB만 사용. production INSERT/UPDATE/DELETE 0.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── constants ────────────────────────────────────────────────────────────────
APPROVED_SCHEMA_ID = "dc79ac3c-388c-42dc-b029-3dd9bda54a47"
INSP_ID_A = "aaaaaaaa-0001-0001-0001-000000000001"
INSP_ID_B = "bbbbbbbb-0002-0002-0002-000000000002"   # 다른 회사 점검
INSP_LEGACY = "cccccccc-0003-0003-0003-000000000003"  # assignment_id=None
WS_ID = "dddddddd-0004-0004-0004-000000000004"
COMPANY_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
COMPANY_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
FACTORY_A = "ffffffff-0001-0001-0001-000000000001"
FACTORY_B = "ffffffff-0002-0002-0002-000000000002"
DOC_ID = "eeeeeeee-0005-0005-0005-000000000005"
USER_ID = "11111111-1111-1111-1111-111111111111"


# ── fake supabase builder ─────────────────────────────────────────────────────
class _Q:
    """Chainable query mock. eq() conditions are applied as real row filters."""
    def __init__(self, rows, count=None):
        self._rows = list(rows) if isinstance(rows, list) else ([] if rows is None else [rows])
        self._count = count
        self._single = False
        self._filters: dict = {}
        self._limit_n: int | None = None

    def select(self, *a, **kw): return self
    def order(self, *a, **kw): return self
    def range(self, *a): return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def single(self):
        self._single = True
        return self

    def _filtered(self):
        result = [
            r for r in self._rows
            if isinstance(r, dict) and all(
                (r.get(k) == v) if v is not None else (r.get(k) is None)
                for k, v in self._filters.items()
            )
        ]
        if self._limit_n is not None:
            result = result[:self._limit_n]
        return result

    def execute(self):
        filtered = self._filtered()
        m = MagicMock()
        m.count = self._count if self._count is not None else len(filtered)
        if self._single:
            m.data = filtered[0] if filtered else None
        else:
            m.data = filtered
        return m


class _FakeSB:
    """Fake Supabase client. Records all insert calls. rpc() returns single dict."""
    def __init__(self, table_map: dict, insert_result=None):
        self._map = table_map
        self._inserts: list = []
        self._insert_result = insert_result

    def table(self, name: str):
        rows = self._map.get(name, [])
        sb = self

        class _Tbl:
            def select(self_, *a, **kw): return _Q(rows)
            def insert(self_, payload):
                sb._inserts.append((name, payload))
                result_rows = [sb._insert_result] if sb._insert_result else [payload]
                return _Q(result_rows)

        return _Tbl()

    def rpc(self, name, params=None):
        """rpc() returns a single-row result (dict), as the real Supabase client does."""
        rows = self._map.get("_rpc_" + name, [])
        result_data = rows[0] if rows else {}
        m = MagicMock()
        m.execute.return_value.data = result_data
        return m


def _insp(status="IN_PROGRESS", aid=WS_ID, fid=FACTORY_A):
    return {"id": INSP_ID_A, "assignment_id": aid, "factory_id": fid, "status_code": status}


def _ws(cid=COMPANY_A, fid=FACTORY_A):
    return {"id": WS_ID, "company_id": cid, "factory_id": fid}


def _schema(status="APPROVED_FOR_RUNTIME_USE"):
    return {"id": APPROVED_SCHEMA_ID, "status": status}


def _doc(approved=False, cid=COMPANY_A, fid=FACTORY_A):
    return {
        "id": DOC_ID, "form_schema_id": APPROVED_SCHEMA_ID,
        "source_inspection_id": INSP_ID_A,
        "company_id": cid, "factory_id": fid,
        "status": "APPROVED_BY_HUMAN" if approved else "DRAFT",
        "version": 1, "runtime_data_json": {}, "evidence_links": [],
    }


def _user(cid=COMPANY_A, fid=FACTORY_A, role="011"):
    return {"id": USER_ID, "company_id": cid, "factory_id": fid, "role_code": role}


# ── import service ────────────────────────────────────────────────────────────
import services.document_engine_svc as svc_mod


# ══════════════════════════════════════════════════════════════════════════════
# T01  APPROVED schema + valid inspection → DRAFT with source_inspection_id
# ══════════════════════════════════════════════════════════════════════════════

def test_T01_create_with_inspection_sets_source_inspection_id():
    inserted_doc = {
        "id": DOC_ID, "form_schema_id": APPROVED_SCHEMA_ID,
        "source_inspection_id": INSP_ID_A, "status": "DRAFT", "version": 1,
        "company_id": COMPANY_A, "factory_id": FACTORY_A,
        "runtime_data_json": {}, "evidence_links": [],
    }
    sb = _FakeSB(
        {
            "runtime_form_schema": [_schema()],
            "runtime_document_data": [],
            "runtime_lifecycle_audit_log": [],
        },
        insert_result=inserted_doc,
    )
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.create_document(
            APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
            source_inspection_id=INSP_ID_A,
        )
    assert result["source_inspection_id"] == INSP_ID_A
    assert result["status"] == "DRAFT"
    assert len(sb._inserts) == 2  # runtime_document_data + audit


# ══════════════════════════════════════════════════════════════════════════════
# T02  Same (inspection, schema) re-call → return existing, INSERT 0
# ══════════════════════════════════════════════════════════════════════════════

def test_T02_idempotent_returns_existing_no_insert():
    existing = _doc()  # company_id=COMPANY_A, factory_id=FACTORY_A
    sb = _FakeSB({
        "runtime_form_schema": [_schema()],
        "runtime_document_data": [existing],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.create_document(
            APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
            source_inspection_id=INSP_ID_A,
        )
    assert result["id"] == DOC_ID
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T03  DB UNIQUE violation → service propagates 23505 to router
# ══════════════════════════════════════════════════════════════════════════════

def test_T03_unique_violation_returns_existing():
    """Service raises 23505 exception; router is responsible for idempotent re-query."""
    def _raise_unique(*a, **kw):
        raise Exception("duplicate key value violates unique constraint "
                        "\"uq_rdd_source_inspection_form_schema\" (23505)")

    with patch("services.document_engine_svc.get_supabase") as mock_sb_fn:
        sb = _FakeSB({"runtime_form_schema": [_schema()], "runtime_document_data": []})
        original_table = sb.table
        call_count = [0]

        def table_side_effect(name):
            if name == "runtime_document_data":
                call_count[0] += 1
                if call_count[0] == 2:
                    tbl = MagicMock()
                    tbl.select.return_value = _Q([])
                    tbl.insert.side_effect = _raise_unique
                    return tbl
            return original_table(name)

        sb.table = table_side_effect
        mock_sb_fn.return_value = sb

        try:
            svc_mod.create_document(
                APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
                source_inspection_id=INSP_ID_A,
            )
            raised = False
        except Exception as e:
            raised = True
            assert "23505" in str(e) or "uq_rdd_source_inspection_form_schema" in str(e)

    assert raised, "Service should propagate DB UNIQUE exception to router"


# ══════════════════════════════════════════════════════════════════════════════
# T04  다른 회사 점검 → 404, 쓰기 0
# [FIXED] outer except Exception 제거 — HTTPException(404)만 허용
# ══════════════════════════════════════════════════════════════════════════════

def test_T04_cross_company_denied_no_write():
    """Router-level: _ensure_own_company raises for cross-company access → 404 only."""
    from fastapi import HTTPException

    sb = _FakeSB({
        "safety_inspections": [
            {"id": INSP_ID_B, "assignment_id": WS_ID, "factory_id": FACTORY_B,
             "status_code": "IN_PROGRESS"}
        ],
        "work_schedules": [{"id": WS_ID, "company_id": COMPANY_B, "factory_id": FACTORY_B}],
        "runtime_document_data": [],
    })
    user = _user(cid=COMPANY_A)

    with patch("routers.document_engine_api.get_supabase", return_value=sb), \
         patch("routers.document_engine_api._ensure_own_company",
               side_effect=HTTPException(404, "점검 레코드를 찾을 수 없습니다.")), \
         patch("routers.document_engine_api._ensure_inspection_own"):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(
            form_schema_id=APPROVED_SCHEMA_ID,
            source_inspection_id=INSP_ID_B,
        )
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should have raised HTTPException(404)"
        except HTTPException as he:
            assert he.status_code == 404

    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T05a 존재하지 않는 점검 → 404
# ══════════════════════════════════════════════════════════════════════════════

def test_T05a_nonexistent_inspection_404():
    from fastapi import HTTPException

    sb = _FakeSB({"safety_inspections": [], "runtime_document_data": []})
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=sb):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(
            form_schema_id=APPROVED_SCHEMA_ID,
            source_inspection_id=INSP_ID_A,
        )
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should have raised"
        except HTTPException as e:
            assert e.status_code == 404
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T05b assignment_id=None legacy 점검 → 422 (인가 전 데이터 유효성 실패)
# ══════════════════════════════════════════════════════════════════════════════

def test_T05b_legacy_no_assignment_id_422():
    from fastapi import HTTPException

    sb = _FakeSB({
        "safety_inspections": [
            {"id": INSP_LEGACY, "assignment_id": None, "factory_id": None,
             "status_code": "IN_PROGRESS"}
        ],
        "runtime_document_data": [],
    })
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=sb):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(
            form_schema_id=APPROVED_SCHEMA_ID,
            source_inspection_id=INSP_LEGACY,
        )
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should have raised"
        except HTTPException as e:
            assert e.status_code == 422
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T05c factory_id 불일치(복합키 실패) → 422
# ══════════════════════════════════════════════════════════════════════════════

def test_T05c_factory_mismatch_422():
    from fastapi import HTTPException

    sb = _FakeSB({
        "safety_inspections": [
            {"id": INSP_ID_A, "assignment_id": WS_ID, "factory_id": FACTORY_A,
             "status_code": "IN_PROGRESS"}
        ],
        "work_schedules": [],  # no matching (assignment_id, factory_id) composite
        "runtime_document_data": [],
    })
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=sb):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(
            form_schema_id=APPROVED_SCHEMA_ID,
            source_inspection_id=INSP_ID_A,
        )
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should have raised"
        except HTTPException as e:
            assert e.status_code == 422
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T06  CANDIDATE 스키마 → svc raises ValueError → 400
# ══════════════════════════════════════════════════════════════════════════════

def test_T06_candidate_schema_rejected():
    sb = _FakeSB({
        "runtime_form_schema": [{"id": APPROVED_SCHEMA_ID, "status": "CANDIDATE"}],
        "runtime_document_data": [],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        try:
            svc_mod.create_document(
                APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
                source_inspection_id=INSP_ID_A,
            )
            assert False, "Should raise"
        except ValueError as e:
            assert "not approved" in str(e)
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T07  source_inspection_id=None → 기존 수동 생성 회귀
# ══════════════════════════════════════════════════════════════════════════════

def test_T07_manual_create_regression_no_source_inspection_id():
    inserted_doc = {
        "id": DOC_ID, "form_schema_id": APPROVED_SCHEMA_ID,
        "source_inspection_id": None, "status": "DRAFT", "version": 1,
        "company_id": COMPANY_A, "factory_id": FACTORY_A,
        "runtime_data_json": {}, "evidence_links": [],
    }
    sb = _FakeSB(
        {"runtime_form_schema": [_schema()], "runtime_lifecycle_audit_log": []},
        insert_result=inserted_doc,
    )
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.create_document(
            APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
            source_inspection_id=None,
        )
    assert result["source_inspection_id"] is None
    assert result["status"] == "DRAFT"
    assert any(t == "runtime_document_data" for t, _ in sb._inserts)
    inserts_rdd = [(t, p) for t, p in sb._inserts if t == "runtime_document_data"]
    assert len(inserts_rdd) == 1
    assert "source_inspection_id" not in inserts_rdd[0][1]


# ══════════════════════════════════════════════════════════════════════════════
# T08a IN_PROGRESS 허용 / T08b COMPLETED 허용 / T08c PENDING 차단
# ══════════════════════════════════════════════════════════════════════════════

def _make_router_sb(status_code):
    return _FakeSB({
        "safety_inspections": [
            {"id": INSP_ID_A, "assignment_id": WS_ID, "factory_id": FACTORY_A,
             "status_code": status_code}
        ],
        "work_schedules": [_ws()],
        "runtime_document_data": [],
    })


def _make_svc_sb():
    return _FakeSB(
        {"runtime_form_schema": [_schema()], "runtime_document_data": [],
         "runtime_lifecycle_audit_log": []},
        insert_result={
            "id": DOC_ID, "form_schema_id": APPROVED_SCHEMA_ID,
            "source_inspection_id": INSP_ID_A, "status": "DRAFT",
            "version": 1, "company_id": COMPANY_A, "factory_id": FACTORY_A,
            "runtime_data_json": {}, "evidence_links": [],
        },
    )


def test_T08a_in_progress_allowed():
    router_sb = _make_router_sb("IN_PROGRESS")
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=router_sb), \
         patch("routers.document_engine_api._ensure_own_company"), \
         patch("routers.document_engine_api._ensure_inspection_own"), \
         patch("routers.document_engine_api.resolve_inspection_record",
               return_value={"inspection_status": "IN_PROGRESS", "is_active": True}), \
         patch("services.document_engine_svc.get_supabase", return_value=_make_svc_sb()):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_A)
        from routers.document_engine_api import create_document as route_fn
        result = route_fn(body=body, current_user=user)
    assert result["status"] == "success"


def test_T08b_completed_allowed():
    router_sb = _make_router_sb("COMPLETED")
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=router_sb), \
         patch("routers.document_engine_api._ensure_own_company"), \
         patch("routers.document_engine_api._ensure_inspection_own"), \
         patch("routers.document_engine_api.resolve_inspection_record",
               return_value={"inspection_status": "COMPLETED", "is_active": True}), \
         patch("services.document_engine_svc.get_supabase", return_value=_make_svc_sb()):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_A)
        from routers.document_engine_api import create_document as route_fn
        result = route_fn(body=body, current_user=user)
    assert result["status"] == "success"


def test_T08c_pending_blocked():
    """PENDING 상태 차단 — auth 패치 후 resolver에서 PENDING 반환 → 422.
    C2 fix: fallback 없음. resolver 직접 패치."""
    from fastapi import HTTPException

    router_sb = _make_router_sb("PENDING")
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=router_sb), \
         patch("routers.document_engine_api._ensure_own_company"), \
         patch("routers.document_engine_api._ensure_inspection_own"), \
         patch("routers.document_engine_api.resolve_inspection_record",
               return_value={"inspection_status": "PENDING", "is_active": True}):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_A)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should raise"
        except HTTPException as e:
            assert e.status_code == 422
    assert all(t != "runtime_document_data" for t, _ in router_sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T09  APPROVED_BY_HUMAN 문서 재요청 → 조회 반환, INSERT 0
# ══════════════════════════════════════════════════════════════════════════════

def test_T09_approved_sealed_document_returned_no_insert():
    sealed = _doc(approved=True)  # company_id=COMPANY_A, factory_id=FACTORY_A
    sb = _FakeSB({
        "runtime_form_schema": [_schema()],
        "runtime_document_data": [sealed],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.create_document(
            APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
            source_inspection_id=INSP_ID_A,
        )
    assert result["status"] == "APPROVED_BY_HUMAN"
    assert result["id"] == DOC_ID
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# T10  기존 svc.create_document 서비스 회귀 — source_inspection_id=None
# ══════════════════════════════════════════════════════════════════════════════

def test_T10_existing_service_contract_regression():
    inserted_doc = {
        "id": "rr-" + DOC_ID, "form_schema_id": APPROVED_SCHEMA_ID,
        "status": "DRAFT", "version": 1,
        "company_id": COMPANY_A, "factory_id": FACTORY_A,
        "runtime_data_json": {}, "evidence_links": [],
    }
    sb = _FakeSB(
        {"runtime_form_schema": [_schema()], "runtime_lifecycle_audit_log": []},
        insert_result=inserted_doc,
    )
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.create_document(
            APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
        )
    assert result["status"] == "DRAFT"
    inserts_rdd = [(t, p) for t, p in sb._inserts if t == "runtime_document_data"]
    assert len(inserts_rdd) == 1
    assert "source_inspection_id" not in inserts_rdd[0][1]


# ══════════════════════════════════════════════════════════════════════════════
# T11  법령/FORM647/자동생성/배포 경로 코드 미존재 확인
# ══════════════════════════════════════════════════════════════════════════════

def test_T11_no_leg_form647_autoassign_code():
    import re
    forbidden = [
        "FORM647", "law_master", "law_version", "law_article",
        "legal_obligation_atom", "auto_approve", "auto_fill",
        "inferred_default", "semantic_match", "fallback_mapping",
    ]
    files = [
        ROOT / "schemas/document_engine.py",
        ROOT / "services/document_engine_svc.py",
        ROOT / "routers/document_engine_api.py",
    ]
    violations = []
    for fp in files:
        content = fp.read_text()
        for pattern in forbidden:
            if pattern in content:
                violations.append(f"{fp.name}: {pattern}")
    real_violations = []
    for v in violations:
        fname, pat = v.split(": ", 1)
        fp = next(f for f in files if f.name == fname)
        lines = fp.read_text().splitlines()
        for line in lines:
            if pat in line and not line.strip().startswith("#"):
                real_violations.append(v)
                break
    assert real_violations == [], f"Forbidden patterns found: {real_violations}"


# ══════════════════════════════════════════════════════════════════════════════
# T12  UUID 형식 오류 → pydantic 422
# ══════════════════════════════════════════════════════════════════════════════

def test_T12_invalid_uuid_format_rejected():
    from pydantic import ValidationError
    try:
        from schemas.document_engine import DocumentCreateIn
        DocumentCreateIn(
            form_schema_id=APPROVED_SCHEMA_ID,
            source_inspection_id="not-a-uuid",
        )
        assert False, "Should raise ValidationError"
    except (ValidationError, Exception) as e:
        assert "uuid" in str(e).lower() or "value" in str(e).lower() or "invalid" in str(e).lower()


# ══════════════════════════════════════════════════════════════════════════════
# TC1  타 테넌트 점검 접근 시 resolve_inspection_record 미호출 (C1 검증)
# ══════════════════════════════════════════════════════════════════════════════

def test_TC1_cross_tenant_status_not_disclosed():
    """C1: resolver는 인가 성공 후에만 호출 — 타 테넌트 점검의 상태가 노출되지 않아야 함."""
    from fastapi import HTTPException

    sb = _FakeSB({
        "safety_inspections": [
            {"id": INSP_ID_B, "assignment_id": WS_ID, "factory_id": FACTORY_B,
             "status_code": "IN_PROGRESS"}
        ],
        "work_schedules": [{"id": WS_ID, "company_id": COMPANY_B, "factory_id": FACTORY_B}],
        "runtime_document_data": [],
    })
    user = _user(cid=COMPANY_A)

    resolver_call_count = [0]

    def _spy_resolver(*a, **kw):
        resolver_call_count[0] += 1
        return {"inspection_status": "IN_PROGRESS", "is_active": True}

    with patch("routers.document_engine_api.get_supabase", return_value=sb), \
         patch("routers.document_engine_api.resolve_inspection_record",
               side_effect=_spy_resolver), \
         patch("routers.document_engine_api._ensure_own_company",
               side_effect=HTTPException(404, "점검 레코드를 찾을 수 없습니다.")), \
         patch("routers.document_engine_api._ensure_inspection_own"):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_B)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should have raised HTTPException(404)"
        except HTTPException as he:
            assert he.status_code == 404

    # resolve_inspection_record는 인가 실패 전에 호출되지 않아야 함
    assert resolver_call_count[0] == 0, \
        "resolve_inspection_record must NOT be called before auth fails (status non-disclosure)"
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# TC2  is_active=False → 문서 생성 차단 (C2 검증)
# ══════════════════════════════════════════════════════════════════════════════

def test_TC2_inactive_inspection_blocked():
    """C2: is_active=False인 점검(IN_PROGRESS라도)은 문서 연결 불가."""
    from fastapi import HTTPException

    router_sb = _make_router_sb("IN_PROGRESS")
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=router_sb), \
         patch("routers.document_engine_api._ensure_own_company"), \
         patch("routers.document_engine_api._ensure_inspection_own"), \
         patch("routers.document_engine_api.resolve_inspection_record",
               return_value={"inspection_status": "IN_PROGRESS", "is_active": False}):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_A)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should raise"
        except HTTPException as e:
            assert e.status_code == 422
    assert all(t != "runtime_document_data" for t, _ in router_sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# TC3  canonical resolver 예외 → fallback 없이 fail-closed 422 (C2 검증)
# ══════════════════════════════════════════════════════════════════════════════

def test_TC3_resolver_exception_fail_closed():
    """C2: resolver가 예외를 던지면 raw status_code fallback 없이 422 반환."""
    from fastapi import HTTPException

    router_sb = _make_router_sb("IN_PROGRESS")
    user = _user()

    with patch("routers.document_engine_api.get_supabase", return_value=router_sb), \
         patch("routers.document_engine_api._ensure_own_company"), \
         patch("routers.document_engine_api._ensure_inspection_own"), \
         patch("routers.document_engine_api.resolve_inspection_record",
               side_effect=Exception("DB RPC timeout")):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_A)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should raise"
        except HTTPException as e:
            # Must fail-closed with 422, NOT 200 (fallback to status_code was removed)
            assert e.status_code == 422, \
                f"Expected 422 fail-closed, got {e.status_code}"
    assert all(t != "runtime_document_data" for t, _ in router_sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# TC4  멱등 재조회: 저장 문서의 company/factory 불일치 → fail-closed (C3 서비스)
# ══════════════════════════════════════════════════════════════════════════════

def test_TC4_idempotent_scope_mismatch_rejected():
    """C3 service: 기존 문서의 company/factory가 서버 확정 정본과 다르면 ValueError."""
    # 저장된 문서의 company_id가 COMPANY_B (요청 정본 COMPANY_A와 불일치)
    wrong_doc = _doc(cid=COMPANY_B, fid=FACTORY_B)
    sb = _FakeSB({
        "runtime_form_schema": [_schema()],
        "runtime_document_data": [wrong_doc],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        try:
            svc_mod.create_document(
                APPROVED_SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
                source_inspection_id=INSP_ID_A,
            )
            assert False, "Should raise ValueError for scope mismatch"
        except ValueError as e:
            assert "mismatch" in str(e) or "scope" in str(e)
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# TC5  UNIQUE 충돌 후 재조회: company/factory 불일치 → 409 (C3 라우터)
# ══════════════════════════════════════════════════════════════════════════════

def test_TC5_unique_collision_wrong_tenant_returns_409():
    """C3 router: UNIQUE 충돌 후 재조회한 문서의 company/factory가 다르면 409."""
    from fastapi import HTTPException

    user = _user()
    wrong_doc = _doc(cid=COMPANY_B, fid=FACTORY_B)
    router_sb = _make_router_sb("IN_PROGRESS")
    # 재조회용 runtime_document_data에 wrong_doc 추가
    router_sb._map["runtime_document_data"] = [wrong_doc]

    def _raise_unique(*a, **kw):
        raise Exception("uq_rdd_source_inspection_form_schema (23505)")

    with patch("routers.document_engine_api.get_supabase", return_value=router_sb), \
         patch("routers.document_engine_api._ensure_own_company"), \
         patch("routers.document_engine_api._ensure_inspection_own"), \
         patch("routers.document_engine_api.resolve_inspection_record",
               return_value={"inspection_status": "IN_PROGRESS", "is_active": True}), \
         patch("services.document_engine_svc.get_supabase") as mock_svc_sb:
        # 서비스 SB: schema 통과 후 INSERT 시 unique violation
        svc_sb = _FakeSB({"runtime_form_schema": [_schema()], "runtime_document_data": []})
        original_table = svc_sb.table
        call_count = [0]

        def svc_table_side_effect(name):
            if name == "runtime_document_data":
                call_count[0] += 1
                if call_count[0] == 2:
                    tbl = MagicMock()
                    tbl.select.return_value = _Q([])
                    tbl.insert.side_effect = _raise_unique
                    return tbl
            return original_table(name)

        svc_sb.table = svc_table_side_effect
        mock_svc_sb.return_value = svc_sb

        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_A)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should raise HTTPException"
        except HTTPException as e:
            # company/factory 불일치 → 409 (타 테넌트 문서 반환 차단)
            assert e.status_code == 409, \
                f"Expected 409 for wrong-tenant collision, got {e.status_code}"


# ══════════════════════════════════════════════════════════════════════════════
# TC6  사업장(factory) 권한 검사 실패 → 404 (auth before status — C1 검증)
# ══════════════════════════════════════════════════════════════════════════════

def test_TC6_cross_factory_denied_404():
    """C1: 다른 사업장 접근 시 인가 실패 → 404, 상태 미노출."""
    from fastapi import HTTPException

    # FACTORY_B 소속 점검; FACTORY_A 사용자
    sb = _FakeSB({
        "safety_inspections": [
            {"id": INSP_ID_A, "assignment_id": WS_ID, "factory_id": FACTORY_B,
             "status_code": "IN_PROGRESS"}
        ],
        "work_schedules": [{"id": WS_ID, "company_id": COMPANY_A, "factory_id": FACTORY_B}],
        "runtime_document_data": [],
    })
    user = _user(cid=COMPANY_A, fid=FACTORY_A)

    resolver_call_count = [0]

    def _spy_resolver(*a, **kw):
        resolver_call_count[0] += 1
        return {"inspection_status": "IN_PROGRESS", "is_active": True}

    with patch("routers.document_engine_api.get_supabase", return_value=sb), \
         patch("routers.document_engine_api.resolve_inspection_record",
               side_effect=_spy_resolver), \
         patch("routers.document_engine_api._ensure_own_company",
               side_effect=HTTPException(404, "점검 레코드를 찾을 수 없습니다.")), \
         patch("routers.document_engine_api._ensure_inspection_own"):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=APPROVED_SCHEMA_ID,
                                source_inspection_id=INSP_ID_A)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should have raised HTTPException(404)"
        except HTTPException as he:
            assert he.status_code == 404

    assert resolver_call_count[0] == 0, \
        "resolver must not be called before factory auth fails"
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)
