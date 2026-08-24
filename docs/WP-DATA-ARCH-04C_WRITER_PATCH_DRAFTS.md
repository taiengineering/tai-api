# WP-DATA-ARCH-04C · WRITER PATCH DRAFTS  (PATCH ARTIFACT ONLY · CODE MUTATION = 0)

```
목적 = 3 INSERT creator가 신규 assignment에 factory_id = parent work_schedules.factory_id 를 기록하도록 준비.
규율 = 이 문서는 DIFF/ARTIFACT 전용. 파일 실제 적용 금지. deploy = cutover gate.
공통 계약 = factory source는 오직 parent schedule. request/user/asset/company 추론 금지.
           NULL fallback 후 계속 금지 = 3 writer 전부 fail-closed로 **강제**(W1 RAISE EXCEPTION · W2/W3 HTTP 409).
           parent factory_id NULL은 오늘 0건이나 work_schedules.factory_id가 nullable이므로 구조적 방어를 코드에 둔다.
IDEMPOTENCY = 이번 patch에 ON CONFLICT 미포함(UNIQUE arbiter 부재). PREPARED ≠ DEPLOYED.
```

---

## W1 — public.generate_daily_assignments()  (DB function replacement SQL)

REPLACEMENT (factory_id 컬럼 + ws.factory_id 추가; 그 외 동일):
```sql
CREATE OR REPLACE FUNCTION public.generate_daily_assignments()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
begin

-- ★ fail-closed: active schedule 중 factory_id NULL 존재 시 중단 (NULL fallback 후 계속 금지)
if exists (
    select 1 from work_schedules
    where active_yn = true and factory_id is null
) then
    raise exception 'generate_daily_assignments: active schedule factory_id NULL';
end if;

insert into work_assignments (
    id,
    schedule_id,
    asset_id,
    assigned_user_id,
    scheduled_date,
    status_code,
    factory_id            -- ★ 추가
)
select
    gen_random_uuid(),
    ws.id,
    ws.asset_id,
    ws.assigned_user_id,
    current_date,
    'READY',
    ws.factory_id         -- ★ 추가 (parent companion)
from work_schedules ws
where ws.active_yn = true;

end;
$function$;
```
비고: ON CONFLICT는 이번 범위 아님(WA transition). 함수 교체는 cutover의 patched-writer deploy 단계에서.

---

## W2 — routers/legal_engine_patch.py :: auto_assign_schedules  (diff)

스케줄 조회는 이미 factory_id를 select 하므로 쿼리 변경 불요. (a) side-effect 시작 전 fail-closed 가드, (b) assign_rows dict에 1줄 추가:
```diff
     sched_res = q.execute()
     schedules = sched_res.data or []
 
+    # ★ fail-closed: factory_id 없는 일정 존재 시 자동배정 전체 중단 (NULL fallback 후 계속 금지)
+    if any(not s.get("factory_id") for s in schedules):
+        raise HTTPException(
+            status_code=409,
+            detail="factory_id가 없는 일정이 있어 자동배정을 중단합니다.",
+        )
+
     if not schedules:
         return {"status": "success", "data": {"assigned": 0, "skipped": 0, "message": "배정할 스케줄 없음"}}
...
         for s in scheds:
             assign_rows.append({
                 "schedule_id":      s["id"],
                 "assigned_user_id": manager_id,
                 "scheduled_date":   s.get("planned_date") or today_str,
                 "status_code":      "PENDING",
                 "created_at":       now,
+                "factory_id":       s["factory_id"],   # ★ parent companion (조회 시 이미 select됨)
             })
             sched_ids.append(s["id"])
```
비고: s["factory_id"]는 상단 `.select("id, factory_id, company_id, ...")`에서 확보. request/user 신뢰 아님.

---

## W3 — routers/work_schedules.py :: _apply_one_update  (diff)

업데이트 **전에** 부모 factory_id를 PRE-READ하여 fail-closed → 통과 후에만 schedule UPDATE(부분반영 방지) → 신규 INSERT에 주입:
```diff
+    # ★ parent factory PRE-READ (side-effect 전 fail-closed; factory_id는 이 endpoint가 변경하는 필드 아님)
+    _parent_factory_id = None
+    if assign_changed and fields["assigned_user_id"]:
+        _parent = supabase.table("work_schedules").select("factory_id") \\
+            .eq("id", schedule_id).limit(1).execute()
+        _parent_factory_id = _parent.data[0].get("factory_id") if _parent.data else None
+        if not _parent_factory_id:
+            raise HTTPException(
+                status_code=409,
+                detail="일정의 factory_id를 확인할 수 없습니다.",
+            )
+
+    # fail-closed 통과 후에만 기존 UPDATE 수행
     res = supabase.table("work_schedules").update(payload).eq("id", schedule_id).execute()
     updated = bool(res.data)

     if assign_changed:
         auid = fields["assigned_user_id"]
         if auid:
             existing = supabase.table("work_assignments").select("id") \\
                 .eq("schedule_id", schedule_id).in_("status_code", wa_active_query_values()).limit(1).execute()
             if existing.data:
                 supabase.table("work_assignments").update({
                     "assigned_user_id": auid, "updated_at": now,
                 }).eq("id", existing.data[0]["id"]).execute()
             else:
                 supabase.table("work_assignments").insert({
                     "schedule_id": schedule_id, "assigned_user_id": auid,
                     "scheduled_date": datetime.now().date().isoformat(),
                     "status_code": wa_write_ready(), "created_at": now,
+                    "factory_id": _parent_factory_id,   # ★ parent companion (PRE-READ 값)
                 }).execute()
         else:
             supabase.table("work_assignments").update({
                 "status_code": "CANCELLED", "updated_at": now,
             }).eq("schedule_id", schedule_id).in_("status_code", wa_active_query_values()).execute()
     return updated
```
비고: fail-closed 검사를 부모 UPDATE **앞**에 배치 → factory_id NULL이면 schedule UPDATE 자체가 수행되지 않아 부분반영(부모만 변경) 없음. `factory_id`는 이 endpoint가 변경하는 필드가 아니므로 UPDATE 직전 동일 schedule PRE-READ 값을 companion source로 사용(계약 일치). 존재-UPDATE 경로는 factory 무변(기존 행 유지). CANCELLED 경로 무관.

---

## 배포 전제 (cutover와 연동)
```
schema-first: 세 patch는 factory_id 컬럼이 존재하는 NEW DB 상태에서만 deploy (OLD DB + NEW CODE = BREAKS).
따라서 순서 = ADD COLUMN(+backfill) → 이 3 patch deploy. (WRITER_CUTOVER_PLAN 참조)
ON CONFLICT / UNIQUE = 미포함. 별도 WA maintenance transition에서.
```
