"""WO-MSDS-04A-PATCH-002 — MSDS Document Intake 단위 테스트.

FakeSupabase 격리 — 운영 DB/네트워크/Storage 불사용.
leg-prod reference_svc: unittest.mock.patch 으로 격리.
No pytest-asyncio — asyncio.run() 패턴 사용.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from services import msds_intake_svc as svc
from services import msds_fact_extractor as extractor
from services import msds_reference_svc as ref_svc
from services.msds_product_svc import MsdsProductError


def _run(coro):
    """Sync wrapper for async service calls."""
    return asyncio.run(coro)


# ─── FakeSupabase (extended from test_msds_versions pattern) ──────────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _FakeBucket:
    """Fake Storage bucket — tracks uploads/removes/downloads."""
    def __init__(self):
        self.uploads: list = []
        self.removes: list = []
        self._store: dict = {}  # path → bytes

    def upload(self, path, file, file_options=None):
        self.uploads.append(path)
        self._store[path] = file if isinstance(file, bytes) else b""

    def download(self, path):
        if path not in self._store:
            raise Exception(f"path not found: {path}")
        return self._store[path]

    def remove(self, paths):
        self.removes.extend(paths)
        for p in paths:
            self._store.pop(p, None)

    def create_signed_url(self, path, expires_in=3600):
        return {"signedURL": f"https://fake/{path}"}


class _FakeStorageRoot:
    def __init__(self):
        self._buckets: dict = {}

    def from_(self, bucket_name):
        if bucket_name not in self._buckets:
            self._buckets[bucket_name] = _FakeBucket()
        return self._buckets[bucket_name]


class _Query:
    def __init__(self, store, table, log, hooks=None):
        self.store = store
        self.table_name = table
        self.log = log
        self._hooks = hooks or {}
        self._op = None
        self._payload = None
        self._filters = []
        self._cols = "*"
        self._limit_n = None
        self._order_col = None
        self._order_desc = False
        self._count_mode = None
        self._upsert_on_conflict = None

    def select(self, cols="*", *a, **k):
        self._op = "select"
        self._cols = cols or "*"
        self._count_mode = k.get("count")
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, patch):
        self._op = "update"
        self._payload = patch
        return self

    def upsert(self, row, on_conflict=None):
        self._op = "upsert"
        self._payload = row
        self._upsert_on_conflict = on_conflict
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, c, v):
        self._filters.append(("eq", c, v))
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def order(self, col, desc=False, **k):
        self._order_col = col
        self._order_desc = desc
        return self

    def _match(self, row):
        for op, c, v in self._filters:
            rv = row.get(c)
            if op == "eq":
                if isinstance(v, bool) or isinstance(rv, bool):
                    if bool(rv) != bool(v):
                        return False
                elif str(rv) != str(v):
                    return False
        return True

    def _project(self, row):
        if not self._cols or self._cols == "*":
            return dict(row)
        keys = [c.strip().split(":")[0] for c in self._cols.split(",") if c.strip()]
        return {k: row.get(k) for k in keys if k}

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        self.log.append((self.table_name, self._op))

        if self._op == "select":
            matched = [self._project(r) for r in rows if self._match(r)]
            if self._order_col:
                matched.sort(key=lambda r: (r.get(self._order_col) is None, r.get(self._order_col) or 0), reverse=self._order_desc)
            if self._limit_n is not None:
                matched = matched[:self._limit_n]
            cnt = len([r for r in rows if self._match(r)]) if self._count_mode == "exact" else None
            return _Result(matched, count=cnt)

        if self._op == "insert":
            hook = self._hooks.get((self.table_name, "insert"))
            if hook is not None:
                return hook(self._payload)
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            out = []
            for it in items:
                it = dict(it)
                it.setdefault("id", str(uuid.uuid4()))
                rows.append(it)
                out.append(dict(it))
            return _Result(out)

        if self._op == "update":
            matched = [r for r in rows if self._match(r)]
            for r in matched:
                r.update(self._payload)
            return _Result([dict(r) for r in matched])

        if self._op == "upsert":
            existing = next((r for r in rows if self._match(r)), None)
            if existing:
                existing.update(self._payload)
                return _Result([dict(existing)])
            else:
                it = dict(self._payload)
                it.setdefault("id", str(uuid.uuid4()))
                rows.append(it)
                return _Result([dict(it)])

        if self._op == "delete":
            self.store[self.table_name] = [r for r in rows if not self._match(r)]
            return _Result([])

        return _Result([])


class FakeSB:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []
        self._rpc_overrides: Dict[str, Any] = {}
        self._table_hooks: Dict[tuple, Any] = {}
        self.storage = _FakeStorageRoot()

    def table(self, name):
        return _Query(self.store, name, self.log, self._table_hooks)

    def set_rpc_override(self, fn_name: str, result: Any):
        self._rpc_overrides[fn_name] = result

    def set_insert_hook(self, table_name: str, fn):
        self._table_hooks[(table_name, "insert")] = fn

    def rpc(self, fn_name: str, params: dict):
        if fn_name in self._rpc_overrides:
            override = self._rpc_overrides[fn_name]
            if callable(override):
                return _FakeRpcResult(override(params))
            return _FakeRpcResult(override)

        if fn_name == "register_customer_msds_version":
            return _FakeRpcResult(self._fake_register(params))
        if fn_name == "promote_customer_msds_version":
            return _FakeRpcResult(self._fake_promote(params))
        if fn_name == "void_customer_msds_version":
            return _FakeRpcResult({"status": "VOIDED"})
        return _FakeRpcResult({"status": "UNKNOWN_RPC"})

    def _fake_register(self, p: dict) -> dict:
        from datetime import datetime
        fid = str(p.get("p_factory_id", ""))
        pid = str(p.get("p_chemical_product_id", ""))
        doc_id = str(p.get("p_document_id", ""))
        sha256 = str(p.get("p_content_sha256", ""))

        products = self.store.get("chemical_products", [])
        if not any(str(r.get("id")) == pid and str(r.get("factory_id")) == fid for r in products):
            return {"status": "PRODUCT_NOT_FOUND"}

        docs = self.store.get("documents", [])
        doc = next((d for d in docs if str(d.get("id")) == doc_id), None)
        if not doc:
            return {"status": "DOCUMENT_NOT_FOUND"}
        if not doc.get("is_active", True):
            return {"status": "DOCUMENT_INACTIVE"}
        if doc.get("category") != "msds":
            return {"status": "DOCUMENT_INVALID_CATEGORY"}
        if str(doc.get("factory_id", "")) != fid:
            return {"status": "DOCUMENT_FACTORY_MISMATCH"}
        if doc.get("linked_table") != "chemical_products":
            return {"status": "DOCUMENT_LINKED_TABLE_MISMATCH"}
        if str(doc.get("linked_id", "")) != pid:
            return {"status": "DOCUMENT_LINKED_ID_MISMATCH"}

        versions = self.store.setdefault("customer_msds_versions", [])
        if any(str(v.get("document_id")) == doc_id for v in versions):
            return {"status": "DOCUMENT_ALREADY_USED"}

        existing = next(
            (v for v in versions if str(v.get("chemical_product_id")) == pid
             and v.get("content_sha256") == sha256), None
        )
        if existing:
            return {
                "status": "NO_CHANGE",
                "version_id": existing["id"],
                "version_no": existing["version_no"],
                "is_current": existing["is_current"],
                "record_status": existing["record_status"],
            }

        existing_nos = [v.get("version_no", 0) for v in versions
                        if str(v.get("chemical_product_id")) == pid]
        v_no = max(existing_nos, default=0) + 1
        active_count = sum(
            1 for v in versions
            if str(v.get("chemical_product_id")) == pid and v.get("record_status") == "ACTIVE"
        )
        is_first = active_count == 0
        new_id = str(uuid.uuid4())
        row = {
            "id": new_id,
            "factory_id": fid,
            "chemical_product_id": pid,
            "document_id": doc_id,
            "version_no": v_no,
            "content_sha256": sha256,
            "is_current": is_first,
            "record_status": "ACTIVE",
            "created_at": datetime.utcnow().isoformat(),
        }
        versions.append(row)
        return {"status": "NEW_VERSION", "version_id": new_id, "version_no": v_no, "is_current": is_first, "record_status": "ACTIVE"}

    def _fake_promote(self, p: dict) -> dict:
        return {"status": "PROMOTED"}


class _FakeRpcResult:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


# ─── Constants ────────────────────────────────────────────────────────────────

CO_A = "company-a"
CO_B = "company-b"
FAC_A1 = str(uuid.uuid4())
FAC_A2 = str(uuid.uuid4())
FAC_B  = str(uuid.uuid4())
PROD_A1_1 = str(uuid.uuid4())
PROD_A1_2 = str(uuid.uuid4())
USER_A = {"id": "user-a", "company_id": CO_A, "role_code": "010"}
USER_B = {"id": "user-b", "company_id": CO_B, "role_code": "010"}
USER_FAC_A1 = {"id": "user-fac-a1", "company_id": CO_A, "role_code": "012", "factory_id": FAC_A1}

_ROLE_DATA_SCOPE = [
    {"role_code": "010", "scope_type": "COMPANY"},
    {"role_code": "012", "scope_type": "FACTORY"},
    {"role_code": "013", "scope_type": "TEAM"},
    {"role_code": "020", "scope_type": "ASSIGNED"},
    {"role_code": "099", "scope_type": "ALL"},
]

_FACTORIES = [
    {"id": FAC_A1, "company_id": CO_A, "name": "A사 1공장"},
    {"id": FAC_A2, "company_id": CO_A, "name": "A사 2공장"},
    {"id": FAC_B,  "company_id": CO_B, "name": "B사 공장"},
]

_PRODUCTS = [
    {
        "id": PROD_A1_1,
        "factory_id": FAC_A1,
        "product_name": "염산",
        "product_name_normalized": "염산",
        "manufacturer_normalized": "제조사a",
        "manufacturer_name": "제조사A",
        "identity_status": "DRAFT",
        "status_code": "ACTIVE",
        "created_source": "MANUAL",
    },
    {
        "id": PROD_A1_2,
        "factory_id": FAC_A1,
        "product_name": "황산",
        "product_name_normalized": "황산",
        "manufacturer_normalized": None,
        "manufacturer_name": None,
        "identity_status": "DRAFT",
        "status_code": "ACTIVE",
        "created_source": "MANUAL",
    },
]

PDF_BYTES = b"%PDF-1.4 test intake content " + b"x" * 100

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _make_sb(extra=None):
    store = {
        "factories": list(_FACTORIES),
        "role_data_scope": list(_ROLE_DATA_SCOPE),
        "chemical_products": [dict(p) for p in _PRODUCTS],
        "documents": [],
        "customer_msds_versions": [],
        "msds_intakes": [],
        "msds_intake_artifacts": [],
        "msds_intake_facts": [],
        "msds_match_candidates": [],
        "msds_reference_links": [],
        "chemical_product_identifiers": [],
    }
    if extra:
        store.update(extra)
    return FakeSB(store)


# ─── Helper: make a valid intake in RECEIVED state ───────────────────────────

def _make_received_intake(sb, user=None, factory_id=None, file_bytes=None):
    user = user or USER_A
    factory_id = factory_id or FAC_A1
    file_bytes = file_bytes or PDF_BYTES
    result = svc.create_intake(
        sb=sb, current_user=user, factory_id=factory_id,
        file_bytes=file_bytes, file_name="test.pdf", mime_type="application/pdf",
    )
    return result["intake"]


# ─── INT: Intake Create Tests ─────────────────────────────────────────────────

def test_int01_create_intake_success():
    """INT01: create_intake succeeds for valid PDF, returns intake + artifact."""
    sb = _make_sb()
    result = svc.create_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
    )
    assert result["duplicate"] is False
    assert result["intake"]["status"] == "RECEIVED"
    assert result["intake"]["factory_id"] == FAC_A1
    assert result["artifact"]["content_sha256"] == _sha(PDF_BYTES)
    bucket = sb.storage.from_("company-docs")
    assert len(bucket.uploads) == 1


def test_int02_duplicate_finalized_sha_returns_duplicate():
    """INT02: Uploading same SHA as a FINALIZED intake returns duplicate=True."""
    sb = _make_sb()
    sha = _sha(PDF_BYTES)
    fin_id = str(uuid.uuid4())
    sb.store["msds_intakes"].append({
        "id": fin_id, "factory_id": FAC_A1, "status": "FINALIZED",
        "final_msds_version_id": str(uuid.uuid4()),
    })
    sb.store["msds_intake_artifacts"].append({
        "id": str(uuid.uuid4()), "intake_id": fin_id, "content_sha256": sha,
    })
    result = svc.create_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
    )
    assert result["duplicate"] is True


def test_int03_auth_deny_wrong_company():
    """INT03: User from company B cannot create intake for company A factory."""
    sb = _make_sb()
    with pytest.raises(MsdsProductError) as exc:
        svc.create_intake(
            sb=sb, current_user=USER_B, factory_id=FAC_A1,
            file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
        )
    assert exc.value.status_code in (403, 404)


def test_int04_invalid_pdf_rejected():
    """INT04: Non-PDF bytes raise INVALID_MSDS_PDF."""
    sb = _make_sb()
    with pytest.raises(MsdsProductError) as exc:
        svc.create_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            file_bytes=b"NOT A PDF", file_name="msds.pdf", mime_type="application/pdf",
        )
    assert exc.value.code == "INVALID_MSDS_PDF"


def test_int05_factory_not_found():
    """INT05: Unknown factory_id raises 404."""
    sb = _make_sb()
    unknown_fac = str(uuid.uuid4())
    with pytest.raises(MsdsProductError) as exc:
        svc.create_intake(
            sb=sb, current_user=USER_A, factory_id=unknown_fac,
            file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
        )
    assert exc.value.status_code in (403, 404)


def test_int06_get_intake_success():
    """INT06: get_intake returns intake row for authorised user."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    fetched = svc.get_intake(sb, USER_A, FAC_A1, intake["id"])
    assert fetched["id"] == intake["id"]


