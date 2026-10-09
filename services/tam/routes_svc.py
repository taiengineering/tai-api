"""TAM-008B — Approval Route Foundation service.

Scope: tam_approval_routes, tam_approval_route_versions,
       tam_approval_route_steps, tam_approval_step_assignees.

Design contract: docs/TAI_WO_TAM_006_DESIGN_CONSOLIDATION.md (DESIGN_MERGE_SHA 8fa4c9a2)

Authorization gate: permission ledger (ROUTE_MANAGER) is OWNER_DECISION_REQUIRED.
  All write operations are called only from isolated tests until the ledger is defined.
  The router layer enforces fail-closed 403 for all HTTP callers.

Tenant isolation (Layer 2):
  Every operation verifies user['company_id'] == route.company_id before any mutation.
  Existence is hidden behind 404 for cross-company access (no information leak).

R1 concurrency hardening:
  All write operations acquire SELECT FOR UPDATE on the route row first.
  publish_version additionally acquires SELECT FOR UPDATE on the version row immediately
  after the route lock (route → version consistent ordering prevents deadlock).
  Triggers 3 & 4 acquire FOR UPDATE on the version row within the same transaction,
  providing an additional guard for direct-SQL access paths.

R3 factory scope gate (fail-closed):
  create_route, get_route, list_routes block access to factory-scoped routes
  unless user.factory_id matches the route's factory_id exactly.
  role_data_scope (Supabase client) is incompatible with this psycopg2 layer;
  fail-closed until OD-01 owner decision.  Company-wide routes are unaffected.
"""
from __future__ import annotations

import logging
import os
import uuid as _uuid
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import psycopg2.errors

log = logging.getLogger("tam.routes")

__all__ = [
    "TamError",
    "create_route",
    "create_version",
    "create_step",
    "create_assignee",
    "publish_version",
    "get_route",
    "list_routes",
]

_DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")


