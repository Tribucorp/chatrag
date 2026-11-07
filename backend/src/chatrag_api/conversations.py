"""Visión operativa de conversaciones y consumo del RAG — deliberadamente **no** el mismo
camino que `tribu-audit` (`audit.py`): ese es el registro de cumplimiento, firmado, opt-in,
persistente, pensado para auditoría legal. Esto es un buffer en memoria, siempre activo (cero
configuración), pensado para que un admin vea "qué se está preguntando ahora mismo" sin
necesitar Postgres — se pierde al reiniciar el proceso, y eso es aceptable: no es el registro
de cumplimiento, es una vista operativa rápida encima de él.

Los contadores acumulados (`Metrics`) sí viven desde el arranque del proceso (no se capan),
distinto del buffer de conversaciones recientes (`ConversationLog`, tamaño fijo) — para que
"cuántas consultas van hoy" no dependa de cuántas quepan en el buffer."""

from __future__ import annotations

import time
from collections import Counter, deque

from pydantic import BaseModel, ConfigDict


class ConversationEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_unix: float
    user_id: str
    question: str
    answer: str
    abstained: bool
    citations_shown: tuple[str, ...] = ()


class SourceCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_uri: str
    count: int


class RagMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_queries: int
    total_answered: int
    total_abstained: int
    abstention_rate: float
    top_sources: tuple[SourceCount, ...]


class ConversationLog:
    """Buffer circular de las últimas `max_entries` conversaciones + contadores acumulados
    desde el arranque. No es thread-safe más allá de lo que ya garantiza el event loop único de
    asyncio (todo esto corre en el hilo principal, sin locks porque no hace falta)."""

    def __init__(self, *, max_entries: int = 100) -> None:
        self._entries: deque[ConversationEntry] = deque(maxlen=max_entries)
        self._total_answered = 0
        self._total_abstained = 0
        self._source_counts: Counter[str] = Counter()

    def record(
        self,
        *,
        user_id: str,
        question: str,
        answer: str,
        abstained: bool,
        citations_shown: tuple[str, ...] = (),
    ) -> None:
        self._entries.appendleft(
            ConversationEntry(
                timestamp_unix=time.time(),
                user_id=user_id,
                question=question,
                answer=answer,
                abstained=abstained,
                citations_shown=citations_shown,
            )
        )
        if abstained:
            self._total_abstained += 1
        else:
            self._total_answered += 1
            self._source_counts.update(citations_shown)

    def recent(self, limit: int = 50) -> list[ConversationEntry]:
        return list(self._entries)[:limit]

    def metrics(self, *, top_n: int = 10) -> RagMetrics:
        total = self._total_answered + self._total_abstained
        return RagMetrics(
            total_queries=total,
            total_answered=self._total_answered,
            total_abstained=self._total_abstained,
            abstention_rate=(self._total_abstained / total) if total else 0.0,
            top_sources=tuple(
                SourceCount(source_uri=uri, count=n)
                for uri, n in self._source_counts.most_common(top_n)
            ),
        )
