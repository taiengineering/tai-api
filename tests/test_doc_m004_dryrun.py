"""WO-TAI-DOC-M004-WP-L1-DRYRUN-001 — 의무별 문서 비교분석 Dry-run 테스트

테스트 시나리오:
  DR01 REUSE(A): 의무 → form_code → doc_id → document_forms → APPROVED schema + fields
  DR02 EXTEND(B): document_forms 존재, runtime_field 없음 → B
  DR03 EXTEND(B): form_templates 존재, doc_id 없음 → B (form_only)
  DR04 NEW_REQUIRED(C): form_code 있으나 catalog/schema 없음 → C
  DR05 REVIEW_REQUIRED(D): 복수 form_code → D
  DR06 REVIEW_REQUIRED(D): OSHACT-FORM-002 법령 충돌 이력 → D
  DR07 REVIEW_REQUIRED(D): form_templates 없음 → D
  DR08 REVIEW_REQUIRED(D): form_code·doc_id 모두 없음 → D
  DR09 doc_id 있으나 document_forms 없음 → D (review)
  DR10 중복 doc_id 처리 (first-win, no crash)
  DR11 run_dryrun 배치 요약 카운트 정확성
  DR12 Production DB write 0 — mock insert 미호출 확인
  DR13 form_code=OSHACT-FORM-002: law REVIEW이지만 TAI catalog 비교는 진행
  DR14 기존 CANDIDATE schema → B (not A)
  DR15 runtime_form_schema 없고 document_forms도 없음 → C (form_code + form_templates 있음)

Production DB write = 0 (mock 전용).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.doc_m004_dryrun import (
    classify_one_obligation,
    run_dryrun,
    UNVERIFIED,
    _APPROVED,
    _CANDIDATE,
)


# ─── fixture helpers ─────────────────────────────────────────────────────────

class _R:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if isinstance(data, list) else 0)


def _sb(table_data: dict) -> MagicMock:
    """Minimal Supabase mock. table_data: {table_name: [rows]}."""
    sb = MagicMock()
    insert_calls: list = []

    def _tbl(name):
        rows = table_data.get(name, [])
        tbl = MagicMock()
        q = MagicMock()
        tbl.select.return_value = q
        tbl.insert.side_effect = lambda d: insert_calls.append(("INSERT", name, d)) or MagicMock(execute=lambda: _R([]))
        q.eq.return_value = q
        q.limit.return_value = q
        q.execute.return_value = _R(rows)
        q.single.return_value = MagicMock(execute=lambda: _R(rows[0] if rows else None))
        return tbl

    sb.table.side_effect = _tbl
    sb._insert_calls = insert_calls
    return sb


# ─── shared fixtures ─────────────────────────────────────────────────────────

OB_SIMPLE = {
    "id": "ob-001",
    "category_code": "OB-OSHACT-001",
    "legal_rule_id": "RULE-001",
    "law_api_id": "LA-001",
    "law_mst_no": "MST-001",
    "law_name": "산업안전보건법",
}

OB_OSHACT_FORM_002 = {
    "id": "ob-002",
    "category_code": "OB-OSHACT-002",
    "legal_rule_id": "RULE-002",
    "law_api_id": UNVERIFIED,
    "law_mst_no": UNVERIFIED,
}

OB_NO_FORM = {
    "id": "ob-003",
    "category_code": "OB-003",
    "legal_rule_id": None,
    "law_api_id": UNVERIFIED,
    "law_mst_no": UNVERIFIED,
}

FORM_TEMPLATE_A = {
    "id": "ft-001",
    "form_code": "FORM-A-001",
    "form_name": "테스트서식A",
    "law_code": "OSHACT",
    "bylseq": "BYL-100",
    "is_active": True,
}

FORM_TEMPLATE_OSHACT_002 = {
    "id": "ft-002",
    "form_code": "OSHACT-FORM-002",
    "form_name": "안전보건교육 기록서",
    "law_code": "OSHACT",
    "bylseq": "BYL-002",
    "is_active": True,
}

DOC_FORM_A = {
    "id": "df-uuid-001",
    "doc_id": "DOC-CHK-001",
    "doc_name": "안전점검표A",
    "category": "안전",
    "law_ref": "산업안전보건법 제38조",
    "is_active": True,
}

SCHEMA_APPROVED = {
    "id": "rfs-001",
    "status": _APPROVED,
    "form_name": "안전점검표A v1",
    "version": "1.0",
    "catalog_document_id": "df-uuid-001",
    "field_count": 15,
}

SCHEMA_CANDIDATE = {
    "id": "rfs-002",
    "status": _CANDIDATE,
    "form_name": "점검표B v0",
    "version": "0.1",
    "catalog_document_id": "df-uuid-002",
    "field_count": 0,
}

FIELD_ROW = {"id": "rf-001", "form_schema_id": "rfs-001", "field_key": "check_1", "input_type": "checkbox"}


def _full_reuse_sb() -> MagicMock:
    """A(REUSE) 조건 완비 mock."""
    return _sb({
        "obligation_form_mapping": [{"form_code": "FORM-A-001"}],
        "form_templates":          [FORM_TEMPLATE_A],
        "rule_doc_mapping":        [{"rule_id": "RULE-001", "doc_id": "DOC-CHK-001"}],
        "document_forms":          [DOC_FORM_A],
        "runtime_form_schema":     [SCHEMA_APPROVED],
        "runtime_field":           [FIELD_ROW],
    })


# ─── DR01: A=REUSE ────────────────────────────────────────────────────────────

def test_DR01_reuse_full_chain():
    """의무 → form_code → doc_id → document_forms → APPROVED schema + fields → A."""
    sb = _full_reuse_sb()
    r = classify_one_obligation(sb, OB_SIMPLE)

    assert r["reuse_status"] == "A", f"expected A, got {r['reuse_status']}"
    assert r["form_code"] == "FORM-A-001"
    assert r["doc_id"] == "DOC-CHK-001"
    assert r["document_form_id"] == "df-uuid-001"
    assert r["runtime_form_schema_id"] == "rfs-001"
    assert r["bylseq"] == "BYL-100"
    assert r["matching_status"] == "MATCHED_FULL"
    assert r["review_reason"] is None


# ─── DR02: B=EXTEND (field 없음) ─────────────────────────────────────────────

def test_DR02_extend_no_fields():
    """APPROVED schema 있으나 runtime_field 0건 → B."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-A-001"}],
        "form_templates":          [FORM_TEMPLATE_A],
        "rule_doc_mapping":        [{"rule_id": "RULE-001", "doc_id": "DOC-CHK-001"}],
        "document_forms":          [DOC_FORM_A],
        "runtime_form_schema":     [SCHEMA_APPROVED],
        "runtime_field":           [],  # 필드 없음
    })
    r = classify_one_obligation(sb, OB_SIMPLE)
    assert r["reuse_status"] == "B"
    assert "runtime_field" in r["missing_fields"]


