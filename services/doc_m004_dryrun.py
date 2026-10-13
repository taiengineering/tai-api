"""doc_m004_dryrun.py — WP-L1 Dry-run: Obligation ↔ Document Asset Comparison

MASTERPLAN-004 본선 WP-L1: 기존 TAI 문서 DB와 법령 의무를 READ-ONLY로 비교하여
재사용/보완/신규/검토 여부를 판정한다.

- Production DB write = 0 (READ-ONLY)
- 신규 테이블 생성 없음
- 식별자 구분: law_api_id / law_mst_no / bylseq / form_code / doc_id / document_forms.id
  각각 별도 식별자로 유지 — 이름 유사로 JOIN 금지

재사용 상태 분류:
  A = REUSE          — 기존 runtime_form_schema(APPROVED) + field 존재
  B = EXTEND         — 기존 document_forms 존재하나 schema/field 보완 필요
  C = NEW_REQUIRED   — 법령 의무 확인, 기존 자산 없음
  D = REVIEW_REQUIRED — 식별자 충돌/불명확/복수 후보/법령 버전 미확인
"""
from __future__ import annotations

from typing import Any, Optional

# 확인되지 않은 값 마커
UNVERIFIED = "UNVERIFIED"

# APPROVED_FOR_RUNTIME_USE 상태값
_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_CANDIDATE = "CANDIDATE"

# 알려진 법령 식별자 충돌 form_code 목록 (REVIEW_REQUIRED 강제)
_KNOWN_LAW_CONFLICTS: frozenset[str] = frozenset({"OSHACT-FORM-002"})


# ── 분류 결과 행 타입 ────────────────────────────────────────────────────────

def _empty_result(obligation_code: str) -> dict:
    """필수 컬럼이 전부 포함된 빈 결과 행."""
    return {
        "obligation_code":         obligation_code,
        "rule_id":                 UNVERIFIED,
        "law_api_id":              UNVERIFIED,
        "law_mst_no":              UNVERIFIED,
        "source_namespace":        UNVERIFIED,
        "bylseq":                  UNVERIFIED,
        "form_code":               UNVERIFIED,
        "doc_id":                  UNVERIFIED,
        "document_form_id":        UNVERIFIED,
        "runtime_form_schema_id":  UNVERIFIED,
        "matching_status":         "NO_MATCH",
        "reuse_status":            "D",
        "missing_fields":          [],
        "recommended_action":      UNVERIFIED,
        "evidence_reference":      UNVERIFIED,
        "review_reason":           None,
    }


# ── Step helpers ─────────────────────────────────────────────────────────────

def _step1_form_codes(sb, obligation_id: str) -> list[str]:
    """obligation_form_mapping에서 form_code 목록 조회.
    obligation_id는 legal_obligations.id.
    """
    res = sb.table("obligation_form_mapping").select("form_code").eq(
        "obligation_id", obligation_id
    ).execute()
    return [r["form_code"] for r in (res.data or []) if r.get("form_code")]


def _step2_form_template(sb, form_code: str) -> Optional[dict]:
    """form_templates에서 form_code로 조회 (bylseq, law_code 등)."""
    res = sb.table("form_templates").select(
        "id, form_code, form_no, form_name, law_code, bylseq, is_active"
    ).eq("form_code", form_code).limit(1).execute()
    return res.data[0] if res.data else None


def _step3_rule_doc(sb, rule_id: str) -> Optional[str]:
    """rule_doc_mapping에서 rule_id로 doc_id 조회.
    이름이 비슷하다는 이유만으로 JOIN하지 않음 — 실제 row 존재 여부로 판단.
    """
    if not rule_id:
        return None
    res = sb.table("rule_doc_mapping").select("doc_id").eq(
        "rule_id", rule_id
    ).limit(1).execute()
    return res.data[0]["doc_id"] if res.data else None


def _step4_document_form(sb, doc_id: str) -> Optional[dict]:
    """document_forms에서 doc_id로 조회."""
    res = sb.table("document_forms").select(
        "id, doc_id, doc_name, category, law_ref, is_active"
    ).eq("doc_id", doc_id).limit(1).execute()
    return res.data[0] if res.data else None


