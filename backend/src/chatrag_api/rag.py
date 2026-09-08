"""Pipeline RAG de ChatRAG: recuperar → filtrar por ACL de la fuente → construir citas.

Diseño deliberado: la recuperación se define por un **Protocol** (`Retriever`), no por un
import directo de `tribu-rag`. Así (a) el producto se testea sin el registry del SDK inyectando
un retriever falso, y (b) la adaptación al SDK vive en un solo sitio (`tribu_rag_retriever`),
con import perezoso. La lógica **propia del producto** —el filtrado de ACL heredado de la
fuente y el ensamblado de citas verificables— es la que se prueba aquí, y es fail-closed:
un fragmento sin `source_uri` se descarta, y una cita cuya ACL no posee el usuario no se muestra.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from chatrag_api.models import Answer, Citation, Query, UserContext


class Retriever(Protocol):
    """Contrato mínimo de recuperación. Lo implementa el adaptador de `tribu-rag` en producción
    y un doble en los tests."""

    def retrieve(self, question: str, *, top_k: int) -> Sequence[Citation]:
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
    posee. El filtrado es del servidor: el cliente nunca decide qué puede ver."""

    visible: list[Citation] = []
    for c in citations:
        if not c.source_uri:
            continue
        if c.required_acl is not None and c.required_acl not in user.acls:
            continue
        visible.append(c)
    return tuple(visible)


async def answer_query(
    retriever: Retriever, generator: ChatGenerator, query: Query, user: UserContext
) -> Answer:
    """Orquesta una consulta: recupera, filtra por ACL y genera la respuesta sobre esas citas.

    Si tras el filtrado no queda ninguna cita, se **abstiene** en vez de inventar: devuelve una
    respuesta marcada `abstained` que dice que no hay base accesible — nunca una respuesta sin
    procedencia (alineado con tribu-confidence y la regla de "sin procedencia no hay respuesta").
    El generador ni se invoca en ese caso: no hay base sobre la que anclar nada.
    """

    candidates = retriever.retrieve(query.question, top_k=query.top_k)
    visible = filter_by_acl(candidates, user)

    if not visible:
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
    return Answer(text=text, citations=ordered, abstained=False)


def tribu_rag_retriever(embed_dim: int) -> Retriever:  # pragma: no cover - requiere el registry
    """Adaptador de producción sobre `tribu-rag`. Import perezoso: el paquete del SDK solo se
    exige cuando de verdad se usa el retriever real, no al importar este módulo (así los tests
    del producto corren sin el registry privado).

    Nota: aquí es donde el guard de dimensión dinámico de `tribu-rag` contrasta `embed_dim`
    (2048 por defecto) contra la dimensión real del endpoint y falla-cerrado si difieren.
    """

    from tribu_rag import HybridRetriever  # type: ignore[import-not-found]

    return HybridRetriever(embed_dim=embed_dim)  # type: ignore[no-any-return]


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
        from tribu_http.client import TribuHttpClient  # type: ignore[import-not-found]
        from tribu_http.egress import EgressAllowlist  # type: ignore[import-not-found]

        self._url = f"{nim_chat_url.rstrip('/')}/v1/chat/completions"
        self._model = model
        self._client = TribuHttpClient(EgressAllowlist(allowed_hosts=allowed_hosts))

    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        contexto = "\n\n".join(
            f"[{c.title or c.source_uri}] ({c.source_uri}): {c.text}" for c in citations
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
    producto corren con un doble, sin el registry privado ni el NIM)."""

    return _TribuNimChatGenerator(nim_chat_url, model=model, allowed_hosts=allowed_hosts)
