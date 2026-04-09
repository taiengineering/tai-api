# 1순위 작업지시 프롬프트 — 산업섹터 파이프라인 연결

> 이 파일을 **백엔드 Claude 창**에 그대로 붙여넣으세요.

---

```
당신은 TAI Safe 백엔드 개발자입니다.

## 프로젝트 스택
- FastAPI / Python (tai-api)
- Railway 배포: api.taieng.co.kr
- Supabase / PostgreSQL (project: xntdkrjhgcscmqctdzyo)
- GitHub: taiengineering/tai-api
- Supabase MCP + GitHub MCP 사용 가능

---

## 오늘 작업: inspection_sets → work_schedules 자동생성 파이프라인 연결

### 현재 DB 상태 (문제 확인됨)
- inspection_sets 활성: 76개
- 기준일 있음: 58개
- 담당자 있음: 0개  ← 핵심 문제
- 법령엔진 발생 work_schedules: 0건 (전부 MANUAL)
- inspection_set_items: 67개 (세트당 체크항목)

### 파이프라인 목표
```
inspection_sets (4조건 충족)
  → work_schedules 자동 생성 (source_type='LAW_ENGINE')
    → work_assignments 배정 (assigned_user_id)
      → notifications D-3 알림 발송
```

---

## 4가지 조건 정의

스케줄 생성 가능 조건 (모두 충족해야 함):
1. `schedule_anchor_date IS NOT NULL` (언제 — 기준일)
2. `cycle_unit IS NOT NULL` (언제 — 주기)
3. `assignee_user_id IS NOT NULL` (누가 — 담당자)
4. `obligation_summary IS NOT NULL` (무엇을 — 의무내용)
   AND (행정의무이거나 inspection_set_items 1개 이상 존재)

행정의무 obligation_type (체크항목 불필요):
`REPORT`, `DOCUMENT`, `NOTIFY`, `APPOINT`, `ACTION`

---

## 구현할 API 엔드포인트

### 1. inspection_sets → work_schedules 생성

**파일**: `routers/inspection_sets.py` (기존 파일에 엔드포인트 추가)

```
POST /inspection-sets/generate-schedules/{factory_id}
```

**로직:**
```python
# 1. 해당 factory_id의 4조건 충족 inspection_sets 조회
sets = supabase.table("inspection_sets")
    .select("*, inspection_set_items(count)")
    .eq("factory_id", factory_id)
    .eq("is_active", True)
    .not_.is_("schedule_anchor_date", "null")
    .not_.is_("cycle_unit", "null")
    .not_.is_("assignee_user_id", "null")
    .not_.is_("obligation_summary", "null")
    .execute()

ADMIN_OBL = {'REPORT','DOCUMENT','NOTIFY','APPOINT','ACTION'}

created = 0
skipped = 0

for iset in sets:
    obl = iset['obligation_type'] or 'OTHER'
    is_admin = obl in ADMIN_OBL
    item_count = iset.get('inspection_set_items', [{}])[0].get('count', 0)
    
    # 실물점검인데 체크항목 없으면 SKIP
    if not is_admin and item_count == 0:
        skipped += 1
        continue
    
    # 이미 이 inspection_set_id로 PENDING 스케줄 존재 시 SKIP
    existing = supabase.table("work_schedules")
        .select("id", count="exact")
        .eq("inspection_set_id", iset['id'])
        .eq("status_code", "PENDING")
        .eq("source_type", "LAW_ENGINE")
        .execute()
    if existing.count and existing.count > 0:
        skipped += 1
        continue
    
    # 주기 기반 planned_date 계산
    anchor = date.fromisoformat(str(iset['schedule_anchor_date'])[:10])
    planned = calc_next_date(anchor, iset['cycle_unit'], iset['cycle_value'] or 1)
    
    # work_schedules INSERT
    supabase.table("work_schedules").insert({
        "factory_id":        factory_id,
        "company_id":        iset.get('company_id'),
        "inspection_set_id": iset['id'],
        "assigned_user_id":  iset['assignee_user_id'],
        "source_type":       "LAW_ENGINE",
        "obligation_type":   obl,
        "law_name":          iset.get('law_name', ''),
        "law_article":       iset.get('law_article', ''),
        "description":       iset.get('obligation_summary', ''),
        "cycle_base_guide":  iset.get('cycle_base_guide', ''),
        "planned_date":      planned.isoformat(),
        "status_code":       "PENDING",
        "active_yn":         True,
        "rule_code":         iset.get('legal_rule_code', ''),
    }).execute()
    created += 1

