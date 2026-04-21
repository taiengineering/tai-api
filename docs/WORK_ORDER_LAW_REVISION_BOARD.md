# 작업지시서: 법령 개정 게시판 + 알림 + 점검앙커 연동

> DB: `law_revision_board` 테이블 생성 완료 (2026-04-21)
> 목적: 법령 개정 시 (1)게시판 자동등록 (2)안전관리자 알림 (3)점검앙커 출력
> 활용: 내부 사업장 공지 + 외부 마케팅사이트 홍보

---

## 테이블 구조 (law_revision_board)

```
id                    UUID PK
law_name              TEXT      법령명
law_type              TEXT      LAW/ENFORCEMENT_DECREE/NOTICE
revision_type         TEXT      일부개정/전부개정/제정
revision_date         DATE      개정일
enforcement_date      DATE      시행일
law_change_log_id     UUID FK   law_change_log 연결
title                 TEXT      게시글 제목
summary               TEXT      1~2줄 핵심 변경 요약
body                  TEXT      상세 설명 (마크다운)
impact_description    TEXT      사업장 영향 설명
affected_sectors      TEXT[]    영향 섹터
affected_rule_ids     TEXT[]    영향 rule_id 목록
affected_factory_count INT      영향 시설 수
status                TEXT      DRAFT/PUBLISHED/ARCHIVED
is_public             BOOLEAN   마케팅사이트 노출 여부
is_pinned             BOOLEAN   고정 여부
notification_sent     BOOLEAN   알림 발송 완료 여부
notification_sent_at  TIMESTAMPTZ
notification_count    INT       발송 알림 수
```

---

## PART 1: 백엔드 — 개정 감지 시 자동 등록

### 1-1. law_collector.py 수정

파일: `routers/law_collector.py` (28KB)
위치: `check_law_update()` 함수 내부, `mark_rules_needs_review()` 호출 직후

```python
# check_law_update() 함수 내부 — mark_rules_needs_review() 직후에 추가:

# ① 영향받는 섹터 파악
affected_rules = supabase.table("master_building_legal_rules")\
    .select("rule_id, sector")\
    .ilike("law_name", f"%{law_name}%")\
    .eq("is_active", True)\
    .execute()

affected_sectors = list(set(r["sector"] for r in affected_rules.data))
affected_rule_ids = [r["rule_id"] for r in affected_rules.data]

# ② 영향받는 시설 수 조회
affected_factories = supabase.table("factory_diagnosis_results")\
    .select("factory_id", count="exact")\
    .eq("is_latest", True)\
    .in_("sector", affected_sectors)\
    .execute()

# ③ 게시판 자동 등록
supabase.table("law_revision_board").insert({
    "law_name": law_name,
    "law_type": law_type_name_to_code(current.get("law_type_name", "")),
    "revision_type": current.get("revision_type", ""),
    "revision_date": str(current.get("announcement_date")) if current.get("announcement_date") else None,
    "enforcement_date": str(current.get("enforcement_date")) if current.get("enforcement_date") else None,
    "law_change_log_id": change_log_id,  # INSERT 후 반환된 ID
    "title": f"[{current.get('revision_type', '개정')}] {law_name}",
    "summary": f"{law_name}이 {current.get('revision_type', '개정')}되었습니다. 시행일: {current.get('enforcement_date', '미정')}",
    "impact_description": f"적용 룰 {len(affected_rule_ids)}건, 영향 시설 {affected_factories.count or 0}개",
    "affected_sectors": affected_sectors,
    "affected_rule_ids": affected_rule_ids,
    "affected_factory_count": affected_factories.count or 0,
    "status": "PUBLISHED",      # 자동 발행
    "is_public": True,          # 마케팅사이트에도 노출
}).execute()
```

### 1-2. 알림 발송 (기존 notifications 테이블 활용)

```python
# ④ 영향받는 시설의 안전관리자에게 알림
safety_roles = ['003', '005', '008', '009', '010']  # 안전관리자, 현장소장, 총책임자 등

# 영향 시설의 factory_id 목록
factory_ids = [r["factory_id"] for r in affected_factories.data]

# 해당 시설의 안전관리자 조회
if factory_ids:
    users = supabase.table("users")\
        .select("id, company_id, factory_id, name, phone")\
        .in_("factory_id", factory_ids)\
        .in_("role_code", safety_roles)\
        .execute()

    # 인앱 알림 생성
    notifications = []
    for user in users.data:
        notifications.append({
            "company_id": user["company_id"],
            "user_id": user["id"],
            "trigger_code": "LAW_REVISION",
            "trigger_group": "LEGAL",
            "title": f"[법령 개정] {law_name}",
            "body": f"귀 사업장에 적용되는 {law_name}이 개정되었습니다. 점검 항목을 확인하세요.",
            "link_url": f"/law-revision/{board_id}",
            "priority": "HIGH",
            "channel": "IN_APP",
            "send_status": "SENT",
            "is_read": False,
        })
    
    if notifications:
        supabase.table("notifications").insert(notifications).execute()

    # SMS 발송 (MessageMi)
    # 안전관리자에게만 SMS (비용 절감)
    sms_targets = [u for u in users.data if u.get("phone") and u["role_code"] in ['003','008']]
    for user in sms_targets:
        # messaging.py의 send_sms() 호출
        pass

    # 게시판 알림 상태 업데이트
    supabase.table("law_revision_board").update({
        "notification_sent": True,
        "notification_sent_at": datetime.now().isoformat(),
        "notification_count": len(notifications),
    }).eq("id", board_id).execute()
```

### 1-3. 점검 앙커 목록에 신규 법규 플래그

