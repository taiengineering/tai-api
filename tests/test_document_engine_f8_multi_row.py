"""WO-DOC260-P1C-F8-BACKEND-COMPLETE-002 — WP-A 서버 검증 + WP-B HTML 렌더 테스트.

대상 필드: DOC-SERA-011 / submitted_document_list
  field_id : ad21a5f2-7452-401e-ba4f-59c1718ea83e
  field_key: submitted_document_list
  input_type: multi_row

WP-A: _validate_runtime_keys() 에서 F8 배열/행/컬럼/셀자료형 검증
WP-B: build_render_artifacts() 에서 F8 필드 → 4열 HTML 표 출력

순수 단위 테스트. DB/네트워크 없음.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

# ──────────────────────────────────────────────────────────────────────────────
# 공유 상수
# ──────────────────────────────────────────────────────────────────────────────

_F8_FIELD_ID = "ad21a5f2-7452-401e-ba4f-59c1718ea83e"
_F8_FIELD_KEY = "submitted_document_list"
SCHEMA_ID = "82be19be-ec01-46c7-a15c-fccf1a894dd8"


# ──────────────────────────────────────────────────────────────────────────────
# Supabase mock helper
# ──────────────────────────────────────────────────────────────────────────────

def _make_sb(field_rows, checklist_rows=None):
    """_validate_runtime_keys 에서 호출하는 두 테이블을 격리된 MagicMock으로 반환."""
    sb = MagicMock()
    tables: dict = {}

    def _tbl(name: str):
        if name not in tables:
            tables[name] = MagicMock()
        return tables[name]

    sb.table.side_effect = _tbl
    sb._tables = tables
    _tbl("runtime_field")
    _tbl("runtime_checklist_item")
    sb._tables["runtime_field"].select.return_value.eq.return_value.execute.return_value.data = field_rows
    sb._tables["runtime_checklist_item"].select.return_value.eq.return_value.execute.return_value.data = checklist_rows or []
    return sb


def _make_f8_field(fid=None):
    return {
        "id": fid or _F8_FIELD_ID,
        "field_key": _F8_FIELD_KEY,
        "input_type": "multi_row",
        "field_label": "제출 문서 목록",
        "field_order": 1,
        "form_schema_id": SCHEMA_ID,
        "required_status": "NOT_REQUIRED",
    }


# ──────────────────────────────────────────────────────────────────────────────
# WP-A: _validate_runtime_keys F8 검증
# ──────────────────────────────────────────────────────────────────────────────

class TestWpAValidation:
    def _validate(self, value, field_rows=None):
        from services.document_engine_svc import _validate_runtime_keys
        rows = field_rows if field_rows is not None else [_make_f8_field()]
        sb = _make_sb(rows)
        _validate_runtime_keys(sb, SCHEMA_ID, {_F8_FIELD_KEY: value})

    # ── 정상 케이스 ──────────────────────────────────────────────────────────

    def test_WpA_01_empty_array_accepted(self):
        """0행 [] — 정상 삭제 값으로 허용"""
        self._validate([])  # should not raise

    def test_WpA_02_one_row_accepted(self):
        """1행 저장 — 정상"""
        self._validate([{"document_name": "사용설명서", "submission_date": "2026-01-01",
                         "submitted_to": "발주처", "notes": "비고"}])

    def test_WpA_03_fifty_rows_accepted(self):
        """50행 — 경계 최대값 허용"""
        rows = [{"document_name": f"문서{i}", "submission_date": "", "submitted_to": "", "notes": ""}
                for i in range(50)]
        self._validate(rows)

    def test_WpA_04_partial_columns_accepted(self):
        """일부 컬럼만 있는 행 — 빈 값 허용 (선택 입력)"""
        self._validate([{"document_name": "계획서"}])

    def test_WpA_05_empty_row_dict_accepted(self):
        """빈 객체 {} — 컬럼이 없으면 검증할 내용 없으므로 허용"""
        self._validate([{}])

    # ── 거부 케이스 — 배열 형식 ──────────────────────────────────────────────

    def test_WpA_06_fifty_one_rows_rejected(self):
        """51행 → 거부"""
        rows = [{"document_name": f"d{i}"} for i in range(51)]
        with pytest.raises(ValueError, match="50"):
            self._validate(rows)

    def test_WpA_07_non_array_value_rejected(self):
        """배열 아닌 값 → 거부"""
        with pytest.raises(ValueError, match="JSON array"):
            self._validate("not a list")

    def test_WpA_08_dict_value_rejected(self):
        """dict → 거부"""
        with pytest.raises(ValueError, match="JSON array"):
            self._validate({"document_name": "x"})

    def test_WpA_09_null_value_rejected(self):
        """null → 거부 (빈 배열과 구분; null은 runtime_data_json 값으로는 유효하지 않다)"""
        with pytest.raises(ValueError, match="JSON array"):
            self._validate(None)

    # ── 거부 케이스 — 행 내용 ────────────────────────────────────────────────

    def test_WpA_10_non_dict_row_rejected(self):
        """행이 dict가 아님 → 거부"""
        with pytest.raises(ValueError, match="JSON object"):
            self._validate(["문자열행"])

    def test_WpA_11_disallowed_column_rejected(self):
        """허용되지 않은 컬럼 키 → 거부"""
        with pytest.raises(ValueError, match="disallowed"):
            self._validate([{"document_name": "x", "injected_col": "y"}])

    def test_WpA_12_number_cell_rejected(self):
        """셀 값이 숫자 → 거부"""
        with pytest.raises(ValueError, match="string"):
            self._validate([{"document_name": 42}])

    def test_WpA_13_bool_cell_rejected(self):
        """셀 값이 bool → 거부"""
        with pytest.raises(ValueError, match="string"):
            self._validate([{"document_name": True}])

    def test_WpA_14_list_cell_rejected(self):
        """셀 값이 배열 → 거부"""
        with pytest.raises(ValueError, match="string"):
            self._validate([{"document_name": ["a"]}])

    def test_WpA_15_object_cell_rejected(self):
        """셀 값이 객체 → 거부"""
        with pytest.raises(ValueError, match="string"):
            self._validate([{"document_name": {"k": "v"}}])

    # ── 보호 케이스 — 다른 multi_row 필드 pass-through 유지 ──────────────────

    def test_WpA_16_other_multi_row_field_not_validated(self):
        """F8 아닌 다른 multi_row 필드 ID → 엄격 검증 미적용, pass-through"""
        other_field = {
            "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "field_key": "other_list",
            "input_type": "multi_row",
            "field_label": "다른 반복 필드",
            "field_order": 1,
            "form_schema_id": SCHEMA_ID,
        }
        from services.document_engine_svc import _validate_runtime_keys
        sb = _make_sb([other_field])
        # 숫자 셀값이어도 F8 아닌 필드는 pass-through
        _validate_runtime_keys(sb, SCHEMA_ID, {"other_list": [{"any_col": 999}]})

    def test_WpA_17_existing_text_field_unaffected(self):
        """일반 text 필드는 multi_row 검증 영향 없음 (회귀 없음)"""
        text_field = {"id": "bbbbbbbb-0001-0001-0001-000000000001",
                      "field_key": "subject", "input_type": "text"}
        from services.document_engine_svc import _validate_runtime_keys
        sb = _make_sb([_make_f8_field(), text_field])
        _validate_runtime_keys(sb, SCHEMA_ID, {"subject": "내용"})


# ──────────────────────────────────────────────────────────────────────────────
# WP-B: build_render_artifacts F8 표 렌더
# ──────────────────────────────────────────────────────────────────────────────

from services.document_schema_renderer import build_render_artifacts

_RENDERER_SCHEMA_ID = "aaaaaaaa-f800-f800-f800-aaaaaaaaaaaa"
_DOC_ID = "dddddddd-f800-f800-f800-dddddddddddd"


def _schema(**over):
    s = {"id": _RENDERER_SCHEMA_ID, "form_name": "제출 서류 목록 서식"}
    s.update(over)
    return s


def _f8_field(**over):
    f = {
        "id": _F8_FIELD_ID,
        "form_schema_id": _RENDERER_SCHEMA_ID,
        "field_key": _F8_FIELD_KEY,
        "field_label": "제출 문서 목록",
        "input_type": "multi_row",
        "field_order": 1,
        "required_status": "NOT_REQUIRED",
    }
    f.update(over)
    return f


def _doc(data=None, **over):
    d = {
        "id": _DOC_ID,
        "form_schema_id": _RENDERER_SCHEMA_ID,
        "version": 1,
        "status": "DRAFT",
        "runtime_data_json": data if data is not None else {},
    }
    d.update(over)
    return d


def _build(data=None, **over):
    kwargs = dict(
        document=_doc(data),
        schema=_schema(),
        fields=[_f8_field()],
        checklists=[],
    )
    kwargs.update(over)
    return build_render_artifacts(**kwargs)


class TestWpBRenderer:

    # ── 표 구조 ──────────────────────────────────────────────────────────────

    def test_WpB_01_four_column_headers_rendered(self):
        """4열 헤더 (문서명/제출일/제출처/비고) 출력"""
        data = {_F8_FIELD_KEY: [{"document_name": "계획서", "submission_date": "2026-01-01",
                                  "submitted_to": "발주처", "notes": "비고"}]}
        body = _build(data)["rendered_body"]
        assert "문서명" in body
        assert "제출일" in body
        assert "제출처" in body
        assert "비고" in body

    def test_WpB_02_row_values_present(self):
        """저장된 값이 표에 출력됨"""
        rows = [{"document_name": "설계도면", "submission_date": "2026-03-15",
                 "submitted_to": "감리단", "notes": "원본"}]
        body = _build({_F8_FIELD_KEY: rows})["rendered_body"]
        assert "설계도면" in body
        assert "2026-03-15" in body
        assert "감리단" in body
        assert "원본" in body

    def test_WpB_03_row_order_preserved(self):
        """입력 행 순서 유지"""
        rows = [
            {"document_name": "첫번째문서", "submission_date": "", "submitted_to": "", "notes": ""},
            {"document_name": "두번째문서", "submission_date": "", "submitted_to": "", "notes": ""},
            {"document_name": "세번째문서", "submission_date": "", "submitted_to": "", "notes": ""},
        ]
        body = _build({_F8_FIELD_KEY: rows})["rendered_body"]
        assert body.index("첫번째문서") < body.index("두번째문서") < body.index("세번째문서")

    def test_WpB_04_html_escape_in_cells(self):
        """셀 값 HTML escape — XSS 방지"""
        rows = [{"document_name": '<script>alert(1)</script>', "submission_date": "",
                 "submitted_to": "", "notes": ""}]
        body = _build({_F8_FIELD_KEY: rows})["rendered_body"]
        assert "<script>" not in body
        assert "&lt;script&gt;" in body

    def test_WpB_05_zero_rows_shows_empty_marker(self):
        """0행 [] → (미등록) 출력, state=missing"""
        body = _build({_F8_FIELD_KEY: []})["rendered_body"]
        assert "(미등록)" in body
        assert 'data-state="missing"' in body
        assert "(미입력)" not in body

    def test_WpB_06_field_absent_shows_missing(self):
        """키 자체가 없으면 state=missing"""
        body = _build({})["rendered_body"]
        assert 'data-state="missing"' in body

    def test_WpB_07_deterministic_output(self):
        """같은 입력 → 완전 동일 출력 (결정성)"""
        rows = [{"document_name": "A", "submission_date": "2026-01-01",
                 "submitted_to": "B", "notes": "C"}]
        bodies = {_build({_F8_FIELD_KEY: rows})["rendered_body"] for _ in range(10)}
        assert len(bodies) == 1

    def test_WpB_08_state_present_for_non_empty_rows(self):
        """1행 이상이면 state=present"""
        rows = [{"document_name": "문서1"}]
        body = _build({_F8_FIELD_KEY: rows})["rendered_body"]
        assert 'data-state="present"' in body

    def test_WpB_09_field_key_in_data_attribute(self):
        """data-field-key 속성에 field_key 포함"""
        rows = [{"document_name": "문서1"}]
        body = _build({_F8_FIELD_KEY: rows})["rendered_body"]
        assert f'data-field-key="{_F8_FIELD_KEY}"' in body

    def test_WpB_10_input_type_in_data_attribute(self):
        """data-input-type 속성에 multi_row 포함"""
        body = _build({_F8_FIELD_KEY: []})["rendered_body"]
        assert 'data-input-type="multi_row"' in body

    # ── Archive 보호 ──────────────────────────────────────────────────────────

    def test_WpB_11_confirmed_archive_not_rerendered(self):
        """APPROVED_BY_HUMAN 문서는 이 함수가 아닌 archive 경로로 처리됨.
        build_render_artifacts 는 pure function — APPROVED_BY_HUMAN 상태도 render 가능.
        (실제 archive 반환은 render_document_html() 에서 처리 — 이 테스트는 순수함수만 검증)
        """
        rows = [{"document_name": "봉인문서"}]
        art = _build({_F8_FIELD_KEY: rows}, document=_doc({_F8_FIELD_KEY: rows},
                                                           status="APPROVED_BY_HUMAN"))
        assert "봉인문서" in art["rendered_body"]

    # ── 비F8 필드 회귀 없음 ───────────────────────────────────────────────────

    def test_WpB_12_non_f8_field_unaffected(self):
        """F8 아닌 필드(예: text)는 기존 방식으로 렌더됨 (회귀 없음)"""
        other_field = {
            "id": "bbbbbbbb-0002-0002-0002-bbbbbbbbbbbb",
            "form_schema_id": _RENDERER_SCHEMA_ID,
            "field_key": "subject",
            "field_label": "제목",
            "input_type": "text",
            "field_order": 2,
        }
        art = build_render_artifacts(
            document=_doc({"subject": "안전보고서", _F8_FIELD_KEY: [{"document_name": "도면"}]}),
            schema=_schema(),
            fields=[_f8_field(), other_field],
            checklists=[],
        )
        body = art["rendered_body"]
        assert "안전보고서" in body
        assert "도면" in body

    def test_WpB_13_non_f8_multi_row_field_falls_through_to_json(self):
        """F8 아닌 multi_row 필드는 기존 JSON 문자열 렌더링 유지 (pass-through)"""
        other_mr = {
            "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "form_schema_id": _RENDERER_SCHEMA_ID,
            "field_key": "other_list",
            "field_label": "기타 목록",
            "input_type": "multi_row",
            "field_order": 2,
        }
        art = build_render_artifacts(
            document=_doc({"other_list": [{"k": "v"}]}),
            schema=_schema(),
            fields=[other_mr],
            checklists=[],
        )
        body = art["rendered_body"]
        # JSON 문자열로 표시됨 — HTML escaped (F8 전용 표가 아님)
        assert "&quot;k&quot;" in body and "&quot;v&quot;" in body
        # F8 전용 컬럼 헤더 없음
        assert "<th>문서명</th>" not in body

    def test_WpB_14_pdf_path_uses_same_html(self):
        """PDF 경로는 render_document_html() → build_render_artifacts() 로 HTML 생성.
        build_render_artifacts 가 동일 HTML을 반환하면 PDF 경로도 동일 HTML 사용.
        (PDF 생성 자체는 이 테스트 범위 밖)
        """
        rows = [{"document_name": "준공도면"}]
        body1 = _build({_F8_FIELD_KEY: rows})["rendered_body"]
        body2 = _build({_F8_FIELD_KEY: rows})["rendered_body"]
        assert body1 == body2

    # ── RENDERER_VERSION 검증 ─────────────────────────────────────────────────

    def test_WpB_15_renderer_version_bumped(self):
        """RENDERER_VERSION = 2 (WP-B 변경 반영)"""
        from services import document_schema_renderer as r
        assert r.RENDERER_VERSION == "2"

    def test_WpB_16_template_identity_uses_new_version(self):
        """template_identity 는 schema-renderer:2:sha256:... 형식"""
        from services import document_schema_renderer as r
        tid = _build()["template_identity"]
        assert tid.startswith("schema-renderer:2:sha256:")
        digest = tid.rsplit(":", 1)[1]
        assert len(digest) == 64
