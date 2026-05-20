# Runtime Document Engine Simulation

## 개념

문서는 Runtime의 결과물이 아니라, **Runtime 상태를 증명하는 Projection**이다.

```
Runtime Execution (실행)
  → Evidence Collection (증빗 수집)
    → Document Completeness (문서 완성도)
      → Reviewer Approval (검토 승인)
        → Auditable Record (감사 가능 기록)
```

---

## Document Completeness Tier

| 등급 | 조건 |
|---|---|
| COMPLETE | completed + evidence validated + assignee |
| PARTIAL | in_progress + evidence uploaded |
| REJECTED | evidence rejected |
| INCOMPLETE | evidence missing or 미실행 |

## 현재 결과 (Virtual 80건)

| 등급 | 건수 | 비율 |
|---|---|---|
| COMPLETE | 25 | 31.3% |
| PARTIAL | 5 | 6.3% |
| REJECTED | 5 | 6.3% |
| INCOMPLETE | 45 | 56.3% |

## Audit Trace

| Trace | 연결 |
|---|---|
| task→instance | 80 (100%) |
| instance→evidence | 80 (100%) |
| instance→audit | 188건 |
| evidence→audit(reviewed) | 14건 |
| task→document_forms | 68건 bindable |

## 핵심 병목

1. doc_rule_mapping 227건 전부 PENDING
2. obligation_form_mapping 11건만 연결
3. evidence missing 37건 → 문서 56.3% 미완성

## Evidence → Document Field Mapping

| Evidence | Document Field |
|---|---|
| 점검표 | 점검결과/적합여부 |
| 교육일지 | 교육일시/참석/강사 |
| 측정기록 | 측정항목/측정값/판정 |
| 선임신고서 | 자격명/자격번호/선임일 |
| 사진 | 현장사진 섹션 |

## Conditional Rendering

- 위험물 보유 → 위험물 점검 섹션
- 건설업 → 공사일지 섹션
- qualification mismatch → 경고 표시
- evidence missing → INCOMPLETE 표시
