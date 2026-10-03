"""WO-E2E300-CLF10-CST-AMOUNT-EXACT-BRIDGE-REPAIR-026

Unit tests for _contract_eok_to_won() and create_factory_for_site() payload.

T1-T8:    helper unit tests
T9-T10:   Frozen20 / Pass80 regression (parametric)
T11:      create_factory_for_site integration (insert payload exact int)
"""
from __future__ import annotations

import sys
import os
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.construction_svc import _contract_eok_to_won, create_factory_for_site


# ─────────────────────────────────────────────────────────────────────────────
# T1: integer eok
# ─────────────────────────────────────────────────────────────────────────────
def test_T1_integer_eok():
    assert _contract_eok_to_won(8) == 800_000_000
    assert _contract_eok_to_won(8.00) == 800_000_000


# ─────────────────────────────────────────────────────────────────────────────
# T2: one decimal (was failing with float ×)
# ─────────────────────────────────────────────────────────────────────────────
def test_T2_one_decimal_eok():
    assert _contract_eok_to_won(8.3) == 830_000_000


# ─────────────────────────────────────────────────────────────────────────────
# T3: problematic frozen cases (were failing before WO-026)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("eok,expected_won", [
    (20.4,  2_040_000_000),
    (316.1, 31_610_000_000),
    (291.4, 29_140_000_000),
    (646.2, 64_620_000_000),
    (4.1,     410_000_000),
])
def test_T3_problematic_frozen_cases(eok, expected_won):
    assert _contract_eok_to_won(eok) == expected_won


# ─────────────────────────────────────────────────────────────────────────────
# T4: string input
# ─────────────────────────────────────────────────────────────────────────────
def test_T4_string_input():
    assert _contract_eok_to_won("8.30") == 830_000_000


# ─────────────────────────────────────────────────────────────────────────────
# T5: Decimal input
# ─────────────────────────────────────────────────────────────────────────────
def test_T5_decimal_input():
    assert _contract_eok_to_won(Decimal("8.30")) == 830_000_000


# ─────────────────────────────────────────────────────────────────────────────
# T6: None → 0
# ─────────────────────────────────────────────────────────────────────────────
def test_T6_none_returns_zero():
    assert _contract_eok_to_won(None) == 0


# ─────────────────────────────────────────────────────────────────────────────
# T7: invalid string → ValueError
# ─────────────────────────────────────────────────────────────────────────────
def test_T7_invalid_string_raises():
    with pytest.raises(ValueError, match="INVALID_CONTRACT_AMOUNT"):
        _contract_eok_to_won("abc")


# ─────────────────────────────────────────────────────────────────────────────
# T8: non-integral WON → ValueError (no auto-rounding)
# ─────────────────────────────────────────────────────────────────────────────
def test_T8_non_integral_won_raises():
    # 0.000000001 억 = 0.1원 — non-integer WON, must not silently round
    with pytest.raises(ValueError, match="NON_INTEGER_WON_AMOUNT"):
        _contract_eok_to_won("0.000000001")


# ─────────────────────────────────────────────────────────────────────────────
# T9: Frozen20 exact — all 20 C1-fail cases must produce exact integer WON
# ─────────────────────────────────────────────────────────────────────────────
FROZEN20 = [
    ("CST-013", 8.3, 830000000),
    ("CST-021", 20.4, 2040000000),
    ("CST-022", 316.1, 31610000000),
    ("CST-032", 159.8, 15980000000),
    ("CST-043", 9.8, 980000000),
    ("CST-046", 19.9, 1990000000),
    ("CST-050", 150.3, 15030000000),
    ("CST-054", 291.4, 29140000000),
    ("CST-056", 157.8, 15780000000),
    ("CST-058", 41.2, 4120000000),
    ("CST-059", 287.4, 28740000000),
    ("CST-062", 311.9, 31190000000),
    ("CST-063", 73.1, 7310000000),
    ("CST-074", 64.4, 6440000000),
    ("CST-079", 78.9, 7890000000),
    ("CST-083", 646.2, 64620000000),
    ("CST-094", 84.6, 8460000000),
    ("CST-095", 33.3, 3330000000),
    ("CST-098", 4.1, 410000000),
    ("CST-100", 4.1, 410000000),
]


