"""Modelos de la API de ChatRAG. Lo propio del producto (no del SDK): la forma de una consulta,
una cita verificable y la respuesta con procedencia.

Principio heredado del SDK (fail-closed, procedencia obligatoria): **sin `source_uri` no hay
cita**, y una cita cuya etiqueta de acceso no case con las del usuario **no se muestra** — el
filtrado de ACLs ocurre en el servidor, nunca en el cliente (ver `rag.filter_by_acl`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserContext(BaseModel):
    """Identidad y permisos del usuario que consulta — los provee `tribu-auth`, aquí solo se
    transportan. `acls` son las etiquetas de acceso que el usuario posee."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    acls: frozenset[str] = frozenset()


class Query(BaseModel):
    """Una consulta al RAG."""

    model_config = ConfigDict(frozen=True)

    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=50)


class Citation(BaseModel):
    """Una cita verificable: el fragmento recuperado con su procedencia y su etiqueta de acceso.
    `source_uri` es obligatorio — sin él, el fragmento no puede citarse ni entrar en contexto."""

    model_config = ConfigDict(frozen=True)

    text: str
    source_uri: str = Field(min_length=1)
    title: str = ""
    score: float = 0.0
    required_acl: str | None = None
    """Etiqueta de acceso que exige este fragmento. `None` = público. Si está y el usuario no la
    tiene, la cita se descarta en el servidor."""


class Answer(BaseModel):
    """Respuesta del RAG con sus citas. Si `abstained`, no hubo base suficiente y `text` explica
    qué faltaba (abstención con principio, alineada con tribu-confidence)."""

    model_config = ConfigDict(frozen=True)

    text: str
    citations: tuple[Citation, ...] = ()
    abstained: bool = False
