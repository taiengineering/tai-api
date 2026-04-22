# 법령 수집 저장방식 설계 — 2026-04-22

> **방식 확정**: 하이브리드 (원본 TX1 + 파싱 TX2) + UPSERT + 상태 추적
> **원칙**: 원본 보존 최우선, 재실행 가능(idempotent), 유닛 단위 검증

---

## 🎯 핵심 원칙

```
1. 원본 XML은 무조건 먼저 저장 (복구 가능성)
2. 파싱 결과는 atomic (한 조문만 있고 나머지 없는 상태 방지)
3. UPSERT로 중복 원천 차단 (ON CONFLICT DO UPDATE)
4. 각 유닛 끝에 검증 체크리스트 실행
5. collection_status로 진행 추적 (재실행 가능)
6. 실패해도 원본은 남음 → 파서만 고쳐서 재파싱 가능
```

---

## 📊 저장 흐름 (유닛 1개 = 법령 1개)

```
┌─────────────────────────────────────────────────────────┐
│ Step 0. 시작                                             │
│ collection_status: PENDING → IN_PROGRESS                │
│ started_at 기록                                          │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 1. 법제처 API 호출                                  │
│ GET /DRF/lawService.do?OC=taieng&ID={law_api_id}&MST={mst}│
│ 실패 → status=FAILED, 종료                               │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ TX1: 원본 보존 (독립 트랜잭션) ⭐                        │
│  BEGIN                                                   │
│    UPSERT law_master_new                                │
│    UPSERT law_version_new                               │
│    INSERT law_content_raw_new (원본 XML)                │
│  COMMIT                                                  │
│                                                          │
│ 여기서 실패 → 전체 취소. 원본도 못 남음.                │
│ 여기서 성공 → 원본은 확실히 남음 (재파싱 가능)          │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 2. XML 파싱                                         │
│ 파싱 실패 → status=FAILED                                │
│           → 하지만 원본은 이미 TX1에서 저장됨 ⭐         │
│           → 나중에 파서만 개선해서 재파싱 가능           │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ TX2: 파싱 결과 저장 (atomic)                             │
│  BEGIN                                                   │
│    UPSERT law_article_new × N (조문)                    │
│    UPSERT law_paragraph_new × M (항)                    │
│    UPSERT law_item_new × K (호/목)                      │
│    UPSERT law_attachment_new × L (별표)                 │
│  COMMIT                                                  │
│                                                          │
│ 실패 → 파싱 결과 전체 롤백. 원본은 TX1에서 남음.        │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 3. 검증 체크리스트 실행                             │
│  ☐ API 호출 성공?                                        │
│  ☐ 원본 XML 저장?                                        │
│  ☐ 파싱 성공?                                            │
│  ☐ 조문수 합리적?                                        │
│  ☐ valid_pct ≥ 30%?                                      │
│  ☐ 별표/서식 수집?                                       │
│  ☐ 중복 없이 UPSERT?                                     │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│ Step 4. 상태 업데이트                                    │
│  collection_status: SUCCESS / FAILED                    │
│  last_collected_at = NOW()                              │
│  last_collection_result = {체크리스트 결과 JSONB}       │
│  verification_checklist = {상세 JSONB}                  │
└─────────────────────────────────────────────────────────┘
                    ↓
             다음 유닛 or 종료
```

---

## 🔧 UPSERT SQL 템플릿

### 1) law_master_new
```sql
INSERT INTO law_master_new (
  law_key, law_api_id, law_mst_no, law_name, 
  law_type_code, domain_code, ministry_name,
  law_number, announcement_date, enforcement_date,
  current_version_id, is_active
) VALUES (
  $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true
)
ON CONFLICT (law_api_id, law_mst_no) 
WHERE law_api_id IS NOT NULL AND law_mst_no IS NOT NULL
DO UPDATE SET
  law_name = EXCLUDED.law_name,
  law_type_code = EXCLUDED.law_type_code,
  domain_code = EXCLUDED.domain_code,
  ministry_name = EXCLUDED.ministry_name,
  announcement_date = EXCLUDED.announcement_date,
  enforcement_date = EXCLUDED.enforcement_date,
  current_version_id = EXCLUDED.current_version_id,
  updated_at = NOW()
RETURNING id;
```