def test_int07_get_intake_not_found():
    """INT07: get_intake with unknown id raises 404."""
    sb = _make_sb()
    with pytest.raises(MsdsProductError) as exc:
        svc.get_intake(sb, USER_A, FAC_A1, str(uuid.uuid4()))
    assert exc.value.status_code == 404


def test_int08_get_intake_wrong_factory_denied():
    """INT08: get_intake for intake belonging to different factory raises 404."""
    sb = _make_sb()
    intake = _make_received_intake(sb, factory_id=FAC_A1)
    with pytest.raises(MsdsProductError) as exc:
        svc.get_intake(sb, USER_A, FAC_A2, intake["id"])
    assert exc.value.status_code == 404


# ─── STG: Storage Compensation Tests ──────────────────────────────────────────

def test_stg01_storage_upload_failure_fails_intake():
    """STG01: Storage upload failure → intake status FAILED."""
    sb = _make_sb()
    # Make storage upload raise
    def _fail_upload(*a, **kw):
        raise RuntimeError("S3 unavailable")

    sb.storage.from_("company-docs").upload = _fail_upload

    with pytest.raises(MsdsProductError) as exc:
        svc.create_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
        )
    assert exc.value.code == "STORAGE_UPLOAD_FAILED"
    intake = sb.store["msds_intakes"][0]
    assert intake["status"] == "FAILED"
    assert intake["error_code"] == "STORAGE_UPLOAD_FAILED"


def test_stg02_artifact_insert_exception_cleans_storage():
    """STG02: Storage success + artifact INSERT exception → storage removed + intake FAILED."""
    sb = _make_sb()

    def _raise_on_artifact(payload):
        raise RuntimeError("DB insert failed")

    sb.set_insert_hook("msds_intake_artifacts", _raise_on_artifact)

    with pytest.raises(MsdsProductError) as exc:
        svc.create_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
        )
    assert exc.value.code == "ARTIFACT_CREATE_FAILED"
    # Storage should be cleaned up
    bucket = sb.storage.from_("company-docs")
    assert len(bucket.removes) == 1
    assert len(bucket._store) == 0
    # Intake marked FAILED
    intake = sb.store["msds_intakes"][0]
    assert intake["status"] == "FAILED"


