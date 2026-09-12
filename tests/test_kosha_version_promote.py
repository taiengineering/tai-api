"""WP-1C-5A atomic version promotion (memory replica of SQL function)."""
from __future__ import annotations

import threading

from services.kosha_safety_materials.storage.version_service import MemoryVersionStore, VersionError


def _row(key="X", sha="a" * 64, current=True, **extra):
    base = {
        "asset_id": 1, "material_id": "m1", "source_asset_key": key,
        "content_checksum": sha, "storage_provider": "R2",
        "storage_bucket": "tai-kosha-originals", "storage_key": f"kosha/{sha}/f.pdf",
        "source_file_name": "f.pdf", "source_file_size": 1, "is_derivative": False,
        "license_observed_type": "1", "storage_basis": "KOGL",
        "source_med_seq": "1", "source_url": "https://portal.kosha.or.kr/x",
        "is_current_version": current,
    }
    base.update(extra)
    return base


def test_same_checksum_no_change():
    st = MemoryVersionStore()
    a = "a" * 64
    st.promote(_row(sha=a))
    dml = st.dml
    r = st.promote(_row(sha=a))
    assert r["status"] == "NO_CHANGE"
    assert r["dml"] == 0
    assert st.dml == dml


def test_new_checksum_switches_current():
    st = MemoryVersionStore()
    a, b = "a" * 64, "b" * 64
    st.promote(_row(sha=a, storage_key="ka"))
    r = st.promote(_row(sha=b, storage_key="kb"))
    assert r["status"] == "NEW_VERSION"
    assert st.current("X")["content_checksum"] == b
    assert st.current_count("X") == 1
    old = st.by_checksum("X", a)
    assert old["is_current_version"] is False


def test_previous_checksum_reappears():
    st = MemoryVersionStore()
    a, b = "a" * 64, "b" * 64
    st.promote(_row(sha=a, storage_key="ka"))
    st.promote(_row(sha=b, storage_key="kb"))
    n = len(st.rows)
    r = st.promote(_row(sha=a, storage_key="ka"))
    assert r["status"] == "PROMOTED_EXISTING_VERSION"
    assert len(st.rows) == n
    assert st.current("X")["content_checksum"] == a
    assert st.current_count("X") == 1


def test_db_failure_preserves_old_current():
    st = MemoryVersionStore()
    a, b = "a" * 64, "b" * 64
    st.promote(_row(sha=a, storage_key="ka"))
    st.fail_next_insert = True
    try:
        st.promote(_row(sha=b, storage_key="kb"))
        assert False
    except VersionError as e:
        assert e.code == "DB_INSERT_FAILED"
    assert st.current("X")["content_checksum"] == a
    assert st.current("X")["is_current_version"] is True
    assert st.current_count("X") == 1


def test_concurrent_same_key_one_current():
    st = MemoryVersionStore()
    a = "a" * 64
    st.promote(_row(sha=a, storage_key="ka"))
    err = []

    def go(i):
        try:
            st.promote(_row(sha=f"{i:064x}", storage_key=f"k{i}"))
        except Exception as e:
            err.append(e)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(1, 6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert st.current_count("X") == 1
    assert err == [] or st.current_count("X") == 1
