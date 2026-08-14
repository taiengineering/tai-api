# -*- coding: utf-8 -*-
"""support_answer_svc.explain 테스트 — LLM 을 fake 로 주입(외부비용 0).

케이스:
  1. FAQ → LLM 미호출 + 기존 답변 그대로
  2. KNOWLEDGE → evidence 기반 설명
  3. KNOWLEDGE evidence 밖 정보 요구 → INSUFFICIENT
  4. diagnosis(CONTEXT) → 실제 evidence 기반 설명
  5. diagnosis evidence 에 없는 사유 질문 → INSUFFICIENT
  6. citation/source trace 유지
  7. LLM 오류 → ERROR
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


def llm_ok(answer_text):
    calls = {"n": 0}

    def _f(system, user):
        calls["n"] += 1
        return json.dumps({"answer": answer_text, "insufficient": False})
    _f.calls = calls
    return _f


def llm_insufficient():
    def _f(system, user):
        return json.dumps({"answer": "", "insufficient": True})
    return _f


def llm_boom():
    def _f(system, user):
        raise RuntimeError("openai down")
    return _f


# 1. FAQ → LLM 미호출 + 기존 답변 그대로
faq_llm = llm_ok("AI가 만든 답(쓰이면 안됨)")
faq_ev = {"status": "ANSWER", "source": "FAQ",
          "evidence": {"doc_id": "FAQ-1", "title": "무료진단 안내",
                       "question": "무료 진단은 무료인가요", "answer_short": "네, 무료입니다."}}
r = svc.explain(faq_ev, "무료 진단은 무료인가요?", llm_call=faq_llm)
check("1 FAQ->ANSWER 기존답변 그대로", r["status"] == "ANSWER" and r["answer"] == "네, 무료입니다.")
check("1b FAQ->LLM 미호출", faq_llm.calls["n"] == 0)

# 2. KNOWLEDGE → evidence 기반 설명
kn_ev = {"status": "ANSWER", "source": "KNOWLEDGE",
         "evidence": [{"doc_id": "KB-1", "title": "진단 결과 보는 법", "slug": "diagnosis-guide",
                       "body": "결과 화면 상단에서 위험도를 확인합니다."}]}
r = svc.explain(kn_ev, "진단 결과 어디서 보나요?", llm_call=llm_ok("결과 화면 상단에서 위험도를 볼 수 있습니다."))
check("2 KNOWLEDGE->ANSWER 설명", r["status"] == "ANSWER" and "위험도" in r["answer"])

# 3. KNOWLEDGE evidence 밖 정보 요구 → INSUFFICIENT
r = svc.explain(kn_ev, "환불 계좌는 어디에 등록하나요?", llm_call=llm_insufficient())
check("3 KNOWLEDGE evidence 밖->INSUFFICIENT", r["status"] == "INSUFFICIENT")

# 4. diagnosis(CONTEXT) → 실제 evidence 기반 설명
ctx_ev = {"status": "ANSWER", "source": "CONTEXT",
          "evidence": {"id": "D-1", "factory_id": "F-1",
                       "result_data": {"risk_level": "HIGH",
                                       "applicable_law_categories": ["산업안전보건법"]}}}
r = svc.explain(ctx_ev, "왜 위험도가 높나요?",
                llm_call=llm_ok("현재 진단 결과의 위험도가 HIGH 로 나타나 있습니다."))
check("4 CONTEXT->ANSWER 설명", r["status"] == "ANSWER" and "HIGH" in r["answer"])

# 5. diagnosis evidence 에 없는 사유 질문 → INSUFFICIENT
r = svc.explain(ctx_ev, "이 결과로 과태료가 얼마 나오나요?", llm_call=llm_insufficient())
check("5 CONTEXT evidence 밖->INSUFFICIENT", r["status"] == "INSUFFICIENT")

# 6. citation/source trace 유지 (각 source)
check("6a FAQ citation",
      svc.explain(faq_ev, "q", llm_call=faq_llm)["citations"][0]["id"] == "FAQ-1")
r = svc.explain(kn_ev, "q", llm_call=llm_ok("x"))
check("6b KNOWLEDGE citation+slug",
      r["citations"][0]["type"] == "KNOWLEDGE" and r["citations"][0]["id"] == "KB-1"
      and r["citations"][0].get("slug") == "diagnosis-guide")
r = svc.explain(ctx_ev, "q", llm_call=llm_ok("x"))
check("6c CONTEXT citation", r["citations"][0]["type"] == "CONTEXT" and r["citations"][0]["id"] == "D-1")

# 7. LLM 오류 → ERROR
r = svc.explain(kn_ev, "q", llm_call=llm_boom())
check("7 LLM 오류->ERROR", r["status"] == "ERROR")

# 부가: 비-ANSWER 입력 → ERROR (오용 방지)
r = svc.explain({"status": "HANDOFF", "reason": "x"}, "q", llm_call=llm_ok("x"))
check("8 비-ANSWER 입력->ERROR", r["status"] == "ERROR")

# 부가: FAQ answer_short 없고 body 있으면 body 사용
faq_body = {"status": "ANSWER", "source": "FAQ",
            "evidence": {"doc_id": "FAQ-2", "title": "안내", "body": "<p>본문 답변</p>"}}
r = svc.explain(faq_body, "q", llm_call=llm_ok("x"))
check("9 FAQ body fallback", r["status"] == "ANSWER" and "본문 답변" in r["answer"])

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
print("ALL PASS")
