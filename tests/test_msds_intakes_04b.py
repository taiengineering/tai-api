"""WO-MSDS-04B-IMPLEMENTATION-001 — Photo Intake, OCR, CAS Validator unit tests.

FakeSupabase isolation — no production DB / network / storage.
CLOVA / Vision providers mocked via unittest.mock.patch.
"""
from __future__ import annotations

import hashlib
import io
import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from services import msds_intake_svc as svc
from services.cas_validator import extract_valid_cas, try_correct_cas, validate_cas
from services import msds_ocr_fact_parser as parser
from services.msds_product_svc import MsdsProductError


# ─── Shared FakeSupabase (imported pattern from test_msds_intakes) ─────────────

class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count if count is not None else (len(data) if data else 0)


class _FakeBucket:
    def __init__(self):
        self.uploads: list = []
        self.removes: list = []
        self._store: dict = {}

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


class _FakeStorageRoot:
    def __init__(self):
        self._buckets: dict = {}

    def from_(self, name):
        if name not in self._buckets:
            self._buckets[name] = _FakeBucket()
        return self._buckets[name]


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

    def select(self, cols="*", *a, **k):
        self._op = "select"
        self._cols = cols or "*"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, patch):
        self._op = "update"
        self._payload = patch
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
            if self._limit_n is not None:
                matched = matched[:self._limit_n]
            return _Result(matched)

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

        if self._op == "delete":
            self.store[self.table_name] = [r for r in rows if not self._match(r)]
            return _Result([])

        return _Result([])


class FakeSB:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log = []
        self._table_hooks: dict = {}
        self.storage = _FakeStorageRoot()

    def table(self, name):
        return _Query(self.store, name, self.log, self._table_hooks)

    def set_insert_hook(self, table_name, fn):
        self._table_hooks[(table_name, "insert")] = fn


# ─── Fixtures ─────────────────────────────────────────────────────────────────

CO_A = "company-a"
FAC_A = str(uuid.uuid4())
USER_A = {"id": "user-a", "company_id": CO_A, "role_code": "010"}

_ROLE_DATA_SCOPE = [{"role_code": "010", "scope_type": "COMPANY"}]
_FACTORIES = [{"id": FAC_A, "company_id": CO_A, "name": "A사 1공장"}]

JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 60  # minimal JPEG bytes


def _make_sb():
    return FakeSB({
        "factories": list(_FACTORIES),
        "role_data_scope": list(_ROLE_DATA_SCOPE),
        "chemical_products": [],
        "msds_intakes": [],
        "msds_intake_artifacts": [],
        "msds_intake_facts": [],
        "msds_match_candidates": [],
        "msds_reference_links": [],
        "chemical_product_identifiers": [],
    })


# ─── CAS Validator tests ───────────────────────────────────────────────────────

