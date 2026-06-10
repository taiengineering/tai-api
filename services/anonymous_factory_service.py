"""Anonymous / consumer diagnosis via Compiler Core (temp factory lifecycle).

Phase 2: replaces runtime_metadata_resolution path for consumer step1.
Creates a short-lived factories row, on-demand facility_applicability evaluation,
fetches compiler candidates, converts to legacy step1 JSON, then cleans up.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from schemas.legal_engine import DiagnoseStep1Body
from services.compiler_core_svc import COMPILER_VERSION, fetch_compiler_candidates
from services.facility_applicability_eval import evaluate_draft_for_facility
from services.input_normalizer import normalize_input
from services.legal_context import _input_to_facility_context
from services.legal_helpers import get_sector_groups
from services.diagnosis_helpers import SOURCE_DIAGNOSIS
from services.legal_rules import get_construction_summary, normalize_sector_db, risk_level
from constants.sectors import to_mapping_sector

log = logging.getLogger(__name__)

ANONYMOUS_COMPILER_ENGINE_VERSION = "v3.0-compiler-core-anonymous"
RULE_VERSION_COMPILER = "compiler_core:facility_applicability:v1"

_DRAFT_PAGE = 1000
_INSERT_CHUNK = 200
_PERSIST_STATUSES = frozenset({"MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"})

# ─────────────────────────────────────────────────────────────────────────────
# 입구(sector) 표준 매핑
#
# 중요: MANUFACTURING은 엔진 내부(입구~제일 뒤)가 일관되게 쓰는 내부 표준 용어다.
#   입력 표준(법령분류·law_sector_mapping·factories.sector)은 INDUSTRIAL을 쓰고,
#   엔진에 넣을 때 입구에서 INDUSTRIAL→MANUFACTURING으로 변환한다.
#   따라서 law_sector_mapping과 대조할 때는 "변환 전 입력 표준값"으로 되돌려서
#   매칭해야 한다.
#
#   sector 변환 표준은 이 파일에서 따로 정의하지 않는다. 표준 정의처
#   constants.sectors.to_mapping_sector 를 그대로 인용한다(단일 원천).
#   검증 하니스(diagnosis_factory_test)도 같은 함수를 인용하여 동일 기준으로 대조한다.
#   to_mapping_sector 내부는 normalize_sector_db(MANUFACTURING/INDUSTRY→INDUSTRIAL,
#   SPECIAL→SPECIAL_FACILITY)를 사용. 문제가 생길 때마다 이 환원 규칙을 여기서
#   바꾸지 말 것 — 표준을 고쳐야 하면 constants.sectors 한 곳만 고친다.
#
# law_sector_mapping.sectors 표준값: BUILDING / INDUSTRIAL / CONSTRUCTION / SPECIAL_FACILITY
# factories.sector 표준값:           BUILDING / INDUSTRIAL / CONSTRUCTION / SPECIAL_FACILITY / COMMON
# ─────────────────────────────────────────────────────────────────────────────


def _mapping_sector_key(sector_value: str) -> str:
    """factory/엔진 sector 값을 law_sector_mapping.sectors 표준 키로 환원.

    표준 정의처(constants.sectors.to_mapping_sector)를 인용한다. 여기서 별도 규칙을
    만들지 않는다. 검증 하니스와 동일한 한 함수를 봄으로써 입구·검증이 항상 같은
    기준으로 동작한다.
    """
    return to_mapping_sector(sector_value or "")

_TASK_TYPE_TO_BUCKET: Dict[str, Tuple[str, str]] = {
    "APPOINTMENT": ("appointment", "선임"),
    "DESIGNATE": ("appointment", "선임"),
    "REPORT": ("report", "신고"),
    "NOTIFY": ("notify", "보고"),
    "SUBMIT": ("report", "신고"),
    "INSPECTION": ("inspection", "점검"),
    "INSPECT": ("inspection", "점검"),
    "MEASURE": ("inspection", "점검"),
    "INSTALL": ("action", "조치"),
    "MAINTAIN": ("action", "조치"),
    "EDUCATION": ("action", "조치"),
    "RECORD": ("action", "조치"),
    "PRESERVATION": ("action", "조치"),
}

# bucket → obligation_type (결과페이지/작업할당 분류 기준).
# _bucket_for_task_type가 이미 task_type을 bucket으로 정확히 분류하므로,
# obligation_type은 그 bucket에서 직접 도출한다(추측·재판정 없음).
_BUCKET_TO_OBLIGATION: Dict[str, str] = {
    "appointment": "APPOINT",
    "inspection": "INSPECT",
    "report": "REPORT",
    "notify": "NOTIFY",
    "action": "ACTION",
}

_ACTION_TO_TASK: Dict[str, str] = {
    "INSPECT_FAMILY": "INSPECTION_TASK_CANDIDATE",
    "REPORT_FAMILY": "REPORT_TASK_CANDIDATE",
    "TRAINING_FAMILY": "TRAINING_TASK_CANDIDATE",
    "APPOINT_FAMILY": "APPOINTMENT_TASK_CANDIDATE",
    "RECORD_FAMILY": "RECORD_TASK_CANDIDATE",
    "PRESERVE_FAMILY": "PRESERVE_TASK_CANDIDATE",
    "INSTALL_FAMILY": "INSTALL_TASK_CANDIDATE",
    "MANAGE_FAMILY": "MANAGE_TASK_CANDIDATE",
    "NOTIFY_FAMILY": "NOTIFY_TASK_CANDIDATE",
    "MEASURE_FAMILY": "MEASURE_TASK_CANDIDATE",
    "VERIFY_FAMILY": "VERIFY_TASK_CANDIDATE",
    "DESIGNATE_FAMILY": "DESIGNATE_TASK_CANDIDATE",
    "EXECUTE_FAMILY": "EXECUTE_TASK_CANDIDATE",
    "PUBLISH_FAMILY": "PUBLISH_TASK_CANDIDATE",
    "CONSULT_FAMILY": "CONSULT_TASK_CANDIDATE",
    "PROVIDE_FAMILY": "PROVIDE_TASK_CANDIDATE",
    "REPAIR_FAMILY": "REPAIR_TASK_CANDIDATE",
    "REPLACE_FAMILY": "REPLACE_TASK_CANDIDATE",
    "CANCEL_FAMILY": "CANCEL_TASK_CANDIDATE",
    "CORRECT_FAMILY": "CORRECT_TASK_CANDIDATE",
    "PREVENT_FAMILY": "PREVENT_TASK_CANDIDATE",
    "PROCESS_FAMILY": "PROCESS_TASK_CANDIDATE",
    "REQUEST_FAMILY": "REQUEST_TASK_CANDIDATE",
}

_OBLIGATION_FAMILIES = frozenset(
    {
        "MANDATORY_FAMILY",
        "PERMISSIVE_FAMILY",
        "MANDATORY_ITEM_FAMILY",
        "PROHIBITION_FAMILY",
    }
)


def _is_token_text(value: Any) -> bool:
    """사람이 읽는 문장이 아니라 내부 코드 토큰이면 True.

    예: "APPOINTMENT_TASK_CANDIDATE: APPOINT_FAMILY", "INSPECT_FAMILY".
    """
    s = (value or "").strip() if isinstance(value, str) else str(value or "").strip()
    if not s:
        return True
    u = s.upper()
    if "TASK_CANDIDATE" in u or "_FAMILY" in u:
        return True
    return False


def _obligation_summary_text(
    *,
    description: str,
    law_name: str,
    law_article: str,
    fallback: str,
) -> str:
    """의무 요약: 사람이 읽는 텍스트 우선, 코드 토큰은 배제.

    1) description(법조문 제목 등)이 토큰이 아니면 사용
    2) 아니면 "법령명 조문" 조합
    3) 아니면 fallback
    """
    desc = (description or "").strip()
    if desc and not _is_token_text(desc):
        return desc
    law_bit = " ".join(p for p in ((law_name or "").strip(), (law_article or "").strip()) if p).strip()
    if law_bit and not _is_token_text(law_bit):
        return law_bit
    fb = (fallback or "").strip()
    if fb and not _is_token_text(fb):
        return fb
    return "의무사항"


def _bucket_for_task_type(task_type: str) -> Tuple[str, str]:
    tt = (task_type or "ACTION").upper()
    if tt in _TASK_TYPE_TO_BUCKET:
        return _TASK_TYPE_TO_BUCKET[tt]
    for prefix, bucket in _TASK_TYPE_TO_BUCKET.items():
        if tt.startswith(prefix):
            return bucket
    return ("action", "조치")


def _merge_body_input(body: DiagnoseStep1Body) -> Dict[str, Any]:
    inp = dict(body.input or {})
    for k, v in {
        "building_use_type": body.building_use_type,
        "employee_count": body.employee_count,
        "floor_area": body.floor_area,
        "worker_count": body.worker_count,
        "total_floor_area": body.total_floor_area,
        "electric_capacity": body.electric_capacity,
        "floor_count": body.floor_count,
        "contract_amount_eok": body.contract_amount_eok,
        "ksic_major": body.ksic_major,
        "facility_type": body.facility_type,
        "elevator_count": body.elevator_count,
        "gas_capacity_kg": body.gas_capacity_kg,
        "gas_capacity_m3": body.gas_capacity_m3,
        "boiler_capacity_kw": body.boiler_capacity_kw,
        "annual_energy_toe": body.annual_energy_toe,
        "has_high_pressure_gas": body.has_high_pressure_gas,
        "has_boiler": body.has_boiler,
        "has_hazardous_material": body.has_hazardous_material,
        "has_chemical_substance": body.has_chemical_substance,
        "construction_type": body.construction_type,
        "direct_workers": body.direct_workers,
        "subcon_workers": body.subcon_workers,
        "electrical_capacity_kw": body.electrical_capacity_kw,
        "has_tunnel_bridge": body.has_tunnel_bridge,
        "has_blasting": body.has_blasting,
        "has_crane": body.has_crane,
        "has_high_work": body.has_high_work,
    }.items():
        if v is not None and k not in inp:
            inp[k] = v
    return inp


def normalize_consumer_inp(body: DiagnoseStep1Body) -> Dict[str, Any]:
    """
    Consumer path: merge body fields → normalize_input → legal_context-ready dict.

    Defends legal_context float() parsing from unit strings (e.g. 800kVA, 78억).
    """
    base = _merge_body_input(body)
    sector = body.sector.strip().upper()
    norm = normalize_input({**base, "sector": sector})
    merged = {**base, **norm}
    if sector == "CONSTRUCTION":
        won = norm.get("contract_amount") or norm.get("construction_amount")
        if won is not None:
            merged["contract_amount_eok"] = float(won) / 100_000_000.0
    return merged


def prepare_step1_body_for_compiler(body: DiagnoseStep1Body) -> DiagnoseStep1Body:
    """Persist normalized values into body.input before compiler step1."""
    norm = normalize_consumer_inp(body)
    payload_input = dict(body.input or {})
    for key, val in norm.items():
        if key == "sector":
            continue
        payload_input[key] = val
    return body.model_copy(update={"input": payload_input})


def _resolve_site_type(sector_raw: str, inp: Dict[str, Any], ctx: Dict[str, Any]) -> str:
    """Layer 1→2: site_type = facility/building use (not sector enum)."""
    use = str(
        inp.get("building_use_type")
        or inp.get("facility_type")
        or ctx.get("building_use_code")
        or ""
    ).strip()
    if use:
        return use
    if sector_raw == "CONSTRUCTION":
        return str(ctx.get("construction_type") or "").strip()
    if sector_raw == "MANUFACTURING":
        return str(ctx.get("ksic_code") or "").strip()
    return ""


def create_temp_factory(supabase, body: DiagnoseStep1Body) -> str:
    """Consumer input → short-lived factories row (is_active=false)."""
    sector_raw = body.sector.strip().upper()
    inp = normalize_consumer_inp(body)
    ctx = _input_to_facility_context(sector_raw, inp)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    building_use_code = str(
        inp.get("building_use_type") or inp.get("facility_type") or ctx.get("building_use_code") or ""
    ).strip()
    site_type = _resolve_site_type(sector_raw, inp, ctx)
    sector_db = normalize_sector_db(sector_raw)
    row: Dict[str, Any] = {
        "name": f"[ANON]{sector_raw}-{ts}"[:200],
        "sector": sector_db,
        "site_type": site_type or None,
        "is_active": False,
        "status_code": "ANON_TEMP",
        "employee_count": int(ctx.get("worker_count") or ctx.get("employee_count") or 0),
        "building_area": float(ctx.get("building_area") or ctx.get("total_floor_area") or 0),
        "electrical_capacity_kw": float(
            ctx.get("electrical_capacity_kw") or ctx.get("electric_capacity") or 0
        ),
        "transformer_capacity_kva": float(ctx.get("transformer_capacity_kva") or 0),
        "gas_capacity_kg": float(ctx.get("gas_capacity_kg") or 0),
        "construction_amount": float(ctx.get("construction_amount") or 0),
        "subcontractor_worker_count": int(
            ctx.get("subcontractor_worker_count") or ctx.get("subcon_workers") or 0
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    ksic = str(ctx.get("ksic_code") or "").strip()
    if ksic:
        row["ksic_code"] = ksic
    construction_type = str(ctx.get("construction_type") or "").strip()
    if construction_type:
        row["construction_type"] = construction_type
    if building_use_code:
        row["building_use_code"] = building_use_code
    floor_count = int(ctx.get("floor_count") or 0)
    if floor_count > 0:
        row["floor_count"] = floor_count
    gas_m3 = float(ctx.get("gas_capacity_m3") or 0)
    if gas_m3 > 0:
        row["gas_capacity_m3"] = gas_m3
    boiler_kw = float(ctx.get("boiler_capacity_kw") or 0)
    if boiler_kw > 0:
        row["boiler_capacity_kw"] = boiler_kw
    elevator_count = int(ctx.get("elevator_count") or 0)
    if elevator_count > 0:
        row["elevator_count"] = elevator_count
    annual_toe = float(ctx.get("annual_energy_toe") or 0)
    if annual_toe > 0:
        row["annual_energy_toe"] = annual_toe
    is_haz = ctx.get("is_hazardous_material")
    if is_haz is not None:
        row["is_hazardous_material"] = bool(is_haz)
    res = supabase.table("factories").insert(row).execute()
    if not res.data:
        raise RuntimeError("임시 시설(factories) 생성 실패")
    return str(res.data[0]["id"])


def _load_sector_allowed_draft_ids(supabase, sector_value: str) -> Optional[Set[str]]:
    """입구 sector 필터: 이 sector에 적용되는 draft_id 집합을 반환.

    법령분류 표준(law_sector_mapping)을 '그대로 읽어서' 거른다. 표준을 새로 만들지
    않는다. 연결: executable_draft → law_article → law_master ← law_sector_mapping.

    통과 규칙(사장님 확정):
      - 해당 sector가 law_sector_mapping.sectors에 포함된 draft  → 통과
      - law_sector_mapping에 매핑이 아예 없는 법령의 draft        → 통과(가지고 감)
        (미매핑은 나중에 매핑을 채운 뒤 제외 예정. 지금 빼면 의무 누락 위험)
      - 다른 sector 전용으로 명시된 법령(예: 의료법=SPECIAL_FACILITY)의 draft → 제외

    Returns:
      허용 draft_id 집합. 매핑 데이터가 없거나 조회 실패 시 None을 돌려주어
      호출부가 '필터 미적용(전체 평가)'로 안전하게 폴백하도록 한다.
    """
    key = _mapping_sector_key(sector_value)
    if not key:
        return None

    # 1) executable_draft → article_id
    draft_article: Dict[str, str] = {}
    article_ids: Set[str] = set()
    offset = 0
    while True:
        try:
            res = (
                supabase.table("executable_draft")
                .select("id, article_id")
                .not_.is_("article_id", "null")
                .range(offset, offset + _DRAFT_PAGE - 1)
                .execute()
            )
        except Exception as exc:
            log.warning("sector-filter executable_draft fetch failed: %s", exc)
            return None
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            did = str(row.get("id") or "")
            aid = str(row.get("article_id") or "")
            if did and aid:
                draft_article[did] = aid
                article_ids.add(aid)
        if len(chunk) < _DRAFT_PAGE:
            break
        offset += _DRAFT_PAGE

    if not draft_article:
        return None

    # 2) law_article → law_id
    article_law: Dict[str, str] = {}
    law_ids: Set[str] = set()
    aid_list = list(article_ids)
    for i in range(0, len(aid_list), _INSERT_CHUNK):
        chunk = aid_list[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("law_article")
                .select("id, law_id")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("sector-filter law_article fetch failed: %s", exc)
            return None
        for row in res.data or []:
            aid = str(row.get("id") or "")
            lid = str(row.get("law_id") or "")
            if aid and lid:
                article_law[aid] = lid
                law_ids.add(lid)

    # 3) law_sector_mapping: law_id → sectors[]  (매핑된 법령만 존재)
    law_sectors: Dict[str, List[str]] = {}
    lid_list = list(law_ids)
    for i in range(0, len(lid_list), _INSERT_CHUNK):
        chunk = lid_list[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("law_sector_mapping")
                .select("law_id, sectors")
                .in_("law_id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("sector-filter law_sector_mapping fetch failed: %s", exc)
            return None
        for row in res.data or []:
            lid = str(row.get("law_id") or "")
            secs = row.get("sectors") or []
            if lid:
                law_sectors[lid] = [str(s).strip().upper() for s in secs if s]

    if not law_sectors:
        # 매핑 테이블이 비었거나 연결 실패 → 필터 미적용(전체 평가) 폴백
        return None

    # 4) draft별 통과 판정
    allowed: Set[str] = set()
    for did, aid in draft_article.items():
        lid = article_law.get(aid)
        if not lid:
            # 법령 연결이 끊긴 draft는 보수적으로 통과(누락 방지)
            allowed.add(did)
            continue
        secs = law_sectors.get(lid)
        if secs is None:
            # 미매핑 법령 → 가지고 감(나중에 제외)
            allowed.add(did)
        elif key in secs:
            # 해당 sector에 적용되는 법령 → 통과
            allowed.add(did)
        # else: 다른 sector 전용 → 제외
    return allowed


def _load_draft_slot_groups(
    supabase,
    allowed_draft_ids: Optional[Set[str]] = None,
) -> Tuple[Dict[str, List[Dict]], Dict[str, List[Dict]]]:
    """Paginate draft_slot → numeric / scope groups keyed by draft_id.

    allowed_draft_ids가 주어지면 그 집합에 속한 draft만 적재한다(입구 sector 필터).
    None이면 종전대로 전체 적재(폴백).
    """
    numerics: Dict[str, List[Dict[str, Any]]] = {}
    scopes: Dict[str, List[Dict[str, Any]]] = {}
    offset = 0
    while True:
        res = (
            supabase.table("draft_slot")
            .select("draft_id, part_id, section, binding_field, operator, value, unit, family_name")
            .not_.is_("binding_field", "null")
            .in_("section", ["IF_NUMERIC", "IF_SCOPE"])
            .range(offset, offset + _DRAFT_PAGE - 1)
            .execute()
        )
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            draft_id = str(row.get("draft_id") or "")
            if not draft_id:
                continue
            if allowed_draft_ids is not None and draft_id not in allowed_draft_ids:
                continue
            section = (row.get("section") or "").upper()
            if section == "IF_NUMERIC":
                if not row.get("operator") or row.get("value") is None:
                    continue
                numerics.setdefault(draft_id, []).append(
                    {
                        "part_id": str(row.get("part_id") or ""),
                        "binding_field": row.get("binding_field"),
                        "operator": row.get("operator"),
                        "value": row.get("value"),
                        "unit": row.get("unit"),
                        "family": row.get("family_name"),
                    }
                )
            elif section == "IF_SCOPE":
                scopes.setdefault(draft_id, []).append(
                    {
                        "part_id": str(row.get("part_id") or ""),
                        "binding_field": row.get("binding_field"),
                        "family": row.get("family_name"),
                    }
                )
        if len(chunk) < _DRAFT_PAGE:
            break
        offset += _DRAFT_PAGE
    return numerics, scopes


def evaluate_single_factory(supabase, factory_id: str) -> Dict[str, int]:
    """
    On-demand facility_applicability for one factory (Compiler Core materialize).

    Uses facility_applicability_eval pure logic; persists MATCH/POSSIBLE rows only.

    입구 sector 필터: factory.sector(입력 표준값)를 기준으로 law_sector_mapping에
    맞는 draft만 평가 대상으로 적재한다. 타 sector 전용 법령(예: 제조업 진단에
    들어오던 의료법·특수교육법=SPECIAL_FACILITY)은 평가 진입 전에 분리된다.
    판정 로직(evaluate_draft_for_facility) 자체는 변경하지 않는다.
    """
    fac_res = supabase.table("factories").select("*").eq("id", factory_id).limit(1).execute()
    if not fac_res.data:
        raise LookupError(f"factory not found: {factory_id}")
    facility = fac_res.data[0]

    # 입구에서 sector 표준값으로 허용 draft 집합 산출(법령분류 표준을 그대로 읽음).
    sector_value = str(facility.get("sector") or "").strip()
    allowed_draft_ids = _load_sector_allowed_draft_ids(supabase, sector_value)

    numerics, scopes = _load_draft_slot_groups(supabase, allowed_draft_ids)
    all_draft_ids = set(numerics.keys()) | set(scopes.keys())

    rows: List[Dict[str, Any]] = []
    for draft_id in all_draft_ids:
        evaluated = evaluate_draft_for_facility(
            facility,
            draft_id,
            numerics.get(draft_id, []),
            scopes.get(draft_id, []),
        )
        if not evaluated:
            continue
        overall, part_id, check_results = evaluated
        if overall not in _PERSIST_STATUSES:
            continue
        rows.append(
            {
                "factory_id": factory_id,
                "draft_id": draft_id,
                "part_id": part_id,
                "applicability_status": overall,
                "match_details": {"checks": len(check_results)},
            }
        )

    inserted = 0
    for i in range(0, len(rows), _INSERT_CHUNK):
        batch = rows[i : i + _INSERT_CHUNK]
        if not batch:
            continue
        supabase.table("facility_applicability").insert(batch).execute()
        inserted += len(batch)

    return {
        "drafts_evaluated": len(all_draft_ids),
        "applicability_inserted": inserted,
        "sector_filtered": allowed_draft_ids is not None,
    }


def cleanup_temp_factory(supabase, factory_id: str) -> None:
    """Remove temp applicability rows and factories record."""
    fid = (factory_id or "").strip()
    if not fid:
        return
    try:
        supabase.table("facility_applicability").delete().eq("factory_id", fid).execute()
    except Exception as exc:
        log.warning("facility_applicability cleanup failed factory_id=%s: %s", fid, exc)
    try:
        supabase.table("factories").delete().eq("id", fid).execute()
    except Exception as exc:
        log.warning("factories cleanup failed factory_id=%s: %s", fid, exc)


def _load_draft_fallback_context(
    supabase,
    draft_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Batch-read executable_draft, law_master, draft_slot for fallback rule rows."""
    unique = [
        d
        for d in dict.fromkeys(str(x).strip() for x in draft_ids if x and str(x).strip())
    ]
    if not unique or supabase is None:
        return {}

    ctx: Dict[str, Dict[str, Any]] = {d: {} for d in unique}
    articles_by_draft: Dict[str, str] = {}

    for i in range(0, len(unique), _INSERT_CHUNK):
        chunk = unique[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("executable_draft")
                .select("id, article_id, rule_candidate_id, part_id")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("executable_draft batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            did = str(row.get("id") or "")
            if not did:
                continue
            ctx[did]["article_id"] = row.get("article_id")
            ctx[did]["rule_candidate_id"] = row.get("rule_candidate_id")
            ctx[did]["part_id"] = row.get("part_id")
            if row.get("article_id"):
                articles_by_draft[did] = str(row["article_id"])

    article_meta: Dict[str, Dict[str, Any]] = {}
    article_ids = list(dict.fromkeys(articles_by_draft.values()))
    for i in range(0, len(article_ids), _INSERT_CHUNK):
        chunk = article_ids[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("law_article")
                .select("id, law_id, article_no, article_title")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("law_article batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            article_meta[str(row["id"])] = row

    law_ids = list(
        dict.fromkeys(str(r.get("law_id")) for r in article_meta.values() if r.get("law_id"))
    )
    law_names: Dict[str, str] = {}
    for i in range(0, len(law_ids), _INSERT_CHUNK):
        chunk = law_ids[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("law_master")
                .select("id, law_name")
                .in_("id", chunk)
                .execute()
            )
        except Exception as exc:
            log.warning("law_master batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            law_names[str(row["id"])] = (row.get("law_name") or "").strip()

    for did, aid in articles_by_draft.items():
        am = article_meta.get(aid) or {}
        law_name = law_names.get(str(am.get("law_id") or ""), "")
        art_no = am.get("article_no") or ""
        art_title = (am.get("article_title") or "").strip()
        ctx[did]["law_name"] = law_name
        ctx[did]["law_article"] = str(art_no) if art_no else ""
        # description = 법조문 제목(사람이 읽는 텍스트). THEN_ACTION raw_token으로 덮지 않는다.
        ctx[did]["description"] = art_title or law_name

    slots_by_draft: Dict[str, List[Dict[str, Any]]] = {}
    for i in range(0, len(unique), _INSERT_CHUNK):
        chunk = unique[i : i + _INSERT_CHUNK]
        try:
            res = (
                supabase.table("draft_slot")
                .select("draft_id, section, family_name, raw_token")
                .in_("draft_id", chunk)
                .eq("section", "THEN_ACTION")
                .execute()
            )
        except Exception as exc:
            log.warning("draft_slot batch fetch failed: %s", exc)
            continue
        for row in res.data or []:
            did = str(row.get("draft_id") or "")
            if did:
                slots_by_draft.setdefault(did, []).append(row)

    for did, slots in slots_by_draft.items():
        obligation = ""
        for slot in slots:
            fam = slot.get("family_name") or ""
            if fam in _OBLIGATION_FAMILIES:
                obligation = fam
        for slot in slots:
            fam = slot.get("family_name") or ""
            if fam not in _ACTION_TO_TASK:
                continue
            ctx[did]["task_type"] = _ACTION_TO_TASK[fam]
            ctx[did]["source_action_family"] = fam
            # raw_token은 코드 토큰이므로 description을 덮지 않고 별도 보관.
            token = (slot.get("raw_token") or "").strip()
            if token:
                ctx[did]["then_action_token"] = token
            break
        ctx[did]["obligation_family"] = obligation

    return ctx


def _rule_row_flags(bucket: str) -> Dict[str, bool]:
    return {
        "appointment_required": bucket == "appointment",
        "inspection_required": bucket == "inspection",
        "action_required": bucket == "action",
        "report_required": bucket == "report",
        "notify_required": bucket == "notify",
    }


def _task_to_rule_row(task: Dict[str, Any], sector_raw: str) -> Dict[str, Any]:
    task_type = (task.get("task_type") or "ACTION").upper()
    bucket, cat_label = _bucket_for_task_type(task_type)
    fam = (task.get("obligation_family") or "").strip()
    source_fam = (task.get("source_action_family") or "").strip()
    desc = (task.get("description") or "").strip()
    # obligation_type은 bucket에서 직접 도출(task_type 토큰 매칭 실패 → ACTION 강등 버그 제거).
    obl_type = _BUCKET_TO_OBLIGATION.get(bucket, "ACTION")
    law_name = fam or "Compiler Candidate"
    summary = _obligation_summary_text(
        description=desc,
        law_name=law_name,
        law_article="",
        fallback=fam,
    )
    token = f"{task.get('task_type', '')}: {task.get('source_action_family', '')}".strip(": ")
    return {
        "rule_id": str(task.get("id") or ""),
        "rule_type": task_type,
        "law_name": law_name,
        "law_article": "",
        "obligation_summary": summary,
        "remarks": desc if (desc and not _is_token_text(desc)) else "",
        "description": summary,
        "category": cat_label,
        "obligation_type": obl_type,
        "source_action_family": source_fam,
        "then_action_token": token,
        "sector": sector_raw,
        "diagnosis_stage": 1,
        "schedule_type": "ON_DEMAND",
        "penalty_summary": "",
        "source": SOURCE_DIAGNOSIS,
        **_rule_row_flags(bucket),
        "_bucket": bucket,
    }


def _applicability_to_rule_row(
    applicability: Dict[str, Any],
    sector_raw: str,
    draft_ctx: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    draft_id = str(applicability.get("draft_id") or "")
    meta = draft_ctx.get(draft_id) or {}
    task_type = (meta.get("task_type") or "ACTION").upper()
    bucket, cat_label = _bucket_for_task_type(task_type)
    source_fam = (meta.get("source_action_family") or "").strip()
    fam = (meta.get("obligation_family") or "").strip()
    law_name = (meta.get("law_name") or "").strip() or fam or "Compiler Candidate"
    law_article = meta.get("law_article") or ""
    desc = (meta.get("description") or "").strip()
    token = (meta.get("then_action_token") or "").strip()
    # obligation_type은 bucket에서 직접 도출(task_type 토큰 매칭 실패 → ACTION 강등 버그 제거).
    obl_type = _BUCKET_TO_OBLIGATION.get(bucket, "ACTION")
    # 요약은 법조문 제목(description) 우선. source_fam 토큰을 제목으로 쓰지 않는다.
    summary = _obligation_summary_text(
        description=desc,
        law_name=law_name,
        law_article=law_article,
        fallback=fam,
    )
    return {
        "rule_id": str(applicability.get("id") or draft_id),
        "rule_type": task_type,
        "law_name": law_name,
        "law_article": law_article,
        "obligation_summary": summary,
        "remarks": desc if (desc and not _is_token_text(desc)) else "",
        "description": summary,
        "category": cat_label,
        "obligation_type": obl_type,
        "source_action_family": source_fam,
        "then_action_token": token,
        "sector": sector_raw,
        "diagnosis_stage": 1,
        "schedule_type": "ON_DEMAND",
        "penalty_summary": "",
        "source": SOURCE_DIAGNOSIS,
        **_rule_row_flags(bucket),
        "_bucket": bucket,
    }


def _compiler_result_to_step1_format(
    compiler: Dict[str, Any],
    *,
    sector_raw: str,
    facility_ctx: Dict[str, Any],
    evaluated_at: str,
    supabase=None,
) -> Dict[str, Any]:
    """Compiler Core / DiagnosisService-shaped dict → legacy step1 result_data."""
    sector_db = normalize_sector_db(sector_raw)
    sector_groups = get_sector_groups(sector_db)
    tasks = compiler.get("task_candidates") or []
    applicability = compiler.get("applicability_candidates") or []

    rules_from_tasks = [_task_to_rule_row(t, sector_raw) for t in tasks]
    if not rules_from_tasks and applicability:
        draft_ids = [str(a.get("draft_id") or "") for a in applicability]
        draft_ctx = _load_draft_fallback_context(supabase, draft_ids)
        rules_from_tasks = [
            _applicability_to_rule_row(a, sector_raw, draft_ctx) for a in applicability
        ]

    triggered: Dict[str, List] = {
        "appointment": [],
        "inspection": [],
        "notify": [],
        "report": [],
        "action": [],
        "not_applicable": [],
    }
    for row in rules_from_tasks:
        bucket = row.pop("_bucket", "action")
        triggered[bucket].append(row)

    rules_table: List[Dict[str, Any]] = []
    for key, label in [
        ("appointment", "선임"),
        ("inspection", "점검"),
        ("action", "조치"),
        ("report", "신고"),
        ("notify", "보고"),
    ]:
        for row in triggered[key]:
            rules_table.append({"category": label, **row})

    total_applicable = sum(len(triggered[k]) for k in ("appointment", "inspection", "notify", "report", "action"))
    law_names = sorted({x.get("law_name") for x in rules_from_tasks if x.get("law_name")})
    appointment_n = len(triggered["appointment"])
    risk = risk_level(total_applicable, appointment_n)

    key_obligations: List[Dict[str, Any]] = []
    seen_key_titles: set[str] = set()
    for x in rules_from_tasks[:20]:
        t = (x.get("obligation_summary") or x.get("remarks") or "").strip()
        if t and t not in seen_key_titles:
            seen_key_titles.add(t)
            key_obligations.append(
                {
                    "title": t,
                    "law_name": (x.get("law_name") or "").strip(),
                    "rule_type": (x.get("rule_type") or "").strip(),
                    "source": SOURCE_DIAGNOSIS,
                }
            )

    obligations: List[Dict[str, Any]] = []
    for key, label in [("appointment", "선임"), ("inspection", "점검"), ("action", "조치")]:
        if triggered[key]:
            obligations.append({"category": key, "label": label, "items": triggered[key]})
    if triggered["report"]:
        obligations.append({"category": "report", "label": "신고", "items": triggered["report"]})
    if triggered["notify"]:
        obligations.append({"category": "notify", "label": "보고", "items": triggered["notify"]})

    risk_reason = f"적용 법령 {len(law_names)}개, 법적 의무 {total_applicable}건 (Compiler Core Candidate)"

    result: Dict[str, Any] = {
        "sector": sector_raw,
        "sector_groups": sector_groups,
        "step": 1,
        "engine_version": ANONYMOUS_COMPILER_ENGINE_VERSION,
        "rule_version": RULE_VERSION_COMPILER,
        "evaluated_at": evaluated_at,
        "facility_context": facility_ctx,
        "risk_level": risk,
        "risk_reason": risk_reason,
        "applicable_law_categories": law_names,
        "appointment_required_flag": appointment_n > 0,
        "key_obligations": key_obligations,
        "law_badges": law_names,
        "obligations": obligations,
        "rules_table": rules_table,
        "rules": rules_table,
        "appointment_required": triggered["appointment"],
        "inspection_required": triggered["inspection"],
        "action_required": triggered["action"],
        "report_required": triggered["report"] + triggered["notify"],
        "not_applicable": [],
        "not_applicable_total": 0,
        "total_rules_checked": total_applicable + len(applicability),
        "applicable_count": total_applicable,
        "article_mapping_stats": {
            "total_rules": total_applicable,
            "mapped_rules": 0,
            "coverage_pct": 0.0,
        },
        "inspection_schedule_ready": {
            "periodic_count": 0,
            "before_work_count": 0,
            "on_demand_count": len(triggered["inspection"]),
            "periodic": [],
            "before_work": [],
        },
        "summary": {
            "total": total_applicable,
            "appointment": len(triggered["appointment"]),
            "inspection": len(triggered["inspection"]),
            "action": len(triggered["action"]),
            "report": len(triggered["report"]),
            "notify": len(triggered["notify"]),
            "form_linked": 0,
        },
        "compiler_core": {
            "compiler_version": compiler.get("compiler_version") or COMPILER_VERSION,
            "warning": compiler.get("warning"),
            "applicability_count": len(applicability),
            "task_count": len(tasks),
            "schedule_count": len(compiler.get("schedule_candidates") or []),
            "applicability_candidates": applicability,
            "task_candidates": tasks,
            "schedule_candidates": compiler.get("schedule_candidates") or [],
        },
    }
    if sector_raw == "CONSTRUCTION":
        result["construction_summary"] = get_construction_summary(facility_ctx)
    return result


def run_anonymous_diagnosis(
    supabase,
    body: DiagnoseStep1Body,
    allowed_sectors: FrozenSet[str],
) -> Dict[str, Any]:
    """Full orchestration: temp factory → evaluate → fetch → format → cleanup."""
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError(
            "sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다."
        )

    inp = normalize_consumer_inp(body)
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = datetime.now(timezone.utc).isoformat()

    factory_id: Optional[str] = None
    try:
        factory_id = create_temp_factory(supabase, body)
        evaluate_single_factory(supabase, factory_id)
        compiler = fetch_compiler_candidates(supabase, factory_id)
        return _compiler_result_to_step1_format(
            compiler,
            sector_raw=sector_raw,
            facility_ctx=facility_ctx,
            evaluated_at=evaluated_at,
            supabase=supabase,
        )
    finally:
        if factory_id:
            cleanup_temp_factory(supabase, factory_id)
