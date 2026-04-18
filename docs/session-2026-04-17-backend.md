# 백엔드 세션 요약 — 2026-04-17

**담당:** 백엔드 창  
**범위:** BE-08 ~ BE-10 + SB-06 검증  
**최종 커밋:** 6c412aa6 (dev 브랜치)

---

## 완료 작업 목록

### SB-06 산재판례 수집 Edge Function 수정

**문제:** `collect-precedents` 3회 실행 모두 saved=0  
**원인:** `datSrcNm=근로복지공단산재판례` 파라미터가 법제처 API에서 소스 매칭 실패 → 결과 0건  
**수정:** Edge Function v2.0.0 재배포

| 수정 항목 | 내용 |
|---|---|
| `datSrcNm` 파라미터 | 제거 → 전체 판례 검색 |
| 키 접근 | 단일 키 → `pick()` 다중 후보 순서대로 |
| 페이지 | 1페이지 → 2페이지 순회 (display=10) |
| console.log | 응답 키 목록 + skip 사유 전부 기록 |
| 키워드 | 14개 → 8개 (핵심만) |

**다음 액션:** `POST https://api.taieng.co.kr/precedents/collect` 수동 1회 실행 필요

---

### 검증 4항목 결과

| 항목 | 결과 |
|---|---|
| ① /precedents/collect | ⚠️ Edge Fn v2.0.0 재배포 완료, 실행 대기 |
| ② weather.py 기상청 API | ✅ Edge Fn ACTIVE, 200 OK 확인 |
| ③ precedent_api.py 법제처 | ✅ 라우터 정상 (DB 쿼리 경로 검증) |
| ④ agent-service 라우터 | ✅ 25건 active (construction/industrial/facility) |

**추가:** 검증용 산재판례 테스트 데이터 3건 posts 테이블에 직접 삽입

---

### BE-08: diagnosis_transform.py v1.0.0

**파일:** `routers/diagnosis_transform.py`  
**main.py:** v5.27.0

**DB migration:** `be08_diagnosis_transform_columns`
- `factory_diagnosis_results`: `expires_at`, `refund_at`, `refund_reason` 추가
- `master_building_legal_rules`: `is_retroactive` 추가

**API:**
- `GET /diagnosis/transform/{diagnosis_id}` — ID 기반 Transform
- `GET /diagnosis/transform/latest/{factory_id}` — 시설 최신 진단 Transform

**원칙:** legal_engine.py 미수정, result_data JSONB 읽기 전용  
**변환 우선순위:** 6개 섹션 (headline/obligations/warnings/exposure/inspection_schedule/roi) 레거시 폴백 체인

---

### BE-09: UUID 동기화 현황 조사

**결론:** 방법 B(auth_id 컬럼) 이미 완전 구현됨. 추가 DB 작업 불필요.

**확인 내용:**
- `auth_id` 컬럼 존재 ✅
- UNIQUE INDEX 2개 (`idx_users_auth_id`, `users_auth_id_unique`) ✅
- 10명 auth_id 올바르게 세팅 ✅
- auth.py 전 엔드포인트 `auth_id` 기반 조회 ✅
- scen-*.test 7명은 auth.users 없는 더미 계정 (방치 정상)

**워크오더:** `docs/workorder-BE09-uuid-sync.md`

---

### BE-10: 업무 지연 에스컬레이션 v1.0.0

**파일:** `routers/overdue_checker.py`  
**main.py:** v5.28.0

**DB migration:** `be10_overdue_escalation`
- `work_assignments`: `due_date`, `overdue_level`, `last_reminded_at`, `resolved_at` 4컬럼 추가
- `overdue_history`: 신규 테이블 (FK 3개, 인덱스 3개)

**에스컬레이션 4단계:**

| 단계 | level | 조건 | 대상 | 채널 |
|---|---|---|---|---|
| D-1 리마인더 | 1 | 마감 1일 전 | 작업자 | SMS |
| D+1 작업자 경고 | 2 | 1일 초과 | 작업자 | SMS + FCM |
| D+2 관리자 알림 | 3 | 2일 초과 | 안전관리자 | SMS + FCM |
| D+7 OVERDUE | 4 | 7일 초과 | 안전관리자 | SMS + FCM + 상태전환 |

**API:**
- `POST /overdue/check` — 에스컬레이션 실행 (dry_run 지원)
- `GET /overdue/summary` — 지연 현황 요약
- `GET /overdue/history` — 이력 조회
- `POST /overdue/resolve/{history_id}` — 지연 해소

**dry_run 시뮬레이션 결과 (기존 4,266건):**
- D-1 REMIND: 698건
- D+1 WARN: 265건
- D+2 NOTIFY: 1,325건
- D+7 OVERDUE: 1,978건

**주의:** due_date 미설정 → scheduled_date 기준 계산. 실운영 전 due_date 세팅 권장.  
**FCM:** send-push Edge Function 미배포 → SMS + notifications만 즉시 동작.

---

## 커밋 이력 (dev 브랜치)

| SHA | 내용 |
|---|---|
| 4e1d965f | BE-08: diagnosis_transform.py + main.py v5.27.0 |
| 13374b10 | BE-09: UUID 동기화 워크오더 |
| 6c412aa6 | BE-10: overdue_checker.py + main.py v5.28.0 |
| ba6358b6 | docs: BE-06-final 완료 보고 + 세션 pt4 요약 |

---

## PENDING 사항

| 항목 | 조치 |
|---|---|
| SB-06 collect 수동 실행 | `POST https://api.taieng.co.kr/precedents/collect` |
| PR #1 머지 (dev→main) | 기획창 승인 후 머지 |
| FCM send-push Edge Function | 별도 배포 필요 |
| due_date 세팅 | work_assignments 실 운영 전 마감일 입력 |
| agent_service 가격 | base_price 전부 null → PATCH로 단가 입력 |