class TamError(Exception):
    def __init__(self, http_status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"TamError({self.http_status}, {self.code!r})"


def _connect(dsn: Optional[str] = None) -> "psycopg2.extensions.connection":
    url = dsn or _DATABASE_URL
    if not url:
        raise TamError(500, "DB_NOT_CONFIGURED", "DATABASE_URL is not set")
    return psycopg2.connect(url)


def _cur(conn: "psycopg2.extensions.connection"):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _user_company(user: Dict[str, Any]) -> str:
    company = user.get("company_id") if user else None
    if not company:
        raise TamError(403, "USER_NO_COMPANY", "authenticated user has no company scope")
    return str(company)


def _user_id(user: Dict[str, Any]) -> str:
    uid = user.get("id") if user else None
    if not uid:
        raise TamError(401, "USER_NO_ID", "authenticated user has no id")
    return str(uid)


# ── Route ─────────────────────────────────────────────────────────────────────

def create_route(
    user: Dict[str, Any],
    *,
    company_id: str,
    factory_id: Optional[str] = None,
    route_scope: str,
    scope_key: Optional[str] = None,
    display_name: str,
    dsn: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new approval route. Tenant: user.company_id must equal company_id."""
    actor_company = _user_company(user)
    actor_id = _user_id(user)

    if actor_company != str(company_id):
        raise TamError(403, "CROSS_COMPANY_FORBIDDEN",
                       "route company_id must match authenticated user company")

    if route_scope not in ("COMPANY_DEFAULT", "FACTORY_DEFAULT", "DOCUMENT_TYPE", "PROCESS_TYPE"):
        raise TamError(422, "INVALID_ROUTE_SCOPE",
                       f"invalid route_scope: {route_scope!r}")

    if route_scope in ("COMPANY_DEFAULT", "FACTORY_DEFAULT") and scope_key is not None:
        raise TamError(422, "SCOPE_KEY_NOT_ALLOWED",
                       "scope_key must be NULL for DEFAULT scope types")

    if route_scope in ("DOCUMENT_TYPE", "PROCESS_TYPE") and not scope_key:
        raise TamError(422, "SCOPE_KEY_REQUIRED",
                       "scope_key is required for DOCUMENT_TYPE and PROCESS_TYPE scopes")

    if route_scope == "FACTORY_DEFAULT" and not factory_id:
        raise TamError(422, "FACTORY_ID_REQUIRED",
                       "factory_id is required for FACTORY_DEFAULT scope")

    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = _cur(conn)

        # R1: validate factory belongs to this company and is ACTIVE
        if factory_id:
            cur.execute(
                "SELECT id FROM factories WHERE id = %s AND company_id = %s AND status_code = 'ACTIVE'",
                (factory_id, company_id),
            )
            if not cur.fetchone():
                raise TamError(422, "FACTORY_NOT_FOUND",
                               f"factory {factory_id} not found or not accessible")

        # R3: fail-closed factory scope gate
        if factory_id is not None:
            user_factory = user.get("factory_id")
            if user_factory is None or str(user_factory) != str(factory_id):
                raise TamError(
                    422, "FACTORY_SCOPE_NOT_FINALIZED",
                    "factory-scoped route creation requires factory scope authorization "
                    "(contract pending OD-01 owner decision)",
                )

        cur.execute(
            """
            INSERT INTO tam_approval_routes
                (company_id, factory_id, route_scope, scope_key, display_name, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (company_id, factory_id, route_scope, scope_key, display_name, actor_id),
        )
        row = dict(cur.fetchone())
        conn.commit()
        return row
    except TamError:
        conn.rollback()
        raise
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise TamError(409, "ROUTE_SCOPE_DUPLICATE",
                       "a route with this scope already exists for the company/factory")
    except psycopg2.errors.CheckViolation as e:
        conn.rollback()
        raise TamError(422, "CONSTRAINT_VIOLATION", str(e)) from e
    except Exception as e:
        conn.rollback()
        raise TamError(500, "INTERNAL_ERROR", str(e)) from e
    finally:
        conn.close()


def get_route(
    user: Dict[str, Any],
    *,
    route_id: str,
    dsn: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        _uuid.UUID(str(route_id))
    except (ValueError, AttributeError):
        raise TamError(422, "INVALID_ROUTE_ID", "route_id는 UUID 형식이어야 합니다")

    actor_company = _user_company(user)

    try:
        conn = _connect(dsn)
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.routes: get_route DB 연결 실패: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "서비스를 일시적으로 이용할 수 없습니다") from exc

    try:
        cur = _cur(conn)
        cur.execute(
            "SELECT * FROM tam_approval_routes WHERE route_id = %s",
            (route_id,),
        )
        row = cur.fetchone()
        if not row or str(row["company_id"]) != actor_company:
            raise TamError(404, "ROUTE_NOT_FOUND", "route not found")

        # R3: fail-closed factory scope gate
        if row["factory_id"] is not None:
            user_factory = user.get("factory_id")
            if user_factory is None or str(user_factory) != str(row["factory_id"]):
                raise TamError(
                    422, "FACTORY_SCOPE_NOT_FINALIZED",
                    "access to factory-scoped routes requires factory scope authorization "
                    "(contract pending OD-01 owner decision)",
                )

        return dict(row)
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.routes: get_route SQL 오류: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "서비스를 일시적으로 이용할 수 없습니다") from exc
    finally:
        conn.close()


def list_routes(
    user: Dict[str, Any],
    *,
    company_id: str,
    factory_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    dsn: Optional[str] = None,
) -> List[Dict[str, Any]]:
    actor_company = _user_company(user)
    if actor_company != str(company_id):
        raise TamError(403, "CROSS_COMPANY_FORBIDDEN",
                       "company_id must match authenticated user company")

    user_factory = user.get("factory_id")

    # R3: factory scope gate on explicit factory_id filter
    if factory_id is not None:
        if user_factory is None or str(user_factory) != str(factory_id):
            raise TamError(
                422, "FACTORY_SCOPE_NOT_FINALIZED",
                "access to factory-scoped routes requires factory scope authorization "
                "(contract pending OD-01 owner decision)",
            )

    try:
        conn = _connect(dsn)
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.routes: list_routes DB 연결 실패: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "서비스를 일시적으로 이용할 수 없습니다") from exc

    try:
        cur = _cur(conn)
        sql = "SELECT * FROM tam_approval_routes WHERE company_id = %s"
        params: list = [company_id]

        # R3: restrict results to user's factory scope
        if user_factory is not None:
            sql += " AND (factory_id IS NULL OR factory_id = %s)"
            params.append(user_factory)
        else:
            sql += " AND factory_id IS NULL"

        if factory_id is not None:
            sql += " AND factory_id = %s"
            params.append(factory_id)
        if is_active is not None:
            sql += " AND is_active = %s"
            params.append(is_active)
        sql += " ORDER BY created_at"
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    except TamError:
        raise
    except Exception as exc:
        log.error("tam.routes: list_routes SQL 오류: %s", type(exc).__name__)
        raise TamError(503, "SERVICE_UNAVAILABLE", "서비스를 일시적으로 이용할 수 없습니다") from exc
    finally:
        conn.close()


