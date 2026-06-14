"""
admin_executor_llm_fix — executor 보정 3층 LLM(GPT API) 임시 라우터.

목적: semantic_clause_fix의 DEFER_REVIEW 잔여(조건절/수식절 깊은 주어)를
GPT API로 주어 판정 → 6중 그물 검증 → 통과분만 executor_fixed에 기록.

규정: docs/2026-06-14_LLM_EXECUTOR_RULES_VALIDATION.md
- LLM은 원문서 주어 발췌만(생성 금지). 주어없음/의무아님 허용.
- 6중그물: ①Kiwi 명사검증 ②원문 발췌존재 ③BLOCKLIST(법령형식어·사물) ④role_check(실행주체만)
  ⑤벌칙/효력/준용 종결(의무아님) ⑥부사격 차단(에/에는/에 대해서=장소·대상, 주체 아님).
- executor_text 직접 변경 금지. executor_fixed에만 기록. 검증·표본 후 별도 반영.
- 원본 semantic_clause 무변경. 임시 라우터(작업 끝나면 제거).

보호: X-Internal-Secret 헤더 = INTERNAL_API_SECRET 필요.
실행(백그라운드 전체): POST /admin/executor-llm-fix/start?dry_run=false&batch_size=50
  → 즉시 202 응답, 서버 뒤에서 전체 처리. 긴 HTTP 요청 타임아웃(502) 회피.
진행 확인: GET /admin/executor-llm-fix/status
단발(동기): POST /admin/executor-llm-fix?limit=50&dry_run=true  (검증·표본용)
"""
import os
import json
import re
import threading
import time
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from db.supabase_client import get_supabase

router = APIRouter()

OPENAI_MODEL = "gpt-4o-mini"

# ── 진행 상태(메모리, 단일 워커 가정) ──
_JOB = {"running": False, "started_at": None, "processed": 0, "applied": 0,
        "rejected": 0, "non_subject": 0, "error": 0, "batches": 0,
        "remaining": None, "reject_reasons": {}, "last_update": None, "stop": False}
_JOB_LOCK = threading.Lock()

# ── BLOCKLIST (그물3) ──
_B1_LAW_FORMS = ("대통령령", "부령", "조례", "고시", "총리령", "훈령", "예규", "규칙")
_SAMUL_SUFFIX = re.compile(
    r"(권리|금액|기간|비용|시설|설비|장치|배관|가스|사고|규모|연면적|높이|층수|방향|"
    r"오염도|권한|자격|회의|항목|규정|재단|안전성|업무|사업|행위|자료|서류|사항|결과|내용|기준|"
    r"단지|크레인|차량|기계|기구|건축물|구조물|토양|물건)$"
)
_OBLIG_NOT = re.compile(r"(처한다|과태료|벌금|징역|부과한다|준용한다|소멸한다|효력을 상실|로 본다)")

_SYSTEM_PROMPT = (
    "너는 한국 법령 의미절의 '의무 주체(주어)'만 원문에서 찾아 발췌하는 도구다. "
    "새 단어를 만들지 말고 원문에 있는 표현만 그대로 발췌한다. 다음 규칙을 엄격히 지켜라.\n"
    "1) 의무 주체 = 그 의무(동사)를 실행하는 쪽. 수령/대상/객체/장소는 주체가 아니다.\n"
    "   - 'X에 대하여는/X에게는 ~을 지급/지원/적용한다' → X는 받는 대상이지 주체 아님.\n"
    "   - 'X에는/X에 대해서는 ~한다'에서 X(장소·대상)는 주체 아님. (산업단지에는, 크레인에 대해서는)\n"
    "   - 'X를 ~한다'의 X(목적어), 'X에 관하여는'의 X(화제)도 주체 아님.\n"
    "   - 의무 주체는 보통 'X은/는/이/가 ~하여야 한다' 형태로 주격조사가 붙는다.\n"
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
    '"role_check":"실행주체|수령대상|객체|장소|없음",'
    '"confidence":"high|low"}'
)


def _gpt_judge(source_text: str, source_part: str, content_type: str) -> dict:
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
        messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                  {"role": "user", "content": user}],
        temperature=0, response_format={"type": "json_object"}, max_tokens=300,
    )
    return json.loads(resp.choices[0].message.content)


_kiwi = None
def _kiwi_is_noun_ending(text: str) -> bool:
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
        return not re.search(r"(하|되|받|당|들|르|기|고|며|서|은|는|이|가|을|를|에)$", text)


