"""
TAI Safe x OpenAI GPT-4o 카피라이팅 API - v1.0.1
"""
import os
import json
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI"])

# OpenAI 클라이언트
try:
    from openai import OpenAI
    _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
except ImportError:
    _client = None
    log.warning("openai 패키지 미설치")

# 브랜드 컨텍스트
BRAND_CONTEXT = (
    "[TAI Safe 브랜드]\n"
    "- 서비스: 산업안전 법령 기반 SaaS 플랫폼 (taieng.co.kr)\n"
    "- 핵심 가치: 안전관리자 혼자 처리하는 구조 -> 작업자 분산 안전관리\n"
    "- 기능: 법령진단 -> 점검일정 자동생성 -> 작업자배정 -> 알림 -> 완료기록\n"
    "- 제품: SaaS(산업/건설/건물), 법령진단, 전문가연결 플랫폼\n"
    "- 가격: SaaS 79,000원/월(Basic), 149,000원/월(Premium)\n"
    "- 특허: 2026-03-29 출원 (조건코드 기반 산업안전 법령 자동 판정 시스템)\n"
    "- 주의: 인력소개업/알선/소개 표현 절대 금지. 플랫폼이용료 모델."
)

# 섹션별 프롬프트 (단순 문자열로 작성 — triple-quote 충돌 방지)
SECTION_PROMPTS = {
    "hero": (
        "메인페이지 히어로 롤링 배너 5개 슬라이드를 작성하세요.\n"
        "각 슬라이드는 다른 타겟: 전체방문자, 안전관리자, 법령진단희망기업, 전문가연결희망기업, 비전공감자.\n"
        "JSON: {\"slides\":[{\"target\":\"\",\"headline\":\"(20자이내)\",\"sub\":\"(40자이내)\",\"cta\":\"(8자이내)\"}]}\n"
        "JSON만 반환."
    ),
    "diagnosis": (
        "법령진단 소개 섹션 카피를 작성하세요.\n"
        "JSON: {\"headline\":\"(30자이내)\",\"sub\":\"(60자이내)\","
        "\"stat1\":\"통계문구1\",\"stat2\":\"통계문구2\",\"stat3\":\"통계문구3\","
        "\"cta_building\":\"건물진단버튼(6자)\",\"cta_industry\":\"산업진단버튼(6자)\","
        "\"cta_construction\":\"건설진단버튼(6자)\",\"free_guide\":\"무료진단유도문구(40자이내)\"}\n"
        "JSON만 반환."
    ),
    "saas": (
        "SaaS 서비스 소개 섹션 카피를 작성하세요.\n"
        "JSON: {\"headline\":\"(30자이내)\",\"sub\":\"(60자이내)\","
        "\"flow\":[\"1단계(15자)\",\"2단계(15자)\",\"3단계(15자)\"],"
        "\"building_title\":\"건물카드제목(15자)\",\"building_desc\":\"건물카드설명(30자)\","
        "\"industry_title\":\"산업카드제목(15자)\",\"industry_desc\":\"산업카드설명(30자)\","
        "\"construction_title\":\"건설카드제목(15자)\",\"construction_desc\":\"건설카드설명(30자)\"}\n"
        "JSON만 반환."
    ),
    "expert_safety": (
        "안전관리자 선임 지원 섹션 카피를 작성하세요.\n"
        "주의: 인력소개업/알선/소개 표현 절대 금지. 플랫폼이용료 모델. 연결신청 표현 사용.\n"
        "JSON: {\"headline\":\"(30자이내)\","
        "\"demand_points\":[\"기업혜택1(20자)\",\"기업혜택2(20자)\",\"기업혜택3(20자)\"],"
        "\"supply_points\":[\"전문가혜택1(20자)\",\"전문가혜택2(20자)\",\"전문가혜택3(20자)\"],"
        "\"cta_demand\":\"기업CTA(8자)\",\"cta_supply\":\"전문가CTA(8자)\"}\n"
        "JSON만 반환."
    ),
    "vision": (
        "컨설팅/교육 비전 소개 섹션 카피를 작성하세요.\n"
        "JSON: {\"headline\":\"(30자이내)\","
        "\"consulting_title\":\"(15자)\",\"consulting_desc\":\"(40자)\","
        "\"education_title\":\"(15자)\",\"education_desc\":\"(40자)\","
        "\"badge\":\"준비중뱃지문구(10자)\"}\n"
        "JSON만 반환."
    ),
    "slogan": (
        "TAI Safe 대표 슬로건 {count}개를 작성하세요.\n"
        "조건: 20자 이내, 기억하기 쉽고 전문적.\n"
        "JSON: {\"slogans\":[\"슬로건1\",\"슬로건2\"...]}\n"
        "JSON만 반환."
    ),
}


