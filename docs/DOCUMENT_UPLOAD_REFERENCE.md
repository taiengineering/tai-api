# TAI Safe 문서·사진 업로드 통합 레퍼런스

**v1.0.0 | 2026-04-25**
**이 문서는 백엔드창·프론트창·기획창 모두에서 참조하는 단일 소스입니다.**

---

## 1. 아키텍처 한눈에 보기

```
┌─────────────────────────────────────────────────────────────┐
│  프론트엔드 (safe / admin / PWA app)                         │
│                                                              │
│  tai-image-compress.js ──→ 이미지 자동 압축 (8MB→300KB)       │
│         ↓                                                    │
│  tai-document.js ──→ 업로드/조회/다운로드/삭제 API 클라이언트    │
│         ↓                                                    │
│  POST /documents/upload (multipart/form-data)                │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌──────────────────────────┴──────────────────────────────────┐
│  백엔드 (tai-api)                                            │
│                                                              │
│  routers/documents.py ──→ HTTP 엔드포인트 10개                │
│         ↓                                                    │
│  services/document_svc.py ──→ 비즈니스 로직 (Router와 분리)    │
│         ↓                                                    │
│  ┌─────────────────┐   ┌──────────────────────────────┐     │
│  │ Supabase Storage │   │ Supabase DB                  │     │
│  │ 버킷: company-docs│   │ 테이블: documents (33컬럼)    │     │
│  │ (private, RLS)   │   │ RLS: company_id 기반 격리     │     │
│  └─────────────────┘   └──────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 파일 위치

| 파일 | 레포 | 브랜치 | 용도 |
|---|---|---|---|
| `services/document_svc.py` | tai-api | dev | 문서 서비스 (비즈니스 로직) |
| `routers/documents.py` | tai-api | dev | REST API 엔드포인트 |
| `tadmin/full-version/assets/js/tai/tai-document.js` | tai-admin | main | 프론트 문서 모듈 |
| `tadmin/full-version/assets/js/tai/tai-image-compress.js` | tai-admin | main | 이미지 압축 모듈 |

---

## 3. Storage 경로 규칙

```
company-docs/{company_id}/{category}/{YYYY-MM}/{uuid}.{ext}
```

예시:
```
company-docs/a1b2c3d4-.../inspection/2026-04/f5e6d7c8-....webp   ← 점검 사진
company-docs/a1b2c3d4-.../certificate/2026-04/g9h0i1j2-....pdf   ← 인증서
company-docs/a1b2c3d4-.../report/2026-04/k3l4m5n6-....pdf        ← 자동생성 보고서
```

---

## 4. 카테고리 (doc_category ENUM)

| 값 | 용도 | 이미지 압축 | 보존 연한 |
|---|---|---|---|
| `inspection` | 점검 사진/기록 | ✅ 1920px WebP 80% | 3년 |
| `corrective` | 시정조치 증빙 (전/후) | ✅ 1920px WebP 80% | 3년 |
| `tbm` | TBM 기록/서명 | ✅ 1280px WebP 75% | 3년 |
| `certificate` | 인증서, 면허, 자격증 | ✅ 2560px WebP 85% | 갱신 시까지 |
| `education` | 교육자료, 수료증 | ✅ 1920px WebP 80% | 3년 |
| `safety_plan` | 안전보건관리계획서 | ❌ 문서 원본 | 5년 |
| `risk_assessment` | 위험성평가서 | ❌ 문서 원본 | 3년 |
| `msds` | 물질안전보건자료 | ❌ 문서 원본 | 상시 |
| `report` | 보고서 (자동생성 포함) | ❌ 문서 원본 | 3년 |
| `contract` | 계약서 | ❌ 문서 원본 | 5년 |
| `equipment` | 설비 관련 문서 | ✅ 1920px WebP 80% | 설비 폐기 시까지 |
| `facility_drawing` | 시설 도면 | ❌ **원본 보존 필수** | 건물 존속 시까지 |
| `general` | 기타 | ✅ 1920px WebP 80% | 1년 |

---

## 5. 백엔드 API 레퍼런스

### 5.1 업로드

```
POST /documents/upload
Content-Type: multipart/form-data

