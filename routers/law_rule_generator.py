"""
AI 법령 룰 생성기 — law_rule_generator.py
============================================
Claude Haiku API로 법령 조문 → 판정룰 초안 자동 생성.

상태 흐름:
  PENDING → (승인) APPROVED → (법령개정) NEEDS_REVIEW → (재검토) APPROVED/REJECTED
  PENDING → (거부) REJECTED
  PENDING → (수정) MODIFIED → (승인) APPROVED

v1.8.0 (2026-04-25):
  [ADD] POST /auto-parse-all — 모든 미파싱 법령 일괄 처리 (백그라운드)
        로컬 스크립트(scripts/auto_parse_all.py) Railway 내장 endpoint 화
        환경변수 의존 0, 인코딩 문제 0, curl 1회로 시작
  [REUSE] reparse_job_log 테이블 재사용 (sector="AUTO_PARSE_ALL" 마커)
          진행률은 기존 GET /reparse-master/status/{job_id} 그대로 사용

v1.7.0 (2026-04-25):
  [FIX] SYSTEM_PROMPT 5영역 확장 — "산업안전" 한정 편향 제거
        재난·환경·근로자보호·시설·산안 모두 추출 대상
  [FIX] USER_PROMPT_TEMPLATE — "안전관리 의무" → "사업장 의무"
  [FIX] auto-parse-and-approve 자동승인 조건 확장
        기존: INSPECT만 자동 master 등록
        변경: APPOINT/INSPECT/NOTIFY/REPORT/ACTION 5개 모두
              + condition_code 게이트 (4/24 학습)
  [KEEP] 학교·병원·사회복지시설 건너뛰기 룰 유지

v1.6.0 (2026-04-20):
  [FIX] POST /reparse-master — BackgroundTasks 비동기 전환 (서버 타임아웃 방지)
  [ADD] GET /reparse-master/status/{job_id} — 진행률 조회
  [ADD] GET /reparse-master/jobs — 최근 작업 목록
  [ADD] reparse_job_log 테이블 (DDL: sql/20260420_reparse_job_log.sql)

v1.5.0 (2026-04-05):
  [ADD] GET /drafts — has_condition 파라미터 추가

v1.4.0 (2026-04-03):
  [ADD] POST /bulk-approve-unregistered

v1.3.0 (2026-04-03):
  [ADD] POST /auto-parse-and-approve

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
from services.safe_db_update import safe_update_master

router = APIRouter(prefix="/law-rule-generator", tags=["AI룰생성"])

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-sonnet-4-20250514"
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

# v1.7.0: 자동승인 가능 의무 유형 (INSPECT 한정 → 5개 모두)
AUTO_APPROVE_ELIGIBLE_TYPES = {"INSPECT", "APPOINT", "NOTIFY", "REPORT", "ACTION"}

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

# v1.7.0: SYSTEM_PROMPT 5영역 확장
SYSTEM_PROMPT = """당신은 한국 사업장 의무 법령 전문가입니다.
법령 원문(본조+시행령+별표+벌칙)을 분석하여 사업장이 이행해야 할 판정 룰을 JSON 형식으로 추출합니다.

추출 대상 영역 (모든 사업장 의무 — 산업안전 외 영역도 포함):
1. 산업안전·보건 의무 (산안법, 산안기준규칙, 화학물질관리법 등)
2. 재난·안전관리 의무 (재난기본법 — 모든 사업장 재난 대비 의무)
3. 환경관리 의무 (탄소중립·녹색성장 기본법, 토양환경보전법, 잔류성오염물질 관리법, 악취방지법, 소음·진동관리법)
4. 근로자 보호 의무 (파견근로자보호법, 근로기준법)
5. 시설·건물 관리 의무 (주택법, 건축법, 화재예방법, 소방시설법, 다중이용업소법 등)

추출 대상 의무 유형:
- APPOINT: 안전관리자·재난관리책임자·환경관리자·소방안전관리자 등 선임 의무
- INSPECT: 정기점검·안전검사·환경측정 의무
- NOTIFY: 신고·보고·제출 의무 (재난신고·환경신고 포함)
- REPORT: 기록·보존 의무
- ACTION: 조치·설치·이행 의무 (재난대비·환경기준 준수 포함)

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

섹터 코드 (반드시 아래 5가지 중 하나만 사용):
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

