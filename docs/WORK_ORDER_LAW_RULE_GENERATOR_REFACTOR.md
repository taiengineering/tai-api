# 작업지시서: law_rule_generator.py 서비스 계층 분리

> 대상: `routers/law_rule_generator.py` (46KB, 1291줄, 32함수, 16엔드포인트)
> 기준 규칙: `docs/DEV_RULES_SERVICE_LAYER.md`
> 브랜치: `main` (직접 push — 외부 import 없어 안전)
> 작업 도구: **Cursor** (46KB 파일이므로 MCP 금지)
> 핵심 원칙: **매 단계 후 서버 실행 → 기존 API 응답 동일 확인**
> 특이사항: **외부 라우터에서 import 없음 → 호환 래퍼 불필요**

---

## 현재 구조 분석

### 엔드포인트 16개
```
GET  /laws                    - 법령 목록 (41줄)
GET  /articles                - 조문 목록 (26줄)
POST /parse                   - 단건 파싱 (44줄)
POST /parse-batch             - 배치 파싱 (71줄)
POST /auto-parse              - 자동 파싱+승인 (96줄)
POST /bulk-approve            - 미등록 일괄 승인 (69줄)
POST /validate-master         - 마스터 검증 (49줄)
POST /reparse-master          - 리파싱 시작 (35줄)
GET  /reparse-master/status   - 리파싱 상태 (34줄)
GET  /reparse-master/jobs     - 리파싱 이력 (14줄)
GET  /stats                   - 통계 (40줄)
GET  /drafts                  - 초안 목록 (36줄)
GET  /drafts/:id              - 초안 상세 (8줄)
PATCH /drafts/:id             - 초안 수정 (15줄)
POST /drafts/:id/approve      - 초안 승인 (32줄)
POST /drafts/:id/reject       - 초안 반려 (13줄)
```

### 내부 함수 16개 (3그룹)
```
[순수 헬퍼 11개 — DB/AI 없음]
_extract_json_payload()        20줄   AI 응답에서 JSON 추출
_normalize_submit_org_code()    6줄   제출기관 코드 정규화
_to_bool()                      9줄   불리언 변환
_safe_float()                   8줄   안전 float 변환
_safe_int()                     8줄   안전 int 변환
_is_blank()                     3줄   빈값 체크
_build_master_payload()        43줄   마스터 데이터 구성
_build_reparse_prompt()        23줄   리파싱 프롬프트 구성
_build_draft_row()             25줄   초안 행 구성
_validate_rule_row()           30줄   룰 유효성 검증
_pick_reparse_targets()        16줄   리파싱 대상 선정

[DB 호출 2개]
_auto_approve_to_master()      21줄   자동 승인→마스터 저장
_fetch_few_shot_examples()     14줄   퓨샷 예시 조회

[AI 호출 3개]
_call_claude_messages()        24줄   Claude API 호출
call_claude()                  10줄   Claude 래퍼
_run_reparse_background()      ??줄   백그라운드 리파싱
```

---

## 사전 준비

```bash
git fetch origin
git checkout main
git pull origin main
```

services/, schemas/, tests/ 디렉토리가 이미 존재 (legal_engine 분리 시 생성됨).

---

## STEP 1: 패키지 생성 + 헬퍼 분리

### 1-1. `services/rule_gen_helpers.py` 생성

순수 유틸 함수 7개를 이동:

```
_extract_json_payload()        20줄
_normalize_submit_org_code()    6줄
_to_bool()                      9줄
_safe_float()                   8줄
_safe_int()                     8줄
_is_blank()                     3줄
_validate_rule_row()           30줄
합계: ~84줄
```

### 1-2. `services/rule_gen_builders.py` 생성

데이터 구성/빌더 함수 3개를 이동:

```
_build_master_payload()        43줄
_build_reparse_prompt()        23줄
_build_draft_row()             25줄
_pick_reparse_targets()        16줄
합계: ~107줄
```

**주의:** builders는 helpers의 함수를 호출할 수 있음.
```python
from services.rule_gen_helpers import _safe_float, _safe_int, _to_bool, _is_blank
```

### 1-3. `routers/law_rule_generator.py`에서 삭제 + import 교체

```python
from services.rule_gen_helpers import (
    _extract_json_payload, _normalize_submit_org_code,
    _to_bool, _safe_float, _safe_int, _is_blank, _validate_rule_row
)
from services.rule_gen_builders import (
    _build_master_payload, _build_reparse_prompt,
    _build_draft_row, _pick_reparse_targets
)
```

### 1-4. 확인

