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

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, ConfigDict

from chatrag_api.rag import PUBLIC_ACL

if TYPE_CHECKING:
    from tribu_http.client import TribuHttpClient
    from tribu_rag.milvus_store import MilvusVectorStore
    from tribu_rag.nim_client import NimEmbeddingProvider


_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def split_front_matter(text: str) -> tuple[str | None, str]:
    """Compatibilidad: (`source`, cuerpo). Ver `parse_front_matter`."""

    meta, body = parse_front_matter(text)
    return meta.source, body


class FrontMatter(BaseModel):
    """Cabecera de un documento del corpus: `source:` (URL http(s) citable) y `acl:` (etiquetas
    separadas por comas que puede ver; sin `acl:` el documento es público)."""

    model_config = ConfigDict(frozen=True)

    source: str | None = None
    acl: frozenset[str] = frozenset()


_ACL_TAG = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


def parse_front_matter(text: str) -> tuple[FrontMatter, str]:
    """(cabecera, cuerpo sin cabecera). La cabecera la escribe quien prepara el corpus:
    `source:` es la URL real de la que sale el contenido, que pasa a ser el `source_uri` de la
    cita (verificable, a diferencia de un `file://` del servidor) — solo http(s), o `kb://`
    para la base de conocimiento propia (sin URL pública); `acl:` restringe
    el documento a esas etiquetas. Etiquetas mal formadas se ignoran; si `acl:` no deja ninguna
    válida el documento NO pasa a público: se queda con una etiqueta que nadie tiene (fail-closed).
    """

    m = _FRONT_MATTER.match(text)
    if not m:
        return FrontMatter(), text
    source: str | None = None
    acl: frozenset[str] = frozenset()
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key == "source" and re.match(r"(https?|kb)://\S+$", value):
            source = value
        elif key == "acl":
            tags = {t.strip().lower() for t in value.split(",") if t.strip()}
            valid = frozenset(t for t in tags if _ACL_TAG.fullmatch(t))
            acl = valid if valid and valid == tags else frozenset({"acl-invalida"})
    return FrontMatter(source=source, acl=acl), text[m.end():].lstrip("\n")


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


class TribuRagIngestor:  # pragma: no cover - requiere NIM + Milvus reales
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

    def _build_clients(
        self,
    ) -> tuple[TribuHttpClient, NimEmbeddingProvider, Any, MilvusVectorStore]:
        # `Any` = pymilvus.AsyncMilvusClient (pymilvus no publica tipos).
        """Un solo lugar para construir http/embedding_provider/milvus_client/store — lo
        comparten `ingest_markdown_dir` e `ingest_text` (antes duplicado; refactorizado al
        añadir `ingest_text` para `POST /admin/sources`, subir un documento suelto)."""

        from pymilvus import AsyncMilvusClient  # type: ignore[import-untyped]  # sin py.typed
        from tribu_http.client import TribuHttpClient
        from tribu_http.egress import EgressAllowlist
        from tribu_rag.milvus_store import MilvusVectorStore
        from tribu_rag.nim_client import NimEmbeddingProvider

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
        allowed_roles: frozenset[str],
        http: TribuHttpClient,
        embedding_provider: NimEmbeddingProvider,
        store: MilvusVectorStore,
    ) -> IngestReport:
        from tribu_rag.contextual import Contextualizer
        from tribu_rag.ingest import (
            HeadingContextualizer,
            ingest_document,
        )
        from tribu_rag.nim_contextualizer import NimContextualizer

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
            # Sin `acl:` en la cabecera, público (`rag.PUBLIC_ACL`, que todo usuario tiene).
            allowed_roles=allowed_roles or frozenset({PUBLIC_ACL}),
            source_uri=source_uri,
            contextualizer=contextualizer,
            embedding_provider=embedding_provider,
        )
        if chunks:
            await store.upsert(self._tenant_id, chunks)
        return IngestReport(document_id=document_id, chunks=len(chunks))

    async def _write_index_metadata(self, store: MilvusVectorStore) -> None:
        from tribu_rag.embeddings import IndexMetadata

        # Registra CON QUÉ se ingirió de verdad (B-25 del SDK) — lo que
        # `rag.py: tribu_rag_retriever` contrasta en su propio arranque contra el NIM de
        # embeddings en vivo, para no depender de que ambos lados compartan config por
        # casualidad.
        await store.write_index_metadata(
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
                meta, body = parse_front_matter(f.read_text(encoding="utf-8"))
                reports.append(
                    await self._ingest_one(
                        document_id=f.name,
                        text=body,
                        source_uri=meta.source or f"file://{f}",
                        allowed_roles=meta.acl,
                        http=http,
                        embedding_provider=embedding_provider,
                        store=store,
                    )
                )
            await self._write_index_metadata(store)
        finally:
            await milvus_client.close()
            await http.aclose()
        return reports

    async def ingest_text(self, document_id: str, text: str) -> IngestReport:
        http, embedding_provider, milvus_client, store = self._build_clients()
        try:
            meta, body = parse_front_matter(text)
            report = await self._ingest_one(
                document_id=document_id,
                text=body,
                source_uri=meta.source or f"admin-upload://{document_id}",
                allowed_roles=meta.acl,
                http=http,
                embedding_provider=embedding_provider,
                store=store,
            )
            await self._write_index_metadata(store)
        finally:
            await milvus_client.close()
            await http.aclose()
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
