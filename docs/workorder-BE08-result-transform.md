# BE-08 워크오더 — diagnosis_transform.py

**버전:** v1.0.0  
**브랜치:** dev  
**상태:** ✅ 완료

---

## 목적

`legal_engine.py` 및 `result_data` JSONB를 **수정하지 않고**,  
기존 JSONB의 다양한 필드 구조(레거시 포함)를 FN-06 표준 응답 포맷으로 변환하는  
읽기 전용 Transform 레이어를 제공한다.

---

## 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /diagnosis/transform/{diagnosis_id}` | ID 기반 Transform |
| `GET /diagnosis/transform/latest/{factory_id}?sector=&stage=` | 시설 최신 진단 Transform |

---

## Transform 변환 우선순위 (폴백 체인)

| 섹션 | 폴백 체인 |
|------|----------|
| headline | `headline` → `headline_message` → `summary.headline` → 자동생성 |
| severity | `risk_summary.overall_level` → `rule_count` 추정 |
| obligations | `obligations` → `key_obligations` → `mandatory_obligations` → `critical_obligations` → legacy category/items 평탄화 |
| warnings | `warnings` + `urgent_action_items` + `construction_specific_tips` + `age_warnings` (object 타입 지원) |
| exposure | `exposure.penalty_max_krw` → `penalty_risk` → `total_exposure_krw` → `roi.annual_penalty_risk_krw` → `rule_count × 300만원` |
| inspection_schedule | `inspection_schedule` → `inspection_schedule_ready` → `inspection_schedule_summary` |

---

## 원칙

- `legal_engine.py` **미수정**
- `result_data` JSONB **읽기 전용** (PATCH/UPDATE 없음)
- 엔진 재실행 **금지**
- 가격 하드코딩 **금지** — `result_data.roi.subscription_annual_krw` 필드만 사용

---

## DB 신규 컬럼 (Supabase migration: be08_diagnosis_transform_columns)

| 테이블 | 컬럼 | 타입 | 기본값 |
|--------|------|------|--------|
| `factory_diagnosis_results` | `expires_at` | timestamptz | null |
| `factory_diagnosis_results` | `refund_at` | timestamptz | null |
| `factory_diagnosis_results` | `refund_reason` | text | null |
| `master_building_legal_rules` | `is_retroactive` | boolean | false |

---

## 파일 구조

```
tai-api/
  routers/diagnosis_transform.py    ← Transform 레이어 본체 (v1.0.0)
  main.py                           ← v5.27.0 (diagnosis_transform_router 등록)
  docs/workorder-BE08-result-transform.md
```

---

## FN-06 연동

- `diagnosis-result-v2.html` → `GET /diagnosis/transform/{id}` 단일 호출
- `schema_version != v2026.04` 시 → warnings[0]에 DANGER 레벨 경고 삽입 후 200 반환
- FN-06은 warnings 배열에 DANGER 항목 존재 시 재진단 배너 렌더링
