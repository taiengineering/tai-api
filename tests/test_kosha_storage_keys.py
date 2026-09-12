"""WP-1C-5A storage_keys — logical checksum ≠ binary SHA."""
from services.kosha_safety_materials.asset_parser import logical_checksum
from services.kosha_safety_materials.storage.storage_keys import (
    content_checksum,
    object_key,
    sanitize_filename,
    source_asset_key,
    version_action,
)


def test_logical_key_matches_assets_checksum_formula():
    assert source_asset_key("m1", "FL1", 1, "a.pdf") == logical_checksum("m1", "FL1", 1, "a.pdf")


def test_content_hash_in_immutable_path():
    sak = source_asset_key("m1", "FL1", 1, "a.pdf")
    a = content_checksum(b"AAA")
    b = content_checksum(b"BBB")
    k1 = object_key("m1", sak, a, "hello world.pdf")
    k2 = object_key("m1", sak, b, "hello world.pdf")
    assert k1.startswith("kosha/m1/")
    assert a in k1
    assert k1 != k2
    assert k1.endswith("hello_world.pdf")
    assert version_action(a, a) == "NO_CHANGE"
    assert version_action(None, a) == "NEW_VERSION"


def test_sanitize_and_reject_short_sha():
    assert sanitize_filename("스티커.pdf") == "file.pdf"
    assert ".." not in sanitize_filename("../etc/passwd.pdf")
    try:
        object_key("m", "aa", "short", "f.pdf")
        assert False
    except ValueError:
        pass
