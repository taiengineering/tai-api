# BE-09: 익명 진단 토큰 기반 플랜 추천 API

**작성일:** 2026-04-18  
**파일:** `routers/anonymous_diagnosis.py` (BE-08 함수 재사용)  
**main.py:** 변경 없음 (기존 anonymous_diagnosis 라우터 내부 추가)

---

## 엔드포인트

```
GET /anonymous-diagnosis/{token}/recommend-plan
```

- 인증 불필요 (공개) — 익명 진단 결과 페이지에서 바로 소비
- `/{token}` 보다 **앞에** 등록 (경로 섀도잉 방지)

---

## 핵심 원칙

| 원칙 | 내용 |
|---|---|
| BE-08 함수 재사용 | `_recommend_industry/building/construction`, `_build_alternatives`, `_build_comparison` import |
| 코드 중복 금지 | 추천 로직 0줄 복사 |
| main.py 변경 없음 | anonymous_diagnosis 라우터 내부 추가 |

---

## sector 보정 매핑

| 입력 (법령엔진 내부) | 출력 (추천 엔진) | 이유 |
|---|---|---|
| `MANUFACTURING` | `INDUSTRY` | 법령엔진 내부 코드 → 추천 플랜 코드 |
| `SPECIAL_FACILITY` | `BUILDING` | 기타시설 → 건물 플랜군 적용 |
| `CONSTRUCTION` | `CONSTRUCTION` | 그대로 |
| `BUILDING` | `BUILDING` | 그대로 |

---

## 입력 데이터 소스

| 변수 | 소스 | fallback |
|---|---|---|
| `sector` | `input_data.sector` → `full_result.sector` | — |
| `severity` | `full_result.headline.severity` | `full_result.risk_level` → `"LOW"` |
| `obl_cnt` | `len(full_result.key_obligations)` | `full_result.applicable_count` → 0 |
| `workers` | `input_data.workers` | 0 |
| `penalty_risk_krw` | `full_result.roi.annual_penalty_risk_krw` | 0 |

---

## 응답 구조

```json
{
  "status": "success",
  "source": "anonymous_token",
  "token": "uuid",
  "sector": "INDUSTRY",
  "sector_raw": "MANUFACTURING",
  "input_summary": {
    "severity": "HIGH",
    "obl_count": 6,
    "workers": 45
  },
  "recommended": {
    "plan_code":   "INDUSTRY_BUSINESS_V2",
    "plan_name":  "산업 BUSINESS",
    "monthly_krw": 149000,
    "is_custom":  false,
    "pricing_note": "월 149,000원 (부가세 별도)"
  },
  "reasons": [
    "위험도 HIGH — 체계적인 점검 일정 자동화가 효과적입니다",
    "법적 의무 6건 — BUSINESS 플랜의 자동 일정 생성으로 누락 방지",
    "작업 분산 배치 + 지연 알림 + 월간 리포트 포함"
  ],
  "alternatives": {
    "lower": {"plan_code": "INDUSTRY_STARTER_V2", "monthly": 79000, ...},
    "upper": {"plan_code": "INDUSTRY_PRO", "monthly": 249000, ...}
  },
  "comparison": {
    "annual_penalty_risk_krw": 150000000,
    "tai_safe_annual_krw": 1788000,
    "risk_reduction_ratio": 83.9,
    ...
  },
  "cta": {
    "primary":   {"label": "지금 시작하기",        "action": "go_pricing"},
    "secondary": {"label": "전체 요금제 비교하기",  "action": "go_pricing_all"},
    "signup":    {"label": "회원가입 후 상세 진단", "action": "go_register"}
  }
}
```

---

## 전체 사용자 플로우

```
무료 진단 페이지
  └─ POST /anonymous-diagnosis
        ↓ publicToken 반환
  진단 결과 페이지 (/result?token=xxx)
        ↓
  GET /anonymous-diagnosis/{token}/recommend-plan   ← BE-09
        ↓
  추천 플랜 카드 + 이유 + 과태료 비교 (FN-06 UI 소비)
        ↓
  [지금 시작하기] → pricing.html?plan=INDUSTRY_BUSINESS_V2
```

---

## BE-08 vs BE-09 차이

| 항목 | BE-08 | BE-09 |
|---|---|---|
| 엔드포인트 | `GET /diagnosis/{diagnosis_id}/recommend-plan` | `GET /anonymous-diagnosis/{token}/recommend-plan` |
| 데이터 소스 | `factory_diagnosis_results` (DB UUID) | `anonymous_diagnosis_results` (public_token) |
| 로그인 필요 | 불필요 | 불필요 |
| 추천 로직 | BE-08 원본 | BE-08 완전 재사용 (import) |
| sector 보정 | factories.sector 우선 | `_SECTOR_NORMALIZE` 매핑 추가 |
| cta | primary + secondary | primary + secondary + signup |