필수: file, company_id
선택: category, factory_id, linked_table, linked_id, title, description, tags, uploaded_by
```

```python
# 다른 라우터에서 서비스 직접 호출 (PDF 자동 등록 등)
from services.document_svc import upload_document, register_generated

# 사용자 업로드
result = await upload_document(
    file_bytes=file_bytes,
    file_name="점검사진.jpg",
    mime_type="image/jpeg",
    company_id=company_id,
    category="inspection",
    factory_id=factory_id,
    linked_table="inspections",
    linked_id=inspection_id,
    uploaded_by=user_id
)

# 자동생성 PDF 등록
result = await register_generated(
    file_bytes=pdf_bytes,
    file_name="진단보고서_대성정밀_2026-04.pdf",
    mime_type="application/pdf",
    company_id=company_id,
    category="report",
    generated_by="diagnosis_report",
    generation_params={"token": public_token, "tier": "PAID2"}
)
```

### 5.2 다중 업로드

```
POST /documents/upload-multiple
Content-Type: multipart/form-data

필수: files (다중), company_id
선택: category, factory_id, linked_table, linked_id, uploaded_by
```

### 5.3 목록 조회

```
GET /documents?company_id={uuid}
  &category=inspection        (선택)
  &factory_id={uuid}          (선택)
  &linked_table=inspections   (선택)
  &linked_id={uuid}           (선택)
  &search=키워드               (선택, title/file_name/description 검색)
  &tags=태그1,태그2            (선택)
  &page=1&per_page=20         (페이징)

응답: { status, items: [...], total, page, per_page, total_pages }
```

### 5.4 특정 엔티티의 첨부파일

```
GET /documents/by-entity/{table}/{record_id}

예: GET /documents/by-entity/inspections/abc-123-def
    GET /documents/by-entity/corrective_actions/xyz-456
    GET /documents/by-entity/education_records/uvw-789
```

### 5.5 다운로드 (Signed URL)

```
GET /documents/{doc_id}/download

응답: { status: "success", url: "https://...signed-url...&token=..." }
```

### 5.6 상세/수정/삭제

```
GET    /documents/{doc_id}              ← 상세
PATCH  /documents/{doc_id}              ← 수정 (title, description, tags, category)
DELETE /documents/{doc_id}              ← soft delete (is_active=false, deleted_at 설정)
```

### 5.7 통계/보존기한

```
GET /documents/stats?company_id={uuid}
GET /documents/expiring?company_id={uuid}&days=90
```

---

## 6. 프론트엔드 사용법

### 6.1 스크립트 로드 (순서 중요)

```html
<script src="/assets/js/tai/tai-image-compress.js"></script>
<script src="/assets/js/tai/tai-document.js"></script>
```

### 6.2 초기화

```javascript
const docMgr = new TaiDocument({
  apiBase: 'https://api.taieng.co.kr',
  companyId: currentUser.company_id,
  factoryId: currentFactory?.id,   // 선택
  token: authToken                 // 선택 (인증 필요 시)
});
```

### 6.3 시나리오별 사용법

#### A. 점검 화면 — 이상 발견 시 사진 첨부

```javascript
docMgr.createAttachmentWidget('photo-area', 'inspections', inspectionId, {
  category: 'inspection',
  accept: 'image/*',
  capture: 'environment',  // 모바일 후면 카메라
  maxFiles: 5,
  onComplete: () => console.log('업로드 완료')
});
```
→ 드래그앤드롭 영역 + 파일 목록이 `#photo-area`에 자동 생성됨
→ 이미지는 **자동 압축** (8MB → 300KB)

#### B. 시정조치 — 전/후 사진

```javascript
// 전 사진
docMgr.createAttachmentWidget('before-photo', 'corrective_actions', actionId, {
  category: 'corrective',
  accept: 'image/*',
  tags: ['before']
});

// 후 사진
docMgr.createAttachmentWidget('after-photo', 'corrective_actions', actionId, {
  category: 'corrective',
  accept: 'image/*',
  tags: ['after']
});
```

#### C. 교육 관리 — 자료 업로드

```javascript
docMgr.createUploadZone('edu-upload', {
  category: 'education',
  accept: '.pdf,.pptx,.docx,.hwp',
  multiple: true,
  maxSize: 30 * 1024 * 1024  // 30MB
});
```

