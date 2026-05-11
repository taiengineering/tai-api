# Penalty Candidate Engine — 핸드오프

## 작업 일시

2026-05-11

## 핵심: Penalty는 법적 결론이 아니라 연관 후보이다.

---

## 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| penalty_candidate | 3,129 | 벌칙/과태료/행정처분 후보 |
| penalty_numeric | 1,696 | 금액/기간 수치 |
| penalty_reference_link | 2,749 | 의무조문 참조 링크 |
| penalty_obligation_relation | 7,511 | 의무-처벌 연결 |
| penalty_issue | 0 | 이슈 |

---

## Penalty Family

| family | 건수 |
|---|---|
| SURCHARGE_FAMILY | 797 |
| ADMINISTRATIVE_FINE_FAMILY | 596 |
| CRIMINAL_FINE_FAMILY | 551 |
| CORRECTIVE_ORDER_FAMILY | 434 |
| IMPRISONMENT_FAMILY | 385 |
| BUSINESS_SUSPENSION_FAMILY | 264 |
| USE_SUSPENSION_FAMILY | 48 |
| LICENSE_REVOCATION_FAMILY | 41 |
| UNKNOWN_PENALTY_FAMILY | 9 |
| CONFISCATION_FAMILY | 4 |

## DB 검증

| 검증 | 결과 |
|---|---|
| 건수 일치 | ✅ |
| 명시 참조 기반 Relation만 | ✅ (no_ref_rel=0) |
| 위반 확정 | ✅ 없음 |
| 금액 확정 부과 | ✅ 없음 |

---

## 14개 프롬프트 전체 총괄

| # | 프롬프트 | 결과 |
|---|---|---|
| 1 | Constraint Graph | 284,579 / 54,122 |
| 2 | Subtype | 14종, 100% |
| 3 | Numeric | 10,329 |
| 4 | Numeric Family | 10,329 / 6,934 |
| 5 | Rule Candidate | 34,456 / 146K / 59K |
| 6 | Compatibility | 12,748 / 757 |
| 7 | Executable Draft | 10,725 / 50K / 10K |
| 8 | Facility Applicability | 25,920 / 3,045 |
| 9 | Task Candidate | 3,388 / 15,456 |
| 10 | Schedule Candidate | 1,159 |
| 11 | Compliance Package | 30 / 1,737 / 20 |
| 12 | Law Versioning | 35,412 Hash |
| 13 | Residual Coverage | 111,142 / 10,020 / 704 |
| 14 | Penalty Candidate | 3,129 / 1,696 / 7,511 |

**테이블 42개, 스크립트 14개, 핸드오프 14건.**
