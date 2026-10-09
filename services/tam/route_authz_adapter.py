"""TAM-008C-007 — TAM Route Authorization Adapter.

Resolves a TAM Route from the DB and delegates to check_tam_effective_authorization.
Returns a candidate authorization result — write_enabled is always False.

Data flow:
    Authenticated user + route_id
        → server-side route lookup (tam_approval_routes)
        → trusted Resource construction
        → check_tam_effective_authorization()
        → candidate result (write_enabled=False)

This adapter is a standalone internal service.
It is NOT registered with any HTTP router or application entrypoint.
HTTP write activation requires separate Owner approval (OD-01).

Design anchor: c388a7f6 (TAM-008C-003 FROZEN)
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

import psycopg2

from services.tam.authz_svc import check_tam_effective_authorization
from services.tam.permissions_svc import TamError

log = logging.getLogger("tam.route_authz")

_TAM_PG_DSN: Optional[str] = os.getenv("TAM_PG_DSN") or os.getenv("DATABASE_URL")

_ROUTE_SQL = """
SELECT
    route_id::text,
    company_id::text,
    factory_id::text
FROM tam_approval_routes
WHERE route_id   = %(route_id)s::uuid
  AND company_id = %(company_id)s::uuid
"""


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


def _connect(dsn: Optional[str] = None):
    url = dsn or _TAM_PG_DSN
    if not url:
        raise TamError(503, "DB_NOT_CONFIGURED", "TAM database DSN is not configured")
    try:
        return psycopg2.connect(url)
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.route_authz: connection failed: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "Route authorization service temporarily unavailable")


def _fetch_route(route_id: str, company_id: str, dsn: Optional[str] = None) -> Optional[dict]:
    """Return route dict or None. Route-not-found and cross-company both return None."""
    conn = _connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_ROUTE_SQL, {"route_id": route_id, "company_id": company_id})
            row = cur.fetchone()
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.route_authz: route query failed: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "Route authorization service temporarily unavailable")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if row is None:
        return None
    return {
        "route_id":   row[0],
        "company_id": row[1],
        "factory_id": row[2],  # None for company-wide routes
    }


def assess_tam_route_authorization_candidate(
    user: dict,
    *,
    route_id: str,
    dsn: Optional[str] = None,
) -> dict:
    """Assess whether a user is a candidate ROUTE_MANAGER for the given route.

    Performs:
      1. Route ID UUID format validation
      2. Server-side route lookup (user.company_id scoped — prevents cross-company leak)
      3. Trusted resource construction from DB values only
      4. check_tam_effective_authorization() delegation

    Returns:
        {
            "candidate_valid": bool,
            "write_enabled": False,        # always — OD-01 not yet authorized
            "grant_id": str | None,
            "code": str,
        }

    Raises:
        TamError(503) on any DB failure (fail-closed).
    """
    def _deny(code: str) -> dict:
        return {"candidate_valid": False, "write_enabled": False, "grant_id": None, "code": code}

    # Step 1: UUID format guard
    if not _is_valid_uuid(route_id):
        return _deny("INVALID_ROUTE_ID")

    # Step 2: Company ID required before DB query
    if not user.get("company_id"):
        return _deny("COMPANY_ID_MISSING")

    # Step 3: Server-side route lookup
    route = _fetch_route(str(route_id), str(user["company_id"]), dsn)
    if route is None:
        return _deny("ROUTE_NOT_FOUND")

    # Step 4: Trusted resource — DB values only, never from client input
    resource = {
        "id":         route["route_id"],
        "company_id": route["company_id"],
        "factory_id": route["factory_id"],
        "team_id":    None,              # TAM routes have no team_id column
    }

    # Step 5: Full effective authorization check
    authz = check_tam_effective_authorization(
        user,
        resource=resource,
        permission_code="ROUTE_MANAGER",
        dsn=dsn,
    )

    if not authz.get("authorized"):
        return _deny(authz.get("code", "AUTHORIZATION_DENIED"))

    return {
        "candidate_valid": True,
        "write_enabled":   False,        # write gate — never True here
        "grant_id":        authz.get("grant_id"),
        "code":            "CANDIDATE_VALID",
    }
