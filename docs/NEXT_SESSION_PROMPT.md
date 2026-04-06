# TAI Safe 신규 창 시작 프롬프트
**작성일: 2026-04-07 5차 세션 종료 | 목적: 서식매핑·E2E테스트·완성도 고도화**

---

## 🎯 현재 상황 요약

### ✅ 이번 세션(5차) 완료된 것

**법령엔진 완성도 분석 & 의무 데이터 보강:**
- ✅ 건설 ACTION 46건 condition_code 입력 완료 (`construction_amount`)
- ✅ 건물 DOCUMENT 46건 condition_code 입력 완료 (법령별 분류)
- ✅ 산업 REPORT 22건 condition_code 입력 완료
- ✅ 산업 ACTION 29건 condition_code 입력 완료
- ✅ **전 섹터 핵심 완성도: 건물 ~98% / 산업 ~98% / 건설 ~95%**

**서식 매핑 (document_form_master) 대폭 확장:**
- ✅ `executor_type_code`, `executor_role`, `submit_deadline_days`, `submit_frequency` 컬럼 추가
- ✅ 서식 27건 → **63건** 확장
  - APPOINT 선임신고서 8종 신규 추가 (안전/보건/소방/전기/가스/승강기/에너지/위험물)
  - INSPECT 점검기록서 10종 신규 추가 (승강기/소방/전기/가스/위험물/보일러/작업환경 등)
  - BEFORE_WORK 작업전점검표 18종 신규 추가 (공종별 전종)
- ✅ 의무-서식 매핑 (`form_code`) 대폭 개선
  - APPOINT: 16% → **60%**
  - INSPECT: 11% → **57%**
  - BEFORE_WORK: 0% → **83%**
  - DOCUMENT: 0% → **100%**

**E2E 종단간 테스트 추가:**
- ✅ `tests/test_e2e_form_flow.py` 생성 — 12시나리오 더미데이터 테스트
  - 건물 4종 (소형/중형/대형/가스특수)
  - 산업 4종 (소형/중형위험물/화학대형/에너지대형)
  - 건설 4종 (소규모/중규모/대규모/토목대형)
  - BEFORE_WORK 공종별 서식 연결 검증
  - 의무→서식→제출기관→이행주체 전체 흐름 검증

### ⚠️ 잔여 과제 (다음 세션)
- 산업 INSPECT 서식 매핑 3% → 목표 50%+
- 건설 INSPECT 서식 매핑 0% → 법정검사 13건 매핑 필요
- REPORT condition 완비율: COMMON 12%, MANUFACTURING 60%
- Railway "Wait for CI" 미활성
- PENDING 잔류 1건: ELEV-039-CMN

---

## 📊 현재 데이터 현황 (2026-04-07 기준)

### 의무 완성도 (누가/언제/무엇을/조건)
| 섹터 | 완성도 | 잔여 이슈 |
|---|---|---|
| BUILDING | **~98%** | REPORT 5건 condition 미비 |
| MANUFACTURING | **~98%** | 거의 완전 |
| CONSTRUCTION | **~95%** | DOCUMENT 3건, REPORT 3건 미비 |

### 서식 매핑 현황 (form_code)
| 타입 | 완비율 | 비고 |
|---|---|---|
| DOCUMENT | **100%** | ✅ 완전 |
| OTHER | **100%** | ✅ 완전 |
| REPORT | **78%** | 보고서식 대부분 연결 |
| NOTIFY | **72%** | 신고서식 대부분 연결 |
| BEFORE_WORK | **83%** | 공종별 점검표 18종 |
| APPOINT | **60%** | 선임신고서 7종 |
| INSPECT | **57%** | 점검기록서 10종 |
| ACTION | **5%** | 조치류는 서식 없음이 정상 |

### document_form_master
- 총 63건 (이전 27건)
- 신규 필드: executor_type_code, executor_role, submit_deadline_days, submit_frequency
- 서식별 "언제/누가/어디에/어떻게" 완비

### 활성 룰 구성
- 전체 활성: ~1,196건
- BEFORE_WORK: 60건 / INSPECT: 234건 / APPOINT: 49건
- law_rule_drafts: APPROVED 1,566 / PENDING 1 / REJECTED 585

---

## 📋 다음 세션 목표

