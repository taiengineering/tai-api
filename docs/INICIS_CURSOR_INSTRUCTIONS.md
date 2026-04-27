# 이니시스 결제 Cursor 작업지시서

## 대상 파일
- `services/payment_svc.py` (27KB, MCP 수정 금지)

## 서비스 계층 규칙
- docs/DEV_RULES_SERVICE_LAYER.md 준수
- Router=HTTP만, Service=비즈니스로직, Schema=Pydantic검증
- `from fastapi import` 금지 (Service 파일에서)

---

## 작업 1: payment_helpers.py 수정사항 (이미 MCP로 반영됨)

### 추가된 함수/상수:
- `sha512()` — 빌링/취소 API용
- `ts_yyyymmddhhmmss()` — 빌링/취소 timestamp 형식
- `INICIS_INILITE_KEY`, `INICIS_INIAPI_KEY`, `INICIS_BILLING_MID` — 빌링/취소 전용 키
- `BILLING_ISSUE_URL`, `BILLING_CHARGE_URL`, `REFUND_URL` — API URL 상수
- `decrypt_billkey()` — AES256 빌링키 복호화
- `get_server_ip()` — 서버 IP 조회

---

## 작업 2: payment_svc.py 전면 재작성

### 2-1. 유지할 함수 (변경 없음)
- `PaymentPrepareError`
- `load_sign_key()` — 단건용 SignKey
- `process_auth_failure()`
- `process_vbank_issued()`
- `process_card_success()`
- `create_vbank_record()`
- `process_vbank_deposit()`
- health probe 등록

### 2-2. 수정할 함수

#### `call_pay_auth()` — 단건 STEP3 승인
현재 코드 정상이나, RSA 서명 부분 제거 (불필요하고 오류 원인 가능):
```python
def call_pay_auth(auth_token: str, auth_url: str, sign_key: str) -> Dict[str, Any]:
    timestamp = ts_ms()
    signature = sha256(f"authToken={auth_token}&timestamp={timestamp}")
    verification = sha256(f"authToken={auth_token}&signKey={sign_key}&timestamp={timestamp}")
    params = {
        "mid": INICIS_MID,
        "authToken": auth_token,
        "timestamp": timestamp,
        "signature": signature,
        "verification": verification,
        "charset": "UTF-8",
        "format": "JSON",
    }
    # RSA signData 제거 — 테스트 MID에서는 불필요하며 오류 원인
    resp = _requests.post(auth_url, data=params, timeout=30,
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    return resp.json()
```

#### `run_inicis_prepare()` — 단건 STEP1
현재 코드 거의 정상. 응답에 `acceptmethod: "centerCd(Y)"` 추가:
```python
return {
    "status": "success",
    "data": {
        ...
        "acceptmethod": "centerCd(Y)",
    },
}
```

### 2-3. 완전히 재작성할 함수

#### `run_billing_prepare()` — 빌링키 발급 준비
```python
def run_billing_prepare(body) -> Dict[str, Any]:
    """빌링키 발급 준비 — inilitepay.inicis.com 으로 POST할 파라미터 생성."""
    from services.payment_helpers import (
        INICIS_BILLING_MID, INICIS_INILITE_KEY, BILLING_ISSUE_URL,
        sha512, ts_yyyymmddhhmmss, make_order_id, now_iso, split_supply_vat
    )
    if not INICIS_BILLING_MID:
        raise PaymentPrepareError(500, "INICIS_BILLING_MID 미설정")
    if not INICIS_INILITE_KEY:
        raise PaymentPrepareError(500, "INICIS_INILITE_KEY 미설정")

    supabase = get_supabase()
    now = now_iso()
    order_id = make_order_id()
    timestamp = ts_yyyymmddhhmmss()  # YYYYMMDDhhmmss 형식!
    price_str = str(body.amount)

    # SHA512(price + mid + orderId + timestamp + INILiteKey)
    hash_data = sha512(price_str + INICIS_BILLING_MID + order_id + timestamp + INICIS_INILITE_KEY)

    # subscriptions 테이블 생성
    supply, vat = split_supply_vat(body.amount)
    row = {
        "user_id": body.user_id,
        "company_id": body.company_id,
        "product_type": body.product_type,
        "plan_code": body.plan_code,
        "plan_name": body.goodname,
        "amount": body.amount,
        "supply_amount": supply,
        "vat_amount": vat,
        "billing_cycle": "monthly",
        "status": "PENDING",
        "created_at": now,
        "updated_at": now,
    }
    # billing_key_id는 빌키 발급 후 연결 (NOT NULL이므로 임시 처리 필요)
    # → DB 마이그레이션에서 billing_key_id nullable로 변경 필요

    return {
        "status": "success",
        "data": {
            "billing_issue_url": BILLING_ISSUE_URL,
            "mid": INICIS_BILLING_MID,
            "orderId": order_id,
            "price": price_str,
            "timestamp": timestamp,
            "hashData": hash_data,
            "goodName": body.goodname,
            "buyerName": body.buyername or "고객",
            "buyerTel": body.buyertel or "00000000000",
            "buyerEmail": body.buyeremail or "",
            "returnUrl": f"https://api.taieng.co.kr/payments/inicis/billing/return",
        },
    }
```

