# 백엔드 창 시작 프롬프트 — 건설관리 v2.1.0

> 이 파일을 백엔드 Claude 창에 붙여넣어 세션을 시작합니다.

---

아래 내용을 읽고 즉시 준비됐다고 알려주세요.

## 프로젝트 정보

- **레포**: `taiengineering/tai-api` (branch: main)
- **배포**: Railway → api.taieng.co.kr
- **DB**: Supabase xntdkrjhgcscmqctdzyo
- **스택**: FastAPI/Python + Supabase/PostgreSQL

## 현재 상태

`routers/construction.py` v2.1.0 이 **완전히 완료**된 상태입니다.

완료된 기능:
- POST /construction/sites/{id}/diagnose (법령진단 독립 실행)
- POST /construction/sites/{id}/generate-schedules (작업일정 자동 생성)
- 점검 저장 시 FCM 자동 발송 (이상 감지 → 관리자 알림)
- 전체 CRUD: sites, processes, works, workers, inspections

## 지금 당장 할 일

### 우선순위 1: FCM_SERVER_KEY 환경변수 확인
```
1. api.taieng.co.kr/health 호출해서 현재 버전 확인
2. Firebase FCM 서버 키가 Railway 환경변수에 설정되어 있는지 확인
   (미설정 시 점검 저장은 정상, FCM만 건너뜀)
```

### 우선순위 2: construction 엔드포인트 동작 검증
```bash
# 현장 목록 조회
GET https://api.taieng.co.kr/construction/sites?company_id={cid}&size=5

# 법령진단 테스트 (기존 현장 ID 사용)
POST https://api.taieng.co.kr/construction/sites/{site_id}/diagnose

# 일정 생성 테스트
POST https://api.taieng.co.kr/construction/sites/{site_id}/generate-schedules
```

### 우선순위 3: 프론트엔드 지원 API 보강 (필요 시)
프론트엔드 창에서 요청이 오면:
- `/construction/sites/{id}/workers` 에서 `users` 테이블 조인 추가
- `/construction/sites/{id}/processes` 에서 작업 연결 정보 추가
- 기타 프론트 개발 중 발견되는 누락 필드 보강

## 개발 규칙

- 테스트: 터미널 Python 파일 또는 Supabase MCP
- 브라우저 테스트 금지
- DB DDL: `supabase:apply_migration` 사용
- DB DML/SELECT: `supabase:execute_sql` 사용
- 커밋: `github-tai:push_files` (다중) 또는 `github-tai:create_or_update_file` (단일)

## 참고 문서

```
tai-api/docs/workorder_construction_backend.md   ← 백엔드 상세 워크오더
tai-api/docs/workorder_construction_v21_summary.md ← 전체 요약
```

준비됐으면 OK라고 알려주세요.