return {
    "status": "success",
    "data": {"created": created, "skipped": skipped, "total": len(sets)}
}
```

**calc_next_date 헬퍼:**
```python
from datetime import date
from dateutil.relativedelta import relativedelta

def calc_next_date(anchor: date, cycle_unit: str, cycle_value: int) -> date:
    u = (cycle_unit or '').lower()
    v = max(int(cycle_value or 1), 1)
    if u == 'day':        return anchor + timedelta(days=v)
    if u == 'week':       return anchor + timedelta(weeks=v)
    if u == 'month':      return anchor + relativedelta(months=v)
    if u == 'quarter':    return anchor + relativedelta(months=3)
    if u == 'half_year':  return anchor + relativedelta(months=6)
    if u == 'year':       return anchor + relativedelta(years=v)
    return anchor + relativedelta(years=1)  # 기본 1년
```

**응답 구조:**
```json
{
  "status": "success",
  "data": {
    "created": 34,
    "skipped": 24,
    "total": 58
  }
}
```

---

### 2. 전체 공장 일괄 생성

```
POST /inspection-sets/generate-schedules-all
```

로직: factories 전체 순회 → 위 함수 호출

```json
{
  "status": "success",
  "data": {
    "factories_processed": 3,
    "total_created": 67,
    "total_skipped": 42
  }
}
```

---

### 3. D-3 알림 발송 수정

**파일**: `routers/schedule_pipeline.py` 기존 `/notifications/trigger-due-alerts` 수정

현재 문제: work_schedules에 LAW_ENGINE 일정이 0건이라 알림이 0건

수정사항:
- `source_type` 필터 제거 (MANUAL + LAW_ENGINE 모두 대상)
- `assigned_user_id` 있는 일정만 대상
- FCM push_token 있으면 FCM도 같이 발송

```python
# 수정 후 쿼리
sched_res = (
    supabase.table("work_schedules")
    .select("id, factory_id, company_id, assigned_user_id, description, obligation_type, law_name")
    .eq("planned_date", target_date.isoformat())
    .eq("status_code", "PENDING")
    .eq("active_yn", True)
    .not_.is_("assigned_user_id", "null")  # 담당자 있는 것만
    .execute()
)
```

---

## 구현 순서

```
1. inspection_sets.py — POST /inspection-sets/generate-schedules/{factory_id}
2. inspection_sets.py — POST /inspection-sets/generate-schedules-all
3. schedule_pipeline.py — trigger-due-alerts 수정 (담당자 필터 추가)
4. main.py 버전 업 (v5.7.5 → v5.7.6)
5. Railway 배포 확인
6. Supabase에서 결과 확인:
   SELECT count(*), source_type FROM work_schedules
   WHERE source_type = 'LAW_ENGINE' GROUP BY source_type;
```

---

## 주의사항

- `NOT EXISTS` 패턴으로 중복 생성 방지 필수
- `cycle_unit` 값: 'day', 'week', 'month', 'quarter', 'half_year', 'year'
- `dateutil.relativedelta` 패키지 사용 (requirements.txt 확인)
- FastAPI route ordering: 구체 경로를 파라미터 경로보다 먼저 선언
  - `/generate-schedules-all` 을 `/{id}` 보다 앞에
- 완료 후 GitHub push (taiengineering/tai-api, main 브랜치)
- 완료 후 다음 SQL로 결과 검증:
```sql
SELECT source_type, count(*) 
FROM work_schedules 
GROUP BY source_type;
```
```
