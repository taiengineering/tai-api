"""
Temporary CSI central-keyword extractor.

Reads unprocessed CSI accident rows, asks OpenAI for page-level central
keywords in semantic batches, validates the response contract, and writes
only to public.keyword_central_extracted. Source rows are never modified.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, Header, HTTPException, Query
from openai import OpenAI
from db.supabase_client import get_supabase

router = APIRouter(prefix="/admin/csi-keyword-extract")

MODEL = os.getenv("CSI_KEYWORD_MODEL", "gpt-4o-mini")
CREATED_BY = "gpt-accident-csi-extract"
GROUP_SIZE = 10
MAX_WORKERS = int(os.getenv("CSI_KEYWORD_WORKERS", "16"))

SYSTEM_PROMPT = """너는 CSI 건설 재해사례의 페이지별 SEO 중심키워드 추출기다.
각 입력은 하나의 사고 페이지이며 서로 독립적으로 판단한다.
우선순위는 cause_detail이다. 단 cause_detail이 '작업자 부주의/불안전한 행동/원인미상/조사중'처럼
사고 대상물이 없거나 노이즈면 summary를 사용한다. title은 절대 사용하지 않는다.

목표: 사고의 현장 물체·설비·공법을 나타내는 검색 가능한 명사 1개(1~2어절)를 central_keyword로 선택.
지역/시간/사람/순수 행위/상태/부주의/낙상 자체는 키워드가 아니다.
일반어 기타·자재·공구류·건물·구조물·설비·부재는 단독 central_keyword로 쓰지 말고 더 구체어를 찾는다.
근거 없는 명사를 만들지 않는다. 불명확하면 relevance='none', central_keyword=null.
alt_keywords는 원문 근거가 있는 일반/구체 대안 0~2개.
reason은 어떤 원문 명사를 왜 골랐는지 한 줄.
입력된 content_id를 절대 변경하지 않는다.
출력은 JSON 객체 하나만:
{"items":[{"content_id":"...","central_keyword":string|null,"alt_keywords":[string],
"relevance":"relevant"|"none","confidence":0.0,"reason":"..."}]}
"""


def _secret_ok(value: str | None) -> bool:
    return bool(value) and value == os.environ.get("INTERNAL_API_SECRET")


def _chunks(rows: list[dict], size: int) -> list[list[dict]]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _validate(row: dict, out: dict) -> dict:
    rel = out.get("relevance")
    kw = out.get("central_keyword")
    alts = out.get("alt_keywords") or []
    conf = float(out.get("confidence", 0))
    reason = str(out.get("reason") or "").strip()
    if out.get("content_id") != row["content_id"]:
        raise ValueError("content_id mismatch")
    if rel not in ("relevant", "none"):
        raise ValueError("invalid relevance")
    if rel == "none":
        kw = None
        alts = []
    elif not isinstance(kw, str) or not kw.strip():
        raise ValueError("relevant requires keyword")
    if not (0 <= conf <= 1):
        raise ValueError("invalid confidence")
    alts = [str(x).strip() for x in alts if str(x).strip()][:2]
    return {
        "page_type": "accident_csi",
        "page_id": row["content_id"],
        "central_keyword": kw.strip() if isinstance(kw, str) else None,
        "alt_keywords": alts,
        "relevance": rel,
        "confidence": conf,
        "reason": reason or "GPT semantic extraction",
        "created_by": CREATED_BY,
    }


def _judge_group(rows: list[dict]) -> list[dict]:
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    payload = [
        {
            "content_id": r["content_id"],
            "cause_detail": (r.get("cause_detail") or "").strip(),
            "summary": (r.get("summary") or "").strip(),
        }
        for r in rows
    ]
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=3200,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    items = data.get("items")
    if not isinstance(items, list) or len(items) != len(rows):
        raise ValueError("batch cardinality mismatch")
    by_id = {x.get("content_id"): x for x in items if isinstance(x, dict)}
    if len(by_id) != len(rows):
        raise ValueError("batch ids mismatch")
    return [_validate(r, by_id[r["content_id"]]) for r in rows]


def _judge_group_resilient(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    try:
        return _judge_group(rows), []
    except Exception as exc:
        if len(rows) == 1:
            return [], [{
                "content_ids": [rows[0]["content_id"]],
                "error": str(exc)[:300],
            }]
        mid = len(rows) // 2
        left_results, left_errors = _judge_group_resilient(rows[:mid])
        right_results, right_errors = _judge_group_resilient(rows[mid:])
        return left_results + right_results, left_errors + right_errors


@router.post("/run")
def run(
    limit: int = Query(1000, ge=1, le=2000),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    if not _secret_ok(x_internal_secret):
        raise HTTPException(status_code=403, detail="forbidden")
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY missing")

    sb = get_supabase()
    todo = (
        sb.rpc("get_unprocessed_csi_keyword_rows", {"p_limit": limit})
        .execute()
    ).data or []
    if not todo:
        return {
            "model": MODEL, "requested": 0, "applied": 0,
            "error_count": 0, "errors": [], "created_by": CREATED_BY,
        }

    groups = _chunks(todo, GROUP_SIZE)
    results: list[dict] = []
    errors: list[dict] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {pool.submit(_judge_group_resilient, group): group for group in groups}
        for fut in as_completed(future_map):
            group_results, group_errors = fut.result()
            results.extend(group_results)
            errors.extend(group_errors)

    if results:
        sb.table("keyword_central_extracted").upsert(
            results, on_conflict="page_type,page_id"
        ).execute()

    return {
        "model": MODEL,
        "requested": len(todo),
        "applied": len(results),
        "error_count": len(errors),
        "errors": errors[:20],
        "groups": len(groups),
        "group_size": GROUP_SIZE,
        "workers": MAX_WORKERS,
        "created_by": CREATED_BY,
    }
