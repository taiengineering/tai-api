"""
AI 법령 룰 생성기 — law_rule_generator.py
============================================
Claude API를 사용하여 법령 조문 텍스트를 분석하고
master_building_legal_rules 판정 룰 초안을 자동 생성합니다.

모델: claude-haiku-4-5-20251001 (비용 최적화 — Sonnet 대비 ~25배 저렴)
전략: Haiku로 전체 파싱 → 확신도 낮은 것만 수동 검토

Endpoints:
  GET  /law-rule-generator/laws                     : 수집 법령 목록
  GET  /law-rule-generator/laws/{law_id}/articles   : 법령 조문 목록
  POST /law-rule-generator/parse                    : 조문 → AI 룰 초안 생성
  POST /law-rule-generator/parse-batch              : 법령 전체 일괄 파싱
  GET  /law-rule-generator/drafts                   : 초안 목록
  PATCH /law-rule-generator/drafts/{draft_id}       : 초안 수정
  POST /law-rule-generator/drafts/{draft_id}/approve: 승인 → master 등록
  POST /law-rule-generator/drafts/{draft_id}/reject : 거부
  GET  /law-rule-generator/stats                    : 통계
"""
import os
import json
import re
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import httpx

from db.supabase_client import get_supabase

router = APIRouter(prefix="/law-rule-generator", tags=["AI룰생성"])

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── 모델 설정 ──────────────────────────────────
# Haiku: ~$0.0004/조문 → 전체 파싱 약 $7 (1만원)
# Sonnet: ~$0.011/조문 → 전체 파싱 약 $200 (29만원)
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# 판정 룰 생성에 사용할 시스템 프롬프트
SYSTEM_PROMPT = """당신은 한국 산업안전 법령 전문가입니다.
법령 조문 텍스트를 분석하여 안전관리 시스템의 판정 룰을 JSON 형식으로 추출합니다.

추출 대상 의무 유형:
- APPOINT: 안전관리자·소방안전관리자 등 선임 의무
- INSPECT: 정기점검·안전검사 의무
- NOTIFY: 신고·보고·제출 의무
- REPORT: 기록·보존 의무
- ACTION: 조치·설치·이행 의무

조건 코드 (condition_code) 목록:
- building_area: 건물 연면적 (㎡)
- worker_count: 근로자 수 (명)
- electric_capacity: 전기 수전용량 (kW)
- gas_capacity_kg: LPG 저장량 (kg)
- gas_capacity_m3: 도시가스 사용량 (㎥/시)
- boiler_capacity_kw: 보일러 용량 (kW)
- elevator_count: 승강기 대수
- is_hazardous_material: 위험물 취급 여부 (0/1)
- annual_energy_toe: 연간 에너지 사용량 (TOE)
- construction_amount: 공사금액 (원)
- floor_count: 건물 층수
- hospital_beds: 병상 수
- student_count: 학생 수
- is_factory_registered: 공장등록 여부 (0/1)

섹터 코드:
- BUILDING: 건물·시설 (업무용·판매용·의료 등)
- MANUFACTURING: 공장·제조업
- CONSTRUCTION: 건설현장
- SPECIAL_FACILITY: 특수시설 (학교·병원·사회복지시설 등)
- COMMON: 전 섹터 공통
- CONSTRUCTION_MANUFACTURING: 건설+제조 공통

응답은 반드시 순수 JSON 배열만 출력하세요. 마크다운이나 설명 없이 JSON만 출력합니다.
의무가 없는 조문(정의, 목적, 용어해설 등)은 빈 배열 []을 반환하세요."""

