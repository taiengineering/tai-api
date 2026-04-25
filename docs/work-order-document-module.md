# 작업지시서: 통합 문서 스토리지 모듈 구현

**작성일**: 2026-04-25
**실행 대상**: Cursor (백엔드) + 프론트 창 (프론트엔드)
**관련 설계서**: `docs/DOCUMENT_STORAGE_DESIGN.md`
**DB Migration**: 완료 (`create_unified_document_storage`)
**버킷**: `company-docs` 생성 완료 (private, RLS 적용)

---

## 선행 규칙

- `docs/DEV_RULES_SERVICE_LAYER.md` 준수
- Router = HTTP만 (SQL 금지), Service = 비즈니스 로직 (FastAPI 금지)
- 파일당 최대 400줄 / 15KB
- `from db.supabase_client import get_supabase`

---

## 백엔드 (tai-api, dev 브랜치)

### 파일 1: services/document_svc.py (~300줄)

```python
"""TAI Safe 통합 문서 서비스 v1.0.0"""
import uuid
from datetime import datetime, date
from typing import Optional
from db.supabase_client import get_supabase

# 카테고리별 기본 보존 연한
RETENTION_DEFAULTS = {
    'inspection': 3, 'certificate': None, 'education': 3,
    'safety_plan': 5, 'risk_assessment': 3, 'msds': None,
    'corrective': 3, 'report': 3, 'contract': 5,
    'tbm': 3, 'equipment': None, 'facility_drawing': None, 'general': 1
}

BUCKET = 'company-docs'

def _build_path(company_id: str, category: str, ext: str) -> str:
    now = datetime.utcnow()
    file_uuid = str(uuid.uuid4())
    return f"{company_id}/{category}/{now.strftime('%Y-%m')}/{file_uuid}.{ext}"

def _get_ext(filename: str) -> str:
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

async def upload_document(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    company_id: str,
    category: str = 'general',
    source: str = 'USER_UPLOAD',
    factory_id: str = None,
    linked_table: str = None,
    linked_id: str = None,
    title: str = None,
    description: str = None,
    tags: list = None,
    uploaded_by: str = None,
    retention_years: int = None,
    generated_by: str = None,
    generation_params: dict = None
) -> dict:
    sb = get_supabase()
    ext = _get_ext(file_name)
    storage_path = _build_path(company_id, category, ext)

    # 1. Storage 업로드
    sb.storage.from_(BUCKET).upload(
        path=storage_path,
        file=file_bytes,
        file_options={'content-type': mime_type}
    )

    # 2. 보존기한 계산
    if retention_years is None:
        retention_years = RETENTION_DEFAULTS.get(category)
    retention_until = None
    if retention_years:
        retention_until = date(
            datetime.utcnow().year + retention_years,
            datetime.utcnow().month,
            datetime.utcnow().day
        ).isoformat()

    # 3. 메타데이터 INSERT
    record = {
        'company_id': company_id,
        'factory_id': factory_id,
        'category': category,
        'source': source,
        'file_name': file_name,
        'storage_path': storage_path,
        'bucket_id': BUCKET,
        'file_size': len(file_bytes),
        'mime_type': mime_type,
        'file_ext': ext,
        'linked_table': linked_table,
        'linked_id': linked_id,
        'title': title or file_name,
        'description': description,
        'tags': tags or [],
        'is_photo': mime_type.startswith('image/'),
        'uploaded_by': uploaded_by,
        'generated_by': generated_by,
        'generation_params': generation_params,
        'retention_years': retention_years,
        'retention_until': retention_until
    }
    # None 값 제거
    record = {k: v for k, v in record.items() if v is not None}

    result = sb.table('documents').insert(record).execute()
    return result.data[0] if result.data else record


async def register_generated(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    company_id: str,
    category: str,
    generated_by: str,
    generation_params: dict = None,
    **kwargs
) -> dict:
    """자동생성 문서 등록 (PDF 등)"""
    return await upload_document(
        file_bytes=file_bytes,
        file_name=file_name,
        mime_type=mime_type,
        company_id=company_id,
        category=category,
        source='AUTO_GENERATED',
        generated_by=generated_by,
        generation_params=generation_params,
        **kwargs
    )


async def list_documents(
    company_id: str,
    category: str = None,
    factory_id: str = None,
    linked_table: str = None,
    linked_id: str = None,
    search: str = None,
    tags: list = None,
    page: int = 1,
    per_page: int = 20
) -> dict:
    sb = get_supabase()
    query = sb.table('documents').select('*', count='exact')
    query = query.eq('company_id', company_id)
    query = query.eq('is_active', True)
    query = query.is_('deleted_at', 'null')

    if category:
        query = query.eq('category', category)
    if factory_id:
        query = query.eq('factory_id', factory_id)
    if linked_table and linked_id:
        query = query.eq('linked_table', linked_table).eq('linked_id', linked_id)
    if search:
        query = query.or_(f"title.ilike.%{search}%,file_name.ilike.%{search}%,description.ilike.%{search}%")
    if tags:
        query = query.contains('tags', tags)

    offset = (page - 1) * per_page
    query = query.order('uploaded_at', desc=True)
    query = query.range(offset, offset + per_page - 1)

    result = query.execute()
    total = result.count or 0
    return {
        'items': result.data,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    }


async def get_document(doc_id: str) -> dict:
    sb = get_supabase()
    result = sb.table('documents').select('*').eq('id', doc_id).single().execute()
    return result.data


async def get_signed_url(doc_id: str, expires_in: int = 3600) -> str:
    sb = get_supabase()
    doc = await get_document(doc_id)
    if not doc:
        return None
    result = sb.storage.from_(doc['bucket_id']).create_signed_url(
        doc['storage_path'], expires_in
    )
    return result.get('signedURL') or result.get('signed_url')


async def get_attachments(linked_table: str, linked_id: str) -> list:
    sb = get_supabase()
    result = sb.table('documents').select('*') \
        .eq('linked_table', linked_table) \
        .eq('linked_id', linked_id) \
        .eq('is_active', True) \
        .is_('deleted_at', 'null') \
        .order('uploaded_at', desc=True) \
        .execute()
    return result.data


async def soft_delete(doc_id: str) -> bool:
    sb = get_supabase()
    result = sb.table('documents').update({
        'deleted_at': datetime.utcnow().isoformat(),
        'is_active': False
    }).eq('id', doc_id).execute()
    return len(result.data) > 0


async def get_stats(company_id: str) -> list:
    sb = get_supabase()
    result = sb.table('v_document_stats').select('*') \
        .eq('company_id', company_id).execute()
    return result.data


async def get_expiring(company_id: str, days: int = 90) -> list:
    sb = get_supabase()
    result = sb.table('v_documents_expiring').select('*') \
        .eq('company_id', company_id) \
        .lte('days_remaining', days) \
        .execute()
    return result.data
```

