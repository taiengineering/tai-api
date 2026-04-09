# 건설관리 v2.1.0 창 배분 요약표

> 작성일: 2026-04-09 | API 기준: construction.py v2.1.0

---

## 창 배분

| 창 | 역할 | 작업 범위 |
|----|------|----------|
| 플래닝 창 | 지시·검토 | 이 문서 |
| **백엔드 창** | `tai-api` | construction.py 추가 API, DB 스키마 검증 |
| **프론트엔드 창** | `tai-admin` | 6개 HTML 파일 신규·재작성 |

---

## 백엔드 현황 (v2.1.0 완료)

| 엔드포인트 | 상태 | 비고 |
|-----------|------|------|
| POST /construction/sites | ✅ 완료 | 현장 등록 + 자동진단 + 자동일정 |
| POST /construction/sites/{id}/diagnose | ✅ 완료 | 법령진단 독립 실행 |
| POST /construction/sites/{id}/generate-schedules | ✅ 완료 | 작업일정 자동 생성 |
| POST /construction/sites/{id}/inspections | ✅ 완료 | 점검 저장 + FCM 자동 발송 |
| GET/PATCH/DELETE 전체 CRUD | ✅ 완료 | sites/processes/works/workers/inspections |
| FCM_SERVER_KEY 환경변수 | ⚠️ 설정 필요 | Railway Variables에 추가 |

**백엔드 추가 작업 없음.** v2.1.0 완성 상태.

---

## 프론트엔드 작업 목록

| 순서 | 파일 | 방식 | 예상 작업량 |
|------|------|------|------------|
| 1 | construction-site-list.html | 전면 재작성 | 大 |
| 2 | construction-process.html | 신규 | 中 |
| 3 | construction-worker-list.html | worker-list.html 재활용 | 中 |
| 4 | construction-inspection-list.html | 전면 재작성 | 中 |
| 5 | construction-inspection-anchor.html | inspection-anchor.html 재활용 | 小 |
| 6 | worker-check-construction.html | worker-check.html 재활용 | 小 |

**경로:** `tadmin/full-version/html/horizontal-menu-template/`

---

## 프롬프트 파일 위치

```
tai-api/docs/prompt_construction_backend.md   ← 백엔드 창에 붙여넣기
tai-api/docs/prompt_construction_frontend.md  ← 프론트엔드 창에 붙여넣기
```

## 상세 워크오더 위치

```
tai-api/docs/workorder_construction_backend.md   ← 백엔드 상세
tai-api/docs/workorder_construction_frontend.md  ← 프론트엔드 상세 (최신)
tai-admin/docs/workorder_construction_frontend.md ← 동일 파일 (미러)
```
