"""
[ISOLATED] Nexas / anonymous diagnosis — Runtime Compiler step1 (Phase 1 legacy path).

Consumer diagnosis (Phase 2) uses services/anonymous_factory_service.run_anonymous_diagnosis
instead of this module. Retained for factory_id-attached enrichment and internal tooling.

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
from services.compiler_core_svc import fetch_compiler_candidates
from services.legal_runtime_fetch import fetch_runtime_rules_as_v1
from services.legal_step1_builder import build_step1_result_data

RUNTIME_ENGINE_VERSION = "v3.0-runtime-compiler"

_ARTICLE_NO_RE = re.compile(r"제(\d+)조")
_SLOT_TYPES_WHO = frozenset({"ACTOR"})
_SLOT_TYPES_WHAT = frozenset({"OBLIGATION", "ACTION", "TARGET"})
_SLOT_TYPES_WHEN = frozenset({"DEADLINE", "FREQUENCY"})
_SLOT_TYPES_QUERY = tuple(_SLOT_TYPES_WHO | _SLOT_TYPES_WHAT | _SLOT_TYPES_WHEN)
_CHUNK = 200


def _parse_article_no(law_article: str) -> Optional[str]:
    """예: '산업안전보건법 제29조)' → '29'."""
    if not law_article:
        return None
    m = _ARTICLE_NO_RE.search(str(law_article))
    if m:
        return m.group(1)
    digits = re.sub(r"[^\d]", "", str(law_article))
    return digits if digits else None


def _slot_lookup_key(law_name: str, law_article: str) -> Optional[Tuple[str, str]]:
    """(law_name, article_no) — law_name은 rules_table 별도 필드."""
    law = (law_name or "").strip()
    art = _parse_article_no(law_article or "")
    if law and art:
        return (law, art)
    return None


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


def _fetch_law_version_ids(
    supabase, law_names: List[str]
) -> Dict[str, str]:
    """law_name → 현행 law_version.id (law_master → law_version)."""
    version_by_law: Dict[str, str] = {}
    for law in law_names:
        try:
            lm = (
                supabase.table("law_master")
                .select("id")
                .eq("law_name", law)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
        except Exception:
            continue
        if not lm.data:
            continue
        law_id = str(lm.data[0].get("id") or "")
        if not law_id:
            continue
        try:
            lv = (
                supabase.table("law_version")
                .select("id")
                .eq("law_id", law_id)
                .eq("is_current", True)
                .limit(1)
                .execute()
            )
        except Exception:
            continue
        if lv.data:
            vid = str(lv.data[0].get("id") or "")
            if vid:
                version_by_law[law] = vid
    return version_by_law


def _build_slot_lookup_by_law_article(
    supabase, rules: List[Dict[str, Any]]
) -> Dict[Tuple[str, str], Dict[str, str]]:
    """
    (law_name, article_no) → {who, what, when, rule_kind}
    law_master → law_version → law_article → rule_candidate → rule_candidate_slot
    """
    keys_needed: Dict[Tuple[str, str], None] = {}
    art_nos_by_law: Dict[str, set[str]] = {}
    for r in rules:
        key = _slot_lookup_key(r.get("law_name") or "", r.get("law_article") or "")
        if not key:
            continue
        keys_needed[key] = None
        art_nos_by_law.setdefault(key[0], set()).add(key[1])

    if not keys_needed:
        return {}

    version_by_law = _fetch_law_version_ids(supabase, list(art_nos_by_law.keys()))
    article_id_by_key: Dict[Tuple[str, str], str] = {}
    for law_name, art_nos in art_nos_by_law.items():
        vid = version_by_law.get(law_name)
        if not vid:
            continue
        art_ints = []
        for a in art_nos:
            try:
                art_ints.append(int(a))
            except ValueError:
                continue
        if not art_ints:
            continue
        for i in range(0, len(art_ints), _CHUNK):
            chunk = art_ints[i : i + _CHUNK]
            try:
                res = (
                    supabase.table("law_article")
                    .select("id,article_no")
                    .eq("law_version_id", vid)
                    .in_("article_no", chunk)
                    .execute()
                )
            except Exception:
                continue
            for row in res.data or []:
                art_no = str(row.get("article_no") or "")
                aid = str(row.get("id") or "")
                key = (law_name, art_no)
                if aid and key in keys_needed and key not in article_id_by_key:
                    article_id_by_key[key] = aid

    if not article_id_by_key:
        return {}

    article_ids = list(dict.fromkeys(article_id_by_key.values()))
    rc_ids_by_article: Dict[str, List[str]] = {}
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
            if aid and rcid:
                rc_ids_by_article.setdefault(aid, []).append(rcid)

    all_rc_ids = list(
        dict.fromkeys(rcid for ids in rc_ids_by_article.values() for rcid in ids)
    )
    if not all_rc_ids:
        return {}

    slots_by_rc = _fetch_rule_candidate_slots(supabase, all_rc_ids)
    lookup: Dict[Tuple[str, str], Dict[str, str]] = {}
    for key, aid in article_id_by_key.items():
        slots: List[Dict[str, Any]] = []
        for rcid in rc_ids_by_article.get(aid, []):
            slots.extend(slots_by_rc.get(rcid, []))
        triplet = _slots_to_triplet(slots)
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
    key = _slot_lookup_key(row.get("law_name") or "", row.get("law_article") or "")
    meta = meta_by_id.get(str(row.get("rule_id") or ""))
    triplet = _merge_triplet(slot_lookup.get(key) if key else None, meta)
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


_RULE_KIND_MAP_FOR_BINDING: Dict[str, str] = {
    "APPOINT_FAMILY": "APPOINTMENT",
    "APPOINT": "APPOINTMENT",
    "PRESERVE_FAMILY": "INSPECTION",
    "PRESERVE": "INSPECTION",
    "REPORT_FAMILY": "REPORT",
    "REPORT": "REPORT",
    "TRAINING_FAMILY": "TRAINING",
    "TRAINING": "TRAINING",
    "MANDATORY_FAMILY": "INSPECTION",
    "MANDATORY": "INSPECTION",
    "PROHIBITION_FAMILY": "PROHIBITION",
    "PROHIBITION": "PROHIBITION",
    "PERMISSIVE_FAMILY": "STANDARD",
    "선임": "APPOINTMENT",
    "점검": "INSPECTION",
    "신고": "REPORT",
    "교육": "TRAINING",
    "서류": "REPORT",
    "OTHER": "STANDARD",
    "INSPECTION": "INSPECTION",
    "APPOINTMENT": "APPOINTMENT",
}


def convert_rules_table_to_matched_rules(rules_table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    full_result rules_table → Legal Adapter project_rules()용 matched_rules.
    """
    matched: List[Dict[str, Any]] = []
    for i, rule in enumerate(rules_table):
        if not isinstance(rule, dict):
            continue
        raw_kind = (rule.get("rule_kind") or rule.get("category") or "").upper()
        rule_kind = _RULE_KIND_MAP_FOR_BINDING.get(raw_kind, raw_kind)

        who = (rule.get("who") or "").strip()
        what = (rule.get("what") or "").strip()
        when = (rule.get("when") or "").strip()
        desc_parts = [p for p in (who, what, when) if p]
        description = " | ".join(desc_parts)

        penalty = rule.get("penalty_summary") or ""
        matched.append(
            {
                "rule_id": str(rule.get("rule_id") or rule.get("id") or f"diag-{i}"),
                "rule_kind": rule_kind,
                "title": rule.get("obligation_summary") or rule.get("what") or f"Rule {i}",
                "description": description,
                "law_name": rule.get("law_name"),
                "article": rule.get("law_article"),
                "severity": "high" if "과태료" in penalty else "medium",
            }
        )
    return matched


