# TAI Cursor 작업지시서 — 법정점검 반복주기 생성 버그 수정

> 우선순위: 🔴 긴급  
> 작성일: 2026-03-31  
> 레포: taiengineering/tai-api  
> 대상 파일: `routers/legal_engine.py`, `routers/schedule_engine.py`, `routers/inspection_checklist.py`

---

## 배경 (테스트 결과 요약)

실제 API 흐름을 테스트한 결과 아래 4가지 버그가 확인됨:

```
[정상] diagnose/step1 → factory_diagnosis_results 저장 ✅
[정상] inspection/generate-schedules/{factory_id} → 152개 생성 ✅

[버그1] diagnose/step1 완료 → create-inspection-sets 호출 → "법령판정 결과가 없습니다." ❌
[버그2] create-inspection-sets 158건 insert → Failed to fetch (Railway 타임아웃) ❌
[버그3] schedule-engine/generate/{iset_id} → created_count: 0 (미작동) ❌
[버그5] anchor=NULL인 inspection_set에서 generate-schedules 실행 → 날짜 신뢰 불가 ❌
```

---

## 버그 1 수정 — create-inspection-sets가 factory_diagnosis_results도 읽도록

### 파일: `routers/legal_engine.py`
### 함수: `create_inspection_sets_from_legal(factory_id)`

현재 코드:
```python
result_json = fac.data.get("legal_result_json")  # apply API 결과만 체크
if not result_json:
    raise HTTPException(status_code=400, detail="법령판정 결과가 없습니다.")
inspection_rules = result_json.get("inspection_required", [])
```

수정 코드:
```python
result_json = fac.data.get("legal_result_json")
inspection_rules = []

# 1) 기존 경로: factories.legal_result_json (apply API)
if result_json:
    inspection_rules = result_json.get("inspection_required", [])

# 2) 신규 경로 fallback: factory_diagnosis_results (diagnose/step1 API)
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
            # result_data 안의 inspection_required 추출
            inspection_rules = result_data.get("inspection_required", [])
            # 또는 rules 리스트에서 INSPECT 타입만 필터
            if not inspection_rules:
                all_rules = result_data.get("rules", [])
                inspection_rules = [
                    r for r in all_rules
                    if r.get("rule_type") in ("INSPECT", "inspection", "002")
                    or "inspection" in str(r.get("obligation", "")).lower()
                ]
    except Exception as e:
        print(f"[CREATE_ISET] factory_diagnosis_results 조회 실패: {e}")

if not inspection_rules:
    # diagnose/step1 결과에서 직접 적용 규칙 조회
    try:
        rule_res = supabase.table("diagnosis_rule_results") \
            .select("rule_code, rule_name, law_name, law_article, form_code") \
            .eq("diagnosis_id",
                supabase.table("factory_diagnosis_results")
                    .select("id")
                    .eq("factory_id", factory_id)
                    .eq("is_latest", True)
                    .limit(1).execute().data[0]["id"]
            ).execute()
        # diagnosis_rule_results 행을 inspection_rules 형식으로 변환
        inspection_rules = [
            {
                "rule_id": r.get("rule_code"),
                "law_name": r.get("law_name"),
                "law_article": r.get("law_article"),
                "description": r.get("rule_name"),
                "inspection_cycle": "",  # master_rules에서 JOIN으로 보완
            }
            for r in (rule_res.data or [])
        ]
    except Exception as e:
        print(f"[CREATE_ISET] diagnosis_rule_results 조회 실패: {e}")

if not inspection_rules:
    return {"status": "success", "message": "생성할 점검 항목이 없습니다.", "data": {"created": 0}}
```

---

## 버그 2 수정 — create-inspection-sets 타임아웃 방어

### 파일: `routers/legal_engine.py`
### 함수: `create_inspection_sets_from_legal(factory_id)`

**현재 문제:** 158건 일괄 insert → Railway 30초 타임아웃  
**원인:** inspection_rules 158건을 50건씩 나눠도 DB insert + cycle 파싱 + 중복 삭제가 너무 오래 걸림

**수정 내용:**

### 2-1. 중복 삭제 쿼리 최적화
```python
# 기존: 전체 삭제 후 재삽입 (느림)
supabase.table("inspection_sets").delete() \
    .eq("factory_id", factory_id) \
    .eq("source", "LEGAL_ENGINE").execute()

# 수정: 기존 rule_id 목록 가져와서 upsert 방식으로 변경
# (삭제 없이 on_conflict로 처리)
```

### 2-2. cycle 파싱을 master_rules 코드 기반으로 교체

현재 코드는 `cycle_label` 문자열을 텍스트 파싱해서 변환:
```python
# 기존 (텍스트 파싱 — 느리고 불안정)
if "월 1회" in cycle_label: cycle_unit, cycle_value = "month", 1
elif "반기" in cycle_label: cycle_unit, cycle_value = "month", 6
...
```

