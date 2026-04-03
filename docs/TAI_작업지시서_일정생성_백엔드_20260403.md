# 작업지시서 — 일정관리 백엔드 확장
## 목적
`engine-legal-ai`의 파싱→검토→승인 워크플로우와 동일하게,
INSPECT 마스터 룰 → 일정세트 생성 → 기준일 검토 → 마스터 일정 활성화 파이프라인 구축.

## 파일
`routers/inspection_schedule.py` 에 아래 엔드포인트 추가

---

## 신규 API 1 — GET /inspection-schedule/rules
**설명**: 마스터 INSPECT 룰 목록 조회 (탭1 좌측 패널용)

**Query Params**:
- `sector` str optional (BUILDING|MANUFACTURING|CONSTRUCTION|COMMON 등)
- `law_name` str optional (검색)
- `page` int default=1
- `page_size` int default=50 max=100

**DB 조회**: `master_building_legal_rules`
- `is_active = true`
- `obligation_type = 'INSPECT'`
- `diagnosis_stage = 1`
- `sector NOT IN ('SPECIAL_FACILITY','SPECIAL')`

**Response**:
```json
{
  "status": "success",
  "data": {
    "items": [
      {
        "rule_id": "ELEVACT-010",
        "sector": "BUILDING",
        "law_name": "승강기 안전관리법",
        "law_article": "제32조",
        "obligation_summary": "승강기 정기검사",
        "cycle_unit": "year",          // inspection_cycle_unit_code 변환
        "cycle_value": 1,              // inspection_cycle_value
        "cycle_label": "연 1회",        // 계산값
        "condition_code": "elevator_count",
        "condition_value": "1",
        "condition_operator": "gte",
        // inspection_sets로 이미 생성된 시설 수
        "converted_factory_count": 0,
        "total_factory_count": 12
      }
    ],
    "total": 191,
    "page": 1,
    "page_size": 50,
    // 섹터별 집계
    "sector_summary": {
      "BUILDING": {"total": 109, "converted": 67},
      "MANUFACTURING": {"total": 65, "converted": 0},
      "CONSTRUCTION": {"total": 7, "converted": 0}
    }
  }
}
```

**cycle_unit 변환 로직** (inspection_cycle_unit_code → cycle_unit):
```python
CYCLE_CODE_TO_UNIT = {
    "001": ("day",   1),
    "002": ("week",  1),
    "003": ("month", 1),
    "004": ("month", 3),
    "005": ("month", 6),
    "006": ("year",  1),
    "007": ("year",  2),
    "008": ("year",  5),
    "009": ("year",  4),
    "010": ("year",  3),
    "011": ("year",  3),
    "012": ("year", 10),
    "013": ("year",  5),
}
```

**cycle_label 생성**:
```python
def get_cycle_label(unit: str, value: int) -> str:
    labels = {
        "year":      lambda v: f"연 {v}회" if v == 1 else f"{v}년마다",
        "month":     lambda v: f"월 {v}회" if v == 1 else f"{v}개월마다",
        "quarter":   lambda v: "분기 1회",
        "half_year": lambda v: "반기 1회",
        "week":      lambda v: f"주 {v}회" if v == 1 else f"{v}주마다",
        "day":       lambda v: f"일 {v}회" if v == 1 else f"{v}일마다",
    }
    fn = labels.get(unit)
    return fn(value) if fn else f"{value} {unit}"
```

---

## 신규 API 2 — GET /inspection-schedule/rules/{rule_id}/factories
**설명**: 특정 룰에 대해 시설별 생성 여부 조회 (탭1 우측 패널용)

**Response**:
```json
{
  "status": "success",
  "data": {
    "rule": { /* 룰 상세 */ },
    "factories": [
      {
        "factory_id": "uuid",
        "factory_name": "대한물류창고 안산센터",
        "sector": "INDUSTRY",
        "condition_met": true,   // 이 시설이 룰 조건을 충족하는지 (간단 판단)
        "inspection_set_id": "uuid",   // 이미 생성된 경우
        "inspection_set_status": "PENDING_ANCHOR",  // 생성된 경우 상태
        "anchor_confirmed": false
      }
    ]
  }
}
```

