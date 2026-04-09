"""
TAI Safe × OpenAI GPT-4o 카피라이팅 API — v1.0.0

GPT-4o를 사용해 taieng.co.kr 홈페이지 각 섹션의
헤드라인, 서브텍스트, CTA 문구를 자동 생성합니다.

API:
  POST /ai/copywrite          섹션별 카피 생성
  POST /ai/copywrite/batch    전체 섹션 일괄 생성
  POST /ai/slogan             슬로건 생성
"""
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI"])

# =====================================================
# OpenAI 클라이언트 초기화
# =====================================================
try:
    from openai import OpenAI
    _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
except ImportError:
    _client = None
    log.warning("openai 패키지 미설치. pip install openai 필요")

# =====================================================
# TAI Safe 브랜드 컨텍스트
# =====================================================
BRAND_CONTEXT = """
[TAI Safe 브랜드 컨텍스트]
- 회사명: TAI Engineering (주)TAI엔지니어링
- 서비스: 산업안전 법령 기반 SaaS 플랫폼
- 핸심 가치: 안전관리자 혼자 모든 의무를 처리하는 구조 → 작업자가 직접 참여하는 분산 안전관리
- 주요 기능: 법령진단 → 점검일정 자동생성 → 작업자 배정 → 알림 발송 → 완료 기록
- 대상 제품: SaaS(산업/건설/건물), 법령진단, 전문가연결 플랫폼
- 단가: SaaS 79,000원/월 (Basic), 149,000원/월 (Premium)
- 특허 출원: 2026-03-29 (조건코드 기반 산업안전 법령 자동 판정 시스템)
- 주의: 인력소개업 표현 금지, 플랫폼 이용료 모델
"""