def _step5_runtime_schema(sb, catalog_document_id: str) -> Optional[dict]:
    """runtime_form_schema에서 catalog_document_id로 APPROVED 스키마 조회."""
    res = sb.table("runtime_form_schema").select(
        "id, status, form_name, version, catalog_document_id, field_count"
    ).eq("catalog_document_id", catalog_document_id).execute()
    rows = res.data or []
    approved = [r for r in rows if r.get("status") == _APPROVED]
    if approved:
        return approved[0]
    candidates = [r for r in rows if r.get("status") == _CANDIDATE]
    return candidates[0] if candidates else None


def _step6_field_count(sb, form_schema_id: str) -> int:
    """runtime_field에서 form_schema_id로 필드 수 조회."""
    res = sb.table("runtime_field").select(
        "id", count="exact"
    ).eq("form_schema_id", form_schema_id).execute()
    return res.count or 0


# ── 단일 의무 분류 ────────────────────────────────────────────────────────────

def classify_one_obligation(sb, ob: dict) -> dict:
    """단일 legal_obligations 행을 READ-ONLY로 분류.

    ob 필드:
      id              — legal_obligations.id (UUID)
      category_code   — obligation 식별 코드 (없으면 id 사용)
      legal_rule_id   — rule_doc_mapping.rule_id 조회에 사용 (확인된 경우)
      law_name        — 참고 법령명 (식별자 아님)
      law_api_id      — 법제처 API ID (있는 경우)
      law_mst_no      — 법령 일련번호 (있는 경우)

    반환: WO 요구 컬럼 전체 포함 결과 dict
    """
    obligation_id   = ob.get("id") or ""
    obligation_code = ob.get("category_code") or ob.get("obligation_code") or obligation_id
    law_api_id      = ob.get("law_api_id") or UNVERIFIED
    law_mst_no      = ob.get("law_mst_no") or UNVERIFIED
    rule_id_raw     = ob.get("legal_rule_id") or ob.get("rule_id")

    row = _empty_result(obligation_code)
    row["rule_id"]    = rule_id_raw or UNVERIFIED
    row["law_api_id"] = law_api_id
    row["law_mst_no"] = law_mst_no

    review_reasons: list[str] = []

    # Step 1 — form_code via obligation_form_mapping
    form_codes: list[str] = []
    if obligation_id:
        form_codes = _step1_form_codes(sb, obligation_id)

    # 복수 form_code → REVIEW_REQUIRED
    if len(form_codes) > 1:
        review_reasons.append(f"복수 form_code: {form_codes}")

    # form_code 결정
    form_code: Optional[str] = form_codes[0] if form_codes else None
    row["form_code"] = form_code or UNVERIFIED

    # Step 2 — form_templates
    ft: Optional[dict] = None
    if form_code:
        ft = _step2_form_template(sb, form_code)
        if ft:
            row["bylseq"]           = ft.get("bylseq") or UNVERIFIED
            row["source_namespace"] = ft.get("law_code") or UNVERIFIED
        else:
            review_reasons.append(f"form_templates 없음: {form_code}")

    # 알려진 법령 충돌 form_code → REVIEW_REQUIRED (법령 연결만)
    if form_code and form_code in _KNOWN_LAW_CONFLICTS:
        review_reasons.append(f"법령 식별자 충돌 이력: {form_code}")

    # Step 3 — rule_doc_mapping → doc_id
    doc_id: Optional[str] = None
    if rule_id_raw:
        doc_id = _step3_rule_doc(sb, rule_id_raw)
    row["doc_id"] = doc_id or UNVERIFIED

    # Step 4 — document_forms
    df: Optional[dict] = None
    if doc_id:
        df = _step4_document_form(sb, doc_id)
        if df:
            row["document_form_id"] = df["id"]
        else:
            review_reasons.append(f"document_forms 없음: doc_id={doc_id}")

    # Step 5 — runtime_form_schema
    schema: Optional[dict] = None
    if df and df.get("id"):
        schema = _step5_runtime_schema(sb, df["id"])
        if schema:
            row["runtime_form_schema_id"] = schema["id"]

    # Step 6 — runtime_field count
    field_count = 0
    if schema and schema.get("id"):
        field_count = _step6_field_count(sb, schema["id"])

    # ── 분류 ──────────────────────────────────────────────────────────────────
    reuse_status = _classify(
        form_code=form_code,
        ft=ft,
        doc_id=doc_id,
        df=df,
        schema=schema,
        field_count=field_count,
        review_reasons=review_reasons,
    )

    row["reuse_status"] = reuse_status
    row["matching_status"] = _matching_status(form_code, doc_id, df, schema)
    row["review_reason"]   = "; ".join(review_reasons) if review_reasons else None
    row["evidence_reference"] = _build_evidence_ref(form_code, doc_id, schema)
    row["recommended_action"] = _recommended_action(reuse_status, review_reasons)
    row["missing_fields"]     = _missing_fields(schema, field_count, reuse_status)

    return row


