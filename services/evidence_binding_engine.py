"""evidence_binding_engine.py — Evidence Binding (PHASE E)

field ↔ evidence 연결 + 무결성 검증.
"""
from db.supabase_client import get_supabase
from typing import Optional


def get_evidence_for_document(document_type: str, tenant_context: dict) -> list:
    """document_type에 연결된 evidence 목록 조회"""
    sb = get_supabase()
    facility_id = tenant_context.get("facility_id")
    if not facility_id:
        return []

    result = sb.table("runtime_compliance_evidence").select(
        "id, evidence_type, source_domain, evidence_status, uploaded_at, immutable_hash"
    ).eq("source_entity_id", facility_id).order("uploaded_at", desc=True).limit(50).execute()

    return result.data or []


def bind_evidence_to_fields(sections: list, evidence_list: list) -> dict:
    """field의 evidence_ref 타입 필드에 evidence 연결"""
    bound = 0
    orphan_evidence = []
    missing_evidence = []

    evidence_by_type = {}
    for ev in evidence_list:
        et = ev.get("evidence_type", "UNKNOWN")
        if et not in evidence_by_type:
            evidence_by_type[et] = []
        evidence_by_type[et].append(ev)

    for section in sections:
        for field in section.get("fields", []):
            if field.get("field_type") == "evidence_ref" or field.get("field_type") == "image":
                # evidence 연결 시도
                field_evidence = evidence_by_type.get(field.get("field_code", "").upper(), [])
                if not field_evidence:
                    # 일반 매칭
                    field_evidence = evidence_by_type.get("PHOTO", []) or evidence_by_type.get("DOCUMENT", [])

                if field_evidence:
                    field["evidence_bound"] = True
                    field["evidence_count"] = len(field_evidence)
                    field["evidence_ids"] = [e["id"] for e in field_evidence[:5]]
                    bound += 1
                else:
                    field["evidence_bound"] = False
                    field["evidence_count"] = 0
                    if field.get("required_level") == "MANDATORY":
                        missing_evidence.append(field.get("field_code"))

    # orphan evidence: 어떤 필드에도 연결 안 된 증빙
    used_types = set()
    for section in sections:
        for field in section.get("fields", []):
            if field.get("evidence_bound"):
                used_types.add(field.get("field_code", "").upper())

    for et, evs in evidence_by_type.items():
        if et not in used_types and et not in ("PHOTO", "DOCUMENT"):
            orphan_evidence.extend([e["id"] for e in evs])

    return {
        "bound_count": bound,
        "missing_evidence_fields": missing_evidence,
        "orphan_evidence_ids": orphan_evidence[:10],
        "total_evidence": len(evidence_list),
    }
