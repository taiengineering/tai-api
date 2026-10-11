---
wo: WO-REF05-CMS-DESIGN-REPAIR-002
date: 2026-10-11
status: DESIGN_REPAIR_READY
section: OBJ-REF-05
publication: NOT_FOR_PUBLICATION
dependency: OBJ-REF-08 (BLOCKED)
parent: WO-REF05-CMS-PUBLIC-INTEGRATION-DESIGN-001.md
next_gate: GPT_REF05_CMS_DETAIL_DESIGN_VERIFY_R2
scope: DOCS / DESIGN REPAIR ONLY — 운영 DB DDL·데이터·OpenSearch·배포·PR merge·외부공개 금지
---

# REF-05 CMS 설계 보완 (v2 — REPAIR)

WO-REF05-CMS-DESIGN-REPAIR-002.

GPT_REF05_CMS_DETAIL_DESIGN_VERIFY HOLD 판정에서 확인된 결함 수정.
기존 설계 방향(RPC 원자성 B, Method A 스트리밍, 9 테이블 구조)은 유지.

---

## 1. Outbox RPC 시그니처 교정

### 1.1 실제 함수 계약 (소스: `20260920_shared_search_incremental_outbox.sql`)

```sql
CREATE OR REPLACE FUNCTION public.enqueue_search_index_sync(
    p_domain_name   TEXT,          -- arg 1
    p_object_type   TEXT,          -- arg 2
    p_canonical_id  TEXT,          -- arg 3  ← UUID 문자열 (참고서식 form_id)
    p_event_key     TEXT,          -- arg 4  ← 이벤트별 고유 키
    p_reason        TEXT DEFAULT NULL  -- arg 5  ← 이벤트 타입 (사유)
) RETURNS BIGINT
```

**canonical_id = UUID 문자열.** `REFERENCE_FORM::` 접두사는 OpenSearch writer 내부 문서 ID이며 어댑터/RPC 계층에서 붙이지 않는다.

### 1.2 교정된 RPC PERFORM 호출

```sql
PERFORM public.enqueue_search_index_sync(
    'REFERENCE_FORM',                                    -- p_domain_name
    'REFERENCE_FORM',                                    -- p_object_type
    p_form_id::text,                                     -- p_canonical_id (UUID)
    'reference_form:' || p_form_id::text || ':' || v_event_id::text,  -- p_event_key
    'PUBLISHED'                                          -- p_reason
);
```

### 1.3 교정된 RPC 3종

#### rpc_publish_reference_form

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
    v_event_id         UUID;
    v_approved_hash    TEXT;
    v_current_hash     TEXT;
BEGIN
    -- 1. DRAFT + owner_approved 확인
    SELECT approved_content_hash INTO v_approved_hash
      FROM public.reference_form_approvals
     WHERE form_id = p_form_id
       AND is_current = true
       AND approval_status = 'APPROVED'
     LIMIT 1;

    IF v_approved_hash IS NULL THEN
        RAISE EXCEPTION 'PUBLISH_PRECONDITION_FAILED: no current APPROVED approval record';
    END IF;

    -- 2. 현재 콘텐츠 해시 일치 확인 (승인 후 변경 차단)
    SELECT content_hash INTO v_current_hash
      FROM public.reference_form_content
     WHERE form_id = p_form_id
     LIMIT 1;

    IF v_current_hash IS DISTINCT FROM v_approved_hash THEN
        RAISE EXCEPTION 'PUBLISH_PRECONDITION_FAILED: content changed after approval — re-approval required';
    END IF;

    -- 3. 게시 상태 전이
    UPDATE public.reference_forms
       SET status       = 'PUBLISHED',
           published_at = now()
     WHERE id = p_form_id
       AND status IN ('DRAFT');

    IF NOT FOUND THEN
        RAISE EXCEPTION 'PUBLISH_PRECONDITION_FAILED: form not in DRAFT state';
    END IF;

    -- 4. 감사 이벤트 기록
    INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
    VALUES (p_form_id, 'PUBLISHED', p_actor, p_payload)
    RETURNING id INTO v_event_id;

    -- 5. Outbox enqueue (동일 트랜잭션 — fail-closed)
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

#### rpc_unpublish_reference_form

```sql
CREATE OR REPLACE FUNCTION public.rpc_unpublish_reference_form(
    p_form_id  UUID,
    p_actor    TEXT,
    p_reason   TEXT DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE v_event_id UUID;
BEGIN
    UPDATE public.reference_forms
       SET status = 'DRAFT'
     WHERE id = p_form_id
       AND status = 'PUBLISHED';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'UNPUBLISH_PRECONDITION_FAILED: form not PUBLISHED';
    END IF;

    INSERT INTO public.reference_form_events (form_id, event_type, actor, payload)
    VALUES (p_form_id, 'UNPUBLISHED', p_actor,
            jsonb_build_object('reason', p_reason))
    RETURNING id INTO v_event_id;

    PERFORM public.enqueue_search_index_sync(
        'REFERENCE_FORM',
        'REFERENCE_FORM',
        p_form_id::text,
        'reference_form:' || p_form_id::text || ':' || v_event_id::text,
        'UNPUBLISHED'
    );

    RETURN v_event_id;
END;
$$;
```