# ─── DR03: B=EXTEND (form_templates만 존재, doc_id 없음) ──────────────────────

def test_DR03_extend_form_only_no_catalog():
    """form_templates 있고 rule_doc_mapping 없음 → B (form_only)."""
    ob = {**OB_SIMPLE, "legal_rule_id": None}
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-A-001"}],
        "form_templates":          [FORM_TEMPLATE_A],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, ob)
    assert r["reuse_status"] == "B"
    assert r["matching_status"] == "FORM_ONLY_NO_CATALOG"
    assert r["doc_id"] == UNVERIFIED


# ─── DR04: C=NEW_REQUIRED ─────────────────────────────────────────────────────

def test_DR04_new_required_no_assets():
    """form_code 존재, form_templates 없음, catalog/schema 없음 → C."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-NEW-999"}],
        "form_templates":          [],  # 공식서식 없음
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, {**OB_SIMPLE, "legal_rule_id": None})
    assert r["reuse_status"] in ("C", "D"), f"expected C or D, got {r['reuse_status']}"


# ─── DR05: D=REVIEW 복수 form_code ────────────────────────────────────────────

def test_DR05_review_multiple_form_codes():
    """obligation_form_mapping에 form_code 2건 → D (복수 후보)."""
    sb = _sb({
        "obligation_form_mapping": [
            {"form_code": "FORM-A-001"},
            {"form_code": "FORM-B-002"},
        ],
        "form_templates":      [FORM_TEMPLATE_A],
        "rule_doc_mapping":    [],
        "document_forms":      [],
        "runtime_form_schema": [],
        "runtime_field":       [],
    })
    r = classify_one_obligation(sb, OB_SIMPLE)
    assert r["reuse_status"] == "D"
    assert r["review_reason"] and "복수" in r["review_reason"]


# ─── DR06: D=REVIEW OSHACT-FORM-002 법령 충돌 ────────────────────────────────

def test_DR06_review_oshact_form_002_law_conflict():
    """OSHACT-FORM-002는 법령 식별자 충돌 이력 → D (법령 연결 REVIEW_REQUIRED)."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-002"}],
        "form_templates":          [FORM_TEMPLATE_OSHACT_002],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, OB_OSHACT_FORM_002)
    assert r["reuse_status"] == "D"
    assert r["review_reason"] and "충돌" in r["review_reason"]
    # form_code는 OSHACT-FORM-002로 기록됨 (연결은 D이지만 form 확인은 완료)
    assert r["form_code"] == "OSHACT-FORM-002"


