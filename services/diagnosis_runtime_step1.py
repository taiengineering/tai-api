"""
Nexas / anonymous diagnosis — Runtime Compiler step1 실행.

legal_engine_svc.run_diagnose_step1(legacy) 대신
runtime_metadata_resolution → v1 projection → build_step1_result_data.

웹 결과 표시 정제(BE-08 dedupe/FAMILY→한글)는
routers/diagnosis_result_web._refine_rules_table() 에서 조회 시 적용.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from schemas.legal_engine import DiagnoseStep1Body
from services.legal_context import _input_to_facility_context
from services.legal_engine_svc import evaluate_facility_conditions_db
from services.legal_rules import get_construction_summary
from services.legal_format import _classify_rules_db, format_rule_result_db
from services.legal_helpers import get_sector_groups
from services.legal_rules import normalize_sector_db, risk_level
from services.legal_runtime_fetch import fetch_runtime_rules_as_v1
from services.legal_step1_builder import build_step1_result_data
from services.rule_candidate_projection import _format_article_no

RUNTIME_ENGINE_VERSION = "v3.0-runtime-compiler"

_SLOT_TYPES_WHO = frozenset({"ACTOR"})
_SLOT_TYPES_WHAT = frozenset({"OBLIGATION", "ACTION"})
_SLOT_TYPES_WHEN = frozenset({"DEADLINE", "FREQUENCY"})
_SLOT_TYPES_QUERY = tuple(_SLOT_TYPES_WHO | _SLOT_TYPES_WHAT | _SLOT_TYPES_WHEN)
_CHUNK = 200


def _article_digits_key(law_name: str, law_article: str) -> Tuple[str, str]:
    law = (law_name or "").strip()
    raw = (law_article or "").strip()
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        formatted = _format_article_no(raw)
        digits = re.sub(r"[^\d]", "", formatted)
    return (law, digits)


def _join_tokens(tokens: List[str]) -> str:
    seen: List[str] = []
    for t in tokens:
        t = (t or "").strip()
        if t and t not in seen:
            seen.append(t)
    return " · ".join(seen)


def _slots_to_triplet(slots: List[Dict[str, Any]]) -> Dict[str, str]:
    who_t: List[str] = []
    what_t: List[str] = []
    when_t: List[str] = []
    families: List[str] = []
    for slot in slots:
        st = (slot.get("slot_type") or "").upper()
        tok = (slot.get("canonical_token") or slot.get("raw_token") or "").strip()
        fam = (slot.get("family_name") or "").strip()
        if not tok:
            continue
        if st in _SLOT_TYPES_WHO:
            who_t.append(tok)
        elif st in _SLOT_TYPES_WHAT:
            what_t.append(tok)
        elif st in _SLOT_TYPES_WHEN:
            when_t.append(tok)
        if fam:
            families.append(fam)
    return {
        "who": _join_tokens(who_t),
        "what": _join_tokens(what_t),
        "when": _join_tokens(when_t),
        "rule_kind": families[0] if families else "",
    }


def _fetch_metadata_triplets(
    supabase, metadata_ids: List[str]
) -> Dict[str, Dict[str, str]]:
    """runtime_metadata_resolution who/when/how 폴백."""
    out: Dict[str, Dict[str, str]] = {}
    clean = [x for x in metadata_ids if x]
    for i in range(0, len(clean), _CHUNK):
        chunk = clean[i : i + _CHUNK]
        res = (
            supabase.table("runtime_metadata_resolution")
            .select("id,who_value,when_value,how_value")
            .in_("id", chunk)
            .execute()
        )
        for row in res.data or []:
            rid = str(row.get("id") or "")
            if not rid:
                continue
            out[rid] = {
                "who": (row.get("who_value") or "").strip(),
                "what": (row.get("how_value") or "").strip(),
                "when": (row.get("when_value") or "").strip(),
                "rule_kind": "",
            }
    return out


def _fetch_rule_candidate_slots(
    supabase, rule_candidate_ids: List[str]
) -> Dict[str, List[Dict[str, Any]]]:
    """rule_candidate_id → slot rows (ACTOR/OBLIGATION/ACTION/DEADLINE/FREQUENCY)."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    clean = list(dict.fromkeys(x for x in rule_candidate_ids if x))
    for i in range(0, len(clean), _CHUNK):
        chunk = clean[i : i + _CHUNK]
        res = (
            supabase.table("rule_candidate_slot")
            .select("rule_candidate_id,slot_type,canonical_token,raw_token,family_name")
            .in_("rule_candidate_id", chunk)
            .in_("slot_type", list(_SLOT_TYPES_QUERY))
            .execute()
        )
        for row in res.data or []:
            rcid = str(row.get("rule_candidate_id") or "")
            if rcid:
                grouped.setdefault(rcid, []).append(row)
    return grouped