### 2) law_version_new
```sql
INSERT INTO law_version_new (
  law_id, version_no, revision_type_code,
  announcement_date, enforcement_date,
  effective_from, version_status_code, is_current
) VALUES ($1, $2, $3, $4, $5, $6, 'ACTIVE', true)
ON CONFLICT (law_id, version_no)
WHERE version_no IS NOT NULL
DO UPDATE SET
  revision_type_code = EXCLUDED.revision_type_code,
  announcement_date = EXCLUDED.announcement_date,
  enforcement_date = EXCLUDED.enforcement_date,
  effective_from = EXCLUDED.effective_from,
  is_current = true,
  updated_at = NOW()
RETURNING id;
```

### 3) law_content_raw_new
```sql
INSERT INTO law_content_raw_new (
  law_version_id, raw_xml, content_hash, collected_at
) VALUES ($1, $2, $3, NOW())
ON CONFLICT (law_version_id)
WHERE law_version_id IS NOT NULL
DO UPDATE SET
  raw_xml = EXCLUDED.raw_xml,
  content_hash = EXCLUDED.content_hash,
  collected_at = NOW();
```

### 4) law_article_new
```sql
INSERT INTO law_article_new (
  law_version_id, article_internal_key,
  article_no, article_sub_no, article_no_sort,
  article_type, article_title, article_text,
  article_text_normalized, article_status_code
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (law_version_id, article_internal_key)
WHERE article_internal_key IS NOT NULL
DO UPDATE SET
  article_no = EXCLUDED.article_no,
  article_sub_no = EXCLUDED.article_sub_no,
  article_title = EXCLUDED.article_title,
  article_text = EXCLUDED.article_text,
  article_text_normalized = EXCLUDED.article_text_normalized,
  updated_at = NOW()
RETURNING id;
```

### 5) law_paragraph_new
```sql
INSERT INTO law_paragraph_new (
  article_id, paragraph_internal_key,
  paragraph_no, paragraph_no_sort,
  paragraph_text, paragraph_text_normalized,
  paragraph_status_code
) VALUES ($1, $2, $3, $4, $5, $6, 'ACTIVE')
ON CONFLICT (article_id, paragraph_internal_key)
WHERE paragraph_internal_key IS NOT NULL
DO UPDATE SET
  paragraph_no = EXCLUDED.paragraph_no,
  paragraph_text = EXCLUDED.paragraph_text,
  paragraph_text_normalized = EXCLUDED.paragraph_text_normalized,
  updated_at = NOW()
RETURNING id;
```

### 6) law_item_new
```sql
INSERT INTO law_item_new (
  paragraph_id, parent_item_id, item_internal_key,
  item_level_code, item_no, item_no_sort,
  item_text, item_text_normalized, item_status_code
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'ACTIVE')
ON CONFLICT (paragraph_id, item_internal_key)
WHERE item_internal_key IS NOT NULL
DO UPDATE SET
  parent_item_id = EXCLUDED.parent_item_id,
  item_level_code = EXCLUDED.item_level_code,
  item_no = EXCLUDED.item_no,
  item_text = EXCLUDED.item_text,
  item_text_normalized = EXCLUDED.item_text_normalized,
  updated_at = NOW()
RETURNING id;
```

### 7) law_attachment_new
```sql
INSERT INTO law_attachment_new (
  law_version_id, parent_article_id,
  attachment_type_code, attachment_no,
  attachment_title, attachment_text,
  attachment_raw, text_hash
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (law_version_id, attachment_no, attachment_type_code)
WHERE attachment_no IS NOT NULL AND attachment_type_code IS NOT NULL
DO UPDATE SET
  parent_article_id = EXCLUDED.parent_article_id,
  attachment_title = EXCLUDED.attachment_title,
  attachment_text = EXCLUDED.attachment_text,
  attachment_raw = EXCLUDED.attachment_raw,
  text_hash = EXCLUDED.text_hash,
  updated_at = NOW()
RETURNING id;
```

---

## 🐍 Python 수집 함수 Pseudocode

