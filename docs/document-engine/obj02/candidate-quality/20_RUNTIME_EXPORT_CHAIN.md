---
title: Runtime Export Chain — Gate X1
description: Trace of POST /document-engine/documents/{id}/generate through to PDF output
type: evidence
wo: WO-DOC-OBJ02-C1-SUPPLEMENTAL-CONTRACT-VERIFY-002
status: COLLECTED
gate: X1
---

# Runtime Export Chain — Gate X1

## Frontend Call Site

`tai-admin/vue3/src/pages/document-forms/useDocumentFormsGenerate.ts`

```typescript
async function postGenerate(exportType = 'pdf'): Promise<any> {
    const docId = await ensureRuntimeDocument()
    await syncRuntimeFields()
    const resp = await api.request('POST', `/document-engine/documents/${docId}/generate`, { export_type: exportType })
    return extractPdfUrl(resp?.data ?? resp)
}
```

`extractPdfUrl()` tries: `pdf_url || file_url || url || signed_url || download_url || storage_url || output_url`

## NEW Path: `/document-engine/documents/{id}/generate`

### Router

`routers/document_engine_api.py:221`

```python
@router.post("/documents/{doc_id}/generate")
def generate_document(doc_id: str, body: GenerateDocumentIn):
    result = svc.generate_document(doc_id, body.export_type)
    return {"status": "success", "data": result}
```

### Service

`services/document_engine_svc.py:generate_document()` (line 369)

```python
def generate_document(doc_id: str, export_type: str = "HTML") -> dict:
    """입력된 값만 사용. auto fill / inferred summary 금지."""
    sb = get_supabase()
    doc = sb.table("runtime_document_data").select("*").eq("id", doc_id).single().execute()
    if not doc.data:
        raise ValueError("document not found")
    record = {
        "runtime_document_id": doc_id,
        "form_schema_id": doc.data.get("form_schema_id"),
        "export_type": export_type,
        "status": "PENDING",  # WP-DOCUMENT-ARCH-03C: ...
    }
    res = sb.table("generated_document").insert(record).execute()
    gen = res.data[0] if res.data else {}
    if gen:
        _audit(sb, doc_id, "CREATED", None, None, gen)
    return gen
```

### Response Shape

```json
{
  "id": "<uuid>",
  "runtime_document_id": "<doc_id>",
  "form_schema_id": "<schema_id>",
  "export_type": "pdf",
  "status": "PENDING",
  "created_at": "<timestamp>"
}
```

**No PDF URL in response.** `extractPdfUrl()` returns `undefined`. Frontend receives no download URL.

### Renderer Call

NONE. `generate_document()` creates a PENDING stub record only. `document_schema_renderer.py` is NOT called from this path. No PDF bytes are produced.

---

## OLD Path: `/document-forms/{doc_id}/generate`

### Router

`routers/document_engine.py:70` (prefix `/document-forms`)

```python
_FETCHERS = {
    "DOC-OSH-056": TbmFetcher(),
    # TODO: 추가 패철 등록
}

@router.post("/{doc_id}/generate")
async def generate_document(doc_id: str, req: GenerateRequest):
    fetcher = _FETCHERS.get(doc_id)
    if not fetcher:
        raise HTTPException(404, f"No fetcher registered for {doc_id}")
    ...
    pdf_bytes = await generate_document_pdf(doc_id, data)
    return Response(content=pdf_bytes, media_type="application/pdf", ...)
```

**FINDING**: The OLD path DOES call the renderer and produces PDF bytes. BUT:
1. It is only accessible via `POST /document-forms/{doc_id}/generate` (not `/document-engine/documents/{id}/generate`)
2. Only `DOC-OSH-056` (TBM) has a registered fetcher. All other 23 P0 docs return 404.
3. The frontend calls the NEW path (`/document-engine/documents/${docId}/generate`), NOT the OLD path.
4. The OLD path takes `factory_id + date range + meeting_id` as input — NOT `runtime_data_json`.

---

## Export Chain Assessment

| Step | NEW path | OLD path (DOC-OSH-056 only) |
|------|----------|------------------------------|
| Frontend calls | `/document-engine/documents/{id}/generate` | NOT called by frontend |
| Fetcher invoked | NO | YES (TbmFetcher) |
| Renderer invoked | NO | YES (generate_document_pdf) |
| PDF bytes produced | NO | YES (DOC-OSH-056 only) |
| PDF URL in response | NO | YES (as binary Response, not URL) |
| runtime_data_json consumed | NO | NO (fetcher reads from DB directly) |

## Conclusion

**Gate X1: EXPORT CHAIN BROKEN**

- `POST /document-engine/documents/{id}/generate` produces only a PENDING stub. No renderer call. No PDF.
- Frontend `postGenerate()` cannot extract a PDF URL.
- The renderer-connected OLD path (`/document-forms/{doc_id}/generate`) is not called by the frontend and covers only DOC-OSH-056.
- Result: All 24 P0 documents have a broken PDF export path for the runtime document workflow.

Commit reference: `7c93c939` — "fix(document-engine): generate_document() writes PENDING not GENERATED (WO-DOCUMENT-ARCH-03C)". The PENDING-only behavior is intentional per the comment: "object 미생성 상태이므로 GENERATED 금지 (pre-DDL compat). 실제 완료는 output/snapshot 계약(Q5)에서 GENERATED 승격." Q5 (output/snapshot contract) has not been implemented.