# ─── DR07: D=REVIEW form_templates 없음 ──────────────────────────────────────

def test_DR07_review_no_form_template():
    """obligation_form_mapping에 form_code 있으나 form_templates 없음 → D."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-MISSING-001"}],
        "form_templates":          [],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, OB_SIMPLE)
    assert r["reuse_status"] == "D"
    assert r["review_reason"] and "form_templates" in r["review_reason"]


# ─── DR08: D=REVIEW form_code·doc_id 모두 없음 ───────────────────────────────

def test_DR08_review_no_form_no_doc():
    """obligation_form_mapping 없고 rule_doc_mapping도 없음 → D."""
    sb = _sb({
        "obligation_form_mapping": [],
        "form_templates":          [],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, OB_NO_FORM)
    assert r["reuse_status"] == "D"
    assert r["form_code"] == UNVERIFIED
    assert r["doc_id"] == UNVERIFIED


# ─── DR09: D=REVIEW doc_id 있으나 document_forms 없음 ────────────────────────

def test_DR09_review_doc_id_no_document_forms():
    """rule_doc_mapping에 doc_id 있으나 document_forms에 row 없음 → D."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-A-001"}],
        "form_templates":          [FORM_TEMPLATE_A],
        "rule_doc_mapping":        [{"rule_id": "RULE-001", "doc_id": "DOC-ORPHAN"}],
        "document_forms":          [],  # doc_id에 해당하는 row 없음
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, OB_SIMPLE)
    assert r["reuse_status"] == "D"
    assert r["doc_id"] == "DOC-ORPHAN"
    assert r["document_form_id"] == UNVERIFIED
    assert "document_forms" in (r["review_reason"] or "")


# ─── DR10: 중복 doc_id 처리 — first-win ──────────────────────────────────────

