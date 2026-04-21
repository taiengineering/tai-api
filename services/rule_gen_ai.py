from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx


async def _call_claude_messages(
    system_prompt: str,
    user_prompt: str,
    model: str,
    extract_json_payload_fn,
    api_key: str,
    max_tokens: int = 2200,
    timeout: int = 60,
) -> Any:
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Claude API 오류: {resp.text[:200]}")

    raw = ""
    for block in resp.json().get("content", []):
        if block.get("type") == "text":
            raw += block["text"]
    return extract_json_payload_fn(raw)


async def call_claude(
    law_name: str,
    article_text: str,
    full_context: str,
    user_prompt_template: str,
    few_shot_rule: Dict[str, Any],
    system_prompt: str,
    model: str,
    extract_json_payload_fn,
    api_key: str,
) -> List[Dict[str, Any]]:
    user_prompt = user_prompt_template.format(
        law_name=law_name,
        article_text=article_text[:3000],
        full_context=(full_context or "")[:15000],
        few_shot=json.dumps(few_shot_rule, ensure_ascii=False),
    )
    parsed = await _call_claude_messages(
        system_prompt,
        user_prompt,
        model,
        extract_json_payload_fn,
        api_key,
    )
    return parsed if isinstance(parsed, list) else []


async def _fetch_few_shot_examples(supabase, law_name: str, limit: int = 5) -> List[dict]:
    rows = (
        supabase.table("master_building_legal_rules")
        .select("*")
        .eq("is_active", True)
        .eq("law_name", law_name)
        .not_.is_("obligation_summary", "null")
        .not_.is_("remarks", "null")
        .not_.is_("submit_org_code", "null")
        .limit(limit)
        .execute()
    ).data or []
    return rows
