# 문서 기준 데이터 수집 추적표 (Traceability Matrix)

> 작성일: 2026-04-30
> 원칙: 문서(결과물)가 요구하는 항목 → 데이터 소스 → 수집 상태 → 갭

---

## 1. field_key 유형 분류

29건 문서의 required_fields에서 추출한 field_key를 5개 유형으로 분류.

| 유형 | 설명 | field_key 수 | 수집 상태 |
|------|------|------------|----------|
| A. 메타데이터 | 점검일시, 점검자, 실시여부 | 8 | ✅ 수집됨 |
| B. 결과 데이터 | 점검결과, 이상여부, 조치사항 | 5 | ✅ 수집됨 |
| C. 설비별 체크리스트 | 브레이크, 절연, 누출 등 상세항목 | 18 | ⚠️ 파이프라인 끊김 |
| D. 특수 계측 | 온도, 압력, 운전시간 등 숫자값 | 4 | ❌ 미수집 |
| E. TBM/교육/공사일지 | 별도 모듈 데이터 | 19 | △ 부분 수집 |

---

## 2. 유형별 상세 매핑

### A. 메타데이터 — ✅ 수집됨

문서가 공통으로 필요로 하는 기본 정보. 이미 DB에 있음.

| field_key | field_name | 데이터 소스 | 상태 |
|-----------|-----------|------------|------|
| inspection_done | 점검 실시 여부 | `safety_inspections.status_code` | ✅ |
| inspection_datetime | 점검일시 | `safety_inspections.inspection_date` | ✅ |
| inspection_date | 점검일자 | `safety_inspections.inspection_date` | ✅ |
| inspector | 점검자 | `safety_inspections.inspector_id` → `users.name` | ✅ |
| inspector_sign | 점검자 서명 | `safety_inspections.inspector_id` → 서명 없음 | ❌ 서명 기능 미구현 |
| target | 점검 대상 | `equipment_assets.name` | ✅ |
| equipment_name | 설비명 | `equipment_assets.name` | ✅ |
| inspection_content | 점검내용 | `inspection_set_items.item_name` | ✅ |

**갭:** `inspector_sign`(점검자 서명) — 현재 서명 기능이 safety_inspections에 없음. TBM에만 서명 있음.

### B. 결과 데이터 — ✅ 수집됨

점검 결과로 기록되는 데이터. safety_inspection_results에 저장.

| field_key | field_name | 데이터 소스 | 상태 |
|-----------|-----------|------------|------|
| result | 점검결과 | `safety_inspection_results.result_code` (NORMAL/ISSUE/HOLD) | ✅ |
| abnormal | 이상 여부 | `result_code = 'ISSUE'` 로 판단 | ✅ |
| defect | 불량사항 | `result_code = 'ISSUE'` 인 항목의 `note` | ✅ |
| action | 조치사항 | `safety_inspection_results.note` | ✅ |
| risk | 위험요인 | `safety_inspection_results.note` | ⚠️ 별도 필드 없음, note에 통합 |

**갭:** `risk`(위험요인)과 `action`(조치사항)이 같은 `note` 필드에 들어감.
→ 분리할지 여부는 문서 출력 시 판단. 현재는 통합으로도 법적 충족.

### C. 설비별 체크리스트 — ⚠️ 파이프라인 끊김

**이것이 대형 이슈.** 문서가 요구하는 상세 항목이 inspection_master(772개)에 있지만 inspection_set_items와 연결되지 않음.

| field_key | field_name | 해당 설비 (inspection_master) | 상태 |
|-----------|-----------|------------------------------|------|
| electrical_check | 전기설비 점검 | 분전반, 배전반, 변압기 | ⚠️ |
| insulation | 절연 상태 | 분전반 → "절연저항 기준 충족" | ⚠️ |
| grounding | 접지 상태 | 접지설비 → "접지저항 측정" | ⚠️ |
| equipment_check | 설비 점검 | 프레스, 선반, CNC 등 전체 | ⚠️ |
| scaffold_check | 비계 점검 | 비계_시스템, 비계_강관 | ⚠️ |
| install_status | 설치 상태 | 비계 → "수직·수평 확인" | ⚠️ |
| collapse_risk | 붕괴 위험 | 비계 → "벽연결재 고정" | ⚠️ |
| binding | 결속 상태 | 비계 → "클램프 체결" | ⚠️ |
| crane_check | 크레인 점검 | 타워크레인 (CNS-016) | ⚠️ |
| brake | 브레이크 상태 | 타워크레인 → "브레이크 작동" | ⚠️ |
| wire | 와이어 상태 | 타워크레인 → "와이어 로프 마모" | ⚠️ |
| guard_check | 방호장치 점검 | 프레스 → "방호장치 작동" | ⚠️ |
| removed | 제거 여부 | 프레스 → "방호덮개 설치" | ⚠️ |
| gas_check | 가스시설 점검 | 가스탱크, LPG탱크 | ⚠️ |
| leak | 누출 여부 | 가스탱크 → "누출검지" | ⚠️ |
| valve | 밸브 상태 | 밸브 → "개폐 상태" | ⚠️ |
| facility_check | 시설 점검 | 화학물질탱크 | ⚠️ |
| storage | 저장 상태 | 저장탱크 → "밀봉 상태" | ⚠️ |