USER_PROMPT_TEMPLATE = """다음 법령 조문을 분석하여 판정 룰을 추출해주세요.

법령명: {law_name}
조문: {article_text}

위 조문에서 안전관리 의무(선임·점검·신고·보고·조치)를 추출하여 다음 JSON 형식으로 반환하세요.
의무가 없는 조문이면 []을 반환하세요.

[
  {{
    "draft_rule_id": "법령약어-번호-섹터약어 (예: FIREACT-001-MFG)",
    "obligation_type": "APPOINT|INSPECT|NOTIFY|REPORT|ACTION",
    "sector": "BUILDING|MANUFACTURING|CONSTRUCTION|SPECIAL_FACILITY|COMMON|CONSTRUCTION_MANUFACTURING",
    "condition_code": "위 목록에서 선택 또는 null",
    "condition_operator": "gte|lte|gt|lt|eq",
    "condition_value": "숫자 문자열 또는 null",
    "obligation_summary": "의무 내용 1줄 요약 (최대 100자)",
    "penalty_summary": "위반 시 벌칙 요약 또는 null",
    "appointment_target": "선임 대상자명 (APPOINT인 경우만, 예: 소방안전관리자) 또는 null",
    "diagnosis_stage": 1,
    "ai_confidence": 0~100,
    "ai_reasoning": "판단 근거 1~2줄",
    "ai_flags": ["주의사항1", "주의사항2"]
  }}
]"""


# ──────────────────────────────────────────────
# Claude API 호출
# ──────────────────────────────────────────────

async def call_claude(law_name: str, article_text: str) -> List[Dict]:
    """Claude Haiku API로 조문 분석 → 룰 초안 JSON 반환"""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        law_name=law_name,
        article_text=article_text[:3000],
    )

    payload = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1500,
        "system":     SYSTEM_PROMPT,
        "messages":   [{"role": "user", "content": user_prompt}],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json=payload,
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Claude API 오류: {resp.text[:200]}")

    data = resp.json()
    raw_text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            raw_text += block["text"]

    raw_text = raw_text.strip()
    raw_text = re.sub(r"```json\s*", "", raw_text)
    raw_text = re.sub(r"```\s*", "", raw_text)
    raw_text = raw_text.strip()

    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return []


# ──────────────────────────────────────────────
# GET /law-rule-generator/laws
# ──────────────────────────────────────────────

