"""
admin_executor_llm_fix — executor 보정 3층 LLM(GPT API) 임시 라우터.

목적: semantic_clause_fix의 DEFER_REVIEW 잔여(조건절/수식절 깊은 주어)를
GPT API로 주어 판정 → 5중 그물 검증 → 통과분만 executor_fixed에 기록.

규정: docs/2026-06-14_LLM_EXECUTOR_RULES_VALIDATION.md (v2, 4중그물 + 벌칙그물)
- LLM은 원문서 주어 발췌만(생성 금지). 주어없음/의무아님 허용.
- 5중그물: ①Kiwi 명사검증 ②원문 발췌존재 ③BLOCKLIST ④role_check(실행주체만)
  ⑤벌칙/효력/준용 종결(의무아님) 차단.
- executor_text 직접 변경 금지. executor_fixed에만 기록. 검증·표본 후 별도 반영.
- 원본 semantic_clause 무변경. 임시 라우터(작업 끝나면 제거).

보호: X-Internal-Secret 헤더 = INTERNAL_API_SECRET 필요.
실행: POST /admin/executor-llm-fix?limit=50&dry_run=true
"""
import os
import json
import re
from fastapi import APIRouter, Header, HTTPException, Query
from db.supabase_client import get_supabase

router = APIRouter()

OPENAI_MODEL = "gpt-4o-mini"

# ── BLOCKLIST (그물3) ──
_B1_LAW_FORMS = ("대통령령", "부령", "조례", "고시", "총리령", "훈령", "예규", "규칙")
_SAMUL_SUFFIX = re.compile(
    r"(권리|금액|기간|비용|시설|설비|장치|배관|가스|사고|규모|연면적|높이|층수|방향|"
    r"오염도|권한|자격|회의|항목|규정|재단|안전성|업무|사업|행위|자료|서류|사항|결과|내용|기준)$"
)
# 그물5: 벌칙/효력/준용 종결 (의무 아님)
_OBLIG_NOT = re.compile(r"(처한다|과태료|벌금|징역|부과한다|준용한다|소멸한다|효력을 상실|로 본다)")

# ── LLM 규정 v2 프롬프트 ──
_SYSTEM_PROMPT = (
    "너는 한국 법령 의미절의 '의무 주체(주어)'만 원문에서 찾아 발췌하는 도구다. "
    "새 단어를 만들지 말고 원문에 있는 표현만 그대로 발췌한다. 다음 규칙을 엄격히 지켜라.\n"
    "1) 의무 주체 = 그 의무(동사)를 실행하는 쪽. 수령/대상/객체는 주체가 아니다.\n"
    "   - 'X에 대하여는/X에게는 ~을 지급/지원/적용한다' → X는 받는 대상이지 주체 아님.\n"
    "   - 'X를 ~한다'의 X(목적어), 'X에 관하여는'의 X(화제)도 주체 아님.\n"
    "2) 주어가 원문에 명시 안 됐으면(생략) executor='주어없음'.\n"
    "3) 의무 자체가 아니면 executor='의무아님'. 특히 문장이 "
    "'…에 처한다 / 과태료를 부과한다 / 벌금 / 징역'으로 끝나는 벌칙, "
    "'정한다'(위임), '준용한다'(준용), '소멸한다/상실한다'(효력)는 모두 '의무아님'이다. "
    "벌칙의 '…한 자'는 의무 주체가 아니라 처벌 대상이므로 절대 executor로 내지 마라.\n"
    "4) 법령형식어(대통령령/부령/조례/고시)는 주어가 아니다.\n"
    "5) 'X가 ~하는/~된/~인' 수식절의 X는 수식절 주어일 뿐 의무 주체가 아니다.\n"
    "6) 주어를 발췌할 때는 수식어구를 포함한 완전한 명사구로 발췌하라. "
    "예: '…으로 하는 자' 전체를 발췌하고 '하는 자'처럼 잘라내지 마라.\n"
    "7) 불확실하면 executor='주어없음', confidence='low'.\n"
    "출력은 JSON만. 형식: "
    '{"executor":"<원문 발췌 or 주어없음 or 의무아님>",'
    '"source_span":"<주어 포함 원문 구절 그대로>",'
    '"role_check":"실행주체|수령대상|객체|없음",'
    '"confidence":"high|low"}'
)


