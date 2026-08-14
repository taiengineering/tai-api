# -*- coding: utf-8 -*-
"""member_support._handle_ask 결선 테스트 — route/explain/save 를 fake 로 주입(외부비용 0).

실제 라우터 함수(routers.member_support._handle_ask)를 import 해 검증한다.
DB/Slack/LLM 은 호출하지 않는다(전부 주입 대체). FAQ 케이스만 실제 support_answer_svc.explain 을
counting LLM 과 함께 써서 "FAQ 는 LLM 미호출"을 직접 검증한다.

케이스:
  1. FAQ → ANSWER, LLM 미호출 경로 유지
  2. Knowledge → ANSWER
  3. diagnosis → CONTEXT ANSWER
  4. Routing ASK → 저장 안 함
  5. Routing HANDOFF → inquiry 1건 저장
  6. Answer INSUFFICIENT → inquiry 1건 저장
  7. HANDOFF 시 context 보존
  8. HANDOFF 저장 실패 → ERROR
  9. Routing ERROR → ERROR
 10. Answer ERROR → ERROR
"""
import json

from routers.member_support import _handle_ask
from services import support_answer_svc

results = []


def check(name, cond):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


IDENT = {"user_id": "U-1", "company_id": "C-1", "name": "홍길동", "page_url": "https://safe/x"}


def route_ret(**kw):
    return lambda q, ctx, aa: dict(kw)


def save_recorder(no="TAI-INQ-20260814-0001", boom=False):
    rec = {"calls": 0, "kwargs": None}

    def _f(supabase, **kwargs):
        rec["calls"] += 1
        rec["kwargs"] = kwargs
        if boom:
            raise RuntimeError("db down")
        return {"no": no}
    _f.rec = rec
    return _f


def explain_real_counting(refs=None, answer="설명", insufficient=False):
    """실제 support_answer_svc.explain 을 counting LLM 과 함께 사용."""
    calls = {"n": 0}

    def llm(system, user):
        calls["n"] += 1
        payload = {"insufficient": insufficient, "answer": answer}
        if refs is not None:
            payload["evidence_refs"] = refs
        return json.dumps(payload)

    def _explain(r, q):
        return support_answer_svc.explain(r, q, llm_call=llm)
    _explain.calls = calls
    return _explain


# 1. FAQ → ANSWER + LLM 미호출
faq_explain = explain_real_counting()
save1 = save_recorder()
r = _handle_ask("무료인가요?", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="FAQ",
                                   evidence={"doc_id": "FAQ-1", "title": "안내",
                                             "answer_short": "네, 무료입니다."}),
                explain_fn=faq_explain, save_fn=save1)
check("1 FAQ->ANSWER", r["status"] == "ANSWER" and r["source"] == "FAQ" and r["answer"] == "네, 무료입니다.")
check("1b FAQ->LLM 미호출", faq_explain.calls["n"] == 0)
check("1c FAQ->저장 안 함", save1.rec["calls"] == 0)

# 2. Knowledge → ANSWER
r = _handle_ask("어떻게?", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="KNOWLEDGE",
                                   evidence=[{"doc_id": "KB-1", "title": "가이드", "slug": "g"}]),
                explain_fn=explain_real_counting(refs=[0], answer="가이드 설명"), save_fn=save_recorder())
check("2 Knowledge->ANSWER", r["status"] == "ANSWER" and r["source"] == "KNOWLEDGE"
      and r["citations"][0]["id"] == "KB-1")

# 3. diagnosis → CONTEXT ANSWER
r = _handle_ask("왜?", {"factory_id": "F-1", "object_type": "diagnosis", "object_id": "D-1"}, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="CONTEXT",
                                   evidence={"id": "D-1", "result_data": {"risk_level": "HIGH"}}),
                explain_fn=explain_real_counting(refs=[0], answer="위험도 HIGH"), save_fn=save_recorder())
check("3 diagnosis->CONTEXT ANSWER", r["status"] == "ANSWER" and r["source"] == "CONTEXT")

# 4. Routing ASK → 저장 안 함
save4 = save_recorder()
r = _handle_ask("내 진단?", {"object_type": "diagnosis"}, False, IDENT,
                route_fn=route_ret(status="ASK", missing_field="factory_id"),
                explain_fn=lambda r, q: {"status": "ERROR"}, save_fn=save4)
check("4 ASK->상태 반환", r["status"] == "ASK" and r["missing_field"] == "factory_id" and r["already_asked"] is True)
check("4b ASK->저장 안 함", save4.rec["calls"] == 0)

# 5. Routing HANDOFF → inquiry 1건 저장
save5 = save_recorder(no="TAI-INQ-20260814-0009")
r = _handle_ask("환불", None, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="no evidence found"),
                explain_fn=lambda r, q: {"status": "ERROR"}, save_fn=save5)
check("5 HANDOFF->저장1건+inquiry_no",
      r["status"] == "HANDOFF" and r["inquiry_no"] == "TAI-INQ-20260814-0009" and save5.rec["calls"] == 1)

# 6. Answer INSUFFICIENT → inquiry 1건 저장
save6 = save_recorder()
r = _handle_ask("근거밖 질문", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="KNOWLEDGE",
                                   evidence=[{"doc_id": "KB-1", "title": "g"}]),
                explain_fn=explain_real_counting(insufficient=True), save_fn=save6)
check("6 Answer INSUFFICIENT->HANDOFF 저장", r["status"] == "HANDOFF" and save6.rec["calls"] == 1)

# 7. HANDOFF 시 context 보존
save7 = save_recorder()
stored = {"factory_id": "F-9", "object_type": "diagnosis", "object_id": "D-9"}
r = _handle_ask("이관질문", stored, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="x"),
                explain_fn=lambda r, q: {"status": "ERROR"}, save_fn=save7)
kw = save7.rec["kwargs"]
check("7 HANDOFF context 보존",
      kw["context"] == stored and kw["user_id"] == "U-1" and kw["company_id"] == "C-1"
      and kw["page_url"] == "https://safe/x" and kw["question"] == "이관질문")

# 8. HANDOFF 저장 실패 → ERROR
r = _handle_ask("환불", None, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="x"),
                explain_fn=lambda r, q: {"status": "ERROR"}, save_fn=save_recorder(boom=True))
check("8 저장 실패->ERROR", r["status"] == "ERROR" and "save failed" in r["detail"])

# 9. Routing ERROR → ERROR
r = _handle_ask("x", None, False, IDENT,
                route_fn=route_ret(status="ERROR", detail="faq_search failed"),
                explain_fn=lambda r, q: {"status": "ANSWER"}, save_fn=save_recorder())
check("9 Routing ERROR->ERROR", r["status"] == "ERROR" and "faq_search" in r["detail"])

# 10. Answer ERROR → ERROR
r = _handle_ask("x", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="KNOWLEDGE", evidence=[{"doc_id": "KB-1"}]),
                explain_fn=lambda r, q: {"status": "ERROR", "detail": "llm_call failed"},
                save_fn=save_recorder())
check("10 Answer ERROR->ERROR", r["status"] == "ERROR" and "llm_call" in r["detail"])

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
print("ALL PASS")
