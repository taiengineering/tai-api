---
wo: WO-REF05-CMS-CONTRACT-FINALIZATION-003
date: 2026-10-11
status: CONTRACT_FINAL_READY
section: OBJ-REF-05
publication: NOT_FOR_PUBLICATION
dependency: OBJ-REF-08 (BLOCKED)
parent: WO-REF05-CMS-DESIGN-REPAIR-002.md
next_gate: GPT_REF05_IMPLEMENTATION_CONTRACT_VERIFY
scope: DOCS ONLY — 운영 DB DDL·데이터·OpenSearch·배포·PR merge·외부공개 금지
---

# REF-05 CMS 계약 최종 정합화 (v3 — FINALIZATION)

WO-REF05-CMS-CONTRACT-FINALIZATION-003.

GPT_REF05_CMS_DETAIL_DESIGN_VERIFY_R2 HOLD 판정 결함 해소.
기존 아키텍처 유지, 실행 가능한 SQL·API 계약으로 완성.

---

## 1. v2 대비 교정 Diff 요약

| 항목 | v2 (REPAIR-002) | v3 (이번 문서) |
|------|----------------|---------------|
| 테이블 수 | 9 + 3(신규) — 명시 미완 | **12개 전체 목록 + 생성 순서 확정** |
| content_hash DDL | RPC에서 참조하나 컬럼 정의 없음 | **reference_form_content.content_hash 컬럼 + 갱신 트리거 정의** |
| 게시 RPC | content_hash 1개 비교 | **7-gate: 콘텐츠·파일·권리·미리보기·Owner·승인·상태 전이 전부** |
| slug 변경 RPC | registry 갱신 미포함 | **registry 원자적 갱신 + 동일 form_id 과거 slug 재사용 금지** |
| 스트리밍 | StreamingResponse(iter_chunks) — 실제 메모리 적재 명시 없음 | **storage3 SDK 메모리 적재 제약 명시 + 20MB 상한 + 대안 결정** |
| 미리보기 캐시 | `Cache-Control: public, max-age=3600` | **`Cache-Control: no-store` — 공개 취소 즉시 차단** |
| public view | 게시 상태만 확인 | **승인 버전 일치 + 파일 QA 게이트 포함** |
| 검색 연동 | `_SECTION_TYPES` / `TYPE_ALLOWLIST` 수정 없음 | **`reference-form` 타입명 3곳 동시 추가** |
| sitemap updated_at | view에 없는 컬럼 참조 | **`GREATEST(rf.updated_at, rfc.updated_at)` 컬럼 추가** |

---

## 2. 12개 테이블 전체 목록 및 생성 순서

생성 순서는 FK 의존성 기준. 삭제는 역순.

| 순서 | 테이블명 | 역할 |
|------|---------|------|
| 1 | `reference_forms` | 핵심 식별자·게시 상태 |
| 2 | `reference_form_content` | 언어별 내용·slug·content_hash |
| 3 | `reference_form_slug_history` | slug 변경 이력 (301 redirect 근거) |
| 4 | `reference_form_slug_registry` | 전역 slug 예약 (충돌 방어선) |
| 5 | `reference_form_files` | 첨부 파일·QA·SHA256 |
| 6 | `reference_form_preview_artifacts` | 파생 미리보기 파일 |
| 7 | `reference_form_sources` | 출처·이용권 |
| 8 | `reference_form_relations` | 서식 간 연관 관계 |
| 9 | `reference_form_legacy_links` | REF-C### 레거시 코드 |
| 10 | `reference_form_aliases` | URL 별칭 (redirect) |
| 11 | `reference_form_approvals` | Owner 승인 버전 바인딩 |
| 12 | `reference_form_events` | 감사 로그 (불변) |

**삭제 정책 (전 테이블):**
- `ON DELETE RESTRICT` — 부모 서식 삭제 전 모든 자식 행 제거 필요
- `reference_forms` 직접 삭제 금지 — `ARCHIVED` 상태 전이로 대체

---

## 3. DDL 교정 — reference_form_content (content_hash 추가)

```sql
-- 이전 DDL에서 content_hash 컬럼 추가 + 갱신 트리거

ALTER TABLE public.reference_form_content
    ADD COLUMN content_hash TEXT;

-- content_hash 자동 계산 트리거
-- 입력: canonical_slug || title || COALESCE(description,'') || COALESCE(body_html,'')
-- 직렬화: 순서 고정, 구분자 '\x1F' (Unit Separator), UTF-8
CREATE OR REPLACE FUNCTION public.fn_reference_form_content_hash()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    NEW.content_hash = encode(
        digest(
            NEW.canonical_slug
            || E'\x1F' || NEW.title
            || E'\x1F' || COALESCE(NEW.description, '')
            || E'\x1F' || COALESCE(NEW.body_html, ''),
            'sha256'
        ),
        'hex'
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER reference_form_content_hash_update
    BEFORE INSERT OR UPDATE ON public.reference_form_content
    FOR EACH ROW EXECUTE FUNCTION public.fn_reference_form_content_hash();
```

