# KG이니시스 결제 연동 스펙 v2.0 (매뉴얼 기반 재정리)

작성일: 2026-04-27  
기준 매뉴얼: https://manual.inicis.com/pay/stdpay_pc.html, https://manual.inicis.com/pay/bill.html, https://manual.inicis.com/pay/cancel.html

---

## 1. 서비스 구분과 키(Key) 체계

| 서비스 | 키 이름 | 위치 | 환경변수 |
|--------|---------|------|----------|
| PC 일반결제 (INIStdPay) | **Sign Key** | 가맹점관리자 > KEY정보 > 웹결제 | `INICIS_SIGN_KEY` |
| 빌링키 발급 (INILite) | **INILite Key** | 가맹점관리자 > KEY정보 > INILite/Express | `INICIS_INILITE_KEY` |
| 빌링승인/취소/환불 API | **INIAPI Key** | 가맹점관리자 > KEY정보 > INIAPI | `INICIS_INIAPI_KEY` |

> ⚠️ 3가지 키가 모두 다름! 기존 코드는 SignKey 하나로 모든 서비스를 처리하려 해서 빌링이 동작하지 않았음.

---

## 2. PC 단건결제 (INIStdPay) — 4단계 플로우

### STEP 1. 결제요청 (프론트 → 이니시스)

- JS: `https://stdpay.inicis.com/stdjs/INIStdPay.js`
- method: POST, charset: UTF-8

**서명 생성 (서버에서):**
```
signature    = SHA256("oid={oid}&price={price}&timestamp={timestamp}")
verification = SHA256("oid={oid}&price={price}&signKey={signKey}&timestamp={timestamp}")
mKey         = SHA256(signKey)
```

**필수 폼 파라미터:**
| 파라미터 | 값 | 비고 |
|----------|-----|------|
| version | "1.0" | 고정 |
| gopaymethod | "Card" 또는 빈값(전체) | |
| mid | 상점ID | env |
| oid | 주문번호 (Unique) | 서버생성 |
| price | 결제금액 (숫자만) | |
| timestamp | TimeInMillis(Long) | |
| use_chkfake | "Y" | 고정 |
| signature | SHA256 | oid,price,timestamp |
| verification | SHA256 | oid,price,signKey,timestamp |
| mKey | SHA256(signKey) | |
| currency | "WON" | |
| goodname | 상품명 | max 40byte |
| buyername | 구매자명 | max 30byte |
| buyertel | 구매자 전화 | |
| buyeremail | 구매자 이메일 | **필수** |
| returnUrl | 인증결과 수신 URL | **결제페이지와 동일 도메인** |
| closeUrl | 결제창 닫기 URL | |
| acceptmethod | "centerCd(Y)" | **필수** |

### STEP 2. 인증결과 (이니시스 → returnUrl)

이니시스가 returnUrl로 POST. 주요 파라미터:
- `resultCode`: "0000"=성공
- `authToken`: 승인 검증 토큰
- `authUrl`: 승인요청 URL (IDC별 다름)
- `idc_name`: IDC센터코드 (fc/ks/stg)
- `netCancelUrl`: 망취소 URL
- `orderNumber`: 주문번호

### STEP 3. 승인요청 (서버 → authUrl)

- Content-Type: application/x-www-form-urlencoded
- POST to authUrl (STEP2에서 받은 URL)

**서명 생성:**
```
signature    = SHA256("authToken={authToken}&timestamp={timestamp}")
verification = SHA256("authToken={authToken}&signKey={signKey}&timestamp={timestamp}")
```

**파라미터:**
| 파라미터 | 값 |
|----------|-----|
| mid | 상점ID |
| authToken | STEP2에서 받은 값 |
| timestamp | 새로운 TimeInMillis |
| signature | SHA256 (authToken, timestamp) |
| verification | SHA256 (authToken, signKey, timestamp) |
| charset | "UTF-8" |
| format | "JSON" |

### STEP 4. 승인결과