**해결 방법:**
- 간단 모드: field_key 1개로 "점검 했다" 기록 → 현재 작동
- 상세 모드: field_key → inspection_master의 해당 설비 항목 자동 매핑
- 두 모드 모두 문서 출력 가능 (상세도만 다름)

### D. 특수 계측 — ❌ 미수집

보일러·냉동기 전용. 숫자값 입력이 필요한 항목.

| field_key | field_name | 필요 DB | 상태 |
|-----------|-----------|---------|------|
| temperature | 온도 | `safety_inspection_results.value_number` | ⚠️ 컬럼 존재하나 미사용 |
| pressure | 압력 | `safety_inspection_results.value_number` | ⚠️ 컬럼 존재하나 미사용 |
| runtime | 운전시간 | `safety_inspection_results.value_number` | ⚠️ 컬럼 존재하나 미사용 |
| operation_condition | 운전 조건 | `safety_inspection_results.value_text` | ⚠️ 컬럼 존재하나 미사용 |
| equipment_status | 설비 상태 | `safety_inspection_results.result_code` | ✅ |

**발견:** `safety_inspection_results`에 `value_number`, `value_text` 컬럼이 이미 존재!
→ 앱에서 숫자 입력 UI만 추가하면 됨. DB 변경 불필요.

### E. TBM / 교육 / 공사일지 — △ 부분 수집

#### TBM (DOC-OSH-056, DOC-CON-012)

| field_key | field_name | 데이터 소스 | 상태 |
|-----------|-----------|------------|------|
| work_content | 작업내용 | `tbm_meetings.work_description` | ✅ |
| risk_share | 위험요인 공유 | `tbm_meetings.risk_items` (JSONB) | ✅ |
| participants | 참석자 | `tbm_attendees` | ✅ |
| signatures | 서명 | `tbm_attendees.signed_at` | ✅ |

**TBM은 완전 수집됨.** 문서 출력 준비 완료.

#### 보호구 (DOC-OSH-046)

| field_key | field_name | 데이터 소스 | 상태 |
|-----------|-----------|------------|------|
| ppe_check | 보호구 착용 여부 | `tbm_attendees.issue_flag` (반전) | ⚠️ TBM에 종속 |
| worker | 작업자 | `tbm_attendees.name` | ⚠️ TBM에 종속 |
| non_compliance | 미착용자 | `issue_flag = true` 인 참석자 | ⚠️ TBM에 종속 |
| action | 조치사항 | `tbm_attendees.issue_note` | ⚠️ TBM에 종속 |

**보호구 점검은 TBM의 서브셋.** TBM 서명 시 "보호구+건강 이상 없음" 확인하므로, TBM 데이터에서 추출 가능. 별도 모듈 불필요.

#### 교육 (DOC-OSH-006, 037, SERA-006) — ⏸ 보류

| field_key | field_name | 데이터 소스 | 상태 |
|-----------|-----------|------------|------|
| education_done | 교육 실시 | `education_history.status_code` | ✅ |
| education_hours | 교육시간 | `education_history.completed_hours` | ✅ |
| education_content | 교육내용 | `education_history.education_code` → 코드 매핑 | ⚠️ |
| education_datetime | 교육일시 | `education_history.completed_at` | ✅ |
| attendees | 참석자 | `education_history` (user_id별 1행) | ✅ |
| signatures | 서명 | 없음 | ❌ |
| target | 교육대상 | `education_history.user_id` → `users` | ✅ |

**교육 모듈 미운영 상태 → 교육 3건 문서 후순위 보류.**

#### 공사일지 (DOC-CON-006)

