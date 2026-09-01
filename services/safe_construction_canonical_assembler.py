"""services/safe_construction_canonical_assembler.py

WO-SAFE-LEGAL-CST-CANONICAL-IMPLEMENT-001 / STEP4 — CONSTRUCTION canonical → Marketing 27 assembler.

실제 건설 SaaS 자산(construction_sites / construction_site_processes / construction_works /
subcontractors)만 READ-ONLY 로 읽어 Marketing CONSTRUCTION PAID 계약(MKT_CST_PAID_CONTRACT_V1,
27 target)으로 조립한다. 저장모델/라우터/진단엔진/LEG 미접촉. INDUSTRIAL assembler 와 동일 패턴
(frozen target · provenance · unresolved · no-invention · DB WRITE 0)만 재사용한다.

원칙:
  - source NULL → output NULL. NULL→false/0/[] 승격 금지. 추정/현재연도/LLM/fuzzy 금지(no-invention).
  - false/0 는 보존(truthy filter 금지). NULL = unknown.
  - construction_type 은 site_type 의 EXACT key map(BUILDING/CIVIL/SPECIALTY)만. unknown fallback('건축') 금지.
  - E15(worker_count 포함 15개)는 이번 STEP 에서 항상 NULL + UNRESOLVED. CST text/legacy/mirror 값이 있어도 사용 금지.
  - special_work_type / hazard 문자열 의미추론 금지. hazard 는 현재 저장표현의 structural parsing(comma split)만.
  - table/row 중 하나라도 Marketing 계약으로 정확히 표현 불가하면 해당 field 전체 = NULL + unresolved(조용히 버리지 않음).
  - factories / equipment_assets / factory_materials / system_codes / diagnosis_input_fields 미조회. DB WRITE 0.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CONTRACT_VERSION = "MKT_CST_PAID_CONTRACT_V1"
SECTOR = "CONSTRUCTION"

# frozen 27 target (순서 고정)
TARGET_FIELDS = [
    "project_amount", "worker_count", "construction_type", "project_address",
    "has_subcontractor", "subcontractor_count", "process_list",
    "has_excavation", "has_demolition",
    "work_height_m", "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
    "has_tower_crane", "has_confined_space", "has_asbestos_demo", "has_blasting", "has_diving",
    "has_asbestos", "has_chemical_substance", "has_gas", "has_high_pressure_gas",
    "has_water_tank", "is_energy_intensive", "is_multi_use",
    "subcontractor",
]

# construction_type: site_type EXACT map. unknown fallback 금지.
CONSTRUCTION_TYPE_MAP = {
    "BUILDING": "건축",
    "CIVIL": "토목",
    "SPECIALTY": "공통",
}

# E15 — 이번 STEP 항상 NULL + UNRESOLVED (worker_count 포함 15).
E15_FIELDS = (
    "worker_count",
    "has_excavation", "has_demolition",
    "has_tower_crane", "has_confined_space", "has_asbestos_demo", "has_blasting", "has_diving",
    "has_asbestos", "has_chemical_substance", "has_gas", "has_high_pressure_gas",
    "has_water_tank", "is_energy_intensive", "is_multi_use",
)

# C5 실제 작업속성 (STEP2/STEP3 canonical)
C5_NUMERIC = ("work_height_m", "truck_loading_height_m", "manual_handling_weight_kg")
C5_BOOLEAN = ("has_truck_loading_unloading", "has_manual_heavy_handling")

# Marketing frozen 허용 hazard (이 밖의 토큰이 있으면 process_list = NULL + unresolved; 자동변환/드롭 0)
ALLOWED_HAZARDS = {"전도", "추락", "협착", "충돌", "화재", "폭발", "감전", "질식", "절단", "기타"}


def _rows(res) -> List[dict]:
    return list(getattr(res, "data", None) or [])


def _parse_hazard_tokens(text: Any) -> List[str]:
    """현재 저장표현(construction_works.hazard_codes text)의 structural parsing.
    comma split → trim → empty 제거 → 순서보존 dedupe. fuzzy synonym 변환 없음."""
    if text is None:
        return []
    parts = [t.strip() for t in str(text).split(",")]
    out: List[str] = []
    seen = set()
    for t in parts:
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def assemble_construction_marketing_contract(supabase, site_id: str) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    provenance: Dict[str, Dict[str, Any]] = {}
    unresolved: set = set()

    def _resolve(field, value, mode, source):
        values[field] = value
        provenance[field] = {"mode": mode, "source": source}

    def _unresolved(field, source):
        values[field] = None
        provenance[field] = {"mode": "UNRESOLVED", "source": source}
        unresolved.add(field)

    # ── construction_sites (single row) ──
    site_res = supabase.table("construction_sites").select("*").eq("id", site_id).limit(1).execute()
    site_rows = _rows(site_res)
    site = site_rows[0] if site_rows else {}

    # 05 SITE DIRECT (2): 억원 그대로, 재환산 금지
    _resolve("project_amount", site.get("contract_amount"), "DIRECT", "construction_sites.contract_amount")
    _resolve("project_address", site.get("site_address"), "DIRECT", "construction_sites.site_address")

    # 07 construction_type: site_type EXACT map (NULL→NULL, unknown non-null→NULL+unresolved)
    st = site.get("site_type")
    if st is None:
        _resolve("construction_type", None, "TRANSFORM", "construction_sites.site_type")
    elif st in CONSTRUCTION_TYPE_MAP:
        _resolve("construction_type", CONSTRUCTION_TYPE_MAP[st], "TRANSFORM", "construction_sites.site_type")
    else:
        _unresolved("construction_type", "construction_sites.site_type(unknown code)")

    # ── subcontractors (active) ──
    sub_res = (
        supabase.table("subcontractors")
        .select("company_name, work_type, worker_count, has_safety_manager, is_active")
        .eq("site_id", site_id)
        .eq("is_active", True)
        .execute()
    )
    sub_rows = _rows(sub_res)
    active_sub_count = len(sub_rows)

    # 05 has_subcontractor / 06 subcontractor_count — count 기반(별도 boolean 저장 없음)
    _resolve("has_subcontractor", active_sub_count > 0, "TRANSFORM", "subcontractors(active count)")
    _resolve("subcontractor_count", active_sub_count, "TRANSFORM", "subcontractors(active count)")

    # 27 subcontractor transport
    if active_sub_count == 0:
        _resolve("subcontractor", None, "COMPOSITE", "subcontractors")
    else:
        rows_out = []
        ok = True
        for s in sub_rows:
            wt = s.get("work_type")
            if wt is None or (isinstance(wt, str) and wt.strip() == ""):
                ok = False  # required work_scope 정확 생성 불가 → 조용히 버리지 않고 전체 unresolved
                break
            sm = s.get("has_safety_manager")
            safety_label = "있음" if sm is True else ("없음" if sm is False else "모름")
            rows_out.append({
                "company_name": s.get("company_name"),
                "work_scope": wt,
                "worker_count": s.get("worker_count"),  # 0 보존
                "safety_manager": safety_label,
            })
        if ok:
            _resolve("subcontractor", rows_out, "COMPOSITE", "subcontractors")
        else:
            _unresolved("subcontractor", "subcontractors(work_type 결측 active row)")

    # ── construction_works (active) — hazard 원천 + C5 집계 ──
    work_res = (
        supabase.table("construction_works")
        .select("*")
        .eq("site_id", site_id)
        .eq("is_active", True)
        .execute()
    )
    work_rows = _rows(work_res)

    # ── construction_site_processes (active) → process_list ──
    proc_res = (
        supabase.table("construction_site_processes")
        .select("id, process_name, is_active")
        .eq("site_id", site_id)
        .eq("is_active", True)
        .execute()
    )
    proc_rows = _rows(proc_res)

    if not proc_rows:
        _resolve("process_list", None, "COMPOSITE", "construction_site_processes")  # 등록 공정 없음(강제 unresolved 아님)
    else:
        rows_out = []
        bad_token = False
        for p in proc_rows:
            pid = p.get("id")
            toks: List[str] = []
            seen = set()
            for w in work_rows:
                if w.get("process_id") == pid:
                    for t in _parse_hazard_tokens(w.get("hazard_codes")):
                        if t not in seen:
                            seen.add(t)
                            toks.append(t)
            for t in toks:
                if t not in ALLOWED_HAZARDS:  # 허용목록 밖 토큰 → 자동변환/드롭 없이 전체 unresolved
                    bad_token = True
                    break
            if bad_token:
                break
            rows_out.append({
                "name": p.get("process_name"),
                "hazard_codes": toks,
            })
        if bad_token:
            _unresolved("process_list", "construction_works.hazard_codes(허용목록 밖 토큰)")
        else:
            _resolve("process_list", rows_out, "COMPOSITE", "construction_site_processes+construction_works")

    # ── C5 numeric (active work non-null distinct: 0→NULL, 1→value, 2+→NULL+unresolved; MAX/SUM/AVG 금지) ──
    for field in C5_NUMERIC:
        distinct = []
        seen = set()
        for w in work_rows:
            v = w.get(field)
            if v is None:
                continue
            if v not in seen:
                seen.add(v)
                distinct.append(v)
        if len(distinct) == 0:
            _resolve(field, None, "COMPOSITE", "construction_works")
        elif len(distinct) == 1:
            _resolve(field, distinct[0], "COMPOSITE", "construction_works")  # 0 보존
        else:
            _unresolved(field, "construction_works(상충하는 다중 값)")

    # ── C5 boolean (any True→True; all explicit False→False; False+NULL/NULL-only→NULL+unresolved; 0 work→NULL) ──
    for field in C5_BOOLEAN:
        if not work_rows:
            _resolve(field, None, "COMPOSITE", "construction_works")
            continue
        vals = [w.get(field) for w in work_rows]
        if any(v is True for v in vals):
            _resolve(field, True, "COMPOSITE", "construction_works")
        elif all(v is False for v in vals):
            _resolve(field, False, "COMPOSITE", "construction_works")
        else:
            _unresolved(field, "construction_works(False/NULL 혼재 또는 NULL only)")

    # ── E15 — 항상 NULL + UNRESOLVED (CST text/legacy/mirror 사용 금지, special_work_type 소비 0) ──
    for f in E15_FIELDS:
        _unresolved(f, "미확정(건설 의미 미입증) — STEP4 파생 금지")

    # 27 정합성(안전망)
    for f in TARGET_FIELDS:
        if f not in values:
            _unresolved(f, "MISSING")

    return {
        "contract_version": CONTRACT_VERSION,
        "sector": SECTOR,
        "site_id": site_id,
        "values": {f: values[f] for f in TARGET_FIELDS},  # 정확히 27, 순서 고정
        "unresolved_fields": sorted(unresolved),
        "provenance": provenance,
    }
