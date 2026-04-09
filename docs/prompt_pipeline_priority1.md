# Pipeline Priority 1 — 백엔드 Claude 창 시작 프롬프트

> **사용법:** 이 파일 전체를 백엔드 Claude 창에 붙여넣어 시작

---

```
당신은 TAI Safe 백엔드 개발자입니다.

## 프로젝트 스택
- FastAPI / Python (tai-api)
- Railway 배포: api.taieng.co.kr
- Supabase / PostgreSQL (project: xntdkrjhgcscmqctdzyo)
- GitHub: taiengineering/tai-api (github-tai MCP)
- 브라우저 테스트 금지 (Claude in Chrome 사용 금지)
- 모든 테스트: Supabase MCP 또는 터미널 Python 파일

## 오늘 작업: inspection_sets → work_schedules 파이프라인

### ★ 완료 기준
```sql
SELECT source_type, count(*)
FROM work_schedules
GROUP BY source_type;
-- LAW_ENGINE 행이 생겨야 성공
```

---

## DB 현황 (2026-04-09 기준)

**inspection_sets 76건:**
| 조건 | 충족 건수 |
|------|-----------|
| schedule_anchor_date (기준일) | 58건 |
| cycle_unit (주기) | 76건 |
| assignee_user_id (담당자) | **0건** ← 모두 null |
| description (의무내용) | 71건 |

**work_schedules source_type:**
- MANUAL, LEGAL 등 존재 / LAW_ENGINE 없음 → 생성 목표

---

## 작업 1: POST /inspection-sets/generate-schedules/{factory_id}

**파일:** `routers/inspection_sets.py` (v1.8.0 → v1.9.0으로 버전업)

### 4조건 체크 로직
```python
# 4조건:
# 1. schedule_anchor_date IS NOT NULL
# 2. cycle_unit IS NOT NULL
# 3. assignee_user_id IS NOT NULL   ← 현재 0건이므로 스킵되더라도 정상
# 4. (description IS NOT NULL AND description != '') OR legal_rule_code IS NOT NULL

def _meets_4_conditions(iset: dict) -> bool:
    has_anchor   = bool(iset.get("schedule_anchor_date"))
    has_cycle    = bool(iset.get("cycle_unit"))
    has_assignee = bool(iset.get("assignee_user_id"))
    has_content  = bool((iset.get("description") or "").strip()) or bool(iset.get("legal_rule_code"))
    return has_anchor and has_cycle and has_assignee and has_content
```

> **중요:** 담당자(assignee_user_id)가 현재 0건이라 4조건 충족 시 생성, 0건이면 0건 생성이 정상.
> 완료 기준은 "4조건 충족 시 LAW_ENGINE 스케줄 생성"이지 "무조건 생성"이 아님.
> 테스트 시 inspection_sets 1건에 assignee_user_id를 임시 설정 후 확인.

### calc_next_date 헬퍼
기존 `_next_planned_from(base, cycle_unit, cycle_value)` 함수 재사용 (이미 inspection_sets.py에 존재).

### source_type = 'LAW_ENGINE' (기존 'LEGAL'과 다름!)

### 응답 구조
```json
{
  "status": "success",
  "data": {
    "factory_id": "uuid",
    "created": 5,
    "skipped": 53,
    "skipped_no_condition": 18,
    "total_sets": 76
  }
}
```

### NOT EXISTS 중복 방지
```python
# 이미 동일 inspection_set_id + source_type='LAW_ENGINE' + status='PENDING' 존재 시 스킵
existing = supabase.table("work_schedules").select("inspection_set_id") \
    .eq("factory_id", factory_id) \
    .eq("source_type", "LAW_ENGINE") \
    .eq("status_code", "PENDING") \
    .execute()
existing_set_ids = {r["inspection_set_id"] for r in (existing.data or []) if r.get("inspection_set_id")}
```

### 생성할 work_schedules 행
```python
{
    "factory_id":        iset["factory_id"],
    "company_id":        iset.get("company_id"),
    "inspection_set_id": iset["id"],
    "assigned_user_id":  iset["assignee_user_id"],  # inspection_sets에서 가져옴
    "source_type":       "LAW_ENGINE",               # ★ 핵심
    "description":       iset.get("description") or iset.get("law_name") or "",
    "obligation_type":   iset.get("inspection_category") or "INSPECT",
    "law_name":          iset.get("law_name") or "",
    "law_article":       iset.get("law_article") or "",
    "planned_date":      calc_next_date(...).isoformat(),
    "status_code":       "PENDING",
    "active_yn":         True,
    "rule_code":         iset.get("legal_rule_code") or iset.get("legal_rule_id") or "",
}
```

---

## 작업 2: POST /inspection-sets/generate-schedules-all

**파일:** `routers/inspection_sets.py`

```
전체 공장(factories 테이블) 일괄 실행
→ 각 factory_id에 대해 작업1 로직 실행
→ 결과 집계 반환
```

### 응답 구조
```json
{
  "status": "success",
  "data": {
    "total_factories": 10,
    "processed": 8,
    "total_created": 12,
    "total_skipped": 244,
    "results": [
      {"factory_id": "uuid", "created": 3, "skipped": 21},
      ...
    ]
  }
}
```

---

## 작업 3: schedule_pipeline.py 수정

**파일:** `routers/schedule_pipeline.py` (v1.0.0 → v1.1.0으로 버전업)

### trigger-due-alerts에 assigned_user_id NULL 필터 추가

**현재 코드 (수정 전):**
```python
sched_res = (
    supabase.table("work_schedules")
    .select("id, factory_id, company_id, assigned_user_id, description, ...")
    .eq("planned_date", target_date.isoformat())
    .eq("status_code", "PENDING")
    .eq("active_yn", True)
    .execute()
)
schedules = sched_res.data or []
```

**수정 후:**
```python
sched_res = (
    supabase.table("work_schedules")
    .select("id, factory_id, company_id, assigned_user_id, description, ...")
    .eq("planned_date", target_date.isoformat())
    .eq("status_code", "PENDING")
    .eq("active_yn", True)
    .not_.is_("assigned_user_id", "null")  # ★ 담당자 없는 일정 알림 발송 안 함
    .execute()
)
schedules = sched_res.data or []
```

---

## 구현 순서

1. inspection_sets.py에 `generate-schedules/{factory_id}` 엔드포인트 추가
2. inspection_sets.py에 `generate-schedules-all` 엔드포인트 추가
3. schedule_pipeline.py trigger_due_alerts 수정
4. GitHub push → Railway 재배포 대기 (~2분)
5. 완료 기준 SQL 실행으로 검증

## 완료 검증 SQL
```sql
-- 1. LAW_ENGINE 스케줄 생성 확인
SELECT source_type, COUNT(*) FROM work_schedules GROUP BY source_type;

-- 2. 4조건 충족 inspection_sets 확인 (assignee_user_id 임시 설정 후)
SELECT COUNT(*) FROM inspection_sets
WHERE schedule_anchor_date IS NOT NULL
  AND cycle_unit IS NOT NULL
  AND assignee_user_id IS NOT NULL
  AND (description IS NOT NULL OR legal_rule_code IS NOT NULL)
  AND is_active = true;
```

## 코드 규칙
1. FastAPI 경로: 구체 경로(`/generate-schedules-all`)를 파라미터 경로(`/{id}`) 앞에 선언
2. 다중 파일 커밋: github-tai:push_files 사용
3. 단일 파일 수정: github-tai:create_or_update_file (SHA 먼저 조회 필수)
4. 커밋 후 Railway 자동 배포 확인
```
