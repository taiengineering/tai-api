"""
AI 법령 룰 생성기 — law_rule_generator.py
============================================
Claude Haiku API로 법령 조문 → 판정룰 초안 자동 생성.

상태 흐름:
  PENDING → (승인) APPROVED → (법령개정) NEEDS_REVIEW → (재검토) APPROVED/REJECTED
  PENDING → (거부) REJECTED
  PENDING → (수정) MODIFIED → (승인) APPROVED

v1.2.0 (2026-04-03):
  [FIX] max_articles 백엔드 하드캡 50 → 제거 (UI 값 그대로 사용, 기본 30)
  [FIX] skip_existing: law_rule_drafts 대신 law_article.ai_parsed_at으로 판단
        → "의무없음" 조문도 파싱 완료 기록됨 → 재파싱 방지
  [ADD] parse_batch 파싱 완료 후 law_article.ai_parsed_at 업데이트

v1.1.0 (2026-04-02):
  - SPECIAL_FACILITY 섹터 제외 (용도별 법령 적용 필요 → 나라장터 등록 후 추가 예정)
"""
import os
import json
import re
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
from datetime import datetime, timezone
import httpx

from db.supabase_client import get_supabase

router = APIRouter(prefix="/law-rule-generator", tags=["AI룰생성"])

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-haiku-4-5-20251001"

# ★ 파싱에서 제외할 섹터 — SPECIAL_FACILITY는 용도별 법령 체계가 달라 별도 처리 예정
EXCLUDED_SECTORS = {"SPECIAL_FACILITY", "SPECIAL", "CONSTRUCTION_SPECIAL",
                    "MANUFACTURING_SPECIAL", "CONSTRUCTION_MANUFACTURING_SPECIAL"}

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
- is_factory_registered: 공장등록 여부 (0/1)

섹터 코드 (반드시 아래 4가지 중 하나만 사용):
- BUILDING: 건물·시설 (업무용·판매용·숙박·근린생활 등 일반 건축물)
- MANUFACTURING: 공장·제조업
- CONSTRUCTION: 건설현장
- COMMON: 전 섹터 공통
- CONSTRUCTION_MANUFACTURING: 건설+제조 공통

⚠️ 주의: 학교·병원·사회복지시설 등 특수시설 전용 법령은 건너뜁니다.
  해당 법령(의료법·학교안전법·사회복지사업법 등)의 조문에서 의무가 발견되면 []을 반환하세요.

응답은 반드시 순수 JSON 배열만 출력하세요. 마크다운이나 설명 없이 JSON만 출력합니다.
의무가 없는 조문(정의, 목적, 용어해설 등)은 빈 배열 []을 반환하세요."""

USER_PROMPT_TEMPLATE = """다음 법령 조문을 분석하여 판정 룰을 추출해주세요.

법령명: {law_name}
조문: {article_text}

위 조문에서 안전관리 의무(선임·점검·신고·보고·조치)를 추출하여 다음 JSON 형식으로 반환하세요.
의무가 없는 조문이면 []을 반환하세요.

