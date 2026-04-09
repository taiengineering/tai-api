# TAI Safe 건설섹터 백엔드 작업지시서

---

## ★ API v2.1.0 추가 기능 (최우선 반영)

### 1. 법령진단 독립 실행

**엔드포인트**: `POST /construction/sites/{site_id}/diagnose`

**응답 구조 (필수 준수):**
```json
{
  "status": "success",
  "data": {
    "site_id": "uuid",
    "total_rules": 173,
    "applicable_rules": 47,
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

**구현 포인트:**
- 중복 실행 시 기존 inspection_sets SKIP (NOT EXISTS 패턴 사용)
- 진단 완료 후 `construction_sites.diagnosis_applicable_count` 업데이트 필수
- `construction_sites.last_diagnosis_at` = now() 업데이트 필수
- 에러 시 HTTP 422 + `{ "detail": "공사금액을 먼저 입력해주세요." }` 형식 반환

---

### 2. 작업일정 자동 생성

**엔드포인트**: `POST /construction/sites/{site_id}/generate-schedules`

**응답 구조 (필수 준수):**
```json
{
  "status": "success",
  "data": {
    "created": 34,
    "skipped": 13,
    "total_rules": 47
  }
}
```

**구현 포인트:**
- `diagnosis_applicable_count == 0` 인 경우 HTTP 400 반환:
  ```json
  { "detail": "법령진단을 먼저 실행하세요." }
  ```
- 4조건 미충족 inspection_set → `skipped` 카운트에 포함
- BEFORE_WORK 의무: `cycle_unit=day, cycle_value=1` 자동 적용
- 이미 생성된 스케줄은 중복 생성하지 않음 (NOT EXISTS 패턴)

---

### 3. 점검 저장 → FCM 자동 발송

**엔드포인트**: `POST /construction/inspections`

**요청 Body `checklist_items` 배열 형식 (필수 준수):**
```json
{
  "site_id": "uuid",
  "process_id": "uuid",
  "inspector_phone": "01047758888",
  "checklist_items": [
    { "item_name": "타이어 상태", "result": "ok",  "note": "" },
    { "item_name": "경적 작동",  "result": "bad", "note": "경적 불량" },
    { "item_name": "브레이크",   "result": "ok",  "note": "" }
  ]
}
```

**`overall_result` 생략 가능 → API 자동 계산:**
```python
overall_result = "ISSUE" if any(i["result"] == "bad" for i in checklist_items) else "PASS"
defect_count   = sum(1 for i in checklist_items if i["result"] == "bad")
```

**이상 발생 시 FCM 자동 발송 로직:**
```python
if overall_result == "ISSUE":
    # 현장 안전관리자 FCM 토큰 조회
    manager = get_site_manager(site_id)  # manager_id → users.push_token
    if manager and manager.push_token:
        send_push(
            fcm_token=manager.push_token,
            title="⚠️ 건설현장 점검 이상 발생",
            body=f"{site_name} — 이상 {defect_count}건 발생",
            data={"type": "inspection", "site_id": site_id, "inspection_id": str(new_id)}
        )
```

**`FCM_SERVER_KEY` Railway 설정 방법:**
```
Railway Dashboard → 프로젝트 선택 → Variables
→ FIREBASE_CREDENTIALS = '{"type":"service_account","project_id":"tai-safe",...}'
(Firebase Console → 프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성 → JSON 전체 내용)
```

---

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
    thresholds = {'건축': 15_000_000_000, '토목': 12_000_000_000, '복합': 12_000_000_000}
    threshold = thresholds.get(construction_type, 15_000_000_000)
    return contract_amount >= threshold
```

---

### 2. 건설 법령진단 API
→ ★ v2.1.0 섹션 참조

---

### 3. 건설 공정 API
**파일**: `routers/construction.py`

```
GET  /construction/sites/{site_id}/processes
POST /construction/sites/{site_id}/processes
PATCH /construction/sites/{site_id}/processes/{id}
DELETE /construction/sites/{site_id}/processes/{id}
```

**고위험 작업 분류 (work_type_code 기준):**
```python
HIGH_RISK_TYPES = {
    'DEMOLITION', 'EXCAVATION', 'HIGH_PLACE', 'CRANE',
    'TUNNEL', 'COFFERDAM', 'CONCRETE_FORM', 'STEEL_FRAME',
}
```

---

### 4. 건설 점검 결과 저장 API
→ ★ v2.1.0 섹션 참조 (checklist_items 형식, FCM 발송 포함)

```
POST /construction/inspections
GET  /construction/inspections
GET  /construction/inspections/{id}
PATCH /construction/inspections/{id}  # 시정조치 업데이트
```

---

### 5. 건설 작업자 관리 API

```
GET  /construction/sites/{site_id}/workers
POST /construction/sites/{site_id}/workers
DELETE /construction/sites/{site_id}/workers/{id}
```

---

### 6. 작업일정 자동 생성
→ ★ v2.1.0 섹션 참조 (created/skipped/total_rules 응답 포함)

```
POST /construction/sites/{site_id}/generate-schedules
```

---

## 구현 순서

```
1단계: construction sites CRUD
2단계: 건설 법령진단 (★ v2.1.0 응답구조 준수)
3단계: 공정 등록
4단계: 점검 결과 저장 + FCM 알림 (★ v2.1.0 checklist_items 형식 준수)
5단계: 작업일정 자동 생성 (★ v2.1.0 created/skipped 응답 준수)
```

---

## 주의사항

1. **건설은 factory_id가 없어도 됨**: `construction_sites.factory_id`는 선택사항
2. **하도급 근로자 합산**: `total_workers = direct_workers + subcon_workers`
3. **공사금액 기준 선임**: 법령진단 시 `contract_amount` 기준으로 선임 의무 자동 판단
4. **공정 기반 점검**: `construction_inspections.process_id`로 공정별 점검 이력 추적
5. **작업 중단 플로우**: 이상 발생 → 시정조치 요구 → 조치 완료 확인 후 재개
