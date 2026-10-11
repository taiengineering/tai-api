---
wo: WO-REF05-CMS-PUBLIC-INTEGRATION-DESIGN-001
date: 2026-10-11
status: DESIGN_READY
section: OBJ-REF-05
publication: NOT_FOR_PUBLICATION
dependency: OBJ-REF-08 (BLOCKED)
parent: WO-REF01-GATE-A-R2-FINAL-CONTRACT-003.md
next_gate: GPT_REF05_CMS_DETAIL_DESIGN_VERIFY
scope: DESIGN+DDL_DRAFT ONLY — 운영 DB DDL·데이터·OpenSearch·배포·PR merge·외부공개 금지
---

# REF-05 CMS 물리 스키마 + 공개 연계 설계 (v1)

WO-REF05-CMS-PUBLIC-INTEGRATION-DESIGN-001.

Gate A R2 Final Contract (WO-REF01-GATE-A-R2-FINAL-CONTRACT-003) 계약을 기반으로
CMS 물리 스키마·원자성 설계·공개 API·Storage 접근제어·OpenSearch 연계를 정의한다.

---

## WP-05A — CMS 물리 스키마

### 1. ERD (논리 구조)

```
reference_forms (핵심 식별자 + 게시 상태)
  │
  ├── reference_form_content (언어별 내용: 제목·설명·본문·slug)
  │     └── reference_form_slug_history (slug 변경 이력 → 301 redirect)
  │
  ├── reference_form_files (첨부 파일 목록: XLSX·DOCX·PDF·HWPX·HWP)
  │
  ├── reference_form_sources (출처: KOSHA·MOL·공식 URL)
  │
  ├── reference_form_relations (타 서식 간 연관 관계)
  │
  ├── reference_form_legacy_links (REF-C### 레거시 코드 연결)
  │
  ├── reference_form_aliases (추가 slug 별칭 → 301 redirect)
  │
  └── reference_form_events (CMS 이벤트 감사 로그 + Outbox trigger 입력)
```

---

### 2. DDL 초안

#### 2.1 `reference_forms`

```sql
-- Migration: 20261011_reference_forms_core.sql

CREATE TABLE public.reference_forms (
  id                UUID        NOT NULL DEFAULT gen_random_uuid(),
  status            TEXT        NOT NULL DEFAULT 'DRAFT'
                                CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
  published_at      TIMESTAMPTZ,
  archived_at       TIMESTAMPTZ,
  owner_approved    BOOLEAN     NOT NULL DEFAULT false,
  owner_approved_at TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_forms_pkey PRIMARY KEY (id),
  -- 게시 일관성 제약
  CONSTRAINT reference_forms_published_at_chk
    CHECK (
      (status = 'PUBLISHED' AND published_at IS NOT NULL AND owner_approved = true)
      OR status <> 'PUBLISHED'
    ),
  CONSTRAINT reference_forms_archived_at_chk
    CHECK (
      (status = 'ARCHIVED' AND archived_at IS NOT NULL)
      OR status <> 'ARCHIVED'
    )
);

CREATE INDEX reference_forms_status_idx ON public.reference_forms (status);
CREATE INDEX reference_forms_published_at_idx ON public.reference_forms (published_at)
  WHERE status = 'PUBLISHED';

-- updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION public.fn_reference_forms_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER reference_forms_updated_at
  BEFORE UPDATE ON public.reference_forms
  FOR EACH ROW EXECUTE FUNCTION public.fn_reference_forms_set_updated_at();

-- RLS
ALTER TABLE public.reference_forms ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_forms FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_forms TO service_role;
```

#### 2.2 `reference_form_content`

```sql
-- 언어별 1:1 (현재 ko 전용, lang 컬럼으로 확장 여지 보존)

CREATE TABLE public.reference_form_content (
  id              UUID        NOT NULL DEFAULT gen_random_uuid(),
  form_id         UUID        NOT NULL,
  lang            TEXT        NOT NULL DEFAULT 'ko',
  canonical_slug  TEXT        NOT NULL,
  title           TEXT        NOT NULL,
  description     TEXT,           -- SEO meta description (30–170자 권고)
  body_html       TEXT,           -- 상세 본문 HTML
  summary         TEXT,           -- 카드용 요약 (선택)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_content_pkey PRIMARY KEY (id),
  CONSTRAINT reference_form_content_form_lang_key
    UNIQUE (form_id, lang),
  CONSTRAINT reference_form_content_slug_key
    UNIQUE (canonical_slug),
  CONSTRAINT reference_form_content_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE,
  CONSTRAINT reference_form_content_slug_chk
    CHECK (canonical_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  CONSTRAINT reference_form_content_title_chk
    CHECK (char_length(title) BETWEEN 1 AND 60),
  CONSTRAINT reference_form_content_description_chk
    CHECK (description IS NULL OR char_length(description) BETWEEN 30 AND 170)
);

CREATE INDEX reference_form_content_form_id_idx
  ON public.reference_form_content (form_id);
CREATE INDEX reference_form_content_slug_idx
  ON public.reference_form_content (canonical_slug);

CREATE TRIGGER reference_form_content_updated_at
  BEFORE UPDATE ON public.reference_form_content
  FOR EACH ROW EXECUTE FUNCTION public.fn_reference_forms_set_updated_at();

ALTER TABLE public.reference_form_content ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_content FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_content TO service_role;
```

