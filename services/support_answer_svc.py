# -*- coding: utf-8 -*-
"""TAI 고객응대 — Evidence → User Answer 설명 계층.

책임(단일): Routing 이 반환한 ANSWER + evidence 를 사용자에게 읽기 좋은 답변으로 변환한다.
Routing(근거 탐색/경로 결정)은 이 서비스가 하지 않는다. 이미 찾은 evidence 만 설명한다.

핵심 원칙(고정):
- LLM 은 evidence 밖의 사실을 추가하지 않는다. 근거를 찾지 않는다.
- evidence 가 부족하면 임의 보완하지 않고 INSUFFICIENT 를 반환한다(호출측이 Human handoff 로 연결).
- 법률 적용 여부/법적 의무를 AI 가 새로 판단하지 않는다.
- 근거 출처 식별정보(citations)를 반드시 보존한다.
- RESOLVED 를 만들지 않는다. 문의 종료 판단을 하지 않는다.

source 별 동작:
- FAQ      : LLM 미호출. 기존 FAQ 의 answer_short(없으면 body)를 그대로 사용.
- KNOWLEDGE: LLM 으로 evidence 기반 짧은 한국어 설명. evidence 밖 생성 금지.
- CONTEXT  : (현재 diagnosis) 실제 evidence 에 존재하는 정보만 설명. 새 법적 판단 금지.

LLM 재사용: 기존 자산(routers/ai_copywrite.py)이 쓰는 것과 동일한 provider·설정을 재사용한다
  — OpenAI SDK, env OPENAI_API_KEY, model gpt-4o, chat.completions(JSON). 신규 provider/abstraction 없음.
LLM 호출은 주입 가능(llm_call)하며, 미주입 시 위 기본 구현을 지연 import 로 사용한다.

출력 계약(고정):
  { "status": "ANSWER"|"INSUFFICIENT"|"ERROR",
    "answer": "...",
    "source": "FAQ"|"KNOWLEDGE"|"CONTEXT",
    "citations": [ {"type": "...", "id": "...", "title": "..."} ] }
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

# LLM 프롬프트 불변 제약(요구사항). evidence only / no inference / no legal decision / insufficient / concise KO.
_LLM_SYSTEM = (
    "You explain TAI Safe support answers to a Korean user.\n"
    "STRICT RULES:\n"
    "- Use the supplied evidence only.\n"
    "- Do not infer or add facts that are not in the evidence.\n"
    "- Do not make legal decisions or new legal judgments.\n"
    "- If the evidence is insufficient to answer, return insufficient.\n"
    "- Answer concisely in Korean.\n"
    'Return JSON only: {"answer": "<concise Korean answer>", "insufficient": <true|false>}'
)


def _default_llm_call(system_msg: str, user_msg: str) -> str:
    """기존 ai_copywrite 와 동일 provider·설정 재사용(OpenAI gpt-4o, JSON). raw 문자열 반환."""
    import os
    from openai import OpenAI  # 지연 import
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _err(detail: str) -> Dict[str, Any]:
    return {"status": "ERROR", "answer": "", "source": None, "citations": [], "detail": detail}


def _faq_answer(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """FAQ: LLM 미호출. 기존 답변 그대로."""
    ans = (evidence.get("answer_short") or "").strip() or (evidence.get("body") or "").strip()
    citation = {
        "type": "FAQ",
        "id": evidence.get("doc_id"),
        "title": evidence.get("title") or evidence.get("question"),
    }
    if not ans:
        return {"status": "INSUFFICIENT", "answer": "", "source": "FAQ", "citations": [citation]}
    return {"status": "ANSWER", "answer": ans, "source": "FAQ", "citations": [citation]}


def _run_llm(source: str, question: str, evidence_text: str,
             citations: List[Dict[str, Any]], llm_call: Callable[[str, str], str]) -> Dict[str, Any]:
    user_msg = (
        f"[사용자 질문]\n{question}\n\n"
        f"[evidence]\n{evidence_text}\n\n"
        "위 evidence 만 근거로 답하세요. evidence 에 없으면 insufficient=true."
    )
    try:
        raw = llm_call(_LLM_SYSTEM, user_msg)
    except Exception as e:  # noqa: BLE001
        return _err(f"llm_call failed: {e}")
    try:
        parsed = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        return _err(f"llm output not json: {e}")
    if parsed.get("insufficient") is True:
        return {"status": "INSUFFICIENT", "answer": "", "source": source, "citations": citations}
    answer = (parsed.get("answer") or "").strip()
    if not answer:
        return {"status": "INSUFFICIENT", "answer": "", "source": source, "citations": citations}
    return {"status": "ANSWER", "answer": answer, "source": source, "citations": citations}


def _knowledge_citations(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for doc in evidence or []:
        c = {"type": "KNOWLEDGE", "id": doc.get("doc_id"), "title": doc.get("title")}
        slug = doc.get("slug") or doc.get("page_slug")
        if slug:
            c["slug"] = slug
        out.append(c)
    return out


def _compact_evidence(evidence: Any, cap: int = 4000) -> str:
    try:
        text = json.dumps(evidence, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        text = str(evidence)
    return text[:cap]


def explain(
    routing_result: Dict[str, Any],
    question: str,
    *,
    llm_call: Optional[Callable[[str, str], str]] = None,
) -> Dict[str, Any]:
    """Routing ANSWER + evidence → 사용자 설명. 입력은 status=='ANSWER' 여야 한다."""
    if not isinstance(routing_result, dict):
        return _err("routing_result must be dict")
    if routing_result.get("status") != "ANSWER":
        return _err(f"not an ANSWER routing result: {routing_result.get('status')}")

    source = routing_result.get("source")
    evidence = routing_result.get("evidence")
    q = (question or "").strip()
    llm_call = llm_call or _default_llm_call

    if source == "FAQ":
        if not isinstance(evidence, dict):
            return _err("FAQ evidence must be a dict")
        return _faq_answer(evidence)

    if source == "KNOWLEDGE":
        if not isinstance(evidence, list) or not evidence:
            return {"status": "INSUFFICIENT", "answer": "", "source": "KNOWLEDGE", "citations": []}
        citations = _knowledge_citations(evidence)
        return _run_llm("KNOWLEDGE", q, _compact_evidence(evidence), citations, llm_call)

    if source == "CONTEXT":
        if not evidence:
            return {"status": "INSUFFICIENT", "answer": "", "source": "CONTEXT", "citations": []}
        cid = None
        title = "최신 진단 결과"
        if isinstance(evidence, dict):
            cid = evidence.get("id") or evidence.get("factory_id")
        citations = [{"type": "CONTEXT", "id": cid, "title": title}]
        return _run_llm("CONTEXT", q, _compact_evidence(evidence), citations, llm_call)

    return _err(f"unsupported source: {source}")
