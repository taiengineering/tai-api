# 건설섹터 v2.1.0 창 배분 요약표

> 최종 업데이트: 2026-04-09

## 현재 상태

| 순서 | 작업 | 핵심 내용 | 상태 |
|------|------|-----------|------|
| 1 | 현장 CRUD | `/construction/sites` — 공사금액·공사유형 기반 선임 자동 판단 | ✅ 완료 |
| 2 | 법령진단 | `/construction/sites/{id}/diagnose` — CONSTRUCTION 조건코드 매칭 | ✅ 완료 |
| 3 | 공정 CRUD | `/construction/sites/{id}/processes` — 고위험 작업 자동 분류 | ✅ 완료 |
| 4 | 점검 저장 | `/construction/inspections` — 이상 시 FCM 자동 발송 | ✅ 완료 |
| 5 | 작업자 관리 | `/construction/sites/{id}/workers` | ✅ 완료 |
| 6 | 스케줄 생성 | `/construction/sites/{id}/generate-schedules` 독립 엔드포인트 | ✅ 완료 |

## 완성된 API 목록 (routers/construction.py v2.1.0)

```
GET  /construction/sites                        현장 목록
POST /construction/sites                        현장 등록 (자동진단+스케줄 포함)
GET  /construction/sites/{id}                   현장 단건
PATCH /construction/sites/{id}                  현장 수정
DELETE /construction/sites/{id}                 현장 비활성화
GET  /construction/sites/{id}/stats             현장 통계

POST /construction/sites/{id}/diagnose          ★ 법령진단 독립 실행
POST /construction/sites/{id}/generate-schedules ★ 작업일정 자동 생성

GET  /construction/sites/{id}/processes         공정 목록
POST /construction/sites/{id}/processes         공정 등록
GET  /construction/processes/{id}               공정 단건
PATCH /construction/processes/{id}              공정 수정
DELETE /construction/processes/{id}             공정 비활성화

GET  /construction/kcsc/processes               KCSC 공정 마스터
GET  /construction/kcsc/works                   KCSC 위험작업 마스터
GET  /construction/kcsc/works/{process_id}      공정별 위험작업

GET  /construction/sites/{id}/works             작업허가서 목록
POST /construction/sites/{id}/works             작업허가서 등록 (PTW 자동채번)
GET  /construction/works/{id}                   작업 단건
PATCH /construction/works/{id}                  작업 수정
PATCH /construction/works/{id}/ptw              PTW 승인/반려
DELETE /construction/works/{id}                 작업 비활성화

GET  /construction/sites/{id}/workers           작업자 목록
POST /construction/sites/{id}/workers           작업자 등록
GET  /construction/workers/{id}                 작업자 단건
PATCH /construction/workers/{id}                작업자 수정
PATCH /construction/workers/{id}/entry          출입 상태 변경
DELETE /construction/workers/{id}              작업자 비활성화

GET  /construction/sites/{id}/inspections       점검 목록
POST /construction/sites/{id}/inspections       ★ 점검 저장 + FCM 자동발송
GET  /construction/inspections/{id}             점검 단건
PATCH /construction/inspections/{id}            점검 수정
PATCH /construction/inspections/{id}/corrective 시정조치 업데이트
DELETE /construction/inspections/{id}          점검 비활성화

POST /construction/engine/safety-manager        선임 의무 판정 엔진
```

## 다음 단계 (프론트엔드)

`docs/workorder_construction_frontend.md` 참조  
→ 프론트엔드 창에서 `docs/prompt_construction_frontend.md` 붙여넣기

## 기술 참고

- FCM 알림: Railway `FCM_SERVER_KEY` 환경변수 필요 (없으면 무시)
- 현장 등록 시 factory 자동생성 → 법령진단 자동실행 → 스케줄 자동생성
- 독립 diagnose/generate-schedules 엔드포인트로 재진단/재생성 가능