**SEO 길이 제약 근거:**
- `title` ≤ 60: `seo-meta-lint.mjs` > 60 → HARD FAIL
- `description` 30–170: < 30 → FAIL, > 170 → FAIL (enforcement 확인됨)

#### 2.3 `reference_form_slug_history`

```sql
-- slug 변경 이력 → 301 redirect 근거 테이블
-- 기존 codebase에 없는 신규 패턴

CREATE TABLE public.reference_form_slug_history (
  id          UUID        NOT NULL DEFAULT gen_random_uuid(),
  form_id     UUID        NOT NULL,
  lang        TEXT        NOT NULL DEFAULT 'ko',
  old_slug    TEXT        NOT NULL,
  new_slug    TEXT        NOT NULL,
  redirected_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_slug_history_pkey PRIMARY KEY (id),
  -- old_slug는 전역 UNIQUE — 재사용 방지
  CONSTRAINT reference_form_slug_history_old_slug_key
    UNIQUE (old_slug),
  CONSTRAINT reference_form_slug_history_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE
);

CREATE INDEX reference_form_slug_history_old_slug_idx
  ON public.reference_form_slug_history (old_slug);

ALTER TABLE public.reference_form_slug_history ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_slug_history FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_slug_history TO service_role;
```

**old_slug UNIQUE 제약 목적:** 이전에 사용한 slug가 새 서식에 재배정되어 301 무한루프·잘못된 색인 전파 방지.

#### 2.4 `reference_form_files`

```sql
CREATE TABLE public.reference_form_files (
  id           UUID        NOT NULL DEFAULT gen_random_uuid(),
  form_id      UUID        NOT NULL,
  file_ref     TEXT        NOT NULL,  -- 'storage://reference-forms/{uuid}/{filename}'
  format       TEXT        NOT NULL
                           CHECK (format IN ('XLSX','DOCX','PDF','HWPX','HWP','ETC')),
  display_name TEXT        NOT NULL,  -- 화면 표시 파일명 + 확장자
  file_size_bytes BIGINT,
  sort_order   INTEGER     NOT NULL DEFAULT 0,
  is_active    BOOLEAN     NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_files_pkey PRIMARY KEY (id),
  CONSTRAINT reference_form_files_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE,
  CONSTRAINT reference_form_files_file_ref_chk
    CHECK (file_ref ~ '^storage://')
);

CREATE INDEX reference_form_files_form_id_idx
  ON public.reference_form_files (form_id)
  WHERE is_active = true;

CREATE TRIGGER reference_form_files_updated_at
  BEFORE UPDATE ON public.reference_form_files
  FOR EACH ROW EXECUTE FUNCTION public.fn_reference_forms_set_updated_at();

ALTER TABLE public.reference_form_files ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_files FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_files TO service_role;
```

#### 2.5 `reference_form_sources`

```sql
CREATE TABLE public.reference_form_sources (
  id          UUID        NOT NULL DEFAULT gen_random_uuid(),
  form_id     UUID        NOT NULL,
  source_type TEXT        NOT NULL
                          CHECK (source_type IN ('KOSHA','MOL','MOEL','OFFICIAL_URL','ETC')),
  source_id   TEXT,
  source_url  TEXT,
  note        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_sources_pkey PRIMARY KEY (id),
  CONSTRAINT reference_form_sources_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE
);

CREATE INDEX reference_form_sources_form_id_idx
  ON public.reference_form_sources (form_id);

ALTER TABLE public.reference_form_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_sources FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_sources TO service_role;
```

#### 2.6 `reference_form_relations`

```sql
CREATE TABLE public.reference_form_relations (
  id              UUID  NOT NULL DEFAULT gen_random_uuid(),
  form_id         UUID  NOT NULL,
  related_form_id UUID  NOT NULL,
  relation_type   TEXT  NOT NULL
                        CHECK (relation_type IN ('SIMILAR','SUPERSEDES','SUPERSEDED_BY','LINKED')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_relations_pkey PRIMARY KEY (id),
  CONSTRAINT reference_form_relations_no_self
    CHECK (form_id <> related_form_id),
  CONSTRAINT reference_form_relations_unique
    UNIQUE (form_id, related_form_id, relation_type),
  CONSTRAINT reference_form_relations_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE,
  CONSTRAINT reference_form_relations_related_fk
    FOREIGN KEY (related_form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE
);

ALTER TABLE public.reference_form_relations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_relations FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_relations TO service_role;
```

#### 2.7 `reference_form_legacy_links`

