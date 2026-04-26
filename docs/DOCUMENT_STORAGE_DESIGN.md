# TAI Safe 통합 문서 스토리지 설계서

**작성일**: 2026-04-25
**상태**: DB Migration 완료, 코드 구현 대기

---

## 1. 아키텍처 개요

```
[사용자]
  │
  ├─ safe.taieng.co.kr (안전관리자)
  ├─ safe.taieng.co.kr/app (작업자 PWA)
  └─ admin.taieng.co.kr (슈퍼어드민)
  │
  ▼
[tai-document.js]  ← 프론트엔드 모듈 (공통)
  │
  ├─ 직접 업로드 → Supabase Storage (company-docs 버킷)
  └─ 메타데이터 → API → documents 테이블
  │
  ▼
[services/document_svc.py]  ← 백엔드 서비스 (공통)
  │
  ├─ routers/documents.py     (REST API)
  ├─ routers/inspection_sets.py  (점검 사진 연동)
  ├─ routers/education.py       (교육 자료 연동)
  ├─ routers/diagnosis_report.py (자동생성 PDF 등록)
  └─ 기타 라우터
```

## 2. 스토리지 구조

### 2.1 버킷 정리

| 버킷 | 용도 | public | 유지/통합 |
|---|---|---|---|
| **company-docs** | 고객 문서 전체 (신규) | ❌ private | **신규 — 핵심** |
| site-assets | 마케팅 사이트 자산 | ✅ | 유지 |
| diagrams | SVG 다이어그램 | ✅ | 유지 |
| app | PWA 앱 자산 | ✅ | 유지 |
| proposals | 자동생성 기안 PDF | ✅ | 유지 (향후 company-docs로 이관 검토) |
| inspection-images | → company-docs로 통합 | - | 폐기 예정 |
| facility-drawings | → company-docs로 통합 | - | 폐기 예정 |
| company-logo | → company-docs로 통합 | - | 폐기 예정 |
| expert-documents | → company-docs로 통합 | - | 폐기 예정 |
| contracts | → company-docs로 통합 | - | 폐기 예정 |
| final-reports | → company-docs로 통합 | - | 폐기 예정 |
| inspections | → company-docs로 통합 | - | 폐기 예정 |
| form-originals | 서식 원본 (HWP 등) | ❌ | 유지 (시스템) |
| form-templates | 서식 HTML 템플릿 | ❌ | 유지 (시스템) |
| form-outputs | 서식 PDF 출력 | ❌ | 유지 (시스템) |
| mail-attachments | 메일 첨부 | ❌ | 유지 (시스템) |

### 2.2 경로 규칙

```
company-docs/{company_id}/{category}/{YYYY-MM}/{uuid}.{ext}
```

예시:
```
company-docs/a1b2c3d4-xxx/inspection/2026-04/f5e6d7c8-xxx.jpg
company-docs/a1b2c3d4-xxx/certificate/2026-04/g9h0i1j2-xxx.pdf
company-docs/a1b2c3d4-xxx/report/2026-04/k3l4m5n6-xxx.pdf
```

**왜 이 구조인가:**
- `company_id`가 첫 세그먼트 → Storage RLS에서 경로 기반 격리 가능
- `category`로 폴더 분류 → 관리자가 탐색 가능
- `YYYY-MM`로 시간 분류 → 보존기한 관리 + 오래된 파일 정리 용이
- `uuid.ext`로 파일명 충돌 방지

### 2.3 RLS 보안

**documents 테이블**: `users.company_id = documents.company_id`
**storage.objects**: 경로 첫 세그먼트 = `users.company_id`

→ 회사 A의 사용자는 회사 B의 문서를 볼 수도, 다운로드할 수도 없음.

## 3. DB 스키마

### 3.1 documents 테이블 (완료)