### 파일 2: routers/documents.py (~200줄)

```python
"""TAI Safe 문서 관리 API v1.0.0"""
from fastapi import APIRouter, UploadFile, File, Form, Query, HTTPException
from typing import Optional, List
from services import document_svc

router = APIRouter(prefix='/documents', tags=['Documents'])

@router.post('/upload')
async def upload_document(
    file: UploadFile = File(...),
    company_id: str = Form(...),
    category: str = Form('general'),
    factory_id: str = Form(None),
    linked_table: str = Form(None),
    linked_id: str = Form(None),
    title: str = Form(None),
    description: str = Form(None),
    tags: str = Form(None),  # 쉼표 구분
    uploaded_by: str = Form(None)
):
    file_bytes = await file.read()
    tag_list = [t.strip() for t in tags.split(',')] if tags else []
    result = await document_svc.upload_document(
        file_bytes=file_bytes,
        file_name=file.filename,
        mime_type=file.content_type or 'application/octet-stream',
        company_id=company_id,
        category=category,
        factory_id=factory_id,
        linked_table=linked_table,
        linked_id=linked_id,
        title=title,
        description=description,
        tags=tag_list,
        uploaded_by=uploaded_by
    )
    return {'status': 'success', 'data': result}


@router.post('/upload-multiple')
async def upload_multiple(
    files: List[UploadFile] = File(...),
    company_id: str = Form(...),
    category: str = Form('general'),
    factory_id: str = Form(None),
    linked_table: str = Form(None),
    linked_id: str = Form(None),
    uploaded_by: str = Form(None)
):
    results = []
    for f in files:
        fb = await f.read()
        r = await document_svc.upload_document(
            file_bytes=fb, file_name=f.filename,
            mime_type=f.content_type or 'application/octet-stream',
            company_id=company_id, category=category,
            factory_id=factory_id, linked_table=linked_table,
            linked_id=linked_id, uploaded_by=uploaded_by
        )
        results.append(r)
    return {'status': 'success', 'data': results, 'count': len(results)}


@router.get('')
async def list_documents(
    company_id: str = Query(...),
    category: str = Query(None),
    factory_id: str = Query(None),
    linked_table: str = Query(None),
    linked_id: str = Query(None),
    search: str = Query(None),
    tags: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    tag_list = [t.strip() for t in tags.split(',')] if tags else None
    result = await document_svc.list_documents(
        company_id=company_id, category=category,
        factory_id=factory_id, linked_table=linked_table,
        linked_id=linked_id, search=search, tags=tag_list,
        page=page, per_page=per_page
    )
    return {'status': 'success', **result}


@router.get('/stats')
async def document_stats(company_id: str = Query(...)):
    return {'status': 'success', 'data': await document_svc.get_stats(company_id)}


@router.get('/expiring')
async def expiring_documents(
    company_id: str = Query(...), days: int = Query(90)
):
    return {'status': 'success', 'data': await document_svc.get_expiring(company_id, days)}


@router.get('/by-entity/{table}/{record_id}')
async def by_entity(table: str, record_id: str):
    return {'status': 'success', 'data': await document_svc.get_attachments(table, record_id)}


@router.get('/{doc_id}')
async def get_document(doc_id: str):
    doc = await document_svc.get_document(doc_id)
    if not doc:
        raise HTTPException(404, 'Document not found')
    return {'status': 'success', 'data': doc}


@router.get('/{doc_id}/download')
async def download_document(doc_id: str):
    url = await document_svc.get_signed_url(doc_id)
    if not url:
        raise HTTPException(404, 'Document not found')
    return {'status': 'success', 'url': url}


@router.patch('/{doc_id}')
async def update_document(doc_id: str, body: dict):
    from db.supabase_client import get_supabase
    allowed = {'title', 'description', 'tags', 'category'}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, 'No valid fields to update')
    sb = get_supabase()
    result = sb.table('documents').update(updates).eq('id', doc_id).execute()
    return {'status': 'success', 'data': result.data[0] if result.data else None}


@router.delete('/{doc_id}')
async def delete_document(doc_id: str):
    ok = await document_svc.soft_delete(doc_id)
    if not ok:
        raise HTTPException(404, 'Document not found')
    return {'status': 'success'}
```

