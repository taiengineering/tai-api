# Phase 1: DB 마이그레이션

**목적**: `inquiries` 테이블 확장. 외부 채널 통합과 TAI에 바란다(FEEDBACK) 분류를 위해 `source`, `inquiry_type` 컬럼 추가.

## 적용 방법 (Supabase Studio)

1. https://supabase.com/dashboard 로그인
2. 프로젝트 **`vwlahtguyggrhvslabax`** (서울) 선택
3. 좌측 **SQL Editor** → 우측 상단 **+ New query**
4. `db/migrations/20260504_inbox_phase1_inquiries.sql` 파일 내용 전체 복사 → 붙여넣기
5. **Run** 클릭 (단축키: Cmd/Ctrl + Enter)

트랜잭션(BEGIN/COMMIT)으로 감싸여 있어서 중간 에러 시 자동 롤백됩니다.

## 적용 결과 — 케이스 별 동작

### 케이스 A: inquiries 테이블이 없는 경우 (현재 추정)
- `CREATE TABLE IF NOT EXISTS`로 신규 생성
- 모든 컬럼·인덱스·RLS 정책·트리거 적용
- mock 데이터는 어드민 페이지에서만 표시되고 DB는 비어있음

### 케이스 B: 이미 있는 경우 (운영 중)
- `CREATE TABLE`은 IF NOT EXISTS로 스킵됨
- `ADD COLUMN IF NOT EXISTS`로 누락 컬럼만 추가
- 기존 row의 `source`/`inquiry_type`이 NULL이면 `direct`/`INQUIRY`로 채움
- 기존 데이터 손상 없음

## 검증 쿼리

적용 후 Supabase SQL Editor에서 실행해서 결과 공유:

### V1. 컬럼 확인
```sql
SELECT column_name, data_type, column_default, is_nullable
  FROM information_schema.columns
 WHERE table_name = 'inquiries'
 ORDER BY ordinal_position;
```

**기대 결과**: 다음 컬럼이 모두 존재해야 함
- id, no, category, title, content, answer
- name, company, phone, email, is_member
- user_id, company_id
- status, priority, assigned
- **source, inquiry_type** ← 신규
- page_url, ip_hash
- replied_at, created_at, updated_at

### V2. row 분포 확인
```sql
SELECT
  count(*) as total,
  count(*) FILTER (WHERE source='direct')          as direct_count,
  count(*) FILTER (WHERE source='marketing')       as marketing_count,
  count(*) FILTER (WHERE source='safe')            as safe_count,
  count(*) FILTER (WHERE inquiry_type='INQUIRY')   as inquiry_count,
  count(*) FILTER (WHERE inquiry_type='FEEDBACK')  as feedback_count
FROM inquiries;
```

**기대 결과**:
- 케이스 A: total=0, 모든 카운트 0
- 케이스 B: total = 기존 row 수, direct_count = total, inquiry_count = total

### V3. RLS 정책 확인
```sql
SELECT policyname, cmd, roles
  FROM pg_policies
 WHERE tablename = 'inquiries';
```

**기대 결과**: `anon insert external inquiries` (cmd=INSERT, roles={anon}) 1개

### V4. anon 정책 시뮬레이션

**차단 케이스 — 실패해야 정상**:
```sql
SET LOCAL ROLE anon;
INSERT INTO inquiries (source, inquiry_type, category, content)
  VALUES ('direct', 'FEEDBACK', 'fb_feature', '이건 차단되어야 정상입니다');
RESET ROLE;
```
→ 에러: `new row violates row-level security policy` ✅

**통과 케이스 — 성공해야 정상**:
```sql
SET LOCAL ROLE anon;
INSERT INTO inquiries (source, inquiry_type, category, content)
  VALUES ('marketing', 'FEEDBACK', 'fb_feature', '의견 테스트 — 길이 10자 이상');
RESET ROLE;

-- 정리
DELETE FROM inquiries WHERE content LIKE '의견 테스트%';
```
→ INSERT 1건 성공 ✅

## 어드민 inquiry-list 영향

**영향 없음**. inquiry-list가 호출하는 API는 service_role(서비스 키) 사용 → RLS 무시. 기존 mock 흐름 그대로 유지. Phase 4에서 실제 API 연결 시 새 컬럼들도 자연스럽게 노출됨.

## 롤백

원하는 경우 다음 SQL로 컬럼 제거 가능 (테이블 자체는 유지):

```sql
BEGIN;
ALTER TABLE inquiries DROP CONSTRAINT IF EXISTS inquiries_source_chk;
ALTER TABLE inquiries DROP CONSTRAINT IF EXISTS inquiries_type_chk;
ALTER TABLE inquiries DROP COLUMN IF EXISTS source;
ALTER TABLE inquiries DROP COLUMN IF EXISTS inquiry_type;
DROP POLICY IF EXISTS "anon insert external inquiries" ON inquiries;
ALTER TABLE inquiries DISABLE ROW LEVEL SECURITY;
COMMIT;
```

## 진행 후 다음 단계

Phase 2로 이동: `PHASE2_SLACK_SETUP.md`
