# BE-08: 진단 기반 SaaS 플랜 자동 추천 API

**작성일**: 2026-04-18  
**작성자**: 기획창 (심태왕 대표 × Claude)  
**선행조건**: BE-06 완료 (v2026.04 스키마), BE-07 완료 (ROI API)  
**배포 브랜치**: dev → PR → main  

---

## 배경

TAI SaaS 플랜은 sector별 3~4개 tier로 구성되어 있지만, 사용자가 스스로 적합한 플랜을 선택하기 어려움.  
법령진단 결과 데이터(sector, severity, obligation 수, worker_count)에 이미 플랜 추천에 필요한 모든 정보가 포함되어 있으므로, **별도 AI 없이 조건 분기 로직**으로 자동 추천 가능.

TAI 서비스 철학: "데이터를 입력하고, 그 데이터를 토대로 엔진이 판단하여 실행" → 플랜 추천도 동일 구조.

---

## 현재 DB 상태

### price_saas_plan (active 10건)

| sector_code | plan_code | display_name | monthly_base_fee | sort_order |
|---|---|---|---|---|
| BUILDING | BUILDING_BASIC | 기본관리 | 59,000 | 1 |
| BUILDING | BUILDING_STANDARD | 정밀관리 | 145,000 | 2 |
| BUILDING | BUILDING_CUSTOM | 대형건물 | 249,000 | 3 |
| INDUSTRY | INDUSTRY_STARTER_V2 | STARTER | 79,000 | 10 |
| INDUSTRY | INDUSTRY_BUSINESS_V2 | BUSINESS | 149,000 | 11 |
| INDUSTRY | INDUSTRY_PRO | PRO | 249,000 | 12 |
| INDUSTRY | INDUSTRY_CUSTOM_V2 | CUSTOM | 협의 | 13 |
| CONSTRUCTION | CONSTRUCTION_STANDARD_V2 | STANDARD | 145,000 | 20 |
| CONSTRUCTION | CONSTRUCTION_PREMIUM_V2 | PREMIUM | 385,000 | 21 |
| CONSTRUCTION | CONSTRUCTION_CUSTOM_V2 | CUSTOM | 협의 | 22 |

### 추천에 사용할 데이터 소스

| 데이터 | 소스 테이블 | 필드 |
|---|---|---|
| 섹터 | factories | sector |
| 작업자 수 | factories | total_worker_count_calc |
| 위험도 | factory_diagnosis_results | result_data→headline→severity |
| 의무 항목 수 | factory_diagnosis_results | jsonb_array_length(result_data→obligations) |
| 과태료 노출액 | factory_diagnosis_results | result_data→roi→total_exposure_krw |
| 규칙 수 | factory_diagnosis_results | result_data→rules 배열 길이 |

---

## TASK

### 1. 엔드포인트 생성

```
GET /diagnosis/{diagnosis_id}/recommend-plan
```

**응답 스키마:**
```json
{
  "recommended": {
    "plan_code": "INDUSTRY_BUSINESS_V2",
    "display_name": "BUSINESS",
    "monthly_base_fee": 149000,
    "sector_code": "INDUSTRY"
  },
  "reasons": [
    "의무 항목 128건 — STARTER(50건 이하)로는 관리 범위 부족",
    "위험도 HIGH — 자동 알림·누락 추적이 필수적인 수준",
    "작업자 85명 — 분산 점검 배정 기능 필요"
  ],
  "alternatives": [
    {
      "plan_code": "INDUSTRY_PRO",
      "display_name": "PRO",
      "monthly_base_fee": 249000,
      "note": "200명 이상 확장 또는 다공정 관리 시 권장"
    }
  ],
  "comparison": {
    "annual_plan_cost": 1788000,
    "single_penalty_avg": 3000000,
    "message": "TAI 1년 구독(178.8만원)은 과태료 1건(평균 300만원)보다 저렴합니다"
  }
}
```

### 2. 추천 로직 (조건 분기)

#### INDUSTRY

| 조건 | 추천 플랜 |
|---|---|
| severity=LOW AND obligations<50 AND workers<50 | STARTER (79K) |
| severity∈{MEDIUM,HIGH} OR obligations 50~150 OR workers 50~200 | BUSINESS (149K) |
| severity=CRITICAL OR obligations>150 OR workers 200~500 | PRO (249K) |
| workers>500 | CUSTOM (협의) |

#### BUILDING

| 조건 | 추천 플랜 |
|---|---|
| severity∈{LOW,MEDIUM} AND obligations<40 | 기본관리 (59K) |
| severity=HIGH OR obligations 40~100 | 정밀관리 (145K) |
| severity=CRITICAL OR obligations>100 | 대형건물 (249K) |

#### CONSTRUCTION

| 조건 | 추천 플랜 |
|---|---|
| severity∈{LOW,MEDIUM} AND obligations<120 | STANDARD (145K) |
| severity∈{HIGH,CRITICAL} OR obligations>120 | PREMIUM (385K) |
| workers>300 OR project_cost>15000000000 | CUSTOM (협의) |

**우선순위**: severity > obligations > workers (severity가 가장 강한 판단 기준)

### 3. reasons[] 생성 규칙

각 추천에 대해 **최소 2개, 최대 4개** 이유를 자동 생성:
- 의무 항목 수 기반: "의무 항목 {N}건 — {하위플랜}으로는 관리 범위 부족"
- 위험도 기반: "위험도 {severity} — {기능}이 필수적인 수준"
- 작업자 수 기반: "작업자 {N}명 — 분산 점검 배정 기능 필요"
- 비용 비교: "월 {X}원 = 과태료 {Y}건 대비 {Z}% 절감"

### 4. comparison 블록

BE-07 ROI 데이터 연동:
- `annual_plan_cost`: recommended.monthly_base_fee × 12
- `single_penalty_avg`: 3,000,000 (고정값 또는 result_data→roi→total_exposure_krw 기반)
- `message`: 자동 생성 문구

### 5. 파일 구조

```
routers/
  plan_recommend.py     ← 새 라우터
schemas/
  plan_recommend.py     ← Pydantic 응답 모델
```

main.py에 라우터 등록.

---

## 테스트

1. INDUSTRY + severity HIGH + obligations 128건 + workers 85명 → BUSINESS 추천 확인
2. BUILDING + severity LOW + obligations 22건 → 기본관리 추천 확인
3. CONSTRUCTION + severity CRITICAL + obligations 200건 → PREMIUM 추천 확인
4. INDUSTRY + workers 600명 → CUSTOM 추천 확인
5. reasons[] 최소 2개 포함 확인
6. comparison.annual_plan_cost 계산 정확성 확인

---

## 완료 조건

- [ ] GET /diagnosis/{diagnosis_id}/recommend-plan 정상 응답
- [ ] 3 sector × 각 tier 테스트 통과
- [ ] reasons[] 자동 생성 (최소 2개)
- [ ] comparison 블록 포함
- [ ] Pydantic 검증 통과
- [ ] 기존 API 영향 없음

---

## 금기

- AI/LLM API 호출 금지 (조건 분기 로직으로만 구현)
- price_saas_plan 테이블 구조 변경 금지
- main 직접 커밋 금지
- 하드코딩된 가격 금지 (DB에서 조회)
