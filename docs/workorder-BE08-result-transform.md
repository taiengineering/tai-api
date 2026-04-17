# BE-08: diagnosis_transform.py — 진단 결과 Transform 레이어

**자상일:** 2026-04-17  
**파일:** `routers/diagnosis_transform.py` v1.0.0  
**상태:** ✅ 완료

---

## 원칙

| 원칙 | 내용 |
|---|---|
| 엔진 수정 금지 | `legal_engine.py` 코드 절대 미수정 |
| DB 읽기 전용 | `result_data` JSONB 읽기만, 쓰기(수정) 없음 |
| 단일 스키마 | FN 레이어가 이 API 하나만 따르면 됨 |
| 템포럴 블라인 | 레거시 / v2026.04 둘 다 처리 |

---

## API

### `GET /diagnosis/transform/{diagnosis_id}`

단일 ID로 진단 결과를 Transform해 반환.

### `GET /diagnosis/transform/latest/{factory_id}`

시설 최신 진단 결과 Transform. 선택적 필터:
- `?sector=BUILDING|INDUSTRY|CONSTRUCTION`
- `?stage=1~4`

---

## Transform 표준 응답 스키마

```json
{
  "status": "success",
  "data": {
    "meta": {
      "diagnosis_id": "uuid",
      "factory_id": "uuid",
      "sector": "INDUSTRY",
      "diagnosis_stage": 1,
      "rule_count": 65,
      "is_latest": true,
      "schema_version": "2026.04",
      "created_at": "ISO8601",
      "expires_at": null,
      "refund_at": null,
      "refund_reason": null,
      "transform_version": "1.0.0",
      "transformed_at": "ISO8601"
    },
    "headline": {
      "summary": "...",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW"
    },
    "obligations": [
      {
        "id": "obl_001",
        "law_ref": "...",
        "title": "...",
        "is_retroactive": false,
        "penalty": {"krw": 0, "criminal": null, "type": null}
      }
    ],
    "warnings": [
      {"code": "URGENT", "message": "...", "level": "HIGH"}
    ],
    "exposure": {
      "penalty_max_krw": 48000000,
      "criminal_risk": null,
      "current_exposure": null,
      "source": "roi_estimate"
    },
    "inspection_schedule": {
      "daily": 0, "weekly": 0, "monthly": 3,
      "quarterly": 2, "semiannual": 1, "annual": 4,
      "onetime": 0,
      "periodic_count": 10, "before_work_count": 3, "on_demand_count": 2,
      "source": "inspection_schedule_ready"
    },
    "roi": {
      "annual_penalty_risk_krw": 213000000,
      "tai_safe_annual_cost_krw": 2988000,
      "payback_days": 6,
      "risk_reduction_percent": 70,
      "penalty_source": "rule_count_estimate",
      "calculated_at": "ISO8601"
    },
    "risk_summary": {"critical": 4, "high": 14, "medium": 21, "low": 32},
    "applicable_laws": [],
    "next_actions": [],
    "evidence": ["input.worker_count=85", "..."]
  }
}
```

---

## DB 변경 (Migration: `be08_diagnosis_transform_columns`)

### `factory_diagnosis_results` 신규 콼럼

| 콼럼 | 타입 | 설명 |
|---|---|---|
| `expires_at` | `timestamptz` | 진단결과 유효기간 (NULL=무기한) |
| `refund_at` | `timestamptz` | 환불 처리 일시 |
| `refund_reason` | `text` | 환불 사유 |

### `master_building_legal_rules` 신규 콼럼

| 콼럼 | 타입 | 설명 |
|---|---|---|
| `is_retroactive` | `boolean` | 소급적용 여부 (false=기본값) |

---

## 폴백 진단 체인 (legacy → v2026.04)

| 필드 | v2026.04 소스 | legacy 폴백 순서 |
|---|---|---|
| headline | `rd.headline` | `headline_message` → `summary.headline` → 자동생성 |
| obligations | `rd.obligations` | `key_obligations` → `mandatory_obligations` → `critical_obligations` |
| warnings | `rd.warnings` | `urgent_action_items` + `construction_specific_tips` + `age_warnings` |
| exposure | `rd.exposure` | `penalty_risk.max_fine_krw` → `total_exposure_krw` → `roi.annual_penalty_risk_krw` → `rule_countxd73M` |
| inspection_schedule | `rd.inspection_schedule` | `inspection_schedule_ready` → `inspection_schedule_summary` |
| roi | `rd.roi` | `rule_countxd73M` 추정 |

---

## main.py 등록 필요

```python
from routers.diagnosis_transform import router as diagnosis_transform_router  # v5.27.0
# ...
app.include_router(diagnosis_transform_router)  # 인증 필요 엔드포인트
```

---

## 주의사항

- `GET /diagnosis/transform/latest/{factory_id}` 영엁에서
  `GET /diagnosis/transform/{diagnosis_id}` 이 충돌 가능성 있음.
  FastAPI 라우터 등록 순서: **`/transform/latest/{factory_id}` 먼저** 등록 필수.
  `main.py`에 `diagnosis_transform_router` 등록 시 `diagnosis_router` 없에 위치할 것.
