# TAI Phase 5 — Runtime Review Governance & Approval Authority
## 2026-05-12 | Session Handoff

---

## 신규 DB 테이블 (4개)
| 테이블 | 목적 |
|--------|------|
| runtime_review_authority | 누가 무엇을 승인할 수 있는지 정의 (6건 초기 권한) |
| runtime_review_decision | Review decision lifecycle (APPROVE/REJECT/RETURN/ESCALATE/REOPEN) |
| runtime_review_escalation | Review escalation queue |
| runtime_review_audit | Review audit trail |

## 트리거 (1개)
- fn_validate_review_authority: authority 존재 검증 + 중복 approval 차단 + status 자동 설정

## Bridge API (routers/review_bridge.py)
- GET /bridge/review-queue, /bridge/review-queue/{id}
- POST /bridge/review-decisions
- GET /bridge/review-authority
- GET /bridge/review-escalations
- POST /bridge/approve, /bridge/reject, /bridge/reopen

## CHECK 제약: 44개 | Authority Rules: 6건 | Integrity: 9/9 PASS

## PENDING
- [ ] main.py에 review_bridge.router 등록 (v5.50.0)