```bash
uvicorn main:app --reload
curl -s https://api.taieng.co.kr/health | python -m json.tool
```

**STEP 1 완료 기준:**
- [ ] `services/rule_gen_helpers.py` (7함수, ~84줄)
- [ ] `services/rule_gen_builders.py` (4함수, ~107줄)
- [ ] 라우터에서 11개 함수 삭제 + import 교체
- [ ] 서버 정상 실행
- [ ] 라우터 크기: 46KB → **약 38KB** (8KB 감소)

---

## STEP 2: 스키마 분리

### 2-1. `schemas/rule_gen.py` 생성

각 엔드포인트의 요청/응답을 Pydantic 모델로:

```python
# schemas/rule_gen.py
from pydantic import BaseModel, Field
from typing import Optional, List

class ParseArticleRequest(BaseModel):
    law_id: str
    article_number: str
    # ... 기존 parse 엔드포인트가 받는 필드

class ParseBatchRequest(BaseModel):
    law_id: str
    articles: List[str]

class ReparseMasterRequest(BaseModel):
    sector: Optional[str] = None
    limit: int = Field(100, ge=1, le=1000)

class DraftUpdateRequest(BaseModel):
    # ... drafts/:id PATCH가 받는 필드
    pass
```

### 2-2. 확인

```bash
uvicorn main:app --reload
```

**STEP 2 완료 기준:**
- [ ] `schemas/rule_gen.py` 생성
- [ ] `req: Request` + `await req.json()` 패턴 → Pydantic 전환
- [ ] 서버 정상 실행

---

## STEP 3: 서비스 분리

### 3-1. `services/rule_gen_ai.py` 생성

Claude API 호출 관련 함수:

```
_call_claude_messages()        24줄   API 호출
call_claude()                  10줄   래퍼
_fetch_few_shot_examples()     14줄   퓨샷 예시 (DB)
합계: ~48줄
```

### 3-2. `services/rule_gen_svc.py` 생성

핵심 비즈니스 로직 (엔드포인트에서 추출):

```
_auto_approve_to_master()      21줄   자동 승인→마스터
_run_reparse_background()      ??줄   백그라운드 리파싱

+ 엔드포인트에서 추출할 비즈니스 로직:
  run_parse_article()          ~30줄   단건 파싱
  run_parse_batch()            ~50줄   배치 파싱
  run_auto_parse()             ~70줄   자동 파싱+승인
  run_bulk_approve()           ~50줄   일괄 승인
  run_validate_master()        ~35줄   마스터 검증
  run_reparse_master()         ~25줄   리파싱 시작
합계: ~280줄
```

**import 구조:**
```python
# services/rule_gen_svc.py
from db.supabase_client import get_supabase
from services.rule_gen_helpers import _extract_json_payload, _validate_rule_row, _safe_float, _safe_int
from services.rule_gen_builders import _build_master_payload, _build_draft_row, _build_reparse_prompt
from services.rule_gen_ai import call_claude, _fetch_few_shot_examples
# FastAPI import 금지!
```

### 3-3. 확인

```bash
uvicorn main:app --reload
# 주요 엔드포인트 확인
curl -s https://api.taieng.co.kr/law-rule-generator/stats | python -m json.tool
curl -s "https://api.taieng.co.kr/law-rule-generator/reparse-master/jobs?limit=2" | python -m json.tool
```

**STEP 3 완료 기준:**
- [ ] `services/rule_gen_ai.py` (~48줄)
- [ ] `services/rule_gen_svc.py` (~280줄)
- [ ] 라우터 크기: ~38KB → **약 10KB**

---

## STEP 4: 라우터 슬림화

### 4-1. 각 엔드포인트 5~10줄로 축소

**After (목표):**
```python
@router.post("/parse")
async def parse_article(req: ParseArticleRequest):
    result = await rule_gen_svc.run_parse_article(req)
    return {"status": "success", "data": result}

@router.post("/reparse-master")
async def reparse_master(req: ReparseMasterRequest, background_tasks: BackgroundTasks):
    return rule_gen_svc.run_reparse_master(req, background_tasks)
```

### 4-2. 확인

```bash
uvicorn main:app --reload
wc -l routers/law_rule_generator.py  # 200줄 이내 확인
```

**STEP 4 완료 기준:**
- [ ] `routers/law_rule_generator.py` **200줄(7KB) 이내**
- [ ] 16개 엔드포인트 전부 서비스 호출만
- [ ] 서버 정상 실행

---

## STEP 5: 테스트 작성

### 5-1. `tests/test_rule_gen_helpers.py`

