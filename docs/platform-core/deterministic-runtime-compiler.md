# TAI Deterministic Runtime Compiler

## 정의

TAI는 "법령 AI"가 아니다.

TAI는:

```
법령 구조 → Runtime Metadata → Operational Candidate → Runtime
```

으로 변환하는 **Deterministic Legal Runtime Compiler**이다.

---

## 핵심 개념 정의

### Legal Candidate
법령 원문에서 추출된 구조적 데이터.
Rule Candidate, Task Candidate, Schedule Candidate, Penalty Candidate.
모든 출력은 CANDIDATE 상태. Truth가 아님.

### Runtime Metadata
법령 구조 내부에서 deterministic하게 추출된 운영 메타데이터.
- **WHO**: 행위 주체 (사업주, 관리감독자 등)
- **WHEN**: 시점 (작업 전, 즉시, 정기적으로)
- **HOW**: 행위 (점검, 교육, 기록, 보고)
- **CONDITION**: 조건 (인원수, 설비유형, 위험물)
- **SCHEDULE**: 주기 (매년, 분기, 이벤트 기반)
- **EVIDENCE**: 증빙 (기록보존, 보고서)
- **THRESHOLD**: 수치 기준 (50명 이상, 500kVA 초과)

### Operational Candidate
Runtime Metadata가 충분히 채워진 상태.
사람이 검토하고 승인하면 Runtime으로 전환 가능.

### Runtime Candidate
Operational Candidate 중 실제 Runtime으로 전환 대기 상태.
WHO + HOW + (WHEN 또는 SCHEDULE) + CONDITION이 존재.

### Activation
사람이 승인한 후 Runtime에 등록되는 행위.
자동 등록 절대 금지.

### Runtime
실제 운영 시스템에서 실행되는 작업.
점검 task, 교육 스케줄, 증빙 요구, 알림 등.

---

## Runtime 계층 구조

### Structural Runtime (법령 내부)
법령 구조만으로 deterministic하게 추출 가능한 영역.

| 영역 | 복원률 | 소스 |
|---|---|---|
| WHO | 90.3% | 조문 주어 |
| HOW | 93.6% | 조문 동사 |
| CONDITION | 85.0% | 조건절 |
| SCHEDULE | 75.4% | 수치+기간 패턴 |
| WHEN | 52.9% | 시점 표현 |
| THRESHOLD | 31,964건 | 수치+단위+조건 |

### Operational Runtime (법령 외부)
법령에 규정되지 않는 운영 영역.

| 영역 | 상태 | 해결 방법 |
|---|---|---|
| EVIDENCE 형식 | 30.3% | 증빙 사전 (15종 구축) |
| 체크리스트 UX | 0% | 산업별 설계 |
| 모바일 입력 UX | 0% | 프론트엔드 설계 |
| 승인 흐름 | 0% | 운영 정책 |
| 알림 정책 | 0% | 운영 정책 |

---

## Compiler 파이프라인

```
법령 원문 (768개 법령)
    │
    ▼
Constraint Graph (284K node)
    │
    ▼
Rule Candidate IR (34,456)
    │
    ▼
Executable Draft (10,725)
    │
    ▼
Facility Applicability (25,920)
    │
    ▼
Task Candidate (3,388)
    │
    ▼
Runtime Metadata Resolution (3,395)
    │  WHO: 90.3% / HOW: 93.6% / CONDITION: 85.0%
    │  SCHEDULE: 75.4% / WHEN: 52.9% / EVIDENCE: 30.3%
    │
    ▼
Completeness Tier:
    ├─ FULL_RUNTIME: 1,762 (51.9%)     → 즉시 운영화 가능
    ├─ OPERATIONAL_RUNTIME: 1,159 (34.1%) → 보조데이터 추가 시 가능
    ├─ REVIEW_REQUIRED: 383 (11.3%)       → 사람 검토 필요
    └─ UNRESOLVED: 91 (2.7%)              → 구조적 복원 불가
    │
    ▼
Runtime Candidate
    │  사람 승인 필수. 자동 등록 금지.
    ▼
Activation → Runtime (실제 운영)
```

---

## 금지 규칙

- ❌ LLM 추론으로 값 생성
- ❌ Candidate → Truth 승격
- ❌ 자동 Runtime 등록
- ❌ 법령 의미 해석 강화
- ❌ UNKNOWN 제거
- ❌ Residual 숨김

## 핵심 문장

TAI는 "법령을 이해하는 AI"가 아니다.
법령 구조를 운영 Runtime으로 deterministic하게 컴파일하는 시스템이다.
