# TAI 개발 규칙 — 서비스 계층 분리

> 작성일: 2026-04-21
> 최종 수정: 2026-04-26 (v4 — 분리 대상 6건 전부 완료)
> 상태: **필수 적용** (모든 개발 창에서 준수)
> 적용 시점: 20KB 이상 라우터 파일을 수정할 때 선행 적용. 신규 파일은 처음부터 적용.

---

## 핵심 원칙

```
1. "테스트가 먼저다."
   → 분리 전에 현재 동작을 테스트로 기록한다.
   → 테스트가 없으면 뭐가 깨졌는지 모른다.
   → 테스트가 통과하면 분리가 정확한 것이다.

2. "한 파일 = 한 가지 책임"
   → 파일 크기는 신호등일 뿐. 진짜 기준은 책임 분리.
   → HTTP 처리 / 비즈니스 로직 / 검증 / AI 호출은 각각 다른 파일.

3. "수정할 때마다 분리한다."
   → 새로 만들 때는 처음부터 분리한다.
```

---

## 왜 분리하는가

파일 크기를 줄이는 건 수단이다. 실제 목적:

| 분리 기준 | 효과 |
|---|---|
| HTTP ↔ 비즈니스 로직 | API 경로 바꿔도 로직 안 깨짐 |
| AI 호출 ↔ 데이터 가공 | 모델 교체해도 나머지 안 바뀜 |
| 검증 ↔ 실행 | 검증 규칙만 독립 테스트 가능 |
| 프롬프트 ↔ 로직 | 프롬프트 수정이 코드 변경 아님 |

**그리고 이 모든 것의 전제는 테스트.**
테스트 없이 분리하면 코드 정리일 뿐, 안전성은 0이다.

---

## 계층 구조

| 계층 | 역할 | 규칙 |
|---|---|---|
| **Tests** | 현재 동작 기록 + 변경 시 깨짐 감지 | **가장 먼저 작성. 분리의 전제조건.** |
| **Router** | HTTP 받고 → 서비스 호출 → 응답 반환 | if문/SQL 금지. 서비스 호출만 |
| **Service** | 비즈니스 로직 집중 | HTTP를 모름. 순수 함수 위주. `from fastapi import` 금지 |
| **Schema** | Pydantic으로 입력/출력 검증 | 필드별 자동 검증. if문 불필요 |

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

## 분리 실행 순서 (6단계)

**STEP 0이 가장 중요합니다. 테스트 없이 STEP 1로 넘어가지 마세요.**

### STEP 0. 테스트 먼저 작성 (필수 — 분리의 전제조건)

분리하기 **전에** 현재 코드의 동작을 테스트로 기록합니다.

```
tests/test_{모듈}_current.py  ← 현재 동작 스냅샷
```

**작성 대상:**
- 핵심 비즈니스 함수의 입출력 (실제 DB 없이 mock 가능한 것)
- 헬퍼/유틸 함수의 순수 테스트
- 주요 엔드포인트의 응답 구조 (HTTP 200 + 필수 필드)

**기준:** 최소 5개 테스트. 분리 전에 `pytest tests/test_{모듈}_current.py -v` 전부 PASS.

### STEP 1. 패키지 생성 + 헬퍼 분리

가장 안전한 첫 걸음. 순수 함수를 먼저 빼면 아무것도 안 깨지면서 파일이 즉시 작아집니다.

```
services/{module}_helpers.py   ← 순수 유틸 함수
```

### STEP 2. 스키마 분리

기계적 작업. 라우터에 인라인으로 있는 Pydantic 모델을 schemas/로 이동.

```
schemas/{module}.py            ← 모든 Request/Response 모델
```

### STEP 3. 서비스 분리

핵심 분리. 라우터에 있는 비즈니스 로직을 services/로 이동.

```
services/{module}_svc.py       ← 핵심 비즈니스 로직
```

### STEP 4. 라우터 슬림화

라우터에 남은 잔여 로직을 서비스로 이동하고, 각 엔드포인트를 5줄 이내로.

**확인**: 라우터 파일이 15KB(400줄) 이내.

### STEP 5. 테스트 보강

분리된 서비스별 세분화 테스트 추가.

---

## 적용 규칙

### 기존 파일 수정 시