#### rpc_change_slug_reference_form

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
BEGIN
    -- 1. 현재 slug 조회
    SELECT canonical_slug INTO v_old_slug
      FROM public.reference_form_content
     WHERE form_id = p_form_id
     LIMIT 1;

    IF v_old_slug IS NULL THEN
        RAISE EXCEPTION 'SLUG_CHANGE_FAILED: no content row for form_id';
    END IF;

    -- 2. 새 slug 전역 충돌 확인 (§7 통합 slug 예약)
    PERFORM public.fn_assert_slug_globally_unique(p_new_slug, p_form_id);

    -- 3. slug 변경
    UPDATE public.reference_form_content
       SET canonical_slug = p_new_slug
     WHERE form_id = p_form_id;

    -- 4. 이전 slug 이력 등록 (301 redirect 근거)
    INSERT INTO public.reference_form_slug_history
        (form_id, lang, old_slug, new_slug)
    VALUES (p_form_id, 'ko', v_old_slug, p_new_slug)
    ON CONFLICT (old_slug) DO NOTHING;  -- 동일 old_slug 재등록 방지

    -- 5. 감사 이벤트 + Outbox
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

### 1.4 RPC 실행 권한

```sql
REVOKE ALL ON FUNCTION public.rpc_publish_reference_form(UUID, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.rpc_unpublish_reference_form(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.rpc_change_slug_reference_form(UUID, TEXT, TEXT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.rpc_publish_reference_form(UUID, TEXT, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.rpc_unpublish_reference_form(UUID, TEXT, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.rpc_change_slug_reference_form(UUID, TEXT, TEXT) TO service_role;
```

---

## 2. OpenSearch Adapter 교정

### 2.1 실제 DomainAdapter Protocol (소스: `adapters/base.py`)

```python
class DomainAdapter(Protocol):
    domain_name: str      # 'REFERENCE_FORM'
    object_type: str      # 'REFERENCE_FORM'

    def iter_documents(self) -> Iterator[dict]: ...
    def iter_expected_hashes(self) -> Iterator[dict]: ...
    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]: ...
```

- `async fetch_document()` — 존재하지 않음 (이전 설계 오류)
- `DOMAIN_ADAPTERS` 딕셔너리 — 존재하지 않음 (`build_production_adapters()` 는 `list` 반환)
- `canonical_id` — UUID 문자열만 (`REFERENCE_FORM::` 접두사 없음)

### 2.2 교정된 ReferenceFormAdapter

```python
# services/shared_search/adapters/reference_form.py (신규)

"""REFERENCE_FORM adapter — WO-REF05-CMS-DESIGN-REPAIR-002.

Source of truth: reference_form_public_view (PUBLISHED + owner_approved
  + file_qa_approved — 조건 해소 후 CMS 테이블 직접 조회).

Public detail route: tai-www /reference-form/{canonical_slug} (신규 SSR 페이지).
"""
from __future__ import annotations

from typing import Callable, Iterable, Iterator, Optional

from services.shared_search.adapters._common import (
    expected_hashes_from_documents,
)


Fetcher = Callable[[], Iterable[dict]]


class ReferenceFormAdapter:
    domain_name = "REFERENCE_FORM"
    object_type = "REFERENCE_FORM"

    def __init__(
        self,
        *,
        fetch_current: Fetcher,
        fetch_by_id: Optional[Callable[[str], Optional[dict]]] = None,
    ):
        self._fetch_current = fetch_current
        self._fetch_by_id = fetch_by_id or (lambda _id: None)

    def iter_documents(self) -> Iterator[dict]:
        for row in self._fetch_current():
            payload = _normalize_reference_form(row)
            if payload is not None:
                yield payload

    def iter_expected_hashes(self) -> Iterator[dict]:
        yield from expected_hashes_from_documents(self.iter_documents)

    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]:
        """Return SearchDocument payload or None (tombstone) for a single form_id."""
        row = self._fetch_by_id(canonical_id)
        if row is None:
            return None  # UNPUBLISHED / ARCHIVED → tombstone
        return _normalize_reference_form(row)


def _normalize_reference_form(row: dict) -> Optional[dict]:
    """Map reference_form_public_view row → SearchDocument payload dict."""
    form_id  = row.get("id")
    slug     = row.get("canonical_slug")
    title    = row.get("title")

    if not form_id or not slug or not title:
        return None

    description  = row.get("description") or ""
    published_at = row.get("published_at")
    formats      = row.get("formats") or []      # list[str] e.g. ["XLSX","PDF"]
    legacy_codes = row.get("legacy_codes") or []  # list[str] e.g. ["REF-C002"]

    search_text = " ".join(filter(None, [title, description] + legacy_codes))

    return {
        "object_type":        ReferenceFormAdapter.object_type,
        "canonical_id":       str(form_id),          # UUID 문자열만
        "source_id":          "REFERENCE_FORM_CMS",
        "source_key":         slug,
        "title":              title,
        "summary":            description or None,
        "search_text":        search_text,
        "aliases":            list(legacy_codes),
        "keywords":           list(formats),
        "subjects":           [],
        "context":            [],
        "public_url":         f"/reference-form/{slug}",
        "saas_url":           None,
        "publication_status": "PUBLISHED",
        "visibility_scopes":  ["PUBLIC", "SAAS", "PAID"],
        "source_updated_at":  published_at,
    }
```

### 2.3 교정된 production_bindings.py 연동

```python
# services/shared_search/production_bindings.py (기존 파일 수정)
# 추가 import:
from services.shared_search.adapters.reference_form import ReferenceFormAdapter

# build_production_adapters() 내부 — adapters 리스트에 추가:
def _make_reference_form_adapter(client: SupabaseClient) -> ReferenceFormAdapter:
    def _iter_current() -> Iterator[dict]:
        yield from paginate_supabase(
            client,
            table="reference_form_public_view",   # PUBLISHED + owner_approved 뷰
            select=(
                "id,canonical_slug,title,description,"
                "published_at,formats,legacy_codes"
            ),
            order_column="id",
        )

    def _by_id(form_id: str) -> Optional[dict]:
        return _fetch_one(
            client, table="reference_form_public_view",
            select=(
                "id,canonical_slug,title,description,"
                "published_at,formats,legacy_codes"
            ),
            key_column="id", key_value=form_id,
        )

    return ReferenceFormAdapter(fetch_current=_iter_current, fetch_by_id=_by_id)


# build_production_adapters() 내부 adapters 리스트 끝에 추가:
# adapters.append(_make_reference_form_adapter(client))
# (REF-08 QA BLOCKED 해소 후 활성화 — 그 전에는 줄 주석 처리)
```