```python
import hashlib
from datetime import datetime
from typing import Optional
import psycopg2
import httpx

class LawCollector:
    """
    법령 수집기 — 유닛 단위 (법령 1개 = 1 유닛)
    """
    
    def __init__(self, conn, oc='taieng'):
        self.conn = conn
        self.oc = oc
        self.api_base = 'https://www.law.go.kr/DRF/lawService.do'
    
    def collect_one(self, target: dict) -> dict:
        """
        1개 법령 수집. target은 law_collection_target_new의 row.
        
        Returns:
          {
            'target_id': UUID,
            'status': 'SUCCESS' | 'FAILED',
            'checklist': {...},
            'error': Optional[str]
          }
        """
        result = {
            'target_id': target['id'],
            'status': 'FAILED',
            'checklist': {},
            'error': None,
            'started_at': datetime.now().isoformat()
        }
        
        # Step 0: 상태 업데이트
        self._update_status(target['id'], 'IN_PROGRESS')
        
        try:
            # Step 1: API 호출
            xml_raw, http_status = self._fetch_api(
                target['law_api_id'], 
                target['law_api_mst_no']
            )
            result['checklist']['api_call_success'] = True
            result['checklist']['http_status'] = http_status
            result['checklist']['response_size'] = len(xml_raw)
            
            # TX1: 원본 보존 (독립 트랜잭션)
            with self.conn.transaction():
                master_id = self._upsert_master(target, xml_raw)
                version_id = self._upsert_version(master_id, xml_raw)
                content_raw_id = self._save_content_raw(version_id, xml_raw)
            
            result['checklist']['xml_saved'] = True
            result['version_id'] = version_id
            
            # Step 2: 파싱
            parsed = self._parse_xml(xml_raw)
            result['checklist']['parsing_success'] = True
            result['checklist']['article_count'] = len(parsed['articles'])
            result['checklist']['attachment_count'] = len(parsed.get('attachments', []))
            
            # TX2: 파싱 결과 저장 (atomic)
            with self.conn.transaction():
                article_count = self._upsert_articles(version_id, parsed['articles'])
                paragraph_count = self._upsert_paragraphs(parsed['articles'])
                item_count = self._upsert_items(parsed['articles'])
                attachment_count = self._upsert_attachments(
                    version_id, parsed.get('attachments', [])
                )
            
            # Step 3: 검증 체크리스트
            result['checklist']['article_count_reasonable'] = (
                article_count >= (target.get('expected_article_count', 1) * 0.5)
                if target.get('expected_article_count') 
                else article_count > 0
            )
            result['checklist']['valid_pct'] = self._calc_valid_pct(
                version_id, article_count
            )
            result['checklist']['valid_pct_above_30'] = (
                result['checklist']['valid_pct'] >= 30.0
            )
            result['checklist']['no_duplicate_created'] = True  # UPSERT 사용
            
            # Step 4: 성공 판정
            if self._all_checks_pass(result['checklist']):
                result['status'] = 'SUCCESS'
            else:
                result['status'] = 'FAILED'
                result['error'] = '검증 체크리스트 일부 실패'
        
        except APIError as e:
            result['status'] = 'FAILED'
            result['error'] = f'API 오류: {e}'
            result['checklist']['api_call_success'] = False
        
        except ParseError as e:
            # 원본은 이미 저장됨. 파싱만 실패.
            result['status'] = 'FAILED'
            result['error'] = f'파싱 실패 (원본 보존됨): {e}'
            result['checklist']['parsing_success'] = False
        
        except Exception as e:
            result['status'] = 'FAILED'
            result['error'] = f'예상치 못한 오류: {e}'
        
        finally:
            # Step 4: 상태 최종 업데이트
            result['completed_at'] = datetime.now().isoformat()
            self._update_target_result(
                target['id'],
                status=result['status'],
                checklist=result['checklist'],
                error=result.get('error')
            )
        
        return result
    
    # ──────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────
    
    def _fetch_api(self, law_api_id, law_mst_no) -> tuple[str, int]:
        """법제처 API 호출. 실패 시 APIError."""
        params = {'OC': self.oc, 'ID': law_api_id, 'type': 'XML'}
        if law_mst_no:
            params['MST'] = law_mst_no
        
        response = httpx.get(self.api_base, params=params, timeout=30)
        if response.status_code != 200:
            raise APIError(f'HTTP {response.status_code}')
        if not response.text or len(response.text) < 100:
            raise APIError('응답 너무 짧음')
        return response.text, response.status_code
    
    def _upsert_master(self, target, xml_raw) -> UUID:
        """law_master_new UPSERT. id 반환."""
        # XML에서 메타데이터 추출
        meta = self._extract_master_meta(xml_raw)
        
        law_key = self._make_law_key(target['law_api_id'], meta['mst_no'])
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO law_master_new (
              law_key, law_api_id, law_mst_no, law_name,
              law_type_code, domain_code, ministry_name,
              announcement_date, enforcement_date, is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (law_api_id, law_mst_no)
            WHERE law_api_id IS NOT NULL AND law_mst_no IS NOT NULL
            DO UPDATE SET
              law_name = EXCLUDED.law_name,
              announcement_date = EXCLUDED.announcement_date,
              enforcement_date = EXCLUDED.enforcement_date,
              updated_at = NOW()
            RETURNING id
        """, (
            law_key, target['law_api_id'], meta['mst_no'], target['law_name'],
            target['law_type_code'], target['domain_code'], target['ministry_name'],
            meta['announcement_date'], meta['enforcement_date']
        ))
        return cursor.fetchone()[0]
    
    def _upsert_version(self, master_id, xml_raw) -> UUID:
        """law_version_new UPSERT."""
        meta = self._extract_version_meta(xml_raw)
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO law_version_new (
              law_id, version_no, revision_type_code,
              announcement_date, enforcement_date,
              effective_from, version_status_code, is_current
            ) VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', true)
            ON CONFLICT (law_id, version_no)
            WHERE version_no IS NOT NULL
            DO UPDATE SET
              revision_type_code = EXCLUDED.revision_type_code,
              announcement_date = EXCLUDED.announcement_date,
              enforcement_date = EXCLUDED.enforcement_date,
              is_current = true,
              updated_at = NOW()
            RETURNING id
        """, (
            master_id, meta['version_no'], meta['revision_type'],
            meta['announcement_date'], meta['enforcement_date'],
            meta['effective_from']
        ))
        version_id = cursor.fetchone()[0]
        
        # law_master_new.current_version_id 업데이트
        cursor.execute("""
            UPDATE law_master_new 
            SET current_version_id = %s, 
                current_version_no = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (version_id, meta['version_no'], master_id))
        
        return version_id
    
    def _save_content_raw(self, version_id, xml_raw) -> UUID:
        """원본 XML 저장. UPSERT (버전당 1개)."""
        content_hash = hashlib.sha256(xml_raw.encode()).hexdigest()
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO law_content_raw_new (
              law_version_id, raw_xml, content_hash, collected_at
            ) VALUES (%s, %s, %s, NOW())
            ON CONFLICT (law_version_id)
            WHERE law_version_id IS NOT NULL
            DO UPDATE SET
              raw_xml = EXCLUDED.raw_xml,
              content_hash = EXCLUDED.content_hash,
              collected_at = NOW()
            RETURNING id
        """, (version_id, xml_raw, content_hash))
        return cursor.fetchone()[0]
    
    def _parse_xml(self, xml_raw) -> dict:
        """XML 파싱. 기존 Pilot 1+2+3 개선 로직 재사용."""
        # ... 파싱 로직 ...
        return {
            'articles': [...],
            'attachments': [...]
        }
    
    def _upsert_articles(self, version_id, articles) -> int:
        """조문 UPSERT. 개수 반환."""
        count = 0
        for article in articles:
            internal_key = self._make_article_key(
                article['no'], article.get('sub_no')
            )
            # ... UPSERT ...
            count += 1
        return count
    
    # ... paragraphs, items, attachments UPSERT 함수들 ...
    
    def _calc_valid_pct(self, version_id, article_count) -> float:
        """valid_pct 계산 — 파싱 품질 지표."""
        # 조문 중 article_text가 유의미한 비율
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
              COUNT(*) FILTER (WHERE LENGTH(article_text) > 20) * 100.0 / 
              NULLIF(COUNT(*), 0) AS valid_pct
            FROM law_article_new
            WHERE law_version_id = %s
        """, (version_id,))
        result = cursor.fetchone()
        return float(result[0]) if result[0] else 0.0
    
    def _all_checks_pass(self, checklist) -> bool:
        """모든 체크 통과 여부."""
        required_checks = [
            'api_call_success',
            'xml_saved',
            'parsing_success',
            'article_count_reasonable',
            'valid_pct_above_30'
        ]
        return all(checklist.get(k, False) for k in required_checks)
    
    def _update_status(self, target_id, status):
        """collection_status만 빠르게 업데이트."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE law_collection_target_new
            SET collection_status = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (status, target_id))
        self.conn.commit()
    
    def _update_target_result(self, target_id, status, checklist, error):
        """수집 완료 후 최종 결과 업데이트."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE law_collection_target_new
            SET 
              collection_status = %s,
              last_collected_at = NOW(),
              last_collection_result = %s,
              verification_checklist = %s,
              remarks = COALESCE(remarks, '') || CASE 
                WHEN %s IS NOT NULL THEN ' | ' || %s 
                ELSE '' 
              END,
              updated_at = NOW()
            WHERE id = %s
        """, (
            status, 
            json.dumps(checklist),
            json.dumps(checklist),
            error, error,
            target_id
        ))
        self.conn.commit()


# ═══════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════
def main():
    conn = psycopg2.connect(DATABASE_URL)
    collector = LawCollector(conn)
    
    # 타겟 조회 (status=PENDING만)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
          id, law_name, law_type_code, domain_code, 
          law_api_id, law_api_mst_no, ministry_name,
          expected_article_count
        FROM law_collection_target_new
        WHERE is_active = true 
          AND collection_status = 'PENDING'
          AND law_api_id IS NOT NULL
        ORDER BY collection_priority, added_in_phase, law_name
    """)
    targets = cursor.fetchall()
    
    total = len(targets)
    success_count = 0
    fail_count = 0
    
    for idx, row in enumerate(targets, 1):
        target = {
            'id': row[0], 'law_name': row[1], 
            'law_type_code': row[2], 'domain_code': row[3],
            'law_api_id': row[4], 'law_api_mst_no': row[5],
            'ministry_name': row[6], 
            'expected_article_count': row[7]
        }
        
        print(f'[{idx}/{total}] {target["law_name"]} 수집 중...')
        result = collector.collect_one(target)
        
        if result['status'] == 'SUCCESS':
            success_count += 1
            print(f'  ✅ 성공 (valid_pct: {result["checklist"].get("valid_pct", 0):.1f}%)')
        else:
            fail_count += 1
            print(f'  ❌ 실패: {result.get("error", "unknown")}')
    
    print(f'\n전체 {total}개 중 성공 {success_count}, 실패 {fail_count}')
    conn.close()


if __name__ == '__main__':
    main()
```

