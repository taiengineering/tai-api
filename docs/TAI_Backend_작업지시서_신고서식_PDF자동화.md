# TAI Backend 작업지시서 — 신고서식 PDF 자동화

작성일: 2026-03-28  
레포: taiengineering/tai-api (main)  
담당: 백엔드 창 Claude

---

## ⚠️ 작업 원칙
- 브라우저 사용 금지
- 테스트: Supabase MCP 또는 터미널 Python만
- 매 단계 완료 후 확인 후 다음 단계 진행

---

## 1단계 — DB 테이블 생성 (Supabase apply_migration)

### 1-1. legal_obligations 테이블 신규

```sql
CREATE TABLE IF NOT EXISTS legal_obligations (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  category_code    VARCHAR(50) UNIQUE NOT NULL,  -- OSH_MGR_REPORT
  domain           VARCHAR(50),                  -- 산업안전보건
  obligation_name  VARCHAR(200),
  obligation_type  VARCHAR(30),                  -- NOTIFICATION / REPORT / PERMIT
  base_point       VARCHAR(200),                 -- 안전관리자 선임/변경/해임
  due_value        INTEGER,                      -- 14
  due_unit         VARCHAR(10),                  -- 일 / 개월
  due_condition    VARCHAR(20),                  -- 이내 / 이전
  target_authority VARCHAR(200),
  required_documents TEXT,
  legal_basis      VARCHAR(300),
  basis_level      VARCHAR(50),
  history_required VARCHAR(5),                   -- Y / N
  status           VARCHAR(50) DEFAULT 'ACTIVE_MASTER_DRAFT',
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

### 1-2. obligation_form_mapping 테이블 신규

```sql
CREATE TABLE IF NOT EXISTS obligation_form_mapping (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  obligation_code  VARCHAR(50) NOT NULL,  -- legal_obligations.category_code
  obligation_name  VARCHAR(200),
  form_code        VARCHAR(30),           -- form_templates.form_code
  form_name        VARCHAR(200),
  auto_generate    VARCHAR(5),            -- Y / N
  notes            TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(obligation_code, form_code)
);
```

---

## 2단계 — 데이터 적재

### 2-1. legal_obligations 11건 INSERT

```sql
INSERT INTO legal_obligations
  (category_code, domain, obligation_name, obligation_type, base_point, due_value, due_unit, due_condition, target_authority, required_documents, legal_basis, basis_level, history_required, status)
VALUES
('OSH_MGR_REPORT','산업안전보건','안전관리자 선임 등 보고','NOTIFICATION','안전관리자 선임/변경/해임',14,'일','이내','관할 지방고용노동관서의 장','안전관리자·보건관리자·산업보건의 선임 등 보고서(별지 제2호/제3호의2 서식); 자격증 사본; 경력/재직 증빙','산업안전보건법 시행규칙 제11조, 제23조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_HEALTH_REPORT','산업안전보건','보건관리자 선임 등 보고','NOTIFICATION','보건관리자 선임/변경/해임',14,'일','이내','관할 지방고용노동관서의 장','안전관리자·보건관리자·산업보건의 선임 등 보고서(별지 제2호/제3호의2 서식); 자격증 사본; 경력/재직 증빙','산업안전보건법 시행규칙 제11조, 제23조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_DOCTOR_REPORT','산업안전보건','산업보건의 선임 등 보고','NOTIFICATION','산업보건의 선임/위촉/해촉/변경',14,'일','이내','관할 지방고용노동관서의 장','안전관리자·보건관리자·산업보건의 선임 등 보고서(별지 제2호/제3호의2 서식); 면허·위촉 증빙','산업안전보건법 시행규칙 제11조, 제23조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_ACCIDENT_REPORT','산업안전보건','산업재해조사표 제출','REPORT','산업재해 발생',1,'개월','이내','관할 지방고용노동관서의 장','산업재해조사표(별지 제30호서식); 사고경위; 재해자 정보; 관련 사진/기록','산업안전보건법 시행규칙 제73조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_SERIOUS_REPORT','산업안전보건','중대재해 발생 보고','REPORT','중대재해 발생',1,'일','이내','관할 지방고용노동관서의 장; 고용노동부장관','중대재해 발생 보고서; 산업재해조사표','산업안전보건법 제54조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_CONTRACT_APPROVAL','산업안전보건','도급 승인 신청','PERMIT','유해·위험작업 도급 전',30,'일','이전','관할 지방고용노동관서의 장','유해·위험작업 도급승인 신청서(별지 제31호서식); 작업계획서; 안전보건조치 계획','산업안전보건법 제58조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_SELF_CERT','산업안전보건','자율안전확인 신고','NOTIFICATION','자율안전확인 대상 기계·기구 출하 전',NULL,'일','이전','한국산업안전보건공단','자율안전확인 신고서(별지 제48호서식); 시험성적서; 제원표','산업안전보건법 제89조','법령 기준','N','ACTIVE_MASTER_DRAFT'),
('OSH_SAFETY_INSPECT','산업안전보건','안전검사 신청','INSPECTION','안전검사 주기 도래',NULL,'일','이전','공단 또는 지정 검사기관','안전검사 신청서(별지 제50호서식)','산업안전보건법 제93조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_IMPROV_PLAN','산업안전보건','안전보건개선계획 수립·제출','PLAN','명령서 수령',30,'일','이내','관할 지방고용노동관서의 장','안전보건개선계획서(별지 제26호 관련 양식); 현황 진단 자료','산업안전보건법 제49조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_RISK_ASSESS','산업안전보건','위험성평가 실시·보존','RECORD','최초·정기 평가 실시',NULL,'년','보존','사내 보존(고용노동부 요청 시 제출)','위험성평가 결과표; 개선조치 이행기록','산업안전보건법 제36조','법령 기준','Y','ACTIVE_MASTER_DRAFT'),
('OSH_EDU_RECORD','산업안전보건','안전보건교육 실시·기록','RECORD','정기교육 실시 후',3,'년','보존','사내 보존','안전보건교육 실시 일지; 참석자 명단; 교육내용 증빙','산업안전보건법 시행규칙 제28조','법령 기준','Y','ACTIVE_MASTER_DRAFT')
ON CONFLICT (category_code) DO NOTHING;
```

### 2-2. obligation_form_mapping 11건 INSERT

```sql
INSERT INTO obligation_form_mapping
  (obligation_code, obligation_name, form_code, form_name, auto_generate, notes)
