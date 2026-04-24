"""
AI 법령 룰 생성기 — law_rule_generator.py
============================================
Claude Haiku API로 법령 조문 → 판정룰 초안 자동 생성.

상태 흐름:
  PENDING → (승인) APPROVED → (법령개정) NEEDS_REVIEW → (재검토) APPROVED/REJECTED
  PENDING → (거부) REJECTED
  PENDING → (수정) MODIFIED → (승인) APPROVED

v1.6.0 (2026-04-20):
  [FIX] POST /reparse-master — BackgroundTasks 비동기 전환 (서버 타임아웃 방지)
        즉시 {status: "accepted", job_id} 반환 + 백그라운드 1건씩 처리
  [ADD] GET /reparse-master/status/{job_id} — 진행률 조회
  [ADD] GET /reparse-master/jobs — 최근 작업 목록
  [ADD] reparse_job_log 테이블 (DDL: sql/20260420_reparse_job_log.sql)

v1.5.0 (2026-04-05):
  [ADD] GET /drafts — has_condition 파라미터 추가
        has_condition=false → condition_code IS NULL 필터
        has_condition=true  → condition_code IS NOT NULL 필터
        has_condition=""    → 전체 (기존 동작)

v1.4.0 (2026-04-03):
  [ADD] POST /bulk-approve-unregistered — APPROVED + 미등록 draft 일괄 master 등록

v1.3.0 (2026-04-03):
  [ADD] POST /auto-parse-and-approve — 파싱+고신뢰도 자동승인 일괄 처리
        ai_confidence >= auto_approve_threshold(기본 80)인 INSPECT 초안 자동 master 등록

v1.2.0 (2026-04-03):
  [FIX] max_articles 백엔드 하드캡 50 → 제거
  [FIX] skip_existing: law_article.ai_parsed_at으로 재파싱 방지

v1.1.0 (2026-04-02):
  - SPECIAL_FACILITY 섹터 제외
"""
import os
import json
import uuid
import asyncio
import logging
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

from db.supabase_client import get_supabase
from services.law_context_builder import build_full_context
from services.rule_gen_ai import (
    _call_claude_messages as call_claude_messages_ai,
    _fetch_few_shot_examples,
    call_claude as call_claude_ai,
)
from services.rule_gen_builders import (
    _build_draft_row,
    _build_master_payload,
    _build_reparse_prompt,
    _pick_reparse_targets,
)
from services.rule_gen_helpers import (
    _extract_json_payload,
    _is_blank,
    _normalize_submit_org_code,
    _to_bool,
    _validate_rule_row,
)
from services.rule_gen_svc import _auto_approve_to_master

router = APIRouter(prefix="/law-rule-generator", tags=["AI룰생성"])

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-haiku-4-5-20251001"
CLAUDE_SONNET_MODEL = "claude-sonnet-4-20250514"
INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET")
if not INTERNAL_SECRET:
    raise RuntimeError(
        "INTERNAL_API_SECRET 환경변수 필수. Railway Variables에 설정 필요."
    )

EXCLUDED_SECTORS = {"SPECIAL_FACILITY", "SPECIAL", "CONSTRUCTION_SPECIAL",
                    "MANUFACTURING_SPECIAL", "CONSTRUCTION_MANUFACTURING_SPECIAL"}

VALID_CONDITION_CODES = {
    "building_area", "worker_count", "electric_capacity", "gas_capacity_kg",
    "gas_capacity_m3", "boiler_capacity_kw", "elevator_count", "is_hazardous_material",
    "annual_energy_toe", "construction_amount", "floor_count", "is_factory_registered",
    "employee_count", "contract_amount", "has_chemical_substance", "is_multi_use",
    "contractor_count", "has_high_pressure_gas", "transformer_capacity_kva",
    "has_boiler", "electrical_capacity_kw", "boiler_capacity_th", "hospital_beds",
    "student_count",
}