---

## 🔁 재실행 시나리오 (idempotent 확인)

### 시나리오 1: 처음부터 실행
```
모든 타겟 status='PENDING'
→ 184개 전부 수집 시도
→ 성공: SUCCESS, 실패: FAILED
```

### 시나리오 2: 중간에 중단 → 재실행
```
일부 SUCCESS, 일부 IN_PROGRESS(중단), 나머지 PENDING
→ WHERE collection_status = 'PENDING' 쿼리로 나머지만 수집
→ IN_PROGRESS는 수동 확인 후 재실행
→ UPSERT라 중복 안 생김
```

### 시나리오 3: 일부 FAILED만 재시도
```
SQL:
UPDATE law_collection_target_new 
SET collection_status = 'PENDING' 
WHERE collection_status = 'FAILED';

→ FAILED였던 것만 재시도
→ 이전 수집 데이터는 그대로 유지 (UPSERT)
```

### 시나리오 4: 파서 개선 후 재파싱만
```
-- 원본(law_content_raw_new)은 유지
-- 파싱 결과만 삭제
BEGIN;
  DELETE FROM law_article_new WHERE law_version_id IN (...);
  -- CASCADE로 paragraph, item도 삭제됨
  
  -- 원본에서 다시 파싱 실행
  UPDATE law_collection_target_new 
  SET collection_status = 'PENDING'
  WHERE id IN (...);
COMMIT;

→ API 호출 안 하고 원본에서 재파싱
→ 속도 10배 빠름
```