```
파일 크기 < 20KB  → 기존 구조 유지 (분리 불필요)
파일 크기 >= 20KB → STEP 0(테스트)부터 시작하여 분리 선행 후 수정
```

### 신규 파일 생성 시

```
처음부터 Router / Service / Schema / Tests 분리하여 생성
```

### 파일 크기 제한

```
한 파일 최대 400줄 (약 15KB)
초과 시 반드시 분할
```

---

## Router / Service 작성 규칙

```python
# ✅ 올바른 라우터 — 서비스 호출만
@router.post("/diagnosis", response_model=DiagnosisResponse)
async def diagnose(req: DiagnosisRequest, user=Depends(get_current_user)):
    result = await run_diagnosis(req, user.id)
    return {"status": "success", "data": result}
```

```python
# ✅ 올바른 서비스 — HTTP를 모름
async def run_diagnosis(req: DiagnosisRequest, user_id: str) -> dict:
    rules = await fetch_matching_rules(req.facility_type, req.worker_count)
    penalties = calculate_penalties(rules)
    return {"rules": rules, "penalties": penalties}
```

```python
# ❌ 금지 — 라우터에서 직접 SQL
# ❌ 금지 — 서비스에서 from fastapi import
```

---

## 분리 대상 현황 — ✅ 전부 완료

| 순위 | 파일 | 원본 → 현재 | 완료일 | 테스트 |
|---|---|---|---|---|
| ~~1~~ | ~~legal_engine.py~~ | 77KB → 5KB | 완료 | ✅ 6개 |
| ~~2~~ | ~~law_rule_generator.py~~ | 46KB → 16KB | 완료 | ✅ 2개 |
| ~~3~~ | ~~construction.py~~ | 58KB → 1.8KB | 완료 | — |
| ~~4~~ | ~~payment.py~~ | 72KB → 12KB | 2026-04-26 | ✅ 16개 |
| ~~5~~ | ~~matching.py~~ | 42KB → 5.3KB | 2026-04-26 | ✅ 11개 |
| ~~6~~ | ~~inspection_sets.py~~ | 38KB → 3.2KB | 2026-04-26 | ✅ 11개 |

**총 축소: 333KB → 43KB (87% 감소), 테스트 46개 추가**

### 추가 20KB 초과 파일 (수정 시 분리 필요)

| 파일 | 크기 | 비고 |
|---|---|---|
| payment_billing.py | 31KB | payment와 연관 |
| education.py | 29KB | |
| auth.py | 27KB | |
| companies.py | 27KB | |
| inspection_checklist.py | 26KB | |
| contracts.py | 25KB | |
| report_forms.py | 25KB | |
| personnel.py | 25KB | |
| inspection_schedule.py | 23KB | |

---

## Cursor / Claude Code 작업지시서 필수 포함 규칙

모든 작업지시서에 아래를 포함:

```
[TAI 개발 규칙 — 서비스 계층 분리]
문서: docs/DEV_RULES_SERVICE_LAYER.md

이 파일이 20KB 이상이면 아래 6단계를 선행:
  STEP 0: 테스트 먼저 작성 (현재 동작 기록, 최소 5개, 전부 PASS 확인)
  STEP 1: 패키지 생성 + 헬퍼 분리
  STEP 2: 스키마 분리
  STEP 3: 서비스 분리
  STEP 4: 라우터 슬림화
  STEP 5: 테스트 보강

★ STEP 0 없이 STEP 1로 넘어가지 말 것!
★ 매 단계마다 기존 테스트 PASS + API 응답 동일 확인!
```

---

## 이 규칙이 해결하는 것

| 현재 문제 | 해결 |
|---|---|
| 77KB 파일을 통째로 덮어씀 | 5KB 서비스 파일만 수정 |
| 한 줄 고치면 다른 곳 깨짐 | 테스트가 즉시 깨짐을 알려줌 |
| 에러 원인을 모름 | 단위 테스트가 어디서 깨졌는지 특정 |
| 분리했는데 뭐가 달라졌는지 모름 | STEP 0 테스트가 변경 전 동작을 보장 |
| 검증 누락 | Pydantic 스키마가 자동 검증 |
| 엔진 수정이 두려움 | 계산 함수만 테스트하고 수정 가능 |
