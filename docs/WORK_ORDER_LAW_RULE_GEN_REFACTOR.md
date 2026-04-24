# Cursor 작업지시서: law_rule_generator.py 서비스 계층 분리 + 품질 게이트

> 규칙: `docs/DEV_RULES_SERVICE_LAYER.md` 준수 (★ STEP 0 필수)
> 브랜치: `dev` → PR → `main`
> 대상: `routers/law_rule_generator.py` (52KB)
> 목표: 52KB → ~12KB (엔드포인트만)

---

## ⚠️ 사고 방지 규칙

```
1. STEP 0(테스트) 없이 STEP 1 진행 금지
2. 매 STEP 완료 후 uvicorn main:app --reload 서버 확인
3. 서버 안 뜨면 git checkout -- . 원복
4. 52KB 파일 전체 덮어쓰기 금지 — 함수 단위로 이동
5. 기존 API 응답 형식 절대 변경 금지
```

---

## 현재 구조 분석

이미 존재하는 서비스 파일:
```
routers/_rule_gen_prompts.py    6.7KB  프롬프트+상수 (이미 분리됨)
services/rule_gen_ai.py         2.4KB  AI 호출
services/rule_gen_builders.py   5.4KB  드래프트 빌더
services/rule_gen_helpers.py    5.0KB  헬퍼 함수
services/rule_gen_reparse.py    9.0KB  reparse 로직
services/rule_gen_svc.py       12.0KB  핵심 서비스
schemas/rule_gen.py                    Pydantic 모델
```

문제: 라우터(52KB)에 동일 로직이 **중복** 존재. 서비스로 이동하고 라우터는 import만.

---

## STEP 0: 테스트 먼저 작성

```bash
# 파일: tests/test_law_rule_generator_current.py
# 최소 5개 테스트 — 분리 전에 전부 PASS 확인
```

테스트 대상:
1. `_extract_json_payload()` — JSON 추출 정확성
2. `_normalize_submit_org_code()` — 코드 정규화
3. `_to_bool()` / `_safe_float()` / `_safe_int()` — 타입 변환
4. `_build_master_payload()` — master INSERT 페이로드 구조
5. `_validate_rule_row()` — 무결성 검증
6. `_build_draft_row()` — 드래프트 INSERT 페이로드
7. `_is_blank()` — 빈 값 판단

```bash
pytest tests/test_law_rule_generator_current.py -v
# 전부 PASS 확인 후 STEP 1
```

---

## STEP 1: 라우터 중복 제거 + 헬퍼 이동

라우터에 있는 함수들을 기존 서비스 파일로 이동:

### 1-1. 중복 프롬프트/상수 제거
라우터에서 `SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE`, `FEW_SHOT_RULE` 삭제.
`from routers._rule_gen_prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, FEW_SHOT_RULE` 사용.

### 1-2. 헬퍼 함수 → `services/rule_gen_helpers.py`
라우터에서 이동:
- `_extract_json_payload()`
- `_normalize_submit_org_code()` + `SUBMIT_ORG_LABELS`
- `_to_bool()`, `_safe_float()`, `_safe_int()`
- `_is_blank()`
- `_validate_rule_row()` + `VALID_CONDITION_CODES`

### 1-3. 빌더 함수 → `services/rule_gen_builders.py`
- `_build_master_payload()`
- `_build_draft_row()`
- `_build_reparse_prompt()`

```bash
pytest tests/test_law_rule_generator_current.py -v  # PASS 확인
uvicorn main:app --reload  # 서버 정상 확인
```

---

## STEP 2: AI 호출 + master 등록 로직 이동

### 2-1. `services/rule_gen_ai.py`로 이동
- `_call_claude_messages()`
- `call_claude()`

### 2-2. `services/rule_gen_svc.py`로 이동
- `_auto_approve_to_master()`
- `_fetch_few_shot_examples()`
- `_pick_reparse_targets()`

### 2-3. `services/rule_gen_reparse.py`로 이동
- `_run_reparse_background()`

```bash
pytest tests/test_law_rule_generator_current.py -v  # PASS 확인
```

---

## STEP 3: 라우터 슬림화