def test_stg03_artifact_insert_empty_cleans_storage():
    """STG03: Storage success + artifact INSERT returns empty data → storage removed + intake FAILED."""
    sb = _make_sb()

    def _empty_insert(payload):
        return _Result([])

    sb.set_insert_hook("msds_intake_artifacts", _empty_insert)

    with pytest.raises(MsdsProductError) as exc:
        svc.create_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
        )
    assert exc.value.code == "ARTIFACT_CREATE_FAILED"
    bucket = sb.storage.from_("company-docs")
    assert len(bucket.removes) == 1
    intake = sb.store["msds_intakes"][0]
    assert intake["status"] == "FAILED"


def test_stg04_no_orphan_on_success():
    """STG04: Successful create_intake leaves no orphaned storage objects."""
    sb = _make_sb()
    svc.create_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        file_bytes=PDF_BYTES, file_name="msds.pdf", mime_type="application/pdf",
    )
    bucket = sb.storage.from_("company-docs")
    assert len(bucket.removes) == 0
    assert len(bucket._store) == 1


# ─── TXT: Extractor Tests ─────────────────────────────────────────────────────

def test_txt01_empty_bytes_ocr_required():
    """TXT01: Empty bytes (no PDF reader) should return error or ocr_required."""
    result = extractor.extract_facts(b"")
    assert result.error is not None or result.ocr_required


def test_txt02_valid_pdf_but_no_text_ocr_required():
    """TXT02: PDF with no extractable text yields ocr_required=True."""
    with patch("services.msds_fact_extractor.PdfReader") as MockReader:
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_reader.pages = [mock_page]
        MockReader.return_value = mock_reader
        result = extractor.extract_facts(b"%PDF-fake")
    assert result.ocr_required is True
    assert result.facts == []


def test_txt03_product_name_extracted():
    """TXT03: PDF with '제품명: 염산' yields PRODUCT_NAME fact."""
    text = "제품명: 염산\n제조사: 주식회사A\n"
    with patch("services.msds_fact_extractor.PdfReader") as MockReader:
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = text
        mock_reader.pages = [mock_page]
        MockReader.return_value = mock_reader
        result = extractor.extract_facts(b"%PDF-fake")
    pnames = [f for f in result.facts if f["fact_type"] == "PRODUCT_NAME"]
    assert len(pnames) >= 1
    assert "염산" in pnames[0]["raw_value"]


def test_txt04_cas_extracted_via_context():
    """TXT04: CAS number near '구성 성분' context is extracted."""
    text = "구성 성분:\n물질명: 염화수소\nCAS No: 7647-01-0\n"
    with patch("services.msds_fact_extractor.PdfReader") as MockReader:
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = text
        mock_reader.pages = [mock_page]
        MockReader.return_value = mock_reader
        result = extractor.extract_facts(b"%PDF-fake")
    cas = [f for f in result.facts if f["fact_type"] == "CAS"]
    assert len(cas) >= 1
    assert cas[0]["normalized_value"] == "7647-01-0"


def test_txt05_cas_fallback_without_context():
    """TXT05: CAS number in document without section context is still extracted."""
    text = "Material Info\n7647-01-0 is the CAS number\n"
    with patch("services.msds_fact_extractor.PdfReader") as MockReader:
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = text
        mock_reader.pages = [mock_page]
        MockReader.return_value = mock_reader
        result = extractor.extract_facts(b"%PDF-fake")
    cas = [f for f in result.facts if f["fact_type"] == "CAS"]
    assert len(cas) >= 1


def test_txt06_manufacturer_extracted():
    """TXT06: PDF with '제조사: 주식회사A' yields MANUFACTURER_NAME fact."""
    text = "제품명: 황산\n제조사: 주식회사A\n"
    with patch("services.msds_fact_extractor.PdfReader") as MockReader:
        mock_reader = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = text
        mock_reader.pages = [mock_page]
        MockReader.return_value = mock_reader
        result = extractor.extract_facts(b"%PDF-fake")
    mfrs = [f for f in result.facts if f["fact_type"] == "MANUFACTURER_NAME"]
    assert len(mfrs) >= 1
    assert "주식회사a" in mfrs[0]["normalized_value"]


# ─── PC: Product Candidate Tests ──────────────────────────────────────────────

def test_pc01_exact_name_manufacturer_match():
    """PC01: Exact product_name_normalized + manufacturer_normalized yields EXACT_NAME_MANUFACTURER candidate."""
    sb = _make_sb()
    facts = [
        {"fact_type": "PRODUCT_NAME", "normalized_value": "염산"},
        {"fact_type": "MANUFACTURER_NAME", "normalized_value": "제조사a"},
    ]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    reasons = [c["match_reason"] for c in candidates]
    assert "EXACT_NAME_MANUFACTURER" in reasons
    pids = [c["candidate_product_id"] for c in candidates]
    assert PROD_A1_1 in pids