@router.get("/laws")
async def get_laws(
    search: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    """수집된 법령 목록 — 조문 수 및 초안 현황 포함"""
    supabase = get_supabase()

    q = supabase.table("law_master").select("id, law_name, law_type_code, ministry_name, is_active", count="exact")
    if search:
        q = q.ilike("law_name", f"%{search}%")
    q = q.eq("is_active", True)
    offset = (page - 1) * page_size
    res = q.range(offset, offset + page_size - 1).order("law_name").execute()

    law_ids = [r["id"] for r in (res.data or [])]
    article_counts: Dict[str, int] = {}

    if law_ids:
        for lid in law_ids:
            try:
                ver_res = supabase.table("law_version").select("id").eq("law_id", lid).eq("is_current", True).limit(1).execute()
                if ver_res.data:
                    art_res = supabase.table("law_article").select("id", count="exact").eq("law_version_id", ver_res.data[0]["id"]).execute()
                    article_counts[lid] = art_res.count or 0
            except Exception:
                article_counts[lid] = 0

    return {
        "status": "success",
        "data": {
            "items": [
                {**r, "article_count": article_counts.get(r["id"], 0)}
                for r in (res.data or [])
            ],
            "total": res.count or 0,
            "page": page,
            "page_size": page_size,
        },
    }


# ──────────────────────────────────────────────
# GET /law-rule-generator/laws/{law_id}/articles
# ──────────────────────────────────────────────

@router.get("/laws/{law_id}/articles")
async def get_articles(law_id: str):
    """법령의 조문 목록 반환 (현재 버전)"""
    supabase = get_supabase()

    ver_res = supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver_res.data:
        raise HTTPException(status_code=404, detail="현재 버전 없음")

    ver_id = ver_res.data[0]["id"]
    art_res = supabase.table("law_article").select(
        "id, article_no, article_sub_no, article_title, article_text"
    ).eq("law_version_id", ver_id).order("article_no_sort").execute()

    articles = []
    for a in (art_res.data or []):
        dr = supabase.table("law_rule_drafts").select("id, status").eq("article_id", a["id"]).execute()
        drafts_info = dr.data or []
        a["draft_count"]  = len(drafts_info)
        a["has_approved"] = any(d["status"] == "APPROVED" for d in drafts_info)
        a["has_pending"]  = any(d["status"] == "PENDING"  for d in drafts_info)
        articles.append(a)

    return {"status": "success", "data": articles}


# ──────────────────────────────────────────────
# POST /law-rule-generator/parse
# ──────────────────────────────────────────────

@router.post("/parse")
async def parse_article(body: dict):
    """단일 조문 AI 파싱 → 초안 생성"""
    supabase = get_supabase()

    law_name     = body.get("law_name", "")
    law_article  = body.get("law_article", "")
    article_text = body.get("article_text", "")
    article_id   = body.get("article_id")

    if not law_name or not article_text:
        raise HTTPException(status_code=400, detail="law_name, article_text 필수")

    try:
        rules = await call_claude(law_name, article_text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 호출 실패: {str(e)}")

    if not rules:
        return {"status": "success", "data": {"drafts": [], "message": "의무 없는 조문 (빈 배열 반환)"}}

    saved = []
    for rule in rules:
        row = {
            "law_name":           law_name,
            "law_article":        law_article,
            "article_id":         article_id,
            "article_text":       article_text[:2000],
            "draft_rule_id":      rule.get("draft_rule_id"),
            "obligation_type":    rule.get("obligation_type"),
            "sector":             rule.get("sector"),
            "condition_code":     rule.get("condition_code"),
            "condition_operator": rule.get("condition_operator", "gte"),
            "condition_value":    str(rule["condition_value"]) if rule.get("condition_value") is not None else None,
            "obligation_summary": rule.get("obligation_summary"),
            "penalty_summary":    rule.get("penalty_summary"),
            "appointment_target": rule.get("appointment_target"),
            "diagnosis_stage":    rule.get("diagnosis_stage", 1),
            "ai_confidence":      rule.get("ai_confidence"),
            "ai_reasoning":       rule.get("ai_reasoning"),
            "ai_flags":           rule.get("ai_flags"),
            "status":             "PENDING",
        }
        ins = supabase.table("law_rule_drafts").insert(row).execute()
        if ins.data:
            saved.append(ins.data[0])

    return {
        "status": "success",
        "data": {"draft_count": len(saved), "drafts": saved, "message": f"{len(saved)}개 초안 생성 완료"},
    }


# ──────────────────────────────────────────────
# POST /law-rule-generator/parse-batch
# ──────────────────────────────────────────────

@router.post("/parse-batch")
async def parse_batch(body: dict):
    """법령 전체 조문 일괄 AI 파싱 (Haiku — 비용 최적화)"""
    supabase = get_supabase()

    law_id        = body.get("law_id")
    skip_existing = body.get("skip_existing", True)
    max_articles  = min(body.get("max_articles", 30), 50)

    if not law_id:
        raise HTTPException(status_code=400, detail="law_id 필수")

    lm_res = supabase.table("law_master").select("law_name").eq("id", law_id).single().execute()
    if not lm_res.data:
        raise HTTPException(status_code=404, detail="법령 없음")
    law_name = lm_res.data["law_name"]

    ver_res = supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver_res.data:
        raise HTTPException(status_code=404, detail="현재 버전 없음")

    ver_id = ver_res.data[0]["id"]
    art_res = supabase.table("law_article").select(
        "id, article_no, article_sub_no, article_title, article_text"
    ).eq("law_version_id", ver_id).not_.is_("article_text", "null").order("article_no_sort").limit(max_articles).execute()

    articles = art_res.data or []
    results = {"total": len(articles), "processed": 0, "skipped": 0, "drafts_created": 0, "errors": []}

    for art in articles:
        try:
            art_text = (art.get("article_text") or "").strip()
            if not art_text or len(art_text) < 20:
                results["skipped"] += 1
                continue

            if skip_existing and art.get("id"):
                exists = supabase.table("law_rule_drafts").select("id").eq("article_id", art["id"]).limit(1).execute()
                if exists.data:
                    results["skipped"] += 1
                    continue

            article_label = f"제{art.get('article_no','')}조{art.get('article_title','')}"
            rules = await call_claude(law_name, art_text)

            if rules:
                for rule in rules:
                    row = {
                        "law_name":           law_name,
                        "law_article":        article_label,
                        "article_id":         art.get("id"),
                        "article_text":       art_text[:2000],
                        "draft_rule_id":      rule.get("draft_rule_id"),
                        "obligation_type":    rule.get("obligation_type"),
                        "sector":             rule.get("sector"),
                        "condition_code":     rule.get("condition_code"),
                        "condition_operator": rule.get("condition_operator", "gte"),
                        "condition_value":    str(rule["condition_value"]) if rule.get("condition_value") is not None else None,
                        "obligation_summary": rule.get("obligation_summary"),
                        "penalty_summary":    rule.get("penalty_summary"),
                        "appointment_target": rule.get("appointment_target"),
                        "diagnosis_stage":    rule.get("diagnosis_stage", 1),
                        "ai_confidence":      rule.get("ai_confidence"),
                        "ai_reasoning":       rule.get("ai_reasoning"),
                        "ai_flags":           rule.get("ai_flags"),
                        "status":             "PENDING",
                    }
                    supabase.table("law_rule_drafts").insert(row).execute()
                    results["drafts_created"] += 1

            results["processed"] += 1
        except Exception as e:
            results["errors"].append({"article": str(art.get("article_no")), "error": str(e)[:100]})

    return {"status": "success", "law_name": law_name, "data": results}


# ──────────────────────────────────────────────
# GET /law-rule-generator/drafts
# ──────────────────────────────────────────────

@router.get("/drafts")
async def get_drafts(
    status:         str = Query(""),
    sector:         str = Query(""),
    ob_type:        str = Query(""),
    law_name:       str = Query(""),
    confidence_min: int = Query(0),
    page:           int = Query(1, ge=1),
    page_size:      int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("law_rule_drafts").select("*", count="exact")
    if status:         q = q.eq("status", status)
    if sector:         q = q.eq("sector", sector)
    if ob_type:        q = q.eq("obligation_type", ob_type)
    if law_name:       q = q.ilike("law_name", f"%{law_name}%")
    if confidence_min: q = q.gte("ai_confidence", confidence_min)
    offset = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return {"status": "success", "data": {"items": res.data or [], "total": res.count or 0, "page": page, "page_size": page_size}}


# ──────────────────────────────────────────────
# PATCH /law-rule-generator/drafts/{draft_id}
# ──────────────────────────────────────────────

@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, body: dict):
    """검토자가 초안 내용 수정"""
    supabase = get_supabase()
    allowed = [
        "draft_rule_id", "obligation_type", "sector",
        "condition_code", "condition_operator", "condition_value",
        "obligation_summary", "penalty_summary", "appointment_target",
        "diagnosis_stage", "reviewer_note",
    ]
    update_data = {k: v for k, v in body.items() if k in allowed}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    if update_data:
        update_data["status"] = "MODIFIED"
    res = supabase.table("law_rule_drafts").update(update_data).eq("id", draft_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "data": res.data[0]}


# ──────────────────────────────────────────────
# POST /law-rule-generator/drafts/{draft_id}/approve
# ──────────────────────────────────────────────

@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, body: dict = None):
    """초안 승인 → master_building_legal_rules 자동 등록"""
    supabase = get_supabase()
    body = body or {}

    dr = supabase.table("law_rule_drafts").select("*").eq("id", draft_id).single().execute()
    if not dr.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    d = dr.data

    rule_id = body.get("rule_id") or d.get("draft_rule_id") or f"AI-{draft_id[:8].upper()}"
    exists = supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute()
    if exists.data:
        rule_id = rule_id + "-V2"

    master_row = {
        "rule_id":                 rule_id,
        "sector":                  d.get("sector") or "BUILDING",
        "law_name":                d.get("law_name"),
        "law_article":             d.get("law_article"),
        "obligation_type":         d.get("obligation_type"),
        "obligation_summary":      d.get("obligation_summary"),
        "penalty_summary":         d.get("penalty_summary"),
        "appointment_target_code": d.get("appointment_target"),
        "condition_code":          d.get("condition_code"),
        "condition_operator_code": d.get("condition_operator", "gte"),
        "condition_value":         d.get("condition_value"),
        "appointment_required":    d.get("obligation_type") == "APPOINT",
        "inspection_required":     d.get("obligation_type") == "INSPECT",
        "notify_required":         d.get("obligation_type") == "NOTIFY",
        "report_required":         d.get("obligation_type") == "REPORT",
        "action_required":         d.get("obligation_type") == "ACTION",
        "diagnosis_stage":         d.get("diagnosis_stage", 1),
        "is_active":               True,
        "source_api":              "AI_GENERATED",
    }
    ins = supabase.table("master_building_legal_rules").insert(master_row).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="master 등록 실패")

    supabase.table("law_rule_drafts").update({
        "status":             "APPROVED",
        "registered_rule_id": rule_id,
        "reviewer_note":      body.get("reviewer_note"),
        "reviewed_at":        datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()

    return {"status": "success", "rule_id": rule_id, "message": f"master_building_legal_rules에 {rule_id}로 등록됐습니다.", "data": ins.data[0]}


# ──────────────────────────────────────────────
# POST /law-rule-generator/drafts/{draft_id}/reject
# ──────────────────────────────────────────────

@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, body: dict = None):
    supabase = get_supabase()
    body = body or {}
    res = supabase.table("law_rule_drafts").update({
        "status":        "REJECTED",
        "reviewer_note": body.get("reviewer_note"),
        "reviewed_at":   datetime.now(timezone.utc).isoformat(),
        "updated_at":    datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "message": "거부 처리 완료"}


# ──────────────────────────────────────────────
# GET /law-rule-generator/stats
# ──────────────────────────────────────────────

@router.get("/stats")
async def get_stats():
    supabase = get_supabase()
    res = supabase.table("law_rule_drafts").select("status, sector, obligation_type, ai_confidence").execute()
    rows = res.data or []

    status_cnt: Dict[str, int] = {}
    sector_cnt: Dict[str, int] = {}
    obtype_cnt: Dict[str, int] = {}
    confidence_sum = 0
    confidence_cnt = 0

    for r in rows:
        s = r.get("status") or "PENDING"
        status_cnt[s] = status_cnt.get(s, 0) + 1
        sec = r.get("sector") or "UNKNOWN"
        sector_cnt[sec] = sector_cnt.get(sec, 0) + 1
        ot = r.get("obligation_type") or "UNKNOWN"
        obtype_cnt[ot] = obtype_cnt.get(ot, 0) + 1
        if r.get("ai_confidence") is not None:
            confidence_sum += r["ai_confidence"]
            confidence_cnt += 1

    master_res = supabase.table("master_building_legal_rules").select("source_api", count="exact").eq("source_api", "AI_GENERATED").execute()

    return {
        "status": "success",
        "data": {
            "model":              CLAUDE_MODEL,
            "total_drafts":       len(rows),
            "status_breakdown":   status_cnt,
            "sector_breakdown":   sector_cnt,
            "obtype_breakdown":   obtype_cnt,
            "avg_confidence":     round(confidence_sum / confidence_cnt, 1) if confidence_cnt else 0,
            "approved_in_master": master_res.count or 0,
        },
    }
