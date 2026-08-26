"""WP-PERSISTENCE-03 — Web View Composer (READ-ONLY).

OBJ-01 KNOT-2: 현재 점검값의 source 는 base ledger 직독이 아니라 Effective Record
Resolver(fn_resolve_inspection_record) 이다. 이 모듈은 resolver 가 돌려준 current
effective record 를 소비해 explicit set/schema resolution → GENERAL presentation
schema View Model 을 lazy compose 한다.

아키텍처 (STEP-0 REV-1 SEALED + KNOT-2 read cutover):
    inspection(effective) → inspection_set (P-A primary / P-B corroboration)
    inspection_set → runtime_inspection_bridge → runtime_form_schema (approved + GENERAL v1 support gate)
    → GENERAL 5-field code contract View Model (Option B)

READ-ONLY invariant:
    이 모듈은 어떤 테이블에도 write 하지 않는다 (insert/update/delete/upsert/DDL/storage 금지).
    current effective record 는 read-only resolver(fn_resolve_inspection_record) 를 통해
    조회하며, base ledger(safety_inspections / safety_inspection_results) 를 직접 읽지 않는다.
    runtime_document_data / generated_document 를 생성하지 않는다. PDF/HTML/renderer 없음.

AUTH invariant:
    이 서비스는 auth 를 담당하지 않는다.
    PUBLIC CALLER MUST perform inspection ownership/scope guard
    (inspection_checklist._ensure_inspection_own 계열 또는 동등한 company/factory scoped guard)
    BEFORE calling compose_inspection_view(). 이 STEP 에는 router 가 없다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.inspection_record_resolver import (
    InspectionRecordError,
    resolve_inspection_record,
)

# ── 고정 상수 (SEALED contract) ────────────────────────────────────
GENERAL_SCHEMA_ID = "dc79ac3c-388c-42dc-b029-3dd9bda54a47"
GENERAL_FORM_CODE = "GEN-INSPECT-RESULT-001"
GENERAL_SCHEMA_VERSION = 1
GENERAL_FIELD_COUNT = 5
APPROVED_STATUS = "APPROVED_FOR_RUNTIME_USE"

# GENERAL 5-field code contract (Option B) — runtime_field 를 동적으로 읽지 않는다.
GENERAL_FIELD_KEYS = (
    "inspection_subject",
    "inspected_at",
    "inspection_title",
    "inspector_display",
    "inspection_results",
)
REQUIRED_BY_HUMAN_FIELDS = ("inspection_subject", "inspected_at", "inspection_results")


class InspectionViewComposeError(Exception):
    """Composer domain exception. HTTP mapping 은 future router 책임."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _rows(resp: Any) -> List[Dict[str, Any]]:
    """supabase execute() 응답에서 data 리스트를 안전하게 추출 (write 아님)."""
    data = getattr(resp, "data", None)
    if data is None and isinstance(resp, dict):
        data = resp.get("data")
    return list(data or [])


