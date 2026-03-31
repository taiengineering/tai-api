# TAI Cursor 작업지시서 — 법정점검 반복일정 생성 버그 수정

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 근거: 실제 API 호출 테스트 결과

---

## 테스트 결과 요약 (실측)

```
[정상]
✅ POST /legal-engine/diagnose/step1
   → factory_diagnosis_results 183건 저장 확인
   → diagnosis_rule_results 183건 저장 확인
   → diagnosis_id 응답 반환 확인

✅ POST /inspection/generate-schedules/{factory_id}
   → 67개 inspection_set → 152개 work_schedules 생성 성공

[버그]
🔴 BUG-1: diagnose/step1 → create-inspection-sets 경로 단절
🔴 BUG-2: create-inspection-sets 타임아웃 (158건 insert)
🟡 BUG-3: schedule-engine/generate 단건 작동 안 함
🟡 BUG-4: anchor 없는 set에 generate-schedules 실행 시 방어 없음
```

---

## BUG-1 🔴 diagnose/step1 → create-inspection-sets 경로 단절

### 원인
`create-inspection-sets`가 `factories.legal_result_json`(구 apply API 전용)만 체크.
`diagnose/step1`은 `factory_diagnosis_results`에 저장하는데 `legal_result_json`은 채우지 않아서
"법령판정 결과가 없습니다." 오류 발생.

### 수정 파일
`routers/legal_engine.py` — `create_inspection_sets_from_legal()` 함수

### 수정 내용

```python
@router.post("/create-inspection-sets/{factory_id}")
async def create_inspection_sets_from_legal(factory_id: str):
    supabase = get_supabase()
    fac = supabase.table("factories").select(
        "id, company_id, legal_result_json"
    ).eq("id", factory_id).single().execute()
    if not fac.data:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다.")

    company_id   = fac.data.get("company_id")
    result_json  = fac.data.get("legal_result_json")
    inspection_rules = []

    # ── 기존: legal_result_json (apply API 경로) ──
    if result_json:
        inspection_rules = result_json.get("inspection_required", [])

    # ── 신규 fallback: factory_diagnosis_results (diagnose/step1 경로) ──
    if not inspection_rules:
        try:
            diag_res = supabase.table("factory_diagnosis_results") \
                .select("result_data") \
                .eq("factory_id", factory_id) \
                .eq("is_latest", True) \
                .order("created_at", desc=True) \
                .limit(1).execute()
            if diag_res.data:
                result_data = diag_res.data[0].get("result_data") or {}
                # result_data 구조: {rules: [{rule_type, obligation, ...}]}
                # inspection 타입만 필터링
                all_rules = result_data.get("rules", [])
                inspection_rules = [
                    r for r in all_rules
                    if str(r.get("rule_type", "")).upper() in ("002", "INSPECT", "INSPECTION")
                    or r.get("inspection_required") == True
                ]
                # diagnosis_rule_results에서 직접 가져오는 방법도 병행
                if not inspection_rules:
                    drr = supabase.table("diagnosis_rule_results") \
                        .select("rule_code, rule_name, law_name, law_article, obligation, form_code") \
                        .eq("diagnosis_id",
                            supabase.table("factory_diagnosis_results")
                            .select("id").eq("factory_id", factory_id)
                            .eq("is_latest", True).limit(1).execute()
                            .data[0]["id"]
                        ).execute()
                    # diagnosis_rule_results는 모든 의무를 담고 있어
                    # inspection 식별 불가 → master_building_legal_rules JOIN 필요
                    # 여기서는 law_name 기반으로 inspection_sets 생성
                    inspection_rules = [
                        {
                            "rule_id":       r.get("rule_code", ""),
                            "law_name":      r.get("law_name", ""),
                            "law_article":   r.get("law_article", ""),
                            "description":   r.get("obligation", ""),
                            "inspection_cycle": "",  # master에서 조회
                            "form_code":     r.get("form_code"),
                        }
                        for r in (drr.data or [])
                    ]
        except Exception as e:
            print(f"[CREATE-INSP-SETS] fallback 조회 실패: {e}")

    if not inspection_rules:
        return {
            "status": "success",
            "message": "생성할 점검 항목이 없습니다. 먼저 법령진단을 실행하세요.",
            "data": {"created": 0}
        }

    # ... 이하 기존 inspection_set 생성 로직 유지
```

### ⚠️ 중요: master_building_legal_rules에서 주기 정보 JOIN

diagnosis_rule_results → rule_code로 master_building_legal_rules 조회 후
`inspection_cycle_value`, `cycle_unit_std`, `cycle_base_type`, `cycle_base_guide` 가져와서
inspection_set에 저장해야 합니다.

