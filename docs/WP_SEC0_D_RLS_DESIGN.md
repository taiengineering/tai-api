# WP-SEC0-D: RLS 보안 설계 — 미실행 설계안

```
WO:        WO-TAI-DOC-SEC0-IMPLEMENT-001 / WO-TAI-DOC-SEC0-PR609-CORRECTION-001
작성일:    2026-10-13 KST
작성자:    Claude Code (claude-sonnet-4-6)
상태:      DESIGN_ONLY — DDL/DML 실행 없음, Owner 별도 승인 필요
개정 이유: GPT Code IV 지적 P0-04 — 실제 운영 정책명 반영
```

---

## 1. 현황 (GPT Read-Only Production Evidence 기준)

| 테이블 / 버킷 | 실제 운영 정책명 | 위험도 |
|---|---|---|
| `form_submissions` | anon_select / anon_insert / anon_update / anon_delete / authenticated_all | CRITICAL |
| `form_templates` | anon_select / anon_insert / anon_update / anon_delete / authenticated_all | HIGH |
| `report_events` | anon_select / anon_insert / anon_update / anon_delete | CRITICAL |
| `form-outputs` bucket | public = true | CRITICAL |

> **중요**: anon CRUD 정책이 모두 USING (true) / WITH CHECK (true) 이며,
> `authenticated_all` 정책도 광범위하게 허용된 상태입니다.
> 새 restrictive 정책만 추가하면 기존 permissive 정책이 OR 논리로 우선 적용됩니다.
> 보안 실효성을 위해 기존 정책 DROP이 반드시 선행되어야 합니다.

---

## 2. 설계 원칙

1. **최소 권한**: anon 역할은 모든 테이블에서 SELECT/INSERT/UPDATE/DELETE 불허
2. **authenticated 역할**: JWT company_id 클레임 기반 행 필터 (클레임 존재 여부 사전 확인 필요)
3. **service_role**: RLS 우회 (서버 내부 전용 — 기존 유지)
4. **기존 정책 선제 DROP 필수**: OR 우선 평가로 인한 무력화 방지
5. **버킷 private**: `form-outputs` 버킷 public → private 전환, signed URL 만료 1시간

---

## 3. form_submissions RLS 설계안

```sql
-- ① 기존 정책 제거 (실제 정책명 기준)
DROP POLICY IF EXISTS "anon_select_form_submissions" ON form_submissions;
DROP POLICY IF EXISTS "anon_insert_form_submissions" ON form_submissions;
DROP POLICY IF EXISTS "anon_update_form_submissions" ON form_submissions;
DROP POLICY IF EXISTS "anon_delete_form_submissions" ON form_submissions;
DROP POLICY IF EXISTS "authenticated_all_form_submissions" ON form_submissions;

-- ② RLS 활성화 (미활성화 상태일 경우)
ALTER TABLE form_submissions ENABLE ROW LEVEL SECURITY;

-- ③ authenticated: 자사 factory_id 행만 읽기
CREATE POLICY "sec0_authenticated_select_own"
ON form_submissions
FOR SELECT
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
);

-- ④ authenticated: 자사 factory_id 행만 삽입
CREATE POLICY "sec0_authenticated_insert_own"
ON form_submissions
FOR INSERT
TO authenticated
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
);

-- ⑤ authenticated: 자사 factory_id 행만 수정
CREATE POLICY "sec0_authenticated_update_own"
ON form_submissions
FOR UPDATE
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
)
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
);

-- anon: 정책 없음 = 기본 차단
```

> **JWT 클레임 주의**: `auth.jwt() ->> 'company_id'` 접근 방식 대신
> `users.auth_id = auth.uid()` 를 통한 `company_id` 조회를 사용.
> TAI Auth가 JWT custom claim을 설정하는 경우 `auth.jwt() ->> 'company_id'` 단축 가능.
> 적용 전 TAI Auth 구성 확인 필수.

---

## 4. form_templates RLS 설계안

```sql
-- ① 기존 정책 제거
DROP POLICY IF EXISTS "anon_select_form_templates" ON form_templates;
DROP POLICY IF EXISTS "anon_insert_form_templates" ON form_templates;
DROP POLICY IF EXISTS "anon_update_form_templates" ON form_templates;
DROP POLICY IF EXISTS "anon_delete_form_templates" ON form_templates;
DROP POLICY IF EXISTS "authenticated_all_form_templates" ON form_templates;

-- ② RLS 활성화
ALTER TABLE form_templates ENABLE ROW LEVEL SECURITY;

-- ③ authenticated: 전체 읽기 허용 (카탈로그)
CREATE POLICY "sec0_authenticated_select_catalog"
ON form_templates
FOR SELECT
TO authenticated
USING (true);

-- INSERT/UPDATE/DELETE: service_role 전용 (RLS 우회) — 정책 불필요
-- anon SELECT 차단 (정책 없음)
```

---

## 5. report_events RLS 설계안

