# TAI 백엔드 작업지시서 — 신고서식 자동화 (PDF 다운로드까지)

> 작성일: 2026-03-28  
> 레포: taiengineering/tai-api  
> 담당: 백엔드 창

---

## 현황 요약

| 항목 | 상태 |
|------|------|
| `form_templates` 테이블 | ✅ 존재, 11개 적재, **form_json = NULL** |
| `report_events` 테이블 | ✅ 존재, 데이터 없음 |
| `form_submissions` 테이블 | ✅ 존재, 데이터 없음 |
| `legal_obligations` 테이블 | ❌ **없음** — 생성 필요 |
| `obligation_form_mapping` 테이블 | ❌ **없음** — 생성 필요 |
| OSHACT-FORM-002 HTML 템플릿 | ✅ GPT 파싱 완료 |
| PDF 생성 API | ❌ **없음** — 구현 필요 |

---

## 작업 순서

### STEP 1. 신규 테이블 생성 (단계적 실행)

```sql
-- 1-1. legal_obligations 테이블
CREATE TABLE legal_obligations (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  category_code    VARCHAR(50) UNIQUE NOT NULL,  -- OSH_MGR_REPORT 등
  domain           VARCHAR(50),                  -- 산업안전보건 / 전기 / 소방 등
  obligation_name  TEXT NOT NULL,
  obligation_type  VARCHAR(20),                  -- NOTIFICATION / REPORT / APPROVAL / INSPECTION
  base_point       TEXT,                         -- 신고 기준점
  due_value        INTEGER,                      -- 기한 숫자
  due_unit         VARCHAR(10),                  -- 일 / 개월
  due_condition    VARCHAR(50),                  -- 이내 / 사전 / 지체없이
  target_authority TEXT,                         -- 제출처
  required_documents TEXT,
  legal_basis      TEXT,                         -- 법령 근거
  basis_level      VARCHAR(50),
  history_required BOOLEAN DEFAULT false,
  status           VARCHAR(30) DEFAULT 'ACTIVE',
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 1-2. obligation_form_mapping 테이블
CREATE TABLE obligation_form_mapping (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  obligation_code  VARCHAR(50) NOT NULL,         -- legal_obligations.category_code 참조
  obligation_name  TEXT,
  form_code        VARCHAR(30),                  -- form_templates.form_code 참조
  form_name        TEXT,
  auto_generate    BOOLEAN DEFAULT false,        -- 자동 생성 가능 여부
  notes            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_legal_obligations_code ON legal_obligations(category_code);
CREATE INDEX idx_obligation_form_mapping_code ON obligation_form_mapping(obligation_code);
CREATE INDEX idx_obligation_form_mapping_form ON obligation_form_mapping(form_code);
```

---

### STEP 2. 데이터 적재

#### 2-1. legal_obligations 데이터 적재 (25건)

