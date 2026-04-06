# TAI Safe 신규 창 시작 프롬프트
**작성일: 2026-04-06 2차 세션 종료 | 컨텍스트: 법령엔진 무결성 검증 완료 → 점검 스케줄 연계 단계**

---

## 🎯 현재 상황 요약

### 완료된 것
- ✅ 법령엔진 무결성 78건 ALL PASS (정방향 + 역방향 + 복합 + 격리)
- ✅ 엔진 v5.6.3 GitHub 업로드 완료
  - inspection_cycle 4필드 완비 (schedule_type: PERIODIC/BEFORE_WORK/ON_DEMAND)
  - DiagnoseStep1Body 수치 입력 필드 추가 (gas_capacity_kg, boiler_capacity_kw, elevator_count 등)
- ✅ DB 버그 수정: GASACT-001 조건코드, HAZMAT-015-MFG-V2 target_code, 한글 코드 정규화
- ✅ 점검 4필드 완비율 분석: 건물 85% / 산업 72% / 건설 12%

### 미완료 (즉시 해야 할 것)
- ❌ **Railway v5.6.3 배포 미완료** — GitHub에 코드 있으나 Railway는 v5.5.2 운영 중
  → Railway 대시보드 접속 → 수동 재배포 필요
- ❌ 점검 무결성 테스트 (v5.6.3 배포 후 실행)
  ```bash
  python tests/test_legal_engine_layer.py
  ```
  → 현재 16건 중 8건 실패 (배포 후 14/16 예상)

---

## 📋 다음 세션 작업순서

### 1️⃣ Railway 재배포 확인 (최우선)
```
https://api.taieng.co.kr/ → {"version": "5.6.3"} 확인
```

### 2️⃣ 점검 4필드 완전 검증 (배포 후)
아래 테스트 실행:
```bash
python tests/test_legal_engine.py       # 26건 기준 (항상 통과해야 함)
python tests/test_legal_engine_52.py    # 52건 추가
python tests/test_legal_engine_layer.py # 단계별 (v5.6.3 후 30건 예상)
```

검증 항목:
- 승강기: elevator_count=1 → 승강기안전관리법 점검 + 승강기안전관리자 선임 둘다 발동
- 가스: gas_capacity_kg=1 → >=1 룰 발동, gas_capacity_kg=100 → >=1+>=100 발동
- inspection_cycle, inspection_cycle_code, inspection_cycle_unit, schedule_type 필드 확인
- inspection_schedule_ready.periodic / before_work 분류 확인

### 3️⃣ 건설 BEFORE_WORK 점검 설계 결정
건설 INSPECT 73건 중 64건이 주기 없음 (작업 전 점검 구조)
- BEFORE_WORK 룰 → 작업 등록 시 자동 생성하는 스케줄러 로직 필요
- master_building_legal_rules에 cycle_type 컬럼 추가 여부 결정 필요

### 4️⃣ 점검 → 일정 자동생성 연계 검증
- POST /legal-engine/create-inspection-sets/{factory_id} 호출
- inspection_sets 생성 확인 (cycle_unit, cycle_value, schedule_type 정확히 들어가는지)

### 5️⃣ 신고/보고 검증 (ACTION 이후)
- 신고(REPORT) 144건 / 보고(NOTIFY) 58건 → 언제/누가/무엇 기준 동일하게 검증

---

## 🗄️ 현재 엔진 구조 핵심

### 점검 분류 (v5.6.2+)
```python
# format_rule_result_db()가 반환하는 점검 관련 필드
{
  "inspection_cycle":      "연 1회",     # 언제 — 레이블
  "inspection_cycle_code": "006",        # 언제 — 코드
  "inspection_cycle_unit": "year",       # 언제 — 스케줄러 단위
  "inspection_cycle_int":  1,            # 언제 — 스케줄러 정수
  "schedule_type":         "PERIODIC",   # PERIODIC/BEFORE_WORK/ON_DEMAND
  "executor_type_code":    "external",   # 누가
  "condition_code":        "elevator_count",  # 무엇이 있을 때
  "condition_value":       "1"           # 임계값
}
```

### 가스 단계별 임계값 (수정 금지)
```
gas_capacity_kg >= 1    → 기본 점검 (선임 등)
gas_capacity_kg >= 100  → 정기검사 (연1회, 고압가스안전관리법)
gas_capacity_kg >= 300  → 추가 검사
gas_capacity_kg >= 1000 → 특별 의무
```

### 진단 입력 (v5.6.3+)
```json
{
  "sector": "BUILDING",
  "input": {
    "elevator_count": 3,       ← 승강기 대수 직접
    "gas_capacity_kg": 250,    ← 가스 용량 직접 (250kg → >=1, >=100 발동)
    "boiler_capacity_kw": 500, ← 보일러 용량 직접
    "has_hazardous_material": true,
    "electric_capacity": 300
  }
}
```

---

## 📌 절대 원칙
1. **무결성 규칙**: 법령/엔진 변경 후 반드시 test_legal_engine.py + test_legal_engine_52.py 통과
2. **가스 조건값 수정 금지**: 법적 기준값 (100/300/1000 kg)
3. **배포 전 GitHub 확인**: SHA 항상 최신 조회 후 업데이트
4. **공지예외주장 기한: 2026-04-28**

---

## 🔐 인증
- **Supabase**: xntdkrjhgcscmqctdzyo
- **Railway API**: https://api.taieng.co.kr/ (GitHub: v5.6.3 / 운영: v5.5.2)
- **Admin**: hetto@kakao.com (role 001)
