# TAI Backend MEMORY — 교육 발령·이수 관리 (2026-03-31)

## 작업 결과 요약

작업지시서: `docs/TAI_Cursor_작업지시서_교육발령_이수관리_20260331.md`

백엔드 작업 전 확인 결과 **이미 완성 상태**였음.
크론 등록(누락)만 신규 처리.

---

## 완료 항목

### routers/education_assign.py (v1.0.0) — 기존 완성

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /education/master | 교육 마스터 목록 |
| GET | /education/company-settings | 회사별 링크 목록 (effective_url 포함) |
| PUT | /education/company-settings/{education_id} | UPSERT |
| DELETE | /education/company-settings/{education_id} | 기본값 복원 |
| POST | /education/assign | 교육 발령 다건 |
| GET | /education/assignments/summary | 요약 통계 |
| GET | /education/assignments | 목록 (effective_url 포함) |
| PATCH | /education/assignment/{id}/complete | 이수 완료 |
| POST | /education/assignment/{id}/certificate | 이수증 URL 저장 |
| POST | /education/assignments/expire | 만료 처리 (크론용) |

### DB 테이블 — 기존 완성

- `company_education_setting`: id, company_id, education_id, custom_url, custom_url_label, custom_note, is_active, created_by, created_at, updated_at
- `education_assignment`: id, factory_id, education_id, worker_id, user_id, assigned_at, due_date, status_code, completed_at, completed_hours, certificate_url, note, ...
- `education_master`: 기존 테이블 활용

### main.py — v4.8.0 (기존 등록 완료)

```python
app.include_router(education_assign_router)  # /education prefix
```

### cron_job_master — 금일 신규 등록

```
job_code:        EDU_EXPIRE_DAILY
endpoint_url:    /education/assignments/expire
cron_expression: 0 1 * * *  (매일 01:00)
```

---

## effective_url 우선순위

```
1순위: company_education_setting.custom_url
2순위: education_master.source_url  (KOSHA 기본)
3순위: None → "이수증만 업로드" 안내
```

---

## PENDING 항목 (프론트 담당)

- education-setting.html (tadmin) — 교육 링크 설정 화면
- education-list.html (tadmin) — 이수 현황 + 발령 모달
