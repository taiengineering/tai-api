"""Diagnosis engine interface (STAGE B #0 skeleton).

Defines the abstract engine boundary and two concrete engine bindings
(Compiler Core, LEG). Engine selection is a Decision Pending; these are stubs
that later steps wire to the existing runtimes. No business logic here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from .dto import CanonicalDiagnosisRequest


class DiagnosisEngine(ABC):
    name: str = "abstract"

    @abstractmethod
    def evaluate(self, request: CanonicalDiagnosisRequest) -> Dict[str, Any]:
        raise NotImplementedError


class CompilerCoreEngine(DiagnosisEngine):
    name = "compiler-core"

    def evaluate(self, request: CanonicalDiagnosisRequest) -> Dict[str, Any]:
        raise NotImplementedError("engine binding is wired in a later STAGE B step")


class LEGEngine(DiagnosisEngine):
    name = "leg"

    def evaluate(self, request: CanonicalDiagnosisRequest) -> Dict[str, Any]:
        raise NotImplementedError("engine binding is wired in a later STAGE B step")
