"""
TAI Safe x OpenAI GPT-4o 카피라이팅 API - v1.1.0
v1.1.0: 시스템 프롬프트 전면 개선 — 타겟 페르소나 고통 기반, 스토리텔링 중심
"""
import os
import json
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI"])

try:
    from openai import OpenAI
    _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
except ImportError:
    _client = None
    log.warning("openai 패키지 미설치")

# ── 브랜드 + 페르소나 컨텍스트 (강화) ──
BRAND_CONTEXT = """
[TAI Safe 서비스]
- 산업안전 법령 기반 SaaS 플랫폼 (taieng.co.kr)
- 법령진단 -> 점검일정 자동생성 -> 작업자배정 -> D-3 알림 -> 완료기록
- 가격: 79,000원/월(Basic), 149,000원/월(Premium)
- 특허 출원: 조건코드 기반 산업안전 법령 자동 판정 시스템

[핵심 가치]
안전관리자 혼자 모든 법령 의무를 처리하는 구조에서 벗어나,
작업자 스스로 참여하는 분산형 안전관리로 전환.
안전관리자의 역할: 직접 하는 사람 -> 배정하고 모니터링하는 사람.

[타겟 페르소나]
1. 이창은 (중소기업 대표/공장장, 50대, 직설적)
   - 직원 30명 제조업체 운영
   - "중대재해처벌법 때문에 내가 감방 가는 거 아냐?" 불안
   - 안전 담당자 뽑기엔 규모가 작고, 혼자 챙기기엔 너무 많음
   - 법령 용어 어렵고, 뭘 지켜야 하는지 정확히 모름
   - "빨리 결과 보여줘. 설명 길면 안 봄."

2. 박안전 (안전관리자, 겸직, 40대)
   - 총무팀장이면서 안전관리자도 겸직
   - 산업안전보건법이 개정됐는데 뭐가 바뀐지 모름
   - 점검일지 형식도 매번 검색해서 찾음
   - 적발되면 대표님한테 어떻게 설명하나 걱정
   - "나 혼자 다 해야 하는데 방법을 모르겠어요"

[카피 금지 표현]
- 교과서식: "새로운 기준", "함께하세요", "더 나은 미래", "스마트한 안전"
- 두루뭉술: "간편하게", "쉽게", "편리하게", "효율적으로"
- 인력소개업 연상: "인력 소개", "알선", "연결해드립니다"

[좋은 카피의 조건]
- 타겟이 겪는 구체적 상황에서 출발
- 숫자/법령명/벌금 등 구체적 수치 활용
- 친한 선배가 알려주듯 직접적이고 솔직한 톤
- 읽는 순간 "이거 나 얘기네" 싶은 공감
- 짧고 강렬. 불필요한 형용사 제거.
"""

