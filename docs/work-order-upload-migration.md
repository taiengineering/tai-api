# 파일 업로드 마이그레이션 작업지시서

**작성일**: 2026-04-25
**목적**: 기존 파일 업로드 코드를 통합 문서 시스템(tai-document.js + document_svc.py)으로 전환
**참조**: `docs/DOCUMENT_UPLOAD_REFERENCE.md`

---

## 현재 파일 업로드 위치 전체 스캔 결과

### taieng (new.taieng.co.kr) — 0건
마케팅 사이트에 파일 업로드 없음. 수정 불필요.

---

### tai-admin 프론트엔드 — 7개 파일

| # | 파일 | 사이트 | 현재 업로드 방식 | 카테고리 | 수정 방향 |
|---|---|---|---|---|---|
| F1 | `tadmin/full-version/app/inspect.html` | PWA app | `FormData` → `_utils.js` → 직접 API | inspection | `TaiImageCompress` + `TaiDocument.upload()` |
| F2 | `tadmin/full-version/app/construction_inspect.html` | PWA app | `FormData` → `_utils.js` → 직접 API | inspection | `TaiImageCompress` + `TaiDocument.upload()` |
| F3 | `tadmin/full-version/app/_utils.js` | PWA app | FormData 유틸 함수 | (공통) | `TaiDocument` 내부 호출로 대체 |
| F4 | `tadmin/full-version/html/horizontal-menu-template/my-company.html` | safe | 회사 로고/문서 업로드 | certificate, general | `TaiDocument.createUploadZone()` |
| F5 | `tadmin/full-version/html/horizontal-menu-template/worker-list.html` | safe | 작업자 사진/자격증 업로드 | certificate | `TaiDocument.upload()` |
| F6 | `tadmin/full-version/html/horizontal-menu-template/construction-inspection-list.html` | safe | 건설 점검 사진 | inspection | `TaiDocument.createAttachmentWidget()` |
| F7 | `tadmin/full-version/assets/js/tai/pages/education-list.page.js` | safe | 교육 자료 업로드 | education | `TaiDocument.createUploadZone()` |

**메일 관련 (수정 불필요 — 별도 시스템):**
- `admin/*/mail.page.js`, `mail.page.v2.js` — 메일 첨부파일은 `mail-attachments` 버킷 유지. 고객 문서가 아닌 내부 시스템이므로 통합 대상 아님.

---

### tai-api 백엔드 — 4개 파일

| # | 파일 | 현재 방식 | 수정 방향 |
|---|---|---|---|
| B1 | `services/upload_service.py` | 구 업로드 서비스 (개별 버킷 직접 접근) | `document_svc.py`로 대체. 기존 코드 deprecated 처리 |
| B2 | `routers/contacts.py` | 문의 첨부파일 → Supabase 직접 업로드 | `document_svc.upload_document()` 호출로 변경 |
| B3 | `routers/education.py` | 교육 자료 → `education_files` 테이블 + Supabase 직접 | `document_svc.upload_document(category='education')` |
| B4 | `routers/mail.py` | 메일 첨부 → `mail-attachments` 버킷 | **유지** (내부 시스템, 통합 대상 아님) |

---

## 수정 상세

### F1. inspect.html (PWA 점검)

**현재:**
```javascript
// _utils.js의 submitInspection() 내부
const fd = new FormData();
fd.append('photo', fileInput.files[0]);
await fetch(`${API}/inspections/${id}/photo`, { method: 'POST', body: fd });
```

**변경 후:**
```html
<script src="tai-image-compress.js"></script>
<script src="tai-document.js"></script>
<script>
// 이상 발견 시 사진 첨부 영역
const docMgr = new TaiDocument({
  apiBase: API_BASE,
  companyId: user.company_id,
  factoryId: currentFactory.id
});

// 기존 file input change 이벤트를 교체
document.getElementById('anomaly-photo').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  await docMgr.upload(file, {
    category: 'inspection',
    linkedTable: 'inspections',
    linkedId: currentInspectionId,
    uploadedBy: user.id
  });
});
</script>
```

**핵심**: `TaiImageCompress`가 로드되어 있으면 `upload()` 내부에서 자동 압축. 별도 코드 불필요.

---

### F2. construction_inspect.html (건설 점검)
F1과 동일 패턴. `category: 'inspection'`.

---

### F3. _utils.js (PWA 공통 유틸)
기존 FormData 업로드 함수를 `TaiDocument` 래퍼로 교체. 호출부(F1, F2)가 변경되면 자연스럽게 사용되지 않음.

---

### F4. my-company.html (업체 정보)

**현재:** 로고/사업자등록증 등 개별 `<input type="file">` + 직접 API 호출

**변경 후:**
```html
<script src="/assets/js/tai/tai-image-compress.js"></script>
<script src="/assets/js/tai/tai-document.js"></script>
<script>
const docMgr = new TaiDocument({ apiBase: API_BASE, companyId });

// 사업자등록증 업로드 영역
docMgr.createUploadZone('biz-cert-upload', {
  category: 'certificate',
  accept: '.pdf,.jpg,.png',
  maxFiles: 1,
  linkedTable: 'companies',
  linkedId: companyId,
  tags: ['사업자등록증']
});

// 회사 로고 업로드 영역
docMgr.createUploadZone('logo-upload', {
  category: 'general',
  accept: 'image/*',
  maxFiles: 1,
  linkedTable: 'companies',
  linkedId: companyId,
  tags: ['로고']
});
</script>
```

