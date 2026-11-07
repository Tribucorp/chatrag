"""Ingesta real del corpus de ChatRAG a `tribu-rag` (Milvus). Antes de esta sesión, ChatRAG
nunca llamaba a esto — el retriever de producción (`rag.py`) suponía un índice ya poblado por
otra vía que no existía. El pipeline real ya está completo en el SDK
(`tribu-sdk/scripts/ingesta_corpus.py`): este módulo es ese mismo patrón, parametrizado para el
tenant/corpus de ChatRAG en vez del corpus del propio SDK, expuesto como algo que `admin.py`
puede disparar bajo demanda en vez de un script suelto.

Fuente inicial: `knowledge/*.md` (ya en el repo, en la raíz del proyecto). Portar
`legacy/elevenlabs-kb/crawl-site-to-kb.ts` a un recolector real de `munistgo.cl` que alimente
este mismo pipeline queda para un paso posterior — mismo filtro evergreen-vs-noticias que ya
tiene ese script, pero como origen de documentos, no como cambio a esta función.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class IngestReport(BaseModel):
    """Resultado de ingerir un documento."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    chunks: int


class Ingestor(Protocol):
    """Contrato mínimo de ingesta. Lo implementa el adaptador de `tribu-rag` en producción y un
    doble en los tests — mismo patrón que `Retriever`/`ChatGenerator` en `rag.py`."""

    async def ingest_markdown_dir(self, directory: Path) -> list[IngestReport]:
        """Ingiere cada `*.md` de `directory` (no recursivo) como un documento propio."""
        ...

    async def ingest_text(self, document_id: str, text: str) -> IngestReport:
        """Ingiere un único documento sin tocar el resto del índice — para
        `POST /admin/sources` (subir un documento suelto), a diferencia de
        `ingest_markdown_dir` que reingesta el directorio completo."""
        ...


