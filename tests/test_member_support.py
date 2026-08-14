# -*- coding: utf-8 -*-
"""member_support._handle_ask 결선 테스트 — route/explain/classify/save 를 fake 로 주입(외부비용 0).

실제 라우터 함수(routers.member_support._handle_ask)를 import 해 검증한다.
DB/Slack/LLM/classifier 는 호출하지 않는다(전부 주입 대체). FAQ 케이스만 실제 support_answer_svc.explain 을
counting LLM 과 함께 써서 "FAQ 는 LLM 미호출"을 직접 검증한다.

[트랙 B 주의] _handle_ask 의 기본 classify_fn 은 실제 classifier(OpenAI)다. 따라서 HANDOFF 로 가는
모든 케이스는 반드시 deterministic classify_fn 을 주입한다(외부 호출 0 유지). ANSWER/ASK 케이스는
분류를 호출하지 않지만, 회귀 방지를 위해 카운팅 classify_fn 을 주입해 "0회"를 직접 검증한다.

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
 11. _build_routing_context: diagnosis object_type 단독(object_id 없이) 보존 / object_id 미포함 / 비허용 제거
 12. _handle_ask(routing_ctx=...): route 는 routing_ctx(+company_id) 사용, 저장은 stored_ctx(clean)
 13. 하위호환: routing_ctx 미지정 → stored_ctx 를 routing 근거로 사용

 Enriched HANDOFF(구현 1단계 + 의미 안전성 보정):
 14. diagnosis(CONTEXT) INSUFFICIENT → context.support 에 diagnosis_summary FACT + safe token
 15. KNOWLEDGE INSUFFICIENT → support 미첨부(기존과 동일, context None)
 16. Routing HANDOFF(evidence 없음) → support 미첨부, screen context 보존
 17. raw diagnosis payload/obligations 원문/input_data/rules 가 support 에 저장되지 않음
 18. stored_ctx + diagnosis INSUFFICIENT → screen context + support 공존
 19. _do_handoff(verified_support=None) → 기존과 동일(support 없음)
 20. obligations list → obligation_count=len / rule_count 만 있으면 obligation_count 없음(fallback 제거)
 21. _project_diagnosis_summary 단위: obligations list→count, rule_count→미저장, 대표값 없음→None
 22. _safe_reason_token whitelist: raw 내부 reason 을 token 으로만(needs_review 포함)
 23. _safe_support_projection: raw 내부 reason 이 support JSON 에 그대로 저장되지 않음

 트랙 B(HANDOFF taxonomy 분류):
 24. ANSWER → classifier 0회
 25. ASK → classifier 0회
 26. routing HANDOFF → classifier 1회
 27. INSUFFICIENT → classifier 1회
 28. valid pair → type_code/subtype_code/resolution_axis(HANDOFF) 저장
 29. invalid/mismatch(classifier None) → type_code/subtype_code NULL, axis 는 HANDOFF
 30. classifier exception → HANDOFF 저장 계속(taxonomy NULL)
 31. taxonomy 는 정규 컬럼으로만 — context.support 에 type_code 등을 넣지 않음
"""
import json

from routers.member_support import (
    _build_routing_context,
    _do_handoff,
    _handle_ask,
    _project_diagnosis_summary,
    _safe_reason_token,
    _safe_support_projection,
)
from routers.member_inquiries import InquiryContextBody
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


def classify_recorder(result=None, boom=False):
    """deterministic classify_fn. 호출 횟수/safe_context 기록. result=None → None 반환(무효/실패 모사).

    _handle_ask 의 classify_fn(question, safe_context) 시그니처에 맞춘다.
    """
    rec = {"calls": 0, "ctx": None}

    def _f(question, safe_context):
        rec["calls"] += 1
        rec["ctx"] = safe_context
        if boom:
            raise RuntimeError("classifier down")
        return dict(result) if result else None
    _f.rec = rec
    return _f


# 트랙 B: 기본적으로 모든 케이스에 주입할 valid classifier(호출되면 이 값 저장, 안 되면 0회로 검증)
VALID_TAX = {"type_code": "T7", "subtype_code": "T7_PAYMENT_REFUND"}