```python
# ⑤ 영향받는 시설의 inspection_sets에 신규 항목 추가
for factory_id in factory_ids:
    # 해당 시설의 활성 inspection_set 조회
    sets = supabase.table("inspection_sets")\
        .select("id")\
        .eq("factory_id", factory_id)\
        .eq("is_active", True)\
        .execute()
    
    for iset in sets.data:
        supabase.table("inspection_set_items").insert({
            "inspection_set_id": iset["id"],
            "item_name": f"[법령개정] {law_name} 확인",
            "description": f"{revision_type} ({enforcement_date} 시행) — 점검 기준 변경 여부 확인 필요",
            "is_required": True,
            "check_type": "CONFIRM",
            "risk_type": "LAW_CHANGE",
            "source": "LAW_REVISION",
            "is_active": True,
        }).execute()
```

---

## PART 2: 프론트엔드 — safe.taieng.co.kr (내부)

### 2-1. 대시보드 위젯

위치: 안전관리자 대시보드 (index.html)

```
┌────────────────────────────────────────┐
│ ⚠️ 법령 개정 알림                    2건 │
├────────────────────────────────────────┤
│ [일부개정] 산업안전보건법 시행령      │
│ 적용 룰 12건 | 2026-05-01 시행    │
├────────────────────────────────────────┤
│ [일부개정] 화학물질관리법             │
│ 적용 룰 3건 | 2026-06-15 시행     │
└────────────────────────────────────────┘
```

API: `GET /law-revision-board?sector={user_sector}&status=PUBLISHED&limit=5`

### 2-2. 법령 개정 상세 페이지

페이지: `law-revision-detail.html?id={board_id}`

내용:
- 개정 요약
- 영향받는 점검 항목 목록
- 원문 링크 (law.go.kr)
- "추가된 점검 항목 보기" 버튼

### 2-3. 점검 앙커 목록에 배지 표시

점검항목 목록에서 `source = 'LAW_REVISION'`인 항목에:
```html
<span class="badge bg-warning">⚠️ 법령개정</span>
```

---

## PART 3: 프론트엔드 — new.taieng.co.kr (외부 홍보)

### 3-1. 법령 개정 현황 페이지

페이지: `nexas/law-updates.html`

API: `GET /public/law-revision-board?status=PUBLISHED&is_public=true`

디자인:
```
┌─────────────────────────────────────────────┐
│  TAI가 모니터링하는 473개 법령의 개정 현황  │
│  "우리 사업장에 적용되는 법령이 바뀌면    │
│   TAI가 자동으로 알려드립니다"            │
├─────────────────────────────────────────────┤
│ 2026-04-21  [일부개정] 산업안전보건법 시행령  │
│ 2026-04-15  [일부개정] 화학물질관리법       │
│ 2026-04-01  [제정] 중대재해처벌법 시행령     │
│ ...                                       │
├─────────────────────────────────────────────┤
│  무료 법령진단으로 우리 사업장 확인하기 →    │
└─────────────────────────────────────────────┘
```

홍보 포인트:
- "다른 안전관리 서비스는 법령 개정을 알려주지 않습니다"
- "TAI Safe는 473개 법령을 24시간 모니터링합니다"
- "개정 시 자동으로 사업장에 통보하고 점검항목을 업데이트합니다"

---

## PART 4: API 엔드포인트

### 4-1. 내부용 (인증 필요)

```
GET /law-revision-board
  ?sector=MANUFACTURING        내 시설 섹터 필터
  &status=PUBLISHED
  &page=1&page_size=10

GET /law-revision-board/{id}   상세
```

### 4-2. 공개용 (마케팅사이트)

```
GET /public/law-revision-board
  ?status=PUBLISHED
  &is_public=true
  &page=1&page_size=20

GET /public/law-revision-board/{id}
```

---

## 데이터 흐름 요약

```
법령 개정 감지 (law_collector.py)
  │
  ├── law_change_log INSERT
  ├── law_rule_drafts APPROVED → NEEDS_REVIEW
  │
  ├── ① law_revision_board INSERT (게시판 등록)
  │     └─ is_public=true → 마케팅사이트 노출
  │
  ├── ② notifications INSERT (안전관리자 알림)
  │     ├─ IN_APP: 대시보드 알림 표시
  │     └─ SMS: MessageMi 발송 (안전관리자+총책임자만)
  │
  └── ③ inspection_set_items INSERT (점검 앙커 항목)
        └─ source='LAW_REVISION'
        └─ risk_type='LAW_CHANGE'
        └─ 프론트에서 ⚠️ 배지 표시
```

---

## 우선순위

| 순위 | 작업 | 대상 | 창 |
|---|---|---|---|
| 1 | law_collector.py 수정 (게시판+알림+점검앙커) | 백엔드 | Cursor |
| 2 | law_revision_board API 라우터 생성 | 백엔드 | Cursor |
| 3 | 대시보드 위젯 추가 | safe 프론트 | Cursor |
| 4 | nexas/law-updates.html | 마케팅 프론트 | Cursor |

---

## [TAI 개발 규칙 — 서비스 계층 분리]

law_collector.py는 28KB로 20KB 초과.
수정 시 서비스 분리를 선행할 것.

5단계:
  STEP 1: 패키지 생성 + 헬퍼 분리
  STEP 2: 스키마 분리
  STEP 3: 서비스 분리
  STEP 4: 라우터 슬림화
  STEP 5: 테스트 작성

절대 하지 말 것:
- 라우터에서 직접 SQL 실행 (services에서만)
- 서비스에서 Request/Response 객체 사용
- 한 파일에 400줄 이상 작성
- 20KB 이상 파일을 통째로 덮어쓰기