### 1️⃣ 시작 시 현황 확인
```sql
-- 서식 매핑 현황
SELECT obligation_type,
  COUNT(*) AS total,
  COUNT(CASE WHEN form_code IS NOT NULL THEN 1 END) AS has_form,
  ROUND(COUNT(CASE WHEN form_code IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100, 0) AS form_ratio
FROM master_building_legal_rules
WHERE is_active=true AND sector IN ('BUILDING','MANUFACTURING','CONSTRUCTION')
GROUP BY obligation_type ORDER BY obligation_type;

-- document_form_master 현황
SELECT form_type, obligation_type, COUNT(*) FROM document_form_master
WHERE is_active=true GROUP BY form_type, obligation_type ORDER BY form_type;
```

### 2️⃣ 우선 과제
1. **산업/건설 INSPECT 서식 매핑** — 현재 3~0%, 목표 50%+
2. **스케줄 자동생성** — INSPECT 룰 → 점검 일정 자동 생성 로직
3. **Railway Wait for CI 설정**
4. **BEFORE_WORK 체크리스트 UI 연동**

### 3️⃣ 수정 후 필수 검증
```
GitHub push → Actions 자동 실행 → 4개 Job 모두 ✅ 확인
https://github.com/taiengineering/tai-api/actions
```

---

## 📌 서식 구조 설계 (document_form_master)

```
언제: trigger_event + submit_timing + submit_deadline_days + submit_frequency
누가: executor_type_code (anyone/qualified/external/appointed) + executor_role (구체 역할)
어디에: submit_agency (기관명) + submit_org_code 참조
어떻게: submit_method (api/mail/visit/fax/keep)
보존: retention_years + retention_start
```

### 주요 서식 코드 목록
```
[APPOINT] APPOINT-SAFE/HLTH/FIRE/ELEC/GAS/ELEV/ENERGY/HAZ-001
[INSPECT] INSPECT-ELEV/FIRE/ELEC/GAS/HAZ/BLD/BOIL/WORKEN-001
[BEFORE_WORK] BW-CRANE/TCR/MCR/SCF/EXC/HIGH/CONF/BLAST/CCP/FORM/REINF/STEEL/WELD/TELEC/HST/LFT/GDL/TUN-001
[STANDARD] STD-ACC/COST/EDU/ELEC/ENV/FIRE/HEALTH/INSPECT/MTG/RISK-001
[LEGAL] LEGAL-OSHH-001~008, LEGAL-CONST-001~002, LEGAL-FIRE/GAS-001
```

---

## 📌 엔진 핵심 상수 (변경 금지)

### 가스 단계별 임계값 (법적 기준 — 절대 수정 금지)
```
gas_capacity_kg >= 1    → 기본 점검/선임
gas_capacity_kg >= 100  → 정기검사
gas_capacity_kg >= 300  → 추가 검사
gas_capacity_kg >= 1000 → 특별 의무
```

### obligation_type 허용값
```
APPOINT / INSPECT / ACTION / REPORT / NOTIFY / DOCUMENT / OTHER / BEFORE_WORK
```

### has_appt() 비교 주의
```python
APPOINTMENT_TARGET_MAP = {
  "safety_manager": "안전관리자",
  "electric_safety_manager": "전기안전관리자",
  "gas_safety_manager": "가스안전관리자",
  "elevator_safety_manager": "승강기안전관리자",
  "energy_manager": "에너지관리자",
  "hazardous_material_manager": "위험물안전관리자",
  ...
}
def has_appt(data, target_code):
    label = APPOINTMENT_TARGET_MAP.get(target_code, target_code)
    return any(r.get("appointment_target") in (target_code, label)
               for r in data.get("appointment_required", []))
```

---

## 🔐 인증
- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (v5.6.4)
- **Admin**: hetto@kakao.com (role 001)
- **GitHub**: taiengineering/tai-api (main branch)

## 📌 절대 원칙
1. API 사이즈: `size <= 100`
2. SHA 필수: create_or_update_file 시 현재 SHA 먼저 조회
3. 무결성 원칙: 변경 후 CI 4-Job 통과 확인 필수
4. **공지예외주장 기한: 2026-04-28** (patent.go.kr) ← D-21
5. 가스 조건값 수정 금지 (100/300/1000 kg)