---

## 📊 수집 진행 모니터링 SQL

### 전체 진행률
```sql
SELECT 
  collection_status,
  COUNT(*) AS 개수,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS 비율
FROM law_collection_target_new
WHERE is_active = true
GROUP BY collection_status
ORDER BY collection_status;
```

### 도메인별 성공률
```sql
SELECT 
  domain_code,
  COUNT(*) FILTER (WHERE collection_status = 'SUCCESS') AS 성공,
  COUNT(*) FILTER (WHERE collection_status = 'FAILED') AS 실패,
  COUNT(*) FILTER (WHERE collection_status = 'PENDING') AS 대기,
  COUNT(*) AS 전체,
  ROUND(
    COUNT(*) FILTER (WHERE collection_status = 'SUCCESS') * 100.0 / 
    NULLIF(COUNT(*), 0), 1
  ) AS 성공률
FROM law_collection_target_new
WHERE is_active = true
GROUP BY domain_code
ORDER BY 성공률 DESC;
```

### 검증 실패 세부 분석
```sql
SELECT 
  law_name,
  ministry_name,
  verification_checklist -> 'valid_pct' AS valid_pct,
  verification_checklist -> 'article_count' AS article_count,
  remarks
FROM law_collection_target_new
WHERE collection_status = 'FAILED'
ORDER BY added_in_phase, law_name;
```