```sql
INSERT INTO legal_obligations (category_code, domain, obligation_name, obligation_type, base_point, due_value, due_unit, due_condition, target_authority, required_documents, legal_basis, basis_level, history_required, status) VALUES
('OSH_MGR_REPORT', '산업안전보건', '안전관리자 선임 등 보고', 'NOTIFICATION', '안전관리자 선임/변경/해임', 14, '일', '이내', '관할 지방고용노동관서의 장', '안전관리자·보건관리자·산업보건의 선임 등 보고서(별지 제2호/제3호의 2 서식); 자격증 사본; 경력/재직 증빙', '산업안전보건법 시행규칙 제11조, 제23조', '법령 기준', true, 'ACTIVE'),
('OSH_HEALTH_REPORT', '산업안전보건', '보건관리자 선임 등 보고', 'NOTIFICATION', '보건관리자 선임/변경/해임', 14, '일', '이내', '관할 지방고용노동관서의 장', '안전관리자·보건관리자·산업보건의 선임 등 보고서(별지 제2호/제3호의 2 서식); 자격증 사본', '산업안전보건법 시행규칙 제11조, 제23조', '법령 기준', true, 'ACTIVE'),
('OSH_ACCIDENT_REPORT', '산업안전보건', '산업재해조사표 제출', 'REPORT', '산업재해 발생', 1, '개월', '이내', '관할 지방고용노동관서의 장', '산업재해조사표(별지 제30호서식); 사고경위; 재해자 정보', '산업안전보건법 시행규칙 제73조', '법령 기준', true, 'ACTIVE'),
('OSH_SERIOUS_REPORT', '산업안전보건', '중대재해 발생 보고', 'REPORT', '중대재해 발생 사실 인지', 0, NULL, '지체 없이', '고용노동부장관(실무상 관할 지방고용노동관서)', '즉시 보고 내용; 사고개요; 피해현황', '산업안전보건법 제54조제2항', '법령 기준', true, 'ACTIVE'),
('OSH_CONTRACT_APPROVAL', '산업안전보건', '유해·위험작업 도급승인 신청', 'APPROVAL', '도급 작업 전', 0, NULL, '사전', '관할 지방고용노동관서의 장', '유해·위험작업 도급승인 신청서(별지 제31호서식); 작업계획서; 안전관리계획서', '산업안전보건법 제61조', '법령 기준', true, 'ACTIVE'),
('ELEC_MGR_APPOINT', '전기', '전기안전관리자 선임 신고', 'NOTIFICATION', '전기안전관리자 선임', 30, '일', '이내', '전력기술인단체(산업통상자원부장관 지정 단체)', '전기안전관리자 선임(해임) 신고서(별지 제16호서식); 자격증 사본; 재직/경력 증빙', '전기안전관리법 시행규칙 제34조', '법령 기준', true, 'ACTIVE'),
('ELEC_MGR_CHANGE', '전기', '전기안전관리자 선임신고사항 변경신고', 'NOTIFICATION', '회사명·대표자·설치장소·용량·전압 등 변경사유 발생', 30, '일', '이내', '전력기술인단체', '전기안전관리자 선임신고사항 변경신고서(별지 제20호서식); 변경 증빙서류', '전기안전관리법 시행규칙 제35조', '법령 기준', true, 'ACTIVE'),
('FIRE_MGR_REPORT', '소방', '소방안전관리자 선임 신고', 'NOTIFICATION', '소방안전관리자 선임', 14, '일', '이내', '소방본부장 또는 소방서장', '소방안전관리자 선임신고서(별지 제15호서식); 소방안전관리자 자격증; 감독직 증빙', '화재의 예방 및 안전관리에 관한 법률 시행규칙 별지 제15호서식, 제14조', '법령/공식 안내 기준', true, 'ACTIVE'),
('FIRE_SELFCHECK_REPORT', '소방', '소방시설등 자체점검 실시결과 보고', 'REPORT', '자체점검 종료', 7, '일', '이내', '소방본부장 또는 소방서장', '소방시설등 자체점검 실시결과 보고서; 소방시설등점검표', '소방시설 설치 및 관리에 관한 법률 제24조, 시행규칙 제23조·제25조 관련', '법령 기준', true, 'ACTIVE'),
('LPG_MGR_APPOINT', '가스(LPG)', 'LPG 안전관리자 선임', 'NOTIFICATION', '사업 시작 또는 사용 전', 0, NULL, '사전', '허가관청/등록관청/시장·군수·구청장', '안전관리자 선임·해임·퍼직 신고서(별지 제35호서식); 자격증 등', '액화석유가스의 안전관리 및 사업법 제34조, 시행규칙 제49조', '법령 기준', true, 'ACTIVE'),
('HPGAS_USE_REPORT', '가스(고압가스)', '특정고압가스 사용신고', 'NOTIFICATION', '특정고압가스 사용 전', 0, NULL, '사전', '시장·군수 또는 구청장', '특정고압가스사용신고서(별지 제33호서식)', '고압가스 안전관리법 제20조, 시행규칙 제46조', '법령 기준', true, 'ACTIVE');
```

#### 2-2. obligation_form_mapping 데이터 적재

```sql
INSERT INTO obligation_form_mapping (obligation_code, obligation_name, form_code, form_name, auto_generate, notes) VALUES
('OSH_MGR_REPORT', '안전관리자 선임 등 보고', 'OSHACT-FORM-002', '안전관리자·보건관리자 선임 보고서', true, '핵심 필수 서식'),
('OSH_HEALTH_REPORT', '보건관리자 선임 등 보고', 'OSHACT-FORM-002', '안전관리자·보건관리자 선임 보고서', true, '동일 서식 사용'),
('OSH_ACCIDENT_REPORT', '산업재해조사표 제출', 'OSHACT-FORM-030', '산업재해조사표', true, '사고 발생 시 자동 생성'),
('OSH_SERIOUS_REPORT', '중대재해 발생 보고', 'OSHACT-FORM-030', '산업재해조사표', true, '중대재해도 동일 서식 사용'),
('OSH_CONTRACT_APPROVAL', '도급승인 신청', 'OSHACT-FORM-031', '도급승인 신청서', true, '사전 승인 필수'),
('ELEC_MGR_APPOINT', '전기안전관리자 선임 신고', 'ELEC-FORM-001', '전기안전관리자 선임신고서', true, '전기협회 제출용'),
('ELEC_MGR_CHANGE', '전기안전관리자 변경 신고', 'ELEC-FORM-002', '전기안전관리자 변경신고서', true, '변경 시 자동 생성'),
('FIRE_MGR_REPORT', '소방안전관리자 선임 신고', 'FIRE-FORM-001', '소방안전관리자 선임신고서', true, '소방서 제출'),
('FIRE_SELFCHECK_REPORT', '소방 점검 결과 보고', 'FIRE-FORM-002', '소방시설 점검결과보고서', true, '점검 후 자동 생성'),
('LPG_MGR_APPOINT', 'LPG 안전관리자 선임', 'GAS-FORM-001', '가스 안전관리자 선임신고서', true, '가스안전공사 제출'),
('HPGAS_USE_REPORT', '고압가스 사용 신고', 'GAS-FORM-002', '고압가스 사용신고서', true, '사전 신고 필수');
```

