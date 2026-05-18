"""Audience Profile — 대상별 출력 차등화."""

from __future__ import annotations

from enum import Enum


class AudienceProfile(str, Enum):
    """메시지 수신 대상 프로필.

    operator: 일반 운영자 — 기술 용어 완전 제거
    admin: 관리자 — 도메인 용어 허용, technical 선택적
    developer: 개발자 — technical 필수 포함
    """

    OPERATOR = "operator"
    ADMIN = "admin"
    DEVELOPER = "developer"

    @property
    def include_technical(self) -> bool:
        """technical 필드 포함 여부."""
        return self == AudienceProfile.DEVELOPER

    @property
    def allow_domain_terms(self) -> bool:
        """도메인 용어 허용 여부 (워크플로우, 에스컬레이션 등)."""
        return self in (AudienceProfile.ADMIN, AudienceProfile.DEVELOPER)
