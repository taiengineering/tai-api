# WP-PARTITION-02B-R1 · HASH DRY-RUN PLAN  (rollback-only · production 미변경)

```
UNIT = WP-PARTITION-02B-R1  work_schedules HASH rebased dry-run
MODE = 설계 문서 · 실제 실행은 HASH EXECUTION gate 승인 후
목적 = rebased UP 을 rollback-only 로 검증하여 실제 production apply 전 안전 확인.
```

## 1. 왜 transaction-controlled dry-run 이 필요한가
```
rebased UP 파일은 내부에 BEGIN ... COMMIT 을 포함한다(단일 tx 원자성 계약).
파일을 그대로 실행하면 COMMIT 이 영구 반영되어 outer rollback 이 불가능하다.
→ dry-run 은 "UP 과 다른 SQL 로직" 을 만들지 않는다. transaction boundary 만 외부 제어한다:
   UP 본문에서 최상단 BEGIN 과 최하단 COMMIT 만 제거한 동일 SQL 을 하나의 외부 트랜잭션으로 감싸고,
   맨 끝에 의도적 RAISE EXCEPTION 을 두어 전체 rollback 을 강제한다.
   (SQL 로직·검증문·DDL 순서는 UP 과 100% 동일. 오직 tx 경계만 외부 제어.)
```

## 2. dry-run 구조 (개념)
```
[외부 단일 트랜잭션 시작]
  (UP §0-B LOCK 4테이블)
  (UP §1 PRECHECK 전체)
  (UP §2 스냅샷 테이블 생성 + _mig_/matview privilege lockdown)
  (UP §3~§4 shadow partitioned table + 16 partitions + partition privilege lockdown)
  (UP §5~§6 37col copy + full-row equality)
  (UP §7~§9 indexes + outbound FK + comments 재생성)
  (UP §11 wa/si pair CHECK)
  (UP §12 cutover: 단일FK drop → rename → old privilege lockdown → composite FK 3종)
  (UP §13~§14 RLS/policy/owner/grants 재생성)
  (UP §14-B dashboard_stats matview OID rebind)
  (UP §15 POSTCHECK 전체 + child companion 보존 + matview + anchor/partition lockdown assertion)
  -- 여기까지 UP 과 동일. 이제 결과를 캡처하고 강제 rollback:
  SELECT ... INTO (검증 결과 지표들)  -- 아래 §3 체크리스트
  RAISE EXCEPTION 'DRYRUN_RESULT || <지표들>';   -- 전체 rollback 강제
[트랜잭션 rollback — production 영구 변경 0]
```

## 3. dry-run 검증 체크리스트 (RAISE 로 캡처)
```
STRUCTURE:
  partitions = 16
  parent relkind = 'p' (partitioned)
  PK = (id, factory_id)  · UNIQUE = (inspection_set_id, planned_date, factory_id)
DATA:
  37-col full-row equality old↔new = 0 diff
  row count old == new (66)
CHILD REWIRE:
  wa FK confmatchtype='f' (MATCH FULL) · si FK confmatchtype='f' · ec FK confmatchtype='s' (MATCH SIMPLE)
  wa CHECK chk_wa_schedule_factory_pair 존재 · si CHECK chk_si_schedule_factory_pair 존재
  si legacy NULL pair 1건: composite FK + pair CHECK 통과(둘 다 NULL) 확인
  ec ON DELETE SET NULL(schedule_id) column-list DDL 성공 (PG 17.6에서 실제 생성됨)
META EXACT:
  comments/grants(grantor·is_grantable)/policies/owner/RLS(enabled+forced) old↔new = 0 diff
COMPANION 보존:
  work_assignments.factory_id 존재 · safety_inspections.factory_id 존재 (HASH 가 삭제 안 함)
MATVIEW (CRITICAL-1):
  dashboard_stats 가 NEW canonical work_schedules OID 에 재결합 (pg_depend/pg_rewrite)
  dashboard_stats 가 work_schedules_old 를 더 이상 참조하지 않음
  dashboard_stats populated=true · unique idx idx_dashboard_stats_singleton 존재 · owner postgres
  refresh_dashboard_stats() 호출 정상(이름기반 REFRESH — dry-run tx 내에서는 skip 가능, rollback 후 read 로 확인)
ANCHOR/PARTITION LOCKDOWN (CRITICAL-2):
  _mig_ws_* 전부 anon/authenticated/service_role grants = 0
  work_schedules_old direct grants(anon/authenticated/service_role) = 0
  p00~p15 direct grants(anon/authenticated/service_role) = 0
  canonical parent work_schedules service_role SELECT = 정상 (API access 보존)
```

## 4. rollback 후 재확인 (별도 read, 트랜잭션 밖)
```
production original structure exact:
  work_schedules relkind='r' · PK(id) 단일 · rows 66 · cols 37
  work_schedules_new / _p00~_p15 / _mig_* 부재 (전부 rollback)
04C/04D companions intact:
  work_assignments.factory_id 존재 · mismatch 0
  safety_inspections.factory_id 존재 · linked mismatch 0 · legacy NULL pair 1
equipment_checkins: rows 0 · 단일 FK 그대로
MATVIEW restored (rollback 후):
  dashboard_stats 가 restored regular work_schedules OID 에 결합 (dry-run 은 UP 만 rollback 하므로 원래 OID 로 복귀)
  refresh_dashboard_stats() 실행 시 정상(오류 없음) — 이름기반이라 rebind 후에도 자동으로 현재 canonical 참조
  _mig_ws_matview/_matview_idx/_matview_grants 부재(rollback)
anchor lockdown(dry-run 특성): dry-run 은 전체 rollback 이므로 lockdown 도 함께 rollback →
  production apply(비-rollback)에서만 영구. dry-run 은 lockdown DDL 이 오류 없이 수행됨을 확인.
```

## 5. dry-run PASS 기준
```
= §3 전 항목 expected + §4 rollback 후 production 원형 exact + companion intact.
하나라도 실패 → HASH EXECUTION gate 진입 금지, 원인 규명.
특히 ec ON DELETE SET NULL(schedule_id) column-list DDL 이 PG 17.6에서 실제 성공하는지가 핵심 관문.
```

## 6. 실행 주체/도구
```
dry-run = Claude(DB owner) MCP execute_sql 단일 호출(외부 tx + 강제 RAISE rollback).
production apply = 별도 HASH EXECUTION gate 승인 후 (EXECUTION_RUNBOOK).
dry-run 은 production 을 변경하지 않으므로 maintenance/WRITE OFF 불요. 단 LOCK 획득은 순간적.
```
