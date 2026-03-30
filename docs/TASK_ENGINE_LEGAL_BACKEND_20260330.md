# engine-legal 백엔드 작업 지시서
## 담당: Claude Code
## 참조: docs/TASK_LAW_BACKEND_20260330.md

---

## STEP 1. routers/engine_legal.py 신규 생성

아래 엔드포인트 전부 구현:

```python
# routers/engine_legal.py
from fastapi import APIRouter, HTTPException
from db.database import get_supabase

router = APIRouter(prefix="/engine-legal", tags=["법령 엔진 관리"])


# ── 통계 ────────────────────────────────────────────────────
@router.get("/stats")
def get_stats():
    """
    상단 통계 카드용
    - 전체 법령수 / 전체 조문수 / 전체 항수
    - 판정룰 수 / 미매핑 룰 수
    - 별표 데이터 합계 (안전인증/자율안전확인/위험물/선임기준/법정검사)
    - 항수=0인 법령 수 (파싱 누락)
    - BUILDING만 매핑된 법령 수 (섹터 편중)
    - obligation_summary 공백 룰 수
    """
    sb = get_supabase()

    total_laws = sb.table("law_master").select("id", count="exact") \
        .in_("law_type_code", ["LAW", "ENFORCEMENT_DECREE", "ENFORCEMENT_RULE"]).execute()
    total_articles = sb.table("law_article").select("id", count="exact").execute()
    total_paras = sb.table("law_paragraph").select("id", count="exact").execute()
    total_rules = sb.table("master_building_legal_rules").select("id", count="exact") \
        .eq("is_active", True).execute()

    # 미매핑 룰 (법령명이 law_master에 없는 룰)
    unmapped = sb.rpc("count_unmapped_rules", {}).execute() if False else None  # 직접 SQL 필요

    # 별표 합계
    cert = sb.table("master_safety_certification").select("id", count="exact") \
        .eq("cert_type", "CERT").execute()
    self_cert = sb.table("master_safety_certification").select("id", count="exact") \
        .eq("cert_type", "SELF").execute()
    goods = sb.table("master_dangerous_goods").select("id", count="exact").execute()
    manager = sb.table("master_safety_manager_criteria").select("id", count="exact").execute()
    inspection = sb.table("master_legal_inspection_target").select("id", count="exact").execute()

    return {
        "status": "success",
        "data": {
            "total_laws":        total_laws.count,
            "total_articles":    total_articles.count,
            "total_paragraphs":  total_paras.count,
            "total_rules":       total_rules.count,
            "unmapped_rules":    0,   # TODO: SQL로 직접 계산
            "byulpyo": {
                "safety_cert":      cert.count,
                "self_cert":        self_cert.count,
                "dangerous_goods":  goods.count,
                "safety_manager":   manager.count,
                "legal_inspection": inspection.count,
                "total": (cert.count or 0) + (self_cert.count or 0) +
                         (goods.count or 0) + (manager.count or 0) + (inspection.count or 0)
            }
        }
    }


# ── 법령 목록 ────────────────────────────────────────────────
@router.get("/laws")
def list_laws(
    law_type_code: str = None,
    search: str = None,
    page: int = 1,
    page_size: int = 50
):
    """
    탭1: 법령 목록
    - law_type_code 필터: LAW / ENFORCEMENT_DECREE / ENFORCEMENT_RULE
    - search: 법령명 검색
    - 각 법령의 조문수 / 항수 / 판정룰수 포함
    """
    sb = get_supabase()

    # law_master 조회
    q = sb.table("law_master").select("id,law_name,law_type_code,ministry_name,created_at")
    if law_type_code:
        q = q.eq("law_type_code", law_type_code)
    else:
        q = q.in_("law_type_code", ["LAW", "ENFORCEMENT_DECREE", "ENFORCEMENT_RULE"])
    if search:
        q = q.ilike("law_name", f"%{search}%")

    total_q = q.execute()
    total = len(total_q.data)

    laws = q.order("law_name").range((page-1)*page_size, page*page_size-1).execute()

    # 각 법령의 조문수·항수·룰수 조인
    result = []
    for law in laws.data:
        # 현재 버전 조문수·항수
        ver = sb.table("law_version").select("id").eq("law_id", law["id"]) \
            .eq("is_current", True).limit(1).execute()
        article_cnt = 0
        para_cnt = 0
        if ver.data:
            vid = ver.data[0]["id"]
            ac = sb.table("law_article").select("id", count="exact") \
                .eq("law_version_id", vid).execute()
            pc = sb.table("law_paragraph").select("law_paragraph.id", count="exact") \
                .execute()  # JOIN 없이는 복잡 → 단순 카운트
            article_cnt = ac.count or 0

        # 판정룰 수
        rule_cnt = sb.table("master_building_legal_rules").select("id", count="exact") \
            .eq("law_name", law["law_name"]).eq("is_active", True).execute()

        result.append({
            **law,
            "article_count": article_cnt,
            "paragraph_count": para_cnt,
            "rule_count": rule_cnt.count or 0,
        })

    return {"status": "success", "total": total, "data": result}


# ── 법령 상세 (사이드패널) ────────────────────────────────────
@router.get("/laws/{law_id}")
def get_law_detail(law_id: str):
    """
    법령 상세 사이드패널용
    - 법령 기본정보
    - 조문 목록 (최대 50개)
    - 연결된 판정룰 목록
    """
    sb = get_supabase()
    law = sb.table("law_master").select("*").eq("id", law_id).single().execute()
    if not law.data:
        raise HTTPException(status_code=404, detail="법령을 찾을 수 없습니다")

    # 현재 버전 조문
    ver = sb.table("law_version").select("id").eq("law_id", law_id) \
        .eq("is_current", True).limit(1).execute()
    articles = []
    if ver.data:
        arts = sb.table("law_article").select("article_no,article_title,article_text") \
            .eq("law_version_id", ver.data[0]["id"]).order("article_no").limit(50).execute()
        articles = arts.data

    # 연결 판정룰
    rules = sb.table("master_building_legal_rules") \
        .select("rule_id,law_article,sector,obligation_type,obligation_summary") \
        .eq("law_name", law.data["law_name"]).eq("is_active", True).execute()

    return {"status": "success", "data": {
        **law.data,
        "articles": articles,
        "rules": rules.data
    }}


# ── 판정룰 목록 ──────────────────────────────────────────────
@router.get("/rules")
def list_rules(
    sector: str = None,
    obligation_type: str = None,
    search: str = None,
    page: int = 1,
    page_size: int = 50
):
    """
    탭2: 판정룰 목록
    - sector 필터: BUILDING / MANUFACTURING / CONSTRUCTION / SPECIAL_FACILITY
    - obligation_type: APPOINT / INSPECT / REPORT / NOTIFY / ACTION / OTHER
    - search: 법령명·의무요약 검색
    """
    sb = get_supabase()
    q = sb.table("master_building_legal_rules").select(
        "id,rule_id,law_name,law_article,sector,obligation_type,"
        "obligation_summary,penalty_summary,form_code,is_active"
    ).eq("is_active", True)

    if sector:
        q = q.eq("sector", sector)
    if obligation_type:
        q = q.eq("obligation_type", obligation_type)
    if search:
        q = q.or_(f"law_name.ilike.%{search}%,obligation_summary.ilike.%{search}%")

    total_q = q.execute()
    total = len(total_q.data)
    data = q.order("law_name").order("sector").range((page-1)*page_size, page*page_size-1).execute()

    return {"status": "success", "total": total, "data": data.data}


# ── 판정룰 상세 (행 ID 기준) ─────────────────────────────────
@router.get("/rules/row/{row_id}")
def get_rule_detail(row_id: str):
    sb = get_supabase()
    rule = sb.table("master_building_legal_rules").select("*").eq("id", row_id).single().execute()
    if not rule.data:
        raise HTTPException(status_code=404, detail="룰을 찾을 수 없습니다")
    return {"status": "success", "data": rule.data}


# ── 별표 목록 ────────────────────────────────────────────────
@router.get("/appendix")
def list_appendix(domain: str = None):
    """
    탭3: 별표 현황
    domain: SAFETY_CERT / SELF_CERT / HAZMAT / APPOINTMENT / STATUTORY_INSPECTION
    """
    sb = get_supabase()
    result = {}

    if not domain or domain == "SAFETY_CERT":
        r = sb.table("master_safety_certification").select("*") \
            .eq("cert_type", "CERT").eq("is_active", True).order("cert_code").execute()
        result["safety_cert"] = r.data

    if not domain or domain == "SELF_CERT":
        r = sb.table("master_safety_certification").select("*") \
            .eq("cert_type", "SELF").eq("is_active", True).order("cert_code").execute()
        result["self_cert"] = r.data

    if not domain or domain == "HAZMAT":
        r = sb.table("master_dangerous_goods").select("*") \
            .eq("is_active", True).order("goods_code").execute()
        result["dangerous_goods"] = r.data

    if not domain or domain == "APPOINTMENT":
        r = sb.table("master_safety_manager_criteria").select("*") \
            .eq("is_active", True).order("criteria_code").execute()
        result["safety_manager"] = r.data

    if not domain or domain == "STATUTORY_INSPECTION":
        r = sb.table("master_legal_inspection_target").select("*") \
            .eq("is_active", True).order("target_code").execute()
        result["legal_inspection"] = r.data

    return {"status": "success", "data": result}


@router.get("/appendix/{item_id}")
def get_appendix_detail(item_id: str, table: str = "master_safety_certification"):
    sb = get_supabase()
    r = sb.table(table).select("*").eq("id", item_id).single().execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")
    return {"status": "success", "data": r.data}
```