SUBMIT_ORG_LABELS = {
    "kosha": "한국산업안전보건공단 (관할 지역본부)",
    "local_gov": "관할 시·군·구청",
    "moel": "관할 지방고용노동관서",
    "me": "관할 지방환경관서",
    "kgs": "한국가스안전공사 (관할 지사)",
    "mlit": "관할 지방국토관리청",
    "nfa": "관할 소방서",
    "kesco": "한국전기안전공사 (관할 지사)",
}

FEW_SHOT_RULE = {
    "draft_rule_id": "FIREACT-001-BLD",
    "obligation_type": "APPOINT",
    "sector": "BUILDING",
    "condition_code": "building_area",
    "condition_operator": "gte",
    "condition_value": "400",
    "obligation_summary": "소방안전관리자 선임 의무",
    "penalty_summary": "미선임 시 300만원 이하 과태료 (제53조)",
    "penalty_value": 300,
    "form_code": "NFA-별지제5호",
    "form_name": "소방안전관리자 선임신고서",
    "submit_org_code": "nfa",
    "due_days": 14,
    "report_method_code": "online",
    "report_method_std": "api",
    "appointment_target": "소방안전관리자",
    "appointment_qualification_code": "fire_safety_1",
    "appointment_qualification_level_code": "grade1",
    "appointment_count_value": 1,
    "inspection_cycle_value": 6,
    "inspection_cycle_unit_code": "month",
    "cycle_base_guide": "최초 선임일로부터 6개월마다",
    "online_system": "소방청 민원 시스템",
    "system_url": "https://www.safetykorea.go.kr",
    "tai_feature_code": "APPOINTMENT",
    "remarks": "연면적 400㎡ 이상 특정소방대상물",
    "diagnosis_stage": 1,
    "ai_confidence": 95,
    "ai_reasoning": "화재예방법 제24조 + 시행령 제22조 별표4 기준",
    "ai_flags": [],
}

SYSTEM_PROMPT = """당신은 한국 산업안전 법령 전문가입니다.
법령 원문(본조+시행령+별표+벌칙)을 분석하여 안전관리 시스템의 판정 룰을 JSON 형식으로 추출합니다.

추출 대상 의무 유형:
- APPOINT: 안전관리자·소방안전관리자 등 선임 의무
- INSPECT: 정기점검·안전검사 의무
- NOTIFY: 신고·보고·제출 의무
- REPORT: 기록·보존 의무
- ACTION: 조치·설치·이행 의무

조건 코드 (condition_code) 목록 (정확히 아래에서만 선택):
- building_area: 건물 연면적 (㎡)
- worker_count: 근로자 수 (명)
- electric_capacity: 전기 수전용량 (kW)
- electrical_capacity_kw: 전기 수전용량 (kW, 동의어)
- gas_capacity_kg: LPG 저장량 (kg)
- gas_capacity_m3: 도시가스 사용량 (㎥/시)
- boiler_capacity_kw: 보일러 용량 (kW)
- boiler_capacity_th: 보일러 용량 (ton/hr)
- elevator_count: 승강기 대수
- is_hazardous_material: 위험물 취급 여부 (0/1)
- annual_energy_toe: 연간 에너지 사용량 (TOE)
- construction_amount: 공사금액 (원)
- floor_count: 건물 층수
- is_factory_registered: 공장등록 여부 (0/1)
- employee_count: 상시근로자 수 (명)
- contract_amount: 공사금액 (원, 동의어)
- has_chemical_substance: 화학물질 취급 여부 (0/1)
- is_multi_use: 다중이용업소 여부 (0/1)
- contractor_count: 수급업체 수
- has_high_pressure_gas: 고압가스 취급 여부 (0/1)
- transformer_capacity_kva: 변압기 용량 (kVA)
- has_boiler: 보일러 보유 여부 (0/1)
- hospital_beds: 병상 수
- student_count: 학생 수

섹터 코드 (반드시 아래 4가지 중 하나만 사용):
- BUILDING: 건물·시설 (업무용·판매용·숙박·근린생활 등 일반 건축물)
- MANUFACTURING: 공장·제조업
- CONSTRUCTION: 건설현장
- COMMON: 전 섹터 공통
- CONSTRUCTION_MANUFACTURING: 건설+제조 공통

⚠️ 주의: 학교·병원·사회복지시설 등 특수시설 전용 법령은 건너뜁니다.
  해당 법령(의료법·학교안전법·사회복지사업법 등)의 조문에서 의무가 발견되면 []을 반환하세요.

submit_org_code는 반드시 아래 중 하나만 사용:
- kosha, local_gov, moel, me, kgs, mlit, nfa, kesco

condition_code가 있으면 condition_operator + condition_value를 함께 채웁니다.
inspection_required=true이면 inspection_cycle_value + inspection_cycle_unit_code를 채웁니다.
report_required=true이면 report_method_code를 채웁니다.
appointment_required=true이면 appointment_qualification_code를 채웁니다.
penalty_summary가 있으면 penalty_value(만원)를 가능한 범위에서 채웁니다.

응답은 반드시 순수 JSON 배열만 출력하세요. 마크다운/설명 금지.
의무가 없는 조문은 빈 배열 []을 반환하세요."""

