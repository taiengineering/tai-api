"""KECO chemical public read layer.

LEG DB (msds_ref schema) 에서 CAS 번호로 화학물질 정보 조회.
Write=0. raw_payload 미노출. regulatory_facts 포함.
CAS format: 1-7 digits, dash, 2 digits, dash, 1 digit  (e.g. 50-00-0).
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

_CAS_RE = re.compile(r'^\d{1,7}-\d{2}-\d$')


class KecoReadError(Exception):
    pass


class KecoLegUnavailable(KecoReadError):
    pass


def validate_cas(cas_no: str) -> str:
    """Validate and normalize CAS number. Returns stripped value or raises ValueError."""
    cas = cas_no.strip()
    if not _CAS_RE.match(cas):
        raise ValueError(f"Invalid CAS format: {cas!r}")
    return cas


def _get_leg_client():
    url = os.environ.get("LEG_SUPABASE_URL", "").strip()
    key = os.environ.get("LEG_SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise KecoLegUnavailable(
            "KECO_LEG_UNAVAILABLE: LEG_SUPABASE_URL and "
            "LEG_SUPABASE_SERVICE_ROLE_KEY must be set"
        )
    from supabase import create_client
    return create_client(url, key)


def get_chemicals_by_cas(cas_no: str) -> List[Dict[str, Any]]:
    """Fetch keco_chemicals rows for a CAS number from LEG msds_ref schema.

    Returns list of dicts with safe public fields only.
    raw_payload is never exposed.
    """
    cas = validate_cas(cas_no)
    client = _get_leg_client()
    db = client.schema("msds_ref")

    res = (
        db.table("keco_chemicals")
        .select(
            "id,source_record_id,cas_no,korexst_raw,"
            "chemical_name_ko,chemical_name_en,"
            "alias_name_ko,alias_name_en,"
            "molecular_formula,molecular_weight_raw,"
            "last_seen_at,last_changed_at"
        )
        .eq("cas_no", cas)
        .execute()
    )
    chemicals = list(res.data or [])
    if not chemicals:
        return []

    chem_ids = [c["id"] for c in chemicals if c.get("id")]
    facts_by_chem: Dict[str, list] = {cid: [] for cid in chem_ids}
    if chem_ids:
        for start in range(0, len(chem_ids), 100):
            batch = chem_ids[start:start + 100]
            facts_res = (
                db.table("keco_regulatory_facts")
                .select(
                    "keco_chemical_id,classification_type,unique_no,"
                    "content_info,exception_info,notice_date_raw,notice_info,"
                    "source_ordinal"
                )
                .in_("keco_chemical_id", batch)
                .order("source_ordinal")
                .execute()
            )
            for f in (facts_res.data or []):
                cid = f.get("keco_chemical_id")
                if cid in facts_by_chem:
                    facts_by_chem[cid].append({
                        "classification_type": f.get("classification_type"),
                        "unique_no": f.get("unique_no"),
                        "content_info": f.get("content_info"),
                        "exception_info": f.get("exception_info"),
                        "notice_date_raw": f.get("notice_date_raw"),
                        "notice_info": f.get("notice_info"),
                        "source_ordinal": f.get("source_ordinal"),
                    })

    result = []
    for c in chemicals:
        cid = c.get("id")
        result.append({
            "source_record_id": c.get("source_record_id"),
            "cas_no": c.get("cas_no"),
            "korexst_raw": c.get("korexst_raw"),
            "chemical_name_ko": c.get("chemical_name_ko"),
            "chemical_name_en": c.get("chemical_name_en"),
            "alias_name_ko": c.get("alias_name_ko"),
            "alias_name_en": c.get("alias_name_en"),
            "molecular_formula": c.get("molecular_formula"),
            "molecular_weight_raw": c.get("molecular_weight_raw"),
            "last_seen_at": c.get("last_seen_at"),
            "last_changed_at": c.get("last_changed_at"),
            "regulatory_facts": facts_by_chem.get(cid, []),
        })

    return result