---

### STEP 3. form_templates.form_json 적재

**OSHACT-FORM-002** (GPT 파싱 완료 — HTML 템플릿 + 필드 매핑 확정)

```sql
UPDATE form_templates
SET form_json = '{
  "form_code": "OSHACT-FORM-002",
  "form_name": "안전관리자·보건관리자·산업보건의 선임 등 보고서",
  "form_no": "별지 제2호서식",
  "law_basis": "산업안전보건법 시행규칙 제11조제1항, 제23조제1항",
  "submit_to": "관할 지방고용노동관서의 장",
  "submit_timing": "선임·위촉·해임·해촉·변경 등 날부터 14일 이내",
  "sections": [
    {
      "section_id": "company",
      "section_name": "사업체",
      "fields": [
        {"field_id": "company_name", "label": "사업장명", "type": "text", "required": true, "auto_fill": "factories.name"},
        {"field_id": "industry", "label": "업종 또는 주요생산품명", "type": "text", "required": true, "auto_fill": "factories.ksic_name"},
        {"field_id": "company_address", "label": "소재지", "type": "text", "required": true, "auto_fill": "factories.address", "colspan": 2},
        {"field_id": "business_number", "label": "사업자등록번호", "type": "text", "required": true, "auto_fill": "companies.business_number"},
        {"field_id": "worker_total", "label": "근로자 수 원단위", "type": "number", "required": true, "auto_fill": "factories.employee_count"},
        {"field_id": "worker_male", "label": "남", "type": "number", "required": false},
        {"field_id": "worker_female", "label": "여", "type": "number", "required": false},
        {"field_id": "company_phone", "label": "전화번호", "type": "tel", "required": false, "auto_fill": "companies.phone", "colspan": 4}
      ]
    },
    {
      "section_id": "safety_manager",
      "section_name": "안전관리자 (안전관리전문기관)",
      "fields": [
        {"field_id": "safety_name", "label": "성명", "type": "text", "required": false},
        {"field_id": "safety_birth", "label": "생년월일", "type": "date", "required": false},
        {"field_id": "safety_org", "label": "기관명", "type": "text", "required": false},
        {"field_id": "safety_email", "label": "전자우편 주소", "type": "email", "required": false},
        {"field_id": "safety_phone", "label": "전화번호", "type": "tel", "required": false},
        {"field_id": "safety_license", "label": "자격/면허번호", "type": "text", "required": false},
        {"field_id": "safety_assign_date", "label": "선임 등 연월일", "type": "date", "required": false},
        {"field_id": "safety_type", "label": "전담·겨임 구분", "type": "select", "options": ["전담", "겨임"], "required": false}
      ]
    },
    {
      "section_id": "health_manager",
      "section_name": "보건관리자 (보건관리전문기관)",
      "fields": [
        {"field_id": "health_name", "label": "성명", "type": "text", "required": false},
        {"field_id": "health_birth", "label": "생년월일", "type": "date", "required": false},
        {"field_id": "health_org", "label": "기관명", "type": "text", "required": false},
        {"field_id": "health_email", "label": "전자우편 주소", "type": "email", "required": false},
        {"field_id": "health_phone", "label": "전화번호", "type": "tel", "required": false},
        {"field_id": "health_license", "label": "자격/면허번호", "type": "text", "required": false},
        {"field_id": "health_assign_date", "label": "선임 등 연월일", "type": "date", "required": false},
        {"field_id": "health_type", "label": "전담·겨임 구분", "type": "select", "options": ["전담", "겨임"], "required": false}
      ]
    },
    {
      "section_id": "doctor",
      "section_name": "산업보건의",
      "fields": [
        {"field_id": "doctor_name", "label": "성명", "type": "text", "required": false},
        {"field_id": "doctor_birth", "label": "생년월일", "type": "date", "required": false},
        {"field_id": "doctor_org", "label": "기관명", "type": "text", "required": false},
        {"field_id": "doctor_email", "label": "전자우편 주소", "type": "email", "required": false},
        {"field_id": "doctor_phone", "label": "전화번호", "type": "tel", "required": false},
        {"field_id": "doctor_license", "label": "자격/면허번호", "type": "text", "required": false},
        {"field_id": "doctor_assign_date", "label": "선임 등 연월일", "type": "date", "required": false},
        {"field_id": "doctor_type", "label": "전담·겨임 구분", "type": "select", "options": ["전담", "겨임"], "required": false}
      ]
    },
    {
      "section_id": "submit",
      "section_name": "제출 정보",
      "fields": [
        {"field_id": "submit_date", "label": "제출일", "type": "date", "required": true, "auto_fill": "today"},
        {"field_id": "reporter_name", "label": "보고인(사업주 또는 대표자)", "type": "text", "required": true, "auto_fill": "companies.representative_name"},
        {"field_id": "signature_text", "label": "서명 또는 인", "type": "signature", "required": false}
      ]
    }
  ],
  "html_template_path": "templates/forms/OSHACT_FORM_002.html",
  "auto_fill_fields": [
    "company_name", "industry", "company_address",
    "business_number", "worker_total", "submit_date", "reporter_name"
  ]
}'
WHERE form_code = 'OSHACT-FORM-002';
```