### 2.4 reference_form_public_view DDL (조회 전용 뷰)

```sql
-- 게시 + Owner 승인 + 파일 QA 완료된 서식만 노출
CREATE OR REPLACE VIEW public.reference_form_public_view AS
SELECT
    rf.id,
    rfc.canonical_slug,
    rfc.title,
    rfc.description,
    rf.published_at,
    ARRAY(
        SELECT DISTINCT rff.format
          FROM public.reference_form_files rff
         WHERE rff.form_id = rf.id
           AND rff.is_active = true
           AND rff.qa_status = 'QA_PASS'
    ) AS formats,
    ARRAY(
        SELECT rfl.legacy_code
          FROM public.reference_form_legacy_links rfl
         WHERE rfl.form_id = rf.id
    ) AS legacy_codes
  FROM public.reference_forms rf
  JOIN public.reference_form_content rfc ON rfc.form_id = rf.id
 WHERE rf.status = 'PUBLISHED'
   AND rf.owner_approved = true;
```

---

## 3. 파일 메타데이터·검수 스키마 보완

### 3.1 교정된 `reference_form_files` DDL

```sql
CREATE TABLE public.reference_form_files (
    id                UUID        NOT NULL DEFAULT gen_random_uuid(),
    form_id           UUID        NOT NULL,

    -- Storage 위치
    file_ref          TEXT        NOT NULL,  -- 'storage://reference-forms/{path}'
    bucket            TEXT        NOT NULL DEFAULT 'reference-forms',

    -- 파일 식별
    format            TEXT        NOT NULL
                                  CHECK (format IN ('XLSX','DOCX','PDF','HWPX','HWP','ETC')),
    display_name      TEXT        NOT NULL,
    mime_type         TEXT        NOT NULL,
    file_size_bytes   BIGINT,
    sha256_checksum   TEXT,       -- 원본 파일 SHA256 16진수
    sort_order        INTEGER     NOT NULL DEFAULT 0,

    -- 버전 관리
    file_version      TEXT        NOT NULL DEFAULT '1',
    source_file_id    UUID,       -- 이 파일의 원본 버전 참조 (self-FK)
    is_latest_version BOOLEAN     NOT NULL DEFAULT true,

    -- 파일별 QA 검수
    qa_status         TEXT        NOT NULL DEFAULT 'PENDING'
                                  CHECK (qa_status IN ('PENDING','QA_PASS','QA_FAIL','QA_BLOCKED')),
    qa_reviewer       TEXT,
    qa_reviewed_at    TIMESTAMPTZ,
    qa_notes          TEXT,

    -- 공개 미리보기 연결 (§6 참조)
    preview_artifact_id UUID,     -- reference_form_preview_artifacts.id FK (별도 테이블)

    -- 콘텐츠 공개 승인
    approved_version  TEXT,       -- 승인된 file_version
    approved_at       TIMESTAMPTZ,
    approved_by       TEXT,

    -- 상태
    is_active         BOOLEAN     NOT NULL DEFAULT true,
    deactivated_at    TIMESTAMPTZ,
    deactivation_reason TEXT,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT reference_form_files_pkey PRIMARY KEY (id),
    CONSTRAINT reference_form_files_form_id_fk
        FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
        ON DELETE RESTRICT,   -- 부모 삭제 차단: 파일 보존 우선
    CONSTRAINT reference_form_files_source_fk
        FOREIGN KEY (source_file_id) REFERENCES public.reference_form_files (id),
    CONSTRAINT reference_form_files_file_ref_chk
        CHECK (file_ref ~ '^storage://'),
    CONSTRAINT reference_form_files_sha256_chk
        CHECK (sha256_checksum IS NULL OR sha256_checksum ~ '^[0-9a-f]{64}$')
);

CREATE INDEX reference_form_files_form_active_idx
    ON public.reference_form_files (form_id)
    WHERE is_active = true AND qa_status = 'QA_PASS';

CREATE TRIGGER reference_form_files_updated_at
    BEFORE UPDATE ON public.reference_form_files
    FOR EACH ROW EXECUTE FUNCTION public.fn_reference_forms_set_updated_at();

ALTER TABLE public.reference_form_files ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_files FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_files TO service_role;
```

**REF-08 연결 계약:**
- `qa_status = 'QA_PASS'` 가 아닌 파일은 다운로드·미리보기·목록 모두에서 제외
- `is_active = true AND qa_status = 'QA_PASS' AND approved_at IS NOT NULL` 세 조건 모두 충족한 파일만 공개

---

## 4. 출처·이용권 검증 (reference_form_sources 보완)