---

## ⚠️ 주의 사항

### 1. API 호출 속도 제한
```
법제처 API는 일반적으로 제한이 있음
→ 요청 간 500ms~1s 대기 필요
→ Python `time.sleep(0.5)` 또는 httpx rate limiter 사용
```

### 2. OC=taieng IP 제한
```
등록 IP: 115.68.227.222 (공인 IP)
→ 로컬 실행 (사용자님 PC)에서만 작동
→ Railway 서버에서는 DATA_GOV_SERVICE_KEY 필요
```

### 3. 트랜잭션 크기
```
TX2 (파싱 결과 저장)는 조문 많은 법령일 경우 큼:
- 대기환경보전법 시행규칙: 718조문 + 항/호/목 = 수천 개
- 한 트랜잭션에 다 넣어도 PostgreSQL은 문제 없음
- 단, 네트워크 끊김 시 전체 롤백
```

### 4. 파싱 실패 시 처리
```
XML 받았지만 파싱 실패:
1. 원본은 law_content_raw_new에 저장됨 ⭐
2. status=FAILED, error='파싱 실패 (원본 보존됨)'
3. 나중에 파서 개선 후 재파싱 가능
4. 법제처에 재요청 불필요 (원본 있음)
```

---

## 🔗 다음 세션 시작 시

### Cursor(작업창)에서 할 일
```
1. scripts/all_laws_recollect_v2.py 파일 생성
2. 이 문서의 pseudocode를 실제 Python으로 구현
3. Pilot 1+2+3의 파싱 로직 import
4. 로컬(~/dev/tai-api)에서 실행
5. 진행상황 실시간 모니터링 (SQL 쿼리)
```

### 기획창(Claude)에서 할 일
```
1. 실행 결과 MCP로 모니터링
2. FAILED 케이스 분석
3. 필요 시 파서 개선 방향 조언
4. 유닛별 검증 상세 리뷰
```

### 실행 예상
```
- 184개 타겟
- 유닛당 3~10초 (API 호출 + 파싱 + 저장)
- 평균 5초 가정 시: 184 × 5초 = 약 15분
- Rate limit 대기 포함 시: 약 20~30분
```

---

## 📌 체크리스트 — 수집 실행 직전 확인

```
☐ law_collection_target_new에 184개 타겟 있음
☐ _new 테이블 8개 모두 빈 구조 상태
☐ UNIQUE 제약 10개 설정됨
☐ FK 9개 CASCADE로 연결됨
☐ 법제처 OC=taieng IP 등록됨 (115.68.227.222)
☐ Python 스크립트 작성됨
☐ DATABASE_URL 환경변수 설정됨
☐ 실행 전 백업 테이블 확인
```
