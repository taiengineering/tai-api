# WP-PARTITION-02B-R1 · HASH EXECUTION RUNBOOK  — EXECUTION HOLD

```
UNIT = WP-PARTITION-02B-R1  work_schedules HASH rebased production execution
MODE = RUNBOOK ONLY · 각 단계 실행은 HASH EXECUTION gate 승인 후
전제 = artifact package SEALED · dry-run PASS · 04C/04D/04E LIVE · single-tx atomicity 보장 가능
CODE DEPLOY = 0 (companion 이미 LIVE) · Railway deployed SHA 전후 동일 expected
```

## 0. 실행 주체
```
DB(LOCK/PRECHECK/UP/POSTCHECK/DOWN) = Claude(DB owner) MCP.
application maintenance ON/OFF = 운영자/Cursor (트래픽 차단).
UP 은 반드시 단일 transactional apply 1회 (executor atomicity 미보장 시 STOP).
```

## 1. 실행 순서 (승인 후)
```
1. FRESH PRECHECK (LOCK 전 예비)
   - tai-api/main HEAD = 6874bb85 (또는 그 이후 no-op) · deployed SHA 동일
   - work_schedules_old/_new/_mig_* 부재 · dup target 0 · factory NULL 0
   - work_schedules_old 존재 시 STOP (이전 미완 잔재)
2. MAINTENANCE ON (application write freeze)
   - API/worker 트래픽 차단. 활성 write 세션 0 확인:
     SELECT count(*) FROM pg_stat_activity WHERE state='active' AND query ILIKE '%work_schedules%';
3. HASH UP APPLY (단일 transaction)
   - rebased UP 전체(§0-B LOCK → §1 PRECHECK → §2~§9 shadow/copy/meta → §11 pair CHECK →
     §12 cutover+composite FK → §13~§14 RLS/grants → §14-B matview rebind → §15 POSTCHECK → COMMIT) 1회 실행.
   - §0-B 의 4테이블 ACCESS EXCLUSIVE LOCK 이 direct anon equipment_checkins INSERT 까지 대기시킴.
   - 실패(RAISE) 시 전체 rollback → 원본 무변경. 원인 규명 후 재시도.
4. POST-APPLY DB VALIDATION (UP §15 POSTCHECK 가 tx 내 통과했음 + 별도 read 재확인)
   - partitions 16 · relkind 'p' · PK(id,factory_id) · 37col full-row equality
   - wa/si MATCH FULL + pair CHECK · ec MATCH SIMPLE + ON DELETE SET NULL(schedule_id)
   - comments/grants/policies/owner/RLS exact
   - ★ work_assignments.factory_id / safety_inspections.factory_id 존재(보존) · mismatch 0
   - equipment_checkins cross-factory 0
   - ★ dashboard_stats NEW canonical OID 재결합 · old 미참조 · populated
   - ★ anchor lockdown: work_schedules_old / _mig_ws_data_snapshot / p00~p15 anon·authenticated·service_role grants 0
     · canonical work_schedules service_role SELECT 정상
5. ANALYZE public.work_schedules;   (첫 production query 부터 partition stats 사용 가능하게)
6. READ-ONLY HEALTH / QUERY / EXPLAIN SMOKE (코드 배포 없음 · production synthetic business write = 0)
   - /health 200 · deployed SHA == step1 (불변)
   - GET /work-schedules?factory_id=... (partition pruning) · GET /work-schedules/{id}
   - EXPLAIN 으로 partition pruning 확인 (physical child 직접 접근 아님, logical parent 경유)
   - refresh_dashboard_stats() 1회 실행 → 정상(NEW canonical 참조) 확인
   - ※ PATCH/POST 등 business write smoke 는 하지 않는다. 실제 natural write 발생 시 관찰만.
7. MAINTENANCE OFF (트래픽 재개)
8. WINDOW 유지 (work_schedules_old 보존 — FAST-PATH DOWN 가능 상태)
   - 기능 검증 통과 후 별도 cleanup WP 승인 시에만 DROP work_schedules_old (그 전엔 금지)
   - ★ cleanup 시 dashboard_stats 는 이미 NEW 에 결합됐으므로 old DROP 이 matview 로 막히지 않음(POSTCHECK 로 사전 보장)
```

