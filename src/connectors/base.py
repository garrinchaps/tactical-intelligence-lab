"""Contrato comum dos conectores."""

from __future__ import annotations

from abc import ABC
from typing import ClassVar


class ConnectorUnavailable(RuntimeError):
    """O conector não pode operar agora (sem chave, sem rede, recurso inexistente). Erro tratado."""


class Connector(ABC):
    name: ClassVar[str]
    source: ClassVar[str]
    license: ClassVar[str]
    family: ClassVar[str]          # "events" | "aggregates"
    default_tier: ClassVar[str]    # OFFICIAL | DERIVED | SIMULATED