# ── Version ───────────────────────────────────────────────────────────────────

def create_version(
    user: Dict[str, Any],
    *,
    route_id: str,
    notes: Optional[str] = None,
    dsn: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new DRAFT version for an existing route.

    R1: Route row is locked (SELECT FOR UPDATE) before computing MAX(version_number)+1
    to serialize concurrent creates and prevent UNIQUE(route_id, version_number) collisions.
    """
    actor_company = _user_company(user)
    actor_id = _user_id(user)

    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = _cur(conn)

        # R1: lock route row to serialize concurrent version number assignment
        cur.execute(
            "SELECT * FROM tam_approval_routes WHERE route_id = %s FOR UPDATE",
            (route_id,),
        )
        route = cur.fetchone()
        if not route or str(route["company_id"]) != actor_company:
            raise TamError(404, "ROUTE_NOT_FOUND", "route not found")

        # Atomic version_number increment under route lock: MAX + 1 within same route
        cur.execute(
            """
            INSERT INTO tam_approval_route_versions
                (route_id, version_number, notes, created_by)
            SELECT %s,
                   COALESCE(MAX(version_number), 0) + 1,
                   %s,
                   %s
              FROM tam_approval_route_versions
             WHERE route_id = %s
            RETURNING *
            """,
            (route_id, notes, actor_id, route_id),
        )
        row = dict(cur.fetchone())
        conn.commit()
        return row
    except TamError:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise TamError(500, "INTERNAL_ERROR", str(e)) from e
    finally:
        conn.close()


# ── Step ──────────────────────────────────────────────────────────────────────

def create_step(
    user: Dict[str, Any],
    *,
    version_id: str,
    step_order: int,
    step_name: str,
    step_type: str,
    allow_supplement: bool = False,
    dsn: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a step under a DRAFT version.

    R1: Route row is locked (SELECT FOR UPDATE) before re-checking version status,
    so a concurrent publish_version cannot promote the version between the tenant
    check and the INSERT.
    """
    actor_company = _user_company(user)
    actor_id = _user_id(user)

    if step_type not in ("SEQUENTIAL", "PARALLEL_ANY", "PARALLEL_ALL"):
        raise TamError(422, "INVALID_STEP_TYPE", f"invalid step_type: {step_type!r}")
    if step_order < 1:
        raise TamError(422, "INVALID_STEP_ORDER", "step_order must be >= 1")

    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = _cur(conn)

        # Tenant check via version → route chain (discover route_id; no lock yet)
        cur.execute(
            """
            SELECT r.route_id, r.company_id
              FROM tam_approval_route_versions v
              JOIN tam_approval_routes         r ON r.route_id = v.route_id
             WHERE v.version_id = %s
            """,
            (version_id,),
        )
        ver_row = cur.fetchone()
        if not ver_row or str(ver_row["company_id"]) != actor_company:
            raise TamError(404, "VERSION_NOT_FOUND", "version not found")

        # R1: lock route to serialize concurrent publish/step operations
        cur.execute(
            "SELECT route_id FROM tam_approval_routes WHERE route_id = %s FOR UPDATE",
            (str(ver_row["route_id"]),),
        )
        if not cur.fetchone():
            raise TamError(404, "VERSION_NOT_FOUND", "version not found")

        # Re-check version status under route lock
        cur.execute(
            "SELECT version_status FROM tam_approval_route_versions WHERE version_id = %s",
            (version_id,),
        )
        ver = cur.fetchone()
        if not ver or ver["version_status"] != "DRAFT":
            raise TamError(409, "VERSION_NOT_DRAFT", "can only add steps to DRAFT version")

        cur.execute(
            """
            INSERT INTO tam_approval_route_steps
                (version_id, step_order, step_name, step_type, allow_supplement)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (version_id, step_order, step_name, step_type, allow_supplement),
        )
        row = dict(cur.fetchone())
        conn.commit()
        return row
    except TamError:
        conn.rollback()
        raise
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise TamError(409, "STEP_ORDER_DUPLICATE",
                       "a step with this step_order already exists in the version")
    except Exception as e:
        conn.rollback()
        raise TamError(500, "INTERNAL_ERROR", str(e)) from e
    finally:
        conn.close()


# ── Assignee ──────────────────────────────────────────────────────────────────

def create_assignee(
    user: Dict[str, Any],
    *,
    step_id: str,
    user_id: str,
    dsn: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a user as assignee on a DRAFT version's step.

    R1:
      - Route row locked (SELECT FOR UPDATE) before re-checking version status.
      - Assignee user_id validated against users table: must exist, be ACTIVE,
        and belong to the same company as the actor.
    R2:
      - Factory-scoped routes (factory_id IS NOT NULL) are fail-closed:
        assignee designation raises FACTORY_SCOPE_NOT_FINALIZED until the
        factory scope authorization contract is resolved (OD-01 owner decision).
    """
    actor_company = _user_company(user)
    actor_id = _user_id(user)

    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = _cur(conn)

        # Tenant check via step → version → route chain (discover route_id; no lock yet)
        cur.execute(
            """
            SELECT r.company_id, r.route_id, r.factory_id, v.version_status
              FROM tam_approval_route_steps    s
              JOIN tam_approval_route_versions v ON v.version_id = s.version_id
              JOIN tam_approval_routes         r ON r.route_id   = v.route_id
             WHERE s.step_id = %s
            """,
            (step_id,),
        )
        row = cur.fetchone()
        if not row or str(row["company_id"]) != actor_company:
            raise TamError(404, "STEP_NOT_FOUND", "step not found")

        # R2: fail-closed — factory-scoped routes require factory scope authorization
        if row["factory_id"] is not None:
            raise TamError(
                422, "FACTORY_SCOPE_NOT_FINALIZED",
                "assignee designation for factory-scoped routes requires factory scope "
                "authorization (contract pending OD-01 owner decision)",
            )

        # R1: lock route to serialize concurrent publish/assignee operations
        cur.execute(
            "SELECT route_id FROM tam_approval_routes WHERE route_id = %s FOR UPDATE",
            (str(row["route_id"]),),
        )
        if not cur.fetchone():
            raise TamError(404, "STEP_NOT_FOUND", "step not found")

        # Re-check version status under route lock
        cur.execute(
            """
            SELECT v.version_status
              FROM tam_approval_route_steps    s
              JOIN tam_approval_route_versions v ON v.version_id = s.version_id
             WHERE s.step_id = %s
            """,
            (step_id,),
        )
        ver_status_row = cur.fetchone()
        if not ver_status_row or ver_status_row["version_status"] != "DRAFT":
            raise TamError(409, "VERSION_NOT_DRAFT",
                           "can only assign to steps in a DRAFT version")

        # R1: validate assignee — must exist, be ACTIVE, belong to actor's company
        cur.execute(
            "SELECT id, company_id, status_code, is_active FROM users WHERE id = %s",
            (user_id,),
        )
        target_user = cur.fetchone()
        if not target_user:
            raise TamError(422, "ASSIGNEE_NOT_FOUND", f"user {user_id} not found")
        if not target_user["is_active"] or target_user["status_code"] != "ACTIVE":
            raise TamError(422, "ASSIGNEE_INACTIVE", f"user {user_id} is not active")
        if str(target_user["company_id"]) != actor_company:
            raise TamError(422, "ASSIGNEE_CROSS_COMPANY",
                           f"assignee user {user_id} does not belong to actor company")

        cur.execute(
            """
            INSERT INTO tam_approval_step_assignees
                (step_id, user_id, assigned_by)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (step_id, user_id, actor_id),
        )
        result = dict(cur.fetchone())
        conn.commit()
        return result
    except TamError:
        conn.rollback()
        raise
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise TamError(409, "ASSIGNEE_DUPLICATE",
                       "this user is already an assignee for this step")
    except Exception as e:
        conn.rollback()
        raise TamError(500, "INTERNAL_ERROR", str(e)) from e
    finally:
        conn.close()


# ── Publish ───────────────────────────────────────────────────────────────────

def publish_version(
    user: Dict[str, Any],
    *,
    route_id: str,
    version_id: str,
    dsn: Optional[str] = None,
) -> Dict[str, Any]:
    """Atomic publish: DRAFT → PUBLISHED + update routes.current_version_id.

    Transaction (R1 lock ordering: route → version):
      1. SELECT route FOR UPDATE  (serialize concurrent publishes per route)
      2. Tenant check
      3. SELECT version FOR UPDATE  (prevent concurrent step edits while validating)
      4. Version belongs to route + is DRAFT
      5. All steps have >= 1 assignee
      6. Steps are sequential starting from 1 (no gaps, no duplicates)
      7. UPDATE version: DRAFT → PUBLISHED
      8. UPDATE route: current_version_id = version_id
      (trigger 1 verifies PUBLISHED status before step 8 commits)
    """
    actor_company = _user_company(user)
    actor_id = _user_id(user)

    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = _cur(conn)

        # 1. SELECT FOR UPDATE to serialize concurrent publish attempts on same route
        cur.execute(
            "SELECT * FROM tam_approval_routes WHERE route_id = %s FOR UPDATE",
            (route_id,),
        )
        route = cur.fetchone()
        if not route or str(route["company_id"]) != actor_company:
            raise TamError(404, "ROUTE_NOT_FOUND", "route not found")

        # 2. SELECT version FOR UPDATE immediately after route lock (consistent ordering)
        #    This blocks concurrent step/assignee INSERTs that also lock the version row.
        cur.execute(
            """
            SELECT * FROM tam_approval_route_versions
             WHERE version_id = %s AND route_id = %s
               FOR UPDATE
            """,
            (version_id, route_id),
        )
        version = cur.fetchone()
        if not version:
            raise TamError(404, "VERSION_NOT_FOUND", "version not found for this route")
        if version["version_status"] != "DRAFT":
            raise TamError(409, "VERSION_NOT_DRAFT", "version is not in DRAFT status")

        # 3. All steps must have >= 1 assignee; steps must be sequential from 1
        cur.execute(
            """
            SELECT s.step_id, s.step_order,
                   COUNT(a.assignee_id) AS assignee_count
              FROM tam_approval_route_steps      s
              LEFT JOIN tam_approval_step_assignees a ON a.step_id = s.step_id
             WHERE s.version_id = %s
             GROUP BY s.step_id, s.step_order
             ORDER BY s.step_order
            """,
            (version_id,),
        )
        steps = cur.fetchall()
        if not steps:
            raise TamError(422, "NO_STEPS",
                           "version must have at least one step before publishing")

        orders = [s["step_order"] for s in steps]
        expected = list(range(1, len(orders) + 1))
        if orders != expected:
            raise TamError(422, "STEPS_NOT_SEQUENTIAL",
                           f"step_order must be sequential starting from 1, got {orders}")

        for step in steps:
            if step["assignee_count"] == 0:
                raise TamError(
                    422,
                    "STEP_MISSING_ASSIGNEE",
                    f"step {step['step_order']} has no assignees assigned",
                )

        # 4. Promote version: DRAFT → PUBLISHED
        cur.execute(
            """
            UPDATE tam_approval_route_versions
               SET version_status = 'PUBLISHED',
                   published_at   = NOW(),
                   published_by   = %s
             WHERE version_id = %s
            """,
            (actor_id, version_id),
        )

        # 5. Point route to the new published version
        #    Trigger tam_routes_published_guard_trg fires here and verifies PUBLISHED status
        cur.execute(
            """
            UPDATE tam_approval_routes
               SET current_version_id = %s
             WHERE route_id = %s
            """,
            (version_id, route_id),
        )

        conn.commit()

        cur.execute(
            "SELECT * FROM tam_approval_route_versions WHERE version_id = %s",
            (version_id,),
        )
        return dict(cur.fetchone())
    except TamError:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise TamError(500, "INTERNAL_ERROR", str(e)) from e
    finally:
        conn.close()
