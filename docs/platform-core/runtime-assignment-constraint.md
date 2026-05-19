# Runtime Assignment Constraint

## 개념

엔진은 사람을 검증하지 않는다.
엔진은 사람이 검증할 수 있도록 **요구조건을 구조화된 값으로 출력**한다.

## 검증과 요구조건 출력의 차이

| | 요구조건 출력 (Compiler) | 검증 (Validation Layer) |
|---|---|---|
| 책임 | 법령엔진 | 회원/조직 시스템 |
| 입력 | 법령 조문 | 사용자 자격 데이터 |
| 출력 | 필요 자격/기관/인원 | 충족 여부 |
| 예시 | "산업안전기사 이상 1명" | "User A는 산업안전기사 보유 → 충족" |

## 요구조건 유형

### 1. 개인 자격 (individual_qualification)
- 산업안전기사, 산업안전산업기사, 산업안전지도사
- 건설안전기사, 위험물산업기사, 전기기사

### 2. 기관 자격 (organization_qualification / designated_agency / professional_agency)
- 안전관리전문기관, 보건관리전문기관
- 지정검사기관, 지정교육기관, 지정측정기관

### 3. 인원수 (staffing_count)
- 1명 이상, 2명 이상 등

### 4. 선임조건 (appointment_required)
- 안전관리자 선임, 보건관리자 선임

### 5. 근무조건 (presence_required / dedication_required)
- 전담, 상주, 겨직 가능/금지

## 자동 배정 금지 원칙

### Compiler/Resolver 책임
- ✅ 요구 자격 출력
- ✅ 요구 기관 출력
- ✅ 최소 인원 출력
- ✅ 선임 필요 여부 출력

### Validation Layer 책임
- ✅ 실제 사용자 자격 보유 확인
- ✅ 조직이 지정기관인지 확인
- ✅ 인원수 충족 여부 계산

### Human Governance 책임
- ✅ 최종 이행자 지정
- ✅ 기관 선택
- ✅ 선임 승인

### 금지
- ❌ 자동 담당자 지정
- ❌ 자동 선임 처리
- ❌ 자동 법적 충족 확정
- ❌ 사람 승인 없는 assignment

## Runtime Task 연결 방식

```
runtime_task
  │
  └─ runtime_assignment_requirement (1:N)
       ├─ individual_qualification: "산업안전기사 이상"
       ├─ staffing_count: minimum_count=1
       ├─ appointment_required: true
       └─ dedicated_required: true
```

## 향후 Validation Layer 연결

```
runtime_assignment_requirement
  │  (요구조건)
  ▼
Validation Layer
  │  (사용자 자격 데이터 조회)
  ▼
Assignment Validation Result
  │  (충족/부족/불명)
  ▼
Human Decision
  │  (사람이 최종 지정)
  ▼
Runtime Assignment
```