def test_pc02_exact_name_only_match():
    """PC02: Exact product_name_normalized without manufacturer yields EXACT_NAME."""
    sb = _make_sb()
    facts = [{"fact_type": "PRODUCT_NAME", "normalized_value": "황산"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    reasons = [c["match_reason"] for c in candidates]
    assert "EXACT_NAME" in reasons
    pids = [c["candidate_product_id"] for c in candidates]
    assert PROD_A1_2 in pids


def test_pc03_no_match_returns_empty():
    """PC03: No matching product in factory yields empty candidates list."""
    sb = _make_sb()
    facts = [{"fact_type": "PRODUCT_NAME", "normalized_value": "알수없는물질"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    assert candidates == []


def test_pc04_exact_identifier_ean_typed_match():
    """PC04: EAN fact with matching identifier_type=EAN yields EXACT_IDENTIFIER candidate."""
    sb = _make_sb()
    sb.store["chemical_product_identifiers"].append({
        "id": str(uuid.uuid4()),
        "chemical_product_id": PROD_A1_1,
        "factory_id": FAC_A1,
        "identifier_type": "EAN",
        "identifier_normalized": "1234567890123",
        "is_active": True,
    })
    facts = [{"fact_type": "EAN", "normalized_value": "1234567890123"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    reasons = [c["match_reason"] for c in candidates]
    assert "EXACT_IDENTIFIER" in reasons
    pids = [c["candidate_product_id"] for c in candidates]
    assert PROD_A1_1 in pids


def test_pc05_cross_factory_isolation():
    """PC05: Product in FAC_B is not returned when searching FAC_A1."""
    sb = _make_sb()
    sb.store["chemical_products"].append({
        "id": str(uuid.uuid4()),
        "factory_id": FAC_B,
        "product_name": "염산",
        "product_name_normalized": "염산",
        "manufacturer_normalized": "제조사b",
        "status_code": "ACTIVE",
    })
    facts = [{"fact_type": "PRODUCT_NAME", "normalized_value": "염산"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    for c in candidates:
        pid = c["candidate_product_id"]
        prod = next(p for p in sb.store["chemical_products"] if p["id"] == pid)
        assert prod["factory_id"] == FAC_A1


def test_pc06_cas_is_not_product_identifier():
    """PC06: CAS fact does NOT produce EXACT_IDENTIFIER product candidate."""
    sb = _make_sb()
    sb.store["chemical_product_identifiers"].append({
        "id": str(uuid.uuid4()),
        "chemical_product_id": PROD_A1_1,
        "factory_id": FAC_A1,
        "identifier_type": "EAN",
        "identifier_normalized": "7647-01-0",  # same value as CAS but wrong type
        "is_active": True,
    })
    facts = [{"fact_type": "CAS", "normalized_value": "7647-01-0"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    # CAS fact must not produce EXACT_IDENTIFIER
    exact_id_cands = [c for c in candidates if c["match_reason"] == "EXACT_IDENTIFIER"]
    assert exact_id_cands == []


def test_pc07_wrong_identifier_type_no_match():
    """PC07: EAN value in DB but fact_type=BARCODE → no EXACT_IDENTIFIER match."""
    sb = _make_sb()
    sb.store["chemical_product_identifiers"].append({
        "id": str(uuid.uuid4()),
        "chemical_product_id": PROD_A1_1,
        "factory_id": FAC_A1,
        "identifier_type": "EAN",
        "identifier_normalized": "1234567890123",
        "is_active": True,
    })
    facts = [{"fact_type": "BARCODE", "normalized_value": "1234567890123"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    # BARCODE fact must only match identifier_type=BARCODE
    eid_cands = [c for c in candidates if c["match_reason"] == "EXACT_IDENTIFIER"]
    # No BARCODE-typed identifier in DB → no match
    assert eid_cands == []


def test_pc08_barcode_typed_match():
    """PC08: BARCODE fact with matching identifier_type=BARCODE yields EXACT_IDENTIFIER."""
    sb = _make_sb()
    sb.store["chemical_product_identifiers"].append({
        "id": str(uuid.uuid4()),
        "chemical_product_id": PROD_A1_1,
        "factory_id": FAC_A1,
        "identifier_type": "BARCODE",
        "identifier_normalized": "9876543210",
        "is_active": True,
    })
    facts = [{"fact_type": "BARCODE", "normalized_value": "9876543210"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    eid_cands = [c for c in candidates if c["match_reason"] == "EXACT_IDENTIFIER"]
    assert len(eid_cands) == 1
    assert eid_cands[0]["candidate_product_id"] == PROD_A1_1


def test_pc09_same_value_wrong_type_no_match():
    """PC09: Same identifier value but mismatched identifier_type → no match."""
    sb = _make_sb()
    sb.store["chemical_product_identifiers"].append({
        "id": str(uuid.uuid4()),
        "chemical_product_id": PROD_A1_1,
        "factory_id": FAC_A1,
        "identifier_type": "GTIN",
        "identifier_normalized": "00012345678905",
        "is_active": True,
    })
    facts = [{"fact_type": "EAN", "normalized_value": "00012345678905"}]
    candidates = svc._find_product_candidates(sb, FAC_A1, facts)
    eid_cands = [c for c in candidates if c["match_reason"] == "EXACT_IDENTIFIER"]
    assert eid_cands == []


# ─── RC: Reference Candidate Tests ────────────────────────────────────────────

SNAPSHOT_ID = "0ad73e46-d61b-474d-a90e-5b5ab8080d80"

def _mock_ref_find(hits):
    return patch("services.msds_intake_svc.ref_svc.find_reference_candidates", return_value=hits)


def test_rc01_reference_candidate_cas_match():
    """RC01: CAS match from ref_svc is returned as REFERENCE candidate."""
    hits = [{
        "reference_content_id": "REF-001", "reference_chem_id": "CHEM-001",
        "reference_snapshot_id": SNAPSHOT_ID, "cas_no": "7647-01-0",
        "match_reason": "EXACT_CAS", "rank_no": 1, "evidence_json": {"cas": "7647-01-0"},
    }]
    facts = [{"fact_type": "CAS", "normalized_value": "7647-01-0"}]
    with _mock_ref_find(hits):
        candidates = svc._find_reference_candidates(facts, SNAPSHOT_ID)
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "REFERENCE"
    assert candidates[0]["match_reason"] == "EXACT_CAS"
    assert candidates[0]["reference_content_id"] == "REF-001"


def test_rc02_reference_candidate_product_name_match():
    """RC02: Product name match from ref_svc is returned."""
    hits = [{
        "reference_content_id": "REF-002", "reference_chem_id": "CHEM-002",
        "reference_snapshot_id": SNAPSHOT_ID, "cas_no": None,
        "match_reason": "EXACT_REFERENCE_PRODUCT_NAME", "rank_no": 2,
        "evidence_json": {"product_name_normalized": "황산"},
    }]
    facts = [{"fact_type": "PRODUCT_NAME", "normalized_value": "황산"}]
    with _mock_ref_find(hits):
        candidates = svc._find_reference_candidates(facts, SNAPSHOT_ID)
    assert len(candidates) == 1
    assert candidates[0]["match_reason"] == "EXACT_REFERENCE_PRODUCT_NAME"


def test_rc03_reference_lookup_failure_propagates():
    """RC03: ref_svc exception propagates from _find_reference_candidates."""
    facts = [{"fact_type": "PRODUCT_NAME", "normalized_value": "황산"}]
    with patch("services.msds_intake_svc.ref_svc.find_reference_candidates", side_effect=RuntimeError("leg-prod down")):
        with pytest.raises(RuntimeError):
            svc._find_reference_candidates(facts, SNAPSHOT_ID)


def test_rc04_no_facts_no_candidates():
    """RC04: Empty facts list produces no reference candidates."""
    with _mock_ref_find([]):
        candidates = svc._find_reference_candidates([], SNAPSHOT_ID)
    assert candidates == []


def test_rc05_multiple_reference_hits():
    """RC05: Multiple reference hits are all returned."""
    hits = [
        {"reference_content_id": f"REF-{i}", "reference_chem_id": f"CHEM-{i}",
         "reference_snapshot_id": SNAPSHOT_ID, "cas_no": None,
         "match_reason": "EXACT_CAS", "rank_no": 1, "evidence_json": {}}
        for i in range(3)
    ]
    facts = [{"fact_type": "CAS", "normalized_value": "7647-01-0"}]
    with _mock_ref_find(hits):
        candidates = svc._find_reference_candidates(facts, SNAPSHOT_ID)
    assert len(candidates) == 3


def test_rc06_process_intake_stores_reference_candidates():
    """RC06: process_intake stores REFERENCE candidates in msds_match_candidates."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    text_facts = [
        {"fact_type": "PRODUCT_NAME", "raw_value": "염산", "normalized_value": "염산",
         "source_page": 1, "evidence_json": {}},
        {"fact_type": "CAS", "raw_value": "7647-01-0", "normalized_value": "7647-01-0",
         "source_page": 1, "evidence_json": {"cas": "7647-01-0"}},
    ]
    ref_hits = [{
        "reference_content_id": "REF-001", "reference_chem_id": "CHEM-001",
        "reference_snapshot_id": SNAPSHOT_ID, "cas_no": "7647-01-0",
        "match_reason": "EXACT_CAS", "rank_no": 1, "evidence_json": {"cas": "7647-01-0"},
    }]
    mock_result = MagicMock()
    mock_result.page_count = 2
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         _mock_ref_find(ref_hits):
        svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    ref_cands = [r for r in sb.store["msds_match_candidates"] if r.get("candidate_type") == "REFERENCE"]
    assert len(ref_cands) >= 1
    assert ref_cands[0]["reference_content_id"] == "REF-001"


def test_rc07_ocr_required_status():
    """RC07: PDF with no extractable text → status=OCR_REQUIRED."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = []
    mock_result.ocr_required = True
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result):
        result = svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert result["status"] == "OCR_REQUIRED"
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake_id)
    assert stored["status"] == "OCR_REQUIRED"


# ─── REF: Reference Service Table Tests ───────────────────────────────────────

def test_ref08_service_queries_public_view():
    """REF08: msds_reference_svc queries msds_ref_identity_projection_v (not identity_projection)."""
    import inspect
    source = inspect.getsource(ref_svc)
    assert "msds_ref_identity_projection_v" in source
    assert 'table("identity_projection")' not in source


def test_ref09_service_does_not_query_private_table():
    """REF09: msds_reference_svc does not directly query private msds_ref schema table."""
    import inspect
    source = inspect.getsource(ref_svc)
    # Should not contain direct reference to the private table name without the view prefix
    assert '"identity_projection"' not in source or "msds_ref_identity_projection_v" in source


def test_ref10_find_candidates_exception_propagates():
    """REF10: find_reference_candidates lets exceptions propagate (no silent catch)."""
    from unittest.mock import MagicMock, patch
    with patch("services.msds_reference_svc._get_leg_client", side_effect=RuntimeError("LEG_SUPABASE_URL not set")):
        with pytest.raises(RuntimeError):
            ref_svc.find_reference_candidates(SNAPSHOT_ID, [], None, None, None)


def test_ref11_verify_exception_propagates():
    """REF11: verify_reference_exists lets exceptions propagate (fail-closed)."""
    with patch("services.msds_reference_svc._get_leg_client", side_effect=RuntimeError("connection refused")):
        with pytest.raises(RuntimeError):
            ref_svc.verify_reference_exists(SNAPSHOT_ID, "REF-001")


# ─── CF: Confirm Tests ────────────────────────────────────────────────────────

def _make_review_required_intake(sb):
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    for r in sb.store["msds_intakes"]:
        if r["id"] == intake_id:
            r["status"] = "REVIEW_REQUIRED"
            break
    return intake


def test_cf01_confirm_existing_product():
    """CF01: confirm_intake with existing_product_id transitions to CONFIRMED."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake["id"],
        existing_product_id=PROD_A1_1, new_product=None,
        selected_reference_candidate_ids=[],
    )
    assert result["status"] == "CONFIRMED"
    assert result["selected_product_id"] == PROD_A1_1
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake["id"])
    assert stored["status"] == "CONFIRMED"
    assert stored["selected_product_id"] == PROD_A1_1


def test_cf02_confirm_new_product_creates_product():
    """CF02: confirm_intake with new_product creates Product via OBJ-02 contract."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake["id"],
        existing_product_id=None,
        new_product={"product_name": "신규물질", "manufacturer_name": "신규제조사"},
        selected_reference_candidate_ids=[],
    )
    assert result["status"] == "CONFIRMED"
    new_pid = result["new_product_created"]
    assert new_pid is not None
    # Product row created
    new_prod = next((p for p in sb.store["chemical_products"] if p["id"] == new_pid), None)
    assert new_prod is not None
    assert new_prod["product_name"] == "신규물질"
    # identity_status updated to CONFIRMED
    assert new_prod["identity_status"] == "CONFIRMED"
    # intake selected_product_id points to new product
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake["id"])
    assert stored["selected_product_id"] == new_pid


def test_cf03_confirm_conflict_existing_and_new():
    """CF03: Providing both existing_product_id and new_product raises 422."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake["id"],
            existing_product_id=PROD_A1_1,
            new_product={"product_name": "물질", "manufacturer_name": None},
            selected_reference_candidate_ids=[],
        )
    assert exc.value.code == "CONFIRM_PRODUCT_CONFLICT"


def test_cf04_confirm_no_product_raises_422():
    """CF04: Providing neither existing_product_id nor new_product raises 422."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake["id"],
            existing_product_id=None, new_product=None,
            selected_reference_candidate_ids=[],
        )
    assert exc.value.code == "CONFIRM_NO_PRODUCT"


def test_cf05_confirm_product_not_in_factory():
    """CF05: existing_product_id from different factory raises 404."""
    sb = _make_sb()
    intake_a2 = {"id": str(uuid.uuid4()), "factory_id": FAC_A2, "status": "REVIEW_REQUIRED",
                 "reference_snapshot_id": SNAPSHOT_ID}
    sb.store["msds_intakes"].append(intake_a2)
    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A2,
            intake_id=intake_a2["id"],
            existing_product_id=PROD_A1_1,  # belongs to FAC_A1
            new_product=None,
            selected_reference_candidate_ids=[],
        )
    assert exc.value.status_code == 404


def test_cf06_confirm_wrong_status_raises_409():
    """CF06: confirm_intake on a FINALIZED intake raises 409."""
    sb = _make_sb()
    fin_id = str(uuid.uuid4())
    sb.store["msds_intakes"].append({
        "id": fin_id, "factory_id": FAC_A1, "status": "FINALIZED",
    })
    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=fin_id,
            existing_product_id=PROD_A1_1, new_product=None,
            selected_reference_candidate_ids=[],
        )
    assert exc.value.code == "INTAKE_NOT_REVIEW_REQUIRED"


def test_cf07_confirm_marks_selected_candidates():
    """CF07: selected_reference_candidate_ids are marked SELECTED."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    intake_id = intake["id"]
    cand_id = str(uuid.uuid4())
    sb.store["msds_match_candidates"].append({
        "id": cand_id, "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "PENDING",
        "match_reason": "EXACT_CAS",
    })
    svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake_id,
        existing_product_id=PROD_A1_1, new_product=None,
        selected_reference_candidate_ids=[cand_id],
    )
    cand = next(r for r in sb.store["msds_match_candidates"] if r["id"] == cand_id)
    assert cand["decision_status"] == "SELECTED"


def test_cf08_confirm_auth_denied_cross_company():
    """CF08: User from company B cannot confirm intake of company A factory."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_B, factory_id=FAC_A1,
            intake_id=intake["id"],
            existing_product_id=PROD_A1_1, new_product=None,
            selected_reference_candidate_ids=[],
        )
    assert exc.value.status_code in (403, 404)


def test_cf09_confirm_invalid_reference_candidate_id_raises_422():
    """CF09: selected_reference_candidate_ids with nonexistent ID raises 422."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    bad_cand_id = str(uuid.uuid4())
    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake["id"],
            existing_product_id=PROD_A1_1, new_product=None,
            selected_reference_candidate_ids=[bad_cand_id],
        )
    assert exc.value.code == "REFERENCE_CANDIDATE_INVALID"


def test_cf10_confirm_customer_product_candidate_as_reference_raises_422():
    """CF10: Passing a CUSTOMER_PRODUCT candidate ID as reference raises 422."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    intake_id = intake["id"]
    cand_id = str(uuid.uuid4())
    sb.store["msds_match_candidates"].append({
        "id": cand_id, "intake_id": intake_id,
        "candidate_type": "CUSTOMER_PRODUCT",  # wrong type
        "decision_status": "PENDING", "match_reason": "EXACT_NAME",
    })
    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake_id,
            existing_product_id=PROD_A1_1, new_product=None,
            selected_reference_candidate_ids=[cand_id],
        )
    assert exc.value.code == "REFERENCE_CANDIDATE_INVALID"


# ─── NP: New Product End-to-End Tests ─────────────────────────────────────────

def test_np01_new_product_confirm_calls_create_product():
    """NP01: new_product confirm calls OBJ-02 create_product."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    initial_count = len(sb.store["chemical_products"])
    svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake["id"],
        existing_product_id=None,
        new_product={"product_name": "벤젠", "manufacturer_name": "화학사"},
        selected_reference_candidate_ids=[],
    )
    assert len(sb.store["chemical_products"]) == initial_count + 1


def test_np02_new_product_identity_status_confirmed():
    """NP02: New Product from intake confirm has identity_status=CONFIRMED."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake["id"],
        existing_product_id=None,
        new_product={"product_name": "벤젠", "manufacturer_name": None},
        selected_reference_candidate_ids=[],
    )
    new_pid = result["new_product_created"]
    prod = next(p for p in sb.store["chemical_products"] if p["id"] == new_pid)
    assert prod["identity_status"] == "CONFIRMED"


def test_np03_new_product_selected_product_id_set():
    """NP03: intake.selected_product_id is set to new product ID."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake["id"],
        existing_product_id=None,
        new_product={"product_name": "톨루엔", "manufacturer_name": None},
        selected_reference_candidate_ids=[],
    )
    new_pid = result["new_product_created"]
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake["id"])
    assert stored["selected_product_id"] == new_pid


def test_np04_new_product_finalize_succeeds():
    """NP04: New Product confirm → finalize succeeds (not NO_PRODUCT_SELECTED)."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    confirm_result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake["id"],
        existing_product_id=None,
        new_product={"product_name": "아세톤", "manufacturer_name": "신규사"},
        selected_reference_candidate_ids=[],
    )
    new_pid = confirm_result["new_product_created"]

    with patch("services.msds_intake_svc.create_version", side_effect=_mock_create_version), \
         patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=True):
        result = _run(svc.finalize_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake["id"],
        ))

    assert result["status"] == "FINALIZED"


def test_np05_new_product_finalize_creates_version_for_new_product():
    """NP05: Finalized MSDS version is linked to the newly created product."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    confirm_result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake["id"],
        existing_product_id=None,
        new_product={"product_name": "메탄올", "manufacturer_name": None},
        selected_reference_candidate_ids=[],
    )
    new_pid = confirm_result["new_product_created"]

    create_version_calls = []
    async def _spy_create_version(sb, current_user, factory_id, product_id, **kw):
        create_version_calls.append(product_id)
        return await _mock_create_version(sb, current_user, factory_id, product_id, **kw)

    with patch("services.msds_intake_svc.create_version", side_effect=_spy_create_version), \
         patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=True):
        _run(svc.finalize_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake["id"],
        ))

    assert len(create_version_calls) == 1
    assert create_version_calls[0] == new_pid


# ─── RF: Reference Fail-Closed Tests ──────────────────────────────────────────

def _build_confirmed_intake_for_finalize(sb, product_id=None):
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    for r in sb.store["msds_intakes"]:
        if r["id"] == intake_id:
            r["status"] = "CONFIRMED"
            r["selected_product_id"] = product_id or PROD_A1_1
            r["reference_snapshot_id"] = SNAPSHOT_ID
            break
    return intake_id


async def _mock_create_version(sb, current_user, factory_id, product_id, file_bytes, file_name, mime_type, **kwargs):
    from datetime import datetime
    doc_id = str(uuid.uuid4())
    sha = hashlib.sha256(file_bytes).hexdigest()
    doc = {
        "id": doc_id, "factory_id": factory_id, "company_id": CO_A,
        "category": "msds", "linked_table": "chemical_products", "linked_id": product_id,
        "bucket_id": "company-docs", "storage_path": f"{CO_A}/msds/2026-10/{doc_id}.pdf",
        "is_active": True, "deleted_at": None, "file_name": file_name,
        "mime_type": mime_type, "file_size": len(file_bytes),
        "uploaded_at": datetime.utcnow().isoformat(),
    }
    sb.store.setdefault("documents", []).append(doc)
    ver_id = str(uuid.uuid4())
    ver = {
        "id": ver_id, "factory_id": factory_id, "chemical_product_id": product_id,
        "document_id": doc_id, "version_no": 1, "content_sha256": sha,
        "is_current": True, "record_status": "ACTIVE",
        "created_at": datetime.utcnow().isoformat(),
    }
    sb.store.setdefault("customer_msds_versions", []).append(ver)
    return (ver, "NEW_VERSION")


def test_rf01_selected_ref_exists_finalize_succeeds():
    """RF01: Selected reference exists in leg-prod → finalize succeeds with link."""
    sb = _make_sb()
    intake_id = _build_confirmed_intake_for_finalize(sb)
    cand_id = str(uuid.uuid4())
    sb.store["msds_match_candidates"].append({
        "id": cand_id, "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-001",
        "reference_chem_id": "CHEM-001", "evidence_json": {"cas": "7647-01-0"},
    })

    with patch("services.msds_intake_svc.create_version", side_effect=_mock_create_version), \
         patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=True):
        result = _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake_id))

    assert result["status"] == "FINALIZED"
    links = sb.store.get("msds_reference_links", [])
    assert len(links) == 1
    assert links[0]["reference_content_id"] == "REF-001"


def test_rf02_selected_ref_missing_raises_reference_verify_failed():
    """RF02: verify_reference_exists returns False → REFERENCE_VERIFY_FAILED (no version created)."""
    sb = _make_sb()
    intake_id = _build_confirmed_intake_for_finalize(sb)
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-GONE",
        "reference_chem_id": "CHEM-GONE", "evidence_json": {},
    })

    with patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=False):
        with pytest.raises(MsdsProductError) as exc:
            _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake_id))

    assert exc.value.code == "REFERENCE_VERIFY_FAILED"


def test_rf03_leg_prod_unavailable_raises_reference_verify_failed():
    """RF03: verify_reference_exists raises exception → REFERENCE_VERIFY_FAILED."""
    sb = _make_sb()
    intake_id = _build_confirmed_intake_for_finalize(sb)
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-001",
        "reference_chem_id": "CHEM-001", "evidence_json": {},
    })

    with patch("services.msds_intake_svc.ref_svc.verify_reference_exists", side_effect=RuntimeError("connection refused")):
        with pytest.raises(MsdsProductError) as exc:
            _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake_id))

    assert exc.value.code == "REFERENCE_VERIFY_FAILED"


def test_rf04_verify_failure_create_version_not_called():
    """RF04: verify failure → create_version must not be called."""
    sb = _make_sb()
    intake_id = _build_confirmed_intake_for_finalize(sb)
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-MISSING",
        "reference_chem_id": "CHEM-MISSING", "evidence_json": {},
    })

    create_version_called = []
    async def _spy(*a, **kw):
        create_version_called.append(True)
        return await _mock_create_version(*a, **kw)

    with patch("services.msds_intake_svc.create_version", side_effect=_spy), \
         patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=False):
        with pytest.raises(MsdsProductError):
            _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake_id))

    assert create_version_called == []


def test_rf05_verify_failure_temp_storage_preserved():
    """RF05: verify failure → temp storage artifact is preserved (not cleaned up)."""
    sb = _make_sb()
    intake_id = _build_confirmed_intake_for_finalize(sb)
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-BAD",
        "reference_chem_id": "CHEM-BAD", "evidence_json": {},
    })
    # Count removes before
    bucket = sb.storage.from_("company-docs")
    removes_before = len(bucket.removes)

    with patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=False):
        with pytest.raises(MsdsProductError):
            _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake_id))

    assert len(bucket.removes) == removes_before


def test_rf06_verify_failure_intake_not_finalized():
    """RF06: verify failure → intake status is NOT FINALIZED."""
    sb = _make_sb()
    intake_id = _build_confirmed_intake_for_finalize(sb)
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-BAD",
        "reference_chem_id": "CHEM-BAD", "evidence_json": {},
    })

    with patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=False):
        with pytest.raises(MsdsProductError):
            _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake_id))

    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake_id)
    assert stored["status"] != "FINALIZED"


# ─── Process + Finalize integration ──────────────────────────────────────────

def test_process_already_processed_raises_409():
    """Process on already REVIEW_REQUIRED intake raises 409."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    with pytest.raises(MsdsProductError) as exc:
        svc.process_intake(sb, USER_A, FAC_A1, intake["id"])
    assert exc.value.code == "INTAKE_ALREADY_PROCESSED"


def test_finalize_intake_not_confirmed_raises_409():
    """Finalize on REVIEW_REQUIRED (not confirmed) intake raises 409."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    with pytest.raises(MsdsProductError) as exc:
        _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake["id"]))
    assert exc.value.code == "INTAKE_NOT_CONFIRMED"


def test_finalize_no_product_selected_raises_409():
    """Finalize on CONFIRMED intake with no selected_product_id raises 409."""
    sb = _make_sb()
    cfm_id = str(uuid.uuid4())
    sb.store["msds_intakes"].append({
        "id": cfm_id, "factory_id": FAC_A1, "status": "CONFIRMED",
        "selected_product_id": None, "reference_snapshot_id": SNAPSHOT_ID,
    })
    with pytest.raises(MsdsProductError) as exc:
        _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=cfm_id))
    assert exc.value.code == "NO_PRODUCT_SELECTED"


def test_finalize_already_finalized_returns_noop():
    """Finalize on FINALIZED intake returns ALREADY_FINALIZED."""
    sb = _make_sb()
    fin_id = str(uuid.uuid4())
    sb.store["msds_intakes"].append({
        "id": fin_id, "factory_id": FAC_A1, "status": "FINALIZED",
        "selected_product_id": PROD_A1_1, "reference_snapshot_id": SNAPSHOT_ID,
    })
    result = _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=fin_id))
    assert result["status"] == "ALREADY_FINALIZED"


def test_finalize_success_creates_version_and_link():
    """Finalize creates MSDS version and reference link, transitions to FINALIZED."""
    sb = _make_sb()
    intake_id = _build_confirmed_intake_for_finalize(sb)
    cand_id = str(uuid.uuid4())
    sb.store["msds_match_candidates"].append({
        "id": cand_id, "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-001",
        "reference_chem_id": "CHEM-001", "evidence_json": {"cas": "7647-01-0"},
    })

    with patch("services.msds_intake_svc.create_version", side_effect=_mock_create_version), \
         patch("services.msds_intake_svc.ref_svc.verify_reference_exists", return_value=True):
        result = _run(svc.finalize_intake(sb=sb, current_user=USER_A, factory_id=FAC_A1, intake_id=intake_id))

    assert result["status"] == "FINALIZED"
    assert result["rpc_status"] == "NEW_VERSION"
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake_id)
    assert stored["status"] == "FINALIZED"
    assert stored["final_msds_version_id"] == result["version_id"]
    links = sb.store.get("msds_reference_links", [])
    assert len(links) >= 1
    assert links[0]["reference_content_id"] == "REF-001"


# ─── Reference lookup failure in process_intake ───────────────────────────────

def test_process_reference_lookup_failed_transitions_to_failed():
    """Reference lookup failure during process_intake → intake FAILED with REFERENCE_LOOKUP_FAILED."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    text_facts = [
        {"fact_type": "PRODUCT_NAME", "raw_value": "염산", "normalized_value": "염산",
         "source_page": 1, "evidence_json": {}},
    ]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         patch("services.msds_intake_svc.ref_svc.find_reference_candidates", side_effect=RuntimeError("leg-prod timeout")):
        with pytest.raises(MsdsProductError) as exc:
            svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert exc.value.code == "REFERENCE_LOOKUP_FAILED"
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake_id)
    assert stored["status"] == "FAILED"
    assert stored["error_code"] == "REFERENCE_LOOKUP_FAILED"