def _passes_nets(executor: str, source_part: str, role_check: str, source_text: str = "") -> tuple[bool, str]:
    if executor in ("주어없음", "의무아님", "", None):
        return False, f"non_subject:{executor}"
    if _OBLIG_NOT.search(source_text):
        return False, "not_obligation(penalty/effect)"
    if role_check != "실행주체":
        return False, f"role_check:{role_check}"
    if any(b in executor for b in _B1_LAW_FORMS):
        return False, "blocklist_B1_lawform"
    if _SAMUL_SUFFIX.search(executor):
        return False, "blocklist_B3_samul"
    core = re.sub(r"\s+", "", executor)
    pt_ns = re.sub(r"\s+", "", source_part)
    if core not in pt_ns:
        return False, "not_in_source(hallucination)"
    if not _kiwi_is_noun_ending(executor):
        return False, "kiwi_not_noun"
    if executor in ("하는 자", "한 자", "되는 자", "된 자", "있는 자", "그 자", "자", "것"):
        return False, "incomplete_subject(modifier_cut)"
    pos = pt_ns.find(core)
    if pos >= 0:
        after = pt_ns[pos + len(core): pos + len(core) + 6]
        if re.match(r"(에는|에게|에대하여|에대해서|에관하여|에관해서|에서|에)", after) \
           and not re.match(r"(에서의|에관한)", after) \
           and not re.search(re.escape(core) + r"(은|는|이|가)", pt_ns):
            return False, "adverbial_case(place/object_not_subject)"
    return True, "ok"


def _fetch(sb, n):
    return (
        sb.table("semantic_clause_fix")
        .select("id, source_text, source_part_text, content_type, executor_text")
        .eq("fix_status", "DEFER_REVIEW").limit(n).execute()
    ).data or []


def _process_one(sb, r, dry_run):
    rid = r["id"]
    st = (r.get("source_text") or "").strip()
    pt = (r.get("source_part_text") or "").strip()
    ct = r.get("content_type") or ""
    try:
        j = _gpt_judge(st, pt, ct)
    except Exception:
        _JOB["error"] += 1
        return
    executor = (j.get("executor") or "").strip()
    role = j.get("role_check") or ""
    conf = j.get("confidence") or "low"
    ok, reason = _passes_nets(executor, pt, role, st)
    if ok and conf == "high":
        _JOB["applied"] += 1
        if not dry_run:
            sb.table("semantic_clause_fix").update({
                "executor_fixed": executor, "fix_status": "LLM_CANDIDATE",
                "review_reason": f"GPT-{OPENAI_MODEL} 판정 채택 후보: {role}",
            }).eq("id", rid).execute()
    else:
        if executor in ("주어없음", "의무아님") or reason.startswith("not_obligation"):
            _JOB["non_subject"] += 1
            if not dry_run:
                sb.table("semantic_clause_fix").update({
                    "review_reason": f"GPT 판정: {executor} / {reason}",
                }).eq("id", rid).execute()
        else:
            _JOB["rejected"] += 1
            _JOB["reject_reasons"][reason] = _JOB["reject_reasons"].get(reason, 0) + 1


def _run_job(dry_run: bool, batch_size: int, max_batches: int):
    """백그라운드 전체 처리. 배치마다 Supabase 재접속."""
    try:
        for b in range(max_batches):
            if _JOB["stop"]:
                break
            sb = get_supabase()
            try:
                rows = _fetch(sb, batch_size)
            except Exception:
                sb = get_supabase()
                try:
                    rows = _fetch(sb, batch_size)
                except Exception:
                    break
            if not rows:
                break
            for r in rows:
                _process_one(sb, r, dry_run)
                _JOB["processed"] += 1
            _JOB["batches"] = b + 1
            _JOB["last_update"] = time.time()
            if dry_run:
                break
        # 잔여 카운트
        try:
            sb = get_supabase()
            rem = (sb.table("semantic_clause_fix").select("id", count="exact")
                   .eq("fix_status", "DEFER_REVIEW").limit(1).execute())
            _JOB["remaining"] = rem.count
        except Exception:
            pass
    finally:
        _JOB["running"] = False
        _JOB["last_update"] = time.time()


