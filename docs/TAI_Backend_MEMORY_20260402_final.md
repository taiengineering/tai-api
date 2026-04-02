# TAI Backend 작업 메모리 — 2026-04-02 (최종)

> 백엔드 창 전용. 작성: Claude CTO 창

---

## 오늘 완료된 전체 작업 목록

### WORK_ORDER_20260402_backend.md (5개 작업)

| # | 파일 | 내용 |
|---|------|------|
| 1 🔴 | `legal_engine.py` | `_evaluate_facility_conditions_db()` — CONSTRUCTION + 산안법 제16조② + APPOINT/NOTIFY → worker_count >= 50 자동 발동 |
| 2 🔴 | `legal_engine.py` | `diagnose_step2()` — `work_type_codes` 직접 입력 파라미터 추가 (BLASTING·CRANE 대응) |
| 3 🟠 | `legal_engine.py` | `_get_construction_summary()` — `key_thresholds_met`에 `50명이상_안전관리자선임` / `300명이상_안전관리자선임` 추가 |
| 4 🟠 | `public_admin.py` | `rows_html()` — "서식" 컬럼 추가, form_url → `[form_code]` 링크 / ONLINE → `[온라인신고]` 링크 |
| 5 🟡 | `main.py` + `legal_engine.py` | 버전 → `5.2.5` / `5.3.1` |

### 긴급 수정 2건

| 수정 | 내용 |
|------|------|
| **코드 fix** | `_get_construction_summary` 억원 표시 버그: `threshold/100_000_000` → `threshold/10_000_000` (건축 15억→150억) |
| **DB fix** | `CONMACT-002-CON` (건설기계관리법 제26조), `CONST-TECH-002` (건설기술진흥법 시행령 제98조의3) → `contract_amount >= 100,000,000` 조건 추가 (소규모 현장 과잉 트리거 방지) |

### WORK_ORDER_20260402_construction_input.md — v5.4.0 (7개 수정)

| # | 수정 내용 |
|---|-----------|
| 1 | `ENGINE_VERSION` → `"5.4.0"` |
| 2 | `DiagnoseStep1Body` CONSTRUCTION 전용 명시적 필드 7개 추가: `construction_type`, `direct_workers`, `subcon_workers`, `electrical_capacity_kw`, `has_tunnel_bridge`, `has_blasting`, `has_crane` |
| 3 | `diagnose_step1` `flat_fields`에 7개 건설 전용 필드 추가 |
| 4 | `_input_to_facility_context` CONSTRUCTION 분기: `has_blasting`, `has_crane`, `electrical_capacity_kw`(임시전기 75kW 이상 → 전기안전관리자 선임 트리거) 파싱 추가 |
| 5 | `_get_construction_summary` 억원 표기 버그 수정 (이미 완료, 재확인) |
| 6 | `diagnose_step2`: `factory_id` 없어도 익명 진단 지원, `sector` 기본값 `CONSTRUCTION`, DB 저장 조건부 처리 |
| 7 | `diagnose_step3`: `inspection_schedules` 하드코딩 2년 → DB 실제 점검주기 조회 (`eq_cycle_map`) |

---

## 최종 버전 현황

| 파일 | 버전 |
|------|------|
| `main.py` | **v5.2.5** |
| `routers/legal_engine.py` | **v5.4.0** |
| `routers/public_admin.py` | **v1.1.0** |
| `routers/alert_messages.py` | v1.0.0 |
| `routers/feature_flags.py` | v1.0.0 |

---

## DB 변경 사항

| 항목 | 내용 |
|------|------|
| `CONMACT-002-CON` | `condition_code=contract_amount`, `gte`, `100000000` 추가 |
| `CONST-TECH-002` | `condition_code=contract_amount`, `gte`, `100000000` 추가 |

---

## 핵심 설계 결정 (오늘 확정)

1. **임시전기 용량** — `electrical_capacity_kw` 파라미터로 직접 입력, `electric_capacity` + `electrical_capacity_kw` + `transformer_capacity_kva` 모두 동일값 설정 (룰 코드 다양성 대응)
2. **발파·크레인** — `has_blasting`, `has_crane` boolean → `work_type_codes`에 BLASTING·CRANE 포함해서 step2에 전달하는 방식 병행
3. **step2 익명 진단** — factory_id 없으면 DB 저장/이벤트 생성 스킵, sector 기본값 CONSTRUCTION
4. **step3 점검주기** — DB `master_building_legal_rules`에서 실제 주기 조회 → 없으면 2년 기본값 유지
5. **소규모 현장 과잉 트리거** — 건설기계관리법·건설기술진흥법 시행령 2개 룰에 1억 이상 조건 추가로 해결

---

## PENDING (다음 세션)

- [ ] Railway 배포 확인: `GET https://api.taieng.co.kr/` → `"version":"5.2.5"` (main.py 버전 기준)
- [ ] legal_engine v5.4.0 배포 확인 (Railway는 main.py version 표시, engine version은 `/diagnose/step1` 응답 확인)
- [ ] 건설 법령엔진 검증 3가지 시나리오
  - 건축 150억 + 60명 → `safety_manager_required=true`, `safety_manager_basis="건축 150억원 이상, 근로자 60명 >= 50명"`
  - 건축 100억 + 55명 → `safety_manager_required=true` (인원 조건으로 발동)
  - 건축 150억 + `electrical_capacity_kw=75` → appointment에 전기안전관리자 포함
- [ ] contracts.plan_code 정합성 작업 (INDUSTRY_PRO → BUSINESS 등 매핑)
- [ ] 12개 법령 수집 (data.go.kr: 근로기준법, 소음진동관리법 등)
- [ ] 80개 report-obligation rules → form_code 매핑
- [ ] Cloudflare Zero Trust Access (taieng.co.kr 잠금)
- [ ] **공지예외주장 제출 기한: 2026-04-28** (patent.go.kr)

---

## 오늘 생성/수정된 GitHub 파일

```
routers/legal_engine.py     v5.4.0 (7개 수정)
routers/public_admin.py     v1.1.0 (form_url 링크)
routers/alert_messages.py   v1.0.0 (신규)
routers/feature_flags.py    v1.0.0 (신규)
main.py                     v5.2.5
docs/WORK_ORDER_20260402_backend.md
docs/WORK_ORDER_20260402_construction_input.md
docs/TAI_Backend_MEMORY_20260402_final.md  (이 파일)
```
