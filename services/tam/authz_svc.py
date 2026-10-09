"""TAM-008C-006 — TAI Core Effective Authorization Integration.

Combines four conditions into a single authorization result:
  1. Core Identity Gate  (user active, same company, role present)
  2. Core Role Scope     (role_data_scope DB lookup — direct psycopg2)
  3. Business Object Scope (company / factory / team membership)
  4. TAM Permission Grant  (via check_tam_permission_grant)

result authorized=true  iff all four conditions pass simultaneously.

Fail-closed contract:
  Any DB failure raises TamError(503).
  Callers MUST NOT grant access on exception.

Design anchor: c388a7f6 (TAM-008C-003 FROZEN)
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import psycopg2

from services.tam.permissions_svc import TamError, check_tam_permission_grant

log = logging.getLogger("tam.authz")

_TAM_PG_DSN: Optional[str] = os.getenv("TAM_PG_DSN") or os.getenv("DATABASE_URL")

_REQUIRED_RESOURCE_KEYS = frozenset({"id", "company_id", "factory_id", "team_id"})
_VALID_SCOPES = frozenset({"ALL", "COMPANY", "FACTORY", "TEAM", "ASSIGNED"})

_SCOPE_SQL = """
SELECT scope_type
FROM role_data_scope
WHERE role_code = %(role_code)s
"""

_FACTORY_SQL = """
SELECT id
FROM factories
WHERE id          = %(factory_id)s::uuid
  AND company_id  = %(company_id)s::uuid
  AND status_code = 'ACTIVE'
  AND deleted_at  IS NULL
"""


def _connect(dsn: Optional[str] = None):
    url = dsn or _TAM_PG_DSN
    if not url:
        raise TamError(503, "DB_NOT_CONFIGURED", "TAM database DSN is not configured")
    try:
        return psycopg2.connect(url)
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.authz: connection failed: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "Authorization service temporarily unavailable")


def _query_scope(role_code: str, dsn: Optional[str] = None) -> Optional[str]:
    """Return scope_type from role_data_scope, or None if missing/ambiguous/invalid."""
    conn = _connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_SCOPE_SQL, {"role_code": role_code})
            rows = cur.fetchall()
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.authz: scope query failed: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "Authorization service temporarily unavailable")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if len(rows) != 1:
        return None
    scope = rows[0][0]
    return scope if scope in _VALID_SCOPES else None


def _verify_factory(factory_id: str, company_id: str, dsn: Optional[str] = None) -> bool:
    """Return True iff factory exists, belongs to company, is ACTIVE, not soft-deleted."""
    conn = _connect(dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(_FACTORY_SQL, {
                "factory_id": factory_id,
                "company_id": company_id,
            })
            return cur.fetchone() is not None
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.authz: factory verify failed: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "Authorization service temporarily unavailable")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _check_object_scope(scope_type: str, user: dict, resource: dict) -> Optional[str]:
    """Return deny code if business object scope check fails, None if passes.

    ALL / COMPANY: company match (already verified) is sufficient.
    FACTORY: user.factory_id must match resource.factory_id (None → DENY).
    TEAM: factory must match; if resource.team_id present, team must match;
          company-wide resource (factory_id=None) is always DENY.
    ASSIGNED: handled before this call — should not reach here.
    """
    resource_factory_id = resource.get("factory_id")
    resource_team_id = resource.get("team_id")
    user_factory_id = user.get("factory_id")

    if scope_type in ("ALL", "COMPANY"):
        return None

    if scope_type == "FACTORY":
        if not user_factory_id:
            return "USER_FACTORY_MISSING"
        if resource_factory_id is None:
            return "FACTORY_SCOPE_MISMATCH"
        if str(user_factory_id) != str(resource_factory_id):
            return "FACTORY_SCOPE_MISMATCH"
        return None

    if scope_type == "TEAM":
        if not user_factory_id:
            return "USER_FACTORY_MISSING"
        if resource_factory_id is None:
            return "FACTORY_SCOPE_MISMATCH"
        if str(user_factory_id) != str(resource_factory_id):
            return "FACTORY_SCOPE_MISMATCH"
        if resource_team_id is not None:
            user_team_id = user.get("team_id")
            if not user_team_id:
                return "TEAM_SCOPE_MISMATCH"
            if str(user_team_id) != str(resource_team_id):
                return "TEAM_SCOPE_MISMATCH"
        return None

    return "ROLE_SCOPE_UNDEFINED"


def check_tam_effective_authorization(
    user: dict,
    *,
    resource: dict,
    permission_code: str,
    dsn: Optional[str] = None,
) -> dict:
    """Check full TAM effective authorization for a user against a business object.

    Args:
        user:            Trusted dict from get_current_user() — never from request body.
        resource:        Server-side DB row for the target business object.
                         Must contain: id, company_id, factory_id, team_id.
                         factory_id and team_id may be None for company-wide objects.
        permission_code: One of the five TAM grant permission codes.
        dsn:             Override DB connection string (test injection).

    Returns:
        {"authorized": bool, "grant_id": str | None, "code": str}

        authorized=true only when all four conditions pass.
        DENY results never leak other companies' data or grant IDs.

    Raises:
        TamError(503) on any DB failure (fail-closed).
    """
    def _deny(code: str) -> dict:
        return {"authorized": False, "grant_id": None, "code": code}

    # §4 Resource key completeness
    if not _REQUIRED_RESOURCE_KEYS.issubset(resource.keys()):
        return _deny("RESOURCE_SCOPE_MISSING")

    # §5 Core Identity Gate
    if not user.get("id"):
        return _deny("USER_ID_MISSING")
    if user.get("status_code") != "ACTIVE" or not user.get("is_active"):
        return _deny("USER_INACTIVE")
    if not user.get("company_id"):
        return _deny("COMPANY_ID_MISSING")
    if not resource.get("company_id"):
        return _deny("RESOURCE_COMPANY_MISSING")
    if str(user["company_id"]) != str(resource["company_id"]):
        return _deny("COMPANY_MISMATCH")
    if not user.get("role_code"):
        return _deny("ROLE_CODE_MISSING")

    # §6 Core Role Scope — DB lookup, fail-closed
    scope_type = _query_scope(str(user["role_code"]), dsn)
    if scope_type is None:
        return _deny("ROLE_SCOPE_UNDEFINED")
    if scope_type == "ASSIGNED":
        return _deny("ASSIGNMENT_SCOPE_NOT_READY")

    # §7 Business Object Scope Matrix
    scope_deny = _check_object_scope(scope_type, user, resource)
    if scope_deny is not None:
        return _deny(scope_deny)

    # §8 Factory Existence Verification
    resource_factory_id = resource.get("factory_id")
    if resource_factory_id is not None:
        if not _verify_factory(
            str(resource_factory_id), str(resource["company_id"]), dsn
        ):
            return _deny("FACTORY_NOT_FOUND")

    # §9 TAM Grant check (delegates to existing service — no duplicate logic)
    try:
        grant_result = check_tam_permission_grant(
            user,
            company_id=resource["company_id"],
            factory_id=resource["factory_id"],
            permission_code=permission_code,
            dsn=dsn,
        )
    except TamError:
        raise

    if not grant_result.get("grant_valid"):
        return _deny(grant_result.get("code", "GRANT_NOT_FOUND"))

    return {
        "authorized": True,
        "grant_id":   grant_result["grant_id"],
        "code":       "AUTHORIZED",
    }
