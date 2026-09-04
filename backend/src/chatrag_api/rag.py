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


def answer_query(retriever: Retriever, query: Query, user: UserContext) -> Answer:
    """Orquesta una consulta: recupera, filtra por ACL y arma la respuesta con citas.

    Si tras el filtrado no queda ninguna cita, se **abstiene** en vez de inventar: devuelve una
    respuesta marcada `abstained` que dice que no hay base accesible — nunca una respuesta sin
    procedencia (alineado con tribu-confidence y la regla de "sin procedencia no hay respuesta").
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
    resumen = _draft_grounded_summary(query.question, ordered)
    return Answer(text=resumen, citations=ordered, abstained=False)


def _draft_grounded_summary(question: str, citations: Sequence[Citation]) -> str:
    """Placeholder determinista del paso de generación. En producción, este resumen lo produce
    el NIM de chat on-prem sobre EXACTAMENTE estas citas (nunca sobre conocimiento no citado),
    y pasa por el verificador de salida del SDK. Aquí devolvemos un extracto trazable para que
    el pipeline y las citas sean testeables sin NIM."""

    fuentes = ", ".join(dict.fromkeys(c.title or c.source_uri for c in citations))
    return f"Según {fuentes}: (resumen pendiente de generación por el NIM de chat on-prem)."


def tribu_rag_retriever(embed_dim: int) -> Retriever:  # pragma: no cover - requiere el registry
    """Adaptador de producción sobre `tribu-rag`. Import perezoso: el paquete del SDK solo se
    exige cuando de verdad se usa el retriever real, no al importar este módulo (así los tests
    del producto corren sin el registry privado).

    Nota: aquí es donde el guard de dimensión dinámico de `tribu-rag` contrasta `embed_dim`
    (2048 por defecto) contra la dimensión real del endpoint y falla-cerrado si difieren.
    """

    from tribu_rag import HybridRetriever  # type: ignore[import-not-found]

    return HybridRetriever(embed_dim=embed_dim)  # type: ignore[no-any-return]
