"""runtime_binding_resolver.py — Runtime Data Binding Engine (PHASE B)

schema field에 runtime data binding 수행.
document_schema_registry.source_mapping → 실제 DB 데이터 조회.

절대 금지: AI 기반 field mapping, semantic inference, guessed binding
"""
import json
from typing import Optional
from db.supabase_client import get_supabase

# Source → (table, column) deterministic 매핑
SOURCE_TABLE_MAP = {
    # runtime_facility_profile
    "facility.facility_name": ("runtime_facility_profile", "facility_name"),
    "facility.industry_code": ("runtime_facility_profile", "industry_code"),
    "facility.industry_name": ("runtime_facility_profile", "industry_name"),
    "facility.worker_count": ("runtime_facility_profile", "worker_count"),
    "facility.address": ("runtime_facility_profile", "address"),
    "facility.contractor_exists": ("runtime_facility_profile", "contractor_exists"),
    "facility.facility_types": ("runtime_facility_profile", "facility_types"),
    # facility_condition (key-value)
    "condition.electrical_capacity": ("facility_condition", "electrical_capacity"),
    "condition.hazardous_quantity": ("facility_condition", "hazardous_quantity"),
    "condition.building_area": ("facility_condition", "building_area"),
    # sites
    "site.site_name": ("sites", "site_name"),
    "site.site_code": ("sites", "site_code"),
}


def resolve_source_value(source_mapping: str, tenant_context: dict) -> dict:
    """source_mapping 문자열을 실제 값으로 resolve. deterministic only."""
    if not source_mapping:
        return {"value": None, "resolved": False, "reason": "no_source_mapping"}

    facility_id = tenant_context.get("facility_id")
    if not facility_id:
        return {"value": None, "resolved": False, "reason": "no_facility_id"}

    sb = get_supabase()

    # facility_condition은 key-value 구조
    if source_mapping.startswith("condition."):
        field_name = source_mapping.split(".", 1)[1]
        result = sb.table("facility_condition").select("condition_value").eq(
            "factory_id", facility_id
        ).eq("condition_field", field_name).limit(1).execute()
        if result.data:
            return {"value": result.data[0]["condition_value"], "resolved": True, "source": source_mapping}
        return {"value": None, "resolved": False, "reason": f"condition '{field_name}' not found"}

    # 일반 테이블 매핑
    mapping = SOURCE_TABLE_MAP.get(source_mapping)
    if not mapping:
        return {"value": None, "resolved": False, "reason": f"unknown_source: {source_mapping}"}

    table, column = mapping
    try:
        result = sb.table(table).select(column).eq("id", facility_id).limit(1).execute()
        if result.data:
            return {"value": result.data[0].get(column), "resolved": True, "source": source_mapping}
        return {"value": None, "resolved": False, "reason": f"no data in {table}"}
    except Exception as e:
        return {"value": None, "resolved": False, "reason": str(e)}


def resolve_document_runtime(document_type: str, tenant_context: dict) -> dict:
    """document_type의 전체 필드를 runtime data로 binding"""
    sb = get_supabase()

    # 섹션 조회
    sections = sb.table("document_schema_section").select("*").eq(
        "document_type", document_type
    ).eq("enabled", True).order("section_order").execute()

    # 필드 조회
    fields = sb.table("document_schema_registry").select("*").eq(
        "document_type", document_type
    ).eq("enabled", True).order("field_order").execute()

    if not fields.data:
        return {"error": f"No schema for {document_type}"}

    # 섹션별 그룹
    section_fields = {}
    for f in fields.data:
        sc = f.get("section_code", "GENERAL")
        if sc not in section_fields:
            section_fields[sc] = []

        # runtime binding
        binding = resolve_source_value(f.get("source_mapping"), tenant_context)

        cond_raw = f.get("conditional_rule")
        if cond_raw is not None and not isinstance(cond_raw, (dict, list)):
            try:
                cond_raw = json.loads(cond_raw) if isinstance(cond_raw, str) else cond_raw
            except (json.JSONDecodeError, TypeError):
                cond_raw = None

        val_raw = f.get("validation_rule")
        if val_raw is not None and not isinstance(val_raw, dict):
            try:
                val_raw = json.loads(val_raw) if isinstance(val_raw, str) else val_raw
            except (json.JSONDecodeError, TypeError):
                val_raw = None

        section_fields[sc].append({
            "field_code": f["field_code"],
            "field_label": f["field_label"],
            "field_type": f["field_type"],
            "required_level": f["required_level"],
            "value": binding["value"],
            "source": f.get("source_mapping"),
            "resolved": binding["resolved"],
            "resolve_reason": binding.get("reason"),
            "render_component": f.get("render_component"),
            "source_trace": f.get("source_trace"),
            "source_reason": f.get("source_reason"),
            "source_mapping": f.get("source_mapping"),
            "conditional_rule": cond_raw,
            "validation_rule": val_raw,
        })

    # 조립
    result_sections = []
    for s in (sections.data or []):
        sc = s["section_code"]
        result_sections.append({
            "section_code": sc,
            "section_title": s["section_title"],
            "section_order": s["section_order"],
            "fields": section_fields.get(sc, []),
        })

    return {
        "document_type": document_type,
        "tenant_context": {k: str(v)[:50] for k, v in tenant_context.items()},
        "sections": result_sections,
    }