```sql
CREATE TABLE public.reference_form_legacy_links (
  id           UUID  NOT NULL DEFAULT gen_random_uuid(),
  form_id      UUID  NOT NULL,
  legacy_code  TEXT  NOT NULL,  -- e.g., 'REF-C002', 'REF-C067'
  note         TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_legacy_links_pkey PRIMARY KEY (id),
  CONSTRAINT reference_form_legacy_links_legacy_code_key
    UNIQUE (legacy_code),
  CONSTRAINT reference_form_legacy_links_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE
);

CREATE INDEX reference_form_legacy_links_form_id_idx
  ON public.reference_form_legacy_links (form_id);

ALTER TABLE public.reference_form_legacy_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_legacy_links FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_legacy_links TO service_role;
```

#### 2.8 `reference_form_aliases`

```sql
-- 추가 slug 별칭: 301 redirect 처리용

CREATE TABLE public.reference_form_aliases (
  id          UUID  NOT NULL DEFAULT gen_random_uuid(),
  form_id     UUID  NOT NULL,
  alias_slug  TEXT  NOT NULL,
  lang        TEXT  NOT NULL DEFAULT 'ko',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_aliases_pkey PRIMARY KEY (id),
  CONSTRAINT reference_form_aliases_slug_key
    UNIQUE (alias_slug),
  CONSTRAINT reference_form_aliases_slug_chk
    CHECK (alias_slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  CONSTRAINT reference_form_aliases_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE
);

ALTER TABLE public.reference_form_aliases ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_aliases FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_aliases TO service_role;
```

#### 2.9 `reference_form_events`

```sql
-- CMS 감사 로그 + Outbox Trigger 소스 테이블
-- INSERT 시 DB 트리거가 search_index_outbox 에 enqueue 함 (WP-05B 참조)

CREATE TABLE public.reference_form_events (
  id          UUID        NOT NULL DEFAULT gen_random_uuid(),
  form_id     UUID        NOT NULL,
  event_type  TEXT        NOT NULL
                          CHECK (event_type IN (
                            'CREATED','UPDATED','PUBLISHED','UNPUBLISHED',
                            'ARCHIVED','SLUG_CHANGED','FILE_ADDED','FILE_REMOVED',
                            'OWNER_APPROVED'
                          )),
  actor       TEXT        NOT NULL,  -- 관리자 계정 식별자
  payload     JSONB       NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT reference_form_events_pkey PRIMARY KEY (id),
  CONSTRAINT reference_form_events_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE CASCADE
);

CREATE INDEX reference_form_events_form_id_idx
  ON public.reference_form_events (form_id);
CREATE INDEX reference_form_events_event_type_idx
  ON public.reference_form_events (event_type);
CREATE INDEX reference_form_events_created_at_idx
  ON public.reference_form_events (created_at DESC);

ALTER TABLE public.reference_form_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_events FROM anon, authenticated;
GRANT SELECT, INSERT ON public.reference_form_events TO service_role;
-- UPDATE/DELETE 금지: 감사 로그 불변성
```

---

### 3. RLS 매트릭스

| 테이블 | anon | authenticated | service_role |
|--------|------|---------------|--------------|
| reference_forms | DENY | DENY | ALL |
| reference_form_content | DENY | DENY | ALL |
| reference_form_slug_history | DENY | DENY | ALL |
| reference_form_files | DENY | DENY | ALL |
| reference_form_sources | DENY | DENY | ALL |
| reference_form_relations | DENY | DENY | ALL |
| reference_form_legacy_links | DENY | DENY | ALL |
| reference_form_aliases | DENY | DENY | ALL |
| reference_form_events | DENY | DENY | SELECT+INSERT |

**공개 읽기 경로:** 모든 공개 데이터는 서버 측 API를 통해서만 노출. service_role JWT로 호출.

---

## WP-05B — DB Trigger vs RPC 원자성 비교 및 선택

### 배경

WO-REF01-GATE-A-R2-FINAL-CONTRACT-003 §3에서 확정:
> "동일 API 요청 내 순차 실행"은 원자성을 보장하지 않는다.
> DB Trigger (A) 또는 Stored Procedure (B) 중 하나 필요.

### 방식 A — DB Trigger

`reference_form_events` INSERT 시 트리거가 `search_index_outbox` 에 자동 enqueue.

```sql
CREATE OR REPLACE FUNCTION public.fn_reference_form_events_enqueue_outbox()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  -- event_key: reference_form:{uuid}:{event_id}
  -- cms_event_id = NEW.id (unique per change, 충돌 없음)
  PERFORM public.enqueue_search_index_sync(
    'REFERENCE_FORM',
    NEW.form_id::text,
    NEW.event_type,
    'reference_form:' || NEW.form_id::text || ':' || NEW.id::text
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER reference_form_events_enqueue_outbox
  AFTER INSERT ON public.reference_form_events
  FOR EACH ROW EXECUTE FUNCTION public.fn_reference_form_events_enqueue_outbox();
```