```sql
CREATE TABLE public.reference_form_sources (
    id                UUID  NOT NULL DEFAULT gen_random_uuid(),
    form_id           UUID  NOT NULL,
    source_type       TEXT  NOT NULL
                           CHECK (source_type IN ('KOSHA','MOL','MOEL','OFFICIAL_URL','ETC')),
    source_id         TEXT,
    source_url        TEXT,
    source_title      TEXT,
    source_org        TEXT,          -- 출처 기관명

    -- 현행성
    verified_at       TIMESTAMPTZ,   -- 출처 확인일
    next_review_at    TIMESTAMPTZ,   -- 재확인 예정일

    -- 이용권
    license_type      TEXT,
    commercial_use    BOOLEAN,       -- 상업적 이용 허용 여부 (NULL = 불명확)
    derivative_works  BOOLEAN,       -- 변형·파생 허용 여부 (NULL = 불명확)
    redistribution    BOOLEAN,       -- 재배포 허용 여부 (NULL = 불명확)
    license_url       TEXT,
    license_notes     TEXT,

    -- 권리 검토
    rights_status     TEXT  NOT NULL DEFAULT 'REVIEW_REQUIRED'
                           CHECK (rights_status IN ('REVIEW_REQUIRED','CLEARED','BLOCKED')),
    rights_reviewer   TEXT,
    rights_reviewed_at TIMESTAMPTZ,
    rights_evidence   TEXT,          -- 검토 근거 요약

    note              TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT reference_form_sources_pkey PRIMARY KEY (id),
    CONSTRAINT reference_form_sources_form_id_fk
        FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
        ON DELETE RESTRICT
);

ALTER TABLE public.reference_form_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_sources FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_sources TO service_role;
```

**법적 의무 사항:** 법령 판단이 필요한 항목은 LEG SoT (law_article) 와 연결한다. 이 테이블은 출처 메타데이터만 기록하며, 법적 의무 자동 생성 또는 추론 금지.

---

## 5. 공개 미리보기 아티팩트 테이블

```sql
-- 비회원 열람용 파생 미리보기 파일 (원본 ≠ 미리보기)

CREATE TABLE public.reference_form_preview_artifacts (
    id                   UUID  NOT NULL DEFAULT gen_random_uuid(),
    form_id              UUID  NOT NULL,
    source_file_id       UUID  NOT NULL,  -- reference_form_files.id

    -- 파생본 위치 (원본과 다른 경로 필수)
    preview_ref          TEXT  NOT NULL,  -- 'storage://reference-forms-preview/{path}'

    -- 버전 추적
    preview_version      TEXT  NOT NULL DEFAULT '1',
    source_file_sha256   TEXT  NOT NULL,  -- 원본 해시 (파생 기준점)
    preview_artifact_sha TEXT,            -- 파생본 해시

    -- 페이지 정보
    page_count           INTEGER,
    preview_page_count   INTEGER,  -- 공개 페이지 수 (전체 페이지 미만 가능)

    -- 검수 상태
    generation_status    TEXT  NOT NULL DEFAULT 'PENDING'
                              CHECK (generation_status IN (
                                  'PENDING','GENERATING','READY','FAILED')),
    qa_status            TEXT  NOT NULL DEFAULT 'PENDING'
                              CHECK (qa_status IN ('PENDING','QA_PASS','QA_FAIL')),
    qa_reviewer          TEXT,
    qa_reviewed_at       TIMESTAMPTZ,

    -- 공개 승인
    is_published         BOOLEAN NOT NULL DEFAULT false,
    published_at         TIMESTAMPTZ,
    unpublished_at       TIMESTAMPTZ,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT reference_form_preview_artifacts_pkey PRIMARY KEY (id),
    CONSTRAINT reference_form_preview_artifacts_unique
        UNIQUE (source_file_id, preview_version),
    CONSTRAINT reference_form_preview_artifacts_form_id_fk
        FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
        ON DELETE RESTRICT,
    CONSTRAINT reference_form_preview_artifacts_source_fk
        FOREIGN KEY (source_file_id) REFERENCES public.reference_form_files (id),
    CONSTRAINT reference_form_preview_artifacts_ref_chk
        CHECK (preview_ref ~ '^storage://reference-forms-preview/')
);

ALTER TABLE public.reference_form_preview_artifacts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_preview_artifacts FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.reference_form_preview_artifacts TO service_role;
```

### 미리보기 API 계약

```
GET /reference-forms/{form_slug}/preview/{file_id}
인증: 불필요 (비회원 열람 허용)
```

서버 흐름:
1. `form.status = 'PUBLISHED' AND owner_approved = true` 확인 → 아니면 404
2. `reference_form_preview_artifacts.is_published = true AND qa_status = 'QA_PASS'` 확인 → 아니면 404
3. `source_file_sha256`와 현재 `reference_form_files.sha256_checksum` 일치 확인 → 불일치 시 `410 Gone` (미리보기 구버전)
4. 미리보기 파일 스트리밍 응답 (원본 Storage URL 미노출)
5. `Cache-Control: public, max-age=3600` (공개 취소 전까지만 허용)

**공개 취소 시:** `reference_form_preview_artifacts.is_published = false` 즉시 → API 404 반환 → CDN 무효화 (별도 WO 범위).

---

## 6. 승인 버전 바인딩 (reference_form_approvals)

`owner_approved = boolean` 단독으로는 "어느 버전이 승인됐는가"를 알 수 없다.

```sql
CREATE TABLE public.reference_form_approvals (
    id                   UUID  NOT NULL DEFAULT gen_random_uuid(),
    form_id              UUID  NOT NULL,
    approver             TEXT  NOT NULL,
    approved_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- 승인 당시 콘텐츠 해시 (reference_form_content.content_hash)
    approved_content_hash TEXT NOT NULL,

    -- 승인 당시 활성 파일 해시 목록 (JSON array of {file_id, sha256})
    approved_file_hashes  JSONB NOT NULL DEFAULT '[]',

    -- 승인 상태
    approval_status      TEXT  NOT NULL DEFAULT 'APPROVED'
                              CHECK (approval_status IN ('APPROVED','REVOKED')),
    revoked_at           TIMESTAMPTZ,
    revocation_reason    TEXT,

    is_current           BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT reference_form_approvals_pkey PRIMARY KEY (id),
    CONSTRAINT reference_form_approvals_form_id_fk
        FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX reference_form_approvals_current_idx
    ON public.reference_form_approvals (form_id)
    WHERE is_current = true AND approval_status = 'APPROVED';

ALTER TABLE public.reference_form_approvals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_approvals FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.reference_form_approvals TO service_role;
```

