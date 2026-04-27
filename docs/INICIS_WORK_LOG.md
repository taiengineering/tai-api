# KG이니시스 결제 연동 작업 내역 v2.1 (2026-04-27 최종)

## 세션 요약
이니시스 매뉴얼 3개(일반결제/빌링/취소)를 처음부터 학습 후, 백엔드 전면 재작성 완료.

---

## 완료된 작업 (전부 main 커밋, Railway 자동배포)

### 1. 매뉴얼 학습 + 스펙 문서
- `docs/INICIS_INTEGRATION_SPEC.md` — 3가지 키 체계, 4단계 단건 플로우, 빌링 플로우, 취소 API 전체 정리

### 2. payment_helpers.py v2
- `sha512()` — 빌링/취소 API hashData용
- `ts_yyyymmddhhmmss()` — 빌링/취소 timestamp (YYYYMMDDhhmmss)
- `INICIS_BILLING_MID`, `INICIS_INILITE_KEY`, `INICIS_INIAPI_KEY` 환경변수
- `BILLING_ISSUE_URL`, `BILLING_CHARGE_URL`, `REFUND_URL` API URL 상수
- `decrypt_billkey()` — AES256 빌링키 복호화
- `get_server_ip()` — 빌링승인/취소 API clientIp용

### 3. schemas/payment.py v2
- `BillingReturnBody`: 이니시스 빌키발급 STEP2 응답 전체 19개 파라미터
- `RefundBody`, `PartialRefundBody`: 취소/부분취소 스키마

### 4. payment_svc.py v4 (전면 재작성)
**단건결제:**
- `call_pay_auth()`: RSA 서명 블록 완전 제거 (결제창 미표시 원인)
- `run_inicis_prepare()`: 응답에 `acceptmethod: "centerCd(Y)"` 추가

**빌링(구독):**
- `run_billing_prepare()`: INILiteKey + SHA512 + `inilitepay.inicis.com` + YYYYMMDDhhmmss
- `run_billing_return()`: AES256 빌키 복호화 + billing_keys 저장 + subscriptions 연결
- `run_billing_charge()`: INIAPIKey + SHA512 + NVP + `iniapi.inicis.com/api/v1/billing`
- `run_billing_cancel()`: DB 빌키 폐기 + 구독 CANCELLED

**취소/환불 (신규):**
- `run_refund()`: 전체취소 SHA512 + iniapi.inicis.com/api/v1/refund
- `run_partial_refund()`: 부분취소

### 5. routers/payment.py v4
- `/inicis/billing/return`: JSON → form POST 수신으로 변경
- `POST /{payment_id}/refund`: 전체취소 라우터
- `POST /{payment_id}/partial-refund`: 부분취소 라우터

### 6. DB 마이그레이션
- `subscriptions.billing_key_id` nullable
- `subscriptions.inicis_order_id` 추가
- `billing_keys.subscription_id` 추가

---

## 프론트엔드 확인 사항 (브라우저에서 검증)

### diagnosis.html (단건결제)
- [x] `INIStdPay.js` 로드됨
- [x] `inicis-fix.js` 로드됨
- [x] 폼 ID: `diag_inicis_form` → `INIStdPay.pay('diag_inicis_form')` 호출 확인
- [x] accept-charset: UTF-8
- [x] version: 1.0, gopaymethod: Card, use_chkfake: Y, acceptmethod: centerCd(Y)
- [x] API 호출 후 mid, mKey, oid, price, signature, verification, returnUrl, closeUrl 채워짐

### 결제창 미표시 원인 분석
- RSA 서명이 `call_pay_auth()`에 포함되어 있었음 → **제거 완료**
- 테스트 MID(`INIpayTest`)로 실 도메인 결제 시 동작하지 않을 수 있음 → **오리지널 키 원복 완료**

---

## API 엔드포인트 최종 정리

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | /payments/inicis/prepare | 단건결제 준비 (STEP1) |
| POST | /payments/inicis/return | 단건 인증결과 수신 (STEP2→3) |
| POST | /payments/inicis/noti | 단건 서버 노티 백업 |
| POST | /payments/inicis/billing/prepare | 빌키발급 준비 |
| POST | /payments/inicis/billing/return | 빌키발급 결과 (form POST) |
| POST | /payments/inicis/billing/charge | 빌링 승인(과금) |
| POST | /subscriptions/{id}/cancel | 구독 해지 |
| POST | /payments/{id}/refund | 전체취소 |
| POST | /payments/{id}/partial-refund | 부분취소 |
| POST | /payments/vbank/prepare | 가상계좌 발급 |
| POST | /payments/vbank/noti | 가상계좌 입금 확인 |
| GET | /payments/pricing | 결제 선택 페이지 |
| GET | /payments/result | 결제 결과 페이지 |
| GET | /payments/billing/terms | 구독 이용안내 |

---

## 환경변수 (Railway)

| 변수 | 용도 | 상태 |
|------|------|------|
| INICIS_MID | 단건결제 MID | ✅ 오리지널 |
| INICIS_SIGN_KEY | 단건결제 서명키 | ✅ 오리지널 |
| INICIS_BILLING_MID | 빌링 MID | ✅ 설정됨 |
| INICIS_INILITE_KEY | 빌키발급 키 | ✅ 설정됨 |
| INICIS_INIAPI_KEY | 빌링승인/취소 키 | ✅ 설정됨 |

---

## 파일 위치

| 파일 | 레포 | 크기 | 상태 |
|------|------|------|------|
| `services/payment_helpers.py` | tai-api | 7KB | ✅ v2 완료 |
| `schemas/payment.py` | tai-api | 6KB | ✅ v2 완료 |
| `services/payment_svc.py` | tai-api | 38KB | ✅ v4 완료 |
| `routers/payment.py` | tai-api | 14KB | ✅ v4 완료 |
| `docs/INICIS_INTEGRATION_SPEC.md` | tai-api | 신규 | ✅ 완료 |

## 매뉴얼 참고
- PC 일반결제: https://manual.inicis.com/pay/stdpay_pc.html
- 빌링(정기과금): https://manual.inicis.com/pay/bill.html
- 취소/환불: https://manual.inicis.com/pay/cancel.html