라우터에 남은 것: **엔드포인트 정의만** (import + 호출 + 예외 매핑)

각 엔드포인트 패턴:
```python
@router.post("/parse")
async def parse_article(body: dict):
    supabase = get_supabase()
    try:
        result = await rule_gen_svc.parse_article(supabase, body)
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

**목표: 52KB → ~12KB**

```bash
pytest tests/test_law_rule_generator_current.py -v  # PASS
curl -s http://localhost:8000/law-rule-generator/stats  # 정상
curl -s http://localhost:8000/health  # healthy
```

---

## STEP 4: 품질 게이트 + 스코어카드 (분리 완료 후)

### 4-1. master 등록 품질 게이트
`services/rule_gen_svc.py` — `_auto_approve_to_master()` 수정:
```python
def _auto_approve_to_master(supabase, draft: dict) -> Optional[str]:
    # 품질 게이트: condition_code 없으면 master 등록 거부
    if not draft.get("condition_code"):
        log.info(f"[QUALITY GATE] {draft.get('draft_rule_id')} — condition_code 없어 스킵")
        return None
    # ... 기존 로직
```

`bulk_approve_unregistered` 엔드포인트에도 동일 게이트 추가.

### 4-2. 자동승인 범위 확대
`auto_parse_and_approve` 엔드포인트:
```python
# 변경 전: if ob_type == "INSPECT" and conf >= threshold:
# 변경 후:
if conf >= threshold and draft.get("condition_code"):
```

### 4-3. 스코어카드 API
```python
@router.get("/scorecard")
async def get_scorecard():
    supabase = get_supabase()
    res = supabase.rpc("legal_engine_scorecard").execute()
    rows = res.data or []
    grades = {"pass": 0, "warn": 0, "fail": 0}
    for r in rows:
        g = r.get("grade", "")
        if "\u2705" in g: grades["pass"] += 1
        elif "\ud83d\udfe1" in g: grades["warn"] += 1
        elif "\ud83d\udd34" in g: grades["fail"] += 1
    return {"status": "success", "data": {"items": rows, "summary": grades}}
```

---

## STEP 5: 테스트 보강

```bash
tests/test_rule_gen_helpers.py   # _extract_json, _normalize, _validate 등
tests/test_rule_gen_svc.py       # master 등록 품질 게이트 테스트
tests/test_rule_gen_builders.py  # payload 구조 테스트
```

품질 게이트 테스트 필수:
```python
def test_quality_gate_rejects_no_condition():
    """condition_code 없는 draft는 master 등록 거부"""
    draft = {"draft_rule_id": "TEST-001", "condition_code": None, ...}
    result = _auto_approve_to_master(mock_supabase, draft)
    assert result is None

def test_quality_gate_accepts_with_condition():
    """condition_code 있는 draft는 master 등록 허용"""
    draft = {"draft_rule_id": "TEST-002", "condition_code": "building_area", ...}
    result = _auto_approve_to_master(mock_supabase, draft)
    assert result is not None
```

---

## 커밋 규칙

```bash
# STEP 0 커밋
git add tests/test_law_rule_generator_current.py
git commit -m "test: law_rule_generator 현재 동작 스냅샷 테스트"

# STEP 1~3 커밋 (한 번에)
git add routers/law_rule_generator.py services/rule_gen_*.py
git commit -m "refactor: law_rule_generator 52KB→12KB 서비스 계층 분리"

# STEP 4 커밋
git commit -m "feat: master 등록 품질게이트 + 자동승인확대 + 스코어카드 API"

# STEP 5 커밋
git commit -m "test: rule_gen 테스트 보강 + 품질게이트 테스트"

git push origin dev
```

---

## [TAI 개발 규칙]
문서: docs/DEV_RULES_SERVICE_LAYER.md
★ STEP 0 없이 STEP 1로 넘어가지 말 것!
★ 매 단계 테스트 PASS + 서버 정상 확인!

절대 하지 말 것:
- 52KB 파일 통째 덮어쓰기
- INTERNAL_SECRET 값 하드코딩
- 기존 API 응답 형식 변경
- condition_code 검증을 우회하는 코드
- 2개 파일 동시 분리
