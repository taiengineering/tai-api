# Cursor 작업지시서: payment_svc.py VAT 포함 결제금액

> **파일**: `services/payment_svc.py` (38KB)
> **선행 완료**: `services/payment_helpers.py`에 `add_vat()` 함수 추가됨
> **배포**: main push → Railway 자동배포

---

## 변경 1: import에 add_vat 추가

```python
# 찾기 (약 line 50)
from services.payment_helpers import (
    ...
    split_supply_vat,
    ...
)

# add_vat 추가
from services.payment_helpers import (
    ...
    add_vat,           # ← 추가
    split_supply_vat,
    ...
)
```

## 변경 2: run_inicis_prepare 함수 (단건결제)

```python
# 찾기
    price_str = str(body.amount)

# 변경
    total_with_vat = add_vat(body.amount)  # 공급가액 → VAT 포함
    price_str = str(total_with_vat)
```

```python
# 찾기
    supply_amount, vat_amount = split_supply_vat(body.amount)

# 변경 (run_inicis_prepare 내부)
    supply_amount, vat_amount = split_supply_vat(total_with_vat)
```

```python
# 찾기 (run_inicis_prepare 내부 row dict)
        "total_amount": body.amount,

# 변경
        "total_amount": total_with_vat,
```

## 변경 3: create_vbank_record 함수 (가상계좌)

```python
# 찾기
    price_str = str(body.amount)

# 변경
    total_with_vat = add_vat(body.amount)
    price_str = str(total_with_vat)
```

```python
# 찾기 (create_vbank_record 내부)
    supply_amount, vat_amount = split_supply_vat(body.amount)

# 변경
    supply_amount, vat_amount = split_supply_vat(total_with_vat)
```

```python
# 찾기 (create_vbank_record 내부 row dict)
        "total_amount": body.amount,

# 변경
        "total_amount": total_with_vat,
```

## 변경 4: run_billing_prepare 함수 (빌링/구독)

```python
# 찾기
    price_str = str(body.amount)

# 변경
    total_with_vat = add_vat(body.amount)
    price_str = str(total_with_vat)
```

```python
# 찾기 (run_billing_prepare 내부)
    supply, vat = split_supply_vat(body.amount)

# 변경
    supply, vat = split_supply_vat(total_with_vat)
```

```python
# 찾기 (run_billing_prepare 내부 row dict)
        "amount": body.amount,

# 변경
        "amount": total_with_vat,
```

## 검증

변경 후 다음 명령으로 확인:
```bash
grep -n 'body.amount' services/payment_svc.py
```

남아있는 `body.amount` 사용처:
- `body.amount` → `run_billing_charge`에서 `int(body.amount or sub.get("amount"))` — 이건 이미 VAT 포함된 금액이 subscriptions에 저장되므로 변경 불필요
- PrepareBody 검증 등 — 변경 불필요

## 결과 확인

진단 결제: 99,000원(공급) → 이니시스 결제창 **108,900원** 표시
SaaS 빌링: 79,000원(공급) → 빌링 **86,900원** 표시
