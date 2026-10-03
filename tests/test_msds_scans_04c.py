"""WO-MSDS-04C-IMPLEMENTATION-001 — Barcode/QR Scan Resolver unit tests.

FakeSupabase isolation — no production DB / network / storage.
All scans produce 0 DB writes. Factory-scoped exact lookup only.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import pytest

from services import msds_scan_svc as svc
from services.msds_product_svc import MsdsProductError


# ─── FakeSupabase ─────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table, log):
        self.store = store
        self.table_name = table
        self.log = log
        self._op = None
        self._filters: list = []
        self._in_filters: list = []
        self._cols = "*"
        self._limit_n = None

    def select(self, cols="*", *a, **k):
        self._op = "select"
        self._cols = cols or "*"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def eq(self, c, v):
        self._filters.append(("eq", c, v))
        return self

    def in_(self, c, values):
        self._in_filters.append((c, list(values)))
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def _match(self, row):
        for _, c, v in self._filters:
            rv = row.get(c)
            if isinstance(v, bool) or isinstance(rv, bool):
                if bool(rv) != bool(v):
                    return False
            elif str(rv) != str(v):
                return False
        for c, vals in self._in_filters:
            rv = row.get(c)
            if rv not in vals:
                return False
        return True

    def _project(self, row):
        if not self._cols or self._cols == "*":
            return dict(row)
        keys = [c.strip().split(":")[0] for c in self._cols.split(",") if c.strip()]
        return {k: row.get(k) for k in keys if k}

    def execute(self):
        self.log.append((self.table_name, self._op))
        if self._op == "select":
            rows = self.store.get(self.table_name, [])
            matched = [self._project(r) for r in rows if self._match(r)]
            if self._limit_n is not None:
                matched = matched[:self._limit_n]
            return _Result(matched)
        if self._op == "insert":
            rows = self.store.setdefault(self.table_name, [])
            payload = self._payload
            items = payload if isinstance(payload, list) else [payload]
            out = []
            for it in items:
                it = dict(it)
                it.setdefault("id", str(uuid.uuid4()))
                rows.append(it)
                out.append(dict(it))
            return _Result(out)
        return _Result([])


class FakeSB:
    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.log: list = []

    def table(self, name):
        return _Query(self.store, name, self.log)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

CO_A = "company-a"
CO_B = "company-b"
FAC_A = str(uuid.uuid4())
FAC_B = str(uuid.uuid4())

USER_A = {"id": "user-a", "company_id": CO_A, "role_code": "010"}
USER_B = {"id": "user-b", "company_id": CO_B, "role_code": "010"}

_ROLE_DATA_SCOPE = [{"role_code": "010", "scope_type": "COMPANY"}]
_FACTORIES = [
    {"id": FAC_A, "company_id": CO_A, "name": "Factory A"},
    {"id": FAC_B, "company_id": CO_B, "name": "Factory B"},
]

PROD_A_ID = str(uuid.uuid4())
PROD_B_ID = str(uuid.uuid4())
VER_A_ID = str(uuid.uuid4())

BARCODE_VAL = "8801234567890"

_BASE_PRODUCTS = [
    {
        "id": PROD_A_ID, "factory_id": FAC_A, "product_name": "테스트 제품 A",
        "manufacturer_name": "제조사A", "identity_status": "CONFIRMED",
        "status_code": "ACTIVE",
    },
]

_BASE_VERSIONS = [
    {
        "id": VER_A_ID, "chemical_product_id": PROD_A_ID, "factory_id": FAC_A,
        "version_no": 2, "is_current": True, "record_status": "ACTIVE",
    },
]

_IDENT_A_EAN = {
    "id": str(uuid.uuid4()), "chemical_product_id": PROD_A_ID,
    "factory_id": FAC_A, "identifier_type": "EAN",
    "identifier_value": BARCODE_VAL, "identifier_normalized": BARCODE_VAL,
    "is_active": True,
}
_IDENT_A_GTIN = {
    "id": str(uuid.uuid4()), "chemical_product_id": PROD_A_ID,
    "factory_id": FAC_A, "identifier_type": "GTIN",
    "identifier_value": BARCODE_VAL, "identifier_normalized": BARCODE_VAL,
    "is_active": True,
}
_IDENT_A_BARCODE = {
    "id": str(uuid.uuid4()), "chemical_product_id": PROD_A_ID,
    "factory_id": FAC_A, "identifier_type": "BARCODE",
    "identifier_value": BARCODE_VAL, "identifier_normalized": BARCODE_VAL,
    "is_active": True,
}

QR_VAL = "https://supplier.example/Product/AaBb?x=1"
_IDENT_A_QR = {
    "id": str(uuid.uuid4()), "chemical_product_id": PROD_A_ID,
    "factory_id": FAC_A, "identifier_type": "QR_ALIAS",
    "identifier_value": QR_VAL, "identifier_normalized": QR_VAL,
    "is_active": True,
}


def _make_sb(identifiers=None, products=None, versions=None):
    return FakeSB({
        "factories": list(_FACTORIES),
        "role_data_scope": list(_ROLE_DATA_SCOPE),
        "chemical_products": list(_BASE_PRODUCTS if products is None else products),
        "chemical_product_identifiers": list(identifiers if identifiers is not None else []),
        "customer_msds_versions": list(_BASE_VERSIONS if versions is None else versions),
    })


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write_count(sb: FakeSB) -> int:
    return sum(1 for _, op in sb.log if op in ("insert", "update", "delete"))


# ─── SC: Symbology-to-Type Mapping ───────────────────────────────────────────

class TestSymbologyMapping:
    """SC01-SC08: Identifier type lists match spec."""

    def test_sc01_ean13(self):
        types = svc._resolve_identifier_types("BARCODE", "EAN_13")
        assert types == ["EAN", "GTIN", "BARCODE"]

    def test_sc02_ean8(self):
        types = svc._resolve_identifier_types("BARCODE", "EAN_8")
        assert types == ["EAN", "GTIN", "BARCODE"]

    def test_sc03_upc_a(self):
        types = svc._resolve_identifier_types("BARCODE", "UPC_A")
        assert types == ["UPC", "GTIN", "BARCODE"]

    def test_sc04_upc_e(self):
        types = svc._resolve_identifier_types("BARCODE", "UPC_E")
        assert types == ["UPC", "GTIN", "BARCODE"]

    def test_sc05_gtin14(self):
        types = svc._resolve_identifier_types("BARCODE", "GTIN_14")
        assert types == ["GTIN", "BARCODE"]

    def test_sc06_itf14(self):
        types = svc._resolve_identifier_types("BARCODE", "ITF_14")
        assert types == ["GTIN", "BARCODE"]

    def test_sc07_code128(self):
        types = svc._resolve_identifier_types("BARCODE", "CODE_128")
        assert types == ["BARCODE", "GTIN", "EAN", "UPC"]

    def test_sc08_unknown_symbology(self):
        types = svc._resolve_identifier_types("BARCODE", "UNKNOWN")
        assert types == ["BARCODE", "GTIN", "EAN", "UPC"]

    def test_sc09_null_symbology_uses_default(self):
        types = svc._resolve_identifier_types("BARCODE", None)
        assert types == ["BARCODE", "GTIN", "EAN", "UPC"]

    def test_sc10_qr_always_qr_alias(self):
        types = svc._resolve_identifier_types("QR", None)
        assert types == ["QR_ALIAS"]

    def test_sc11_qr_ignores_symbology(self):
        types = svc._resolve_identifier_types("QR", "EAN_13")
        assert types == ["QR_ALIAS"]


# ─── IV: Input Validation ──────────────────────────────────────────────────────

class TestInputValidation:
    """IV01-IV07: scan_kind, empty, control-char, length guards."""

    def _user(self):
        return USER_A

    def test_iv01_invalid_scan_kind(self):
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, self._user(), FAC_A, "RFID", "123")
        assert exc.value.status_code == 422
        assert exc.value.code == "INVALID_SCAN_KIND"

    def test_iv02_empty_raw_value(self):
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, self._user(), FAC_A, "BARCODE", "")
        assert exc.value.status_code == 422
        assert exc.value.code == "SCAN_VALUE_EMPTY"

    def test_iv03_whitespace_only_raw_value(self):
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, self._user(), FAC_A, "BARCODE", "   ")
        assert exc.value.status_code == 422
        assert exc.value.code == "SCAN_VALUE_EMPTY"

    def test_iv04_nul_in_barcode(self):
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, self._user(), FAC_A, "BARCODE", "abc\x00def")
        assert exc.value.status_code == 422
        assert exc.value.code == "SCAN_VALUE_INVALID"

    def test_iv05_control_char_in_qr(self):
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, self._user(), FAC_A, "QR", "abc\x01def")
        assert exc.value.status_code == 422
        assert exc.value.code == "SCAN_VALUE_INVALID"

    def test_iv06_barcode_too_long(self):
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, self._user(), FAC_A, "BARCODE", "X" * 257)
        assert exc.value.status_code == 422
        assert exc.value.code == "SCAN_VALUE_TOO_LONG"

    def test_iv07_qr_too_long(self):
        sb = _make_sb()
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, self._user(), FAC_A, "QR", "X" * 2049)
        assert exc.value.status_code == 422
        assert exc.value.code == "SCAN_VALUE_TOO_LONG"

    def test_iv08_barcode_256_chars_accepted(self):
        sb = _make_sb()
        result = svc.resolve_scan(sb, self._user(), FAC_A, "BARCODE", "X" * 256)
        assert result["state"] == "NOT_FOUND"

    def test_iv09_qr_2048_chars_accepted(self):
        sb = _make_sb()
        result = svc.resolve_scan(sb, self._user(), FAC_A, "QR", "X" * 2048)
        assert result["state"] == "NOT_FOUND"


# ─── MR: Matched Result ───────────────────────────────────────────────────────

class TestMatchedResult:
    """MR01-MR07: MATCHED state, response shape, MSDS summary."""

    def test_mr01_exact_match_ean(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert result["state"] == "MATCHED"

    def test_mr02_matched_product_fields(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        p = result["product"]
        assert p["id"] == PROD_A_ID
        assert p["product_name"] == "테스트 제품 A"
        assert p["status_code"] == "ACTIVE"
        # internal audit fields not exposed
        assert "created_by" not in p
        assert "updated_by" not in p
        assert "company_id" not in p

    def test_mr03_matched_identifiers_list(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        idents = result["matched_identifiers"]
        assert len(idents) >= 1
        assert any(i["identifier_type"] == "EAN" for i in idents)

    def test_mr04_msds_available_when_current_version_exists(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert result["msds"]["status"] == "AVAILABLE"
        assert result["msds"]["current_version_id"] == VER_A_ID
        assert result["msds"]["version_no"] == 2

    def test_mr05_msds_missing_when_no_current_version(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN], versions=[])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert result["state"] == "MATCHED"
        assert result["msds"]["status"] == "MISSING"
        assert result["msds"]["current_version_id"] is None

    def test_mr06_scan_summary_in_response(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        s = result["scan"]
        assert s["scan_kind"] == "BARCODE"
        assert s["raw_value"] == BARCODE_VAL
        assert s["normalized_value"] == BARCODE_VAL
        assert s["symbology"] == "EAN_13"
        assert "EAN" in s["identifier_types_considered"]

    def test_mr07_no_signed_url_in_matched_response(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert "download_url" not in result
        assert "signed_url" not in result
        msds = result.get("msds") or {}
        assert "download_url" not in msds
        assert "signed_url" not in msds


# ─── NF: Not Found ────────────────────────────────────────────────────────────

class TestNotFound:
    """NF01-NF05: NOT_FOUND state and no DB writes."""

    def test_nf01_no_identifier_rows(self):
        sb = _make_sb(identifiers=[])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert result["state"] == "NOT_FOUND"

    def test_nf02_not_found_product_null(self):
        sb = _make_sb(identifiers=[])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL)
        assert result["product"] is None
        assert result["matched_identifiers"] == []
        assert result["msds"] is None

    def test_nf03_not_found_zero_db_writes(self):
        sb = _make_sb(identifiers=[])
        svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL)
        assert _write_count(sb) == 0

    def test_nf04_scan_summary_present_on_not_found(self):
        sb = _make_sb(identifiers=[])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "CODE_128")
        s = result["scan"]
        assert s["scan_kind"] == "BARCODE"
        assert s["normalized_value"] == BARCODE_VAL

    def test_nf05_substring_not_matched(self):
        """NF05: scan of prefix string must NOT match full stored value."""
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL[:-1], "EAN_13")
        assert result["state"] == "NOT_FOUND"


# ─── LZ: Leading Zero Preservation ───────────────────────────────────────────

LEADING_ZERO_VAL = "012345678905"
_IDENT_LEADING = {
    "id": str(uuid.uuid4()), "chemical_product_id": PROD_A_ID,
    "factory_id": FAC_A, "identifier_type": "BARCODE",
    "identifier_value": LEADING_ZERO_VAL, "identifier_normalized": LEADING_ZERO_VAL,
    "is_active": True,
}

class TestLeadingZero:
    """LZ01-LZ02: Leading zero must be preserved; stripped scan → NOT_FOUND."""

    def test_lz01_leading_zero_exact_match(self):
        sb = _make_sb(identifiers=[_IDENT_LEADING])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", LEADING_ZERO_VAL)
        assert result["state"] == "MATCHED"

    def test_lz02_stripped_leading_zero_not_found(self):
        stripped = LEADING_ZERO_VAL.lstrip("0")
        sb = _make_sb(identifiers=[_IDENT_LEADING])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", stripped)
        assert result["state"] == "NOT_FOUND"


# ─── DQ: Deduplication (same product, multiple identifier types) ──────────────

class TestDeduplication:
    """DQ01: Same product with EAN+GTIN+BARCODE rows = MATCHED (not AMBIGUOUS)."""

    def test_dq01_same_product_multi_identifier_types(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN, _IDENT_A_GTIN, _IDENT_A_BARCODE])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "CODE_128")
        assert result["state"] == "MATCHED"
        assert result["product"]["id"] == PROD_A_ID

    def test_dq02_matched_identifiers_has_all_hit_rows(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN, _IDENT_A_GTIN, _IDENT_A_BARCODE])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "CODE_128")
        types_found = {i["identifier_type"] for i in result["matched_identifiers"]}
        # All three identifier rows returned (all same product)
        assert len(result["matched_identifiers"]) == 3
        assert types_found == {"EAN", "GTIN", "BARCODE"}


# ─── AM: Ambiguous ────────────────────────────────────────────────────────────

PROD_C_ID = str(uuid.uuid4())

class TestAmbiguous:
    """AM01-AM04: AMBIGUOUS when same scan value maps to multiple distinct ACTIVE products."""

    def _ambiguous_sb(self):
        prod_c = {
            "id": PROD_C_ID, "factory_id": FAC_A, "product_name": "제품 C",
            "manufacturer_name": "제조사C", "identity_status": "CONFIRMED",
            "status_code": "ACTIVE",
        }
        ident_c = {
            "id": str(uuid.uuid4()), "chemical_product_id": PROD_C_ID,
            "factory_id": FAC_A, "identifier_type": "GTIN",
            "identifier_value": BARCODE_VAL, "identifier_normalized": BARCODE_VAL,
            "is_active": True,
        }
        return _make_sb(
            products=list(_BASE_PRODUCTS) + [prod_c],
            identifiers=[_IDENT_A_BARCODE, ident_c],
        )

    def test_am01_state_is_ambiguous(self):
        sb = self._ambiguous_sb()
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL)
        assert result["state"] == "AMBIGUOUS"

    def test_am02_candidates_list_has_both_products(self):
        sb = self._ambiguous_sb()
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL)
        ids = {c["product_id"] for c in result["candidates"]}
        assert PROD_A_ID in ids
        assert PROD_C_ID in ids

    def test_am03_no_auto_select(self):
        sb = self._ambiguous_sb()
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL)
        assert "product" not in result or result.get("product") is None
        assert result.get("state") == "AMBIGUOUS"

    def test_am04_ambiguous_zero_db_writes(self):
        sb = self._ambiguous_sb()
        svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL)
        assert _write_count(sb) == 0


# ─── QR: QR_ALIAS lookup ──────────────────────────────────────────────────────

class TestQrResolution:
    """QR01-QR05: QR uses only QR_ALIAS; opaque string; case-sensitive."""

    def test_qr01_exact_match(self):
        sb = _make_sb(identifiers=[_IDENT_A_QR])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "QR", QR_VAL)
        assert result["state"] == "MATCHED"
        assert result["product"]["id"] == PROD_A_ID

    def test_qr02_case_sensitive_mismatch(self):
        sb = _make_sb(identifiers=[_IDENT_A_QR])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "QR", QR_VAL.upper())
        assert result["state"] == "NOT_FOUND"

    def test_qr03_qr_types_considered_only_qr_alias(self):
        sb = _make_sb(identifiers=[_IDENT_A_QR])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "QR", QR_VAL)
        assert result["scan"]["identifier_types_considered"] == ["QR_ALIAS"]

    def test_qr04_barcode_ean_not_found_as_qr(self):
        """QR lookup does not match EAN-type identifiers."""
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "QR", BARCODE_VAL)
        assert result["state"] == "NOT_FOUND"

    def test_qr05_url_string_treated_opaque(self):
        """URL-shaped QR value is matched as-is, not parsed."""
        url = "https://supplier.example/Product/AaBb?x=1"
        ident = dict(_IDENT_A_QR, identifier_value=url, identifier_normalized=url)
        sb = _make_sb(identifiers=[ident])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "QR", url)
        assert result["state"] == "MATCHED"


# ─── CF: Cross-Factory Isolation ─────────────────────────────────────────────

class TestCrossFactory:
    """CF01-CF02: Factory B cannot see Factory A products."""

    def _cross_sb(self):
        ident_b = {
            "id": str(uuid.uuid4()), "chemical_product_id": PROD_A_ID,
            "factory_id": FAC_A,  # stored in FAC_A only
            "identifier_type": "BARCODE",
            "identifier_value": BARCODE_VAL, "identifier_normalized": BARCODE_VAL,
            "is_active": True,
        }
        return _make_sb(identifiers=[ident_b])

    def test_cf01_factory_b_scan_returns_not_found(self):
        sb = self._cross_sb()
        result = svc.resolve_scan(sb, USER_B, FAC_B, "BARCODE", BARCODE_VAL)
        assert result["state"] == "NOT_FOUND"

    def test_cf02_factory_b_product_info_not_leaked(self):
        sb = self._cross_sb()
        result = svc.resolve_scan(sb, USER_B, FAC_B, "BARCODE", BARCODE_VAL)
        assert result.get("product") is None


# ─── IA: Inactive Identifier / Product ───────────────────────────────────────

class TestInactiveGuard:
    """IA01-IA03: Inactive identifiers and inactive products excluded."""

    def test_ia01_inactive_identifier_not_matched(self):
        inactive_ident = dict(_IDENT_A_EAN, is_active=False)
        sb = _make_sb(identifiers=[inactive_ident])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert result["state"] == "NOT_FOUND"

    def test_ia02_inactive_product_not_matched(self):
        inactive_product = dict(_BASE_PRODUCTS[0], status_code="INACTIVE")
        sb = _make_sb(identifiers=[_IDENT_A_EAN], products=[inactive_product])
        result = svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert result["state"] == "NOT_FOUND"

    def test_ia03_inactive_product_zero_writes(self):
        inactive_product = dict(_BASE_PRODUCTS[0], status_code="INACTIVE")
        sb = _make_sb(identifiers=[_IDENT_A_EAN], products=[inactive_product])
        svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert _write_count(sb) == 0


# ─── WR: No Writes ───────────────────────────────────────────────────────────

class TestNoWrites:
    """WR01-WR03: All result states produce zero DB writes."""

    def test_wr01_matched_zero_writes(self):
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert _write_count(sb) == 0

    def test_wr02_not_found_zero_writes(self):
        sb = _make_sb(identifiers=[])
        svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL)
        assert _write_count(sb) == 0

    def test_wr03_ambiguous_zero_writes(self):
        prod_c = {
            "id": PROD_C_ID, "factory_id": FAC_A, "product_name": "제품 C",
            "manufacturer_name": None, "identity_status": "DRAFT",
            "status_code": "ACTIVE",
        }
        ident_c = {
            "id": str(uuid.uuid4()), "chemical_product_id": PROD_C_ID,
            "factory_id": FAC_A, "identifier_type": "EAN",
            "identifier_value": BARCODE_VAL, "identifier_normalized": BARCODE_VAL,
            "is_active": True,
        }
        sb = _make_sb(
            products=list(_BASE_PRODUCTS) + [prod_c],
            identifiers=[_IDENT_A_EAN, ident_c],
        )
        svc.resolve_scan(sb, USER_A, FAC_A, "BARCODE", BARCODE_VAL, "EAN_13")
        assert _write_count(sb) == 0


# ─── AU: Authorization guard ─────────────────────────────────────────────────

class TestAuthGuard:
    """AU01-AU02: Unknown role → factory not found; wrong company → not found."""

    def test_au01_unknown_role_denied(self):
        user = {"id": "u-x", "company_id": CO_A, "role_code": "ZZZ"}
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, user, FAC_A, "BARCODE", BARCODE_VAL)
        assert exc.value.status_code == 404

    def test_au02_wrong_company_denied(self):
        user = {"id": "u-wrong", "company_id": CO_B, "role_code": "010"}
        sb = _make_sb(identifiers=[_IDENT_A_EAN])
        with pytest.raises(MsdsProductError) as exc:
            svc.resolve_scan(sb, user, FAC_A, "BARCODE", BARCODE_VAL)
        assert exc.value.status_code == 404
