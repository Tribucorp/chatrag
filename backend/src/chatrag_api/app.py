"""App FastAPI de ChatRAG. Un servicio, un contenedor, config por entorno, healthcheck —
k8s-ready aunque hoy corra en compose (regla del SDK).

Wiring del SDK (en producción, con los wheels del registry):
- **tribu-observability**: trazas/métricas del servicio (se enchufa en `startup`).
- **tribu-auth**: valida el bearer y produce el `UserContext` (aquí, la dependencia
  `current_user` lo materializa desde cabeceras ya validadas por el middleware de auth).
- **tribu-http**: cliente único con egress deny-by-default hacia los NIM on-prem.
- **tribu-rag**: el retriever real (inyectado como `Retriever`).

`create_app` acepta un `Retriever` inyectado para poder testear el servicio entero sin el
registry del SDK; si no se inyecta, se construye perezosamente el de `tribu-rag` en `startup`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from chatrag_api.config import Settings
from chatrag_api.models import Answer, Query, UserContext
from chatrag_api.rag import Retriever, answer_query


def current_user(
    x_user_id: str | None = Header(default=None),
    x_user_acls: str | None = Header(default=None),
) -> UserContext:
    """Materializa el usuario a partir de cabeceras que **tribu-auth ya validó** aguas arriba.
    Sin identidad, 401 — fail-closed, nunca un usuario anónimo con acceso implícito."""

    if not x_user_id:
        raise HTTPException(status_code=401, detail="falta identidad (tribu-auth)")
    acls = frozenset(a.strip() for a in (x_user_acls or "").split(",") if a.strip())
    return UserContext(user_id=x_user_id, acls=acls)


def create_app(
    *, settings: Settings | None = None, retriever: Retriever | None = None
) -> FastAPI:
    """Crea la app. `retriever` inyectable para tests; si es `None`, se construye el de
    `tribu-rag` en el arranque (requiere el registry privado)."""

    app_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # tribu-observability: instrumentar el servicio (trazas de decisión, Prometheus).
        # Import perezoso del retriever real para no exigir el wheel del SDK en tests.
        if app.state.retriever is None:  # pragma: no cover - requiere el registry del SDK
            from chatrag_api.rag import tribu_rag_retriever

            app.state.retriever = tribu_rag_retriever(app_settings.embed_dim)
        yield

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.retriever = retriever

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "app": app_settings.app_name,
            "embed_dim": app_settings.embed_dim,
            "voice_enabled": app_settings.voice_enabled,
        }

    @app.post("/query", response_model=Answer)
    def query(
        body: Query,
        request: Request,
        user: UserContext = Depends(current_user),
    ) -> Answer:
        retriever = request.app.state.retriever
        if retriever is None:
            raise HTTPException(status_code=503, detail="retriever no inicializado")
        return answer_query(retriever, body, user)

    return app
