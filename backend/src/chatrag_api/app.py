"""App FastAPI de ChatRAG. Un servicio, un contenedor, config por entorno, healthcheck —
k8s-ready aunque hoy corra en compose (regla del SDK).

Wiring del SDK (en producción, con los wheels del registry):
- **tribu-http**: cliente único con egress deny-by-default hacia los NIM on-prem.
- **tribu-rag**: el retriever real (inyectado como `Retriever`).
- **tribu-auth**: NO existe todavía en el registry (fase S0 del SDK, ver
  `tribu_maestro_estado_sdk`) — `current_user` es un stopgap deliberado: confía en
  `X-User-Id`/`X-User-Acls` ya puestas por el BFF (`src/app/api/chat/route.ts` en el frontend,
  con Auth.js) hasta que exista el módulo real.
- **tribu-audit** (`audit.py`): traza de decisión — API confirmada leyendo el código fuente
  real del SDK en disco (no el corpus de x9, que se rehusó por falta de referencia). Opt-in:
  sin `CHATRAG_AUDIT_DATABASE_URL`/`CHATRAG_AUDIT_CHAIN_KEY`, `NullAuditLog` (sin traza, la
  consulta sigue funcionando). tribu-observability, que sería el candidato "natural" del
  nombre, no existe en el registry — de ahí que la traza de decisión pase por tribu-audit.
- **tribu-guardrails**: `render_untrusted_as_data` (`tribu_guardrails.tool_poisoning`) envuelve
  cada cita en `rag.py: _TribuNimChatGenerator.generate` antes de mandarla al NIM — el contenido
  viene de `munistgo.cl`, no confiable. `check_lethal_trifecta` corre aquí en `lifespan` contra
  el manifiesto real de ChatRAG (abajo).

Panel de administración (`admin.py`, montado como router): ingesta real a `tribu-rag`/Milvus
(`POST /admin/reindex`), estado del índice (`GET /admin/index-status`) y traza de auditoría
(`GET /admin/audit`) — protegido por `CHATRAG_ADMIN_TOKEN`, sin comportamiento por defecto
abierto (503 sin configurar).

`create_app` acepta un `Retriever` inyectado para poder testear el servicio entero sin el
registry del SDK; si no se inyecta, se construye perezosamente el de `tribu-rag` en `startup`.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from chatrag_api import admin
from chatrag_api.audit import AuditLog, NullAuditLog
from chatrag_api.config import Settings
from chatrag_api.conversations import ConversationLog
from chatrag_api.middleware import RateLimiter, RateLimitMiddleware, RequestLoggingMiddleware
from chatrag_api.models import Answer, Query, UserContext
from chatrag_api.rag import ChatGenerator, Retriever, answer_query
from chatrag_api.theme import Theme, get_theme_store
from chatrag_api.voice import (
    SpeakRequest,
    VoiceConfigError,
    VoiceDisabledError,
    VoiceService,
    VoiceSessionInfo,
    VoiceTokenError,
    tribu_voice_service,
)

logger = logging.getLogger("chatrag_api")


def verify_service_bearer(
    request: Request, authorization: str | None = Header(default=None)
) -> None:
    """`current_user` confía en que `X-User-Id`/`X-User-Acls` ya vienen validadas "aguas
    arriba" — pero sin esto, cualquier caller que alcance el backend puede declarar su propia
    identidad, no solo el BFF del frontend. Si `service_bearer_token` está configurado, exige
    `Authorization: Bearer <token>` coincidente (comparación de tiempo constante) antes de
    seguir. Sin configurar (`None`, default), no hace nada — preserva el comportamiento actual;
    fail-closed una vez activado, igual que `dev_identity_bypass`."""

    settings: Settings = request.app.state.settings
    expected = settings.service_bearer_token
    if expected is None:
        return
    token = authorization.removeprefix("Bearer ") if authorization else None
    if token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="falta o es inválido el bearer de servicio")


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
    audit_log: AuditLog | None = None,
    voice_service: VoiceService | None = None,
) -> FastAPI:
    """Crea la app. `retriever`/`generator`/`audit_log`/`voice_service` inyectables para tests;
    si son `None`, se construyen los de producción (`tribu-rag`, NIM de chat vía `tribu-http`,
    traza sobre `tribu-audit` si está configurada, voz sobre `tribu-voice` si
    `voice_enabled`) en el arranque (requieren el registry privado, el NIM on-prem y Postgres
    respectivamente — `audit_log` cae a `NullAuditLog` si no hay Postgres configurado, no
    bloquea el arranque; `voice_service` se queda en `None` si `voice_enabled` es `False`, y
    los endpoints `/voice/*` responden 503 en ese caso)."""

    app_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.retriever is None:  # pragma: no cover - requiere el registry del SDK
            from chatrag_api.rag import tribu_rag_retriever

            app.state.retriever = await tribu_rag_retriever(
                embed_dim=app_settings.embed_dim,
                tenant_id=app_settings.tenant_id,
                milvus_uri=app_settings.milvus_uri,
                nim_embed_url=app_settings.nim_embed_url,
                nim_embed_model_id=app_settings.nim_embed_model_id,
                nim_rerank_url=app_settings.nim_rerank_url,
                nim_rerank_model_id=app_settings.nim_rerank_model_id,
                allowed_hosts=app_settings.egress_allowed_hosts,
            )
        if app.state.generator is None:  # pragma: no cover - requiere el NIM de chat on-prem
            from chatrag_api.rag import tribu_nim_chat_generator

            app.state.generator = tribu_nim_chat_generator(
                app_settings.nim_chat_url,
                model=app_settings.nim_chat_model,
                allowed_hosts=app_settings.egress_allowed_hosts,
            )
        if app.state.audit_log is None:
            if (
                app_settings.audit_database_url is not None
                and app_settings.audit_chain_key is not None
            ):  # pragma: no cover - requiere tribu-audit del registry + Postgres
                from chatrag_api.audit import TribuPostgresAuditLog

                real_audit_log = TribuPostgresAuditLog(
                    app_settings.audit_database_url, chain_key=app_settings.audit_chain_key
                )
                await real_audit_log.connect()
                app.state.audit_log = real_audit_log
            else:
                app.state.audit_log = NullAuditLog()
        if (
            app.state.voice_service is None and app_settings.voice_enabled
        ):  # pragma: no cover - requiere tribu-voice del registry + NIM Riva real
            theme_store = get_theme_store(
                audit_database_url=app_settings.audit_database_url,
                theme_file=Path(app_settings.theme_file),
            )
            app.state.voice_service = tribu_voice_service(
                nim_tts_url=app_settings.nim_tts_url,
                nim_asr_url=app_settings.nim_asr_url,
                allowed_hosts=app_settings.egress_allowed_hosts,
                get_theme=theme_store.get,
            )
        if retriever is None and generator is None:  # pragma: no cover - requiere el registry
            # tribu-guardrails: solo en arranque de producción (sin dobles inyectados) — el
            # check en sí es una función pura sin dependencias, pero el paquete solo se exige
            # instalado cuando de verdad se usa, igual que tribu-rag/tribu-http arriba. ChatRAG
            # no es un agente con acciones/planificación (solo redacta texto anclado en citas),
            # pero sí concurren dos de las tres patas de la lethal trifecta (datos con ACL +
            # contenido no confiable de munistgo.cl) — declarar el manifiesto real deja la
            # tercera pata (comunicación externa) explícita y chequeada en cada arranque, no
            # solo razonada en un comentario.
            from tribu_guardrails.lethal_trifecta import (  # type: ignore[import-not-found]
                AgentManifest,
                check_lethal_trifecta,
            )

            check_lethal_trifecta(
                AgentManifest(
                    agent_id=app_settings.app_name,
                    has_private_data_access=True,
                    has_untrusted_content_exposure=True,
                    has_external_communication=False,
                )
            )
        try:
            yield
        finally:
            aclose = getattr(app.state.generator, "aclose", None)
            if aclose is not None:  # pragma: no cover - requiere el generador real
                await aclose()
            audit_aclose = getattr(app.state.audit_log, "aclose", None)
            if audit_aclose is not None:  # pragma: no cover - requiere Postgres real
                await audit_aclose()

    app = FastAPI(title=app_settings.app_name, lifespan=lifespan)
    app.state.settings = app_settings
    app.state.retriever = retriever
    app.state.generator = generator
    app.state.audit_log = audit_log
    app.state.voice_service = voice_service
    app.state.conversation_log = ConversationLog(
        max_entries=app_settings.conversation_log_max_entries
    )
    app.include_router(admin.router)

    app.add_middleware(RequestLoggingMiddleware)
    if app_settings.rate_limit_max_requests > 0:
        app.add_middleware(
            RateLimitMiddleware,
            limiter=RateLimiter(
                max_requests=app_settings.rate_limit_max_requests,
                window_seconds=app_settings.rate_limit_window_seconds,
            ),
            paths=frozenset({"/query", "/voice/speak", "/voice/transcribe"}),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Red de seguridad: cualquier excepción no capturada explícitamente (fallo de red a un
        # NIM, bug real) se convierte en JSON en vez de la página HTML 500 por defecto de
        # Starlette — el frontend (y cualquier caller) siempre puede esperar JSON de este
        # servicio. `HTTPException` no pasa por aquí (Starlette la despacha con su propio
        # handler antes de llegar a este, que solo ve lo genuinamente inesperado).
        logger.exception("excepción no manejada en %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "error interno del servicio"}, status_code=500)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "app": app_settings.app_name,
            "embed_dim": app_settings.embed_dim,
            "voice_enabled": app_settings.voice_enabled,
        }

    @app.get("/theme")
    async def theme() -> Theme:
        # Público a propósito, sin dependencies=[Depends(verify_service_bearer)] — cualquier
        # visitante necesita el tema para pintar la página (branding, colores), antes de que
        # exista ninguna sesión. No expone nada sensible: `Theme` es solo identidad visual.
        store = get_theme_store(
            audit_database_url=app_settings.audit_database_url,
            theme_file=Path(app_settings.theme_file),
        )
        return await store.get()

    @app.post("/query", response_model=Answer, dependencies=[Depends(verify_service_bearer)])
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
        try:
            answer = await asyncio.wait_for(
                answer_query(
                    retriever, generator, body, user, audit_log=request.app.state.audit_log
                ),
                timeout=app_settings.query_timeout_seconds,
            )
            conversation_log: ConversationLog = request.app.state.conversation_log
            conversation_log.record(
                user_id=user.user_id,
                question=body.question,
                answer=answer.text,
                abstained=answer.abstained,
                citations_shown=tuple(c.source_uri for c in answer.citations),
            )
            return answer
        except TimeoutError as exc:
            logger.warning(
                "timeout de %.0fs en /query para user_id=%s", app_settings.query_timeout_seconds,
                user.user_id,
            )
            raise HTTPException(
                status_code=504,
                detail=f"la consulta tardó más de {app_settings.query_timeout_seconds:.0f}s",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            # Cualquier otro fallo del retriever/generador reales (NIM caído, Milvus
            # inalcanzable) llega aquí como una excepción cruda de red/SDK — se traduce a 502
            # (bad gateway: el problema es aguas arriba, no de esta consulta) con detalle
            # genérico; el traceback real queda en el log, no en la respuesta al cliente.
            logger.exception("fallo en /query para user_id=%s", user.user_id)
            raise HTTPException(
                status_code=502, detail="no se pudo completar la consulta (servicio aguas arriba)"
            ) from exc

    def _voice_service_or_503(request: Request) -> VoiceService:
        service: VoiceService | None = request.app.state.voice_service
        if service is None:
            raise HTTPException(status_code=503, detail=str(VoiceDisabledError()))
        return service

    @app.post(
        "/voice/session",
        response_model=VoiceSessionInfo,
        dependencies=[Depends(verify_service_bearer)],
    )
    async def voice_session(request: Request) -> VoiceSessionInfo:
        try:
            return await _voice_service_or_503(request).mint_session()
        except VoiceConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/voice/speak", dependencies=[Depends(verify_service_bearer)])
    async def voice_speak(body: SpeakRequest, request: Request) -> Response:
        service = _voice_service_or_503(request)
        try:
            audio = await service.speak(
                token_id=body.token_id, text=body.text, emotion=body.emotion
            )
        except VoiceTokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except VoiceConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(content=audio, media_type="audio/wav")

    @app.post("/voice/transcribe", dependencies=[Depends(verify_service_bearer)])
    async def voice_transcribe(
        request: Request, x_voice_token: str = Header(...)
    ) -> dict[str, str]:
        service = _voice_service_or_503(request)
        audio = await request.body()
        content_type = request.headers.get("content-type", "audio/wav")
        try:
            text = await service.transcribe(
                token_id=x_voice_token, audio=audio, content_type=content_type
            )
        except VoiceTokenError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {"text": text}

    return app