**승인 무효화 조건:**
- 콘텐츠(`title`, `description`, `body_html`) 변경 → `content_hash` 갱신 → 승인 불일치 → PUBLISH 실패
- 파일 추가·삭제·버전 교체 → `approved_file_hashes` 불일치 → PUBLISH 실패
- 재승인 후 새 `reference_form_approvals` 행 INSERT (기존 행 `is_current=false` 처리)

**content_hash 생성 기준:**
`reference_form_content.content_hash = SHA256(canonical_slug + title + description + body_html)` — 순서 고정, 정규화된 UTF-8.

---

## 7. Slug 전역 충돌 차단

### 문제: 세 테이블 간 cross-table 중복

- `reference_form_content.canonical_slug UNIQUE` — 현재 slug
- `reference_form_slug_history.old_slug UNIQUE` — 이전 slug
- `reference_form_aliases.alias_slug UNIQUE` — 별칭 slug

각 테이블 내부에서는 UNIQUE이지만 테이블 간 같은 값이 들어갈 수 있다.

### 해결: 통합 slug 예약 테이블

```sql
CREATE TABLE public.reference_form_slug_registry (
    slug         TEXT  NOT NULL,
    form_id      UUID  NOT NULL,
    slug_type    TEXT  NOT NULL
                       CHECK (slug_type IN ('CANONICAL','HISTORY','ALIAS')),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT reference_form_slug_registry_pkey PRIMARY KEY (slug),  -- 전역 UNIQUE
    CONSTRAINT reference_form_slug_registry_form_id_fk
        FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
        ON DELETE RESTRICT
);

ALTER TABLE public.reference_form_slug_registry ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reference_form_slug_registry FROM anon, authenticated;
GRANT SELECT, INSERT, DELETE ON public.reference_form_slug_registry TO service_role;
```

### fn_assert_slug_globally_unique

```sql
CREATE OR REPLACE FUNCTION public.fn_assert_slug_globally_unique(
    p_slug     TEXT,
    p_form_id  UUID  -- 자기 자신의 현재 slug 교체는 허용
)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.reference_form_slug_registry
         WHERE slug = p_slug
           AND form_id <> p_form_id   -- 다른 서식이 이미 사용 중
    ) THEN
        RAISE EXCEPTION 'SLUG_CONFLICT: slug already registered by another form';
    END IF;
END;
$$;
```

### slug 등록 흐름

1. 최초 slug 설정: `reference_form_slug_registry INSERT (slug, form_id, 'CANONICAL')`
2. slug 변경: registry의 기존 'CANONICAL' 행 삭제 → `INSERT (old_slug, form_id, 'HISTORY')` + `INSERT (new_slug, form_id, 'CANONICAL')`
3. alias 추가: `INSERT (alias_slug, form_id, 'ALIAS')`

---

## 8. 다운로드 스트리밍 교정 (Method A)

### 문제

이전 설계의 `Response(content=data, ...)` 는 Supabase Storage `.download()` 결과 전체를 메모리에 적재한다. 대용량 파일에 부적합.

### 교정: StreamingResponse

```python
# routers/reference_forms.py (교정된 다운로드 엔드포인트)

from fastapi.responses import StreamingResponse
import io

@router.get("/{form_slug}/files/{file_id}/download")
async def download_reference_form_file(
    form_slug: str,
    file_id: str,
    current_user: dict = Depends(get_current_user),
    supabase = Depends(get_supabase_client),
):
    # 1. 서식 게시 상태 — DB 직접 조회 (캐시 없음)
    form_row = _get_published_form_by_slug(supabase, form_slug)
    if not form_row:
        raise HTTPException(status_code=404, detail="NOT_FOUND_OR_UNPUBLISHED")

    # 2. 파일 소유권 + QA 검수 확인
    file_row = (supabase.table("reference_form_files")
        .select("file_ref, display_name, format, mime_type, sha256_checksum")
        .eq("id", file_id)
        .eq("form_id", form_row["id"])
        .eq("is_active", True)
        .eq("qa_status", "QA_PASS")
        .limit(1)
        .execute()
    )
    rows = list(getattr(file_row, "data", None) or [])
    if not rows:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND_OR_NOT_QA_PASSED")

    file_meta = rows[0]
    bucket, path = _parse_storage_ref(file_meta["file_ref"])

    # 3. Storage 서버에서 스트리밍 (Storage URL 브라우저 미전달)
    data: bytes = supabase.storage.from_(bucket).download(path)
    if not data:
        raise HTTPException(status_code=503, detail="FILE_STORAGE_UNAVAILABLE")

    def iter_chunks(content: bytes, chunk_size: int = 65536):
        buf = io.BytesIO(content)
        while True:
            chunk = buf.read(chunk_size)
            if not chunk:
                break
            yield chunk

    from urllib.parse import quote
    filename = quote(file_meta["display_name"])
    media_type = file_meta.get("mime_type") or "application/octet-stream"

    return StreamingResponse(
        content=iter_chunks(data),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Content-Length": str(len(data)),
            "Cache-Control": "no-store",   # 공개 취소 시 즉시 차단
            "X-Content-Type-Options": "nosniff",
        },
    )
```

