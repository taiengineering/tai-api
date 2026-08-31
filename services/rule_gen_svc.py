from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.rule_gen_ai import _call_claude_messages, _fetch_few_shot_examples, call_claude
from services.rule_gen_builders import _build_draft_row, _build_master_payload, _build_reparse_prompt, _pick_reparse_targets
from services.rule_gen_helpers import _is_blank, _normalize_submit_org_code, _validate_rule_row
from services.time import now_kst, serialize_external_utc


def _auto_approve_to_master(supabase, draft: dict) -> Optional[str]:
    rule_id = draft.get("draft_rule_id") or f"AI-{str(draft['id'])[:8].upper()}"
    if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
        rule_id = rule_id + "-V2"
    if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
        return None
    ins = supabase.table("master_building_legal_rules").insert(_build_master_payload(draft, rule_id)).execute()
    if ins.data:
        supabase.table("law_rule_drafts").update(
            {
                "status": "APPROVED",
                "registered_rule_id": rule_id,
                "reviewed_at": serialize_external_utc(now_kst()),
                "reviewer_note": "자동 승인 (ai_confidence 기준)",
            }
        ).eq("id", draft["id"]).execute()
        return rule_id
    return None


async def run_parse_article(supabase, body, build_full_context_fn, excluded_sectors, user_prompt_template, few_shot_rule, system_prompt, claude_model, extract_json_payload_fn, api_key):
    law_name = body.law_name
    law_article = body.law_article
    article_text = body.article_text
    article_id = body.article_id
    if not law_name or not article_text:
        raise ValueError("law_name, article_text 필수")
    full_context = await build_full_context_fn(law_name, law_article, article_id)
    rules = await call_claude(
        law_name,
        article_text,
        full_context,
        user_prompt_template,
        few_shot_rule,
        system_prompt,
        claude_model,
        extract_json_payload_fn,
        api_key,
    )
    if article_id:
        supabase.table("law_article").update({"ai_parsed_at": serialize_external_utc(now_kst())}).eq("id", article_id).execute()
    if not rules:
        return {"status": "success", "data": {"drafts": [], "message": "의무 없는 조문"}}
    saved = []
    for rule in rules:
        if (rule.get("sector") or "").strip().upper() in excluded_sectors:
            continue
        row = _build_draft_row(law_name, law_article, article_id, article_text, rule)
        ins = supabase.table("law_rule_drafts").insert(row).execute()
        if ins.data:
            saved.append(ins.data[0])
    return {"status": "success", "data": {"draft_count": len(saved), "drafts": saved, "message": f"{len(saved)}개 초안 생성 완료"}}


async def run_parse_batch(supabase, body, build_full_context_fn, excluded_sectors, user_prompt_template, few_shot_rule, system_prompt, claude_model, extract_json_payload_fn, api_key):
    law_id = body.law_id
    skip_existing = body.skip_existing
    max_articles = body.max_articles
    lm = supabase.table("law_master").select("law_name").eq("id", law_id).single().execute()
    if not lm.data:
        raise LookupError("법령 없음")
    law_name = lm.data["law_name"]
    ver = supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver.data:
        raise LookupError("현재 버전 없음")
    q = supabase.table("law_article").select("id, article_no, article_sub_no, article_title, article_text").eq("law_version_id", ver.data[0]["id"]).not_.is_("article_text", "null")
    if skip_existing:
        q = q.is_("ai_parsed_at", "null")
    articles = q.order("article_no_sort").limit(max_articles).execute().data or []
    results = {"total": len(articles), "processed": 0, "skipped": 0, "drafts_created": 0, "special_excluded": 0, "errors": []}
    now_iso = serialize_external_utc(now_kst())
    for art in articles:
        try:
            art_text = (art.get("article_text") or "").strip()
            if not art_text or len(art_text) < 20:
                results["skipped"] += 1
                if art.get("id"):
                    supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
                continue
            label = f"제{art.get('article_no', '')}조{art.get('article_title', '')}"
            law_article_label = f"제{art.get('article_no', '')}조{art.get('article_title', '')}"
            full_context = await build_full_context_fn(law_name, law_article_label, art.get("id"))
            rules = await call_claude(law_name, art_text, full_context, user_prompt_template, few_shot_rule, system_prompt, claude_model, extract_json_payload_fn, api_key)
            if art.get("id"):
                supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
            for rule in rules:
                if (rule.get("sector") or "").strip().upper() in excluded_sectors:
                    results["special_excluded"] += 1
                    continue
                supabase.table("law_rule_drafts").insert(_build_draft_row(law_name, label, art.get("id"), art_text, rule)).execute()
                results["drafts_created"] += 1
            results["processed"] += 1
        except Exception as e:
            results["errors"].append({"article": str(art.get("article_no")), "error": str(e)[:100]})
    return {"status": "success", "law_name": law_name, "data": results}