#### D. 문서함 — 전체 목록

```javascript
const result = await docMgr.list({
  category: 'certificate',  // 선택
  search: '소방',            // 선택
  page: 1,
  perPage: 20
});
// result.items = [{id, file_name, category, file_size, uploaded_at, ...}, ...]
```

#### E. 다운로드

```javascript
// 브라우저 다운로드 트리거
await docMgr.download(docId);

// signed URL만 가져오기
const url = await docMgr.getDownloadUrl(docId);
```

#### F. 코드에서 직접 업로드 (위젯 없이)

```javascript
const fileInput = document.getElementById('my-file-input');
const file = fileInput.files[0];

const result = await docMgr.upload(file, {
  category: 'certificate',
  title: '소방안전관리자 선임 증명서',
  linkedTable: 'factories',
  linkedId: factoryId,
  tags: ['소방', '선임']
});
// result.data = { id, storage_path, file_name, ... }
```

#### G. 압축 비활성화 (도면 등)

```javascript
await docMgr.upload(file, {
  category: 'facility_drawing',
  autoCompress: false  // 원본 그대로 업로드
});
```

---

## 7. 이미지 압축 모듈 단독 사용

`tai-document.js` 없이 `tai-image-compress.js`만 로드해도 동작합니다.

```html
<script src="tai-image-compress.js"></script>
```

```javascript
// 단일 파일 압축
const compressed = await TaiImageCompress.compress(file, { category: 'inspection' });

// 다중 파일 압축
const results = await TaiImageCompress.compressMultiple(files, { category: 'corrective' });

// 압축 결과 확인
const summary = TaiImageCompress.getSummary(originalFile, compressed);
console.log(`${summary.originalKB}KB → ${summary.compressedKB}KB (${summary.savedPercent}% 절감)`);

// 커스텀 설정
const custom = await TaiImageCompress.compress(file, {
  maxWidth: 800,
  maxHeight: 800,
  quality: 0.6,
  format: 'webp'
});

// 이미지 여부 확인
TaiImageCompress.isImage(file);   // true/false

// WebP 지원 확인
const ok = await TaiImageCompress.supportsWebP();  // true/false
```

### 안전장치

| 상황 | 동작 |
|---|---|
| 이미지가 아닌 파일 (PDF, HWP) | 원본 반환 |
| HEIC/HEIF (iPhone) | 원본 반환 |
| 이미 작은 파일 (500KB 이하 + 해상도 이내) | 원본 반환 |
| facility_drawing 카테고리 | 압축 안 함 |
| 압축 후 오히려 커짐 | 원본 반환 |
| Canvas 오류 | 원본 반환 |

**어떤 상황에서도 실패하지 않음. 최악의 경우 원본이 그대로 올라감.**

---

## 8. DB 스키마 (documents 테이블)

### 핵심 컬럼

| 컬럼 | 타입 | 용도 | 필수 |
|---|---|---|---|
| `company_id` | UUID FK | RLS 격리 키 | ✅ |
| `factory_id` | UUID FK | 사업장 단위 분류 | |
| `category` | doc_category | 13종 문서 분류 | ✅ |
| `source` | doc_source | USER_UPLOAD / AUTO_GENERATED / MIGRATED | ✅ |
| `file_name` | TEXT | 원본 파일명 (표시용) | ✅ |
| `storage_path` | TEXT | Storage 전체 경로 | ✅ |
| `file_size` | INTEGER | bytes | ✅ |
| `mime_type` | TEXT | | ✅ |
| `linked_table` | TEXT | 폴리모픽 연결 대상 테이블 | |
| `linked_id` | UUID | 폴리모픽 연결 대상 ID | |
| `title` | TEXT | 검색용 제목 | |
| `tags` | TEXT[] | 자유 태그 (GIN 인덱스) | |
| `is_photo` | BOOLEAN | 사진 여부 (자동 판별) | |
| `thumbnail_path` | TEXT | 썸네일 경로 (향후) | |
| `generated_by` | TEXT | 자동생성 시 생성기 이름 | |
| `generation_params` | JSONB | 자동생성 파라미터 | |
| `uploaded_by` | UUID | 업로드한 사용자 | |
| `retention_years` | INTEGER | 보존 연한 | |
| `retention_until` | DATE | 보존 만료일 (자동 계산) | |
| `deleted_at` | TIMESTAMPTZ | soft delete | |

