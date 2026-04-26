# 세션 로그 — 2026-04-26 (SaaS·법령진단 리뷰 반영 + 가격 정책 전면 수정)

## 완료 작업

### 1. diagnosis.html — 리뷰 반영 재구성
- 섹션 순서: 히어로 → 공감 → 처벌 경고(올림) → 3분 흐름 → 무료 샘플 → 유료 킬러 → 요금표(올림) → 파일럿 → FAQ → SaaS → CTA
- 삭제: 장점 6개 섹션, 유료 목업 단독 섹션, 관공서 점검대응, 가짜 판례
- 추가: FAQ 5개, 파일럿 배너, 중간 CTA, 입력 미리보기 한 줄
- 커밋: taieng 레포 다수 (diagnosis.html)

### 2. 무료 결과 목업 — 실제 페이지 구조 반영
- 기존: "적용 법령 12개 / 선임 3건 / 점검 18건"
- 변경: HIGH RISK / 205건 / 4칸 카테고리 / 긴급 D-day 4건 / 법령 뱃지 18개 / 법률별 상세 / 유료 잠금
- 맥락 뱃지: "건물 · 제조업 · 50인 · 500㎡ 기준"
- 커밋: taieng `92dc681`

### 3. 샘플 링크 동선 개선
- 기존: "샘플 보기" → diagnosis-sample.html(설명) → 실제 리포트 (2클릭)
- 변경: "샘플 보기" → paid-diagnosis-result.html?token=DEMO-CON-2026 직접 연결 (1클릭)
- diagnosis-sample.html은 "리포트 구성 자세히 알아보기" 보조 링크로 격하
- 중복 링크 삭제: "실제 인터랙티브 리포트 열기", "인터랙티브 데모 열기"
- 커밋: taieng `77b4643`

### 4. diagnosis-sample.html 신규 생성
- 유료 리포트 7가지 구성을 목업으로 보여주는 별도 페이지
- URL: https://new.taieng.co.kr/service/diagnosis-sample.html
- 커밋: taieng 레포

### 5. 가격 정책 전면 수정 (PRICING_FINAL.md 3회 업데이트)
- 커밋 `e894200`: 시설당 과금, 인원 무제한, 입력 범위 차이, CUSTOM 재정의, 마케팅 표기 원칙 추가
- 커밋 `3a85764`: 건물 BASIC(59K) 삭제, DB 동기화 SQL 추가
- 커밋 `15a1ab9`: DB 실제 코드 매핑 정리 (BUILDING_LITE 비활성 기록)

### 6. 법령진단 가격표 수정
- "업종 구분 없이" → 삭제
- "법개정 자동반영" → "개정된 최신법으로 진단"
- "관공서 점검대응 가이드" → 삭제
- 산업: 인원수 → 사업장/위험시설·공정/시설 범위
- 건물: 면적 기준 법조항 차이 설명
- 건설: 공사금액 기준 법조항 차이 설명
- 하단: "가격 차이는 적용되는 법이 달라지기 때문"

### 7. SaaS 요금제 수정 (saas.html)
- 건물 59K 카드 삭제 (BUILDING_LITE → is_active=false)
- 인원수 삭제 (5~30인/30~100인/100인+)
- 산업: 상황 중심 문구 ("건물과 특수설비만 있는 사업장" / "공정이 있다면" / "설비까지 있다면")
- BUSINESS·PRO: "세팅 대행 (유료)"
- 건설: "하도급 관리 모든 플랜" + 기능 동일
- CUSTOM: "별도 커스터마이징" (API/전담CS/SLA 삭제)
- "시설 1개 기준 과금 · 관리자/작업자 무제한"

### 8. DB 동기화
- `BUILDING_LITE` → is_active=false
- display_name 업데이트: 정밀관리(145K), 대형건물(249K), Enterprise
- description 전체 업데이트 (등록 범위 / 세팅 대행 / 하도급)
- max_users, included_users → 99999 (무제한)
- CONSTRUCTION_PREMIUM_V2: 299K → 385K (SaaS 가격)

### 9. 인프라 이전 계획 확정
- 현재: Railway 싱가포르 + Supabase 싱가포르 (도쿄 아님, 확인 완료)
- 이전: Railway → Google 서울(asia-northeast3) + Supabase → AWS 서울(ap-northeast-2)
- 시점: 기능 완성 직후 ~ 첫 고객 유입 전
- Supabase 서울 리전 가용 확인 (Pro 플랜, 한도 문제 없음)

## 핵심 결정 사항

### TAI 가격 원칙 (대표 직접 지시)
1. **시설당 과금** (사업장 아님)
2. **관리자/작업자 무제한**
3. **기능은 모든 플랜에서 동일** — 입력 범위가 다름
4. **"많이 넣으면 많이 나온다"** = TAI의 방식
5. 건물 BASIC(59K) 삭제 — 진단 입력이 FREE/PAID 2단계뿐, 중간 티어 근거 없음
6. CUSTOM = 별도 커스터마이징 (대형 사업장 아님, API/전담CS 불가, 1인 창업)
7. BUSINESS·PRO에 세팅 대행(유료)

### 마케팅 표현 원칙
- "가격 차이는 기능이 달라서가 아닙니다. 적용되는 법이 달라지기 때문입니다."
- TurboTax 모델과 유사: 소득 유형이 다르면 세법이 다름 → TAI: 등록 범위가 다르면 산안법 조항이 다름
- Land and Expand: 79K 시작 → 사용하면서 자연스럽게 PRO(249K)로 확장

## DB 코드 매핑 (최종)

| sector | plan_code | monthly | display |
|---|---|---|---|
| BUILDING | ~~BUILDING_LITE~~ | ~~59K~~ | ~~삭제~~ |
| BUILDING | BUILDING_BASIC | 145K | 정밀관리 |
| BUILDING | BUILDING_STANDARD | 249K | 대형건물 |
| BUILDING | BUILDING_CUSTOM | 협의 | Enterprise |
| INDUSTRY | INDUSTRY_STARTER_V2 | 79K | STARTER |
| INDUSTRY | INDUSTRY_BUSINESS_V2 | 149K | BUSINESS |
| INDUSTRY | INDUSTRY_PRO | 249K | PRO |
| INDUSTRY | INDUSTRY_CUSTOM_V2 | 협의 | CUSTOM |
| CONSTRUCTION | CONSTRUCTION_STANDARD_V2 | 145K | STANDARD |
| CONSTRUCTION | CONSTRUCTION_PREMIUM_V2 | 385K | PREMIUM |
| CONSTRUCTION | CONSTRUCTION_CUSTOM_V2 | 협의 | CUSTOM |

## 미해결 이슈

1. **카운터 0 표시** — IntersectionObserver + requestAnimationFrame 비활성 탭 문제
2. **diagnosis-sample.html 헤더/푸터** — header.js/footer.js 로딩 확인 필요
3. **산업 가격표 "위험시설/공정까지"** — 정확한 표현 확인 필요
