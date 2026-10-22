"""WO-TAI-M004-AUTO-WEB-MAINLINE-INTEGRATION-001-CORR-001-FINAL
보정 날짜: 2026-10-22

기존 테스트 재사용 매핑 (코드 변경 없음):
  A01 AUTO Inspection HTML    ← test_auto_doc_security_integration::test_SI2
                                 test_auto_document_quality::T1-T6
  A02 AUTO Inspection PDF     ← test_auto_doc_security_integration::test_SI4
  A03 AUTO TBM HTML/PDF       ← test_auto_doc_security_integration::test_ST2 / test_ST4
                                 test_auto_document_quality::T7-T9
  A04 AUTO 미완료 업무 차단   ← test_auto_reuse_01_discovery::test_RR1-RR4
  A05 AUTO 타사업장 접근 차단 ← test_auto_doc_factory_isolation (13 tests)
                                 test_auto_doc_security_integration::test_SI1/SI3/ST1/ST3
  A06 AUTO 미승인 필드 자동입력 차단
      수준1(API계약)           ← NEW: test_A06_generate_document_no_auto_fetcher
      수준2(서비스 실행)       ← NEW: test_A06b_render_html_user_data_not_overwritten
  W01 WEB 편집기 열기
      RUNTIME_CREATION_PASS   ← test_m004_e2e_pipeline::test_E2E_02
      UI_NOT_VERIFIED          ← UI 실행 검증 없음. 서비스 계층 생성만 확인.
  W02 WEB 입력·수정           ← test_m004_e2e_pipeline::test_E2E_04
  W03 WEB 저장                ← test_m004_e2e_pipeline::test_E2E_02 / test_E2E_04
  W04 WEB 복원·재수정
      RESTORE_REDIT_PASS            ← NEW: test_W04_restore_and_re_edit
      FAKEDB_PERSISTENCE_RELOAD_PASS ← 재조회 + 2차 수정 검증 포함 (CORR-F1/F2)
  W05 WEB HTML 렌더링
      RENDER_PATH_UNIT_PASS    ← test_m004_e2e_pipeline::test_E2E_08
      실제 렌더러는 Mock 처리됨 (build_render_artifacts mocked).
      실제 HTML 렌더링 완료가 아님.
  W06 WEB PDF 생성
      API_CONTRACT_PASS        ← NEW: test_W06_generate_document_pdf
      PDF_RENDER_INTEGRATION_UNVERIFIED ← Gotenberg 외부 서비스 필요.
                                           로컬 환경에서 실제 변환 미검증.
  W07 WEB CANDIDATE 차단      ← test_m004_e2e_pipeline::test_E2E_10a
  W08 WEB 상태 전이           ← test_m004_e2e_pipeline::test_E2E_05a / 05b / 05c
  W09 WEB 봉인 문서 편집 차단 ← test_m004_e2e_pipeline::test_E2E_10d
  W10 WEB 잘못된 전이 차단    ← test_m004_e2e_pipeline::test_E2E_10c
  C01 REFERENCE_DOWNLOAD      ← test_document_catalog::T2 / T10
  C02 OFFICIAL_ORIGINAL       ← test_document_catalog::T3 / T4
  C03 WEB_EDIT                ← test_document_catalog::T1 / T9
  C04 SAAS_EXPORT             ← test_document_catalog::T9
  C05 SAAS_AUTO_FILL          ← test_document_catalog::T5
  C06 채널 필터               ← test_document_catalog::T11 / T12 / T13

CORR-F1: _MutableUpdateQ — _FakeSB._map 직접 변경으로 post-update get_document() 검증 가능.
CORR-F2: test_W04_restore_and_re_edit — field_false=False/field_zero=0 falsy 보존 +
         재조회(단계6) + 2차 부분 수정(단계7) 검증.

Production write = 0. Fake DB only.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── 공통 픽스처 ────────────────────────────────────────────────────────────────
SCHEMA_ID = "sc000001-0000-0000-0000-000000000001"
DOC_ID    = "doc00001-0000-0000-0000-000000000001"
USER_ID   = "user0001-0000-0000-0000-000000000001"
_FAKE_HTML = "<html><body>WEB 문서</body></html>"
_FAKE_PDF  = b"%PDF-1.4 fake"


# ── 로컬 FakeDB (test_m004_e2e_pipeline 패턴 재사용) ───────────────────────────

class _Q:
    def __init__(self, rows, single_mode=False):
        self._rows = list(rows) if isinstance(rows, list) else ([] if rows is None else [rows])
        self._filters: dict = {}
        self._single = single_mode

    def select(self, *a, **kw): return self
    def order(self, *a, **kw): return self
    def limit(self, n): return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def single(self):
        self._single = True
        return self

    def update(self, payload):
        return _UpdateQ(self._rows, self._filters, payload)

    def _filtered(self):
        return [
            r for r in self._rows
            if isinstance(r, dict) and all(
                (r.get(k) == v) if v is not None else (r.get(k) is None)
                for k, v in self._filters.items()
            )
        ]

    def execute(self):
        filtered = self._filtered()
        m = MagicMock()
        m.count = len(filtered)
        m.data = filtered[0] if self._single and filtered else (
            None if self._single else filtered
        )
        return m


class _UpdateQ:
    """Non-persisting UPDATE used by _Q.update() (legacy path, does not mutate _FakeSB._map)."""
    def __init__(self, rows, filters, payload):
        self._rows = rows
        self._filters = dict(filters)
        self._payload = payload

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def execute(self):
        updated = []
        for r in self._rows:
            if isinstance(r, dict) and all(r.get(k) == v for k, v in self._filters.items()):
                updated.append({**r, **self._payload})
        m = MagicMock()
        m.data = updated
        return m


class _MutableUpdateQ:
    """Persisting UPDATE used by _FakeSB._Tbl.update().

    Mutates _FakeSB._map[table_name] in place so that subsequent
    get_document() / select() calls see the updated row.
    Required for CORR-F2 post-update reload verification.
    """
    def __init__(self, map_ref: dict, table_name: str, filters: dict, payload: dict):
        self._map_ref = map_ref
        self._table_name = table_name
        self._filters = dict(filters)
        self._payload = payload

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def execute(self):
        updated = []
        rows = self._map_ref.get(self._table_name, [])
        for i, r in enumerate(rows):
            if isinstance(r, dict) and all(
                r.get(k) == v for k, v in self._filters.items()
            ):
                new_row = {**r, **self._payload}
                rows[i] = new_row  # mutate _map in place
                updated.append(new_row)
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
                return _MutableUpdateQ(sb._map, name, {}, payload)

        return _Tbl()

    def rpc(self, name, params=None):
        rows = self._map.get("_rpc_" + name, [])
        m = MagicMock()
        m.execute.return_value.data = rows[0] if rows else {}
        return m


def _make_doc(runtime_data_json=None):
    return {
        "id": DOC_ID, "form_schema_id": SCHEMA_ID,
        "status": "DRAFT", "version": 1,
        "company_id": "c1", "factory_id": "f1",
        "runtime_data_json": dict(runtime_data_json or {}),
        "evidence_links": [],
        "submitted_by": None, "submitted_at": None,
        "reviewed_by": None, "reviewed_at": None, "review_comment": None,
    }


def _make_schema():
    return {
        "id": SCHEMA_ID, "status": "APPROVED_FOR_RUNTIME_USE",
        "form_name": "테스트 서식", "version": 1,
        "catalog_document_id": None, "source_trace": {},
    }


def _make_fields(keys):
    return [
        {"id": f"fld-{k}", "form_schema_id": SCHEMA_ID, "field_key": k,
         "input_type": "text", "field_order": i}
        for i, k in enumerate(keys)
    ]


def _check_doc_scope_noop(_sb, _doc_id, _user):
    return {"id": _doc_id, "company_id": "c1", "factory_id": "f1", "status": "DRAFT"}


# ══════════════════════════════════════════════════════════════════════════════
# A06  AUTO 미승인 필드 자동입력 차단 — 수준 1 (API 계약)
#      generate_document() 가 InspectionFetcher / TbmFetcher 를 직접 호출하지 않음.
# ══════════════════════════════════════════════════════════════════════════════

def test_A06_generate_document_no_auto_fetcher():
    """WEB export_type=HTML: render_document_html 호출 O, InspectionFetcher/TbmFetcher 호출 X.

    수준: API 계약 (generate_document 라우터 수준 격리 검증).
    svc.render_document_html 은 Mock 처리됨.
    """
    from schemas.document_engine import GenerateDocumentIn
    from routers.document_engine_api import generate_document

    insp_called: list[bool] = []
    tbm_called: list[bool] = []

    async def _fake_insp(*a, **kw):
        insp_called.append(True)
        return {}

    async def _fake_tbm(*a, **kw):
        tbm_called.append(True)
        return {}

    with patch("routers.document_engine_api.get_supabase", return_value=MagicMock()):
        with patch("routers.document_engine_api._check_doc_scope",
                   side_effect=_check_doc_scope_noop):
            with patch("routers.document_engine_api.svc.render_document_html",
                       return_value=_FAKE_HTML):
                with patch(
                    "services.document_engine.fetchers.inspection_fetcher.InspectionFetcher.fetch",
                    new_callable=AsyncMock, side_effect=_fake_insp,
                ):
                    with patch(
                        "services.document_engine.fetchers.tbm_fetcher.TbmFetcher.fetch",
                        new_callable=AsyncMock, side_effect=_fake_tbm,
                    ):
                        body = GenerateDocumentIn(export_type="HTML")
                        resp = asyncio.run(
                            generate_document(DOC_ID, body, current_user={"id": USER_ID})
                        )

    assert not insp_called, \
        "generate_document must NOT call InspectionFetcher.fetch (auto fill 금지)"
    assert not tbm_called, \
        "generate_document must NOT call TbmFetcher.fetch (auto fill 금지)"
    assert _FAKE_HTML in resp.body.decode(), "render_document_html 결과가 응답에 포함돼야 함"


# ══════════════════════════════════════════════════════════════════════════════
# A06b AUTO 미승인 필드 자동입력 차단 — 수준 2 (서비스 실행)
#      실제 svc.render_document_html() 호출 + FakeDB 격리.
#      build_render_artifacts / resolve_signature_images_for_render 만 Mock.
# ══════════════════════════════════════════════════════════════════════════════

def test_A06b_render_html_user_data_not_overwritten_by_autofill():
    """실제 svc.render_document_html() 가 사용자 runtime_data_json 을 덮어쓰지 않음을 검증.

    수준: 서비스 실행 (FakeDB 격리, 외부 렌더러만 Mock).
    검증:
    - build_render_artifacts 에 전달된 document.runtime_data_json 이 사용자 입력값과 동일
    - InspectionFetcher.fetch / TbmFetcher.fetch 미호출
    - 사용자 입력값이 자동입력값으로 대체되지 않음

    svc.render_document_html docstring 명시: "Does NOT call InspectionFetcher or TbmFetcher."
    """
    import services.document_engine_svc as svc_mod

    USER_INPUT = {"inspection_result": "완료", "note": "이상 없음"}
    fields = _make_fields(["inspection_result", "note"])

    sb = _FakeSB({
        "runtime_document_data": [_make_doc(USER_INPUT)],
        "runtime_form_schema": [_make_schema()],
        "runtime_field": fields,
        "runtime_checklist_item": [],
        "runtime_evidence_field": [],
    })

    captured_doc: list[dict] = []

    def _capture_build(*a, document=None, **kw):
        captured_doc.append(document or {})
        return {"rendered_body": "<html>RENDERED</html>"}

    insp_called: list[bool] = []
    tbm_called: list[bool] = []

    async def _fake_insp(*a, **kw): insp_called.append(True); return {}
    async def _fake_tbm(*a, **kw): tbm_called.append(True); return {}

    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        with patch("services.document_schema_renderer.build_render_artifacts",
                   side_effect=_capture_build):
            with patch(
                "services.document_signature_svc.resolve_signature_images_for_render",
                return_value={"images": {}, "manifest": []},
            ):
                with patch(
                    "services.document_engine.fetchers.inspection_fetcher.InspectionFetcher.fetch",
                    new_callable=AsyncMock, side_effect=_fake_insp,
                ):
                    with patch(
                        "services.document_engine.fetchers.tbm_fetcher.TbmFetcher.fetch",
                        new_callable=AsyncMock, side_effect=_fake_tbm,
                    ):
                        html = svc_mod.render_document_html(DOC_ID)

    assert html == "<html>RENDERED</html>", "render_document_html 반환값 확인"

    assert len(captured_doc) == 1, "build_render_artifacts 정확히 1회 호출"
    passed_data = captured_doc[0].get("runtime_data_json")
    assert passed_data == USER_INPUT, (
        f"render_document_html 은 사용자 runtime_data_json 을 그대로 전달해야 함. "
        f"expected={USER_INPUT!r}, got={passed_data!r}"
    )

    assert not insp_called, \
        "InspectionFetcher.fetch 는 WEB render 경로에서 호출되면 안 됨"
    assert not tbm_called, \
        "TbmFetcher.fetch 는 WEB render 경로에서 호출되면 안 됨"


# ══════════════════════════════════════════════════════════════════════════════
# W04  WEB 복원·재수정
#      저장된 문서 재조회 → 기존값 보존 확인 → 일부 필드 수정 → merge 검증
#      CORR-F1: _MutableUpdateQ 로 FakeDB 내 실제 row 변경
#      CORR-F2: field_false=False / field_zero=0 falsy 보존 +
#               재조회(단계6, FAKEDB_PERSISTENCE_RELOAD_PASS) +
#               2차 부분 수정(단계7)
# ══════════════════════════════════════════════════════════════════════════════

def test_W04_restore_and_re_edit():
    """WEB 문서 복원·재수정 흐름 계약.  RESTORE_REDIT_PASS / FAKEDB_PERSISTENCE_RELOAD_PASS

    흐름:
    1. FakeDB 에 초기 runtime_data_json 을 가진 DRAFT 문서 존재
       (field_false=False, field_zero=0 falsy 값 포함)
    2. get_document() 로 재조회 → 초기값 확인 (단계 2-3)
    3. update_document() 로 field_a 만 수정 (단계 4)
    4. 반환된 문서: field_a = 수정값, field_b / field_false / field_zero 기존값 유지 (단계 5)
    5. 동일 FakeDB 재조회 → 수정 지속성 검증 (단계 6, FAKEDB_PERSISTENCE_RELOAD_PASS)
    6. 2차 부분 수정(field_b) → 1차 수정값(field_a) 유지 검증 (단계 7)

    기존 E2E-03 (idempotency) 과 구분:
      E2E-03 = 동일 점검 재요청 시 INSERT 방지.
      W04    = 저장된 문서 재조회 후 부분 수정 시 기존 필드 보존.
    """
    import services.document_engine_svc as svc_mod

    INITIAL = {
        "field_a": "초기값_A",
        "field_b": "초기값_B",
        "field_false": False,
        "field_zero": 0,
    }
    fields = _make_fields(["field_a", "field_b", "field_false", "field_zero"])

    sb = _FakeSB({
        "runtime_document_data": [_make_doc(INITIAL)],
        "runtime_form_schema": [_make_schema()],
        "runtime_field": fields,
        "runtime_checklist_item": [],
        "runtime_lifecycle_audit_log": [],
    })

    with patch("services.document_engine_svc.get_supabase", return_value=sb):
        # 단계 2-3: 재조회 — 저장된 초기값 보존 확인 (falsy 포함)
        restored = svc_mod.get_document(DOC_ID)
        assert restored is not None, "문서 재조회 실패"
        assert restored["runtime_data_json"]["field_a"] == "초기값_A"
        assert restored["runtime_data_json"]["field_b"] == "초기값_B"
        assert restored["runtime_data_json"]["field_false"] is False, \
            "재조회 후 falsy 값 False 보존"
        assert restored["runtime_data_json"]["field_zero"] == 0, \
            "재조회 후 falsy 값 0 보존"

        # 단계 4-5: 일부 필드(field_a) 수정, 나머지는 건드리지 않음
        result = svc_mod.update_document(
            DOC_ID,
            runtime_data_json={"field_a": "수정값_A"},
            updated_by=USER_ID,
        )
        assert result is not None, "update_document 반환값 없음"
        merged = result.get("runtime_data_json") or {}
        assert merged["field_a"] == "수정값_A", \
            "수정한 field_a 는 새 값으로 업데이트돼야 함"
        assert merged["field_b"] == "초기값_B", \
            "수정하지 않은 field_b 는 기존값을 유지해야 함 (PATCH merge semantics)"
        assert merged["field_false"] is False, \
            "PATCH merge: falsy False 보존"
        assert merged["field_zero"] == 0, \
            "PATCH merge: falsy 0 보존"

        # 단계 6: 동일 FakeDB 재조회 → 수정 지속성 검증 (FAKEDB_PERSISTENCE_RELOAD_PASS)
        reloaded = svc_mod.get_document(DOC_ID)
        assert reloaded is not None, "수정 후 재조회 실패"
        assert reloaded["runtime_data_json"]["field_a"] == "수정값_A", \
            "재조회 후 수정값 유지 (FAKEDB persistence)"
        assert reloaded["runtime_data_json"]["field_b"] == "초기값_B"
        assert reloaded["runtime_data_json"]["field_false"] is False
        assert reloaded["runtime_data_json"]["field_zero"] == 0

        # 단계 7: 2차 부분 수정 → 1차 수정값 유지
        result2 = svc_mod.update_document(
            DOC_ID,
            runtime_data_json={"field_b": "수정값_B"},
            updated_by=USER_ID,
        )
        assert result2 is not None, "2차 update_document 반환값 없음"
        merged2 = result2.get("runtime_data_json") or {}
        assert merged2["field_a"] == "수정값_A", \
            "2차 수정 후 field_a 1차 수정값 유지"
        assert merged2["field_b"] == "수정값_B", \
            "2차 field_b 수정값"
        assert merged2["field_false"] is False
        assert merged2["field_zero"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# W06  WEB PDF 생성 — 수준 1 (API 계약)
#      generate_document(export_type=PDF) → application/pdf + bytes 보존
#
# 수준 2 (실제 PDF 변환):
#   PDF_RENDER_INTEGRATION_UNVERIFIED
#   _html_to_pdf 는 외부 Gotenberg 서비스 의존.
#   로컬 테스트 환경에서 Gotenberg 미운영 → 실제 변환 경로 미검증.
#   Mock PDF 바이트 반환을 실제 PDF 생성 성공으로 해석하지 않음.
# ══════════════════════════════════════════════════════════════════════════════

def test_W06_generate_document_pdf():
    """export_type=PDF → Content-Type: application/pdf, PDF bytes 반환, DB 저장 없음.

    수준: API 계약 (_html_to_pdf Mock, application/pdf 응답 구조 검증).
    실제 PDF 변환: PDF_RENDER_INTEGRATION_UNVERIFIED (Gotenberg 필요).
    """
    from schemas.document_engine import GenerateDocumentIn
    from routers.document_engine_api import generate_document

    with patch("routers.document_engine_api.get_supabase", return_value=MagicMock()):
        with patch("routers.document_engine_api._check_doc_scope",
                   side_effect=_check_doc_scope_noop):
            with patch("routers.document_engine_api.svc.render_document_html",
                       return_value=_FAKE_HTML) as mock_render:
                with patch("routers.document_engine_api._html_to_pdf",
                           new_callable=AsyncMock, return_value=_FAKE_PDF) as mock_pdf:
                    body = GenerateDocumentIn(export_type="PDF")
                    resp = asyncio.run(
                        generate_document(DOC_ID, body, current_user={"id": USER_ID})
                    )

    assert resp.media_type == "application/pdf", (
        f"PDF export 시 Content-Type 은 application/pdf 여야 함, got {resp.media_type!r}"
    )
    assert resp.body == _FAKE_PDF, "PDF bytes 원본 보존 필요"
    mock_render.assert_called_once_with(DOC_ID)
    mock_pdf.assert_called_once_with(_FAKE_HTML)
