"""Base Fetcher Interface"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import date


class BaseFetcher(ABC):
    """문서 데이터 패처 기본 클래스.

    각 문서 유형(doc_id)별로 서브클래스를 만들고 fetch() 를 구현합니다.
    반환값은 해당 HTML 템플릿의 Jinja2 변수에 매핑됩니다.
    """

    doc_id: str = ""

    @abstractmethod
    async def fetch(
        self,
        factory_id: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """DB에서 데이터를 조회하여 템플릿 변수 dict를 반환합니다."""
        ...