class FakeIngestor:
    """Doble de test: no toca Milvus ni ningún NIM. Cuenta párrafos separados por línea en
    blanco como un "chunk" cada uno — solo para que los tests puedan afirmar sobre `chunks` sin
    depender de la lógica real de `tribu_rag.chunking`."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    async def ingest_markdown_dir(self, directory: Path) -> list[IngestReport]:
        self.calls.append(directory)
        reports = []
        for f in sorted(directory.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            n = len([p for p in text.split("\n\n") if p.strip()])
            reports.append(IngestReport(document_id=f.name, chunks=n))
        return reports

    async def ingest_text(self, document_id: str, text: str) -> IngestReport:
        n = len([p for p in text.split("\n\n") if p.strip()])
        return IngestReport(document_id=document_id, chunks=n)


class TribuRagIngestor:  # pragma: no cover - requiere el registry + NIM + Milvus reales
    """Adaptador de producción: mismo pipeline que `tribu-sdk/scripts/ingesta_corpus.py`
    (`tribu_rag.ingest.ingest_document` + `MilvusVectorStore.upsert` + guard de dimensión ANTES
    de indexar + `HeadingContextualizer`/`NimContextualizer`), parametrizado para el tenant de
    ChatRAG en vez de `tribu-maestro`. Import perezoso: el paquete del SDK solo se exige cuando
    de verdad se ingesta algo, no al importar este módulo."""

    def __init__(
        self,
        *,
        tenant_id: str,
        milvus_uri: str,
        embed_dim: int,
        nim_embed_url: str,
        nim_embed_model_id: str,
        nim_chat_url: str | None,
        nim_chat_model: str | None,
        allowed_hosts: frozenset[str],
    ) -> None:
        self._tenant_id = tenant_id
        self._milvus_uri = milvus_uri
        self._embed_dim = embed_dim
        self._nim_embed_url = nim_embed_url
        self._nim_embed_model_id = nim_embed_model_id
        self._nim_chat_url = nim_chat_url
        self._nim_chat_model = nim_chat_model
        self._allowed_hosts = allowed_hosts

    def _build_clients(self) -> tuple[object, object, object, object]:
        """Un solo lugar para construir http/embedding_provider/milvus_client/store — lo
        comparten `ingest_markdown_dir` e `ingest_text` (antes duplicado; refactorizado al
        añadir `ingest_text` para `POST /admin/sources`, subir un documento suelto)."""

        from pymilvus import AsyncMilvusClient  # type: ignore[import-not-found]
        from tribu_http.client import TribuHttpClient  # type: ignore[import-not-found]
        from tribu_http.egress import EgressAllowlist  # type: ignore[import-not-found]
        from tribu_rag.milvus_store import MilvusVectorStore  # type: ignore[import-not-found]
        from tribu_rag.nim_client import NimEmbeddingProvider  # type: ignore[import-not-found]

        # timeout=300s: una generación real de embeddings/chat en un NIM tarda más que una API
        # normal (mismo criterio que ingesta_corpus.py del SDK real).
        http = TribuHttpClient(EgressAllowlist(allowed_hosts=self._allowed_hosts), timeout=300.0)
        # input_type="passage": estamos INDEXANDO documentos (el NIM de embed es asimétrico;
        # la búsqueda usa "query", ver rag.py: tribu_rag_retriever).
        embedding_provider = NimEmbeddingProvider(
            http,
            base_url=self._nim_embed_url,
            model_id=self._nim_embed_model_id,
            dimension=self._embed_dim,
            input_type="passage",
        )
        milvus_client = AsyncMilvusClient(uri=self._milvus_uri)
        store = MilvusVectorStore(milvus_client, embedding_dim=self._embed_dim)
        return http, embedding_provider, milvus_client, store

    async def _ingest_one(
        self,
        *,
        document_id: str,
        text: str,
        source_uri: str,
        http: object,
        embedding_provider: object,
        store: object,
    ) -> IngestReport:
        from tribu_rag.contextual import Contextualizer  # type: ignore[import-not-found]
        from tribu_rag.ingest import (  # type: ignore[import-not-found]
            HeadingContextualizer,
            ingest_document,
        )
        from tribu_rag.nim_contextualizer import NimContextualizer  # type: ignore[import-not-found]

        contextualizer: Contextualizer
        if self._nim_chat_url:
            contextualizer = NimContextualizer(
                http,
                base_url=self._nim_chat_url,
                model_id=self._nim_chat_model or "nvidia/nemotron-nano-9b-v2",
                document_title=document_id,
                document_text=text,
            )
        else:
            contextualizer = HeadingContextualizer(document_id)
        chunks = await ingest_document(
            document_id=document_id,
            text=text,
            tenant_id=self._tenant_id,
            classification="publico",
            owner="chatrag",
            # Todo el corpus inicial (knowledge/*.md) es público por diseño — ver
            # rag.py: Citation.required_acl vacío = público. Un futuro origen con
            # contenido restringido pasaría allowed_roles reales aquí, no "publico".
            allowed_roles=frozenset({"publico"}),
            source_uri=source_uri,
            contextualizer=contextualizer,
            embedding_provider=embedding_provider,
        )
        if chunks:
            await store.upsert(self._tenant_id, chunks)  # type: ignore[attr-defined]
        return IngestReport(document_id=document_id, chunks=len(chunks))

    async def _write_index_metadata(self, store: object) -> None:
        from tribu_rag.embeddings import IndexMetadata  # type: ignore[import-not-found]

        # Registra CON QUÉ se ingirió de verdad (B-25 del SDK) — lo que
        # `rag.py: tribu_rag_retriever` contrasta en su propio arranque contra el NIM de
        # embeddings en vivo, para no depender de que ambos lados compartan config por
        # casualidad.
        await store.write_index_metadata(  # type: ignore[attr-defined]
            self._tenant_id,
            IndexMetadata(
                model_id=self._nim_embed_model_id,
                dimension=self._embed_dim,
                truncation_policy="none",
            ),
        )

    async def ingest_markdown_dir(self, directory: Path) -> list[IngestReport]:
        files = sorted(directory.glob("*.md"))
        http, embedding_provider, milvus_client, store = self._build_clients()
        reports: list[IngestReport] = []
        try:
            for f in files:
                reports.append(
                    await self._ingest_one(
                        document_id=f.name,
                        text=f.read_text(encoding="utf-8"),
                        source_uri=f"file://{f}",
                        http=http,
                        embedding_provider=embedding_provider,
                        store=store,
                    )
                )
            await self._write_index_metadata(store)
        finally:
            await milvus_client.close()  # type: ignore[attr-defined]
            await http.aclose()  # type: ignore[attr-defined]
        return reports

    async def ingest_text(self, document_id: str, text: str) -> IngestReport:
        http, embedding_provider, milvus_client, store = self._build_clients()
        try:
            report = await self._ingest_one(
                document_id=document_id,
                text=text,
                source_uri=f"admin-upload://{document_id}",
                http=http,
                embedding_provider=embedding_provider,
                store=store,
            )
            await self._write_index_metadata(store)
        finally:
            await milvus_client.close()  # type: ignore[attr-defined]
            await http.aclose()  # type: ignore[attr-defined]
        return report


def tribu_rag_ingestor(
    *,
    tenant_id: str,
    milvus_uri: str,
    embed_dim: int,
    nim_embed_url: str,
    nim_embed_model_id: str,
    nim_chat_url: str | None,
    nim_chat_model: str | None,
    allowed_hosts: frozenset[str],
) -> Ingestor:
    return TribuRagIngestor(
        tenant_id=tenant_id,
        milvus_uri=milvus_uri,
        embed_dim=embed_dim,
        nim_embed_url=nim_embed_url,
        nim_embed_model_id=nim_embed_model_id,
        nim_chat_url=nim_chat_url,
        nim_chat_model=nim_chat_model,
        allowed_hosts=allowed_hosts,
    )