**Content-Range / Range 요청:** 현재 Supabase Storage Python SDK는 Range 스트리밍 미지원. 대용량 파일 Range 지원은 별도 WO 범위.

---

## 9. 공개 취소 일관성 교정 (비동기 OpenSearch)

### 문제

이전 설계 §UNPUB-03: "공개 취소 후 OpenSearch 색인 확인 → delete 완료 후 검색 결과 없음"

OpenSearch Outbox는 비동기다. DB 트랜잭션 커밋 직후 OpenSearch에서 즉시 삭제되지 않는다.

### 교정된 UNPUBLISH 일관성 보장

| 계층 | 동작 | 완료 시점 |
|------|------|----------|
| DB 상태 전이 | `status = 'DRAFT'` | DB 트랜잭션 커밋 즉시 |
| 상세 페이지 | `GET /reference-forms/{slug}` → 404 | DB 트랜잭션 커밋 즉시 |
| 미리보기 | `preview.is_published = false` → 404 | DB 트랜잭션 커밋 즉시 |
| 다운로드 | 게시 상태 DB 재확인 → 403 | DB 트랜잭션 커밋 즉시 |
| Outbox enqueue | `search_index_outbox PENDING 생성` | DB 트랜잭션 커밋 즉시 |
| OpenSearch tombstone | `process_queue()` 처리 후 삭제 | 비동기 (수초~수분) |
| 검색 결과 비노출 | OpenSearch tombstone 완료 후 | 비동기 (수초~수분) |

**즉시 비노출이 필수인 경우 (설계 결정 DCSN-06):**

`public_safety_search.py` 에서 REFERENCE_FORM 결과를 반환하기 전 DB 게시 상태 재확인:

```python
# public_safety_search.py 검색 결과 후처리 (option)
# 성능 비용 있음 — 활성화 여부는 Owner 결정

def _filter_published(results, supabase):
    """REFERENCE_FORM 결과만 DB 게시 상태 재확인."""
    ids = [r["canonical_id"] for r in results
           if r.get("object_type") == "REFERENCE_FORM"]
    if not ids:
        return results
    published = {
        row["id"] for row in
        supabase.table("reference_forms")
            .select("id")
            .in_("id", ids)
            .eq("status", "PUBLISHED")
            .execute().data or []
    }
    return [r for r in results
            if r.get("object_type") != "REFERENCE_FORM"
            or r["canonical_id"] in published]
```

즉시 비노출 미적용 시: 공개 취소 후 OpenSearch tombstone 처리 완료 전 최대 수분간 검색 결과에 서식이 남을 수 있다. 상세 페이지 / 다운로드는 즉시 차단된다.

---

## 10. reference_form_events 보존 정책 교정

### 문제

이전 DDL에 `FOREIGN KEY ... ON DELETE CASCADE` — 부모 서식 삭제 시 감사 로그 함께 삭제됨. 불변 감사 로그와 모순.

### 교정

```sql
-- reference_form_events FK 교정
CONSTRAINT reference_form_events_form_id_fk
    FOREIGN KEY (form_id) REFERENCES public.reference_forms (id)
    ON DELETE RESTRICT   -- 이벤트 존재하면 부모 삭제 금지
```

**부모 테이블 삭제 정책:** `reference_forms` 삭제는 원칙적으로 허용하지 않는다. 서식 폐기는 `ARCHIVED` 상태 전이로 처리한다.

모든 `reference_form_*` 테이블의 FK를 `ON DELETE CASCADE` → `ON DELETE RESTRICT` 로 교정.

---

## 11. composite-entry.js 라우팅 교정

### 확인된 실제 변수명 (소스: `workers/composite-entry.js`)

```js
const p = new URL(request.url).pathname;  // 변수명 p (pathname 아님)
```

### 교정된 추가 패턴 (기존 라우팅 끝에 삽입)

```js
// WO-REF05: 참고서식 상세 페이지 (Astro SSR, prerender=false)
if (p === '/reference-form' || p === '/reference-form/') {
  return astroPremiumWorker.fetch(rewritePath(request, '/reference-form'), env, ctx);
}
if (/^\/reference-form\/[^/]+$/.test(p)) {
  return astroPremiumWorker.fetch(request, env, ctx);
}
if (/^\/reference-form\/[^/]+\/$/.test(p)) {
  return astroPremiumWorker.fetch(rewritePath(request, p.slice(0, -1)), env, ctx);
}
// WO-REF05: 참고서식 동적 sitemap (prerender=false)
if (p === '/sitemap_reference_forms.xml') {
  return astroPremiumWorker.fetch(request, env, ctx);
}
```

**후행 슬래시 정규화:** 기존 `/safety-guide/[id]/` 패턴과 동일하게 trailing slash를 `rewritePath` 로 제거 후 SSR로 전달.

---

## 12. pages-live-worker.js sitemap index 추가

### 현재 상태

`handleSitemapIndex()` 는 `/sitemap_index.xml` 을 동적 생성한다. 현재 sitemap 목록에 `sitemap_reference_forms.xml` 없음.

### 추가 계약

```js
// handleSitemapIndex() 내부 sitemaps 배열에 추가:
// (reference_form_public_view에서 max(updated_at) 조회 — 다른 동적 sitemap과 동일 패턴)
{ loc: SN_SITE + "/sitemap_reference_forms.xml", lastmod: maxLm(refFormLm, "updated_at") || "2026-10-11" },
```