수정: `master_building_legal_rules`에서 직접 cycle 정보 JOIN:
```python
# inspection_rules에서 rule_id 목록 추출
rule_ids = [r.get("rule_id") for r in inspection_rules if r.get("rule_id")]

# master_rules에서 cycle 정보 일괄 조회
master_res = supabase.table("master_building_legal_rules") \
    .select("rule_id, inspection_cycle_value, inspection_cycle_unit_code, "
            "cycle_unit_std, cycle_base_type, cycle_base_guide") \
    .in_("rule_id", rule_ids).execute()

# dict로 변환 (rule_id → cycle 정보)
master_map = {r["rule_id"]: r for r in (master_res.data or [])}

# 단위 코드 → 표준 영문 변환 테이블
UNIT_CODE_TO_STD = {
    "003": ("month",     1),
    "004": ("quarter",   1),
    "005": ("half_year", 1),
    "006": ("year",      1),
    "007": ("year",      2),  # value는 inspection_cycle_value 우선
    "008": ("year",      5),
    "009": ("year",      4),
    "010": ("year",      3),
    "011": ("year",      3),
    "012": ("year",     10),
}
```

### 2-3. insert_rows 구성 시 master_map에서 cycle 가져오기
```python
for rule in inspection_rules:
    rule_id   = rule.get("rule_id", "")
    law_name  = rule.get("law_name", "")
    master    = master_map.get(rule_id, {})

    unit_code  = master.get("inspection_cycle_unit_code") or "006"
    cycle_unit, default_value = UNIT_CODE_TO_STD.get(unit_code, ("year", 1))
    cycle_value = int(master.get("inspection_cycle_value") or default_value)

    # cycle_unit_std가 있으면 우선
    if master.get("cycle_unit_std"):
        cycle_unit = master["cycle_unit_std"]

    insert_rows.append({
        "company_id":           company_id,
        "factory_id":           factory_id,
        "inspection_set_name":  f"{law_name} 점검",
        "inspection_set_code":  rule_id,
        "legal_rule_id":        rule_id,
        "law_name":             law_name,
        "law_article":          rule.get("law_article", ""),
        "cycle_unit":           cycle_unit,
        "cycle_value":          cycle_value,
        "cycle_base_type":      master.get("cycle_base_type") or "LAST_INSPECTION",
        "cycle_base_guide":     master.get("cycle_base_guide") or "",
        "description":          rule.get("description", ""),
        "source":               "LEGAL_ENGINE",
        "is_active":            True,
        "status_code":          "PENDING_ANCHOR",
        "anchor_confirmed":     False,
    })
```

---

## 버그 3 수정 — schedule-engine/generate 단건 미작동

### 파일: `routers/schedule_engine.py`
### 엔드포인트: `POST /schedule-engine/generate/{inspection_set_id}`

**현재 문제:** anchor 있어도 `created_count: 0` 반환

현재 코드를 확인해서 아래 로직이 없으면 추가:

```python
@router.post("/generate/{inspection_set_id}")
async def generate_schedule(inspection_set_id: str):
    supabase = get_supabase()

    # inspection_set 조회
    iset_res = supabase.table("inspection_sets") \
        .select("*").eq("id", inspection_set_id).single().execute()
    if not iset_res.data:
        raise HTTPException(status_code=404, detail="점검 세트 없음")

    iset = iset_res.data

    # [버그 원인] anchor_confirmed 체크가 없거나 잘못되어 있을 경우
    # anchor 없어도 next_planned_date 있으면 생성 가능하도록 수정
    anchor = iset.get("schedule_anchor_date")
    next_date = iset.get("next_planned_date")

    if not next_date and not anchor:
        return {"success": False, "reason": "기준일(anchor) 미설정",
                "inspection_set_id": inspection_set_id, "created_count": 0}

    # next_planned_date 없으면 anchor + cycle로 계산
    if not next_date and anchor:
        from dateutil.relativedelta import relativedelta
        from datetime import date
        a = date.fromisoformat(anchor)
        cv = iset.get("cycle_value") or 1
        cu = iset.get("cycle_unit") or "year"
        DELTA = {
            "year":      relativedelta(years=cv),
            "month":     relativedelta(months=cv),
            "half_year": relativedelta(months=6),
            "quarter":   relativedelta(months=3),
        }
        next_date = (a + DELTA.get(cu, relativedelta(years=1))).isoformat()

    # work_schedules 중복 방지: 같은 inspection_set_id + planned_date 있으면 skip
    existing = supabase.table("work_schedules") \
        .select("id").eq("inspection_set_id", inspection_set_id) \
        .eq("planned_date", next_date).execute()
    if existing.data:
        return {"success": True, "reason": "이미 생성된 일정",
                "inspection_set_id": inspection_set_id, "created_count": 0,
                "existing_id": existing.data[0]["id"]}

    # work_schedules insert
    insert_data = {
        "factory_id":         iset.get("factory_id"),
        "company_id":         iset.get("company_id"),
        "inspection_set_id":  inspection_set_id,
        "planned_date":       next_date,
        "start_date":         next_date,
        "repeat_type":        iset.get("cycle_unit") or "year",
        "repeat_interval":    iset.get("cycle_value") or 1,
        "status_code":        "SCHEDULED",
        "active_yn":          True,
        "description":        f"{iset.get('inspection_set_name','점검')} — 법정점검 일정",
    }
    result = supabase.table("work_schedules").insert(insert_data).execute()
    created = len(result.data or [])

    return {
        "success":            True,
        "inspection_set_id": inspection_set_id,
        "created_count":     created,
        "created_rows":      result.data or [],
    }
```