**특성:**
| 항목 | 값 |
|------|-----|
| 원자성 | 동일 트랜잭션 — reference_form_events INSERT와 outbox INSERT는 같이 COMMIT/ROLLBACK |
| enqueue_search_index_sync 없는 경우 | trigger 생성 실패 → 의존성 명확 |
| 이벤트 선택성 | PUBLISHED / UNPUBLISHED / SLUG_CHANGED 만 색인 필요 — trigger 내 WHERE 절로 필터 |
| 실패 전파 | outbox INSERT 실패 → 전체 트랜잭션 ROLLBACK — fail-closed |
| 사이드이펙트 | 모든 reference_form_events INSERT가 trigger를 거침 (불필요한 이벤트 가드 필요) |

**이벤트 필터 추가:**

```sql
CREATE OR REPLACE FUNCTION public.fn_reference_form_events_enqueue_outbox()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  -- 색인 관련 이벤트만 outbox 등록
  IF NEW.event_type NOT IN ('PUBLISHED','UNPUBLISHED','SLUG_CHANGED','ARCHIVED') THEN
    RETURN NEW;
  END IF;

  PERFORM public.enqueue_search_index_sync(
    'REFERENCE_FORM',
    NEW.form_id::text,
    NEW.event_type,
    'reference_form:' || NEW.form_id::text || ':' || NEW.id::text
  );
  RETURN NEW;
END;
$$;
```

### 방식 B — Stored Procedure (RPC)

단일 RPC 호출로 reference_form_events INSERT + outbox enqueue를 명시적 트랜잭션 안에서 실행.

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
  v_event_id UUID;
BEGIN
  -- 1. 게시 상태 전이
  UPDATE public.reference_forms
     SET status = 'PUBLISHED',
         published_at = now()
   WHERE id = p_form_id
     AND status = 'DRAFT'
     AND owner_approved = true;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'PUBLISH_PRECONDITION_FAILED: form not DRAFT or not owner_approved';
  END IF;

  -- 2. 감사 이벤트 기록
  INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
  VALUES (p_form_id, 'PUBLISHED', p_actor, p_payload)
  RETURNING id INTO v_event_id;

  -- 3. Outbox enqueue (동일 트랜잭션)
  PERFORM public.enqueue_search_index_sync(
    'REFERENCE_FORM',
    p_form_id::text,
    'PUBLISHED',
    'reference_form:' || p_form_id::text || ':' || v_event_id::text
  );

  RETURN v_event_id;
END;
$$;
```

**특성:**
| 항목 | 값 |
|------|-----|
| 원자성 | 명시적 — 같은 SQL 함수 내에서 원자적 실행 |
| 이벤트별 RPC | PUBLISH / UNPUBLISH / SLUG_CHANGE 각각 별도 RPC 필요 |
| 투명성 | 각 상태 전이가 독립 함수 — 비즈니스 로직 가시성 높음 |
| trigger 의존성 없음 | trigger 없이 동작 — 테스트 격리 용이 |
| API 계층 단순화 | FastAPI 라우터는 RPC 1개만 호출 |

### 방식 선택 권고

**방식 B (Stored Procedure)를 권고한다.**

근거:
1. 이벤트 타입별 전이 로직(PUBLISH / UNPUBLISH / SLUG_CHANGE)이 다르다 — trigger 내 분기가 복잡해진다.
2. RPC는 FastAPI 라우터 → RPC 호출 1회로 단순화된다.
3. 테스트 시 trigger를 우회하기 어렵다 — RPC는 mock-able.
4. `rpc_publish_reference_form` / `rpc_unpublish_reference_form` / `rpc_change_slug_reference_form` 3개로 상태 전이를 완전 관리한다.

**최종 결정은 GPT_REF05_CMS_DETAIL_DESIGN_VERIFY Gate에서 Owner 확정.**

---

## WP-05C — 공개 API · Storage · 다운로드 스트리밍 설계

### 1. API 엔드포인트 목록

모든 공개 엔드포인트는 FastAPI 라우터 `/reference-forms/` prefix.

#### 1.1 상세 페이지 데이터

```
GET /reference-forms/{canonical_slug}
```

- 인증 불필요 (공개)
- 응답: form 메타 + content (title, description, body_html) + files 목록 + sources
- 게시 상태 필터: `status = 'PUBLISHED' AND owner_approved = true`
- 미게시 서식 → 404

```json
{
  "id": "uuid",
  "canonical_slug": "string",
  "title": "string",
  "description": "string",
  "body_html": "string",
  "files": [
    {
      "id": "uuid",
      "format": "XLSX",
      "display_name": "안전작업허가서.xlsx",
      "sort_order": 0
    }
  ],
  "sources": [...],
  "published_at": "ISO8601"
}
```

**주의:** `file_ref` (Storage 경로) 는 응답에 포함하지 않는다.

#### 1.2 파일 다운로드 (Method A — 서버 스트리밍, 권장)

```
GET /reference-forms/{form_slug}/files/{file_id}/download
Authorization: Bearer {JWT}
```

서버 흐름:
1. JWT 검증 → 비인증 시 `401 UNAUTHORIZED`
2. `reference_forms.status = 'PUBLISHED' AND owner_approved = true` 확인 → 미충족 시 `403 FORBIDDEN`
3. RLS: service_role로 `reference_form_files.file_ref` 조회 (file_id 기반)
4. Storage path 파싱: `storage://reference-forms/{path}` → bucket + path 분리
5. `supabase.storage.from_("reference-forms").download(path)` → bytes stream
6. `StreamingResponse(content=stream, media_type=..., headers={"Content-Disposition": ...})`

