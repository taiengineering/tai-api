# TAI 자동 QA 정책 v1.1

> 사람이 QA를 하지 않아도 서비스 이상을 자동으로 감지하는 것이 목표.
> 사이트별 / 모듈별 / 서비스별로 체크 항목을 정의하고, 기능 완성 시 순차 활성화.

---

## 0. 인프라 현황 (2026-04-20 기준)

| 항목 | 내용 |
|------|------|
| **백엔드** | Railway (Singapore, asia-southeast1) |
| **배포 방식** | main push → 즉시 자동배포 (staging 없음) |
| **Gotenberg** | Railway 내부: `gotenberg.railway.internal:3000` (pg_net 직접 접근 불가 → /health 간접 확인) |
| **Proxy** | iwinv VPS 115.68.227.222:3128 (SMS 발송용) |
| **DB** | Supabase (xntdkrjhgcscmqctdzyo) |
| **프론트** | Cloudflare Pages |

---

## 1. 범위

| 사이트 | URL | 비고 |
|--------|-----|------|
| 마케팅 사이트 | taieng.co.kr | Nexas 템플릿, Cloudflare Pages |
| Safe 앱 | safe.taieng.co.kr | 작업자/안전관리자 인터페이스 |
| Backend API | api.taieng.co.kr | Railway, FastAPI |
| Admin | admin.taieng.co.kr | 슈퍼어드민 전용 |

---

## 2. 체크 등급 정의

| 등급 | 기준 | 실패 시 액션 |
|------|------|--------------||
| **P0** | 서비스 완전 불가 | 즉시 이메일 알림 (taiengcokr@taieng.co.kr) |
| **P1** | 핵심 기능 오류 | 이메일 알림 |
| **P2** | 부가 기능 오류 | 로그만 기록 |
| **P3** | 성능 저하 (latency) | 로그만 기록 |

---

## 3. Backend API 체크리스트

### 3-1. 인프라 / 헬스 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-01 | 서버 응답 | GET /health | 200, status=healthy | ✅ 활성 |
| B-02 | DB 연결 | /health 내 law_engine count | count > 0 | ✅ 활성 |
| B-03 | Gotenberg 간접 확인 | GET /health | 200 (Gotenberg 상태 포함) | ✅ 활성 (내부 URL 직접 접근 불가) |
| B-04 | Cold start 응답시간 | GET /health | < 3초 | ✅ 활성 |

### 3-2. 인증 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-10 | 토큰 발급 | POST /auth/token (테스트 계정) | 200 + access_token | ✅ 활성 |
| B-11 | 토큰 검증 | GET /auth/me (발급된 토큰) | 200 + user_id | ✅ 활성 |
| B-12 | 만료 토큰 차단 | GET /auth/me (만료 토큰) | 401 | ⏸️ 비활성 (만료 토큰 생성 로직 필요) |

### 3-3. 법령진단 — 핵심 파이프라인 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-20 | 진단 실행 (건물 무료) | POST /diagnosis/run {sector:BUILDING, tier:FREE} | 200 + result_id | ✅ 활성 |
| B-21 | 진단 결과 조회 | GET /diagnosis/transform/{id} | 200 + obligations 배열 | ✅ 활성 |
| B-22 | 진단 실행 (산업) | POST /diagnosis/run {sector:INDUSTRY} | 200 | ⏸️ 비활성 (POST 미지원) |
| B-23 | 진단 실행 (건설) | POST /diagnosis/run {sector:CONSTRUCTION} | 200 | ⏸️ 비활성 (POST 미지원) |
| B-24 | 주소 자동완성 | GET /diagnosis/autofill/address | 200 + 건축물대장 | ⏸️ 비활성 |
| B-25 | 사업자번호 자동완성 | GET /diagnosis/autofill/biz | 200 | ⏸️ 비활성 |
| B-26 | 유료 PDF 생성 | POST /diagnosis/report-pdf/{token} | 200 + PDF | ⚠️ #5 검증 중 |
| B-27 | 기안서 PDF 생성 | POST /proposals/{id}/pdf | 200 + PDF | ⏸️ 비활성 |

### 3-4. 결제 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-30 | 결제 준비 | POST /payments/prepare | 200 + order_id | ❌ 미개발 (KG이니시스 승인대기) |
| B-31 | 결제 검증 | POST /payments/verify | 200 | ❌ 미개발 |
| B-32 | SaaS 요금 API | GET /pricing/saas | 200 + 요금 배열 | ✅ 활성 |
| B-33 | 진단 요금 API | GET /pricing/diagnosis | 200 + 요금 배열 | ⏸️ 비활성 |

### 3-5. SaaS 핵심 기능 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-40 | 시설 목록 조회 | GET /factories | 200 + 배열 | ⏸️ 비활성 |
| B-41 | 점검 일정 조회 | GET /schedules | 200 | ⏸️ 비활성 |
| B-42 | 점검 일정 생성 | POST /schedules/generate | 200 | ⏸️ 비활성 |
| B-43 | 작업 배정 조회 | GET /work-assignments | 200 | ⏸️ 비활성 |
| B-44 | 미이행 요약 | GET /overdue/summary | 200 | ⏸️ 비활성 |
| B-45 | TBM 실행 여부 | GET /tbm | count > 0 | ❌ 미구현 |
| B-46 | 위험성평가 | GET /risk-assessments | 200 + count | ❌ 미구현 |

