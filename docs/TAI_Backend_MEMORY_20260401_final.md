# TAI Backend 작업 메모리 — 2026-04-01 (최종)

> 백엔드 창 전용. 작성: Claude CTO 창

---

## 오늘 완료된 전체 작업 목록

### 1. legal_engine.py v5.1.0 — 건설 법령엔진 버그수정 (기존 완료 확인)
- `CONDITION_CODE_TO_CONTEXT_KEY`에 `contract_amount`, `electric_capacity` 추가
- CONSTRUCTION context 완성 (site_type, subcon_workers, contract_amount, employee_count)
- `construction_summary` 블록 추가 (safety_manager_required, key_thresholds_met)
- `ENGINE_VERSION = "5.1.0"`

### 2. legal_engine.py v5.2.0 — KCSC 공정·작업 연동
- `diagnose/step2`: `kcsc_process_ids` → `kcsc_process_master`에서 `work_type_code` 자동 조회
  - 기존 `construction_work_types` 하위 호환 유지
  - 응답에 `kcsc_process_summary` 추가
- `diagnose/step3`: `construction_work_ids` / `kcsc_work_ids` → `kcsc_work_master`에서 `equipment_type_codes` 자동 조회
  - 기존 `equipments` 직접 입력 하위 호환 유지
  - 응답에 `kcsc_work_summary`, `equipment_codes_applied` 추가

### 3. public_admin.py — 상태 업데이트 API 확인 (main.py v5.2.1)
- `PATCH /{id}/status` 이미 존재 확인
- `admin_memo`, `result_sent_at`, `result_html` 컬럼 모두 존재 확인
- CORS `taieng.co.kr` 이미 있음 확인
- main.py 버전 5.2.1 bump

### 4. alert_messages.py v1.0.0 신규 생성 (main.py v5.2.2)
- `GET /alert-messages` — 목록 (role 001)
- `GET /alert-messages/codes` — 전체 코드:메시지 딕셔너리 **(인증 불필요, 프론트 JS용)**
- `GET /alert-messages/contexts` — context 목록 (role 001)
- `POST /alert-messages` — 신규 등록 (중복 코드 검사 포함)
- `PATCH /alert-messages/{id}` — 수정
- `PATCH /alert-messages/{id}/toggle` — is_active 토글
- `DELETE /alert-messages/{id}` — 비활성화 처리

### 5. B-CON-001 — 건설 전용 필드 + legal_engine.py v5.3.0

#### DB Migration
```sql
ALTER TABLE factories
  ADD COLUMN IF NOT EXISTS construction_type VARCHAR(20)
    CHECK (construction_type IN ('건축','토목','공통','기타')) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS subcontractor_worker_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_worker_count_calc INTEGER
    GENERATED ALWAYS AS (
      COALESCE(employee_count,0) + COALESCE(subcontractor_worker_count,0)
    ) STORED;
```
※ `worker_count` 없어서 `employee_count` 사용

#### factories.py v2.2.0
- `FactoryCreate`, `FactoryUpdate` 모두 `construction_type`, `subcontractor_worker_count` 추가

#### legal_engine.py v5.3.0
- `get_effective_worker_count(factory)`: CONSTRUCTION → employee_count + subcontractor_worker_count
- `get_construction_amount_threshold(factory)`: 건축 150억 / 토목·공통·기타 120억
- `_factory_to_context()`: CONSTRUCTION 시 하도급 자동 합산
- `_get_construction_summary()`: construction_type 기반 동적 임계값
- `_input_to_facility_context()`: subcon_workers + subcontractor_worker_count 파라미터 통합, 영문코드(BUILDING/CIVIL) → 한글 변환
- `apply_legal_engine` `triggered_by_source`에 construction_type, total_worker_count, subcontractor_count, threshold_used 추가

### 6. B-CON-002 — 건설 룰 데이터 정비 (Supabase execute_sql)

#### 작업 1: construction_work_type 입력
| work_type | 건수 |
|-----------|------|
| 건축 | 2 (CONST-003 비활성, OSH-CON-102 활성) |
| 토목 | 2 (CONST-004 비활성, OSH-CON-101 활성) |
| 공통 | 181 |
| NULL | **0** ✅ |

#### 작업 2: 조건 없는 룰 분류
- COMMON 표기: 9건 (CON1-ACC-002, CON1-CON-001/002, CON1-EDU-002 등)
- NEED_CONDITION 복원: 3건 (CON1-COM-001/002, CON1-REG-001 → condition_code=employee_count, gte, 100)
- SECTOR_MISMATCH remarks 추가: 28건 (이미 is_active=false)

#### 최종 검증 결과
| stage | is_active | null_worktype |
|-------|-----------|---------------|
| 1 | false | 0 ✅ |
| 1 | true | 0 ✅ |

### 7. B-FEAT-001 — 섹터×플랜 Feature Flag 시스템 (main.py v5.2.3)