```python
# routers/reference_forms.py (신규)

REFERENCE_FORMS_BUCKET = "reference-forms"

@router.get("/{form_slug}/files/{file_id}/download")
async def download_reference_form_file(
    form_slug: str,
    file_id: UUID,
    current_user: dict = Depends(get_current_user),
    supabase = Depends(get_supabase_client),
):
    # 1. 서식 게시 상태 확인
    form_row = supabase.table("reference_forms") \
        .select("id, status, owner_approved") \
        .eq("status", "PUBLISHED") \
        .eq("owner_approved", True) \
        .single()  # 내부에서 content join 필요 — slug 조회 포함

    if not form_row:
        raise HTTPException(status_code=404, detail="NOT_FOUND_OR_UNPUBLISHED")

    # 2. 파일 조회
    file_row = supabase.table("reference_form_files") \
        .select("file_ref, display_name, format") \
        .eq("id", str(file_id)) \
        .eq("form_id", form_row["id"]) \
        .eq("is_active", True) \
        .single()

    if not file_row:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    # 3. Storage path 파싱
    file_ref = file_row["file_ref"]  # storage://reference-forms/uuid/filename
    bucket, path = _parse_storage_ref(file_ref)

    # 4. 서버 스트리밍 (Storage URL 클라이언트 미노출)
    data = supabase.storage.from_(bucket).download(path)

    media_type = _format_to_media_type(file_row["format"])
    filename = quote(file_row["display_name"])

    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{filename}',
        }
    )
```

#### 1.3 파일 다운로드 (Method B — Short-lived Signed URL, 대안)

```
GET /reference-forms/{form_slug}/files/{file_id}/signed-url
Authorization: Bearer {JWT}
```

서버 흐름:
1–3. Method A 동일
4. `supabase.storage.from_("reference-forms").create_signed_url(path, expires_in=30)` → signedUrl
5. 응답: `{"signed_url": "...", "expires_in": 30}`

**Storage URL이 응답 JSON에 포함됨 — 브라우저 네트워크 탭에서 노출됨.**
UI는 즉시 redirect/fetch 처리. Method B 사용 시 보안 계약에 "일시 노출 허용" 명시 필요.

#### 1.4 sitemap 엔드포인트

```
GET /reference-forms/sitemap
```

- 인증 불필요
- `status = 'PUBLISHED'` 전체 목록 → `{canonical_slug, published_at, updated_at}`
- tai-www `sitemap_reference_forms.xml.js` 가 이 엔드포인트를 호출

#### 1.5 OpenSearch 색인 데이터 (내부)

```
GET /reference-forms/{form_id}/search-document
```

- 내부 전용 (`X-Internal-Key` 헤더 또는 service_role JWT)
- REFERENCE_FORM DomainAdapter 가 호출
- 응답: SearchDocument 필드 (canonical_id, title, description, public_url, tags 등)

---

### 2. Storage 버킷 설계

```
버킷명: reference-forms
공개 여부: PRIVATE (RLS 적용)
최대 파일 크기: 20MB (설정 필요)
허용 MIME: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet (xlsx)
           application/vnd.openxmlformats-officedocument.wordprocessingml.document (docx)
           application/pdf
           application/x-hwp (hwp)
           application/haansofthwp (hwpx)
```

Storage Policy (버킷 생성 마이그레이션에 포함):
```sql
-- 공개 읽기 차단: 모든 Storage 접근은 service_role API를 통해서만
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('reference-forms', 'reference-forms', false, 20971520);

-- anon/authenticated direct Storage access 차단
CREATE POLICY "reference_forms_storage_deny_anon"
  ON storage.objects FOR SELECT
  TO anon, authenticated
  USING (bucket_id = 'reference-forms' AND false);
```

---

## WP-05C.2 — 파일 업로드 흐름 (Admin CMS)

```
POST /admin/reference-forms/{form_id}/files/upload-url
Authorization: Bearer {admin_JWT}
```

1. Admin JWT 검증 (admin 권한 확인)
2. `supabase.storage.from_("reference-forms").create_signed_upload_url(path)` → signedUrl
3. Admin 클라이언트: PUT {signedUrl} with file binary
4. 업로드 완료 후: `POST /admin/reference-forms/{form_id}/files/register` → `reference_form_files` INSERT

---

## WP-05D — SEO · OpenSearch REFERENCE_FORM Adapter 계약

### 1. REFERENCE_FORM DomainAdapter

