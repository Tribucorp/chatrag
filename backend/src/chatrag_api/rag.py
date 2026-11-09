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
import re
from collections.abc import Callable, Iterable, Sequence
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


# Etiqueta de lo público. La ingesta marca así los documentos sin `acl:` y `tribu-rag` filtra en
# Milvus con JSON_CONTAINS_ANY(allowed_roles, requester_roles): si no se añade a los roles de
# TODO usuario, lo público no le aparece a nadie (con `requester_roles` vacío no matchea nada).
PUBLIC_ACL = "publico"


def effective_acls(user: UserContext) -> frozenset[str]:
    """ACLs con las que consulta un usuario: las suyas más la pública."""

    return frozenset(user.acls) | {PUBLIC_ACL}


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
        if c.required_acl and not (c.required_acl & effective_acls(user)):
            continue
        visible.append(c)
    return tuple(visible)


# Marca de cita que el generador pone tras cada dato: `[1]`, `[2, 3]`. El espacio previo se
# captura para no dejar huecos sueltos al quitar una marca inválida.
_CITE_MARKER = re.compile(r"(?P<sp>[ \t]*)\[(?P<ids>\d{1,3}(?:\s*,\s*\d{1,3})*)\]")
# Una racha de marcas seguidas (`[1][2][3]`) respalda UN dato; más de este número de fuentes a
# la vez no es una cita, es el modelo volcando la lista de fuentes (visto con nano-9b-v2 ante un
# "gracias": "¡De nada! [1][2]…[8]") y se descarta entera.
MAX_SOURCES_PER_CLAIM = 3
_CITE_RUN = re.compile(r"(?:[ \t]*\[\d{1,3}(?:\s*,\s*\d{1,3})*\])+")


