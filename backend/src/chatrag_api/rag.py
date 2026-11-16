"""Pipeline RAG de ChatRAG: recuperar → filtrar por ACL de la fuente → construir citas.

Diseño deliberado: la recuperación se define por un **Protocol** (`Retriever`), no por un
import directo de `tribu-rag`. Así (a) el producto se testea sin NIM ni Milvus inyectando
un retriever falso, y (b) la adaptación al SDK vive en un solo sitio (`tribu_rag_retriever`),
con import perezoso. La lógica **propia del producto** —el filtrado de ACL heredado de la
fuente y el ensamblado de citas verificables— es la que se prueba aquí, y es fail-closed:
un fragmento sin `source_uri` se descarta, y una cita cuya ACL no posee el usuario no se muestra.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from tribu_rag.milvus_store import MilvusVectorStore
    from tribu_rag.nim_client import NimEmbeddingProvider
    from tribu_rag.rerank_client import NimRerankClient

from chatrag_api.audit import AuditLog, NullAuditLog
from chatrag_api.models import Answer, Citation, Query, UserContext

logger = logging.getLogger("chatrag_api")


class Retriever(Protocol):
    """Contrato mínimo de recuperación. Lo implementa el adaptador de `tribu-rag` en producción
    y un doble en los tests.

    Async y con `requester_roles` obligatorio (no `question`/`top_k` solos) porque el backend
    real (`tribu_rag.milvus_store.MilvusVectorStore.query_hybrid`) exige ambas cosas: la
    recuperación real es asíncrona (NIM de embeddings + Milvus + NIM de reranking, todo por
    red), y el RBAC se aplica **server-side** en la propia consulta — sin `requester_roles` no
    hay valor por defecto "ver todo" que un caller pueda olvidar pasar (mismo principio
    fail-closed que el resto del SDK). `filter_by_acl` sigue existiendo como segunda capa, no
    como la única."""

    async def retrieve(
        self, question: str, *, top_k: int, requester_roles: frozenset[str]
    ) -> Sequence[Citation]:
        """Devuelve fragmentos candidatos (ya con `source_uri`, score y `required_acl`)."""
        ...


class ChatGenerator(Protocol):
    """Contrato mínimo de generación. Lo implementa el adaptador del NIM de chat on-prem (vía
    `tribu-http`) en producción y un doble en los tests. Recibe SIEMPRE las citas ya filtradas
    por ACL — nunca genera sobre nada que el usuario no pueda ver.

    Async porque el adaptador real llama al NIM de chat a través de `TribuHttpClient`, que es
    async-only (envuelve `httpx.AsyncClient` con egress/circuit breaker/retry) — no hay una vía
    síncrona que pase por esos controles del SDK."""

    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        """Redacta la respuesta anclada exclusivamente en `citations`."""
        ...


def filter_by_acl(
    citations: Iterable[Citation], user: UserContext
) -> tuple[Citation, ...]:
    """Se queda solo con las citas que el usuario tiene derecho a ver. Fail-closed en dos frentes:
    descarta lo que no tiene `source_uri` (no citable) y lo que exige una ACL que el usuario no
    posee. El filtrado es del servidor: el cliente nunca decide qué puede ver.

    Evaluado contra `tribu-datagov` (clasificación + etiquetado jurisdiccional en origen, según
    `tribu_maestro_como_hacer`): "reduce significativamente" la necesidad de ACL manual, no la
    elimina — no hay fuente que documente que sustituye este filtro. Se mantiene esta función
    como la barrera de defensa en profundidad; si `tribu-datagov` se integra más adelante para
    etiquetar en origen, este filtro sigue siendo la última línea antes de que algo salga del
    backend, no se borra."""

    visible: list[Citation] = []
    for c in citations:
        if not c.source_uri:
            continue
        if c.required_acl and not (c.required_acl & user.acls):
            continue
        visible.append(c)
    return tuple(visible)


async def answer_query(
    retriever: Retriever,
    generator: ChatGenerator,
    query: Query,
    user: UserContext,
    *,
    audit_log: AuditLog | None = None,
) -> Answer:
    """Orquesta una consulta: recupera, filtra por ACL y genera la respuesta sobre esas citas.

    Si tras el filtrado no queda ninguna cita, se **abstiene** en vez de inventar: devuelve una
    respuesta marcada `abstained` que dice que no hay base accesible — nunca una respuesta sin
    procedencia (alineado con tribu-confidence y la regla de "sin procedencia no hay respuesta").
    El generador ni se invoca en ese caso: no hay base sobre la que anclar nada.

    `audit_log` (ver `audit.py`, sobre `tribu-audit`) registra qué se mostró y qué se bloqueó
    por ACL — `None` usa `NullAuditLog` (sin traza; la auditoría es opt-in, ver `config.py`).
    """

    log = audit_log or NullAuditLog()
    candidates = await retriever.retrieve(
        query.question, top_k=query.top_k, requester_roles=user.acls
    )
    visible = filter_by_acl(candidates, user)
    visible_uris = {c.source_uri for c in visible}
    blocked = [
        {"source_uri": c.source_uri, "required_acl": sorted(c.required_acl)}
        for c in candidates
        if c.source_uri not in visible_uris
    ]

    if not visible:
        logger.info(
            "abstención: user_id=%s candidatos=%d bloqueados=%d",
            user.user_id,
            len(candidates),
            len(blocked),
        )
        await log.record(
            actor_id=user.user_id,
            action="chatrag.query.abstained",
            payload={"question": query.question, "blocked": blocked},
        )
        return Answer(
            text=(
                "No encontré base accesible para responder con seguridad a esta pregunta. "
                "Puede que la información exista pero requiera permisos que no tienes, o que "
                "no esté en el corpus."
            ),
            citations=(),
            abstained=True,
        )

    ordered = tuple(sorted(visible, key=lambda c: c.score, reverse=True))
    text = await generator.generate(query.question, ordered)
    logger.info(
        "respondido: user_id=%s citas_mostradas=%d bloqueadas=%d",
        user.user_id,
        len(ordered),
        len(blocked),
    )
    await log.record(
        actor_id=user.user_id,
        action="chatrag.query.answered",
        payload={
            "question": query.question,
            "shown": [c.source_uri for c in ordered],
            "blocked": blocked,
        },
    )
    return Answer(text=text, citations=ordered, abstained=False)


class _TribuRagRetriever:  # pragma: no cover - requiere NIM + Milvus reales
    """Adaptador de producción compuesto sobre tribu-rag: NIM de embeddings (query) + búsqueda
    híbrida real de Milvus (BM25+ANN+RRF nativos, `MilvusVectorStore.query_hybrid`) + reranking
    real (`NimRerankClient`/`rerank_chunks`).

    No existe una clase "HybridRetriever" que haga esto por una sola llamada — verificado
    leyendo el código fuente real de `tribu_rag` (`~/repositorio/tribu-sdk/python/tribu-rag/`),
    no asumido por el nombre: el módulo `tribu_rag.retriever` solo estandariza el *Protocol* de
    salida (`Retriever`/`RetrievedChunk`) para que los productos no se inventen cada uno el
    suyo, pero la composición real (embed → store → rerank) la escribe cada producto. La
    versión anterior de este adaptador importaba `tribu_rag.HybridRetriever`, que nunca existió
    — nunca se detectó porque el test de integración correspondiente nunca corrió con el
    SDK real instalado."""

    def __init__(
        self,
        store: MilvusVectorStore,
        embed_provider: NimEmbeddingProvider,
        rerank_client: NimRerankClient,
        *,
        tenant_id: str,
    ) -> None:
        self._store = store
        self._embed = embed_provider
        self._rerank = rerank_client
        self._tenant_id = tenant_id

    async def retrieve(
        self, question: str, *, top_k: int, requester_roles: frozenset[str]
    ) -> Sequence[Citation]:
        from tribu_rag.rerank_client import rerank_chunks

        [embedding] = await self._embed.embed([question])
        chunks = await self._store.query_hybrid(
            self._tenant_id,
            tuple(embedding),
            question,
            top_k,
            requester_roles=requester_roles,
        )
        if chunks:
            chunks = await rerank_chunks(self._rerank, question, chunks)
        # `query_hybrid`/`rerank_chunks` devuelven `list[Chunk]` ya en orden de relevancia
        # (Reciprocal Rank Fusion / logit del NIM de reranking) pero SIN un score numérico
        # adjunto por chunk — `Chunk` no lo trae, a diferencia de `RetrievedChunk.score` (que es
        # un wrapper de `tribu_rag.retriever`, no lo que devuelve `MilvusVectorStore`). Se
        # asigna un score sintético descendente por posición para que el `sorted(...)` de
        # `answer_query` no reordene lo que tribu-rag ya ordenó correctamente.
        n = len(chunks)
        return [
            Citation(
                text=chunk.text,
                source_uri=chunk.metadata.source_uri or "",
                title=chunk.chunk_id,
                score=(n - i) / n if n else 0.0,
                required_acl=chunk.metadata.allowed_roles,
            )
            for i, chunk in enumerate(chunks)
        ]


async def tribu_rag_retriever(
    *,
    embed_dim: int,
    tenant_id: str,
    milvus_uri: str,
    nim_embed_url: str,
    nim_embed_model_id: str,
    nim_rerank_url: str,
    nim_rerank_model_id: str,
    allowed_hosts: frozenset[str],
) -> Retriever:  # pragma: no cover - requiere NIM + Milvus reales
    """Construye el `_TribuRagRetriever` de producción. Import perezoso: el paquete del SDK
    solo se exige cuando de verdad se usa el retriever real, no al importar este módulo (así
    los tests del producto corren sin NIM ni Milvus). Async (a diferencia de la versión
    anterior de este adaptador) porque el guard de dimensión real lee Milvus.

    El guard de dimensión dinámico de `tribu-rag` (`verify_dimension_guard`) NO llama al NIM —
    solo compara dos `IndexMetadata` entre sí (ver su código fuente real:
    `tribu_rag.embeddings`). Para que verifique algo real (no una tautología contra sus propios
    parámetros) hay que contrastar el proveedor de embeddings **en vivo** contra lo que
    `ingest.py` dejó **persistido** de verdad en la última ingesta
    (`store.read_index_metadata`, escrito por `store.write_index_metadata` — mismo patrón que
    `tribu-sdk/scripts/ingesta_corpus.py`), no contra un valor construido aquí mismo con los
    mismos parámetros. Si el tenant nunca se ingirió todavía, no hay nada que contrastar."""

    from pymilvus import AsyncMilvusClient  # type: ignore[import-untyped]  # sin py.typed
    from tribu_http.client import TribuHttpClient
    from tribu_http.egress import EgressAllowlist
    from tribu_rag.embeddings import verify_dimension_guard
    from tribu_rag.milvus_store import MilvusVectorStore
    from tribu_rag.nim_client import NimEmbeddingProvider
    from tribu_rag.rerank_client import NimRerankClient

    http = TribuHttpClient(EgressAllowlist(allowed_hosts=allowed_hosts))
    # input_type="query": el NIM de embeddings es asimétrico (verificado en ingesta_corpus.py
    # del SDK real) — "passage" es para indexar, "query" para buscar; sin el correcto, 400.
    embed_provider = NimEmbeddingProvider(
        http, base_url=nim_embed_url, model_id=nim_embed_model_id, dimension=embed_dim,
        input_type="query",
    )
    milvus_client = AsyncMilvusClient(uri=milvus_uri)
    store = MilvusVectorStore(milvus_client, embedding_dim=embed_dim)
    persisted_index = await store.read_index_metadata(tenant_id)
    if persisted_index is not None:
        verify_dimension_guard(embed_provider, persisted_index)
    rerank_client = NimRerankClient(http, base_url=nim_rerank_url, model_id=nim_rerank_model_id)
    return _TribuRagRetriever(store, embed_provider, rerank_client, tenant_id=tenant_id)


_GROUNDED_SYSTEM_PROMPT = (
    "Eres el asistente de trámites de la comuna de Santiago. Responde ÚNICAMENTE con la "
    "información de las fuentes que se te entregan a continuación; si no alcanzan para "
    "responder, dilo explícitamente. Nunca añadas datos que no estén en las fuentes."
)


class _TribuNimChatGenerator:  # pragma: no cover - requiere el NIM de chat on-prem
    """Adaptador de producción sobre el NIM de chat, vía `tribu_http.TribuHttpClient` (egress
    deny-by-default + circuit breaker; el POST no reintenta — no idempotente). Contrato
    OpenAI-compatible `/v1/chat/completions`, el estándar de los NIM de LLM."""

    def __init__(self, nim_chat_url: str, *, model: str, allowed_hosts: frozenset[str]) -> None:
        from tribu_http.client import TribuHttpClient
        from tribu_http.egress import EgressAllowlist

        self._url = f"{nim_chat_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        self._client = TribuHttpClient(EgressAllowlist(allowed_hosts=allowed_hosts))

    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        # `c.text` viene de munistgo.cl (contenido de terceros, no confiable) — se envuelve con
        # tribu-guardrails (`render_untrusted_as_data`, ver módulo `tool_poisoning`) antes de
        # concatenarlo en el prompt: delimitador estructural inequívoco + escapado de `<`, para
        # que ninguna cita pueda forjar la frontera del bloque ni pasar por instrucción del
        # sistema. Mitigación probabilística, no control (el propio módulo lo dice: el control
        # real sería Plan-Then-Execute, que no aplica aquí — este generador no ejecuta acciones,
        # solo redacta texto anclado en `citations`).
        from tribu_guardrails.tool_poisoning import (  # type: ignore[import-untyped]  # sin py.typed
            render_untrusted_as_data,
        )

        contexto = "\n\n".join(
            render_untrusted_as_data(
                c.text, tag="citation", attributes=f'source_uri="{c.source_uri}"'
            )
            for c in citations
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _GROUNDED_SYSTEM_PROMPT},
                {"role": "user", "content": f"Fuentes:\n{contexto}\n\nPregunta: {question}"},
            ],
            "temperature": 0.0,
        }
        response = await self._client.post(self._url, json=payload)
        response.raise_for_status()
        data = response.json()
        content: str = data["choices"][0]["message"]["content"]
        return content

    async def aclose(self) -> None:
        await self._client.aclose()


def tribu_nim_chat_generator(
    nim_chat_url: str, *, model: str, allowed_hosts: frozenset[str]
) -> ChatGenerator:  # pragma: no cover - requiere el NIM de chat on-prem
    """Construye el `ChatGenerator` de producción. Import perezoso: `tribu-http` solo se exige
    cuando de verdad se usa el generador real, no al importar este módulo (los tests del
    producto corren con un doble, sin el NIM)."""

    return _TribuNimChatGenerator(nim_chat_url, model=model, allowed_hosts=allowed_hosts)
