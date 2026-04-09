# 건설관리 백엔드 워크오더

> 작성일: 2026-04-09  
> 기준: `routers/construction.py` v2.1.0  
> 상태: **완료 — 추가 작업 없음**

---

## 현황 요약

construction.py v2.1.0은 프론트엔드에서 필요한 모든 API를 포함하고 있습니다.

---

## 완료된 API 목록

### ① 건설현장 (Sites)
```
GET    /construction/sites                      현장 목록
POST   /construction/sites                      현장 등록 (+ 자동진단 + 자동일정)
GET    /construction/sites/{site_id}            현장 단건
PATCH  /construction/sites/{site_id}            현장 수정
DELETE /construction/sites/{site_id}            현장 삭제 (soft)
GET    /construction/sites/{site_id}/stats      현장 통계
```

### ② 법령진단 독립 실행 (v2.1.0 신규)
```
POST   /construction/sites/{site_id}/diagnose
```
- CONSTRUCTION sector 173개 규칙 → 현장 조건 매칭
- `factory_diagnosis_results` 저장 (is_latest=true)
- `construction_sites.diagnosis_applicable_count` 자동 업데이트
- 응답: `applicable_rules`, `by_obligation_type`

### ③ 작업일정 자동 생성 (v2.1.0 신규)
```
POST   /construction/sites/{site_id}/generate-schedules
```
- 최신 진단 결과의 `inspection_required` + `action_required` 조회
- `work_schedules` 생성 (source_type=LEGAL)
- 중복 rule_code 자동 스킵
- 응답: `created`, `skipped`, `total_rules`

### ④ 공정 (Processes)
```
GET    /construction/sites/{site_id}/processes
POST   /construction/sites/{site_id}/processes
GET    /construction/processes/{process_id}
PATCH  /construction/processes/{process_id}
DELETE /construction/processes/{process_id}
```

### ⑤ KCSC 마스터
```
GET    /construction/kcsc/processes    공정 마스터 (자동완성)
GET    /construction/kcsc/works        작업 마스터
GET    /construction/kcsc/works/{process_id}
```

### ⑥ 위험작업/PTW (Works)
```
GET    /construction/sites/{site_id}/works
POST   /construction/sites/{site_id}/works
GET    /construction/works/{work_id}
PATCH  /construction/works/{work_id}
PATCH  /construction/works/{work_id}/ptw    PTW 승인/거절/완료
DELETE /construction/works/{work_id}
```

### ⑦ 작업자 (Workers)
```
GET    /construction/sites/{site_id}/workers
POST   /construction/sites/{site_id}/workers
GET    /construction/workers/{worker_id}
PATCH  /construction/workers/{worker_id}
PATCH  /construction/workers/{worker_id}/entry   출입 상태 변경 (IN/OUT/OFFSITE)
DELETE /construction/workers/{worker_id}
```

### ⑧ 안전점검 (Inspections) — v2.1.0 FCM 추가
```
GET    /construction/sites/{site_id}/inspections
POST   /construction/sites/{site_id}/inspections   (이상 감지 시 FCM 자동 발송)
GET    /construction/inspections/{inspection_id}
PATCH  /construction/inspections/{inspection_id}
PATCH  /construction/inspections/{inspection_id}/corrective   시정조치 상태
DELETE /construction/inspections/{inspection_id}
```

**FCM 동작 (v2.1.0):**
- `checklist_items` 중 result = `bad/fail/이상/FAIL` → defect_count 자동 집계
- `overall_result` 자동 판정: defect_count >= 1 → ISSUE, 0 → PASS
- FAIL/ISSUE + defect_count > 0 → site.manager_id → users.fcm_token 조회 → FCM 발송
- `FCM_SERVER_KEY` 환경변수 없으면 자동 무시

### ⑨ 안전관리자 판정 엔진
```
POST   /construction/engine/safety-manager
body: { site_type, contract_amount, total_workers }
```

---

## 환경변수 설정 (Railway)

```
FCM_SERVER_KEY = [Firebase 서버 키]
```
- 미설정 시 FCM 발송 건너뜀, 점검 저장에는 영향 없음
- Railway 대시보드 → 해당 서비스 → Variables → 추가

---

## DB 테이블 구조

| 테이블 | 용도 |
|--------|------|
| `construction_sites` | 현장 (factory_id 자동 생성) |
| `construction_site_processes` | 공정 |
| `construction_works` | 작업/PTW |
| `construction_workers` | 작업자 |
| `construction_inspections` | 안전점검 |
| `kcsc_process_master` | KCSC 공정 마스터 |
| `kcsc_work_master` | KCSC 작업 마스터 |
| `factories` | 법령진단 연동용 (자동 생성) |
| `factory_diagnosis_results` | 진단 결과 저장 |
| `work_schedules` | 자동 생성 작업일정 |

---

## 안전관리자 선임의무 판정 로직

```python
# 산안법 시행령 제16조
건축(BUILDING): 도급금액 >= 150억 → 선임
토목(CIVIL):    도급금액 >= 120억 → 선임
상시 근로자 >= 50명 → 선임 (도급금액 무관)
```

현장 등록/수정 시 자동 계산되어 `safety_manager_required`, `safety_manager_count` 저장.

---

## 현장 등록 자동화 흐름 (v2.0.0+)

```
POST /construction/sites
  └─ construction_sites 저장
  └─ factories 자동 생성 (sector=CONSTRUCTION)
  └─ construction_sites.factory_id 업데이트
  └─ _run_diagnosis() 실행 → factory_diagnosis_results 저장
  └─ _run_generate_schedules() 실행 → work_schedules 생성
  └─ 응답 auto.diagnosis, auto.schedules 포함
```