USER_PROMPT_TEMPLATE = """다음 법령 조문을 분석하여 판정 룰을 추출해주세요.

법령명: {law_name}
핵심 조문: {article_text}

[풀 컨텍스트]
{full_context}

[좋은 예시 1개]
{few_shot}

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
    "remarks": "맥락 설명 (최대 100자)",
    "penalty_summary": "위반 시 벌칙 요약 또는 null",
    "penalty_value": "과태료 숫자 (만원 단위) 또는 null",
    "form_code": "별지서식 번호 또는 null",
    "form_name": "서식명 또는 null",
    "submit_org_code": "kosha|local_gov|moel|me|kgs|mlit|nfa|kesco 중 선택 또는 null",
    "due_days": "기한 일수 숫자 또는 null",
    "report_method_code": "online|offline|both 또는 null",
    "report_method_std": "api|paper|keep 또는 null",
    "online_system": "온라인 시스템명 또는 null",
    "system_url": "시스템 URL 또는 null",
    "appointment_qualification_code": "자격 코드 또는 null",
    "appointment_qualification_level_code": "자격 등급 또는 null",
    "appointment_count_value": "선임 인원수 또는 null",
    "inspection_cycle_value": "점검 주기 숫자 또는 null",
    "inspection_cycle_unit_code": "day|week|month|quarter|half_year|year 또는 null",
    "cycle_base_guide": "주기 설명 (최대 50자) 또는 null",
    "tai_feature_code": "APPOINTMENT|INSPECTION|REPORT|EDUCATION|DOCUMENT|FIX|CHECKLIST 또는 null",
    "appointment_target": "선임 대상자명 (APPOINT인 경우만) 또는 null",
    "appointment_required": "true|false",
    "inspection_required": "true|false",
    "notify_required": "true|false",
    "report_required": "true|false",
    "action_required": "true|false",
    "diagnosis_stage": 1,
    "ai_confidence": 0~100,
    "ai_reasoning": "판단 근거 1~2줄",
    "ai_flags": ["주의사항1"]
  }}
]"""


