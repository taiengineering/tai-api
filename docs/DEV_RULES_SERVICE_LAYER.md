# TAI 개발 규칙 — 서비스 계층 분리

> 작성일: 2026-04-21
> 상태: **필수 적용** (모든 개발 창에서 준수)
> 적용 시점: 20KB 이상 라우터 파일을 수정할 때 선행 적용. 신규 파일은 처음부터 적용.

---

## 핵심 원칙

```
"한 파일에 모든 것을 넣지 않는다."
"수정할 때마다 분리한다."
"새로 만들 때는 처음부터 분리한다."
```

---

## 계층 구조

| 계층 | 역할 | 규칙 |
|---|---|---|
| **Router** | HTTP 받고 → 서비스 호출 → 응답 반환 | if문/SQL 금지. 서비스 호출만 |
| **Service** | 비즈니스 로직 집중 | HTTP를 모름. 순수 함수 위주. `from fastapi import` 금지 |
| **Schema** | Pydantic으로 입력/출력 검증 | 필드별 자동 검증. if문 불필요 |
| **Tests** | 서비스 함수 단위 테스트 | 수정 후 pytest로 깨짐 확인 |

---

## 디렉토리 구조

```
tai-api/
├── routers/           # HTTP 엔드포인트 (얇게)
│   └── legal_engine.py
├── services/          # 비즈니스 로직
│   ├── __init__.py
│   ├── legal_helpers.py       # 순수 헬퍼 함수
│   ├── legal_context.py       # 입력→컨텍스트 변환
│   ├── legal_rules.py         # 조건코드 매칭·판정
│   ├── legal_engine_svc.py    # 핵심 진단 오케스트레이션
│   └── legal_format.py        # 결과 포맷팅·DB 저장형식
├── schemas/           # Pydantic 스키마
│   └── legal_engine.py
└── tests/             # 단위 테스트
    ├── test_legal_helpers.py
    ├── test_legal_rules.py
    └── test_legal_format.py
```

---

## 분리 실행 순서 (5단계)

**매 단계마다 API 응답이 동일해야 합니다. 중간에 멈춰도 안전합니다.**

### STEP 1. 패키지 생성 + 헬퍼 분리

가장 안전한 첫 걸음. 순수 함수를 먼저 빼면 아무것도 안 깨지면서 파일이 즉시 작아집니다.

```
services/__init__.py           ← 빈 파일 생성
services/legal_helpers.py      ← _to_float, _to_int, _now_iso 등 순수 유틸
services/legal_context.py      ← _survey_data_to_context, _factory_to_context 등
```

**기준**: DB 호출 없이 입력→출력만 하는 함수 = 헬퍼.
**확인**: 라우터에서 `from services.legal_helpers import ...` 으로 교체 후 API 응답 동일 확인.

### STEP 2. 스키마 분리

기계적 작업. 라우터에 인라인으로 있는 Pydantic 모델을 schemas/로 이동.

```
schemas/legal_engine.py        ← 모든 Request/Response 모델
```

**확인**: import 경로만 바뀜. API 응답 동일.

### STEP 3. 서비스 분리

핵심 분리. 라우터에 있는 비즈니스 로직(DB 호출 + 판정 로직)을 services/로 이동.

```
services/legal_engine_svc.py   ← apply, diagnose 오케스트레이션
services/legal_rules.py        ← _check_rule_conditions, 의무판정
services/legal_format.py       ← format_rule_result, format_rule_result_db
```

**기준**: `from fastapi import` 가 없으면 서비스로 이동 가능.
**확인**: 라우터가 서비스 호출만 하게 된 후 API 응답 동일.

### STEP 4. 라우터 슬림화

마지막 정리. 라우터에 남은 잔여 로직을 서비스로 이동하고, 각 엔드포인트를 5줄 이내로.

```python
# 최종 라우터 형태
@router.post("/apply/{factory_id}")
async def apply_legal_engine(factory_id: str, user=Depends(get_current_user)):
    result = await legal_engine_svc.apply(factory_id, user.id)
    return {"status": "success", "data": result}
```

**확인**: 라우터 파일이 15KB(400줄) 이내. API 응답 동일.

### STEP 5. 테스트 작성

서비스가 순수 함수로 분리되어야 테스트 작성이 가능합니다.

```
tests/test_legal_helpers.py    ← _to_float, _to_int 등 유틸 테스트
tests/test_legal_rules.py      ← 조건코드 매칭 단위 테스트
tests/test_legal_format.py     ← 결과 포맷 테스트
```

**테스트 대상**: Service 함수만. Router는 테스트하지 않음 (통합 테스트는 별도).
**실행**: `pytest tests/test_legal_rules.py -v`
**확인**: 모든 테스트 통과 후 수정 완료.

