# Full-scale Runtime Metadata Expansion 결과

## 2026-05-19

## DB 5테이블 전수 확장

| 테이블 | 건수 |
|---|---|
| appendix_runtime_metadata | 31,964 |
| legal_delegation_graph | 7,745 |
| runtime_schedule_pattern | 220 |
| runtime_metadata_resolution | 3,395 |
| evidence_runtime_dictionary | 15 |

## Resolution Coverage

| Metadata | Resolved | Ratio |
|---|---|---|
| WHO | 506 (R) + 2,889 (P) | 14.9% (R) / 100% (R+P) |
| HOW | 3,179 | 93.6% |
| CONDITION | 2,886 | 85.0% |
| SCHEDULE | 2,561 | 75.4% |
| WHEN | 1,797 | 52.9% |
| EVIDENCE | 1,028 | 30.3% |

## Operationalization

- 전체: 3,395건
- 즉시 운영화 가능 (≥80%): 316건 (9.3%)
- 보조 데이터 추가 시 (≥60%): ~2,100건 (62%)
- 평균 completeness: 61.0%

## 핵심 발견

- law_attachment 1,322건은 환경시험방법 PDF이며, 실제 별표(별표3,4,5)는 별도 구조화 저장 안 됨
- WHO regex 확장으로 14.9%→70%+ 가능
- delegation PARTIAL→RESOLVED 자동매칭으로 WHEN 52.9%→75%+ 가능
- EVIDENCE는 법령 외부 사전 필요 (15종 구축 완료)
