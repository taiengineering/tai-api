"""TAI 문서엔진 서비스 v1.2.0

Router = HTTP만, Service = 비즈니스 로직 (FastAPI import 금지)
절대 금지: auto fill, auto approve, inferred default,
           semantic match, fallback mapping, candidate→truth 승격

v1.1.0: Audit 수정 — field_key 검증, evidence 검증, generate audit 추가
v1.2.0: OBJ02-C2A — runtime key contract, PATCH merge semantics,
        resolve_runtime_document_state(), render_document_html()
"""
import re as _re
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

# UUID pattern for checklist key detection (36-char with dashes)
_UUID_RE = _re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    _re.IGNORECASE,
)
# Canonical checklist values (case-sensitive)
_CHECKLIST_VALUES = frozenset({"PASS", "FAIL", "NA"})


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
    schema = (
        sb.table("runtime_form_schema")
        .select("id,status")
        .eq("id", form_schema_id)
        .single()
        .execute()
    )
    if not schema.data:
        raise ValueError(f"schema not found: {form_schema_id}")
    if schema.data["status"] != "APPROVED_FOR_RUNTIME_USE":
        raise ValueError(
            f"schema not approved for runtime use: {form_schema_id} "
            f"(status={schema.data['status']})"
        )
    now = serialize_external_utc(now_kst())
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
    _EDITABLE = frozenset({"DRAFT", "IN_PROGRESS", "RETURNED_FOR_EDIT"})
    if before.data["status"] not in _EDITABLE:
        raise ValueError(
            f"document status '{before.data['status']}' does not allow editing; "
            f"editable: {sorted(_EDITABLE)}"
        )

    schema_id = before.data["form_schema_id"]
    now = serialize_external_utc(now_kst())
    update = {"updated_at": now}
    changes = {}

    # Guardrail: runtime_field field_key OR checklist UUID key만 저장 (C2A)
    if runtime_data_json is not None:
        _validate_runtime_keys(sb, schema_id, runtime_data_json)
        # PATCH merge semantics (C2A) — incoming keys overwrite, others preserved
        existing_json = before.data.get("runtime_data_json") or {}
        merged = {**existing_json, **runtime_data_json}
        update["runtime_data_json"] = merged
        changes["runtime_data_json"] = True

    # Guardrail: evidence_links의 linked_field_id 검증
    if evidence_links is not None:
        _validate_evidence_links(sb, schema_id, evidence_links)
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

    now = serialize_external_utc(now_kst())
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
# Internal — Validation
# ═══════════════════════════════════════════════════════

def _validate_field_keys(sb, schema_id: str, data_json: dict):
    """Deprecated wrapper: use _validate_runtime_keys() instead."""
    _validate_runtime_keys(sb, schema_id, data_json)


def _validate_runtime_keys(sb, schema_id: str, data_json: dict):
    """runtime_field field_key OR checklist UUID key만 허용.

    CONTRACT B (OBJ02-C2A):
    - field_key (str) — registered in runtime_field (non-UUID, non-signature)
    - checklist UUID (str UUID) — registered in runtime_checklist_item
      - value must be PASS | FAIL | NA (or null/None)
    - signature input_type field_keys: DENIED via PATCH — use apply-profile endpoint
    Unknown UUID-like keys not registered as checklist IDs → DENIED.
    """
    if not data_json:
        return

    # 1. Load allowed field_keys + input_type (to detect signature guard)
    res = (
        sb.table("runtime_field")
        .select("field_key,input_type")
        .eq("form_schema_id", schema_id)
        .execute()
    )
    allowed_field_keys = {r["field_key"] for r in (res.data or []) if r.get("field_key")}
    signature_field_keys = {
        r["field_key"] for r in (res.data or [])
        if r.get("field_key") and r.get("input_type") == "signature"
    }

    # 2. Load allowed checklist UUIDs
    cl_res = (
        sb.table("runtime_checklist_item")
        .select("id")
        .eq("form_schema_id", schema_id)
        .execute()
    )
    allowed_checklist_ids = {str(r["id"]) for r in (cl_res.data or []) if r.get("id")}

    unknown_keys = []
    for key, value in data_json.items():
        is_uuid = bool(_UUID_RE.match(key))
        if is_uuid:
            # UUID key: must be a registered checklist item
            if key not in allowed_checklist_ids:
                unknown_keys.append(key)
                continue
            # Validate checklist value: PASS / FAIL / NA or null
            if value is not None and value not in _CHECKLIST_VALUES:
                raise ValueError(
                    f"invalid checklist value for key {key!r}: "
                    f"must be one of {sorted(_CHECKLIST_VALUES)} or null, got {value!r}"
                )
        else:
            # Non-UUID key: must be a known field_key
            if key not in allowed_field_keys:
                unknown_keys.append(key)
                continue
            # Signature field guard: must use canonical apply-profile endpoint
            if key in signature_field_keys:
                raise ValueError(
                    f"signature field {key!r} cannot be set via PATCH; "
                    "use POST /document-engine/documents/{doc_id}"
                    f"/signature/{key}/apply-profile"
                )

    if unknown_keys:
        raise ValueError(
            f"unknown keys not in runtime_field or runtime_checklist_item: "
            f"{sorted(unknown_keys)}"
        )