[
  {{
    "draft_rule_id": "법령약어-번호-섹터약어 (예: FIREACT-001-BLD)",
    "obligation_type": "APPOINT|INSPECT|NOTIFY|REPORT|ACTION",
    "sector": "BUILDING|MANUFACTURING|CONSTRUCTION|COMMON|CONSTRUCTION_MANUFACTURING",
    "condition_code": "위 목록에서 선택 또는 null",
    "condition_operator": "gte|lte|gt|lt|eq",
    "condition_value": "숫자 문자열 또는 null",
    "obligation_summary": "의무 내용 1줄 요약 (최대 100자)",
    "penalty_summary": "위반 시 벌칙 요약 또는 null",
    "appointment_target": "선임 대상자명 (APPOINT인 경우만) 또는 null",
    "diagnosis_stage": 1,
    "ai_confidence": 0~100,
    "ai_reasoning": "판단 근거 1~2줄",
    "ai_flags": ["주의사항1"]
  }}
]"""


async def call_claude(law_name: str, article_text: str) -> List[Dict]:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        law_name=law_name, article_text=article_text[:3000])

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": CLAUDE_MODEL, "max_tokens": 1500,
                  "system": SYSTEM_PROMPT,
                  "messages": [{"role": "user", "content": user_prompt}]},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Claude API 오류: {resp.text[:200]}")

    raw = ""
    for block in resp.json().get("content", []):
        if block.get("type") == "text":
            raw += block["text"]

    raw = re.sub(r"```json\s*", "", raw.strip())
    raw = re.sub(r"```\s*", "", raw).strip()

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return []


# ── GET /laws ──────────────────────────────────────────────

@router.get("/laws")
async def get_laws(
    search: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("law_master").select(
        "id, law_name, law_type_code, ministry_name, is_active", count="exact")
    if search:
        q = q.ilike("law_name", f"%{search}%")
    q = q.eq("is_active", True)
    offset = (page - 1) * page_size
    res = q.range(offset, offset + page_size - 1).order("law_name").execute()

    article_counts: Dict[str, int] = {}
    parsed_counts: Dict[str, int] = {}
    for r in (res.data or []):
        try:
            ver = supabase.table("law_version").select("id").eq("law_id", r["id"]).eq("is_current", True).limit(1).execute()
            if ver.data:
                vid = ver.data[0]["id"]
                ac = supabase.table("law_article").select("id", count="exact").eq("law_version_id", vid).execute()
                pc = supabase.table("law_article").select("id", count="exact").eq("law_version_id", vid).not_.is_("ai_parsed_at", "null").execute()
                article_counts[r["id"]] = ac.count or 0
                parsed_counts[r["id"]] = pc.count or 0
        except Exception:
            article_counts[r["id"]] = 0
            parsed_counts[r["id"]] = 0

    return {"status": "success", "data": {
        "items": [{
            **r,
            "article_count": article_counts.get(r["id"], 0),
            "parsed_count": parsed_counts.get(r["id"], 0),
        } for r in (res.data or [])],
        "total": res.count or 0, "page": page, "page_size": page_size,
    }}


# ── GET /laws/{law_id}/articles ────────────────────────────

@router.get("/laws/{law_id}/articles")
async def get_articles(law_id: str):
    supabase = get_supabase()
    ver = supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver.data:
        raise HTTPException(status_code=404, detail="현재 버전 없음")

    arts = supabase.table("law_article").select(
        "id, article_no, article_sub_no, article_title, article_text, ai_parsed_at"
    ).eq("law_version_id", ver.data[0]["id"]).order("article_no_sort").execute()

    articles = []
    for a in (arts.data or []):
        dr = supabase.table("law_rule_drafts").select("id, status").eq("article_id", a["id"]).execute()
        di = dr.data or []
        a["draft_count"]  = len(di)
        a["has_approved"] = any(d["status"] == "APPROVED"      for d in di)
        a["has_pending"]  = any(d["status"] == "PENDING"       for d in di)
        a["needs_review"] = any(d["status"] == "NEEDS_REVIEW"  for d in di)
        a["is_parsed"]    = a.get("ai_parsed_at") is not None
        articles.append(a)

    return {"status": "success", "data": articles}


# ── POST /parse ────────────────────────────────────────────

@router.post("/parse")
async def parse_article(body: dict):
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

    # 파싱 완료 기록 (의무없음이어도 ai_parsed_at 업데이트)
    if article_id:
        supabase.table("law_article").update({
            "ai_parsed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", article_id).execute()

    if not rules:
        return {"status": "success", "data": {"drafts": [], "message": "의무 없는 조문"}}

    saved = []
    for rule in rules:
        # ★ 특수시설 섹터 초안 저장 차단
        rule_sector = (rule.get("sector") or "").strip().upper()
        if rule_sector in EXCLUDED_SECTORS:
            continue

        row = {
            "law_name": law_name, "law_article": law_article,
            "article_id": article_id, "article_text": article_text[:2000],
            "draft_rule_id": rule.get("draft_rule_id"),
            "obligation_type": rule.get("obligation_type"),
            "sector": rule.get("sector"),
            "condition_code": rule.get("condition_code"),
            "condition_operator": rule.get("condition_operator", "gte"),
            "condition_value": str(rule["condition_value"]) if rule.get("condition_value") is not None else None,
            "obligation_summary": rule.get("obligation_summary"),
            "penalty_summary": rule.get("penalty_summary"),
            "appointment_target": rule.get("appointment_target"),
            "diagnosis_stage": rule.get("diagnosis_stage", 1),
            "ai_confidence": rule.get("ai_confidence"),
            "ai_reasoning": rule.get("ai_reasoning"),
            "ai_flags": rule.get("ai_flags"),
            "status": "PENDING",
        }
        ins = supabase.table("law_rule_drafts").insert(row).execute()
        if ins.data:
            saved.append(ins.data[0])

    return {"status": "success", "data": {
        "draft_count": len(saved), "drafts": saved,
        "message": f"{len(saved)}개 초안 생성 완료"}}


# ── POST /parse-batch ──────────────────────────────────────

@router.post("/parse-batch")
async def parse_batch(body: dict):
    """
    법령 일괄 파싱.

    [v1.2.0 변경사항]
    - max_articles 백엔드 상한 제거 (UI에서 전달된 값 그대로 사용)
    - skip_existing: law_article.ai_parsed_at IS NOT NULL → 파싱 완료 판단
      (의무없음 조문도 ai_parsed_at 기록 → 재파싱 방지)
    - 파싱 완료(의무있음/없음) 후 law_article.ai_parsed_at 업데이트
    """
    supabase = get_supabase()
    law_id        = body.get("law_id")
    skip_existing = body.get("skip_existing", True)
    # ★ max_articles 상한 제거 — UI에서 전달된 값 그대로 사용 (기본 50)
    max_articles  = int(body.get("max_articles", 50))

    if not law_id:
        raise HTTPException(status_code=400, detail="law_id 필수")

    lm = supabase.table("law_master").select("law_name").eq("id", law_id).single().execute()
    if not lm.data:
        raise HTTPException(status_code=404, detail="법령 없음")
    law_name = lm.data["law_name"]

    ver = supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver.data:
        raise HTTPException(status_code=404, detail="현재 버전 없음")

    # ★ skip_existing=True면 ai_parsed_at IS NULL인 조문만 가져옴
    q = supabase.table("law_article").select(
        "id, article_no, article_sub_no, article_title, article_text"
    ).eq("law_version_id", ver.data[0]["id"]).not_.is_("article_text", "null")

    if skip_existing:
        q = q.is_("ai_parsed_at", "null")  # 미파싱 조문만

    q = q.order("article_no_sort").limit(max_articles)
    arts = q.execute()

    articles = arts.data or []
    results  = {"total": len(articles), "processed": 0, "skipped": 0,
                "drafts_created": 0, "special_excluded": 0, "errors": []}

    now_iso = datetime.now(timezone.utc).isoformat()

    for art in articles:
        try:
            art_text = (art.get("article_text") or "").strip()
            if not art_text or len(art_text) < 20:
                results["skipped"] += 1
                # 짧은 조문도 파싱 완료 표시 (재시도 방지)
                if art.get("id"):
                    supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
                continue

            label = f"제{art.get('article_no', '')}조{art.get('article_title', '')}"
            rules = await call_claude(law_name, art_text)

            # ★ 파싱 완료 기록 — 의무있음/없음 무관하게 ai_parsed_at 업데이트
            if art.get("id"):
                supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()

            for rule in rules:
                # ★ 특수시설 섹터 초안 저장 차단
                rule_sector = (rule.get("sector") or "").strip().upper()
                if rule_sector in EXCLUDED_SECTORS:
                    results["special_excluded"] += 1
                    continue

                supabase.table("law_rule_drafts").insert({
                    "law_name": law_name, "law_article": label,
                    "article_id": art.get("id"), "article_text": art_text[:2000],
                    "draft_rule_id": rule.get("draft_rule_id"),
                    "obligation_type": rule.get("obligation_type"),
                    "sector": rule.get("sector"),
                    "condition_code": rule.get("condition_code"),
                    "condition_operator": rule.get("condition_operator", "gte"),
                    "condition_value": str(rule["condition_value"]) if rule.get("condition_value") is not None else None,
                    "obligation_summary": rule.get("obligation_summary"),
                    "penalty_summary": rule.get("penalty_summary"),
                    "appointment_target": rule.get("appointment_target"),
                    "diagnosis_stage": rule.get("diagnosis_stage", 1),
                    "ai_confidence": rule.get("ai_confidence"),
                    "ai_reasoning": rule.get("ai_reasoning"),
                    "ai_flags": rule.get("ai_flags"),
                    "status": "PENDING",
                }).execute()
                results["drafts_created"] += 1

            results["processed"] += 1
        except Exception as e:
            results["errors"].append({"article": str(art.get("article_no")), "error": str(e)[:100]})

    return {"status": "success", "law_name": law_name, "data": results}


# ── GET /drafts ────────────────────────────────────────────

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
    # ★ 특수시설 섹터 초안 항상 제외
    q = q.not_.in_("sector", list(EXCLUDED_SECTORS))
    offset = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return {"status": "success", "data": {
        "items": res.data or [], "total": res.count or 0,
        "page": page, "page_size": page_size}}


# ── GET /drafts/{draft_id} — 단건 조회 (수정 모달용) ───────

@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    supabase = get_supabase()
    res = supabase.table("law_rule_drafts").select("*").eq("id", draft_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "data": res.data}


# ── PATCH /drafts/{draft_id} ───────────────────────────────

@router.patch("/drafts/{draft_id}")
async def update_draft(draft_id: str, body: dict):
    supabase = get_supabase()
    allowed = ["draft_rule_id", "obligation_type", "sector",
               "condition_code", "condition_operator", "condition_value",
               "obligation_summary", "penalty_summary", "appointment_target",
               "diagnosis_stage", "reviewer_note"]
    data = {k: v for k, v in body.items() if k in allowed}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["status"] = "MODIFIED"
    res = supabase.table("law_rule_drafts").update(data).eq("id", draft_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "data": res.data[0]}


# ── POST /drafts/{draft_id}/approve ───────────────────────

@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, body: dict = None):
    supabase = get_supabase()
    body = body or {}

    dr = supabase.table("law_rule_drafts").select("*").eq("id", draft_id).single().execute()
    if not dr.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    d = dr.data

    # ★ 특수시설 섹터 초안은 master 등록 차단
    if (d.get("sector") or "").upper() in EXCLUDED_SECTORS:
        raise HTTPException(status_code=400, detail="특수시설 섹터는 현재 master 등록 불가 (용도별 법령 체계 구축 후 추가 예정)")

    rule_id = body.get("rule_id") or d.get("draft_rule_id") or f"AI-{draft_id[:8].upper()}"
    if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
        rule_id = rule_id + "-V2"

    ins = supabase.table("master_building_legal_rules").insert({
        "rule_id": rule_id,
        "sector":  d.get("sector") or "BUILDING",
        "law_name":    d.get("law_name"),
        "law_article": d.get("law_article"),
        "obligation_type":         d.get("obligation_type"),
        "obligation_summary":      d.get("obligation_summary"),
        "penalty_summary":         d.get("penalty_summary"),
        "appointment_target_code": d.get("appointment_target"),
        "condition_code":          d.get("condition_code"),
        "condition_operator_code": d.get("condition_operator", "gte"),
        "condition_value":         d.get("condition_value"),
        "appointment_required": d.get("obligation_type") == "APPOINT",
        "inspection_required":  d.get("obligation_type") == "INSPECT",
        "notify_required":      d.get("obligation_type") == "NOTIFY",
        "report_required":      d.get("obligation_type") == "REPORT",
        "action_required":      d.get("obligation_type") == "ACTION",
        "diagnosis_stage": d.get("diagnosis_stage", 1),
        "is_active": True, "source_api": "AI_GENERATED",
    }).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="master 등록 실패")

    supabase.table("law_rule_drafts").update({
        "status": "APPROVED", "registered_rule_id": rule_id,
        "reviewer_note": body.get("reviewer_note"),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()

    return {"status": "success", "rule_id": rule_id,
            "message": f"master에 {rule_id}로 등록됐습니다.", "data": ins.data[0]}


# ── POST /drafts/{draft_id}/reject ────────────────────────

@router.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, body: dict = None):
    supabase = get_supabase()
    body = body or {}
    res = supabase.table("law_rule_drafts").update({
        "status": "REJECTED",
        "reviewer_note": body.get("reviewer_note"),
        "reviewed_at":   datetime.now(timezone.utc).isoformat(),
        "updated_at":    datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "message": "거부 처리 완료"}


# ── GET /stats ─────────────────────────────────────────────

@router.get("/stats")
async def get_stats():
    supabase = get_supabase()
    res = supabase.table("law_rule_drafts").select(
        "status, sector, obligation_type, ai_confidence").execute()
    rows = res.data or []

    status_cnt: Dict[str, int] = {}
    sector_cnt: Dict[str, int] = {}
    obtype_cnt: Dict[str, int] = {}
    conf_sum, conf_cnt = 0, 0

    for r in rows:
        s  = r.get("status")  or "PENDING"
        sc = r.get("sector")  or "UNKNOWN"
        ot = r.get("obligation_type") or "UNKNOWN"
        # 특수시설 제외하고 집계
        if sc.upper() not in EXCLUDED_SECTORS:
            status_cnt[s]  = status_cnt.get(s, 0)  + 1
            sector_cnt[sc] = sector_cnt.get(sc, 0) + 1
            obtype_cnt[ot] = obtype_cnt.get(ot, 0) + 1
            if r.get("ai_confidence") is not None:
                conf_sum += r["ai_confidence"]; conf_cnt += 1

    master_res = supabase.table("master_building_legal_rules").select(
        "source_api", count="exact").eq("source_api", "AI_GENERATED").execute()

    return {"status": "success", "data": {
        "model":              CLAUDE_MODEL,
        "total_drafts":       len(rows),
        "status_breakdown":   status_cnt,
        "sector_breakdown":   sector_cnt,
        "obtype_breakdown":   obtype_cnt,
        "avg_confidence":     round(conf_sum / conf_cnt, 1) if conf_cnt else 0,
        "approved_in_master": master_res.count or 0,
        "needs_review":       status_cnt.get("NEEDS_REVIEW", 0),
    }}