**해시 입력 직렬화 규칙:**
1. 필드 순서 고정: `canonical_slug`, `title`, `description`, `body_html`
2. NULL → 빈 문자열로 정규화 (`COALESCE`)
3. 구분자: `\x1F` (ASCII Unit Separator, 콘텐츠 내 출현 불가)
4. PostgreSQL `digest()` = pgcrypto 확장 필요 (`CREATE EXTENSION IF NOT EXISTS pgcrypto`)
5. 결과: hex 인코딩 64자 문자열 (`sha256_chk` regex 동일)

---

## 4. 교정된 rpc_publish_reference_form (7-gate)

```sql
CREATE OR REPLACE FUNCTION public.rpc_publish_reference_form(
    p_form_id   UUID,
    p_actor     TEXT,
    p_payload   JSONB DEFAULT '{}'
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_event_id          UUID;
    v_approval          RECORD;
    v_current_hash      TEXT;
    v_file_rec          RECORD;
    v_file_hash_row     JSONB;
    v_rights_block      BOOLEAN;
    v_preview_required  BOOLEAN := false;  -- REF-08 QA 완료 후 true로 전환
BEGIN
    -- ── GATE-1: form이 DRAFT 상태인지 확인 ─────────────────────────────
    IF NOT EXISTS (
        SELECT 1 FROM public.reference_forms
         WHERE id = p_form_id AND status = 'DRAFT'
    ) THEN
        RAISE EXCEPTION 'PUBLISH_GATE1_FAIL: form not in DRAFT state';
    END IF;

    -- ── GATE-2: 유효한 Owner 승인 레코드 조회 ───────────────────────────
    SELECT * INTO v_approval
      FROM public.reference_form_approvals
     WHERE form_id = p_form_id
       AND is_current = true
       AND approval_status = 'APPROVED';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'PUBLISH_GATE2_FAIL: no current APPROVED approval record';
    END IF;

    -- ── GATE-3: 현재 content_hash == 승인 당시 content_hash ─────────────
    SELECT content_hash INTO v_current_hash
      FROM public.reference_form_content
     WHERE form_id = p_form_id
     LIMIT 1;

    IF v_current_hash IS DISTINCT FROM v_approval.approved_content_hash THEN
        RAISE EXCEPTION
            'PUBLISH_GATE3_FAIL: content changed after approval (current=%, approved=%)',
            v_current_hash, v_approval.approved_content_hash;
    END IF;

    -- ── GATE-4: 활성 파일의 SHA256 + QA 상태 검증 ──────────────────────
    -- 승인 당시 파일 목록: v_approval.approved_file_hashes (jsonb array of {file_id, sha256})
    FOR v_file_rec IN
        SELECT id, sha256_checksum, qa_status, approved_at
          FROM public.reference_form_files
         WHERE form_id = p_form_id
           AND is_active = true
    LOOP
        IF v_file_rec.qa_status <> 'QA_PASS' THEN
            RAISE EXCEPTION
                'PUBLISH_GATE4_FAIL: file % qa_status=% (expected QA_PASS)',
                v_file_rec.id, v_file_rec.qa_status;
        END IF;

        IF v_file_rec.approved_at IS NULL THEN
            RAISE EXCEPTION
                'PUBLISH_GATE4_FAIL: file % not individually approved',
                v_file_rec.id;
        END IF;

        -- SHA256 일치 검증 (승인된 해시 vs 현재 파일 해시)
        SELECT value INTO v_file_hash_row
          FROM jsonb_array_elements(v_approval.approved_file_hashes)
         WHERE (value->>'file_id')::uuid = v_file_rec.id
         LIMIT 1;

        IF v_file_hash_row IS NULL THEN
            RAISE EXCEPTION
                'PUBLISH_GATE4_FAIL: file % not in approved_file_hashes (added after approval)',
                v_file_rec.id;
        END IF;

        IF (v_file_hash_row->>'sha256') IS DISTINCT FROM v_file_rec.sha256_checksum THEN
            RAISE EXCEPTION
                'PUBLISH_GATE4_FAIL: file % sha256 mismatch (file changed after approval)',
                v_file_rec.id;
        END IF;
    END LOOP;

    -- ── GATE-5: 출처 권리 검토 통과 확인 ────────────────────────────────
    SELECT EXISTS (
        SELECT 1 FROM public.reference_form_sources
         WHERE form_id = p_form_id
           AND rights_status IN ('REVIEW_REQUIRED', 'BLOCKED')
    ) INTO v_rights_block;

    IF v_rights_block THEN
        RAISE EXCEPTION
            'PUBLISH_GATE5_FAIL: one or more sources have rights_status REVIEW_REQUIRED or BLOCKED';
    END IF;

    -- ── GATE-6: 미리보기 QA (v_preview_required = true 일 때 강제) ───────
    IF v_preview_required THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.reference_form_preview_artifacts
             WHERE form_id = p_form_id
               AND is_published = true
               AND qa_status = 'QA_PASS'
        ) THEN
            RAISE EXCEPTION
                'PUBLISH_GATE6_FAIL: no published QA_PASS preview artifact';
        END IF;
    END IF;

    -- ── GATE-7: 상태 전이 수행 ──────────────────────────────────────────
    UPDATE public.reference_forms
       SET status       = 'PUBLISHED',
           published_at = now(),
           owner_approved    = true,
           owner_approved_at = now()
     WHERE id = p_form_id
       AND status = 'DRAFT';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'PUBLISH_GATE7_FAIL: concurrent state change detected';
    END IF;

    -- ── 감사 이벤트 기록 ────────────────────────────────────────────────
    INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
    VALUES (p_form_id, 'PUBLISHED', p_actor,
            p_payload || jsonb_build_object(
                'approval_id', v_approval.id,
                'content_hash', v_current_hash
            ))
    RETURNING id INTO v_event_id;

    -- ── Outbox enqueue (동일 트랜잭션) ─────────────────────────────────
    PERFORM public.enqueue_search_index_sync(
        'REFERENCE_FORM',
        'REFERENCE_FORM',
        p_form_id::text,
        'reference_form:' || p_form_id::text || ':' || v_event_id::text,
        'PUBLISHED'
    );

    RETURN v_event_id;
END;
$$;
```