# 1. FAQ → ANSWER + LLM 미호출
faq_explain = explain_real_counting()
save1 = save_recorder()
cls1 = classify_recorder(VALID_TAX)
r = _handle_ask("무료인가요?", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="FAQ",
                                   evidence={"doc_id": "FAQ-1", "title": "안내",
                                             "answer_short": "네, 무료입니다."}),
                explain_fn=faq_explain, classify_fn=cls1, save_fn=save1)
check("1 FAQ->ANSWER", r["status"] == "ANSWER" and r["source"] == "FAQ" and r["answer"] == "네, 무료입니다.")
check("1b FAQ->LLM 미호출", faq_explain.calls["n"] == 0)
check("1c FAQ->저장 안 함", save1.rec["calls"] == 0)
check("1d FAQ->classifier 미호출", cls1.rec["calls"] == 0)

# 2. Knowledge → ANSWER
cls2 = classify_recorder(VALID_TAX)
r = _handle_ask("어떻게?", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="KNOWLEDGE",
                                   evidence=[{"doc_id": "KB-1", "title": "가이드", "slug": "g"}]),
                explain_fn=explain_real_counting(refs=[0], answer="가이드 설명"),
                classify_fn=cls2, save_fn=save_recorder())
check("2 Knowledge->ANSWER", r["status"] == "ANSWER" and r["source"] == "KNOWLEDGE"
      and r["citations"][0]["id"] == "KB-1")
check("2b Knowledge ANSWER->classifier 미호출", cls2.rec["calls"] == 0)

# 3. diagnosis → CONTEXT ANSWER
cls3 = classify_recorder(VALID_TAX)
r = _handle_ask("왜?", {"factory_id": "F-1", "object_type": "diagnosis", "object_id": "D-1"}, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="CONTEXT",
                                   evidence={"id": "D-1", "result_data": {"risk_level": "HIGH"}}),
                explain_fn=explain_real_counting(refs=[0], answer="위험도 HIGH"),
                classify_fn=cls3, save_fn=save_recorder())
check("3 diagnosis->CONTEXT ANSWER", r["status"] == "ANSWER" and r["source"] == "CONTEXT")
check("3b CONTEXT ANSWER->classifier 미호출", cls3.rec["calls"] == 0)

# 4. Routing ASK → 저장 안 함
save4 = save_recorder()
cls4 = classify_recorder(VALID_TAX)
r = _handle_ask("내 진단?", {"object_type": "diagnosis"}, False, IDENT,
                route_fn=route_ret(status="ASK", missing_field="factory_id"),
                explain_fn=lambda r, q: {"status": "ERROR"}, classify_fn=cls4, save_fn=save4)
check("4 ASK->상태 반환", r["status"] == "ASK" and r["missing_field"] == "factory_id" and r["already_asked"] is True)
check("4b ASK->저장 안 함", save4.rec["calls"] == 0)
check("4c ASK->classifier 미호출", cls4.rec["calls"] == 0)

# 5. Routing HANDOFF → inquiry 1건 저장
save5 = save_recorder(no="TAI-INQ-20260814-0009")
cls5 = classify_recorder(VALID_TAX)
r = _handle_ask("환불", None, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="no evidence found"),
                explain_fn=lambda r, q: {"status": "ERROR"}, classify_fn=cls5, save_fn=save5)
check("5 HANDOFF->저장1건+inquiry_no",
      r["status"] == "HANDOFF" and r["inquiry_no"] == "TAI-INQ-20260814-0009" and save5.rec["calls"] == 1)
check("5b HANDOFF stored None->context None(support 없음)", save5.rec["kwargs"]["context"] is None)

# 6. Answer INSUFFICIENT → inquiry 1건 저장
save6 = save_recorder()
cls6 = classify_recorder(VALID_TAX)
r = _handle_ask("근거밖 질문", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="KNOWLEDGE",
                                   evidence=[{"doc_id": "KB-1", "title": "g"}]),
                explain_fn=explain_real_counting(insufficient=True), classify_fn=cls6, save_fn=save6)
check("6 Answer INSUFFICIENT->HANDOFF 저장", r["status"] == "HANDOFF" and save6.rec["calls"] == 1)

# 7. HANDOFF 시 context 보존
save7 = save_recorder()
stored = {"factory_id": "F-9", "object_type": "diagnosis", "object_id": "D-9"}
r = _handle_ask("이관질문", stored, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="x"),
                explain_fn=lambda r, q: {"status": "ERROR"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save7)