SECTION_PROMPTS = {
    "hero": (
        "메인페이지 히어로 롤링 배너 5개 슬라이드를 작성하세요.\n"
        "각 슬라이드는 타겟이 다릅니다:\n"
        "1. 중소기업 대표 (법령 위반 불안, 중대재해처벌법 걱정)\n"
        "2. 안전관리자 겸직자 (혼자 다 하기 버거움, 뭘 해야 할지 모름)\n"
        "3. 법령진단 원하는 기업 (우리 회사 위반사항 빨리 알고 싶음)\n"
        "4. 전문가/선임 필요한 기업 (선임 의무는 있는데 방법을 모름)\n"
        "5. TAI 비전 공감자 (안전한 산업현장을 원하는 사람)\n\n"
        "각 슬라이드 작성 방법:\n"
        "- headline: 타겟의 고통이나 상황을 직접 언급하는 문장 (20자 이내)\n"
        "  예시: '중대재해법, 나만 몰라서 걸리는 건 아닐까?'\n"
        "- sub: 그 고통을 해결해준다는 구체적 메시지 (40자 이내)\n"
        "  예시: '법령 위반 리스크를 3분 만에 진단합니다. 무료입니다.'\n"
        "- cta: 행동 유도 버튼 (8자 이내, 구체적 행동)\n"
        "  예시: '지금 진단하기', '무료로 확인'\n\n"
        "JSON: {\"slides\":[{\"target\":\"\",\"headline\":\"\",\"sub\":\"\",\"cta\":\"\"}]}\n"
        "JSON만 반환."
    ),
    "diagnosis": (
        "법령진단 소개 섹션 카피를 작성하세요.\n"
        "이 섹션의 목적: 방문자가 '우리 회사도 혹시 위반하고 있나?' 불안해서 클릭하게 만들기.\n\n"
        "작성 방법:\n"
        "- headline: 불안감을 건드리는 질문형 또는 경고형. 구체적 법령/수치 포함.\n"
        "  예시: '우리 회사에 적용되는 법령, 몇 개인지 아세요?'\n"
        "- sub: 모르면 생기는 구체적 결과 언급 (벌금, 처벌, 적발)\n"
        "- stat1/2/3: 실제 수치로 위기감 조성\n"
        "  예시: '중대재해처벌법 시행 후 적발 347% 증가',\n"
        "         '위반 시 최대 10억 벌금 + 경영책임자 징역 1년',\n"
        "         '산업재해 은폐 적발 시 최대 5,000만원 과태료'\n"
        "- cta_building/industry/construction: 버튼 (6자, 구체적)\n"
        "  예시: '건물 진단', '공장 진단', '현장 진단'\n"
        "- free_guide: 무료 진단 유도 (부담 없이 시작할 수 있다는 뉘앙스)\n\n"
        "JSON: {\"headline\":\"\",\"sub\":\"\",\"stat1\":\"\",\"stat2\":\"\",\"stat3\":\"\","
        "\"cta_building\":\"\",\"cta_industry\":\"\",\"cta_construction\":\"\",\"free_guide\":\"\"}\n"
        "JSON만 반환."
    ),
    "saas": (
        "SaaS 서비스 소개 섹션 카피를 작성하세요.\n"
        "이 섹션의 목적: '법령진단 결과, 이걸 자동으로 관리해줘' 느낌 주기.\n"
        "타겟: 법령진단 결과를 봐서 이미 불안한 상태인 방문자.\n\n"
        "작성 방법:\n"
        "- headline: 법령진단 이후 자동화되는 흐름을 한 줄로\n"
        "  예시: '진단 끝나면 점검일정이 자동으로 만들어집니다'\n"
        "- sub: 안전관리자가 혼자 하던 걸 시스템이 대신해준다는 메시지\n"
        "- flow 3단계: 실제 작동 방식 (짧고 구체적)\n"
        "  예시: ['법령 자동 분석', '작업자에게 배정+알림', '완료 확인+기록']\n"
        "- 각 섹터 카드 (건물/산업/건설):\n"
        "  title: 해당 섹터 대표 업무 (15자)\n"
        "  desc: 그 업무의 핵심 고통 해결 (30자)\n"
        "  예시: {\"industry_title\":\"설비점검 자동 관리\", \"industry_desc\":\"지게차부터 프레스까지, 누락 없이 기록됩니다\"}\n\n"
        "JSON: {\"headline\":\"\",\"sub\":\"\",\"flow\":[\"\",\"\",\"\"],"
        "\"building_title\":\"\",\"building_desc\":\"\","
        "\"industry_title\":\"\",\"industry_desc\":\"\","
        "\"construction_title\":\"\",\"construction_desc\":\"\"}\n"
        "JSON만 반환."
    ),
    "expert_safety": (
        "안전관리자 선임 지원 섹션 카피를 작성하세요.\n"
        "주의: 인력소개업/알선/소개 표현 절대 금지. '플랫폼 이용', '연결 신청' 표현만 사용.\n"
        "이 섹션의 목적: 선임 의무가 있는 기업이 플랫폼을 통해 전문가를 만나도록 유도.\n\n"
        "작성 방법:\n"
        "- headline: 선임 의무를 모르거나 막막한 기업 대표 심정에서 출발\n"
        "  예시: '안전관리자 선임, 어디서 어떻게 해야 하는지 모르겠죠?'\n"
        "- demand_points: 기업 입장에서 이 서비스로 해결되는 것 3가지 (구체적)\n"
        "  예시: '선임 요건이 되는지 3분 안에 확인', '조건 맞는 전문가 직접 확인', '법정 서류도 플랫폼에서 처리'\n"
        "- supply_points: 전문가 입장에서 이 플랫폼을 써야 하는 이유 3가지\n"
        "  예시: '활동 지역 수요를 먼저 받아볼 수 있음', '계약/정산 플랫폼 내에서 처리', '포트폴리오 관리 가능'\n"
        "- cta_demand: 기업 CTA (8자, 구체적)\n"
        "- cta_supply: 전문가 CTA (8자, 구체적)\n\n"
        "JSON: {\"headline\":\"\",\"demand_points\":[\"\",\"\",\"\"],\"supply_points\":[\"\",\"\",\"\"],"
        "\"cta_demand\":\"\",\"cta_supply\":\"\"}\n"
        "JSON만 반환."
    ),
    "vision": (
        "컨설팅/교육 비전 소개 섹션 카피를 작성하세요.\n"
        "이 섹션의 목적: TAI Safe가 단순 SaaS가 아니라 산업안전 생태계를 만들어간다는 비전 전달.\n"
        "현재 준비 중인 서비스이므로 기대감을 높이는 톤.\n\n"
        "작성 방법:\n"
        "- headline: 큰 그림. TAI가 만들어갈 세상.\n"
        "  예시: '안전관리를 팔지 않겠습니다. 안전한 문화를 만듭니다.'\n"
        "- consulting_title/desc: 컨설팅 서비스 (준비 중)\n"
        "- education_title/desc: 교육 서비스 (준비 중)\n"
        "- badge: 준비 중 배지 문구 (10자 이내, 기대감 유발)\n"
        "  예시: '2026 하반기 오픈'\n\n"
        "JSON: {\"headline\":\"\",\"consulting_title\":\"\",\"consulting_desc\":\"\","
        "\"education_title\":\"\",\"education_desc\":\"\",\"badge\":\"\"}\n"
        "JSON만 반환."
    ),
    "slogan": (
        "TAI Safe 대표 슬로건 {count}개를 작성하세요.\n"
        "좋은 슬로건 조건:\n"
        "- 안전관리자나 기업대표가 '이거 내 얘기네' 싶은 것\n"
        "- 20자 이내, 외우기 쉬운 리듬감\n"
        "- 교과서식 표현 금지. 직접적이고 현실적.\n"
        "- 참고: 토스 '돈 관리의 모든 것', 당근마켓 '우리 동네 당근마켓'\n"
        "- TAI Safe만의 키워드: 법령, 자동, 분산, 현장, 배정\n\n"
        "JSON: {\"slogans\":[\"\",\"\"...]}\n"
        "JSON만 반환."
    ),
}


