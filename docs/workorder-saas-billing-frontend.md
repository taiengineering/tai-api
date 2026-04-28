# 작업지시서: SaaS + 진단 페이지 결제 수정 (Cursor)

> **우선순위**: 최상
> **대상 레포**: `taiengineering/taieng` (Cloudflare Pages `taieng-new`)
> **관련 규칙**: `docs/DEV_RULES_SERVICE_LAYER.md`

---

## 1. SaaS 페이지 (`nexas/service/saas.html`, 95KB)

### 1-1. accept-charset 수정
```html
<!-- 현재 -->
<form id="sp_inicis_form" accept-charset="euc-kr">

<!-- 수정 -->
<form id="sp_inicis_form" accept-charset="UTF-8">
```

### 1-2. 단건결제 → 빌링 결제 전환
현재: `INIStdPay.pay('sp_inicis_form')` 단건결제
변경: 구독결제 빌링 페이지로 리다이렉트

```javascript
// 기존 결제하기 버튼 함수 교체
function startBillingPayment(planCode, amount, goodname, productType) {
  // 빌링키 발급 페이지로 리다이렉트
  var url = 'https://taieng.co.kr/_api/payments/billing/pay'
    + '?user_id=' + userId
    + '&amount=' + amount
    + '&product_type=' + productType
    + '&goodname=' + encodeURIComponent(goodname)
    + '&plan_code=' + planCode;
  window.location.href = url;
}
```

### 1-3. api.taieng.co.kr 하드코딩 제거
HTML 내 `api.taieng.co.kr` → `taieng.co.kr/_api`로 모두 변경
(Cloudflare Pages Function 프록시 경유)

---

## 2. 진단 페이지 (`nexas/service/diagnosis.html`, 66KB)

### 2-1. closeUrl V023 에러 확인
페이지 내 `closeUrl` 또는 `returnUrl`에 `api.taieng.co.kr` 하드코딩이 있는지 확인.
있으면 `taieng.co.kr/_api`로 변경.

### 2-2. accept-charset 확인
`accept-charset="euc-kr"` → `UTF-8` 변경 (있는 경우)

---

## 3. 빌링 결제 플로우 (참고)

```
SaaS 페이지 "결제하기"
  → window.location.href = taieng.co.kr/_api/payments/billing/pay?...
  → billing_pay.html 자동 로드 (백엔드 template)
  → /payments/inicis/billing/prepare API 호출
  → 폼 채움 → inilitepay.inicis.com 자동 제출
  → 이니시스 빌링키 발급 화면
  → 카드 정보 입력 → 빌링키 발급
  → /payments/inicis/billing/return 결과 수신
  → billkey 저장 + 첫 결제 자동 실행 + 구독 활성화
  → /payments/result 리다이렉트
```

## 4. 검색 키워드 (변경 대상 찾기)

```
grep -n 'api\.taieng\.co\.kr' nexas/service/saas.html
grep -n 'api\.taieng\.co\.kr' nexas/service/diagnosis.html
grep -n 'euc-kr' nexas/service/saas.html
grep -n 'euc-kr' nexas/service/diagnosis.html
grep -n 'INIStdPay' nexas/service/saas.html
grep -n 'closeUrl' nexas/service/saas.html
grep -n 'closeUrl' nexas/service/diagnosis.html
```

## 5. 주의사항

- SaaS 빌링 MID는 단건결제 MID(`taieng4350`)와 다름 → 백엔드에서 `INICIS_BILLING_MID` 환경변수 사용
- 빌링 결제 백엔드 API는 이미 구현 완료: `/payments/inicis/billing/prepare`, `/billing/return`, `/billing/charge`
- `templates/payment/billing_pay.html` 백엔드 템플릿도 생성 완료
- VAT 10% 포함 결제금액 적용 필요 (`docs/workorder-payment-vat.md` 참조)
