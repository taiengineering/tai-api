import json
import logging
import os
import re

import httpx

from services.contract_helpers import _default_sections, _expert_type_label

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"


async def generate_contract_sections(
    expert_type: str,
    contract_amount: int,
    duration_months: int,
    client_name: str,
    expert_name: str,
    description: str,
    proposal_note: str,
) -> dict:
    if not ANTHROPIC_API_KEY:
        return _default_sections(expert_type)

    prompt = f"""다음 정보를 바탕으로 안전관리 서비스 계약서의 조항을 한국어로 작성해 주세요.

서비스 유형: {expert_type} ({_expert_type_label(expert_type)})
계약 금액: {contract_amount:,}원
계약 기간: {duration_months}개월
위탁자: {client_name}
수탁자: {expert_name}
요구사항: {description}
특이사항: {proposal_note}

아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만:
{{
  "article3": "<p>서비스 범위 및 의무 내용...</p>",
  "article5": "<p>지급 조건 내용...</p>",
  "article6": "<p>이행 조건 및 특이사항 내용...</p>",
  "article7": "<p>해지 및 면책 조건 내용...</p>"
}}

작성 기준:
- 산업안전보건법 관련 법령 준수
- 명확하고 법적으로 유효한 문구
- HTML 태그(<p>, <ul>, <li>) 사용
- 각 조항 200자 이상"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            log.error("[CONTRACT GEN] Claude API %s: %s", resp.status_code, resp.text[:200])
            return _default_sections(expert_type)

        raw = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                raw += block["text"]

        raw = re.sub(r"```json\s*", "", raw.strip())
        raw = re.sub(r"```\s*", "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        log.error("[CONTRACT GEN] Claude 오류: %s", e)
        return _default_sections(expert_type)


async def revise_with_claude(original_html: str, revision_note: str) -> str:
    if not ANTHROPIC_API_KEY:
        return original_html

    prompt = f"""아래는 기존 계약서 HTML입니다.
수정 요청 내용을 반영하여 계약서를 수정해 주세요.
HTML 전체를 반환하되, 수정 요청에 해당하는 부분만 변경하세요.

수정 요청: {revision_note}

기존 계약서:
{original_html[:6000]}"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code != 200:
            log.error("[CONTRACT REVISE] Claude API %s", resp.status_code)
            return original_html

        raw = ""
        for block in resp.json().get("content", []):
            if block.get("type") == "text":
                raw += block["text"]
        return raw.strip() or original_html
    except Exception as e:
        log.error("[CONTRACT REVISE] Claude 오류: %s", e)
        return original_html
