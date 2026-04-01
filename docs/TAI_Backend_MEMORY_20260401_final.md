# TAI Backend MEMORY — 2026-04-01 마감

## 오늘 완료된 작업

---

### Priority 2 — TBM / 안전회의 / 위험성평가 / 법령진단 접근체크

---

#### routers/tbm.py v1.0.0 (신규)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /tbm | TBM 생성 (company_id 자동 조회) |
| GET | /tbm | 목록 (factory_id/status/날짜 필터, 페이징) |
| GET | /tbm/{id} | 상세 + 참석자 포함 |
| PATCH | /tbm/{id} | 수정 |
| POST | /tbm/{id}/complete | 완료 처리 |
| POST | /tbm/transcribe | STT 텍스트 저장 (고정경로, /{id} 앞 선언) |
| GET | /tbm/{id}/attendees | 참석자 목록 |
| POST | /tbm/{id}/attendees | 참석자 추가 + attendee_count 자동 갱신 |
| PATCH | /tbm/{id}/attendees/{aid}/sign | 전자서명 등록 |

---

#### routers/safety_meetings.py v1.0.0 (신규)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /safety-meetings | 회의록 생성 (retention_expires 자동 계산) |
| GET | /safety-meetings | 목록 (meeting_type/status/year 필터) |
| GET | /safety-meetings/schedule | 개최 주기 준수 현황 (고정경로) |
| GET | /safety-meetings/{id} | 상세 |
| PATCH | /safety-meetings/{id} | 수정 |
| POST | /safety-meetings/{id}/files | 파일 URL 첨부 (files_json 배열) |
| POST | /safety-meetings/{id}/complete | 완료 처리 |

schedule 응답 구조:
- SAFETY_COMMITTEE: 분기별(1~4) 개최 여부 + overdue 여부
- CONTRACTOR_COUNCIL: 월별(1~12) 개최 여부 + overdue 여부

---

#### routers/risk_assessments.py v1.0.0 (신규)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /risk-assessments | 등록 (REGULAR이면 next_review_date 자동 +1년) |
| GET | /risk-assessments | 목록 (type/status/year 필터, next_review_dday 포함) |
| GET | /risk-assessments/dashboard | 현황 요약 (고정경로) |
| GET | /risk-assessments/{id} | 상세 |
| PATCH | /risk-assessments/{id} | 수정 |
| POST | /risk-assessments/{id}/files | 파일 URL 첨부 |
| POST | /risk-assessments/{id}/complete | 완료 처리 |

dashboard 응답: initial_done, next_regular_dday, pending_special, alert 문자열

---

#### routers/diagnosis.py v1.0.0 (어제 완료, 오늘 배포 포함)

`GET /diagnosis/access-check?factory_id=&step=`
- step=1 → FREE (항상 접근 가능)
- step=2/3/99 → diagnosis_purchases 단건 결제 확인
- SaaS contract_level 체크 없음

---

### main.py v5.0.0

신규 등록:
```python
from routers.tbm             import router as tbm_router           # /tbm
from routers.safety_meetings import router as safety_meetings_router # /safety-meetings
from routers.risk_assessments import router as risk_assessments_router # /risk-assessments
```

---

## 현재 API 버전 현황

```
main.py                      v5.0.0
routers/auth.py              v3.4.0
routers/companies.py         v2.1.0
routers/factories.py         v2.1.0
routers/users.py             v2.1.0
routers/equipment_assets.py  v1.1.0
routers/event_trigger.py     v1.0.0
routers/worker_registry.py   v1.0.0
routers/inspection_sets.py   v1.5.0
routers/inspection_checklist.py v1.4.0
routers/education_assign.py  v1.0.0
routers/factory_process_v3.py v3.2.0
routers/diagnosis.py         v1.0.0
routers/tbm.py               v1.0.0  ← NEW
routers/safety_meetings.py   v1.0.0  ← NEW
routers/risk_assessments.py  v1.0.0  ← NEW
```

---

## DB 테이블 현황 (오늘 기준)

| 테이블 | 상태 | 비고 |
|--------|------|------|
| tbm_meetings | ✅ | audio_url, transcript_text, status_code 등 |
| tbm_attendees | ✅ | worker_id, signature_url 등 |
| safety_committee_meetings | ✅ | meeting_type, files_json 등 |
| risk_assessments | ✅ | items_json, files_json, next_review_date 등 |
| diagnosis_purchases | ✅ | step(2/3/99), status(PAID/REFUNDED), expires_at |
| work_schedules | ✅ | created_at/updated_at 컬럼 추가 완료 |

---

## PENDING 작업

1. `POST /auth/seed-test-accounts` 호출 미실행
2. 12개 법령 수집 (data.go.kr)
3. 80개 report-obligation rules → form_code 매핑
4. 건설섹터 알고리즘
5. Cloudflare Zero Trust Access
6. **공지예외주장 제출 기한: 2026-04-28** (patent.go.kr)
7. 프론트: factory_id UUID 형식 수정 (cc000003 → UUID)
8. 프론트: tbm-list.html / safety-meeting-list.html / risk-assessment-list.html
