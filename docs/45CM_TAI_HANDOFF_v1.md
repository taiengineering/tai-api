# 45CM / TAI Cleanup & Stabilization Handoff

## 현재 상태 요약

이번 세션의 목표는:

- TAI 전체를 폐기하는 것이 아니라
- runtime core를 보호하면서
- migrated surface / extraction lineage / historical residue를
- 운영 수준에서 분리·격리하는 것이었다.

현재 상태:

- runtime core 보호 완료
- migrated surface freeze 완료
- extraction pipeline isolation 완료
- deploy ownership 분리 완료
- obvious residue cleanup 완료
- DB logical boundary 정의 완료

---

# 1. Canonical Runtime (절대 보호 영역)

다음은 현재 active canonical runtime이다.

## Runtime Services

- services/legal_engine_svc.py
- services/legal_runtime.py
- services/diagnosis_service.py
- services/runtime_evaluator_svc.py
- services/simulation_svc.py
- services/rule_gen_svc.py

## Runtime Routers

- routers/compiler_core.py
- routers/engine_legal.py

## Runtime DB

- runtime_*
- facility_*
- compliance_*
- law_*
- schedule_*
- task_*
- SaaS/product/payment tables

## Runtime Infra

- Supabase runtime DB
- Railway runtime
- DATABASE_URL
- active deploy configs

⛔ 절대 cleanup 금지
⛔ DROP/TRUNCATE 금지
⛔ schema migration 금지

---

# 2. Migrated Surface 상태

## Canonical UI

현재 canonical UI는 모두 45cminc 기준.

### Canonical Repos

- 45cminc/ui
- apps/mkt-ui
- shell
- ops-ui
- prj-ui

### Canonical Deploy

- app.45cm.com
- ops-app.45cm.com
- prj-app.45cm.com

---

## Frozen Legacy Surface

### Repo

taiengineering/45cm/surfaces/app-shell

### 상태

FROZEN

### 적용 완료

- README freeze notice
- LEGACY_MOVED_TO_45CM.md
- FREEZE_NOTICE.md
- DEPLOYMENT_STATUS.md
- ARCHIVE_CANDIDATE.md

### 현재 의미

historical/reference only.

신규 개발 금지.
운영 ownership 없음.

---

# 3. Extraction Pipeline 상태

## 대상

- engine/*
- scripts/track_e_phase2_run.py
- stage_*
- candidate/evidence/family/residual graph 계층

## 현재 판단

offline extraction/decomposition lineage.

현재까지:
runtime direct dependency는 미확인.

하지만:
runtime reconstruction lineage 가능성이 매우 높음.

즉:

⛔ 삭제 금지
⛔ temp 취급 금지

---

# 4. Database 상태

## 핵심 결과

DB는 다음 boundary로 분리 완료:

| Boundary | 의미 |
|---|---|
| Runtime Canonical | active runtime |
| Extraction/Stage | legal lineage |
| Historical/Audit | traceability |
| Legacy/Contaminated | frozen historical |
| Quarantine | ownership unknown |

---

## DB 규모

| 영역 | 규모 |
|---|---|
| Runtime Canonical | ~262 tables |
| Extraction/Stage | ~79 tables |
| Historical/Audit | ~35 tables |
| Legacy/Contaminated | 5 tables |
| Quarantine | 97 tables |

총:
~550+ tables.

---

## 중요한 발견

### Extraction은 temp가 아님

특히:

- evidence_candidate
- family_candidate
- constraint_node
- residual_candidate

등은:
runtime 재구축 lineage 가능성이 큼.

즉:
historical + reproducibility asset.

---

## Quarantine이 현재 유일한 주요 미정 영역

약 97개 0-row tables.

현재 상태:
- dormant feature
- reserve schema
- abandoned feature
- 미구현 runtime

혼재 가능성.

현재:
cleanup 금지 상태.

---

# 5. Cleanup 상태

## 완료된 것

- runtime 보호
- migrated surface freeze
- extraction isolation
- stale deploy 식별
- obvious residue archive
- test artifact 제거
- historical preservation 정책화

---

## 남겨둔 것 (의도적)

삭제하지 않은 것:

- session logs
- workorder docs
- migration history
- prompts
- audit docs
- extraction lineage
- historical memory

이유:
historical/reference/debugging value.

---

# 6. 절대 금지 작업

## Runtime

- services/* refactor
- runtime schema 변경
- runtime table rename
- DB cleanup
- FK rewiring
- public schema split
- RLS 변경

## Extraction

- engine/* 삭제
- stage_* 삭제
- candidate/evidence graph 삭제

## Historical

- audit log 삭제
- migration history 삭제
- archive cleanup

---

# 7. 현재 권장 상태

TAI는 이제:

“계속 cleanup하는 workspace”

가 아니라:

“운영 유지 + historical isolation 완료 상태”

이다.

즉:

- maintenance mode 유지
- runtime bugfix만 수행
- 대규모 cleanup 중단
- 추가 cleanup은 quarantine만 대상으로 제한

---

# 8. 다음에 가능한 작업 (선택적)

## 가능

- quarantine refinement
- runtime dependency graph
- service ↔ table ownership graph
- backup policy
- retention policy
- schema namespace planning

---

## 아직 금지

- schema split
- extraction schema 이동
- runtime schema 이동
- archive DB 분리
- destructive cleanup

---

# 9. 핵심 결론

이번 작업의 핵심 성과는:

“무엇이 runtime인가”
“무엇이 migrated surface인가”
“무엇이 extraction lineage인가”
“무엇이 historical asset인가”

를 운영 수준에서 분리한 것이다.

현재는:
cleanup보다 stabilization이 더 중요하다.