def _validate_evidence_links(sb, schema_id: str, links: list):
    """evidence_links 내 linked_field_id가 runtime_evidence_field에 존재하는지 검증."""
    if not links:
        return
    field_ids = [
        el.get("linked_field_id")
        for el in links
        if isinstance(el, dict) and el.get("linked_field_id")
    ]
    if not field_ids:
        return
    res = (
        sb.table("runtime_evidence_field")
        .select("id")
        .eq("form_schema_id", schema_id)
        .execute()
    )
    allowed = {str(r["id"]) for r in (res.data or [])}
    unknown = set(field_ids) - allowed
    if unknown:
        raise ValueError(
            f"unknown evidence field_ids not in runtime_evidence_field: {sorted(unknown)}"
        )



# ═══════════════════════════════════════════════════════
# 8. Runtime Document State Resolution & Rendering (C2A)
# ═══════════════════════════════════════════════════════

def resolve_runtime_document_state(doc_id: str) -> dict:
    """Load full runtime document state for rendering.

    Returns:
        {
            "document": <runtime_document_data row>,
            "schema": <runtime_form_schema row>,
            "fields": [<runtime_field rows>],
            "checklists": [<runtime_checklist_item rows>],
            "evidence_fields": [<runtime_evidence_field rows>],
            "catalog": <document_forms row or None>,
        }

    Raises:
        ValueError: if document or schema not found.
    """
    sb = get_supabase()

    doc_res = (
        sb.table("runtime_document_data")
        .select("*")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not doc_res.data:
        raise ValueError(f"document not found: {doc_id}")
    document = doc_res.data

    schema_id = document.get("form_schema_id")
    if not schema_id:
        raise ValueError(f"document has no form_schema_id: {doc_id}")

    schema_res = (
        sb.table("runtime_form_schema")
        .select("*")
        .eq("id", schema_id)
        .single()
        .execute()
    )
    if not schema_res.data:
        raise ValueError(f"schema not found: {schema_id}")
    schema = schema_res.data

    fields = (
        sb.table("runtime_field")
        .select("*")
        .eq("form_schema_id", schema_id)
        .order("field_order")
        .execute()
    ).data or []

    checklists = (
        sb.table("runtime_checklist_item")
        .select("*")
        .eq("form_schema_id", schema_id)
        .order("item_order")
        .execute()
    ).data or []

    evidence_fields = (
        sb.table("runtime_evidence_field")
        .select("*")
        .eq("form_schema_id", schema_id)
        .execute()
    ).data or []

    catalog = None
    catalog_document_id = schema.get("catalog_document_id")
    if catalog_document_id:
        cat_res = (
            sb.table("document_forms")
            .select("*")
            .eq("id", catalog_document_id)
            .single()
            .execute()
        )
        catalog = cat_res.data

    return {
        "document": document,
        "schema": schema,
        "fields": fields,
        "checklists": checklists,
        "evidence_fields": evidence_fields,
        "catalog": catalog,
    }


def render_document_html(doc_id: str) -> str:
    """Render canonical HTML from runtime document state.

    CONTRACT C (OBJ02-C2A):
    1. Resolve full state via resolve_runtime_document_state()
    2. If confirmed (APPROVED_BY_HUMAN) and archive has rendered_body, return it.
    3. Otherwise render fresh via document_schema_renderer.build_render_artifacts()

    Does NOT call InspectionFetcher or TbmFetcher.
    """
    from services.document_schema_renderer import build_render_artifacts

    state = resolve_runtime_document_state(doc_id)
    document = state["document"]

    if document.get("status") in ("APPROVED_BY_HUMAN", "ARCHIVED"):
        doc_version = document.get("version")
        sb = get_supabase()
        archive_res = (
            sb.table("runtime_document_archive")
            .select("rendered_body,document_version")
            .eq("runtime_document_id", doc_id)
            .eq("document_version", doc_version)
            .execute()
        )
        if not archive_res.data:
            raise ValueError(
                f"confirmed document archive not found: "
                f"doc_id={doc_id}, version={doc_version}"
            )
        body = archive_res.data[0].get("rendered_body")
        if not body:
            raise ValueError(
                f"confirmed document archive has no rendered_body: "
                f"doc_id={doc_id}, version={doc_version}"
            )
        return body

    from services.document_signature_svc import resolve_signature_images_for_render

    sig_result = resolve_signature_images_for_render(
        runtime_data_json=document.get("runtime_data_json") or {},
        fields=state["fields"],
        document_id=str(document.get("id") or doc_id),
    )
    artifacts = build_render_artifacts(
        document=document,
        schema=state["schema"],
        fields=state["fields"],
        checklists=state["checklists"],
        signature_images=sig_result.get("images"),
        signature_manifest=sig_result.get("manifest"),
    )
    return artifacts["rendered_body"]


# ═══════════════════════════════════════════════════════
# Internal — Audit & Approval
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
