# KG이니시스 결제 연동 작업 내역 (2026-04-27)

## 세션 요약
이니시스 PC 웹표준 결제(INIStdPay) 연동 디버깅. 결제창이 뜨지 않는 문제를 매뉴얼 기반으로 추적·수정.

---

## 완료된 작업

### 1. 백엔드 수정 (tai-api)
- `schemas/payment.py`: `DIAG_BUILDING` 등 프론트 product_type → `DIAGNOSIS`로 자동 매핑
- `schemas/payment.py`: 비-UUID user_id(`guest_xxx`) → `uuid4()` 자동 변환

### 2. DB 마이그레이션 (Supabase)
- `allow_guest_payment_nullable_user_id`: payments.user_id nullable + FK ON DELETE SET NULL
- `guest_payment_trigger`: BEFORE INSERT 트리거 — 비회원 user_id가 auth.users에 없으면 NULL 처리

### 3. 프론트 수정 (taieng)
- `nexas/service/diagnosis.html`: 로그인 체크 제거, guest 폴백, Authorization 선택적
- `nexas/service/diagnosis.html`: returnUrl/closeUrl → `new.taieng.co.kr/_api/*` 프록시 경유
- `nexas/service/diagnosis.html`: accept-charset `euc-kr` → `UTF-8`, acceptmethod `CARDONLY:CARDPOINT:centerCd(Y)` → `centerCd(Y)`
- `nexas/assets/js/inicis-fix.js`: 폼 파라미터 런타임 패치 (charset + acceptmethod)

### 4. Cloudflare Pages Function (taieng)
- `functions/_api/[[path]].js`: `new.taieng.co.kr/_api/*` → `api.taieng.co.kr/*` 프록시
- 목적: 이니시스 V023 에러 방지 (결제요청 페이지와 returnUrl 동일 도메인)
- 동작 확인: `https://new.taieng.co.kr/_api/health` → 200 OK

### 5. Railway 환경변수 (임시 테스트)
- `INICIS_MID` = `INIpayTest` (카드사 심사 후 `taieng4350`으로 원복)
- `INICIS_SIGN_KEY` = `SU5JTElURV9UUklQTEVERVNfS0VZU1RS` (카드사 심사 후 실제 키로 원복)

---

## 현재 상태 (🔴 미해결)

### 증상
- `INIStdPay.pay()` 호출 성공
- 이니시스 모달(반투명 오버레이) 표시됨
- 이니시스 광고 팝업 표시됨 (ds-cdn.inicis.com)
- **BUT: 광고 X 닫은 후 실제 카드 결제 폼이 뜨지 않음**
- 에러 리다이렉트는 없음 (페이지가 diagnosis URL에 유지)

### 디버깅으로 확인된 사항
1. API `/payments/inicis/prepare` → 200 성공, MID=INIpayTest
2. 폼 파라미터 전부 정상 채워짐 (mid, oid, price, signature, mKey, verification 등)
3. `stdpay.inicis.com/payMain/pay` POST → 200 반환
4. iframe 존재 (1704x929, display:block, visible)
5. iframe src = empty (POST target이므로 정상)
6. `INIStdPay.boolInitDone = true`
7. `gopaymethod`를 빈값으로 변경 시 → V023 에러 확인 ("휴대폰결제는 HPP 필수")
8. `gopaymethod="Card"` + `acceptmethod="centerCd(Y)"` → 에러 리다이렉트 없음

### 남은 가능성
1. **iframe 내부에 이니시스 에러 메시지가 표시되고 있을 수 있음** (크로스 오리진이라 JS로 읽기 불가)
2. 이니시스 테스트 MID(`INIpayTest`)가 특정 도메인에서만 동작할 수 있음
3. signature/verification/mKey 계산이 INIpayTest 기준으로 올바른지 재검증 필요
4. 이니시스 공식 샘플(PHP/JSP)과 직접 비교 필요

---

## 다음 세션에서 해야 할 작업

### 우선순위 1: 이니시스 공식 샘플 비교
1. https://manual.inicis.com/stdpay/ 에서 PHP/JSP 샘플 다운로드
2. 샘플의 signature, verification, mKey 생성 로직과 `tai-api/services/payment_helpers.py` 비교
3. 특히 mKey 생성: `SHA256(signKey)` vs 매뉴얼 방식 일치 확인
4. verification 생성: `SHA256("oid={oid}&price={price}&signKey={signKey}&timestamp={timestamp}")` 확인

### 우선순위 2: iframe 에러 직접 확인
1. 대표님 브라우저에서 F12 → Network 탭 → `stdpay.inicis.com/payMain/pay` 응답 본문 확인
2. 또는 F12 → Elements → iframe 선택 → 내부 HTML 확인
3. 에러 코드(V013/V014/V016/V021/V023 등)가 있으면 해당 FAQ 참고

### 우선순위 3: 카드사 심사 후 실 MID 테스트
1. Railway 환경변수 원복: `INICIS_MID=taieng4350`, `INICIS_SIGN_KEY=실제키`
2. 실 MID로 결제창 동작 확인
3. 이니시스 매니저에게 "연동 완료" 회신

---

## 파일 위치 정리

| 파일 | 레포 | 설명 |
|------|------|------|
| `schemas/payment.py` | tai-api | DIAG_* 매핑 + guest UUID 변환 |
| `services/payment_helpers.py` | tai-api | 이니시스 prepare 로직 (signature/mKey/verification 생성) |
| `routers/payment.py` | tai-api | 결제 API 라우터 |
| `nexas/service/diagnosis.html` | taieng | 결제 페이지 (66KB, Cursor로 편집) |
| `nexas/assets/js/inicis-fix.js` | taieng | 폼 파라미터 런타임 패치 |
| `functions/_api/[[path]].js` | taieng | Cloudflare Pages Function 프록시 |
| `docs/INICIS_WORK_LOG.md` | tai-api | 이 문서 |

## 이니시스 매뉴얼 참고
- PC 일반결제: https://manual.inicis.com/pay/stdpay_pc.html
- FAQ: https://www.inicis.com/blog/archives/category/cs/cs_best/모듈연동-faq/웹표준(PC
- 테스트 MID: `INIpayTest`, SignKey: `SU5JTElURV9UUklQTEVERVNfS0VZU1RS`