### 3-6. 알림 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-50 | SMS 발송 | POST /messaging/debug-send | 200 + code=100 | ✅ 활성 |
| B-51 | 날씨 작업중지 판단 | GET /weather/check | 200 + 판단값 | ⏸️ 비활성 |

### 3-7. 데이터 (P2)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| B-60 | 산재판례 수집 | GET /precedents | count > 0 | ❌ 0건 |
| B-61 | 외부 API 모니터 | GET /external-api/status | PENDING → 정상 | ⚠️ PENDING |

---

## 4. 마케팅 사이트 체크리스트 (taieng.co.kr)

### 4-1. 페이지 로딩 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| M-01 | 홈 로딩 | GET / | 200, < 3초 | ✅ 활성 |
| M-02 | 가격표 페이지 | GET /nexas/pricing.html | 200 | ✅ 활성 |
| M-03 | 법령진단 입력 폼 | GET /free-diagnosis.html | 200 | ✅ 활성 |
| M-04 | 특허 페이지 | GET /nexas/patents.html | 200 | ⏸️ 비활성 |

### 4-2. 마케팅 전환 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| M-10 | 진단 CTA 링크 존재 | HTML href 확인 | /free-diagnosis.html 링크 | ⏸️ 비활성 |
| M-11 | 가격표 API 렌더링 | pricing.html 로드 | 가격 텍스트 노출 | ⏸️ 비활성 |
| M-12 | 안전관리자 타겟 페이지 | GET /nexas/for-safety-manager.html | 200 | ❌ 미완성 |
| M-13 | 사업주 타겟 페이지 | GET /nexas/for-business-owner.html | 200 | ❌ 미완성 |

### 4-3. 진단 플로우 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| M-20 | 진단 입력 폼 요소 | HTML form 요소 존재 | form 존재 | ⏸️ 비활성 |
| M-21 | 유료 진단 결과 페이지 | GET /paid-diagnosis-result.html | 200 | ❌ 기획 대기 |
| M-22 | 본인인증 API | POST /identity/verify | 200 | ❌ 미개발 |

---

## 5. Safe 사이트 체크리스트 (safe.taieng.co.kr)

### 5-1. 페이지 로딩 (P0)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-01 | 로그인 페이지 | GET /login.html | 200 | ✅ 활성 |
| S-02 | 대시보드 (인증 후) | GET /safety-dashboard.html | 200 | ⏸️ 비활성 (토큰 필요) |
| S-03 | 작업자 홈 | GET /app/index.html | 200 | ⏸️ 비활성 |
| S-04 | 점검 캘린더 | GET /inspection-calendar.html | 200 | ⏸️ 비활성 |

### 5-2. 안전관리자 기능 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-10 | 날씨 위젯 | GET /weather/check | 날씨 데이터 노출 | ⏸️ 비활성 |
| S-11 | 미이행 대시보드 | GET /overdue-list.html | 200 | ⏸️ 비활성 |
| S-12 | 점검 일정 목록 | GET /inspection-schedule.html | 200 | ⏸️ 비활성 |
| S-13 | 진단 결과 렌더러 | GET /diagnosis-result-v2.html | 200 | ⏸️ 비활성 |
| S-14 | 시설 목록 | GET /factory-list.html | 200 | ⏸️ 비활성 |

### 5-3. 작업자 기능 (P1)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-20 | 작업 배정 목록 | GET /work-assignment-list.html | 200 | ⏸️ 비활성 |
| S-21 | TBM 실행 페이지 | GET /tbm-start.html | 200 | ⚠️ 건설 하드코딩 이슈 |
| S-22 | 점검 완료율 > 0% | 대시보드 게이지 | 0% 아님 | ❌ 항상 0% 버그 |
| S-23 | 이상 보고 등록 | POST /corrective-actions | 200 | ❌ 0건 상태 |

### 5-4. 미래 기능 (P1~P2)

| ID | 체크 항목 | 방법 | 기준 | 현황 |
|----|-----------|------|------|----- |
| S-30 | QR/RFID 체크인 | POST /checkin/qr | 200 | ❌ 미구현 |
| S-31 | 위험성평가 작성 | POST /risk-assessments | 200 | ❌ 미구현 |
| S-32 | 교육 이수 체크 | POST /education/complete | 200 | ❌ 미구현 |

---

## 6. 체크 실행 정책

| 항목 | 정책 |
|------|------|
| 실행 주기 | **30분마다** (사용자 증가 시 5분으로 단축 예정) |
| 실행 방법 | pg_cron (Supabase) → `run_auto_qa()` 함수 |
| 결과 저장 | `auto_qa_log` 테이블 |
| 알림 조건 | P0: 1회 실패 → 이메일 즉시 발송 |
| 알림 채널 | `taiengcokr@taieng.co.kr` (via /mail/send-system) |
| 중복 방지 | 동일 check_id 30분 이내 재발송 없음 |
| 비활성화 | `auto_qa_checks.is_active = false` |
| 관리 화면 | admin.taieng.co.kr/auto-qa-dashboard.html |

---

## 7. 구현 우선순위

### Phase 1 — 현재 활성 (14개)
B-01, B-02, B-03, B-04, B-10, B-11, B-20, B-21, B-32, B-50, M-01, M-02, M-03, S-01

### Phase 2 — KG이니시스 승인 후
B-30, B-31, M-22

### Phase 3 — 미구현 기능 완성 후
B-45, B-46, S-21~S-23, M-12, M-13

### Phase 4 — 장기
S-30~S-32, B-60