| 컬럼 | 타입 | 용도 |
|---|---|---|
| id | UUID PK | |
| company_id | UUID FK → companies | RLS 격리 키 |
| factory_id | UUID FK → factories | 사업장 단위 분류 (선택) |
| category | doc_category ENUM | 13종 문서 분류 |
| source | doc_source ENUM | USER_UPLOAD / AUTO_GENERATED / MIGRATED |
| file_name | TEXT | 원본 파일명 (표시용) |
| storage_path | TEXT | Supabase Storage 전체 경로 |
| bucket_id | TEXT | 기본값 'company-docs' |
| file_size | INTEGER | bytes |
| mime_type | TEXT | |
| file_ext | TEXT | pdf, jpg 등 |
| linked_table | TEXT | 폴리모픽 연결 대상 테이블 |
| linked_id | UUID | 폴리모픽 연결 대상 ID |
| title | TEXT | 문서 제목 (검색용) |
| description | TEXT | 설명/메모 |
| tags | TEXT[] | 자유 태그 |
| is_photo | BOOLEAN | 사진 여부 |
| image_width/height | INTEGER | 이미지 크기 |
| taken_at | TIMESTAMPTZ | 촬영 시간 |
| gps_lat/lng | NUMERIC | 촬영 위치 |
| exif_json | JSONB | EXIF 원본 |
| thumbnail_path | TEXT | 썸네일 경로 |
| generated_by | TEXT | 자동생성 시 생성기 이름 |
| generation_params | JSONB | 자동생성 파라미터 |
| uploaded_by | UUID | 업로드 사용자 |
| uploaded_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | 자동 갱신 |
| deleted_at | TIMESTAMPTZ | soft delete |
| is_active | BOOLEAN | |
| retention_years | INTEGER | 보존 연한 (산안법 3년, 중대재해 5년) |
| retention_until | DATE | 보존 만료일 |

### 3.2 카테고리 (doc_category ENUM)

| 값 | 용도 | 보존 연한 기본값 |
|---|---|---|
| inspection | 점검 사진/기록 | 3년 |
| certificate | 인증서, 면허, 자격증 | 갱신 시까지 |
| education | 교육자료, 수료증 | 3년 |
| safety_plan | 안전보건관리계획서 | 5년 |
| risk_assessment | 위험성평가서 | 3년 |
| msds | 물질안전보건자료 | 상시 |
| corrective | 시정조치 증빙 | 3년 |
| report | 보고서 (자동생성 포함) | 3년 |
| contract | 계약서 | 5년 |
| tbm | TBM 기록/서명 | 3년 |
| equipment | 설비 관련 문서 | 설비 폐기 시까지 |
| facility_drawing | 시설 도면 | 상시 |
| general | 기타 | 1년 |

### 3.3 뷰

- `v_document_stats`: 회사별·카테고리별 문서 수, 용량, 최근 업로드 시간
- `v_documents_expiring`: 보존기한 90일 이내 만료 예정 문서

## 4. 모듈 설계

### 4.1 백엔드: services/document_svc.py

**원칙**: Router에서 import해서 사용. SQL 직접 실행, FastAPI 의존성 없음.