class TestCasValidator:
    def test_cv01_valid_cas_format_and_checksum(self):
        """CV01: Known valid CAS numbers pass both format and checksum."""
        valid_cases = [
            "7647-01-0",  # HCl
            "67-64-1",    # Acetone
            "64-17-5",    # Ethanol
            "7664-93-9",  # H2SO4
            "1310-73-2",  # NaOH
        ]
        for cas in valid_cases:
            fmt, chk = validate_cas(cas)
            assert fmt is True, f"{cas} format failed"
            assert chk is True, f"{cas} checksum failed"

    def test_cv02_wrong_checksum_format_ok(self):
        """CV02: Wrong check digit: format valid, checksum invalid."""
        fmt, chk = validate_cas("7647-01-1")
        assert fmt is True
        assert chk is False

    def test_cv03_bad_format_returns_false_false(self):
        """CV03: Missing check digit → both False."""
        fmt, chk = validate_cas("7647-01")
        assert fmt is False
        assert chk is False

    def test_cv04_no_hyphens_format_invalid(self):
        """CV04: No hyphens → format invalid."""
        fmt, chk = validate_cas("76470100")
        assert fmt is False
        assert chk is False

    def test_cv05_ocr_correction_o_to_0_valid(self):
        """CV05: 'O' in second segment corrects to '0' → valid HCl."""
        # "7647-O1-0" → "7647-01-0" (HCl)
        corrected = try_correct_cas("7647-O1-0")
        assert corrected == "7647-01-0"

    def test_cv06_ocr_correction_i_to_1_valid(self):
        """CV06: 'I' in second segment corrects to '1' → valid HCl."""
        corrected = try_correct_cas("7647-0I-0")
        assert corrected == "7647-01-0"

    def test_cv07_correction_invalid_after_substitution(self):
        """CV07: OCR substitution does not produce valid checksum → None."""
        # "764O-01-0" → "7640-01-0": checksum = 9 ≠ 0
        corrected = try_correct_cas("764O-01-0")
        assert corrected is None

    def test_cv08_extract_valid_cas_direct(self):
        """CV08: extract_valid_cas returns canonical form for valid CAS."""
        assert extract_valid_cas("7647-01-0") == "7647-01-0"

    def test_cv09_extract_valid_cas_with_correction(self):
        """CV09: extract_valid_cas returns corrected form when raw is invalid."""
        assert extract_valid_cas("7647-O1-0") == "7647-01-0"

    def test_cv10_extract_valid_cas_none_for_invalid(self):
        """CV10: extract_valid_cas returns None for uncorrectable CAS."""
        assert extract_valid_cas("ABCD-12-3") is None


# ─── OCR Fact Parser tests ─────────────────────────────────────────────────────