- resultCode "0000" = 성공
- tid: 거래번호 (취소 시 필요)
- applNum: 승인번호
- TotPrice: 결제금액
- CARD_Code, P_FN_NM 등

---

## 3. 빌링(구독) 결제 — 2단계 플로우

### 3-1. 빌링키 발급

**요청 URL:** `https://inilitepay.inicis.com/pay/card/billing`  
**Method:** POST, Content-Type: application/x-www-form-urlencoded, UTF-8

**hashData 생성:**
```
hashData = SHA512(price + mid + orderId + timestamp + INILiteKey)
```
> ⚠️ SHA512임! (단건은 SHA256) 그리고 INILiteKey 사용 (SignKey 아님)
> ⚠️ timestamp 형식: YYYYMMDDhhmmss (단건의 millis와 다름!)

**필수 파라미터:**
| 파라미터 | 값 |
|----------|-----|
| mid | 빌링용 상점ID |
| buyerTel | 구매자 전화 |
| buyerEmail | 구매자 이메일 |
| buyerName | 구매자명 |
| goodName | 상품명 |
| orderId | 주문번호 (Unique) |
| price | 금액 |
| timestamp | YYYYMMDDhhmmss |
| returnUrl | 결과수신 URL |
| hashData | SHA512 |

**발급결과 (returnUrl POST):**
- `resultCode`: "SUCCESS" = 성공 (단건의 "0000"과 다름!)
- `billkey`: AES256 암호화된 빌링키 (복호화 필요)
- `cardNumber`, `cardCode`, `cardCompanyName`
- `tid`: 거래번호

**빌링키 복호화:**
- AES256 복호화 후 UTF-8 URL Decode
- 복호화 키: INILite Key 사용

### 3-2. 빌링 승인 (서버-to-서버)

**요청 URL:** `https://iniapi.inicis.com/api/v1/billing`  
**Method:** POST  
**Content-Type:** application/x-www-form-urlencoded;charset=utf-8  
**Key:** INIAPI Key (또 다른 키!)

**hashData 생성 (V1 NVP):**
```
hashData = SHA512(INIAPIKey + type + paymethod + timestamp + clientIp + mid + moid + price + billKey)
```

**필수 파라미터:**
| 파라미터 | 값 |
|----------|-----|
| type | "Billing" 고정 |
| paymethod | "Card" |
| timestamp | YYYYMMDDhhmmss |
| clientIp | 서버 IP |
| mid | 상점ID |
| url | 가맹점 URL |
| moid | 주문번호 |
| goodName | 상품명 |
| buyerName | 구매자명 |
| buyerEmail | 구매자 이메일 |
| price | 결제금액 |
| billKey | 복호화된 빌링키 |
| authentification | "00" 고정 |
| hashData | SHA512 |

**승인결과:**
- resultCode "00" = 성공 (단건 "0000", 빌키발급 "SUCCESS"와 다름!)
- tid, payDate, payTime, payAuthCode

---

## 4. 취소/환불 API

**요청 URL:** `https://iniapi.inicis.com/api/v1/refund`  
**Key:** INIAPI Key

### 4-1. 전체취소

**hashData:**
```
hashData = SHA512(INIAPIKey + type + paymethod + timestamp + clientIp + mid + tid)
```

**파라미터:**
| 파라미터 | 값 |
|----------|-----|
| type | "Refund" 고정 |
| paymethod | 지불수단 ("Card", "Vacct" 등) |
| timestamp | YYYYMMDDhhmmss |
| clientIp | 서버 IP |
| mid | 상점ID |
| tid | 취소할 거래번호 |
| msg | 취소사유 |
| hashData | SHA512 |

### 4-2. 부분취소

**hashData:**
```
hashData = SHA512(INIAPIKey + type + paymethod + timestamp + clientIp + mid + tid + price + confirmPrice)
```

추가 파라미터: `price`(취소금액), `confirmPrice`(잔여금액)

---

## 5. 기존 코드 문제점 분석