```sql
-- ① 기존 정책 제거
DROP POLICY IF EXISTS "anon_select_report_events" ON report_events;
DROP POLICY IF EXISTS "anon_insert_report_events" ON report_events;
DROP POLICY IF EXISTS "anon_update_report_events" ON report_events;
DROP POLICY IF EXISTS "anon_delete_report_events" ON report_events;
-- authenticated_all 이 존재하면 함께 제거
DROP POLICY IF EXISTS "authenticated_all_report_events" ON report_events;

-- ② RLS 활성화
ALTER TABLE report_events ENABLE ROW LEVEL SECURITY;

-- ③ authenticated: 자사 factory_id 행만 읽기
CREATE POLICY "sec0_authenticated_select_own"
ON report_events
FOR SELECT
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
);

-- ④ authenticated: 자사 factory_id 행만 삽입
CREATE POLICY "sec0_authenticated_insert_own"
ON report_events
FOR INSERT
TO authenticated
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
);

-- ⑤ authenticated: 자사 factory_id 행만 수정
CREATE POLICY "sec0_authenticated_update_own"
ON report_events
FOR UPDATE
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
)
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
);
```

---

## 6. form-outputs 버킷 private 전환 계획

### 현황
- `form-outputs` 버킷: `public = true`
- PDF 파일 경로: `{factory_id}/{submission_id}.pdf`
- 경로만 알면 무인증 다운로드 가능

### 전환 절차 (Owner 승인 후 실행)

1. **기존 외부 HTTP URL 레거시 처리**:
   - `form_submissions.pdf_url LIKE 'http%'` 인 행 확인
   - 해당 PDF는 별도 마이그레이션 경로 필요 (현재 BLOCKED)

2. **버킷 설정 변경** (Supabase Dashboard → Storage):
   - `form-outputs` → Settings → Public: OFF

3. **Storage RLS 정책 추가**:

```sql
-- form-outputs 버킷 읽기: 경로 prefix = 자사 factory_id
CREATE POLICY "sec0_authenticated_read_own_factory_outputs"
ON storage.objects
FOR SELECT
TO authenticated
USING (
    bucket_id = 'form-outputs'
    AND (storage.foldername(name))[1] IN (
        SELECT f.id::text FROM factories f
        WHERE f.company_id = (
            SELECT u.company_id FROM users u
            WHERE u.auth_id = auth.uid()
            LIMIT 1
        )
    )
);
```

4. **앱 레이어는 이미 완료** (v2.2.0):
   - `GET /report-forms/storage/signed-url/{id}` — 소유권 검증 후 서버사이드 signed URL 반환
   - `POST /report-forms/submissions/{id}/pdf` — 소유권 검증 후 PDF 스트림 반환

---

## 7. 적용 전후 검증 SQL

```sql
-- 적용 전: 현재 정책 목록 확인
SELECT schemaname, tablename, policyname, roles, cmd, qual
FROM pg_policies
WHERE tablename IN ('form_submissions', 'form_templates', 'report_events')
ORDER BY tablename, policyname;

-- 적용 후: 남은 정책 확인 (anon 정책이 없어야 함)
SELECT policyname, roles, cmd FROM pg_policies
WHERE tablename = 'form_submissions' AND 'anon' = ANY(roles);

-- Storage bucket 상태 확인
SELECT id, name, public FROM storage.buckets WHERE id = 'form-outputs';
```

### Rollback

```sql
-- 롤백: sec0_ 접두사 신규 정책 제거
DROP POLICY IF EXISTS "sec0_authenticated_select_own" ON form_submissions;
DROP POLICY IF EXISTS "sec0_authenticated_insert_own" ON form_submissions;
DROP POLICY IF EXISTS "sec0_authenticated_update_own" ON form_submissions;
DROP POLICY IF EXISTS "sec0_authenticated_select_catalog" ON form_templates;
DROP POLICY IF EXISTS "sec0_authenticated_select_own" ON report_events;
DROP POLICY IF EXISTS "sec0_authenticated_insert_own" ON report_events;
DROP POLICY IF EXISTS "sec0_authenticated_update_own" ON report_events;

-- 기존 정책 복구 (서비스 영향 최소화 — 보안 후퇴)
-- 원래 정책명으로 재생성 필요
```

---

## 8. 차단 항목

```
UNRESOLVED_REPORT_EVENTS_CONTRACT = BLOCKED
  → report_events 범용/전용 여부 Owner 확인 필요
  → idempotency / event-to-document linkage 계약 미결

UNRESOLVED_LEGACY_PDF_HTTP_URLS = BLOCKED
  → form_submissions.pdf_url이 http로 시작하는 레거시 행의 안전한 조회 경로 미결
  → form-outputs bucket private 전환 시 해당 URL 접근 방법 별도 결정 필요

SECURITY_REMEDIATION = SEPARATE_OWNER_APPROVAL
  → DB RLS 정책 및 Storage 설정 변경은 Owner 별도 승인 후 별도 마이그레이션으로 실행
```
