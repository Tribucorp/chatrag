"""Panel de administración de ChatRAG — `POST /admin/reindex`, `GET /admin/index-status`,
`GET /admin/audit`. Protegido por un bearer dedicado (`CHATRAG_ADMIN_TOKEN`), separado del
bearer de servicio del BFF (`service_bearer_token` en `app.py`): son dos callers de confianza
distintos (el BFF del frontend vs. quien administra el corpus), con alcances distintos, así que
comparten el patrón (`hmac.compare_digest`) pero no el secreto.

Sin `CHATRAG_ADMIN_TOKEN` configurado, todo el router responde 503 — a diferencia de
`service_bearer_token`/`dev_identity_bypass`, aquí no hay comportamiento por defecto "abierto":
reindexar gasta tráfico real contra los NIM y toca el índice, así que no tiene un modo dev sin
token.
"""

from __future__ import annotations

import hmac
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from chatrag_api.config import Settings
from chatrag_api.conversations import ConversationEntry, ConversationLog, RagMetrics
from chatrag_api.ingest import Ingestor, IngestReport, tribu_rag_ingestor
from chatrag_api.theme import Theme, get_theme_store

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_bearer(
    request: Request, authorization: str | None = Header(default=None)
) -> None:
    settings: Settings = request.app.state.settings
    expected = settings.admin_token
    if expected is None:
        raise HTTPException(
            status_code=503, detail="admin no configurado (falta CHATRAG_ADMIN_TOKEN)"
        )
    token = authorization.removeprefix("Bearer ") if authorization else None
    if token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="falta o es inválido el bearer de admin")


def get_ingestor(request: Request) -> Ingestor:
    """Dependencia de FastAPI (no `app.state`, a diferencia de retriever/generator/audit_log en
    `app.py`): la ingesta es una acción bajo demanda, no algo que necesite vivir construido
    durante todo el ciclo de vida del proceso — se construye en cada llamada, con import
    perezoso real solo dentro de `TribuRagIngestor` (ver `ingest.py`). Overrideable en tests vía
    `app.dependency_overrides[get_ingestor]`."""

    settings: Settings = request.app.state.settings
    return tribu_rag_ingestor(
        tenant_id=settings.tenant_id,
        milvus_uri=settings.milvus_uri,
        embed_dim=settings.embed_dim,
        nim_embed_url=settings.nim_embed_url,
        nim_embed_model_id=settings.nim_embed_model_id,
        nim_chat_url=settings.nim_chat_url,
        nim_chat_model=settings.nim_chat_model,
        allowed_hosts=settings.egress_allowed_hosts,
    )


@router.post("/reindex", dependencies=[Depends(verify_admin_bearer)])
async def reindex(
    request: Request, ingestor: Ingestor = Depends(get_ingestor)
) -> list[IngestReport]:
    settings: Settings = request.app.state.settings
    directory = Path(settings.knowledge_dir)
    if not directory.is_dir():
        raise HTTPException(
            status_code=404, detail=f"knowledge_dir no existe: {directory} (CHATRAG_KNOWLEDGE_DIR)"
        )
    return await ingestor.ingest_markdown_dir(directory)


# Lista blanca, no lista negra: nombre de archivo simple (sin ruta, sin oculto, sin byte nulo),
# ASCII, terminado en .md. Cualquier otra cosa es 400 — más estricto de lo imprescindible a
# propósito: el nombre acaba en el sistema de archivos del servidor.
_DOCUMENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.md")


def _safe_source_path(knowledge_dir: str, document_id: str) -> Path:
    """Ruta destino de un documento subido, o 400. Dos defensas independientes: lista blanca
    del nombre y, además, que la ruta resuelta quede DENTRO de `knowledge_dir` (por si un
    symlink o un cambio futuro de la lista blanca abriera una salida)."""

    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "document_id debe ser un nombre de archivo simple terminado en .md: letras y "
                "números ASCII, '.', '_' o '-', sin ruta ni punto inicial (máx. 123 caracteres)"
            ),
        )
    base = Path(knowledge_dir).resolve()
    target = (base / document_id).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(status_code=400, detail="document_id fuera de knowledge_dir")
    return target


class UploadSourceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Nombre de archivo simple, sin ruta — se valida contra path traversal antes de escribir
    # (ver upload_source): debe terminar en .md y no puede contener separadores de directorio.
    document_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


@router.post("/sources", dependencies=[Depends(verify_admin_bearer)])
async def upload_source(
    request: Request, body: UploadSourceRequest, ingestor: Ingestor = Depends(get_ingestor)
) -> IngestReport:
    """Sube e ingesta UN documento suelto, sin reingestar todo `knowledge_dir` — a diferencia
    de `POST /admin/reindex`. Se persiste como fichero en `knowledge_dir` (así un futuro
    `/admin/reindex` completo también lo recoge) y se ingesta de inmediato para que quede
    consultable sin esperar a un reindex manual."""

    settings: Settings = request.app.state.settings
    Path(settings.knowledge_dir).mkdir(parents=True, exist_ok=True)
    target = _safe_source_path(settings.knowledge_dir, body.document_id)
    target.write_text(body.text, encoding="utf-8")
    return await ingestor.ingest_text(target.name, body.text)


@router.get("/index-status", dependencies=[Depends(verify_admin_bearer)])
def index_status(request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    directory = Path(settings.knowledge_dir)
    source_files = sorted(f.name for f in directory.glob("*.md")) if directory.is_dir() else []
    return {
        "tenant_id": settings.tenant_id,
        "milvus_uri": settings.milvus_uri,
        "embed_dim": settings.embed_dim,
        "nim_embed_model_id": settings.nim_embed_model_id,
        "nim_rerank_model_id": settings.nim_rerank_model_id,
        "knowledge_dir": str(directory),
        "source_files": source_files,
    }


@router.get("/audit", dependencies=[Depends(verify_admin_bearer)])
async def audit_trail(request: Request, limit: int = 50) -> list[dict[str, object]]:
    settings: Settings = request.app.state.settings
    if settings.audit_database_url is None:
        raise HTTPException(
            status_code=503,
            detail="auditoría no configurada (falta CHATRAG_AUDIT_DATABASE_URL)",
        )
    from chatrag_api.audit import read_recent_entries

    return await read_recent_entries(settings.audit_database_url, limit=limit)


@router.get("/theme", dependencies=[Depends(verify_admin_bearer)])
async def get_theme(request: Request) -> Theme:
    settings: Settings = request.app.state.settings
    store = get_theme_store(
        audit_database_url=settings.audit_database_url, theme_file=Path(settings.theme_file)
    )
    return await store.get()


@router.put("/theme", dependencies=[Depends(verify_admin_bearer)])
async def put_theme(request: Request, theme: Theme) -> Theme:
    settings: Settings = request.app.state.settings
    store = get_theme_store(
        audit_database_url=settings.audit_database_url, theme_file=Path(settings.theme_file)
    )
    await store.set(theme)
    return theme


@router.get("/conversations", dependencies=[Depends(verify_admin_bearer)])
def conversations(request: Request, limit: int = 50) -> list[ConversationEntry]:
    """Últimas conversaciones (más reciente primero) desde el buffer en memoria de
    `ConversationLog` (ver `conversations.py`) — no es el audit trail (`GET /admin/audit`):
    esto es una vista operativa rápida, sin Postgres, que se pierde al reiniciar el proceso."""

    conversation_log: ConversationLog = request.app.state.conversation_log
    return conversation_log.recent(limit=limit)


@router.get("/metrics", dependencies=[Depends(verify_admin_bearer)])
def metrics(request: Request, top_n: int = 10) -> RagMetrics:
    conversation_log: ConversationLog = request.app.state.conversation_log
    return conversation_log.metrics(top_n=top_n)
