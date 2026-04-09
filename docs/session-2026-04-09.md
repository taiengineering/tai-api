# TAI Safe 작업 내역 — 2026-04-09

## 1. construction.py v2.1.0 — 건설섹터 백엔드 완성

### 추가 엔드포인트
- `POST /construction/sites/{site_id}/diagnose` — 건설 법령진단 독립 실행
  - CONSTRUCTION 173개 규칙 → 현장 조건 매칭
  - `factory_diagnosis_results` 저장
  - `construction_sites.diagnosis_applicable_count` 업데이트
- `POST /construction/sites/{site_id}/generate-schedules` — 작업일정 자동 생성 독립 엔드포인트
  - 최신 진단 결과의 `inspection_required` + `action_required` → `work_schedules` 생성
  - 중복 rule_code 자동 스킵
- 점검 저장 시 이상 감지 → 안전관리자 FCM 자동 발송
  - `checklist_items` 중 bad/fail → `defect_count` 자동 계산
  - FAIL/ISSUE 시 `site.manager_id → users.fcm_token → FCM` 발송

---

## 2. inspection_sets.py v2.0.0 — Pipeline Priority 1

### 핵심 변경
- `POST /inspection-sets/generate-schedules/{factory_id}` v2.0.0
  - **4조건 체크**: `schedule_anchor_date` + `cycle_unit` + `assignee_user_id` + `description/legal_rule_code`
  - `source_type = 'LAW_ENGINE'` (기존 LEGAL과 구분)
  - NOT EXISTS 중복 방지 (`inspection_set_id` 기준)
  - `mode='law_engine'`(기본) / `mode='anchor'`(v1.9.0 하위 호환)
- `POST /inspection-sets/generate-schedules-all` 신규
  - 전체 factories 일괄 LAW_ENGINE 스케줄 생성

### DB 현황 확인
- inspection_sets 76건 중 assignee_user_id = 0건 (4조건 미충족)
- → assignee_user_id 설정 시 즉시 LAW_ENGINE 스케줄 생성 가능

---

## 3. schedule_pipeline.py v1.1.0

- `trigger-due-alerts`: `assigned_user_id IS NOT NULL` 필터 추가
- 담당자 없는 일정에는 D-7/D-3/당일 알림 미발송

---

## 4. payment.py — pricing 페이지 기간 선택 탭 삭제

- 1개월/3개월/6개월/12개월 선택 탭 제거
- 가격 고정: 베이직 79,000원 / 프리미엄 149,000원
- `period_months: 1` 고정, 할인 로직 제거
- summaryText: "베이직" / "프리미엄" (개월 표시 제거)

---

## 5. messaging.py v2.0.0 — 메세지미 SMS 연동 완성

### 문제 해결 과정
1. `MESSAGEME_SENDER` 잘못된 값 (070-8080-1858 → 01047758888 수정)
2. API URL 오류: `https://www.messageme.co.kr/send_api_v2.jsp` → `http://221.139.14.136/APIV2/API/sms_send`
3. 파라미터명 오류: `sender/receiver` → `callback/dstaddr`
4. Railway IP → 메세지미 서버 직접 연결 차단 (타임아웃)

### 최종 해결: Supabase Edge Function 우회
```
Railway (TAI API) → Supabase Edge Function (send-sms) → 메세지미 서버
```
- Edge Function 배포: `supabase.co/functions/v1/send-sms`
- 발송 성공 확인: `result_code: 100`
- Railway Variables: `MESSAGEME_API_KEY`, `MESSAGEME_SENDER`
- Supabase Secrets: `MESSAGEME_API_KEY`, `MESSAGEME_SENDER`

### 진단 엔드포인트
- `GET /messaging/debug` — 환경변수 상태 확인
- `GET /messaging/debug-send?receiver=&message=` — 실제 발송 + 원본 응답

---

## 6. robots.txt — 전체 크롤링 차단 (tai-admin 레포)

모든 검색엔진 수집 완전 차단:
- `robots.txt` (루트) — 기본
- `site/full-version/html/robots.txt` — admin.taieng.co.kr
- `tadmin/robots.txt` — safe.taieng.co.kr
- `request/robots.txt` — taieng.co.kr

```
User-agent: *
Disallow: /
```

---

## 7. 건설섹터 문서 업데이트 (tai-api/docs)

- `workorder_construction_v21_summary.md` — 6개 항목 모두 완료 표시
- `prompt_construction_backend.md` — v2.1.0 완료 상태 반영
- `prompt_construction_frontend.md` — 백엔드 API 현황 포함

---

## 8. 논의 사항 (미구현, 향후 진행)

### KOSHA 공공 API 신청 예정
현재 미신청 항목 (data.go.kr에서 신청):
- 사고사망 게시판 조회
- 건설현장 안전 신호등
- 위험성평가 인정사업장 현황

### 위험관리엔진 설계 논의
- 법령엔진과 별개: 공정·설비·모델 기반 위험도 산출
- 위험도 = 발생빈도 × 피해강도 (ISO 31000 기준)
- `hazard_master` 테이블 설계 → 4단계 (LOW/MEDIUM/HIGH/CRITICAL)
- KOSHA 재해사례 API 연동으로 위험 데이터 강화

### 알림톡
- 카카오 채널 등록 + 메세지미 연동 완료
- 템플릿 등록 필요 (TAI Safe 주요 알림 = 앱 푸시로 처리, 알림톡 우선순위 낮음)
- 발신번호 통신사 차단 해제 후 SMS 테스트 재진행

### 다국어 지원 검토
- 건설·제조업 외국인 비중: 건설 16.2%, 어업 30~40%, 제조업 10~15%
- 주요 국적: 한국계 중국인(1위), 베트남(2위), 네팔(3위)
- 앱 UI 다국어 지원 시 경쟁 차별점 확보 가능 (중국어·베트남어·영어)

---

## 완료 기준 SQL (LAW_ENGINE 파이프라인)
```sql
SELECT source_type, COUNT(*)
FROM work_schedules
GROUP BY source_type;
-- LAW_ENGINE 행이 생겨야 성공
-- 현재: assignee_user_id = 0건이므로 inspection_sets에 담당자 설정 필요
```