SECTION_PROMPTS = {
    "hero": """
메인페이지 히어로 롤링 배너 5개 슬라이드를 작성하세요.
각 슬라이드는 다른 색당 타겟을 가집니다:
1. 전체 방문자 대상
2. 안전관리자 (SA) 대상
3. 법령진단 원하는 기업 대상
4. 전문가 연결 필요 기업 대상
5. 비전/하이라이트 대상

각 슬라이드:
- headline: 주제 (20자 이내)
- sub: 부제 (40자 이내)
- cta: CTA 버튼 문구 (8자 이내)
- target: 타겟 설명
""",
    "diagnosis": """
법령진단 소개 섹션 컨텐츠를 작성하세요.
- 상단 위기감 통계 3개 (실제 수치 사용: 중대재해처벨법 위반 적발 347% 증가, 최대 10억 벌금 등)
- 섹션 헤드라인 (30자 이내)
- 서브 텍스트 (60자 이내)
- 3종 진단 버튼 라벨: [건물 무료진단] [산업 무료진단] [건설 무료진단]
- 무료진단 유도 문야 (1줄)
""",
    "saas": """
SaaS 서비스 소개 섹션 컨텐츠를 작성하세요.
- 섹션 헤드라인 (30자 이내)
- 서브 텍스트 (60자 이내)
- 간단한 동작 방식 설명 (3단계, 각 20자 이내)
  1. 법령진단 → 일정자동생성
  2. 작업자에게 배정+알림
  3. 완료확인+실적및처
- 각 종류별 카드 타이틀
  building_title: 건물 안전관리 (20자)
  industry_title: 산업 안전관리 (20자)
  construction_title: 건설 안전관리 (20자)
""",
    "expert_safety": """
안전관리 전문가 연결 소개 섹션 컨텐츠를 작성하세요.
"""인력소개업"", ""알선"", ""소개"" 같은 표현은 절대 사용하지 마세요.
플랫폼 이용료 모델이며, 수요자와 전문가를 연결하는 환경을 제공하는 서비스입니다.
- 섹션 헤드라인
- 수요자용 컨텐츠 3빭릿
- 전문가용 컨텐츠 3빭릿
- 수요자 CTA 버튼, 전문가 CTA 버튼
""",
    "vision": """
컨설팅/교육 비전 소개 섹션 컨텐츠를 작성하세요.
- 섹션 헤드라인 (미래지향적, 30자 이내)
- 컨설팅 타이틀/서브텍스트
- 교육 타이틀/서브텍스트
- 준비 중 배지 문구
""",
}


# =====================================================
# 모델
# =====================================================
class CopywriteRequest(BaseModel):
    section: str                        # hero | diagnosis | saas | expert_safety | vision
    context: Optional[str] = None       # 추가 컨텍스트
    tone: Optional[str] = "professional_trust"  # professional_trust | urgent | friendly
    language: Optional[str] = "ko"     # ko | en
    variants: Optional[int] = 1         # 생성할 안 개수

class BatchCopywriteRequest(BaseModel):
    sections: List[str]
    context: Optional[str] = None
    language: Optional[str] = "ko"

class SloganRequest(BaseModel):
    count: Optional[int] = 5
    focus: Optional[str] = None         # safety | tech | trust | platform


# =====================================================
# 티에이시스턴
# =====================================================
def _get_tone_desc(tone: str) -> str:
    return {
        "professional_trust": "전문적이고 신뢰감 있고 직접적. 공포보다 해결 중심.",
        "urgent": "직접적이고 긴법감 있음. 숫자와 구체적 위험을 강조.",
        "friendly": "친근하고 쉽게. 파트너 같은 느낙.",
    }.get(tone, "전문적")


async def _call_gpt(system: str, user: str, temperature: float = 0.7) -> str:
    if not _client:
        raise HTTPException(status_code=500, detail="OpenAI 클라이언트 초기화 실패. pip install openai")
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
    try:
        resp = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content
    except Exception as e:
        log.error(f"GPT 호출 실패: {e}")
        raise HTTPException(status_code=502, detail=f"GPT 호출 실패: {str(e)}")


# =====================================================
# 엔드포인트
# =====================================================
@router.post("/copywrite")
async def generate_copy(body: CopywriteRequest):
    """
    섹션별 카피 생성.
    section: hero | diagnosis | saas | expert_safety | vision
    """
    section_prompt = SECTION_PROMPTS.get(body.section)
    if not section_prompt:
        available = list(SECTION_PROMPTS.keys())
        raise HTTPException(status_code=400, detail=f"지원하지 않는 섹션입니다. 사용 가능: {available}")

    system = f"""당신은 TAI Safe의 마케팅 컨설턴트입니다.

{BRAND_CONTEXT}

톤: {_get_tone_desc(body.tone)}
언어: {'한국어' if body.language == 'ko' else '영어'}
성공적인 SaaS 랜딩페이지 컨텐츠를 JSON 형식으로 반환하세요.
"""

    user = f"""{section_prompt}

{"웹 컨텍스트: " + body.context if body.context else ""}

{f'{body.variants}가지 안으로 만들어주세요. JSON 배열에 담아주세요.' if body.variants > 1 else ''}
다른 텝스트 없이 JSON만 반환."""

    content = await _call_gpt(system, user)

    import json
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"raw": content}

    return {
        "status": "success",
        "data": {
            "section": body.section,
            "language": body.language,
            "copy": parsed,
        }
    }


@router.post("/copywrite/batch")
async def generate_batch(body: BatchCopywriteRequest):
    """
    여러 섹션 일괄 생성.
    """
    results = {}
    for section in body.sections:
        prompt = SECTION_PROMPTS.get(section)
        if not prompt:
            results[section] = {"error": "지원하지 않는 섹션"}
            continue

        system = f"""당신은 TAI Safe의 마케팅 컨설턴트입니다.
{BRAND_CONTEXT}
언어: {'한국어' if body.language == 'ko' else '영어'}
JSON만 반환."""
        user = prompt + (f"\n\n컨텍스트: {body.context}" if body.context else "")

        try:
            import json
            content = await _call_gpt(system, user)
            results[section] = json.loads(content)
        except Exception as e:
            results[section] = {"error": str(e)}

    return {"status": "success", "data": results}


@router.post("/slogan")
async def generate_slogan(body: SloganRequest):
    """
    TAI Safe 주요 슬로건 생성.
    """
    focus_map = {
        "safety": "안전 강조",
        "tech": "기술/자동화 강조",
        "trust": "신뢰/공신력 강조",
        "platform": "플랫폼/연결 강조",
    }
    focus_desc = focus_map.get(body.focus, "법령과 기술의 결합") if body.focus else "전체적"

    system = f"""당신은 TAI Safe의 브랜드 슬로건 전문가입니다.
{BRAND_CONTEXT}
"""
    user = f"""강조할 점: {focus_desc}
한국어로 {body.count}개의 다양한 슬로건을 만들어주세요.
조건: 20자 이내, 기억하기 쉬운, 전문적
다른 텍스트 없이 JSON 배열 {{'slogans': [...]}} 형식으로만."""

    import json
    content = await _call_gpt(system, user, temperature=0.9)
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"slogans": [content]}

    return {"status": "success", "data": parsed}
