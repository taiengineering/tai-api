# payment.py 서비스 레이어 분리 — Cursor 작업지시서

> 대상: `routers/payment.py` (72KB, ~1,500줄)
> 규칙: `docs/DEV_RULES_SERVICE_LAYER.md` 필수 준수
> 브랜치: `dev` (main 직접 push 금지)
> 목표: 72KB → 라우터 15KB 이내 + 서비스·스키마·헬퍼·템플릿 분리

---

## 현재 구조 분석

| 영역 | 줄수(약) | 내용 |
|------|----------|------|
| 유틸 함수 | ~100줄 | `_sha256`, `_ts_ms`, `_make_order_id`, `_calc_expired_at`, `_load_sign_key`, `_load_mpriv_pem`, `_rsa_sign_sha256`, `_call_pay_auth` |
| 상수 | ~15줄 | `INICIS_MID`, `INICIS_KEY_PATH`, URL상수, `SAAS_PRODUCT_TYPES` |
| Pydantic 모델 | ~80줄 | `PrepareBody`, `VbankPrepareBody`, `DiagnosisVbankPrepareBody`, `ManualConfirmBody`, `CancelBody` |
| HTML 템플릿 | **~350줄** | `_PRICING_HTML`, `_RESULT_HTML`, `_BILLING_TERMS_HTML` — **파일의 절반** |
| 엔드포인트 | ~400줄 | 14개 엔드포인트 |

---

## 분리 계획 — 5개 파일 생성

### 파일 1: `schemas/payment.py` (신규, ~80줄)

기계적 이동, 로직 변경 없음:
```
PrepareBody
VbankPrepareBody
DiagnosisVbankPrepareBody
ManualConfirmBody
CancelBody
```

### 파일 2: `services/payment_helpers.py` (신규, ~120줄)

순수 함수 + 상수, DB 호출 없음:
```
# 상수
INICIS_MID, INICIS_KEY_PATH, INICIS_KEY_PASSWORD
DEFAULT_RETURN_URL, DEFAULT_CLOSE_URL, FRONT_RETURN_URL
SAAS_PRODUCT_TYPES

# 순수 함수
_sha256, _ts_ms, _make_order_id, _now_iso, _calc_expired_at
_load_sign_key, _load_mpriv_pem, _rsa_sign_sha256, _call_pay_auth

# 템플릿 로더
def load_template(name: str) -> str
```

### 파일 3: `services/payment_svc.py` (신규, ~250줄)

비즈니스 로직. `from fastapi import` 금지:
```
create_payment_record(body) -> dict
process_auth_return(data: dict) -> dict  # {"redirect_url": str}
process_server_noti(data: dict) -> str
create_vbank_record(body) -> dict
process_vbank_deposit(data: dict) -> str
confirm_payment_manual(body) -> dict
cancel_payment_record(payment_id, reason) -> dict
query_payments(filters) -> dict
query_expiring(days, page, size) -> dict
get_vbank_status_data(payment_id) -> dict
```

### 파일 4: `templates/payment/` (3개 HTML)

```
templates/payment/pricing.html        ← _PRICING_HTML
templates/payment/result.html         ← _RESULT_HTML
templates/payment/billing_terms.html  ← _BILLING_TERMS_HTML
```

### 파일 5: `routers/payment.py` (수정, ~150줄)

HTTP만 담당. 엔드포인트당 5줄 이내.

---

## 실행 순서 (DEV_RULES 6단계)

### STEP 0: 테스트 먼저 작성 (필수)

파일: `tests/test_payment_current.py`

최소 5개:
1. `_sha256` 순수 함수 테스트
2. `_make_order_id` 형식 검증 (TAI + 날짜 + 6자리)
3. `_calc_expired_at` 계산 정확성
4. `PrepareBody` validation (필수필드 누락 시 에러)
5. `VbankPrepareBody` validation (product_type 유효값)

확인: `pytest tests/test_payment_current.py -v` → 전부 PASS

### STEP 1: 헬퍼 분리

1. `services/payment_helpers.py` 생성
2. 상수 + 순수 함수 이동
3. `routers/payment.py`에서 import 변경
4. 테스트 PASS 확인

### STEP 2: 스키마 분리

1. `schemas/payment.py` 생성 (`schemas/` 디렉토리 없으면 `__init__.py`와 함께 생성)
2. Pydantic 모델 5개 이동
3. import 변경
4. 테스트 PASS 확인

### STEP 3: 템플릿 분리

1. `templates/payment/` 디렉토리 생성
2. HTML 3개 파일 생성
3. `payment_helpers.py`에 `load_template()` 함수 추가
4. `routers/payment.py`에서 인라인 HTML 변수 삭제 → `load_template()` 호출
5. 테스트 PASS 확인

### STEP 4: 서비스 분리

1. `services/payment_svc.py` 생성
2. 각 엔드포인트의 비즈니스 로직을 서비스 함수로 추출
3. 라우터는 HTTP 수신 → 서비스 호출 → 응답 반환만
4. 테스트 PASS 확인
5. **라우터 15KB / 400줄 이내 확인**

### STEP 5: 테스트 보강

```
tests/test_payment_helpers.py   ← 순수 함수 테스트
tests/test_payment_svc.py       ← 서비스 로직 테스트 (mock DB)
```

---

## 절대 하지 말 것

- 테스트 없이 분리 시작
- 라우터에서 직접 SQL 실행 (services에서만)
- 서비스에서 `from fastapi import Request, Response` 사용
- 한 파일에 400줄 이상 작성
- 20KB 이상 파일을 통째로 덮어쓰기
- STEP 0 테스트 PASS 확인 없이 다음 단계 진행
- 기존 API 응답 구조 변경 (입력/출력은 100% 동일해야 함)

---

## 커밋 단위

```
1. feat: STEP 0 — payment 현재 동작 테스트 5+개
2. refactor: STEP 1 — payment_helpers.py 헬퍼 분리
3. refactor: STEP 2 — schemas/payment.py 스키마 분리
4. refactor: STEP 3 — templates/payment/ HTML 분리
5. refactor: STEP 4 — payment_svc.py 서비스 분리 + 라우터 슬림화
6. test: STEP 5 — payment 테스트 보강
```

## 완료 기준

| 항목 | 기준 |
|------|------|
| `routers/payment.py` | 15KB (400줄) 이내 |
| `services/payment_helpers.py` | 15KB 이내 |
| `services/payment_svc.py` | 15KB 이내 |
| `schemas/payment.py` | 5KB 이내 |
| HTML 템플릿 | 별도 파일 3개 |
| 테스트 | 최소 10개, 전부 PASS |
| API 응답 | 분리 전후 100% 동일 |
| 브랜치 | dev에 커밋 (main 직접 push 금지) |
