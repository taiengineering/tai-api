# Runtime Compiler Projection — 제품화 구현 가이드

## 2026-05-21
## 상태: P2 제품화 연결 완료

---

## 1. Projection 데이터 구조 (토큰 기반)

### full_result 필드 구조

| 필드 | 역할 | Runtime Boundary |
|---|---|---|
| `summary` | 의무 집계 (total/appointment/inspection/action/report) | ✅ Projection |
| `law_badges` | 적용 법령 목록 | ✅ Projection |
| `law_groups` | 법령별 그룹 + rules | ✅ Projection |
| `rules_table` | 의무 목록 (WHO/HOW/WHEN/SCHEDULE) | ✅ Projection |
| `key_obligations` | 주요 의무 (위험도 HIGH) | ✅ Projection |
| `assignment_projection` | **누가 해야 하는가** | ✅ Projection |
| `evidence_projection` | **무엇을 남겨야 하는가** | ✅ Projection |
| `schedule_projection` | **언제 해야 하는가** | ✅ Projection |
| `risk_projection` | **법적 리스크 가능성** | ✅ Projection |
| ~~overdue~~ | ~~기한 초과~~ | ❌ Runtime Only |
| ~~completed~~ | ~~완료 상태~~ | ❌ Runtime Only |
| ~~uploaded~~ | ~~업로드 상태~~ | ❌ Runtime Only |

---

## 2. Assignment Projection 구조

### key_assignments 예시

```json
{
  "title": "안전관리자",
  "qualification": "산업안전기사 이상",
  "min_count": 1,
  "agency_allowed": true,
  "agency_type": "안전관리전문기관",
  "dedicated": false,
  "law": "산업안전보건법 제17조"
}
```

### UI 표시 규칙

| 필드 | 표시 | 예시 |
|---|---|---|
| qualification | 요구 자격 | "산업안전기사 이상" |
| min_count | 최소 인원 | "1명 이상" |
| agency_allowed | 전문기관 위탁 | "안전관리전문기관 위탁 가능" |
| dedicated | 전담 필요 | "전담 필요" / "겨직 가능" |
| law | 법적 근거 | "산업안전보건법 제17조" |

---

## 3. Evidence Projection 구조

### requirements 예시

```json
{
  "type": "점검표",
  "format": "체크리스트",
  "required": true,
  "cycle": "매일/매주",
  "law": "산업안전보건기준에 관한 규칙"
}
```

### UI 표시: "무엇을 남겨야 하는가"

---

## 4. Schedule Projection 구조

### by_frequency 예시

| 빈도 | 횟수 | 레이블 | 예시 |
|---|---|---|---|
| daily | 2 | 매일 | 작업 전 안전점검 |
| quarterly | 3 | 분기 | 정기안전보건교육 |
| biannual | 2 | 6개월 | 작업환경측정 |
| annual | 4 | 연1회 | 위험성평가 |
| on_event | 3 | 발생시 | 사고보고 |

### UI 표시: "연간 반복 규칙" (실제 일정 아님)

---

## 5. Risk Projection 구조

### penalties 예시

| 유형 | 최대 금액 | 대상 | 법적 근거 |
|---|---|---|---|
| 과태료 | 5,000만원 | 안전관리자 미선임 | 산안법 제175조 |
| 형사처벌 | 5년/5억 | 중대재해 발생 | 중대재해법 제6조 |

### UI 표시: "법적 리스크 가능성" (현재 위반 아님)

---

## 6. Activation CTA

```
[이 의무들을 실제 운영 흐름으로 관리하시겠습니까?]
[반복 운영 체계를 시작하시겠습니까?]
```

Activation 전: runtime_task 생성 금지
Activation 후: runtime_task + schedule + instance + evidence 생성

---

## 7. PDF Projection v2 구조

| 섹션 | 내용 | Source |
|---|---|---|
| 표지 | 사업장명 + 진단일 + 브랜드 | input_data |
| 요약 | 적용법령수 + 의무수 + 리스크 | summary |
| 적용법령 | 법령별 건수 + 조문 | law_groups |
| 의무목록 | WHO/HOW/WHEN/SCHEDULE | rules_table |
| 담당조건 | 자격/기관/인원 | assignment_projection |
| 증빗요구 | 점검표/교육일지/측정기록 | evidence_projection |
| 반복규칙 | 연간 운영 주기 | schedule_projection |
| 리스크 | 과태료/형사처벌 | risk_projection |
| CTA | "운영 시작" | |

---

## 8. Excel 5시트 구조

| 시트 | Source | 열 |
|---|---|---|
| Obligations | rules_table | 의무명/WHO/HOW/WHEN/법령/조문 |
| Schedule Rules | schedule_projection | 빈도/횟수/예시 |
| Assignment Req | assignment_projection | 직책/자격/인원/기관/전담 |
| Evidence Req | evidence_projection | 유형/포맷/필수/주기/법령 |
| Risk Matrix | risk_projection | 유형/금액/대상/법령 |

---

## 9. 테스트 토큰

| Token | CASE | 데이터 크기 |
|---|---|---|
| runtime-case1-construction | 건설현장 78억 | 24KB |
| runtime-case2-injection | 사출공장 250명 | 49KB |

---

## 10. 제품화 철학

| 원칙 | 의미 |
|---|---|
| 진단 = Projection | "해야 하는 것"을 보여준다 |
| Runtime = Operation | "실제로 하고 있는가"를 관리한다 |
| Activation = 전환점 | 진단 → Runtime 전환 순간 |
| Human Governance | TAI는 책임을 대신 지지 않는다 |
| Optional Adoption | 엑셀 운영도 가능 |
