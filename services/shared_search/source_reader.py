"""Shared Supabase pagination helper.

WO-TAI-SHARED-SEARCH-F2. Every Domain adapter that reads its SoT
from Supabase uses ONE paginator. Individual `.range(start, end)`
loops duplicated across 7 adapters would violate the shared-use
modularization rule (F2 WO §14, §29).

The helper is intentionally minimal — Domain adapters supply the
table name, select clause, filter callable, and ordering. It handles
range-based pagination in fixed-size chunks and yields rows.
"""
from __future__ import annotations

from typing import Any, Callable, Iterator, Optional, Protocol


class SupabaseClient(Protocol):
    """Minimal duck-typed slice of the Supabase-py client used here.

    Anything that responds to `.table(name).select(...).range(...).execute()`
    with `.data` on the result works. Kept structural so tests can pass
    a fake without needing an actual Supabase library.
    """
    def table(self, name: str) -> Any: ...


def paginate_supabase(
    client: SupabaseClient,
    *,
    table: str,
    select: str,
    apply_filters: Optional[Callable[[Any], Any]] = None,
    order_column: Optional[str] = None,
    order_desc: bool = False,
    page_size: int = 1000,
) -> Iterator[dict]:
    """Yield rows from a Supabase table using range-based pagination.

    Parameters
    ----------
    client : SupabaseClient
        Supabase-py client (or a duck-typed test double).
    table : str
        Supabase table / view name.
    select : str
        Comma-separated column list passed to `.select(...)`.
    apply_filters : Callable[[query], query], optional
        Callable that receives the query builder after `.select(...)`
        and returns it with `.eq(...)` / `.neq(...)` / `.in_(...)`
        applied. Adapters own their filter policy; the paginator just
        composes.
    order_column : str, optional
        Column to `.order()` by. Required for stable pagination when
        the table doesn't have a natural row order.
    order_desc : bool
        If True, `.order(..., desc=True)`.
    page_size : int
        Rows per range window.
    """
    start = 0
    while True:
        q = client.table(table).select(select)
        if apply_filters is not None:
            q = apply_filters(q)
        if order_column is not None:
            q = q.order(order_column, desc=order_desc)
        q = q.range(start, start + page_size - 1)
        result = q.execute()
        rows = list(getattr(result, "data", None) or result or [])
        if not rows:
            return
        for row in rows:
            yield row
        if len(rows) < page_size:
            return
        start += page_size