#### `run_billing_return()` — 빌링키 발급 결과 처리
```python
def run_billing_return(body) -> Dict[str, Any]:
    """빌링키 발급 결과 처리 — returnUrl POST 데이터."""
    from services.payment_helpers import (
        INICIS_INILITE_KEY, decrypt_billkey, now_iso
    )
    if body.resultCode != "SUCCESS":
        raise PaymentPrepareError(400, body.resultMsg or "빌링키 발급 실패")

    # billkey 복호화 (AES256)
    bill_key = decrypt_billkey(body.billkey, INICIS_INILITE_KEY)
    if not bill_key:
        raise PaymentPrepareError(400, "빌링키 복호화 실패")

    supabase = get_supabase()
    now = now_iso()

    # billing_keys 테이블 저장
    key_row = supabase.table("billing_keys").insert({
        "user_id": body.user_id,
        "company_id": body.company_id,
        "bill_key": bill_key,
        "mid": body.mid or INICIS_BILLING_MID,
        "inicis_tid": body.tid,
        "card_name": body.cardCompanyName,
        "card_num_masked": body.cardNumber,
        "card_issuer_code": body.cardCode,
        "status": "ACTIVE",
        "inicis_raw": body.raw_data,
        "created_at": now,
        "updated_at": now,
    }).execute()

    # subscriptions 연결 (orderId로 찾기)
    if body.orderId:
        supabase.table("subscriptions").update({
            "billing_key_id": key_row.data[0]["id"],
            "status": "ACTIVE",
            "started_at": now,
            "updated_at": now,
        }).eq("inicis_order_id", body.orderId).execute()

    return {"status": "success", "data": {"billing_key_id": key_row.data[0]["id"]}}
```

#### `run_billing_charge()` — 빌링 승인 (정기과금)
```python
def run_billing_charge(body) -> Dict[str, Any]:
    """빌링 승인 — iniapi.inicis.com/api/v1/billing"""
    from services.payment_helpers import (
        INICIS_BILLING_MID, INICIS_INIAPI_KEY, BILLING_CHARGE_URL,
        sha512, ts_yyyymmddhhmmss, make_order_id, now_iso,
        split_supply_vat, get_server_ip
    )
    supabase = get_supabase()
    now = now_iso()

    # subscription + billing_key 조회
    sub = supabase.table("subscriptions").select("*").eq("id", body.subscription_id).limit(1).execute()
    if not sub.data:
        raise PaymentPrepareError(404, "구독을 찾을 수 없습니다.")
    sub = sub.data[0]

    key = supabase.table("billing_keys").select("*").eq("id", sub["billing_key_id"]).eq("status", "ACTIVE").limit(1).execute()
    if not key.data:
        raise PaymentPrepareError(404, "활성 빌링키가 없습니다.")
    key = key.data[0]

    amount = int(body.amount or sub["amount"])
    moid = make_order_id()
    timestamp = ts_yyyymmddhhmmss()
    client_ip = get_server_ip()

    # SHA512(INIAPIKey + type + paymethod + timestamp + clientIp + mid + moid + price + billKey)
    hash_str = INICIS_INIAPI_KEY + "Billing" + "Card" + timestamp + client_ip + INICIS_BILLING_MID + moid + str(amount) + key["bill_key"]
    hash_data = sha512(hash_str)

    payload = {
        "type": "Billing",
        "paymethod": "Card",
        "timestamp": timestamp,
        "clientIp": client_ip,
        "mid": INICIS_BILLING_MID,
        "url": "https://taieng.co.kr",
        "moid": moid,
        "goodName": body.goodname or sub.get("plan_name", "TAI Safe 정기결제"),
        "buyerName": "고객",
        "buyerEmail": "",
        "price": str(amount),
        "billKey": key["bill_key"],
        "authentification": "00",
        "hashData": hash_data,
    }

    resp = _requests.post(
        BILLING_CHARGE_URL,
        data=payload,  # NVP 형식: key=value
        timeout=30,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    result = resp.json()

    if str(result.get("resultCode", "")) != "00":
        # 실패 처리
        fc = int(sub.get("failure_count", 0)) + 1
        supabase.table("subscriptions").update({
            "failure_count": fc,
            "last_failure_at": now,
            "last_failure_reason": result.get("resultMsg", ""),
            "status": "PAUSED" if fc >= 3 else sub["status"],
            "updated_at": now,
        }).eq("id", sub["id"]).execute()
        raise PaymentPrepareError(400, result.get("resultMsg", "빌링 승인 실패"))

    # 성공: payments 기록 + subscription 갱신
    supply, vat = split_supply_vat(amount)
    supabase.table("payments").insert({
        "user_id": sub["user_id"],
        "company_id": sub.get("company_id"),
        "product_type": sub["product_type"],
        "plan_code": sub["plan_code"],
        "payment_method": "INICIS_BILLING",
        "payment_type": "BILLING",
        "total_amount": amount,
        "supply_amount": supply,
        "vat_amount": vat,
        "inicis_order_id": moid,
        "inicis_tid": result.get("tid", ""),
        "status_code": "SUCCESS",
        "service_status": "ACTIVE",
        "inicis_raw": result,
        "paid_at": now,
        "subscription_id": sub["id"],
        "billing_key_id": key["id"],
        "is_recurring": True,
        "created_at": now,
        "updated_at": now,
    }).execute()

    # next_billing_at 갱신
    from dateutil.relativedelta import relativedelta
    from datetime import datetime, timezone
    next_dt = datetime.now(timezone.utc) + relativedelta(months=1)
    supabase.table("subscriptions").update({
        "status": "ACTIVE",
        "failure_count": 0,
        "last_billed_at": now,
        "next_billing_at": next_dt.isoformat(),
        "updated_at": now,
    }).eq("id", sub["id"]).execute()

    return {"status": "success", "data": {"tid": result.get("tid"), "amount": amount}}
```

