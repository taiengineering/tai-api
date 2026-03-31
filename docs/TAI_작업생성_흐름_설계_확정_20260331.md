# TAI 작업 생성 흐름 설계 확정
## 작성일: 2026-03-31
## 결정: 산업/건물과 건설은 작업 생성 흐름이 다르므로 완전 별도 처리

---

## 핵심 차이

| 구분 | 산업/건물 (BUILDING·MANUFACTURING·SPECIAL) | 건설 (CONSTRUCTION) |
|------|----------------------------------------|--------------------|
| 기준 | **시간 주기** (N개월마다, N년마다) | **작업 흐름** (공정 시작 전/중/후) |
| 트리거 | 달력 날짜 도래 | 작업(PTW) 등록 이벤트 |
| 반복 | 주기적 자동 반복 | 작업마다 1회 생성 |
| 단위 | 법령 유형 묶음 × 주기 | 공정 × 작업 × 타이밍 |
| 배정 | 안전관리자/안전담당자 | 관리감독자/해당 작업자 |

---

## 흐름 A — 산업/건물 (시간 주기형)

```
[1] 법령진단 (diagnose/step1)
      ↓ 적용 법령 추출 (INSPECT 의무)

[2] 점검세트 자동 생성 (create-inspection-sets)
      ↓ 법령별 → 유형 묶음으로 그룹화
        소방 계열 → 소방 반기점검 1건
        전기 계열 → 전기 연간점검 1건
        산안법 계열 → 산안법 반기점검 1건
        ...
      ↓ cycle_unit + cycle_value + cycle_base_type 저장

[3] 기준일 입력 (inspection-anchor.html — tadmin)
      ↓ 사용자가 마지막 점검일 / 사용승인일 / 설치일 입력
      ↓ next_planned_date 자동 계산
      ↓ anchor_confirmed = true

[4] 반복 일정 생성 (inspection/generate-schedules)
      ↓ anchor_confirmed=true 인 세트만 처리
      ↓ next_planned_date 도래 → work_schedules INSERT
      ↓ 완료 처리 시 → 다음 회차 자동 생성 (next = 완료일 + cycle)

[5] 작업 배정 (work_assignments)
      ↓ factory의 안전관리자(role=012) 자동 배정
      ↓ 담당자 없으면 PENDING 상태로 대기
```

### 작업 생성 단위
**[법령 유형] [주기] 점검** 1건 = work_schedules 1건

```
소방 반기점검     ← 소방시설법 제22조 + 소방시설공사업법 + 화재예방법 묶음
전기 연간점검     ← 전기안전관리법 + 전기사업법 묶음  
산안법 반기점검   ← 산안법 제36조 + 산업안전보건기준규칙 묶음
환경 연간점검     ← 대기환경보전법 + 물환경보전법 + 소음진동법 묶음
건축물 3년점검    ← 건축물관리법 제12조
```

### inspection_category 묶음 기준 (추가 필요)
```
소방   = 소방시설%, 화재예방%, 소방기본%
전기   = 전기안전관리%, 전기사업%
가스   = 고압가스%, 도시가스%, 액화석유가스%
산안법  = 산업안전보건%, 중대재해%, 산업안전보건기준%
환경   = 대기환경%, 물환경%, 소음진동%, 악취%, 토양환경%, 폐기물%
건축물  = 건축법%, 건축물관리법%
기계설비 = 기계설비%, 승강기%
위험물  = 위험물안전관리%
```

### 필요 DB 작업
- [ ] master_building_legal_rules에 `inspection_category` 컬럼 추가
- [ ] 법령명 기반으로 카테고리 자동 분류
- [ ] inspection_sets에 `inspection_category` 저장
- [ ] create-inspection-sets에서 카테고리별 묶음 생성 로직

### 필요 API 작업 (Cursor)
- 버그1·2 수정 완료 후: 묶음 로직 추가
- inspection/complete 완료 시 → 다음 회차 자동 INSERT

---

## 흐름 B — 건설 (작업 흐름형)

