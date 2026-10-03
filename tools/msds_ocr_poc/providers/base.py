"""Abstract OCR provider interface for OBJ-MSDS-04B PoC."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


class OcrProviderError(Exception):
    pass

class BlockedCredentials(OcrProviderError):
    """Provider credentials are absent — benchmark records BLOCKED_CREDENTIALS."""

class ProviderNotInstalled(OcrProviderError):
    """Provider runtime/binary is not installed — benchmark records NOT_EXECUTED."""


@dataclass
class OcrPage:
    page_no: int
    text: str
    confidence: Optional[float] = None
    provider_request_id: Optional[str] = None
    latency_ms: Optional[float] = None


@dataclass
class OcrResult:
    provider: str
    pages: list[OcrPage] = field(default_factory=list)
    total_latency_ms: float = 0.0
    call_count: int = 0
    estimated_cost_krw: float = 0.0
    error: Optional[str] = None
    blocked: bool = False

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)


class OcrProvider(ABC):
    name: str = "ABSTRACT"

    @abstractmethod
    def ocr_pdf(self, pdf_path: str, max_pages: Optional[int] = None) -> OcrResult:
        """Run OCR on a PDF file. max_pages=None means full document."""

    @abstractmethod
    def ocr_image(self, image_path: str) -> OcrResult:
        """Run OCR on a single image file."""

    def is_available(self) -> bool:
        try:
            self._check_availability()
            return True
        except OcrProviderError:
            return False

    def _check_availability(self) -> None:
        pass
