"""
semantic_diagnosis_service — D단계: 엔진을 의미절(semantic_clause)에 직접 연결.

설계: docs/2026-06-14_STAGE_D_SEMANTIC_CLAUSE_CONNECTION_DESIGN.md
- 현재 진단(anonymous_factory_service)은 executable_draft+draft_slot만 의무 원천으로 씀
  → 의무의 98%가 평가장에 못 들어옴(PASS 31%·binding 7% 병목).
- 이 서비스는 의무 원천을 semantic_clause로 전환. sector+article 해당 OBLIGATION/PROHIBITION
  의미절 전체를 "해당 의무 목록"으로 도출(1차 범위). 수치 게이팅은 후속(체크엔진).
- executor 보정분을 읽기 위해 semantic_clause_fix(임시테이블, APPLIED 계열)를 우선 읽음.

영역 경계:
- 분해기·판정로직(evaluate_draft_for_facility)·정제레이어·master_rule_v2 = GPT 영역, 무수정.
- 이 파일은 런타임 적재원 전환만(Claude=Product/Runtime Ops). 의미절 데이터 수정 없음(읽기만).
- sector 필터는 기존 표준(article→law→law_sector_mapping) 그대로 재사용. 새 표준 안 만듦.

출력: anonymous_factory_service._compiler_result_to_step1_format이 쓰는 것과 호환되는
      rules_table/obligations/summary 구조(정제 레이어 재사용).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from schemas.legal_engine import DiagnoseStep1Body
from services.legal_context import _input_to_facility_context
from services.legal_helpers import get_sector_groups
from services.legal_rules import normalize_sector_db, risk_level
from services.diagnosis_helpers import SOURCE_DIAGNOSIS
from services.anonymous_factory_service import (
    normalize_consumer_inp,
    _mapping_sector_key,
    _bucket_for_task_type,
    _is_token_text,
)

log = logging.getLogger(__name__)

SEMANTIC_ENGINE_VERSION = "v3.1-semantic-clause-direct"
RULE_VERSION_SEMANTIC = "semantic_clause:direct:v1"

_PAGE = 1000
_CHUNK = 200

# 의무로 취급할 content_type (벌칙/위임/정의/효력 제외)
_OBLIGATION_CONTENT_TYPES = ("OBLIGATION", "PROHIBITION")

# action_text/source 키워드 → bucket (수범자 행위 분류)
_ACTION_KEYWORDS = [
    ("선임", "appointment"), ("지정", "appointment"),
    ("점검", "inspection"), ("검사", "inspection"), ("측정", "inspection"), ("진단", "inspection"),
    ("신고", "report"), ("제출", "report"), ("등록", "report"), ("신청", "report"),
    ("보고", "notify"), ("통보", "notify"), ("통지", "notify"),
]


def _bucket_for_clause(action_text: str, source_text: str) -> tuple[str, str]:
    """의미절의 action_text/source_text에서 bucket 분류. 매칭 없으면 조치(action)."""
    hay = f"{action_text or ''} {source_text or ''}"
    for kw, bucket in _ACTION_KEYWORDS:
        if kw in hay:
            label = {"appointment": "선임", "inspection": "점검",
                     "report": "신고", "notify": "보고", "action": "조치"}[bucket]
            return bucket, label
    return "action", "조치"


def _load_sector_allowed_article_ids(supabase, sector_value: str) -> Optional[Set[str]]:
    """sector → 허용 article_id 집합. 기존 표준(law_article→law_master←law_sector_mapping) 재사용.

    통과 규칙(기존 _load_sector_allowed_draft_ids와 동일):
      - 해당 sector가 law_sector_mapping.sectors에 포함 → 통과
      - 미매핑 법령 → 통과(가지고 감)
      - 타 sector 전용 → 제외
    Returns: 허용 article_id 집합. 매핑 없거나 실패 시 None(필터 미적용 폴백).
    """
    key = _mapping_sector_key(sector_value)
    if not key:
        return None

    # 1) 의미절이 참조하는 article_id 전체 + law_id 매핑
    article_law: Dict[str, str] = {}
    law_ids: Set[str] = set()
    offset = 0
    while True:
        try:
            res = (
                supabase.table("law_article")
                .select("id, law_id")
                .range(offset, offset + _PAGE - 1)
                .execute()
            )
        except Exception as exc:
            log.warning("semantic sector-filter law_article fetch failed: %s", exc)
            return None
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            aid = str(row.get("id") or "")
            lid = str(row.get("law_id") or "")
            if aid and lid:
                article_law[aid] = lid
                law_ids.add(lid)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE

    if not article_law:
        return None

    # 2) law_sector_mapping: law_id → sectors[]
    law_sectors: Dict[str, List[str]] = {}
    lid_list = list(law_ids)
    for i in range(0, len(lid_list), _CHUNK):
        chunk = lid_list[i:i + _CHUNK]
        try:
            res = (
                supabase.table("law_sector_mapping")
                .select("law_id, sectors")
                .in_("law_id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("semantic sector-filter law_sector_mapping fetch failed: %s", exc)
            return None
        for row in res.data or []:
            lid = str(row.get("law_id") or "")
            secs = row.get("sectors") or []
            if lid:
                law_sectors[lid] = [str(s).strip().upper() for s in secs if s]

    if not law_sectors:
        return None

    # 3) article별 통과 판정
    allowed: Set[str] = set()
    for aid, lid in article_law.items():
        secs = law_sectors.get(lid)
        if secs is None:
            allowed.add(aid)        # 미매핑 → 가지고 감
        elif key in secs:
            allowed.add(aid)        # 해당 sector
        # else 타 sector 전용 → 제외
    return allowed


def _load_obligation_clauses(
    supabase,
    allowed_article_ids: Optional[Set[str]],
) -> List[Dict[str, Any]]:
    """semantic_clause_fix(보정 우선)에서 OBLIGATION/PROHIBITION 의무절 적재.

    executor 보정분(executor_text 교정됨)을 그대로 읽는다. sector 필터(allowed_article_ids)가
    주어지면 그 article에 속한 것만. None이면 전체(폴백).
    """
    clauses: List[Dict[str, Any]] = []
    offset = 0
    while True:
        try:
            res = (
                supabase.table("semantic_clause_fix")
                .select("id, source_article_id, source_text, executor_text, action_text, "
                        "cycle_text, content_type, sector, law_name, law_article")
                .in_("content_type", list(_OBLIGATION_CONTENT_TYPES))
                .range(offset, offset + _PAGE - 1)
                .execute()
            )
        except Exception as exc:
            log.warning("semantic_clause_fix fetch failed: %s", exc)
            break
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            aid = str(row.get("source_article_id") or "")
            if allowed_article_ids is not None and aid and aid not in allowed_article_ids:
                continue
            clauses.append(row)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE
    return clauses


def _clause_to_rule_row(clause: Dict[str, Any], sector_raw: str) -> Dict[str, Any]:
    """의미절 → 정제 레이어 호환 rule row."""
    action_text = (clause.get("action_text") or "").strip()
    source_text = (clause.get("source_text") or "").strip()
    executor = (clause.get("executor_text") or "").strip()
    bucket, cat_label = _bucket_for_clause(action_text, source_text)
    obl_map = {"appointment": "APPOINT", "inspection": "INSPECT",
               "report": "REPORT", "notify": "NOTIFY", "action": "ACTION"}
    obl_type = obl_map.get(bucket, "ACTION")
    law_name = (clause.get("law_name") or "").strip()
    law_article = (clause.get("law_article") or "").strip()
    # 요약 = source_text(의무 원문) 우선, 토큰이면 법령명+조문
    summary = source_text if (source_text and not _is_token_text(source_text)) else \
        " ".join(p for p in (law_name, law_article) if p).strip() or "의무사항"
    return {
        "rule_id": str(clause.get("id") or ""),
        "rule_type": bucket.upper(),
        "law_name": law_name or "법령",
        "law_article": law_article,
        "obligation_summary": summary[:300],
        "remarks": "",
        "description": summary[:300],
        "category": cat_label,
        "obligation_type": obl_type,
        "executor": executor,                 # ★ 보정된 수범자(주어)
        "source_action_family": "",
        "then_action_token": "",
        "sector": sector_raw,
        "diagnosis_stage": 1,
        "schedule_type": "ON_DEMAND",
        "penalty_summary": "",
        "source": SOURCE_DIAGNOSIS,
        "appointment_required": bucket == "appointment",
        "inspection_required": bucket == "inspection",
        "action_required": bucket == "action",
        "report_required": bucket == "report",
        "notify_required": bucket == "notify",
        "_bucket": bucket,
    }


def run_semantic_diagnosis(
    supabase,
    body: DiagnoseStep1Body,
    allowed_sectors,
) -> Dict[str, Any]:
    """D단계 의미절 직접 진단. 기존 run_anonymous_diagnosis와 같은 출력 구조.

    임시 factory 생성/평가/cleanup 없음 — 의미절을 sector+article로 직접 도출.
    1차 범위 = 의무 목록 도출(수치 게이팅 없음, 체크엔진 후속).
    """
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError("sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다.")

    inp = normalize_consumer_inp(body)
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = datetime.now(timezone.utc).isoformat()
    sector_db = normalize_sector_db(sector_raw)

    allowed_article_ids = _load_sector_allowed_article_ids(supabase, sector_db)
    clauses = _load_obligation_clauses(supabase, allowed_article_ids)
    rules_from_clauses = [_clause_to_rule_row(c, sector_raw) for c in clauses]

    triggered: Dict[str, List] = {
        "appointment": [], "inspection": [], "notify": [], "report": [], "action": [], "not_applicable": [],
    }
    for row in rules_from_clauses:
        bucket = row.pop("_bucket", "action")
        triggered[bucket].append(row)

    rules_table: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치"),
                       ("report", "신고"), ("notify", "보고")]:
        for row in triggered[key]:
            rules_table.append({"category": label, **row})

    total_applicable = sum(len(triggered[k]) for k in ("appointment", "inspection", "notify", "report", "action"))
    law_names = sorted({x.get("law_name") for x in rules_from_clauses if x.get("law_name")})
    appointment_n = len(triggered["appointment"])
    risk = risk_level(total_applicable, appointment_n)

    obligations: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치"),
                       ("report", "신고"), ("notify", "보고")]:
        if triggered[key]:
            obligations.append({"category": key, "label": label, "items": triggered[key]})

    return {
        "sector": sector_raw,
        "sector_groups": get_sector_groups(sector_db),
        "step": 1,
        "engine_version": SEMANTIC_ENGINE_VERSION,
        "rule_version": RULE_VERSION_SEMANTIC,
        "evaluated_at": evaluated_at,
        "facility_context": facility_ctx,
        "risk_level": risk,
        "risk_reason": f"적용 법령 {len(law_names)}개, 법적 의무 {total_applicable}건 (의미절 직접)",
        "applicable_law_categories": law_names,
        "appointment_required_flag": appointment_n > 0,
        "law_badges": law_names,
        "obligations": obligations,
        "rules_table": rules_table,
        "rules": rules_table,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "not_applicable": [],
        "total_rules_checked": total_applicable,
        "applicable_count": total_applicable,
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
            "notify": len(triggered["notify"]),
            "form_linked": 0,
        },
        "semantic_direct": {
            "clauses_loaded": len(clauses),
            "sector_filtered": allowed_article_ids is not None,
            "allowed_articles": len(allowed_article_ids) if allowed_article_ids else None,
        },
    }
