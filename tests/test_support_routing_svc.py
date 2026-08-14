# -*- coding: utf-8 -*-
"""support_routing_svc.route 테스트 — 조회를 fake 로 주입(외부 의존 없음).

실행: python tests/test_support_routing_svc.py  (0 종료코드 = 전체 통과)
필수 케이스:
  1. FAQ 정확 일치 → ANSWER
  2. FAQ 유사하지만 불확실 → FAQ ANSWER 금지
  3. Knowledge 근거 존재 → ANSWER + evidence
  4. diagnosis(factory only, 소유 OK) → latest 근거
  5. diagnosis(object_id 있는데 정확 조회 불가) → HANDOFF
  6. 다른 object_type → HANDOFF
  7. 추가질문 1회 규칙
  8. 근거 없음 → HANDOFF
소유권 검증 케이스(신규):
  4b. 소유 아님 → HANDOFF, latest 미호출
  4c. company_id 없음 → HANDOFF, latest 미호출
  4d. 소유권 체크 예외 → ERROR
보완 케이스:
  11. Knowledge hit 있어도 object_type=diagnosis + factory_id(+소유 OK) 이면 CONTEXT 우선
  12. Context 없는 일반 질문은 Knowledge ANSWER
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))
import support_routing_svc as svc  # noqa: E402


def empty(*_a, **_k):
    return {"items": [], "total": 0}


def faq_with(question_text):
    def _f(q, ctx):
        return {"items": [{"doc_id": "FAQ-1", "type": "FAQ", "question": question_text,
                           "answer_short": "답변", "body": "<p>답변</p>"}], "total": 1}
    return _f


def kn_with(items):
    def _f(q, ctx):
        return {"items": items, "total": len(items)}
    return _f


owns_true = lambda company_id, factory_id: True   # noqa: E731
owns_false = lambda company_id, factory_id: False  # noqa: E731


results = []


def check(name, cond):
    results.append((name, cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# 1. FAQ 정확 일치(정규화: 공백/구두점 무시) → ANSWER(FAQ)
r = svc.route(
    "무료 진단은 정말 무료인가요?",
    context={},
    faq_search=faq_with("무료진단은 정말 무료인가요"),   # 공백·물음표 차이만
    knowledge_search=empty,
)
check("1 FAQ 정확일치->ANSWER(FAQ)", r["status"] == "ANSWER" and r["source"] == "FAQ")

# 2. FAQ 유사하지만 불일치 → FAQ ANSWER 금지 (KB도 없음 → HANDOFF)
r = svc.route(
    "무료 진단 환불 규정이 어떻게 되나요?",
    context={},
    faq_search=faq_with("무료 진단은 무료인가요"),   # 주제만 유사, 문구 불일치
    knowledge_search=empty,
)
check("2 FAQ 유사->FAQ ANSWER 금지", not (r["status"] == "ANSWER" and r.get("source") == "FAQ"))
check("2b FAQ 유사->HANDOFF", r["status"] == "HANDOFF")

# 3. Knowledge 근거 존재 → ANSWER + evidence
kn_items = [{"doc_id": "KB-1", "type": "PAGE_GUIDE", "title": "진단 결과 보는 법", "body": "..."}]
r = svc.route(
    "진단 결과 화면은 어떻게 보나요?",
    context={},
    faq_search=empty,
    knowledge_search=kn_with(kn_items),
)
check("3 Knowledge->ANSWER(KNOWLEDGE)+evidence",
      r["status"] == "ANSWER" and r["source"] == "KNOWLEDGE" and r["evidence"] == kn_items)

# 4. diagnosis(factory only, 소유 OK) → latest 근거 → ANSWER(CONTEXT)
latest_payload = {"result_data": {"rules": [], "risk_level": "LOW"}, "sector": "INDUSTRIAL"}
r = svc.route(
    "왜 이 법이 우리 사업장에 적용됐나요?",
    context={"object_type": "diagnosis", "factory_id": "F-1", "company_id": "C-1"},
    faq_search=empty, knowledge_search=empty,
    latest_diagnosis=lambda fid: latest_payload if fid == "F-1" else None,
    company_owns_factory=owns_true,
)
check("4 diagnosis(factory,소유OK)->ANSWER(CONTEXT) latest",
      r["status"] == "ANSWER" and r["source"] == "CONTEXT" and r["evidence"] == latest_payload)

# 4b. 소유 아님 → HANDOFF, latest 미호출(진단 조회 이전에 차단)
called_b = {"latest": False}


def _latest_guard_b(fid):
    called_b["latest"] = True
    return latest_payload


r = svc.route(
    "왜 이 법이 우리 사업장에 적용됐나요?",
    context={"object_type": "diagnosis", "factory_id": "F-9", "company_id": "C-1"},
    faq_search=empty, knowledge_search=empty,
    latest_diagnosis=_latest_guard_b,
    company_owns_factory=owns_false,
)
check("4b 소유 아님->HANDOFF", r["status"] == "HANDOFF" and r.get("reason") == "factory not owned by company")
check("4b2 소유 아님->latest 미호출", called_b["latest"] is False)

# 4c. company_id 없음(검증 불가) → HANDOFF, latest 미호출
called_c = {"latest": False}


def _latest_guard_c(fid):
    called_c["latest"] = True
    return latest_payload


r = svc.route(
    "왜 이 법이 우리 사업장에 적용됐나요?",
    context={"object_type": "diagnosis", "factory_id": "F-1"},   # company_id 없음
    faq_search=empty, knowledge_search=empty,
    latest_diagnosis=_latest_guard_c,
    company_owns_factory=owns_true,
)
check("4c company_id 없음->HANDOFF", r["status"] == "HANDOFF")
check("4c2 company_id 없음->latest 미호출", called_c["latest"] is False)

# 4d. 소유권 체크 예외 → ERROR
def _owns_boom(company_id, factory_id):
    raise RuntimeError("db down")


r = svc.route(
    "왜 이 법이 적용됐나요?",
    context={"object_type": "diagnosis", "factory_id": "F-1", "company_id": "C-1"},
    faq_search=empty, knowledge_search=empty,
    latest_diagnosis=lambda fid: latest_payload,
    company_owns_factory=_owns_boom,
)
check("4d 소유권 체크 예외->ERROR", r["status"] == "ERROR")

# 5. diagnosis(object_id 있는데 정확 조회 불가) → HANDOFF (latest 대체 금지)
called = {"latest": False}


def _latest_should_not_run(fid):
    called["latest"] = True
    return latest_payload


r = svc.route(
    "이 진단 결과가 왜 이런가요?",
    context={"object_type": "diagnosis", "factory_id": "F-1", "object_id": "D-99", "company_id": "C-1"},
    faq_search=empty, knowledge_search=empty,
    latest_diagnosis=_latest_should_not_run,
    diagnosis_by_id=None,   # 정확 조회 경로 미확인
)
check("5 diagnosis(object_id, 조회불가)->HANDOFF", r["status"] == "HANDOFF")
check("5b latest 대체 금지(latest 미호출)", called["latest"] is False)

# 5c. object_id 있고 정확 조회 경로가 확인된 경우 → 해당 diagnosis 사용
by_id_payload = {"id": "D-99", "result_data": {"risk_level": "HIGH"}}
r = svc.route(
    "이 진단 결과가 왜 이런가요?",
    context={"object_type": "diagnosis", "factory_id": "F-1", "object_id": "D-99", "company_id": "C-1"},
    faq_search=empty, knowledge_search=empty,
    diagnosis_by_id=lambda oid: by_id_payload if oid == "D-99" else None,
)
check("5c diagnosis(object_id, 조회가능)->ANSWER(CONTEXT)",
      r["status"] == "ANSWER" and r["source"] == "CONTEXT" and r["evidence"] == by_id_payload)

# 6. 다른 object_type → HANDOFF
r = svc.route(
    "이 보고서 왜 이렇게 나왔나요?",
    context={"object_type": "report", "object_id": "R-1", "factory_id": "F-1", "company_id": "C-1"},
    faq_search=empty, knowledge_search=empty,
)
check("6 다른 object_type->HANDOFF", r["status"] == "HANDOFF")

# 7. 추가질문 1회 규칙 — diagnosis 인데 factory_id·object_id 모두 없음 → ASK(1회)
r = svc.route(
    "내 진단이 왜 이런가요?",
    context={"object_type": "diagnosis", "company_id": "C-1"},
    faq_search=empty, knowledge_search=empty,
)
check("7 부족정보->ASK 1회", r["status"] == "ASK" and r.get("missing_field") == "factory_id")
r2 = svc.route(
    "내 진단이 왜 이런가요?",
    context={"object_type": "diagnosis", "company_id": "C-1"},
    already_asked=True,
    faq_search=empty, knowledge_search=empty,
)
check("7b already_asked->HANDOFF", r2["status"] == "HANDOFF")

# 8. 근거 없음(FAQ/KB miss, object 없음) → HANDOFF
r = svc.route(
    "결제가 안 되는데 환불해 주세요",
    context={},
    faq_search=empty, knowledge_search=empty,
)
check("8 근거 없음->HANDOFF", r["status"] == "HANDOFF")

# 9. 빈 질문 → ERROR
r = svc.route("   ", context={})
check("9 빈 질문->ERROR", r["status"] == "ERROR")


# 10. 조회 예외 → ERROR
def boom(*_a, **_k):
    raise RuntimeError("db down")


r = svc.route("아무 질문", context={}, faq_search=boom)
check("10 조회 예외->ERROR", r["status"] == "ERROR")

# 11. Knowledge hit가 있어도 object_type=diagnosis + factory_id(+소유 OK) 이면 CONTEXT 우선
kn_hit = [{"doc_id": "KB-9", "type": "PAGE_GUIDE", "title": "법 적용 안내", "body": "..."}]
ctx_payload = {"result_data": {"risk_level": "HIGH"}, "sector": "INDUSTRIAL"}
r = svc.route(
    "왜 이 법이 우리 사업장에 적용됐나요?",
    context={"object_type": "diagnosis", "factory_id": "F-1", "company_id": "C-1"},
    faq_search=empty,
    knowledge_search=kn_with(kn_hit),      # Knowledge hit 존재해도
    latest_diagnosis=lambda fid: ctx_payload,
    company_owns_factory=owns_true,
)
check("11 diagnosis+factory: KB hit 있어도 CONTEXT 우선",
      r["status"] == "ANSWER" and r["source"] == "CONTEXT" and r["evidence"] == ctx_payload)

# 12. Context 없는 일반 질문은 기존대로 Knowledge ANSWER
r = svc.route(
    "TBM은 어떻게 등록하나요?",
    context={},                              # object_type 없음
    faq_search=empty,
    knowledge_search=kn_with(kn_hit),
)
check("12 일반질문(context 없음)->Knowledge ANSWER",
      r["status"] == "ANSWER" and r["source"] == "KNOWLEDGE" and r["evidence"] == kn_hit)


failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("FAILED:", failed)
    raise SystemExit(1)
print("ALL PASS")
