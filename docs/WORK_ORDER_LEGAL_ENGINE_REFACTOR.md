# 작업지시서: legal_engine.py 서비스 계층 분리

> 대상: `routers/legal_engine.py` (77KB, 1313줄, 53함수, 12엔드포인트)
> 기준 규칙: `docs/DEV_RULES_SERVICE_LAYER.md`
> 브랜치: `dev`
> 작업 도구: **Cursor** (77KB 파일이므로 MCP 금지)
> 핵심 원칙: **매 단계 후 서버 실행 → 기존 API 응답 동일 확인**

---

## 사전 준비

```bash
git fetch origin
git checkout origin/dev
git checkout -b refactor/legal-engine-service-layer
```

디렉토리 생성:
```bash
mkdir -p services schemas tests
touch services/__init__.py
touch schemas/__init__.py
touch tests/__init__.py
```

---

## STEP 1: 패키지 생성 + 헬퍼 분리

### 1-1. `services/legal_helpers.py` 생성

`routers/legal_engine.py`에서 아래 8개 순수 유틸 함수를 **잘라내어** 이동:

```
함수명                              줄수   설명
─────────────────────────────────────────────────
_to_float()                         7줄    문자열→float 안전 변환
_to_int()                           7줄    문자열→int 안전 변환
_now_iso()                          3줄    현재시각 ISO 문자열
_parse_survey_data()                8줄    설문 JSON 파싱
_normalize_target_code()            4줄    타겟코드 정규화
get_sector_groups()                 9줄    섹터별 그룹 목록
get_effective_worker_count()        8줄    유효 근로자 수 계산
get_construction_amount_threshold() 3줄    건설 공사금액 임계값
─────────────────────────────────────────────────
합계: ~49줄
```

**작업 방법:**
1. `services/legal_helpers.py` 파일 생성
2. 위 8개 함수를 복사
3. 필요한 import만 추가 (typing 등)
4. `routers/legal_engine.py`에서 해당 함수 삭제
5. `routers/legal_engine.py` 상단에 추가:
   ```python
   from services.legal_helpers import (
       _to_float, _to_int, _now_iso, _parse_survey_data,
       _normalize_target_code, get_sector_groups,
       get_effective_worker_count, get_construction_amount_threshold
   )
   ```

### 1-2. `services/legal_context.py` 생성

입력 데이터를 법령엔진 판정용 컨텍스트로 변환하는 함수 3개:

```
함수명                        줄수   설명
─────────────────────────────────────────
_survey_data_to_context()     34줄   설문→컨텍스트
_factory_to_context()         33줄   시설정보→컨텍스트
_input_to_facility_context()  78줄   통합입력→컨텍스트
─────────────────────────────────────────
합계: ~145줄
```

**주의:** 이 함수들은 `legal_helpers`의 함수를 호출함.
```python
from services.legal_helpers import (
    _to_float, _to_int, _parse_survey_data,
    get_sector_groups, get_effective_worker_count,
    get_construction_amount_threshold
)
```

### 1-3. 확인

```bash
# 서버 실행
uvicorn main:app --reload

# 기존 API 테스트 (curl 또는 브라우저)
curl -s https://api.taieng.co.kr/health | python -m json.tool
# 주요 엔드포인트 몇 개 호출하여 응답 동일 확인
```

**STEP 1 완료 기준:**
- [ ] `services/legal_helpers.py` 생성 (8함수, ~49줄)
- [ ] `services/legal_context.py` 생성 (3함수, ~145줄)
- [ ] `routers/legal_engine.py`에서 11개 함수 삭제 + import 교체
- [ ] 서버 정상 실행
- [ ] `routers/legal_engine.py` 크기: 77KB → **약 70KB** (7KB 감소)

---

## STEP 2: 스키마 분리

### 2-1. `schemas/legal_engine.py` 생성