```python
class DocumentService:
    # === 업로드 ===
    async def upload(
        file: UploadFile,
        company_id: UUID,
        category: str,
        factory_id: UUID = None,
        linked_table: str = None,
        linked_id: UUID = None,
        title: str = None,
        tags: list = None,
        uploaded_by: UUID = None,
        retention_years: int = None
    ) -> dict:
        # 1. UUID 파일명 생성
        # 2. storage_path 조립: {company_id}/{category}/{YYYY-MM}/{uuid}.{ext}
        # 3. Supabase Storage 업로드
        # 4. 이미지면 EXIF 추출 + 썸네일 생성
        # 5. documents 테이블 INSERT
        # 6. 반환: {id, storage_path, file_url, ...}

    # === 자동생성 문서 등록 ===
    async def register_generated(
        file_bytes: bytes,
        file_name: str,
        mime_type: str,
        company_id: UUID,
        category: str,
        generated_by: str,
        generation_params: dict = None,
        **kwargs
    ) -> dict:
        # PDF 자동생성 후 호출하는 메서드
        # Storage 업로드 + metadata INSERT

    # === 조회 ===
    async def list_documents(
        company_id: UUID,
        category: str = None,
        factory_id: UUID = None,
        linked_table: str = None,
        linked_id: UUID = None,
        search: str = None,
        tags: list = None,
        page: int = 1,
        per_page: int = 20
    ) -> dict:  # {items: [...], total: N, page: N}

    async def get_document(doc_id: UUID) -> dict

    # === 다운로드 URL ===
    async def get_signed_url(doc_id: UUID, expires_in: int = 3600) -> str:
        # Supabase Storage signed URL 생성 (1시간 기본)

    # === 삭제 ===
    async def soft_delete(doc_id: UUID, deleted_by: UUID = None) -> bool:
        # deleted_at = now(), is_active = false
        # Storage 파일은 유지 (보존기한)

    async def hard_delete(doc_id: UUID) -> bool:
        # Storage 파일 삭제 + DB 레코드 삭제
        # 보존기한 만료 확인 후에만 실행

    # === 통계 ===
    async def get_stats(company_id: UUID) -> dict

    # === 특정 엔티티의 첨부파일 ===
    async def get_attachments(linked_table: str, linked_id: UUID) -> list:
        # 점검 기록, 교육 이력 등에 연결된 문서 조회

    # === 보존기한 ===
    async def get_expiring(company_id: UUID, days: int = 90) -> list
```

### 4.2 백엔드: routers/documents.py

```
GET    /documents                     # 문서 목록 (필터: category, factory_id, search, tags)
GET    /documents/{id}                # 문서 상세
GET    /documents/{id}/download       # 다운로드 (signed URL redirect)
POST   /documents/upload              # 단일 업로드 (multipart)
POST   /documents/upload-multiple     # 다중 업로드
DELETE /documents/{id}                # soft delete
PATCH  /documents/{id}                # 메타데이터 수정 (title, description, tags)
GET    /documents/stats               # 회사별 통계
GET    /documents/expiring            # 보존기한 만료 예정
GET    /documents/by-entity/{table}/{id}  # 특정 엔티티 첨부 문서
```

### 4.3 프론트엔드: tai-document.js

**설치 위치**:
- `tadmin/full-version/assets/js/tai/tai-document.js` (safe/admin 공용)
- `tadmin/full-version/app/tai-document.js` (PWA 앱용 — 동일 코드)

**사용 예시**:

```html
<!-- 어디서든 이렇게 사용 -->
<script src="/assets/js/tai/tai-document.js"></script>
<script>
  const docMgr = new TaiDocument({
    apiBase: 'https://api.taieng.co.kr',
    supabaseUrl: 'https://xntdkrjhgcscmqctdzyo.supabase.co',
    supabaseKey: ANON_KEY,
    companyId: currentUser.company_id,
    factoryId: currentFactory?.id  // 선택
  });
</script>
```

**주요 메서드:**

