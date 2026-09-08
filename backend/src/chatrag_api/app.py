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
from chatrag_api.rag import ChatGenerator, Retriever, answer_query


def current_user(
    request: Request,
    x_user_id: str | None = Header(default=None),
    x_user_acls: str | None = Header(default=None),
) -> UserContext:
    """Materializa el usuario a partir de cabeceras que **tribu-auth ya validó** aguas arriba.
    Sin identidad, 401 — fail-closed, nunca un usuario anónimo con acceso implícito.

    Única excepción: `dev_identity_bypass` en settings, pensado solo para desarrollo local
    mientras tribu-auth no esté wireado al cliente (apagado por defecto)."""

    if not x_user_id:
        settings: Settings = request.app.state.settings
        if settings.dev_identity_bypass:
            return UserContext(user_id=settings.dev_identity_bypass, acls=frozenset({"dev"}))
        raise HTTPException(status_code=401, detail="falta identidad (tribu-auth)")
    acls = frozenset(a.strip() for a in (x_user_acls or "").split(",") if a.strip())
    return UserContext(user_id=x_user_id, acls=acls)


def create_app(
    *,
    settings: Settings | None = None,
    retriever: Retriever | None = None,
    generator: ChatGenerator | None = None,
) -> FastAPI:
    """Crea la app. `retriever`/`generator` inyectables para tests; si son `None`, se
    construyen los de producción (`tribu-rag`, NIM de chat vía `tribu-http`) en el arranque
    (requieren el registry privado y el NIM on-prem respectivamente)."""

    app_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # tribu-observability: instrumentar el servicio (trazas de decisión, Prometheus).
        # Import perezoso de los adaptadores reales para no exigir sus wheels/NIM en tests.
        if app.state.retriever is None:  # pragma: no cover - requiere el registry del SDK
            from chatrag_api.rag import tribu_rag_retriever

            app.state.retriever = tribu_rag_retriever(app_settings.embed_dim)
        if app.state.generator is None:  # pragma: no cover - requiere el NIM de chat on-prem
            from chatrag_api.rag import tribu_nim_chat_generator

            app.state.generator = tribu_nim_chat_generator(
                app_settings.nim_chat_url,
                model=app_settings.nim_chat_model,
                allowed_hosts=app_settings.egress_allowed_hosts,
            )
        try:
            yield
        finally:
            aclose = getattr(app.state.generator, "aclose", None)
            if aclose is not None:  # pragma: no cover - requiere el generador real
                await aclose()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.retriever = retriever
    app.state.generator = generator

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "app": app_settings.app_name,
            "embed_dim": app_settings.embed_dim,
            "voice_enabled": app_settings.voice_enabled,
        }

    @app.post("/query", response_model=Answer)
    async def query(
        body: Query,
        request: Request,
        user: UserContext = Depends(current_user),
    ) -> Answer:
        retriever = request.app.state.retriever
        generator = request.app.state.generator
        if retriever is None:
            raise HTTPException(status_code=503, detail="retriever no inicializado")
        if generator is None:
            raise HTTPException(status_code=503, detail="generador no inicializado")
        return await answer_query(retriever, generator, body, user)

    return app