#### 신규: `run_refund()` — 취소/환불
```python
def run_refund(tid: str, paymethod: str = "Card", reason: str = "사용자 요청") -> Dict[str, Any]:
    """일반 전체취소 — iniapi.inicis.com/api/v1/refund"""
    from services.payment_helpers import (
        INICIS_MID, INICIS_INIAPI_KEY, REFUND_URL,
        sha512, ts_yyyymmddhhmmss, get_server_ip, now_iso
    )
    timestamp = ts_yyyymmddhhmmss()
    client_ip = get_server_ip()

    hash_str = INICIS_INIAPI_KEY + "Refund" + paymethod + timestamp + client_ip + INICIS_MID + tid
    hash_data = sha512(hash_str)

    payload = {
        "type": "Refund",
        "paymethod": paymethod,
        "timestamp": timestamp,
        "clientIp": client_ip,
        "mid": INICIS_MID,
        "tid": tid,
        "msg": reason,
        "hashData": hash_data,
    }

    resp = _requests.post(
        REFUND_URL,
        data=payload,
        timeout=30,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    result = resp.json()

    if str(result.get("resultCode", "")) != "00":
        raise PaymentPrepareError(400, result.get("resultMsg", "취소 실패"))

    # payments 상태 업데이트
    supabase = get_supabase()
    now = now_iso()
    supabase.table("payments").update({
        "status_code": "CANCELLED",
        "service_status": "ENDED",
        "cancelled_at": now,
        "cancel_reason": reason,
        "updated_at": now,
    }).eq("inicis_tid", tid).execute()

    return {"status": "success", "data": result}
```

---

## 작업 3: DB 마이그레이션

### subscriptions.billing_key_id nullable 변경
```sql
ALTER TABLE subscriptions ALTER COLUMN billing_key_id DROP NOT NULL;
```

### subscriptions에 inicis_order_id 컬럼 추가 (빌키발급 추적용)
```sql
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS inicis_order_id TEXT;
```

---

## 작업 순서

1. ✅ payment_helpers.py 수정 (MCP, 이미 반영)
2. ✅ schemas/payment.py 수정 (MCP, 이미 반영)
3. ✅ DB 마이그레이션 (Supabase MCP)
4. ⏳ payment_svc.py 재작성 (이 문서 기반, Cursor에서 실행)
5. ⏳ 프론트 diagnosis.html 수정 (Cursor, 66KB)
6. ⏳ Railway 환경변수 추가 (INICIS_INILITE_KEY, INICIS_INIAPI_KEY)
7. ⏳ 이니시스 매니저에게 빌링 MID 발급 요청
