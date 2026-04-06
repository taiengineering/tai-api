# TAI Safe 신규 창 시작 프롬프트
**작성일: 2026-04-06 4차 세션 종료 | 목적: 법령엔진·데이터 고도화 완료**

---

## 🎯 현재 상황 요약

### ✅ 이번 세션(4차) 완료된 것
- ✅ MCP 복구: Supabase 인증 재설정 완료
- ✅ **INSPECT 4완비율 전 섹터 100%** (BUILDING/MANUFACTURING/CONSTRUCTION/COMMON 모두)
- ✅ **BEFORE_WORK** 신규 obligation_type 추가 — CONSTRUCTION 64건 분리
  - `chk_obligation_type_allowed_values` 제약조건에 BEFORE_WORK 추가
  - 작업 전 점검 60건 → BEFORE_WORK, 법정 안전검사 13건 → INSPECT 유지
- ✅ **PENDING 262건 처리 완료** (1건만 잔류 — ELEV-039-CMN, 신뢰도 60)
  - APPROVED: 1,566건 / REJECTED: 585건
- ✅ **무결성 점검 완료** — condition_value 이상값 5건 수정, 중복 3건 비활성화
- ✅ **CI 4-Job 파이프라인 완성** — Layer 테스트 29건 추가, ALL PASS
  - [1] DB 무결성 (10항목, BEFORE_WORK 포함)
  - [2] 정적 매핑 커버리지
  - [3] API 78건
  - [4] 단계별 Layer 29건 (정방향+역방향) ← 신규

### ⚠️ 미완료
- Railway "Wait for CI" 미활성 — Service → Settings → GitHub → Wait for CI 체크 필요
- REPORT condition 완비율 낮음: COMMON 12% (6/50), MANUFACTURING 60.7% → 다음 세션
- PENDING 잔류 1건: ELEV-039-CMN (신뢰도 60, 조문 불완전) → 수동 검토 필요

---

## 📊 현재 데이터 현황 (2026-04-06 기준)

### INSPECT 4완비율
| 섹터 | 완비율 |
|---|---|
| BUILDING | 100% (123/123) |
| MANUFACTURING | 100% (75/75) |
| CONSTRUCTION | 100% (13/13) |
| COMMON | 100% (12/12) |
| BUILDING_MANUFACTURING | 100% (1/1) |
| CONSTRUCTION_MANUFACTURING | 100% (7/7) |

### 활성 룰 구성
- 전체 활성: ~1,196건
- BEFORE_WORK: 60건 (CONSTRUCTION 작업 전 점검)
- INSPECT: 234건
- APPOINT: 49건 (전부 완비)
- law_rule_drafts: APPROVED 1,566 / PENDING 1 / REJECTED 585

---

## 📋 다음 세션 목표

### 1️⃣ 시작 시 현황 확인
```sql
-- obligation_type별 현황
SELECT obligation_type, COUNT(*) FROM master_building_legal_rules
WHERE is_active=true GROUP BY obligation_type ORDER BY obligation_type;

-- REPORT condition 완비율
SELECT sector,
  COUNT(*) AS total,
  COUNT(CASE WHEN condition_code IS NOT NULL THEN 1 END) AS has_condition,
  ROUND(COUNT(CASE WHEN condition_code IS NOT NULL THEN 1 END)::numeric / COUNT(*) * 100, 1) AS ratio
FROM master_building_legal_rules
WHERE obligation_type='REPORT' AND is_active=true
GROUP BY sector ORDER BY sector;
```

### 2️⃣ 우선 과제
1. **REPORT condition 완비율 개선** — COMMON 12%, MANUFACTURING 60.7%
2. **스케줄 자동생성** — INSPECT 룰 → 점검 일정 자동 생성 로직
3. **Railway Wait for CI 설정** — 배포 안전장치
4. **BEFORE_WORK 체크리스트 연동** — 공종별 작업 전 점검 UI 연결

### 3️⃣ 수정 후 필수 검증
```
GitHub push → Actions 자동 실행 → 4개 Job 모두 ✅ 확인
https://github.com/taiengineering/tai-api/actions
```

---

## 📌 엔진 핵심 상수 (변경 금지)

### 가스 단계별 임계값 (법적 기준 — 절대 수정 금지)
```
gas_capacity_kg >= 1    → 기본 점검/선임
gas_capacity_kg >= 100  → 정기검사 (고압가스안전관리법)
gas_capacity_kg >= 300  → 추가 검사
gas_capacity_kg >= 1000 → 특별 의무
```

### inspection_cycle_unit_code 매핑
```
003 = 월 / 004 = 분기 / 005 = 반기 / 006 = 년
007 = N년 (value=년수) / 008 = 5년 / 009 = 4년
BEFORE_WORK 타입은 cycle 불필요 (작업 발생 시 트리거)
```

### obligation_type 허용값
```
APPOINT / INSPECT / ACTION / REPORT / NOTIFY / DOCUMENT / OTHER / BEFORE_WORK
```

### has_appt() 비교 주의 (테스트 코드 패턴)
```python
# 엔진이 appointment_target을 한글 레이블로 반환 — 영문+한글 둘 다 비교 필수
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

### ENGINE_CONTEXT_KEYS 동기화 원칙
새 condition_code 추가 시 반드시:
1. `routers/legal_engine.py` 매핑 추가
2. `tests/check_mapping_coverage.py` `ENGINE_CONTEXT_KEYS` 셋 추가
3. GitHub push → CI 4-Job 통과 확인

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
4. **공지예외주장 기한: 2026-04-28** (patent.go.kr) ← D-22
5. 가스 조건값 수정 금지 (100/300/1000 kg)