`refFormLm` 조회:
```js
const [knLm, snLm, ..., refFormLm] = await Promise.all([
  ...,
  taengGET("/reference_form_public_view?select=updated_at&order=updated_at.desc.nullslast&limit=1"),
]);
```

REF-08 QA 완료 + Owner 공개 승인 전에는 이 항목이 sitemap_index에 포함되어도 `sitemap_reference_forms.xml` 이 빈 XML을 반환하도록 Astro 엔드포인트가 처리한다.

---

## 13. public_safety_search.py allowlist 추가

```python
# routers/public_safety_search.py (기존 파일 수정)

_PUBLIC_OBJECT_TYPES: list[str] = [
    "GUIDE",
    "SAFETY_MATERIAL",
    "CSI_ACCIDENT",
    "CHEM",
    "CHEM_REGULATION",
    "KNOWLEDGE",
    "PRECEDENT",
    "LEGAL",
    "REFERENCE_FORM",   # 추가
]

_TYPE_MAP: dict[str, list[str]] = {
    # ... 기존 ...
    "reference_form": ["REFERENCE_FORM"],  # 추가
}
```

REF-08 QA BLOCKED 해소 전에는 `REFERENCE_FORM` 을 `_PUBLIC_OBJECT_TYPES` 에 추가해도 실제 색인된 문서가 없으므로 검색 결과에 노출되지 않는다. 활성화 시점을 맞추기 위해 adapter 등록과 동시에 추가한다.

---

## 14. 비회원 다운로드 모달 복귀 redirect

WO-REF04-REF09-UI-SPECIFICATION-001 §4/5 계약 유지:

API 응답 계약:
- 비회원 다운로드 클릭 → 프론트엔드에서 로그인 모달 표시 (서버 호출 없이 UI가 먼저 처리)
- JWT 없이 API 호출 시 → `401 UNAUTHORIZED` with `{"detail": "LOGIN_REQUIRED"}`
- 로그인 완료 후 `returnTo=/reference-form/{slug}` redirect 파라미터로 원래 페이지 복귀

---

## 15. 수정 대상 전체 파일 목록 (교정)

### tai-api (신규 파일 — 교정)

| 파일 경로 | 설명 |
|----------|------|
| `supabase/migrations/20261011_reference_forms_core.sql` | 11 테이블 DDL + RLS (approvals + slug_registry + preview_artifacts 추가) |
| `supabase/migrations/20261011_reference_forms_storage.sql` | reference-forms + reference-forms-preview 버킷 |
| `supabase/migrations/20261011_reference_forms_rpc.sql` | RPC 3종 + fn_assert_slug_globally_unique + public_view |
| `routers/reference_forms.py` | 공개 API + Admin API + StreamingResponse 다운로드 + 미리보기 API |
| `services/shared_search/adapters/reference_form.py` | REFERENCE_FORM DomainAdapter |

### tai-api (기존 파일 수정 — 교정)

| 파일 경로 | 수정 내용 |
|----------|---------|
| `main.py` | reference_forms 라우터 include |
| `services/shared_search/production_bindings.py` | `_make_reference_form_adapter()` + `adapters.append(...)` |
| `routers/public_safety_search.py` | `_PUBLIC_OBJECT_TYPES` + `_TYPE_MAP` 에 REFERENCE_FORM 추가 |
| `services/shared_search/adapters/__init__.py` | `ReferenceFormAdapter` export 추가 |

### tai-www (신규 파일 — 교정)

| 파일 경로 | 설명 |
|----------|------|
| `src/pages/reference-form/[slug].astro` | SSR 상세 페이지 (prerender=false) |
| `src/pages/sitemap_reference_forms.xml.js` | 동적 sitemap (prerender=false) |
| `src/lib/api/referenceForms.ts` | tai-api 호출 클라이언트 |

### tai-www (기존 파일 수정 — 교정)

| 파일 경로 | 수정 내용 |
|----------|---------|
| `workers/composite-entry.js` | `/reference-form/` + trailing slash + sitemap 4개 패턴 추가 (`p` 변수 사용) |
| `workers/pages-live-worker.js` | `handleSitemapIndex()` 에 `sitemap_reference_forms.xml` 추가 |

---

## 16. 격리 테스트 계획

### T1 — RPC 인자 순서 및 SQL 시그니처 정합

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T1-01 | `rpc_publish_reference_form` PASS 케이스 | outbox PENDING 1건, event_type=PUBLISHED |
| T1-02 | `rpc_unpublish_reference_form` PASS 케이스 | outbox PENDING 1건, event_type=UNPUBLISHED |
| T1-03 | `rpc_change_slug_reference_form` PASS 케이스 | slug_history 1건, slug_registry 교체 |
| T1-04 | outbox `event_key` 동일 재시도 | `ON CONFLICT DO NOTHING` — 중복 없음 |
| T1-05 | 서로 다른 CMS 변경 이벤트 2건 | 각각 고유 event_key, outbox 2건 |

### T2 — Adapter Protocol 정합

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T2-01 | `ReferenceFormAdapter` Protocol 검사 | `isinstance(adapter, DomainAdapter)` True |
| T2-02 | `iter_documents()` — PUBLISHED 서식 | `publication_status="PUBLISHED"`, `canonical_id=UUID 문자열` |
| T2-03 | `iter_documents()` — DRAFT 서식 | yield 없음 |
| T2-04 | `object_reindex_payload(form_id)` — 존재 | payload dict 반환 |
| T2-05 | `object_reindex_payload(form_id)` — UNPUBLISHED | None 반환 (tombstone) |
| T2-06 | SearchDocument 필드 검증 | `forbidden_document_keys` 없음, 필수 필드 존재 |

