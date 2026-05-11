# Admin Legal Review System — 핸드오프

## 작업 일시

2026-05-11

## 핵심: 사람이 검토한 법령만 엔진에 추가된다.

---

## DB 4테이블

| 테이블 | 역할 |
|---|---|
| admin_review_queue | Admin 검토 대기열 (7종 review_type) |
| admin_reprocessing_queue | 재처리 대기열 |
| registry_versions | Registry 변경 버전 (rollback 지원) |
| admin_audit_logs | Admin 감사 로그 (8종 action) |

## API 12개 엔드포인트

`routers/admin_review.py` — prefix: `/api/v1/admin`

| API | 용도 |
|---|---|
| GET /admin/review-queue | 검토 목록 |
| GET /admin/review-queue/{id} | 검토 상세 |
| POST /admin/review/{id}/approve | **승인 (10종 액션)** |
| POST /admin/review/{id}/reject | 거절 |
| POST /admin/family/create | **Family 생성** |
| POST /admin/registry/add-token | **Token 추가** |
| POST /admin/reference/link | Reference 연결 |
| POST /admin/attachment/link | Attachment 연결 |
| POST /admin/rule/approve | **Rule Candidate 승인** |
| POST /admin/reprocessing/trigger | 재처리 |
| POST /admin/rollback | **Rollback** |
| GET /admin/audit-logs | Audit 조회 |

## 승인 플로우

```
Residual/Cluster/Gap → Admin Review Queue
→ 사람 검토 (10종 액션)
→ 승인 → Registry Update + Versioning
→ Reprocessing Queue
→ Candidate 재생성
```

## 준수 사항

- ✅ 자동 학습 금지
- ✅ 자동 Registry 확장 금지
- ✅ source_examples 필수
- ✅ Audit 전건 기록
- ✅ Rollback 가능
- ✅ Versioning 적용

## main.py 등록

```python
from routers.admin_review import router as admin_router
app.include_router(admin_router)
```
