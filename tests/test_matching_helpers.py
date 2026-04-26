"""services/matching_helpers 단위 테스트."""
from __future__ import annotations

import re
from datetime import datetime

import pytest

from services.matching_helpers import now_iso, validate_status_transition


def test_now_iso_parseable_utc():
    s = now_iso()
    datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_validate_status_transition_received_to_matching_ok():
    validate_status_transition("RECEIVED", "MATCHING")


def test_validate_status_transition_received_to_in_progress_raises():
    with pytest.raises(ValueError, match=re.escape("'RECEIVED'")):
        validate_status_transition("RECEIVED", "IN_PROGRESS")