def _build_slot_lookup_by_law_article(
    supabase, rules: List[Dict[str, Any]]
) -> Dict[Tuple[str, str], Dict[str, str]]:
    """
    (law_name, article_digits) → {who, what, when, rule_kind}
    rule_candidate JOIN rule_candidate_slot 경로.
    """
    law_names = list({(r.get("law_name") or "").strip() for r in rules if r.get("law_name")})
    if not law_names:
        return {}

    article_id_by_key: Dict[Tuple[str, str], str] = {}
    for law in law_names:
        try:
            res = (
                supabase.table("law_article")
                .select("id,law_name,article_no")
                .eq("law_name", law)
                .limit(500)
                .execute()
            )
        except Exception:
            continue
        for row in res.data or []:
            ln = (row.get("law_name") or "").strip()
            art_no = str(row.get("article_no") or "")
            key = _article_digits_key(ln, art_no)
            if key[0] and key[1] and key not in article_id_by_key:
                article_id_by_key[key] = str(row.get("id") or "")

    if not article_id_by_key:
        return {}

    article_ids = list(dict.fromkeys(article_id_by_key.values()))
    rc_id_by_article: Dict[str, str] = {}
    for i in range(0, len(article_ids), _CHUNK):
        chunk = article_ids[i : i + _CHUNK]
        res = (
            supabase.table("rule_candidate")
            .select("id,article_id")
            .in_("article_id", chunk)
            .execute()
        )
        for row in res.data or []:
            aid = str(row.get("article_id") or "")
            rcid = str(row.get("id") or "")
            if aid and rcid and aid not in rc_id_by_article:
                rc_id_by_article[aid] = rcid

    rc_ids = list(rc_id_by_article.values())
    if not rc_ids:
        return {}

    slots_by_rc = _fetch_rule_candidate_slots(supabase, rc_ids)
    lookup: Dict[Tuple[str, str], Dict[str, str]] = {}
    for key, aid in article_id_by_key.items():
        rcid = rc_id_by_article.get(aid)
        if not rcid:
            continue
        triplet = _slots_to_triplet(slots_by_rc.get(rcid, []))
        if triplet.get("who") or triplet.get("what") or triplet.get("when"):
            lookup[key] = triplet
    return lookup


def _merge_triplet(
    slot_triplet: Optional[Dict[str, str]],
    meta_triplet: Optional[Dict[str, str]],
) -> Dict[str, str]:
    slot_triplet = slot_triplet or {}
    meta_triplet = meta_triplet or {}
    return {
        "who": slot_triplet.get("who") or meta_triplet.get("who") or "",
        "what": slot_triplet.get("what") or meta_triplet.get("what") or "",
        "when": slot_triplet.get("when") or meta_triplet.get("when") or "",
        "rule_kind": slot_triplet.get("rule_kind") or meta_triplet.get("rule_kind") or "",
    }


def _apply_who_what_when(
    row: Dict[str, Any],
    slot_lookup: Dict[Tuple[str, str], Dict[str, str]],
    meta_by_id: Dict[str, Dict[str, str]],
) -> None:
    key = _article_digits_key(row.get("law_name") or "", row.get("law_article") or "")
    meta = meta_by_id.get(str(row.get("rule_id") or ""))
    triplet = _merge_triplet(slot_lookup.get(key), meta)
    row["who"] = triplet["who"]
    row["what"] = triplet["what"]
    row["when"] = triplet["when"]
    if triplet.get("rule_kind"):
        row["rule_kind"] = triplet["rule_kind"]


def _enrich_rules_with_slots(
    supabase,
    rules: List[Dict[str, Any]],
    slot_lookup: Dict[Tuple[str, str], Dict[str, str]],
) -> None:
    meta_ids = [str(r.get("rule_id") or "") for r in rules if r.get("rule_id")]
    meta_by_id = _fetch_metadata_triplets(supabase, meta_ids)
    for row in rules:
        if isinstance(row, dict):
            _apply_who_what_when(row, slot_lookup, meta_by_id)


def _enrich_result_data_slots(
    supabase,
    result_data: Dict[str, Any],
    slot_lookup: Dict[Tuple[str, str], Dict[str, str]],
) -> None:
    """rules_table 및 분류 리스트에 who/what/when 주입."""
    rule_lists = [
        "rules_table",
        "appointment_required",
        "inspection_required",
        "action_required",
        "report_required",
    ]
    rows: List[Dict[str, Any]] = []
    for key in rule_lists:
        items = result_data.get(key) or []
        if isinstance(items, list):
            rows.extend(r for r in items if isinstance(r, dict))
    _enrich_rules_with_slots(supabase, rows, slot_lookup)


def run_diagnose_step1_runtime(
    supabase,
    body: DiagnoseStep1Body,
    allowed_sectors: FrozenSet[str],
) -> Dict[str, Any]:
    """Runtime compiler 기반 step1 — legacy master_building_legal_rules 미사용."""
    sector_raw = body.sector.strip().upper()
    if sector_raw not in allowed_sectors:
        raise ValueError(
            "sector는 BUILDING, MANUFACTURING, CONSTRUCTION, SPECIAL_FACILITY 중 하나여야 합니다."
        )

    sector_db = normalize_sector_db(sector_raw)
    sector_groups = get_sector_groups(sector_db)

    all_rules = fetch_runtime_rules_as_v1(
        supabase,
        sector_db=sector_db,
        factory_id=(body.factory_id or "").strip() or None,
        diagnosis_stage=1,
    )

    inp = dict(body.input or {})
    flat_fields = {
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
    }
    for k, v in flat_fields.items():
        if v is not None and k not in inp:
            inp[k] = v

    facility_ctx = _input_to_facility_context(sector_raw, inp)
    evaluated_at = datetime.now().isoformat()
    applicable, not_applicable = evaluate_facility_conditions_db(
        facility_ctx, all_rules, sector_raw
    )

    slot_lookup = _build_slot_lookup_by_law_article(supabase, applicable)
    _enrich_rules_with_slots(supabase, applicable, slot_lookup)

    result_data = build_step1_result_data(
        sector_raw,
        sector_groups,
        RUNTIME_ENGINE_VERSION,
        evaluated_at,
        facility_ctx,
        applicable,
        not_applicable,
        _classify_rules_db,
        format_rule_result_db,
        risk_level,
        get_construction_summary,
        supabase=supabase,
    )
    result_data["rule_version"] = "runtime_metadata_resolution:v1"
    _enrich_result_data_slots(supabase, result_data, slot_lookup)
    return result_data
