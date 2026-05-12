"""TAI 문서엔진 서비스 v1.0.0

Router = HTTP만, Service = 비즈니스 로직 (FastAPI import 금지)
절대 금지: auto fill, auto approve, inferred default,
           semantic match, fallback mapping, candidate→truth 승격
"""
from datetime import datetime, timezone
from db.supabase_client import get_supabase


# ═══════════════════════════════════════════════════════
# 1. Runtime Form Schema 조회
# ═══════════════════════════════════════════════════════

def list_form_schemas(
    document_family: str = None,
    form_type: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    sb = get_supabase()
    q = sb.table("runtime_form_schema").select("*", count="exact")
    if document_family:
        q = q.eq("document_family", document_family)
    if form_type:
        q = q.eq("form_type", form_type)
    if status:
        q = q.eq("status", status)
    offset = (page - 1) * page_size
    q = q.order("document_family").order("form_name")
    q = q.range(offset, offset + page_size - 1)
    res = q.execute()
    return {
        "items": res.data or [],
        "total": res.count or 0,
        "page": page,
        "page_size": page_size,
    }


def get_form_schema_detail(schema_id: str) -> dict:
    """schema + fields + checklists + evidence_fields 통합 조회"""
    sb = get_supabase()
    schema = (
        sb.table("runtime_form_schema")
        .select("*")
        .eq("id", schema_id)
        .single()
        .execute()
    )
    if not schema.data:
        return None
    fields = (
        sb.table("runtime_field")
        .select("*")
        .eq("form_schema_id", schema_id)
        .order("field_order")
        .execute()
    )
    checklists = (
        sb.table("runtime_checklist_item")
        .select("*")
        .eq("form_schema_id", schema_id)
        .order("item_order")
        .execute()
    )
    evidence = (
        sb.table("runtime_evidence_field")
        .select("*")
        .eq("form_schema_id", schema_id)
        .execute()
    )
    return {
        "schema": schema.data,
        "fields": fields.data or [],
        "checklists": checklists.data or [],
        "evidence_fields": evidence.data or [],
    }


# ═══════════════════════════════════════════════════════
# 2. Runtime Document CRUD
# ═══════════════════════════════════════════════════════

def create_document(
    form_schema_id: str,
    factory_id: str = None,
    company_id: str = None,
    created_by: str = None,
) -> dict:
    sb = get_supabase()
    # schema 존재 확인
    schema = (
        sb.table("runtime_form_schema")
        .select("id,status")
        .eq("id", form_schema_id)
        .single()
        .execute()
    )
    if not schema.data:
        raise ValueError(f"schema not found: {form_schema_id}")
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "form_schema_id": form_schema_id,
        "runtime_data_json": {},
        "evidence_links": [],
        "status": "DRAFT",
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    if factory_id:
        record["factory_id"] = factory_id
    if company_id:
        record["company_id"] = company_id
    if created_by:
        record["created_by"] = created_by
    res = sb.table("runtime_document_data").insert(record).execute()
    doc = res.data[0] if res.data else {}
    if doc:
        _audit(sb, doc["id"], "CREATED", created_by, None, doc)
    return doc


def get_document(doc_id: str) -> dict:
    sb = get_supabase()
    res = (
        sb.table("runtime_document_data")
        .select("*")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    return res.data


def list_documents(
    factory_id: str = None,
    company_id: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    sb = get_supabase()
    q = sb.table("runtime_document_data").select(
        "id,form_schema_id,factory_id,company_id,status,version,"
        "created_at,updated_at",
        count="exact",
    )
    if factory_id:
        q = q.eq("factory_id", factory_id)
    if company_id:
        q = q.eq("company_id", company_id)
    if status:
        q = q.eq("status", status)
    offset = (page - 1) * page_size
    q = q.order("updated_at", desc=True).range(offset, offset + page_size - 1)
    res = q.execute()
    return {
        "items": res.data or [],
        "total": res.count or 0,
        "page": page,
        "page_size": page_size,
    }


def update_document(
    doc_id: str,
    runtime_data_json: dict = None,
    evidence_links: list = None,
    updated_by: str = None,
) -> dict:
    sb = get_supabase()
    before = (
        sb.table("runtime_document_data")
        .select("*")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not before.data:
        raise ValueError("document not found")
    if before.data["status"] == "ARCHIVED":
        raise ValueError("ARCHIVED document cannot be modified")
    now = datetime.now(timezone.utc).isoformat()
    update = {"updated_at": now}
    changes = {}
    if runtime_data_json is not None:
        update["runtime_data_json"] = runtime_data_json
        changes["runtime_data_json"] = True
    if evidence_links is not None:
        update["evidence_links"] = evidence_links
        changes["evidence_links"] = True
    if updated_by:
        update["updated_by"] = updated_by
    res = (
        sb.table("runtime_document_data")
        .update(update)
        .eq("id", doc_id)
        .execute()
    )
    doc = res.data[0] if res.data else {}
    if doc:
        _audit(sb, doc_id, "FIELD_EDIT", updated_by, before.data, doc, changes)
    return doc


# ═══════════════════════════════════════════════════════
# 3. 상태 전이 (State Machine)
# ═══════════════════════════════════════════════════════

def get_transitions() -> list:
    sb = get_supabase()
    res = (
        sb.table("runtime_state_transition_rule")
        .select("*")
        .order("from_status")
        .execute()
    )
    return res.data or []


def change_status(
    doc_id: str,
    to_status: str,
    actor_id: str = None,
    comment: str = None,
) -> dict:
    sb = get_supabase()
    doc = (
        sb.table("runtime_document_data")
        .select("*")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not doc.data:
        raise ValueError("document not found")
    from_status = doc.data["status"]

    # 전이 규칙 확인 — runtime_state_transition_rule 기준만
    rule = (
        sb.table("runtime_state_transition_rule")
        .select("*")
        .eq("from_status", from_status)
        .eq("to_status", to_status)
        .execute()
    )
    if not rule.data:
        raise ValueError(
            f"transition not allowed: {from_status} -> {to_status}"
        )
    rule_row = rule.data[0]

    # Guardrail: reviewer 필수 / comment 필수 검증
    if rule_row["requires_reviewer"] and not actor_id:
        raise ValueError("reviewer_id required for this transition")
    if rule_row["requires_comment"] and not comment:
        raise ValueError("review_comment required for this transition")

    now = datetime.now(timezone.utc).isoformat()
    update = {"status": to_status, "updated_at": now}

    if to_status == "SUBMITTED_FOR_REVIEW":
        update["submitted_at"] = now
        if actor_id:
            update["submitted_by"] = actor_id
    if to_status in (
        "APPROVED_BY_HUMAN",
        "REJECTED_BY_HUMAN",
        "RETURNED_FOR_EDIT",
    ):
        update["reviewed_at"] = now
        update["reviewed_by"] = actor_id
        if comment:
            update["review_comment"] = comment
    if to_status == "ARCHIVED":
        update["archived_at"] = now

    res = (
        sb.table("runtime_document_data")
        .update(update)
        .eq("id", doc_id)
        .execute()
    )
    after = res.data[0] if res.data else {}
    _audit(sb, doc_id, "STATUS_CHANGE", actor_id, doc.data, after)

    # 승인/반려 시 approval 스냅샷
    if to_status in ("APPROVED_BY_HUMAN", "REJECTED_BY_HUMAN") and actor_id:
        action = "APPROVE" if to_status == "APPROVED_BY_HUMAN" else "REJECT"
        _approval(sb, doc_id, actor_id, action, comment, doc.data)

    return after


# ═══════════════════════════════════════════════════════
# 4. Evidence
# ═══════════════════════════════════════════════════════

def link_evidence(
    doc_id: str,
    evidence_type: str,
    storage_path: str,
    file_name: str = None,
    file_size: int = None,
    mime_type: str = None,
    linked_field_id: str = None,
    uploaded_by: str = None,
) -> dict:
    sb = get_supabase()
    record = {
        "document_data_id": doc_id,
        "evidence_type": evidence_type,
        "storage_path": storage_path,
        "status": "LINKED",
    }
    if file_name:
        record["file_name"] = file_name
    if file_size is not None:
        record["file_size"] = file_size
    if mime_type:
        record["mime_type"] = mime_type
    if linked_field_id:
        record["linked_field_id"] = linked_field_id
    if uploaded_by:
        record["uploaded_by"] = uploaded_by
    res = sb.table("evidence_vault_link").insert(record).execute()
    ev = res.data[0] if res.data else {}
    if ev:
        _audit(sb, doc_id, "EVIDENCE_UPLOAD", uploaded_by, None, ev)
    return ev


def list_evidence(doc_id: str) -> list:
    sb = get_supabase()
    res = (
        sb.table("evidence_vault_link")
        .select("*")
        .eq("document_data_id", doc_id)
        .order("uploaded_at", desc=True)
        .execute()
    )
    return res.data or []


# ═══════════════════════════════════════════════════════
# 5. Generated Document
# ═══════════════════════════════════════════════════════

def generate_document(doc_id: str, export_type: str = "HTML") -> dict:
    """입력된 값만 사용. auto fill / inferred summary 금지."""
    sb = get_supabase()
    doc = (
        sb.table("runtime_document_data")
        .select("*")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not doc.data:
        raise ValueError("document not found")
    record = {
        "runtime_document_id": doc_id,
        "form_schema_id": doc.data.get("form_schema_id"),
        "export_type": export_type,
        "status": "GENERATED",
    }
    res = sb.table("generated_document").insert(record).execute()
    return res.data[0] if res.data else {}


def list_generated(doc_id: str) -> list:
    sb = get_supabase()
    res = (
        sb.table("generated_document")
        .select("*")
        .eq("runtime_document_id", doc_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


# ═══════════════════════════════════════════════════════
# 6. Metrics
# ═══════════════════════════════════════════════════════

def get_metrics() -> list:
    sb = get_supabase()
    res = sb.table("v_runtime_metrics").select("*").execute()
    return res.data or []


def get_metrics_by_factory(factory_id: str) -> list:
    sb = get_supabase()
    res = (
        sb.table("v_runtime_metrics_by_factory")
        .select("*")
        .eq("factory_id", factory_id)
        .execute()
    )
    return res.data or []


# ═══════════════════════════════════════════════════════
# 7. Audit Log
# ═══════════════════════════════════════════════════════

def get_audit_log(doc_id: str) -> list:
    sb = get_supabase()
    res = (
        sb.table("runtime_lifecycle_audit_log")
        .select("*")
        .eq("runtime_document_id", doc_id)
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


# ═══════════════════════════════════════════════════════
# Internal
# ═══════════════════════════════════════════════════════

def _audit(sb, doc_id, action, actor_id, before, after, field_changes=None):
    """모든 상태 변경은 audit log 기록"""
    try:
        sb.table("runtime_lifecycle_audit_log").insert(
            {
                "runtime_document_id": doc_id,
                "action": action,
                "actor_id": actor_id,
                "before_state": before,
                "after_state": after,
                "field_changes": field_changes,
                "rollback_available": True,
            }
        ).execute()
    except Exception:
        pass  # audit 실패가 본 동작을 막지 않음


def _approval(sb, doc_id, reviewer_id, action, comment, doc_data):
    """승인/반려 시 스냅샷 저장. rollback 가능."""
    try:
        sb.table("runtime_document_approval").insert(
            {
                "runtime_document_id": doc_id,
                "reviewer_id": reviewer_id,
                "review_action": action,
                "review_comment": comment,
                "runtime_snapshot": doc_data.get("runtime_data_json"),
                "evidence_snapshot": doc_data.get("evidence_links"),
                "source_trace_snapshot": {},
                "rollback_available": True,
            }
        ).execute()
    except Exception:
        pass