@router.post("/admin/executor-llm-fix/start")
def start_job(
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(False),
    batch_size: int = Query(50, ge=1, le=200),
    max_batches: int = Query(300, ge=1, le=2000),
    x_internal_secret: str = Header(None, alias="X-Internal-Secret"),
):
    """백그라운드로 전체 DEFER_REVIEW 처리 시작. 즉시 202 응답."""
    if x_internal_secret != os.environ.get("INTERNAL_API_SECRET"):
        raise HTTPException(status_code=403, detail="forbidden")
    if _JOB["running"]:
        return {"status": "already_running", **_status_snapshot()}
    # 상태 초기화
    for k in ("processed", "applied", "rejected", "non_subject", "error", "batches"):
        _JOB[k] = 0
    _JOB["reject_reasons"] = {}
    _JOB["running"] = True
    _JOB["stop"] = False
    _JOB["started_at"] = time.time()
    _JOB["remaining"] = None
    background_tasks.add_task(_run_job, dry_run, batch_size, max_batches)
    return {"status": "started", "dry_run": dry_run, "batch_size": batch_size}


def _status_snapshot():
    return {
        "running": _JOB["running"], "processed": _JOB["processed"],
        "applied": _JOB["applied"], "rejected": _JOB["rejected"],
        "non_subject": _JOB["non_subject"], "error": _JOB["error"],
        "batches": _JOB["batches"], "remaining": _JOB["remaining"],
        "reject_reasons": _JOB["reject_reasons"],
        "started_at": _JOB["started_at"], "last_update": _JOB["last_update"],
    }


@router.get("/admin/executor-llm-fix/status")
def job_status(x_internal_secret: str = Header(None, alias="X-Internal-Secret")):
    if x_internal_secret != os.environ.get("INTERNAL_API_SECRET"):
        raise HTTPException(status_code=403, detail="forbidden")
    return _status_snapshot()


@router.post("/admin/executor-llm-fix/stop")
def stop_job(x_internal_secret: str = Header(None, alias="X-Internal-Secret")):
    if x_internal_secret != os.environ.get("INTERNAL_API_SECRET"):
        raise HTTPException(status_code=403, detail="forbidden")
    _JOB["stop"] = True
    return {"status": "stopping", **_status_snapshot()}


@router.post("/admin/executor-llm-fix")
def executor_llm_fix(
    limit: int = Query(50, ge=1, le=500),
    dry_run: bool = Query(True),
    x_internal_secret: str = Header(None, alias="X-Internal-Secret"),
):
    """단발 동기 모드 (검증·표본용). 전체 처리는 /start 사용."""
    if x_internal_secret != os.environ.get("INTERNAL_API_SECRET"):
        raise HTTPException(status_code=403, detail="forbidden")
    sb = get_supabase()
    rows = _fetch(sb, limit)
    # 임시로 JOB 카운터 재사용하지 않고 로컬 집계
    local = {"requested": len(rows), "applied": 0, "rejected": 0,
             "non_subject": 0, "error": 0, "samples": [], "reject_reasons": {}}
    for r in rows:
        rid = r["id"]; st = (r.get("source_text") or "").strip()
        pt = (r.get("source_part_text") or "").strip(); ct = r.get("content_type") or ""
        try:
            j = _gpt_judge(st, pt, ct)
        except Exception:
            local["error"] += 1; continue
        executor = (j.get("executor") or "").strip()
        role = j.get("role_check") or ""; conf = j.get("confidence") or "low"
        ok, reason = _passes_nets(executor, pt, role, st)
        if ok and conf == "high":
            local["applied"] += 1
            if not dry_run:
                sb.table("semantic_clause_fix").update({
                    "executor_fixed": executor, "fix_status": "LLM_CANDIDATE",
                    "review_reason": f"GPT-{OPENAI_MODEL} 판정 채택 후보: {role}",
                }).eq("id", rid).execute()
            if len(local["samples"]) < 25:
                local["samples"].append({"id": rid, "executor": executor, "role": role,
                                          "conf": conf, "src": st[:60],
                                          "span": (j.get("source_span") or "")[:50]})
        else:
            if executor in ("주어없음", "의무아님") or reason.startswith("not_obligation"):
                local["non_subject"] += 1
                if not dry_run:
                    sb.table("semantic_clause_fix").update({
                        "review_reason": f"GPT 판정: {executor} / {reason}",
                    }).eq("id", rid).execute()
            else:
                local["rejected"] += 1
                local["reject_reasons"][reason] = local["reject_reasons"].get(reason, 0) + 1
    return local
