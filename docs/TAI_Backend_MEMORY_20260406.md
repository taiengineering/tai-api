# TAI Backend 작업 메모리 — 2026-04-06

> 백엔드 창 전용. 작성: Claude CTO 창

---

## 최종 버전 현황

| 파일 | 버전 | 커밋 |
|------|------|------|
| `main.py` | **v5.6.0** | `6db67f3` |
| `routers/law_rule_generator.py` | **v1.5.0** | `4cbce6a` |
| `routers/contract_kmong.py` | **v1.0.0** | `71f3532` |
| `routers/engine_document.py` | **v1.0.0** | 기존 |
| `routers/legal_engine.py` | **v5.4.2** | 기존 |

---

## 오늘 완료된 작업

### 작업1: AI 생성 룰 937개 비활성화 ✅
```sql
UPDATE master_building_legal_rules
SET is_active = false,
    review_reason = 'condition_code 미설정 — 수동 검토 필요',
    needs_review = true
WHERE source_api = 'AI_GENERATED'
  AND condition_code IS NULL
  AND is_active = true;
```
**결과**: active_count=1143 / inactive_count=1144 / needs_review_count=938

### 작업2: GET /drafts has_condition 필터 추가 ✅
- `law_rule_generator.py` v1.5.0
- `has_condition=false` → condition_code IS NULL
- `has_condition=true` → condition_code IS NOT NULL
- `has_condition=""` → 전체

### 작업3: main.py v5.6.0 ✅
- v5.5.5 → v5.6.0 버전업
- 변경 내역 주석 정리

### 작업4: 크몽 법령진단 API (contract_kmong.py v1.0.0) ✅
| Method | URL | 설명 |
|--------|-----|------|
| POST | `/contract/kmong/{id}/engine` | 법령엔진 판정 → diagnosis_result 저장, IN_REVIEW |
| PATCH | `/contract/kmong/{id}` | status_code / result_html / admin_memo 수정 |
| POST | `/contract/kmong/{id}/pdf` | result_html → xhtml2pdf → Storage → result_pdf_url |
| GET | `/contract/kmong` | 목록 (page/size/search/status/source) |
| GET | `/contract/kmong/{id}` | 단건 조회 |

---

## 데이터 분석 리포트 (2026-04-06)

### PENDING 262개 법령별 condition 없는 비율

| 법령 | 전체 | no_condition | 비율 |
|------|------|-------------|------|
| 고압가스 안전관리법 | 42 | 42 | 100% |
| 시설물의 안전 및 유지관리에 관한 특별법 | 31 | 31 | 100% |
| 도시가스사업법 | 28 | 28 | 100% |
| 산업안전보건기준에 관한 규칙 | 34 | 26 | 76% |
| 소방시설 설치 및 관리에 관한 법률 | 15 | 14 | 93% |
| 화학물질관리법 | 21 | 11 | 52% |
| 액화석유가스의 안전관리 및 사업법 | 27 | 11 | 41% |
| 에너지이용 합리화법 | 11 | 9 | 82% |
| 승강기 안전관리법 | 19 | 8 | 42% |
| 산업안전보건법 | 9 | 8 | 89% |
| 전기안전관리법 | 8 | 8 | 100% |
| 위험물안전관리법 | 16 | 1 | 6% |

### BUILDING 섹터 완성도 (is_active=true)

| rule_type_code | 총 룰 | condition 있음 | 주기 있음 | 상태 |
|---------------|------|--------------|---------|------|
| 001 (선임) | 38 | 38 ✅ | — | 완성 |
| 002 (점검) | 118 | 118 ✅ | 108 (92%) | 양호 |
| 003 (신고) | 79 | 78 ✅ | 1 | 양호 |
| 004 (보고) | 10 | 10 ✅ | 1 | 완성 |
| 005 (조치) | 143 | 143 ✅ | 1 | 완성 |
| 007 | 14 | 14 ✅ | 8 (57%) | 주기 보완 필요 |
| 008 | 14 | 14 ✅ | 14 ✅ | 완성 |
| **NULL** | **52** | **0 ❌** | **0 ❌** | **🚨 전체 미완성** |

**핵심 문제**: rule_type_code=NULL 52개 → 진단 사용 불가. 즉시 분류 필요.

### inspection_sets 미생성 INSPECT 룰 (50건 추출)

법령별 분포:
| 법령 | 미생성 수 | 우선순위 |
|------|---------|--------|
| 승강기 안전관리법 | 12건 | 🔴 최우선 |
| 고압가스 안전관리법 | 4건 | 🔴 위험설비 |
| 시설물의 안전 및 유지관리에 관한 특별법 | 4건 | 🟡 |
| 액화석유가스의 안전관리 및 사업법 | 3건 | 🟡 |
| 다중이용업소의 안전관리에 관한 특별법 | 2건 | 🟡 |
| 기타 | 25건 | 🟢 |

---

## condition_code 입력 우선순위 목록

| 순위 | 법령명 | 의무유형 | 추정 condition_code | 근거 |
|------|--------|---------|-------------------|------|
| 1 | 고압가스 안전관리법 | INSPECT | `gas_capacity_kg` | 저장량 기준 (250kg 등 임계값) |
| 2 | 고압가스 안전관리법 | ACTION | `gas_capacity_kg` | 동일 법령 동일 기준 |
| 3 | 시설물의 안전 및 유지관리에 관한 특별법 | INSPECT | `building_area` | 1·2종 시설물 연면적·층수 기준 |
| 4 | 도시가스사업법 | INSPECT | `gas_capacity_m3` | 도시가스 사용량(㎥/시) 기준 |
| 5 | 도시가스사업법 | ACTION | `gas_capacity_m3` | 동일 법령 기준 |
| 6 | 산업안전보건기준에 관한 규칙 | ACTION | `worker_count` | 작업자 수 기준 안전조치 |
| 7 | 소방시설 설치 및 관리에 관한 법률 | INSPECT | `building_area` | 연면적 기준 소방시설 점검 |
| 8 | 에너지이용 합리화법 | INSPECT | `annual_energy_toe` | 에너지 다소비 사업장 (2,000TOE) |
| 9 | 산업안전보건법 | APPOINT | `worker_count` | 상시 50명·100명 기준 선임 |
| 10 | 전기안전관리법 | INSPECT | `electric_capacity` | 수전용량 75kW 이상 |
| 11 | rule_type_code=NULL 52개 | 전체 | — | rule_type_code 분류 선행 필요 |

---

## PENDING (다음 세션)

- [ ] rule_type_code=NULL 52개 분류 (진단 사용 불가 상태)
- [ ] 승강기 안전관리법 INSPECT 12건 → inspection_sets 즉시 생성 가능
- [ ] 고압가스 안전관리법 42건 → condition_code `gas_capacity_kg` 일괄 입력
- [ ] PENDING 262개 수동 검토
- [ ] Railway 배포 확인: `GET https://api.taieng.co.kr/` → `"version":"5.6.0"`
- [ ] 공지예외주장 제출 기한: **2026-04-28** (patent.go.kr)