def compose_inspection_view(inspection_id: str, supabase: Any = None) -> Dict[str, Any]:
    """inspection 1건을 GENERAL presentation View Model 로 compose (READ-ONLY).

    Args:
        inspection_id: safety_inspections.id
        supabase: 주입된 supabase client (테스트/격리용). None 이면 get_supabase().

    Returns:
        View Model dict (top-level contract 은 STEP-0 VIEW_MODEL_CONTRACT 정본).

    Raises:
        InspectionViewComposeError: 결정적 오류(code 보유). REQUIRED_SOURCE_FIELD_MISSING 는
            예외가 아니라 completeness 로만 표현된다.
    """
    if supabase is None:
        from db.supabase_client import get_supabase  # lazy: 테스트에서 db 패키지 불필요

        supabase = get_supabase()

    # ── 1) current effective record (base ledger + journal folding, READ-ONLY) ─
    #      base 직독(safety_inspections/safety_inspection_results) 을 하지 않고
    #      단일 정본 resolver 를 통해 현재 유효 레코드를 얻는다.
    try:
        record = resolve_inspection_record(inspection_id, supabase)
    except InspectionRecordError as exc:
        raise InspectionViewComposeError(exc.code, exc.detail)

    active = record.get("is_active")
    if active is False:
        raise InspectionViewComposeError("INSPECTION_INACTIVE", inspection_id)
    if not isinstance(active, bool):
        raise InspectionViewComposeError("SOURCE_INTEGRITY_ERROR", f"inspection is_active {active!r}")

    insp = {
        "id": record.get("inspection_id"),
        "assignment_id": record.get("assignment_id"),
        "asset_id": record.get("asset_id"),
        "inspector_id": record.get("inspector_id"),
        "inspection_date": record.get("inspection_date"),
        "factory_id": record.get("factory_id"),
    }
    if insp["id"] is None:
        raise InspectionViewComposeError("SOURCE_INTEGRITY_ERROR", "effective record missing inspection_id")

    # ── 2) effective ACTIVE results 만 소비 (result deactivation = 유일 정상 제외 사유) ─
    raw_results = record.get("results")
    if not isinstance(raw_results, list):
        raise InspectionViewComposeError("SOURCE_INTEGRITY_ERROR", "effective results not a list")
    results: List[Dict[str, Any]] = []
    for e in raw_results:
        ra = e.get("is_active")
        if not isinstance(ra, bool):
            raise InspectionViewComposeError(
                "SOURCE_INTEGRITY_ERROR", f"result is_active {ra!r} (result {e.get('result_id')})"
            )
        if ra is False:
            continue  # inactive result 는 Web View 에서 제외 (silent drop 아님: deactivation 정본)
        results.append(
            {
                "id": e.get("result_id"),
                "inspection_id": insp["id"],
                "inspection_set_item_id": e.get("inspection_set_item_id"),
                "item_name": e.get("item_name"),
                "result_code": e.get("result_code"),  # effective canonical code (재해석 금지)
                "value_text": e.get("value_text"),
                "value_number": e.get("value_number"),
                "note": e.get("note"),
                "checked_at": e.get("checked_at"),
                "photo_url": e.get("photo_url"),
                "photo_urls": e.get("photo_urls"),
                "created_at": e.get("created_at"),
            }
        )

    # ── 3) set_item batch 조회 (N+1 금지) ────────────────────────────
    set_item_ids = sorted({r["inspection_set_item_id"] for r in results if r.get("inspection_set_item_id")})
    set_items: Dict[str, Dict[str, Any]] = {}
    if set_item_ids:
        si_rows = _rows(
            supabase.table("inspection_set_items")
            .select("id, inspection_set_id, item_seq, item_name")
            .in_("id", set_item_ids)
            .execute()
        )
        set_items = {row["id"]: row for row in si_rows}
        # non-null set_item_id 인데 master row 없음 → dangling secondary identity
        for r in results:
            sid = r.get("inspection_set_item_id")
            if sid and sid not in set_items:
                raise InspectionViewComposeError(
                    "RESULT_ITEM_UNRESOLVED", f"dangling set_item_id {sid} (result {r.get('id')})"
                )

    # ── 4) INSPECTION → SET resolution (P-A primary / P-B corroboration) ──────
    final_set_id = _resolve_set_id(insp, results, set_items, supabase)

    # ── 5) inspection_set 조회 (title) ─────────────────────────────
    set_rows = _rows(
        supabase.table("inspection_sets")
        .select("id, inspection_set_name")
        .eq("id", final_set_id)
        .limit(1)
        .execute()
    )
    if not set_rows:
        raise InspectionViewComposeError("SOURCE_INTEGRITY_ERROR", f"inspection_set {final_set_id} missing")
    inspection_title = set_rows[0].get("inspection_set_name")

    # ── 6) SET → PRESENTATION SCHEMA (bridge) ────────────────────────
    bridge_rows = _rows(
        supabase.table("runtime_inspection_bridge")
        .select("id, inspection_set_id, runtime_form_schema_id")
        .eq("inspection_set_id", final_set_id)
        .execute()
    )
    if len(bridge_rows) == 0:
        raise InspectionViewComposeError("BRIDGE_NOT_FOUND", final_set_id)
    if len(bridge_rows) > 1:
        raise InspectionViewComposeError("SOURCE_INTEGRITY_ERROR", f"bridge rows={len(bridge_rows)} for set {final_set_id}")
    schema_id = bridge_rows[0].get("runtime_form_schema_id")
    if schema_id is None:
        raise InspectionViewComposeError("PRESENTATION_SCHEMA_NOT_MAPPED", final_set_id)

    # ── 7) SCHEMA gate + GENERAL v1 support gate ───────────────────────
    schema_rows = _rows(
        supabase.table("runtime_form_schema")
        .select("id, status, version, field_count, source_trace")
        .eq("id", schema_id)
        .limit(1)
        .execute()
    )
    if not schema_rows:
        raise InspectionViewComposeError("SCHEMA_NOT_FOUND", schema_id)
    schema = schema_rows[0]
    if schema.get("status") != APPROVED_STATUS:
        raise InspectionViewComposeError("SCHEMA_NOT_APPROVED", f"{schema_id} status={schema.get('status')}")

    source_trace = schema.get("source_trace") or {}
    form_code = source_trace.get("form_code") if isinstance(source_trace, dict) else None
    if (
        schema.get("id") != GENERAL_SCHEMA_ID
        or form_code != GENERAL_FORM_CODE
        or schema.get("version") != GENERAL_SCHEMA_VERSION
        or schema.get("field_count") != GENERAL_FIELD_COUNT
    ):
        raise InspectionViewComposeError(
            "UNSUPPORTED_PRESENTATION_SCHEMA",
            f"id={schema.get('id')} form_code={form_code} version={schema.get('version')} field_count={schema.get('field_count')}",
        )

    # ── 8) top-level fields ──────────────────────────────────────
    inspection_subject = _resolve_inspection_subject(insp, supabase)
    inspected_at = insp.get("inspection_date")
    inspector_display = _resolve_inspector_display(insp, supabase)

    # ── 9) inspection_results (source fidelity, item_name contract) ───────────
    result_rows = [_compose_result_row(r, set_items) for r in results]
    result_rows = _deterministic_sort(result_rows, results, set_items)

    # ── 10) completeness ───────────────────────────────────────
    missing: List[str] = []
    if inspection_subject is None:
        missing.append("inspection_subject")
    if inspected_at is None:
        missing.append("inspected_at")
    if len(result_rows) == 0:
        missing.append("inspection_results")

    return {
        "inspection_id": insp["id"],
        "inspection_set_id": final_set_id,
        "schema_id": schema_id,
        "form_code": GENERAL_FORM_CODE,
        "schema_version": GENERAL_SCHEMA_VERSION,
        "fields": {
            "inspection_subject": inspection_subject,
            "inspected_at": inspected_at,
            "inspection_title": inspection_title,
            "inspector_display": inspector_display,
            "inspection_results": result_rows,
        },
        "completeness": {
            "is_complete": len(missing) == 0,
            "missing_required_fields": missing,
        },
    }


