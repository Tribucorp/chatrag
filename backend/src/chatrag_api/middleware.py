"""Robustez transversal del backend: límite de tasa en memoria (por IP) y logging estructurado
por request. Ninguno es una dependencia externa nueva — todo vive en el propio proceso.

`RateLimiter` es una ventana deslizante en memoria: correcta para un piloto de una sola
instancia, pero cada réplica cuenta por su cuenta si el servicio corre con más de un worker —
para eso hace falta un store compartido (Redis, etc.), fuera de alcance aquí; se documenta la
limitación en vez de fingir que no existe."""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("chatrag_api")


class RateLimiter:
    """Ventana deslizante por clave (típicamente IP). `allow()` es la única operación: registra
    el intento y dice si cabía en la ventana — no hay un método `reset` a propósito, el olvido
    de intentos viejos ya lo hace `allow()` en cada llamada."""

    def __init__(self, *, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float) -> bool:
        hits = self._hits[key]
        while hits and now - hits[0] > self._window_seconds:
            hits.popleft()
        if len(hits) >= self._max_requests:
            return False
        hits.append(now)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """429 fail-closed cuando se supera la tasa en las rutas vigiladas (`paths`) — el resto del
    servicio (`/health`, `/theme`, `/admin/*`) no pasa por aquí, solo lo que gasta tráfico real
    contra los NIM (`/query`, `/voice/*`)."""

    def __init__(
        self, app: object, *, limiter: RateLimiter, paths: frozenset[str]
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._limiter = limiter
        self._paths = paths

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in self._paths:
            client = request.client.host if request.client else "desconocido"
            if not self._limiter.allow(client, now=time.monotonic()):
                logger.warning(
                    "límite de tasa superado: path=%s client=%s", request.url.path, client
                )
                return JSONResponse(
                    {"detail": "demasiadas solicitudes, intenta de nuevo en un momento"},
                    status_code=429,
                )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Un log por request: método, ruta, status, duración, y un `request_id` corto que también
    se devuelve en la cabecera `X-Request-Id` — para correlacionar un error que ve el usuario
    con la línea exacta del log del servicio."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = uuid.uuid4().hex[:12]
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000
            logger.exception(
                "request_id=%s method=%s path=%s status=excepción duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-Id"] = request_id
        return response