@pytest.mark.parametrize("case_id,eok,expected_won", FROZEN20)
def test_T9_frozen20_exact(case_id, eok, expected_won):
    result = _contract_eok_to_won(eok)
    assert result == expected_won, (
        f"{case_id}: eok={eok} → got {result}, expected {expected_won}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T10: Pass80 exact — existing 80 PASS cases must remain exact
# ─────────────────────────────────────────────────────────────────────────────
PASS80 = [
    ("CST-001", 598.9, 59890000000),
    ("CST-002", 681.1, 68110000000),
    ("CST-003", 995.3, 99530000000),
    ("CST-004", 317.5, 31750000000),
    ("CST-005", 577.4, 57740000000),
    ("CST-006", 907.2, 90720000000),
    ("CST-007", 230.2, 23020000000),
    ("CST-008", 310.3, 31030000000),
    ("CST-009", 682.9, 68290000000),
    ("CST-010", 589.9, 58990000000),
    ("CST-011", 6.9, 690000000),
    ("CST-012", 11.5, 1150000000),
    ("CST-014", 14.6, 1460000000),
    ("CST-015", 12.5, 1250000000),
    ("CST-016", 216.1, 21610000000),
    ("CST-017", 156.6, 15660000000),
    ("CST-018", 33.0, 3300000000),
    ("CST-019", 116.1, 11610000000),
    ("CST-020", 456.2, 45620000000),
    ("CST-023", 201.9, 20190000000),
    ("CST-024", 381.0, 38100000000),
    ("CST-025", 93.0, 9300000000),
    ("CST-026", 172.1, 17210000000),
    ("CST-027", 76.2, 7620000000),
    ("CST-028", 190.3, 19030000000),
    ("CST-029", 63.2, 6320000000),
    ("CST-030", 44.0, 4400000000),
    ("CST-031", 57.4, 5740000000),
    ("CST-033", 66.0, 6600000000),
    ("CST-034", 299.0, 29900000000),
    ("CST-035", 213.6, 21360000000),
    ("CST-036", 21.7, 2170000000),
    ("CST-037", 1.9, 190000000),
    ("CST-038", 14.0, 1400000000),
    ("CST-039", 15.1, 1510000000),
    ("CST-040", 6.1, 610000000),
    ("CST-041", 14.0, 1400000000),
    ("CST-042", 47.4, 4740000000),
    ("CST-044", 11.7, 1170000000),
    ("CST-045", 18.3, 1830000000),
    ("CST-047", 9.4, 940000000),
    ("CST-048", 20.0, 2000000000),
    ("CST-049", 230.0, 23000000000),
    ("CST-051", 52.6, 5260000000),
    ("CST-052", 124.8, 12480000000),
    ("CST-053", 258.8, 25880000000),
    ("CST-055", 102.2, 10220000000),
    ("CST-057", 120.2, 12020000000),
    ("CST-060", 147.5, 14750000000),
    ("CST-061", 437.7, 43770000000),
    ("CST-064", 411.5, 41150000000),
    ("CST-065", 153.5, 15350000000),
    ("CST-066", 431.5, 43150000000),
    ("CST-067", 307.3, 30730000000),
    ("CST-068", 1098.2, 109820000000),
    ("CST-069", 1419.4, 141940000000),
    ("CST-070", 1619.6, 161960000000),
    ("CST-071", 1900.2, 190020000000),
    ("CST-072", 1856.1, 185610000000),
    ("CST-073", 724.3, 72430000000),
    ("CST-075", 80.8, 8080000000),
    ("CST-076", 95.3, 9530000000),
    ("CST-077", 2.5, 250000000),
    ("CST-078", 91.7, 9170000000),
    ("CST-080", 22.1, 2210000000),
    ("CST-081", 87.1, 8710000000),
    ("CST-082", 567.0, 56700000000),
    ("CST-084", 38.1, 3810000000),
    ("CST-085", 554.5, 55450000000),
    ("CST-086", 329.5, 32950000000),
    ("CST-087", 687.4, 68740000000),
    ("CST-088", 739.6, 73960000000),
    ("CST-089", 674.6, 67460000000),
    ("CST-090", 125.5, 12550000000),
    ("CST-091", 62.7, 6270000000),
    ("CST-092", 55.5, 5550000000),
    ("CST-093", 86.7, 8670000000),
    ("CST-096", 132.9, 13290000000),
    ("CST-097", 3.1, 310000000),
    ("CST-099", 2.9, 290000000),
]


@pytest.mark.parametrize("case_id,eok,expected_won", PASS80)
def test_T10_pass80_exact(case_id, eok, expected_won):
    result = _contract_eok_to_won(eok)
    assert result == expected_won, (
        f"{case_id}: eok={eok} → got {result}, expected {expected_won}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T11: create_factory_for_site — insert payload has exact integer WON
# ─────────────────────────────────────────────────────────────────────────────
def test_T11_create_factory_payload_exact_int():
    """create_factory_for_site() must send exact integer WON to factories table."""
    inserts = []
    updates = []

    class _R:
        def __init__(self, data): self.data = data

    class _Table:
        def __init__(self, name, inserts, updates):
            self._name = name
            self._inserts = inserts
            self._updates = updates
        def insert(self, payload):
            self._inserts.append((self._name, payload))
            return self
        def update(self, payload):
            self._updates.append((self._name, payload))
            return self
        def eq(self, *a): return self
        def execute(self):
            if self._inserts:
                return _R([{"id": "factory-uuid-001"}])
            return _R([])

    class _SB:
        def __init__(self, inserts, updates):
            self._inserts = inserts
            self._updates = updates
        def table(self, name):
            return _Table(name, self._inserts, self._updates)

    sb = _SB(inserts, updates)
    site = {
        "id": "site-uuid-001",
        "site_name": "E2E300-CST-021",
        "company_id": "company-uuid-001",
        "contract_amount": 20.4,   # was failing: 20.4 * 100_000_000 = 2039999999.9999998
        "site_type": "003",
        "direct_workers": 50,
        "subcon_workers": 10,
        "site_address": "서울시",
    }
    factory_id = create_factory_for_site(sb, site, lambda: "2026-10-03T00:00:00+00:00")

    assert factory_id == "factory-uuid-001"
    assert len(inserts) == 1
    _, payload = inserts[0]

    construction_amount = payload["construction_amount"]
    assert isinstance(construction_amount, int), (
        f"construction_amount must be int, got {type(construction_amount).__name__}: {construction_amount}"
    )
    assert construction_amount == 2_040_000_000, (
        f"expected 2040000000, got {construction_amount}"
    )
