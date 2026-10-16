"""WP01-A 비교 모듈 전용 예외."""
from __future__ import annotations


class CollectionError(RuntimeError):
    """현재 입력 사실 수집 실패(DB 오류 등). UNRESOLVED 반환 트리거."""

    def __init__(self, message: str, *, sector: str | None = None) -> None:
        super().__init__(message)
        self.sector = sector


class BaselineNotFound(LookupError):
    """C10 정상 조회했으나 행 없음. BASELINE_REQUIRED 반환 트리거."""

    def __init__(self, message: str, *, factory_id: str | None = None) -> None:
        super().__init__(message)
        self.factory_id = factory_id


class BaselineQueryError(RuntimeError):
    """C10 조회 자체 실패 (DB/권한/연결 오류). UNRESOLVED 반환 트리거.

    BaselineNotFound(행 없음 — 진단 이력 없음)와 구분.
    시스템 장애를 BASELINE_REQUIRED 로 잘못 분류하면 안 됨.
    """

    def __init__(self, message: str, *, factory_id: str | None = None) -> None:
        super().__init__(message)
        self.factory_id = factory_id