class CopywriteRequest(BaseModel):
    section: str
    context: Optional[str] = None
    tone: Optional[str] = "real_talk"
    language: Optional[str] = "ko"
    variants: Optional[int] = 1

class BatchCopywriteRequest(BaseModel):
    sections: List[str]
    context: Optional[str] = None
    language: Optional[str] = "ko"

class SloganRequest(BaseModel):
    count: Optional[int] = 5
    focus: Optional[str] = None


def _tone_desc(tone: str) -> str:
    return {
        "real_talk": (
            "친한 선배가 직접 알려주듯 솔직하고 직접적인 톤. "
            "교과서식 표현 금지. 타겟의 실제 고통과 상황에서 출발. "
            "짧고 강렬하게. 불필요한 형용사 제거."
        ),
        "urgent": (
            "지금 당장 행동하지 않으면 손해라는 긴박감. "
            "법령 위반/벌금/처벌 구체적 수치 강조. "
            "단, 과장 없이 실제 법령 기반 수치만 사용."
        ),
        "professional": (
            "전문적이고 신뢰감 있는 톤. "
            "법령 기반 서비스임을 강조. "
            "특허/수치/근거로 신뢰 구축."
        ),
    }.get(tone, "친한 선배가 직접 알려주듯 솔직하고 직접적인 톤.")


async def _call_gpt(system_msg: str, user_msg: str, temperature: float = 0.8) -> str:
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


@router.post("/copywrite")
async def generate_copy(body: CopywriteRequest):
    prompt = SECTION_PROMPTS.get(body.section)
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 섹션. 가능: {list(SECTION_PROMPTS.keys())}"
        )

    system_msg = (
        "당신은 한국 중소기업 산업안전 시장 전문 카피라이터입니다.\n\n"
        f"{BRAND_CONTEXT}\n\n"
        f"톤 가이드: {_tone_desc(body.tone)}\n\n"
        "중요: 교과서식 표현, 두루뭉술한 형용사, 범용 SaaS 카피는 즉시 탈락.\n"
        "타겟이 읽는 순간 '이거 내 얘기네' 싶어야 합격.\n"
        "반드시 JSON만 반환."
    )
    extra = f"\n\n추가 지침: {body.context}" if body.context else ""
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
            "당신은 한국 중소기업 산업안전 시장 전문 카피라이터입니다.\n"
            f"{BRAND_CONTEXT}\n"
            "교과서식/범용 표현 금지. 타겟 고통에서 출발. JSON만 반환."
        )
        user_msg = prompt + (f"\n\n추가 지침: {body.context}" if body.context else "")
        try:
            raw = await _call_gpt(system_msg, user_msg)
            results[section] = json.loads(raw)
        except Exception as e:
            results[section] = {"error": str(e)}

    return {"status": "success", "data": results}


@router.post("/slogan")
async def generate_slogan(body: SloganRequest):
    focus_map = {
        "safety": "산업안전, 법령 준수, 사고 예방",
        "tech": "자동화, 법령진단, 시스템",
        "trust": "신뢰, 공신력, 특허, 검증",
        "platform": "플랫폼, 분산관리, 연결",
    }
    focus_desc = focus_map.get(body.focus, "TAI Safe 전체") if body.focus else "TAI Safe 전체"

    system_msg = (
        "당신은 한국 스타트업 브랜드 슬로건 전문가입니다.\n"
        f"{BRAND_CONTEXT}\n"
        "참고 레퍼런스: 토스 '돈 관리의 모든 것', 당근 '우리 동네 당근마켓'\n"
        "교과서식 표현 절대 금지. 현장감 있고 기억에 남는 슬로건만."
    )
    user_msg = (
        f"강조 포인트: {focus_desc}\n"
        f"한국어 슬로건 {body.count}개 (각 20자 이내).\n"
        "안전관리자나 중소기업 대표가 읽고 '이거다' 싶을 것.\n"
        "JSON: {\"slogans\":[...]} 형식만 반환."
    )

    raw = await _call_gpt(system_msg, user_msg, temperature=0.9)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {"slogans": [raw]}

    return {"status": "success", "data": parsed}
