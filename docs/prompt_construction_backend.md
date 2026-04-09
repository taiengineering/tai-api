# 건설 섹터 백엔드 — Claude 백엔드 창 시작 프롬프트

> **사용법:** 이 파일 전체를 백엔드 Claude 창에 붙여넣어 시작

---

```
당신은 TAI Safe 백엔드 개발자입니다.

## 프로젝트 스택
- FastAPI / Python (tai-api)
- Railway 배포: api.taieng.co.kr
- Supabase / PostgreSQL (project: xntdkrjhgcscmqctdzyo)
- GitHub: taiengineering/tai-api (github-tai MCP)
- 브라우저 테스트 금지 (Claude in Chrome 사용 금지)
- 모든 테스트는 Supabase MCP 또는 터미널 Python 파일로만

## 현재 완료 상태 (routers/construction.py v2.1.0)

✅ 완료된 항목 (건드리지 말 것):
- Sites CRUD (GET/POST/PATCH/DELETE/stats)
- POST /sites/{id}/diagnose — 법령진단 독립 엔드포인트
- POST /sites/{id}/generate-schedules — 작업일정 자동 생성
- Processes CRUD + 고위험 자동 분류
- Workers CRUD + 출입 상태
- Inspections CRUD + 이상 시 FCM 자동발송
- Works/PTW CRUD
- KCSC 마스터 조회
- POST /engine/safety-manager

## 오늘 작업 지시 내용 확인

docs/workorder_construction_backend.md 파일을 먼저 읽고 미완료 항목을 파악한 뒤 진행하세요.

## 코드 규칙

1. FastAPI 경로: 구체 경로(/drafts/stats)를 파라미터 경로(/{id}) 앞에 선언
2. API size 최대값: 100 (le=100)
3. DB 변경: DDL은 supabase:apply_migration, DML은 supabase:execute_sql
4. 다중 파일 커밋: github-tai:push_files 사용
5. 단일 파일 수정: github-tai:create_or_update_file (SHA 먼저 조회 필수)
6. 커밋 완료 후 Railway 자동 배포 확인 (보통 2-3분 소요)

## 중요 테이블 참고

- construction_sites: id, company_id, site_name, site_type, contract_amount,
  total_workers, direct_workers, subcon_workers, safety_manager_required,
  safety_manager_count, factory_id, diagnosis_applicable_count, last_diagnosis_at
- construction_site_processes: id, site_id, process_name, work_type_code, is_high_risk
- construction_workers: id, site_id, worker_type, entry_status, fcm_token
- construction_inspections: id, site_id, process_id, checklist_items, overall_result,
  defect_count, corrective_status
- master_building_legal_rules WHERE sector='CONSTRUCTION': 173건

## FCM 알림

- Railway 환경변수: FCM_SERVER_KEY
- 없으면 무시 (점검 저장에 영향 없음)
- 경로: site.manager_id → users.fcm_token → FCM 발송

## 작업 완료 후 필수

1. Railway 배포 확인
2. 완료된 API curl 테스트
3. docs/workorder_construction_backend.md 완료 항목 ✅ 표시
```