**GATE 실패 시:** 모든 게이트 예외는 트랜잭션 전체를 ROLLBACK. `status`, `events`, `outbox` 모두 변경 없음.

**v_preview_required 플래그:**
- 현재: `false` — REF-08 Content Factory QA BLOCKED 상태이므로 미리보기 없어도 게시 가능
- REF-08 해소 후: `true` 로 전환 (마이그레이션으로 상수 교체 또는 별도 설정 테이블)

---

## 5. 교정된 rpc_change_slug_reference_form (Registry 원자성)

```sql
CREATE OR REPLACE FUNCTION public.rpc_change_slug_reference_form(
    p_form_id   UUID,
    p_new_slug  TEXT,
    p_actor     TEXT
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_old_slug  TEXT;
    v_event_id  UUID;
    v_reg_type  TEXT;
BEGIN
    -- 1. 현재 canonical slug 조회
    SELECT canonical_slug INTO v_old_slug
      FROM public.reference_form_content
     WHERE form_id = p_form_id
     LIMIT 1;

    IF v_old_slug IS NULL THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAIL: no content row for form_id %', p_form_id;
    END IF;

    IF v_old_slug = p_new_slug THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAIL: new slug identical to current slug';
    END IF;

    -- 2. 동일 form_id의 과거 slug 재사용 금지
    --    (같은 서식이 한 번 사용했던 slug를 다시 canonical로 되돌리는 것 금지)
    IF EXISTS (
        SELECT 1 FROM public.reference_form_slug_registry
         WHERE slug = p_new_slug
           AND form_id = p_form_id
           AND slug_type = 'HISTORY'
    ) THEN
        RAISE EXCEPTION
            'SLUG_CHANGE_FAIL: cannot reuse a past slug (%) on the same form', p_new_slug;
    END IF;

    -- 3. 전역 충돌 검사 (다른 서식 또는 다른 타입)
    SELECT slug_type INTO v_reg_type
      FROM public.reference_form_slug_registry
     WHERE slug = p_new_slug
     LIMIT 1;

    IF v_reg_type IS NOT NULL THEN
        -- 자기 자신의 현재 CANONICAL인 경우만 업데이트 허용 (slug 재확인 없는 중복 호출)
        IF NOT (v_reg_type = 'CANONICAL' AND EXISTS (
            SELECT 1 FROM public.reference_form_slug_registry
             WHERE slug = p_new_slug AND form_id = p_form_id AND slug_type = 'CANONICAL'
        )) THEN
            RAISE EXCEPTION
                'SLUG_CHANGE_FAIL: slug (%) already registered as % by another form',
                p_new_slug, v_reg_type;
        END IF;
    END IF;

    -- 4. slug registry: 기존 CANONICAL → HISTORY 전환
    UPDATE public.reference_form_slug_registry
       SET slug_type = 'HISTORY'
     WHERE slug = v_old_slug
       AND form_id = p_form_id
       AND slug_type = 'CANONICAL';

    -- 5. slug registry: 새 slug → CANONICAL 등록
    --    ON CONFLICT는 최종 방어선 — 동시 실행 경쟁 차단
    INSERT INTO public.reference_form_slug_registry (slug, form_id, slug_type)
    VALUES (p_new_slug, p_form_id, 'CANONICAL')
    ON CONFLICT (slug) DO NOTHING;

    -- 6. 실제 INSERT 성공 여부 확인 (ON CONFLICT DO NOTHING 으로 silent fail 방지)
    IF NOT EXISTS (
        SELECT 1 FROM public.reference_form_slug_registry
         WHERE slug = p_new_slug AND form_id = p_form_id AND slug_type = 'CANONICAL'
    ) THEN
        RAISE EXCEPTION
            'SLUG_CHANGE_FAIL: registry insert blocked by concurrent write for slug (%)', p_new_slug;
    END IF;

    -- 7. reference_form_content 갱신
    UPDATE public.reference_form_content
       SET canonical_slug = p_new_slug
     WHERE form_id = p_form_id;

    -- 8. slug_history 기록
    INSERT INTO public.reference_form_slug_history (form_id, lang, old_slug, new_slug)
    VALUES (p_form_id, 'ko', v_old_slug, p_new_slug)
    ON CONFLICT (old_slug) DO NOTHING;

    -- 9. 승인 무효화: slug 변경은 content_hash 재계산을 유발
    --    (트리거가 content_hash 갱신 → 기존 approval의 approved_content_hash 불일치)
    --    → rpc_publish 호출 시 GATE-3에서 자동 차단됨 (추가 처리 불필요)

    -- 10. 감사 이벤트 + Outbox
    INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
    VALUES (p_form_id, 'SLUG_CHANGED', p_actor,
            jsonb_build_object('old_slug', v_old_slug, 'new_slug', p_new_slug))
    RETURNING id INTO v_event_id;

    PERFORM public.enqueue_search_index_sync(
        'REFERENCE_FORM',
        'REFERENCE_FORM',
        p_form_id::text,
        'reference_form:' || p_form_id::text || ':' || v_event_id::text,
        'SLUG_CHANGED'
    );

    RETURN v_event_id;
END;
$$;
```