### 폴리모픽 연결 (linked_table + linked_id)

어떤 테이블의 어떤 레코드에든 문서를 연결할 수 있음:

```sql
-- 특정 점검 기록의 첨부파일
SELECT * FROM documents
WHERE linked_table = 'inspections' AND linked_id = '{inspection_id}'
  AND is_active = true AND deleted_at IS NULL;

-- 특정 교육 기록의 첨부파일
SELECT * FROM documents
WHERE linked_table = 'education_records' AND linked_id = '{record_id}';

-- 특정 설비의 문서
SELECT * FROM documents
WHERE linked_table = 'equipments' AND linked_id = '{equipment_id}';
```

### 뷰

```sql
-- 회사별·카테고리별 통계
SELECT * FROM v_document_stats WHERE company_id = '{uuid}';
-- → { category, doc_count, total_size, last_uploaded, auto_count, upload_count }

-- 보존기한 90일 이내 만료 예정
SELECT * FROM v_documents_expiring WHERE company_id = '{uuid}';
-- → { id, category, file_name, retention_until, days_remaining }
```

---

## 9. RLS 보안

| 계층 | 정책 | 설명 |
|---|---|---|
| **DB (documents)** | `users.company_id = documents.company_id` | 자기 회사 문서만 조회/생성/수정 |
| **Storage (company-docs)** | 경로 첫 세그먼트 = `users.company_id` | 자기 회사 폴더만 접근 |
| **service_role** | 전체 접근 | 백엔드 API (Railway) |

→ 회사 A 사용자가 회사 B 문서에 접근 불가 (DB + Storage 이중 차단)

---

## 10. 다른 라우터에서 문서 서비스 사용하기

### 패턴: 자동생성 PDF 등록

```python
# routers/diagnosis_report.py 또는 routers/inspection_sets.py 등에서

from services.document_svc import register_generated

# Gotenberg로 PDF 생성 후
pdf_bytes = await generate_pdf_with_gotenberg(html_content)

# 문서 시스템에 등록
doc = await register_generated(
    file_bytes=pdf_bytes,
    file_name=f"점검표_{factory_name}_{date_str}.pdf",
    mime_type="application/pdf",
    company_id=company_id,
    category="report",
    generated_by="inspection_report",
    generation_params={"factory_id": str(factory_id), "date": date_str},
    factory_id=str(factory_id)
)
# doc['id'] = 생성된 문서 ID
# doc['storage_path'] = Storage 경로
```

### 패턴: 엔티티에 연결된 첨부파일 조회

```python
from services.document_svc import get_attachments

# 특정 점검 기록의 사진 목록
photos = await get_attachments("inspections", str(inspection_id))
# photos = [{ id, file_name, storage_path, mime_type, file_size, ... }, ...]

# 특정 시정조치의 전/후 사진
before = [d for d in await get_attachments("corrective_actions", str(action_id)) 
          if 'before' in (d.get('tags') or [])]
after  = [d for d in await get_attachments("corrective_actions", str(action_id)) 
          if 'after' in (d.get('tags') or [])]
```

### 패턴: Signed URL 생성

```python
from services.document_svc import get_signed_url

# 1시간 유효한 다운로드 URL
url = await get_signed_url(doc_id, expires_in=3600)
```

---

## 11. 용량 절감 효과 요약

| 방법 | 절감률 | 적용 대상 |
|---|---|---|
| 이미지 클라이언트 압축 | **95%** | 점검, 시정조치, TBM 사진 |
| DB 저장 + 실시간 PDF | **99%** | 자동생성 문서 (웹 열람, 필요 시 PDF) |
| 업로드 용량 제한 | 간접 | 전체 |

**고객 1개소 월 예상**: 사진 100MB(압축 전 2GB) + 문서 50MB = **~150MB/월**
**Pro 플랜 100GB 기준**: 고객 ~650개소까지 추가 비용 없음