```
[1] 현장 등록 (construction_sites)
      ↓ 도급금액·인원 입력 → 안전관리자 선임 의무 자동 판정

[2] 공정 등록 (construction_site_processes)
      ↓ KCSC 표준공정 선택 (건축 75 / 토목 50 / 공통 36)
      ↓ 공정별 위험작업 목록 자동 표시

[3] 위험작업 등록 (construction_works + PTW)
      ↓ 작업 등록 시 → 작업 전 안전점검 자동 생성
      ↓ PTW 승인 전 → 점검 REQUIRED 상태
      ↓ 작업 진행 중 → 일상점검 생성 (작업일마다)
      ↓ 작업 완료 후 → 완료 확인 점검 생성

[4] 점검 실시 (construction_inspections)
      ↓ KCSC safety_standard 기반 체크리스트 자동 로드
      ↓ PASS/FAIL/CONDITIONAL 결과 기록
      ↓ FAIL → 시정조치 연결

[5] PTW 완료
      ↓ 모든 점검 PASS 확인 후 작업 CLOSE
```

### 작업 생성 트리거

| 타이밍 | 트리거 | 생성되는 작업 |
|--------|--------|-------------|
| 작업 전 | PTW 등록 시 자동 | 작업 전 안전점검 (construction_inspections) |
| 작업 중 | 작업 진행 중 매일 | 일상 안전점검 (daily inspection) |
| 작업 후 | 작업 완료 처리 시 | 완료 확인 점검 |
| 공정 시작 | 공정 등록 시 | 공정 착수 전 안전계획 확인 |
| 이벤트 | 중대재해 발생 시 | 즉시 조사 작업 |

### 핵심: 건설은 work_schedules가 아닌 construction_inspections가 작업 단위

```
산업/건물: work_schedules → work_assignments (시간 기반 반복)
건설:      construction_works → construction_inspections (이벤트 기반 1회)
```

### 필요 작업
- [ ] construction_works 등록 시 → construction_inspections 자동 생성 트리거
  - BEFORE_WORK: PTW 등록 시
  - DAILY: 작업일마다 (작업 기간 내)
  - AFTER_WORK: 완료 처리 시
- [ ] PTW 상태 변경 시 점검 상태 연동
  - PTW APPROVED → BEFORE_WORK 점검 통과 확인 후 승인
  - PTW CLOSED → AFTER_WORK 점검 자동 생성

---

## 현재 구현 현황

### 산업/건물 흐름
| 단계 | 구현 상태 |
|------|----------|
| 법령진단 DB 저장 | ✅ 완료 |
| 점검세트 생성 (버그 수정 전) | 🔴 버그1·2 수정 필요 |
| 기준일 입력 tadmin 페이지 | 🔴 미구현 |
| PATCH anchor API | 🔴 미구현 |
| 반복일정 생성 (anchor 방어) | 🔴 버그5 수정 필요 |
| 완료 후 다음 회차 자동생성 | 🔴 미구현 |
| 법령 유형 묶음 그룹화 | 🔴 미구현 |

### 건설 흐름
| 단계 | 구현 상태 |
|------|----------|
| 현장/공정/작업 테이블 | ✅ DB 완료 |
| 현장관리 5개 HTML 페이지 | 🔴 미구현 |
| construction.py 라우터 | ✅ 구현 완료 |
| 작업 등록 시 점검 자동생성 | 🔴 미구현 |
| PTW → 점검 상태 연동 | 🔴 미구현 |

---

## 권장 우선순위

### Phase 1 (산업/건물 먼저 완성)
1. 버그1·2 수정 → create-inspection-sets 정상화
2. inspection_category 묶음 로직 추가
3. PATCH anchor API + tadmin 기준일 페이지
4. 완료 후 다음 회차 자동생성 로직

### Phase 2 (건설)
1. 건설안전 5개 HTML 페이지 생성
2. construction_works 등록 시 construction_inspections 자동생성
3. PTW 상태 ↔ 점검 상태 연동