---

### STEP 4. PDF 생성 API 구현

**파일:** `routers/report_forms.py` 업데이트 (v1.0.0 이미 존재)

**새로 추가할 엔드포인트:**

```python
# POST /report-forms/submissions/{submission_id}/pdf
# - form_submissions 레코드의 form_data(JSONB)를 가져와
# - form_templates.form_json의 html_template_path HTML 템플릿에 데이터 주입
# - WeasyPrint으로 PDF 생성
# - Supabase Storage 또는 /tmp 저장 후 다운로드 URL 반환

# GET /report-forms/submissions/{submission_id}/pdf
# - 기생성된 PDF URL로 리다이렉트 또는 직접 스트림

# POST /report-forms/submissions/preview-pdf
# - body: {form_code, form_data}
# - 저장 없이 즉시 PDF 스트림 (Content-Type: application/pdf)
```

**WeasyPrint 설치:**
```bash
pip install weasyprint --break-system-packages
```

**HTML 템플릿 저장 위치:** `routers/templates/forms/OSHACT_FORM_002.html`

(oshact_form_002_html_pdf_bundle.md 의 HTML 템플릿 사용)

---

### STEP 5. legal_obligations 추가 API 엔드포인트

`routers/report_forms.py`에 아래 엔드포인트 추가:

```python
GET /report-forms/obligations              # 전체 의무 목록
GET /report-forms/obligations/{code}       # 의무 상세 + 파싱된 서식 연결
GET /report-forms/obligations/by-factory/{factory_id}  # 시설별 헤당 의무 목록
```

---

## 완료 체크리스트

```
□ STEP 1: legal_obligations 테이블 Supabase apply_migration
□ STEP 1: obligation_form_mapping 테이블 Supabase apply_migration
□ STEP 2: legal_obligations 데이터 적재 (11건)
□ STEP 2: obligation_form_mapping 데이터 적재 (11건)
□ STEP 3: OSHACT-FORM-002 form_json UPDATE
□ STEP 4: WeasyPrint pip install (Railway requirements.txt 추가)
□ STEP 4: HTML 템플릿 파일 저장 (templates/forms/OSHACT_FORM_002.html)
□ STEP 4: POST /report-forms/submissions/{id}/pdf 구현
□ STEP 4: POST /report-forms/submissions/preview-pdf 구현
□ STEP 5: GET /report-forms/obligations 엔드포인트 추가
□ Railway 배포 확인
```

---

## 전체 흐름 (완성 후)

```
법령진단 루려 발생
  ↓
legal_obligations + master_building_legal_rules 연결
  ↓
report_events 생성 (신고 기한 자동 계산)
  ↓
tadmin 대시보드 D-day 카드 표시
  ↓
[서류 작성] 버튼 콴릭
  ↓
HTML 입력폼 자동채움 (factories + companies 데이터)
  ↓
form_submissions 저장
  ↓
PDF 생성 (WeasyPrint)
  ↓
다운로드 제공 ←━━ ★ 최종 목표
```
