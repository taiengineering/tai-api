# -*- coding: utf-8 -*-
"""support_answer_svc.explain 테스트 — LLM 을 fake 로 주입(외부비용 0).

기본 케이스:
  1. FAQ → LLM 미호출 + 기존 답변 그대로
  2. KNOWLEDGE → evidence 기반 설명
  3. KNOWLEDGE evidence 밖(insufficient) → INSUFFICIENT
  4. diagnosis(CONTEXT) → 실제 evidence 기반 설명
  5. diagnosis evidence 밖(insufficient) → INSUFFICIENT
  6. citation/source trace 유지
  7. LLM 오류 → ERROR
Evidence 경계(evidence_refs) 케이스:
  E1. KNOWLEDGE evidence_refs=[0] → ANSWER + 해당 citation만
  E2. KNOWLEDGE 존재하지 않는 [99] → fail closed
  E3. KNOWLEDGE refs 없음 + insufficient=false → fail closed
  E4. 여러 KB 중 [1]만 선택 → citation 도 1번 문서만
  E5. CONTEXT [0] → ANSWER
  E6. CONTEXT [1] → fail closed
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))
import support_answer_svc as svc  # noqa: E402

results = []


def check(name, cond):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


def llm(answer="", insufficient=False, evidence_refs=None):
    """fake LLM. 새 계약: {insufficient, evidence_refs, answer}."""
    calls = {"n": 0}

    def _f(system, user):
        calls["n"] += 1
        payload = {"insufficient": insufficient, "answer": answer}
        if evidence_refs is not None:
            payload["evidence_refs"] = evidence_refs
        return json.dumps(payload)
    _f.calls = calls
    return _f


def llm_boom():
    def _f(system, user):
        raise RuntimeError("openai down")
    return _f


def llm_bad_json():
    def _f(system, user):
        return "not json"
    return _f


# ── 기본 ──
faq_llm = llm(answer="AI가 만든 답(쓰이면 안됨)", evidence_refs=[0])
faq_ev = {"status": "ANSWER", "source": "FAQ",
          "evidence": {"doc_id": "FAQ-1", "title": "무료진단 안내",
                       "question": "무료 진단은 무료인가요", "answer_short": "네, 무료입니다."}}
r = svc.explain(faq_ev, "무료 진단은 무료인가요?", llm_call=faq_llm)
check("1 FAQ->ANSWER 기존답변 그대로", r["status"] == "ANSWER" and r["answer"] == "네, 무료입니다.")
check("1b FAQ->LLM 미호출", faq_llm.calls["n"] == 0)

kn_ev = {"status": "ANSWER", "source": "KNOWLEDGE",
         "evidence": [{"doc_id": "KB-1", "title": "진단 결과 보는 법", "slug": "diagnosis-guide",
                       "body": "결과 화면 상단에서 위험도를 확인합니다."}]}
r = svc.explain(kn_ev, "진단 결과 어디서 보나요?",
                llm_call=llm(answer="결과 화면 상단에서 위험도를 볼 수 있습니다.", evidence_refs=[0]))
check("2 KNOWLEDGE->ANSWER 설명", r["status"] == "ANSWER" and "위험도" in r["answer"])

r = svc.explain(kn_ev, "환불 계좌는?", llm_call=llm(insufficient=True))
check("3 KNOWLEDGE insufficient->INSUFFICIENT", r["status"] == "INSUFFICIENT")

ctx_ev = {"status": "ANSWER", "source": "CONTEXT",
          "evidence": {"id": "D-1", "factory_id": "F-1",
                       "result_data": {"risk_level": "HIGH",
                                       "applicable_law_categories": ["산업안전보건법"]}}}
r = svc.explain(ctx_ev, "왜 위험도가 높나요?",
                llm_call=llm(answer="현재 진단 결과의 위험도가 HIGH 로 나타나 있습니다.", evidence_refs=[0]))
check("4 CONTEXT->ANSWER 설명", r["status"] == "ANSWER" and "HIGH" in r["answer"])

r = svc.explain(ctx_ev, "과태료 얼마?", llm_call=llm(insufficient=True))
check("5 CONTEXT insufficient->INSUFFICIENT", r["status"] == "INSUFFICIENT")

# citation/source trace
check("6a FAQ citation",
      svc.explain(faq_ev, "q", llm_call=faq_llm)["citations"][0]["id"] == "FAQ-1")
r = svc.explain(kn_ev, "q", llm_call=llm(answer="x", evidence_refs=[0]))
check("6b KNOWLEDGE citation+slug",
      r["citations"][0]["type"] == "KNOWLEDGE" and r["citations"][0]["id"] == "KB-1"
      and r["citations"][0].get("slug") == "diagnosis-guide")
r = svc.explain(ctx_ev, "q", llm_call=llm(answer="x", evidence_refs=[0]))
check("6c CONTEXT citation", r["citations"][0]["type"] == "CONTEXT" and r["citations"][0]["id"] == "D-1")

r = svc.explain(kn_ev, "q", llm_call=llm_boom())
check("7 LLM 오류->ERROR", r["status"] == "ERROR")

# ── Evidence 경계(evidence_refs) ──
# E1. KNOWLEDGE refs=[0] → ANSWER + 해당 citation만
r = svc.explain(kn_ev, "q", llm_call=llm(answer="설명", evidence_refs=[0]))
check("E1 KNOWLEDGE [0]->ANSWER+citation1", r["status"] == "ANSWER" and len(r["citations"]) == 1
      and r["citations"][0]["id"] == "KB-1")

# E2. KNOWLEDGE 존재하지 않는 [99] → fail closed
r = svc.explain(kn_ev, "q", llm_call=llm(answer="설명", evidence_refs=[99]))
check("E2 KNOWLEDGE [99]->fail closed", r["status"] == "INSUFFICIENT")

# E3. refs 없음 + insufficient=false → fail closed
r = svc.explain(kn_ev, "q", llm_call=llm(answer="설명", insufficient=False, evidence_refs=None))
check("E3 refs 없음+insufficient=false->fail closed", r["status"] == "INSUFFICIENT")
# E3b. 빈 refs → fail closed
r = svc.explain(kn_ev, "q", llm_call=llm(answer="설명", evidence_refs=[]))
check("E3b 빈 refs->fail closed", r["status"] == "INSUFFICIENT")

# E4. 여러 KB 중 [1]만 선택 → citation 도 1번 문서만
kn_multi = {"status": "ANSWER", "source": "KNOWLEDGE",
            "evidence": [
                {"doc_id": "KB-A", "title": "문서 A", "slug": "a"},
                {"doc_id": "KB-B", "title": "문서 B", "slug": "b"},
                {"doc_id": "KB-C", "title": "문서 C", "slug": "c"},
            ]}
r = svc.explain(kn_multi, "q", llm_call=llm(answer="B 기반 설명", evidence_refs=[1]))
check("E4 여러 KB 중 [1]만->citation KB-B만",
      r["status"] == "ANSWER" and len(r["citations"]) == 1 and r["citations"][0]["id"] == "KB-B")

# E5. CONTEXT [0] → ANSWER
r = svc.explain(ctx_ev, "q", llm_call=llm(answer="위험도 HIGH 입니다.", evidence_refs=[0]))
check("E5 CONTEXT [0]->ANSWER", r["status"] == "ANSWER" and r["citations"][0]["id"] == "D-1")

# E6. CONTEXT [1] → fail closed (단일 객체는 index 0 뿐)
r = svc.explain(ctx_ev, "q", llm_call=llm(answer="근거밖", evidence_refs=[1]))
check("E6 CONTEXT [1]->fail closed", r["status"] == "INSUFFICIENT")

# ── 부가 ──
r = svc.explain({"status": "HANDOFF", "reason": "x"}, "q", llm_call=llm(answer="x", evidence_refs=[0]))
check("8 비-ANSWER 입력->ERROR", r["status"] == "ERROR")
faq_body = {"status": "ANSWER", "source": "FAQ",
            "evidence": {"doc_id": "FAQ-2", "title": "안내", "body": "<p>본문 답변</p>"}}
r = svc.explain(faq_body, "q", llm_call=faq_llm)
check("9 FAQ body fallback", r["status"] == "ANSWER" and "본문 답변" in r["answer"])
r = svc.explain(kn_ev, "q", llm_call=llm_bad_json())
check("10 LLM 비JSON->ERROR", r["status"] == "ERROR")
# refs 형식 오류(문자열) → fail closed
r = svc.explain(kn_ev, "q", llm_call=llm(answer="x", evidence_refs=["0"]))
check("11 refs 형식오류(str)->fail closed", r["status"] == "INSUFFICIENT")

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
print("ALL PASS")