기존 패턴: `production_bindings.py` 에 `DomainAdapter` 등록.

```python
# services/shared_search/adapters/reference_form_adapter.py (신규)

from ..domain_adapter import DomainAdapter, SearchDocument
from typing import Optional
import httpx

class ReferenceFormAdapter(DomainAdapter):
    domain = "REFERENCE_FORM"

    async def fetch_document(self, entity_id: str) -> Optional[SearchDocument]:
        """
        entity_id: reference_forms.id (UUID)
        """
        resp = await self._api_client.get(
            f"/reference-forms/{entity_id}/search-document"
        )
        if resp.status_code == 404:
            return None  # UNPUBLISHED → tombstone 처리됨
        resp.raise_for_status()
        data = resp.json()
        return SearchDocument(
            canonical_id=f"REFERENCE_FORM::{entity_id}",
            domain="REFERENCE_FORM",
            title=data["title"],
            description=data.get("description", ""),
            public_url=f"/reference-form/{data['canonical_slug']}",
            tags=data.get("tags", []),
            published_at=data.get("published_at"),
            extra={
                "form_id": entity_id,
                "formats": data.get("formats", []),
                "legacy_codes": data.get("legacy_codes", []),
            }
        )
```

### 2. production_bindings.py 등록

```python
# services/shared_search/production_bindings.py (기존 파일 수정)

from .adapters.reference_form_adapter import ReferenceFormAdapter

DOMAIN_ADAPTERS = {
    # ... 기존 ...
    "REFERENCE_FORM": ReferenceFormAdapter(),
}
```

### 3. event_key 계약 (Gate A R2 확정)

```
event_key = "reference_form:{form_uuid}:{event_uuid}"
```

- `form_uuid`: `reference_forms.id` (UUID)
- `event_uuid`: `reference_form_events.id` (UUID, 이벤트마다 고유)
- `ON CONFLICT (event_key) DO NOTHING` — 동일 event_id 재시도 시 멱등 처리

### 4. UNPUBLISH tombstone 처리

`fetch_document()` 가 404 반환 → 기존 `process_queue()` tombstone 처리 경로 활용:

```python
# incremental.py (기존 로직 확인)
if doc is None:
    # 색인에서 삭제 처리
    opensearch_client.delete(index="reference-form", id=canonical_id)
```

**tombstone 발동 조건:**
- `event_type = 'UNPUBLISHED'` → outbox enqueue → process_queue → fetch_document returns None → delete from OpenSearch
- `event_type = 'ARCHIVED'` → 동일 흐름

### 5. SEO 연계 (tai-www)

#### 5.1 상세 페이지 SEO

파일: `src/pages/reference-form/[slug].astro` (신규)

```astro
---
// 서버 측에서 API 호출 후 SEO meta 삽입
const { slug } = Astro.params;
const form = await fetchReferenceForm(slug);
if (!form) return Astro.redirect('/404');
---
<BaseLayout
  title={form.title}
  description={form.description}
  canonical={`https://taieng.co.kr/reference-form/${form.canonical_slug}`}
>
  <!-- 상세 페이지 내용 -->
</BaseLayout>
```

**BaseLayout 계약:**
- `title` 없으면 build error
- `description` 없으면 build error
- `title` > 60 → seo-meta-lint HARD FAIL
- `description` < 30 또는 > 170 → seo-meta-lint HARD FAIL

#### 5.2 sitemap

파일: `src/pages/sitemap_reference_forms.xml.js` (신규)

```js
// prerender = false (동적 SSR) — composite-entry.js 등록 필요
export const prerender = false;