VALUES
('OSH_MGR_REPORT','안전관리자 선임 등 보고','OSHACT-FORM-002','안전관리자·보건관리자 선임 보고서','Y','핵심 필수 서식'),
('OSH_HEALTH_REPORT','보건관리자 선임 등 보고','OSHACT-FORM-002','안전관리자·보건관리자 선임 보고서','Y','동일 서식 사용'),
('OSH_DOCTOR_REPORT','산업보건의 선임 등 보고','OSHACT-FORM-002','안전관리자·보건관리자 선임 보고서','Y','동일 서식 사용'),
('OSH_ACCIDENT_REPORT','산업재해조사표 제출','OSHACT-FORM-030','산업재해조사표','Y','사고 발생 시 자동 생성'),
('OSH_SERIOUS_REPORT','중대재해 발생 보고','OSHACT-FORM-030','산업재해조사표','Y','즉시 보고용'),
('OSH_CONTRACT_APPROVAL','도급 승인 신청','OSHACT-FORM-031','도급승인 신청서','Y','사전 승인 필수'),
('OSH_SELF_CERT','자율안전확인 신고','OSHACT-FORM-048','자율안전확인 신고서','N','별도 신고서 사용'),
('OSH_SAFETY_INSPECT','안전검사 신청','OSHACT-FORM-050','안전검사 신청서','N','기간별 신청'),
('OSH_IMPROV_PLAN','안전보건개선계획 수립·제출','OSHACT-FORM-026','안전보건개선계획서','N','명령서 수령 후 작성'),
('OSH_MGR_REPORT','안전관리자 선임 등 보고','OSHACT-FORM-003-2','선임변경 보고서','Y','변경/해임 시 추가 서식'),
('OSH_HEALTH_REPORT','보건관리자 선임 등 보고','OSHACT-FORM-003-2','선임변경 보고서','Y','변경/해임 시 추가 서식')
ON CONFLICT (obligation_code, form_code) DO NOTHING;
```

### 2-3. OSHACT-FORM-002 form_json UPDATE

```sql
UPDATE form_templates
SET form_json = '{
  "form_code": "OSHACT-FORM-002",
  "form_no": "별지 제2호서식",
  "form_name": "안전관리자·보건관리자·산업보건의 선임 등 보고서",
  "bylSeq": "17853655",
  "submit_to": "관할 지방고용노동관서의 장",
  "submit_timing": "선임·위촉 또는 해임·해촉 후 14일 이내",
  "trigger_event": "안전관리자 선임 시",
  "page_count": 1,
  "sections": [
    {
      "section_id": "S1",
      "section_title": "사업체",
      "rows": [
        {"cells": [
          {"label": "사업장명", "field_id": "company_name", "input_type": "text", "colspan": 1, "required": true, "auto_fill": "factories.name"},
          {"label": "업종 또는 주요생산품명", "field_id": "industry", "input_type": "text", "colspan": 1, "required": true, "auto_fill": "factories.industry"},
          {"label": "소재지", "field_id": "company_address", "input_type": "address", "colspan": 2, "required": true, "auto_fill": "factories.address"}
        ]},
        {"cells": [
          {"label": "사업자등록번호", "field_id": "business_number", "input_type": "text", "colspan": 1, "required": true, "auto_fill": "companies.business_number"},
          {"label": "근로자 수 총", "field_id": "worker_total", "input_type": "number", "colspan": 1, "required": true, "auto_fill": "factories.worker_count"},
          {"label": "남", "field_id": "worker_male", "input_type": "number", "colspan": 1},
          {"label": "여", "field_id": "worker_female", "input_type": "number", "colspan": 1}
        ]},
        {"cells": [
          {"label": "전화번호", "field_id": "company_phone", "input_type": "phone", "colspan": 4, "auto_fill": "factories.phone"}
        ]}
      ]
    },
    {
      "section_id": "S2",
      "section_title": "안전관리자 (안전관리전문기관)",
      "rows": [
        {"cells": [
          {"label": "성명", "field_id": "safety_name", "input_type": "text", "colspan": 1},
          {"label": "생년월일", "field_id": "safety_birth", "input_type": "date", "colspan": 1},
          {"label": "기관명", "field_id": "safety_org", "input_type": "text", "colspan": 1},
          {"label": "전자우편 주소", "field_id": "safety_email", "input_type": "email", "colspan": 1}
        ]},
        {"cells": [
          {"label": "전화번호", "field_id": "safety_phone", "input_type": "phone", "colspan": 1},
          {"label": "자격/면허번호", "field_id": "safety_license", "input_type": "text", "colspan": 1},
          {"label": "선임 등 연월일", "field_id": "safety_assign_date", "input_type": "date", "colspan": 1},
          {"label": "전담·겸임 구분", "field_id": "safety_type", "input_type": "select", "options": ["전담", "겸임"], "colspan": 1}
        ]}
      ]
    },
    {
      "section_id": "S3",
      "section_title": "보건관리자 (보건관리전문기관)",
      "rows": [
        {"cells": [
          {"label": "성명", "field_id": "health_name", "input_type": "text", "colspan": 1},
          {"label": "생년월일", "field_id": "health_birth", "input_type": "date", "colspan": 1},
          {"label": "기관명", "field_id": "health_org", "input_type": "text", "colspan": 1},
          {"label": "전자우편 주소", "field_id": "health_email", "input_type": "email", "colspan": 1}
        ]},
        {"cells": [
          {"label": "전화번호", "field_id": "health_phone", "input_type": "phone", "colspan": 1},
          {"label": "자격/면허번호", "field_id": "health_license", "input_type": "text", "colspan": 1},
          {"label": "선임 등 연월일", "field_id": "health_assign_date", "input_type": "date", "colspan": 1},
          {"label": "전담·겸임 구분", "field_id": "health_type", "input_type": "select", "options": ["전담", "겸임"], "colspan": 1}
        ]}
      ]
    },
    {
      "section_id": "S4",
      "section_title": "산업보건의",
      "rows": [
        {"cells": [
          {"label": "성명", "field_id": "doctor_name", "input_type": "text", "colspan": 1},
          {"label": "생년월일", "field_id": "doctor_birth", "input_type": "date", "colspan": 1},
          {"label": "기관명", "field_id": "doctor_org", "input_type": "text", "colspan": 1},
          {"label": "전자우편 주소", "field_id": "doctor_email", "input_type": "email", "colspan": 1}
        ]},
        {"cells": [
          {"label": "전화번호", "field_id": "doctor_phone", "input_type": "phone", "colspan": 1},
          {"label": "자격/면허번호", "field_id": "doctor_license", "input_type": "text", "colspan": 1},
          {"label": "선임 등 연월일", "field_id": "doctor_assign_date", "input_type": "date", "colspan": 1},
          {"label": "전담·겸임 구분", "field_id": "doctor_type", "input_type": "select", "options": ["전담", "겸임"], "colspan": 1}
        ]}
      ]
    },
    {
      "section_id": "S5",
      "section_title": "제출 정보",
      "rows": [
        {"cells": [
          {"label": "제출일", "field_id": "submit_date", "input_type": "date", "colspan": 2, "required": true},
          {"label": "보고인(사업주 또는 대표자)", "field_id": "reporter_name", "input_type": "text", "colspan": 1, "required": true, "auto_fill": "companies.representative_name"},
          {"label": "서명 또는 인", "field_id": "signature", "input_type": "signature", "colspan": 1}
        ]}
      ]
    }
  ],
  "attachments": [
    {"no": 1, "name": "해당 자격·면허증 사본", "required": "COND", "condition": "자격·면허 보유자인 경우"},
    {"no": 2, "name": "재직증명서", "required": "Y"}
  ],
  "auto_fill_fields": ["company_name", "company_address", "business_number", "worker_total", "company_phone", "reporter_name"]
}'
WHERE form_code = 'OSHACT-FORM-002';
```

---

## 3단계 — PDF API 구현

### 3-1. requirements.txt에 weasyprint 추가

```
weasyprint
```

> ⚠️ Railway 배포 환경에서 weasyprint는 OS 레벨 의존성(pango, cairo 등)이 필요합니다.
> 만약 Railway에서 빌드 오류 발생 시 `xhtml2pdf` 또는 `pdfkit`(wkhtmltopdf)으로 대체 가능.
> 대체 순서: weasyprint → xhtml2pdf → pdfkit

### 3-2. HTML 템플릿 저장

파일 위치: `templates/forms/OSHACT_FORM_002.html`
(이미 tai-api 레포에 커밋됨 — `templates/forms/OSHACT_FORM_002.html` 참조)

### 3-3. PDF API 엔드포인트 추가 (report_forms.py에 추가)

```python
# requirements: pip install weasyprint jinja2
# report_forms.py 하단에 추가

