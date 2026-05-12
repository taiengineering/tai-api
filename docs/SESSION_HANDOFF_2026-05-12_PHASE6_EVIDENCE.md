# TAI Phase 6 — Runtime Compliance Evidence & Legal Traceability
## 2026-05-12 | Session Handoff

---

## 신규 DB 테이블 (6개)
| 테이블 | 목적 |
|--------|------|
| runtime_compliance_evidence | 법적 증빙 registry (8종 evidence_type) |
| runtime_evidence_trace | 증빙 법적 추적 (obligation/work_order/review/document 연결) |
| runtime_evidence_snapshot | Immutable 증빙 snapshot (version + hash) |
| runtime_evidence_retention_policy | 법적 보존 정책 (8건 초기 설정) |
| runtime_evidence_verification | 증빙 검증 (VERIFIED/REJECTED/NEEDS_REUPLOAD) |
| runtime_evidence_audit | 증빙 audit trail |

## Bridge API (routers/evidence_bridge.py)
- GET /bridge/compliance-evidence
- POST /bridge/upload-evidence (immutable hash + duplicate check)
- GET /bridge/evidence-trace
- POST /bridge/verify-evidence
- GET /bridge/evidence-verification
- GET /bridge/evidence-retention
- GET /bridge/evidence-snapshots

## CHECK 제약: 57개 | Retention Policies: 8건 | Integrity: 9/9 PASS

## PENDING
- [ ] main.py에 evidence_bridge.router 등록 (v5.51.0)