# ── set resolution ─────────────────────────────────────────────
def _resolve_set_id(
    insp: Dict[str, Any],
    results: List[Dict[str, Any]],
    set_items: Dict[str, Dict[str, Any]],
    supabase: Any,
) -> str:
    # P-A: assignment_id → work_schedules.id → work_schedules.inspection_set_id
    pa_set: Optional[str] = None
    assignment_id = insp.get("assignment_id")
    if assignment_id:
        ws_rows = _rows(
            supabase.table("work_schedules")
            .select("id, inspection_set_id")
            .eq("id", assignment_id)
            .limit(1)
            .execute()
        )
        if ws_rows and ws_rows[0].get("inspection_set_id"):
            pa_set = ws_rows[0]["inspection_set_id"]

    # P-B: result.set_item_id → inspection_set_items.inspection_set_id (resolvable set들)
    pb_sets = {
        set_items[r["inspection_set_item_id"]]["inspection_set_id"]
        for r in results
        if r.get("inspection_set_item_id") and set_items[r["inspection_set_item_id"]].get("inspection_set_id")
    }

    if pa_set is not None:
        # corroboration: 해소되는 P-B set 은 모두 P-A 와 같아야 함
        for s in pb_sets:
            if s != pa_set:
                raise InspectionViewComposeError(
                    "SOURCE_INTEGRITY_ERROR", f"P-A {pa_set} != P-B {s}"
                )
        return pa_set

    # P-A unresolved → P-B fallback (조건 전부 충족 시에만)
    if len(results) == 0:
        raise InspectionViewComposeError("INSPECTION_SET_UNRESOLVED", "no assignment set + no results")
    if any(not r.get("inspection_set_item_id") for r in results):
        raise InspectionViewComposeError(
            "INSPECTION_SET_UNRESOLVED",
            "P-A unresolved; >=1 result has null set_item_id (P-B fallback requires all non-null)",
        )
    # 이 지점: 모든 set_item_id non-null, dangling 은 이미 상위에서 걸러짐 → 전부 valid
    resolved = {
        set_items[r["inspection_set_item_id"]].get("inspection_set_id") for r in results
    }
    if any(s is None for s in resolved):
        raise InspectionViewComposeError("INSPECTION_SET_UNRESOLVED", "set_item with null inspection_set_id")
    if len(resolved) > 1:
        raise InspectionViewComposeError("MIXED_INSPECTION_SET_SOURCE", f"distinct sets={sorted(resolved)}")
    if len(resolved) != 1:
        raise InspectionViewComposeError("INSPECTION_SET_UNRESOLVED", "no resolvable set")
    return next(iter(resolved))