### T3 — 원자적 롤백

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T3-01 | publish RPC — status 전이 성공, outbox INSERT 실패 | 전체 ROLLBACK, status=DRAFT 유지 |
| T3-02 | publish RPC — content_hash 불일치 | 예외 발생, 전체 ROLLBACK |
| T3-03 | publish RPC — approval_status 없음 | 예외 발생, 전체 ROLLBACK |
| T3-04 | 승인 후 content 변경 | publish 시 content_hash 불일치 → FAIL |

### T4 — 파일·QA 격리

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T4-01 | `qa_status='PENDING'` 파일 다운로드 | 404 |
| T4-02 | `qa_status='QA_PASS'` 파일 다운로드 (인증) | 200 StreamingResponse |
| T4-03 | 타 서식의 `file_id` 다운로드 시도 | 404 (form_id 불일치) |
| T4-04 | 파일 sha256 변조 후 미리보기 요청 | 410 Gone |
| T4-05 | 비인증 다운로드 시도 | 401 |

### T5 — 공개 취소 일관성

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T5-01 | UNPUBLISH 직후 상세 페이지 | 404 즉시 |
| T5-02 | UNPUBLISH 직후 미리보기 API | 404 즉시 |
| T5-03 | UNPUBLISH 직후 다운로드 API | 403 즉시 |
| T5-04 | UNPUBLISH 직후 outbox | PENDING 1건 생성됨 |
| T5-05 | OpenSearch tombstone 처리 전 검색 | 서식 검색 결과 노출될 수 있음 (비동기 지연 명시) |
| T5-06 | ARCHIVED 전환 후 상세 페이지 | 404 |

### T6 — Slug 충돌

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T6-01 | 동일 slug 두 서식에 할당 시도 | slug_registry UNIQUE 위반 |
| T6-02 | 이전 slug를 다른 서식에 재할당 시도 | fn_assert_slug_globally_unique 예외 |
| T6-03 | alias와 canonical 충돌 시도 | slug_registry UNIQUE 위반 |
| T6-04 | slug 변경 후 이전 slug 301 redirect | slug_history에서 new_slug 조회 성공 |

### T7 — composite-entry.js 라우팅

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T7-01 | `GET /reference-form/safe-work-permit` | `astroPremiumWorker` 호출 |
| T7-02 | `GET /reference-form/safe-work-permit/` (trailing slash) | `rewritePath` 후 SSR |
| T7-03 | `GET /sitemap_reference_forms.xml` | `astroPremiumWorker` 호출 |
| T7-04 | 기존 `/safety-guide/[id]` 패턴 | 회귀 없음 |

### T8 — SEO · 사이트맵 · 검색 E2E

| ID | 시나리오 | 기댓값 |
|----|---------|--------|
| T8-01 | 게시 서식 상세 페이지 title 길이 | ≤ 60자 (seo-meta-lint PASS) |
| T8-02 | 게시 서식 상세 페이지 description 길이 | 30–170자 (seo-meta-lint PASS) |
| T8-03 | sitemap_reference_forms.xml — 게시 서식 포함 | URL 존재 |
| T8-04 | sitemap_reference_forms.xml — DRAFT 서식 | URL 없음 |
| T8-05 | sitemap_index.xml — reference_forms 항목 | 포함됨 |
| T8-06 | 통합검색 결과 카드 href | `/reference-form/{slug}` 일치 |
| T8-07 | SearchDocument.canonical_id | UUID 문자열만 (접두사 없음) |

---

## 17. 운영 적용 순서 (교정)

```
1. tai-api: Migration 적용 (순서 필수)
   a. 20261011_reference_forms_core.sql     (11 테이블 + 뷰)
   b. 20261011_reference_forms_storage.sql  (2개 버킷)
   c. 20261011_reference_forms_rpc.sql      (RPC 3종 + 슬러그 함수)

2. tai-api: adapters/reference_form.py + production_bindings.py + router

3. T1~T4 격리 테스트 실행

4. REF-08 파일 QA 검증 완료 후: qa_status='QA_PASS' 파일 등록

5. Owner 공개 승인 → rpc_publish_reference_form 호출

6. tai-www: composite-entry.js + pages-live-worker.js + Astro 페이지 배포

7. T5~T8 E2E 테스트 실행
```

---

## 18. 미결 사항 (GPT_REF05_CMS_DETAIL_DESIGN_VERIFY_R2 결정 필요)

| ID | 항목 | 옵션 |
|----|------|------|
| DCSN-01 | RPC 원자성 방식 | **B 확정 (GPT 결정)** |
| DCSN-02 | 다운로드 방식 | **A 확정 (GPT 결정)** |
| DCSN-03 | CDN 캐시 무효화 | 상세·미리보기·다운로드 캐시 우회 확정. CDN 무효화 자동화는 별도 WO |
| DCSN-05 | SEO description | **승인된 content.description 필수 확정 (GPT 결정)** |
| DCSN-06 | 공개 취소 즉시 검색 비노출 | DB 재확인 필터 활성화 여부 — Owner 결정 |
| DCSN-07 | content_hash 생성 기준 | 본 문서의 정규화 방식 → R2 검증 후 확정 |
| DCSN-08 | REF-08 QA 완료 전 adapter 주석처리 여부 | 코드는 추가하되 주석처리 권고 |

---

## 19. 게이트 조건

| 조건 | 상태 |
|------|------|
| GPT_REF05_CMS_DETAIL_DESIGN_VERIFY_R2 | PENDING |
| OBJ-REF-08 Content factory QA | BLOCKED |
| Owner 최종 공개 승인 | PENDING |

**운영 DB 적용·배포·색인·PR merge 금지 (게이트 해소 전).**
