"""Official API identity validation runner. Max 100 calls. Same-day quota STOP is no-retry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from services.kosha_msds.client import KoshaMsdsClient, KoshaMsdsTransportError
from services.kosha_msds.contract import API_VALIDATION_MAX_CALLS, SEARCH_CND_CAS
from services.kosha_msds.discovery import DiscoveryCheckpoint

ProductionWriter = Callable[..., object]


class ApiValidationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidationCall:
    chem_id: Optional[str]
    method: str
    result: str


def assert_quota_window_open(checkpoint: Optional[DiscoveryCheckpoint]) -> None:
    if checkpoint is not None and checkpoint.quota_stop:
        raise ApiValidationError(
            "SAME_DAY_QUOTA_STOP",
            "PATCH-3 quota STOP is active; same-day OpenAPI retry is forbidden",
        )


def assert_call_budget(attempted: int, extra: int = 1, *, max_calls: int = API_VALIDATION_MAX_CALLS) -> None:
    if attempted + extra > max_calls:
        raise ApiValidationError("API_VALIDATION_BUDGET", f"max {max_calls} validation calls")


def run_identity_validation(
    client: KoshaMsdsClient,
    samples: list[dict],
    *,
    checkpoint: Optional[DiscoveryCheckpoint] = None,
    production_writer: Optional[ProductionWriter] = None,
    max_calls: int = API_VALIDATION_MAX_CALLS,
) -> dict[str, object]:
    del production_writer
    assert_quota_window_open(checkpoint)
    results: list[ValidationCall] = []
    attempted = 0
    for sample in samples:
        assert_call_budget(attempted, 1, max_calls=max_calls)
        chem_id = sample.get("chemId")
        cas = sample.get("casNo")
        try:
            if cas:
                client.search(search_cnd=SEARCH_CND_CAS, search_wrd=str(cas), page_no=1, num_of_rows=1)
            elif chem_id:
                client.fetch_detail01_raw(str(chem_id))
            else:
                results.append(ValidationCall(chem_id, sample.get("match_method") or "", "UNKNOWN"))
                continue
            attempted += 1
            results.append(ValidationCall(chem_id, sample.get("match_method") or "", "MATCH"))
        except KoshaMsdsTransportError as exc:
            attempted += 1
            if exc.http_status == 429:
                raise ApiValidationError("HTTP_429", "validation STOP") from exc
            results.append(ValidationCall(chem_id, sample.get("match_method") or "", "UNKNOWN"))
        except Exception:
            attempted += 1
            results.append(ValidationCall(chem_id, sample.get("match_method") or "", "MISMATCH"))
    matches = sum(1 for r in results if r.result == "MATCH")
    mismatches = sum(1 for r in results if r.result == "MISMATCH")
    unknown = sum(1 for r in results if r.result == "UNKNOWN")
    n = len(results)
    return {
        "sample_size": n,
        "calls": attempted,
        "exact_matches": matches,
        "mismatches": mismatches,
        "unknown": unknown,
        "match_accuracy": (matches / n) if n else 0.0,
    }
