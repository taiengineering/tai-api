"""TAM-008C-005 — Read-only permission grant verification.

Checks whether an authenticated user holds a currently valid TAM permission grant
by querying tam_permission_grants and tam_permission_revocations (read-only).

Contract:
  docs/tam/TAI_WO_TAM_008C_AUTHORIZATION_LEDGER_DESIGN.md  (design anchor c388a7f6)

grant_valid=true signals only that the Grant record is valid.
Final business authorization also requires:
  - Active Core identity (TAI Core)
  - Core data access scope (company_scope.py / scoped_filter)
  - Business object scope
This service does NOT subsume those checks.

Fail-closed: DB failure raises TamError(503). Callers must not grant access on exception.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import psycopg2
import psycopg2.errors

log = logging.getLogger("tam.permissions")

_TAM_PG_DSN: Optional[str] = os.getenv("TAM_PG_DSN") or os.getenv("DATABASE_URL")

_ALLOWED_CODES = frozenset({
    "ROUTE_MANAGER",
    "ASSIGNEE_MANAGER",
    "REQUEST_SUBMITTER",
    "DELEGATION_MANAGER",
    "REQUEST_REVOKER",
})

# factory_id=None  → only company-wide grants match (g.factory_id IS NULL)
# factory_id=<id>  → company-wide OR factory-scoped grants match
# When factory_id param is NULL: `g.factory_id = NULL::uuid` evaluates to NULL,
# so only the IS NULL branch can be true → only company-wide grants qualify.
_GRANT_SQL = """
SELECT g.grant_id::text
FROM tam_permission_grants g
WHERE g.company_id        = %(company_id)s::uuid
  AND g.subject_user_id   = %(user_id)s::uuid
  AND g.permission_code   = %(permission_code)s
  AND (
      g.factory_id IS NULL
      OR g.factory_id = %(factory_id)s::uuid
  )
  AND g.valid_from <= CURRENT_TIMESTAMP
  AND (
      g.valid_until IS NULL
      OR CURRENT_TIMESTAMP < g.valid_until
  )
  AND NOT EXISTS (
      SELECT 1
      FROM tam_permission_revocations r
      WHERE r.grant_id = g.grant_id
  )
LIMIT 1
"""

_DENY_BASE: dict = {"grant_valid": False, "grant_id": None}


class TamError(Exception):
    """Domain exception — routers convert to HTTPException."""

    def __init__(self, http_status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"TamError({self.http_status}, {self.code!r})"


def _connect(dsn: Optional[str] = None) -> "psycopg2.extensions.connection":
    url = dsn or _TAM_PG_DSN
    if not url:
        raise TamError(503, "DB_NOT_CONFIGURED", "TAM database DSN is not configured")
    return psycopg2.connect(url)


def check_tam_permission_grant(
    user: dict,
    *,
    company_id: str,
    factory_id: Optional[str],
    permission_code: str,
    dsn: Optional[str] = None,
) -> dict:
    """Check whether the authenticated user holds a valid TAM permission grant.

    Args:
        user: Trusted dict from get_current_user() — never from request body.
        company_id: Company the permission is being checked against.
        factory_id: Target factory scope (None = company-wide check only).
        permission_code: One of the five Grant permission codes.
        dsn: Override DB connection string (test injection).

    Returns:
        {
            "grant_valid": bool,
            "grant_id":    str | None,
            "permission_code": str,
            "code":        str,
        }

    Raises:
        TamError(503, ...) on DB failure.
        Callers MUST NOT return grant_valid=True on TamError.
    """
    def _deny(code: str) -> dict:
        return {**_DENY_BASE, "permission_code": permission_code, "code": code}

    # ── Conditions 1-4: user identity completeness ────────────────────────────
    if not user.get("id"):
        return _deny("USER_ID_MISSING")

    if not user.get("company_id"):
        return _deny("COMPANY_ID_MISSING")

    if user.get("status_code") != "ACTIVE" or not user.get("is_active"):
        return _deny("USER_INACTIVE")

    # ── Condition 5: company scope ────────────────────────────────────────────
    if str(user["company_id"]) != str(company_id):
        return _deny("COMPANY_MISMATCH")

    # ── Condition 6: permission code guard ────────────────────────────────────
    if permission_code == "STEP_APPROVER":
        return _deny("SNAPSHOT_ONLY_PERMISSION")

    if permission_code not in _ALLOWED_CODES:
        return _deny("INVALID_PERMISSION_CODE")

    # ── Conditions 7-13: DB query (read-only) ─────────────────────────────────
    try:
        conn = _connect(dsn)
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.permissions: connection failed: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "Permission service temporarily unavailable")

    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_GRANT_SQL, {
                "company_id":      str(company_id),
                "user_id":         str(user["id"]),
                "permission_code": permission_code,
                "factory_id":      str(factory_id) if factory_id is not None else None,
            })
            row = cur.fetchone()
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.permissions: query failed: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "Permission service temporarily unavailable")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if row is None:
        return _deny("GRANT_NOT_FOUND")

    return {
        "grant_valid":      True,
        "grant_id":         str(row[0]),
        "permission_code":  permission_code,
        "code":             "GRANT_VALID",
    }