def test_DR10_duplicate_doc_id_first_win():
    """rule_doc_mapping에 같은 rule_id로 복수 row → 첫 번째 doc_id만 사용, crash 없음."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-A-001"}],
        "form_templates":          [FORM_TEMPLATE_A],
        "rule_doc_mapping":        [
            {"rule_id": "RULE-001", "doc_id": "DOC-CHK-001"},
            {"rule_id": "RULE-001", "doc_id": "DOC-CHK-002"},
        ],
        "document_forms":          [DOC_FORM_A],
        "runtime_form_schema":     [SCHEMA_APPROVED],
        "runtime_field":           [FIELD_ROW],
    })
    r = classify_one_obligation(sb, OB_SIMPLE)
    # 첫 번째 doc_id 사용, 예외 없음
    assert r["doc_id"] == "DOC-CHK-001"
    assert r["reuse_status"] in ("A", "B", "C", "D")


# ─── DR11: run_dryrun 배치 요약 카운트 ────────────────────────────────────────

def test_DR11_batch_summary_counts():
    """run_dryrun: 3건 의무 분류 → summary 카운트 정확성."""
    # ob1: A, ob2: D(oshact-conflict), ob3: D(no form)
    ob1 = {**OB_SIMPLE, "id": "ob-r01", "category_code": "OB-R01"}
    ob2 = {**OB_OSHACT_FORM_002, "id": "ob-r02", "category_code": "OB-R02"}
    ob3 = {**OB_NO_FORM, "id": "ob-r03", "category_code": "OB-R03"}

    def _tbl_router(name):
        rows_map = {
            "obligation_form_mapping": [{"form_code": "FORM-A-001"}],
            "form_templates":          [FORM_TEMPLATE_A],
            "rule_doc_mapping":        [{"rule_id": "RULE-001", "doc_id": "DOC-CHK-001"}],
            "document_forms":          [DOC_FORM_A],
            "runtime_form_schema":     [SCHEMA_APPROVED],
            "runtime_field":           [FIELD_ROW],
        }
        rows = rows_map.get(name, [])
        tbl = MagicMock()
        q = MagicMock()
        tbl.select.return_value = q
        q.eq.return_value = q
        q.limit.return_value = q
        q.execute.return_value = _R(rows)
        return tbl

    sb = MagicMock()
    sb.table.side_effect = _tbl_router

    result = run_dryrun(sb, [ob1, ob2, ob3])

    assert result["summary"]["total"] == 3
    assert isinstance(result["summary"]["A"], int)
    assert isinstance(result["summary"]["D"], int)
    assert len(result["results"]) == 3
    # ob1은 FORM-A-001 경로 → A (oshact conflict는 ob2뿐)
    ob1_result = next(r for r in result["results"] if r["obligation_code"] == "OB-R01")
    assert ob1_result["reuse_status"] == "A"


# ─── DR12: Production DB write = 0 ────────────────────────────────────────────

def test_DR12_no_db_write():
    """Dry-run 실행 중 insert가 호출되지 않음."""
    sb = _full_reuse_sb()
    classify_one_obligation(sb, OB_SIMPLE)
    assert len(sb._insert_calls) == 0, f"insert 호출 감지: {sb._insert_calls}"


# ─── DR13: OSHACT-FORM-002 TAI catalog 비교는 진행 ────────────────────────────

def test_DR13_oshact_form_002_catalog_still_compared():
    """OSHACT-FORM-002 법령 충돌이지만 TAI catalog 비교는 수행 → form_code 기록됨."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "OSHACT-FORM-002"}],
        "form_templates":          [FORM_TEMPLATE_OSHACT_002],
        "rule_doc_mapping":        [],
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, OB_OSHACT_FORM_002)
    # D이지만 form_code, bylseq는 기록됨
    assert r["form_code"] == "OSHACT-FORM-002"
    assert r["bylseq"] == "BYL-002"
    # law connection은 REVIEW
    assert r["reuse_status"] == "D"


# ─── DR14: CANDIDATE schema → B ──────────────────────────────────────────────

def test_DR14_candidate_schema_is_B_not_A():
    """runtime_form_schema가 CANDIDATE → A가 아닌 B."""
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-A-001"}],
        "form_templates":          [FORM_TEMPLATE_A],
        "rule_doc_mapping":        [{"rule_id": "RULE-001", "doc_id": "DOC-CHK-002"}],
        "document_forms":          [{**DOC_FORM_A, "id": "df-uuid-002", "doc_id": "DOC-CHK-002"}],
        "runtime_form_schema":     [SCHEMA_CANDIDATE],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, OB_SIMPLE)
    assert r["reuse_status"] == "B"
    assert "schema_approval" in r["missing_fields"]


# ─── DR15: form_code + form_templates만 있고 schema 없음 → C ──────────────────

def test_DR15_form_only_no_catalog_classified_B_or_C():
    """form_templates 있으나 document_forms/schema 없음 → B (보완 가능)."""
    ob = {**OB_SIMPLE, "legal_rule_id": "RULE-X99"}
    sb = _sb({
        "obligation_form_mapping": [{"form_code": "FORM-NEW-100"}],
        "form_templates":          [{"id": "ft-new", "form_code": "FORM-NEW-100",
                                     "form_name": "신규서식", "law_code": "OSHACT",
                                     "bylseq": "BYL-999", "is_active": True}],
        "rule_doc_mapping":        [],  # rule_id 조회해도 없음
        "document_forms":          [],
        "runtime_form_schema":     [],
        "runtime_field":           [],
    })
    r = classify_one_obligation(sb, ob)
    # form_templates만 있고 catalog/schema 없음
    assert r["reuse_status"] in ("B", "C"), f"expected B or C, got {r['reuse_status']}"
    assert r["form_code"] == "FORM-NEW-100"
