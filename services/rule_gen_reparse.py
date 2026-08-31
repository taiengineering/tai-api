"""reparse-master 백그라운드 처리 로직 — rule_gen_svc.py에서 분리."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from services.rule_gen_ai import _call_claude_messages, _fetch_few_shot_examples
from services.rule_gen_builders import _build_reparse_prompt, _pick_reparse_targets
from services.rule_gen_helpers import _is_blank, _normalize_submit_org_code, sanitize_master_patch
from services.time import now_kst, serialize_external_utc


async def _run_reparse_background(
    job_id: str,
    sector: str,
    limit_count: int,
    fill_empty_only: bool,
    rule_ids: List[str],
    *,
    get_supabase_fn,
    build_full_context_fn,
    validate_master_runner,
    submit_org_labels: Dict[str, str],
    sonnet_model: str,
    api_key: str,
    extract_json_payload_fn,
    logger,
):
    """백그라운드에서 master 룰을 1건씩 Sonnet으로 재파싱."""
    supabase = get_supabase_fn()
    try:
        q = supabase.table("master_building_legal_rules").select("*").eq("is_active", True)
        if sector and sector != "ALL":
            q = q.eq("sector", sector)
        if rule_ids:
            q = q.in_("rule_id", rule_ids)
        rows = q.limit(max(limit_count * 3, 50)).execute().data or []
        targets = _pick_reparse_targets(rows, limit_count)
        supabase.table("reparse_job_log").update({"total_targeted": len(targets)}).eq("job_id", job_id).execute()

        processed = updated = skipped = errors_count = 0
        error_details: List[dict] = []
        changed_fields_total: Dict[str, int] = {}

        for row in targets:
            rid = row.get("rule_id") or ""
            law_name = row.get("law_name") or ""
            law_article = row.get("law_article") or ""

            if not law_name or not law_article:
                skipped += 1
                processed += 1
                supabase.table("reparse_job_log").update(
                    {"processed": processed, "skipped": skipped}
                ).eq("job_id", job_id).execute()
                await asyncio.sleep(3)
                continue

            try:
                full_context = await build_full_context_fn(law_name, law_article)
                few_shots = await _fetch_few_shot_examples(supabase, law_name, limit=3)
                prompt = _build_reparse_prompt(row, full_context, few_shots)
                parsed = await _call_claude_messages(
                    "빈 필드 보강 전용 리라이팅 모델입니다. JSON object 1개만 반환하세요.",
                    prompt,
                    sonnet_model,
                    extract_json_payload_fn,
                    api_key,
                    max_tokens=1800,
                    timeout=90,
                )
                if not isinstance(parsed, dict):
                    skipped += 1
                    processed += 1
                    supabase.table("reparse_job_log").update(
                        {"processed": processed, "skipped": skipped}
                    ).eq("job_id", job_id).execute()
                    await asyncio.sleep(3)
                    continue

                patch: Dict[str, Any] = {}
                for key, value in parsed.items():
                    if key not in row:
                        continue
                    if fill_empty_only and not _is_blank(row.get(key)):
                        continue
                    if _is_blank(value):
                        continue
                    if row.get(key) != value:
                        patch[key] = value
                        changed_fields_total[key] = changed_fields_total.get(key, 0) + 1

                if "submit_org_code" in patch:
                    patch["submit_org_code"] = _normalize_submit_org_code(patch["submit_org_code"])
                    if not patch["submit_org_code"]:
                        patch.pop("submit_org_code", None)

                if patch:
                    patch["updated_at"] = serialize_external_utc(now_kst())
                    sanitize_master_patch(patch)
                    supabase.table("master_building_legal_rules").update(patch).eq("id", row["id"]).execute()
                    updated += 1
                else:
                    skipped += 1
                processed += 1

            except Exception as e:
                errors_count += 1
                processed += 1
                error_details.append({"rule_id": rid, "error": str(e)[:200]})
                logger.warning(f"[reparse] {rid} 에러: {e}")

            supabase.table("reparse_job_log").update({
                "processed": processed, "updated": updated, "skipped": skipped,
                "errors": errors_count, "error_details": error_details[-20:],
                "changed_fields": changed_fields_total,
            }).eq("job_id", job_id).execute()
            await asyncio.sleep(3)

        # 완료 → validate-master
        validate_data = None
        try:
            validate_data = validate_master_runner(supabase, sector or "ALL", submit_org_labels).get("data")
        except Exception as e:
            logger.warning(f"[reparse] validate-master 실패: {e}")

        supabase.table("reparse_job_log").update({
            "status": "COMPLETED",
            "completed_at": serialize_external_utc(now_kst()),
            "processed": processed, "updated": updated, "skipped": skipped,
            "errors": errors_count, "error_details": error_details,
            "changed_fields": {**changed_fields_total, "_validation": validate_data or {}},
        }).eq("job_id", job_id).execute()
        logger.info(f"[reparse] job {job_id} 완료: {processed}/{len(targets)} 처리, {updated} 수정, {errors_count} 에러")

    except Exception as e:
        logger.error(f"[reparse] job {job_id} 실패: {e}")
        try:
            supabase.table("reparse_job_log").update({
                "status": "FAILED",
                "completed_at": serialize_external_utc(now_kst()),
                "error_details": [{"error": str(e)[:500]}],
            }).eq("job_id", job_id).execute()
        except Exception:
            pass


def run_reparse_master(
    supabase, body, background_tasks, *,
    get_supabase_fn, build_full_context_fn, validate_master_runner,
    submit_org_labels: Dict[str, str], sonnet_model: str, api_key: str,
    extract_json_payload_fn, logger, internal_secret: str,
):
    """POST /reparse-master — 즉시 job_id 반환, 백그라운드 처리 시작."""
    if body.secret != internal_secret:
        raise PermissionError("내부 전용 엔드포인트")
    sector = (body.sector or "").strip().upper()
    job_id = str(uuid.uuid4())
    supabase.table("reparse_job_log").insert({"job_id": job_id, "sector": sector or "ALL", "status": "RUNNING"}).execute()
    background_tasks.add_task(
        _run_reparse_background,
        job_id, sector, body.limit, body.fill_empty_only, body.rule_ids or [],
        get_supabase_fn=get_supabase_fn,
        build_full_context_fn=build_full_context_fn,
        validate_master_runner=validate_master_runner,
        submit_org_labels=submit_org_labels,
        sonnet_model=sonnet_model,
        api_key=api_key,
        extract_json_payload_fn=extract_json_payload_fn,
        logger=logger,
    )
    return {
        "status": "accepted",
        "job_id": job_id,
        "message": f"재파싱 작업이 시작됐습니다. sector={sector or 'ALL'}, limit={body.limit}",
        "check_status": f"/law-rule-generator/reparse-master/status/{job_id}",
    }


def get_reparse_status(supabase, job_id: str) -> dict:
    """GET /reparse-master/status/{job_id}."""
    res = supabase.table("reparse_job_log").select("*").eq(
        "job_id", job_id
    ).order("created_at", desc=True).limit(1).execute()
    if not res.data:
        raise LookupError("해당 job_id를 찾을 수 없습니다")
    job = res.data[0]
    total = job.get("total_targeted", 0)
    processed = job.get("processed", 0)
    progress_pct = round((processed / total) * 100, 1) if total > 0 else 0
    return {
        "status": "success",
        "data": {
            "job_id": job_id,
            "job_status": job.get("status"),
            "sector": job.get("sector"),
            "total_targeted": total,
            "processed": processed,
            "updated": job.get("updated", 0),
            "skipped": job.get("skipped", 0),
            "errors": job.get("errors", 0),
            "progress_pct": progress_pct,
            "changed_fields": job.get("changed_fields", {}),
            "error_details": job.get("error_details", []),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
        },
    }


def get_reparse_jobs(supabase, limit: int = 10) -> dict:
    """GET /reparse-master/jobs."""
    res = supabase.table("reparse_job_log").select(
        "job_id, sector, total_targeted, processed, updated, skipped, errors, status, started_at, completed_at"
    ).order("created_at", desc=True).limit(limit).execute()
    return {"status": "success", "data": res.data or []}