```python
from services.rule_gen_helpers import _safe_float, _safe_int, _to_bool, _validate_rule_row

def test_safe_float():
    assert _safe_float("3.14") == 3.14
    assert _safe_float("abc") == 0.0
    assert _safe_float(None) == 0.0

def test_to_bool():
    assert _to_bool("true") == True
    assert _to_bool("false") == False
    assert _to_bool(None) == False

def test_validate_rule_row():
    # 유효한 룰 → 통과
    valid = {"obligation_type": "INSPECT", "sector": "BUILDING", ...}
    assert _validate_rule_row(valid) == True
    # 필수 필드 누락 → 실패
    invalid = {"obligation_type": "INSPECT"}
    assert _validate_rule_row(invalid) == False
```

### 5-2. `tests/test_rule_gen_builders.py`

```python
from services.rule_gen_builders import _build_master_payload

def test_build_master_payload():
    draft = {"law_name": "산업안전보건법", ...}
    payload = _build_master_payload(draft)
    assert "rule_id" in payload
    assert "sector" in payload
```

### 5-3. 실행

```bash
pytest tests/test_rule_gen_helpers.py tests/test_rule_gen_builders.py -v
```

**STEP 5 완료 기준:**
- [ ] `tests/test_rule_gen_helpers.py`
- [ ] `tests/test_rule_gen_builders.py`
- [ ] pytest 통과

---

## 최종 파일 구조

```
Before (1개 파일):
  routers/law_rule_generator.py       46KB  1291줄  32함수

After (7개 파일):
  routers/law_rule_generator.py       ~7KB   ~200줄  16엔드포인트 (각 5~10줄)
  services/rule_gen_helpers.py        ~3KB    ~84줄   순수 유틸 7함수
  services/rule_gen_builders.py       ~4KB   ~107줄   빌더 4함수
  services/rule_gen_ai.py             ~2KB    ~48줄   AI 호출 3함수
  services/rule_gen_svc.py           ~10KB   ~280줄   핵심 비즈니스 로직
  schemas/rule_gen.py                 ~3KB   ~100줄   Pydantic 모델
  tests/test_rule_gen_helpers.py      ~2KB    ~50줄
  tests/test_rule_gen_builders.py     ~2KB    ~50줄
```

**가장 큰 파일 10KB. 모두 15KB 이내.**

---

## 추가: 58건 reparse 에러 수정

분리 완료 후, `services/rule_gen_svc.py`에서 아래 버그를 수정:

### 버그 1: UUID 타입 에러 (40건)
`updated_by` 필드에 "system"/"SYSTEM" 문자열 → NULL로 변경
```python
# Before
payload["updated_by"] = "system"
# After
payload["updated_by"] = None  # UUID 컬럼이므로 문자열 불가
```

### 버그 2: Numeric 타입 에러 (17건)
AI가 `condition_value`에 문자열 생성 → 숫자 검증 추가
```python
# _build_master_payload() 또는 저장 직전에:
if payload.get("condition_value") is not None:
    try:
        payload["condition_value"] = float(payload["condition_value"])
    except (ValueError, TypeError):
        payload["condition_value"] = None  # 숫자 아니면 NULL
```

### 버그 3: varchar(30) 초과 (1건)
문자열 길이 truncate 추가

---

## 커밋

```bash
git add .
git commit -m "refactor: law_rule_generator.py 서비스 계층 분리 (46KB→7파일) + reparse 버그 수정"
git push origin main
```

---

## 절대 주의사항

1. **한 번에 전부 하지 말 것** — 단계별 진행, 매 단계 서버 확인
2. **외부 import 없음** — 호환 래퍼 불필요 (legal_engine보다 간단)
3. **BackgroundTasks 주의** — reparse_master는 FastAPI BackgroundTasks 사용. 이것은 라우터에 남겨야 함
4. **Anthropic API 키** — AI 함수에서 환경변수 참조. services/rule_gen_ai.py에서 os.environ 사용
5. **커밋은 단계별** — STEP마다 별도 커밋

---

## [TAI 개발 규칙 — 서비스 계층 분리]
문서: docs/DEV_RULES_SERVICE_LAYER.md

5단계 분리:
  STEP 1: 패키지 생성 + 헬퍼 분리
  STEP 2: 스키마 분리
  STEP 3: 서비스 분리
  STEP 4: 라우터 슬림화
  STEP 5: 테스트 작성

절대 하지 말 것:
- 라우터에서 직접 SQL 실행 (services에서만)
- 서비스에서 Request/Response 객체 사용
- 한 파일에 400줄 이상 작성
- 20KB 이상 파일을 통째로 덮어쓰기
