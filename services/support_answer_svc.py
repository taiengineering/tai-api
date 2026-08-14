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

Evidence 경계 강제(MVP):
- KNOWLEDGE/CONTEXT 의 LLM 은 answer 뿐 아니라 사용한 evidence 의 index 목록(evidence_refs)을 함께 반환한다.
- 서버는 evidence_refs 를 검증한다: 정수 index, 입력 evidence 범위 내, 최소 1개.
  범위 밖 index / 빈 refs / 형식 오류 → fail closed(INSUFFICIENT 또는 ERROR).
- citations 는 LLM 이 만들지 않는다. 서버가 선택된 evidence_refs 에 해당하는 원본 evidence 에서만 구성한다.
- 즉 "어떤 근거를 썼는지 제시하지 않은 자유생성 답변"은 통과하지 못한다.

source 별 동작:
- FAQ      : LLM 미호출. 기존 FAQ 의 answer_short(없으면 body)를 그대로 사용.
- KNOWLEDGE: LLM 으로 evidence 기반 짧은 한국어 설명 + evidence_refs. 서버가 refs 검증·citation 구성.
- CONTEXT  : (현재 diagnosis) 단일 객체를 evidence item 0 으로 취급. evidence_refs=[0] 일 때만 ANSWER.

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
# 추가: 사용한 evidence 의 index 를 evidence_refs 로 반드시 제시(근거 없는 자유생성 차단).
_LLM_SYSTEM = (
    "You explain TAI Safe support answers to a Korean user.\n"
    "The user message contains a numbered list of evidence items (index starts at 0).\n"
    "STRICT RULES:\n"
    "- Use the supplied evidence only.\n"
    "- Do not infer or add facts that are not in the evidence.\n"
    "- Do not make legal decisions or new legal judgments.\n"
    "- If the evidence is insufficient to answer, return insufficient.\n"
    "- Answer concisely in Korean.\n"
    "- evidence_refs MUST list the indices of the evidence items you actually used.\n"
    "- Do NOT invent citation ids; only return evidence_refs indices.\n"
    'Return JSON only: '
    '{"insufficient": <true|false>, "evidence_refs": [<int index>, ...], "answer": "<concise Korean answer>"}'
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


def _insufficient(source: str, citations: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {"status": "INSUFFICIENT", "answer": "", "source": source, "citations": citations or []}


def _faq_answer(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """FAQ: LLM 미호출. 기존 답변 그대로."""
    ans = (evidence.get("answer_short") or "").strip() or (evidence.get("body") or "").strip()
    citation = {
        "type": "FAQ",
        "id": evidence.get("doc_id"),
        "title": evidence.get("title") or evidence.get("question"),
    }
    if not ans:
        return _insufficient("FAQ", [citation])
    return {"status": "ANSWER", "answer": ans, "source": "FAQ", "citations": [citation]}


def _citation_for(source: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """원본 evidence item 하나에서 서버가 citation 을 구성(LLM 이 만들지 않음)."""
    if source == "KNOWLEDGE":
        c = {"type": "KNOWLEDGE", "id": item.get("doc_id"), "title": item.get("title")}
        slug = item.get("slug") or item.get("page_slug")
        if slug:
            c["slug"] = slug
        return c
    # CONTEXT
    return {
        "type": "CONTEXT",
        "id": (item.get("id") or item.get("factory_id")) if isinstance(item, dict) else None,
        "title": "최신 진단 결과",
    }


def _validate_refs(raw_refs: Any, n_items: int) -> Optional[List[int]]:
    """evidence_refs 검증: 정수 index, 0..n_items-1, 최소 1개, 중복 제거. 실패 시 None."""
    if not isinstance(raw_refs, list) or not raw_refs:
        return None
    seen: List[int] = []
    for x in raw_refs:
        if isinstance(x, bool) or not isinstance(x, int):
            return None
        if x < 0 or x >= n_items:
            return None
        if x not in seen:
            seen.append(x)
    return seen or None


def _run_llm_grounded(
    source: str,
    question: str,
    items: List[Dict[str, Any]],
    llm_call: Callable[[str, str], str],
) -> Dict[str, Any]:
    """LLM 설명 + evidence_refs 강제. citations 는 서버가 refs 로만 구성. fail closed."""
    # 번호가 매겨진 evidence 를 사용자 메시지에 넣는다(index 0 부터).
    numbered = []
    for i, it in enumerate(items):
        try:
            body = json.dumps(it, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            body = str(it)
        numbered.append(f"[{i}] {body[:2000]}")
    user_msg = (
        f"[사용자 질문]\n{question}\n\n"
        f"[evidence items] (index 0..{len(items) - 1})\n" + "\n".join(numbered) + "\n\n"
        "위 evidence 만 근거로 답하세요. 사용한 항목의 index 를 evidence_refs 에 넣으세요. "
        "근거가 없으면 insufficient=true 로 반환하세요."
    )
    try:
        raw = llm_call(_LLM_SYSTEM, user_msg)
    except Exception as e:  # noqa: BLE001
        return _err(f"llm_call failed: {e}")
    try:
        parsed = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        return _err(f"llm output not json: {e}")
    if not isinstance(parsed, dict):
        return _err("llm output not an object")

    # LLM 이 insufficient 를 명시하면 그대로 INSUFFICIENT
    if parsed.get("insufficient") is True:
        return _insufficient(source)

    # evidence_refs 검증(fail closed): 없거나 범위 밖/형식 오류면 INSUFFICIENT
    refs = _validate_refs(parsed.get("evidence_refs"), len(items))
    if refs is None:
        return _insufficient(source)

    answer = (parsed.get("answer") or "").strip()
    if not answer:
        return _insufficient(source)

    # citations 는 서버가 선택된 refs 의 원본 evidence 에서만 구성
    citations = [_citation_for(source, items[i]) for i in refs]
    return {"status": "ANSWER", "answer": answer, "source": source, "citations": citations}


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
            return _insufficient("KNOWLEDGE")
        return _run_llm_grounded("KNOWLEDGE", q, evidence, llm_call)

    if source == "CONTEXT":
        if not evidence:
            return _insufficient("CONTEXT")
        # diagnosis 단일 객체 → evidence item 0 으로 취급
        items = evidence if isinstance(evidence, list) else [evidence]
        return _run_llm_grounded("CONTEXT", q, items, llm_call)

    return _err(f"unsupported source: {source}")
