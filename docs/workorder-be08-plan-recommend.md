# BE-08: 진단 기반 SaaS 플랜 자동 추천 API

**작성일:** 2026-04-18  
**파일:** `routers/diagnosis_plan_recommend.py` v1.0.0  
**main.py:** v5.29.0  
**PR:** https://github.com/taiengineering/tai-api/pull/1 (dev→main)

---

## 엔드포인트

```
GET /diagnosis/{diagnosis_id}/recommend-plan
```

- 인증 불필요 (공개) — 진단 결과 페이지에서 바로 소비
- diagnosis_id는 factory_diagnosis_results.id

---

## 추천 로직

AI 없음. 조건 분기만. 우선순위: **severity > obligations 수 > 작업자 수**

### INDUSTRY 추천 규칙

| 조건 | 추천 플랜 |
|---|---|
| 작업자 > 500 | CUSTOM (협의) |
| CRITICAL 또는 의무 > 150 또는 작업자 > 200 | PRO 249K |
| MEDIUM/HIGH 또는 의무 50~150 | BUSINESS 149K |
| LOW + 의무 < 50 + 작업자 < 50 | STARTER 79K |

### BUILDING 추천 규칙

| 조건 | 추천 플랜 |
|---|---|
| CRITICAL 또는 의무 > 100 | CUSTOM 249K |
| MEDIUM/HIGH 또는 의무 30~100 | STANDARD 145K |
| 그 외 | BASIC 59K |

### CONSTRUCTION 추천 규칙

| 조건 | 추천 플랜 |
|---|---|
| 작업자 > 300 | CUSTOM (협의) |
| CRITICAL/HIGH 또는 의무 > 80 | PREMIUM 385K |
| 그 외 | STANDARD 145K |

---

## 입력 데이터

| 소스 | 필드 | 설명 |
|---|---|---|
| `factory_diagnosis_results.result_data` | `headline.severity` | LOW/MEDIUM/HIGH/CRITICAL |
| `factory_diagnosis_results.result_data` | `obligations[]` | 의무 배열 (비면 rule_count 대체) |
| `factory_diagnosis_results` | `rule_count` | obligations 미생성 시 fallback |
| `factory_diagnosis_results.result_data` | `roi.annual_penalty_risk_krw` | 과태료 비교용 |
| `factories` | `total_worker_count_calc` | 작업자 수 (없으면 employee_count) |
| `factories` | `sector` | INDUSTRY/BUILDING/CONSTRUCTION |

---

## 응답 구조

```json
{
  "status": "success",
  "diagnosis_id": "uuid",
  "sector": "INDUSTRY",
  "input_summary": {
    "severity": "HIGH",
    "obl_count": 112,
    "workers": 499,
    "stage": 1
  },
  "recommended": {
    "plan_code": "INDUSTRY_PRO",
    "plan_name": "산업 PRO",
    "monthly_krw": 249000,
    "is_custom": false,
    "pricing_note": "월 249,000원 (부가세 별도)"
  },
  "reasons": [
    "위험도 HIGH — 체계적인 점검 일정 자동화가 효과적입니다",
    "법적 의무 112건 — BUSINESS 플랜의 자동 일정 생성으로 누락 방지",
    "작업자 499명 — 200인 초과 사업장 전담 기능이 포함됩니다",
    "무제한 설비 등록 + API 연동 + 전담 지원 포함"
  ],
  "alternatives": {
    "lower": {
      "plan_code": "INDUSTRY_BUSINESS_V2",
      "plan_name": "산업 BUSINESS",
      "monthly": 149000,
      "note": "기본 기능 위주로 비용을 줄이고 싶다면"
    },
    "upper": {
      "plan_code": "INDUSTRY_CUSTOM_V2",
      "plan_name": "산업 CUSTOM",
      "monthly": null,
      "note": "더 많은 기능과 지원이 필요하다면"
    }
  },
  "comparison": {
    "annual_penalty_risk_krw": 213000000,
    "tai_safe_annual_krw": 2988000,
    "tai_safe_monthly_krw": 249000,
    "risk_reduction_ratio": 71.3,
    "estimated_savings_krw": 210012000,
    "note": "TAI Safe 연간 2,988,000원으로 최대 213,000,000원 과태료 위험을 관리합니다"
  },
  "cta": {
    "primary":   {"label": "지금 시작하기",       "action": "go_pricing", "plan_code": "INDUSTRY_PRO"},
    "secondary": {"label": "전체 요금제 비교하기", "action": "go_pricing_all"}
  }
}
```

---

## 핵심 원칙

- AI 개발 비용 0원 — 기존 법령엔진 데이터 + 조건 분기만
- obligations 배열이 비어있는 경우(stage 1/4) rule_count로 자동 대체
- TAI 철학: 데이터 → 엔진 판단 → 자동 실행
- FN-06(프론트 추천 UI)가 이 API를 소비

---

## 실제 DB 검증 (2026-04-18)

| diagnosis_id | sector | severity | obl_cnt | workers | 추천 |
|---|---|---|---|---|---|
| f48fbff2 | INDUSTRY | CRITICAL | 0→499(rule_count) | 499 | PRO 249K ✅ |
| ac279ad7 | INDUSTRY | HIGH | 158 | 499 | PRO 249K ✅ |
| 233cc6de | CONSTRUCTION | CRITICAL | 0→186(rule_count) | 38 | PREMIUM 385K ✅ |

---

## 선행/후행 관계

- **선행:** 이 API(BE-08) 완료
- **후행:** FN-06 (프론트엔드 창) — 진단 결과 페이지 하단 추천 카드 UI