`routers/legal_engine.py` 안에 인라인으로 정의된 Pydantic 모델을 추출.
현재 엔드포인트의 요청/응답 형태를 분석하여 스키마화:

```python
# schemas/legal_engine.py
from pydantic import BaseModel, Field
from typing import Optional, List

class DiagnoseStep1Request(BaseModel):
    facility_type: str = Field(..., description="BUILDING/INDUSTRY/CONSTRUCTION")
    worker_count: int = Field(0, ge=0)
    area_sqm: Optional[float] = Field(None, ge=0)
    # ... 기존 diagnose_step1 엔드포인트가 받는 필드 전부

class DiagnoseStep2Request(BaseModel):
    diagnosis_id: str
    equipment_ids: List[str] = []

class DiagnoseStep3Request(BaseModel):
    diagnosis_id: str
    process_ids: List[str] = []

class LegalEngineResponse(BaseModel):
    status: str
    data: dict
```

**작업 방법:**
1. 각 엔드포인트의 `req: Request` → `await req.json()` 패턴을 찾기
2. body에서 꺼내는 필드를 Pydantic 모델로 변환
3. 엔드포인트에서 `req: DiagnoseStep1Request` 형태로 교체
4. 기존 `body["field"]` → `req.field` 로 교체

**주의:** 기존에 `Request` 객체를 직접 사용하는 엔드포인트가 있으면,
`body = await req.json()` 패턴을 Pydantic 모델로 전환.

### 2-2. 확인

```bash
uvicorn main:app --reload
# 동일 API 호출 → 동일 응답
```

**STEP 2 완료 기준:**
- [ ] `schemas/legal_engine.py` 생성
- [ ] 모든 엔드포인트가 Pydantic 모델 사용
- [ ] `req: Request` + `await req.json()` 패턴 제거
- [ ] 서버 정상 실행
- [ ] `routers/legal_engine.py` 크기: ~70KB → **약 67KB** (3KB 감소)

---

## STEP 3: 서비스 분리

### 3-1. `services/legal_rules.py` 생성

법령 조건코드 매칭·판정 로직 (핵심 중의 핵심):

```
함수명                        줄수   설명
─────────────────────────────────────────
_check_rule_conditions()      25줄   조건코드 매칭 판정
_resolve_obligation_type()    10줄   의무 유형 결정
_is_notify()                   3줄   신고 의무 여부
_is_report()                   5줄   보고 의무 여부
─────────────────────────────────────────
합계: ~43줄
```

이 파일은 **DB 호출 없음, 순수 판정 로직**이므로 테스트 작성이 가장 쉬움.

### 3-2. `services/legal_format.py` 생성

결과 포맷팅·분류·DB 저장 형식 변환:

```
함수명                            줄수   설명
──────────────────────────────────────────────
format_rule_result()              17줄   단일 규칙 결과 포맷
format_rule_result_db()           74줄   DB 저장용 포맷
_get_inspection_cycle_label()     37줄   점검주기 라벨
_get_schedule_type()               6줄   일정 유형
_get_appointment_target_label()    4줄   선임 대상 라벨
_calc_due_date()                   7줄   마감일 계산
_get_penalty_fallback()           19줄   과태료 폴백
_classify_rules()                  3줄   규칙 분류
_classify_rules_with_source()      3줄   출처별 분류
_classify_one()                    7줄   단일 분류
_classify_rules_db()              26줄   DB용 분류
──────────────────────────────────────────────
합계: ~200줄+
```

### 3-3. `services/legal_engine_svc.py` 생성

핵심 오케스트레이션 (DB 호출 포함):