kw = save7.rec["kwargs"]
check("7 HANDOFF context 보존",
      kw["context"] == stored and kw["user_id"] == "U-1" and kw["company_id"] == "C-1"
      and kw["page_url"] == "https://safe/x" and kw["question"] == "이관질문"
      and "support" not in kw["context"])

# 8. HANDOFF 저장 실패 → ERROR
r = _handle_ask("환불", None, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="x"),
                explain_fn=lambda r, q: {"status": "ERROR"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save_recorder(boom=True))
check("8 저장 실패->ERROR", r["status"] == "ERROR" and "save failed" in r["detail"])

# 9. Routing ERROR → ERROR
r = _handle_ask("x", None, False, IDENT,
                route_fn=route_ret(status="ERROR", detail="faq_search failed"),
                explain_fn=lambda r, q: {"status": "ANSWER"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save_recorder())
check("9 Routing ERROR->ERROR", r["status"] == "ERROR" and "faq_search" in r["detail"])

# 10. Answer ERROR → ERROR
r = _handle_ask("x", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="KNOWLEDGE", evidence=[{"doc_id": "KB-1"}]),
                explain_fn=lambda r, q: {"status": "ERROR", "detail": "llm_call failed"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save_recorder())
check("10 Answer ERROR->ERROR", r["status"] == "ERROR" and "llm_call" in r["detail"])

# 11. _build_routing_context: diagnosis 단독 보존 / object_id 미포함 / 비허용 제거
check("11 routing ctx diagnosis 단독 보존",
      _build_routing_context(InquiryContextBody(factory_id="F-1", object_type="diagnosis"))
      == {"factory_id": "F-1", "object_type": "diagnosis"})
check("11b routing ctx object_id 미포함",
      _build_routing_context(InquiryContextBody(factory_id="F-1", object_type="diagnosis", object_id="D-9"))
      == {"factory_id": "F-1", "object_type": "diagnosis"})
check("11c routing ctx 비허용 object_type 제거",
      _build_routing_context(InquiryContextBody(factory_id="F-1", object_type="report")) == {"factory_id": "F-1"})

# 12. _handle_ask(routing_ctx=...): route 는 routing_ctx(+company_id) 사용, 저장은 stored_ctx(clean)
cap = {}


def route_capture(q, ctx, aa):
    cap["ctx"] = dict(ctx)
    return {"status": "HANDOFF", "reason": "x"}


save12 = save_recorder()
stored12 = {"factory_id": "F-1"}                               # 저장용(object_type 제거된 저장 계약 결과)
routing12 = {"factory_id": "F-1", "object_type": "diagnosis"}  # routing 용(diagnosis 보존)
r = _handle_ask("왜?", stored12, False, IDENT, routing_ctx=routing12,
                route_fn=route_capture, explain_fn=lambda r, q: {"status": "ERROR"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save12)
check("12 route 는 routing_ctx 사용(diagnosis+company_id)",
      cap["ctx"].get("object_type") == "diagnosis" and cap["ctx"].get("factory_id") == "F-1"
      and cap["ctx"].get("company_id") == "C-1")
check("12b 저장은 stored_ctx(회사ID·object_type 없음)",
      save12.rec["kwargs"]["context"] == stored12 and "company_id" not in save12.rec["kwargs"]["context"])

# 13. 하위호환: routing_ctx 미지정 → stored_ctx 를 routing 근거로 사용
cap2 = {}


def route_capture2(q, ctx, aa):
    cap2["ctx"] = dict(ctx)
    return {"status": "HANDOFF", "reason": "x"}


_handle_ask("q", {"factory_id": "F-7"}, False, IDENT,
            route_fn=route_capture2, explain_fn=lambda r, q: {"status": "ERROR"},
            classify_fn=classify_recorder(VALID_TAX), save_fn=save_recorder())
check("13 하위호환: routing_ctx None→stored 사용", cap2["ctx"].get("factory_id") == "F-7")

# ── Enriched HANDOFF(구현 1단계 + 의미 안전성 보정) ──

# 14. diagnosis(CONTEXT) INSUFFICIENT → context.support 에 diagnosis_summary FACT + safe token
save14 = save_recorder()
diag_ev = {"id": "D-1", "result_data": {"verdict": "APPLICABLE", "risk_level": "MEDIUM",
                                        "obligations": [1, 2, 3]}}
r = _handle_ask("왜 이 법이?", {"factory_id": "F-1", "object_type": "diagnosis"}, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="CONTEXT", evidence=diag_ev),
                explain_fn=lambda r, q: {"status": "INSUFFICIENT"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save14)
sup = (save14.rec["kwargs"]["context"] or {}).get("support")
check("14 diagnosis INSUFFICIENT->support FACT+token",
      r["status"] == "HANDOFF" and isinstance(sup, dict)
      and sup.get("handoff_reason") == "answer_insufficient"
      and sup.get("unknown_gap") == "answer_insufficient"
      and any(f.get("fact_type") == "diagnosis_summary" and f.get("verdict") == "APPLICABLE"
              and f.get("risk_level") == "MEDIUM" and f.get("obligation_count") == 3
              for f in sup.get("verified_facts", [])))

# 15. KNOWLEDGE INSUFFICIENT → support 미첨부(context None)
save15 = save_recorder()
r = _handle_ask("가이드 밖", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="KNOWLEDGE", evidence=[{"doc_id": "KB-1"}]),
                explain_fn=lambda r, q: {"status": "INSUFFICIENT"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save15)
check("15 KNOWLEDGE INSUFFICIENT->support 없음",
      r["status"] == "HANDOFF" and save15.rec["kwargs"]["context"] is None)

# 16. Routing HANDOFF(evidence 없음) → support 미첨부, screen context 보존
save16 = save_recorder()
stored16 = {"factory_id": "F-2"}
r = _handle_ask("환불", stored16, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="no evidence found"),
                explain_fn=lambda r, q: {"status": "ERROR"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save16)
check("16 routing HANDOFF->support 없음+context 보존",
      save16.rec["kwargs"]["context"] == stored16 and "support" not in save16.rec["kwargs"]["context"])

# 17. raw diagnosis payload/obligations 원문/input_data/rules 미저장
save17 = save_recorder()
diag_ev2 = {"id": "D-2", "input_data": {"secret": "x"},
            "result_data": {"verdict": "APPLICABLE", "risk_level": "LOW",
                            "obligations": [{"description": "원문"}], "rules": ["r"]}}
r = _handle_ask("왜?", {"factory_id": "F-1", "object_type": "diagnosis"}, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="CONTEXT", evidence=diag_ev2),
                explain_fn=lambda r, q: {"status": "INSUFFICIENT"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save17)
sup17 = save17.rec["kwargs"]["context"]["support"]
blob = json.dumps(sup17, ensure_ascii=False)
check("17 raw payload 미저장",
      "input_data" not in blob and "원문" not in blob and "secret" not in blob and "rules" not in blob
      and sup17["verified_facts"][0]["obligation_count"] == 1)

# 18. stored_ctx + diagnosis INSUFFICIENT → screen context + support 공존
save18 = save_recorder()
stored18 = {"factory_id": "F-1"}
r = _handle_ask("왜?", stored18, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="CONTEXT",
                                   evidence={"result_data": {"risk_level": "HIGH"}}),
                explain_fn=lambda r, q: {"status": "INSUFFICIENT"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save18)
ctx18 = save18.rec["kwargs"]["context"]
check("18 screen+support 공존",
      ctx18.get("factory_id") == "F-1" and "support" in ctx18
      and ctx18["support"]["verified_facts"][0]["risk_level"] == "HIGH")

# 19. _do_handoff(verified_support=None) → 기존과 동일(support 없음)
save19 = save_recorder()
out = _do_handoff("q", {"factory_id": "F-1"}, IDENT, "x", save19, None)
check("19 _do_handoff 기본(support 없음)",
      out["status"] == "HANDOFF" and save19.rec["kwargs"]["context"] == {"factory_id": "F-1"}
      and "support" not in save19.rec["kwargs"]["context"])

# 20. obligations list → obligation_count=len / rule_count 만 있으면 obligation_count 없음(fallback 제거)
save20a = save_recorder()
r = _handle_ask("왜?", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="CONTEXT", evidence={"result_data": {"foo": "bar"}}),
                explain_fn=lambda r, q: {"status": "INSUFFICIENT"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save20a)
check("20 대표값 없음->support 없음", save20a.rec["kwargs"]["context"] is None)
save20b = save_recorder()
r = _handle_ask("왜?", None, False, IDENT,
                route_fn=route_ret(status="ANSWER", source="CONTEXT",
                                   evidence={"result_data": {"risk_level": "LOW", "rule_count": 7}}),
                explain_fn=lambda r, q: {"status": "INSUFFICIENT"},
                classify_fn=classify_recorder(VALID_TAX), save_fn=save20b)
sup20b = save20b.rec["kwargs"]["context"]["support"]
blob20b = json.dumps(sup20b, ensure_ascii=False)
check("20b rule_count fallback 제거(obligation_count 없음, rule_count 미저장)",
      sup20b["verified_facts"][0].get("risk_level") == "LOW"
      and "obligation_count" not in sup20b["verified_facts"][0]
      and "rule_count" not in blob20b)

# 21. _project_diagnosis_summary 단위
check("21 obligations list->count",
      _project_diagnosis_summary({"result_data": {"risk_level": "HIGH", "obligations": [1, 2]}})
      == {"fact_type": "diagnosis_summary", "risk_level": "HIGH", "obligation_count": 2})
check("21b rule_count 만->obligation_count 없음",
      _project_diagnosis_summary({"result_data": {"risk_level": "LOW", "rule_count": 9}})
      == {"fact_type": "diagnosis_summary", "risk_level": "LOW"})
check("21c 대표값 없음->None",
      _project_diagnosis_summary({"result_data": {"foo": "bar"}}) is None)

# 22. _safe_reason_token whitelist
check("22 no evidence found->no_evidence", _safe_reason_token("no evidence found") == "no_evidence")
check("22b answer_insufficient 유지", _safe_reason_token("answer_insufficient") == "answer_insufficient")
check("22c ownership->ownership_unverified",
      _safe_reason_token("factory ownership unverifiable (no company)") == "ownership_unverified"
      and _safe_reason_token("factory not owned by company") == "ownership_unverified")
check("22d unsupported prefix->unsupported_context",
      _safe_reason_token("unsupported object_type: report") == "unsupported_context")
check("22e 미매핑->needs_review", _safe_reason_token("weird new reason") == "needs_review"
      and _safe_reason_token(None) == "needs_review")

# 23. raw 내부 reason 이 support JSON 에 그대로 저장되지 않음(직접 projection)
pkg = _safe_support_projection(
    {"source": "CONTEXT", "evidence": {"result_data": {"risk_level": "HIGH"}}},
    "factory ownership unverifiable (no company)",
)
blob23 = json.dumps(pkg, ensure_ascii=False)
check("23 raw 내부 reason 미저장",
      pkg["handoff_reason"] == "ownership_unverified" and pkg["unknown_gap"] == "ownership_unverified"
      and "ownership unverifiable" not in blob23 and "(no company)" not in blob23)

# ── 트랙 B(HANDOFF taxonomy 분류) ──

# 24. ANSWER → classifier 0회 (2b/3b 에서 이미 검증, 여기서 명시 재확인)
cls24 = classify_recorder(VALID_TAX)
_handle_ask("q", None, False, IDENT,
            route_fn=route_ret(status="ANSWER", source="KNOWLEDGE", evidence=[{"doc_id": "KB-1"}]),
            explain_fn=explain_real_counting(refs=[0], answer="설명"),
            classify_fn=cls24, save_fn=save_recorder())
check("24 ANSWER->classifier 0회", cls24.rec["calls"] == 0)

# 25. ASK → classifier 0회
cls25 = classify_recorder(VALID_TAX)
_handle_ask("q", {"object_type": "diagnosis"}, False, IDENT,
            route_fn=route_ret(status="ASK", missing_field="factory_id"),
            explain_fn=lambda r, q: {"status": "ERROR"}, classify_fn=cls25, save_fn=save_recorder())
check("25 ASK->classifier 0회", cls25.rec["calls"] == 0)

# 26. routing HANDOFF → classifier 1회
cls26 = classify_recorder(VALID_TAX)
_handle_ask("환불", None, False, IDENT,
            route_fn=route_ret(status="HANDOFF", reason="no evidence found"),
            explain_fn=lambda r, q: {"status": "ERROR"}, classify_fn=cls26, save_fn=save_recorder())
check("26 routing HANDOFF->classifier 1회", cls26.rec["calls"] == 1)

# 27. INSUFFICIENT → classifier 1회
cls27 = classify_recorder(VALID_TAX)
_handle_ask("근거밖", None, False, IDENT,
            route_fn=route_ret(status="ANSWER", source="KNOWLEDGE", evidence=[{"doc_id": "KB-1"}]),
            explain_fn=explain_real_counting(insufficient=True), classify_fn=cls27, save_fn=save_recorder())
check("27 INSUFFICIENT->classifier 1회", cls27.rec["calls"] == 1)

# 28. valid pair → type_code/subtype_code/resolution_axis(HANDOFF) 저장
save28 = save_recorder()
cls28 = classify_recorder({"type_code": "T7", "subtype_code": "T7_PAYMENT_REFUND"})
_handle_ask("환불해주세요", None, False, IDENT,
            route_fn=route_ret(status="HANDOFF", reason="x"),
            explain_fn=lambda r, q: {"status": "ERROR"}, classify_fn=cls28, save_fn=save28)
kw28 = save28.rec["kwargs"]
check("28 valid pair 저장",
      kw28.get("type_code") == "T7" and kw28.get("subtype_code") == "T7_PAYMENT_REFUND"
      and kw28.get("resolution_axis") == "HANDOFF")
# safe context 확인: factory 없음/ page_url 전달 / factory_id 원문 미전달
check("28b classifier safe_context(has_factory=False, page_url 전달, factory_id 원문 없음)",
      cls28.rec["ctx"].get("has_factory") is False and cls28.rec["ctx"].get("page_url") == "https://safe/x"
      and "factory_id" not in cls28.rec["ctx"])

# 29. invalid/mismatch(classifier None) → type/subtype NULL, axis 는 HANDOFF
save29 = save_recorder()
cls29 = classify_recorder(None)  # 무효/미분류
_handle_ask("환불", None, False, IDENT,
            route_fn=route_ret(status="HANDOFF", reason="x"),
            explain_fn=lambda r, q: {"status": "ERROR"}, classify_fn=cls29, save_fn=save29)
kw29 = save29.rec["kwargs"]
check("29 classifier None->type/subtype NULL, axis HANDOFF",
      kw29.get("type_code") is None and kw29.get("subtype_code") is None
      and kw29.get("resolution_axis") == "HANDOFF")

# 30. classifier exception → HANDOFF 저장 계속(taxonomy NULL)
save30 = save_recorder()
cls30 = classify_recorder(boom=True)
r = _handle_ask("환불", None, False, IDENT,
                route_fn=route_ret(status="HANDOFF", reason="x"),
                explain_fn=lambda r, q: {"status": "ERROR"}, classify_fn=cls30, save_fn=save30)
kw30 = save30.rec["kwargs"]
check("30 classifier exception->저장 계속, taxonomy NULL",
      r["status"] == "HANDOFF" and save30.rec["calls"] == 1
      and kw30.get("type_code") is None and kw30.get("subtype_code") is None
      and kw30.get("resolution_axis") == "HANDOFF")

# 31. taxonomy 는 정규 컬럼으로만 — context.support 에 type_code 등을 넣지 않음
save31 = save_recorder()
cls31 = classify_recorder({"type_code": "T7", "subtype_code": "T7_PAYMENT_REFUND"})
diag_ev31 = {"result_data": {"risk_level": "HIGH"}}
_handle_ask("왜?", {"factory_id": "F-1", "object_type": "diagnosis"}, False, IDENT,
            route_fn=route_ret(status="ANSWER", source="CONTEXT", evidence=diag_ev31),
            explain_fn=lambda r, q: {"status": "INSUFFICIENT"}, classify_fn=cls31, save_fn=save31)
kw31 = save31.rec["kwargs"]
sup31 = (kw31["context"] or {}).get("support", {})
blob31 = json.dumps(sup31, ensure_ascii=False)
check("31 taxonomy 정규 컬럼 전용(context.support 에 미포함)",
      kw31.get("type_code") == "T7" and "T7" not in blob31
      and "type_code" not in blob31 and "resolution_axis" not in blob31)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
print("ALL PASS")