**condition_met 판단 로직** (간단):
- condition_code가 없으면 → true
- condition_code가 `is_hazardous_material`, `is_factory_registered` 등 bool → factories 테이블 컬럼 확인
- condition_code가 `building_area`, `elevator_count` 등 숫자 → factories 테이블에서 비교
- 매핑: `building_area`→`building_area`, `elevator_count`→`elevator_count`, `worker_count`→`employee_count`

---

## 신규 API 3 — POST /inspection-schedule/generate
**설명**: 선택한 룰+시설 조합으로 inspection_sets 일괄 생성
(engine-legal-ai의 `parse-batch`에 해당)

**Request Body**:
```json
{
  "rule_ids": ["ELEVACT-010", "FIREACT-005"],   // 선택한 룰 목록
  "factory_ids": ["uuid1", "uuid2"],              // 선택한 시설 목록
  "skip_existing": true   // 이미 있는 조합은 스킵
}
```

**처리 로직**:
1. rule_ids × factory_ids 조합 순회
2. `skip_existing=true`이면 이미 inspection_sets에 `(factory_id, legal_rule_id)`가 있는 것 스킵
3. 없는 조합만 inspection_sets INSERT:

```python
row = {
    "company_id":          factory["company_id"],
    "factory_id":          factory_id,
    "inspection_set_name": f"{rule['law_name']} 점검",
    "inspection_set_code": rule["rule_id"],
    "legal_rule_id":       rule["rule_id"],
    "law_name":            rule["law_name"],
    "law_article":         rule["law_article"],
    "cycle_unit":          cycle_unit,   # CYCLE_CODE_TO_UNIT 변환
    "cycle_value":         cycle_value,
    "cycle_base_type":     "LAST_INSPECTION",
    "cycle_base_guide":    f"마지막 점검일로부터 {cycle_label}",
    "description":         rule.get("obligation_summary", ""),
    "source":              "LEGAL_ENGINE",
    "is_active":           True,
    "anchor_confirmed":    False,
    "status_code":         "PENDING_ANCHOR",
}
```

**Response**:
```json
{
  "status": "success",
  "data": {
    "created": 14,
    "skipped": 3,
    "errors": []
  }
}
```

---

## 신규 API 4 — GET /inspection-schedule/sets/summary-by-rule
**설명**: 탭1 상단 요약 카드용 (법령 커버리지)

**Response**:
```json
{
  "status": "success",
  "data": {
    "total_inspect_rules": 191,
    "converted_rules": 67,       // inspection_sets로 변환된 룰 수
    "not_converted_rules": 124,  // 미변환
    "total_factories": 12,
    "factories_with_sets": 2,
    "total_sets": 68,
    "pending_anchor": 67,
    "active": 1
  }
}
```

---

## 기존 API (재사용)
- `GET /inspection-schedule/sets` — 탭2 목록 (이미 있음)
- `GET /inspection-schedule/sets/{id}` — 모달 단건 (이미 있음)
- `PATCH /inspection-schedule/sets/{id}` — 수정 (이미 있음)
- `POST /inspection-schedule/sets/{id}/confirm-anchor` — 기준일 확정→활성화 (이미 있음)
- `GET /inspection-schedule/summary` — 탭2 상단 카드 (이미 있음)

---

## 주의사항
- `CYCLE_CODE_TO_UNIT` 딕셔너리: 기존 legal_engine.py와 동일하게 사용
- factories 조회 시 JOIN: `factories.name`, `factories.company_id`, `factories.sector`
- generate API: 배치 20건씩 insert (기존 패턴 유지)
- 이미 있는 inspection_sets를 덮어쓰지 않음 (`skip_existing=true` 기본)
