# ChatRAG 🇨🇱

**ChatRAG** es el asistente RAG de la comuna de Santiago (Chile) de **Tribucorp** — y el
**piloto nº1 de adopción del [Tribu SDK](../tribu-sdk)**. Responde sobre trámites y servicios
municipales de la Ilustre Municipalidad de Santiago ([munistgo.cl](https://www.munistgo.cl/))
con **citas verificables**: toda respuesta cita su fuente, o el backend se abstiene en vez de
inventar.

> Este repo **reemplazó** su prototipo original (ElevenLabs Conversational AI + voz por
> WebSocket) por la arquitectura del SDK: FastAPI on-prem + Next.js. El prototipo vive en
> `legacy/elevenlabs-kb/` — ver la nota al final sobre por qué sigue ahí.

## Arquitectura

```
Navegador ──► Next.js BFF (src/app/api/chat/route.ts) ──► chatrag-api (FastAPI, backend/)
              │                                             │
              ├─ Auth.js v5 (src/lib/auth.ts)               ├─ tribu-rag  → NIM embed/rerank on-prem
              │  deriva X-User-Id/X-User-Acls                ├─ tribu-http → NIM chat on-prem
              │  (sin provider real todavía — TODO)          └─ filter_by_acl (server-side, fail-closed)
              └─ CHATRAG_SERVICE_BEARER_TOKEN
```

El navegador **nunca** habla directo con `chatrag-api` ni declara su propia identidad: el BFF
adjunta el bearer de servicio y la sesión antes de reenviar. El backend filtra por ACL en el
servidor y se abstiene (en vez de responder sin base) cuando, tras el filtrado, no queda ninguna
cita accesible.

### Qué del SDK está integrado de verdad hoy

Verificado contra el estado real del SDK (no contra lo que un doc diga que "debería" estar):

| Módulo | Estado |
|---|---|
| `tribu-rag` | **Integrado** — retriever real (`backend/src/chatrag_api/rag.py`) |
| `tribu-http` | **Integrado** — cliente al NIM de chat, egress deny-by-default |
| `tribu-audit` | **Integrado** — traza de decisión (`backend/src/chatrag_api/audit.py`), cadena WORM HMAC respaldada en Postgres, opt-in |
| `tribu-guardrails` | **Integrado** — `render_untrusted_as_data` envuelve las citas antes del NIM; `check_lethal_trifecta` corre en `lifespan` |
| `tribu-auth` | No existe en el registry. Stopgap: Auth.js v5 sin provider (TODO) |
| `tribu-observability` | No existe — su rol de traza de decisión lo cubre `tribu-audit` (arriba) |
| `tribu-datagov` | Existe; evaluado para el filtro de ACL, no lo reemplaza (defensa en profundidad) |
| `tribu-voice` | **Integrado** (`backend/src/chatrag_api/voice.py`) — TTS + avatar + token efímero reales; opt-in (`CHATRAG_VOICE_ENABLED`), revisión legal confirmada (ver CLAUDE.md), contrato de red con el NIM Riva sin verificar |
| `tribu-demo-kit` | No existe todavía |

## Stack

- **Frontend**: Next.js 16 (App Router) + React 19 + Tailwind v4. Chat de texto
  (`src/components/chat-agent.tsx`) contra el BFF propio, sin voz cloud.
- **Backend** (`backend/`): FastAPI (`chatrag-api`), Python ≥3.11, `uv` para dependencias.
  Consume los módulos `tribu-*` como wheels del registry privado de Tribucorp — nunca PyPI, nunca
  vendorizado.
- Sin proveedores cloud de voz ni de LLM: todo corre on-prem contra NIM de NVIDIA.

## Puesta en marcha (dev local)

```bash
# 1. Variables de entorno — .env.example tiene tanto las del frontend como las del backend
#    (comentadas, con su prefijo CHATRAG_*); el backend las lee de entorno, no de un .env propio
#    (ver Settings.from_env en backend/src/chatrag_api/config.py).
cp .env.example .env.local

# 2. Frontend
npm install
npm run dev                    # http://localhost:3000 (o el siguiente puerto libre)

# 3. Backend — requiere el registry privado del SDK para el árbol de deps completo
cd backend
uv venv --python 3.12
uv pip install -e .            # instala tribu-http/tribu-rag/tribu-audit/tribu-guardrails/tribu-voice desde el índice `tribu` (ver pyproject.toml)
uv run uvicorn chatrag_api.app:create_app --factory --reload --port 8080
```

Sin acceso al registry privado ni a los NIM on-prem, el backend **no arranca en producción**
(`tribu_rag_retriever`/`tribu_nim_chat_generator` se construyen perezosamente en `startup`), pero
sí se puede desarrollar y testear: `create_app(retriever=..., generator=...)` acepta dobles
inyectados, que es exactamente lo que usan los tests (`backend/tests/`).

### Tests

```bash
cd backend
uv run pytest tests -q                # unitario, sin registry (por defecto excluye `integration`)
uv run pytest tests -m integration -q # requiere tribu-rag/tribu-http instalados de verdad
```

CI (`.github/workflows/ci.yml`) corre tres jobs: `frontend` (lint + build), `backend` (ruff +
mypy --strict + pytest unitario, sin tocar el registry) y `backend-integration` (instala los
wheels reales + levanta un Postgres efímero para las pruebas de `tribu-audit`; solo corre si el
secret `UV_INDEX_TRIBU_URL` está configurado).

## Traza de decisión (`tribu-audit`)

Opt-in — sin `CHATRAG_AUDIT_DATABASE_URL`/`CHATRAG_AUDIT_CHAIN_KEY` (hex), el servicio usa
`NullAuditLog` (sin traza, la consulta sigue funcionando igual). Configuradas ambas, cada
`/query` queda anclado en una cadena WORM HMAC real (`tribu_audit.AuditChain`, respaldada en
Postgres) con qué se mostró y qué se bloqueó por ACL — ver `backend/src/chatrag_api/audit.py`.

## Identidad (estado actual)

`src/lib/auth.ts` trae el scaffold de Auth.js v5 (sesión JWT, `CHATRAG_AUTH_SECRET`) pero **sin
provider configurado todavía** — no hay SSO/OIDC del ecosistema Tribucorp confirmado para este
producto. Hasta que se añada, `auth()` siempre devuelve `null`, el BFF no manda
`X-User-Id`/`X-User-Acls`, y el backend responde 401 (fail-closed) salvo que actives
`CHATRAG_DEV_IDENTITY_BYPASS` en el backend — **solo para desarrollo local, nunca en producción**.

## Administración (`/admin`, `/admin/theme`)

Protegido por `CHATRAG_ADMIN_TOKEN` (bearer propio, distinto de `CHATRAG_SERVICE_BEARER_TOKEN`;
sin configurar, `/admin/*` responde 503 siempre, nunca abierto por defecto):

- **`/admin`** — dispara `POST /admin/reindex` (ingesta real a `tribu-rag`/Milvus, ver
  `backend/src/chatrag_api/ingest.py`), estado del índice (`GET /admin/index-status`) y la
  traza de auditoría (`GET /admin/audit`, si `tribu-audit` está configurado).
- **`/admin/theme`** — editor visual del tema (colores, logo, tipografía, densidad, estilo de
  burbuja de chat, copy de la cabecera, y la voz del asistente — ver
  `backend/src/chatrag_api/theme.py`); `layout.tsx` lo aplica en cada request (SSR) como
  variables CSS, sin flash de tema por defecto.
- **`/admin/conversations`** — vista operativa de conversaciones recientes (pregunta/respuesta/
  citas/abstención) y métricas de consumo del RAG (total de consultas, tasa de abstención,
  fuentes más citadas), sobre `ConversationLog` (`backend/src/chatrag_api/conversations.py`): un
  buffer en memoria siempre activo, sin configuración, que se pierde al reiniciar el proceso a
  propósito — **no** es el registro de cumplimiento (eso es `tribu-audit`, arriba).

## Ingesta del corpus (`knowledge/`, `legacy/elevenlabs-kb/`)

La ingesta real a `tribu-rag` (`backend/src/chatrag_api/ingest.py`, disparada desde
`POST /admin/reindex`) ya está cableada — mismo patrón que
`tribu-sdk/scripts/ingesta_corpus.py` (guard de dimensión, `HeadingContextualizer`/
`NimContextualizer`). Fuente actual: `knowledge/*.md`. `legacy/elevenlabs-kb/` sigue en el repo
porque `crawl-site-to-kb.ts` (el recolector real de `munistgo.cl`, con su filtro
evergreen-vs-noticias) todavía no se portó como *origen* de ese pipeline — se elimina cuando
ese recolector exista sobre `tribu-rag`, no antes.

## Voz

Apagada por defecto, opt-in explícito (`CHATRAG_VOICE_ENABLED`/`NEXT_PUBLIC_VOICE_ENABLED=0`).
`tribu-voice` está **integrado** (`backend/src/chatrag_api/voice.py`): síntesis TTS + avatar +
token efímero reales, sobre el código auditado del SDK. La revisión legal de NVIDIA
(Product-Specific Terms §C.1.1/§C.1.2) fue confirmada por Javier (ver CLAUDE.md) — pero la
regla dura sigue igual, es estructural en `tribu_voice`, no una config: solo voces **stock**,
**jamás clonación de voz**, y el reconocimiento de voz (`RivaAsrClient`, cliente propio de
ChatRAG — no es parte de `tribu-voice`) **nunca** infiere el estado emocional del usuario desde
su audio, solo transcribe texto. El contrato de red con el NIM Riva real está **sin verificar**
(no hay ninguna imagen NIM de Riva pineada en el SDK todavía) — confirmar antes de producción.

Qué voz stock usa el asistente (`Theme.voice_id`, catálogo de `tribu_voice.stock_voice_ids()`) y
con qué nombre de marca (`Theme.app_name`) se configura desde `/admin/theme` sin redeploy —
`TribuVoiceService` re-lee el tema en cada sesión/síntesis, así que un cambio en el admin aplica
a la siguiente sesión sin reiniciar el proceso. Un `voice_id` fuera del catálogo falla-cerrado
(`VoiceConfigError`, 503) en vez de sintetizar con una voz inventada.

## Robustez del backend

- **Límite de tasa** (`backend/src/chatrag_api/middleware.py`): ventana deslizante en memoria
  por IP sobre `/query` y `/voice/*` (`CHATRAG_RATE_LIMIT_MAX_REQUESTS`,
  `CHATRAG_RATE_LIMIT_WINDOW_SECONDS`) — 429 al superarla. No apto para múltiples réplicas (cada
  proceso cuenta por su cuenta); `CHATRAG_RATE_LIMIT_MAX_REQUESTS<=0` lo desactiva.
- **Timeout de `/query`** (`CHATRAG_QUERY_TIMEOUT_SECONDS`): evita que una consulta se cuelgue
  para siempre si un NIM deja de responder — 504 al superarlo.
- **Errores estructurados**: cualquier excepción no manejada se traduce a JSON (nunca la página
  HTML 500 por defecto de Starlette) y queda en el log con `X-Request-Id` para correlacionar.

## Documentación de negocio

No se duplica aquí: vive en `01_PRODUCTOS/FORGE/40_CHATRAG/` (plan, mercado, VPack).
