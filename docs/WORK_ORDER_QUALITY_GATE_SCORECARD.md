# Cursor 작업지시서: law_rule_generator 품질 게이트 + 스코어카드 API

> 규칙: `docs/DEV_RULES_SERVICE_LAYER.md` 준수
> 브랜치: `dev` → PR → `main`
> 대상 파일: `routers/law_rule_generator.py` (52KB)
> 주의: 이 파일은 52KB — 전체 덮어쓰기 금지. 함수 단위로 수정.

---

## ⚠️ 배경 (왜 이 작업이 필요한가)

condition_code가 없는 룰이 master에 들어가면, 해당 섹터의 **모든 사업장**에 적용되어
false positive가 발생합니다. 실제로 923건의 저품질 데이터가 master에 유입되어 삭제하는
사고가 있었습니다. 이를 코드 레벨에서 방지합니다.

---

## 작업 1: master 등록 품질 게이트

### 수정 함수: `_auto_approve_to_master()`

**현재:**
```python
def _auto_approve_to_master(supabase, draft: dict) -> Optional[str]:
    rule_id = draft.get("draft_rule_id") or f"AI-{str(draft['id'])[:8].upper()}"
    # ... 바로 master INSERT
```

**변경:**
```python
def _auto_approve_to_master(supabase, draft: dict) -> Optional[str]:
    # 품질 게이트: condition_code 없으면 master 등록 거부
    if not draft.get("condition_code"):
        log.info(f"[QUALITY GATE] {draft.get('draft_rule_id')} — condition_code 없어 master 등록 스킵")
        return None
    
    rule_id = draft.get("draft_rule_id") or f"AI-{str(draft['id'])[:8].upper()}"
    # ... 기존 로직 유지
```

### 수정 함수: `bulk_approve_unregistered()` 엔드포인트

**변경:** for 루프 내 master INSERT 전에 동일한 품질 게이트 추가
```python
for d in drafts:
    # ... 기존 sector 체크 후
    
    # 품질 게이트 추가
    if not d.get("condition_code"):
        log.info(f"[QUALITY GATE] {d.get('draft_rule_id')} — condition_code 없어 스킵")
        skipped += 1
        continue
    
    # ... 기존 master INSERT 로직
```

---

## 작업 2: auto-parse 자동승인 범위 확대

### 수정 함수: `auto_parse_and_approve()` 엔드포인트

**현재:**
```python
if ob_type == "INSPECT" and conf >= threshold:
    approved_id = _auto_approve_to_master(supabase, draft)
```

**변경:**
```python
# INSPECT뿐 아니라 모든 의무 유형에서 condition_code + 고신뢰도면 자동승인
if conf >= threshold and draft.get("condition_code"):
    approved_id = _auto_approve_to_master(supabase, draft)
```

이제 `_auto_approve_to_master()`에 품질 게이트가 있으므로,
condition_code 없는 건은 어차피 거부됩니다. 이중 안전장치.

---

## 작업 3: 스코어카드 API 엔드포인트

### 추가 위치: `routers/law_rule_generator.py` 하단 (GET /stats 근처)

```python
@router.get("/scorecard")
async def get_scorecard():
    """법령엔진 전체 상태 스코어카드. DB 함수 legal_engine_scorecard() 호출."""
    supabase = get_supabase()
    res = supabase.rpc("legal_engine_scorecard").execute()
    rows = res.data or []
    
    # 등급별 카운트
    grades = {"pass": 0, "warn": 0, "fail": 0}
    for r in rows:
        g = r.get("grade", "")
        if "✅" in g: grades["pass"] += 1
        elif "🟡" in g: grades["warn"] += 1
        elif "🔴" in g: grades["fail"] += 1
    
    return {
        "status": "success",
        "data": {
            "items": rows,
            "summary": grades,
            "overall": "PASS" if grades["fail"] == 0 else "FAIL",
        }
    }
```

**참고:** DB 함수 `legal_engine_scorecard()`는 이미 생성되어 있습니다.
`SELECT * FROM legal_engine_scorecard()` 실행 가능.

supabase.rpc() 호출이 안 되면 아래 대안:
```python
res = supabase.postgrest.rpc("legal_engine_scorecard").execute()
# 또는
from db.supabase_client import get_supabase
supabase = get_supabase()
res = supabase.table("master_building_legal_rules").select("*", count="exact").eq("is_active", True).execute()
# ... 직접 계산
```

---

## 검증

```bash
# 1) 서버 실행
uvicorn main:app --reload

# 2) 스코어카드 API 테스트
curl -s http://localhost:8000/law-rule-generator/scorecard | python3 -m json.tool

# 3) 품질 게이트 테스트 — condition_code 없는 드래프트가 master에 안 들어가는지
# (기존 테스트 PASS 확인)
pytest tests/ -v

# 4) 서버 정상 확인
curl -s http://localhost:8000/health | python3 -m json.tool
```

---

## 절대 하지 말 것

- 52KB 파일 전체 덮어쓰기
- 기존 API 응답 형식 변경
- INTERNAL_SECRET 값 하드코딩
- condition_code 검증을 제거하거나 우회

---

## [TAI 개발 규칙]
문서: docs/DEV_RULES_SERVICE_LAYER.md
★ 기존 테스트 PASS 확인 후 push!
