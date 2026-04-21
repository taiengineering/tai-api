# TAI 개발 규칙 — 서비스 계층 분리

> 작성일: 2026-04-21
> 상태: **필수 적용** (모든 개발 창에서 준수)
> 적용 시점: 20KB 이상 라우터 파일을 수정할 때 선행 적용

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
│   └── legal_engine.py    # 5KB 이내
├── services/          # 비즈니스 로직
│   ├── legal_engine_svc.py
│   └── legal_calc.py      # 순수 계산 함수
├── schemas/           # Pydantic 스키마
│   └── legal_engine.py
└── tests/             # 단위 테스트
    └── test_legal_calc.py
```

---

## 적용 규칙

### 1. 기존 파일 수정 시

```
파일 크기 < 20KB → 기존 구조 유지 (분리 불필요)
파일 크기 >= 20KB → 서비스 분리를 선행한 후 수정
```

**분리 순서:**
1. `schemas/xxx.py` 생성 — Pydantic 입출력 모델 이동
2. `services/xxx_svc.py` 생성 — 비즈니스 로직 이동
3. `routers/xxx.py` 수정 — 서비스 호출만 남기기
4. `tests/test_xxx.py` 생성 — 서비스 함수 테스트
5. 기존 API 응답이 동일한지 확인

### 2. 신규 파일 생성 시

```
처음부터 Router / Service / Schema 분리하여 생성
```

### 3. 파일 크기 제한

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

## Schema 작성 규칙

```python
from pydantic import BaseModel, Field
from typing import Optional

class DiagnosisRequest(BaseModel):
    facility_type: str = Field(..., description="시설 유형: BUILDING/INDUSTRY/CONSTRUCTION")
    worker_count: int = Field(..., ge=1, description="상시 근로자 수")
    area_sqm: Optional[float] = Field(None, ge=0, description="연면적 (㎡)")

class DiagnosisResponse(BaseModel):
    rules_count: int
    penalty_sum: int
    rules: list
```

---

## 우선 분리 대상 (위험도 순)

| 순위 | 파일 | 크기 | 트리거 |
|---|---|---|---|
| 1 | legal_engine.py | 77KB | 법령엔진 수정 시 |
| 2 | construction.py | 58KB | 건설 로직 수정 시 |
| 3 | payment.py | 52KB | 정기결제 MID 추가 시 |
| 4 | law_rule_generator.py | 46KB | AI 파싱 수정 시 |
| 5 | matching.py | 42KB | 매칭 로직 수정 시 |
| 6 | inspection_sets.py | 38KB | 점검세트 수정 시 |

---

## Cursor 프롬프트 필수 포함 규칙

모든 Cursor 작업지시서에 아래를 포함:

```
[TAI 개발 규칙 — 서비스 계층 분리]

이 파일이 20KB 이상이면:
1. services/ 디렉토리에 서비스 파일을 먼저 생성
2. 비즈니스 로직을 서비스로 이동
3. 라우터는 HTTP 받고 → 서비스 호출 → 응답 반환만
4. schemas/ 디렉토리에 Pydantic 스키마 분리
5. 수정 후 기존 API 응답이 동일한지 확인

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
| 51KB 파일을 통째로 덮어씀 | 5KB 서비스 파일만 수정 |
| 한 줄 고치면 다른 곳 깨짐 | 함수가 독립적 → 영향 범위 제한 |
| 에러 원인을 모름 | 테스트가 즉시 알려줌 |
| 검증 누락 | Pydantic 스키마가 자동 검증 |
| 엔진 수정이 두려움 | 계산 함수만 테스트하고 수정 가능 |