## 2. WRITE OFF / DIRECT ANON MODEL
```
이 HASH 는 04D식 별도 DB WRITE-OFF 트리거가 불필요하다.
이유 = UP 이 단일 tx 안에서 4테이블 ACCESS EXCLUSIVE LOCK 을 잡고 composite FK 까지 만든 뒤 COMMIT 하므로,
       migration 중 direct anon INSERT 는 lock 대기, COMMIT 후엔 composite FK 가 이미 pair 를 강제.
       → cross-factory 우회 window 0.
단, application maintenance ON 은 병행(사용자 500/락대기 최소화). single-tx atomicity 가 이 모델의 필수 전제.
```

## 3. ROLLBACK (기능 검증 실패 시)
```
조건 = work_schedules_old 존재(FAST PATH).
실행 = rebased DOWN 1회 (WRITE OFF/lock → composite FK/pair CHECK drop → new→old reconciliation →
       full-row equality → matview drop → partitioned parent drop → old rename back → old grants exact 복원 →
       matview restored 재결합 → 단일 FK 복원 → ★04C/04D companion PRESERVE → exact POSTCHECK → COMMIT).
결과 = HASH 실행 직전(04C/04D/04E 완료) 상태로 복원. wa/si.factory_id 보존.
       04C/04D writer code rollback = 금지/불필요. Railway 재배포 불요(코드 불변).
old 를 이미 DROP 했다면 DOWN §0 ABORT → 백업 복원 별도 절차.
```

## 4. 실패 지점별 상태
```
UP PRECHECK 실패      → tx rollback · 원본 무변경 · 재시도 안전
UP copy/full-row 실패 → tx rollback · 원본 무변경 (내용손상 사전차단)
UP cutover/FK 실패    → tx rollback · 원본 무변경
UP matview rebind 실패 → tx rollback · 원본 무변경 (dashboard_stats old 결합 유지 상태로 롤백)
UP POSTCHECK 실패     → tx rollback · 원본 무변경
UP 성공/기능검증 실패 → DOWN 실행 (데이터 손실 0 · companion 보존 · matview restored)
DOWN reconcile/contract 실패 → tx rollback · 파티션 유지 · 재시도 안전
old DROP 후 DOWN      → §0 ABORT
```

## 5. STOP 조건
```
- single-tx atomicity 미보장(executor) → apply 전 STOP
- work_schedules_old 사전 잔재 → STOP
- PRECHECK 위반(factory NULL / mismatch / dup / cross-factory / companion 부재) → 자동 RAISE rollback
- dry-run 미통과 상태에서 production apply 요구 → STOP
- equipment_checkins cross-factory > 0 → human resolution (자동 보정 금지)
- dashboard_stats 외 다른 객체가 work_schedules 에 종속(matview/view/rule)된 것이 사전 발견 → STOP (rebind 범위 재설계)
```

## 6. 경계
```
이 unit = work_schedules HASH 물리전환 + 3 child composite FK rewire (canonical 설계 그대로)
         + dashboard_stats matview OID rebind + rollback anchor/physical partition privilege lockdown.
미포함 = old table DROP(별도 cleanup WP) · work_schedules 본체 RLS anon 정책 보안 강화(별건 — 이번엔 exact 보존만)
        · child 명명정리(assignment_id 등 별건)
        · submitted_by writer(CD5-1) · worker_check inspector_id roster(별도 HOLD).
20260822 package = 역사적 design artifact 로 보존(삭제/수정 안 함). 이 rebased package 가 execution canonical.
```