```
함수명                                줄수   설명
──────────────────────────────────────────────────
_evaluate_equipment_conditions()      16줄   설비 조건 DB 평가
_evaluate_process_conditions()        15줄   공정 조건 DB 평가
_save_diagnosis_result()              12줄   진단 결과 DB 저장
_create_report_events_from_rules()    12줄   신고 이벤트 생성

+ 엔드포인트에서 추출할 핵심 비즈니스 로직:
  apply_engine_logic()               ~40줄   법령엔진 적용 핵심
  run_diagnose_step1()              ~100줄   진단 1단계 핵심
  run_diagnose_step2()               ~30줄   진단 2단계 핵심
  run_diagnose_step3()               ~30줄   진단 3단계 핵심
──────────────────────────────────────────────────
합계: ~250줄
```

**import 구조:**
```python
# services/legal_engine_svc.py
from db.supabase_client import get_supabase
from services.legal_helpers import _now_iso, _to_float, _to_int
from services.legal_context import _input_to_facility_context, _factory_to_context
from services.legal_rules import _check_rule_conditions, _resolve_obligation_type
from services.legal_format import format_rule_result_db, _classify_rules_db
# FastAPI import 금지!
```

### 3-4. 확인

```bash
uvicorn main:app --reload
# 전체 12개 엔드포인트 응답 동일 확인
```

**STEP 3 완료 기준:**
- [ ] `services/legal_rules.py` 생성 (~43줄)
- [ ] `services/legal_format.py` 생성 (~200줄)
- [ ] `services/legal_engine_svc.py` 생성 (~250줄)
- [ ] 서버 정상 실행
- [ ] `routers/legal_engine.py` 크기: ~67KB → **약 20KB**

---

## STEP 4: 라우터 슬림화

### 4-1. 각 엔드포인트를 5~10줄로 축소

**Before (현재):**
```python
@router.post("/apply/{factory_id}")
async def apply_legal_engine(factory_id: str, request: Request, ...):
    body = await request.json()
    supabase = get_supabase()
    factory = supabase.table("factories").select(...).execute()
    # ... 47줄의 로직 ...
    return {"status": "success", "data": result}
```

**After (목표):**
```python
@router.post("/apply/{factory_id}")
async def apply_legal_engine(factory_id: str, user=Depends(get_current_user)):
    result = await legal_engine_svc.apply_engine(factory_id, user.id)
    return {"status": "success", "data": result}
```

### 4-2. 최종 라우터 구조

```python
# routers/legal_engine.py (최종 ~150줄)
from fastapi import APIRouter, Depends
from auth.jwt_handler import get_current_user
from services import legal_engine_svc
from schemas.legal_engine import (
    DiagnoseStep1Request, DiagnoseStep2Request, DiagnoseStep3Request
)

router = APIRouter(prefix="/legal-engine", tags=["법령엔진"])

@router.post("/apply/{factory_id}")
async def apply_legal_engine(factory_id: str, user=Depends(get_current_user)):
    result = await legal_engine_svc.apply_engine(factory_id, user.id)
    return {"status": "success", "data": result}

@router.post("/diagnose/step1")
async def diagnose_step1(req: DiagnoseStep1Request, user=Depends(get_current_user)):
    result = await legal_engine_svc.run_diagnose_step1(req, user.id)
    return {"status": "success", "data": result}

# ... 나머지 10개 엔드포인트도 동일 패턴
```

### 4-3. 확인

```bash
uvicorn main:app --reload
# 전체 12개 엔드포인트 최종 확인
wc -l routers/legal_engine.py  # 150줄 이내 확인
```

**STEP 4 완료 기준:**
- [ ] `routers/legal_engine.py`가 **150줄(5KB) 이내**
- [ ] 모든 엔드포인트가 서비스 호출 → 응답 반환만
- [ ] SQL/비즈니스 로직이 라우터에 0줄
- [ ] 서버 정상 실행
- [ ] 12개 엔드포인트 전부 응답 동일

---

## STEP 5: 테스트 작성

### 5-1. `tests/test_legal_helpers.py`