---

### F5. worker-list.html (작업자 등록)

**변경 후:**
```javascript
// 작업자 자격증 사진 업로드
docMgr.createAttachmentWidget('worker-cert', 'workers', workerId, {
  category: 'certificate',
  accept: 'image/*,.pdf',
  tags: ['자격증']
});
```

---

### F6. construction-inspection-list.html (건설 점검 목록)

**변경 후:**
```javascript
// 점검 상세 모달에서 사진 첨부
docMgr.createAttachmentWidget('inspection-photos', 'inspections', inspectionId, {
  category: 'inspection',
  accept: 'image/*',
  capture: 'environment'
});
```

---

### F7. education-list.page.js (교육 관리)

**현재:** `education_files` 테이블 + 직접 Storage 업로드

**변경 후:**
```javascript
docMgr.createUploadZone('edu-material-upload', {
  category: 'education',
  accept: '.pdf,.pptx,.docx,.hwp',
  multiple: true,
  linkedTable: 'education_records',
  linkedId: recordId
});
```

---

### B1. services/upload_service.py (백엔드)

**현재:** 개별 버킷 직접 접근하는 업로드 함수들

**변경:**
```python
# 파일 상단에 deprecated 표시 + 신규 서비스 리다이렉트
"""
⚠️ DEPRECATED — document_svc.py 사용
이 파일의 함수들은 하위호환을 위해 유지하지만,
신규 코드에서는 services.document_svc를 사용하세요.
"""
from services.document_svc import upload_document, register_generated

# 기존 함수는 document_svc 래퍼로 변경
async def upload_file(file_bytes, filename, bucket, ...):
    return await upload_document(
        file_bytes=file_bytes,
        file_name=filename,
        mime_type=...,
        company_id=...,
        category=_bucket_to_category(bucket),
        ...
    )
```

---

### B2. routers/contacts.py

**현재:** `FormData` → Supabase Storage 직접

**변경:**
```python
from services.document_svc import upload_document

# 기존 upload 엔드포인트 내부
result = await upload_document(
    file_bytes=await file.read(),
    file_name=file.filename,
    mime_type=file.content_type,
    company_id=company_id,
    category='general',
    linked_table='contacts',
    linked_id=contact_id
)
```

---

### B3. routers/education.py

**현재:** `education_files` 테이블 + Storage 직접

**변경:**
```python
from services.document_svc import upload_document

# education_files INSERT 대신
result = await upload_document(
    file_bytes=await file.read(),
    file_name=file.filename,
    mime_type=file.content_type,
    company_id=company_id,
    category='education',
    linked_table='education_records',
    linked_id=record_id,
    uploaded_by=user_id
)
```

---

## 작업 순서 (의존성 기준)

```
1단계: 백엔드 (tai-api, dev)
  B1 → upload_service.py deprecated + 래퍼 변환
  B2 → contacts.py 수정
  B3 → education.py 수정
  → dev 테스트 → main 머지

2단계: PWA 앱 (tai-admin, main)
  F3 → _utils.js 수정
  F1 → inspect.html 수정
  F2 → construction_inspect.html 수정

3단계: SaaS 페이지 (tai-admin, main)
  F4 → my-company.html
  F5 → worker-list.html
  F6 → construction-inspection-list.html
  F7 → education-list.page.js
```

## 공통 스크립트 로드 (모든 safe/admin HTML)

모든 수정 대상 HTML 파일에 추가:
```html
<!-- tai-document 모듈 (순서 중요) -->
<script src="/assets/js/tai/tai-image-compress.js"></script>
<script src="/assets/js/tai/tai-document.js"></script>
```

PWA app 파일은 상대 경로:
```html
<script src="tai-image-compress.js"></script>
<script src="tai-document.js"></script>
```

---

## 수정 불필요 (유지)

| 파일 | 이유 |
|---|---|
| `mail.page.js` / `mail.page.v2.js` | 내부 메일 시스템 — `mail-attachments` 버킷 유지 |
| `form-originals` / `form-templates` / `form-outputs` 버킷 | 서식 시스템 — 별도 유지 |
| `site-assets` / `diagrams` / `app` 버킷 | 시스템 자산 — 별도 유지 |

---

## 검증 체크리스트

- [ ] B1~B3 백엔드 수정 후 `/documents/upload` 테스트
- [ ] F1 inspect.html — 이상 사진 촬영 → 압축 → 업로드 → documents 테이블 확인
- [ ] F2 construction_inspect.html — 동일 테스트
- [ ] F4 my-company.html — 사업자등록증 업로드 테스트
- [ ] F5 worker-list.html — 자격증 업로드 테스트
- [ ] F6 construction-inspection-list.html — 점검 사진 테스트
- [ ] F7 education-list.page.js — 교육 자료 업로드 테스트
- [ ] 기존 `attachments` / `company_files` / `education_files` 테이블 접근 코드 없는지 확인
- [ ] 기존 개별 버킷 (inspection-images, facility-drawings 등) 직접 접근 코드 없는지 확인
