# TAI Phase 7 — Runtime Regulatory Filing & Submission Governance
## 2026-05-12 | Session Handoff

---

## 신규 DB 테이블 (5개)
| 테이블 | 목적 |
|--------|------|
| runtime_filing_registry | 법정 제출 registry (11건 초기데이터) |
| runtime_submission | 제출 lifecycle (READY→SUBMITTED→ACCEPTED/REJECTED/FAILED) |
| runtime_submission_failure | 제출 실패 관리 (6종 failure_type) |
| runtime_resubmission_request | 재제출 요청 |
| runtime_submission_audit | 제출 audit trail |

## 트리거 (1개)
- fn_validate_submission_eligibility: submitted_by + immutable_hash 필수 검증

## Bridge API (routers/submission_bridge.py)
- GET /bridge/submissions, /bridge/submissions/{id}
- GET /bridge/filing-registry
- POST /bridge/submit-document
- GET /bridge/submission-failures
- GET /bridge/resubmissions
- POST /bridge/retry-submission

## CHECK 제약: 49개 | Filing Registry: 11건 | Integrity: 9/9 PASS

## PENDING
- [ ] main.py에 submission_bridge.router 등록 (v5.52.0)
