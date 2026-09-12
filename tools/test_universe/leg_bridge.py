"""WO-SM-CORE22-E2E-112-BRIDGE-CONTRACT-001 — 112 Profile → Official LEG request projection.

Input projection only. No legal judgment, no HTTP, no baseline overwrite.
Does not modify e2e_runner_all.py (historical Compiler Core runner).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from clients.leg_runtime_client import _LEG_CODE_TO_CONSUMER, _LEG_INPUT_FIELDS
from schemas.diagnosis_integrated import DiagnosisRunBody

MAPPING_VERSION = "leg-112-bridge-v1"
WO = "WO-SM-CORE22-E2E-112-BRIDGE-CONTRACT-001"
EXPECTED_PROFILE_COUNT = 112
EXPECTED_ID_RANGE = tuple(f"PF-{i:04d}" for i in range(1, 113))

DIRECT = "DIRECT"
PRODUCTION_ADAPTER = "PRODUCTION_ADAPTER"
UNSUPPORTED = "UNSUPPORTED"
NOT_APPLICABLE = "NOT_APPLICABLE"

# DiagnosisRunBody top-level names that exist on Profile layers with the same field_code.
_COMPANY_TO_BODY = {
    "region": "region",
    "worker_count": "worker_count",
    "ksic_major": "ksic_major",
}
_BUILDING_TO_BODY = {
    "building_use_type": "building_use_type",
    "total_floor_area": "total_floor_area",
    "floor_area": "floor_area",
    "floor_count": "floor_count",
}
_CONSTRUCTION_TO_BODY = {
    "construction_type": "construction_type",
    "contract_amount_eok": "contract_amount_eok",
    "direct_workers": "direct_workers",
    "subcon_workers": "subcon_workers",
}

_BODY_FIELDS = frozenset(DiagnosisRunBody.model_fields)
_VOCAB_103 = frozenset(_LEG_INPUT_FIELDS)
_CONSUMER_ALIAS_KEYS = frozenset(_LEG_CODE_TO_CONSUMER.values())

_COMPANY_UNSUPPORTED = frozenset({"name", "industry", "ksic_name", "scale", "workers"})
_CONSTRUCTION_UNSUPPORTED = frozenset(
    {"construction_type_code", "kcsc_code", "kcsc_process", "order_type"}
)
_BUILDING_UNSUPPORTED = frozenset({"facility_type"})

# Live HTTP (not this WO) requires these; they are not Profile layers.
_LIVE_AUTH_FIELDS = ("auth_token", "disclaimer_log_id")


class BridgeContractError(RuntimeError):
    """Fail closed: Profile cannot be projected without guesswork or missing required Official field."""


def load_profile_universe(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        raise BridgeContractError("PROFILE_UNIVERSE_MISSING_PROFILES")
    return data


def assert_universe_integrity(profiles: Iterable[Mapping[str, Any]]) -> List[str]:
    ids = [str(p.get("profile_id") or "") for p in profiles]
    if len(ids) != EXPECTED_PROFILE_COUNT:
        raise BridgeContractError(f"PROFILE_COUNT_{len(ids)}")
    if len(set(ids)) != EXPECTED_PROFILE_COUNT:
        raise BridgeContractError("DUPLICATE_PROFILE")
    expected = list(EXPECTED_ID_RANGE)
    if sorted(ids) != sorted(expected):
        raise BridgeContractError("PROFILE_IDS_MISMATCH")
    return ids


def _rec(
    *,
    layer: str,
    source_field: str,
    source_unit: str,
    request_field: Optional[str],
    request_unit: str,
    mapping_type: str,
    production_normalizer: str,
    loss: str,
    evidence: str,
    value: Any = None,
) -> dict:
    return {
        "layer": layer,
        "source_field": source_field,
        "source_unit": source_unit,
        "official_request_field": request_field,
        "request_unit": request_unit,
        "mapping_type": mapping_type,
        "production_normalizer": production_normalizer,
        "loss": loss,
        "evidence": evidence,
        "value": value,
    }


def _put_body(body: dict, key: str, value: Any) -> None:
    if key not in _BODY_FIELDS:
        raise BridgeContractError(f"REQUEST_FIELD_UNKNOWN:{key}")
    body[key] = value


def _put_form(form: dict, key: str, value: Any) -> None:
    form[key] = value


def consumer_entry_sector(profile_sector: str) -> str:
    """Map Frozen Profile classification → Official LEG consumer request.sector.

    WO-SM-E2E-SPECIAL-BRIDGE-PROJECTION-APPLY-001:
    SPECIAL_FACILITY is a Profile classification, not a tai-www consumer entry.
    Consumer entries are BUILDING / INDUSTRY / CONSTRUCTION. This is request
    projection only — not a law-sector rewrite, not a product-tier choice,
    not a Frozen Profile mutation.
    """
    src = str(profile_sector or "")
    if src == "SPECIAL_FACILITY":
        return "BUILDING"
    return src


def profile_to_leg_request(profile: Mapping[str, Any]) -> dict:
    """Project one frozen Profile into a DiagnosisRunBody-compatible dict. No HTTP."""
    pid = str(profile.get("profile_id") or "")
    sector = profile.get("sector")
    if not pid:
        raise BridgeContractError("PROFILE_ID_MISSING")
    if not sector:
        raise BridgeContractError("REQUIRED_SECTOR_MISSING")

    source_sector = str(sector)
    request_sector = consumer_entry_sector(source_sector)

    layers = profile.get("layers") if isinstance(profile.get("layers"), Mapping) else {}
    company = layers.get("company") if isinstance(layers.get("company"), Mapping) else {}
    building = layers.get("building") if isinstance(layers.get("building"), Mapping) else {}
    construction = layers.get("construction") if isinstance(layers.get("construction"), Mapping) else None
    process = layers.get("process") if isinstance(layers.get("process"), list) else []
    facility = layers.get("facility") if isinstance(layers.get("facility"), list) else []
    work = layers.get("work") if isinstance(layers.get("work"), list) else []

    body: Dict[str, Any] = {}
    form_data: Dict[str, Any] = {}
    records: List[dict] = []

    _put_body(body, "sector", request_sector)
    if source_sector == "SPECIAL_FACILITY":
        mapping_type = PRODUCTION_ADAPTER
        production_normalizer = (
            "consumer_entry_sector: SPECIAL_FACILITY→BUILDING "
            "(WO-SM-E2E-SPECIAL-BRIDGE-PROJECTION-APPLY-001); not law-sector rewrite"
        )
        evidence = (
            "tai-www consumer entry is BUILDING|INDUSTRY|CONSTRUCTION; "
            "DiagnosisRunBody.sector receives consumer entry, not Frozen classification"
        )
    elif source_sector == "MANUFACTURING":
        mapping_type = PRODUCTION_ADAPTER
        production_normalizer = "legal_rules.normalize_sector_db (MANUFACTURING→INDUSTRIAL)"
        evidence = "DiagnosisRunBody.sector; run_diagnosis uses normalize_sector_db"
    else:
        mapping_type = DIRECT
        production_normalizer = "DiagnosisRunBody.sector DIRECT"
        evidence = "DiagnosisRunBody.sector; run_diagnosis uses normalize_sector_db"
    records.append(
        _rec(
            layer="profile",
            source_field="sector",
            source_unit="enum",
            request_field="sector",
            request_unit="enum",
            mapping_type=mapping_type,
            production_normalizer=production_normalizer,
            loss="0",
            evidence=evidence,
            value=request_sector,
        )
    )

    if company.get("workers") is not None and company.get("worker_count") is not None:
        if company.get("workers") != company.get("worker_count"):
            raise BridgeContractError("WORKERS_NE_WORKER_COUNT")

    for src, dst in _COMPANY_TO_BODY.items():
        if src not in company or company.get(src) is None:
            continue
        val = company[src]
        _put_body(body, dst, val)
        if dst in _VOCAB_103:
            _put_form(form_data, dst, val)
        records.append(
            _rec(
                layer="company",
                source_field=src,
                source_unit="as-stored",
                request_field=dst,
                request_unit="as-stored",
                mapping_type=DIRECT,
                production_normalizer="DiagnosisRunBody top-level + canonical_applicability if 103-vocab",
                loss="0",
                evidence="schemas/diagnosis_integrated.py DiagnosisRunBody",
                value=val,
            )
        )

    if "workers" in company and company.get("workers") is not None:
        records.append(
            _rec(
                layer="company",
                source_field="workers",
                source_unit="count",
                request_field="worker_count",
                request_unit="count",
                mapping_type=PRODUCTION_ADAPTER,
                production_normalizer="run_diagnosis form_data.workers alias; not summed",
                loss="0 (same value as worker_count; worker_count is the Official field)",
                evidence="diagnosis_integrated_svc._fd_num('workers'); profile workers==worker_count in universe",
                value=company.get("workers"),
            )
        )

    for src in _COMPANY_UNSUPPORTED:
        if src == "workers":
            continue
        if src in company and company.get(src) is not None:
            records.append(
                _rec(
                    layer="company",
                    source_field=src,
                    source_unit="as-stored",
                    request_field=None,
                    request_unit="",
                    mapping_type=UNSUPPORTED,
                    production_normalizer="none",
                    loss="not in DiagnosisRunBody / _LEG_INPUT_FIELDS",
                    evidence="Official LEG request contract does not accept this field",
                    value=company.get(src),
                )
            )

    for src, dst in _BUILDING_TO_BODY.items():
        if src not in building or building.get(src) is None:
            continue
        val = building[src]
        _put_body(body, dst, val)
        if dst in _VOCAB_103:
            _put_form(form_data, dst, val)
        records.append(
            _rec(
                layer="building",
                source_field=src,
                source_unit="m2" if "area" in src else ("count" if src == "floor_count" else "as-stored"),
                request_field=dst,
                request_unit="same",
                mapping_type=DIRECT,
                production_normalizer="DiagnosisRunBody; 103-vocab keys also form_data",
                loss="0",
                evidence="DiagnosisRunBody + _LEG_INPUT_FIELDS",
                value=val,
            )
        )
    for src in _BUILDING_UNSUPPORTED:
        if src in building and building.get(src) is not None:
            records.append(
                _rec(
                    layer="building",
                    source_field=src,
                    source_unit="as-stored",
                    request_field=None,
                    request_unit="",
                    mapping_type=UNSUPPORTED,
                    production_normalizer="none",
                    loss="not in Official LEG request / 103 vocab",
                    evidence="DiagnosisRunBody has no facility_type; _LEG_INPUT_FIELDS has none",
                    value=building.get(src),
                )
            )

    if construction is None:
        for src in list(_CONSTRUCTION_TO_BODY) + list(_CONSTRUCTION_UNSUPPORTED):
            records.append(
                _rec(
                    layer="construction",
                    source_field=src,
                    source_unit="",
                    request_field=None,
                    request_unit="",
                    mapping_type=NOT_APPLICABLE,
                    production_normalizer="none",
                    loss="0",
                    evidence="layers.construction is null for this sector",
                    value=None,
                )
            )
    else:
        for src, dst in _CONSTRUCTION_TO_BODY.items():
            if src not in construction or construction.get(src) is None:
                continue
            val = construction[src]
            _put_body(body, dst, val)
            if dst in _VOCAB_103:
                _put_form(form_data, dst, val)
            # contract_amount_eok is not in 103; C2 attaches it from body.contract_amount_eok verbatim.
            records.append(
                _rec(
                    layer="construction",
                    source_field=src,
                    source_unit="EOK" if src == "contract_amount_eok" else "as-stored",
                    request_field=dst,
                    request_unit="EOK" if src == "contract_amount_eok" else "as-stored",
                    mapping_type=DIRECT,
                    production_normalizer=(
                        "construction_amount_c2.resolve_contract_amount_eok_c2 priority 1: "
                        "body.contract_amount_eok verbatim (no /10000)"
                        if src == "contract_amount_eok"
                        else "DiagnosisRunBody top-level"
                    ),
                    loss="0",
                    evidence=(
                        "DiagnosisRunBody.contract_amount_eok; C2 already-canonical not divided"
                        if src == "contract_amount_eok"
                        else "schemas/diagnosis_integrated.py DiagnosisRunBody"
                    ),
                    value=val,
                )
            )
        for src in _CONSTRUCTION_UNSUPPORTED:
            if src in construction and construction.get(src) is not None:
                records.append(
                    _rec(
                        layer="construction",
                        source_field=src,
                        source_unit="as-stored",
                        request_field=None,
                        request_unit="",
                        mapping_type=UNSUPPORTED,
                        production_normalizer="none",
                        loss="not in Official LEG request contract",
                        evidence="DiagnosisRunBody / _LEG_INPUT_FIELDS",
                        value=construction.get(src),
                    )
                )

    for item in facility:
        if not isinstance(item, Mapping) or not item.get("code"):
            continue
        code = str(item["code"])
        val = item.get("value")
        if code in _VOCAB_103:
            _put_form(form_data, code, val)
            if code in _BODY_FIELDS:
                _put_body(body, code, val)
            records.append(
                _rec(
                    layer="facility",
                    source_field=code,
                    source_unit="as-stored",
                    request_field=f"form_data.{code}",
                    request_unit="as-stored",
                    mapping_type=DIRECT,
                    production_normalizer="canonical_applicability(_LEG_INPUT_FIELDS exact-name)",
                    loss="0",
                    evidence="clients.leg_runtime_client._LEG_INPUT_FIELDS",
                    value=val,
                )
            )
        elif code in _CONSUMER_ALIAS_KEYS:
            _put_form(form_data, code, val)
            if code in _BODY_FIELDS:
                _put_body(body, code, val)
            records.append(
                _rec(
                    layer="facility",
                    source_field=code,
                    source_unit="as-stored",
                    request_field=f"form_data.{code}",
                    request_unit="as-stored",
                    mapping_type=PRODUCTION_ADAPTER,
                    production_normalizer=(
                        "_build_unified_step1_body seeds _LEG_CODE_TO_CONSUMER consumer keys "
                        "then promotes to 103 canonical (has_chemical / has_high_place_work)"
                    ),
                    loss="0",
                    evidence="clients.leg_runtime_client._LEG_CODE_TO_CONSUMER (WO-E2E-SEM-001 approved alias)",
                    value=val,
                )
            )
        else:
            records.append(
                _rec(
                    layer="facility",
                    source_field=code,
                    source_unit="as-stored",
                    request_field=None,
                    request_unit="",
                    mapping_type=UNSUPPORTED,
                    production_normalizer="none — not invented",
                    loss="Official LEG 103 vocab + DiagnosisRunBody do not accept this code",
                    evidence="_LEG_INPUT_FIELDS / DiagnosisRunBody.model_fields",
                    value=val,
                )
            )

    if process:
        records.append(
            _rec(
                layer="process",
                source_field="process[]",
                source_unit="name/ksic",
                request_field="process_list",
                request_unit="",
                mapping_type=UNSUPPORTED,
                production_normalizer="DiagnosisRunBody.process_list is RAW envelope, not canonical applicability",
                loss="RAW ≠ CANONICAL; process_name not mapped to has_*",
                evidence="DiagnosisRunBody.process_list comment: RAW ENVELOPE, not form_data",
                value=process,
            )
        )
    else:
        records.append(
            _rec(
                layer="process",
                source_field="process[]",
                source_unit="",
                request_field=None,
                request_unit="",
                mapping_type=NOT_APPLICABLE,
                production_normalizer="none",
                loss="0",
                evidence="empty process list",
                value=[],
            )
        )

    if work:
        records.append(
            _rec(
                layer="work",
                source_field="work[]",
                source_unit="label",
                request_field=None,
                request_unit="",
                mapping_type=UNSUPPORTED,
                production_normalizer="none — work-name → has_* inference forbidden",
                loss="Korean work labels have no production mapping on /diagnosis/run-leg",
                evidence="no run-leg work-label adapter in tai-api",
                value=work,
            )
        )
    else:
        records.append(
            _rec(
                layer="work",
                source_field="work[]",
                source_unit="",
                request_field=None,
                request_unit="",
                mapping_type=NOT_APPLICABLE,
                production_normalizer="none",
                loss="0",
                evidence="empty work list",
                value=[],
            )
        )

    if form_data:
        _put_body(body, "form_data", form_data)

    # Never attach customer objects or live auth in the projection.
    for forbidden in ("factory_id", "company_id", "project_amount", "payment_ref", "auth_token"):
        if forbidden in body:
            raise BridgeContractError(f"FORBIDDEN_FIELD:{forbidden}")

    DiagnosisRunBody(**body)  # fail closed if Official model rejects

    unsupported = [r for r in records if r["mapping_type"] == UNSUPPORTED]
    gaps = [r for r in records if r["mapping_type"] == "GAP"]
    omitted = [
        r["source_field"]
        for r in records
        if r["mapping_type"] in {UNSUPPORTED, NOT_APPLICABLE}
    ]
    request_fields = sorted(k for k in body.keys() if k != "form_data") + [
        f"form_data.{k}" for k in sorted(form_data)
    ]

    return {
        "profile_id": pid,
        "sector": source_sector,
        "request_sector": request_sector,
        "mapping_version": MAPPING_VERSION,
        "wo": WO,
        "request": body,
        "request_field_list": request_fields,
        "records": records,
        "omitted_source_fields": omitted,
        "unsupported_fields": [
            {"layer": r["layer"], "source_field": r["source_field"], "evidence": r["evidence"]}
            for r in unsupported
        ],
        "mapping_gaps": gaps,
        "live_http_requires": list(_LIVE_AUTH_FIELDS),
        "factory_id": None,
        "company_id": None,
    }


def project_universe(profiles: List[Mapping[str, Any]]) -> Tuple[List[dict], dict]:
    assert_universe_integrity(profiles)
    built: List[dict] = []
    for p in profiles:
        built.append(profile_to_leg_request(p))
    if len(built) != EXPECTED_PROFILE_COUNT:
        raise BridgeContractError("REQUEST_BUILD_COUNT")
    types = {"DIRECT": 0, "PRODUCTION_ADAPTER": 0, "UNSUPPORTED": 0, "NOT_APPLICABLE": 0, "GAP": 0}
    for item in built:
        for r in item["records"]:
            types[r["mapping_type"]] = types.get(r["mapping_type"], 0) + 1
    summary = {
        "wo": WO,
        "mapping_version": MAPPING_VERSION,
        "profile_count": len(built),
        "request_build": len(built),
        "fail": 0,
        "construction_profiles": sum(1 for x in built if x["sector"] == "CONSTRUCTION"),
        "type_counts": types,
        "official_entrypoint": "POST /diagnosis/run-leg",
        "official_request_model": "schemas.diagnosis_integrated.DiagnosisRunBody",
        "http_executed": 0,
    }
    return built, summary
