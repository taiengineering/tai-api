# 세션 6 작업 내역 (2026-04-17)

> 기획창 + 백엔드창 통합 기록
> 이전 세션: session-2026-04-16-pt4-backend.md

---

## 1. 엔진 복구 + DB 전수 점검

- legal_engine.py / legal_engine_patch.py / inspection_set_auto.py dev=main SHA 일치 확인
- DB orphan 정리 340건+
  - inspection_sets factory_id=NULL: 228건 삭제
  - notifications 전부 미읽음: 112건 삭제
  - work_schedules factory_id=NULL: 3건 + FK chain 삭제
- 정리 후: inspection_sets 324, work_schedules 698, work_assignments 4,266, notifications 0

---

## 2. BE-08 diagnosis_transform.py v1.0.1 main 배포

- dev 버전 import 오류 수정 (dependencies.py 미존재 → 제거)
- API: GET /diagnosis/transform/{diagnosis_id}, GET /diagnosis/transform/latest/{factory_id}
- main.py v5.25.0 라우터 등록
- DB 컬럼 4개 추가: expires_at, refund_at, refund_reason (factory_diagnosis_results), is_retroactive (master_building_legal_rules)

---

## 3. weather.py + precedent_api.py main 동기화

- weather.py v1.3.0: /weather/work-stoppage?site_id= 엔드포인트
- precedent_api.py v2.0.1: Edge Function 제거 → Fly.io 직접 law.go.kr 호출
- LAW_API_OC Fly.io secret 설정 완료
- 법제처 IP 등록 시도 → Fly.io outbound IP 유동으로 실패
- Vultr 158.247.224.158 고정 IP 프록시 필요 → Vultr 계정 suspended → Organization 정보 제출 (복구 대기)

---

## 4. BE-10 점검 미이행 에스컬레이션 시스템 [핵심 작업]

### 법적 근거
| 위반 | 법령 | 제재 |
|---|---|---|
| 안전점검 미실시 | 산안법 §36 | 과태료 500만원 |
| 정기점검 미실시 | 산안법 §93 | 과태료 1,000만원 |
| 작업 전 점검 미실시 | 안전보건규칙 §35 | 과태료 300만원 |
| 점검기록 미보존 | 산안법 §164 | 과태료 300만원 |
| 미실시 + 사고 | 산안법 §167 | 7년 징역 / 1억 벌금 |
| 사망사고(50인+) | 중대재해법 §6 | 1년+ 징역 / 법인 50억 벌금 |

### DB 변경
- `work_assignments` 4컬럼 추가: due_date, overdue_level, last_reminded_at, resolved_at
- `overdue_history` 신규 테이블 (에스컬레이션 이력)
- `notification_queue` 신규 테이블 (큐 기반 알림 발송)
- `factories.notification_time` 컬럼 추가 (TIME, 기본 07:00)
- `factories.notification_timezone` 컬럼 추가 (TEXT, 기본 Asia/Seoul)
- `construction_sites.notification_time` 컬럼 추가 (TIME, 기본 06:30)
- `construction_sites.notification_timezone` 컬럼 추가
- CONSTRUCTION sector factories → notification_time=06:30으로 업데이트 (5건)
- DB 트리거 2개: construction_sites ↔ factories notification_time 양방향 동기화

### 백엔드 코드
- `routers/overdue_checker.py` v1.0.0 → v1.1.0 → **v1.2.0** (main 배포)
  - v1.0.0: 기본 에스컬레이션 (D-1/D+1/D+2/D+7)
  - v1.1.0: 현장별 notification_time 필터 (30분 간격 cron)
  - v1.2.0: **큐 기반 구조** (prepare → dispatch 분리)
- `main.py` v5.25.1 (overdue_checker import)

### 에스컬레이션 타임라인
```
D-1  → Level 1: 리마인더 (작업자 SMS)
D+1  → Level 2: 작업자 경고 (SMS + FCM)
D+2  → Level 3: 관리자 에스컬레이션 (SMS + FCM)
D+7  → Level 4: OVERDUE 전환 (status_code 변경 + 알림)
```

