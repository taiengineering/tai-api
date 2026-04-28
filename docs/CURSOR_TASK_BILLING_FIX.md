# Cursor 작업지시서 — 결제 빌링 중복 엔드포인트 제거

**작성**: 2026-04-28 (v2 — Railway 로그 기반 확정 진단)
**우선순위**: 긴급 (이니시스 심사 차단)
**관련 파일**: `routers/payment.py` (14KB)
**규칙**: `docs/DEV_RULES_SERVICE_LAYER.md` 준수

---

## 1. 현상

`POST /payments/inicis/billing/prepare` → **500 Internal Server Error**

## 2. 근본 원인 (Railway 로그 확인 완료)

```
Duplicate Operation ID billing_prepare_payments_inicis_billing_prepare_post
  for function billing_prepare at /app/routers/payment.py
Duplicate Operation ID billing_return_payments_inicis_billing_return_post
  for function billing_return at /app/routers/payment.py
Duplicate Operation ID billing_charge_payments_inicis_billing_charge_post  
  for function billing_charge at /app/routers/payment.py
Duplicate Operation ID cancel_subscription_payments_subscriptions__subscription_id__cancel_post
  for function cancel_subscription at /app/routers/payment.py
```

**`routers/payment.py`(단건결제)에 빌링 엔드포인트 4개가 중복 정의**되어 있음.
`routers/payment_billing.py`(정기결제 전용)과 동일 경로를 등록하므로 FastAPI가 두 핸들러를 모두 등록.
`payment.py`의 빌링 핸들러가 실행되면 schema/로직 차이로 500 크래시.

## 3. 수정 사항

### 3-1. `routers/payment.py`에서 빌링 관련 4개 엔드포인트 **삭제**

다음 함수와 데코레이터를 찾아서 **전체 삭제**:

```python
@router.post("/inicis/billing/prepare")
def billing_prepare(...):
    ...

@router.post("/inicis/billing/return")
async def billing_return(...):
    ...

@router.post("/inicis/billing/charge")
def billing_charge(...):
    ...

@router.post("/subscriptions/{subscription_id}/cancel")
def cancel_subscription(...):
    ...
```

### 3-2. `routers/payment.py`에서 빌링 전용 import 정리

삭제한 함수에서만 사용하는 import가 있다면 함께 제거.
예: `BillingPrepareBody`, `BillingChargeBody`, `SubscriptionCancelBody` 등이
`payment.py` 내부에 정의되어 있거나 import되어 있다면 제거.

### 3-3. 빌링 전용 Pydantic 모델 정리

`payment.py` 내부에 `BillingPrepareBody` 등 로컬 클래스가 있다면 삭제.
정기결제 스키마는 `schemas/payment.py`와 `routers/payment_billing.py`에만 존재해야 함.

### 3-4. 변경하지 않을 것

- `routers/payment_billing.py` — 변경 없음 (이미 정상)
- `schemas/payment.py` — 변경 없음
- `main.py` — 변경 없음 (라우터 순서는 이전 커밋에서 수정 완료)
- `payment.py`의 단건결제 엔드포인트 — 절대 변경하지 않음:
  - `/inicis/prepare`
  - `/inicis/return`
  - `/inicis/noti`
  - `/payments/result`
  - 기타 단건결제/가상계좌/환불 관련 엔드포인트

## 4. 검증

수정 후 push → Railway 배포 대기 (3~5분) → 브라우저 콘솔에서:

```javascript
// api.taieng.co.kr 탭에서 실행
fetch('/payments/inicis/billing/prepare', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    user_id: 'e6d6da1b-ec93-4a69-a570-a6dae9959427',
    product_type: 'SAAS_BUILDING',
    amount: 249000,
    goodname: 'TAI Safe 건물 대형',
    plan_code: 'BUILDING_STANDARD'
  })
}).then(r => r.text()).then(console.log).catch(console.error);

// 기대: {"status":"success","data":{"subscription_id":"...","mid":"...", ...}}
// 503이면 환경변수 미설정
```

또한 Duplicate Operation ID 경고가 사라졌는지 Railway 로그에서 확인.

## 5. 주의사항

- `payment.py`는 14KB — 200줄 미만이므로 MCP 수정 가능하지만, 빌링 함수 규모에 따라 Cursor 권장
- 삭제 후 `/health` 200 확인 필수
- `from db.supabase_client import get_supabase` 패턴 유지
- 단건결제(`/inicis/prepare`, `/inicis/return`) 동작 확인 필수
