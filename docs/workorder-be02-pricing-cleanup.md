# BE-02: 법령진단 가격표 중복 정리

**작업일:** 2026-04-16  
**Migration:** `cleanup_price_diagnosis_duplicates`  
**상태:** ✅ 완료

---

## 배경

`price_diagnosis_report` 테이블에 동일 sector·유사 가격 중복 코드 3쌍 존재.  
프론트 pricing.html 고도화(FN-01) 전 DB 단일 소스 확정 필요.

---

## Before 상태

| code | name | price | is_active |
|---|---|---|---|
| BUILDING | 일반건물 | 99,000 | false |
| BUILDING_V2 | 소형건물 (5,000㎡ 미만) | 99,000 | true |
| BUILDING_LARGE_V2 | 대형건물 (5,000㎡ 이상) | 249,000 | true |
| FACTORY | 제조·공장 | 249,000 | false |
| INDUSTRY_V2 | 제조·산업 | 249,000 | true |
| CONSTRUCTION | 건설 | 399,000 | **false** ← 복구 필요 |
| CONSTRUCTION_V2 | 건설현장 | 199,000 | **true** ← 폐기 필요 |
| HAZARD_LOW | 특수 일반(1~2종) | 199,000 | **false** ← 활성화 필요 |
| HAZARD_MID | 특수 중급(3~5종) | 399,000 | **false** ← 활성화 필요 |
| HAZARD_HIGH | 특수 고급(6종+) | 699,000 | **false** ← 활성화 필요 |

---

## After 상태 (★ 완료 확인 쿼리 결과)

```sql
SELECT facility_type_code, facility_type_name, total_report_fee, is_active, sort_order
FROM price_diagnosis_report ORDER BY sort_order;
```

| facility_type_code | facility_type_name | total_report_fee | is_active | sort_order |
|---|---|---|---|---|
| BUILDING_V2 | 소형건물 (5,000㎡ 미만) | 99,000 | **true** | 1 |
| BUILDING_LARGE_V2 | 대형건물 (5,000㎡ 이상) | 249,000 | **true** | 2 |
| INDUSTRY_V2 | 제조·산업 | 249,000 | **true** | 3 |
| CONSTRUCTION | 건설 | 399,000 | **true** | 4 |
| HAZARD_LOW | 특수 일반(1~2종) | 199,000 | **true** | 5 |
| HAZARD_MID | 특수 중급(3~5종) | 399,000 | **true** | 6 |
| HAZARD_HIGH | 특수 고급(6종+) | 699,000 | **true** | 7 |
| CONSTRUCTION_V2 | 건설현장 | 199,000 | **false** | 90 |
| BUILDING | 일반건물 | 99,000 | false | 91 |
| FACTORY | 제조·공장 | 249,000 | false | 92 |

**is_active=true 7건 ✅** (BUILDING_V2, BUILDING_LARGE_V2, INDUSTRY_V2, CONSTRUCTION, HAZARD_LOW, HAZARD_MID, HAZARD_HIGH)  
**is_active=false 3건 ✅** (CONSTRUCTION_V2, BUILDING, FACTORY) — soft-disable, 결제이력 보존

---

## pricing_key_map 정리 결과

| key | label | is_active |
|---|---|---|
| diag_building_v2 | 건물·시설 | true |
| diag_construction | 건설 | true |
| diag_hazard_high | 특수 고급(6종+) | true |
| diag_hazard_low | 특수 일반(1~2종) | true |
| diag_hazard_mid | 특수 중급(3~5종) | true |
| diag_industry_v2 | 제조·산업 | true |
| diag_building | 일반건물 | **false** (legacy) |
| diag_construction_v2 | 건설현장 | **false** (199K 폐기) |
| diag_factory | 제조·공장 | **false** (legacy) |

---

## diagnosis_purchases 이력

- 총 8건 존재 (결제이력)
- `facility_type_code` 컬럼 없음 → `sector` 필드로 관리됨
- **수정 없음** — 가격 이력 보존 완료 ✅

---

## 완료 조건 체크

- [x] is_active=true 정확히 7건
- [x] 폐기 코드 3건(CONSTRUCTION_V2, BUILDING, FACTORY) is_active=false (soft-disable)
- [x] diagnosis_purchases 레코드 수정 없음
- [x] pricing_key_map 동일 방향 정리 완료
- [x] main 직접 커밋 없음 (Supabase migration으로만 처리)

---

## 다음 단계

FN-02(프론트 pricing.html 고도화) 착수 가능.  
API 엔드포인트 `/public/pricing/diagnosis-reports`는 `is_active=true` 필터 기준으로 응답하므로 별도 백엔드 코드 변경 없음.
