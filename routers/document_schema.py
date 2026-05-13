"""
document_schema.py — Document Schema Registry API

문서 구조 메타데이터 조회. Admin-only 우선.
작업지시서 #1 PHASE I.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from db.supabase_client import get_supabase

router = APIRouter(prefix="/document-schema", tags=["Document Schema"])


@router.get("/list")
async def list_document_schemas(
    status: Optional[str] = Query(None, description="CANDIDATE/CONFIRMED/DEPRECATED"),
    enabled: Optional[bool] = Query(None),
):
    """등록된 문서 유형 목록 + 섹션/필드 요약"""
    sb = get_supabase()

    # document_type별 집계
    q = sb.table("document_schema_registry").select(
        "document_type, schema_version, required_level, status"
    )
    if status:
        q = q.eq("status", status)
    if enabled is not None:
        q = q.eq("enabled", enabled)

    result = q.execute()
    rows = result.data or []

    # 집계
    types = {}
    for r in rows:
        dt = r["document_type"]
        if dt not in types:
            types[dt] = {
                "document_type": dt,
                "schema_version": r["schema_version"],
                "total_fields": 0,
                "mandatory_fields": 0,
                "recommended_fields": 0,
                "optional_fields": 0,
            }
        types[dt]["total_fields"] += 1
        level = r.get("required_level", "OPTIONAL")
        if level == "MANDATORY":
            types[dt]["mandatory_fields"] += 1
        elif level == "RECOMMENDED":
            types[dt]["recommended_fields"] += 1
        else:
            types[dt]["optional_fields"] += 1

    # 섹션 수
    sec_result = sb.table("document_schema_section").select(
        "document_type"
    ).execute()
    sec_counts = {}
    for s in (sec_result.data or []):
        dt = s["document_type"]
        sec_counts[dt] = sec_counts.get(dt, 0) + 1

    for dt in types:
        types[dt]["total_sections"] = sec_counts.get(dt, 0)

    return {
        "total_document_types": len(types),
        "document_types": sorted(types.values(), key=lambda x: x["document_type"]),
    }


@router.get("/{document_type}")
async def get_document_schema(document_type: str):
    """문서 유형의 전체 스키마 (섹션+필드)"""
    sb = get_supabase()

    # 섹션
    sections = sb.table("document_schema_section").select("*").eq(
        "document_type", document_type
    ).order("section_order").execute()

    # 필드
    fields = sb.table("document_schema_registry").select("*").eq(
        "document_type", document_type
    ).eq("enabled", True).order("field_order").execute()

    if not fields.data:
        raise HTTPException(404, f"Document type '{document_type}' not found")

    # 섹션별 그룹
    section_map = {}
    for s in (sections.data or []):
        section_map[s["section_code"]] = {
            **s,
            "fields": [],
        }

    for f in (fields.data or []):
        sc = f.get("section_code", "GENERAL")
        if sc not in section_map:
            section_map[sc] = {
                "section_code": sc,
                "section_title": f.get("section_title", sc),
                "section_order": 999,
                "fields": [],
            }
        section_map[sc]["fields"].append(f)

    ordered = sorted(section_map.values(), key=lambda x: x.get("section_order", 999))

    return {
        "document_type": document_type,
        "total_sections": len(ordered),
        "total_fields": len(fields.data or []),
        "sections": ordered,
    }


@router.get("/render-structure/{document_type}")
async def get_render_structure(document_type: str):
    """프론트엔드 렌더링용 구조 (섹션→필드→render_component)"""
    sb = get_supabase()

    sections = sb.table("document_schema_section").select("*").eq(
        "document_type", document_type
    ).eq("enabled", True).order("section_order").execute()

    fields = sb.table("document_schema_registry").select(
        "section_code, field_code, field_label, field_type, field_order, "
        "required_level, render_component, validation_rule, conditional_rule, repeatable"
    ).eq("document_type", document_type
    ).eq("enabled", True).order("field_order").execute()

    if not fields.data:
        raise HTTPException(404, f"No render structure for '{document_type}'")

    structure = []
    field_by_section = {}
    for f in (fields.data or []):
        sc = f.pop("section_code", "GENERAL")
        if sc not in field_by_section:
            field_by_section[sc] = []
        field_by_section[sc].append(f)

    for s in (sections.data or []):
        sc = s["section_code"]
        structure.append({
            "section_code": sc,
            "section_title": s["section_title"],
            "fields": field_by_section.get(sc, []),
        })

    return {
        "document_type": document_type,
        "render_structure": structure,
    }


@router.get("/field-mapping/{document_type}")
async def get_field_mapping(document_type: str):
    """필드 → 데이터 소스 매핑 (PHASE C)"""
    sb = get_supabase()

    fields = sb.table("document_schema_registry").select(
        "field_code, field_label, source_mapping, source_trace, source_reason, "
        "required_level, status"
    ).eq("document_type", document_type
    ).eq("enabled", True).order("field_order").execute()

    if not fields.data:
        raise HTTPException(404, f"No field mapping for '{document_type}'")

    mapped = [f for f in fields.data if f.get("source_mapping")]
    unmapped = [f for f in fields.data if not f.get("source_mapping")]

    return {
        "document_type": document_type,
        "total_fields": len(fields.data),
        "mapped_fields": len(mapped),
        "unmapped_fields": len(unmapped),
        "fields": fields.data,
    }


@router.get("/integrity/{document_type}")
async def check_schema_integrity(document_type: str):
    """스키마 무결성 점검 (PHASE H)"""
    sb = get_supabase()

    fields = sb.table("document_schema_registry").select("*").eq(
        "document_type", document_type
    ).execute()

    if not fields.data:
        raise HTTPException(404, f"No schema for '{document_type}'")

    issues = []
    for f in fields.data:
        if not f.get("render_component"):
            issues.append({"field": f["field_code"], "issue": "missing_render_component"})
        if f.get("required_level") == "MANDATORY" and not f.get("validation_rule"):
            issues.append({"field": f["field_code"], "issue": "mandatory_without_validation"})
        if f.get("status") == "CANDIDATE":
            issues.append({"field": f["field_code"], "issue": "unconfirmed_candidate"})

    return {
        "document_type": document_type,
        "total_fields": len(fields.data),
        "total_issues": len(issues),
        "integrity_status": "CLEAN" if not issues else "HAS_ISSUES",
        "issues": issues[:50],
    }