### 큐 기반 알림 구조 (v1.2.0)
```
04:00 KST  POST /overdue/prepare
           → 전체 스캔 → notification_queue INSERT
           → 각 건의 scheduled_send_at = 해당 현장의 notification_time

05:00~10:50 KST  POST /overdue/dispatch (매 10분)
           → scheduled_send_at ≤ now() 건만 발송
           → 이미 sent=true인 건 자동 스킵
```

### API 엔드포인트
| 메서드 | 경로 | 용도 |
|---|---|---|
| POST | /overdue/prepare | 큐 생성 (cron 04:00) |
| POST | /overdue/dispatch | 큐 발송 (cron 매 10분) |
| POST | /overdue/check | 호환용 (prepare+dispatch 통합) |
| GET | /overdue/summary | 미이행 현황 요약 |
| GET | /overdue/queue | 오늘 큐 현황 |
| GET | /overdue/history | 에스컬레이션 이력 |
| POST | /overdue/resolve/{id} | 지연 해소 |

### Cron 등록
| 코드 | 시간 | 역할 |
|---|---|---|
| OVERDUE_PREPARE | 매일 04:00 KST | 전체 스캔 → 큐 INSERT |
| OVERDUE_DISPATCH | 05:00~10:50 매 10분 | 시간 도달 건 발송 |

---

## 5. FN-07 프론트엔드 (프론트창 완료)

| 커밋 | 내용 |
|---|---|
| safety-dashboard.html | 안전관리자 대시보드 미이행 위젯 (GET /overdue/summary) |
| overdue-list.html | 미이행 상세 (필터/테이블/해소/재배정/독촉 모달/법적리스크카드) |
| app/index.html | 작업자 홈 미이행 경고 배너 + overdue API 연동 |
| factory-list.html | notification_time 설정 필드 (시설 상세옵션 탭 최상단) |

### notification_time 프론트 동작
- 위치: 시설 상세옵션 탭 최상단
- 기본값: 07:00 (DB default)
- 저장: PATCH /factories/{id} body에 포함
- DB 형식: HH:MM:SS (TIME without timezone)
- UI: HH:MM 입력

---

## 6. 건설 현장 notification_time 동기화 수정

### 문제
- overdue_checker가 factories 테이블만 조회
- construction_sites에 별도 notification_time 존재

### 해결
1. CONSTRUCTION sector factories → 06:30으로 DB 직접 업데이트
2. DB 트리거 2개 생성:
   - `trg_sync_construction_notif_time`: construction_sites 변경 → factories 동기화
   - `trg_sync_factory_notif_time_to_cs`: factories 변경 → construction_sites 동기화
3. work_assignments → work_schedules.factory_id → factories 경로이므로 factories 조회만으로 충분

---

## PENDING (미완료)

| # | 항목 | 상태 |
|---|---|---|
| 1 | dev→main 전체 동기화 (PR 충돌) | ⏸ 대표님 GitHub에서 직접 또는 다음 세션 |
| 2 | diagnosis_autofill + diagnosis_roi main push | ⏸ main.py v5.25.1에 미포함 |
| 3 | Vultr 계정 복구 | ⏸ Organization 제출 완료, 복구 대기 |
| 4 | Vultr 복구 후 law.go.kr 프록시 설치 | ⏸ |
| 5 | FCM send-push Edge Function 배포 | ⏸ SMS만 동작 |
| 6 | PR #1 close | ⏸ 대표님 GitHub 직접 |
| 7 | Midjourney 프롬프트 기획 | ⏸ 구독 완료, 미착수 |

---

## 현재 main 상태

- main.py: v5.25.1
- overdue_checker.py: v1.2.0 (큐 기반)
- precedent_api.py: v2.0.1 (law.go.kr 직접 호출, IP 미등록)
- diagnosis_transform.py: v1.0.1
- weather.py: v1.3.0

## 주요 학습/원칙

- Fly.io outbound IP는 유동 → 외부 API IP 등록에 부적합, Vultr 고정 IP 프록시 필요
- 알림 시간은 현장마다 다르다 → factories.notification_time 현장별 설정 필수
- 큐 기반 알림이 cron 직접 발송보다 안정적 (prepare/dispatch 분리)
- construction_sites ↔ factories 양방향 트리거로 설정 동기화
- 점검 미이행의 법적 결과: 과태료 300~1,000만원, 사고 시 7년 징역/1억 벌금