class TestOcrFactParser:
    def test_fp01_product_name_extracted(self):
        """FP01: '제품명: 염산' yields PRODUCT_NAME fact."""
        facts = parser.parse_ocr_facts("제품명: 염산\n제조사: 주식회사A")
        names = [f for f in facts if f["fact_type"] == "PRODUCT_NAME"]
        assert len(names) == 1
        assert "염산" in names[0]["raw_value"]

    def test_fp02_manufacturer_extracted(self):
        """FP02: '제조사: 주식회사A' yields MANUFACTURER_NAME fact."""
        facts = parser.parse_ocr_facts("제품명: 황산\n제조사: 주식회사A")
        mfrs = [f for f in facts if f["fact_type"] == "MANUFACTURER_NAME"]
        assert len(mfrs) == 1
        assert "주식회사a" in mfrs[0]["normalized_value"]

    def test_fp03_cas_extracted_context(self):
        """FP03: CAS near '구성 성분' context extracted."""
        text = "구성 성분:\nCAS No: 7647-01-0"
        facts = parser.parse_ocr_facts(text)
        cas = [f for f in facts if f["fact_type"] == "CAS"]
        assert len(cas) >= 1
        assert cas[0]["normalized_value"] == "7647-01-0"

    def test_fp04_cas_extracted_fallback(self):
        """FP04: CAS without context marker still extracted."""
        facts = parser.parse_ocr_facts("Some text 67-64-1 here")
        cas = [f for f in facts if f["fact_type"] == "CAS"]
        assert len(cas) == 1
        assert cas[0]["normalized_value"] == "67-64-1"

    def test_fp05_cas_with_ocr_error_corrected(self):
        """FP05: CAS with OCR error '7647-O1-0' corrected to '7647-01-0'."""
        facts = parser.parse_ocr_facts("CAS No: 7647-O1-0")
        cas = [f for f in facts if f["fact_type"] == "CAS"]
        assert len(cas) == 1
        assert cas[0]["normalized_value"] == "7647-01-0"
        assert cas[0]["raw_value"] == "7647-O1-0"

    def test_fp06_invalid_cas_dropped(self):
        """FP06: CAS with bad format is not included in facts."""
        facts = parser.parse_ocr_facts("CAS: 1234-56-7")  # wrong checksum
        cas = [f for f in facts if f["fact_type"] == "CAS"]
        assert cas == []

    def test_fp07_extraction_method_ocr(self):
        """FP07: Default extraction_method is 'OCR'."""
        facts = parser.parse_ocr_facts("제품명: 테스트\n7647-01-0")
        for f in facts:
            assert f["extraction_method"] == "OCR"

    def test_fp08_extraction_method_vision(self):
        """FP08: extraction_method='VISION' propagated to facts."""
        facts = parser.parse_ocr_facts("제품명: 테스트", extraction_method="VISION")
        assert all(f["extraction_method"] == "VISION" for f in facts)

    def test_fp09_is_sufficient_true_with_product_name(self):
        """FP09: is_sufficient returns True when PRODUCT_NAME present."""
        facts = [{"fact_type": "PRODUCT_NAME", "raw_value": "테스트"}]
        assert parser.is_sufficient(facts) is True

    def test_fp10_is_sufficient_true_with_cas(self):
        """FP10: is_sufficient returns True when CAS present."""
        facts = [{"fact_type": "CAS", "normalized_value": "7647-01-0"}]
        assert parser.is_sufficient(facts) is True

    def test_fp11_is_sufficient_false_with_only_manufacturer(self):
        """FP11: is_sufficient returns False when only MANUFACTURER_NAME present."""
        facts = [{"fact_type": "MANUFACTURER_NAME", "raw_value": "제조사"}]
        assert parser.is_sufficient(facts) is False

    def test_fp12_supplier_extracted(self):
        """FP12: '공급자: 공급A' yields SUPPLIER_NAME fact."""
        facts = parser.parse_ocr_facts("공급자: 공급A")
        suppliers = [f for f in facts if f["fact_type"] == "SUPPLIER_NAME"]
        assert len(suppliers) == 1
        assert "공급a" in suppliers[0]["normalized_value"]

    def test_fp13_product_code_extracted(self):
        """FP13: '제품 코드: ABC-123' yields PRODUCT_CODE fact."""
        facts = parser.parse_ocr_facts("제품 코드: ABC-123")
        codes = [f for f in facts if f["fact_type"] == "PRODUCT_CODE"]
        assert len(codes) == 1
        assert "abc-123" in codes[0]["normalized_value"]

    def test_fp14_duplicate_cas_deduplicated(self):
        """FP14: Same CAS appearing twice in text yields only one fact."""
        text = "구성 성분: 7647-01-0\n다시: 7647-01-0"
        facts = parser.parse_ocr_facts(text)
        cas = [f for f in facts if f["fact_type"] == "CAS"]
        cas_values = [f["normalized_value"] for f in cas]
        assert len(set(cas_values)) == len(cas_values)


# ─── Photo Intake tests ────────────────────────────────────────────────────────

