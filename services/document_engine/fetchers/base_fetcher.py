"""Base Fetcher Interface

문서 데이터 패처 공통 계약. 모든 fetcher 는 fetch(params: dict) 로 통일한다.
params 키는 fetcher 마다 다르다(inspection_id / meeting_id / factory_id 등).
반환값은 해당 HTML 템플릿의 Jinja2 변수에 매핑된다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseFetcher(ABC):
    doc_id: str = ""

    @abstractmethod
    async def fetch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """DB에서 데이터를 조회하여 템플릿 변수 dict를 반환한다."""
        ...
