# KG이니시스 결제 연동 작업 내역 v3.0 (2026-04-28 최종)

## 세션 요약
이니시스 매뉴얼 3개(일반결제/빌링/취소)를 처음부터 학습 후, 백엔드 전면 재작성.
Supabase 싱가포르→한국 리전 이전 대응, RLS 문제 해결, 도메인 불일치 문제 발견.

---

## 세션 2 작업 (2026-04-28)

### 1. SaaS 구독결제 페이지 구현
- `templates/payment/billing_pay.html` — 빌링 전용 결제 페이지
  - `/payments/billing/pay?user_id=...&amount=...` 로 접근
  - 자동으로 `/payments/inicis/billing/prepare` API 호출
  - 응답 파라미터로 `inilitepay.inicis.com` 빌키발급 폼 자동 제출
- `routers/payment.py` v4.1 — `GET /payments/billing/pay` 엔드포인트 추가

### 2. returnUrl 도메인 일치 수정 (V023 에러)
- `payment_helpers.py` v2.1 → v2.2
- **변경 전**: `api.taieng.co.kr/payments/inicis/return` (도메인 불일치)
- **변경 후**: `new.taieng.co.kr/_api/payments/inicis/return` (동일 도메인 프록시)
- Cloudflare Pages Function(`functions/_api/[[path]].js`)이 `api.taieng.co.kr`로 프록시
- 모든 URL 변경:
  - `DEFAULT_RETURN_URL` → `new.taieng.co.kr/_api/payments/inicis/return`
  - `DEFAULT_CLOSE_URL` → `new.taieng.co.kr/_api/payments/result?resultCode=CLOSE`
  - `FRONT_RETURN_URL` → `new.taieng.co.kr/_api/payments/result`
  - `BILLING_RETURN_URL` → `new.taieng.co.kr/_api/payments/inicis/billing/return`

### 3. INICIS_CLIENT_IP 고정
- `payment_helpers.py` v2.2 — `get_server_ip()` → `INICIS_CLIENT_IP` 환경변수 우선
- Railway 서버 IP: `115.68.227.222`

### 4. supabase_client.py 수정
- `SUPABASE_SERVICE_KEY` 우선 사용 → RLS 우회
- 기존: `SUPABASE_KEY`(anon 키) → INSERT 시 RLS 차단 발생

### 5. Supabase 리전 이전 대응
- 싱가포르(xntdkrjhgcscmqctdzyo) → 한국(vwlahtguyggrhvslabax)
- payments/subscriptions/billing_keys RLS 비활성화 재적용
- payments RLS 정책 `allow_service_role_all` 추가 → 이후 RLS 자체 비활성화

### 6. 결제창 미표시 원인 분석 (디버깅 완료)
- API prepare → 200 성공 ✅
- 폼 값 전부 정상 (mid, mKey, signature, verification, returnUrl) ✅
- `INIStdPay.pay()` 호출 성공, `boolInitDone=true` ✅
- iframe 생성됨 (1429x723, visible) ✅
- formAction: `stdpay.inicis.com/payMain/pay` ✅
- **원인: 이니시스 MID 등록 도메인 불일치**
  - MID `taieng4350` 등록 도메인: `taieng.co.kr`
  - 실제 결제 페이지: `new.taieng.co.kr`
  - 이니시스 매니저에게 `new.taieng.co.kr` 도메인 추가 등록 메일 발송 완료

---

## 세션 1 작업 (2026-04-27)

### 1. 매뉴얼 학습 + 스펙 문서
- `docs/INICIS_INTEGRATION_SPEC.md` — 3가지 키 체계, 4단계 단건 플로우, 빌링 플로우, 취소 API 전체 정리

### 2. payment_helpers.py v2
- `sha512()` — 빌링/취소 API hashData용
- `ts_yyyymmddhhmmss()` — 빌링/취소 timestamp (YYYYMMDDhhmmss)
- `INICIS_BILLING_MID`, `INICIS_INILITE_KEY`, `INICIS_INIAPI_KEY` 환경변수
- `BILLING_ISSUE_URL`, `BILLING_CHARGE_URL`, `REFUND_URL` API URL 상수
- `decrypt_billkey()` — AES256 빌링키 복호화

### 3. schemas/payment.py v2
- `BillingReturnBody`: 이니시스 빌키발급 STEP2 응답 전체 19개 파라미터
- `RefundBody`, `PartialRefundBody`: 취소/부분취소 스키마