# v1.7.0: USER_PROMPT_TEMPLATE — "안전관리 의무" → "사업장 의무"
USER_PROMPT_TEMPLATE = """다음 법령 조문을 분석하여 판정 룰을 추출해주세요.

법령명: {law_name}
핵심 조문: {article_text}

[풀 컨텍스트]
{full_context}

[좋은 예시 1개]
{few_shot}

위 조문에서 사업장 의무(선임·점검·신고·보고·조치)를 추출하여 다음 JSON 형식으로 반환하세요.
사업장이 직접 이행할 의무가 없는 조문이면 []을 반환하세요.

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

                # v1.7.0: 자동승인 조건 확장
                has_condition = bool(rule.get("condition_code"))
                if (
                    ob_type in AUTO_APPROVE_ELIGIBLE_TYPES
                    and conf >= threshold
                    and has_condition
                ):
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


# ── v1.8.0: POST /auto-parse-all (백그라운드) ─────────────────────────────

async def _process_one_law_for_auto_parse(
    supabase, law_id: str, law_name: str,
    max_articles: int, threshold: int,
) -> Dict[str, int]:
    """단일 법령의 미파싱 article 처리 + 고신뢰도 자동승인.
    auto_parse_and_approve 라우터 핵심 로직과 동일."""
    stats = {"drafts": 0, "approved": 0, "errors": 0}

    ver = supabase.table("law_version").select("id").eq(
        "law_id", law_id).eq("is_current", True).limit(1).execute()
    if not ver.data:
        return stats

    arts = (
        supabase.table("law_article")
        .select("id, article_no, article_title, article_text")
        .eq("law_version_id", ver.data[0]["id"])
        .is_("ai_parsed_at", "null")
        .not_.is_("article_text", "null")
        .order("article_no_sort")
        .limit(max_articles)
        .execute()
    )
    articles = arts.data or []
    now_iso = datetime.now(timezone.utc).isoformat()

    for art in articles:
        try:
            art_text = (art.get("article_text") or "").strip()
            if not art_text or len(art_text) < 20:
                supabase.table("law_article").update({
                    "ai_parsed_at": now_iso}).eq("id", art["id"]).execute()
                continue

            label = f"제{art.get('article_no', '')}조{art.get('article_title', '') or ''}"
            full_context = await build_full_context(law_name, label, art.get("id"))
            rules = await call_claude(law_name, art_text, full_context=full_context)

            supabase.table("law_article").update({
                "ai_parsed_at": now_iso}).eq("id", art["id"]).execute()

            for rule in rules:
                sector = (rule.get("sector") or "").strip().upper()
                if sector in EXCLUDED_SECTORS:
                    continue

                conf = int(rule.get("ai_confidence") or 0)
                ob_type = rule.get("obligation_type", "")
                has_condition = bool(rule.get("condition_code"))

                row = _build_draft_row(
                    law_name, label, art.get("id"), art_text, rule)
                row["ai_confidence"] = conf
                ins = supabase.table("law_rule_drafts").insert(row).execute()
                if not ins.data:
                    continue
                stats["drafts"] += 1
                draft = ins.data[0]

                if (
                    ob_type in AUTO_APPROVE_ELIGIBLE_TYPES
                    and conf >= threshold
                    and has_condition
                ):
                    approved_id = _auto_approve_to_master(supabase, draft)
                    if approved_id:
                        stats["approved"] += 1
        except Exception as e:
            stats["errors"] += 1
            _reparse_logger.warning(
                f"[auto-parse-all] {law_name[:20]}/제{art.get('article_no')}조 에러: {str(e)[:120]}")

    return stats


def _bulk_approve_remaining(supabase) -> int:
    """APPROVED + 미등록 draft를 master 테이블에 일괄 등록.
    bulk_approve_unregistered 라우터 로직과 동일, 5회 반복."""
    total_added = 0
    for _ in range(5):
        res = (
            supabase.table("law_rule_drafts")
            .select("*")
            .eq("status", "APPROVED")
            .is_("registered_rule_id", "null")
            .order("created_at")
            .limit(500)
            .execute()
        )
        drafts = res.data or []
        if not drafts:
            break

        added_in_round = 0
        for d in drafts:
            sector = (d.get("sector") or "").upper()
            if sector in EXCLUDED_SECTORS:
                continue
            try:
                rule_id = d.get("draft_rule_id") or f"AI-{d['id'][:8].upper()}"
                if supabase.table("master_building_legal_rules").select(
                    "rule_id").eq("rule_id", rule_id).execute().data:
                    rule_id = rule_id + "-V2"
                if supabase.table("master_building_legal_rules").select(
                    "rule_id").eq("rule_id", rule_id).execute().data:
                    supabase.table("law_rule_drafts").update({
                        "registered_rule_id": rule_id,
                        "reviewed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", d["id"]).execute()
                    continue

                ins = supabase.table("master_building_legal_rules").insert(
                    _build_master_payload(d, rule_id)
                ).execute()

                if ins.data:
                    supabase.table("law_rule_drafts").update({
                        "registered_rule_id": rule_id,
                        "reviewed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", d["id"]).execute()
                    added_in_round += 1
            except Exception:
                pass

        total_added += added_in_round
        if added_in_round == 0:
            break

    return total_added


async def _run_auto_parse_all_background(
    job_id: str, max_articles_per_law: int, threshold: int,
):
    """백그라운드로 모든 미파싱 법령 순차 처리 + bulk-approve."""
    supabase = get_supabase()

    try:
        # 1. 미파싱 article 있는 법령만 추출 (article_count > parsed_count)
        laws_q = (
            supabase.table("law_master")
            .select("id, law_name")
            .eq("is_active", True)
            .order("law_name")
            .execute()
        )
        all_laws = laws_q.data or []

        target_laws = []
        for law in all_laws:
            ver = supabase.table("law_version").select("id").eq(
                "law_id", law["id"]).eq("is_current", True).limit(1).execute()
            if not ver.data:
                continue
            unparsed = supabase.table("law_article").select(
                "id", count="exact"
            ).eq("law_version_id", ver.data[0]["id"]
            ).is_("ai_parsed_at", "null"
            ).not_.is_("article_text", "null").execute()
            n = unparsed.count or 0
            if n > 0:
                target_laws.append({
                    "law_id": law["id"],
                    "law_name": law["law_name"],
                    "unparsed": n,
                })

        # 작은 법령부터 처리 (실패 시 영향 범위 최소화)
        target_laws.sort(key=lambda x: x["unparsed"])

        supabase.table("reparse_job_log").update({
            "total_targeted": len(target_laws),
        }).eq("job_id", job_id).execute()

        processed_laws = 0
        failed_laws = 0
        total_drafts = 0
        total_approved = 0
        total_article_errors = 0
        errors_list: List[dict] = []

        # 2. 법령별 순차 처리
        for law in target_laws:
            try:
                stats = await _process_one_law_for_auto_parse(
                    supabase, law["law_id"], law["law_name"],
                    max_articles_per_law, threshold,
                )
                total_drafts += stats["drafts"]
                total_approved += stats["approved"]
                total_article_errors += stats["errors"]
                processed_laws += 1
            except Exception as e:
                failed_laws += 1
                processed_laws += 1
                errors_list.append({
                    "law": law["law_name"][:40],
                    "error": str(e)[:200],
                })
                _reparse_logger.warning(
                    f"[auto-parse-all] {law['law_name'][:20]} 실패: {e}")

            # 진행률 업데이트
            supabase.table("reparse_job_log").update({
                "processed": processed_laws,
                "updated": total_drafts,
                "skipped": failed_laws,
                "errors": total_article_errors + failed_laws,
                "error_details": errors_list[-20:],
                "changed_fields": {
                    "drafts_created": total_drafts,
                    "auto_approved": total_approved,
                    "law_failed": failed_laws,
                    "article_errors": total_article_errors,
                    "current_law": law["law_name"][:40],
                },
            }).eq("job_id", job_id).execute()

            # 서버 부하 방지
            await asyncio.sleep(1)

        # 3. bulk-approve 잔여
        try:
            bulk_added = _bulk_approve_remaining(supabase)
        except Exception as e:
            bulk_added = 0
            _reparse_logger.warning(f"[auto-parse-all] bulk-approve 실패: {e}")

        # 4. 완료 마킹
        supabase.table("reparse_job_log").update({
            "status": "COMPLETED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "processed": processed_laws,
            "updated": total_drafts,
            "skipped": failed_laws,
            "errors": total_article_errors + failed_laws,
            "error_details": errors_list,
            "changed_fields": {
                "drafts_created": total_drafts,
                "auto_approved": total_approved,
                "bulk_approve_added": bulk_added,
                "law_failed": failed_laws,
                "article_errors": total_article_errors,
                "total_master_added": total_approved + bulk_added,
            },
        }).eq("job_id", job_id).execute()

        _reparse_logger.info(
            f"[auto-parse-all] job {job_id} 완료: "
            f"법령 {processed_laws}/{len(target_laws)}, "
            f"draft+{total_drafts}, 자동승인+{total_approved}, "
            f"bulk+{bulk_added}, 법령실패 {failed_laws}, 조문에러 {total_article_errors}"
        )

    except Exception as e:
        _reparse_logger.error(f"[auto-parse-all] job {job_id} 실패: {e}")
        try:
            supabase.table("reparse_job_log").update({
                "status": "FAILED",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_details": [{"error": str(e)[:500]}],
            }).eq("job_id", job_id).execute()
        except Exception:
            pass


@router.post("/auto-parse-all")
async def auto_parse_all_endpoint(body: dict, background_tasks: BackgroundTasks):
    """모든 미파싱 법령을 순차 처리 + bulk-approve (백그라운드).
    즉시 job_id 반환, 진행률은 GET /reparse-master/status/{job_id}.

    body:
      secret: INTERNAL_API_SECRET (필수)
      max_articles_per_law: 법령당 처리 article 수 (기본 80)
      auto_approve_threshold: 자동승인 신뢰도 임계값 (기본 80)
    """
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")

    max_articles_per_law = int(body.get("max_articles_per_law", 80))
    threshold = int(body.get("auto_approve_threshold", 80))

    job_id = str(uuid.uuid4())

    supabase = get_supabase()
    supabase.table("reparse_job_log").insert({
        "job_id": job_id,
        "sector": "AUTO_PARSE_ALL",
        "status": "RUNNING",
    }).execute()

    background_tasks.add_task(
        _run_auto_parse_all_background, job_id, max_articles_per_law, threshold,
    )

    return {
        "status": "accepted",
        "job_id": job_id,
        "message": "전체 자동 파싱 작업이 시작됐습니다.",
        "check_status": f"/law-rule-generator/reparse-master/status/{job_id}",
    }


# ── reparse-master (v1.6.0) ────────────────────────────────────────────────

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
                full_context = await build_full_context(law_name, law_article)
                few_shots = await _fetch_few_shot_examples(supabase, law_name, limit=3)
                prompt = _build_reparse_prompt(row, full_context, few_shots)

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
                    any_saved, s_count, f_count = safe_update_master(
                        supabase, row["id"], patch, rule_id=rid)
                    if any_saved:
                        updated += 1
                    else:
                        skipped += 1
                    if f_count > 0:
                        error_details.append({
                            "rule_id": rid,
                            "error": f"partial: {s_count} saved, {f_count} type errors skipped"
                        })
                else:
                    skipped += 1

                processed += 1

            except Exception as e:
                errors_count += 1
                processed += 1
                error_details.append({"rule_id": rid, "error": str(e)[:200]})
                _reparse_logger.warning(f"[reparse] {rid} 에러: {e}")

            supabase.table("reparse_job_log").update({
                "processed": processed,
                "updated": updated,
                "skipped": skipped,
                "errors": errors_count,
                "error_details": error_details[-20:],
                "changed_fields": changed_fields_total,
            }).eq("job_id", job_id).execute()

            await asyncio.sleep(3)

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
    """master 룰을 Sonnet으로 재파싱 (백그라운드 처리)."""
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="내부 전용 엔드포인트")

    sector = (body.get("sector") or "").strip().upper()
    limit_count = int(body.get("limit", 50))
    fill_empty_only = bool(body.get("fill_empty_only", True))
    rule_ids = body.get("rule_ids") or []

    job_id = str(uuid.uuid4())

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
    """재파싱 작업 진행률 조회 (auto-parse-all 도 동일 endpoint 사용)."""
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
    """최근 작업 목록 조회 (reparse / auto-parse-all 모두 포함)."""
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

@router.get("/drafts")
async def get_drafts(
    status:         str = Query(""),
    sector:         str = Query(""),
    ob_type:        str = Query(""),
    law_name:       str = Query(""),
    confidence_min: int = Query(0),
    has_condition:  str = Query("", description="true | false | '' (전체)"),
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
