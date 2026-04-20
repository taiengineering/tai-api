# TAI 자동 QA 정책 v1.0

> 사람이 QA를 하지 않아도 서비스 이상을 자동으로 감지하는 것이 목표.
> 사이트별 / 모듈별 / 서비스별로 체크 항목을 정의하고, 기능 완성 시 순차 활성화.

---

## 1. 범위

| 사이트 | URL | 비고 |
|--------|-----|------|
| 마케팅 사이트 | new.taieng.co.kr | Nexas 템플릿, Cloudflare Pages |
| Safe 앱 | safe.taieng.co.kr | 작업자/안전관리자 인터페이스 |
| Backend API | api.taieng.co.kr | Fly.io, FastAPI |
| Admin | admin.taieng.co.kr | 슈퍼어드민 전용 |

---

## 2. 체크 등급 정의

| 등급 | 기준 | 실패 시 액션 |
|------|------|--------------|
| **P0** | 서비스 완전 불가 | 즉시 SMS 알림 |
| **P1** | 핵심 기능 오류 | SMS 알림 |
| **P2** | 부가 기능 오류 | 로그만 기록 |
| **P3** | 성능 저하 (latency) | 로그만 기록 |

---

## 3. Backend API 체크리스트

### 3-1. 인프라 / 헬스 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-01 | 서버 응답 | GET /health | 200, status=healthy | ✅ 운용 중 |
| B-02 | DB 연결 | /health 내 law_engine count | count > 0 | ✅ 운용 중 |
| B-03 | Gotenberg (PDF 엔진) | GET http://gotenberg.railway.internal:3000/health | 200 | ✅ 운용 중 |
| B-04 | Cold start 감지 | /health 응답시간 | < 3초 | ✅ 운용 중 |

### 3-2. 인증 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-10 | 토큰 발급 | POST /auth/token (테스트 계정) | 200 + access_token | ✅ 가능 |
| B-11 | 토큰 검증 | GET /auth/me (발급된 토큰) | 200 + user_id | ✅ 가능 |
| B-12 | 만료 토큰 차단 | GET /auth/me (만료 토큰) | 401 | ✅ 가능 |

### 3-3. 법령진단 — 핵심 파이프라인 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-20 | 진단 실행 (건물 무료) | POST /diagnosis/run {sector:BUILDING, tier:FREE} | 200 + result_id | ✅ 가능 |
| B-21 | 진단 결과 조회 | GET /diagnosis/transform/{id} | 200 + obligations 배열 | ✅ 가능 |
| B-22 | 진단 실행 (산업) | POST /diagnosis/run {sector:INDUSTRY} | 200 | ✅ 가능 |
| B-23 | 진단 실행 (건설) | POST /diagnosis/run {sector:CONSTRUCTION} | 200 | ✅ 가능 |
| B-24 | 주소 자동완성 | GET /diagnosis/autofill/address | 200 + 건축물대장 | ✅ 가능 |
| B-25 | 사업자번호 자동완성 | GET /diagnosis/autofill/biz | 200 | ✅ 가능 |
| B-26 | 유료 PDF 생성 | POST /diagnosis/report-pdf/{token} | 200 + PDF binary | ⚠️ #5 검증 중 |
| B-27 | 기안서 PDF 생성 | POST /proposals/{id}/pdf | 200 + PDF binary | ✅ 가능 |

### 3-4. 결제 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-30 | 결제 준비 | POST /payments/prepare | 200 + order_id | ⚠️ KG이니시스 승인대기 |
| B-31 | 결제 검증 | POST /payments/verify | 200 | ⚠️ 승인대기 |
| B-32 | 가격 API | GET /pricing/saas | 200 + 요금 배열 | ✅ 가능 |
| B-33 | 진단 가격 API | GET /pricing/diagnosis | 200 + 요금 배열 | ✅ 가능 |

### 3-5. SaaS 핵심 기능 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-40 | 시설(Factory) 목록 | GET /factories | 200 + 배열 | ✅ 가능 |
| B-41 | 점검 일정 조회 | GET /schedules | 200 | ✅ 가능 |
| B-42 | 점검 일정 생성 | POST /schedules/generate | 200 | ✅ 가능 |
| B-43 | 작업 배정 조회 | GET /work-assignments | 200 | ✅ 가능 |
| B-44 | 미이행 요약 | GET /overdue/summary | 200 | ✅ 가능 |
| B-45 | TBM 실행 여부 | GET /tbm (count > 0) | count > 0 | ❌ 미구현 |
| B-46 | 위험성평가 | GET /risk-assessments | 200 + count | ❌ 미구현 |

### 3-6. 알림 / SMS (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-50 | SMS 발송 | POST /messaging/debug-send | 200 + code=100 | ✅ 운용 중 |
| B-51 | 날씨 작업중지 판단 | GET /weather/check | 200 + 판단값 | ✅ 가능 |

### 3-7. 안전정보 / 데이터 (P2)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-60 | 산재판례 수집 | GET /precedents (count > 0) | count > 0 | ❌ 0건 (수동 실행 필요) |
| B-61 | 외부 API 모니터 | GET /external-api/status | 9개 PENDING → 정상 | ⚠️ PENDING |

---

