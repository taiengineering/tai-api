"""CHEM Domain section-field helpers — Section 1 A02 product name.

No Search imports. Payload → A02 → itemDetail only.
"""
from services.kosha_msds.section_fields import extract_product_name


def test_extract_product_name_from_item_array():
    payload = [
        {"msdsItemCode": "A01", "msdsItemNameKor": "식별", "itemDetail": "x"},
        {"msdsItemCode": "A02", "msdsItemNameKor": "제품명",
         "itemDetail": "톨루엔"},
    ]
    assert extract_product_name(payload) == "톨루엔"


def test_extract_product_name_from_items_wrapper():
    payload = {
        "items": [
            {"msdsItemCode": "A02", "itemDetail": "벤젠"},
        ]
    }
    assert extract_product_name(payload) == "벤젠"


def test_extract_product_name_from_json_text():
    payload = '[{"msdsItemCode": "A02", "itemDetail": "에탄올"}]'
    assert extract_product_name(payload) == "에탄올"


def test_extract_product_name_missing_a02_returns_none():
    assert extract_product_name([{"msdsItemCode": "A01", "itemDetail": "x"}]) is None
    assert extract_product_name(None) is None
    assert extract_product_name([]) is None


def test_extract_product_name_blank_item_detail_returns_none():
    assert extract_product_name(
        [{"msdsItemCode": "A02", "itemDetail": "  "}]
    ) is None
    assert extract_product_name(
        [{"msdsItemCode": "A02", "itemDetail": None}]
    ) is None


def test_section_fields_has_no_search_dependency():
    import pathlib
    text = (
        pathlib.Path(__file__).resolve().parents[1]
        / "services" / "kosha_msds" / "section_fields.py"
    ).read_text(encoding="utf-8")
    assert "shared_search" not in text
    assert "SearchDocument" not in text
