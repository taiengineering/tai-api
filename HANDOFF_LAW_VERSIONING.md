# Law Versioning & Legal Diff Engine — 핸드오프

## 작업 일시

2026-05-11

## 작업 요약

프롬프트 "Law Versioning & Legal Diff Engine" 22단계 실행 완료.
Source Hash 35,412건 생성. Diff 인프라 구축.

---

## 핵심: 법령 변경은 구조 변화 추적이다.

---

## 실행

```bash
railway run python3 scripts/run_law_versioning.py
```

---

## 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| law_version_hash | 35,412 | 조문별 MD5 hash |
| law_structural_diff | 0 | 구조 변경 (1버전만 존재) |
| law_diff_impact_candidate | 0 | 영향 후보 |
| law_diff_review_queue | 0 | Review 대기 |
| law_diff_audit_log | 5 | Audit Trail |

---

## 현재 상태

- 법령 768개, 각 1버전만 존재
- Diff 대상 0건 (정상)
- Source Hash 35,412건 생성 완료
- 향후 법령 업데이트 시 자동 diff 작동

---

## Diff 파이프라인

```
법령 업데이트 → law_version 신규 삽입
→ run_law_versioning.py 실행
→ Source Hash 생성 (new version)
→ old hash vs new hash 비교
→ law_structural_diff 생성
→ Impact Candidate 탐색 (RC/Task/Schedule 연결)
→ Review Queue로 전송
→ Human Review
```

---

## DB 검증

| 검증 | 결과 |
|---|---|
| Hash orphan | ✅ 0건 |
| 건수 | ✅ 35,412 |
| 의미 해석 | ✅ 없음 |

---

## 12개 프롬프트 전체 총괄

| # | 프롬프트 | 결과 | DB검증 |
|---|---|---|---|
| 1 | Constraint Graph Enrichment | 284,579 Node / 54,122 Edge | ✅ |
| 2 | Constraint Subtype | 14종 node, 100% 분류 | ✅ |
| 3 | Numeric Constraint | 10,329 / span 100% | ✅ |
| 4 | Numeric Family | 10,329 / 6,934 Rel | ✅ |
| 5 | Rule Candidate IR | 34,456 RC / 146K Slot / 59K Rel | ✅ |
| 6 | Compatibility Validation | PASS 12,748 / 757 Issue | ✅ |
| 7 | Executable Draft | 10,725 / 50K Slot / 10K Graph | ✅ |
| 8 | Facility Applicability | 25,920 / MATCH 3,045 | ✅ |
| 9 | Task Candidate | 3,388 / 15,456 Rel | ✅ |
| 10 | Schedule Candidate | 1,159 / 572 Task | ✅ |
| 11 | Compliance Package | 30 Pkg / 1,737 Review / 20 Audit | ✅ |
| 12 | Law Versioning | 35,412 Hash / Diff 인프라 완료 | ✅ |

**테이블 32개, 총 857,445 레코드.**
**전체 orphan 0건, broken ref 0건.**

---

## 전체 스크립트 목록

| 파일 | 용도 |
|---|---|
| scripts/run_constraint_enrich.py | Constraint Graph Enrichment |
| scripts/run_constraint_subtype.py | Subtype Classification |
| scripts/run_numeric_full.py | Numeric Constraint Extraction |
| scripts/run_numeric_family.py | Numeric Family Builder |
| scripts/run_rule_candidate.py | Rule Candidate IR |
| scripts/run_compatibility_check.py | Compatibility Validation |
| scripts/run_executable_draft.py | Executable Draft |
| scripts/run_facility_applicability.py | Facility Applicability |
| scripts/run_task_candidate.py | Task Candidate |
| scripts/run_schedule_candidate.py | Schedule Candidate |
| scripts/run_compliance_package.py | Compliance Package |
| scripts/run_law_versioning.py | Law Versioning & Diff |

실행: `cd tai-api && railway run python3 scripts/[filename]`