**slug 변경 → content_hash 재계산 흐름:**
1. `UPDATE reference_form_content SET canonical_slug = p_new_slug` 실행
2. `BEFORE UPDATE` 트리거 `fn_reference_form_content_hash()` 가 자동 실행
3. 새 `content_hash = SHA256(new_slug || title || description || body_html)` 계산
4. 결과: 기존 `approval.approved_content_hash != new content_hash`
5. → 다음 `rpc_publish_reference_form` 호출 시 GATE-3 실패 → 재승인 필요

---

## 6. 스트리밍 제약 명시 및 결정

### storage3 SDK v2.32.0 제약

```python
# /opt/homebrew/lib/python3.14/site-packages/storage3/_sync/file_api.py L459-491
def download(self, path: str, ...) -> bytes:
    ...
    return response.content   # 전체 파일을 bytes로 반환 — 네이티브 스트리밍 없음
```

**확인된 사실:** `storage3.SyncBucketFileAPI.download()` 는 `bytes` 를 반환한다. 청크 스트리밍 메서드가 없다. `StreamingResponse(iter_chunks(data))` 를 사용해도 `data` 생성 시점에 전체 파일이 서버 메모리에 적재된다.

### 선택

| 방식 | 설명 | 서버 메모리 | 선택 |
|------|------|------------|------|
| A-MEM | `bytes` 전체 적재 + `StreamingResponse` | 파일 크기 × 1회 | **현행 채택** |
| A-STREAM | httpx 직접 스트리밍 (Storage URL + auth token 추출) | 청크 단위 | 별도 WO (SDK 내부 구현 의존) |
| B | 서버 서명 후 30초 Signed URL 발급 + 클라이언트 redirect | 없음 | URL 노출 허용 시 대안 |

**현행 계약 (A-MEM):**
- 파일 크기 상한: 20MB (`storage.buckets` 설정)
- 20MB × 동시 요청 수 = 서버 메모리 비용 — 운영 모니터링 필요
- `Response(content=data)` → `StreamingResponse(iter_chunks(data))` 으로 전달 효율 개선 (TCP 청킹)은 유효하나 서버 메모리 절감 효과는 없음
- 진정한 메모리 스트리밍은 별도 WO에서 httpx 직접 스트리밍 또는 Method B 전환으로 해결

**코드 주석 (명시 의무):**

```python
# MEMORY_LOAD: storage3 v2.32.0 does not support streaming.
# Full file is loaded into memory before response is sent.
# Max file size 20MB is enforced by bucket configuration.
data: bytes = supabase.storage.from_(bucket).download(path)
```

---

## 7. 미리보기 Cache-Control 교정

**이전:** `Cache-Control: public, max-age=3600` — 공개 취소 후 1시간 캐시 제공 가능

**교정:** `Cache-Control: no-store` — 매 요청 서버에서 DB 게시 상태 재확인

