# TAI Safe Backend (tai-api) - Session Memory
**마지막 업데이트: 2026-04-06 (2차 세션)**

**제품·아키텍처 공유**: [`docs/TAI_전체_작업_정리_공유용.md`](./TAI_전체_작업_정리_공유용.md)

---

## ✅ 이번 세션 완료 작업 (2026-04-06 2차)

### 법령엔진 무결성 검증 — 78건 ALL PASS 확정
- ✅ 기준 26건 (정방향11 + 역방향11 + 비교2 + 격리2) ALL PASS → `tests/test_legal_engine.py` v2.0
- ✅ 추가 52건 (다른 수치·복합·극단값) ALL PASS → `tests/test_legal_engine_52.py` v1.0
- ✅ 단계별 30건 (L1설비 + L2공정step2 + L3복합+미입력) → `tests/test_legal_engine_layer.py` v1.0
- ✅ `docs/ENGINE_INTEGRITY.md` — 무결성 기준 문서화

### DB 버그 수정
- ✅ `GASACT-001`: condition_code `gas_capacity_kg` → `has_high_pressure_gas` (산업 가스 미발동 수정)
- ✅ `HAZMAT-015-MFG-V2`: appointment_target_code `safety_manager` → `hazardous_material_manager`
- ✅ 한글 appointment_target_code 전체 → 영문 코드 정규화 (소방안전관리자, 승강기 안전관리자 등)

### 엔진 코드 업그레이드
- ✅ v5.6.1: MANUFACTURING gas/boiler boolean→수치 변환, elevator_count BUILDING step1 지원, 한글 target 정규화
- ✅ v5.6.2: `format_rule_result_db()` inspection_cycle 4필드 완비 (언제/누가/무엇/어떻게), schedule_type 분류
- ✅ v5.6.3: `DiagnoseStep1Body`에 수치 필드 추가 (gas_capacity_kg, boiler_capacity_kw, elevator_count 등)

### 점검(INSPECT) 4필드 분석
- ✅ 건물 4완비: 106/124건 (85%)
- ✅ 산업 4완비: 56/78건 (72%)
- ⚠️ 건설 4완비: 9/73건 (12%) — 구조적 문제 (작업 전 점검 = 주기 없음)
- ✅ 점검 유형 2가지로 분리 설계: PERIODIC(정기) / BEFORE_WORK(작업전) / ON_DEMAND(수시)

### 가스 조건값 분석 결론
- gas_capacity_kg 조건값 100/300/1000은 법적으로 정확한 단계별 임계값 — 수정 불가
- 해결책: DiagnoseStep1Body에 gas_capacity_kg 수치 직접 입력 필드 추가 (v5.6.3)

---

## 🚨 배포 상태 (중요)
- **GitHub**: v5.6.3 최신 코드 반영됨
- **Railway**: v5.5.2 운영 중 (v5.6.x 미배포 — 수동 재배포 필요)
- Railway 대시보드에서 수동 배포 트리거 필요

---

## ✅ 이전 세션 완료 작업 (2026-04-06 1차)
- ✅ AI 생성 룰 937개 비활성화 (condition_code 미설정 → is_active=false)
- ✅ `GET /drafts` has_condition 필터 추가 (law_rule_generator v1.5.0)
- ✅ `main.py` v5.6.0 업데이트
- ✅ condition_code 입력 우선순위 목록 작성

---

## 📋 현재 DB 상태

| 테이블 | 현황 |
|--------|------|
| `master_building_legal_rules` | active 1,206건 (BUILDING 479 / MANUFACTURING 408 / CONSTRUCTION 181 / COMMON 88 등) |
| `law_rule_drafts` | APPROVED 1,330 / PENDING 263 / REJECTED 559 |
| `inspection_sets` | 68개 활성 일정 |
| `document_form_master` | 10종 (TAI표준서식) |

## 📋 점검 룰 4필드 완비 현황

| 섹터 | 전체 | 4완비 | 완비율 |
|------|------|-------|--------|
| BUILDING | 124 | 106 | 85% |
| MANUFACTURING | 78 | 56 | 72% |
| CONSTRUCTION | 73 | 9 | 12% |
| COMMON | 15 | 0 | 0% |

---

## 📋 다음 작업 (우선순위순)

1. **Railway 수동 재배포** → v5.6.3 배포 확인 후 점검 검증 완료
2. **점검(INSPECT) 78건 무결성 테스트** (배포 후) — 언제/누가/무엇을 전부 검증
3. **건설 INSPECT 주기 없는 64건** — BEFORE_WORK 타입으로 cycle_type 컬럼 추가 여부 결정
4. **COMMON 점검 15건 주기 없음** — 수기 입력 또는 ON_DEMAND 처리
5. **step1→step2 연계 흐름** 검증 (diagnosis_id 전달)
6. **점검주기 → 일정 자동생성** 연계 검증
7. **ACTION/REPORT 룰 과다** — 조건 없이 발동되는 룰 정리
8. PENDING 263개 수동 검토

---

## 🔐 인증 / 계정
- **Admin**: hetto@kakao.com (role 001)
- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (GitHub: v5.6.3 / 운영: v5.5.2)

## 📌 주의사항
1. **API 사이즈 제한**: `size <= 100` (pagination 필수)
2. **라우트 순서**: 구체적 경로(/bulk, /stats)를 /{id} 앞에 선언
3. **SHA 필수**: create_or_update_file 시 현재 SHA 먼저 조회
4. **무결성 원칙**: 법령 추가/수정/엔진 변경 시 반드시 `python tests/test_legal_engine.py` + `python tests/test_legal_engine_52.py` 통과 후 배포
5. **가스 조건값**: gas_capacity_kg=100/300/1000 은 법적 기준 — 수정 금지
6. **공지예외주장 기한: 2026-04-28** (patent.go.kr)