---

## 적용 규칙

### 기존 파일 수정 시

```
파일 크기 < 20KB  → 기존 구조 유지 (분리 불필요)
파일 크기 >= 20KB → 5단계 분리를 선행한 후 수정
```

### 신규 파일 생성 시

```
처음부터 Router / Service / Schema 분리하여 생성
```

### 파일 크기 제한

```
한 파일 최대 400줄 (약 15KB)
초과 시 반드시 분할
```

---

## Router 작성 규칙

```python
# ✅ 올바른 라우터
from services.legal_engine_svc import run_diagnosis
from schemas.legal_engine import DiagnosisRequest, DiagnosisResponse

@router.post("/diagnosis", response_model=DiagnosisResponse)
async def diagnose(req: DiagnosisRequest, user=Depends(get_current_user)):
    result = await run_diagnosis(req, user.id)
    return {"status": "success", "data": result}
```

```python
# ❌ 금지 — 라우터에서 직접 SQL 실행
@router.post("/diagnosis")
async def diagnose(req: Request):
    body = await req.json()
    supabase = get_supabase()
    result = supabase.table("rules").select("*").eq("facility_type", body["type"]).execute()
    # ... 200줄의 비즈니스 로직 ...
```

---

## Service 작성 규칙

```python
# ✅ 올바른 서비스
from db.supabase_client import get_supabase
from schemas.legal_engine import DiagnosisRequest

async def run_diagnosis(req: DiagnosisRequest, user_id: str) -> dict:
    """법령진단 실행. HTTP를 모름. 순수 비즈니스 로직."""
    rules = await fetch_matching_rules(req.facility_type, req.worker_count)
    penalties = calculate_penalties(rules)
    return {"rules": rules, "penalties": penalties}

def calculate_penalties(rules: list) -> int:
    """순수 함수 — DB 호출 없음, 테스트 가능"""
    return sum(r["penalty_amount"] for r in rules if r.get("penalty_amount"))
```

```python
# ❌ 금지 — 서비스에서 FastAPI 객체 사용
from fastapi import Request, Response  # 금지!
```

---

## 우선 분리 대상 (위험도 순)

| 순위 | 파일 | 크기 | 함수 수 | 트리거 |
|---|---|---|---|---|
| 1 | legal_engine.py | 77KB | 53개 | 법령엔진 수정 시 (선제 분리 결정) |
| 2 | construction.py | 58KB | — | 건설 로직 수정 시 |
| 3 | payment.py | 52KB | — | 정기결제 MID 추가 시 |
| 4 | law_rule_generator.py | 46KB | — | AI 파싱 수정 시 |
| 5 | matching.py | 42KB | — | 매칭 로직 수정 시 |
| 6 | inspection_sets.py | 38KB | — | 점검세트 수정 시 |

---

## Cursor 프롬프트 필수 포함 규칙

모든 Cursor 작업지시서에 아래를 포함:

```
[TAI 개발 규칙 — 서비스 계층 분리]
문서: docs/DEV_RULES_SERVICE_LAYER.md

이 파일이 20KB 이상이면 아래 5단계를 선행:
  STEP 1: 패키지 생성 + 헬퍼 분리 (services/__init__.py, *_helpers.py)
  STEP 2: 스키마 분리 (schemas/*.py)
  STEP 3: 서비스 분리 (services/*_svc.py)
  STEP 4: 라우터 슬림화 (routers/*.py → 엔드포인트만)
  STEP 5: 테스트 작성 (tests/test_*.py)

매 단계마다 API 응답이 동일한지 확인.
중간에 멈춰도 안전해야 함.

이 파일이 20KB 미만이면:
- 신규 코드가 추가되어 20KB를 초과할 경우 분리 적용
- 단순 버그 수정은 기존 구조 유지 가능

절대 하지 말 것:
- 라우터에서 직접 SQL 실행 (services에서만)
- 서비스에서 Request/Response 객체 사용
- 한 파일에 400줄 이상 작성
- 20KB 이상 파일을 통째로 덮어쓰기
```

---

## 이 규칙이 해결하는 것

| 현재 문제 | 해결 |
|---|---|
| 77KB 파일을 통째로 덮어씀 | 5KB 서비스 파일만 수정 |
| 한 줄 고치면 다른 곳 깨짐 | 함수가 독립적 → 영향 범위 제한 |
| 에러 원인을 모름 | 테스트가 즉시 알려줌 |
| 검증 누락 | Pydantic 스키마가 자동 검증 |
| 엔진 수정이 두려움 | 계산 함수만 테스트하고 수정 가능 |