async def call_claude(law_name: str, article_text: str, full_context: str = "") -> List[Dict]:
    """조문 파싱용 Claude 호출. 서비스 레이어 오류를 HTTP 예외로 변환."""
    try:
        return await call_claude_ai(
            law_name,
            article_text,
            full_context,
            USER_PROMPT_TEMPLATE,
            FEW_SHOT_RULE,
            SYSTEM_PROMPT,
            CLAUDE_MODEL,
            _extract_json_payload,
            ANTHROPIC_API_KEY,
        )
    except RuntimeError as e:
        msg = str(e)
        if "ANTHROPIC_API_KEY" in msg:
            raise HTTPException(status_code=500, detail=msg)
        raise HTTPException(status_code=502, detail=msg)


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
        full_context = await build_full_context(law_name, law_article, article_id)
        rules = await call_claude(law_name, article_text, full_context=full_context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 호출 실패: {str(e)}")

    if article_id:
        supabase.table("law_article").update({
            "ai_parsed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", article_id).execute()

    if not rules:
        return {"status": "success", "data": {"drafts": [], "message": "의무 없는 조문"}}

    saved = []
    for rule in rules:
        rule_sector = (rule.get("sector") or "").strip().upper()
        if rule_sector in EXCLUDED_SECTORS:
            continue

        row = _build_draft_row(law_name, law_article, article_id, article_text, rule)
        ins = supabase.table("law_rule_drafts").insert(row).execute()
        if ins.data:
            saved.append(ins.data[0])

    return {"status": "success", "data": {
        "draft_count": len(saved), "drafts": saved,
        "message": f"{len(saved)}개 초안 생성 완료"}}


# ── POST /parse-batch ──────────────────────────────────────

@router.post("/parse-batch")
async def parse_batch(body: dict):
    supabase = get_supabase()
    law_id        = body.get("law_id")
    skip_existing = body.get("skip_existing", True)
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

    q = supabase.table("law_article").select(
        "id, article_no, article_sub_no, article_title, article_text"
    ).eq("law_version_id", ver.data[0]["id"]).not_.is_("article_text", "null")

    if skip_existing:
        q = q.is_("ai_parsed_at", "null")

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
                if art.get("id"):
                    supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
                continue

            label = f"제{art.get('article_no', '')}조{art.get('article_title', '')}"
            law_article_label = f"제{art.get('article_no', '')}조{art.get('article_title', '')}"
            full_context = await build_full_context(law_name, law_article_label, art.get("id"))
            rules = await call_claude(law_name, art_text, full_context=full_context)

            if art.get("id"):
                supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()

            for rule in rules:
                rule_sector = (rule.get("sector") or "").strip().upper()
                if rule_sector in EXCLUDED_SECTORS:
                    results["special_excluded"] += 1
                    continue

                supabase.table("law_rule_drafts").insert(
                    _build_draft_row(law_name, label, art.get("id"), art_text, rule)
                ).execute()
                results["drafts_created"] += 1

            results["processed"] += 1
        except Exception as e:
            results["errors"].append({"article": str(art.get("article_no")), "error": str(e)[:100]})

    return {"status": "success", "law_name": law_name, "data": results}


# ── POST /auto-parse-and-approve ───────────────────────────

@router.post("/auto-parse-and-approve")
async def auto_parse_and_approve(body: dict):
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")

    supabase = get_supabase()
    law_id    = body.get("law_id")
    max_art   = int(body.get("max_articles", 30))
    threshold = int(body.get("auto_approve_threshold", 80))

    if not law_id:
        raise HTTPException(status_code=400, detail="law_id 필수")

    lm = supabase.table("law_master").select("law_name").eq("id", law_id).eq("is_active", True).single().execute()
    if not lm.data:
        raise HTTPException(status_code=404, detail="법령 없음")
    law_name = lm.data["law_name"]

    ver = supabase.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver.data:
        return {"status": "success", "law_name": law_name, "data": {"skipped": "버전 없음"}}

    arts = (
        supabase.table("law_article")
        .select("id, article_no, article_title, article_text")
        .eq("law_version_id", ver.data[0]["id"])
        .is_("ai_parsed_at", "null")
        .not_.is_("article_text", "null")
        .order("article_no_sort")
        .limit(max_art)
        .execute()
    )
    articles = arts.data or []

    results = {
        "law_name": law_name,
        "total_articles": len(articles),
        "parsed": 0,
        "drafts_created": 0,
        "auto_approved": 0,
        "pending_review": 0,
        "errors": [],
    }
    now_iso = datetime.now(timezone.utc).isoformat()

    for art in articles:
        try:
            art_text = (art.get("article_text") or "").strip()
            if not art_text or len(art_text) < 20:
                supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
                continue

            label = f"제{art.get('article_no', '')}조{art.get('article_title', '') or ''}"
            full_context = await build_full_context(law_name, label, art.get("id"))
            rules = await call_claude(law_name, art_text, full_context=full_context)

            supabase.table("law_article").update({"ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
            results["parsed"] += 1

            for rule in rules:
                sector = (rule.get("sector") or "").strip().upper()
                if sector in EXCLUDED_SECTORS:
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

                if ob_type == "INSPECT" and conf >= threshold:
                    approved_id = _auto_approve_to_master(supabase, draft)
                    if approved_id:
                        results["auto_approved"] += 1
                    else:
                        results["pending_review"] += 1
                else:
                    results["pending_review"] += 1

        except Exception as e:
            results["errors"].append({
                "article": str(art.get("article_no")),
                "error": str(e)[:100],
            })

    return {"status": "success", "data": results}


# ── POST /bulk-approve-unregistered ───────────────────────

@router.post("/bulk-approve-unregistered")
async def bulk_approve_unregistered(
    secret: str = Query(...),
    limit: int = Query(default=200, le=500),
):
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    supabase = get_supabase()

    res = (
        supabase.table("law_rule_drafts")
        .select("*")
        .eq("status", "APPROVED")
        .is_("registered_rule_id", "null")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    drafts = res.data or []
    ok, fail, skipped = 0, 0, 0

    for d in drafts:
        sector = (d.get("sector") or "").upper()
        if sector in EXCLUDED_SECTORS:
            skipped += 1
            continue
        try:
            rule_id = d.get("draft_rule_id") or f"AI-{d['id'][:8].upper()}"
            if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
                rule_id = rule_id + "-V2"
            if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
                supabase.table("law_rule_drafts").update({
                    "registered_rule_id": rule_id,
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", d["id"]).execute()
                skipped += 1
                continue

            ins = supabase.table("master_building_legal_rules").insert(
                _build_master_payload(d, rule_id)
            ).execute()

            if ins.data:
                supabase.table("law_rule_drafts").update({
                    "registered_rule_id": rule_id,
                    "reviewed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", d["id"]).execute()
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1

    remaining_res = (
        supabase.table("law_rule_drafts")
        .select("id", count="exact")
        .eq("status", "APPROVED")
        .is_("registered_rule_id", "null")
        .execute()
    )
    remaining = remaining_res.count or 0

    return {"status": "success", "data": {
        "processed": len(drafts),
        "ok": ok, "fail": fail, "skipped": skipped,
        "remaining": remaining,
        "done": remaining == 0,
    }}


@router.post("/validate-master")
async def validate_master(body: dict = None):
    body = body or {}
    sector = (body.get("sector") or "ALL").strip().upper()
    supabase = get_supabase()

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
        if key == "duplicate_rule_id":
            continue
        failed_rows.update(ids)

    return {
        "status": "success",
        "data": {
            "sector": sector,
            "total": len(rows),
            "failed": sum(failures.values()),
            "passed": max(0, len(rows) - len(failed_rows)),
            "failures": failures,
            "samples": samples,
            "submit_org_labels": SUBMIT_ORG_LABELS,
        },
    }


_reparse_logger = logging.getLogger("reparse-master")


async def _run_reparse_background(
    job_id: str, sector: str, limit_count: int,
    fill_empty_only: bool, rule_ids: List[str],
):
    """백그라운드에서 master 룰을 1건씩 Sonnet으로 재파싱."""
    supabase = get_supabase()

    try:
        q = supabase.table("master_building_legal_rules").select("*").eq("is_active", True)
        if sector and sector != "ALL":
            q = q.eq("sector", sector)
        if rule_ids:
            q = q.in_("rule_id", rule_ids)
        rows = q.limit(max(limit_count * 3, 50)).execute().data or []
        targets = _pick_reparse_targets(rows, limit_count)

        supabase.table("reparse_job_log").update({
            "total_targeted": len(targets),
        }).eq("job_id", job_id).execute()

        processed = 0
        updated = 0
        skipped = 0
        errors_count = 0
        error_details: List[dict] = []
        changed_fields_total: Dict[str, int] = {}

        for row in targets:
            rid = row.get("rule_id") or ""
            law_name = row.get("law_name") or ""
            law_article = row.get("law_article") or ""

            if not law_name or not law_article:
                skipped += 1
                processed += 1
                supabase.table("reparse_job_log").update({
                    "processed": processed, "skipped": skipped,
                }).eq("job_id", job_id).execute()
                await asyncio.sleep(3)
                continue

            try:
                # 1. build_full_context (DB 조회)
                full_context = await build_full_context(law_name, law_article)
                few_shots = await _fetch_few_shot_examples(supabase, law_name, limit=3)
                prompt = _build_reparse_prompt(row, full_context, few_shots)

                # 2. Claude Sonnet 호출 (timeout=90s)
                parsed = await call_claude_messages_ai(
                    "빈 필드 보강 전용 리라이팅 모델입니다. JSON object 1개만 반환하세요.",
                    prompt,
                    CLAUDE_SONNET_MODEL,
                    _extract_json_payload,
                    ANTHROPIC_API_KEY,
                    max_tokens=1800,
                    timeout=90,
                )
                if not isinstance(parsed, dict):
                    skipped += 1
                    processed += 1
                    supabase.table("reparse_job_log").update({
                        "processed": processed, "skipped": skipped,
                    }).eq("job_id", job_id).execute()
                    await asyncio.sleep(3)
                    continue

                # 3. DB UPDATE
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
                    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
                    supabase.table("master_building_legal_rules").update(patch).eq("id", row["id"]).execute()
                    updated += 1
                else:
                    skipped += 1

                processed += 1

            except Exception as e:
                errors_count += 1
                processed += 1
                error_details.append({"rule_id": rid, "error": str(e)[:200]})
                _reparse_logger.warning(f"[reparse] {rid} 에러: {e}")

            # 4. reparse_job_log UPDATE (매 건)
            supabase.table("reparse_job_log").update({
                "processed": processed,
                "updated": updated,
                "skipped": skipped,
                "errors": errors_count,
                "error_details": error_details[-20:],
                "changed_fields": changed_fields_total,
            }).eq("job_id", job_id).execute()

            # 5. 서버 부하 방지
            await asyncio.sleep(3)

        # 전체 완료 → validate-master 실행
        validate_data = None
        try:
            validate_result = await validate_master({"sector": sector or "ALL"})
            validate_data = validate_result.get("data")
        except Exception as e:
            _reparse_logger.warning(f"[reparse] validate-master 실패: {e}")

        supabase.table("reparse_job_log").update({
            "status": "COMPLETED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "processed": processed,
            "updated": updated,
            "skipped": skipped,
            "errors": errors_count,
            "error_details": error_details,
            "changed_fields": {
                **changed_fields_total,
                "_validation": validate_data or {},
            },
        }).eq("job_id", job_id).execute()

        _reparse_logger.info(
            f"[reparse] job {job_id} 완료: {processed}/{len(targets)} 처리, "
            f"{updated} 수정, {errors_count} 에러"
        )

    except Exception as e:
        _reparse_logger.error(f"[reparse] job {job_id} 실패: {e}")
        try:
            supabase.table("reparse_job_log").update({
                "status": "FAILED",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_details": [{"error": str(e)[:500]}],
            }).eq("job_id", job_id).execute()
        except Exception:
            pass


@router.post("/reparse-master")
async def reparse_master(body: dict, background_tasks: BackgroundTasks):
    """master 룰을 Sonnet으로 재파싱 (백그라운드 처리).
    즉시 job_id 반환, 진행률은 GET /reparse-master/status/{job_id}."""
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")

    sector = (body.get("sector") or "").strip().upper()
    limit_count = int(body.get("limit", 50))
    fill_empty_only = bool(body.get("fill_empty_only", True))
    rule_ids = body.get("rule_ids") or []

    job_id = str(uuid.uuid4())

    # job_log 생성
    supabase = get_supabase()
    supabase.table("reparse_job_log").insert({
        "job_id": job_id,
        "sector": sector or "ALL",
        "status": "RUNNING",
    }).execute()

    background_tasks.add_task(
        _run_reparse_background, job_id, sector, limit_count,
        fill_empty_only, rule_ids,
    )

    return {
        "status": "accepted",
        "job_id": job_id,
        "message": f"재파싱 작업이 시작됐습니다. sector={sector or 'ALL'}, limit={limit_count}",
        "check_status": f"/law-rule-generator/reparse-master/status/{job_id}",
    }


@router.get("/reparse-master/status/{job_id}")
async def reparse_master_status(job_id: str):
    """재파싱 작업 진행률 조회."""
    supabase = get_supabase()
    res = supabase.table("reparse_job_log").select("*").eq(
        "job_id", job_id).order("created_at", desc=True).limit(1).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="해당 job_id를 찾을 수 없습니다")

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


@router.get("/reparse-master/jobs")
async def reparse_master_jobs(
    limit: int = Query(default=10, le=50),
):
    """최근 재파싱 작업 목록 조회."""
    supabase = get_supabase()
    res = supabase.table("reparse_job_log").select(
        "job_id, sector, total_targeted, processed, updated, skipped, errors, status, started_at, completed_at"
    ).order("created_at", desc=True).limit(limit).execute()

    return {"status": "success", "data": res.data or []}


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


# ── GET /drafts ────────────────────────────────────────────
# 주의: /drafts 는 /drafts/{draft_id} 보다 먼저 선언돼야 함

@router.get("/drafts")
async def get_drafts(
    status:         str = Query(""),
    sector:         str = Query(""),
    ob_type:        str = Query(""),
    law_name:       str = Query(""),
    confidence_min: int = Query(0),
    has_condition:  str = Query("", description="true | false | '' (전체)"),  # v1.5.0
    page:           int = Query(1, ge=1),
    page_size:      int = Query(20, ge=1, le=100),
):
    """
    초안 목록 조회
    - has_condition=false → condition_code IS NULL (조건 없는 룰)
    - has_condition=true  → condition_code IS NOT NULL (조건 있는 룰)
    - has_condition=""    → 전체
    """
    supabase = get_supabase()
    q = supabase.table("law_rule_drafts").select("*", count="exact")
    if status:         q = q.eq("status", status)
    if sector:         q = q.eq("sector", sector)
    if ob_type:        q = q.eq("obligation_type", ob_type)
    if law_name:       q = q.ilike("law_name", f"%{law_name}%")
    if confidence_min: q = q.gte("ai_confidence", confidence_min)
    # v1.5.0: condition_code 존재 여부 필터
    if has_condition == "false":
        q = q.is_("condition_code", "null")
    elif has_condition == "true":
        q = q.not_.is_("condition_code", "null")
    q = q.not_.in_("sector", list(EXCLUDED_SECTORS))
    offset = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return {"status": "success", "data": {
        "items": res.data or [], "total": res.count or 0,
        "page": page, "page_size": page_size}}


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str):
    supabase = get_supabase()
    res = supabase.table("law_rule_drafts").select("*").eq("id", draft_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    return {"status": "success", "data": res.data}


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


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, body: dict = None):
    supabase = get_supabase()
    body = body or {}

    dr = supabase.table("law_rule_drafts").select("*").eq("id", draft_id).single().execute()
    if not dr.data:
        raise HTTPException(status_code=404, detail="초안 없음")
    d = dr.data

    if (d.get("sector") or "").upper() in EXCLUDED_SECTORS:
        raise HTTPException(status_code=400, detail="특수시설 섹터는 현재 master 등록 불가")

    rule_id = body.get("rule_id") or d.get("draft_rule_id") or f"AI-{draft_id[:8].upper()}"
    if supabase.table("master_building_legal_rules").select("rule_id").eq("rule_id", rule_id).execute().data:
        rule_id = rule_id + "-V2"

    ins = supabase.table("master_building_legal_rules").insert(
        _build_master_payload(d, rule_id)
    ).execute()
    if not ins.data:
        raise HTTPException(status_code=500, detail="master 등록 실패")

    supabase.table("law_rule_drafts").update({
        "status": "APPROVED", "registered_rule_id": rule_id,
        "reviewer_note": body.get("reviewer_note"),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", draft_id).execute()

    return {"status": "success", "rule_id": rule_id,
            "message": f"master에 {rule_id}로 등록됐습니다.", "data": ins.data[0]}


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