```python
return StreamingResponse(
    content=iter_chunks(preview_data),
    media_type="application/pdf",
    headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
        "Cache-Control": "no-store",          # 공개 취소 즉시 차단
        "X-Content-Type-Options": "nosniff",
        "X-Accel-Buffering": "no",            # Nginx buffering 방지
    },
)
```

**다운로드 API도 동일:** `Cache-Control: no-store`

---

## 8. 교정된 reference_form_public_view

```sql
CREATE OR REPLACE VIEW public.reference_form_public_view
WITH (security_invoker = true)   -- RLS 우회 방지
AS
SELECT
    rf.id,
    rfc.canonical_slug,
    rfc.title,
    rfc.description,
    rfc.body_html,
    rfc.content_hash,
    rf.published_at,
    GREATEST(rf.updated_at, rfc.updated_at) AS updated_at,  -- sitemap lastmod 기준

    -- 게시 승인 일치 검증 (콘텐츠 버전 경계)
    ra.id                    AS approval_id,
    ra.approved_content_hash,
    (rfc.content_hash = ra.approved_content_hash) AS content_approved,

    -- 활성·QA 통과·개별 승인된 파일 목록
    ARRAY(
        SELECT jsonb_build_object(
            'id',           rff.id,
            'format',       rff.format,
            'display_name', rff.display_name,
            'mime_type',    rff.mime_type,
            'sort_order',   rff.sort_order
        )
          FROM public.reference_form_files rff
         WHERE rff.form_id = rf.id
           AND rff.is_active = true
           AND rff.qa_status = 'QA_PASS'
           AND rff.approved_at IS NOT NULL
         ORDER BY rff.sort_order, rff.created_at
    ) AS files,

    -- format 목록 (검색 색인용)
    ARRAY(
        SELECT DISTINCT rff.format
          FROM public.reference_form_files rff
         WHERE rff.form_id = rf.id
           AND rff.is_active = true
           AND rff.qa_status = 'QA_PASS'
    ) AS formats,

    -- 레거시 코드 목록 (검색 별칭용)
    ARRAY(
        SELECT rfl.legacy_code
          FROM public.reference_form_legacy_links rfl
         WHERE rfl.form_id = rf.id
    ) AS legacy_codes

  FROM public.reference_forms rf
  JOIN public.reference_form_content rfc
       ON rfc.form_id = rf.id
       AND rfc.lang = 'ko'                  -- 언어 중복 방지
  JOIN public.reference_form_approvals ra
       ON ra.form_id = rf.id
       AND ra.is_current = true
       AND ra.approval_status = 'APPROVED'  -- Owner 승인 필수
 WHERE rf.status = 'PUBLISHED'
   AND rfc.content_hash = ra.approved_content_hash;  -- 승인된 버전만
```

**`security_invoker = true` 계약:**
- Supabase에서 뷰는 기본적으로 `security_definer` — 생성자 권한으로 실행
- `WITH (security_invoker = true)` 로 호출자(service_role) 권한 기준 RLS 적용
- 내부 저장 경로(`file_ref`)와 SHA256 등 비공개 정보는 뷰에서 제외됨

---

## 9. 검색·SEO·사이트맵 연결 완성

### 9.1 public_safety_search.py 수정 (tai-api)

```python
# routers/public_safety_search.py

_PUBLIC_OBJECT_TYPES: list[str] = [
    "GUIDE",
    "SAFETY_MATERIAL",
    "CSI_ACCIDENT",
    "CHEM",
    "CHEM_REGULATION",
    "KNOWLEDGE",
    "PRECEDENT",
    "LEGAL",
    "REFERENCE_FORM",    # 추가
]

_TYPE_MAP: dict[str, list[str]] = {
    "guide":            ["GUIDE"],
    "material":         ["SAFETY_MATERIAL"],
    "accident":         ["CSI_ACCIDENT"],
    "chem":             ["CHEM"],
    "keco":             ["CHEM_REGULATION"],
    "chem_regulation":  ["CHEM_REGULATION"],
    "knowledge":        ["KNOWLEDGE"],
    "precedent":        ["PRECEDENT"],
    "law":              ["LEGAL"],
    "legal":            ["LEGAL"],
    "reference-form":   ["REFERENCE_FORM"],  # 추가 — 타입명 통일
}
```

### 9.2 _SECTION_TYPES 추가 (sections 엔드포인트)

```python
_SECTION_TYPES: list[tuple[str, str]] = [
    ("knowledge",       "KNOWLEDGE"),
    ("guide",           "GUIDE"),
    ("law",             "LEGAL"),
    ("accident",        "CSI_ACCIDENT"),
    ("material",        "SAFETY_MATERIAL"),
    ("chem",            "CHEM"),
    ("keco",            "CHEM_REGULATION"),
    ("precedent",       "PRECEDENT"),
    ("reference-form",  "REFERENCE_FORM"),  # 추가
]
```

### 9.3 safetySearch.js 수정 (tai-www)