# ── top-level field resolvers ────────────────────────────────────
def _resolve_inspection_subject(insp: Dict[str, Any], supabase: Any) -> Optional[str]:
    asset_id = insp.get("asset_id")
    if not asset_id:
        return None
    rows = _rows(
        supabase.table("equipment_assets")
        .select("id, asset_name")
        .eq("id", asset_id)
        .limit(1)
        .execute()
    )
    if not rows:
        raise InspectionViewComposeError("SOURCE_INTEGRITY_ERROR", f"equipment_assets {asset_id} missing")
    return rows[0].get("asset_name")  # asset_name NULL → None (completeness missing)


def _resolve_inspector_display(insp: Dict[str, Any], supabase: Any) -> Optional[str]:
    inspector_id = insp.get("inspector_id")
    if not inspector_id:
        return None
    rows = _rows(
        supabase.table("users").select("id, name").eq("id", inspector_id).limit(1).execute()
    )
    if not rows:
        raise InspectionViewComposeError("SOURCE_INTEGRITY_ERROR", f"users {inspector_id} missing")
    return rows[0].get("name")  # name NULL → None (NOT_REQUIRED)


# ── result row / item_name contract ──────────────────────────────
def _resolve_item_name(r: Dict[str, Any], set_items: Dict[str, Dict[str, Any]]) -> Optional[str]:
    result_name = r.get("item_name")
    sid = r.get("inspection_set_item_id")
    set_item = set_items.get(sid) if sid else None

    if result_name is not None:
        if set_item is None:
            return result_name  # CASE A
        master_name = set_item.get("item_name")
        if result_name == master_name:
            return result_name  # CASE B
        raise InspectionViewComposeError(  # CASE C
            "SOURCE_INTEGRITY_ERROR",
            f"item_name mismatch result={result_name!r} master={master_name!r} (result {r.get('id')})",
        )
    # result_name is None
    if set_item is not None:
        return set_item.get("item_name")  # CASE D
    raise InspectionViewComposeError(  # CASE E
        "RESULT_ITEM_UNRESOLVED", f"result {r.get('id')} has null item_name and null set_item_id"
    )


def _compose_result_row(r: Dict[str, Any], set_items: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "result_id": r.get("id"),
        "set_item_id": r.get("inspection_set_item_id"),
        "item_name": _resolve_item_name(r, set_items),
        "raw_code": r.get("result_code"),  # effective canonical code 그대로 (upper/normalize/ok-bad 금지)
        "value_text": r.get("value_text"),
        "value_number": r.get("value_number"),
        "note": r.get("note"),
        "checked_at": r.get("checked_at"),
        "photo_url": r.get("photo_url"),
        "photo_urls": r.get("photo_urls"),  # NULL↔[] 정규화 금지
    }


def _deterministic_sort(
    rows: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    set_items: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """item_seq ASC NULLS LAST → created_at ASC NULLS LAST → result.id ASC.

    item_seq/created_at 는 sorting metadata (output field 아님). DB implicit order 미의존.
    """
    by_id = {r.get("id"): r for r in results}

    def key(row: Dict[str, Any]):
        rid = row["result_id"]
        src = by_id.get(rid, {})
        sid = src.get("inspection_set_item_id")
        seq = set_items.get(sid, {}).get("item_seq") if sid else None
        created = src.get("created_at")
        return (
            (seq is None, seq if seq is not None else 0),
            (created is None, created if created is not None else ""),
            str(rid),
        )

    return sorted(rows, key=key)