# ─── List endpoints ───────────────────────────────────────────────────────────

def test_list_facts_returns_facts():
    """list_facts returns all facts for the intake."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    sb.store["msds_intake_facts"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "fact_type": "PRODUCT_NAME", "raw_value": "염산",
        "normalized_value": "염산", "extraction_method": "PDF_NATIVE",
    })
    facts = svc.list_facts(sb, USER_A, FAC_A1, intake_id)
    assert len(facts) == 1
    assert facts[0]["fact_type"] == "PRODUCT_NAME"


def test_list_candidates_separates_types():
    """list_candidates returns product and reference candidates separately."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "CUSTOMER_PRODUCT", "candidate_product_id": PROD_A1_1,
        "match_reason": "EXACT_NAME", "rank_no": 3, "decision_status": "PENDING",
    })
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "REFERENCE", "reference_content_id": "REF-001",
        "match_reason": "EXACT_CAS", "rank_no": 1, "decision_status": "PENDING",
    })
    result = svc.list_candidates(sb, USER_A, FAC_A1, intake_id)
    assert len(result["product_candidates"]) == 1
    assert len(result["reference_candidates"]) == 1


# ─── RT: Retry Idempotency Tests ──────────────────────────────────────────────

def _make_failed_with_data(sb, n_facts=2, n_candidates=1):
    """FAILED intake with pre-existing facts and candidates to simulate prior run."""
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    for r in sb.store["msds_intakes"]:
        if r["id"] == intake_id:
            r["status"] = "FAILED"
            r["error_code"] = "REFERENCE_LOOKUP_FAILED"
            break
    for i in range(n_facts):
        sb.store["msds_intake_facts"].append({
            "id": str(uuid.uuid4()), "intake_id": intake_id,
            "fact_type": "PRODUCT_NAME", "raw_value": f"stale{i}",
            "normalized_value": f"stale{i}", "extraction_method": "PDF_NATIVE",
        })
    for i in range(n_candidates):
        sb.store["msds_match_candidates"].append({
            "id": str(uuid.uuid4()), "intake_id": intake_id,
            "candidate_type": "REFERENCE", "decision_status": "PENDING",
            "match_reason": "EXACT_CAS", "reference_content_id": f"OLD-REF-{i}",
        })
    return intake_id