```python
# rule_code 목록으로 master 한번에 조회
rule_codes = [r.get("rule_id") or r.get("rule_code") for r in inspection_rules]
masters = supabase.table("master_building_legal_rules") \
    .select(
        "rule_id, inspection_cycle_value, inspection_cycle_unit_code,"
        "cycle_unit_std, cycle_base_type, cycle_base_guide"
    ) \
    .in_("rule_id", rule_codes) \
    .eq("obligation_type", "INSPECT") \
    .execute()
master_map = {m["rule_id"]: m for m in (masters.data or [])}

# inspection_set insert 시 master 정보 포함
for rule in inspection_rules:
    m = master_map.get(rule.get("rule_id") or rule.get("rule_code"), {})
    cycle_unit_std = m.get("cycle_unit_std") or "year"
    cycle_value    = int(m.get("inspection_cycle_value") or 1)
    insert_rows.append({
        ...,
        "cycle_unit":       cycle_unit_std,
        "cycle_value":      cycle_value,
        "cycle_base_type":  m.get("cycle_base_type") or "LAST_INSPECTION",
        "cycle_base_guide": m.get("cycle_base_guide") or f"마지막 점검일로부터 {cycle_value}년마다",
        "status_code":      "PENDING_ANCHOR",
        "anchor_confirmed": False,
    })
```

---

## BUG-2 🔴 create-inspection-sets 타임아웃

### 원인
158건을 한 번에 INSERT 시도 → Railway 30초 타임아웃 초과

### 수정 파일
`routers/legal_engine.py` — `create_inspection_sets_from_legal()`

### 수정 내용

```python
# 기존: 50건 배치이지만 DB 왕복이 느림
# 수정: 배치 크기 유지 + 중복 체크 추가 (이미 있는 rule_id는 skip)

# 1. 기존 inspection_sets 조회 (같은 factory, LEGAL_ENGINE source)
existing = supabase.table("inspection_sets") \
    .select("legal_rule_id") \
    .eq("factory_id", factory_id) \
    .eq("source", "LEGAL_ENGINE") \
    .eq("is_active", True) \
    .execute()
existing_rule_ids = {r["legal_rule_id"] for r in (existing.data or [])}

# 2. 이미 있는 rule_id 제외 (중복 skip)
new_rows = [r for r in insert_rows if r["inspection_set_code"] not in existing_rule_ids]

# 3. 없는 것만 insert
created = 0
for i in range(0, len(new_rows), 50):
    res = supabase.table("inspection_sets").insert(new_rows[i:i+50]).execute()
    created += len(res.data or [])

return {
    "status": "success",
    "message": f"{created}개 점검 세트가 생성됐습니다. ({len(existing_rule_ids)}개 기존 유지)",
    "data": {
        "factory_id":   factory_id,
        "created":      created,
        "skipped":      len(existing_rule_ids),
        "source_rules": len(inspection_rules)
    }
}
```

---

## BUG-3 🟡 schedule-engine/generate 단건 작동 안 함

### 현상
`POST /schedule-engine/generate/{inspection_set_id}` 호출 시
`anchor_confirmed=true`, `next_planned_date` 설정된 set인데도 `created_count: 0` 반환

### 수정 파일
`routers/schedule_engine.py`

### 확인 및 수정 내용

```python
# 현재 코드에서 work_schedule INSERT 조건 확인
# 예상 원인: next_planned_date가 과거 날짜일 때 skip 처리

# 테스트한 set의 next_planned_date = '2025-09-30' → 현재 기준 과거
# → 과거 날짜 방어 로직이 생성을 막고 있을 가능성

# 수정 방향:
# 1. next_planned_date가 과거여도 OVERDUE 상태로 생성
# 2. 이미 동일 inspection_set_id + planned_date의 schedule이 있으면 skip (중복 방지)
# 3. anchor 없으면 생성 거부 + 명확한 오류 메시지 반환

@router.post("/generate/{inspection_set_id}")
async def generate_schedule(inspection_set_id: str):
    supabase = get_supabase()
    iset = supabase.table("inspection_sets").select("*") \
        .eq("id", inspection_set_id).single().execute()
    if not iset.data:
        raise HTTPException(status_code=404, detail="점검세트를 찾을 수 없습니다.")

    s = iset.data

    # anchor 없으면 생성 불가
    if not s.get("schedule_anchor_date") or not s.get("anchor_confirmed"):
        return {
            "success": False,
            "reason": "ANCHOR_NOT_SET",
            "message": "기준일이 설정되지 않았습니다. 기준일을 먼저 입력해주세요.",
            "inspection_set_id": inspection_set_id,
            "created_count": 0
        }

    # next_planned_date 계산 (없으면 재계산)
    from dateutil.relativedelta import relativedelta
    anchor = date.fromisoformat(s["schedule_anchor_date"])
    cycle_unit  = s.get("cycle_unit") or "year"
    cycle_value = s.get("cycle_value") or 1
    UNIT_MAP = {
        "year":      relativedelta(years=cycle_value),
        "month":     relativedelta(months=cycle_value),
        "half_year": relativedelta(months=6),
        "quarter":   relativedelta(months=3),
    }
    planned_date = anchor + UNIT_MAP.get(cycle_unit, relativedelta(years=1))

    # 중복 체크
    existing = supabase.table("work_schedules") \
        .select("id") \
        .eq("inspection_set_id", inspection_set_id) \
        .eq("planned_date", planned_date.isoformat()) \
        .execute()
    if existing.data:
        return {
            "success": True,
            "inspection_set_id": inspection_set_id,
            "created_count": 0,
            "message": "이미 동일한 일정이 존재합니다.",
            "planned_date": planned_date.isoformat()
        }

    # 상태 결정
    status = "OVERDUE" if planned_date < date.today() else "SCHEDULED"

    # work_schedule INSERT
    insert_data = {
        "factory_id":        s.get("factory_id"),
        "company_id":        s.get("company_id"),
        "inspection_set_id": inspection_set_id,
        "planned_date":      planned_date.isoformat(),
        "status_code":       status,
        "active_yn":         True,
        "description":       s.get("inspection_set_name") or "",
        "repeat_type":       cycle_unit,
        "repeat_interval":   cycle_value,
        "start_date":        anchor.isoformat(),
    }
    res = supabase.table("work_schedules").insert(insert_data).execute()
    created = res.data or []

    # inspection_sets next_planned_date 업데이트
    supabase.table("inspection_sets").update({
        "next_planned_date": planned_date.isoformat(),
        "status_code": status
    }).eq("id", inspection_set_id).execute()

    return {
        "success": True,
        "inspection_set_id": inspection_set_id,
        "created_count": len(created),
        "created_rows": created,
        "planned_date": planned_date.isoformat(),
        "status": status
    }
```