def _gpt_judge(source_text: str, source_part: str, content_type: str) -> dict:
    """GPT API로 주어 판정. 실패 시 예외 발생(상위에서 처리)."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    user = (
        f"[content_type] {content_type}\n"
        f"[의미절] {source_text}\n"
        f"[원문 전체] {source_part}\n\n"
        "이 의미절의 의무 주체를 위 규칙대로 판정해 JSON만 출력하라."
    )
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=300,
    )
    return json.loads(resp.choices[0].message.content)


# ── 그물1: Kiwi 명사 검증 ──
_kiwi = None
def _kiwi_is_noun_ending(text: str) -> bool:
    """executor 마지막 형태소가 명사류(NN*/XSN)인지. Kiwi 사용, 실패 시 간이검증."""
    global _kiwi
    try:
        if _kiwi is None:
            from kiwipiepy import Kiwi
            _kiwi = Kiwi()
        toks = _kiwi.tokenize(text)
        if not toks:
            return False
        last = toks[-1]
        return last.tag.startswith("NN") or last.tag in ("XSN", "NP", "XR")
    except Exception:
        # 간이검증: 동사/어미 어간으로 끝나면 False
        return not re.search(r"(하|되|받|당|들|르|기|고|며|서|은|는|이|가|을|를|에)$", text)


def _passes_nets(executor: str, source_part: str, role_check: str, source_text: str = "") -> tuple[bool, str]:
    """5중 그물. 통과 여부 + 사유."""
    if executor in ("주어없음", "의무아님", "", None):
        return False, f"non_subject:{executor}"
    # 그물5: 의미절이 벌칙/효력/준용 종결이면 의무 아님 → executor 채우지 않음
    if _OBLIG_NOT.search(source_text):
        return False, "not_obligation(penalty/effect)"
    # 그물4(자동): role_check가 실행주체가 아니면 탈락
    if role_check != "실행주체":
        return False, f"role_check:{role_check}"
    # 그물3: BLOCKLIST
    if any(b in executor for b in _B1_LAW_FORMS):
        return False, "blocklist_B1_lawform"
    if _SAMUL_SUFFIX.search(executor):
        return False, "blocklist_B3_samul"
    # 그물2: 원문 발췌 존재 (핵심 명사가 원문에 있어야)
    core = re.sub(r"\s+", "", executor)
    if core not in re.sub(r"\s+", "", source_part):
        return False, "not_in_source(hallucination)"
    # 그물1: Kiwi 명사 끝
    if not _kiwi_is_noun_ending(executor):
        return False, "kiwi_not_noun"
    # "하는 자"/"한 자"처럼 수식 잘린 불완전 주어 차단(2글자 자/것 단독)
    if executor in ("하는 자", "한 자", "되는 자", "된 자", "있는 자", "그 자", "자", "것"):
        return False, "incomplete_subject(modifier_cut)"
    return True, "ok"


@router.post("/admin/executor-llm-fix")
def executor_llm_fix(
    limit: int = Query(50, ge=1, le=500),
    dry_run: bool = Query(True),
    x_internal_secret: str = Header(None, alias="X-Internal-Secret"),
):
    if x_internal_secret != os.environ.get("INTERNAL_API_SECRET"):
        raise HTTPException(status_code=403, detail="forbidden")

    sb = get_supabase()
    # DEFER_REVIEW 잔여를 limit개 (이미 LLM 시도한 것 제외: review_reason 마커 없는 것)
    rows = (
        sb.table("semantic_clause_fix")
        .select("id, source_text, source_part_text, content_type, executor_text")
        .eq("fix_status", "DEFER_REVIEW")
        .limit(limit)
        .execute()
    ).data or []

    results = {"requested": len(rows), "applied": 0, "rejected": 0,
               "non_subject": 0, "error": 0, "samples": [], "reject_reasons": {}}

    for r in rows:
        rid = r["id"]
        st = (r.get("source_text") or "").strip()
        pt = (r.get("source_part_text") or "").strip()
        ct = r.get("content_type") or ""
        try:
            j = _gpt_judge(st, pt, ct)
        except Exception:
            results["error"] += 1
            continue

        executor = (j.get("executor") or "").strip()
        role = j.get("role_check") or ""
        conf = j.get("confidence") or "low"
        ok, reason = _passes_nets(executor, pt, role, st)

        if ok and conf == "high":
            results["applied"] += 1
            if not dry_run:
                sb.table("semantic_clause_fix").update({
                    "executor_fixed": executor,
                    "fix_status": "LLM_CANDIDATE",  # 표본 검증 전 후보 상태
                    "review_reason": f"GPT-{OPENAI_MODEL} 판정 채택 후보: {role}",
                }).eq("id", rid).execute()
            if len(results["samples"]) < 25:
                results["samples"].append({
                    "id": rid, "executor": executor, "role": role, "conf": conf,
                    "src": st[:60], "span": (j.get("source_span") or "")[:50],
                })
        else:
            if executor in ("주어없음", "의무아님") or reason.startswith("not_obligation"):
                results["non_subject"] += 1
                if not dry_run:
                    sb.table("semantic_clause_fix").update({
                        "review_reason": f"GPT 판정: {executor} / {reason}",
                    }).eq("id", rid).execute()
            else:
                results["rejected"] += 1
                results["reject_reasons"][reason] = results["reject_reasons"].get(reason, 0) + 1

    return results
