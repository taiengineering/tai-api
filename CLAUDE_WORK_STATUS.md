# 익명 무료 법령진단 작업 현황

> 최종 업데이트: 2026-04-05

## 완료된 작업

### 1. DB 테이블 생성 SQL
- **파일**: `sql/20260402_anonymous_diagnosis_results.sql`
- **상태**: SQL 작성 완료, Supabase SQL Editor에서 실행 필요
- **내용**: `anonymous_diagnosis_results` 테이블 + 인덱스

### 2. API 라우터 (FastAPI)
- **파일**: `routers/anonymous_diagnosis.py`
- **상태**: 코드 완료, main.py에 등록 완료
- **엔드포인트**:
  | Method | Path | 설명 | 인증 |
  |--------|------|------|------|
  | POST | `/anonymous-diagnosis` | 진단 생성 (법령엔진 호출 + DB 저장) | 불필요 |
  | GET | `/anonymous-diagnosis/admin/list` | 관리자 목록 조회 (페이지네이션) | 관리자 |
  | POST | `/anonymous-diagnosis/admin/expire-stale` | 만료 ACTIVE→EXPIRED 일괄 처리 | 없음 (스케줄러용) |
  | DELETE | `/anonymous-diagnosis/admin/{record_id}` | 관리자 삭제 | 관리자 |
  | GET | `/anonymous-diagnosis/{token}` | 토큰으로 결과 조회 (partial/full) | 선택 |
  | POST | `/anonymous-diagnosis/{token}/claim` | 로그인 사용자에게 결과 귀속 | 필수 |
- **주의**: `/admin/*` 라우트가 `/{token}` 위에 위치해야 FastAPI path 충돌 방지

### 3. 만료 처리 크론 작업 SQL
- **파일**: `sql/20260405_anon_diag_cron_and_rls.sql` (앞부분)
- **상태**: SQL 작성 완료, Supabase SQL Editor에서 실행 필요
- **내용**: `cron_job_master`에 `ANON_DIAG_EXPIRE` 등록 (매일 KST 03:00)
- **호출 대상**: `POST /anonymous-diagnosis/admin/expire-stale`

### 4. RLS 정책 SQL
- **파일**: `sql/20260405_anon_diag_cron_and_rls.sql` (뒷부분)
- **상태**: SQL 작성 완료, Supabase SQL Editor에서 실행 필요
- **정책 목록**:
  | 정책명 | 대상 | 동작 |
  |--------|------|------|
  | `anon_diag_service_role` | service_role | 전체 접근 (API 서버용) |
  | `anon_diag_insert_open` | anon | INSERT 허용 (비로그인 생성) |
  | `anon_diag_select_by_token` | anon | ACTIVE/CLAIMED + 만료 전 SELECT |
  | `anon_diag_select_claimed` | authenticated | 본인 claimed + 만료 전 SELECT |
  | `anon_diag_update_claim` | authenticated | 본인에게 claim UPDATE |

---

## 미완료 — Supabase SQL 실행 필요

아래 SQL 파일들을 **Supabase SQL Editor**에서 순서대로 실행해야 합니다:

1. `sql/20260402_anonymous_diagnosis_results.sql` — 테이블 생성
2. `sql/20260405_anon_diag_cron_and_rls.sql` — 크론 등록 + RLS 정책

### 실행 방법
1. Supabase Dashboard → SQL Editor
2. 위 파일 내용을 복사·붙여넣기
3. Run 클릭

### 또는 CLI로 실행
```bash
# Supabase CLI 설치 후
supabase db execute --project-ref xntdkrjhgcscmqctdzyo \
  -f sql/20260402_anonymous_diagnosis_results.sql

supabase db execute --project-ref xntdkrjhgcscmqctdzyo \
  -f sql/20260405_anon_diag_cron_and_rls.sql
```

### 또는 psql 직접 연결
Dashboard > Project Settings > Database > Connection string (URI) 복사 후:
```bash
psql "postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres" \
  -f sql/20260402_anonymous_diagnosis_results.sql
```

---

## 관련 프론트엔드 (taieng 레포)

| 파일 | 설명 | 상태 |
|------|------|------|
| `nexas/free-diagnosis.html` | 진단 입력 폼 | 기존 완료 |
| `nexas/free-diagnosis-result.html` | 결과 표시 + 자동 claim | 수정 완료 |
| `nexas/assets/js/tai-free-diagnosis.js` | API 헤더 + 로그인 유도 헬퍼 | 기존 완료 |
| `nexas/log-in.html` | 로그인 후 pendingDiagnosisToken 자동 claim | 기존 완료 |

### 프론트 변경 사항 (이번 작업)
- `free-diagnosis-result.html`: 이미 로그인 상태에서 결과 페이지 접속 시 **자동 claim → 새로고침** 로직 추가

---

## 전체 흐름

```
[비로그인 사용자]
  1. free-diagnosis.html → POST /anonymous-diagnosis → publicToken 발급
  2. free-diagnosis-result.html?token=xxx → GET /anonymous-diagnosis/{token} → partial 결과 표시
  3. "전체 결과 보기" 클릭 → localStorage에 token 저장 → log-in.html 이동
  4. 로그인 성공 → POST /anonymous-diagnosis/{token}/claim → 결과 페이지로 리다이렉트
  5. 결과 페이지에서 full result 표시

[이미 로그인된 사용자]
  1~2 동일
  3. 결과 페이지에서 자동 claim → 새로고침 → full result 바로 표시

[스케줄러]
  - 매일 03:00 KST → POST /anonymous-diagnosis/admin/expire-stale
  - ACTIVE + expires_at 지난 레코드 → EXPIRED로 변경
```