```python
from services.legal_helpers import _to_float, _to_int, get_sector_groups

def test_to_float():
    assert _to_float("3.14") == 3.14
    assert _to_float("abc") == 0.0
    assert _to_float(None) == 0.0

def test_to_int():
    assert _to_int("42") == 42
    assert _to_int("abc") == 0

def test_get_sector_groups():
    groups = get_sector_groups("INDUSTRY")
    assert isinstance(groups, list)
    assert len(groups) > 0
```

### 5-2. `tests/test_legal_rules.py`

```python
from services.legal_rules import _check_rule_conditions

def test_check_rule_basic_match():
    """기본 조건 매칭 테스트"""
    rule = {"condition_codes": ["WC_GTE_50"]}
    context = {"worker_count": 60}
    assert _check_rule_conditions(rule, context) == True

def test_check_rule_no_match():
    rule = {"condition_codes": ["WC_GTE_50"]}
    context = {"worker_count": 30}
    assert _check_rule_conditions(rule, context) == False

def test_resolve_obligation_type():
    # 의무 유형 판정 테스트
    ...
```

### 5-3. `tests/test_legal_format.py`

```python
from services.legal_format import format_rule_result, _calc_due_date

def test_format_rule_result():
    rule = {"law_name": "산업안전보건법", ...}
    result = format_rule_result(rule)
    assert "law_name" in result

def test_calc_due_date():
    # 마감일 계산 테스트
    ...
```

### 5-4. 실행

```bash
pip install pytest --break-system-packages
pytest tests/test_legal_helpers.py tests/test_legal_rules.py tests/test_legal_format.py -v
```

**STEP 5 완료 기준:**
- [ ] `tests/test_legal_helpers.py` — 유틸 함수 테스트
- [ ] `tests/test_legal_rules.py` — 조건 매칭 테스트 (가장 중요)
- [ ] `tests/test_legal_format.py` — 포맷 테스트
- [ ] `pytest` 전체 통과

---

## 최종 파일 구조

```
Before (1개 파일):
  routers/legal_engine.py          77KB  1313줄  53함수

After (8개 파일):
  routers/legal_engine.py          ~5KB   ~150줄  12엔드포인트(각 5줄)
  services/__init__.py              0KB
  services/legal_helpers.py        ~2KB    ~49줄   순수 유틸 8함수
  services/legal_context.py        ~5KB   ~145줄   컨텍스트 변환 3함수
  services/legal_rules.py          ~2KB    ~43줄   조건 매칭 4함수
  services/legal_format.py         ~7KB   ~200줄   포맷팅 11함수
  services/legal_engine_svc.py     ~9KB   ~250줄   핵심 오케스트레이션
  schemas/legal_engine.py          ~3KB   ~100줄   Pydantic 모델
  tests/test_legal_helpers.py      ~2KB    ~50줄
  tests/test_legal_rules.py        ~3KB    ~80줄
  tests/test_legal_format.py       ~2KB    ~50줄
```

**가장 큰 파일이 9KB (legal_engine_svc.py). 모두 15KB 이내.**

---

## PR 생성

5단계 모두 완료 후:

```bash
git add .
git commit -m "refactor: legal_engine.py 서비스 계층 분리 (77KB→8파일)"
git push origin refactor/legal-engine-service-layer
```

PR 제목: `refactor: legal_engine.py 서비스 계층 분리`
PR 설명: 5단계 분리 완료. 모든 API 응답 동일 확인.

---

## 절대 주의사항

1. **한 번에 전부 하지 말 것** — 반드시 단계별로 진행, 매 단계 서버 확인
2. **import 순환 주의** — services/ 파일 간 순환 import 발생 시 helpers를 별도 유틸로
3. **main.py 수정 불필요** — 라우터 등록은 그대로, 내부 구조만 변경
4. **기존 함수 시그니처 유지** — 다른 라우터에서 이 함수를 호출하는 곳이 있으면 import 경로만 변경
5. **커밋은 단계별** — STEP마다 별도 커밋하면 롤백이 쉬움
