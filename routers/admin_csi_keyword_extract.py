"""
Temporary CSI central-keyword extractor.

Reads unprocessed CSI accident rows, asks OpenAI for one page-level central
keyword per row, validates the response, and writes only to
public.keyword_central_extracted. Source rows are never modified.
"""
from __future__ import annotations

import json
import os
from fastapi import APIRouter, Header, HTTPException, Query
from openai import OpenAI
from db.supabase_client import get_supabase

router = APIRouter(prefix="/admin/csi-keyword-extract")

MODEL = os.getenv("CSI_KEYWORD_MODEL", "gpt-4o-mini")
CREATED_BY = "gpt-accident-csi-extract"

SYSTEM_PROMPT = """너는 CSI 건설 재해사례의 페이지별 SEO 중심키워드 추출기다.
각 입력은 하나의 사고 페이지다. 반드시 페이지별로 독립 판단한다.
우선순위는 cause_detail, 단 cause_detail이 '작업자 부주의/불안전한 행동/원인미상/조사중'처럼
사고 대상물이 없거나 노이즈면 summary를 사용한다. title은 절대 사용하지 않는다.

목표: 사고의 현장 물체·설비·공법을 나타내는 검색 가능한 명사 1개(1~2어절)를 central_keyword로 선택.
지역/시간/사람/순수 행위/상태/부주의/낙상 자체는 키워드가 아니다.
일반어 기타·자재·공구류·건물·구조물·설비·부재는 단독 central_keyword로 쓰지 말고 더 구체어를 찾는다.
근거 없는 명사는 만들지 않는다. 불명확하면 relevance='none', central_keyword=null.
alt_keywords는 원문 근거가 있는 일반/구체 대안 0~2개.
reason은 어떤 원문 명사를 왜 골랐는지 한 줄.
출력은 JSON만:
{"central_keyword":string|null,"alt_keywords":[string],"relevance":"relevant"|"none","confidence":0.0,"reason":"..."}
"""


def _secret_ok(value: str | None) -> bool:
    return bool(value) and value == os.environ.get("INTERNAL_API_SECRET")


def _judge(client: OpenAI, row: dict) -> dict:
    user = (
        f"[content_id] {row['content_id']}\n"
        f"[cause_detail] {(row.get('cause_detail') or '').strip()}\n"
        f"[summary] {(row.get('summary') or '').strip()}\n"
    )
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=220,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    )
    out = json.loads(resp.choices[0].message.content)
    rel = out.get("relevance")
    kw = out.get("central_keyword")
    alts = out.get("alt_keywords") or []
    conf = float(out.get("confidence", 0))
    reason = str(out.get("reason") or "").strip()
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


@router.post("/run")
def run(
    limit: int = Query(100, ge=1, le=500),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    if not _secret_ok(x_internal_secret):
        raise HTTPException(status_code=403, detail="forbidden")
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY missing")

    sb = get_supabase()
    done = (
        sb.table("keyword_central_extracted")
        .select("page_id")
        .eq("page_type", "accident_csi")
        .limit(50000)
        .execute()
    ).data or []
    done_ids = {r["page_id"] for r in done}

    rows = (
        sb.table("csi_accident_snapshot_items")
        .select("content_id,cause_detail,summary")
        .order("content_id")
        .limit(50000)
        .execute()
    ).data or []
    todo = [r for r in rows if r["content_id"] not in done_ids][:limit]

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    applied = 0
    errors = []
    for row in todo:
        try:
            result = _judge(client, row)
            sb.table("keyword_central_extracted").upsert(
                result, on_conflict="page_type,page_id"
            ).execute()
            applied += 1
        except Exception as exc:
            errors.append({"content_id": row["content_id"], "error": str(exc)[:240]})

    return {
        "model": MODEL,
        "requested": len(todo),
        "applied": applied,
        "errors": errors[:20],
        "error_count": len(errors),
        "created_by": CREATED_BY,
    }