## 4. 마케팅 사이트 체크리스트 (new.taieng.co.kr)

### 4-1. 페이지 로딩 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| M-01 | 홈 로딩 | GET / | 200, < 3초 | ✅ 가능 |
| M-02 | 가격표 페이지 | GET /nexas/pricing.html | 200 | ✅ 가능 |
| M-03 | 법령진단 입력 | GET /free-diagnosis.html | 200 | ✅ 가능 |
| M-04 | 특허 페이지 | GET /nexas/patents.html | 200 | ✅ 가능 |

### 4-2. 마케팅 핵심 전환 경로 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| M-10 | 진단 CTA 버튼 링크 | HTML 내 href 존재 확인 | /free-diagnosis.html 링크 | ✅ 가능 |
| M-11 | 가격표 API 연동 | pricing.html 로드 후 가격 렌더링 | 가격 텍스트 노출 | ✅ 가능 |
| M-12 | for-safety-manager 페이지 | GET /nexas/for-safety-manager.html | 200 | ❌ 미완성 |
| M-13 | for-business-owner 페이지 | GET /nexas/for-business-owner.html | 200 | ❌ 미완성 |

### 4-3. 법령진단 플로우 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| M-20 | 진단 입력 폼 로딩 | GET /free-diagnosis.html | 200 + form 요소 존재 | ✅ 가능 |
| M-21 | 진단 결과 페이지 | GET /paid-diagnosis-result.html | 200 | ⚠️ 기획 대기 |
| M-22 | 본인인증 API 호출 | KG이니시스 CI 엔드포인트 | 200 | ⚠️ 승인대기 |

---

## 5. Safe 사이트 체크리스트 (safe.taieng.co.kr)

### 5-1. 페이지 로딩 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-01 | 로그인 페이지 | GET /login.html | 200 | ✅ 가능 |
| S-02 | 대시보드 (인증 후) | GET /safety-dashboard.html | 200 (토큰 필요) | ✅ 가능 |
| S-03 | 작업자 홈 | GET /app/index.html | 200 | ✅ 가능 |
| S-04 | 점검 캘린더 | GET /inspection-calendar.html | 200 | ✅ 가능 |

### 5-2. 안전관리자 핵심 기능 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-10 | 날씨 위젯 | GET /weather/check → 위젯 렌더링 | 날씨 데이터 노출 | ✅ 가능 |
| S-11 | 미이행 대시보드 | GET /overdue-list.html | 200 | ✅ 가능 |
| S-12 | 점검 일정 목록 | GET /inspection-schedule.html | 200 | ✅ 가능 |
| S-13 | 법령진단 결과 렌더러 | GET /diagnosis-result-v2.html | 200 | ✅ 가능 |
| S-14 | 시설 목록 | GET /factory-list.html | 200 | ✅ 가능 |

### 5-3. 작업자 기능 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-20 | 작업 배정 목록 | GET /work-assignment-list.html | 200 | ✅ 가능 |
| S-21 | TBM 실행 페이지 | GET /tbm-start.html | 200 | ⚠️ 건설 하드코딩 이슈 |
| S-22 | 점검 완료율 게이지 | 대시보드 게이지 > 0% | 0% 아님 | ❌ 항상 0% 버그 |
| S-23 | 이상 보고 | POST /corrective-actions | 200 | ❌ 0건 상태 |

### 5-4. 미래 기능 (구현 후 활성화) (P1~P2)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-30 | QR/RFID 체크인 | POST /checkin/qr | 200 | ❌ 미구현 |
| S-31 | 위험성평가 작성 | POST /risk-assessments | 200 | ❌ 미구현 |
| S-32 | 교육 이수 체크 | POST /education/complete | 200 | ❌ 미구현 |

---

## 6. 체크 실행 정책

| 항목 | 정책 |
|------|------|
| 실행 주기 | 5분마다 |
| 실행 방법 | pg_cron (Supabase) |
| 결과 저장 | `auto_qa_log` 테이블 (id, check_id, status, latency_ms, error_msg, checked_at) |
| 알림 조건 | P0: 1회 실패 → SMS / P1: 연속 3회 실패 → SMS |
| 알림 채널 | MessageMi SMS → 01047758888 |
| 실패 중복 방지 | 동일 check_id 알림 후 30분 이내 재발송 없음 |
| 비활성화 방법 | `auto_qa_checks` 테이블의 `is_active = false` 처리 |

---

## 7. 구현 우선순위

### Phase 1 — 지금 당장 (현재 구현된 것만)
- B-01, B-02 (헬스)
- B-10, B-11 (인증)
- B-20, B-21 (진단 실행/조회)
- B-50 (SMS)
- M-01, M-03 (마케팅 홈, 진단 폼)
- S-01, S-02 (Safe 로그인, 대시보드)

### Phase 2 — KG이니시스 승인 후
- B-30, B-31 (결제)
- M-22 (본인인증)

### Phase 3 — 미구현 기능 완성 후
- B-45, B-46 (TBM, 위험성평가)
- S-21 ~ S-23 (작업자 기능)
- M-12, M-13 (타겟 페이지)

### Phase 4 — 장기
- S-30 ~ S-32 (QR, 교육)
- B-60 (산재판례)
