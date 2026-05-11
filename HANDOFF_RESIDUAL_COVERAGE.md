# Residual Coverage Engine — 핸드오프

## 작업 일시

2026-05-11

## 핵심: 파싱 실패는 엔진 실패가 아니다.

---

## 테이블

| 테이블 | 건수 | 역할 |
|---|---|---|
| residual_candidate | 111,142 | 미처리 Part (3종) |
| residual_abstract_pattern | 10,020 | 추상 표현 탐지 |
| residual_coverage | 704 | 법령별 커버리지 |
| residual_registry_candidate | 11 | Registry 확장 후보 |
| residual_issue | 0 | 이슈 |

---

## Residual Type

| type | 건수 | 설명 |
|---|---|---|
| REGISTRY_GAP | 60,848 | 토큰 전부 UNKNOWN |
| STRUCTURAL_PARSE_FAILURE | 43,204 | 토큰 없음 |
| UNMATCHED_CONDITION | 7,090 | UNKNOWN Constraint |

## Abstract Pattern (상위 5)

| pattern | 건수 |
|---|---|
| 대통령령으로 정하는 | 5,866 |
| 필요한 경우 | 1,199 |
| 필요한 조치 | 943 |
| 기준에 적합 | 814 |
| 적절한 | 443 |

## Coverage

- Part Coverage: avg=0.6446, min=0.0000, max=1.0000
- Text Coverage: avg=0.7665

## DB 검증

| 검증 | 결과 |
|---|---|
| source_text 누락 | ✅ 0건 |
| 건수 일치 | ✅ |
| 의미 보정 | ✅ 없음 |
| registry 자동 확장 | ✅ 없음 (NEEDS_HUMAN_REVIEW) |

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

**테이블 37개, 총 ~979K 레코드.**
