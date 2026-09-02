"""
routers/diagnosis_result_web.py — v1.3.2

유료/무료 진단 결과 웹 조회 API (JSON)
  GET /diagnosis/result/{public_token}
  GET /diagnosis/paid-result/{public_token}

v1.1.0: BE-08 Transform 정제 함수 연동 (rules_table dedupe + FAMILY→한글)
v1.2.0: 의무 제목/설명 표시 보정 — obligation_summary/remarks가 코드 토큰일 때
        description의 사람이 읽는 텍스트를 우선 사용. 엔진/판정 로직 미변경.
v1.3.0: LEG 결과 표시 변환 — rules_table 부재 시 obligations_raw(rich)에서
        '값 생성 없이' rules_table/summary 형태로 이미 추출된 값만 운반. 축1 무변경.
v1.3.1: WO-FE-MAPPING-001 — Collector(check.collectors) + obligation 확장 매핑(add-only).
        · penalty_summary  ← check.collectors.penalty (COLLECTED + articles 있을 때만,
          의미=동일 법령 내 벌칙/과태료 조문, obligation_specific=false 유지)
        · submit_org_label ← check.collectors.agency.submit_org (COLLECTED만)
        · ministry         → 표시 미연결(DEFERRED). 원본 check.collectors는 불변.
        · D8 가드: distinct law identity == 1 결과에서만 collector 표시(fail-closed).
        · obligation 확장: executor_type_label(who)·condition·consumer_status·
          usable_for_evaluation·mapped_field·triggered_by·evidence (값 있을 때만).
        · top-level contract → payload.data.contract (LEG, 비어있지 않을 때만).
        값 생성 없음. 축1(Compiler) 경로·기존 v1.3.0 필드 무변경.
v1.3.2: obligation 확장 2 + 소관부처 노출(add-only, 값 생성 없음).
        · content_type ← enrichment.content_type (의무/금지 구분, 값 있을 때만)
        · check_result ← obligations_raw.check_result (검증 상태, 값 있을 때만)
        · governing_ministry ← check.collectors.agency.ministry (COLLECTED + 단일 법령만,
          결과 단위 1값. 제출처(submit_org)와 별개. 기존 DEFERRED 방침을 운영자 승인으로 해제)
v1.4.0: FREE-DIAGNOSIS-RESULT-UX-01 WP-B — free_obligations additive contract(add-only).
        · free_obligations[] = 무료 안전 투영(obligation_type·obligation_summary·law_name 3필드만).
          표시용 전체(dedupe 후) rules_table에서 절단 없이 전건 투영. 유료 상세필드·rule_id 미포함.
        · free_obligation_count = len(free_obligations) (사용자 표시 '의무 N건'의 정본).
        기존 rules_table(무료 5건)·summary·applicable_count·law_badges·paid 동작 무변경(additive only).
        엔진·DB·법령 무변경. 새 정규화 엔진 없음(기존 표시행의 최종값 재사용).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from services.diagnosis_runtime_step1 import enrich_rules_with_candidate_slots
from services.paid_result_product_svc import (
    SOURCE_TEXT_KEY,
    build_paid_result_product_v1,
)
from routers.diagnosis_transform import (
    CATEGORY_MAP,
    _extract_obligations,
    _extract_warnings,
    _normalize_category,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["진단결과웹"])

FREE_TIER_CODES = frozenset({
    "BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE",
    "free", "FREE",
})

SECTOR_LABEL = {
    "BUILDING": "건물", "INDUSTRY": "산업",
    "CONSTRUCTION": "건설", "MANUFACTURING": "산업(제조)",
}

_TOKEN_RE = re.compile(r"_CANDIDATE|_FAMILY|^[A-Z][A-Z0-9_]*\s*:\s*[A-Z][A-Z0-9_]*$")


def _is_token(v: Any) -> bool:
    s = (v or "").strip() if isinstance(v, str) else str(v or "").strip()
    if not s:
        return True
    return bool(_TOKEN_RE.search(s))


def _human_text(*cands: Any) -> str:
    for c in cands:
        s = (c or "").strip() if isinstance(c, str) else str(c or "").strip()
        if s and not _is_token(s):
            return s
    return ""


_FAMILY_STEM_TO_CATEGORY_KEY: Dict[str, str] = {
    "APPOINT": "appointment", "APPOINTMENT": "appointment", "DESIGNATE": "appointment",
    "INSPECT": "inspection", "MEASURE": "inspection", "VERIFY": "inspection", "TEST": "inspection",
    "REPORT": "report", "NOTIFY": "report", "REGISTER": "report", "PERMIT": "report",
    "PRESERVE": "document", "RECORD": "document", "MANAGE": "document",
    "INSTALL": "document", "MAINTAIN": "document",
    "TRAINING": "education", "EDUCATION": "education",
    "ACTION": "document", "MANDATORY": "document", "PERMISSIVE": "document", "PROHIBITION": "document",
}

_OBLIGATION_TYPE_TO_CATEGORY_KEY: Dict[str, str] = {
    "APPOINT": "appointment", "INSPECT": "inspection", "REPORT": "report",
    "NOTIFY": "report", "ACTION": "document", "OTHER": "document",
}


def _rule_kind_key(row: Dict[str, Any]) -> str:
    for field in ("rule_kind", "source_action_family", "obligation_family", "obligation_type", "rule_type"):
        val = (row.get(field) or "").strip().upper()
        if val:
            return val
    cat = (row.get("category") or "").strip().upper()
    if cat.endswith("_FAMILY") or cat.endswith("_TASK_CANDIDATE"):
        return cat
    for eng, kor in CATEGORY_MAP.items():
        if kor == row.get("category"):
            return eng.upper()
    return cat or "UNKNOWN"


def _law_article_key(row: Dict[str, Any]) -> str:
    law = (row.get("law_name") or "").strip()
    art = (row.get("law_article") or "").strip()
    return f"{law}|{art}"


def _category_key_for_row(row: Dict[str, Any]) -> str:
    raw = (row.get("rule_kind") or row.get("source_action_family") or row.get("obligation_family") or "").strip().upper()
    if raw.endswith("_FAMILY"):
        stem = raw[: -len("_FAMILY")]
        if stem in _FAMILY_STEM_TO_CATEGORY_KEY:
            return _FAMILY_STEM_TO_CATEGORY_KEY[stem]
    if raw.endswith("_TASK_CANDIDATE"):
        stem = raw.split("_TASK_CANDIDATE", 1)[0]
        if stem in _FAMILY_STEM_TO_CATEGORY_KEY:
            return _FAMILY_STEM_TO_CATEGORY_KEY[stem]
    obl = (row.get("obligation_type") or "").strip().upper()
    if obl in _OBLIGATION_TYPE_TO_CATEGORY_KEY:
        return _OBLIGATION_TYPE_TO_CATEGORY_KEY[obl]
    cat = (row.get("category") or "").strip().lower()
    if cat in CATEGORY_MAP:
        return cat
    kor = (row.get("category") or "").strip()
    for eng, label in CATEGORY_MAP.items():
        if label == kor:
            return eng
    return "document"


def _dedupe_rules_table(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for row in rules_table:
        key = (_law_article_key(row), _rule_kind_key(row))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _rule_row_to_obligation_src(row: Dict[str, Any]) -> Dict[str, Any]:
    cat_key = _category_key_for_row(row)
    law_ref = " ".join(p for p in ((row.get("law_name") or "").strip(), (row.get("law_article") or "").strip()) if p)
    human = _human_text(row.get("description"), row.get("obligation_summary"), row.get("remarks"), row.get("rule_name"))
    return {
        "id": str(row.get("rule_id") or row.get("id") or ""),
        "category": cat_key, "type": cat_key,
        "title": human or "의무사항", "name": human or "", "description": human or "",
        "risk_level": row.get("risk_level") or "MEDIUM",
        "legal_basis": law_ref, "evidence": [law_ref] if law_ref else [],
    }


def _merge_obligation_into_rule_row(obligation: Dict[str, Any], original: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(original)
    merged["category"] = obligation.get("category") or _normalize_category(_category_key_for_row(original))
    merged["rule_kind"] = _rule_kind_key(original)
    merged["rule_kind_label"] = merged["category"]
    human = _human_text(
        obligation.get("title"), obligation.get("description"),
        original.get("description"), original.get("obligation_summary"), original.get("remarks"),
    )
    if human:
        if _is_token(merged.get("obligation_summary")):
            merged["obligation_summary"] = human
        if _is_token(merged.get("description")):
            merged["description"] = human
    if _is_token(merged.get("remarks")):
        merged["remarks"] = ""
    return merged


def _refine_rules_table(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped = _dedupe_rules_table(rules_table)
    if not deduped:
        return []
    lookup: Dict[str, Dict[str, Any]] = {}
    for row in deduped:
        rid = str(row.get("rule_id") or row.get("id") or "")
        if rid:
            lookup[rid] = row
        title_key = (row.get("obligation_summary") or row.get("description") or "")[:120]
        if title_key:
            lookup[f"title:{title_key}"] = row
    extracted = _extract_obligations({"obligations": [_rule_row_to_obligation_src(r) for r in deduped]})
    refined: List[Dict[str, Any]] = []
    for ob in extracted:
        oid = str(ob.get("id") or "")
        orig = lookup.get(oid) if oid else None
        if not orig:
            tkey = f"title:{(ob.get('title') or '')[:120]}"
            orig = lookup.get(tkey)
        if orig:
            refined.append(_merge_obligation_into_rule_row(ob, orig))
    return refined if refined else deduped


# ─────────────────────────────────────────────────────────────
# LEG(법령엔진) 결과 표시 변환 (v1.3.0) + Collector·obligation 확장 (v1.3.1)
# ─────────────────────────────────────────────────────────────
_LEG_TYPE_TO_PAGE: Dict[str, str] = {
    "APPOINT": "APPOINT", "INSPECT": "INSPECT", "REPORT": "REPORT",
    "NOTIFY": "NOTIFY", "ACTION": "ACTION", "TRAINING": "ACTION", "PROHIBIT": "ACTION",
}
_LEG_PAGE_TYPE_TO_SUMMARY: Dict[str, str] = {
    "APPOINT": "appointment", "INSPECT": "inspection", "ACTION": "action",
    "REPORT": "report", "NOTIFY": "notify",
}


def _leg_obligation_type(o: Dict[str, Any]) -> str:
    enr = o.get("enrichment") or {}
    raw = (enr.get("obligation_type") or "").strip().upper()
    return _LEG_TYPE_TO_PAGE.get(raw, "ACTION")


def _leg_rule_row(o: Dict[str, Any]) -> Dict[str, Any]:
    """obligations_raw 1건 → 페이지 rules_table 1행 (값 생성 없음)."""
    enr = o.get("enrichment") or {}
    det = o.get("obligation_detail") or {}
    law_name = (o.get("law_name") or "").strip()
    law_article = (o.get("law_article") or "").strip()
    what = (det.get("what") or "").strip()
    summary_text = what or " ".join(p for p in (law_name, law_article) if p)
    row: Dict[str, Any] = {
        "law_name": law_name,
        "law_article": law_article,
        "obligation_type": _leg_obligation_type(o),
        "obligation_summary": summary_text,
        "description": summary_text,
        "inspection_cycle": (enr.get("inspection_cycle") or "").strip(),
        "atom_id": o.get("atom_id") or "",
        "source": "LEG",
    }
    # v1.3.1 STEP 6 확장 — 이미 존재하는 값만 운반(값 있을 때만, 합성 금지).
    who = (det.get("who") or "").strip()
    if who:
        row["executor_type_label"] = who          # 수행자 (기존 프론트 계약 필드)
    condition = (det.get("condition") or "").strip()
    if condition:
        row["condition"] = condition               # 적용조건
    cstatus = (enr.get("consumer_status") or "").strip()
    if cstatus:
        row["consumer_status"] = cstatus           # 이행상태 (우선)
    if enr.get("usable_for_evaluation") is not None:
        row["usable_for_evaluation"] = enr.get("usable_for_evaluation")  # 보조(합성 금지)
    mapped_field = (o.get("mapped_field") or "").strip()
    if mapped_field:
        row["mapped_field"] = mapped_field         # 적용 이유
    triggered_by = o.get("triggered_by")
    if isinstance(triggered_by, list) and triggered_by:
        row["triggered_by"] = triggered_by         # 적용 이유(입력 필드)
    evidence = (o.get("evidence") or "").strip()
    if evidence:
        row["evidence"] = evidence                 # 근거(원문 그대로, 재작성 금지)
    # v1.3.2 확장 — 값 있을 때만
    content_type = (enr.get("content_type") or "").strip()
    if content_type:
        row["content_type"] = content_type         # 의무/금지 구분(OBLIGATION/PROHIBITION)
    check_result = (o.get("check_result") or "").strip()
    if check_result:
        row["check_result"] = check_result         # 검증 상태(VERIFIED 등)
    return row


def _leg_rules_from_obligations_raw(obligations_raw: List[Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen_atom: set = set()
    for source_index, o in enumerate(obligations_raw):
        if not isinstance(o, dict):
            continue
        appl = (o.get("applicability") or "").strip().upper()
        if appl and appl != "APPLICABLE":
            continue
        aid = str(o.get("atom_id") or "")
        if aid and aid in seen_atom:
            continue
        if aid:
            seen_atom.add(aid)
        row = _leg_rule_row(o)
        if not (row["law_name"] or row["obligation_summary"]):
            continue
        # WO-05D-A: canonical join axis. caller 가 dict-filter 후 넘긴 obligations_raw 의
        # enumerate index = Materializer normalized_obligations.identity.source_index 와 정합.
        row[_INTERNAL_SOURCE_INDEX] = source_index
        rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────
# WO-05D-A: paid-result canonical source-text SAFE PRESENTATION PROJECTION
#   INTERNAL PRODUCT(paid_result_source_text_v1)의 EXACT 원문만 rules_table 표시행에
#   additive(canonical_source_text)로 투영. provenance(atom_id 외)·6-key raw 노출 0.
# ─────────────────────────────────────────────────────────────
# 내부 join axis. Materializer normalized_obligations[n].identity.source_index 와 정합.
# HTTP response 노출 0 — 최종 payload 직전 반드시 제거(_strip_internal_source_index).
_INTERNAL_SOURCE_INDEX = "__source_index"
_CANONICAL_SOURCE_TEXT = "canonical_source_text"


def _source_text_exact_items_by_ref(product: Any) -> Dict[Any, Dict[str, Any]]:
    """paid_result_source_text_v1.items 중 resolution_status==EXACT 이고 text 가
    non-empty 인 항목만 obligation_ref -> item 으로 매핑. SOURCE_MISMATCH/UNRESOLVED 제외."""
    out: Dict[Any, Dict[str, Any]] = {}
    sidecar = product.get(SOURCE_TEXT_KEY) if isinstance(product, dict) else None
    items = sidecar.get("items") if isinstance(sidecar, dict) else None
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("resolution_status") != "EXACT":
            continue
        text = it.get("text")
        if not (isinstance(text, str) and text):
            continue
        out[it.get("obligation_ref")] = it
    return out


def _attach_canonical_source_text(
    rules_table: List[Dict[str, Any]], items_by_ref: Dict[Any, Dict[str, Any]]
) -> None:
    """STEP 6 — EXACT source_index join 이 성립할 때만 canonical_source_text 를 additive 부착.

    조건(전부 만족): A) row 내부 source_index == item.obligation_ref EXACT ·
    B) item.resolution_status==EXACT (items_by_ref 단계에서 보장) · C) item.text non-empty ·
    D) row.atom_id 와 item.atom_id 가 모두 존재하면 EXACT equality.
    duty.what/evidence 복사·SOURCE_MISMATCH·UNRESOLVED fallback·추측 매핑 금지. 기존 필드 무변경.
    """
    for row in rules_table:
        if not isinstance(row, dict) or _INTERNAL_SOURCE_INDEX not in row:
            continue
        it = items_by_ref.get(row.get(_INTERNAL_SOURCE_INDEX))
        if not it:
            continue
        row_atom = row.get("atom_id")
        it_atom = it.get("atom_id")
        if row_atom and it_atom and str(row_atom) != str(it_atom):
            continue  # D: 둘 다 존재하는데 불일치 → 부착 안 함
        row[_CANONICAL_SOURCE_TEXT] = it["text"]


def _strip_internal_source_index(rules_table: List[Dict[str, Any]]) -> None:
    """내부 join key(__source_index) 를 HTTP 노출 전에 제거. free/paid 양 경로 공통."""
    for row in rules_table:
        if isinstance(row, dict):
            row.pop(_INTERNAL_SOURCE_INDEX, None)


def _leg_summary_from_rules(rules: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"appointment": 0, "inspection": 0, "action": 0, "report": 0, "notify": 0}
    for r in rules:
        bucket = _LEG_PAGE_TYPE_TO_SUMMARY.get(r.get("obligation_type") or "", "action")
        counts[bucket] += 1
    counts["total"] = len(rules)
    counts["form_linked"] = 0
    return counts


# ── v1.3.1 Collector 매핑 (check.collectors, 값 생성 없음·status 존중) ──
def _get_collectors(full_result: Dict[str, Any]) -> Dict[str, Any]:
    check = full_result.get("check") or {}
    col = check.get("collectors") or {}
    return col if isinstance(col, dict) else {}


def _collector_penalty_summary(collectors: Dict[str, Any]) -> str:
    """penalty COLLECTED + articles 있을 때만. 의미=동일 법령 내 벌칙/과태료 조문(의무-특정 아님)."""
    pen = collectors.get("penalty") or {}
    if (pen.get("status") or "").strip().upper() != "COLLECTED":
        return ""
    val = pen.get("value") or {}
    articles = val.get("articles") or []
    if not isinstance(articles, list) or not articles:
        return ""
    refs: List[str] = []
    for a in articles:
        if isinstance(a, str):
            s = a.strip()
        elif isinstance(a, dict):
            s = (a.get("article") or a.get("article_no") or a.get("label") or a.get("title") or "").strip()
        else:
            s = ""
        if s:
            refs.append(s)
    base = "동일 법령 내 벌칙·과태료 조문"
    return f"{base} ({', '.join(refs)})" if refs else base


def _collector_submit_org_label(collectors: Dict[str, Any]) -> str:
    """제출처(submit_org) COLLECTED만. 소관부처(ministry)는 여기 넣지 않는다(D5)."""
    ag = collectors.get("agency") or {}
    so = ag.get("submit_org") or {}
    if (so.get("status") or "").strip().upper() != "COLLECTED":
        return ""
    v = so.get("value")
    return v.strip() if isinstance(v, str) and v.strip() else ""


def _collector_ministry(full_result: Dict[str, Any], rules_table: List[Dict[str, Any]]) -> str:
    """소관부처(ministry) COLLECTED + 단일 법령(D8)일 때만. 결과 단위 1값. 제출처(submit_org)와 별개."""
    collectors = _get_collectors(full_result)
    if not collectors:
        return ""
    distinct_laws = {(r.get("law_name") or "").strip() for r in rules_table if (r.get("law_name") or "").strip()}
    if len(distinct_laws) != 1:
        return ""
    mi = (collectors.get("agency") or {}).get("ministry") or {}
    if (mi.get("status") or "").strip().upper() != "COLLECTED":
        return ""
    v = mi.get("value")
    return v.strip() if isinstance(v, str) and v.strip() else ""


def _apply_collectors_to_leg_rows(full_result: Dict[str, Any], rules_table: List[Dict[str, Any]]) -> None:
    """D8 fail-closed: distinct law identity == 1 결과에서만 result-level collector를 각 행에 적용.
    ministry는 표시 미연결(DEFERRED). collector 값을 다중 법령 행에 복제하지 않는다."""
    collectors = _get_collectors(full_result)
    if not collectors:
        return
    distinct_laws = {(r.get("law_name") or "").strip() for r in rules_table if (r.get("law_name") or "").strip()}
    if len(distinct_laws) != 1:
        return  # multi-law: backend law_id-keyed map 제공 전까지 미표시
    penalty_summary = _collector_penalty_summary(collectors)
    submit_org_label = _collector_submit_org_label(collectors)
    if not (penalty_summary or submit_org_label):
        return
    for r in rules_table:
        if penalty_summary:
            r["penalty_summary"] = penalty_summary
        if submit_org_label:
            r["submit_org_label"] = submit_org_label


# ─────────────────────────────────────────────────────────────
# v1.4.0 무료 안전 투영 (FREE = WHAT APPLIES). 유료 상세필드·rule_id 미포함.
#   표시용(dedupe 후) rules_table 행의 최종 표시값만 재사용 — 새 정규화/합성 없음.
# ─────────────────────────────────────────────────────────────
FREE_OBLIGATION_KEYS = ("obligation_type", "obligation_summary", "law_name")


def _project_free_obligation(row: Dict[str, Any]) -> Dict[str, Any]:
    """rules_table 표시행 → 무료 계약 3필드(정확히 이 키만). 유료 상세·내부 메타 제외."""
    return {
        "obligation_type": (row.get("obligation_type") or "").strip(),
        "obligation_summary": (row.get("obligation_summary") or row.get("description") or "").strip(),
        "law_name": (row.get("law_name") or "").strip(),
    }


_PUBLIC_KEY_OBLIGATION_FIELDS = (
    "type", "obligation_type", "obligation_summary", "description", "remarks",
    "rule_name", "law", "law_name", "law_article", "penalty", "penalty_summary",
)


def _public_key_obligation(row: Any) -> Dict[str, Any]:
    """key_obligations public projection — allowlist only(내부 provenance 차단, 값 합성 0)."""
    if not isinstance(row, dict):
        return {}
    return {k: row[k] for k in _PUBLIC_KEY_OBLIGATION_FIELDS if k in row}


def _build_free_obligations(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """표시용 전체 rules_table(절단 전)에서 무료 안전 투영 전건 생성."""
    return [_project_free_obligation(r) for r in rules_table]


RECOMMEND_PLAN = {
    "BUILDING_V2":          {"name": "건물 소형 플랜",  "price": "월 59,000원~"},
    "BUILDING_LARGE_V2":    {"name": "건물 대형 플랜",  "price": "월 145,000원~"},
    "INDUSTRY_V2":          {"name": "산업 STARTER",   "price": "월 79,000원~"},
    "INDUSTRY_STANDARD":    {"name": "산업 BUSINESS",  "price": "월 149,000원~"},
    "INDUSTRY_PREMIUM":     {"name": "산업 PRO",       "price": "월 249,000원~"},
    "CONSTRUCTION":         {"name": "건설 STANDARD",  "price": "월 145,000원~"},
    "CONSTRUCTION_PREMIUM": {"name": "건설 PREMIUM",   "price": "월 385,000원~"},
}


@router.get("/result/{public_token}")
def get_diagnosis_result_web(public_token: str):
    return _build_result_payload(public_token, free_preview_limit=5)


@router.get("/paid-result/{public_token}")
def get_paid_result_web(public_token: str):
    return _build_result_payload(public_token, free_preview_limit=None, include_paid_product=True)


def _build_result_payload(public_token: str, free_preview_limit: Optional[int],
                          include_paid_product: bool = False) -> Dict[str, Any]:
    supabase = get_supabase()

    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, public_token, tier_code, full_result, input_data, status, expires_at, created_at")
        .eq("public_token", public_token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")

    rec = res.data[0]
    if rec.get("status") != "ACTIVE":
        raise HTTPException(status_code=410, detail="비활성화된 진단 결과입니다.")

    tier_code = rec.get("tier_code") or ""
    is_free = tier_code in FREE_TIER_CODES or tier_code.endswith("_FREE") or "FREE" in tier_code.upper()

    full_result = rec.get("full_result") or {}
    input_data = rec.get("input_data") or {}

    sector = (full_result.get("sector") or input_data.get("sector") or "BUILDING").upper()
    sector_label = SECTOR_LABEL.get(sector, sector)

    raw_rules = [r for r in (full_result.get("rules_table") or []) if isinstance(r, dict)]
    leg_summary: Optional[Dict[str, int]] = None
    leg_contract: Optional[Dict[str, Any]] = None
    leg_ministry: str = ""
    if raw_rules:
        # 축1(Compiler) 결과: 기존 경로 무변경.
        rules_table = _refine_rules_table(raw_rules)
    else:
        # LEG 결과: obligations_raw(rich)에서 표시용 rules_table 파생.
        obligations_raw = [o for o in (full_result.get("obligations_raw") or []) if isinstance(o, dict)]
        rules_table = _leg_rules_from_obligations_raw(obligations_raw)
        if rules_table:
            leg_summary = _leg_summary_from_rules(rules_table)
            # v1.3.1: Collector(penalty/submit_org) 적용 — D8 단일 법령 가드.
            _apply_collectors_to_leg_rows(full_result, rules_table)
            # v1.3.2: 소관부처(ministry) — COLLECTED + 단일 법령만(제출처와 별개).
            leg_ministry = _collector_ministry(full_result, rules_table)
            # v1.3.1: top-level contract 노출 (비어있지 않을 때만).
            _contract = full_result.get("contract")
            if isinstance(_contract, dict) and _contract:
                leg_contract = _contract

    # WO-05D-A STEP 3/6/9/10: genuine paid + LEG path 에서만 Product Assembler(canonical caller)
    #   1회 호출 → source-text EXACT 만 additive 투영. legacy(raw_rules) 경로는 source_index
    #   provenance 부재로 부착 0(추측 금지). infra(DB/LEG Runtime) 실패는 성공 위장 금지(503).
    if include_paid_product and not is_free and not raw_rules and rules_table:
        try:
            _paid_product = build_paid_result_product_v1(rec)
        except Exception:
            log.exception("paid_result_product build failed")
            raise HTTPException(status_code=503, detail="유료 진단 법령 원문을 불러오지 못했습니다.")
        _attach_canonical_source_text(rules_table, _source_text_exact_items_by_ref(_paid_product))

    # 내부 join key(__source_index) 제거 — HTTP 노출 0(free/paid 공통).
    _strip_internal_source_index(rules_table)

    warnings = _extract_warnings(full_result)

    inspection_required = [r for r in (full_result.get("inspection_required") or []) if isinstance(r, dict)]
    appointment_required = [r for r in (full_result.get("appointment_required") or []) if isinstance(r, dict)]
    if raw_rules:
        enrich_rules_with_candidate_slots(supabase, rules_table + inspection_required + appointment_required)
    key_obligations = full_result.get("key_obligations") or []
    law_badges = full_result.get("law_badges") or []
    if leg_summary is not None and len(law_badges) <= 1:
        _derived_badges: List[str] = []
        _seen_law: set = set()
        for r in rules_table:
            ln = (r.get("law_name") or "").strip()
            if ln and ln not in _seen_law:
                _seen_law.add(ln)
                _derived_badges.append(ln)
        if _derived_badges:
            law_badges = _derived_badges
    inspection_schedule = full_result.get("inspection_schedule_ready") or {}

    summary = full_result.get("summary") or leg_summary or {}
    total = full_result.get("applicable_count") or summary.get("total") or len(rules_table)
    risk_level = full_result.get("risk_level") or "MEDIUM"
    worker_count = input_data.get("workers") or input_data.get("worker_count") or 0

    law_groups: Dict[str, list] = {}
    for r in rules_table:
        law = r.get("law_name") or "기타"
        law_groups.setdefault(law, []).append(r)
    law_group_list = sorted(
        [{"law_name": k, "count": len(v), "rules": v} for k, v in law_groups.items()],
        key=lambda x: x["count"], reverse=True,
    )

    ob_counts: Dict[str, int] = {}
    for r in rules_table:
        label = r.get("category") or r.get("obligation_type") or "기타"
        ob_counts[label] = ob_counts.get(label, 0) + 1

    plan_info = RECOMMEND_PLAN.get(tier_code, {})
    company_name = input_data.get("company_name") or full_result.get("company_name") or "사업장"

    limit = free_preview_limit if is_free else None
    rules_out = rules_table[:limit] if limit else rules_table
    _key_ob_src = key_obligations[:limit] if limit else key_obligations
    key_ob_out = [_public_key_obligation(r) for r in _key_ob_src if isinstance(r, dict)]
    law_grp_out = law_group_list[:limit] if limit else law_group_list

    # v1.4.0: 무료 안전 의무 목록(additive). 표시용 전체 rules_table에서 절단 없이 전건 투영.
    #   rules_out(무료 5건 legacy)와 독립. summary.total/applicable_count(엔진 dedupe 전 값)과
    #   다를 수 있으므로 사용자 표시 건수의 정본은 free_obligation_count(=len)로 한다.
    free_obligations = _build_free_obligations(rules_table)

    engine_version = full_result.get("engine_version") or "v3.0-runtime-compiler"

    payload = {
        "status": "success",
        "data": {
            "public_token": public_token,
            "tier_code": tier_code,
            "is_free": is_free,
            "sector": sector,
            "sector_label": sector_label,
            "company_name": company_name,
            "risk_level": risk_level,
            "risk_reason": full_result.get("risk_reason"),
            "applicable_count": total,
            "engine_version": engine_version,
            "summary": {
                "total": total,
                "inspection": summary.get("inspection") or len(inspection_required),
                "appointment": summary.get("appointment") or len(appointment_required),
                "action": summary.get("action") or 0,
                "report": (summary.get("report") or 0) + (summary.get("notify") or 0),
                "form_linked": summary.get("form_linked") or 0,
                "law_count": len(law_badges),
                "worker_count": worker_count,
                "csia_applicable": int(worker_count or 0) >= 5,
            },
            "obligation_counts": ob_counts,
            "warnings": warnings,
            "rules_table": rules_out,
            "appointment_required": appointment_required,
            "inspection_required": inspection_required,
            "law_badges": law_badges,
            "key_obligations": key_ob_out,
            "inspection_schedule": inspection_schedule if not is_free else {},
            "law_groups": law_grp_out,
            "free_obligations": free_obligations,
            "free_obligation_count": len(free_obligations),
            "input_data": {
                "company_name": company_name,
                "business_no": input_data.get("business_no") or "",
                "ceo_name": input_data.get("ceo_name") or "",
                "address": input_data.get("address") or "",
                "worker_count": worker_count,
                "floor_area": input_data.get("floor_area") or input_data.get("total_floor_area") or "",
            },
            "recommended_plan": plan_info,
            "pdf_url": f"/diagnosis/report-pdf/{public_token}",
        },
    }
    # v1.3.1: LEG top-level contract (입력 부족 고지용) — 비어있지 않을 때만 add-only.
    if leg_contract is not None:
        payload["data"]["contract"] = leg_contract
    if leg_ministry:
        payload["data"]["governing_ministry"] = leg_ministry
    return payload
