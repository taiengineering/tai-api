# Cursor 작업지시서 — 결제 빌링 라우팅 충돌 수정

**작성**: 2026-04-28  
**우선순위**: 긴급 (이니시스 심사 차단)  
**관련 파일**: `routers/payment.py` (14KB), `routers/payment_billing.py` (30KB)  
**규칙**: `docs/DEV_RULES_SERVICE_LAYER.md` 준수, Router/Service/Schema 분리 대상

---

## 1. 현상

`taieng.co.kr/service/saas` → 결제 버튼 → `/_api/payments/billing/pay` 페이지 → **"Failed to fetch"** 에러.

## 2. 근본 원인 (Chrome MCP로 확인 완료)

### 2-1. 라우팅 충돌

`payment.py`(단건)와 `payment_billing.py`(정기) 모두 `prefix="/payments"` 사용.  
`/payments/inicis/billing/prepare`로 POST 시 **단건 핸들러(`PrepareBody`)가 먼저 매칭**됨.

**증거** — 브라우저에서 직접 테스트:
```
POST /payments/inicis/billing/prepare + plan_name(정기 필드)
→ 422: {"loc":["body","goodname"],"msg":"Field required"}
           ↑ 이것은 단건(PrepareBody)의 필수필드
```

### 2-2. 필드명 불일치

| | 단건 PrepareBody | 정기 BillingPrepareBody | 결제 페이지 전송 |
|---|---|---|---|
| 상품명 | `goodname` (필수) | `plan_name` (필수) | `goodname` |
| plan_code | 선택 | 필수 | ✓ |

결제 페이지가 `goodname`을 보내면 → 단건 핸들러가 매칭 → 단건 처리 시도 → 서버 크래시 → "Failed to fetch".

### 2-3. 배포된 OpenAPI 스키마 (확인 완료)

```json
"/payments/inicis/prepare": {
  "schema": "PrepareBody",
  "required": ["user_id", "product_type", "amount", "goodname"]
}
"/payments/inicis/billing/prepare": {
  "schema": "BillingPrepareBody", 
  "required": ["user_id", "product_type", "plan_code", "plan_name", "amount"]
}
```

## 3. 수정 사항

### 3-1. `routers/payment_billing.py` — BillingPrepareBody 수정

`plan_name`을 선택으로 바꾸고, `goodname`을 받아서 fallback하도록 변경:

```python
class BillingPrepareBody(BaseModel):
    user_id:      str
    product_type: str
    plan_code:    str
    amount:       int
    # goodname과 plan_name 양쪽 모두 수용
    goodname:     Optional[str] = None
    plan_name:    Optional[str] = None
    company_id:   Optional[str] = None
    buyername:    Optional[str] = "고객"
    buyertel:     Optional[str] = "00000000000"
    buyeremail:   Optional[str] = None
    return_url:   Optional[str] = None
    close_url:    Optional[str] = None

    @field_validator("user_id")
    @classmethod
    def user_id_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id는 필수값입니다.")
        return v.strip()

    @field_validator("product_type")
    @classmethod
    def must_be_saas(cls, v: str) -> str:
        if v not in SAAS_PRODUCT_TYPES:
            raise ValueError(f"정기결제는 SaaS 상품에만 가능합니다: {SAAS_PRODUCT_TYPES}")
        return v

    @model_validator(mode="after")
    def resolve_plan_name(self):
        """goodname → plan_name fallback. 둘 다 없으면 에러."""
        if not self.plan_name and self.goodname:
            self.plan_name = self.goodname
        if not self.plan_name:
            raise ValueError("plan_name 또는 goodname 중 하나는 필수입니다.")
        return self
```

**import 추가 필요**:
```python
from pydantic import BaseModel, field_validator, model_validator
```

### 3-2. SAAS_PRODUCT_TYPES 확인

`services/payment_helpers.py`에서 `SAAS_PRODUCT_TYPES`에 다음이 포함되어 있는지 확인:
```python
SAAS_PRODUCT_TYPES = {
    "SAAS_FACILITY",
    "SAAS_BUILDING",      # ← 반드시 포함
    "SAAS_INDUSTRY",      # ← 반드시 포함  
    "SAAS_CONSTRUCTION",  # ← 반드시 포함
}
```

없으면 추가.

### 3-3. 라우팅 충돌 확인

`routers/payment.py`에서 `/inicis/` 관련 라우트 정의를 확인:
- `/inicis/prepare` (POST) — 단건결제
- `/inicis/return` (POST) — 단건 콜백
- `/inicis/noti` (POST) — 단건 알림

이 라우트들이 path parameter를 사용하고 있다면 (예: `@router.post("/inicis/{action}")`) 빌링 경로를 가로챌 수 있음. **path parameter 라우트가 있다면 exact match 라우트로 변경**.

### 3-4. `main.py` 라우터 등록 순서 확인

`payment_billing_router`가 `payment_router`보다 **먼저** 등록되어야 더 구체적인 경로(`/inicis/billing/prepare`)가 우선 매칭됨:

```python
# 기존 (충돌 가능)
app.include_router(payment_router)           # /payments/inicis/prepare
app.include_router(payment_ops_router)
app.include_router(payment_billing_router)   # /payments/inicis/billing/prepare

# 수정 (빌링 먼저)
app.include_router(payment_billing_router)   # /payments/inicis/billing/prepare (더 구체적)
app.include_router(payment_router)           # /payments/inicis/prepare
app.include_router(payment_ops_router)
```

## 4. 검증

수정 후 push → Railway 배포 대기 (3~5분) → 브라우저 콘솔에서:

```javascript
// 테스트 1: goodname만 전송 (결제 페이지와 동일)
fetch('https://api.taieng.co.kr/payments/inicis/billing/prepare', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    user_id: 'e6d6da1b-ec93-4a69-a570-a6dae9959427',
    product_type: 'SAAS_BUILDING',
    amount: 249000,
    goodname: 'TAI Safe 건물 대형',
    plan_code: 'BUILDING_STANDARD',
    buyername: '심태왕',
    buyertel: '01047758888'
  })
}).then(r => r.text()).then(console.log).catch(console.error);

// 기대 결과: {"status":"success","data":{...}} (503이면 환경변수 미설정)
```

```javascript
// 테스트 2: 단건결제가 여전히 동작하는지
fetch('https://api.taieng.co.kr/payments/inicis/prepare', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    user_id: 'e6d6da1b-ec93-4a69-a570-a6dae9959427',
    product_type: 'DIAGNOSIS_PAID',
    amount: 99000,
    goodname: '유료 법령진단'
  })
}).then(r => r.text()).then(console.log).catch(console.error);

// 기대 결과: {"status":"success","data":{...}}
```

## 5. 결제 페이지 위치 (별도 확인 필요)

`taieng.co.kr/_api/payments/billing/pay` 페이지는 `tai-admin` 레포의 정적 파일에 없음.  
Cloudflare Workers/Pages Function 또는 별도 배포 소스에서 서빙 중.  
현재 페이지의 JavaScript가 `goodname`을 보내므로, 백엔드에서 `goodname`을 수용하는 것이 올바른 방향.

## 6. 주의사항

- `payment_billing.py`는 30KB — Router/Service 분리 대상이지만 이번 수정은 Pydantic 모델 + import만 변경
- `main.py`의 라우터 순서 변경 시 다른 `/payments/` 엔드포인트 영향 없는지 확인
- 배포 후 `/health` 200 확인 필수
- `from db.supabase_client import get_supabase` 패턴 유지