def select_cited(text: str, citations: Sequence[Citation]) -> tuple[str, tuple[Citation, ...]]:
    """Se queda solo con las citas que la respuesta usa de verdad.

    El generador recibe las fuentes numeradas desde 1 y marca cada dato con `[n]`. Aquí se
    recogen esas marcas en orden de aparición, se descartan las que no apuntan a ninguna fuente
    entregada (un número inventado no se convierte en procedencia) y se **renumeran** para que
    `[1]` del texto sea la primera cita devuelta. Una respuesta sin marcas (un saludo, una
    aclaración) sale sin citas: no afirma nada del corpus, así que no hay procedencia que
    mostrar — y lo que no se citó no se presenta como fuente. Una racha de más de
    `MAX_SOURCES_PER_CLAIM` fuentes seguidas se descarta: no respalda ningún dato concreto."""

    def ids(match: re.Match[str]) -> list[int]:
        return [int(n) - 1 for n in match.group("ids").split(",")]

    def drop_dumps(run: re.Match[str]) -> str:
        n = sum(len(ids(m)) for m in _CITE_MARKER.finditer(run.group(0)))
        return "" if n > MAX_SOURCES_PER_CLAIM else run.group(0)

    text = _CITE_RUN.sub(drop_dumps, text)

    order: list[int] = []
    for m in _CITE_MARKER.finditer(text):
        for i in ids(m):
            if 0 <= i < len(citations) and i not in order:
                order.append(i)
    renumber = {old: new + 1 for new, old in enumerate(order)}

    def rewrite(m: re.Match[str]) -> str:
        kept = list(dict.fromkeys(renumber[i] for i in ids(m) if i in renumber))
        if not kept:
            return ""
        return m.group("sp") + "".join(f"[{k}]" for k in kept)

    return _CITE_MARKER.sub(rewrite, text), tuple(citations[i] for i in order)


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
    El generador ni se invoca en ese caso: no hay base sobre la que anclar nada. Con base
    accesible, la respuesta lleva solo las citas que el texto marca (`select_cited`), no todo lo
    recuperado.

    `audit_log` (ver `audit.py`, sobre `tribu-audit`) registra qué se mostró y qué se bloqueó
    por ACL — `None` usa `NullAuditLog` (sin traza; la auditoría es opt-in, ver `config.py`).
    """

    log = audit_log or NullAuditLog()
    candidates = await retriever.retrieve(
        query.question, top_k=query.top_k, requester_roles=effective_acls(user)
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
    raw_text = await generator.generate(query.question, ordered)
    text, cited = select_cited(raw_text, ordered)
    logger.info(
        "respondido: user_id=%s recuperadas=%d citadas=%d bloqueadas=%d",
        user.user_id,
        len(ordered),
        len(cited),
        len(blocked),
    )
    await log.record(
        actor_id=user.user_id,
        action="chatrag.query.answered",
        payload={
            "question": query.question,
            # Lo que el generador tuvo delante vs. lo que la respuesta cita y ve el usuario.
            "retrieved": [c.source_uri for c in ordered],
            "shown": [c.source_uri for c in cited],
            "blocked": blocked,
        },
    )
    return Answer(text=text, citations=cited, abstained=False)


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
        titles: Callable[[str], str] | None = None,
    ) -> None:
        self._store = store
        self._embed = embed_provider
        self._rerank = rerank_client
        self._tenant_id = tenant_id
        # `Chunk` no trae el título del documento: lo resuelve el producto desde la cabecera
        # del corpus (`ingest.DocumentTitles`). Sin resolvedor, el id del documento.
        self._titles = titles

    def _title(self, chunk_id: str) -> str:
        document_id = chunk_id.split("::", 1)[0]
        return (self._titles(document_id) if self._titles else "") or document_id

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
                title=self._title(chunk.chunk_id),
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
    titles: Callable[[str], str] | None = None,
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
    return _TribuRagRetriever(
        store, embed_provider, rerank_client, tenant_id=tenant_id, titles=titles
    )


async def tribu_rag_index_exists(
    *, tenant_id: str, milvus_uri: str, embed_dim: int
) -> bool:  # pragma: no cover - requiere Milvus real
    """¿Hay ya un índice ingerido para el tenant? (metadatos que escribe la ingesta)."""

    from pymilvus import AsyncMilvusClient
    from tribu_rag.milvus_store import MilvusVectorStore

    client = AsyncMilvusClient(uri=milvus_uri)
    try:
        store = MilvusVectorStore(client, embedding_dim=embed_dim)
        return await store.read_index_metadata(tenant_id) is not None
    finally:
        await client.close()


# `/no_think` desactiva el razonamiento de los Nemotron (nano-9b-v2, 3.5-lightning): sin él,
# el modelo escribe ~1000 tokens de "pensamiento" antes de responder (25-36 s en la GB10) y la
# consulta excede cualquier timeout razonable. Los modelos que no lo reconocen lo ignoran.
_GROUNDED_SYSTEM_PROMPT = (
    "/no_think\n"
    "Eres un asistente que responde en español ÚNICAMENTE con la información de las fuentes "
    "que se te entregan a continuación; si no alcanzan para responder, dilo explícitamente. "
    "Nunca añadas datos que no estén en las fuentes. Puedes usar listas y negritas en Markdown.\n"
    "Cada fuente lleva un número (atributo id). Justo después de cada dato que tomes de una "
    "fuente, pon su número entre corchetes, por ejemplo [1] o [2][3]. Cita solo las fuentes "
    "que realmente uses. Si el mensaje es un saludo, un agradecimiento, una despedida o no "
    "necesita información de las fuentes, responde con una frase breve SIN ningún número entre "
    "corchetes. Nunca pongas una lista de números al final de la respuesta."
)


class _TribuNimChatGenerator:  # pragma: no cover - requiere el NIM de chat on-prem
    """Adaptador de producción sobre el NIM de chat, vía `tribu_http.TribuHttpClient` (egress
    deny-by-default + circuit breaker; el POST no reintenta — no idempotente). Contrato
    OpenAI-compatible `/v1/chat/completions`, el estándar de los NIM de LLM."""

    def __init__(
        self,
        nim_chat_url: str,
        *,
        model: str,
        allowed_hosts: frozenset[str],
        timeout_seconds: float,
    ) -> None:
        from tribu_http.client import TribuHttpClient
        from tribu_http.egress import EgressAllowlist

        self._url = f"{nim_chat_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        # El default de TribuHttpClient (10 s) sirve para embed/rerank, no para generar texto.
        self._client = TribuHttpClient(
            EgressAllowlist(allowed_hosts=allowed_hosts), timeout=timeout_seconds
        )

    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        # `c.text` viene del corpus (contenido de terceros, no confiable) — se envuelve con
        # tribu-guardrails (`render_untrusted_as_data`, ver módulo `tool_poisoning`) antes de
        # concatenarlo en el prompt: delimitador estructural inequívoco + escapado de `<`, para
        # que ninguna cita pueda forjar la frontera del bloque ni pasar por instrucción del
        # sistema. Mitigación probabilística, no control (el propio módulo lo dice: el control
        # real sería Plan-Then-Execute, que no aplica aquí — este generador no ejecuta acciones,
        # solo redacta texto anclado en `citations`).
        from tribu_guardrails.tool_poisoning import (  # type: ignore[import-untyped]  # sin py.typed
            render_untrusted_as_data,
        )

        # Numeradas desde 1: el número es lo que el modelo cita (`[n]`) y `select_cited`
        # resuelve de vuelta a esta misma secuencia.
        contexto = "\n\n".join(
            render_untrusted_as_data(
                c.text, tag="citation", attributes=f'id="{i}" source_uri="{c.source_uri}"'
            )
            for i, c in enumerate(citations, start=1)
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
    nim_chat_url: str,
    *,
    model: str,
    allowed_hosts: frozenset[str],
    timeout_seconds: float = 60.0,
) -> ChatGenerator:  # pragma: no cover - requiere el NIM de chat on-prem
    """Construye el `ChatGenerator` de producción. Import perezoso: `tribu-http` solo se exige
    cuando de verdad se usa el generador real, no al importar este módulo (los tests del
    producto corren con un doble, sin el NIM)."""

    return _TribuNimChatGenerator(
        nim_chat_url, model=model, allowed_hosts=allowed_hosts, timeout_seconds=timeout_seconds
    )