def _classify(
    form_code, ft, doc_id, df, schema, field_count, review_reasons
) -> str:
    # D 우선: 검토 필요 사유 있으면 D
    if review_reasons:
        return "D"

    # A: document_forms + APPROVED runtime_form_schema + field 존재
    if df and schema and schema.get("status") == _APPROVED and field_count > 0:
        return "A"

    # B: document_forms 또는 CANDIDATE schema 존재 — 보완 필요
    if df or (schema and schema.get("status") == _CANDIDATE):
        return "B"

    # form_code + form_templates 만 있고 doc_id 연결 없음 — C or B
    if form_code and ft and not doc_id:
        return "B"  # 연결 경로 없으나 form 존재 — 보완 가능

    # C: 법령 의무 확인이나 자산 없음
    if form_code or doc_id:
        return "C"

    # 아무 것도 없음 → D (정보 부족)
    return "D"


def _matching_status(form_code, doc_id, df, schema) -> str:
    if df and schema:
        return "MATCHED_FULL"
    if df and not schema:
        return "MATCHED_CATALOG_NO_SCHEMA"
    if form_code and not doc_id:
        return "FORM_ONLY_NO_CATALOG"
    if not form_code and not doc_id:
        return "NO_MATCH"
    return "PARTIAL"


def _build_evidence_ref(form_code, doc_id, schema) -> str:
    parts = []
    if form_code and form_code != UNVERIFIED:
        parts.append(f"form_templates:{form_code}")
    if doc_id and doc_id != UNVERIFIED:
        parts.append(f"document_forms:{doc_id}")
    if schema:
        parts.append(f"runtime_form_schema:{schema['id']}")
    return "; ".join(parts) if parts else UNVERIFIED


def _recommended_action(reuse_status: str, review_reasons: list) -> str:
    mapping = {
        "A": "기존 runtime_form_schema 재사용 — 신규 구현 불필요",
        "B": "document_forms 또는 runtime_field 보완 후 재사용 가능",
        "C": "신규 document_forms + runtime_form_schema 생성 필요 (Owner 승인 후)",
        "D": f"검토 필요: {'; '.join(review_reasons)}" if review_reasons else "검토 필요",
    }
    return mapping.get(reuse_status, UNVERIFIED)


def _missing_fields(schema, field_count: int, reuse_status: str) -> list[str]:
    missing = []
    if reuse_status in ("B", "C"):
        if not schema:
            missing.append("runtime_form_schema")
        if schema and field_count == 0:
            missing.append("runtime_field")
        if schema and schema.get("status") == _CANDIDATE:
            missing.append("schema_approval")
    return missing


# ── 전체 배치 실행 ────────────────────────────────────────────────────────────

def run_dryrun(sb, obligations: list[dict]) -> dict:
    """obligations 리스트 전체 분류 + 요약 반환.

    Returns:
      {
        "results": [per-obligation rows],
        "summary": {"A": n, "B": n, "C": n, "D": n, "total": n},
        "reuse_assets": [A 상태 rows],
        "next_candidate": <first A or B row> | None,
      }
    """
    rows: list[dict] = []
    for ob in obligations:
        rows.append(classify_one_obligation(sb, ob))

    counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    for r in rows:
        counts[r["reuse_status"]] = counts.get(r["reuse_status"], 0) + 1

    reuse_assets = [r for r in rows if r["reuse_status"] == "A"]
    ab_candidates = [r for r in rows if r["reuse_status"] in ("A", "B")]

    return {
        "results":        rows,
        "summary":        {**counts, "total": len(rows)},
        "reuse_assets":   reuse_assets,
        "next_candidate": ab_candidates[0] if ab_candidates else None,
    }