#### DB Migration
- `system_codes`: `plan_code` 4개 (STARTER/BUSINESS/ENTERPRISE/CUSTOM)
- `system_codes`: `sector` 4개 (BUILDING/INDUSTRY/CONSTRUCTION/SPECIAL)
- `factories.sector` VARCHAR(20) CHECK 추가 + site_type 기반 자동 매핑
- `factories.plan_code` VARCHAR(20) DEFAULT 'STARTER' 추가
- `factory_features` 테이블 신규 생성
- `factory_features` 기초 데이터 28건 INSERT (ALL 12, INDUSTRY 7, BUILDING 3, CONSTRUCTION 6)

#### feature_flags.py v1.0.0 신규
- `GET /feature-flags?sector=&plan=` → open/locked/hidden 분류 반환
- `GET /feature-flags/all` — 전체 목록 (관리자·개발용)

### 8. f-string 백슬래시 버그 수정 (Python 3.11)

**수정 1 — `_get_construction_summary`**
```python
# 수정 전: f-string 내 백슬래시 → SyntaxError
basis_parts = [f"... {'이상' if ... else '미만'}"]
# 수정 후
_cmp_label = "이상" if amount >= threshold else "미만"
basis_parts = [f"... {_cmp_label}"]
```

**수정 2 — `create_inspection_sets_from_legal`**
```python
# 수정 전
f"... {'년' if cycle_unit == 'year' else '개월'}마다"
# 수정 후
_unit_label = "년" if cycle_unit == "year" else "개월"
f"... {cycle_value}{_unit_label}마다"
```

---

## 최종 버전 현황

| 파일 | 버전 |
|------|------|
| `main.py` | **v5.2.3** |
| `routers/legal_engine.py` | **v5.3.0** (f-string fix 포함) |
| `routers/factories.py` | **v2.2.0** |
| `routers/alert_messages.py` | **v1.0.0** (신규) |
| `routers/feature_flags.py` | **v1.0.0** (신규) |
| `routers/public_admin.py` | 기존 유지 (status endpoint 확인) |

---

## DB 최종 상태

| 테이블/컬럼 | 상태 |
|------------|------|
| `factories.construction_type` | ✅ VARCHAR(20) CHECK |
| `factories.subcontractor_worker_count` | ✅ INTEGER DEFAULT 0 |
| `factories.total_worker_count_calc` | ✅ GENERATED STORED (employee_count + subcon) |
| `factories.sector` | ✅ VARCHAR(20) DEFAULT 'INDUSTRY' |
| `factories.plan_code` | ✅ VARCHAR(20) DEFAULT 'STARTER' |
| `system_codes` plan_code | ✅ 4개 |
| `system_codes` sector | ✅ 4개 |
| `factory_features` | ✅ 28건 |
| CONSTRUCTION 룰 null_worktype | ✅ 0건 |
| CON1-COM-001/002, CON1-REG-001 | ✅ condition_code=employee_count gte 100 복원 |

---

## 핵심 설계 결정 (오늘 확정)

1. **factories.worker_count 없음** — `employee_count` 사용. `total_worker_count_calc = employee_count + subcontractor_worker_count`
2. **건설 안전관리자 선임 임계값** — 건축 150억 / 토목 120억 (한글 코드 기준). 영문코드(BUILDING/CIVIL)도 자동 변환
3. **f-string 백슬래시 규칙** — Python 3.11부터 f-string 내 `\` 불가. 삼항 표현식이 한글 포함 시 반드시 변수로 분리
4. **Feature Flag 구조** — `factory_features`(마스터) + `GET /feature-flags?sector=&plan=` → open/locked/hidden 3분류
5. **plan_code 실제값** — contracts 테이블 기존 값: INDUSTRY_PRO, STANDARD, null → Feature Flag와 별도 관리, 향후 정합성 작업 필요

---

## PENDING (다음 세션 이어받기)

- [ ] Railway 배포 완료 확인 (`GET https://api.taieng.co.kr/` → `"version":"5.2.3"`)
  - 현재 502 상태 (빌드 중 또는 에러 가능성)
- [ ] 건설 법령엔진 검증 3가지 시나리오 (배포 후)
  - 시나리오1: 건축 200억/80명 → safety_manager_required=true, applicable_count>=10
  - 시나리오2: 토목 50억/20명 → safety_manager_required=false, 1억 기준 충족
  - 시나리오3: 건축 1200억 → 1000억_건설안전판정사=true
- [ ] contracts.plan_code 정합성 작업 (INDUSTRY_PRO → BUSINESS 등 매핑)
- [ ] 12개 법령 수집 (data.go.kr: 근로기준법, 소음진동관리법 등)
- [ ] 80개 report-obligation rules → form_code 매핑
- [ ] Cloudflare Zero Trust Access (taieng.co.kr 잠금)
- [ ] **공지예외주장 제출 기한: 2026-04-28** (patent.go.kr)

---

## 오늘 생성된 GitHub 파일 목록

```
routers/legal_engine.py        v5.3.0 (f-string fix 포함)
routers/factories.py           v2.2.0
routers/alert_messages.py      v1.0.0 (신규)
routers/feature_flags.py       v1.0.0 (신규)
main.py                        v5.2.3
docs/TAI_Backend_MEMORY_20260401_final.md  (이 파일)
```
