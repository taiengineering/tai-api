"""WP01-A 비교 모듈 전용 예외."""
from __future__ import annotations


class CollectionError(RuntimeError):
    """현재 입력 사실 수집 실패(DB 오류 등). UNRESOLVED 반환 트리거."""

    def __init__(self, message: str, *, sector: str | None = None) -> None:
        super().__init__(message)
        self.sector = sector


class BaselineNotFound(LookupError):
    """C10 기준 스냅샷 없음. BASELINE_REQUIRED 반환 트리거."""

    def __init__(self, message: str, *, factory_id: str | None = None) -> None:
        super().__init__(message)
        self.factory_id = factory_id
