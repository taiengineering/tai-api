# WORK ORDER: AI 검증 파이프라인 구축 (Phase 1~3 + 하이브리드 큐)

**작성일:** 2026-04-22  
**대상:** Cursor / Claude Code  
**예상 소요:** 3주 (Phase 1: 1주, Phase 2: 3일, Phase 3: 1주, 통합 검증: 3일)  
**관련 이슈:** #37 (law_collector 파편화), PR #35 / PR #38 (이미 머지됨)

---

## 🎯 목적

법령엔진을 **전문가 검수 없이도 신뢰 가능한 수준**으로 끌어올리기. 다음 3단계:

1. **Phase 1**: 데이터 인프라 복구 (Issue #37 해결 → 재수집)
2. **Phase 2**: 하이브리드 큐 아키텍처 (기존 파이프라인 보존 + 검증 레이어 추가)
3. **Phase 3**: AI 다중 검증 로직 (Haiku→Sonnet 2단 + 누락 탐지 + 크로스체크)

**핵심 원칙:**
- 기존 "법령개정 감지 → 즉시 알림" 파이프라인 **0ms도 지연시키지 말 것**
- 검증은 비동기 큐로 분리 (실패해도 본 파이프라인 영향 없음)
- DEV_RULES v2 준수 (services에 fastapi 금지, 파일 400줄 이내, 테스트 우선)

---

## 📋 현재 상태 (2026-04-22 기준)

| 항목 | 상태 | 비고 |
|---|---|---|
| `master_building_legal_rules` | 1,402건 (AI 562, 수동 840) | penalty 541건 누락, submit_org 269건 누락 |
| `law_article` | 373법령 / 약 24,000 row | 유효 조문 4~8% (95% 파편) |
| 크론 수집기 | 가동 중 (4/17-18 9법령 수집) | 파편 상태로 수집 중 |
| 알림 파이프라인 | 정상 | Push + SMS + inspection_items 플래그 |
| `INTERNAL_API_SECRET` | Railway에 새 값 세팅됨 | PR #38 머지 완료 |

---

## 🗺️ Phase 1: 데이터 인프라 복구 (1주)

### 목표
`law_article` 유효 조문 비율 4% → **80%+**로 복구.

### 1-1. 진단 (0.5일)

**1-1-1. XML 원본 구조 분석**

```sql
-- 건축법 XML 원본 1건 확보
SELECT 
  lv.law_id,
  lm.law_name,
  LEFT(lcr.raw_xml, 3000) AS xml_preview,
  LENGTH(lcr.raw_xml) AS xml_length
FROM law_content_raw lcr
JOIN law_version lv ON lcr.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name = '건축법'
  AND lv.is_current = true
LIMIT 1;
```

전체 XML을 로컬로 저장하고 `xmllint --format` 또는 Python `ET.dump()`로 구조 파악:
- `<조문단위>` 태그 nesting 여부
- `조문키` 속성 고유성
- 조문 외 어디에 `<조문단위>`가 추가로 있는지

**1-1-2. 영향 범위 재측정**

```sql
-- 법령별 파편화 현황 스냅샷 (수정 전 baseline)
CREATE TABLE IF NOT EXISTS law_quality_snapshot_20260422 AS
SELECT 
  lm.law_name,
  lm.id AS law_id,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT la.article_no) AS unique_articles,
  COUNT(*) FILTER (WHERE LENGTH(la.article_text) > 500) AS valid_articles,
  ROUND(100.0 * COUNT(*) FILTER (WHERE LENGTH(la.article_text) > 500) / NULLIF(COUNT(*), 0), 2) AS valid_pct,
  NOW() AS snapshot_at
FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lv.is_current = true AND lm.is_active = true
GROUP BY lm.law_name, lm.id;
```

이 snapshot이 수정 후 비교 기준이 됨.

### 1-2. `parse_law_content_xml()` 수정 (1일)

**파일:** `routers/law_collector.py` (162행 근처)

**수정 전:**
```python
def parse_law_content_xml(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    ...
    articles = []
    for jo in root.findall(".//조문단위"):  # 🐛 descendant-or-self
        article = {
            "article_internal_key": jo.get("조문키", ""),
            "article_no":           _safe_int(jo.findtext("조문번호", "")),
            ...
        }
        articles.append(article)
```

**수정 방향 (XML 분석 결과 따라 택일):**

#### 옵션 A: XPath 엄격화 (구조가 단순할 때)
```python
# 최상위 조문만 수집
for jo in root.findall("./조문/조문단위"):  # 또는 ./본문/조문단위
    ...
```

#### 옵션 B: article_internal_key 기반 중복 제거 (가장 안전)
```python
articles_dict = {}
for jo in root.findall(".//조문단위"):
    key = jo.get("조문키", "")
    if not key:
        continue  # 키 없는 파편 무시
    
    parsed = _parse_single_article(jo)
    
    # 이미 있으면 더 완전한 쪽 유지
    existing = articles_dict.get(key)
    if existing is None:
        articles_dict[key] = parsed
    elif _is_more_complete(parsed, existing):
        articles_dict[key] = parsed

articles = list(articles_dict.values())
```

`_is_more_complete()` 기준:
1. `article_title`이 비어있지 않음
2. `article_text` 길이가 더 김
3. 하위 `<항>` 요소가 더 많음

#### 옵션 C: 옵션 A + B 조합 (권장)
XPath로 1차 필터링 후 키 기반 중복 제거로 2차 안전망.

**단위 테스트 필수** (신규 파일):

```python
# tests/test_law_collector.py
import pytest
from routers.law_collector import parse_law_content_xml

SAMPLE_XML_CLEAN = """<?xml version="1.0"?>
<법령>
  <기본정보><법령명_한글>테스트법</법령명_한글></기본정보>
  <조문>
    <조문단위 조문키="제1조">
      <조문번호>1</조문번호>
      <조문제목>목적</조문제목>
      <조문내용>이 법은...</조문내용>
    </조문단위>
    <조문단위 조문키="제2조">
      <조문번호>2</조문번호>
      <조문제목>정의</조문제목>
      <조문내용>용어의 뜻은...</조문내용>
    </조문단위>
  </조문>
</법령>"""

SAMPLE_XML_NESTED = """<?xml version="1.0"?>
<법령>
  <조문>
    <조문단위 조문키="제1조">
      <조문번호>1</조문번호>
      <조문제목>목적</조문제목>
      <조문내용>이 법은 「제2조」에 따라...</조문내용>
      <항>
        <!-- 중첩된 조문단위 — 파편 유발 지점 -->
        <조문단위><조문번호>1</조문번호><조문내용>파편</조문내용></조문단위>
      </항>
    </조문단위>
  </조문>
</법령>"""


def test_parse_clean_xml_returns_correct_count():
    """정상 XML은 조문 개수대로 반환"""
    result = parse_law_content_xml(SAMPLE_XML_CLEAN)
    assert len(result["articles"]) == 2


def test_parse_nested_xml_deduplicates():
    """중첩된 조문단위가 있어도 진짜 조문만 반환"""
    result = parse_law_content_xml(SAMPLE_XML_NESTED)
    assert len(result["articles"]) == 1
    # 제목 있는 쪽이 선택돼야 함
    assert result["articles"][0]["article_title"] == "목적"


def test_parse_keeps_more_complete_version():
    """동일 키의 두 조문단위 중 더 완전한 쪽 유지"""
    xml = """<법령><조문>
      <조문단위 조문키="제1조"><조문번호>1</조문번호><조문제목></조문제목><조문내용>짧음</조문내용></조문단위>
      <조문단위 조문키="제1조"><조문번호>1</조문번호><조문제목>완전</조문제목><조문내용>완전한 긴 내용입니다</조문내용></조문단위>
    </조문></법령>"""
    result = parse_law_content_xml(xml)
    assert len(result["articles"]) == 1
    assert result["articles"][0]["article_title"] == "완전"
```

### 1-3. 샘플 법령 1건 테스트 재수집 (0.5일)

**목표:** 실 법령 1건만 재수집해서 valid_articles 비율 확인.

```bash
# 로컬 또는 Railway shell에서
curl -X POST "https://api.taieng.co.kr/law-collector/collect/산업안전보건법?force=true"
```

검증 쿼리:
```sql
SELECT 
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE LENGTH(article_text) > 500) AS valid,
  ROUND(100.0 * COUNT(*) FILTER (WHERE LENGTH(article_text) > 500) / COUNT(*), 1) AS valid_pct
FROM law_article la
JOIN law_version lv ON la.law_version_id = lv.id
JOIN law_master lm ON lv.law_id = lm.id
WHERE lm.law_name = '산업안전보건법' AND lv.is_current = true;
```

**합격 기준:** valid_pct >= 80%, unique_articles ≈ 법제처 원본 조문 수.

### 1-4. FK 무결성 보존 전략 (1일)

**위험:** 재수집 시 `law_version` 새로 생기면 기존 `article_id` 무효화 → `law_rule_drafts.article_id`, `inspection_set_items.law_article_id` 등 모두 끊김.

**전략 A (권장): 덮어쓰기 모드**

`save_law_to_db()`를 수정해 **같은 law_mst_no면 기존 version 유지 + article만 갱신**:

```python
if existing_version.data:
    version_id = existing_version.data[0]["id"]
    is_new_version = False
    
    # 🆕 force_refresh 모드: 기존 article 삭제 후 재삽입
    if force_refresh:
        # 1) 기존 article_id 목록 보관
        old_arts = supabase.table("law_article").select("id, article_internal_key")\
            .eq("law_version_id", version_id).execute().data or []
        old_map = {a["article_internal_key"]: a["id"] for a in old_arts}
        
        # 2) 삭제 전에 dependent FK 처리
        # law_rule_drafts, inspection_set_items 등의 article_id를 임시 NULL로 설정
        # (재삽입 후 internal_key로 매칭해서 복원)
        ...
        
        # 3) law_article 삭제
        supabase.table("law_article").delete().eq("law_version_id", version_id).execute()
        
        # 4) 새 article 삽입 (아래 기존 로직)
        # 5) internal_key로 FK 재연결
        ...
```

**전략 B (안전하지만 느림): 새 version 생성 + 매핑 테이블**

```sql
-- 임시 매핑 테이블
CREATE TABLE law_article_key_map (
  old_article_id UUID,
  new_article_id UUID,
  article_internal_key TEXT,
  law_version_id UUID,
  migrated_at TIMESTAMP DEFAULT NOW()
);

-- 재수집 후 매핑 생성
INSERT INTO law_article_key_map (old_article_id, new_article_id, article_internal_key, law_version_id)
SELECT old.id, new.id, old.article_internal_key, new.law_version_id
FROM law_article old
JOIN law_article new ON old.article_internal_key = new.article_internal_key
                     AND old.law_version_id = ...  -- old version
                     AND new.law_version_id = ...; -- new version

-- 참조 테이블 업데이트
UPDATE law_rule_drafts lrd
SET article_id = m.new_article_id
FROM law_article_key_map m
WHERE lrd.article_id = m.old_article_id;

UPDATE inspection_set_items isi
SET law_article_id = m.new_article_id
FROM law_article_key_map m
WHERE isi.law_article_id = m.old_article_id;

-- 구 version 비활성화
UPDATE law_version SET is_current = false WHERE id = <old_version_id>;
```

**결정 기준:** 
- 시간 여유 있고 안전 우선 → 전략 B
- 빨리 가야 함, 중단 시간 허용 → 전략 A
- **기본 권장: 전략 B**

### 1-5. 전체 재수집 실행 (2일)

**순서:**

1. **사전 조치:**
   - Railway cron `check-updates-v2` 일시 중단 (수집 중 중복 트리거 방지)
   - DB 백업: `pg_dump` 또는 Supabase 대시보드 snapshot
   - `ai_validation_queue` 테이블 enqueue 일시 중단 (Phase 2에서 생성 후)

2. **재수집 스크립트:**
   ```python
   # scripts/full_recollect.py
   import requests, time, logging
   
   TARGETS_SQL = """
   SELECT law_name FROM law_collection_target
   WHERE is_active = true
   ORDER BY collection_priority;
   """
   
   for law_name in targets:
       try:
           r = requests.post(
               f"https://api.taieng.co.kr/law-collector/collect/{law_name}",
               params={"force": "true"},
               timeout=120
           )
           log.info(f"{law_name}: {r.status_code}")
           time.sleep(5)  # API 부하 완화
       except Exception as e:
           log.error(f"{law_name} FAIL: {e}")
   ```

3. **검증 (재수집 후):**
   ```sql
   -- 파편화율 대폭 개선 확인
   WITH new_stats AS (
     SELECT lm.law_name,
            COUNT(*) AS new_total,
            COUNT(*) FILTER (WHERE LENGTH(la.article_text) > 500) AS new_valid
     FROM law_article la
     JOIN law_version lv ON la.law_version_id = lv.id
     JOIN law_master lm ON lv.law_id = lm.id
     WHERE lv.is_current = true
     GROUP BY lm.law_name
   )
   SELECT 
     s.law_name,
     s.total_rows AS old_total,
     n.new_total,
     s.valid_articles AS old_valid,
     n.new_valid,
     ROUND(100.0 * n.new_valid / NULLIF(n.new_total, 0), 1) AS new_valid_pct
   FROM law_quality_snapshot_20260422 s
   JOIN new_stats n ON s.law_name = n.law_name
   ORDER BY new_valid_pct DESC;
   ```

4. **롤백 조건:**
   - valid_pct가 이전보다 낮아진 법령이 1건이라도 있으면 **전체 롤백**
   - DB snapshot 복원 후 Phase 1 재시작

### Phase 1 완료 기준

- [ ] `parse_law_content_xml()` 수정 + 테스트 3개 이상 PASSED
- [ ] 샘플 법령 1건 재수집 → valid_pct >= 80%
- [ ] FK 무결성 전략 구현 + 로컬 테스트 통과
- [ ] 전체 재수집 완료 → 373법령 평균 valid_pct >= 80%
- [ ] `master_building_legal_rules` 참조 무결성 100% 유지
- [ ] 기존 `law_revision_board` / `inspection_sets` 정상 작동 확인

---

## 🗺️ Phase 2: 하이브리드 큐 아키텍처 (3일)

### 목표
기존 파이프라인을 **건드리지 않고** 검증 레이어를 "증강"으로 추가.

### 2-1. DDL: `ai_validation_queue` 테이블 (0.5일)

**파일:** `sql/20260423_ai_validation_queue.sql` (신규)

```sql
-- AI 검증 작업 큐
CREATE TABLE IF NOT EXISTS ai_validation_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- 대상 (둘 중 하나는 반드시 채워짐)
  rule_id TEXT,                      -- master_building_legal_rules.rule_id (단건 검증)
  law_id UUID,                       -- law_master.id (법령 전체 검증)
  
  -- 작업 유형
  task_type TEXT NOT NULL CHECK (
    task_type IN ('MULTI_VERIFY', 'MISSING_DETECT', 'CROSSCHECK', 'REVERIFY')
  ),
  
  -- 스케줄링
  priority INT NOT NULL DEFAULT 50,  -- 1(긴급)~100(배치)
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
    status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED', 'SKIPPED')
  ),
  retry_count INT NOT NULL DEFAULT 0,
  max_retries INT NOT NULL DEFAULT 3,
  
  -- 타임스탬프
  enqueued_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,
  
  -- 결과
  result JSONB,
  error_detail TEXT,
  
  -- 트리거 소스 (디버깅용)
  enqueued_by TEXT,  -- 'law_collector.save_law_to_db' | 'manual_api' | 'cron' 등
  
  CONSTRAINT chk_target_required CHECK (rule_id IS NOT NULL OR law_id IS NOT NULL)
);

CREATE INDEX idx_val_queue_processing 
  ON ai_validation_queue(status, priority, enqueued_at) 
  WHERE status = 'PENDING';

CREATE INDEX idx_val_queue_law 
  ON ai_validation_queue(law_id) 
  WHERE status IN ('PENDING', 'RUNNING');

CREATE INDEX idx_val_queue_rule 
  ON ai_validation_queue(rule_id) 
  WHERE status IN ('PENDING', 'RUNNING');


-- master 테이블에 검증 메타 컬럼 추가
ALTER TABLE master_building_legal_rules 
  ADD COLUMN IF NOT EXISTS verification_level TEXT 
    CHECK (verification_level IN ('UNVERIFIED', 'AI_SINGLE', 'AI_MULTI', 'CROSSCHECKED', 'MANUAL')) 
    DEFAULT 'UNVERIFIED',
  ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS verification_notes JSONB;
  -- ai_flags 컬럼은 이미 존재 (검증 경고 append 방식으로 활용)
```

### 2-2. 기존 `save_law_to_db()` 1줄 수정 (0.5일)

**파일:** `routers/law_collector.py` (200행 근처)

**위치:** 함수 맨 마지막 `return` 직전.

```python
def save_law_to_db(law_info, raw_xml, articles, supabase) -> dict:
    ...
    # (기존 코드 그대로)
    
    # 🆕 Phase 2 추가: 검증 큐에 enqueue (실패해도 무시 — 기존 플로우 보호)
    if is_new_version:
        try:
            supabase.table("ai_validation_queue").insert({
                "law_id": law_id,
                "task_type": "MULTI_VERIFY",
                "priority": 10,  # 신규 법령은 긴급 처리
                "enqueued_by": "law_collector.save_law_to_db",
            }).execute()
        except Exception as e:
            # 큐 실패는 로그만. 수집/알림 파이프라인은 계속 진행.
            print(f"[validation_queue] enqueue 실패 law_id={law_id}: {e}")
    
    return {"law_id": law_id, "version_id": version_id, ...}
```

**규칙:** 이 삽입은 **절대 실패시키지 말 것**. try/except로 감싸서 기존 플로우 보호.

### 2-3. Worker 뼈대 (services/validation_worker.py — 신규) (1일)

**파일:** `services/validation_worker.py`

```python
"""
AI 검증 큐 Worker.

기존 법령개정 감지/수집/알림 파이프라인과 **완전 분리**되어 실행됨.
실패/지연이 본 서비스에 영향 없음.

엔트리 포인트:
- POST /law-rule-generator/process-validation-queue (Railway cron)
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

# ⚠️ DEV_RULES: services 레이어는 fastapi import 금지
# from fastapi import ...  ← NO

logger = logging.getLogger("validation-worker")


async def process_queue_batch(
    supabase,
    limit: int = 10,
    *,
    task_dispatcher,  # Callable[[str, dict], Awaitable[dict]] - 의존성 주입
) -> Dict[str, Any]:
    """큐에서 PENDING 작업을 priority 순으로 집어내어 처리.
    
    Args:
        supabase: Supabase 클라이언트
        limit: 한 번에 처리할 최대 작업 수
        task_dispatcher: task_type → 실제 처리 함수 매핑 (routers에서 주입)
    
    Returns:
        {"processed": int, "succeeded": int, "failed": int, "skipped": int}
    """
    # 1) 큐에서 PENDING 작업 조회 (priority 낮은 순, enqueue 시간 순)
    pending = supabase.table("ai_validation_queue").select("*")\
        .eq("status", "PENDING")\
        .lt("retry_count", 3)\
        .order("priority")\
        .order("enqueued_at")\
        .limit(limit)\
        .execute().data or []
    
    if not pending:
        return {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    
    totals = {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    
    for job in pending:
        job_id = job["id"]
        task_type = job["task_type"]
        
        # 2) RUNNING으로 마킹 (동시 실행 방지)
        supabase.table("ai_validation_queue").update({
            "status": "RUNNING",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).eq("status", "PENDING").execute()
        
        try:
            # 3) task dispatch
            result = await task_dispatcher(task_type, job)
            
            supabase.table("ai_validation_queue").update({
                "status": "DONE",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
            }).eq("id", job_id).execute()
            
            totals["succeeded"] += 1
        
        except Exception as e:
            new_retry = job.get("retry_count", 0) + 1
            max_retry = job.get("max_retries", 3)
            new_status = "FAILED" if new_retry >= max_retry else "PENDING"
            
            supabase.table("ai_validation_queue").update({
                "status": new_status,
                "retry_count": new_retry,
                "error_detail": str(e)[:1000],
                "completed_at": datetime.now(timezone.utc).isoformat() if new_status == "FAILED" else None,
            }).eq("id", job_id).execute()
            
            logger.error(f"[job {job_id}] {task_type} 실패 ({new_retry}/{max_retry}): {e}")
            totals["failed" if new_status == "FAILED" else "processed"] += 1
        
        totals["processed"] += 1
    
    return totals


def enqueue_task(
    supabase,
    *,
    task_type: str,
    law_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    priority: int = 50,
    enqueued_by: str = "manual",
) -> Optional[str]:
    """큐에 task 추가. 중복 방지: 같은 대상+type의 PENDING/RUNNING이 있으면 skip."""
    if not law_id and not rule_id:
        raise ValueError("law_id 또는 rule_id 중 하나는 필수")
    
    # 중복 체크
    q = supabase.table("ai_validation_queue").select("id")\
        .eq("task_type", task_type)\
        .in_("status", ["PENDING", "RUNNING"])
    if law_id:
        q = q.eq("law_id", law_id)
    if rule_id:
        q = q.eq("rule_id", rule_id)
    
    existing = q.execute().data or []
    if existing:
        return None  # 이미 큐에 있음
    
    res = supabase.table("ai_validation_queue").insert({
        "law_id": law_id,
        "rule_id": rule_id,
        "task_type": task_type,
        "priority": priority,
        "enqueued_by": enqueued_by,
    }).execute()
    
    return res.data[0]["id"] if res.data else None
```

### 2-4. 라우터 엔드포인트 (routers/law_rule_generator.py 확장) (0.5일)

```python
# routers/law_rule_generator.py 하단에 추가

@router.post("/process-validation-queue")
async def process_validation_queue(body: dict):
    """Railway cron이 호출. 큐에서 대기 중인 검증 작업 처리."""
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(403, "내부 전용")
    
    limit = int(body.get("limit", 10))
    
    from services.validation_worker import process_queue_batch
    from services.validation_tasks import dispatch_task  # Phase 3에서 구현
    
    result = await process_queue_batch(
        get_supabase(), limit,
        task_dispatcher=dispatch_task,
    )
    return {"status": "success", "data": result}


@router.get("/validation-queue/stats")
async def validation_queue_stats():
    """큐 현황 모니터링."""
    supabase = get_supabase()
    
    by_status = supabase.rpc("validation_queue_summary").execute()
    # 또는 간단한 groupby 쿼리
    
    return {"status": "success", "data": by_status.data}


@router.post("/validation-queue/enqueue")
async def manual_enqueue(body: dict):
    """수동 검증 트리거 (관리자용)."""
    secret = body.get("secret", "")
    if secret != INTERNAL_SECRET:
        raise HTTPException(403, "내부 전용")
    
    from services.validation_worker import enqueue_task
    
    job_id = enqueue_task(
        get_supabase(),
        task_type=body["task_type"],
        law_id=body.get("law_id"),
        rule_id=body.get("rule_id"),
        priority=body.get("priority", 50),
        enqueued_by="manual_api",
    )
    
    return {"status": "success", "job_id": job_id}
```

### 2-5. Railway Cron 설정 (0.5일)

Railway 대시보드 → cron 설정:
- **스케줄:** `*/30 * * * *` (30분마다)
- **엔드포인트:** `POST /law-rule-generator/process-validation-queue`
- **Body:** `{"secret": "${INTERNAL_API_SECRET}", "limit": 10}`

또는 기존 `cron_manager`에 등록 (프로젝트 컨벤션에 맞춰).

### Phase 2 완료 기준

- [ ] `ai_validation_queue` 테이블 생성 + 인덱스
- [ ] `master_building_legal_rules`에 `verification_level` 컬럼 추가
- [ ] `save_law_to_db()`에 enqueue 1줄 추가 + try/except 감싸기
- [ ] `services/validation_worker.py` 구현 + 유닛 테스트 3개 이상
- [ ] 3개 엔드포인트 동작 확인
- [ ] Railway cron 등록 + 1시간 모니터링 (큐 처리율 확인)
- [ ] 기존 법령개정 알림 파이프라인 **응답시간 변화 없음** 확인

---

## 🗺️ Phase 3: AI 다중 검증 로직 (1주)

### 목표
Worker가 처리하는 실제 검증 로직 구현. 3가지 task_type.

### 3-1. `services/validation_tasks.py` (신규) (1일)

```python
"""검증 task별 실제 로직.

dispatch_task(task_type, job) → task별 함수 호출
"""
from __future__ import annotations
from typing import Dict, Any
import logging

logger = logging.getLogger("validation-tasks")


async def dispatch_task(task_type: str, job: dict) -> dict:
    """task_type에 따라 적절한 처리 함수 호출."""
    dispatcher = {
        "MULTI_VERIFY":    run_multi_verify,
        "MISSING_DETECT":  run_missing_detect,
        "CROSSCHECK":      run_crosscheck,
        "REVERIFY":        run_reverify,
    }
    
    handler = dispatcher.get(task_type)
    if not handler:
        raise ValueError(f"Unknown task_type: {task_type}")
    
    return await handler(job)


async def run_multi_verify(job: dict) -> dict:
    """Phase 3-2에서 구현."""
    ...


async def run_missing_detect(job: dict) -> dict:
    """Phase 3-3에서 구현."""
    ...


async def run_crosscheck(job: dict) -> dict:
    """Phase 3-4에서 구현."""
    ...


async def run_reverify(job: dict) -> dict:
    """단건 rule 재검증. 수동 트리거용."""
    ...
```

### 3-2. MULTI_VERIFY: Haiku → Sonnet 2단 검증 (2일)

**로직:**

```python
# services/validation_tasks.py

from db.supabase_client import get_supabase
from routers.law_rule_generator import (
    _call_claude_messages, 
    CLAUDE_MODEL, 
    CLAUDE_SONNET_MODEL,
    _build_draft_row, _build_master_payload,
    EXCLUDED_SECTORS,
)
from services.law_context_builder import build_full_context

MIN_HAIKU_CONF = 80
MIN_SONNET_CONF = 90
AUTO_APPROVE_REQUIRES_BOTH = True


async def run_multi_verify(job: dict) -> dict:
    """법령 전체의 새 조문을 Haiku → Sonnet 순으로 검증.
    
    흐름:
      1) 법령의 미파싱 조문 N개 조회
      2) 각 조문에 대해 Haiku 호출 → 초안 rule 추출
      3) 같은 조문+초안을 Sonnet에게 "검증" 프롬프트로 재호출
      4) 두 결과 비교:
         - 일치 + 둘 다 신뢰도 기준 충족 → verification_level='AI_MULTI', auto-master 등록 후보
         - 불일치 → ai_flags에 차이 기록, PENDING 유지 (수동 검토 대상)
    """
    supabase = get_supabase()
    law_id = job["law_id"]
    
    # 미파싱 조문 조회
    articles = _fetch_unparsed_articles(supabase, law_id, limit=50)
    
    totals = {
        "processed": 0,
        "haiku_rules": 0,
        "sonnet_agreed": 0,
        "sonnet_disagreed": 0,
        "auto_approved": 0,
        "needs_manual_review": 0,
    }
    
    for art in articles:
        try:
            haiku_rules = await _extract_with_haiku(art)
            totals["haiku_rules"] += len(haiku_rules)
            
            for rule in haiku_rules:
                sonnet_result = await _verify_with_sonnet(art, rule)
                
                if _results_agree(rule, sonnet_result):
                    totals["sonnet_agreed"] += 1
                    
                    # 둘 다 신뢰도 기준 충족 → auto master
                    if (rule.get("ai_confidence", 0) >= MIN_HAIKU_CONF 
                        and sonnet_result.get("ai_confidence", 0) >= MIN_SONNET_CONF):
                        _save_as_auto_approved(supabase, art, rule, sonnet_result)
                        totals["auto_approved"] += 1
                    else:
                        _save_as_pending(supabase, art, rule, sonnet_result, 
                                         flag="confidence_below_threshold")
                        totals["needs_manual_review"] += 1
                else:
                    totals["sonnet_disagreed"] += 1
                    diff = _compute_diff(rule, sonnet_result)
                    _save_as_pending(supabase, art, rule, sonnet_result,
                                     flag="multi_verify_disagreement",
                                     diff=diff)
                    totals["needs_manual_review"] += 1
            
            _mark_article_parsed(supabase, art["id"])
            totals["processed"] += 1
        
        except Exception as e:
            logger.error(f"[multi_verify] article {art['id']} 실패: {e}")
            raise  # 개별 실패는 job 전체 실패로 — retry 로직이 처리
    
    return totals


async def _extract_with_haiku(art: dict) -> List[dict]:
    """기존 call_claude()와 유사. Haiku로 초안 추출."""
    from routers.law_rule_generator import call_claude
    law_name = art["law_name"]
    full_context = await build_full_context(law_name, art.get("law_article", ""), art.get("id"))
    return await call_claude(law_name, art["article_text"], full_context=full_context)


async def _verify_with_sonnet(art: dict, haiku_rule: dict) -> dict:
    """Sonnet에게 Haiku 결과를 검증시킴."""
    prompt = f"""
다음 법령 조문과 Haiku 모델이 추출한 rule을 보고, 이 rule이 정확한지 검증하세요.

[법령 조문]
{art['article_text'][:3000]}

[Haiku 추출 결과]
{json.dumps(haiku_rule, ensure_ascii=False, indent=2)}

다음 중 하나로 판단:
1. 정확함 → 같은 필드를 그대로 반환하되 ai_confidence만 재평가
2. 일부 오류 → 수정된 필드만 포함한 JSON 반환
3. 완전 오류 → {{"error": "reason", "ai_confidence": 0}} 반환

JSON object 1개만 출력. 마크다운 금지.
"""
    
    result = await _call_claude_messages(
        "법령 rule 검증 전문 모델. JSON만 반환.",
        prompt,
        CLAUDE_SONNET_MODEL,
        max_tokens=1500,
        timeout=90,
    )
    return result if isinstance(result, dict) else {}


def _results_agree(haiku: dict, sonnet: dict) -> bool:
    """핵심 필드 일치 여부 판단."""
    if sonnet.get("error"):
        return False
    
    # 의무 유형, 섹터, 조건 코드가 같아야 일치로 판단
    critical_fields = ["obligation_type", "sector", "condition_code"]
    for field in critical_fields:
        if haiku.get(field) != sonnet.get(field):
            return False
    
    return True


def _compute_diff(haiku: dict, sonnet: dict) -> dict:
    """두 결과의 차이 필드만 추출 (ai_flags에 저장)."""
    diff = {}
    all_keys = set(haiku.keys()) | set(sonnet.keys())
    for key in all_keys:
        if haiku.get(key) != sonnet.get(key):
            diff[key] = {"haiku": haiku.get(key), "sonnet": sonnet.get(key)}
    return diff


def _save_as_auto_approved(supabase, art, haiku_rule, sonnet_result):
    """Sonnet이 동의한 고신뢰도 rule → master 자동 등록."""
    # 기존 _auto_approve_to_master 유사하되 verification_level='AI_MULTI'
    ...


def _save_as_pending(supabase, art, haiku_rule, sonnet_result, flag, diff=None):
    """PENDING draft로 저장. ai_flags에 검증 메타 포함."""
    ...
```

**테스트 (신규):**

```python
# tests/test_validation_tasks.py

def test_results_agree_same_critical_fields():
    haiku = {"obligation_type": "APPOINT", "sector": "BUILDING", "condition_code": "building_area"}
    sonnet = {"obligation_type": "APPOINT", "sector": "BUILDING", "condition_code": "building_area"}
    assert _results_agree(haiku, sonnet) is True


def test_results_disagree_different_obligation():
    haiku = {"obligation_type": "APPOINT"}
    sonnet = {"obligation_type": "INSPECT"}
    assert _results_agree(haiku, sonnet) is False


def test_results_disagree_sonnet_error():
    haiku = {"obligation_type": "APPOINT"}
    sonnet = {"error": "법령 원문과 무관함"}
    assert _results_agree(haiku, sonnet) is False


def test_compute_diff_tracks_field_differences():
    haiku = {"penalty_value": 300, "submit_org_code": "nfa"}
    sonnet = {"penalty_value": 500, "submit_org_code": "nfa"}
    diff = _compute_diff(haiku, sonnet)
    assert "penalty_value" in diff
    assert "submit_org_code" not in diff
    assert diff["penalty_value"]["haiku"] == 300
    assert diff["penalty_value"]["sonnet"] == 500
```

### 3-3. MISSING_DETECT: 누락 탐지 (2일)

**로직:** 법령 전체 조문 + 이미 추출된 rule 목록을 Sonnet에게 "놓친 게 있나?" 프롬프트로 질문.

```python
async def run_missing_detect(job: dict) -> dict:
    """법령 내 추출되지 않은 의무 찾기."""
    supabase = get_supabase()
    law_id = job["law_id"]
    
    # 1) 법령 정보 + 전체 조문
    law_info = _fetch_law_info(supabase, law_id)
    all_articles = _fetch_all_articles(supabase, law_id)
    full_law_text = "\n\n".join([
        f"{a['article_no']}조 {a.get('article_title', '')}: {a['article_text']}"
        for a in all_articles
    ])[:30000]  # Sonnet context 제한 고려
    
    # 2) 기존 master rule 요약
    existing_rules = _fetch_master_rules_for_law(supabase, law_info["law_name"])
    rules_summary = "\n".join([
        f"- [{r['obligation_type']}] {r['law_article']}: {r['obligation_summary']}"
        for r in existing_rules
    ])
    
    # 3) Sonnet에게 질문
    prompt = f"""
다음 법령의 전체 조문을 보고, 이미 추출된 rule 목록에서 **놓친 의무**를 찾아주세요.

특히 아래 유형 중 누락된 게 있는지 집중:
- APPOINT: 선임 의무 (안전관리자, 소방안전관리자 등)
- INSPECT: 정기 점검/검사 의무
- NOTIFY: 신고/보고/제출 의무
- REPORT: 기록/보존 의무
- ACTION: 조치/설치/이행 의무

[법령명] {law_info["law_name"]}

[법령 전체 조문]
{full_law_text}

[이미 추출된 rule]
{rules_summary}

놓친 의무만 JSON array로 반환. 이미 추출된 것과 중복 금지.
형식은 기존 rule 생성 프롬프트와 동일.
놓친 게 없으면 [] 반환.
"""
    
    result = await _call_claude_messages(
        "법령 의무 누락 탐지 전문가. 정확한 추출만 반환.",
        prompt,
        CLAUDE_SONNET_MODEL,
        max_tokens=3000,
        timeout=120,
    )
    
    missing_rules = result if isinstance(result, list) else []
    
    # 4) 누락분을 PENDING 상태로 저장
    created = 0
    for rule in missing_rules:
        if rule.get("sector", "").upper() in EXCLUDED_SECTORS:
            continue
        
        draft_row = _build_draft_row(
            law_info["law_name"],
            rule.get("law_article", ""),
            None,  # article_id unknown
            rule.get("article_text", "")[:2000],
            rule,
        )
        draft_row["status"] = "PENDING"
        draft_row["ai_flags"] = ["missing_detected_by_sonnet"]
        
        supabase.table("law_rule_drafts").insert(draft_row).execute()
        created += 1
    
    return {
        "candidates_found": len(missing_rules),
        "drafts_created": created,
        "existing_rules_count": len(existing_rules),
    }
```

### 3-4. CROSSCHECK: 외부 소스 대조 (2일)

**구현 범위 (MVP):**

**3-4-1. 법제처 공식 "관련 서식" 대조**

```python
async def run_crosscheck(job: dict) -> dict:
    supabase = get_supabase()
    law_id = job["law_id"]
    law_info = _fetch_law_info(supabase, law_id)
    
    # 1) 법제처 API에서 해당 법령의 "별지 서식" 목록 조회
    # /lawService.do의 <별표정보> 섹션 파싱
    official_forms = await _fetch_official_forms(law_info["law_mst_no"])
    
    # 2) 우리 master rule의 form_code/form_name과 대조
    our_rules = supabase.table("master_building_legal_rules").select("rule_id, form_code, form_name")\
        .eq("law_name", law_info["law_name"])\
        .eq("is_active", True)\
        .execute().data or []
    
    our_form_codes = {r["form_code"] for r in our_rules if r.get("form_code")}
    
    # 3) 법제처에 있는데 우리가 참조 안 한 서식
    missing_forms = [
        f for f in official_forms 
        if f["form_code"] not in our_form_codes
    ]
    
    # 4) 결과를 ai_flags에 누적 (master 각 rule에 append 방식)
    if missing_forms:
        logger.warning(
            f"[crosscheck] {law_info['law_name']}에 법제처 서식 {len(missing_forms)}개 누락"
        )
        # 이슈 테이블에 기록 (수동 검토 대상)
        supabase.table("law_rule_drafts").insert({
            "law_name": law_info["law_name"],
            "obligation_summary": f"법제처 서식 {len(missing_forms)}개 누락 탐지",
            "ai_flags": ["crosscheck_missing_forms"],
            "status": "PENDING",
            "ai_reasoning": json.dumps(missing_forms, ensure_ascii=False),
        }).execute()
    
    return {
        "official_forms_count": len(official_forms),
        "our_forms_count": len(our_form_codes),
        "missing_forms_count": len(missing_forms),
        "missing_forms": missing_forms[:10],  # 샘플
    }
```

**3-4-2. KOSHA 체크리스트 (선택, 범위 크면 별도 이슈로)**

초기 MVP에는 **법제처 대조만** 구현. KOSHA는 별도 이슈로 분리.

### 3-5. 전체 재검증 배치 (0.5일)

Phase 1 재수집 완료 후, 기존 1,402개 master 전체를 검증 큐에 enqueue:

```python
# scripts/enqueue_full_reverify.py
"""기존 master 전체를 REVERIFY task로 큐에 삽입.
priority=80 (낮음)으로 며칠에 걸쳐 처리."""

from db.supabase_client import get_supabase
from services.validation_worker import enqueue_task

supabase = get_supabase()

# 법령별 MULTI_VERIFY enqueue (중복 제거)
laws = supabase.table("law_master").select("id").eq("is_active", True).execute().data

for law in laws:
    enqueue_task(
        supabase,
        task_type="MULTI_VERIFY",
        law_id=law["id"],
        priority=80,
        enqueued_by="full_reverify_batch",
    )

# 각 법령당 MISSING_DETECT도 추가
for law in laws:
    enqueue_task(
        supabase,
        task_type="MISSING_DETECT",
        law_id=law["id"],
        priority=85,
        enqueued_by="full_reverify_batch",
    )

# CROSSCHECK도
for law in laws:
    enqueue_task(
        supabase,
        task_type="CROSSCHECK",
        law_id=law["id"],
        priority=90,
        enqueued_by="full_reverify_batch",
    )

print(f"✅ {len(laws) * 3}개 task enqueue 완료")
```

### Phase 3 완료 기준

- [ ] `services/validation_tasks.py` 4개 핸들러 구현
- [ ] `tests/test_validation_tasks.py` 10개 이상 테스트 PASSED
- [ ] MULTI_VERIFY 샘플 법령 1건 실행 → auto_approved, needs_review 비율 합리적
- [ ] MISSING_DETECT 샘플 법령 1건 실행 → 누락 후보 >= 5건 탐지
- [ ] CROSSCHECK 샘플 법령 1건 실행 → 법제처 서식 매칭 동작
- [ ] 전체 재검증 큐 enqueue (약 1,100개 task, 우선순위 80~90)
- [ ] 1주일간 Worker 안정 실행 관찰 (Railway 로그)
- [ ] master 테이블의 `verification_level` 분포 점검

---

## 📦 통합 체크리스트

### 아키텍처
- [ ] 기존 `check_law_update()` 흐름 변경 없음
- [ ] 기존 알림(Push/SMS) 타이밍 변경 없음
- [ ] Worker 실패 시 본 파이프라인 영향 없음 (try/except 확인)
- [ ] Railway cron 2개 (check-updates-v2, process-validation-queue) 공존

### 품질
- [ ] 전체 pytest 통과 (기존 80개 + 신규 15~20개)
- [ ] services 레이어에 `from fastapi` 없음
- [ ] 모든 신규 파일 400줄 이내
- [ ] 신규 DB 컬럼 마이그레이션 rollback 스크립트 준비

### 운영
- [ ] `ai_validation_queue` 대시보드 쿼리 문서화
- [ ] Worker 모니터링: FAILED 3건 이상 누적 시 알림
- [ ] 비용 로깅: 법령당 MULTI_VERIFY 1회 = Haiku×N + Sonnet×N 호출
- [ ] Phase 1 재수집 전 DB 백업 확인

---

## 🚨 롤백 계획

### Phase 1 실패 시
- DB snapshot 복원
- `parse_law_content_xml()` 이전 버전으로 revert
- 재수집 중이었다면 모든 진행 중 version 삭제

### Phase 2 실패 시
- `save_law_to_db()`의 enqueue 1줄 주석 처리
- Railway cron 중단
- `ai_validation_queue` 테이블은 보존 (DROP 금지)

### Phase 3 실패 시
- 특정 task_type만 disable: `validation_tasks.py`의 dispatcher에서 제외
- Worker는 계속 실행 (다른 task type은 유효)

---

## 📎 관련 자료

- **Issue #37**: law_collector XML 파싱 파편화 (이 문서의 Phase 1 전체 대응)
- **PR #35**: sanitize_master_patch numeric 필드 확장 (배포됨)
- **PR #38**: INTERNAL_API_SECRET 로테이션 (배포됨)
- **이전 WORK_ORDER**: `docs/WORK_ORDER_REPARSE_SANITIZE_FIX.md`
- **DEV_RULES**: `docs/DEV_RULES_SERVICE_LAYER.md` v2 (400줄 룰, fastapi 금지 등)

---

## 💰 예상 비용 (Claude API)

| 항목 | 단가 추정 | 건수 | 소계 |
|---|---|---|---|
| Phase 1 재수집 | — (법제처 무료) | 373법령 | 0원 |
| Phase 3 MULTI_VERIFY | Haiku $0.01 + Sonnet $0.05 | 조문 24,000개 | 약 150만원 |
| Phase 3 MISSING_DETECT | Sonnet $0.10 (긴 프롬프트) | 373법령 | 약 50만원 |
| Phase 3 CROSSCHECK | API 호출 없음 (DB 대조) | 373법령 | 0원 |
| **합계** | | | **약 200만원** |

※ 실제 비용은 조문 분포/필드 채움도에 따라 변동. **Phase 3 실행 전 50법령으로 샘플 테스트 후 비용 extrapolate 권장.**

---

**문의:** 기획창(Claude Opus) — MCP로 DB 검증, PR 리뷰, 진행률 모니터링 지원
