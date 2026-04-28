# 작업지시서: 결제 금액 VAT 10% 포함 처리

> **우선순위**: 높음
> **대상 파일**: `services/payment_svc.py` (38KB)
> **관련 규칙**: `docs/DEV_RULES_SERVICE_LAYER.md` — Router/Service/Schema 분리 규칙 준수

---

## 배경

DB `price_diagnosis_report.total_report_fee`는 **공급가액(부가세 별도)**으로 저장되어 있다.
이니시스 결제창에 전달하는 `price`는 **VAT 10% 포함 금액**이어야 한다.

현재: DB 99,000원 → 이니시스 price=99,000원 (❌ 부가세 미포함)
목표: DB 99,000원 → 이니시스 price=108,900원 (✅ VAT 포함)

## 가격표 (VAT 포함 결제금액)

| 상품 | 공급가액 (DB) | VAT | 결제금액 |
|------|-------------|-----|--------|
| 건물 소형 | 99,000 | 9,900 | **108,900** |
| 건물 대형 | 249,000 | 24,900 | **273,900** |
| 산업 기본 | 79,000 | 7,900 | **86,900** |
| 산업 정밀 | 149,000 | 14,900 | **163,900** |
| 산업 종합 | 249,000 | 24,900 | **273,900** |
| 건설 기본 | 145,000 | 14,500 | **159,500** |
| 건설 종합 | 299,000 | 29,900 | **328,900** |

## 수정 사항

### 1. `services/payment_svc.py` — prepare 함수

이니시스에 전달하는 `price` 계산 시 VAT 포함:

```python
# 변경 전 (추정)
price = int(total_report_fee)  # 공급가액 그대로

# 변경 후
supply_amount = int(total_report_fee)  # DB 공급가액
price = int(supply_amount * 1.1)       # VAT 10% 포함 결제금액
```

### 2. `services/payment_svc.py` — return 콜백 (결제 완료 후 DB 저장)

결제 완료 후 `diagnosis_purchases` 또는 관련 테이블에 저장할 때:
- `amount` = 결제금액 (VAT 포함, 이니시스에서 받은 값)
- `supply_amount` = 공급가액 (`split_supply_vat()` 사용)
- `vat_amount` = VAT (`split_supply_vat()` 사용)

```python
from services.payment_helpers import split_supply_vat

supply, vat = split_supply_vat(paid_amount)  # 이미 구현되어 있음
```

### 3. `services/payment_helpers.py` — 헬퍼 함수 추가 (선택)

```python
def add_vat(supply_amount: int) -> int:
    """공급가액에 VAT 10% 추가하여 결제금액 반환"""
    return int(supply_amount * 1.1)
```

## 주의사항

- `split_supply_vat(total_amount)` 함수가 이미 `payment_helpers.py`에 존재 (역산용)
- DB `price_diagnosis_report.total_report_fee`는 수정하지 않음 (공급가액 유지)
- 이니시스 `signature`와 `verification` 해시에 `price`가 포함되므로, VAT 포함 금액으로 해시 계산해야 함
- 프론트엔드(diagnosis.html)에서 가격 표시도 VAT 포함으로 변경 필요 (별도 작업)

## 검증

1. `taieng.co.kr/service/diagnosis`에서 건물 소형 결제 시 이니시스 결제창에 **108,900원** 표시 확인
2. 결제 완료 후 DB에 amount=108,900, supply_amount=99,000, vat_amount=9,900 저장 확인
3. signature/verification 해시가 VAT 포함 price로 정상 계산 확인
