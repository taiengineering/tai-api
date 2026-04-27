# KG이니시스 결제 연동 작업 내역 v2.0 (2026-04-27)

## 세션 요약
이니시스 매뉴얼을 처음부터 학습한 후, 단건결제+구독결제+취소/환불을 전면 재작성.

---

## 핵심 발견: 기존 코드 문제점

### 단건결제 — 거의 정상
- signature, verification, mKey 계산 정상
- STEP3 승인요청 로직 정상
- 문제: RSA 서명이 불필요하게 포함 (테스트 MID에서 오류 가능)
- 문제: acceptmethod가 서버 응답에 누락

### 빌링(구독) — **대부분 잘못됨**
| # | 문제 | 원인 |
|---|------|------|
| 1 | 키 체계 | 이니시스는 3가지 키 사용: SignKey(단건) / INILiteKey(빌키) / INIAPIKey(빌링승인·취소). 기존 코드는 SignKey 하나만 사용 |
| 2 | 빌키발급 URL | `inilitepay.inicis.com/pay/card/billing`으로 POST해야 함. 기존 코드에 없음 |
| 3 | 빌키발급 해시 | SHA512(price+mid+orderId+timestamp+INILiteKey). 기존은 SHA256+SignKey |
| 4 | timestamp 형식 | 빌링은 YYYYMMDDhhmmss. 기존은 millis(단건 형식) |
| 5 | 빌키 복호화 | AES256 암호화된 billkey를 복호화해야 함. 기존 코드에 없음 |
| 6 | 빌링승인 해시 | SHA512(INIAPIKey+type+paymethod+...). 기존은 SHA256+SignKey |
| 7 | 빌링승인 URL | `iniapi.inicis.com/api/v1/billing`. 기존은 잘못된 URL |
| 8 | 빌링승인 파라미터 | type, paymethod, clientIp, authentification 등 누락 |

---

## 완료된 작업 (v2.0)

### 1. 매뉴얼 학습 + 스펙 문서
- `docs/INICIS_INTEGRATION_SPEC.md` — PC단건/빌링/취소 전체 플로우 정리
- `docs/INICIS_CURSOR_INSTRUCTIONS.md` — Cursor 작업지시서

### 2. payment_helpers.py v2 — 키 체계 + 유틸 확장
- `sha512()` — 빌링/취소 API hashData용
- `ts_yyyymmddhhmmss()` — 빌링/취소 timestamp 형식
- `INICIS_BILLING_MID`, `INICIS_INILITE_KEY`, `INICIS_INIAPI_KEY` 환경변수
- `BILLING_ISSUE_URL`, `BILLING_CHARGE_URL`, `REFUND_URL` API URL 상수
- `decrypt_billkey()` — AES256 빌링키 복호화
- `get_server_ip()` — 서버 IP 조회

### 3. schemas/payment.py v2 — 매뉴얼 기준 스키마
- `BillingReturnBody`: 이니시스 빌키발급 STEP2 응답 전체 파라미터 반영
- `RefundBody`: 전체취소
- `PartialRefundBody`: 부분취소
- `BillingPrepareBody`: factory_id 추가

### 4. DB 마이그레이션
- `subscriptions.billing_key_id` → nullable (빌키 발급 전 구독 생성)
- `subscriptions.inicis_order_id` → 추가 (빌키발급 추적용)
- `billing_keys.subscription_id` → 추가 (구독 연결용)

### 5. 기존 유지 (변경 없음)
- 프론트 diagnosis.html 결제 폼
- Cloudflare Pages Function 프록시
- DB payments 테이블 구조
- DB guest 트리거

---

## 남은 작업 (Cursor로 처리)

### 우선순위 1: payment_svc.py 재작성 (27KB, MCP 금지)
- `call_pay_auth()`: RSA 서명 제거
- `run_inicis_prepare()`: acceptmethod 응답 추가
- `run_billing_prepare()`: 전면 재작성 (INILiteKey + SHA512)
- `run_billing_return()`: 전면 재작성 (빌키 복호화, 정확한 파라미터)
- `run_billing_charge()`: 전면 재작성 (INIAPI Key + SHA512 + NVP)
- `run_billing_cancel()`: INIAPI Key 기반 재작성
- 신규 `run_refund()`: 전체/부분 취소

### 우선순위 2: routers/payment.py 라우터 업데이트
- `POST /payments/{id}/refund` — 전체취소 라우터
- `POST /payments/{id}/partial-refund` — 부분취소 라우터
- `/inicis/billing/return` — form POST 수신 (기존 JSON→form 변경)

### 우선순위 3: 이니시스 테스트
- F12 → Network → iframe 내부 응답 확인
- 빌키발급 테스트 (INIpayTest MID로는 불가 → 빌링 전용 테스트 MID 필요)

### 우선순위 4: Railway 환경변수 추가
```
INICIS_INILITE_KEY=     # 이니시스 가맹점관리자에서 확인
INICIS_INIAPI_KEY=      # 이니시스 가맹점관리자에서 확인
INICIS_BILLING_MID=     # 이니시스에서 빌링 전용 MID 발급받기
```

### 우선순위 5: 이니시스 매니저 확인사항
- 빌링(정기결제) 계약 여부 확인
- 빌링 전용 MID 발급 요청
- INILite Key / INIAPI Key 확인
- 테스트 MID INIpayTest의 빌링 사용 가능 여부

---

## 환경변수 정리

| 변수명 | 용도 | 현재값 | 실서비스 |
|--------|------|--------|---------|
| INICIS_MID | 단건결제 MID | INIpayTest | taieng4350 |
| INICIS_SIGN_KEY | 단건결제 서명키 | SU5JTElURV... | 가맹점관리자 |
| INICIS_BILLING_MID | 빌링 MID | (미설정) | 별도 발급 필요 |
| INICIS_INILITE_KEY | 빌키발급 키 | (미설정) | 가맹점관리자 |
| INICIS_INIAPI_KEY | 빌링승인/취소 키 | (미설정) | 가맹점관리자 |

---

## 파일 위치 정리

| 파일 | 레포 | 크기 | 편집 방법 |
|------|------|------|----------|
| `services/payment_helpers.py` | tai-api | 7KB | ✅ MCP 완료 |
| `schemas/payment.py` | tai-api | 6KB | ✅ MCP 완료 |
| `services/payment_svc.py` | tai-api | 27KB | ⏳ Cursor 필요 |
| `routers/payment.py` | tai-api | 13KB | ⏳ Cursor 필요 |
| `docs/INICIS_INTEGRATION_SPEC.md` | tai-api | 신규 | ✅ MCP 완료 |
| `docs/INICIS_CURSOR_INSTRUCTIONS.md` | tai-api | 신규 | ✅ MCP 완료 |
| `nexas/service/diagnosis.html` | taieng | 66KB | Cursor 필요 |
| `functions/_api/[[path]].js` | taieng | 소 | 유지 |

## 이니시스 매뉴얼 참고
- PC 일반결제: https://manual.inicis.com/pay/stdpay_pc.html
- 빌링(정기과금): https://manual.inicis.com/pay/bill.html
- 취소/환불: https://manual.inicis.com/pay/cancel.html
- 데이터암호화 데모: https://manual.inicis.com/pay/demo/hash.html
- 테스트 MID: INIpayTest, SignKey: SU5JTElURV9UUklQTEVERVNfS0VZU1RS
