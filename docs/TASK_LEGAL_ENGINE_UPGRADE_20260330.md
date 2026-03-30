# 법령 엔진 백엔드 고도화 작업 지시서 v4.3.3 → v4.4.0
## 담당: Cursor (백엔드 창)
## 파일: routers/legal_engine.py, routers/engine_legal.py

---

## 발견된 버그 및 개선 항목 (우선순위 순)

---

## BUG 1. sector 정규화 버그 — SPECIAL_FACILITY 진단 불가 [CRITICAL]

### 현상
`_normalize_sector_db()` 함수가 `SPECIAL_FACILITY → SPECIAL` 로 변환하는데,
DB의 `master_building_legal_rules.sector` 컬럼에는 `SPECIAL_FACILITY` 로 저장되어 있음.
따라서 `diagnose/step1` 호출 시 sector=SPECIAL_FACILITY 이면 룰 0개 반환.

### 수정
```python
# 수정 전
def _normalize_sector_db(sector: str) -> str:
    u = sector.strip().upper()
    if u == "SPECIAL_FACILITY":
        return "SPECIAL"
    return u

# 수정 후
def _normalize_sector_db(sector: str) -> str:
    u = sector.strip().upper()
    # DB에 SPECIAL_FACILITY로 저장되어 있으므로 변환하지 않음
    return u
```

### 검증
```bash
curl -s -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{"sector":"SPECIAL_FACILITY","facility_type":"의료기관","employee_count":50}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('룰수:', d['data']['applicable_count'])"
# 기대값: 0보다 큰 숫자 (현재 0이면 버그)
```

---

## BUG 2. diagnose/step1 rules_table에 form_code 미포함 [HIGH]

### 현상
`format_rule_result_db()` 함수가 `form_code`, `form_url` 필드를 반환하지 않음.
프론트의 diagnosis-step1.html에서 신고서식 연결 링크를 표시할 수 없음.

### 수정
`format_rule_result_db()` 함수에 form_code, form_url 추가:

```python
def format_rule_result_db(rule: Dict[str, Any]) -> Dict[str, Any]:
    desc = (rule.get("obligation_summary") or rule.get("remarks") or "").strip()
    return {
        "rule_id":               rule.get("rule_id", ""),
        "rule_type":             str(rule.get("rule_type_code") or ""),
        "law_name":              rule.get("law_name") or "",
        "law_article":           rule.get("law_article") or "",
        "description":           desc,
        "obligation_summary":    desc,                          # ← 추가 (alias)
        "appointment_target":    rule.get("appointment_target_code") or "",
        "qualification_required": rule.get("qualification_type") or "",
        "inspection_cycle":      "",
        "penalty_amount":        (rule.get("penalty_summary") or ""),
        "penalty_summary":       (rule.get("penalty_summary") or ""),  # ← 추가
        "source_label":          "",
        "obligation_type":       _resolve_obligation_type(rule),
        "appointment_required":  bool(rule.get("appointment_required")),
        "inspection_required":   bool(rule.get("inspection_required")),
        "action_required":       bool(rule.get("action_required")),
        "report_required":       bool(rule.get("report_required")),
        "notify_required":       bool(rule.get("notify_required")),
        "form_code":             rule.get("form_code") or "",   # ← 추가
        "form_url":              rule.get("form_url") or "",    # ← 추가
        "due_days":              rule.get("due_days"),           # ← 추가
        "sector":                rule.get("sector") or "",      # ← 추가
    }
```

---

## BUG 3. engine-legal/laws API에 rule_count 없음 [HIGH]

### 현상
`GET /engine-legal/laws` 응답 아이템에 `rule_count` 필드가 없음.
프론트 engine-legal.html의 품질 점수 계산에서 rule_count=0으로 처리되어 점수 -30점.

### 위치
`routers/engine_legal.py` — `get_laws()` 함수

### 수정
법령 목록 조회 시 `master_building_legal_rules` 에서 law_name 기준으로 rule_count JOIN:

```python
@router.get("/laws")
def get_laws(page: int = 1, page_size: int = 30, law_type_code: str = None, search: str = None):
    sb = get_supabase()
    
    # 1. 법령 목록 조회
    q = sb.table("law_master").select(
        "id, law_name, law_type_code, ministry_name, announcement_date, enforcement_date"
    ).eq("is_active", True)
    
    if law_type_code:
        q = q.eq("law_type_code", law_type_code)
    if search:
        q = q.ilike("law_name", f"%{search}%")
    
    total_res = q.execute()
    all_items = total_res.data or []
    total = len(all_items)
    
    # 2. 페이지네이션
    offset = (page - 1) * page_size
    paged = all_items[offset:offset + page_size]
    law_names = [item["law_name"] for item in paged]
    
    # 3. article_count, hang_count JOIN (law_version 경유)
    art_counts = {}
    hang_counts = {}
    for item in paged:
        law_id = item["id"]
        ver_res = sb.table("law_version").select("id").eq("law_id", law_id).eq("is_current", True).limit(1).execute()
        if ver_res.data:
            ver_id = ver_res.data[0]["id"]
            art_res = sb.table("law_article").select("id", count="exact").eq("law_version_id", ver_id).execute()
            art_counts[item["law_name"]] = art_res.count or 0
            hang_res = sb.table("law_paragraph").select("id", count="exact").eq("law_version_id", ver_id).execute()
            hang_counts[item["law_name"]] = hang_res.count or 0
    
    # 4. rule_count: master_building_legal_rules에서 law_name 기준 집계
    rule_counts = {}
    if law_names:
        rule_res = sb.table("master_building_legal_rules").select(
            "law_name"
        ).in_("law_name", law_names).eq("is_active", True).execute()
        for row in (rule_res.data or []):
            ln = row["law_name"]
            rule_counts[ln] = rule_counts.get(ln, 0) + 1
    
    # 5. 결과 조합
    items = []
    for item in paged:
        ln = item["law_name"]
        items.append({
            **item,
            "article_count": art_counts.get(ln, 0),
            "hang_count":    hang_counts.get(ln, 0),
            "rule_count":    rule_counts.get(ln, 0),
        })
    
    return {"status": "success", "data": {"items": items, "total": total, "page": page, "page_size": page_size}}
```