async def run_auto_parse_and_approve(supabase, body, internal_secret, build_full_context_fn, excluded_sectors, user_prompt_template, few_shot_rule, system_prompt, claude_model, extract_json_payload_fn, api_key):
    if body.secret != internal_secret:
        raise PermissionError("내부 전용 엔드포인트")
    lm = supabase.table("law_master").select("law_name").eq("id", body.law_id).eq("is_active", True).single().execute()
    if not lm.data:
        raise LookupError("법령 없음")
    law_name = lm.data["law_name"]
    ver = supabase.table("law_version").select("id").eq("law_id", body.law_id).eq("is_current", True).limit(1).execute()
    if not ver.data:
        return {"status": "success", "law_name": law_name, "data": {"skipped": "버전 없음"}}
    articles = (
        supabase.table("law_article")
        .select("id, article_no, article_title, article_text")
        .eq("law_version_id", ver.data[0]["id"])
        .is_("ai_parsed_at", "null")
        .not_.is_("article_text", "null")
        .order("article_no_sort")
        .limit(body.max_articles)
        .execute()
    ).data or []
    results = {"law_name": law_name, "total_articles": len(articles), "parsed": 0, "drafts_created": 0, "auto_approved": 0, "pending_review": 0, "errors": []}
    now_iso = serialize_external_utc(now_kst())
    for art in articles:
        try:
            art_text = (art.get("article_text") or "").strip()
            if not art_text or len(art_text) < 20:
                supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
                continue
            label = f"제{art.get('article_no', '')}조{art.get('article_title', '') or ''}"
            full_context = await build_full_context_fn(law_name, label, art.get("id"))
            rules = await call_claude(law_name, art_text, full_context, user_prompt_template, few_shot_rule, system_prompt, claude_model, extract_json_payload_fn, api_key)
            supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
            results["parsed"] += 1
            for rule in rules:
                if (rule.get("sector") or "").strip().upper() in excluded_sectors:
                    continue
                conf = int(rule.get("ai_confidence") or 0)
                ob_type = rule.get("obligation_type", "")
                row = _build_draft_row(law_name, label, art.get("id"), art_text, rule)
                row["ai_confidence"] = conf
                ins = supabase.table("law_rule_drafts").insert(row).execute()
                results["drafts_created"] += 1
                if not ins.data:
                    continue
                draft = ins.data[0]
                if ob_type == "INSPECT" and conf >= body.auto_approve_threshold:
                    approved_id = _auto_approve_to_master(supabase, draft)
                    if approved_id:
                        results["auto_approved"] += 1
                    else:
                        results["pending_review"] += 1
                else:
                    results["pending_review"] += 1
        except Exception as e:
            results["errors"].append({"article": str(art.get("article_no")), "error": str(e)[:100]})
    return {"status": "success", "data": results}


def run_bulk_approve_unregistered(supabase, secret: str, internal_secret: str, limit: int, excluded_sectors):
    if secret != internal_secret:
        raise PermissionError("Forbidden")
    drafts = (
        supabase.table("law_rule_drafts")
        .select("*")
        .eq("status", "APPROVED")
        .is_("registered_rule_id", "null")
        .order("created_at")
        .limit(limit)
        .execute()
    ).data or []
    ok, fail, skipped = 0, 0, 0
    for d in drafts:
        if (d.get("sector") or "").upper() in excluded_sectors:
            skipped += 1
            continue
        try:
            rule_id = d.get("draft_rule_id") or f"AI-{d['id'][:8].upper()}"
            if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
                rule_id = rule_id + "-V2"
            if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
                supabase.table("law_rule_drafts").update({"registered_rule_id": rule_id, "reviewed_at": serialize_external_utc(now_kst())}).eq("id", d["id"]).execute()
                skipped += 1
                continue
            ins = supabase.table("master_building_legal_rules").insert(_build_master_payload(d, rule_id)).execute()
            if ins.data:
                supabase.table("law_rule_drafts").update({"registered_rule_id": rule_id, "reviewed_at": serialize_external_utc(now_kst())}).eq("id", d["id"]).execute()
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
    remaining = (
        supabase.table("law_rule_drafts")
        .select("id", count="exact")
        .eq("status", "APPROVED")
        .is_("registered_rule_id", "null")
        .execute()
    ).count or 0
    return {"status": "success", "data": {"processed": len(drafts), "ok": ok, "fail": fail, "skipped": skipped, "remaining": remaining, "done": remaining == 0}}


def run_validate_master(supabase, sector: str, submit_org_labels: Dict[str, str]):
    q = supabase.table("master_building_legal_rules").select("*").eq("is_active", True)
    if sector and sector != "ALL":
        q = q.eq("sector", sector)
    rows = q.execute().data or []
    failures: Dict[str, int] = {}
    samples: Dict[str, List[str]] = {}
    rule_ids: Dict[str, int] = {}
    for row in rows:
        rid = row.get("rule_id") or ""
        if rid:
            rule_ids[rid] = rule_ids.get(rid, 0) + 1
        errs = _validate_rule_row(row)
        for err in errs:
            failures[err] = failures.get(err, 0) + 1
            samples.setdefault(err, [])
            if rid and len(samples[err]) < 8 and rid not in samples[err]:
                samples[err].append(rid)
    dup_ids = [rid for rid, cnt in rule_ids.items() if cnt > 1]
    if dup_ids:
        failures["duplicate_rule_id"] = len(dup_ids)
        samples["duplicate_rule_id"] = dup_ids[:8]
    failed_rows = set()
    for key, ids in samples.items():
        if key != "duplicate_rule_id":
            failed_rows.update(ids)
    return {"status": "success", "data": {"sector": sector, "total": len(rows), "failed": sum(failures.values()), "passed": max(0, len(rows) - len(failed_rows)), "failures": failures, "samples": samples, "submit_org_labels": submit_org_labels}}