def test_rt01_reset_deletes_facts():
    """RT01: _reset_process_data deletes msds_intake_facts for the given intake."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    for i in range(2):
        sb.store["msds_intake_facts"].append({
            "id": str(uuid.uuid4()), "intake_id": intake_id,
            "fact_type": "PRODUCT_NAME", "normalized_value": f"old-{i}",
        })
    assert len([r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]) == 2
    svc._reset_process_data(sb, intake_id)
    assert len([r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]) == 0


def test_rt02_reset_deletes_candidates():
    """RT02: _reset_process_data deletes msds_match_candidates for the given intake."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    for i in range(3):
        sb.store["msds_match_candidates"].append({
            "id": str(uuid.uuid4()), "intake_id": intake_id,
            "candidate_type": "REFERENCE", "decision_status": "PENDING",
        })
    assert len([r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]) == 3
    svc._reset_process_data(sb, intake_id)
    assert len([r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]) == 0


def test_rt03_reprocess_facts_not_duplicated():
    """RT03: Re-processing a FAILED intake replaces facts — does not accumulate."""
    sb = _make_sb()
    intake_id = _make_failed_with_data(sb, n_facts=2, n_candidates=0)

    text_facts = [
        {"fact_type": "PRODUCT_NAME", "raw_value": "염산", "normalized_value": "염산",
         "source_page": 1, "evidence_json": {}},
    ]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         _mock_ref_find([]):
        svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    facts = [r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]
    assert len(facts) == 1  # 2 stale deleted + 1 fresh inserted