**주의:** 이 방식은 law_name 기준 join이라 느릴 수 있음. 아래 최적화 버전 사용 권장:

```python
# 최적화: SQL로 한 번에 집계
rule_count_sql = """
    SELECT law_name, COUNT(*) as cnt
    FROM master_building_legal_rules
    WHERE is_active = true AND law_name = ANY(%s)
    GROUP BY law_name
"""
# supabase에서는 rpc 또는 execute_sql로 처리
```

**대안 (간단):** engine_legal.py에서 기존 쿼리에 아래 서브쿼리 추가:

```sql
-- law_master 조회 후 rule_count를 별도 딕셔너리로 구성
SELECT law_name, COUNT(*) as rule_count
FROM master_building_legal_rules
WHERE is_active = true
GROUP BY law_name
```
→ Python dict로 만든 뒤 법령 목록 items에 merge

---

## FEAT 1. diagnose/step1 — summary에 form_code 연결 건수 포함 [MEDIUM]

### 내용
진단 결과 summary에 서식 연결된 룰 건수를 포함해서 프론트에서 "서식 다운로드" 버튼 표시 가능하게.

```python
# result_data["summary"]에 추가
"form_linked": sum(
    1 for r in applicable
    if r.get("form_code") and r["form_code"] != ""
),
```

---

## FEAT 2. diagnose/step1 — due_days 기반 긴급도 정보 포함 [MEDIUM]

### 내용
due_days가 있는 룰에 대해 마감 기한 계산해서 rules_table에 포함.

```python
from datetime import date, timedelta

def _calc_due_date(due_days: int) -> dict:
    if not due_days:
        return {}
    due_date = (date.today() + timedelta(days=due_days)).isoformat()
    urgency = "IMMEDIATE" if due_days <= 3 else ("URGENT" if due_days <= 14 else "NORMAL")
    return {"due_days": due_days, "due_date": due_date, "urgency": urgency}
```

`format_rule_result_db()`에서 due_days 있으면 due_info 포함:
```python
"due_info": _calc_due_date(rule.get("due_days")),
```

---

## FEAT 3. engine-legal/stats — total_rules DB 실시간 집계 [LOW]

### 현상
`GET /engine-legal/stats`의 `total_rules`가 하드코딩이거나 캐싱된 값일 수 있음.
현재 DB 실제 룰 수는 894개.

### 수정
`get_stats()` 함수에서 실시간 집계:

```python
total_rules_res = sb.table("master_building_legal_rules").select(
    "id", count="exact"
).eq("is_active", True).execute()
total_rules = total_rules_res.count or 0

# rules_by_sector 실시간 집계
for sector in ["BUILDING","MANUFACTURING","CONSTRUCTION","SPECIAL_FACILITY"]:
    res = sb.table("master_building_legal_rules").select(
        "id", count="exact"
    ).eq("is_active", True).eq("sector", sector).execute()
    rules_by_sector[sector] = res.count or 0
```

---

## 작업 순서

1. **BUG 1** — `_normalize_sector_db` 수정 (1분)
2. **BUG 2** — `format_rule_result_db` form_code 추가 (5분)
3. **BUG 3** — `get_laws` rule_count 추가 (15분)
4. **FEAT 1~2** — summary form_linked + due_info (10분)
5. **FEAT 3** — stats 실시간 집계 (5분)
6. 버전 업데이트: `ENGINE_VERSION = "4.4.0"`
7. git commit + push

## 커밋 메시지
```
feat: legal engine v4.4.0 — sector 버그수정 + form_code 응답 + rule_count + due_info
```

## 검증 체크리스트
```bash
# 1. SPECIAL_FACILITY 진단 (버그 수정 확인)
curl -s -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{"sector":"SPECIAL_FACILITY","facility_type":"의료기관","employee_count":50}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('SPECIAL_FACILITY 룰수:', d['data']['applicable_count'])"
# 기대: > 0

# 2. form_code 응답 확인
curl -s -X POST https://api.taieng.co.kr/legal-engine/diagnose/step1 \
  -H 'Content-Type: application/json' \
  -d '{"sector":"BUILDING","building_use_type":"업무시설","employee_count":100}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
rules=d['data']['rules_table']
form_rules=[r for r in rules if r.get('form_code')]
print('form_code 있는 룰:', len(form_rules))
if form_rules: print('샘플:', form_rules[0]['form_code'])
"
# 기대: > 0

# 3. rule_count 응답 확인
curl -s https://api.taieng.co.kr/engine-legal/laws?page=1\&page_size=3 \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
for item in d['data']['items']:
    print(item['law_name'], '| rule_count:', item.get('rule_count','없음'))
"
# 기대: rule_count 숫자 표시

# 4. 버전 확인
curl -s https://api.taieng.co.kr/ | python3 -c "import json,sys; print(json.load(sys.stdin).get('version'))"
# 기대: 4.4.0 포함 버전
```

완료 후 회의실 창에 결과 보고.
