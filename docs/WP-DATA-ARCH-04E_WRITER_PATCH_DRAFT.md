# WP-DATA-ARCH-04E · WRITER PATCH DRAFT  (PATCH ARTIFACT ONLY · CODE MUTATION = 0)

```
목적 = equipment_checkins.submit_checkin 에서 schedule_id 제공 시 asset.factory_id 와 schedule.factory_id pair 일치를 side-effect 전 fail-closed 검증.
규율 = DIFF/ARTIFACT 전용. 실제 적용/배포 금지 = execution gate.
공통 계약 = ASSET = factory authority. schedule = optional relation. cross-factory/미해결 시 INSERT/UPDATE/notify 모두 미수행.
           standalone(schedule_id NULL) 허용 · asset factory 로 저장. schedule factory 로 asset factory overwrite 금지.
DB migration = 없음 (schedule_id·factory_id 이미 존재). rows=0.
```

---

## W — routers/equipment_checkins.py :: submit_checkin()  (blob 6773b8a4, diff)

asset lookup + factory_id/company_id 확보 직후, `# 체크인 레코드 저장` 앞에 pair-validation(side-effect 전) 삽입:

```diff
     asset      = asset_res.data[0]
     factory_id = asset.get("factory_id")
     company_id = None
     if factory_id:
         fac = supabase.table("factories").select("company_id").eq(
             "id", factory_id
         ).limit(1).execute()
         company_id = (fac.data[0] if fac.data else {}).get("company_id")

+    # WP-04E: schedule_id 제공 시 asset.factory_id 와 schedule.factory_id pair 일치 검증 (side-effect 전 fail-closed).
+    #   ASSET = factory authority. cross-factory / 미해결 pair 는 INSERT/UPDATE/notify 이전에 중단.
+    if body.schedule_id:
+        _ws = supabase.table("work_schedules").select("id, factory_id").eq(
+            "id", body.schedule_id
+        ).limit(1).execute()
+        if not _ws.data:
+            raise HTTPException(status_code=409, detail="점검 일정을 찾을 수 없습니다")
+        _sched_factory_id = _ws.data[0].get("factory_id")
+        if not _sched_factory_id:
+            raise HTTPException(status_code=409, detail="일정의 factory_id를 확인할 수 없습니다")
+        if not factory_id:
+            raise HTTPException(status_code=409, detail="설비의 factory_id를 확인할 수 없습니다")
+        if _sched_factory_id != factory_id:
+            raise HTTPException(status_code=409, detail="설비와 일정의 사업장이 일치하지 않습니다")
+
     # 체크인 레코드 저장
     now_iso     = datetime.now(timezone.utc).isoformat()
     insert_data = {
```
비고:
- INSERT.factory_id 는 계속 `asset.factory_id`(=`factory_id` 변수) — schedule factory 로 overwrite하지 않음.
- schedule_id 없으면(standalone) 이 블록 전체 skip → 기존 동작(asset factory 로 저장) 유지.
- HTTPException 이미 import됨(`from fastapi import APIRouter, Depends, HTTPException, Query`).
- 익명 스캔(POST 인증 불필요) 계약 무변경 · GET auth/scope 무변경.

---

## TESTS (pytest, 원문 제출 — Cursor/CI)
```
전제: supabase mock/stub. production/real DB 접근 금지, 신규 데이터 생성 금지.

T1  schedule_id 없음(standalone) + asset.factory=A → INSERT factory_id=A · schedule_id 미포함 · 200
T2  schedule_id 제공 + schedule.factory==asset.factory==A → INSERT factory_id=A · schedule_id 저장 · 200
T3  schedule_id 제공 + work_schedules 조회 결과 없음 → HTTP 409 · equipment_checkins INSERT 호출 = 0
T4  schedule_id 제공 + schedule.factory_id=None → HTTP 409 · INSERT 호출 = 0
T5  schedule_id 제공 + asset.factory_id=None → HTTP 409 · INSERT 호출 = 0
T6  schedule_id 제공 + schedule.factory=B != asset.factory=A → HTTP 409 · INSERT 호출 = 0 · work_schedules UPDATE 0 · notification 0
T7  overall_result 무효값 → 422 (기존 검증 무회귀)
T8  worker_id/worker_name 둘 다 없음 → 422 (기존 검증 무회귀)
T9  정상 OK + schedule_id → work_schedules DONE update 호출 발생 (무회귀)
T10 정상 NG + factory_id → _notify_abnormal_checkin 호출 발생 (무회귀)
기존 관련 테스트도 실행.
```

## 배포 전제
```
DB migration 불요 (schedule_id·factory_id 이미 존재, rows=0). schema-first 제약 없음.
→ 이 writer hardening 은 HASH maintenance 이전 단독 deploy 가능 (WRITE OFF 불요; rows=0이라 backfill/reconciliation 불요).
```