```javascript
class TaiDocument {
  // === 업로드 ===
  async upload(file, options = {}) {}
  // options: { category, linkedTable, linkedId, title, tags, onProgress }
  // 반환: { id, fileName, fileUrl, category, ... }

  async uploadMultiple(files, options = {}) {}
  // 다중 업로드 (Promise.all)

  // === 조회 ===
  async list(filters = {}) {}
  // filters: { category, search, tags, page, perPage }
  // 반환: { items: [...], total, page, totalPages }

  async getByEntity(tableName, recordId) {}
  // 특정 점검/교육/시정조치에 연결된 문서

  // === 다운로드 ===
  async getDownloadUrl(docId) {}
  // signed URL 반환 (1시간 유효)

  async download(docId) {}
  // 브라우저 다운로드 트리거

  // === 삭제 ===
  async delete(docId) {}

  // === 메타데이터 수정 ===
  async update(docId, updates) {}
  // updates: { title, description, tags }

  // === UI 헬퍼 ===
  createUploadZone(containerId, options) {}
  // 드래그앤드롭 + 클릭 업로드 영역 자동 생성
  // options: { category, accept, multiple, maxFiles, maxSize, onComplete }

  createFileList(containerId, filters) {}
  // 문서 목록 UI 자동 생성 (카드/리스트 뷰)

  createAttachmentWidget(containerId, linkedTable, linkedId, options) {}
  // 특정 엔티티에 연결된 첨부파일 위젯
  // 업로드 + 목록 + 삭제 통합

  // === 통계 ===
  async getStats() {}

  // === 유틸 ===
  static formatFileSize(bytes) {}
  static getFileIcon(ext) {}
  static isImage(mimeType) {}
  static isPreviewable(mimeType) {}
}
```

**사용 시나리오별 예시:**

```javascript
// 1. 점검 화면 — 이상 발견 시 사진 첨부
const widget = docMgr.createAttachmentWidget('photo-area', 'inspections', inspectionId, {
  category: 'inspection',
  accept: 'image/*',
  maxFiles: 5,
  capture: 'environment'  // 모바일 카메라
});

// 2. 교육 관리 — 교육자료 업로드
const zone = docMgr.createUploadZone('edu-upload', {
  category: 'education',
  accept: '.pdf,.pptx,.docx,.hwp',
  multiple: true,
  maxSize: 50 * 1024 * 1024
});

// 3. 시정조치 — 전/후 사진
const beforeWidget = docMgr.createAttachmentWidget('before-photo', 'corrective_actions', actionId, {
  category: 'corrective',
  tags: ['before'],
  maxFiles: 3
});
const afterWidget = docMgr.createAttachmentWidget('after-photo', 'corrective_actions', actionId, {
  category: 'corrective',
  tags: ['after'],
  maxFiles: 3
});

// 4. 문서함 페이지 — 전체 문서 목록
const fileList = docMgr.createFileList('doc-container', {
  perPage: 20
});

// 5. 자동생성 PDF 등록 (백엔드에서)
# Python
await doc_svc.register_generated(
    file_bytes=pdf_bytes,
    file_name='진단보고서_대성정밀_2026-04.pdf',
    mime_type='application/pdf',
    company_id=company_id,
    category='report',
    generated_by='diagnosis_report',
    generation_params={'token': public_token, 'tier': 'PAID2'}
)
```

## 5. 보존기한 정책

| 법적 근거 | 보존 연한 | 적용 카테고리 |
|---|---|---|
| 산업안전보건법 시행규칙 | 3년 | inspection, education, risk_assessment, corrective, tbm |
| 중대재해처벌법 | 5년 | safety_plan, contract |
| 물질안전보건자료 관리 | 상시 | msds |
| 건축물관리법 | 건물 존속 시까지 | facility_drawing |

자동 설정: `document_svc.upload()` 시 category별 기본 retention_years 적용.
보존기한 만료 문서는 `v_documents_expiring` 뷰로 90일 전 경고.

## 6. 향후 확장

### 6.1 이미지 리사이즈 파이프라인
- 업로드 시 원본 보관 + 800px 썸네일 자동 생성
- Supabase Edge Function 또는 Railway 서비스
- egress 비용 1/10 절감

### 6.2 Cloudflare R2 마이그레이션
- 고객 100개소 초과 시 검토
- S3 호환이라 storage_path + signed URL 로직만 변경
- egress 무료

### 6.3 버전 관리
- 동일 문서 갱신 시 이전 버전 보관
- `document_versions` 테이블 추가

### 6.4 OCR
- 인증서/면허 사진 → 만료일 자동 추출
- 알림 연동
