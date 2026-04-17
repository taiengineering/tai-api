# BE-08: diagnosis_transform.py 작업지시서

**작성일:** 2026-04-17  
**상태:** ✅ 완료  
**파일:** `routers/diagnosis_transform.py` v1.0.0  
**PR:** https://github.com/taiengineering/tai-api/pull/1 (dev→main)

---

## 배경

엔진 출력(result_data JSONB)을 읽기 전용으로 가공하는 별도 Transform 레이어.
엔진(legal_engine.py) 코드를 절대 수정하지 않고,
FN 렌더러가 단일 표준 스키마로만 작동하도록 보장.

---

## API

| 메서드 | URL | 설명 |
|---|---|---|
| GET | `/diagnosis/transform/{diagnosis_id}` | 진단 ID 기반 Transform |
| GET | `/diagnosis/transform/latest/{factory_id}` | 시설 최신 진단 Transform |

**latest API 쿼리파라미터:**
- `?sector=BUILDING|INDUSTRY|CONSTRUCTION` — 섹터 필터
- `?stage=1|2|3|4` — 단계 필터

---

## 표준 출력 스키마

```json
{
  "diagnosis_id":    "uuid",
  "factory_id":      "uuid",
  "sector":          "BUILDING|INDUSTRY|CONSTRUCTION",
  "diagnosis_stage": 1,
  "schema_version":  "2026.04",
  "created_at":      "ISO8601",
  "expires_at":      null,
  "refund_at":       null,
  "refund_reason":   null,
  "rule_count":      65,

  "headline": {
    "summary":  "...",
    "severity": "CRITICAL|HIGH|MEDIUM|LOW"
  },
  "obligations": [ ... ],
  "warnings": [
    {"code": "URGENT", "message": "...", "level": "HIGH"}
  ],
  "exposure": {
    "penalty_max_krw":  195000000,
    "criminal_risk":    "",
    "current_exposure": "높음",
    "source":           "roi_estimate|exposure|penalty_risk|rule_count_estimate"
  },
  "inspection_schedule": {
    "daily": 0, "weekly": 0, "monthly": 0,
    "quarterly": 0, "semiannual": 0, "annual": 0, "onetime": 0
  },
  "roi": {
    "annual_penalty_risk_krw":  195000000,
    "tai_safe_annual_cost_krw": 2988000,
    "payback_days":             6,
    "risk_reduction_percent":   70.0,
    "penalty_source":           "rule_count_estimate"
  },

  "risk_summary":   {"critical": 4, "high": 14, "medium": 21, "low": 32},
  "applicable_laws": [ ... ],
  "next_actions":   [ ... ],
  "evidence":       [ ... ],
  "tier":           "FREE",

  "factory": {
    "id":             "uuid",
    "name":           "...",
    "sector":         "INDUSTRY",
    "employee_count": 499
  },

  "transform_version": "1.0.0"
}
```

---

## DB 추가 코럼 (Migration: `be08_diagnosis_transform_columns`)

| 테이블 | 코럼 | 타입 | 설명 |
|---|---|---|---|
| `factory_diagnosis_results` | `expires_at` | timestamptz | 진단 결과 유효기간 만료일 (NULL = 무기한) |
| `factory_diagnosis_results` | `refund_at`  | timestamptz | 환불 처리 일시 |
| `factory_diagnosis_results` | `refund_reason` | text | 환불 사유 |
| `master_building_legal_rules` | `is_retroactive` | boolean | 소급적용 여부 |

---

## Transform 변환 로직 요약

| 섹션 | 우선순위 |
|---|---|
| headline | `headline` > `headline_message` > `summary.headline` > 자동생성 |
| severity | `risk_summary` 기반 → `rule_count` 추정 |
| obligations | `obligations` > `key_obligations` > `mandatory_obligations` > `critical_obligations`, legacy category/items 평탄화 |
| warnings | `warnings` + `urgent_action_items` + `construction_specific_tips` + `age_warnings`(object 지원) |
| exposure | `exposure` > `penalty_risk` > `total_exposure_krw` > `roi.annual_penalty_risk_krw` > `rule_count × 300만원` |
| inspection_schedule | `inspection_schedule` > `inspection_schedule_ready` > `inspection_schedule_summary` |
| roi | `roi` 필드 직접 매핑 |

---

## 원칙

- `legal_engine.py` 코드 미수정
- `result_data` JSONB 읽기 전용 (쓰기 없음)
- 모든 레거시 패턴 (legacy PAID2+, construction_specific_tips 등) 추종 취약
- 스키마 네임 통일 도장 역할
