"""Arranque en segundo plano de chatrag-api.

En MarketplaceForge `sparkd` arranca los servicios por `dependsOn` y solo espera a que el anterior
esté `healthy`. chatrag-api tiene que estar sano ANTES que Milvus (Milvus y MinIO leen las
credenciales que genera la api, ver secretos.py), así que el `lifespan` no puede bloquearse
esperando a Milvus o a los NIM: sirve `/health` enseguida y esto hace el resto, con reintentos:

1. Copia el corpus de arranque a `knowledge_dir` si está vacío (sustituye al init-container
   `seed-knowledge` del compose de GB10).
2. Construye el retriever real cuando Milvus y los NIM responden; hasta entonces `/query`
   responde 503 ("arrancando").
3. Si `auto_ingest` y el índice del tenant no existe todavía, ingiere el corpus una vez.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from chatrag_api.ingest import IngestReport
from chatrag_api.rag import Retriever

logger = logging.getLogger("chatrag_api.arranque")


def seed_knowledge(knowledge_dir: Path, seed_dir: Path | None) -> int:
    """Copia los `*.md` de `seed_dir` a `knowledge_dir` si este no tiene ninguno. Nunca pisa
    documentos subidos después desde /admin. Devuelve cuántos copió."""

    if seed_dir is None or not seed_dir.is_dir():
        return 0
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    if any(knowledge_dir.glob("*.md")):
        return 0
    copied = 0
    for f in sorted(seed_dir.glob("*.md")):
        shutil.copy2(f, knowledge_dir / f.name)
        copied += 1
    return copied


async def _retry(
    what: str,
    attempt: Callable[[], Awaitable[Any]],
    *,
    retry_seconds: float,
    max_attempts: int | None,
) -> Any:
    n = 0
    while True:
        n += 1
        try:
            return await attempt()
        except Exception as exc:
            if max_attempts is not None and n >= max_attempts:
                raise
            logger.info("%s aún no disponible (intento %d): %s", what, n, exc)
            await asyncio.sleep(retry_seconds)


async def warmup(
    state: Any,
    *,
    build_retriever: Callable[[], Awaitable[Retriever]],
    index_exists: Callable[[], Awaitable[bool]],
    ingest: Callable[[], Awaitable[list[IngestReport]]] | None,
    retry_seconds: float = 15.0,
    max_attempts: int | None = None,
) -> None:
    """Deja `state.retriever` listo; ingiere antes el corpus si hace falta. `state` es el
    `app.state` de FastAPI (o un doble en tests)."""

    if ingest is not None and not await _retry(
        "índice (Milvus)", index_exists, retry_seconds=retry_seconds, max_attempts=max_attempts
    ):
        reports: list[IngestReport] = await _retry(
            "ingesta del corpus (Milvus + NIM de embeddings)",
            ingest,
            retry_seconds=retry_seconds,
            max_attempts=max_attempts,
        )
        logger.info(
            "corpus ingerido: %d documentos, %d fragmentos",
            len(reports),
            sum(r.chunks for r in reports),
        )
    state.retriever = await _retry(
        "retriever (Milvus + NIM)", build_retriever, retry_seconds=retry_seconds,
        max_attempts=max_attempts,
    )
    logger.info("retriever listo")