### 파일 3: main.py 수정

`routers/documents.py` import + include:
```python
from routers.documents import router as documents_router
app.include_router(documents_router)  # 인증 그룹에 추가
```

---

## 프론트엔드 (tai-admin, main 브랜치)

### 파일: tadmin/full-version/assets/js/tai/tai-document.js (~350줄)

**핵심 클래스** — safe, admin, PWA 앱에서 공통 사용

```javascript
/**
 * TAI Document Module v1.0.0
 * 통합 문서 관리 (업로드/조회/다운로드/삭제)
 * 
 * 사용법:
 *   const doc = new TaiDocument({ apiBase, companyId });
 *   await doc.upload(file, { category: 'inspection' });
 *   const list = await doc.list({ category: 'inspection' });
 */
class TaiDocument {
  constructor({ apiBase, companyId, factoryId = null, token = null }) {
    this.apiBase = apiBase || 'https://api.taieng.co.kr';
    this.companyId = companyId;
    this.factoryId = factoryId;
    this.token = token;
  }

  _headers() {
    const h = { 'Accept': 'application/json' };
    if (this.token) h['Authorization'] = `Bearer ${this.token}`;
    return h;
  }

  // === 업로드 ===
  async upload(file, opts = {}) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('company_id', this.companyId);
    fd.append('category', opts.category || 'general');
    if (this.factoryId) fd.append('factory_id', this.factoryId);
    if (opts.linkedTable) fd.append('linked_table', opts.linkedTable);
    if (opts.linkedId) fd.append('linked_id', opts.linkedId);
    if (opts.title) fd.append('title', opts.title);
    if (opts.description) fd.append('description', opts.description);
    if (opts.tags) fd.append('tags', opts.tags.join(','));
    if (opts.uploadedBy) fd.append('uploaded_by', opts.uploadedBy);

    const resp = await fetch(`${this.apiBase}/documents/upload`, {
      method: 'POST', headers: this._headers(), body: fd
    });
    return resp.json();
  }

  async uploadMultiple(files, opts = {}) {
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    fd.append('company_id', this.companyId);
    fd.append('category', opts.category || 'general');
    if (this.factoryId) fd.append('factory_id', this.factoryId);
    if (opts.linkedTable) fd.append('linked_table', opts.linkedTable);
    if (opts.linkedId) fd.append('linked_id', opts.linkedId);

    const resp = await fetch(`${this.apiBase}/documents/upload-multiple`, {
      method: 'POST', headers: this._headers(), body: fd
    });
    return resp.json();
  }

  // === 조회 ===
  async list(filters = {}) {
    const params = new URLSearchParams({ company_id: this.companyId });
    if (filters.category) params.set('category', filters.category);
    if (filters.factoryId) params.set('factory_id', filters.factoryId);
    if (filters.search) params.set('search', filters.search);
    if (filters.tags) params.set('tags', filters.tags.join(','));
    if (filters.page) params.set('page', filters.page);
    if (filters.perPage) params.set('per_page', filters.perPage);

    const resp = await fetch(`${this.apiBase}/documents?${params}`, {
      headers: this._headers()
    });
    return resp.json();
  }

  async getByEntity(tableName, recordId) {
    const resp = await fetch(
      `${this.apiBase}/documents/by-entity/${tableName}/${recordId}`,
      { headers: this._headers() }
    );
    return resp.json();
  }

  async get(docId) {
    const resp = await fetch(`${this.apiBase}/documents/${docId}`, {
      headers: this._headers()
    });
    return resp.json();
  }

  // === 다운로드 ===
  async getDownloadUrl(docId) {
    const resp = await fetch(`${this.apiBase}/documents/${docId}/download`, {
      headers: this._headers()
    });
    const data = await resp.json();
    return data.url;
  }

  async download(docId) {
    const url = await this.getDownloadUrl(docId);
    if (url) {
      const a = document.createElement('a');
      a.href = url; a.download = ''; a.click();
    }
  }

  // === 수정/삭제 ===
  async update(docId, updates) {
    const resp = await fetch(`${this.apiBase}/documents/${docId}`, {
      method: 'PATCH',
      headers: { ...this._headers(), 'Content-Type': 'application/json' },
      body: JSON.stringify(updates)
    });
    return resp.json();
  }

  async delete(docId) {
    const resp = await fetch(`${this.apiBase}/documents/${docId}`, {
      method: 'DELETE', headers: this._headers()
    });
    return resp.json();
  }

  // === 통계 ===
  async getStats() {
    const resp = await fetch(
      `${this.apiBase}/documents/stats?company_id=${this.companyId}`,
      { headers: this._headers() }
    );
    return resp.json();
  }

  // === UI 위젯: 드래그앤드롭 업로드 영역 ===
  createUploadZone(containerId, opts = {}) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const accept = opts.accept || '*';
    const maxFiles = opts.maxFiles || 10;
    const maxSize = opts.maxSize || 50 * 1024 * 1024;

    el.innerHTML = `
      <div class="tai-upload-zone" style="border:2px dashed #cbd5e1;border-radius:16px;
        padding:32px;text-align:center;cursor:pointer;transition:border-color .2s;
        background:#f8fafc;">
        <div style="font-size:28px;margin-bottom:8px;">📁</div>
        <div style="font-weight:700;margin-bottom:4px;">파일을 끌어놓거나 클릭하세요</div>
        <div style="font-size:13px;color:#94a3b8;">최대 ${maxFiles}개, ${TaiDocument.formatFileSize(maxSize)}</div>
        <input type="file" accept="${accept}" ${opts.multiple !== false ? 'multiple' : ''}
          style="display:none;" ${opts.capture ? 'capture="'+opts.capture+'"' : ''}/>
      </div>
      <div class="tai-upload-list" style="margin-top:12px;"></div>
    `;

    const zone = el.querySelector('.tai-upload-zone');
    const input = el.querySelector('input[type=file]');
    const listEl = el.querySelector('.tai-upload-list');

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor = '#6366f1'; });
    zone.addEventListener('dragleave', () => { zone.style.borderColor = '#cbd5e1'; });
    zone.addEventListener('drop', e => {
      e.preventDefault(); zone.style.borderColor = '#cbd5e1';
      this._handleFiles([...e.dataTransfer.files], opts, listEl);
    });
    input.addEventListener('change', () => {
      this._handleFiles([...input.files], opts, listEl);
      input.value = '';
    });

    return { el, refresh: () => this._refreshList(listEl, opts) };
  }

  async _handleFiles(files, opts, listEl) {
    for (const f of files) {
      const item = document.createElement('div');
      item.style.cssText = 'display:flex;align-items:center;gap:8px;padding:8px 12px;' +
        'background:#f1f5f9;border-radius:10px;margin-bottom:6px;font-size:14px;';
      item.innerHTML = `<span>${TaiDocument.getFileIcon(f.name.split('.').pop())}</span>
        <span style="flex:1;">${f.name}</span>
        <span style="color:#94a3b8;">${TaiDocument.formatFileSize(f.size)}</span>
        <span class="status" style="color:#6366f1;">업로드 중...</span>`;
      listEl.appendChild(item);

      try {
        await this.upload(f, opts);
        item.querySelector('.status').textContent = '✅';
        item.querySelector('.status').style.color = '#22c55e';
      } catch (err) {
        item.querySelector('.status').textContent = '❌ 실패';
        item.querySelector('.status').style.color = '#ef4444';
      }
    }
    if (opts.onComplete) opts.onComplete();
  }

  // === UI 위젯: 첨부파일 (엔티티 연결) ===
  createAttachmentWidget(containerId, linkedTable, linkedId, opts = {}) {
    const zone = this.createUploadZone(containerId, {
      ...opts,
      linkedTable, linkedId,
      onComplete: () => this._refreshAttachments(containerId, linkedTable, linkedId)
    });
    this._refreshAttachments(containerId, linkedTable, linkedId);
    return zone;
  }

  async _refreshAttachments(containerId, table, id) {
    const el = document.getElementById(containerId);
    if (!el) return;
    let listEl = el.querySelector('.tai-attach-list');
    if (!listEl) {
      listEl = document.createElement('div');
      listEl.className = 'tai-attach-list';
      listEl.style.cssText = 'margin-top:12px;display:flex;flex-wrap:wrap;gap:8px;';
      el.appendChild(listEl);
    }
    const resp = await this.getByEntity(table, id);
    const docs = resp.data || [];
    listEl.innerHTML = docs.map(d => `
      <div style="background:#f1f5f9;border-radius:10px;padding:8px 12px;
        font-size:13px;display:flex;align-items:center;gap:6px;">
        <span>${TaiDocument.getFileIcon(d.file_ext)}</span>
        <a href="#" onclick="event.preventDefault();window._taiDoc&&window._taiDoc.download('${d.id}')">
          ${d.file_name}</a>
        <span style="color:#94a3b8;">${TaiDocument.formatFileSize(d.file_size)}</span>
      </div>
    `).join('');
    window._taiDoc = this;
  }

  // === 유틸 ===
  static formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
  }

  static getFileIcon(ext) {
    const map = {
      pdf: '📄', doc: '📝', docx: '📝', hwp: '📝',
      xls: '📊', xlsx: '📊', csv: '📊',
      jpg: '🖼️', jpeg: '🖼️', png: '🖼️', webp: '🖼️', heic: '🖼️',
      zip: '📦', pptx: '📊', txt: '📃'
    };
    return map[(ext || '').toLowerCase()] || '📎';
  }

  static isImage(mime) { return (mime || '').startsWith('image/'); }
  static isPreviewable(mime) {
    return TaiDocument.isImage(mime) || mime === 'application/pdf';
  }
}

// 모듈 export (CommonJS/ESM/전역)
if (typeof module !== 'undefined' && module.exports) module.exports = TaiDocument;
else if (typeof window !== 'undefined') window.TaiDocument = TaiDocument;
```