```js
// src/lib/server/safetySearch.js

export const TYPE_ALLOWLIST = Object.freeze([
  'all',
  'guide',
  'material',
  'accident',
  'chem',
  'keco',
  'knowledge',
  'precedent',
  'law',
  'kosha',
  'reference-form',   // 추가 — API _TYPE_MAP 키와 일치
]);

export const GROUP_DEFS = Object.freeze([
  { type: 'knowledge',      objectType: 'KNOWLEDGE',       label: '지식센터'           },
  { type: 'guide',          objectType: 'GUIDE',           label: '안전가이드'         },
  { type: 'law',            objectType: 'LEGAL',           label: '법령'               },
  { type: 'accident',       objectType: 'CSI_ACCIDENT',    label: '재해사례'           },
  { type: 'material',       objectType: 'SAFETY_MATERIAL', label: '안전자료'           },
  { type: 'chem',           objectType: 'CHEM',            label: 'MSDS'               },
  { type: 'keco',           objectType: 'CHEM_REGULATION', label: '화학물질 규제(KECO)' },
  { type: 'precedent',      objectType: 'PRECEDENT',       label: '판례'               },
  { type: 'reference-form', objectType: 'REFERENCE_FORM',  label: '참고서식'           },  // 추가
  { type: 'kosha',          objectType: null,              label: 'KOSHA 공식검색'     },
]);
```

**타입명 일관성 계약:**
- API `_TYPE_MAP` 키: `"reference-form"` (하이픈)
- API `_SECTION_TYPES` 첫 번째 요소: `"reference-form"`
- JS `TYPE_ALLOWLIST` 항목: `'reference-form'`
- JS `GROUP_DEFS.type`: `'reference-form'`
- URL 파라미터: `?type=reference-form`
- tai-www 페이지 경로: `/reference-form/{slug}`

### 9.4 sitemap_reference_forms.xml.js (updated_at 교정)

```js
// src/pages/sitemap_reference_forms.xml.js

export const prerender = false;

export async function GET({ locals }) {
  const forms = await fetchFromApi('/reference-forms/sitemap');
  // forms: [{ canonical_slug, updated_at, published_at }]
  // updated_at = GREATEST(rf.updated_at, rfc.updated_at) — view에서 제공

  const urls = forms.map(f => {
    const lastmod = f.updated_at
      ? f.updated_at.split('T')[0]
      : f.published_at?.split('T')[0];
    // fallback 없음 — 검증된 타임스탬프만 사용. 없으면 lastmod 생략
    const lastmodXml = lastmod ? `\n      <lastmod>${lastmod}</lastmod>` : '';

    return `  <url>
    <loc>https://taieng.co.kr/reference-form/${f.canonical_slug}</loc>${lastmodXml}
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>`;
  }).join('\n');

  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>`,
    { headers: { 'Content-Type': 'application/xml; charset=utf-8' } }
  );
}
```

### 9.5 sitemap API 엔드포인트 (tai-api)

```python
@router.get("/sitemap")
async def get_reference_forms_sitemap(supabase = Depends(get_supabase_client)):
    """sitemap_reference_forms.xml.js 가 호출하는 내부 API."""
    rows = (supabase.table("reference_form_public_view")
        .select("canonical_slug, updated_at, published_at")
        .order("published_at", desc=True)
        .execute()
    )
    return {"forms": list(getattr(rows, "data", None) or [])}
```

---

## 10. 4-way URL 정합 계약 (최종)

| 위치 | 값 | 형식 |
|------|-----|------|
| SearchDocument.canonical_id | `{form_uuid}` | UUID 문자열 (접두사 없음) |
| SearchDocument.public_url | `/reference-form/{canonical_slug}` | 상대 URL |
| SEO `<link rel="canonical">` | `https://taieng.co.kr/reference-form/{canonical_slug}` | 절대 URL |
| sitemap `<loc>` | `https://taieng.co.kr/reference-form/{canonical_slug}` | 절대 URL |
| 검색 결과 카드 href | `/reference-form/{canonical_slug}` | 상대 URL |
| composite-entry.js 패턴 | `/^\/reference-form\/[^/]+$/` | 변수명 `p` |
| tai-www Astro 파일 | `src/pages/reference-form/[slug].astro` | slug param |

---

## 11. 공개 취소 비동기 처리 (확정)

### 즉시 차단 (DB 트랜잭션 커밋 직후)
- `GET /reference-forms/{slug}` → 404 (view WHERE 조건 실패)
- `GET /reference-forms/{slug}/preview/{file_id}` → 404 (DB 재확인)
- `GET /reference-forms/{slug}/files/{file_id}/download` → 403 (DB 재확인)

### 비동기 처리 (outbox → incremental scheduler)
- OpenSearch 색인 삭제: `process_queue()` 처리 완료 시 (수초~수분)
- 삭제 완료 전 검색 결과에 서식이 남을 수 있음 — 계약에 명시