def test_rt04_reprocess_candidates_not_duplicated():
    """RT04: Re-processing a FAILED intake replaces candidates — does not accumulate."""
    sb = _make_sb()
    intake_id = _make_failed_with_data(sb, n_facts=0, n_candidates=2)

    ref_hits = [{
        "reference_content_id": "REF-NEW", "reference_chem_id": "CHEM-NEW",
        "reference_snapshot_id": SNAPSHOT_ID, "cas_no": "7647-01-0",
        "match_reason": "EXACT_CAS", "rank_no": 1, "evidence_json": {},
    }]
    text_facts = [
        {"fact_type": "CAS", "raw_value": "7647-01-0", "normalized_value": "7647-01-0",
         "source_page": 1, "evidence_json": {"cas": "7647-01-0"}},
    ]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         _mock_ref_find(ref_hits):
        svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    candidates = [r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]
    assert len(candidates) == 1  # 2 stale deleted + 1 fresh inserted
    assert candidates[0]["reference_content_id"] == "REF-NEW"


# ─── CF-PATCH-002: Confirm Side-Effect Ordering Tests ─────────────────────────

def test_cf11_idempotent_confirmed_returns_no_change():
    """CF11: Already CONFIRMED with selected_product_id → no_change=True, no new product."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]
    for r in sb.store["msds_intakes"]:
        if r["id"] == intake_id:
            r["status"] = "CONFIRMED"
            r["selected_product_id"] = PROD_A1_1
            break
    initial_count = len(sb.store["chemical_products"])

    result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake_id,
        existing_product_id=None,
        new_product={"product_name": "새물질", "manufacturer_name": None},
        selected_reference_candidate_ids=[],
    )
    assert result["status"] == "CONFIRMED"
    assert result.get("no_change") is True
    assert len(sb.store["chemical_products"]) == initial_count


def test_cf12_new_product_invalid_ref_candidate_no_product_created():
    """CF12: new_product + nonexistent reference candidate → 422, product NOT created in DB."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    bad_cand_id = str(uuid.uuid4())
    initial_count = len(sb.store["chemical_products"])

    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake["id"],
            existing_product_id=None,
            new_product={"product_name": "신규물질", "manufacturer_name": None},
            selected_reference_candidate_ids=[bad_cand_id],
        )
    assert exc.value.code == "REFERENCE_CANDIDATE_INVALID"
    assert len(sb.store["chemical_products"]) == initial_count


def test_cf13_existing_product_invalid_ref_candidate_intake_not_updated():
    """CF13: existing_product + invalid reference candidate → 422, intake stays REVIEW_REQUIRED."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    bad_cand_id = str(uuid.uuid4())

    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake["id"],
            existing_product_id=PROD_A1_1,
            new_product=None,
            selected_reference_candidate_ids=[bad_cand_id],
        )
    assert exc.value.code == "REFERENCE_CANDIDATE_INVALID"
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake["id"])
    assert stored["status"] == "REVIEW_REQUIRED"


def test_cf14_new_product_customer_product_candidate_no_product_created():
    """CF14: new_product + CUSTOMER_PRODUCT candidate passed as reference → 422, no product created."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    intake_id = intake["id"]
    wrong_cand_id = str(uuid.uuid4())
    sb.store["msds_match_candidates"].append({
        "id": wrong_cand_id, "intake_id": intake_id,
        "candidate_type": "CUSTOMER_PRODUCT",
        "decision_status": "PENDING", "match_reason": "EXACT_NAME",
    })
    initial_count = len(sb.store["chemical_products"])

    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake_id,
            existing_product_id=None,
            new_product={"product_name": "신규물질", "manufacturer_name": None},
            selected_reference_candidate_ids=[wrong_cand_id],
        )
    assert exc.value.code == "REFERENCE_CANDIDATE_INVALID"
    assert len(sb.store["chemical_products"]) == initial_count