from fastapi.responses import StreamingResponse, JSONResponse
from fastapi import Body
import io

def _render_html_template(template_path: str, form_data: dict) -> str:
    """Jinja2 없이 간단한 {{ key }} 치환으로 HTML 렌더링"""
    from pathlib import Path
    html = Path(template_path).read_text(encoding='utf-8')
    for k, v in form_data.items():
        html = html.replace('{{ ' + k + ' }}', str(v) if v is not None else '')
    # 미치환 변수 빈칸 처리
    import re
    html = re.sub(r'\{\{\s*\w+\s*\}\}', '', html)
    return html


@router.post("/submissions/preview-pdf")
def preview_pdf(body: dict = Body(...)):
    """
    즉시 PDF 스트림 반환 (저장 없음)
    body: { form_code, form_data: { ... } }
    """
    form_code = body.get('form_code', 'OSHACT-FORM-002')
    form_data = body.get('form_data', {})

    template_map = {
        'OSHACT-FORM-002': 'templates/forms/OSHACT_FORM_002.html',
    }
    template_path = template_map.get(form_code)
    if not template_path:
        raise HTTPException(status_code=404, detail=f'템플릿 없음: {form_code}')

    html_content = _render_html_template(template_path, form_data)

    try:
        from weasyprint import HTML as WeasyHTML
        pdf_bytes = WeasyHTML(string=html_content, base_url='.').write_pdf()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={'Content-Disposition': f'inline; filename="{form_code}_preview.pdf"'}
        )
    except ImportError:
        # weasyprint 미설치 시 HTML 반환
        return JSONResponse({'status': 'html_only', 'html': html_content[:500] + '...'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'PDF 생성 실패: {str(e)}')


@router.post("/submissions/{submission_id}/pdf")
def generate_and_save_pdf(submission_id: str):
    """
    저장된 서류의 PDF 생성 및 URL 저장
    1. form_submissions에서 form_data 조회
    2. HTML 렌더링 → PDF 생성
    3. Supabase Storage 저장 (또는 로컬 임시)
    4. pdf_url을 form_submissions에 업데이트
    """
    supabase = get_supabase()

    # 서류 조회
    res = supabase.table('form_submissions').select(
        '*, form_templates(form_code, form_json)'
    ).eq('id', submission_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail='서류를 찾을 수 없습니다')

    sub = res.data
    form_code = sub.get('form_code', 'OSHACT-FORM-002')
    form_data = sub.get('form_data', {})

    template_map = {
        'OSHACT-FORM-002': 'templates/forms/OSHACT_FORM_002.html',
    }
    template_path = template_map.get(form_code)
    if not template_path:
        raise HTTPException(status_code=404, detail=f'템플릿 없음: {form_code}')

    html_content = _render_html_template(template_path, form_data)

    try:
        from weasyprint import HTML as WeasyHTML
        pdf_bytes = WeasyHTML(string=html_content, base_url='.').write_pdf()

        # TODO: Supabase Storage 업로드 후 URL 저장
        # 현재: 임시 스트림 반환 + pdf_url mock
        pdf_url = f'/tmp/{form_code}_{submission_id}.pdf'

        # pdf_url DB 저장
        supabase.table('form_submissions').update(
            {'pdf_url': pdf_url, 'updated_at': datetime.now().isoformat()}
        ).eq('id', submission_id).execute()

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{form_code}_{submission_id}.pdf"'}
        )
    except ImportError:
        raise HTTPException(status_code=501, detail='weasyprint 미설치 — pip install weasyprint')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'PDF 생성 실패: {str(e)}')
