# TAI Safe 점검(INSPECT) 룰 분석 보고서
**작성일: 2026-04-06**

## 4필드 완비율 현황

점검 의무가 스케줄로 전환되려면 4가지 필드가 모두 있어야 합니다:
- **언제**: inspection_cycle_unit_code
- **누가**: executor_type_code  
- **무엇을**: condition_code
- **어떻게**: law_article (법령 근거)

| 섹터 | 전체 | 언제(주기) | 누가(수행자) | 무엇(조건) | 법령 | 4완비 | 완비율 |
|------|------|-----------|-------------|-----------|------|-------|--------|
| BUILDING | 124 | 107 | 124 | 123 | 124 | **106** | **85%** |
| MANUFACTURING | 78 | 66 | 78 | 68 | 78 | **56** | **72%** |
| CONSTRUCTION | 73 | 9 | 73 | 73 | 73 | **9** | **12%** |
| COMMON | 15 | 0 | 15 | 15 | 15 | **0** | **0%** |

## 점검 주기 분포

| 주기 | 건수 |
|------|------|
| 연 1회 | 76건 |
| 2년마다 | 31건 |
| 분기 1회 | 25건 |
| 반기 1회 | 24건 |
| 월 1회 | 17건 |
| 3년 이상 | 12건 |

## 핵심 문제

### 건설 INSPECT 주기 누락 (64건)
건설 공종별 점검 룰(`CON2-CRA-*`, `CON2-BLA-*` 등)은 **작업 전 점검** 성격으로
날짜 기반 주기가 아닌 **작업 트리거** 방식입니다.

```
CON2-CRA-003: 크레인 사용 전 과부하방지장치 점검
CON2-BLA-004: 발파 작업 전 도화선·전기뇌관 점검
→ 이런 룰은 construction_work_type이 있고 주기 코드는 없음
```

### 해결 방안: schedule_type 분류 (v5.6.2 적용)

```python
def _get_schedule_type(rule):
    if rule.get("inspection_cycle_unit_code"):  # 주기 있음
        return "PERIODIC"      # → 캘린더 반복 일정 생성
    if rule.get("construction_work_type"):      # 공종 있고 주기 없음
        return "BEFORE_WORK"   # → 작업 등록 시 자동 생성
    return "ON_DEMAND"         # → 수동 트리거
```

### 가스 조건값 단계 (수정 금지)

| 조건 | 건수 | 법령 |
|------|------|------|
| gas_capacity_kg >= 1 | 12건 | 기본 선임/점검 의무 |
| gas_capacity_kg >= 100 | 13건 | 정기검사 (고압가스안전관리법) |
| gas_capacity_kg >= 300 | 1건 | 추가 검사 |
| gas_capacity_kg >= 1000 | 1건 | 특별 의무 |

**결론**: 조건값은 법적으로 정확함. 진단 입력에서 실제 용량을 받아야 단계별 판정 가능.
→ v5.6.3에서 `gas_capacity_kg` 수치 직접 입력 필드 추가로 해결.

## 엔진 응답 변경 (v5.6.2+)

```json
// inspection_required 각 항목에 추가된 필드
{
  "inspection_cycle":      "연 1회",      // 기존: 항상 ""
  "inspection_cycle_code": "006",
  "inspection_cycle_unit": "year",
  "inspection_cycle_int":  1,
  "schedule_type":         "PERIODIC",
  "construction_work_type": "",
  "executor_type_code":    "external",
  "condition_code":        "elevator_count"
}

// step1 응답에 추가된 최상위 블록
{
  "inspection_schedule_ready": {
    "periodic_count":    43,
    "before_work_count": 12,
    "on_demand_count":   8,
    "periodic":          [...],  // 스케줄러 즉시 사용 가능
    "before_work":       [...]   // 작업 등록 시 연계
  }
}
```

## 스케줄러 연계 흐름 (설계)

```
법령 판정 완료
    ↓
inspection_schedule_ready.periodic
    → cycle_unit + cycle_int → 캘린더 반복 일정 생성
    → 마지막 점검일 기준 다음 점검일 계산
    
inspection_schedule_ready.before_work
    → construction_work_type 기반
    → 해당 공종 작업 등록 시 자동 생성
```