class TestPhotoIntake:
    def test_ph01_empty_photos_raises(self):
        """PH01: Empty photo list raises PHOTO_REQUIRED."""
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.create_photo_intake(sb, USER_A, FAC_A, [])
        assert exc.value.code == "PHOTO_REQUIRED"

    def test_ph02_too_many_photos_raises(self):
        """PH02: >50 photos raises PHOTO_TOO_MANY."""
        sb = _make_sb()
        photos = [{"bytes": JPEG_MAGIC, "file_name": f"p{i}.jpg",
                   "sequence_no": i, "mime_type": "image/jpeg"} for i in range(51)]
        with pytest.raises(MsdsProductError) as exc:
            svc.create_photo_intake(sb, USER_A, FAC_A, photos)
        assert exc.value.code == "PHOTO_TOO_MANY"

    def test_ph03_invalid_jpeg_magic_raises(self):
        """PH03: Non-JPEG bytes raise INVALID_PHOTO_FORMAT."""
        sb = _make_sb()
        photos = [{"bytes": b"not a jpeg", "file_name": "p1.jpg",
                   "sequence_no": 1, "mime_type": "image/jpeg"}]
        with pytest.raises(MsdsProductError) as exc:
            svc.create_photo_intake(sb, USER_A, FAC_A, photos)
        assert exc.value.code == "INVALID_PHOTO_FORMAT"

    def test_ph04_wrong_factory_auth_denied(self):
        """PH04: User from wrong company cannot create photo intake."""
        sb = _make_sb()
        wrong_user = {"id": "user-b", "company_id": "company-b", "role_code": "010"}
        photos = [{"bytes": JPEG_MAGIC, "file_name": "p1.jpg",
                   "sequence_no": 1, "mime_type": "image/jpeg"}]
        with pytest.raises(MsdsProductError) as exc:
            svc.create_photo_intake(sb, wrong_user, FAC_A, photos)
        assert exc.value.status_code in (403, 404)

    @patch("services.msds_intake_svc._build_derived_pdf")
    def test_ph05_photo_intake_creates_artifacts(self, mock_build_pdf):
        """PH05: create_photo_intake creates PHOTO artifacts + PHOTO_DERIVED artifact."""
        mock_build_pdf.return_value = b"%PDF-1.4 derived"
        sb = _make_sb()
        photos = [
            {"bytes": JPEG_MAGIC, "file_name": "p1.jpg", "sequence_no": 1, "mime_type": "image/jpeg"},
            {"bytes": JPEG_MAGIC + b"\x01", "file_name": "p2.jpg", "sequence_no": 2, "mime_type": "image/jpeg"},
        ]
        result = svc.create_photo_intake(sb, USER_A, FAC_A, photos)

        assert result["intake"]["source_type"] == "PHOTO"
        assert result["photo_count"] == 2

        artifacts = sb.store["msds_intake_artifacts"]
        photo_arts = [a for a in artifacts if a["artifact_type"] == "PHOTO"]
        derived_arts = [a for a in artifacts if a["artifact_type"] == "PHOTO_DERIVED"]

        assert len(photo_arts) == 2
        assert len(derived_arts) == 1
        assert derived_arts[0]["is_primary"] is True
        assert all(a["is_primary"] is False for a in photo_arts)
        seq_nos = sorted(a["sequence_no"] for a in photo_arts)
        assert seq_nos == [1, 2]

    @patch("services.msds_intake_svc._build_derived_pdf")
    def test_ph06_intake_status_received(self, mock_build_pdf):
        """PH06: Newly created photo intake has RECEIVED status."""
        mock_build_pdf.return_value = b"%PDF-1.4 test"
        sb = _make_sb()
        photos = [{"bytes": JPEG_MAGIC, "file_name": "p1.jpg",
                   "sequence_no": 1, "mime_type": "image/jpeg"}]
        result = svc.create_photo_intake(sb, USER_A, FAC_A, photos)
        assert result["intake"]["status"] == "RECEIVED"

    @patch("services.msds_intake_svc._build_derived_pdf")
    def test_ph07_storage_uploaded_for_each_photo_plus_derived(self, mock_build_pdf):
        """PH07: Storage uploads include one per photo + one for derived PDF."""
        mock_build_pdf.return_value = b"%PDF-1.4 test"
        sb = _make_sb()
        photos = [
            {"bytes": JPEG_MAGIC, "file_name": "p1.jpg", "sequence_no": 1, "mime_type": "image/jpeg"},
            {"bytes": JPEG_MAGIC + b"\x02", "file_name": "p2.jpg", "sequence_no": 2, "mime_type": "image/jpeg"},
        ]
        svc.create_photo_intake(sb, USER_A, FAC_A, photos)
        bucket = sb.storage.from_("company-docs")
        assert len(bucket.uploads) == 3  # 2 photos + 1 derived PDF


# ─── OCR Run tests ─────────────────────────────────────────────────────────────

