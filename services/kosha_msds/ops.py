"""OBJ-CHEM-FULL-READINESS-004 — MSDS operations observability (read-only).

Pure-composition status collectors that read from existing sources
and never mutate anything:

    hydration      → local CHEM-04 artifact  (checkpoint.json / run_report.json /
                                              responses.jsonl)
    production_db  → existing kosha_msds_*   (via CHEM-06 read /
                                              CHEM-10 publish stores)
    publication    → snapshots + snapshot_items
    public_runtime → KOSHA_MSDS_PUBLIC_MODE env var only
    search_dictionary
                   → live GET /search-dict/{health,census,lookup}
                     (falls through to UNVERIFIED_NETWORK on any error;
                     CLI still exits 0)
    full_readiness → services.kosha_msds.cutover.is_full_ready
                     (reuses CHEM-10 preflight_publish; no new gate)

No new engine, no new schema, no new alert framework. Alerts are
simple rules over the collected canonical values.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from services.kosha_msds.contract import (
    ALLOWED_PUBLIC_MODES,
    DEFAULT_PUBLIC_MODE,
    ENUMERATION_FULL_OFFICIAL,
    PUBLIC_MODE_ENV_VAR,
    PUBLIC_MODE_FULL,
    PUBLIC_MODE_OFF,
    PUBLIC_MODE_SEO_PREVIEW,
    PUBLISH_NOT_PUBLISHED,
    PUBLISH_PUBLISHED_FULL,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_RUNNING,
)


# Frozen expectations mirrored from CHEM-04 / CHEM-05 / CHEM-08.
EXPECTED_QUEUE_ROWS = 329_088
EXPECTED_CHEMICAL_COUNT = 20_568


# Search dictionary runtime binding vocabulary.
BINDING_V2_MATCH = "V2_MATCH"
BINDING_V1_OR_OTHER = "V1_OR_OTHER"
BINDING_UNVERIFIED_NETWORK = "UNVERIFIED_NETWORK"

EXPECTED_V2_SNAPSHOT_ID = "SEARCH-DICT-LEGPROD-2026-09-16"


# Alert vocabulary.
ALERT_HYDRATION_ARTIFACT_MISSING = "HYDRATION_ARTIFACT_MISSING"
ALERT_RUNNING_SNAPSHOT_STALE = "RUNNING_SNAPSHOT_STALE"
ALERT_FAILED_SNAPSHOT_PRESENT = "FAILED_SNAPSHOT_PRESENT"
ALERT_PREVIEW_COUNT_MISMATCH = "PREVIEW_COUNT_MISMATCH"
ALERT_FULL_MODE_WITHOUT_FULL_PUBLICATION = "FULL_MODE_WITHOUT_FULL_PUBLICATION"
ALERT_DICTIONARY_RUNTIME_NOT_V2 = "DICTIONARY_RUNTIME_NOT_V2"
ALERT_PUBLIC_MODE_FAILSAFE_OFF = "PUBLIC_MODE_FAILSAFE_OFF"


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------


@dataclass
class HydrationStatus:
    artifact_dir: Optional[str]
    status: str                     # OK / ARTIFACT_NOT_AVAILABLE
    queue_total: int = EXPECTED_QUEUE_ROWS
    completed: Optional[int] = None
    remaining: Optional[int] = None
    unique_chemicals: Optional[int] = None
    complete_chemicals: Optional[int] = None
    incomplete_chemicals: Optional[int] = None
    next_pending_chem_id: Optional[str] = None
    next_pending_section: Optional[int] = None
    last_terminal_reason: Optional[str] = None
    last_run_at: Optional[str] = None
    responses_sha256: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "artifact_dir": self.artifact_dir,
            "status": self.status,
            "queue_total": self.queue_total,
            "completed": self.completed,
            "remaining": self.remaining,
            "unique_chemicals": self.unique_chemicals,
            "complete_chemicals": self.complete_chemicals,
            "incomplete_chemicals": self.incomplete_chemicals,
            "next_pending_chem_id": self.next_pending_chem_id,
            "next_pending_section": self.next_pending_section,
            "last_terminal_reason": self.last_terminal_reason,
            "last_run_at": self.last_run_at,
            "responses_sha256": self.responses_sha256,
            "note": self.note,
        }


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_hydration_status(
    artifact_dir: Optional[str],
    *,
    deep_scan: bool = True,
) -> HydrationStatus:
    """Read the CHEM-04 official_v12 artifact. Returns a status even
    if the artifact is missing (ARTIFACT_NOT_AVAILABLE). Never
    fabricates numbers.
    """
    if not artifact_dir:
        return HydrationStatus(
            artifact_dir=None, status="ARTIFACT_NOT_AVAILABLE",
            note="artifact_dir is not supplied",
        )
    p = Path(artifact_dir)
    if not p.exists():
        return HydrationStatus(
            artifact_dir=str(p), status="ARTIFACT_NOT_AVAILABLE",
            note="directory does not exist",
        )
    run_report = _read_json(p / "run_report.json")
    checkpoint = _read_json(p / "checkpoint.json")
    responses_path = p / "responses.jsonl"

    completed = None
    remaining = None
    last_terminal_reason = None
    last_run_at = None
    if run_report is not None:
        completed = run_report.get("total_completed")
        remaining = run_report.get("remaining")
        last_terminal_reason = run_report.get("stop_reason")
        last_run_at = run_report.get("ended_at")
    if completed is None and checkpoint is not None:
        # Fallback: derive from checkpoint's cumulative fields.
        start_completed = checkpoint.get("start_completed") or 0
        new_success = checkpoint.get("new_success") or 0
        new_official_empty = checkpoint.get("new_official_empty") or 0
        completed = start_completed + new_success + new_official_empty
        remaining = EXPECTED_QUEUE_ROWS - completed
        last_terminal_reason = checkpoint.get("stop_reason") or last_terminal_reason
        last_run_at = checkpoint.get("updated_at") or last_run_at

    unique_chemicals = None
    complete_chemicals = None
    incomplete_chemicals = None
    next_pending_chem_id = None
    next_pending_section = None

    if deep_scan and responses_path.exists():
        # Count unique chemicals and detail-status from responses.jsonl.
        by_chem: dict[str, set[int]] = {}
        try:
            with responses_path.open(encoding="utf-8") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cid = str(r.get("chemId") or "")
                    sec = r.get("sectionNo")
                    if not cid or sec is None:
                        continue
                    try:
                        sec_int = int(sec)
                    except (TypeError, ValueError):
                        continue
                    by_chem.setdefault(cid, set()).add(sec_int)
        except OSError:
            by_chem = {}
        unique_chemicals = len(by_chem)
        complete_chemicals = sum(1 for secs in by_chem.values() if len(secs) == 16)
        incomplete_chemicals = unique_chemicals - complete_chemicals

    # next_pending: from checkpoint's last_completed pair, hop to the
    # subsequent (chem, section) using the queue order that the runner
    # itself walks (see tools/chem04/official_hydrate_v12.py). We do NOT
    # scan the queue file here; instead we report the "first not-in-
    # responses" pair via checkpoint's tail hint.
    if checkpoint is not None:
        last_cid = checkpoint.get("last_completed_chemId")
        last_sec = checkpoint.get("last_completed_sectionNo")
        if last_cid and isinstance(last_sec, int):
            if last_sec < 16:
                next_pending_chem_id = str(last_cid)
                next_pending_section = last_sec + 1
            else:
                # runner steps to the next chemId; without a queue scan
                # we cannot resolve which chemId is next, so leave None.
                next_pending_chem_id = None
                next_pending_section = None

    return HydrationStatus(
        artifact_dir=str(p),
        status="OK",
        completed=completed,
        remaining=remaining,
        unique_chemicals=unique_chemicals,
        complete_chemicals=complete_chemicals,
        incomplete_chemicals=incomplete_chemicals,
        next_pending_chem_id=next_pending_chem_id,
        next_pending_section=next_pending_section,
        last_terminal_reason=last_terminal_reason,
        last_run_at=last_run_at,
        responses_sha256=_file_sha256(responses_path),
    )


# ---------------------------------------------------------------------------
# Production DB
# ---------------------------------------------------------------------------


@dataclass
class ProductionStatus:
    chemicals: Optional[int] = None
    sections: Optional[int] = None
    snapshots: Optional[int] = None
    snapshot_items: Optional[int] = None
    preview_current: Optional[int] = None
    full_current: Optional[int] = None
    latest_completed_snapshot: Optional[str] = None
    latest_preview_snapshot: Optional[str] = None
    latest_full_snapshot: Optional[str] = None
    running_snapshots: Optional[int] = None
    failed_snapshots: Optional[int] = None
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def collect_production_status(*, publish_store, read_store=None) -> ProductionStatus:
    """Best-effort read against the (Supabase or memory) store.

    The publish store already exposes `latest_published_snapshot` per
    scope (CHEM-10). For chemicals / sections / snapshot_items totals
    we walk the store's internal collections when they exist on a
    MemoryPublishStore (test), otherwise we leave them None (this
    module isn't meant to add production count queries — those live
    in the SEO preview daily sync).
    """
    status = ProductionStatus()

    latest_preview = None
    latest_full = None
    latest_completed = None
    try:
        from services.kosha_msds.contract import PUBLICATION_SCOPE_FULL, PUBLICATION_SCOPE_SEO_PREVIEW
        preview = publish_store.latest_published_snapshot(
            publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
        )
        if preview:
            latest_preview = preview.get("id")
        full = publish_store.latest_published_snapshot(
            publication_scope=PUBLICATION_SCOPE_FULL,
        )
        if full:
            latest_full = full.get("id")
    except Exception as exc:
        status.note = f"publish_store scope lookup failed: {exc}"

    # Memory-store internal peek: only if the collections are exposed
    # (MemoryPublishStore has `_snapshots`, `_items`, `_sections`).
    snaps = getattr(publish_store, "_snapshots", None)
    items = getattr(publish_store, "_items", None)
    sections = getattr(publish_store, "_sections", None)
    if isinstance(snaps, list):
        status.snapshots = len(snaps)
        status.running_snapshots = sum(
            1 for s in snaps if s.get("status") == SNAPSHOT_RUNNING
        )
        status.failed_snapshots = sum(
            1 for s in snaps if s.get("status") == SNAPSHOT_FAILED
        )
        # latest COMPLETED (any scope).
        completed = [s for s in snaps if s.get("status") == SNAPSHOT_COMPLETED]
        if completed:
            completed.sort(
                key=lambda s: (s.get("completed_at") or "",
                               s.get("started_at") or ""), reverse=True,
            )
            latest_completed = completed[0].get("id")
    if isinstance(items, list):
        status.snapshot_items = len(items)
        # Preview/full "current" counts: rows in items whose snapshot
        # is currently PUBLISHED_SEO_PREVIEW / PUBLISHED_FULL.
        by_snap = {}
        if isinstance(snaps, list):
            for s in snaps:
                by_snap[str(s.get("id"))] = s.get("publish_state")
        preview_count = sum(
            1 for i in items
            if by_snap.get(str(i.get("snapshot_id"))) == PUBLISH_PUBLISHED_SEO_PREVIEW
            and i.get("in_snapshot", True) is True
        )
        full_count = sum(
            1 for i in items
            if by_snap.get(str(i.get("snapshot_id"))) == PUBLISH_PUBLISHED_FULL
            and i.get("in_snapshot", True) is True
        )
        status.preview_current = preview_count
        status.full_current = full_count
    if isinstance(sections, list):
        status.sections = len({(str(s.get("chemical_id")), int(s.get("section_no")))
                                for s in sections})

    # chemicals: derived from read_store if it exposes _current /
    # _preview lists (MemoryMsdsReadStore).
    if read_store is not None:
        cur = getattr(read_store, "_current", None)
        prev = getattr(read_store, "_preview", None)
        if isinstance(cur, list):
            status.chemicals = len(cur)
        if isinstance(prev, list) and status.preview_current is None:
            status.preview_current = len(prev)

    status.latest_completed_snapshot = latest_completed
    status.latest_preview_snapshot = latest_preview
    status.latest_full_snapshot = latest_full
    return status


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


@dataclass
class PublicationStatus:
    latest_preview_snapshot: Optional[dict] = None
    latest_full_snapshot: Optional[dict] = None
    preview_count: int = 0
    full_count: int = 0

    def to_dict(self) -> dict:
        return {
            "latest_preview_snapshot": self.latest_preview_snapshot,
            "latest_full_snapshot": self.latest_full_snapshot,
            "preview_count": self.preview_count,
            "full_count": self.full_count,
        }


def collect_publication_status(*, publish_store) -> PublicationStatus:
    status = PublicationStatus()
    from services.kosha_msds.contract import (
        PUBLICATION_SCOPE_FULL, PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    prev = publish_store.latest_published_snapshot(
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    full = publish_store.latest_published_snapshot(
        publication_scope=PUBLICATION_SCOPE_FULL,
    )
    if prev:
        status.latest_preview_snapshot = _snapshot_summary(prev)
    if full:
        status.latest_full_snapshot = _snapshot_summary(full)
    snaps = getattr(publish_store, "_snapshots", None)
    if isinstance(snaps, list):
        status.preview_count = sum(
            1 for s in snaps
            if s.get("publish_state") == PUBLISH_PUBLISHED_SEO_PREVIEW
        )
        status.full_count = sum(
            1 for s in snaps if s.get("publish_state") == PUBLISH_PUBLISHED_FULL
        )
    return status


def _snapshot_summary(snap: Mapping[str, Any]) -> dict:
    return {
        "id": snap.get("id"),
        "status": snap.get("status"),
        "enumeration_mode": snap.get("enumeration_mode"),
        "publish_state": snap.get("publish_state"),
        "expected_count": snap.get("expected_count"),
        "discovered_count": snap.get("discovered_count"),
        "completed_at": snap.get("completed_at"),
    }


# ---------------------------------------------------------------------------
# Public runtime mode
# ---------------------------------------------------------------------------


@dataclass
class PublicRuntimeStatus:
    raw_env_value: Optional[str]
    resolved_mode: str
    effective_scope: str
    is_failsafe_off: bool

    def to_dict(self) -> dict:
        return {
            "raw_env_value": self.raw_env_value,
            "resolved_mode": self.resolved_mode,
            "effective_scope": self.effective_scope,
            "is_failsafe_off": self.is_failsafe_off,
        }


def collect_public_runtime(env: Optional[Mapping[str, str]] = None) -> PublicRuntimeStatus:
    env = env if env is not None else os.environ
    raw = env.get(PUBLIC_MODE_ENV_VAR)
    stripped = (raw or DEFAULT_PUBLIC_MODE).strip().lower()
    is_failsafe = False
    if stripped not in ALLOWED_PUBLIC_MODES:
        resolved = PUBLIC_MODE_OFF
        is_failsafe = True
    else:
        resolved = stripped
    scope_map = {
        PUBLIC_MODE_OFF: "OFF",
        PUBLIC_MODE_SEO_PREVIEW: "SEO_PREVIEW",
        PUBLIC_MODE_FULL: "FULL",
    }
    return PublicRuntimeStatus(
        raw_env_value=raw,
        resolved_mode=resolved,
        effective_scope=scope_map.get(resolved, "OFF"),
        is_failsafe_off=is_failsafe,
    )


# ---------------------------------------------------------------------------
# Search dictionary runtime binding
# ---------------------------------------------------------------------------


@dataclass
class DictionaryRuntimeStatus:
    runtime_snapshot: Optional[str]
    subjects: Optional[int]
    indexed_terms: Optional[int]
    chem_term_msds_matched: Optional[bool]
    chem_term_sds_matched: Optional[bool]
    binding: str        # V2_MATCH / V1_OR_OTHER / UNVERIFIED_NETWORK
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "runtime_snapshot": self.runtime_snapshot,
            "subjects": self.subjects,
            "indexed_terms": self.indexed_terms,
            "chem_term_msds_matched": self.chem_term_msds_matched,
            "chem_term_sds_matched": self.chem_term_sds_matched,
            "binding": self.binding,
            "error": self.error,
        }


def collect_dictionary_runtime(
    live_base_url: Optional[str],
    *,
    http_get=None,
    timeout: float = 5.0,
) -> DictionaryRuntimeStatus:
    """Live GET /search-dict/{health,census,lookup?q=MSDS&subject_type=CHEM_TERM}.

    `http_get` is injectable for tests: signature `(url: str, timeout: float) -> dict`.
    Production uses urllib. Any network failure returns
    binding=UNVERIFIED_NETWORK — never PASS-as-if-verified.
    """
    if not live_base_url:
        return DictionaryRuntimeStatus(
            runtime_snapshot=None, subjects=None, indexed_terms=None,
            chem_term_msds_matched=None, chem_term_sds_matched=None,
            binding=BINDING_UNVERIFIED_NETWORK,
            error="live_base_url not supplied",
        )

    if http_get is None:
        http_get = _urllib_get_json

    base = live_base_url.rstrip("/")
    try:
        health = http_get(f"{base}/search-dict/health", timeout=timeout)
        snapshot = health.get("snapshot")
        subjects = health.get("subjects")
        terms = health.get("indexed_terms")

        msds_hit = _lookup_matches(
            http_get, base, "MSDS", subject_type="CHEM_TERM",
            expected_subject_key="물질안전보건자료", timeout=timeout,
        )
        sds_hit = _lookup_matches(
            http_get, base, "SDS", subject_type="CHEM_TERM",
            expected_subject_key="물질안전보건자료", timeout=timeout,
        )

        binding = (BINDING_V2_MATCH if snapshot == EXPECTED_V2_SNAPSHOT_ID
                   else BINDING_V1_OR_OTHER)
        return DictionaryRuntimeStatus(
            runtime_snapshot=snapshot,
            subjects=subjects,
            indexed_terms=terms,
            chem_term_msds_matched=msds_hit,
            chem_term_sds_matched=sds_hit,
            binding=binding,
            error=None,
        )
    except Exception as exc:
        return DictionaryRuntimeStatus(
            runtime_snapshot=None, subjects=None, indexed_terms=None,
            chem_term_msds_matched=None, chem_term_sds_matched=None,
            binding=BINDING_UNVERIFIED_NETWORK,
            error=f"{type(exc).__name__}: {exc}",
        )


def _lookup_matches(
    http_get,
    base: str,
    q: str,
    *,
    subject_type: Optional[str],
    expected_subject_key: str,
    timeout: float,
) -> bool:
    import urllib.parse
    params = {"q": q}
    if subject_type is not None:
        params["subject_type"] = subject_type
    url = f"{base}/search-dict/lookup?{urllib.parse.urlencode(params)}"
    result = http_get(url, timeout=timeout)
    for item in result.get("items") or []:
        if item.get("subject_key") == expected_subject_key:
            return True
    return False


def _urllib_get_json(url: str, timeout: float = 5.0) -> dict:
    """Fallback HTTP GET using stdlib; returns parsed JSON dict."""
    import urllib.request
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# FULL readiness
# ---------------------------------------------------------------------------


@dataclass
class FullReadinessStatus:
    ready: bool
    reason: Optional[str]
    snapshot_id: Optional[str]
    details: Optional[dict]

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "reason": self.reason,
            "snapshot_id": self.snapshot_id,
            "details": self.details,
        }


def collect_full_readiness(*, publish_store) -> FullReadinessStatus:
    """If there's no completed FULL_OFFICIAL / NOT_PUBLISHED candidate
    snapshot, report NO_FULL_CANDIDATE (not an error). Otherwise
    delegate to CHEM-08/CHEM-10 canonical readiness check via
    services.kosha_msds.cutover.is_full_ready.
    """
    snaps = getattr(publish_store, "_snapshots", None)
    candidate = None
    if isinstance(snaps, list):
        for s in snaps:
            if (s.get("status") == SNAPSHOT_COMPLETED
                    and s.get("enumeration_mode") == ENUMERATION_FULL_OFFICIAL
                    and s.get("publish_state") == PUBLISH_NOT_PUBLISHED):
                candidate = s
                break
    if candidate is None:
        return FullReadinessStatus(
            ready=False, reason="NO_FULL_CANDIDATE",
            snapshot_id=None, details=None,
        )

    from services.kosha_msds.cutover import is_full_ready
    report = is_full_ready(str(candidate.get("id")), store=publish_store)
    return FullReadinessStatus(
        ready=report.ready,
        reason=None if report.ready else "PREFLIGHT_BLOCKED",
        snapshot_id=report.snapshot_id,
        details=report.to_dict(),
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Alert:
    code: str
    severity: str
    evidence: str

    def to_dict(self) -> dict:
        return {"code": self.code, "severity": self.severity, "evidence": self.evidence}


def derive_alerts(
    *,
    hydration: HydrationStatus,
    production: ProductionStatus,
    publication: PublicationStatus,
    public_runtime: PublicRuntimeStatus,
    dictionary: DictionaryRuntimeStatus,
) -> list[Alert]:
    alerts: list[Alert] = []
    if hydration.status == "ARTIFACT_NOT_AVAILABLE":
        alerts.append(Alert(
            code=ALERT_HYDRATION_ARTIFACT_MISSING,
            severity="INFO",
            evidence=hydration.note or "artifact dir not present",
        ))
    if (production.running_snapshots or 0) > 0:
        alerts.append(Alert(
            code=ALERT_RUNNING_SNAPSHOT_STALE,
            severity="WARN",
            evidence=f"running_snapshots={production.running_snapshots}",
        ))
    if (production.failed_snapshots or 0) > 0:
        alerts.append(Alert(
            code=ALERT_FAILED_SNAPSHOT_PRESENT,
            severity="WARN",
            evidence=f"failed_snapshots={production.failed_snapshots}",
        ))
    if public_runtime.is_failsafe_off:
        alerts.append(Alert(
            code=ALERT_PUBLIC_MODE_FAILSAFE_OFF,
            severity="WARN",
            evidence=f"raw_env_value={public_runtime.raw_env_value!r}",
        ))
    if (public_runtime.resolved_mode == PUBLIC_MODE_FULL
            and publication.full_count == 0):
        alerts.append(Alert(
            code=ALERT_FULL_MODE_WITHOUT_FULL_PUBLICATION,
            severity="CRIT",
            evidence="public mode=full but no PUBLISHED_FULL snapshot exists",
        ))
    if dictionary.binding == BINDING_V1_OR_OTHER:
        alerts.append(Alert(
            code=ALERT_DICTIONARY_RUNTIME_NOT_V2,
            severity="WARN",
            evidence=f"runtime_snapshot={dictionary.runtime_snapshot!r}",
        ))
    return alerts


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def collect_status(
    *,
    artifact_dir: Optional[str],
    live_base_url: Optional[str],
    publish_store,
    read_store=None,
    env: Optional[Mapping[str, str]] = None,
    deep_scan: bool = True,
    http_get=None,
    git_main: Optional[str] = None,
    runner_version: Optional[str] = None,
    contract_version: str = "KOSHA_MSDS_OPENAPI_V1_2",
) -> dict:
    hydration = collect_hydration_status(artifact_dir, deep_scan=deep_scan)
    production = collect_production_status(
        publish_store=publish_store, read_store=read_store,
    )
    publication = collect_publication_status(publish_store=publish_store)
    public_runtime = collect_public_runtime(env=env)
    dictionary = collect_dictionary_runtime(live_base_url, http_get=http_get)
    full_readiness = collect_full_readiness(publish_store=publish_store)
    alerts = derive_alerts(
        hydration=hydration, production=production, publication=publication,
        public_runtime=public_runtime, dictionary=dictionary,
    )
    return {
        "repository": {
            "git_main": git_main,
            "runner_version": runner_version,
            "contract_version": contract_version,
        },
        "hydration": hydration.to_dict(),
        "production_db": production.to_dict(),
        "publication": publication.to_dict(),
        "public_runtime": public_runtime.to_dict(),
        "search_dictionary": dictionary.to_dict(),
        "full_readiness": full_readiness.to_dict(),
        "alerts": [a.to_dict() for a in alerts],
    }
