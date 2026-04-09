# 백엔드 창 시작 프롬프트 — 파이프라인 1순위

> 이 파일을 백엔드 Claude 창에 붙여넣어 세션을 시작합니다.

---

아래 내용을 읽고 즉시 준비됐다고 알려주세요.

## 프로젝트 정보

- **레포**: `taiengineering/tai-api` (branch: main)
- **배포**: Railway → api.taieng.co.kr
- **DB**: Supabase xntdkrjhgcscmqctdzyo

## 완료된 작업 (이번 세션)

### inspection_sets.py v1.9.0 업데이트 ✅
- 커밋: `96b3d81`
- 신규 엔드포인트: `POST /inspection-sets/generate-schedules/{factory_id}`
  - anchor_confirmed=true 세트에 대해 work_schedules 일괄 생성
  - 이미 SCHEDULED 스케줄 있으면 스킵 (force=true 시 재생성)
  - 응답: { total, created, skipped, results[] }

## 다음 가능한 작업

1. work_schedules.py 확장 — 필터/페이지네이션 지원 추가
   ```
   GET /work-schedules/factory/{factory_id}?source_type=&obligation_type=&status_code=&page=&size=
   ```
   현재는 전체 반환 — 프론튴에서 필터링 중

2. 알림 시스템 점검 — notifications 0건 문제 원인 파악
   - notification_settings 42건 설정되어 있지만 notifications 테이블 0건
   - cron 스케줄러나 트리거 로직 확인 필요

3. 건설관리 API v2.1.0은 완성 상태 (construction.py)

## 개발 규칙

- 테스트: 터미널 Python 파일 또는 Supabase MCP
- 브라우저 테스트 금지
- DB DDL: `supabase:apply_migration`
- DB DML/SELECT: `supabase:execute_sql`
- 커밋: `github-tai:push_files` (다중) 또는 `github-tai:create_or_update_file` (단일)

## FastAPI 라우트 순서 주의

- 구체 경로를 `/{id}` 파라미터 라우트 **앞에** 선언해야 함
- `generate-schedules/{factory_id}`는 POST이므로 `/{inspection_set_id}` GET/PATCH와 충돌없음

## 참고 문서

```
tai-api/docs/workorder_construction_backend.md   ← 건설관리 백엔드
tai-api/docs/workorder_construction_v21_summary.md ← 전체 요약
```

준비됐으면 OK라고 알려주세요.
