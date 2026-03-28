# TAI 백엔드 메모리 — 2026-03-28

## 서버 정보
- API: api.taieng.co.kr (Railway)
- DB: Supabase (xntdkrjhgcscmqctdzyo)
- 스택: FastAPI + Python 3.13.4
- GitHub: taiengineering/tai-api
- 최고관리자: hetto@kakao.com / 심태왕 / role_code: 001

---

## 오늘 완료된 작업

### 1. report_forms.py v2.0.0 업그레이드 ✅

**신규 엔드포인트:**
| 엔드포인트 | 내용 |
|-----------|------|
| `GET /report-forms/obligations` | 법적 의무 목록 |
| `GET /report-forms/obligations/by-factory/{id}` | 시설별 해당 의무 |
| `POST /report-forms/submissions/preview-pdf` | 즉시 PDF 스트림 |
| `POST /report-forms/submissions/{id}/pdf` | 저장 후 PDF 반환 |

**PDF 생성 로직 (WeasyPrint → xhtml2pdf 폴백):**
```python
def _generate_pdf_bytes(html_content):
    try:
        from weasyprint import HTML as WeasyHTML
        return WeasyHTML(string=html_content, base_url=".").write_pdf()
    except ImportError:
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        pisa.CreatePDF(html_content, dest=buf)
        return buf.getvalue()
```

**HTML 렌더링 (Jinja2 없이):**
```python
def _render_html_template(template_path, form_data):
    html = Path(template_path).read_text(encoding='utf-8')
    for k, v in form_data.items():
        html = html.replace('{{ ' + k + ' }}', str(v) if v else '')
    html = re.sub(r'\{\{\s*\w+\s*\}\}', '', html)
    return html
```

**TEMPLATE_MAP (form_code → 파일 경로):**
```python
TEMPLATE_MAP = {
    "OSHACT-FORM-002": "templates/forms/OSHACT_FORM_002.html",
}
```

### 2. templates/forms/OSHACT_FORM_002.html 신규 ✅
- A4 페이지 설정 (@page)
- 사업체 / 안전관리자 / 보건관리자 / 산업보건의 / 제출 정보 섹션
- {{ key }} 치환 방식
- 첨부서류 안내 푸터

### 3. requirements.txt weasyprint 추가 ✅
```
weasyprint  # Railway 빌드 실패 시 xhtml2pdf로 교체
```

### 4. DB 테이블 신규 생성 ✅
```sql
-- legal_obligations (법적 의무 마스터)
-- obligation_form_mapping (의무↔서식 매핑)
```

**적재 현황:**
- legal_obligations: 11건 INSERT 완료 (총 17건 — 기존 포함)
- obligation_form_mapping: ⚠️ 미완료 — 다음 세션
- OSHACT-FORM-002 form_json UPDATE: ⚠️ 미완료 — 다음 세션

### 5. NTS 국세청 검증 응답 필드 확정 ✅
```
valid_yn  : true = 대표자명 진위 일치
is_active : true = 계속사업자
```

---

## 현재 라우터 목록 (main.py v3.2.0)

| 파일 | prefix | 주요 기능 |
|------|--------|----------|
| auth.py | /auth | 로그인/회원가입/토큰 |
| users.py | /users | 회원 CRUD |
| companies.py | /companies | 사업장 CRUD + NTS 검증 |
| factories.py | /factories | 시설 CRUD |
| system_codes.py | /system-codes | 전역변수 (195카테/1,471코드) |
| legal_engine.py | /legal-engine | 법령 판정 v4.1.2 (396룰) |
| ksic_engine.py | /ksic-engine | KSIC 설비 판정 |
| factory_process_v3.py | /factory-process | 공정 관리 |
| process_management.py | /process-management | 공정 마스터 |
| building_register.py | /building-register | 건축물대장 |
| quotes.py | /quotes | 견적/설문 |
| report_forms.py | /report-forms | 신고서식 v2.0.0 |
| contracts.py | - | 계약 (⚠️ 503 오류) |
| contacts.py | - | 문의 |
| education.py | - | 법정교육 |
| notifications.py | - | 알림 |
| equipment_assets.py | /equipment-assets | 설비 자산 |
| schedule_engine.py | /schedule-engine | 점검 일정 |
| roles.py, teams.py | - | 권한/팀 |
| areas.py, buildings.py | - | 구역/건물 |
| inspection_sets.py | - | 점검 세트 |
| work_schedules.py | - | 작업 일정 |
| personnel.py | /personnel | 선임연결 |
| repair.py | /repair | 수선중개 |
| admin_stats.py | /admin/stats | 대시보드 통계 |
| engine_equipment.py | /engine-equipment | 설비엔진 (MV 기반) |
| inspection_checklist.py | /inspection | 점검 체크리스트 |

---

## DB 현황

| 테이블 | 건수 | 비고 |
|--------|------|------|
| form_templates | 11개 | 신고서식 |
| legal_obligations | 17개 | 오늘 신규 |
| obligation_form_mapping | 0개 | ⚠️ INSERT 미완료 |
| master_building_legal_rules | 396개 | |
| system_codes | 1,471개 | 195 카테고리 |

## Materialized View
| MV명 | 행수 | 용도 |
|------|------|------|
| engine_equipment_summary | 508행 | 설비엔진 목록/통계 |
| dashboard_stats | 1행 | 대시보드 통계 |

---

## 미완료 이슈

| 이슈 | 우선순위 | 세부 |
|------|---------|------|
| obligation_form_mapping 11건 INSERT | 🔴 | 다음 세션 즉시 |
| OSHACT-FORM-002 form_json UPDATE | 🔴 | 다음 세션 즉시 |
| contracts 503 오류 | 🔴 | Railway 런타임 로그 확인 |
| NTS API 실제 경로 확인 | 🔴 | /docs에서 /companies 엔드포인트 확인 |
| 로그인 2.5초 지연 | 🟡 | bcrypt + Supabase auth 이중 검증 |
| system_codes POST/PATCH/DELETE | 🟡 | 미구현 |
| weasyprint Railway 빌드 확인 | 🟡 | 실패 시 xhtml2pdf 교체 |
| 건축물도면 API | ⏸️ | blcm.go.kr 승인 대기 |

---

## 다음 세션 즉시 처리 순서
1. obligation_form_mapping 11건 INSERT (SQL: 작업지시서 2-2)
2. form_templates SET form_json WHERE form_code='OSHACT-FORM-002' (SQL: 작업지시서 2-3)
3. contracts 503 원인 파악
4. NTS API 경로 확인 → 프론트 창에 전달

---

## 이메일 스택 (확정)
```
Resend API (HTTP 방식)
포트: 무관
발신: noreply@taieng.co.kr
수신: tai@taieng.co.kr
RESEND_API_KEY: Railway 환경변수
```

## JUSO API
- URL: business.juso.go.kr
- Key: U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=
- firstSort 도로명/지번 자동 판별
- bdMgtSn 직접 반환

## 환경변수 (Railway)
```
SUPABASE_URL     = https://xntdkrjhgcscmqctdzyo.supabase.co
SUPABASE_KEY     = (Railway에만 저장)
LAW_API_OC       = taieng
JUSO_API_KEY     = U01TX0FVVEgyMDI2MDMxODEyMjUxNjExNzc1MTc=
BUILDING_API_KEY = da4e826323c2c9fef9f325bd4e39a3765d06ac1b582695bcbc475bc0a076255b
RESEND_API_KEY   = (Railway에만 저장)
```
