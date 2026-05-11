# Legacy Runtime Migration & Compiler Core Replacement — 아키텍처 문서

## 작업 일시

2026-05-11

## 핵심: 교체 대상은 Runtime이 아니다. 법령 의미판단 Core다.

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│              Legacy Runtime Layer (유지)                │
│                                                         │
│  auth │ factories │ inspection_* │ education           │
│  tbm  │ equipment │ notifications │ payment             │
│  worker_* │ safety_* │ workflow │ dashboard            │
│                                                         │
│  55+ 라우터 미변경                                       │
├─────────────────────────────────────────────────────────┤
│         Compiler Core API (신규 인터페이스)               │
│                                                         │
│  POST /compiler/evaluate-facility                       │
│  GET  /compiler/task-candidates/{factory_id}             │
│  GET  /compiler/schedule-candidates/{factory_id}         │
│  GET  /compiler/penalty-map/{factory_id}                 │
│  GET  /compiler/source-trace/{part_id}                   │
│  GET  /compiler/coverage-summary                         │
│  GET  /compiler/health                                   │
│                                                         │
│  모든 출력: CANDIDATE. Truth 아님.                       │
├─────────────────────────────────────────────────────────┤
│      Deterministic Legal Compiler (신규 엔진)             │
│                                                         │
│  Evidence Token → Canonicalization → Family              │
│  → Constraint Graph → Numeric Constraint                │
│  → Rule Candidate IR → Compatibility                    │
│  → Executable Draft → Facility Applicability             │
│  → Task Candidate → Schedule Candidate                   │
│  → Penalty Candidate → Compliance Package                │
│  → Residual Coverage → Law Versioning                    │
│                                                         │
│  14개 파이프라인 스크립트. 54개 테이블.                    │
├─────────────────────────────────────────────────────────┤
│            Human Review Layer (신규)                      │
│                                                         │
│  Residual Intelligence API (22 엔드포인트)               │
│  Review Queue → Human Decision → Registry Update         │
│  → Reprocessing Queue                                   │
│                                                         │
│  사람 승인 전 registry 반영 금지                          │
└─────────────────────────────────────────────────────────┘
```

---

## A. Runtime Layer (유지) — 55+ 라우터

| 분류 | 라우터 |
|---|---|
| 사용자/권한 | auth, users, roles, teams, identity, pw_reset |
| 시설 관리 | factories, companies, buildings, areas, construction_* |
| 근로자 | worker_registry, worker_check, worker_home, personnel |
| 점검 UI | inspection_checklist, inspection_schedule, inspection_sets, inspection_setup, inspection_templates |
| 안전 | safety_meetings, safety_info, safety_template, risk_assessments, corrective_actions |
| TBM/교육 | tbm, tbm_templates, education, education_assign |
| 설비 | equipment_assets, equipment_checkins |
| 알림 | notifications, fcm, alert_messages, messaging, mail |
| 결제/계약 | payment*, settlements, contracts*, quotes |
| 매칭 | matching*, connect_*, fix_* |
| 기타 | health, weather, juso, feature_flags, posts, public*, admin* |

---

## B. Legal Intelligence Layer (교체 대상) — 25+ 라우터

| 라우터 | 크기 | 교체 상태 |
|---|---|---|
| law_rule_generator.py | 44KB | ❌ LLM rule 생성 → Compiler Core로 대체 |
| _rule_gen_prompts.py | 7KB | ❌ LLM 프롬프트 → 제거 |
| engine_legal.py | 14KB | ❌ 법령 엔진 → Compiler Core |
| legal_engine.py | 5KB | ❌ → Compiler Core |
| legal_engine_patch.py | 11KB | ❌ → Compiler Core |
| legal_engine_v510.py | 2KB | ❌ → Compiler Core |
| engine_model.py | 11KB | ❌ AI 모델 → 제거 |
| engine_qa.py | 18KB | ❌ AI QA → 제거 |
| diagnosis_autofill.py | 13KB | ❌ AI 자동채움 → Compiler Core |
| diagnosis_integrated.py | 10KB | ❌ 통합진단 → Compiler Core |
| diagnosis_plan_recommend.py | 13KB | ❌ AI 추천 → Compiler Core |
| schedule_engine.py | 6KB | ⚠️ 스케줄 엔진 → Candidate 기반으로 변경 |
| schedule_pipeline.py | 8KB | ⚠️ 파이프라인 → Candidate 기반 |
| overdue_checker.py | 19KB | ⚠️ 기한초과 → Candidate 기반 |
| ai_copywrite.py | 15KB | ❌ AI 카피 → 제거 |
| agent_service.py | 3KB | ❌ AI 에이전트 → 제거 |

---

## Compiler Core API

`routers/compiler_core.py` — 7개 엔드포인트

| API | 용도 |
|---|---|
| POST /compiler/evaluate-facility | **Runtime이 호출하는 핵심 API** |
| GET /compiler/task-candidates/{fid} | Task Candidate 조회 |
| GET /compiler/schedule-candidates/{fid} | Schedule Candidate 조회 |
| GET /compiler/penalty-map/{fid} | Penalty 연관 조회 |
| GET /compiler/source-trace/{part_id} | 원문 trace (조/항/호) |
| GET /compiler/coverage-summary | 커버리지 요약 |
| GET /compiler/health | 엔진 상태 |

---

## Workflow 변경

### 기존:
```
AI 판단 → 즉시 task 생성 → 스케줄 확정 → 위반 경고
```

### 변경 후:
```
Compiler Core → Candidate 생성 → Human Review
→ 승인 → Runtime 등록
```

---

## main.py 등록

```python
from routers.compiler_core import router as compiler_router
from routers.residual_intelligence import router as ri_router
app.include_router(compiler_router)
app.include_router(ri_router)
```

---

## 준수 사항

- ✅ Runtime Layer 유지 (55+ 라우터 미변경)
- ✅ Legal Intelligence Layer 교체 대상 식별 (25+ 라우터)
- ✅ Compiler Core API 생성 (7 엔드포인트)
- ✅ Candidate-first workflow
- ✅ Human Review 존재
- ✅ Source Trace 유지
- ✅ Audit Trail 유지
- ✅ Rollback 가능
- ✅ Semantic inference 제거
- ✅ Confidence score 제거
