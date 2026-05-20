# Document Engine Simulation 핸드오프

## 2026-05-20

## 결과

### Document Completeness
| 등급 | 건수 | 비율 |
|---|---|---|
| COMPLETE | 25 | 31.3% |
| INCOMPLETE | 45 | 56.3% |
| REJECTED | 5 | 6.3% |
| PARTIAL | 5 | 6.3% |

### 핵심 병목
- doc_rule_mapping 227건 PENDING
- obligation_form_mapping 11/260 (4.2%)
- attachments 0건

### Document Risk Score: **49.6/100**

### 결론
문서는 Runtime 상태를 증명하는 Projection.
실행이 먼저, 문서가 따라간다.

### P0
1. doc_rule_mapping PENDING → APPROVED 검토
2. obligation_form_mapping 확장
