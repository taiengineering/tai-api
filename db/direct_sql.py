"""Direct Postgres connection — PostgREST 스키마 캐시 우회용.

PostgREST가 subscriptions.inicis_order_id 컨럼을 캐시에서 인식 못하는 문제 해결.
supabase.table() 대신 직접 SQL로 INSERT/SELECT/UPDATE 수행.

환경변수:
    DATABASE_URL — Supabase Dashboard > Settings > Database > Connection string (URI)
    예: postgresql://postgres.[ref]:[password]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres
"""
import os
import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_DATABASE_URL: Optional[str] = None


def _get_url() -> str:
    global _DATABASE_URL
    if _DATABASE_URL is None:
        _DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
    if not _DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL 환경변수가 설정되지 않았습니다. "
            "Supabase Dashboard > Settings > Database > Connection string (URI)"
        )
    return _DATABASE_URL


def _connect():
    import psycopg2
    import psycopg2.extras
    return psycopg2.connect(_get_url())


def insert_subscription(data: Dict[str, Any]) -> Dict[str, Any]:
    """subscriptions INSERT — PostgREST 우회. RETURNING * 로 생성된 row 반환."""
    import psycopg2.extras
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cols = list(data.keys())
            placeholders = [f"%({c})s" for c in cols]
            sql = f"""
                INSERT INTO subscriptions ({', '.join(cols)})
                VALUES ({', '.join(placeholders)})
                RETURNING *
            """
            cur.execute(sql, data)
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else {}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def find_subscription_by_oid(oid: str) -> Optional[Dict[str, Any]]:
    """subscriptions 조회 by inicis_order_id — PostgREST 우회."""
    import psycopg2.extras
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM subscriptions WHERE inicis_order_id = %s LIMIT 1",
                (oid,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def update_subscription_by_oid(oid: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """subscriptions UPDATE by inicis_order_id — PostgREST 우회."""
    import psycopg2.extras
    if not data:
        return None
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            set_parts = [f"{k} = %({k})s" for k in data]
            data["_oid"] = oid
            sql = f"UPDATE subscriptions SET {', '.join(set_parts)} WHERE inicis_order_id = %(_oid)s RETURNING *"
            cur.execute(sql, data)
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
