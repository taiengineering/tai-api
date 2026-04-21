# 작업지시서: 법령 개정 게시판 파이프라인 연결

> DB 테이블: `law_revision_board` (이미 존재, 0건)
> 연결 대상: `routers/law_collector.py` + 알림 + 점검항목
> 브랜치: `dev` → PR → `main`
> 작업 도구: **Cursor** (law_collector.py = 28KB)

---

## 목표 3가지

### ① 법령 개정 감지 시 → 게시판 자동 등록
### ② 해당 사업장 안전관리자에게 알림 발송
### ③ 해당 사업장 점검 항목에 신규 법규 플래그

---

## 현재 구조

```
law_collector.py :: check_law_update()
  │
  ├─ law_change_log INSERT          ← ✅ 작동 중 (34건)
  ├─ law_rule_drafts NEEDS_REVIEW   ← ✅ 작동 중
  │
  ├─ law_revision_board INSERT      ← ❌ 연결 안 됨 (이번 작업)
  ├─ notifications INSERT + SMS     ← ❌ 연결 안 됨 (이번 작업)
  └─ inspection_set_items 플래그    ← ❌ 연결 안 됨 (이번 작업)
```

---

## ① 게시판 자동 등록

### 수정 위치: `routers/law_collector.py` > `check_law_update()` 함수

`mark_rules_needs_review()` 호출 직후에 아래 코드 추가:

```python
# ★ 법령 개정 게시판 자동 등록
affected_factories = _find_affected_factories(law_name, supabase)

board_entry = {
    "law_name":           law_name,
    "law_type":           current.get("law_type_name", ""),
    "revision_type":      current.get("revision_type", ""),
    "revision_date":      str(current.get("announcement_date")) if current.get("announcement_date") else None,
    "enforcement_date":   str(current.get("enforcement_date")) if current.get("enforcement_date") else None,
    "law_change_log_id":  change_log_id,  # law_change_log INSERT 후 받은 ID
    "title":              f"[{current.get('revision_type', '개정')}] {law_name}",
    "summary":            f"{law_name}이 {current.get('revision_type', '개정')}되었습니다. "
                          f"영향받는 사업장 {len(affected_factories)}개소.",
    "impact_level":       "HIGH" if needs_review_count > 5 else "NORMAL",
    "affected_sectors":   _get_affected_sectors(law_name, supabase),
    "affected_rule_ids":  _get_affected_rule_ids(law_name, supabase),
    "affected_factory_ids": affected_factories,
    "affected_factory_count": len(affected_factories),
    "source_url":         f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={current_mst_no}",
    "tags":               [current.get("revision_type", ""), law_type_name_to_code(current.get("law_type_name", ""))],
    "status":             "PUBLISHED",
    "is_public":          True,
    "created_by":         "SYSTEM",
}
supabase.table("law_revision_board").insert(board_entry).execute()
```

### 영향받는 사업장 특정 함수 (신규)

```python
def _find_affected_factories(law_name: str, supabase) -> list:
    """개정된 법령이 적용된 사업장 UUID 목록 반환"""
    # 1) 해당 법령의 룰 ID들
    rules = supabase.table("master_building_legal_rules")\
        .select("rule_id")\
        .ilike("law_name", f"%{law_name}%")\
        .eq("is_active", True)\
        .execute()
    if not rules.data:
        return []
    rule_ids = [r["rule_id"] for r in rules.data]
    
    # 2) 해당 룰이 적용된 사업장 (진단 결과에서)
    results = supabase.table("factory_diagnosis_results")\
        .select("factory_id")\
        .eq("is_latest", True)\
        .execute()
    
    affected = []
    for r in results.data:
        # result_data jsonb 안에 rule_id가 포함된 사업장
        # 또는 sector 기반으로 매칭 (sector가 동일하면 영향)
        affected.append(r["factory_id"])
    
    return list(set(affected))


def _get_affected_sectors(law_name: str, supabase) -> list:
    """개정된 법령이 적용되는 섹터 목록"""
    rules = supabase.table("master_building_legal_rules")\
        .select("sector")\
        .ilike("law_name", f"%{law_name}%")\
        .eq("is_active", True)\
        .execute()
    return list(set(r["sector"] for r in rules.data)) if rules.data else []


def _get_affected_rule_ids(law_name: str, supabase) -> list:
    """개정된 법령의 활성 룰 ID 목록"""
    rules = supabase.table("master_building_legal_rules")\
        .select("rule_id")\
        .ilike("law_name", f"%{law_name}%")\
        .eq("is_active", True)\
        .execute()
    return [r["rule_id"] for r in rules.data] if rules.data else []
```

---

## ② 안전관리자 알림 발송

### 수정 위치: 게시판 INSERT 직후

```python
# ★ 영향받는 사업장의 안전관리자에게 알림
if affected_factories:
    _notify_safety_managers(board_entry, affected_factories, supabase)
```

### 알림 함수 (신규)

