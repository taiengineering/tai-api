# WP-SEC0-D: RLS 보안 설계 — 미실행 설계안

```
WO:        WO-TAI-DOC-SEC0-IMPLEMENT-001
작성일:    2026-10-13 KST
작성자:    Claude Code (claude-sonnet-4-6)
상태:      DESIGN_ONLY — DDL/DML 실행 없음, Owner 별도 승인 필요
```

---

## 1. 현황 (Read-Only Production Evidence)

| 테이블 / 버킷 | anon RLS 현황 | 위험도 |
|---|---|---|
| `form_submissions` | USING (true) / WITH CHECK (true) — 전 행 읽기·쓰기 | CRITICAL |
| `form_templates` | USING (true) — 전 행 읽기 | HIGH |
| `report_events` | USING (true) / WITH CHECK (true) — 전 행 읽기·쓰기 | CRITICAL |
| `form-outputs` bucket | public = true — PDF 무인증 다운로드 | CRITICAL |

---

## 2. 설계 원칙

1. **최소 권한**: anon 역할은 모든 테이블에서 SELECT/INSERT/UPDATE/DELETE 불허
2. **authenticated 역할**: JWT 토큰의 `company_id` 또는 `factory_id` 클레임으로 행 필터
3. **service_role**: RLS 우회 (서버 내부 전용 — 기존 유지)
4. **버킷 private**: `form-outputs` 버킷을 private으로 전환, signed URL 만료 1시간

---

## 3. form_submissions RLS 설계안

```sql
-- 기존 anon 정책 제거
DROP POLICY IF EXISTS "anon full access" ON form_submissions;
DROP POLICY IF EXISTS "Allow anon" ON form_submissions;  -- 실제 정책명은 확인 필요

-- authenticated: 자사 factory_id 행만 읽기
CREATE POLICY "authenticated_select_own_company"
ON form_submissions
FOR SELECT
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
);

-- authenticated: 자사 factory_id 행만 삽입
CREATE POLICY "authenticated_insert_own_company"
ON form_submissions
FOR INSERT
TO authenticated
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
);

-- authenticated: 자사 factory_id 행만 수정
CREATE POLICY "authenticated_update_own_company"
ON form_submissions
FOR UPDATE
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
)
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
);

-- anon: 전체 차단 (정책 없음 = 기본 차단)
```

> **주의**: `auth.jwt() ->> 'company_id'` 는 Supabase JWT custom claim 구성이 필요.
> TAI Auth 현재 구성 확인 후 실제 claim 키 이름 조정 필요.
> 대안: `auth.uid()` 로 `users.auth_id` 매핑 후 `users.company_id` JOIN.

---

## 4. form_templates RLS 설계안

`form_templates` 는 서식 정의 카탈로그로 사내 모든 인증 사용자에게 읽기 허용,
관리 작업(INSERT/UPDATE/DELETE)은 service_role 전용으로 제한.

```sql
-- 기존 anon 정책 제거
DROP POLICY IF EXISTS "anon full access" ON form_templates;

-- authenticated: 전체 읽기 허용 (카탈로그)
CREATE POLICY "authenticated_select_catalog"
ON form_templates
FOR SELECT
TO authenticated
USING (true);

-- anon SELECT 차단 (정책 없음)
-- INSERT/UPDATE/DELETE: service_role 전용 (RLS 우회) — 정책 불필요
```

---

## 5. report_events RLS 설계안

```sql
-- 기존 anon 정책 제거
DROP POLICY IF EXISTS "anon full access" ON report_events;

-- authenticated: 자사 factory_id 행만 읽기
CREATE POLICY "authenticated_select_own_company"
ON report_events
FOR SELECT
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
);

-- authenticated: 자사 factory_id 행만 삽입
CREATE POLICY "authenticated_insert_own_company"
ON report_events
FOR INSERT
TO authenticated
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
);

-- authenticated: 자사 factory_id 행만 수정 (상태 변경)
CREATE POLICY "authenticated_update_own_company"
ON report_events
FOR UPDATE
TO authenticated
USING (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
)
WITH CHECK (
    factory_id IN (
        SELECT f.id FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
);

-- anon: 전체 차단 (정책 없음)
```

---

## 6. form-outputs 버킷 private 전환 계획

### 현황
- `form-outputs` 버킷: `public = true`
- PDF 파일 경로: `{factory_id}/{submission_id}.pdf`
- 경로만 알면 무인증 다운로드 가능

### 전환 절차 (Owner 승인 후 실행)

1. **버킷 설정 변경** (Supabase Dashboard → Storage):
   - `form-outputs` → Settings → Public: OFF

2. **Storage RLS 정책 추가**:

```sql
-- form-outputs 버킷 읽기: 경로 prefix = 자사 factory_id
CREATE POLICY "authenticated_read_own_factory_outputs"
ON storage.objects
FOR SELECT
TO authenticated
USING (
    bucket_id = 'form-outputs'
    AND (storage.foldername(name))[1] IN (
        SELECT f.id::text FROM factories f
        WHERE f.company_id = (auth.jwt() ->> 'company_id')
    )
);
```

3. **앱 레이어 변경 불필요**: `report_forms.py` v2.2.0 이미 서버사이드 signed URL 발급
   - `GET /report-forms/storage/signed-url/{submission_id}` — 인증된 사용자에게만 signed URL 반환
   - `POST /report-forms/submissions/{id}/pdf` — 인증된 소유자에게만 PDF 스트림 반환

---

## 7. 실행 전 확인 사항 (Blocked)

- [ ] JWT custom claims `company_id` 실제 키 이름 확인
- [ ] 기존 anon 정책명 확인 (`\dp form_submissions` 로 현재 정책 목록 조회)
- [ ] `form-outputs` 버킷 public 전환 시 기존 외부 링크(pdf_url이 http로 시작하는 행) 처리 계획
- [ ] RLS 활성화 여부 확인 (`ALTER TABLE form_submissions ENABLE ROW LEVEL SECURITY` 필요 여부)
- [ ] Owner 승인

---

## 8. 차단 항목

```
UNRESOLVED_REPORT_EVENTS_CONTRACT = BLOCKED
  → report_events 가 범용 테이블인지 신고서식 전용인지 Owner 확인 필요
  → idempotency / event-to-document linkage 계약 미결

SECURITY_REMEDIATION = SEPARATE_OWNER_APPROVAL
  → 이 설계안은 코드 레이어(WP-SEC0-A/B) 만 적용됨
  → DB RLS 및 Storage 정책 변경은 Owner 별도 승인 후 별도 마이그레이션으로 실행
```
