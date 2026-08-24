# WP-DATA-ARCH-04D · WRITER PATCH DRAFTS  (PATCH ARTIFACT ONLY · CODE MUTATION = 0)

```
목적 = safety_inspections INSERT creator 2개가 신규 inspection에 factory_id = parent work_schedules.factory_id 기록.
규율 = DIFF/ARTIFACT 전용. 실제 적용/배포 금지 = cutover gate.
공통 계약 = factory source = parent work_schedules ONLY (request/user/asset/company 추론 금지).
           NULL fallback 후 계속 금지 = 2 writer 전부 fail-closed(HTTP 409) 강제.
           work_schedules.factory_id nullable=YES → 구조적 방어를 코드에 둔다(오늘 linked parent NULL 0건이나 미래 방어).
경계(비수정) = submitted_by(별도 CD5-1) · worker_check inspector_id roster fallback(별도 HOLD) 은 04D에서 손대지 않음.
```

---

## W1 — routers/worker_check.py :: submit_check()  (blob 503cf84a, diff)

현재 schedule_ref 확정 직후·safety_inspections INSERT 직전에 (a) standalone fail-closed + (b) parent factory PRE-READ fail-closed 추가, INSERT에 factory_id 주입:

```diff
     schedule_ref = body.schedule_id
     if not schedule_ref and body.assignment_id:
         _wa = supabase.table("work_assignments").select("schedule_id").eq("id", body.assignment_id).limit(1).execute()
         if _wa.data:
             schedule_ref = _wa.data[0].get("schedule_id")

+    # WP-04D: schedule-backed only. 신규 standalone(assignment_id NULL) 생성 금지 → fail-closed.
+    if not schedule_ref:
+        raise HTTPException(status_code=409, detail="일정 참조가 없어 점검을 생성할 수 없습니다.")
+
+    # WP-04D: parent work_schedules 에서 factory_id companion 확보 (body.factory_id 신뢰 금지).
+    _ws = supabase.table("work_schedules").select("id, factory_id").eq("id", schedule_ref).limit(1).execute()
+    if not _ws.data:
+        raise HTTPException(status_code=409, detail="일정을 찾을 수 없습니다.")
+    _parent_factory_id = _ws.data[0].get("factory_id")
+    if not _parent_factory_id:
+        raise HTTPException(status_code=409, detail="일정의 factory_id를 확인할 수 없습니다.")
+
     ins_res = supabase.table("safety_inspections").insert({
         "inspector_id": inspector_id,
         "inspection_date": now,
         "status_code": status_code,
         "assignment_id": schedule_ref,
+        "factory_id": _parent_factory_id,   # WP-04D parent companion (request factory_id 미사용)
     }).execute()
```
비고:
- `CheckSubmitBody.factory_id` 는 계속 **미사용**(신뢰 금지). factory는 오직 parent schedule.
- **inspector_id 로직 불변** — roster fallback(users→worker_registry) 은 04D 범위 아님(별도 HOLD). factory 추가가 이 위험을 가리지 않음.
- 기존 legacy assignment_id=NULL 행은 DB 데이터이며 이 코드가 건드리지 않음. 신규 standalone 만 409로 차단.

---

## W2 — routers/inspection_checklist.py :: start_inspection()  (blob 3907ba49, diff)

`work_schedule_id` 가 parent id. work_schedules status UPDATE(side-effect) **전에** parent factory PRE-READ → fail-closed → INSERT에 factory_id 주입:

```diff
     _ensure_ws_own(supabase, work_schedule_id, current)
     try:
         body = body or {}
         inspector_name = body.get("inspector_name", "")
         started_at     = body.get("started_at", date.today().isoformat())
+
+        # WP-04D: parent factory companion PRE-READ (side-effect 전 fail-closed)
+        _ws = supabase.table("work_schedules").select("factory_id").eq("id", work_schedule_id).limit(1).execute()
+        if not _ws.data:
+            raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")
+        _parent_factory_id = _ws.data[0].get("factory_id")
+        if not _parent_factory_id:
+            raise HTTPException(status_code=409, detail="일정의 factory_id를 확인할 수 없습니다.")
+
         ws_res = supabase.table("work_schedules").update({
             "status_code": "in_progress", "inspector_name": inspector_name,
         }).eq("id", work_schedule_id).execute()
         if not ws_res.data:
             raise HTTPException(status_code=404, detail="점검 일정을 찾을 수 없습니다.")
         insp_res = supabase.table("safety_inspections").insert({
             "assignment_id": work_schedule_id, "inspection_date": started_at, "status_code": "in_progress",
+            "factory_id": _parent_factory_id,   # WP-04D parent companion
         }).execute()
```
비고: factory source = `work_schedules(work_schedule_id).factory_id`. fail-closed 를 status UPDATE **앞**에 두어 부분반영(상태만 in_progress) 방지. auth/ownership(_ensure_ws_own) 무변경.

---

## 배포 전제 (cutover와 연동)
```
schema-first: 두 patch 는 factory_id 컬럼이 존재하는 NEW DB 에서만 deploy (OLD DB + NEW CODE = BREAKS).
순서 = ADD COLUMN(+linked backfill) → 이 2 patch deploy. (WRITER_CUTOVER_PLAN 참조)
standalone 정책: 신규 standalone 생성 금지(W1 409). 기존 legacy assignment_id=NULL 행은 불변.
submitted_by / composite FK / HASH = 미포함(별도 gate).
```