---

## 버그 5 수정 — anchor NULL인 set에서 generate-schedules 방어

### 파일: `routers/inspection_checklist.py` (또는 generate-schedules가 있는 파일)
### 엔드포인트: `POST /inspection/generate-schedules/{factory_id}`

현재 anchor=NULL 상태에서도 152개 생성됨 → 날짜 신뢰 불가

**수정 내용:**

```python
# generate-schedules 내부 inspection_sets 처리 루프에 방어 로직 추가
for iset in inspection_sets:
    # [수정] anchor_confirmed=False이면 일정 생성 건너뜀
    if not iset.get("anchor_confirmed") or not iset.get("schedule_anchor_date"):
        skipped_anchor += 1
        continue

    # next_planned_date 없으면 계산
    next_date = iset.get("next_planned_date")
    if not next_date:
        # anchor + cycle 계산 (버그3 수정과 동일 로직)
        ...

    # 이하 기존 로직 유지
```

**응답에 skipped_anchor 건수 추가:**
```python
return {
    "status":  "success",
    "message": f"{created}개 스케줄이 생성됐습니다.",
    "data": {
        "factory_id":      factory_id,
        "sets_processed":  sets_processed,
        "created":         created,
        "skipped_anchor":  skipped_anchor,   # 추가: 기준일 미설정으로 건너뜀
        "period":          f"{start_date} ~ {end_date}",
    }
}
```

---

## 수정 우선순위

| 순서 | 버그 | 파일 | 중요도 |
|------|------|------|--------|
| 1 | 버그1: create-inspection-sets fallback | legal_engine.py | 🔴 |
| 2 | 버그2: create-inspection-sets cycle 파싱 교체 | legal_engine.py | 🔴 |
| 3 | 버그3: schedule-engine/generate 단건 수정 | schedule_engine.py | 🟡 |
| 4 | 버그5: generate-schedules anchor 방어 | inspection_checklist.py | 🟡 |

---

## 완료 체크리스트

```
□ create-inspection-sets: factory_diagnosis_results fallback 추가
□ create-inspection-sets: diagnosis_rule_results에서도 조회 가능
□ create-inspection-sets: cycle 파싱을 master_rules JOIN으로 교체
□ create-inspection-sets: status_code='PENDING_ANCHOR', anchor_confirmed=False 기본값 설정
□ schedule-engine/generate: anchor 기반 work_schedules 단건 생성 정상 작동
□ schedule-engine/generate: 중복 방지 로직 추가
□ inspection/generate-schedules: anchor_confirmed=False인 set 건너뜀
□ inspection/generate-schedules: 응답에 skipped_anchor 건수 포함
□ Railway 배포 후 버전 확인
```

---

## 검증 방법 (배포 후)

```bash
# 1. diagnose/step1 → create-inspection-sets 연결 테스트
curl -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{"sector":"BUILDING","factory_id":"9ec1ac44-3a80-486c-9aff-eebcc74d9ee3",
       "input":{"worker_count":85,"total_floor_area":3000,"electric_capacity":500}}'
# → diagnosis_id 확인

curl -X POST https://api.taieng.co.kr/legal-engine/create-inspection-sets/9ec1ac44-3a80-486c-9aff-eebcc74d9ee3
# → created > 0 확인, 타임아웃 없음 확인

# 2. anchor 설정 후 단건 generate 테스트
curl -X PATCH https://api.taieng.co.kr/inspection-sets/{id}/anchor \
  -d '{"schedule_anchor_date":"2025-03-31"}'

curl -X POST https://api.taieng.co.kr/schedule-engine/generate/{id}
# → created_count > 0 확인

# 3. generate-schedules skipped_anchor 확인
curl -X POST https://api.taieng.co.kr/inspection/generate-schedules/9ec1ac44-...
# → skipped_anchor 포함 응답 확인
```
