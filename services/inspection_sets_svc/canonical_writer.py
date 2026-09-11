"""services/inspection_sets_svc/canonical_writer.py

WO-SAFE-ALL-OBLIGATION-MATERIALIZATION-IMPLEMENT-001
(prior: WO-SAAS-CANONICAL-INSPECTION-WRITER-001 / STEP 4B-3 REV-1).

official obligations_raw[] 의 **FINAL_EXTRACTED_OBLIGATIONS** (= raw 전체) 를
SaaS inspection_sets 미스케줄(operation) row 로 materialize 한다.

원칙:
- LEGAL TRUTH = official raw obligation. LEGAL PRESENTATION = map_operation_presentation(raw)(재사용, 신규 mapper 0).
- Membership = obligations_raw[] as-is. obligation_type 은 attribute only (생성 gate 아님).
- INSPECT EXACT membership gate = 제거. ACTION→INSPECT 등 type 변환/강제 저장 = 금지.
- check_result / applicability = membership gate 아님 (후단 재판정 필터 0).
- review_required collection 은 이 writer 입력에 합류하지 않음 (호출측 obligations_raw 만).
- 필수 = atom_id + presentation.action. 하나라도 없으면 row 0 (fail-close, 제목/원문 fallback 0).
- CASE C: cycle_unit/cycle_value/anchor/next_planned = 명시 NULL (자연어 timing/cycle → schedule 변환 0, default year/1 0).
- 기존 atom(재진단): LEGAL snapshot 만 refresh, 운영값(cycle/anchor/assignee/status/next_planned)은 보존.
- legal_rule_id/legal_rule_code = NULL (atom/law match 대입 0). partial unique (factory_id, legal_obligation_atom_id) 사용.
- 이 파일은 anchor/schedule 을 생성하지 않는다. has_explicit_schedule_cycle 는 anchor/schedule write 경계에서 쓰는 guard predicate.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.inspection_sets_svc.canonical_bridge import build_canonical_inspection_identity
from services.obligation_presentation_mapper import map_operation_presentation  # noqa: F401 (계약 재사용 명시)

#: 동일 atom 재진단 시 refresh 허용(법령 파생). 운영값은 절대 포함하지 않는다.
_REFRESH_FIELDS = (
    "law_name", "law_article", "obligation_type",
    "obligation_summary", "description", "legal_operation_presentation",
)


def has_explicit_schedule_cycle(iset: Any) -> bool:
    """SaaS operation completeness check (법적 해석 아님).

    cycle_unit 이 truthy 이고 cycle_value 가 None 이 아닐 때만 True.
    anchor/schedule write 경계(set_anchor_bulk / bulk_update_anchors / patch_set(anchor 설정) /
    update_anchor / generate_schedules_for_factory(anchor mode))에서 이 함수가 False 면
    schedule/next_planned 생성 0 · anchor_confirmed=true 0 · status ACTIVE 0 (fail-close).
    """
    d = iset if isinstance(iset, dict) else {}
    return bool(d.get("cycle_unit")) and d.get("cycle_value") is not None


def _obligation_type(raw: Any) -> Optional[str]:
    """enrichment.obligation_type 실값 운반. 없으면 None. 정규화/추정/강제 INSPECT = 0."""
    enr = raw.get("enrichment") if isinstance(raw, dict) else None
    return enr.get("obligation_type") if isinstance(enr, dict) else None


def build_canonical_set_payload(
    raw_obligation: Any, factory_id: Any, company_id: Any
) -> Optional[Dict[str, Any]]:
    """atom_id + presentation.action 있을 때만 신규 canonical row payload. 아니면 None(fail-close).

    obligation_type 은 membership gate 가 아니다. LEG enrichment 실값을 그대로 저장한다.
    """
    identity = build_canonical_inspection_identity(raw_obligation)  # atom_id 없으면 None
    if identity is None:
        return None
    op = identity["operation_presentation"]
    action = op.get("action")
    if not (isinstance(action, str) and action.strip()):  # action 없으면 row 0
        return None
    raw = raw_obligation  # dict 보장(identity None 아님)
    return {
        "factory_id": factory_id,
        "company_id": company_id,
        "source": "LEGAL_ENGINE",
        # 4B-1 exact identity carrier
        "legal_obligation_atom_id": identity["legal_obligation_atom_id"],
        # 4B-3 derived snapshot (consumer read-model, SoT 아님)
        "legal_operation_presentation": op,
        # LEG-derived 공식값 운반 (재작성 0 — action = presentation.action = obligation_detail.what)
        "inspection_set_name": action,
        "law_name": raw.get("law_name"),
        "law_article": raw.get("law_article"),
        "obligation_type": _obligation_type(raw),  # attribute only · INSPECT hardcode 0
        "obligation_summary": action,
        "description": action,
        # CASE C — 명시 NULL (legacy year/1 schedule fallback 차단)
        "cycle_unit": None,
        "cycle_value": None,
        "cycle_base_type": None,
        "cycle_base_guide": None,
        "schedule_anchor_date": None,
        "last_inspection_date": None,
        "next_planned_date": None,
        # 초기 operation 상태 — 자동 스케줄 없음
        "anchor_confirmed": False,
        "assignee_user_id": None,
        "status_code": "PENDING_ANCHOR",
        # legacy identity 비움 (atom/law 대입 0)
        "legal_rule_id": None,
        "legal_rule_code": None,
        "is_active": True,
    }


def materialize_canonical_inspection_sets(
    supabase: Any, factory_id: Any, company_id: Any, obligations_raw: Any
) -> Dict[str, int]:
    """obligations_raw membership → canonical rows materialize.

    신규 atom → INSERT. 기존 atom → LEGAL snapshot refresh(운영값 보존). 동일 atom 중복 INSERT 0.
    입력 obligations_raw mutation 없음. 이 함수는 anchor/schedule 을 만들지 않는다.
    check_result / applicability 로 재필터하지 않는다.
    """
    rows = obligations_raw if isinstance(obligations_raw, list) else []
    seen: set = set()
    payloads: List[Dict[str, Any]] = []
    for raw in rows:
        p = build_canonical_set_payload(raw, factory_id, company_id)
        if p is None:
            continue
        aid = p["legal_obligation_atom_id"]
        if aid in seen:            # 동일 batch 내 중복 atom → 1건만
            continue
        seen.add(aid)
        payloads.append(p)

    result = {"candidates": len(payloads), "inserted": 0, "refreshed": 0, "skipped": 0}
    if not payloads:
        return result

    atom_ids = [p["legal_obligation_atom_id"] for p in payloads]
    existing: Dict[Any, Any] = {}
    res = (
        supabase.table("inspection_sets")
        .select("id, legal_obligation_atom_id")
        .eq("factory_id", factory_id)
        .eq("source", "LEGAL_ENGINE")
        .in_("legal_obligation_atom_id", atom_ids)
        .execute()
    )
    for r in (res.data or []):
        existing[r.get("legal_obligation_atom_id")] = r.get("id")

    to_insert: List[Dict[str, Any]] = []
    for p in payloads:
        aid = p["legal_obligation_atom_id"]
        if aid in existing:
            # LEGAL snapshot 만 갱신 — 운영 상태(cycle/anchor/assignee/status/next_planned) 미포함
            patch = {k: p.get(k) for k in _REFRESH_FIELDS}
            supabase.table("inspection_sets").update(patch).eq("id", existing[aid]).execute()
            result["refreshed"] += 1
        else:
            to_insert.append(p)

    if to_insert:
        supabase.table("inspection_sets").insert(to_insert).execute()
        result["inserted"] = len(to_insert)
    return result