### fail-closed 필터 (DCSN-06 — 활성화 선택 사항)

```python
# public_safety_search.py POST 처리 (REFERENCE_FORM 결과 재검증)
# REF-08 해소 + 운영 부하 테스트 후 활성화 여부 Owner 결정

async def _filter_unpublished_reference_forms(
    results: list[dict],
    supabase,
) -> list[dict]:
    """REFERENCE_FORM 결과만 DB 게시 상태 일괄 재확인."""
    ref_ids = [r["canonical_id"] for r in results
               if r.get("object_type") == "REFERENCE_FORM"]
    if not ref_ids:
        return results

    published_ids = {
        row["id"] for row in
        (supabase.table("reference_forms")
            .select("id")
            .in_("id", ref_ids)
            .eq("status", "PUBLISHED")
            .execute().data or [])
    }

    return [r for r in results
            if r.get("object_type") != "REFERENCE_FORM"
            or r["canonical_id"] in published_ids]
```

---

## 12. 권한·승인 게이트 매트릭스

| 작업 | 호출자 | 게이트 |
|------|--------|--------|
| 상세 조회 | 비회원/회원 | status=PUBLISHED, content_approved=true |
| 파일 목록 | 비회원/회원 | qa_status=QA_PASS, approved_at IS NOT NULL |
| 파일 다운로드 | 회원 (JWT 필수) | 위 + form 소속 확인 |
| 미리보기 조회 | 비회원/회원 | is_published=true, qa_status=QA_PASS, sha256 일치 |
| 서식 게시 | service_role | 7-gate RPC |
| 서식 공개 취소 | service_role | status=PUBLISHED |
| slug 변경 | service_role | registry 전역 충돌 없음, 재사용 금지 |
| 파일 업로드 | Admin JWT | Admin 라우터 인증 |
| 파일 QA 승인 | Admin JWT | qa_status 전이 |
| Owner 승인 | Admin JWT | reference_form_approvals INSERT |

---

## 13. 격리 검증 결과

실제 PostgreSQL 환경 실행 불가 (운영 DB 접근 금지 원칙). 아래 항목은 SQL 문법 및 로직 정합성 기준 정적 검증.

### T1 — 12개 테이블 DDL 정합

| ID | 확인 항목 | 결과 |
|----|---------|------|
| T1-01 | 생성 순서 FK 의존성 | 1→2→3→4→5→6→7→8→9→10→11→12 OK |
| T1-02 | reference_form_events FK ON DELETE RESTRICT | 교정 완료 |
| T1-03 | preview_artifacts.source_file_id → files.id 순환 없음 | 5(files)→6(preview) 단방향 |
| T1-04 | content_hash 컬럼 DDL | fn_reference_form_content_hash 트리거로 자동 계산 |
| T1-05 | slug_registry PRIMARY KEY(slug) 전역 UNIQUE | 설계 확인 |
| T1-06 | approvals UNIQUE INDEX (form_id) WHERE is_current=true AND approval_status='APPROVED' | 유효 승인 1건 보장 |

### T2 — RPC 원자적 롤백 (격리 픽스처 기준)

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T2-01 | 정상 publish (GATE 1-7 전부 통과) | v_event_id 반환, status=PUBLISHED, outbox 1건 |
| T2-02 | GATE-3: content 변경 후 publish | 예외 발생, ROLLBACK, status=DRAFT |
| T2-03 | GATE-4: file sha256 불일치 | 예외 발생, ROLLBACK |
| T2-04 | GATE-5: rights_status=REVIEW_REQUIRED 출처 존재 | 예외 발생, ROLLBACK |
| T2-05 | 정상 unpublish | status=DRAFT, outbox 1건 UNPUBLISHED |
| T2-06 | slug 변경 — new_slug 전역 충돌 | 예외 발생, ROLLBACK, content 미변경 |
| T2-07 | slug 변경 — 동일 form 과거 slug 재사용 | 예외 발생, ROLLBACK |
| T2-08 | slug 변경 성공 → content_hash 자동 재계산 | content_hash ≠ 이전 값 |
| T2-09 | slug 변경 후 publish 시도 | GATE-3 실패 (content_hash 불일치) → 재승인 필요 |

### T3 — 파일·QA·미리보기 격리

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T3-01 | qa_status=PENDING 파일 다운로드 | 404 |
| T3-02 | approved_at=NULL 파일 포함 서식 publish | GATE-4 실패 |
| T3-03 | sha256 변조 파일 포함 서식 publish | GATE-4 실패 |
| T3-04 | 미리보기 source_file_sha256 불일치 | 410 Gone |
| T3-05 | 미리보기 응답 Cache-Control | `no-store` |
| T3-06 | 다운로드 응답 Cache-Control | `no-store` |

