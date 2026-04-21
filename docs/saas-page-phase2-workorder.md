# SaaS 페이지 Phase 2 보완 작업지시

> 파일: `nexas/service/saas.html` (taieng 레포, Cursor 필수)
> 기준: `docs/PRICING_FINAL.md` (tai-api dev) — 유일한 가격 기준

---

## 1. 요금제 가격/플랜명 전체 수정 [필수]

### 건물(BUILDING) — 3티어로 수정 (STANDARD 145K 카드 신규 추가)

| 순서 | 플랜명 | 코드 | 월 요금 | 대상 |
|---|---|---|---|---|
| 1 | 기본관리 | BUILDING_BASIC | 59,000원 | 소형건물 (5,000㎡ 미만) |
| 2 | **정밀관리** | **BUILDING_STANDARD** | **145,000원** | **대형건물 (5,000㎡ 이상)** |
| 3 | 대형건물 | BUILDING_CUSTOM | 249,000원 | 복합·특수건물 |

현재 STARTER → "기본관리", PRO → "대형건물" 으로 명칭 변경.
STANDARD(정밀관리) 카드 새로 추가. Enterprise 카드는 유지.

STANDARD 카드 내용:
```
정밀관리
145,000원 /월 · VAT 별도 · 건물 1개

기본관리 플랜 전체 포함
소방시설 자체점검 연동
승강기 검사 주기 관리
위반 위험 사전 알림

[결제하기] → spPay(event,'SAAS','BUILDING_STANDARD',145000,'건물 정밀관리')
```

PRO(대형건물) 카드 수정:
```
대형건물
249,000원 /월 · VAT 별도 · 건물 1개

정밀관리 플랜 전체 포함
석면·에너지 점검 일정
법정 서식 자동 생성

[결제하기] → spPay(event,'SAAS','BUILDING_CUSTOM',249000,'건물 대형건물')
```

### 산업(INDUSTRY) — 플랜명 순서 수정

현재 페이지: STARTER 79K → **PRO** 149K → **BUSINESS** 249K
PRICING_FINAL: STARTER 79K → **BUSINESS** 149K → **PRO** 249K

| 순서 | 플랜명 | 코드 | 월 요금 | 대상 |
|---|---|---|---|---|
| 1 | STARTER | INDUSTRY_STARTER_V2 | 79,000원 | 5~30인 겸직 |
| 2 | **BUSINESS** | **INDUSTRY_BUSINESS_V2** | **149,000원** | **30~100인** |
| 3 | **PRO** | **INDUSTRY_PRO** | **249,000원** | **100인+ 전담** |
| 4 | CUSTOM | INDUSTRY_CUSTOM_V2 | 협의 | 대기업 |

수정사항:
- 2번째 카드: PRO → BUSINESS, planCode: INDUSTRY_BUSINESS_V2
- 3번째 카드: BUSINESS → PRO, planCode: INDUSTRY_PRO
- spPay onclick의 planCode와 goodname도 수정

### 건설(CONSTRUCTION) — 플랜명 수정

| 순서 | 플랜명 | 코드 | 월 요금 | 대상 |
|---|---|---|---|---|
| 1 | **STANDARD** | **CONSTRUCTION_STANDARD_V2** | 145,000원 | 50억 미만 |
| 2 | **PREMIUM** | **CONSTRUCTION_PREMIUM_V2** | 385,000원 | 50억+ |
| 3 | **CUSTOM** | **CONSTRUCTION_CUSTOM_V2** | 협의 | 대형건설사 |

현재 STARTER → STANDARD, PRO → PREMIUM, ENTERPRISE → CUSTOM
spPay planCode도 함께 수정.

---

## 2. 기능⑤ 복원: "기상 작업중지 감시" [필수]

현재 기능⑤ = "감사·감독 앞에서 '여기 있습니다'"
→ "기상 작업중지 자동 감시"로 교체

```
헤드라인: "폭염특보인데
         작업 계속해도 되는 건가?"

해결:
• 기상청 API 30분 간격 자동 확인
• 강풍·폭염·한파 법정 기준 감지
• 작업중지 권고 알림 자동 발송
• 이행 기록 자동 보관
```

목업: 날씨 대시보드 위젯 (온도/풍속 + 경고 상태)
좌우 배치: 텍스트 좌, 폰 우 (홀수번째 기능)

---

## 3. 도입 섹션: 세팅 대행 안내 추가 [권장]

도입 4단계 하단에 박스 추가:
```
"직접 세팅이 어려우시면 TAI가 대행합니다."
기본 20만원 + 설비당 2~3만원 (견적 기반)
[세팅 대행 문의 →]
```

---

## 4. 카운트업 동작 확인 [확인]

sp-count-scope 2개, #sp-hero-count-scope 1개 존재 확인.
실제 카운트업 애니메이션이 스크롤 시 동작하는지 육안 확인 필요:
- [ ] 히어로 127+ 카운트업
- [ ] 법령엔진 473 / 33,845 카운트업

---

## Cursor 프롬프트

```
SaaS 페이지 Phase 2 — nexas/service/saas.html

기준: tai-api 레포 docs/saas-page-phase2-workorder.md (dev)

수정 4건:

1. 건물 요금제: STANDARD 카드 신규 추가 (STARTER와 PRO 사이)
   - 명칭: 기본관리(59K) → 정밀관리(145K, 신규) → 대형건물(249K)
   - 기존 STARTER → "기본관리", PRO → "대형건물" 명칭 변경
   - STANDARD: spPay(event,'SAAS','BUILDING_STANDARD',145000,'건물 정밀관리')
   - PRO(대형건물): planCode를 BUILDING_CUSTOM으로 변경
   - PRO에서 소방점검/승강기/위반알림 제거 → STANDARD로 이동

2. 산업 요금제: 2번째↔3번째 카드 이름 교환
   - 2번째: PRO → BUSINESS (149K), planCode: INDUSTRY_BUSINESS_V2
   - 3번째: BUSINESS → PRO (249K), planCode: INDUSTRY_PRO
   - ENTERPRISE → CUSTOM 명칭 변경

3. 건설 요금제: 플랜명 변경
   - STARTER → STANDARD, planCode: CONSTRUCTION_STANDARD_V2
   - PRO → PREMIUM, planCode: CONSTRUCTION_PREMIUM_V2
   - ENTERPRISE → CUSTOM

4. 기능⑤: "감사 대응" → "기상 작업중지 감시"
   - 헤드라인: "폭염특보인데 작업 계속해도 되는 건가?"
   - 날씨 대시보드 목업 (온도/풍속 + 경고)

5. 도입 섹션 하단에 세팅 대행 안내 박스
   - "기본 20만원 + 설비당 2~3만원"

절대 수정 금지: spPay 함수 본체, sp_inicis_form, 섹터탭 IIFE, 카운트업 IIFE
수정하는 것: spPay의 onclick 호출 인자(planCode, amount, goodname)만 변경
```
