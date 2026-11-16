"""Configuración del backend de ChatRAG. Todo por entorno (k8s-ready, sin rutas de host).

Notas heredadas del SDK que se materializan aquí:
- **Dimensión de embedding 2048 por defecto** (no 1024): el ecosistema 2026 usa 2048. El guard
  dinámico de `tribu-rag` lee la dimensión real del endpoint en arranque y falla-cerrado si no
  coincide con el índice; aquí solo declaramos el valor esperado para el arranque.
- **On-prem de verdad**: los NIM (embed/rerank/chat/voz) se sirven en la GPU del cliente, nunca
  APIs cloud. No hay claves de proveedores cloud en esta config.
- **`voice_enabled` arranca en `False`** por defecto (opt-in explícito por entorno) — la
  revisión legal NVIDIA (Product Specific Terms §C.1.1/§C.1.2) fue confirmada por Javier
  (15-sep-2026, fuera de este repo; ver CLAUDE.md), pero la regla de arquitectura sigue igual:
  solo voces stock de `tribu-voice`, nunca clonación, nunca inferir la emoción del usuario a
  partir de su audio — eso no depende de la revisión, está forzado en los tipos del propio SDK.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_EMBED_DIM = 2048


class Settings(BaseModel):
    """Ajustes del backend, cargados de entorno con `Settings.from_env()`. Inmutable."""

    model_config = ConfigDict(frozen=True)

    app_name: str = "ChatRAG"
    embed_dim: int = Field(default=DEFAULT_EMBED_DIM, gt=0)

    # Tenant físico en Milvus (colección propia — B-24 del SDK: aislamiento por namespace
    # físico, no un filtro de metadato). Fijo por despliegue, no por request.
    tenant_id: str = "chatrag-santiago"
    # Milvus real (tribu_rag.milvus_store.MilvusVectorStore) — ver
    # tribu-sdk/python/tribu-rag/deploy/docker-compose.milvus.yml para levantarlo.
    milvus_uri: str = "http://localhost:19530"

    # Endpoints on-prem (NIM servidos en la GPU del cliente). Sin defaults cloud.
    nim_embed_url: str = "http://localhost:8002"
    nim_rerank_url: str = "http://localhost:8003"
    nim_chat_url: str = "http://localhost:8004"
    # model_id tal como lo reporta CADA NIM en /v1/models (con el prefijo "nvidia/" para el de
    # embed — verificado contra el NIM real en el Spark, sin él /v1/embeddings responde 404;
    # ver tribu-sdk/scripts/ingesta_corpus.py). El de rerank sigue la misma convención de
    # nombre de imagen pero SIN verificar todavía contra un NIM real -- confirmar contra
    # /v1/models antes de depender de este default en producción.
    nim_embed_model_id: str = "nvidia/llama-nemotron-embed-1b-v2"
    nim_rerank_model_id: str = "nvidia/llama-nemotron-rerank-vl-1b-v2"
    # Nombre del modelo tal como lo expone el contenedor NIM (`/v1/chat/completions`,
    # contrato OpenAI-compatible). Varía por despliegue on-prem — sin default plausible.
    nim_chat_model: str = "nemotron"
    # NIM Riva TTS/ASR (ver voice.py) — contrato de red SIN VERIFICAR contra un NIM Riva real
    # (no hay ninguna imagen NIM de Riva pineada en el SDK todavía). Solo se usan si
    # voice_enabled=True.
    nim_tts_url: str = "http://localhost:8005"
    nim_asr_url: str = "http://localhost:8006"

    # Egress deny-by-default (tribu-http): hosts a los que el backend puede salir. Solo los
    # NIM on-prem por defecto; nada de internet abierto.
    egress_allowed_hosts: frozenset[str] = frozenset({"localhost", "127.0.0.1"})

    # Voz: apagada por defecto, opt-in explícito por entorno (CHATRAG_VOICE_ENABLED=1) — ver
    # voice.py. Revisión legal confirmada (ver docstring del módulo); nunca clonación de voz,
    # nunca inferir la emoción del usuario a partir de su audio.
    voice_enabled: bool = False

    # Bypass de identidad SOLO para desarrollo local, mientras tribu-auth no esté wireado al
    # cliente: si no llega X-User-Id, `current_user` usa esta identidad en vez de fallar con 401.
    # Apagado por defecto (None) — fail-closed se mantiene salvo que se active explícitamente
    # por entorno. Nunca activar en producción.
    dev_identity_bypass: str | None = None

    # Bearer de servicio compartido entre el backend y su único caller de confianza (el BFF del
    # frontend, `chatrag/src/app/api/chat/route.ts`). `None` por defecto: preserva el
    # comportamiento actual (cualquiera que alcance el backend puede declarar su propia
    # identidad vía X-User-Id/X-User-Acls, confiando en que la red ya lo restringe). Activarlo
    # (mismo valor en ambos lados) exige además ese bearer — fail-closed una vez configurado,
    # igual que `dev_identity_bypass`.
    service_bearer_token: str | None = None

    # Traza de decisión sobre tribu-audit (ver audit.py) — Postgres respaldando la cadena WORM
    # HMAC. Ambas `None` por defecto: sin ellas, el servicio usa `NullAuditLog` (sin traza,
    # sin fallar la consulta) — la auditoría es opt-in, no una dependencia dura para correr
    # ChatRAG. `audit_chain_key` es la clave HMAC de la cadena, hex-encoded en el entorno.
    audit_database_url: str | None = None
    audit_chain_key: bytes | None = None

    # Bearer del panel /admin (ingesta, reindex, estado del índice, ver audit trail) — mismo
    # mecanismo de comparación en tiempo constante que `service_bearer_token`. `None` por
    # defecto: sin configurar, /admin/* responde 503 (nunca abierto sin token por omisión, ni
    # siquiera en dev — a diferencia de `dev_identity_bypass`, esto no tiene stopgap de dev
    # porque /admin puede reindexar/gastar tráfico real hacia los NIM).
    admin_token: str | None = None

    # Directorio con el corpus Markdown a ingestar (`POST /admin/reindex`). Relativo al
    # directorio de trabajo del proceso (`cd backend && uv run uvicorn ...` per README, así que
    # el default resuelve a `chatrag/knowledge/`) — no se deriva de `__file__` a propósito,
    # para no asumir un layout de instalación concreto.
    knowledge_dir: str = "../knowledge"

    # Fichero JSON del tema (ver theme.py) cuando no hay Postgres configurado
    # (audit_database_url) — con Postgres, el tema vive en la tabla chatrag_theme de esa misma
    # base en vez de este fichero.
    theme_file: str = "../theme.json"

    # Robustez (ver middleware.py): límite de tasa en memoria por IP sobre /query y /voice/* —
    # no es apto para múltiples réplicas (cada proceso cuenta por su cuenta), ver docstring de
    # RateLimiter. `rate_limit_max_requests<=0` desactiva el límite (útil en tests/dev).
    rate_limit_max_requests: int = 30
    rate_limit_window_seconds: float = Field(default=60.0, gt=0)
    # Timeout de la llamada completa retriever+generador en /query — evita que una consulta se
    # cuelgue para siempre si un NIM deja de responder. `asyncio.TimeoutError` se traduce a 504.
    query_timeout_seconds: float = Field(default=30.0, gt=0)

    # Buffer en memoria de conversaciones recientes (ver conversations.py) — siempre activo,
    # sin configuración, para /admin/conversations y /admin/metrics. Se pierde al reiniciar
    # el proceso a propósito: no es el registro de cumplimiento (eso es tribu-audit, opt-in).
    conversation_log_max_entries: int = Field(default=200, gt=0)

    @classmethod
    def from_env(cls) -> Settings:
        """Construye desde variables de entorno, con los defaults on-prem del SDK."""

        hosts = os.environ.get("CHATRAG_EGRESS_HOSTS")
        allowed = (
            frozenset(h.strip() for h in hosts.split(",") if h.strip())
            if hosts
            else frozenset({"localhost", "127.0.0.1"})
        )
        return cls(
            app_name=os.environ.get("CHATRAG_APP_NAME", "ChatRAG"),
            embed_dim=int(os.environ.get("CHATRAG_EMBED_DIM", DEFAULT_EMBED_DIM)),
            tenant_id=os.environ.get("CHATRAG_TENANT_ID", "chatrag-santiago"),
            milvus_uri=os.environ.get("CHATRAG_MILVUS_URI", "http://localhost:19530"),
            nim_embed_url=os.environ.get("CHATRAG_NIM_EMBED_URL", "http://localhost:8002"),
            nim_rerank_url=os.environ.get("CHATRAG_NIM_RERANK_URL", "http://localhost:8003"),
            nim_chat_url=os.environ.get("CHATRAG_NIM_CHAT_URL", "http://localhost:8004"),
            nim_embed_model_id=os.environ.get(
                "CHATRAG_NIM_EMBED_MODEL_ID", "nvidia/llama-nemotron-embed-1b-v2"
            ),
            nim_rerank_model_id=os.environ.get(
                "CHATRAG_NIM_RERANK_MODEL_ID", "nvidia/llama-nemotron-rerank-vl-1b-v2"
            ),
            nim_chat_model=os.environ.get("CHATRAG_NIM_CHAT_MODEL", "nemotron"),
            nim_tts_url=os.environ.get("CHATRAG_NIM_TTS_URL", "http://localhost:8005"),
            nim_asr_url=os.environ.get("CHATRAG_NIM_ASR_URL", "http://localhost:8006"),
            egress_allowed_hosts=allowed,
            voice_enabled=os.environ.get("CHATRAG_VOICE_ENABLED", "0") == "1",
            dev_identity_bypass=os.environ.get("CHATRAG_DEV_IDENTITY_BYPASS") or None,
            service_bearer_token=os.environ.get("CHATRAG_SERVICE_BEARER_TOKEN") or None,
            audit_database_url=os.environ.get("CHATRAG_AUDIT_DATABASE_URL") or None,
            audit_chain_key=(
                bytes.fromhex(chain_key_hex)
                if (chain_key_hex := os.environ.get("CHATRAG_AUDIT_CHAIN_KEY"))
                else None
            ),
            admin_token=os.environ.get("CHATRAG_ADMIN_TOKEN") or None,
            knowledge_dir=os.environ.get("CHATRAG_KNOWLEDGE_DIR", "../knowledge"),
            theme_file=os.environ.get("CHATRAG_THEME_FILE", "../theme.json"),
            rate_limit_max_requests=int(os.environ.get("CHATRAG_RATE_LIMIT_MAX_REQUESTS", "30")),
            rate_limit_window_seconds=float(
                os.environ.get("CHATRAG_RATE_LIMIT_WINDOW_SECONDS", "60")
            ),
            query_timeout_seconds=float(os.environ.get("CHATRAG_QUERY_TIMEOUT_SECONDS", "30")),
            conversation_log_max_entries=int(
                os.environ.get("CHATRAG_CONVERSATION_LOG_MAX_ENTRIES", "200")
            ),
        )