| field_key | field_name | 데이터 소스 | 상태 |
|-----------|-----------|------------|------|
| project_name | 공사명 | `construction_sites.name` | ✅ |
| date | 작성일자 | 자동 생성 | ✅ |
| work | 작업내용 | `construction_inspections` 또는 별도 | ⚠️ |
| progress | 공정 진행 | 없음 | ❌ |
| workers | 투입 인원 | `tbm_attendees` 집계 가능 | ⚠️ |
| equipment | 장비 사용 | `equipment_assets` | ⚠️ |
| safety | 안전관리 사항 | `tbm_meetings` + `safety_inspections` 조합 | ⚠️ |
| incident | 사고 발생 여부 | 없음 | ❌ |
| worker_list | 작업자 명단 | `tbm_attendees` | ⚠️ |
| risk | 위험요인 | `tbm_meetings.risk_items` | ✅ |
| photos | 사진 | `safety_inspection_results.photo_urls` | ✅ |
| instructions | 지시사항 | 없음 | ❌ |

**공사일지는 건설 전용 모듈이 별도 필요.** 법정 양식 존재.

---

## 3. 전체 요약

| 유형 | field_key 수 | ✅ 수집됨 | ⚠️ 부분/끊김 | ❌ 미수집 |
|------|------------|----------|-------------|----------|
| A. 메타데이터 | 8 | 7 | 0 | 1 (서명) |
| B. 결과 데이터 | 5 | 4 | 1 (risk 분리) | 0 |
| C. 설비별 체크리스트 | 18 | 0 | 18 | 0 |
| D. 특수 계측 | 4 | 1 | 3 (컬럼 있으나 미사용) | 0 |
| E-1. TBM | 4 | 4 | 0 | 0 |
| E-2. 보호구 | 4 | 0 | 4 (TBM 종속) | 0 |
| E-3. 교육 | 7 | 5 | 1 | 1 (서명) |
| E-4. 공사일지 | 12 | 4 | 5 | 3 |
| **합계** | **62** | **25 (40%)** | **32 (52%)** | **5 (8%)** |

---

## 4. 우선순위별 액션

### 즉시 가능 (코드 변경 없이 문서 출력 가능)

| 문서 | 데이터 소스 | 비고 |
|------|----------|------|
| TBM 기록 (DOC-OSH-056, CON-012) | tbm_meetings + tbm_attendees | ✅ 템플릿 완성됨 |
| 안전점검일지 간단모드 (DOC-OSH-007 등 6건) | safety_inspections + results | ✅ 템플릿 완성됨 |
| 보호구 점검 (DOC-OSH-046) | TBM 데이터에서 추출 | ✅ 별도 모듈 불필요 |

### 파이프라인 연결 필요 (inspection_master 매핑)

| 문서 | 필요 작업 | 설비 수 |
|------|----------|--------|
| 기계설비 (DOC-OSH-059) | master → set_items | 38종 |
| 전기설비 (DOC-OSH-060, BLD-009) | master → set_items | 7종 |
| 소방시설 (DOC-BLD-002) | master → set_items | 12종 |
| 승강기 (DOC-BLD-011) | master → set_items | 4종 |
| 비계 (DOC-CON-014, 026) | master → set_items | 4종 |
| 타워크레인 (DOC-CON-032) | master → set_items | 2종 |
| 장비 (DOC-CON-013) | master → set_items | 5종 |
| 가스시설 (DOC-FAC-002) | master → set_items | 3종 |
| 위험물 (DOC-FAC-008) | master → set_items | 2종 |
| 화학물질 (DOC-CHEM-003) | master → set_items | 2종 |

### 앱 UI 추가 필요

| 항목 | 필요 작업 | 우선순위 |
|------|----------|----------|
| 보일러 온도·압력·운전시간 (DOC-FAC-013) | value_number 입력 UI | 중 |
| 냉동기 운전조건 (DOC-FAC-016) | value_text 입력 UI | 중 |
| 점검자 서명 (inspector_sign) | 서명 기능 추가 | 낮음 |

### 별도 모듈 필요 (후순위)

| 항목 | 필요 작업 | 우선순위 |
|------|----------|----------|
| 공사일지 (DOC-CON-006) | 건설 전용 일일 보고 모듈 | 중 |
| 교육 문서 (3건) | 교육 모듈 가동 후 | 보류 |
| 석면 (DOC-BLD-016) | 석면 전용 상태 입력 | 낮음 |

---

## 5. 핵심 결론

1. **40%는 이미 수집됨** — TBM, 기본 점검, 메타데이터
2. **52%는 데이터 구조는 있으나 연결이 안 됨** — inspection_master 파이프라인
3. **8%만 진짜 새로 만들어야 함** — 공사일지 모듈, 서명
4. **특수 계측(온도·압력)은 DB 컬럼이 이미 존재** — 앱 UI만 추가하면 됨

→ 파이프라인 연결(inspection_master → inspection_set_items)이
   전체 갭의 핵심. 이것만 해결하면 52%가 해소됨.