export async function GET() {
  const forms = await fetchPublishedReferenceForms();
  const urls = forms.map(f =>
    `<url>
      <loc>https://taieng.co.kr/reference-form/${f.canonical_slug}</loc>
      <lastmod>${f.updated_at.split('T')[0]}</lastmod>
      <changefreq>monthly</changefreq>
      <priority>0.6</priority>
    </url>`
  ).join('\n');

  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      ${urls}
    </urlset>`,
    { headers: { 'Content-Type': 'application/xml' } }
  );
}
```

---

## WP-05C.3 — 게시 상태 전이표

### 상태 정의

| 상태 | 의미 | 공개 여부 | 색인 여부 |
|------|------|-----------|----------|
| DRAFT | 작성 중 | NO | NO |
| PUBLISHED | 운영 공개 | YES | YES |
| ARCHIVED | 서비스 종료 | NO | NO (tombstone) |

### 전이 규칙

```
DRAFT → PUBLISHED: owner_approved = true 필수
PUBLISHED → DRAFT: 재편집 (공개 취소)
PUBLISHED → ARCHIVED: 영구 종료
DRAFT → ARCHIVED: 미게시 폐기
ARCHIVED → DRAFT: 재활성화 (owner_approved 재확인 필요)
```

### 전이 제약 테이블

| 전이 | 전제조건 | RPC | Outbox event_type |
|------|----------|-----|-------------------|
| DRAFT → PUBLISHED | owner_approved=true | `rpc_publish_reference_form` | PUBLISHED |
| PUBLISHED → DRAFT | — | `rpc_unpublish_reference_form` | UNPUBLISHED |
| PUBLISHED → ARCHIVED | — | `rpc_archive_reference_form` | ARCHIVED |
| DRAFT → ARCHIVED | — | `rpc_archive_reference_form` | — (색인 없음) |
| ARCHIVED → DRAFT | — | `rpc_restore_reference_form` | — |
| slug 변경 | PUBLISHED 상태 | `rpc_change_slug_reference_form` | SLUG_CHANGED |

### 공개 취소 (UNPUBLISH) Fail-Closed 매트릭스

Gate A R2 §4 확정 계약 기반:

| 계층 | 동작 | 실패 시 |
|------|------|---------|
| 1. OpenSearch tombstone | DELETE 색인 레코드 | 검색 결과에 계속 노출 (허용 불가) |
| 2. sitemap 제외 | 다음 sitemap 재생성 시 URL 제거 | Google 크롤 계속 (허용, 자연 소멸) |
| 3. SEO noindex | 페이지 응답에 `<meta name="robots" content="noindex">` | Google 색인 유지 (허용, 자연 소멸) |
| 4. 페이지 404 | `status ≠ PUBLISHED` → 404 반환 | 페이지 접근 가능 (허용 불가) |
| 5. 미리보기 차단 | API 미리보기 엔드포인트 동일 필터 | 미리보기 가능 (허용 불가) |
| 6. 다운로드 차단 | 다운로드 API 게시 상태 확인 | 파일 다운로드 가능 (허용 불가) |
| CF 캐시 무효화 | Cloudflare Cache-Control 정책 | 구 캐시 응답 제공 (허용 불가) |

**허용 불가 항목 처리 전략:**
- 계층 1: `rpc_unpublish_reference_form` 내에서 원자적으로 처리 (outbox enqueue → incremental scheduler → tombstone)
- 계층 4/5/6: API 응답 시 실시간 DB 조회 — 캐시 금지
- CF 캐시: `Cache-Control: no-store` 또는 UNPUBLISH 시 CF Cache Purge API 호출 (별도 WO 필요)

---

## WP-05E — 검증 계획

### D1 — Outbox 트랜잭션 테스트

| 테스트 ID | 시나리오 | 기댓값 |
|-----------|---------|--------|
| ATOM-01 | `rpc_publish_reference_form` 정상 실행 | reference_form_events 1건 INSERT + outbox 1건 PENDING 동시 확인 |
| ATOM-02 | outbox INSERT 실패 (enqueue RPC 강제 오류) | reference_form_events INSERT ROLLBACK, forms.status = DRAFT 유지 |
| ATOM-03 | forms.status UPDATE 실패 (precondition 불충족) | 전체 ROLLBACK, events 0건 |
| ATOM-04 | 동일 event_id 재시도 | ON CONFLICT DO NOTHING — outbox 중복 없음 |

### D2 — UNPUBLISH Fail-Closed 테스트

| 테스트 ID | 시나리오 | 기댓값 |
|-----------|---------|--------|
| UNPUB-01 | UNPUBLISH 후 `GET /reference-forms/{slug}` | 404 |
| UNPUB-02 | UNPUBLISH 후 `GET /reference-forms/{form_id}/files/{file_id}/download` (인증 회원) | 403 FORBIDDEN |
| UNPUB-03 | UNPUBLISH 후 OpenSearch 색인 확인 | document 존재 → DELETE 완료 후 검색 결과 없음 |
| UNPUB-04 | UNPUBLISH 후 sitemap_reference_forms.xml | URL 제거됨 |
| UNPUB-05 | UNPUBLISH 중 동시 다운로드 요청 | 403 (DB 조회 실시간, 캐시 없음) |
| UNPUB-06 | ARCHIVED 전환 후 GET | 404 |

### D3 — 페이지 · SEO · sitemap · 검색 연계 매트릭스

| 항목 | tai-api 파일 | tai-www 파일 | 상태 |
|------|------------|------------|------|
| 상세 페이지 API | `routers/reference_forms.py` | `src/pages/reference-form/[slug].astro` | 신규 |
| SSR 라우팅 | — | `workers/composite-entry.js` (+2 패턴) | 수정 |
| sitemap API | `routers/reference_forms.py` | `src/pages/sitemap_reference_forms.xml.js` | 신규 |
| SEO meta | — | BaseLayout prop (title/description) | 신규 |
| OpenSearch Adapter | `services/shared_search/adapters/reference_form_adapter.py` | — | 신규 |
| Adapter 등록 | `services/shared_search/production_bindings.py` | — | 수정 |
| 다운로드 API | `routers/reference_forms.py` | — | 신규 |
| Storage 버킷 | `supabase/migrations/...` | — | 신규 |
| CMS DDL (9 테이블) | `supabase/migrations/...` | — | 신규 |
| Outbox trigger/RPC | `supabase/migrations/...` | — | 신규 |

---

## WP-05E.2 — 실제 코드 수정 대상 목록

### tai-api (신규 파일)

| 파일 경로 | 설명 |
|----------|------|
| `supabase/migrations/20261011_reference_forms_core.sql` | 9 테이블 DDL + RLS |
| `supabase/migrations/20261011_reference_forms_storage.sql` | reference-forms 버킷 생성 + Storage policy |
| `supabase/migrations/20261011_reference_forms_outbox_rpc.sql` | RPC 3종 (publish/unpublish/change_slug) + trigger |
| `routers/reference_forms.py` | FastAPI 라우터 (공개 API + Admin API + 다운로드) |
| `services/shared_search/adapters/reference_form_adapter.py` | REFERENCE_FORM DomainAdapter |

### tai-api (기존 파일 수정)

| 파일 경로 | 수정 내용 |
|----------|---------|
| `main.py` | `reference_forms` 라우터 include |
| `services/shared_search/production_bindings.py` | `REFERENCE_FORM` adapter 등록 |

### tai-www (신규 파일)

| 파일 경로 | 설명 |
|----------|------|
| `src/pages/reference-form/[slug].astro` | SSR 상세 페이지 |
| `src/pages/sitemap_reference_forms.xml.js` | 동적 sitemap (prerender=false) |
| `src/lib/api/referenceForms.ts` | tai-api 호출 클라이언트 함수 |

### tai-www (기존 파일 수정)

| 파일 경로 | 수정 내용 |
|----------|---------|
| `workers/composite-entry.js` | `/reference-form/` 및 `/sitemap_reference_forms.xml` 라우팅 추가 |

---

## WP-05E.3 — 롤백 및 운영 적용 순서

### 전제조건

OBJ-REF-05 (이 WO) + OBJ-REF-08 (Content factory QA) 완료 전 운영 적용 금지.

### 운영 적용 순서

```
1. tai-api: Migration 적용 (3개 파일 순서대로)
   a. 20261011_reference_forms_core.sql   (9 테이블)
   b. 20261011_reference_forms_storage.sql (버킷 + Policy)
   c. 20261011_reference_forms_outbox_rpc.sql (RPC + Trigger)

2. tai-api: 신규 라우터 + Adapter 코드 배포 (Railway)

3. 검증: ATOM-01~04 테스트 실행

4. tai-www: composite-entry.js 수정 + 신규 페이지 파일 배포 (Cloudflare Workers)

5. 검증: 상세 페이지 SSR 렌더링 확인 (임시 DRAFT 서식으로)

6. Owner 공개 승인 → rpc_publish_reference_form 호출

7. UNPUB-01~06 테스트 실행
```

### 롤백 계획

| 단계 | 롤백 방법 |
|------|---------|
| Migration 이후 | `DROP TABLE` 역순 실행 (서비스 영향 없음 — 기존 테이블과 독립) |
| tai-api 배포 이후 | Railway 이전 revision으로 즉시 rollback |
| tai-www 배포 이후 | Cloudflare Workers 이전 버전으로 즉시 rollback |
| 색인 후 | UNPUBLISH → tombstone → OpenSearch 삭제 |

---

## composite-entry.js 라우팅 추가 계약

**파일:** `tai-www/workers/composite-entry.js`

추가할 패턴 2건:

```js
// 기존 패턴 이후에 추가
if (/^\/reference-form\/[^/]+\/?$/.test(pathname)) {
  return astroPremiumWorker.fetch(request, env, ctx);
}
if (/^\/sitemap_reference_forms\.xml$/.test(pathname)) {
  return astroPremiumWorker.fetch(request, env, ctx);
}
```

**근거:** `prerender = false` 인 Astro SSR 페이지는 composite-entry.js 에 명시적으로 등록해야 `astroPremiumWorker` 로 라우팅된다. 등록 없이는 `existingLiveWorker` 가 처리 → 404.

---

## 미결 항목 (GPT 결정 필요)

| ID | 항목 | 옵션 |
|----|------|------|
| DCSN-01 | Outbox 원자성 방식 | A(Trigger) vs B(RPC) — B 권고 |
| DCSN-02 | 다운로드 방식 | Method A(스트리밍) vs Method B(Signed URL) — A 권고 |
| DCSN-03 | CF 캐시 무효화 | UNPUBLISH 시 CF Cache Purge 자동화 여부 |
| DCSN-04 | Admin CMS 라우터 prefix | `/admin/reference-forms/` vs `/reference-forms/admin/` |
| DCSN-05 | SEO description 소스 | `reference_form_content.description` 필수화 vs `summary` fallback |

---

## 게이트 조건

| 조건 | 상태 |
|------|------|
| GPT_REF05_CMS_DETAIL_DESIGN_VERIFY | PENDING |
| OBJ-REF-08 Content factory QA | BLOCKED |
| Owner 최종 공개 승인 | PENDING |

**운영 DB 적용·배포·색인·PR merge 금지 (게이트 해소 전).**
