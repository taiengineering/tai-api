# BE-03: BUILDING sector 시드 데이터 투입

**작성일:** 2026-04-16  
**마이그레이션명:** `seed_building_factories_v1`  
**상태:** ✅ 완료

---

## 배경

- `factories` 테이블 18건 중 BUILDING sector 기존 1건
- 건물주 사용자 유입 시 진단 예시 화면이 비어있음
- 데모/영업/내부 QA용으로 8건 시드 투입

---

## 투입 데이터 목록

| # | 건물명 | 용도 | 연면적(㎡) | 층수 | 다중이용 | rule_count | company |
|---|--------|------|-----------|------|---------|------------|------|
| 1 | 가나빌딩 (소형오피스) | 업무시설 | 2,400 | 7F/B1 | ✗ | 38 | (주)가나빌딩관리 |
| 2 | 나라타워 (대형오피스) | 업무시설 | 18,500 | 25F/B3 | ✗ | 72 | (주)나라타워운영 |
| 3 | 다올복합쇼핑몰 | 판매시설 | 35,000 | 6F/B4 | ✅ | 95 | 다올복합상가(주) |
| 4 | 라온종합병원 | 의료시설 | 22,000 | 10F/B2 | ✗ | 118 | 라온의료재단 |
| 5 | 마루교육문화센터 | 교육연구시설 | 5,500 | 8F/B1 | ✗ | 64 | 마루교육재단 |
| 6 | 바름공공행정센터 | 공공업무시설 | 12,000 | 5F/B2 | ✗ | 80 | 바름공공시설관리공단 |
| 7 | 사랑호텔 (관광호텔) | 숙박시설 | 28,000 | 20F/B4 | ✅ | 102 | 사랑호텔앤리조트(주) |
| 8 | 아름노인복지센터 | 노유자시설 | 3,800 | 4F/B1 | ✗ | 75 | 아름노인복지재단 |

---

## 시드 식별 방법

```sql
-- 시드 factories 조회
SELECT * FROM factories WHERE remarks = 'SEED_BUILDING_v1';

-- 시드 전용 뷰 (진단결과 포함)
SELECT * FROM v_demo_buildings;

-- 시드 companies 조회 (business_number 패턴)
SELECT * FROM companies WHERE business_number LIKE '555-0%-1000%';
```

---

## status_code 설계

- 시드 factories: `status_code = 'DEMO'` (기존 'ACTIVE'와 구분)
- 실사용자 데이터 필터링: `WHERE status_code != 'DEMO'` 또는 `WHERE status_code = 'ACTIVE'`
- 전용 뷰 `v_demo_buildings`를 통해 데모 데이터만 별도 조회 가능

---

## 무료 진단결과 (stage=1)

- 각 건물에 `factory_diagnosis_results` 1건씩 자동 생성
- `diagnosis_stage = 1` (무료 단계)
- `is_latest = true`
- `rule_count`: 용도·규모 기반 추정치
- `result_data.is_seed = true`로 시드 여부 식별 가능

### rule_count 산정 기준

| 용도 | rule_count | 근거 |
|------|-----------|------|
| 업무시설 (3천㎡ 미만) | 38 | 소규모 오피스 기본 법령 |
| 업무시설 (1만㎡ 이상) | 72 | 대형 오피스 추가 의무 |
| 판매시설 (다중이용) | 95 | 다중이용업소법 + 소방법 중복 |
| 의료시설 | 118 | 의료법 + 소방법 + 산안법 복합 |
| 교육연구시설 | 64 | 교육환경보호법 포함 |
| 공공업무시설 | 80 | 공공기관 추가 의무 |
| 숙박시설 (다중이용) | 102 | 관광진흥법 + 소방법 |
| 노유자시설 | 75 | 노인복지법 + 소방법 |

---

## 롤백 방법 (일괄 삭제)

```sql
-- Step 1: 진단결과 삭제
DELETE FROM factory_diagnosis_results
WHERE factory_id IN (
  SELECT id FROM factories WHERE remarks = 'SEED_BUILDING_v1'
);

-- Step 2: factories 삭제
DELETE FROM factories WHERE remarks = 'SEED_BUILDING_v1';

-- Step 3: companies 삭제 (business_number 패턴)
DELETE FROM companies
WHERE business_number LIKE '555-0_-1000_';

-- Step 4: 뷰 삭제 (선택적)
DROP VIEW IF EXISTS v_demo_buildings;
```

> ⚠️ 롤백 전 `v_demo_buildings` 조회로 삭제 대상을 반드시 확인할 것

---

## 완료 조건 검증

```sql
-- BUILDING sector 8건 이상 확인
SELECT COUNT(*) FROM factories WHERE sector = 'BUILDING' AND remarks = 'SEED_BUILDING_v1';
-- → 8

-- 무료 진단결과 8건 확인  
SELECT COUNT(*) FROM v_demo_buildings WHERE rule_count IS NOT NULL;
-- → 8

-- 전체 BUILDING 수 확인 (기존 1건 + 신규 8건)
SELECT COUNT(*) FROM factories WHERE sector = 'BUILDING';
-- → 9
```

---

## 금기 사항 준수

- ✅ 실제 회사명/건물명 미사용 (가상 한글 이름)
- ✅ 실제 주소 미사용 (서울·경기 가상 번지)
- ✅ main 직접 커밋 없음 (dev 브랜치)
