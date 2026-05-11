# Residual Intelligence & Human Review Workflow — 핸드오프

## 작업 일시

2026-05-11

## 핵심: 애매함은 제거 대상이 아니라 관리 대상이다.

---

## 구현 완료 항목

### DB 12테이블 (Supabase Migration)

| 테이블 | 건수 | 역할 |
|---|---|---|
| residuals | 111,142 | Residual 원문 저장 |
| residual_failed_reasons | 111,434 | 실패 원인 (13종 enum) |
| residual_patterns | 12 | 반복 패턴 |
| residual_clusters | 9 | 패턴 클러스터 |
| residual_cluster_items | 0 | 클러스터↔Residual |
| registry_gaps | 11 | Registry 부족 항목 |
| review_queue | 20 | Human Review 대기열 |
| human_review_decisions | 0 | 사람 검토 결과 (대기중) |
| registry_updates | 0 | 승인된 registry 변경 (대기중) |
| reprocessing_queue | 0 | 재처리 대기열 (대기중) |
| coverage_metrics | 0 | 조문별 커버리지 |
| ri_audit_logs | 1 | 감사 로그 |

### API 22개 엔드포인트

`routers/residual_intelligence.py` — prefix: `/api/v1/residual-intelligence`

핵심 플로우:
```
POST /patterns/mine → 패턴 분석
POST /clusters/build → 클러스터 생성
POST /registry-gaps/detect → Gap 탐지
GET /review-queue → 검토 목록
POST /review-queue/{id}/decision → 사람 검토
POST /registry-updates/apply → 승인 후 반영
POST /reprocessing-queue/enqueue → 재처리
GET /dashboard → 대시보드
```

### 서비스 12모듈

`services/residual_intelligence.py`

ResidualCollector, ResidualStore, ResidualClassifier, PatternMiner,
ClusterBuilder, RegistryGapDetector, ReviewQueueManager, HumanDecisionStore,
ControlledRegistryUpdater, ReprocessingQueue, CoverageAnalyzer, AuditLogger

---

## Human Review 플로우

```
1. Residual 수집 (111,142건)
2. Pattern Mining (12건)
3. Cluster Build (9건, 10회 이상 반복)
4. Registry Gap Detect (11건)
5. Review Queue 생성 (20건)
   ↓
6. 사람 검토 (human_review_decisions)
   ↓
7. 승인된 것만 Registry 반영 (registry_updates)
   ↓
8. 영향 받은 Residual만 재처리 (reprocessing_queue)
```

---

## 준수 사항

- ✅ 자동 해석 금지
- ✅ 사람 승인 전 registry 반영 금지
- ✅ UNKNOWN 유지
- ✅ source_span 필수
- ✅ audit_log 전건 기록
- ✅ rollback 가능

---

## main.py 에 라우터 등록 필요

```python
from routers.residual_intelligence import router as ri_router
app.include_router(ri_router)
```
