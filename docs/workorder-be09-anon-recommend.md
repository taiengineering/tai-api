# BE-09: 익명 진단 플랜 추천 API

**작성일**: 2026-04-18
**작성자**: 기획창
**선행조건**: BE-08 완료 (diagnosis_plan_recommend.py)
**배포 브랜치**: dev → PR → main

---

## 배경

무료진단(anonymous) 결과 페이지에서 플랜 추천을 표시하려면,
BE-08의 `GET /diagnosis/{diagnosis_id}/recommend-plan`을 호출해야 하는데
**익명 진단은 factory_diagnosis_results가 아닌 anonymous_diagnosis_results에 저장**됨.

따라서 anonymous 토큰 기반으로 플랜 추천을 반환하는 별도 엔드포인트가 필요.

---

## TASK 1: 엔드포인트 추가

### 파일

`routers/anonymous_diagnosis.py` 에 엔드포인트 추가.

### 엔드포인트

```
GET /anonymous-diagnosis/{token}/recommend-plan
```

### 동작

1. `anonymous_diagnosis_results` 에서 token으로 레코드 조회
2. `full_result`에서 추천에 필요한 데이터 추출:
   - `sector`: full_result.sector
   - `severity`: full_result.headline.severity (없으면 full_result.risk_level)
   - `obl_count`: len(full_result.key_obligations) 또는 full_result.applicable_count
   - `workers`: input_data.workers
3. BE-08의 추천 로직 함수 재사용 (import):
   - `_recommend_industry(severity, obl_cnt, workers)`
   - `_recommend_building(severity, obl_cnt, workers)`
   - `_recommend_construction(severity, obl_cnt, workers)`
   - `_build_alternatives(sector, plan_code)`
   - `_build_comparison(plan_code, penalty_risk_krw)`
4. BE-08과 동일한 응답 스키마 반환

### 응답 스키마

BE-08 응답과 동일:
```json
{
  "status": "success",
  "recommended": {
    "plan_code": "INDUSTRY_BUSINESS_V2",
    "plan_name": "산업 BUSINESS",
    "monthly_krw": 149000,
    "is_custom": false
  },
  "reasons": [...],
  "alternatives": { "lower": {...}, "upper": {...} },
  "comparison": {
    "annual_penalty_risk_krw": 87000000,
    "tai_safe_annual_krw": 1788000,
    "note": "..."
  },
  "input_summary": {
    "severity": "HIGH",
    "obl_count": 128,
    "workers": 85,
    "sector": "INDUSTRY"
  }
}
```

### import 구조

```python
# anonymous_diagnosis.py 상단에 추가
from routers.diagnosis_plan_recommend import (
    _recommend_industry,
    _recommend_building,
    _recommend_construction,
    _build_alternatives,
    _build_comparison,
    _PLANS,
)
```

### 에러 처리

| 상황 | HTTP | 메시지 |
|---|---|---|
| 토큰 없음/만료 | 404/410 | 기존 _fetch_row 로직 재사용 |
| sector 인식 불가 | 422 | "지원하지 않는 섹터입니다" |
| full_result 없음 | 500 | "진단 결과가 불완전합니다" |

### 라우트 등록 위치

기존 anonymous_diagnosis.py 내부 — `/{token}` 보다 **위**에 등록.
(콘크리트 경로 우선 원칙: `/{token}/recommend-plan` > `/{token}`)

---

## TASK 2: sector 매핑 보정

anonymous_diagnosis의 sector는 `MANUFACTURING` 등을 사용할 수 있음.
추천 로직의 sector는 `INDUSTRY`만 인식.

```python
SECTOR_NORMALIZE = {
    "INDUSTRY": "INDUSTRY",
    "MANUFACTURING": "INDUSTRY",
    "BUILDING": "BUILDING",
    "CONSTRUCTION": "CONSTRUCTION",
    "SPECIAL_FACILITY": "BUILDING",  # fallback
}
```

---

## 테스트

1. 무료진단 실행 → 토큰 획득 → `GET /anonymous-diagnosis/{token}/recommend-plan` 호출
2. INDUSTRY 토큰 → INDUSTRY 플랜 추천 확인
3. BUILDING 토큰 → BUILDING 플랜 추천 확인
4. 만료 토큰 → 410 에러 확인
5. reasons[] 최소 2개 포함 확인
6. comparison 블록 포함 확인

---

## 완료 조건

- [ ] `GET /anonymous-diagnosis/{token}/recommend-plan` 정상 응답
- [ ] BE-08 추천 로직 함수 재사용 (코드 중복 없음)
- [ ] sector 정규화 (MANUFACTURING→INDUSTRY 등)
- [ ] 만료/없는 토큰 에러 처리
- [ ] main.py 추가 등록 불필요 (기존 anonymous_diagnosis 라우터 내부)

---

## 금기

- 추천 로직 복사-붙여넣기 금지 (BE-08 함수 import)
- AI/LLM 호출 금지
- anonymous_diagnosis_results 테이블 구조 변경 금지
- main 직접 커밋 금지