# ── 모델 ──
class CopywriteRequest(BaseModel):
    section: str
    context: Optional[str] = None
    tone: Optional[str] = "professional_trust"
    language: Optional[str] = "ko"
    variants: Optional[int] = 1

class BatchCopywriteRequest(BaseModel):
    sections: List[str]
    context: Optional[str] = None
    language: Optional[str] = "ko"

class SloganRequest(BaseModel):
    count: Optional[int] = 5
    focus: Optional[str] = None


# ── 헬퍼 ──
def _tone_desc(tone: str) -> str:
    return {
        "professional_trust": "전문적이고 신뢰감 있고 직접적. 해결 중심.",
        "urgent": "긴박감 있고 위기의식 자극. 수치 강조.",
        "friendly": "친근하고 파트너 같은 느낌.",
    }.get(tone, "전문적")


async def _call_gpt(system_msg: str, user_msg: str, temperature: float = 0.7) -> str:
    if not _client:
        raise HTTPException(status_code=500, detail="openai 패키지 미설치")
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY 미설정")
    try:
        resp = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content
    except Exception as e:
        log.error("GPT 호출 실패: %s", e)
        raise HTTPException(status_code=502, detail=f"GPT 호출 실패: {e}")


# ── 엔드포인트 ──
@router.post("/copywrite")
async def generate_copy(body: CopywriteRequest):
    prompt = SECTION_PROMPTS.get(body.section)
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 섹션. 가능: {list(SECTION_PROMPTS.keys())}"
        )

    system_msg = (
        f"당신은 TAI Safe의 마케팅 카피라이터입니다.\n\n"
        f"{BRAND_CONTEXT}\n\n"
        f"톤: {_tone_desc(body.tone)}\n"
        f"언어: {'한국어' if body.language == 'ko' else '영어'}\n"
        "반드시 JSON만 반환."
    )
    extra = f"\n\n추가 컨텍스트: {body.context}" if body.context else ""
    user_msg = prompt + extra

    raw = await _call_gpt(system_msg, user_msg)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"raw": raw}

    return {"status": "success", "data": {"section": body.section, "copy": parsed}}


@router.post("/copywrite/batch")
async def generate_batch(body: BatchCopywriteRequest):
    results = {}
    for section in body.sections:
        prompt = SECTION_PROMPTS.get(section)
        if not prompt:
            results[section] = {"error": "지원하지 않는 섹션"}
            continue

        system_msg = (
            f"당신은 TAI Safe의 마케팅 카피라이터입니다.\n{BRAND_CONTEXT}\n"
            f"언어: {'한국어' if body.language == 'ko' else '영어'}\nJSON만 반환."
        )
        user_msg = prompt + (f"\n\n컨텍스트: {body.context}" if body.context else "")
        try:
            raw = await _call_gpt(system_msg, user_msg)
            results[section] = json.loads(raw)
        except Exception as e:
            results[section] = {"error": str(e)}

    return {"status": "success", "data": results}


@router.post("/slogan")
async def generate_slogan(body: SloganRequest):
    focus_map = {
        "safety": "안전 강조",
        "tech": "기술/자동화 강조",
        "trust": "신뢰/공신력 강조",
        "platform": "플랫폼/연결 강조",
    }
    focus_desc = focus_map.get(body.focus, "전체적") if body.focus else "전체적"

    system_msg = f"당신은 TAI Safe의 브랜드 슬로건 전문가입니다.\n{BRAND_CONTEXT}"
    user_msg = (
        f"강조: {focus_desc}\n"
        f"한국어로 {body.count}개 슬로건 (각 20자 이내, 기억하기 쉬운, 전문적).\n"
        "JSON: {\"slogans\":[...]} 형식만 반환."
    )

    raw = await _call_gpt(system_msg, user_msg, temperature=0.9)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"slogans": [raw]}

    return {"status": "success", "data": parsed}
