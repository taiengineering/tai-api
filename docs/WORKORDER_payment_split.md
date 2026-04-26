# 작업지시: `routers/payment.py` 서비스 계층 분리

> 규칙: [DEV_RULES_SERVICE_LAYER.md](./DEV_RULES_SERVICE_LAYER.md) 필수 준수  
> 대상: `tai-api/routers/payment.py` (~50KB)

## 단계

| Step | 내용 | 완료 기준 |
|------|------|-----------|
| 0 | `tests/test_payment_current.py` — 현재 동작 스냅샷 (최소 5개), 전부 PASS | `pytest tests/test_payment_current.py -v` |
| 1 | `services/payment_helpers.py` — 순수 유틸·상수 | 기존 + current 테스트 PASS |
| 2 | `schemas/payment.py` — Pydantic 모델 이동 | import 경로만 변경, 테스트 PASS |
| 3 | `services/payment_svc.py` — INICIS 키/승인 호출 + `inicis_prepare` 비즈니스 | 테스트 PASS |
| 4 | 라우터 슬림화 — `inicis_prepare` 등 얇게 | 테스트 PASS |
| 5 | `test_payment_helpers.py`, `test_payment_svc.py` 보강 | payment 관련 테스트 PASS |

## 금지

- STEP 0 없이 STEP 1 이후 시작  
- 서비스에서 `from fastapi import Request` (HTTP 전용은 라우터)  
- 테스트 없이 대규모 덮어쓰기  