---

## STEP 2. main.py에 engine_legal_router 등록

```python
from routers.engine_legal import router as engine_legal_router
...
app.include_router(engine_legal_router)
```

---

## STEP 3. routers/legal_engine.py 수정

### 3-1. format_rule_result / format_rule_result_db 에 obligation_type 추가

기존 format_rule_result 함수에서 반환하는 딕셔너리에 아래 필드 추가:
```python
"obligation_type": rule.get("obligation_type") or (
    "REPORT" if rule.get("report_required") else
    "NOTIFY" if rule.get("notify_required") else
    "APPOINT" if rule.get("appointment_required") else
    "INSPECT" if rule.get("inspection_required") else
    "ACTION" if rule.get("action_required") else "OTHER"
),
```

### 3-2. diagnose/step1 summary에 report/notify 분리

기존 summary에서 `신고_count` 또는 `report` 단일 값 → 아래와 같이 분리:
```python
"summary": {
    ...,
    "report":  len([r for r in applicable if r.get("obligation_type") == "REPORT"]),
    "notify":  len([r for r in applicable if r.get("obligation_type") == "NOTIFY"]),
    ...
}
```

`rules_table` 항목에도 `obligation_type` 컬럼 포함.

---

## STEP 4. 법령 12개 재수집

(Railway 서버에서 실행 — law.go.kr IP 등록 필요)
curl -s -X POST 로 아래 12개 순차 호출:
근로기준법 / 소방기본법 / 소방시설공사업법 / 소음·진동관리법
수도법 / 악취방지법 / 의료기기법 / 주차장법
토양환경보전법 / 하수도법 / 환경기술 및 환경산업 지원법
장애인·노인·임산부 등의 편의증진 보장에 관한 법률