### 단건결제 (`run_inicis_prepare`, `call_pay_auth`)

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| 1 | STEP1 signature | ✅ 정상 | SHA256(oid,price,timestamp) |
| 2 | STEP1 verification | ✅ 정상 | SHA256(oid,price,signKey,timestamp) |
| 3 | STEP1 mKey | ✅ 정상 | SHA256(signKey) |
| 4 | STEP3 signature | ✅ 정상 | SHA256(authToken,timestamp) |
| 5 | STEP3 verification | ✅ 정상 | SHA256(authToken,signKey,timestamp) |
| 6 | acceptmethod | ⚠️ 프론트에서 설정 | 서버 응답에 포함 필요 |
| 7 | buyeremail | ⚠️ 빈값 허용 | 매뉴얼상 필수 |

### 빌링(구독) — **대부분 잘못됨**

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| 8 | 키 체계 | ❌ 완전히 틀림 | SignKey 하나로 모든 서비스 처리. INILiteKey/INIAPIKey 필요 |
| 9 | 빌키발급 URL | ❌ 틀림 | 현재 없음. `inilitepay.inicis.com/pay/card/billing`으로 POST 필요 |
| 10 | 빌키발급 해시 | ❌ SHA256 사용 | SHA512(price+mid+orderId+timestamp+INILiteKey) 이어야 함 |
| 11 | timestamp 형식 | ❌ millis 사용 | 빌링은 YYYYMMDDhhmmss 형식 |
| 12 | 빌키 복호화 | ❌ 없음 | AES256 복호화 로직 필요 |
| 13 | 빌링승인 해시 | ❌ 틀림 | SHA512(INIAPIKey+type+paymethod+...) 이어야 함 |
| 14 | 빌링승인 URL | ❌ 틀림 | `iniapi.inicis.com/api/v1/billing` 이어야 함 |
| 15 | 빌링승인 파라미터 | ❌ 대부분 누락 | type, paymethod, clientIp, authentification 등 |
| 16 | 취소/환불 API | ❌ 없음 | 완전히 새로 구현 필요 |

---

## 6. 환경변수 정리

### 현재 (테스트)
```
INICIS_MID=INIpayTest
INICIS_SIGN_KEY=SU5JTElURV9UUklQTEVERVNfS0VZU1RS
```

### 추가 필요 (빌링/취소용)
```
INICIS_BILLING_MID=          # 빌링 전용 MID (이니시스에서 별도 발급)
INICIS_INILITE_KEY=          # 빌링키 발급용 키
INICIS_INIAPI_KEY=           # 빌링승인/취소/환불 API 키
```

### 실서비스 전환 시
```
INICIS_MID=taieng4350
INICIS_SIGN_KEY=실제키
INICIS_BILLING_MID=빌링MID
INICIS_INILITE_KEY=실제키
INICIS_INIAPI_KEY=실제키
```

---

## 7. 방화벽 정보

| 서비스 | 스테이징 | 운영 | PORT |
|--------|----------|------|------|
| 일반결제 | stgstdpay.inicis.com (183.109.71.83) | fcstdpay.inicis.com (118.129.210.86), ksstdpay.inicis.com (183.109.71.30) | 443 |
| 빌링키발급 | — | inilitepay.inicis.com (183.109.71.67, 118.129.210.29) | 443 |
| 빌링승인/취소 | stginiapi.inicis.com (118.129.210.153) | iniapi.inicis.com (118.129.210.166, 183.109.71.79) | 443 |

모두 OUTBOUND, TLS 1.2 이상.

---

## 8. 파일 구조 (변경 계획)

```
services/
  payment_helpers.py   — 순수 유틸 (해시, 타임스탬프, 키 로딩)
  payment_svc.py       — 비즈니스 로직 (단건/빌링/취소)
schemas/
  payment.py           — Pydantic 스키마
routers/
  payment.py           — HTTP 라우터 (비즈니스 로직 없음)
templates/payment/
  pricing.html         — 결제 선택 페이지
  result.html          — 결제 결과 페이지
  billing_terms.html   — 구독 이용안내
```
