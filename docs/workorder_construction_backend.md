# TAI Safe 건설섹터 백엔드 작업지시서

## 현황 분석

### DB 현황
- `construction_sites`: 0건 (테이블 있음, 데이터 없음)
- `construction_site_processes`: 0건
- `construction_workers`: 0건
- `construction_inspections`: 0건
- `master_building_legal_rules` CONSTRUCTION 섹터: 173건 (모두 condition_code 있음)

### 법령 의무구분 분포
| obligation_type | 건수 | 비고 |
|---|---|---|
| ACTION (조치) | 69 | 가장 많음 |
| BEFORE_WORK (작업 전 점검) | 60 | 핵심 점검 |
| REPORT (보고) | 15 | |
| INSPECT (정기점검) | 13 | |
| NOTIFY (신고) | 6 | |
| APPOINT (선임) | 5 | |
| OTHER | 5 | |

### 산업 섹터와 건설 섹터 핵심 차이
| 항목 | 산업 (BUILDING/MANUFACTURING) | 건설 (CONSTRUCTION) |
|---|---|---|
| 대상 | 시설(factory) + 설비(equipment) | 건설현장(site) + 공정(process) |
| 법령 적용 단위 | 설비 type 기반 | 공사금액 + 공정 type 기반 |
| 점검 주체 | 안전관리자 → 작업자 배정 | 감리/안전관리자 현장 순회 |
| 선임 기준 | 상시 근로자 수 | 공사금액 (건축 150억, 토목 120억) |
| 하도급 | 없음 | 원청/하도급 구분 필수 |
| 작업 전 점검 | 설비별 체크리스트 | 공정별 체크리스트 |

---

## 백엔드 작업 목록

### 1. construction_sites API 완성
**파일**: `routers/construction.py` (기존 파일 확인 후 미구현 엔드포인트 추가)

```
GET  /construction/sites              건설현장 목록 (company_id 필터)
POST /construction/sites              건설현장 등록
GET  /construction/sites/{id}         건설현장 단건 조회
PATCH /construction/sites/{id}        건설현장 수정
DELETE /construction/sites/{id}       건설현장 비활성화
```

**필수 필드 검증:**
- `site_name`, `company_id`, `contract_amount`, `start_date`, `end_date` 필수
- `construction_type` (건축/토목/복합) 필수 → 안전관리자 선임 기준 자동 계산
- `total_workers` 필수 → 안전관리비 기준

**자동 계산 로직 (저장 시):**
```python
def calc_safety_manager_required(construction_type, contract_amount):
    # 건축: 150억 이상, 토목: 120억 이상
    thresholds = {'건축': 15_000_000_000, '토목': 12_000_000_000, '복합': 12_000_000_000}
    threshold = thresholds.get(construction_type, 15_000_000_000)
    return contract_amount >= threshold
```

---

### 2. 건설 법령진단 API
**파일**: `routers/construction.py` 또는 신규 `routers/construction_diagnosis.py`

```
POST /construction/sites/{site_id}/diagnose
```

**진단 로직:**
1. `master_building_legal_rules WHERE sector='CONSTRUCTION'` 전체 조회
2. `condition_code` 기반 해당 현장 조건 매칭:
   - `CONTRACT_AMOUNT_GTE_{억}`: 공사금액 조건
   - `WORKER_COUNT_GTE_{명}`: 근로자 수 조건  
   - `CONSTRUCTION_TYPE_{건축/토목}`: 공사 유형 조건
3. 해당 규칙을 `inspection_sets` 에 CONSTRUCTION 섹터로 생성
4. 결과를 `construction_sites.diagnosis_applicable_count` 업데이트

```python
# 반환 예시
{
  "status": "success",
  "data": {
    "site_id": "...",
    "total_rules": 173,
    "applicable_rules": 47,  # 조건 매칭된 규칙
    "inspection_sets_created": 47,
    "by_obligation_type": {
      "BEFORE_WORK": 22,
      "ACTION": 18,
      "INSPECT": 5,
      "APPOINT": 2
    }
  }
}
```

---

### 3. 건설 공정 API
**파일**: `routers/construction.py`

```
GET  /construction/sites/{site_id}/processes   공정 목록
POST /construction/sites/{site_id}/processes   공정 등록
PATCH /construction/sites/{site_id}/processes/{id}  공정 수정 (진행률 포함)
DELETE /construction/sites/{site_id}/processes/{id}
```

**공정 등록 시 필수:**
- `process_name`, `construction_type`, `planned_start`, `planned_end` 필수
- `work_type_code` 필수 (고위험 작업 자동 분류 기준)
- `is_high_risk` 자동 계산: 고위험 작업 목록 기반

**고위험 작업 분류 (work_type_code 기준):**
```python
HIGH_RISK_TYPES = {
    'DEMOLITION',    # 해체
    'EXCAVATION',    # 굴착
    'HIGH_PLACE',    # 고소작업 (2m 이상)
    'CRANE',         # 크레인
    'TUNNEL',        # 터널
    'COFFERDAM',     # 흙막이
    'CONCRETE_FORM', # 거푸집 동바리
    'STEEL_FRAME',   # 철골
}
```

---

### 4. 건설 점검 결과 저장 API
**파일**: `routers/construction.py`

```
POST /construction/inspections         점검 결과 저장
GET  /construction/inspections         점검 이력 조회 (site_id 필터)
GET  /construction/inspections/{id}    점검 단건
PATCH /construction/inspections/{id}   시정조치 업데이트
```

**저장 시 자동 처리:**
- `overall_result`: 이상 항목 1개 이상 → 'ISSUE', 모두 정상 → 'PASS'
- `defect_count`: checklist_items 중 result='bad' 카운트
- 이상 발생 시 안전관리자 FCM 알림 자동 발송

---

### 5. 건설 작업자 관리 API
**파일**: `routers/construction.py`

```
GET  /construction/sites/{site_id}/workers   현장 작업자 목록
POST /construction/sites/{site_id}/workers   작업자 등록 (worker_registry 연동)
DELETE /construction/sites/{site_id}/workers/{id}  작업자 제거
```

---

### 6. inspection_sets → 작업일정 자동 생성
**파일**: `routers/construction.py` 또는 `routers/inspection_schedule.py`

```
POST /construction/sites/{site_id}/generate-schedules
```

**조건 검증 (산업 섹터와 동일):**
- 기준일 있음 + 주기 있음 + 담당자 있음 + 의무내용 있음 → 스케줄 생성
- 작업 전 점검 (BEFORE_WORK): `cycle_unit=day, cycle_value=1` 자동 설정

---

## 구현 순서

```
1단계: construction sites CRUD (등록/조회/수정)
2단계: 건설 법령진단 (condition_code 매칭 → inspection_sets 생성)
3단계: 공정 등록 (프로세스 CRUD + 고위험 자동 분류)
4단계: 점검 결과 저장 + FCM 알림
5단계: 작업일정 자동 생성 파이프라인
```

---

## 주의사항

1. **건설은 factory_id가 없어도 됨**: `construction_sites.factory_id`는 선택사항
2. **하도급 근로자 합산**: `total_workers = direct_workers + subcon_workers`
3. **공사금액 기준 선임**: 법령진단 시 `contract_amount` 기준으로 선임 의무 자동 판단
4. **공정 기반 점검**: `construction_inspections.process_id`로 공정별 점검 이력 추적
5. **작업 중단 플로우**: 이상 발생 → 시정조치 요구 → 조치 완료 확인 후 재개