---

## STEP 5. obligation_summary 공백 채우기 (Supabase MCP)

```sql
UPDATE master_building_legal_rules
SET obligation_summary = CONCAT(
  CASE obligation_type
    WHEN 'APPOINT' THEN '선임 의무'
    WHEN 'INSPECT' THEN '점검 의무'
    WHEN 'REPORT'  THEN '신고 의무'
    WHEN 'NOTIFY'  THEN '보고 의무'
    WHEN 'ACTION'  THEN '조치 의무'
    ELSE '의무'
  END,
  ' (', law_name, COALESCE(' ' || law_article, ''), ')'
)
WHERE is_active = true
  AND (obligation_summary IS NULL OR obligation_summary = '');
```

---

## STEP 6. git commit & push

```bash
git add routers/engine_legal.py routers/legal_engine.py main.py
git commit -m "feat: engine_legal.py + legal_engine obligation_type 분리 v4.3.2"
git push origin main
```

## 완료 기준
- [ ] GET /engine-legal/stats 200 응답
- [ ] GET /engine-legal/laws 200 응답
- [ ] GET /engine-legal/rules 200 응답
- [ ] GET /engine-legal/appendix 200 응답
- [ ] legal_engine diagnose/step1 응답에 summary.report / summary.notify 분리
- [ ] obligation_summary 공백 0개
- [ ] Railway 배포 완료 (v4.3.2)
