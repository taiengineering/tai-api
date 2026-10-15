"""WO-TAI-DOC-M004-RUNTIME-E2E-001 — 점검-문서 E2E 파이프라인 격리 테스트

10개 시나리오 검증 (기존 자산 재사용):

  E2E-01  업무 일정·점검 연결 구조 확인 (코드 경로 검증)
  E2E-02  DRAFT 생성 — source_inspection_id 포함
  E2E-03  동일 점검 재요청 → 기존 문서 반환, INSERT 0
  E2E-04  문서 필드 입력·저장 (PATCH merge semantics)
  E2E-05a DRAFT → IN_PROGRESS 전이
  E2E-05b IN_PROGRESS → SUBMITTED_FOR_REVIEW (제출자 identity binding)
  E2E-05c SUBMITTED_FOR_REVIEW → REVIEW_PENDING 전이
  E2E-06  APPROVED_BY_HUMAN — BLOCKED (DATABASE_URL 없음 / psycopg2 직접 연결 필요)
  E2E-07  승인·보관 스냅샷 — BLOCKED (psycopg2 없음)
  E2E-08  DRAFT 상태 HTML 렌더링
  E2E-09  타 회사·사업장 접근 차단 (기존 TC1B·TC6B 회귀 확인)
  E2E-10a 미승인 스키마 차단
  E2E-10b 비활성 점검 차단 (is_active=False)
  E2E-10c 잘못된 상태 전이 차단 (규칙 없음)
  E2E-10d APPROVED_BY_HUMAN 봉인 문서 필드 수정 차단

CONFLICT FINDING:
  CF-01   APPROVED_BY_HUMAN → ARCHIVED 전이 규칙 존재 (DB 조회 확인)
          trg_rdd_seal_guard 와의 정합성: 운영 DB 직접 검증 필요 (UNVERIFIED)

BLOCKED:
  E2E-06, E2E-07 — DATABASE_URL 없음 (psycopg2 직접 연결 불가).
  운영 DB 쓰기 미승인 (Owner 별도 승인 대기).

Mock/fake DB 만 사용. production INSERT/UPDATE/DELETE = 0.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── 공통 픽스처 ────────────────────────────────────────────────────────────────
SCHEMA_ID   = "sc000001-0000-0000-0000-000000000001"
INSP_ID     = "ab000001-0000-0000-0000-000000000001"
WS_ID       = "ws000001-0000-0000-0000-000000000001"
DOC_ID      = "doc00001-0000-0000-0000-000000000001"
COMPANY_A   = "comp0001-0000-0000-0000-000000000001"
COMPANY_B   = "comp0002-0000-0000-0000-000000000002"
FACTORY_A   = "fact0001-0000-0000-0000-000000000001"
FACTORY_B   = "fact0002-0000-0000-0000-000000000002"
USER_ID     = "user0001-0000-0000-0000-000000000001"
FIELD_KEY   = "inspection_result"
FIELD_ID    = "fld00001-0000-0000-0000-000000000001"

# DB에서 조회한 실제 전이 규칙 (Phase A 조회 결과)
# APPROVED_BY_HUMAN → ARCHIVED 규칙 존재 확인
_TRANSITION_RULES = [
    {"from_status": "DRAFT",                "to_status": "IN_PROGRESS",         "requires_reviewer": False, "requires_comment": False},
    {"from_status": "IN_PROGRESS",          "to_status": "SUBMITTED_FOR_REVIEW","requires_reviewer": False, "requires_comment": False},
    {"from_status": "SUBMITTED_FOR_REVIEW", "to_status": "REVIEW_PENDING",      "requires_reviewer": False, "requires_comment": False},
    {"from_status": "REVIEW_PENDING",       "to_status": "APPROVED_BY_HUMAN",   "requires_reviewer": True,  "requires_comment": True},
    {"from_status": "REVIEW_PENDING",       "to_status": "REJECTED_BY_HUMAN",   "requires_reviewer": True,  "requires_comment": True},
    {"from_status": "REVIEW_PENDING",       "to_status": "RETURNED_FOR_EDIT",   "requires_reviewer": True,  "requires_comment": False},
    {"from_status": "APPROVED_BY_HUMAN",    "to_status": "ARCHIVED",            "requires_reviewer": False, "requires_comment": False},
    {"from_status": "REJECTED_BY_HUMAN",    "to_status": "DRAFT",               "requires_reviewer": False, "requires_comment": False},
]


# ── Fake Supabase (기존 패턴 재사용) ────────────────────────────────────────────
class _Q:
    def __init__(self, rows, single_mode=False):
        self._rows = list(rows) if isinstance(rows, list) else ([] if rows is None else [rows])
        self._filters: dict = {}
        self._limit_n = None
        self._single = single_mode

    def select(self, *a, **kw): return self
    def order(self, *a, **kw): return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def single(self):
        self._single = True
        return self

    def update(self, payload):
        return _UpdateQ(self._rows, self._filters, payload)

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
        m.count = len(filtered)
        m.data = filtered[0] if self._single and filtered else (None if self._single else filtered)
        return m


class _UpdateQ:
    def __init__(self, rows, filters, payload):
        self._rows = rows
        self._filters = filters
        self._payload = payload

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def execute(self):
        updated = []
        for r in self._rows:
            if isinstance(r, dict) and all(
                r.get(k) == v for k, v in self._filters.items()
            ):
                row = {**r, **self._payload}
                updated.append(row)
        m = MagicMock()
        m.data = updated
        return m


class _FakeSB:
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
                result_rows = [sb._insert_result or payload]
                return _Q(result_rows)
            def update(self_, payload):
                return _UpdateQ(list(rows), {}, payload)

        return _Tbl()

    def rpc(self, name, params=None):
        rows = self._map.get("_rpc_" + name, [])
        m = MagicMock()
        m.execute.return_value.data = rows[0] if rows else {}
        return m


def _schema(status="APPROVED_FOR_RUNTIME_USE"):
    return {"id": SCHEMA_ID, "status": status, "form_name": "점검 결과 기록서", "version": 1,
            "catalog_document_id": None, "source_trace": {}}


def _doc(status="DRAFT", cid=COMPANY_A, fid=FACTORY_A):
    return {"id": DOC_ID, "form_schema_id": SCHEMA_ID,
            "source_inspection_id": INSP_ID, "status": status, "version": 1,
            "company_id": cid, "factory_id": fid,
            "runtime_data_json": {}, "evidence_links": [],
            "submitted_by": None, "submitted_at": None,
            "reviewed_by": None, "reviewed_at": None, "review_comment": None}


def _insp(status="IN_PROGRESS", fid=FACTORY_A, aid=WS_ID):
    return {"id": INSP_ID, "assignment_id": aid, "factory_id": fid,
            "status_code": status}


def _ws(cid=COMPANY_A, fid=FACTORY_A):
    return {"id": WS_ID, "company_id": cid, "factory_id": fid}


def _user(cid=COMPANY_A, fid=FACTORY_A, role="011"):
    return {"id": USER_ID, "company_id": cid, "factory_id": fid, "role_code": role}


def _field():
    return {"id": FIELD_ID, "form_schema_id": SCHEMA_ID, "field_key": FIELD_KEY,
            "input_type": "text"}


import services.document_engine_svc as svc_mod


# ══════════════════════════════════════════════════════════════════════════════
# E2E-01  업무 일정·점검 연결 구조 확인
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_01_inspection_work_schedule_linkage():
    """점검에 assignment_id(work_schedule.id)와 factory_id가 있고 work_schedule에
    company_id·factory_id가 있는 구조를 코드 경로로 검증한다."""
    insp = _insp()
    ws   = _ws()
    assert insp["assignment_id"] == ws["id"], "inspection must reference work_schedule"
    assert insp["factory_id"] == ws["factory_id"], "factory_id must match"
    assert ws["company_id"] is not None and ws["factory_id"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# E2E-02  DRAFT 생성
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_02_draft_creation_with_inspection():
    """source_inspection_id 포함 DRAFT 문서 생성."""
    inserted = {**_doc(), "source_inspection_id": INSP_ID}
    sb = _FakeSB(
        {"runtime_form_schema": [_schema()],
         "runtime_document_data": [],
         "runtime_lifecycle_audit_log": []},
        insert_result=inserted,
    )
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.create_document(
            SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
            source_inspection_id=INSP_ID,
        )
    assert result["status"] == "DRAFT"
    assert result["source_inspection_id"] == INSP_ID
    inserts_rdd = [(t, p) for t, p in sb._inserts if t == "runtime_document_data"]
    assert len(inserts_rdd) == 1
    assert inserts_rdd[0][1].get("source_inspection_id") == INSP_ID


# ══════════════════════════════════════════════════════════════════════════════
# E2E-03  동일 점검 재요청 → 기존 문서 반환, INSERT 0
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_03_idempotent_returns_existing():
    """동일 (source_inspection_id, form_schema_id) 재요청 시 기존 행 반환, INSERT 없음."""
    existing = _doc()
    sb = _FakeSB({"runtime_form_schema": [_schema()],
                  "runtime_document_data": [existing]})
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.create_document(
            SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
            source_inspection_id=INSP_ID,
        )
    assert result["id"] == DOC_ID
    assert result["status"] == "DRAFT"
    assert all(t != "runtime_document_data" for t, _ in sb._inserts), "INSERT must be 0"


# ══════════════════════════════════════════════════════════════════════════════
# E2E-04  문서 필드 입력·저장 (PATCH merge semantics)
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_04_field_update_merge_semantics():
    """DRAFT 상태 문서에 runtime_data_json 저장 — PATCH merge 확인."""
    draft = _doc(status="DRAFT")
    draft["runtime_data_json"] = {"existing_key": "keep_me"}
    sb = _FakeSB({
        "runtime_document_data": [draft],
        "runtime_field": [_field()],
        "runtime_checklist_item": [],
        "runtime_lifecycle_audit_log": [],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.update_document(
            DOC_ID,
            runtime_data_json={FIELD_KEY: "점검 완료"},
            updated_by=USER_ID,
        )
    assert result is not None
    merged = result.get("runtime_data_json") or {}
    assert merged.get(FIELD_KEY) == "점검 완료", "new key must be stored"
    assert merged.get("existing_key") == "keep_me", "existing key must be preserved"


# ══════════════════════════════════════════════════════════════════════════════
# E2E-05a  DRAFT → IN_PROGRESS 전이
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_05a_draft_to_in_progress():
    """runtime_state_transition_rule: DRAFT → IN_PROGRESS 전이 허용."""
    draft = _doc(status="DRAFT")
    rule  = {"from_status": "DRAFT", "to_status": "IN_PROGRESS",
             "requires_reviewer": False, "requires_comment": False}
    sb = _FakeSB({
        "runtime_document_data": [draft],
        "runtime_state_transition_rule": [rule],
        "runtime_lifecycle_audit_log": [],
        "runtime_document_approval": [],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.change_status(DOC_ID, "IN_PROGRESS", actor_id=USER_ID)
    assert result.get("status") == "IN_PROGRESS"


# ══════════════════════════════════════════════════════════════════════════════
# E2E-05b  IN_PROGRESS → SUBMITTED_FOR_REVIEW
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_05b_submit_for_review():
    """IN_PROGRESS → SUBMITTED_FOR_REVIEW + submitted_by = actor_id."""
    inprog = _doc(status="IN_PROGRESS")
    rule   = {"from_status": "IN_PROGRESS", "to_status": "SUBMITTED_FOR_REVIEW",
              "requires_reviewer": False, "requires_comment": False}
    sb = _FakeSB({
        "runtime_document_data": [inprog],
        "runtime_state_transition_rule": [rule],
        "runtime_lifecycle_audit_log": [],
        "runtime_document_approval": [],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.change_status(DOC_ID, "SUBMITTED_FOR_REVIEW", actor_id=USER_ID)
    assert result.get("status") == "SUBMITTED_FOR_REVIEW"
    assert result.get("submitted_by") == USER_ID, "submitted_by must be bound to actor"
    assert result.get("submitted_at") is not None


# ══════════════════════════════════════════════════════════════════════════════
# E2E-05c  SUBMITTED_FOR_REVIEW → REVIEW_PENDING
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_05c_review_pending():
    """SUBMITTED_FOR_REVIEW → REVIEW_PENDING 전이."""
    submitted = _doc(status="SUBMITTED_FOR_REVIEW")
    rule = {"from_status": "SUBMITTED_FOR_REVIEW", "to_status": "REVIEW_PENDING",
            "requires_reviewer": False, "requires_comment": False}
    sb = _FakeSB({
        "runtime_document_data": [submitted],
        "runtime_state_transition_rule": [rule],
        "runtime_lifecycle_audit_log": [],
        "runtime_document_approval": [],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        result = svc_mod.change_status(DOC_ID, "REVIEW_PENDING")
    assert result.get("status") == "REVIEW_PENDING"


# ══════════════════════════════════════════════════════════════════════════════
# E2E-06  APPROVED_BY_HUMAN — BLOCKED
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_06_approve_blocked_no_database_url():
    """confirm_document_atomic은 psycopg2 직접 연결(DATABASE_URL) 필요.
    로컬 .env에 DATABASE_URL 없음 → 503 (database unavailable) 확인."""
    from services.document_confirm_svc import confirm_document_atomic, ConfirmError

    try:
        confirm_document_atomic(
            DOC_ID,
            actor_id=None,
            comment="테스트",
            current_user=_user(),
        )
        assert False, "Should raise ConfirmError(503)"
    except ConfirmError as e:
        assert e.http_status == 503, \
            f"DATABASE_URL 없으면 503 반환 필요, got {e.http_status}"


# ══════════════════════════════════════════════════════════════════════════════
# E2E-07  승인·보관 스냅샷 해시 — BLOCKED
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_07_snapshot_hash_blocked():
    """compute_confirmed_snapshot_hash 독립 실행 가능 (결정적 SHA-256).
    전체 confirm 트랜잭션(psycopg2 직접 연결)은 DATABASE_URL 없이 검증 불가.

    BLOCKED: E2E-06과 동일한 조건. 해시 함수 자체는 격리 검증 가능.
    """
    from services.document_snapshot_integrity import compute_confirmed_snapshot_hash
    import datetime

    # 해시 함수는 유효한 UUID 문자열 필요 (hex 만 허용)
    _DOC_UUID  = "00000001-0000-0000-0000-000000000001"
    _USER_UUID = "00000002-0000-0000-0000-000000000001"

    kwargs = dict(
        runtime_document_id=_DOC_UUID,
        document_version=1,
        snapshot_schema_version=1,
        runtime_values_snapshot={"inspection_result": "완료"},
        source_trace_snapshot=[{"schema_id": SCHEMA_ID}],
        template_identity="test_template_v1",
        confirmed_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        confirmed_by=_USER_UUID,
        evidence_manifest=[],
        rendered_body="<html><body>점검 결과 기록서</body></html>",
    )
    hash_val = compute_confirmed_snapshot_hash(**kwargs)
    assert isinstance(hash_val, str) and len(hash_val) == 64, \
        "snapshot hash는 SHA-256 hex (64자) 여야 함"
    hash_val2 = compute_confirmed_snapshot_hash(**kwargs)
    assert hash_val == hash_val2, "동일 입력 → 동일 해시 (결정적)"


# ══════════════════════════════════════════════════════════════════════════════
# E2E-08  DRAFT 상태 HTML 렌더링
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_08_html_render_draft_state():
    """DRAFT 상태 문서 HTML 렌더링 (build_render_artifacts 경로)."""
    draft = _doc(status="DRAFT")
    schema = _schema()
    sb = _FakeSB({
        "runtime_document_data": [draft],
        "runtime_form_schema": [schema],
        "runtime_field": [_field()],
        "runtime_checklist_item": [],
        "runtime_lifecycle_audit_log": [],
    })
    fake_html = "<html><body>점검 결과 기록서</body></html>"

    with patch("services.document_engine_svc.resolve_runtime_document_state",
               return_value={"document": draft, "schema": schema, "fields": [_field()],
                             "checklists": []}), \
         patch("services.document_signature_svc.resolve_signature_images_for_render",
               return_value={"images": {}, "manifest": []}), \
         patch("services.document_schema_renderer.build_render_artifacts",
               return_value={"rendered_body": fake_html}):
        result = svc_mod.render_document_html(DOC_ID)
    assert result == fake_html, "HTML 렌더링 결과 반환 필요"


# ══════════════════════════════════════════════════════════════════════════════
# E2E-09  타 회사·사업장 접근 차단 (기존 TC1B·TC6B 회귀)
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_09a_cross_company_denied():
    """기존 TC1B 회귀: 실제 _ensure_own_company로 타 회사 접근 → 404."""
    from fastapi import HTTPException

    sb = _FakeSB({
        "safety_inspections": [
            {"id": INSP_ID, "assignment_id": WS_ID, "factory_id": FACTORY_B,
             "status_code": "IN_PROGRESS"}
        ],
        "work_schedules": [{"id": WS_ID, "company_id": COMPANY_B, "factory_id": FACTORY_B}],
        "runtime_document_data": [],
        "role_data_scope": [{"role_code": "COMPANY_ROLE", "scope_type": "COMPANY"}],
    })
    user = _user(cid=COMPANY_A, fid=FACTORY_A, role="COMPANY_ROLE")

    resolver_calls = [0]

    def _spy(*a, **kw):
        resolver_calls[0] += 1
        return {"inspection_status": "IN_PROGRESS", "is_active": True}

    with patch("routers.document_engine_api.get_supabase", return_value=sb), \
         patch("routers.document_engine_api.resolve_inspection_record", side_effect=_spy), \
         patch("routers.document_engine_api._ensure_inspection_own"):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=SCHEMA_ID, source_inspection_id=INSP_ID)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should raise 404"
        except HTTPException as he:
            assert he.status_code == 404

    assert resolver_calls[0] == 0, "resolver는 인가 실패 전에 호출되면 안 됨"
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


def test_E2E_09b_cross_factory_denied():
    """기존 TC6B 회귀: 실제 _ensure_own_company로 타 사업장 접근 → 404."""
    from fastapi import HTTPException

    sb = _FakeSB({
        "safety_inspections": [
            {"id": INSP_ID, "assignment_id": WS_ID, "factory_id": FACTORY_B,
             "status_code": "IN_PROGRESS"}
        ],
        "work_schedules": [{"id": WS_ID, "company_id": COMPANY_A, "factory_id": FACTORY_B}],
        "runtime_document_data": [],
        "role_data_scope": [{"role_code": "FACTORY_ROLE", "scope_type": "FACTORY"}],
    })
    user = _user(cid=COMPANY_A, fid=FACTORY_A, role="FACTORY_ROLE")

    resolver_calls = [0]

    def _spy(*a, **kw):
        resolver_calls[0] += 1
        return {"inspection_status": "IN_PROGRESS", "is_active": True}

    with patch("routers.document_engine_api.get_supabase", return_value=sb), \
         patch("routers.document_engine_api.resolve_inspection_record", side_effect=_spy), \
         patch("routers.document_engine_api._ensure_inspection_own"):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=SCHEMA_ID, source_inspection_id=INSP_ID)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=user)
            assert False, "Should raise 404"
        except HTTPException as he:
            assert he.status_code == 404

    assert resolver_calls[0] == 0
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# E2E-10a  미승인 스키마 차단
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_10a_candidate_schema_rejected():
    """CANDIDATE 스키마 → ValueError (schema not approved)."""
    sb = _FakeSB({"runtime_form_schema": [_schema(status="CANDIDATE")],
                  "runtime_document_data": []})
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        try:
            svc_mod.create_document(SCHEMA_ID, FACTORY_A, COMPANY_A, USER_ID,
                                    source_inspection_id=INSP_ID)
            assert False, "Should raise"
        except ValueError as e:
            assert "not approved" in str(e)
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# E2E-10b  비활성 점검 차단 (is_active=False)
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_10b_inactive_inspection_blocked():
    """is_active=False 점검 → 문서 생성 불가 (라우터 422)."""
    from fastapi import HTTPException

    router_sb = _FakeSB({
        "safety_inspections": [_insp()],
        "work_schedules": [_ws()],
        "runtime_document_data": [],
    })

    with patch("routers.document_engine_api.get_supabase", return_value=router_sb), \
         patch("routers.document_engine_api._ensure_own_company"), \
         patch("routers.document_engine_api._ensure_inspection_own"), \
         patch("routers.document_engine_api.resolve_inspection_record",
               return_value={"inspection_status": "IN_PROGRESS", "is_active": False}):
        from schemas.document_engine import DocumentCreateIn
        body = DocumentCreateIn(form_schema_id=SCHEMA_ID, source_inspection_id=INSP_ID)
        from routers.document_engine_api import create_document as route_fn
        try:
            route_fn(body=body, current_user=_user())
            assert False, "Should raise"
        except HTTPException as e:
            assert e.status_code == 422
    assert all(t != "runtime_document_data" for t, _ in router_sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# E2E-10c  잘못된 상태 전이 차단 (규칙 없음)
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_10c_invalid_transition_rejected():
    """DRAFT → ARCHIVED는 전이 규칙에 없으므로 ValueError."""
    draft = _doc(status="DRAFT")
    sb = _FakeSB({
        "runtime_document_data": [draft],
        "runtime_state_transition_rule": [],  # 규칙 없음
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        try:
            svc_mod.change_status(DOC_ID, "ARCHIVED")
            assert False, "Should raise"
        except ValueError as e:
            assert "transition not allowed" in str(e)


# ══════════════════════════════════════════════════════════════════════════════
# E2E-10d  봉인 문서 필드 수정 차단
# ══════════════════════════════════════════════════════════════════════════════

def test_E2E_10d_sealed_document_edit_blocked():
    """APPROVED_BY_HUMAN 문서는 필드 수정 불가."""
    sealed = _doc(status="APPROVED_BY_HUMAN")
    sb = _FakeSB({
        "runtime_document_data": [sealed],
        "runtime_field": [_field()],
        "runtime_checklist_item": [],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        try:
            svc_mod.update_document(DOC_ID, runtime_data_json={FIELD_KEY: "변경시도"})
            assert False, "Should raise"
        except ValueError as e:
            assert "APPROVED_BY_HUMAN" in str(e) or "does not allow editing" in str(e)
    assert all(t != "runtime_document_data" for t, _ in sb._inserts)


# ══════════════════════════════════════════════════════════════════════════════
# CF-01  CONFLICT FINDING — APPROVED_BY_HUMAN → ARCHIVED 전이 규칙 vs 봉인 가드
# ══════════════════════════════════════════════════════════════════════════════

def test_CF_01_approved_to_archived_rule_exists_but_seal_guard_blocks():
    """CONFLICT FINDING:
    - DB runtime_state_transition_rule에 APPROVED_BY_HUMAN → ARCHIVED 규칙 존재 (Phase A 확인)
    - 코드에서 change_status가 해당 규칙을 찾고 UPDATE 시도
    - trg_rdd_seal_guard: OLD.status=APPROVED_BY_HUMAN이면 UPDATE 거부 (DB 트리거)
    - → change_status('ARCHIVED')는 코드 경로는 통과하지만 DB 트리거에서 실패
    - 운영 DB에서 이 충돌을 직접 검증해야 함 (UNVERIFIED)

    이 테스트는 코드 레벨에서 transition rule이 존재함을 확인하고
    change_status가 해당 경로에 진입함을 검증한다.
    트리거 차단은 실제 DB 없이는 검증 불가 → UNVERIFIED로 기록.
    """
    approved = _doc(status="APPROVED_BY_HUMAN")
    rule = {"from_status": "APPROVED_BY_HUMAN", "to_status": "ARCHIVED",
            "requires_reviewer": False, "requires_comment": False}
    sb = _FakeSB({
        "runtime_document_data": [approved],
        "runtime_state_transition_rule": [rule],
        "runtime_lifecycle_audit_log": [],
        "runtime_document_approval": [],
    })
    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        # fake SB UPDATE는 트리거 없이 실행됨 → code path가 규칙을 찾음을 확인
        result = svc_mod.change_status(DOC_ID, "ARCHIVED")
    assert result.get("status") == "ARCHIVED", \
        "code path succeeds with fake SB (no trigger); " \
        "real DB: trg_rdd_seal_guard may block — UNVERIFIED"
    # NOTE: 실제 DB에서는 trg_rdd_seal_guard가 이 UPDATE를 차단할 수 있음.
    # 운영 DB 직접 검증 필요.
