# matching.py 서비스 레이어 분리 — Cursor 작업지시서

> 대상: `routers/matching.py` (42KB, ~1,000줄)
> 규칙: `docs/DEV_RULES_SERVICE_LAYER.md` 필수 준수
> 브랜치: `dev` (main 직접 push 금지)
> 목표: 42KB → 라우터 15KB 이내

---

## 현재 구조 분석

| 영역 | 줄수(약) | 내용 |
|------|----------|------|
| 상수 | ~20줄 | `STATUS_TRANSITIONS`, `STATUS_TIMESTAMP_MAP` |
| 유틸 | ~40줄 | `_now_iso()`, `_require_admin()`, `calc_commission()` |
| Pydantic 모델 | ~80줄 | 6개 |
| 매칭 신청 CRUD | ~250줄 | 6개 엔드포인트 |
| 제안서 시스템 | ~300줄 | 7개 엔드포인트 |
| 어드민 대시보드 | ~100줄 | 2개 엔드포인트 |
| commission_router | ~130줄 | CRUD + calculate (별도 APIRouter이지만 같은 파일) |

---

## 분리 계획

### 파일 1: `schemas/matching.py` (신규, ~80줄)

기계적 이동:
```
MatchingRequestBody
StatusUpdateBody
MatchResultCreateBody
ProposalBody
CommissionBody
CalcBody
```

### 파일 2: `services/matching_helpers.py` (신규, ~60줄)

순수 데이터 + 유틸:
```
STATUS_TRANSITIONS
STATUS_TIMESTAMP_MAP
now_iso()
```

### 파일 3: `services/matching_svc.py` (신규, ~300줄)

비즈니스 로직. `from fastapi import` 금지:
```
create_matching_request(body, user_id) -> dict
update_request_status(request_id, new_status, user_id, memo) -> dict
create_match_result(body, admin_id) -> dict
notify_expert_for_result(result_id) -> None
mark_result_viewed(result_id, user_id) -> dict
submit_proposal_for_result(result_id, body, user_id) -> dict
select_expert_result(result_id, user_id, is_admin) -> dict
calc_commission(supabase, expert_type, amount, period_months) -> dict
get_dashboard_stats() -> dict
get_pipeline(expert_type, page, size) -> dict
```

### 파일 4: `routers/matching_commission.py` (신규, ~130줄)

`commission_router` 별도 파일로 분리.
main.py import 경로 변경:
```python
# 기존: from routers.matching import commission_router
# 변경: from routers.matching_commission import commission_router
```

### 파일 5: `routers/matching.py` (수정, ~200줄 목표)

HTTP만 담당.

---

## 실행 순서

### STEP 0: 테스트 먼저 작성

파일: `tests/test_matching_current.py`

최소 5개:
1. `STATUS_TRANSITIONS` — RECEIVED→MATCHING 가능
2. `STATUS_TRANSITIONS` — RECEIVED→IN_PROGRESS 불가
3. `MatchingRequestBody` — expert_type 유효값
4. `MatchingRequestBody` — 잘못된 값 에러
5. `CommissionBody` — fee_rate 범위 검증
6. `calc_commission` — 기본 10% (mock)

```bash
pytest tests/test_matching_current.py -v  # 전부 PASS
```

### STEP 1: 스키마 분리

1. `schemas/matching.py` 생성
2. Pydantic 모델 6개 이동
3. import 변경
4. 테스트 PASS

### STEP 2: 헬퍼 분리

1. `services/matching_helpers.py` 생성
2. 상수 + `_now_iso()` 이동
3. import 변경
4. 테스트 PASS

### STEP 3: commission_router 분리

1. `routers/matching_commission.py` 생성
2. `commission_router` + 관련 코드 이동
3. `main.py` import 경로 변경
4. 테스트 PASS

### STEP 4: 서비스 분리

1. `services/matching_svc.py` 생성
2. DB 로직 → 서비스 함수
3. 라우터 슬림화
4. **15KB / 400줄 이내 확인**

### STEP 5: 테스트 보강

---

## 절대 하지 말 것

- 테스트 없이 분리 시작
- 라우터에서 직접 SQL 실행
- 서비스에서 `from fastapi import` 사용
- `_require_admin` Depends를 서비스로 옮기지 말 것 (FastAPI Depends는 라우터에서만)
- 한 파일 400줄 초과
- main push 금지
- API 응답 구조 변경

## 완료 기준

| 항목 | 기준 |
|------|------|
| `routers/matching.py` | 15KB 이내 |
| `routers/matching_commission.py` | 10KB 이내 |
| `services/matching_helpers.py` | 5KB 이내 |
| `services/matching_svc.py` | 15KB 이내 |
| `schemas/matching.py` | 5KB 이내 |
| 테스트 | 최소 10개 PASS |
| `main.py` | commission_router import 경로 변경 |
| 브랜치 | dev |

## 커밋 단위

```
1. feat: STEP 0 — matching 현재 동작 테스트 6+개
2. refactor: STEP 1 — schemas/matching.py 스키마 분리
3. refactor: STEP 2 — matching_helpers.py 상수+유틸 분리
4. refactor: STEP 3 — matching_commission.py 수수료 라우터 분리
5. refactor: STEP 4 — matching_svc.py 서비스 분리 + 라우터 슬림화
6. test: STEP 5 — matching 테스트 보강
```
