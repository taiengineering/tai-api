"""evidence_binding_engine.py — Evidence Binding (PHASE E)

field ↔ evidence 연결 + 무결성 검증.
orphan evidence는 숨기지 않고 식별 가능한 형태로 반환한다.
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
    """field의 evidence_ref / image 타입에 evidence 연결. 미사용 증빙은 orphan으로 표시."""
    bound = 0
    missing_evidence = []
    used_evidence_ids: set = set()

    evidence_by_type: dict = {}
    for ev in evidence_list:
        et = (ev.get("evidence_type") or "UNKNOWN").upper()
        if et not in evidence_by_type:
            evidence_by_type[et] = []
        evidence_by_type[et].append(ev)

    for section in sections:
        for field in section.get("fields", []):
            ft = field.get("field_type")
            if ft not in ("evidence_ref", "image"):
                continue

            code_key = (field.get("field_code") or "").upper()
            field_evidence = evidence_by_type.get(code_key, [])
            if not field_evidence:
                field_evidence = evidence_by_type.get("PHOTO", []) or evidence_by_type.get("DOCUMENT", [])

            if field_evidence:
                slice_ev = field_evidence[:5]
                field["evidence_bound"] = True
                field["evidence_count"] = len(field_evidence)
                field["evidence_ids"] = [e["id"] for e in slice_ev]
                field["evidence_records"] = slice_ev
                for e in slice_ev:
                    used_evidence_ids.add(e["id"])
                bound += 1
            else:
                field["evidence_bound"] = False
                field["evidence_count"] = 0
                field["evidence_ids"] = []
                field["evidence_records"] = []
                if field.get("required_level") == "MANDATORY":
                    missing_evidence.append(field.get("field_code"))

    orphan_evidence = [e for e in evidence_list if e.get("id") not in used_evidence_ids]

    evidence_bound_pct = 100.0
    need = sum(
        1
        for s in sections
        for f in s.get("fields", [])
        if f.get("field_type") in ("evidence_ref", "image") and f.get("required_level") == "MANDATORY"
    )
    if need:
        ok = sum(
            1
            for s in sections
            for f in s.get("fields", [])
            if f.get("field_type") in ("evidence_ref", "image")
            and f.get("required_level") == "MANDATORY"
            and f.get("evidence_bound")
        )
        evidence_bound_pct = round(100.0 * ok / need, 1)

    return {
        "bound_count": bound,
        "missing_evidence_fields": missing_evidence,
        "orphan_evidence": orphan_evidence[:20],
        "orphan_evidence_ids": [e["id"] for e in orphan_evidence[:20]],
        "orphan_evidence_count": len(orphan_evidence),
        "total_evidence": len(evidence_list),
        "evidence_bound_mandatory_pct": evidence_bound_pct,
    }