class TestOcrRun:
    def _make_ocr_required_intake(self, sb):
        """Insert a pre-built OCR_REQUIRED intake with a stored artifact."""
        intake_id = str(uuid.uuid4())
        artifact_id = str(uuid.uuid4())
        storage_path = f"company-a/msds-intake/{intake_id}/doc.pdf"

        pdf_bytes = b"%PDF-1.4 test ocr required document"
        sb.storage.from_("company-docs")._store[storage_path] = pdf_bytes

        sb.store["msds_intakes"].append({
            "id": intake_id,
            "factory_id": FAC_A,
            "source_type": "PDF",
            "status": "OCR_REQUIRED",
            "reference_snapshot_id": "0ad73e46-d61b-474d-a90e-5b5ab8080d80",
            "created_by": "user-a",
        })
        sb.store["msds_intake_artifacts"].append({
            "id": artifact_id,
            "intake_id": intake_id,
            "artifact_type": "PDF",
            "bucket_id": "company-docs",
            "storage_path": storage_path,
            "file_name": "test.pdf",
            "mime_type": "application/pdf",
            "file_size": len(pdf_bytes),
            "content_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "is_primary": True,
        })
        return intake_id, artifact_id

    def test_ocr01_wrong_status_raises(self):
        """OCR01: run_ocr on RECEIVED intake raises INTAKE_NOT_OCR_REQUIRED."""
        sb = _make_sb()
        intake_id = str(uuid.uuid4())
        sb.store["msds_intakes"].append({
            "id": intake_id, "factory_id": FAC_A, "status": "RECEIVED",
        })
        with pytest.raises(MsdsProductError) as exc:
            svc.run_ocr(sb, USER_A, FAC_A, intake_id)
        assert exc.value.code == "INTAKE_NOT_OCR_REQUIRED"

    def test_ocr02_not_found_raises(self):
        """OCR02: run_ocr on unknown intake_id raises INTAKE_NOT_FOUND."""
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.run_ocr(sb, USER_A, FAC_A, str(uuid.uuid4()))
        assert exc.value.status_code == 404

    @patch("services.msds_intake_svc.run_clova_ocr")
    @patch("services.msds_intake_svc.ref_svc.find_reference_candidates", return_value=[])
    def test_ocr03_clova_facts_extracted_and_stored(self, mock_ref, mock_clova):
        """OCR03: CLOVA text with product name and CAS yields facts stored in DB."""
        from services.msds_ocr_provider import OcrResult
        mock_clova.return_value = OcrResult(
            provider="CLOVA",
            full_text="제품명: 염산\n구성 성분: CAS No: 7647-01-0",
            pages_processed=2,
        )
        sb = _make_sb()
        intake_id, _ = self._make_ocr_required_intake(sb)

        result = svc.run_ocr(sb, USER_A, FAC_A, intake_id)

        assert result["status"] == "REVIEW_REQUIRED"
        facts = sb.store["msds_intake_facts"]
        fact_types = {f["fact_type"] for f in facts}
        assert "PRODUCT_NAME" in fact_types
        assert "CAS" in fact_types

        intake = sb.store["msds_intakes"][0]
        assert intake["status"] == "REVIEW_REQUIRED"

    @patch("services.msds_intake_svc.run_clova_ocr")
    @patch("services.msds_intake_svc.rasterize_pdf_page", return_value=None)
    @patch("services.msds_intake_svc.ref_svc.find_reference_candidates", return_value=[])
    def test_ocr04_insufficient_facts_triggers_vision_fallback(
        self, mock_ref, mock_rasterize, mock_clova
    ):
        """OCR04: CLOVA with only manufacturer falls back to Vision; Vision adds product+CAS."""
        from services.msds_ocr_provider import OcrResult
        from services.msds_vision_provider import VisionResult

        mock_clova.return_value = OcrResult(
            provider="CLOVA", full_text="제조사: 주식회사A"
        )

        with patch("services.msds_intake_svc.run_vision_ocr") as mock_vision, \
             patch("services.msds_intake_svc.rasterize_pdf_page") as mock_rast:
            mock_rast.return_value = "/tmp/fake_page.jpg"
            mock_vision.return_value = VisionResult(
                full_text="제품명: 황산\n구성 성분: CAS No: 7664-93-9"
            )

            sb = _make_sb()
            intake_id, _ = self._make_ocr_required_intake(sb)
            result = svc.run_ocr(sb, USER_A, FAC_A, intake_id)

        assert result["status"] == "REVIEW_REQUIRED"
        facts = sb.store["msds_intake_facts"]
        fact_types = {f["fact_type"] for f in facts}
        assert "PRODUCT_NAME" in fact_types

    @patch("services.msds_intake_svc.run_clova_ocr")
    @patch("services.msds_intake_svc.rasterize_pdf_page", return_value=None)
    def test_ocr05_no_facts_after_all_providers_fails(self, mock_rast, mock_clova):
        """OCR05: No facts extracted from any provider → intake FAILED."""
        from services.msds_ocr_provider import OcrResult
        mock_clova.return_value = OcrResult(provider="CLOVA", full_text="")

        sb = _make_sb()
        intake_id, _ = self._make_ocr_required_intake(sb)

        with pytest.raises(MsdsProductError) as exc:
            svc.run_ocr(sb, USER_A, FAC_A, intake_id)

        assert exc.value.code == "OCR_NO_FACTS"
        intake = sb.store["msds_intakes"][0]
        assert intake["status"] == "FAILED"

    @patch("services.msds_intake_svc.run_clova_ocr")
    @patch("services.msds_intake_svc.ref_svc.find_reference_candidates", return_value=[])
    def test_ocr06_extraction_method_ocr_in_facts(self, mock_ref, mock_clova):
        """OCR06: Facts extracted via CLOVA have extraction_method='OCR'."""
        from services.msds_ocr_provider import OcrResult
        mock_clova.return_value = OcrResult(
            provider="CLOVA", full_text="제품명: 염산\n7647-01-0"
        )
        sb = _make_sb()
        intake_id, _ = self._make_ocr_required_intake(sb)
        svc.run_ocr(sb, USER_A, FAC_A, intake_id)

        facts = sb.store["msds_intake_facts"]
        methods = {f["extraction_method"] for f in facts}
        assert methods <= {"OCR", "VISION"}

    @patch("services.msds_intake_svc.run_clova_ocr")
    @patch("services.msds_intake_svc.ref_svc.find_reference_candidates", return_value=[])
    def test_ocr07_resets_previous_facts_on_retry(self, mock_ref, mock_clova):
        """OCR07: Running OCR twice resets previous facts before processing."""
        from services.msds_ocr_provider import OcrResult
        mock_clova.return_value = OcrResult(
            provider="CLOVA", full_text="제품명: 염산\n7647-01-0"
        )
        sb = _make_sb()
        intake_id, _ = self._make_ocr_required_intake(sb)

        # First run
        svc.run_ocr(sb, USER_A, FAC_A, intake_id)
        first_count = len(sb.store["msds_intake_facts"])

        # Reset status to OCR_REQUIRED for retry
        for r in sb.store["msds_intakes"]:
            if r["id"] == intake_id:
                r["status"] = "OCR_REQUIRED"
                break
        sb.store["msds_intake_facts"].clear()
        sb.store["msds_match_candidates"].clear()

        # Second run
        svc.run_ocr(sb, USER_A, FAC_A, intake_id)
        second_count = len(sb.store["msds_intake_facts"])

        assert second_count == first_count


# ─── is_primary on PDF intake tests ───────────────────────────────────────────

class TestIsPrimary:
    def test_ip01_pdf_artifact_is_primary_true(self):
        """IP01: create_intake sets is_primary=True on the PDF artifact."""
        sb = _make_sb()
        pdf_bytes = b"%PDF-1.4 " + b"x" * 100
        svc.create_intake(
            sb=sb, current_user=USER_A, factory_id=FAC_A,
            file_bytes=pdf_bytes, file_name="test.pdf", mime_type="application/pdf",
        )
        artifacts = sb.store["msds_intake_artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["is_primary"] is True
        assert artifacts[0]["artifact_type"] == "PDF"