def test_cf15_new_product_not_pending_candidate_no_product_created():
    """CF15: new_product + already-SELECTED candidate → 422, no product created."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    intake_id = intake["id"]
    already_selected_id = str(uuid.uuid4())
    sb.store["msds_match_candidates"].append({
        "id": already_selected_id, "intake_id": intake_id,
        "candidate_type": "REFERENCE",
        "decision_status": "SELECTED",
        "match_reason": "EXACT_CAS",
    })
    initial_count = len(sb.store["chemical_products"])

    with pytest.raises(MsdsProductError) as exc:
        svc.confirm_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A1,
            intake_id=intake_id,
            existing_product_id=None,
            new_product={"product_name": "신규물질", "manufacturer_name": None},
            selected_reference_candidate_ids=[already_selected_id],
        )
    assert exc.value.code == "REFERENCE_CANDIDATE_INVALID"
    assert len(sb.store["chemical_products"]) == initial_count


def test_cf16_new_product_valid_candidate_confirms_successfully():
    """CF16: new_product + valid REFERENCE candidate → product created + candidate SELECTED + CONFIRMED."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    intake_id = intake["id"]
    cand_id = str(uuid.uuid4())
    sb.store["msds_match_candidates"].append({
        "id": cand_id, "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "PENDING",
        "match_reason": "EXACT_CAS", "reference_content_id": "REF-001",
    })
    initial_count = len(sb.store["chemical_products"])

    result = svc.confirm_intake(
        sb=sb, current_user=USER_A, factory_id=FAC_A1,
        intake_id=intake_id,
        existing_product_id=None,
        new_product={"product_name": "신규물질", "manufacturer_name": "신규사"},
        selected_reference_candidate_ids=[cand_id],
    )
    assert result["status"] == "CONFIRMED"
    assert result["new_product_created"] is not None
    assert len(sb.store["chemical_products"]) == initial_count + 1
    cand = next(r for r in sb.store["msds_match_candidates"] if r["id"] == cand_id)
    assert cand["decision_status"] == "SELECTED"
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake_id)
    assert stored["status"] == "CONFIRMED"


# ─── RT-PATCH-003: Process Cleanup Closure Tests ──────────────────────────────

def test_rt05_failed_stale_retry_reference_failure_cleanup():
    """RT05: FAILED + stale rows → retry → reference lookup failure → facts=0 / candidates=0."""
    sb = _make_sb()
    intake_id = _make_failed_with_data(sb, n_facts=3, n_candidates=2)

    text_facts = [
        {"fact_type": "PRODUCT_NAME", "raw_value": "염산", "normalized_value": "염산",
         "source_page": 1, "evidence_json": {}},
    ]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         patch("services.msds_intake_svc.ref_svc.find_reference_candidates",
               side_effect=RuntimeError("leg-prod down")):
        with pytest.raises(MsdsProductError) as exc:
            svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert exc.value.code == "REFERENCE_LOOKUP_FAILED"
    stored = next(r for r in sb.store["msds_intakes"] if r["id"] == intake_id)
    assert stored["status"] == "FAILED"
    assert stored["error_code"] == "REFERENCE_LOOKUP_FAILED"
    assert len([r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]) == 0
    assert len([r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]) == 0


def test_rt06_fact_insert_partial_failure_cleanup():
    """RT06: Partial fact INSERT failure → facts=0 / candidates=0 after cleanup."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]

    text_facts = [
        {"fact_type": "PRODUCT_NAME", "raw_value": "염산", "normalized_value": "염산",
         "source_page": 1, "evidence_json": {}},
        {"fact_type": "CAS", "raw_value": "7647-01-0", "normalized_value": "7647-01-0",
         "source_page": 1, "evidence_json": {}},
    ]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    call_count = [0]

    def _partial_fact_insert(payload):
        call_count[0] += 1
        if call_count[0] == 1:
            row = dict(payload)
            row.setdefault("id", str(uuid.uuid4()))
            sb.store["msds_intake_facts"].append(row)
            return _Result([dict(row)])
        raise RuntimeError("DB error on second INSERT")

    sb.set_insert_hook("msds_intake_facts", _partial_fact_insert)

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         _mock_ref_find([]):
        with pytest.raises(MsdsProductError):
            svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert len([r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]) == 0
    assert len([r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]) == 0


def test_rt07_candidate_insert_partial_failure_cleanup():
    """RT07: Partial candidate INSERT failure → facts=0 / candidates=0 after cleanup."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]

    text_facts = [
        {"fact_type": "CAS", "raw_value": "7647-01-0", "normalized_value": "7647-01-0",
         "source_page": 1, "evidence_json": {}},
    ]
    ref_hits = [
        {"reference_content_id": "REF-A", "reference_chem_id": "CHEM-A",
         "reference_snapshot_id": SNAPSHOT_ID, "cas_no": "7647-01-0",
         "match_reason": "EXACT_CAS", "rank_no": 1, "evidence_json": {}},
        {"reference_content_id": "REF-B", "reference_chem_id": "CHEM-B",
         "reference_snapshot_id": SNAPSHOT_ID, "cas_no": "7647-01-0",
         "match_reason": "EXACT_CAS", "rank_no": 1, "evidence_json": {}},
    ]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    call_count = [0]

    def _partial_cand_insert(payload):
        call_count[0] += 1
        if call_count[0] == 1:
            row = dict(payload)
            row.setdefault("id", str(uuid.uuid4()))
            sb.store["msds_match_candidates"].append(row)
            return _Result([dict(row)])
        raise RuntimeError("DB error on second candidate INSERT")

    sb.set_insert_hook("msds_match_candidates", _partial_cand_insert)

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         _mock_ref_find(ref_hits):
        with pytest.raises(MsdsProductError):
            svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert len([r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]) == 0
    assert len([r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]) == 0


def test_rt08_failed_processing_preserves_temp_artifact():
    """RT08: Processing failure preserves temp artifact in storage."""
    sb = _make_sb()
    intake = _make_received_intake(sb)
    intake_id = intake["id"]

    artifact = sb.store["msds_intake_artifacts"][0]
    storage_path = artifact["storage_path"]
    bucket = sb.storage.from_("company-docs")
    assert storage_path in bucket._store

    removes_before = len(bucket.removes)

    text_facts = [{"fact_type": "PRODUCT_NAME", "raw_value": "염산", "normalized_value": "염산",
                   "source_page": 1, "evidence_json": {}}]
    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = text_facts
    mock_result.ocr_required = False
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result), \
         patch("services.msds_intake_svc.ref_svc.find_reference_candidates",
               side_effect=RuntimeError("leg-prod down")):
        with pytest.raises(MsdsProductError):
            svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert storage_path in bucket._store
    assert len(bucket.removes) == removes_before


def test_rt09_failed_stale_retry_ocr_required_clears_stale():
    """RT09: FAILED + stale rows → retry → OCR_REQUIRED → stale facts/candidates removed."""
    sb = _make_sb()
    intake_id = _make_failed_with_data(sb, n_facts=2, n_candidates=2)

    mock_result = MagicMock()
    mock_result.page_count = 1
    mock_result.facts = []
    mock_result.ocr_required = True
    mock_result.error = None

    with patch("services.msds_intake_svc.extractor.extract_facts", return_value=mock_result):
        result = svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert result["status"] == "OCR_REQUIRED"
    assert len([r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]) == 0
    assert len([r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]) == 0


def test_rt10_review_required_process_retry_409_preserves_data():
    """RT10: REVIEW_REQUIRED process retry → 409 → existing facts/candidates unchanged."""
    sb = _make_sb()
    intake = _make_review_required_intake(sb)
    intake_id = intake["id"]

    for i in range(2):
        sb.store["msds_intake_facts"].append({
            "id": str(uuid.uuid4()), "intake_id": intake_id,
            "fact_type": "PRODUCT_NAME", "normalized_value": f"fact{i}",
        })
    sb.store["msds_match_candidates"].append({
        "id": str(uuid.uuid4()), "intake_id": intake_id,
        "candidate_type": "REFERENCE", "decision_status": "PENDING",
        "match_reason": "EXACT_CAS",
    })

    with pytest.raises(MsdsProductError) as exc:
        svc.process_intake(sb, USER_A, FAC_A1, intake_id)

    assert exc.value.code == "INTAKE_ALREADY_PROCESSED"
    assert len([r for r in sb.store["msds_intake_facts"] if r["intake_id"] == intake_id]) == 2
    assert len([r for r in sb.store["msds_match_candidates"] if r["intake_id"] == intake_id]) == 1