### 4. payment_svc.py v4 (전면 재작성)
**단건결제:**
- `call_pay_auth()`: RSA 서명 블록 완전 제거
- `run_inicis_prepare()`: 응답에 `acceptmethod: "centerCd(Y)"` 추가

**빌링(구독):**
- `run_billing_prepare()`: INILiteKey + SHA512 + `inilitepay.inicis.com` + YYYYMMDDhhmmss
- `run_billing_return()`: AES256 빌키 복호화 + billing_keys 저장 + subscriptions 연결
- `run_billing_charge()`: INIAPIKey + SHA512 + NVP + `iniapi.inicis.com/api/v1/billing`
- `run_billing_cancel()`: DB 빌키 폐기 + 구독 CANCELLED

**취소/환불 (신규):**
- `run_refund()`: 전체취소 SHA512 + iniapi.inicis.com/api/v1/refund
- `run_partial_refund()`: 부분취소

### 5. routers/payment.py v4 → v4.1
- `/inicis/billing/return`: JSON → form POST 수신으로 변경
- `POST /{payment_id}/refund`: 전체취소 라우터
- `POST /{payment_id}/partial-refund`: 부분취소 라우터
- `GET /payments/billing/pay`: SaaS 구독결제 전용 페이지

### 6. DB 마이그레이션
- `subscriptions.billing_key_id` nullable
- `subscriptions.inicis_order_id` 추가
- `billing_keys.subscription_id` 추가
- payments/subscriptions/billing_keys RLS 비활성화

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
| GET | /payments/billing/pay | SaaS 구독결제 (빌키발급 시작) |

---

## 환경변수 (Railway)

| 변수 | 용도 | 상태 |
|------|------|------|
| INICIS_MID | 단건결제 MID | ✅ taieng4350 |
| INICIS_SIGN_KEY | 단건결제 서명키 | ✅ 오리지널 |
| INICIS_BILLING_MID | 빌링 MID | ✅ 설정됨 |
| INICIS_INILITE_KEY | 빌키발급 키 | ✅ 설정됨 |
| INICIS_INIAPI_KEY | 빌링승인/취소 키 | ✅ 설정됨 |
| INICIS_CLIENT_IP | 서버 공인 IP | ✅ 115.68.227.222 |
| SUPABASE_URL | DB URL (한국 리전) | ✅ vwlahtguyggrhvslabax |
| SUPABASE_SERVICE_KEY | service_role 키 | ✅ RLS 우회 |

---

## 파일 위치

| 파일 | 레포 | 버전 | 상태 |
|------|------|------|------|
| `services/payment_helpers.py` | tai-api | v2.2 | ✅ 완료 |
| `schemas/payment.py` | tai-api | v2 | ✅ 완료 |
| `services/payment_svc.py` | tai-api | v4 | ✅ 완료 |
| `routers/payment.py` | tai-api | v4.1 | ✅ 완료 |
| `db/supabase_client.py` | tai-api | - | ✅ service_role |
| `templates/payment/billing_pay.html` | tai-api | - | ✅ 생성 |
| `docs/INICIS_INTEGRATION_SPEC.md` | tai-api | - | ✅ 완료 |

---

## PENDING — 미해결 이슈

### ISSUE-01: 결제창 미표시 (도메인 불일치)
- **상태**: 이니시스 매니저에게 도메인 추가 메일 발송 완료
- **원인**: MID `taieng4350` 등록 도메인 `taieng.co.kr` ≠ 결제 페이지 `new.taieng.co.kr`
- **해결**: 이니시스에서 `new.taieng.co.kr` 도메인 추가 등록
- **확인 방법**: 등록 완료 후 `new.taieng.co.kr/service/diagnosis` → 결제하기 클릭 → 결제창 표시

### ISSUE-02: SaaS 프론트 구독결제 변경 (Cursor 작업)
- `nexas/service/saas` 페이지에서:
  1. `accept-charset: euc-kr` → `UTF-8` 변경
  2. 결제하기 버튼: `INIStdPay.pay()` → `window.location.href = api.taieng.co.kr/payments/billing/pay?...` 변경

### ISSUE-03: taieng.co.kr ↔ new.taieng.co.kr 도메인 통합
- KG이니시스 심사 완료 후 통합 예정
- 통합 시 returnUrl도 `taieng.co.kr/_api/...`로 변경 필요

---

## 매뉴얼 참고
- PC 일반결제: https://manual.inicis.com/pay/stdpay_pc.html
- 빌링(정기과금): https://manual.inicis.com/pay/bill.html
- 취소/환불: https://manual.inicis.com/pay/cancel.html