```

---

## 4단계 — 추가 엔드포인트

### 4-1. GET /report-forms/obligations — 의무 목록

```python
@router.get('/obligations')
def get_legal_obligations(
    domain:      Optional[str] = Query(None),
    oblig_type:  Optional[str] = Query(None, alias='type'),
    page:        int           = Query(1, ge=1),
    page_size:   int           = Query(50, ge=1, le=100),
):
    """법적 의무 목록 조회"""
    supabase = get_supabase()
    offset = (page - 1) * page_size

    q = supabase.table('legal_obligations').select('*', count='exact')
    if domain:
        q = q.eq('domain', domain)
    if oblig_type:
        q = q.eq('obligation_type', oblig_type)
    q = q.order('category_code').range(offset, offset + page_size - 1)
    res = q.execute()

    return {
        'status': 'success',
        'data': {'items': res.data or [], 'total': res.count or 0}
    }
```

### 4-2. GET /report-forms/obligations/by-factory/{factory_id} — 시설별 해당 의무

```python
@router.get('/obligations/by-factory/{factory_id}')
def get_obligations_by_factory(factory_id: str):
    """
    시설별 해당 법적 의무 목록
    - 법령 판정 결과(master_building_legal_rules) 기반으로
      해당 시설에 적용되는 obligation만 반환
    - obligation_form_mapping으로 관련 서식 함께 반환
    """
    supabase = get_supabase()

    # 시설 정보 조회
    fac_res = supabase.table('factories').select(
        'id, name, ksic_code, worker_count, site_type'
    ).eq('id', factory_id).single().execute()
    if not fac_res.data:
        raise HTTPException(status_code=404, detail='시설을 찾을 수 없습니다')

    # 현재는 전체 의무 반환 (추후 법령판정 결과 연동)
    oblig_res = supabase.table('legal_obligations').select(
        '*, obligation_form_mapping(form_code, form_name, auto_generate)'
    ).eq('status', 'ACTIVE_MASTER_DRAFT').execute()

    return {
        'status': 'success',
        'data': {
            'factory_id': factory_id,
            'factory_name': fac_res.data.get('name'),
            'obligations': oblig_res.data or [],
            'total': len(oblig_res.data or [])
        }
    }
```

---

## 완료 확인 방법

```bash
# 1. 테이블 생성 확인 (Supabase MCP)
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' AND table_name IN ('legal_obligations','obligation_form_mapping');

# 2. 데이터 확인
SELECT COUNT(*) FROM legal_obligations;          -- 11건
SELECT COUNT(*) FROM obligation_form_mapping;    -- 11건
SELECT form_json IS NOT NULL FROM form_templates WHERE form_code='OSHACT-FORM-002'; -- true

# 3. API 확인 (Railway 배포 후)
curl https://api.taieng.co.kr/report-forms/obligations
curl https://api.taieng.co.kr/report-forms/test
```

---

## Railway weasyprint 빌드 실패 시 대체 방안

```txt
# requirements.txt 수정 순서
1차: weasyprint
2차: xhtml2pdf  (weasyprint 실패 시)
3차: pdfkit     (xhtml2pdf도 실패 시, wkhtmltopdf 바이너리 필요)

# xhtml2pdf 대체 코드
from xhtml2pdf import pisa
import io
pdf_buffer = io.BytesIO()
pisa.CreatePDF(html_content, dest=pdf_buffer)
pdf_bytes = pdf_buffer.getvalue()
```