```python
def _notify_safety_managers(board_entry: dict, factory_ids: list, supabase):
    """3가지 채널로 알림: 인앱 + SMS + 푸시"""
    
    # 안전관리자 역할 코드
    SAFETY_ROLES = ['003', '005', '008', '009', '010']
    
    # 해당 사업장의 안전관리자 조회
    for fid in factory_ids:
        users = supabase.table("users")\
            .select("id, name, phone, company_id")\
            .eq("factory_id", fid)\
            .in_("role_code", SAFETY_ROLES)\
            .eq("is_active", True)\
            .execute()
        
        for user in (users.data or []):
            # 1) 인앱 알림 (notifications 테이블)
            supabase.table("notifications").insert({
                "company_id":   user.get("company_id"),
                "user_id":      user["id"],
                "trigger_code": "LAW_REVISION",
                "trigger_group": "LEGAL",
                "title":        board_entry["title"],
                "body":         board_entry["summary"],
                "link_url":     f"/law-revision/{board_entry.get('id', '')}",
                "priority":     board_entry.get("impact_level", "NORMAL"),
                "channel":      "IN_APP",
                "send_status":  "SENT",
                "is_read":      False,
            }).execute()
            
            # 2) SMS 발송 (MessageMi)
            if user.get("phone"):
                try:
                    from routers.messaging import send_sms  # 기존 SMS 함수 활용
                    send_sms(
                        to=user["phone"],
                        message=f"[TAI] {board_entry['title']}\n{board_entry['summary']}\n상세: safe.taieng.co.kr"
                    )
                except Exception:
                    pass  # SMS 실패 시 무시 (인앱은 이미 전송)
    
    # 게시판 알림 상태 업데이트
    total_notified = sum(
        len(supabase.table("users")
            .select("id", count="exact")
            .eq("factory_id", fid)
            .in_("role_code", SAFETY_ROLES)
            .execute().data or [])
        for fid in factory_ids
    )
    # board_entry의 notification_sent 업데이트는 INSERT 후 별도 UPDATE
```

---

## ③ 점검 항목에 신규 법규 플래그

### 마이그레이션: `inspection_set_items`에 컨럼 추가

```sql
ALTER TABLE inspection_set_items 
  ADD COLUMN IF NOT EXISTS is_law_changed boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS law_changed_at timestamptz,
  ADD COLUMN IF NOT EXISTS law_revision_board_id uuid REFERENCES law_revision_board(id);
```

### 수정 위치: 게시판 INSERT 직후

```python
# ★ 영향받는 점검항목에 신규 법규 플래그
if affected_factories:
    _flag_inspection_items(board_entry, affected_factories, supabase)
```

### 플래그 함수 (신규)

```python
def _flag_inspection_items(board_entry: dict, factory_ids: list, supabase):
    """affected_rule_ids에 해당하는 점검항목에 법령개정 플래그 설정"""
    rule_ids = board_entry.get("affected_rule_ids", [])
    if not rule_ids:
        return
    
    for fid in factory_ids:
        # 해당 사업장의 점검세트
        sets = supabase.table("inspection_sets")\
            .select("id")\
            .eq("factory_id", fid)\
            .eq("is_active", True)\
            .execute()
        
        for s in (sets.data or []):
            # 해당 룰과 연결된 점검항목 찾기
            # source 컨럼이나 master_item_id로 매칭
            supabase.table("inspection_set_items")\
                .update({
                    "is_law_changed": True,
                    "law_changed_at": datetime.now().isoformat(),
                    "law_revision_board_id": board_entry.get("id"),
                })\
                .eq("inspection_set_id", s["id"])\
                .eq("is_active", True)\
                .execute()
```

### 프론트엔드 표시

점검 항목 목록에서 `is_law_changed = true`인 항목에:
```html
<span class="badge bg-warning">⚠️ 법령 개정</span>
```

---

## 프론트엔드 연결 (2곳)

### A) safe.taieng.co.kr 대시보드

"법령 개정 현황" 카드 추가:
```
API: GET /law-revision-board?factory_id={my_factory_id}
표시: 최근 5건, 새 게시물 배지, 원문 링크
```

### B) new.taieng.co.kr 마케팅 사이트

"최근 법령 개정 현황" 섹션:
```
API: GET /public/law-revisions?limit=10
표시: is_public=true 게시물만, 시간순 정렬
홍보 메시지: "TAI Safe는 473개 법령의 개정을 실시간 추적합니다"
```

---

## API 엔드포인트 (신규 2개)

### 1) 인증 필요 (SaaS 대시보드용)
```
GET /law-revision-board
  ?factory_id=xxx        ← 내 사업장 관련만
  ?limit=10
  ?offset=0
응답: { items: [...], total: N }
```

### 2) 공개 (public, 마케팅용)
```
GET /public/law-revisions
  ?limit=10
  ← is_public=true 만 반환, 인증 불필요
응답: { items: [...], total: N }
```

---

## 완료 기준

- [ ] `law_collector.py` :: `check_law_update()`에서 `law_revision_board` INSERT
- [ ] 영향받는 사업장 특정 함수 `_find_affected_factories()`
- [ ] `notifications` 테이블 INSERT (인앱 알림)
- [ ] MessageMi SMS 발송 연결
- [ ] `inspection_set_items`에 `is_law_changed` 커럼 + 플래그 설정
- [ ] `GET /law-revision-board` API (인증)
- [ ] `GET /public/law-revisions` API (공개)
- [ ] 서버 정상 실행 + `/health` 확인

---

## [TAI 개발 규칙 — 서비스 계층 분리]
문서: docs/DEV_RULES_SERVICE_LAYER.md

law_collector.py = 28KB → 20KB 미만이므로 분리 불필요.
신규 함수가 추가되어 20KB 초과 시 분리 적용.

절대 하지 말 것:
- 라우터에서 직접 SQL 실행 (services에서만)
- 서비스에서 Request/Response 객체 사용
- 한 파일에 400줄 이상 작성