---

## BUG-4 🟡 anchor 없는 set에 generate-schedules 방어 없음

### 현상
`POST /inspection/generate-schedules/{factory_id}` 호출 시
`PENDING_ANCHOR`(anchor=NULL) 상태의 set도 처리되어
기준일 없이 생성된 일정의 날짜 신뢰 불가

### 수정 파일
`routers/inspection_checklist.py` — `generate_schedules()` 함수

### 수정 내용

```python
# inspection_sets 조회 시 anchor_confirmed=true인 것만 처리
sets = supabase.table("inspection_sets").select("*") \
    .eq("factory_id", factory_id) \
    .eq("is_active", True) \
    .eq("anchor_confirmed", True) \
    .not_.is_("schedule_anchor_date", "null") \
    .execute()

# 응답에 skip된 건수 포함
return {
    "status": "success",
    "message": f"{created}개 스케줄이 생성됐습니다.",
    "data": {
        "factory_id":      factory_id,
        "sets_processed":  len(sets.data or []),
        "sets_skipped":    total_sets - len(sets.data or []),  # PENDING_ANCHOR 건수
        "created":         created,
        "period":          f"{start} ~ {end}"
    }
}
```

---

## 전체 정상 흐름 (수정 후 목표)

```
[1] POST /legal-engine/diagnose/step1
    → factory_diagnosis_results 저장 ✅
    → diagnosis_rule_results 저장 ✅
    → response: diagnosis_id 포함 ✅

[2] POST /legal-engine/create-inspection-sets/{factory_id}
    → factory_diagnosis_results fallback 조회 ✅ (BUG-1 수정)
    → master_building_legal_rules JOIN으로 cycle 정보 포함 ✅
    → 중복 skip + 50건 배치 (타임아웃 방지) ✅ (BUG-2 수정)
    → inspection_sets 생성 (status=PENDING_ANCHOR)

[3] PATCH /inspection-sets/{id}/anchor  (tadmin 사용자 입력)
    → schedule_anchor_date 저장
    → next_planned_date 자동 계산
    → anchor_confirmed = true
    → status_code = ACTIVE/UPCOMING/OVERDUE

[4] POST /schedule-engine/generate/{inspection_set_id}
    → anchor 없으면 ANCHOR_NOT_SET 오류 반환 ✅ (BUG-3 수정)
    → anchor 있으면 work_schedules 1건 생성
    → 과거 날짜도 OVERDUE 상태로 생성 ✅
    → 중복 방지 ✅

[5] POST /inspection/generate-schedules/{factory_id}
    → anchor_confirmed=true인 것만 처리 ✅ (BUG-4 수정)
    → skip 건수 응답에 포함 ✅
```

---

## 완료 체크리스트

```
□ BUG-1: create-inspection-sets — factory_diagnosis_results fallback 추가
□ BUG-1: create-inspection-sets — master_building_legal_rules JOIN으로 cycle 정보 포함
□ BUG-2: create-inspection-sets — 중복 skip + 배치 처리 유지
□ BUG-3: schedule-engine/generate — anchor 없을 때 명확한 오류 반환
□ BUG-3: schedule-engine/generate — 과거 날짜도 OVERDUE로 생성
□ BUG-3: schedule-engine/generate — 중복 체크 추가
□ BUG-4: inspection/generate-schedules — anchor_confirmed=true 필터 추가
□ BUG-4: inspection/generate-schedules — skip 건수 응답 포함
□ Railway 배포 후 버전 확인 (GET https://api.taieng.co.kr/ → version)
□ 테스트: diagnose/step1 → create-inspection-sets 전체 흐름 재확인
```

---

## 참고 파일

```
routers/legal_engine.py          ← BUG-1, BUG-2 수정 대상
routers/schedule_engine.py       ← BUG-3 수정 대상
routers/inspection_checklist.py  ← BUG-4 수정 대상
db/supabase_client.py            ← get_supabase() 임포트
```