def enrich_rules_with_candidate_slots(
    supabase,
    rules: List[Dict[str, Any]],
) -> None:
    """rule_candidate_slot + metadata 폴백으로 who/what/when 주입 (step1·웹 조회 공용)."""
    rows = [r for r in rules if isinstance(r, dict)]
    if not rows:
        return
    slot_lookup = _build_slot_lookup_by_law_article(supabase, rows)
    _enrich_rules_with_slots(supabase, rows, slot_lookup)


def _enrich_result_data_slots(supabase, result_data: Dict[str, Any]) -> None:
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
    enrich_rules_with_candidate_slots(supabase, rows)


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
    _enrich_result_data_slots(supabase, result_data)

    factory_id = (body.factory_id or "").strip() or None
    if factory_id:
        try:
            core = fetch_compiler_candidates(supabase, factory_id)
            result_data["compiler_core"] = {
                "compiler_version": core["compiler_version"],
                "warning": core["warning"],
                "applicability_count": len(core["applicability_candidates"]),
                "task_count": len(core["task_candidates"]),
                "schedule_count": len(core["schedule_candidates"]),
                "applicability_candidates": core["applicability_candidates"],
                "task_candidates": core["task_candidates"],
                "schedule_candidates": core["schedule_candidates"],
            }
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "compiler_core fetch failed for factory_id=%s: %s",
                factory_id,
                exc,
            )
            result_data["compiler_core"] = None

    return result_data
