"""chatrag-api — backend RAG de ChatRAG, piloto de adopción del Tribu SDK.

Consume tribu-http/rag/audit/guardrails/voice como dependencias git fijadas a un tag del SDK
(ADR-0020 del SDK). La lógica propia del producto (filtrado por ACL de la fuente, citas
verificables, abstención sin base) vive aquí; el SDK aporta recuperación, egress seguro, traza
de decisión, guardrails y voz (esta última tras flag, apagada por defecto).
"""

from chatrag_api.app import create_app
from chatrag_api.config import Settings
from chatrag_api.models import Answer, Citation, Query, UserContext

__version__ = "0.1.0"

__all__ = [
    "Answer",
    "Citation",
    "Query",
    "Settings",
    "UserContext",
    "create_app",
]