### T4 — Slug 충돌·이력

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T4-01 | 두 서식 동일 slug 동시 등록 | registry PK 충돌, 후발 ROLLBACK |
| T4-02 | form A의 과거 slug를 form B에 등록 | registry PK 충돌 |
| T4-03 | form A의 과거 slug를 form A에 재사용 | 재사용 금지 예외 |
| T4-04 | slug 변경 후 이전 slug 301 redirect 조회 | slug_history.old_slug → new_slug 확인 |

### T5 — SearchDocument 계약

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T5-01 | `_normalize_reference_form` 출력 필드 | `canonical_id=UUID`, `publication_status=PUBLISHED` |
| T5-02 | `FORBIDDEN_DOCUMENT_KEYS` 없음 | `file_ref`, `sha256_checksum` 미포함 |
| T5-03 | `object_reindex_payload(form_id)` — DRAFT | None 반환 (view가 DRAFT 제외) |
| T5-04 | `type_name` 일치 | API `reference-form` = JS `reference-form` = objectType `REFERENCE_FORM` |

### T6 — 4-way URL 일치

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T6-01 | `SearchDocument.public_url` | `/reference-form/{slug}` |
| T6-02 | Astro canonical href | `https://taieng.co.kr/reference-form/{slug}` |
| T6-03 | sitemap `<loc>` | `https://taieng.co.kr/reference-form/{slug}` |
| T6-04 | sitemap `<lastmod>` | `GREATEST(rf.updated_at, rfc.updated_at)` 기반 YYYY-MM-DD |
| T6-05 | sitemap lastmod fallback | 없음 (타임스탬프 없으면 생략) |
| T6-06 | composite-entry.js 변수 | `p` (pathname 아님) |

---

## 14. 미해결 사항

| ID | 항목 | 상태 |
|----|------|------|
| DCSN-06 | 공개 취소 즉시 검색 비노출 (DB 재확인) | Owner 결정 대기 |
| DCSN-08 | REF-08 QA 완료 전 adapter 주석처리 | 코드 추가, 빌드 시 비활성화 권고 |
| DCSN-09 | A-STREAM 진정한 스트리밍 | 별도 WO (storage3 SDK 한계) |
| DCSN-10 | GATE-6 미리보기 강제 활성화 시점 | REF-08 해소 후 마이그레이션 |
| DCSN-11 | pgcrypto 확장 운영 설치 여부 | 마이그레이션 `CREATE EXTENSION IF NOT EXISTS pgcrypto` 포함 |

---

## 15. 전체 수정 파일 목록 (최종)

### tai-api (신규)

| 파일 경로 | 설명 |
|----------|------|
| `supabase/migrations/20261011_reference_forms_01_core.sql` | 12테이블 DDL + pgcrypto + content_hash 트리거 |
| `supabase/migrations/20261011_reference_forms_02_storage.sql` | 버킷 2개 + Storage Policy |
| `supabase/migrations/20261011_reference_forms_03_rpc.sql` | RPC 3종 + fn_assert + fn_hash + public_view |
| `routers/reference_forms.py` | 공개+Admin API + StreamingResponse + 미리보기 |
| `services/shared_search/adapters/reference_form.py` | ReferenceFormAdapter |

### tai-api (수정)

| 파일 경로 | 수정 내용 |
|----------|---------|
| `main.py` | router include |
| `services/shared_search/production_bindings.py` | `_make_reference_form_adapter` + `adapters.append` |
| `services/shared_search/adapters/__init__.py` | `ReferenceFormAdapter` export |
| `routers/public_safety_search.py` | `_PUBLIC_OBJECT_TYPES` + `_TYPE_MAP` + `_SECTION_TYPES` + `reference-form` |

### tai-www (신규)

| 파일 경로 | 설명 |
|----------|------|
| `src/pages/reference-form/[slug].astro` | SSR 상세 페이지 |
| `src/pages/sitemap_reference_forms.xml.js` | 동적 sitemap (updated_at 교정) |
| `src/lib/api/referenceForms.ts` | API 클라이언트 |

### tai-www (수정)

| 파일 경로 | 수정 내용 |
|----------|---------|
| `workers/composite-entry.js` | `/reference-form/` + trailing slash + sitemap (변수 `p` 사용) |
| `workers/pages-live-worker.js` | `handleSitemapIndex` 에 `sitemap_reference_forms.xml` 추가 |
| `src/lib/server/safetySearch.js` | `TYPE_ALLOWLIST` + `GROUP_DEFS` 에 `reference-form` 추가 |

---

## 16. 게이트 조건

| 조건 | 상태 |
|------|------|
| GPT_REF05_IMPLEMENTATION_CONTRACT_VERIFY | PENDING |
| OBJ-REF-08 Content factory QA | BLOCKED |
| Owner 최종 공개 승인 | PENDING |

**운영 DB 적용·배포·색인·PR merge 금지 (게이트 해소 전).**
