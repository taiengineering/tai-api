# TAI Safe 확정 가격표 (Single Source of Truth)

> **최종 확정일:** 2026-04-17  
> **이 파일이 유일한 가격 기준입니다.** 다른 가격 문서는 히스토리 참고용.

---

## 1. SaaS 구독 (월 정기과금)

### 건물(BUILDING)

| 플랜 | 코드 | 월 요금 | 대상 |
|---|---|---|---|
| 기본관리 | BUILDING_BASIC | **59,000원** | 소형건물 (5,000㎡ 미만) |
| 정밀관리 | BUILDING_STANDARD | **145,000원** | 대형건물 (5,000㎡ 이상) |
| 대형건물 | BUILDING_CUSTOM | **249,000원** | 복합·특수건물 |

### 산업(INDUSTRY)

| 플랜 | 코드 | 월 요금 | 대상 |
|---|---|---|---|
| STARTER | INDUSTRY_STARTER_V2 | **79,000원** | 5~30인 겸직 |
| BUSINESS | INDUSTRY_BUSINESS_V2 | **149,000원** | 30~100인 |
| PRO | INDUSTRY_PRO | **249,000원** | 100인+ 전담 |
| CUSTOM | INDUSTRY_CUSTOM_V2 | **협의** | 대기업·다사업장 |

### 건설(CONSTRUCTION)

| 플랜 | 코드 | 월 요금 | 대상 |
|---|---|---|---|
| STANDARD | CONSTRUCTION_STANDARD_V2 | **145,000원** | 하도급 미사용 현장 |
| PREMIUM | CONSTRUCTION_PREMIUM_V2 | **385,000원** | 하도급 사용 현장 |
| CUSTOM | CONSTRUCTION_CUSTOM_V2 | **협의** | 대형건설사 |

### 공통 사항
- 포함 인원: 10명, 초과 시 3,000원/명
- 연간 결제 시 2개월 무료
- SMS/카카오/서류: 포함 (무제한)
- 크레딧 미노출 → 포함건수/초과건수로 UI 표시

---

## 2. 법령진단 단건 (1회성 결제)

### 건물

| 등급 | 코드 | 금액 |
|---|---|---|
| 무료진단 | BUILDING_FREE | **무료** |
| 소형건물 (5,000㎡ 미만) | BUILDING_V2 | **99,000원** |
| 대형건물 (5,000㎡ 이상) | BUILDING_LARGE_V2 | **249,000원** |

### 산업

| 등급 | 코드 | 금액 |
|---|---|---|
| 무료진단 | INDUSTRY_FREE | **무료** |
| 기본 | INDUSTRY_V2 | **79,000원** |
| 정밀 | INDUSTRY_STANDARD | **149,000원** |
| 종합 | INDUSTRY_PREMIUM | **249,000원** |

### 건설

| 등급 | 코드 | 금액 |
|---|---|---|
| 무료진단 | CONSTRUCTION_FREE | **무료** |
| 기본 | CONSTRUCTION | **145,000원** |
| 종합 | CONSTRUCTION_PREMIUM | **385,000원** |

> ~~특수(HAZARD_LOW/MID/HIGH)~~ 삭제됨 (is_active=false)

---

## 3. DB 테이블 매핑

| 가격 유형 | 테이블 | active 행 수 |
|---|---|---|
| SaaS 구독 | `price_saas_plan` | 10개 |
| 법령진단 단건 | `price_diagnosis_report` | 10개 |
| API | GET `/public/pricing/saas-plans` | SaaS 전체 반환 |
| API | GET `/public/pricing/diagnosis-reports` | 진단 전체 반환 |

---

## 4. 가격 변경 원칙

1. 가격은 런칭 후 올리기 매우 어려움 → 0고객 시점에 정확하게 설정
2. 이 문서 수정 → DB 동기화 → API 응답 확인 → 프론트 반영 순서
3. 가격 변경 이력은 `price_change_log` 테이블에 자동 기록
4. 금지 용어: 소개비/소개수수료/인력소개/소개료 → 플랫폼 이용료/연결 서비스료/매칭 서비스료 사용
