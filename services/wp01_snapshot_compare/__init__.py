"""WP01-A Snapshot Compare — 입력 사실 변경 감지 모듈.

법령판정이 아닌 데이터 변경 여부만 확인한다.
DB WRITE 0, LEG EXECUTION 0.
"""
from services.wp01_snapshot_compare.compare import compare_snapshot
from services.wp01_snapshot_compare.errors import CollectionError, BaselineNotFound, BaselineQueryError

__all__ = ["compare_snapshot", "CollectionError", "BaselineNotFound", "BaselineQueryError"]