---

## 검증 체크리스트

### 백엔드
- [ ] `POST /documents/upload` — 단일 파일 업로드 + documents 레코드 생성 확인
- [ ] `POST /documents/upload-multiple` — 다중 파일
- [ ] `GET /documents?company_id=...&category=inspection` — 필터링
- [ ] `GET /documents/{id}/download` — signed URL 정상 반환
- [ ] `DELETE /documents/{id}` — soft delete (is_active=false, deleted_at 설정)
- [ ] `GET /documents/stats?company_id=...` — v_document_stats 뷰 정상
- [ ] `GET /documents/by-entity/inspections/{id}` — 폴리모픽 연결 조회
- [ ] Storage 경로: `{company_id}/{category}/{YYYY-MM}/{uuid}.{ext}` 형식 확인

### 프론트엔드
- [ ] `new TaiDocument({...})` 초기화
- [ ] `createUploadZone` — 드래그앤드롭 동작
- [ ] `createAttachmentWidget` — 업로드 + 목록 표시
- [ ] `download` — signed URL → 브라우저 다운로드
- [ ] 모바일 (375px) — 업로드 영역 터치 반응

---

## main.py 등록

```python
from routers.documents import router as documents_router
# 인증 필요 그룹에 추가
app.include_router(documents_router)
```

버전 bump: ENGINE_VERSION → 현재 버전 + 0.1

커밋 메시지: `feat: 통합 문서 관리 모듈 v1.0.0 (service + router + frontend)`
push to dev
