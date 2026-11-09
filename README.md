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
              ├─ tribu-auth (src/lib/auth.ts)               ├─ tribu-rag  → NIM embed/rerank on-prem
              │  sesión + rol → X-User-Id/X-User-Acls        ├─ tribu-http → NIM chat on-prem
              │  (src/lib/acl.ts, src/lib/session.ts)        └─ filter_by_acl (server-side, fail-closed)
              └─ CHATRAG_SERVICE_BEARER_TOKEN
```

El navegador **nunca** habla directo con `chatrag-api` ni declara su propia identidad: el BFF
adjunta el bearer de servicio y la sesión antes de reenviar. El backend filtra por ACL en el
servidor y se abstiene (en vez de responder sin base) cuando, tras el filtrado, no queda ninguna
cita accesible.

### Qué del SDK está integrado de verdad hoy

Verificado contra el SDK **v1.0.0** (tabla «Estado real por módulo» de su CLAUDE.md, 1-nov-2026) y su código:

| Módulo | Estado |
|---|---|
| `tribu-rag` | **Integrado** — retriever real (`backend/src/chatrag_api/rag.py`) |
| `tribu-http` | **Integrado** — cliente al NIM de chat, egress deny-by-default |
| `tribu-audit` | **Integrado** — traza de decisión (`backend/src/chatrag_api/audit.py`), cadena WORM HMAC respaldada en Postgres, opt-in |
| `tribu-guardrails` | **Integrado** — `render_untrusted_as_data` envuelve las citas antes del NIM; `check_lethal_trifecta` corre en `lifespan` |
| `tribu-auth` (TS) | **Integrado** en el frontend (`src/lib/auth.ts`): login email/contraseña, organización + roles → ACLs, rate-limit de login. Sin BD propia todavía (memoryAdapter: se pierde al reiniciar); sin OIDC del ecosistema (no existe en el SDK) |
| `tribu-observability` | Existe (Parcial: OTel GenAI + MAST, sin Prometheus/Sentry). **No integrado todavía**; la traza de decisión la cubre `tribu-audit` |
| `tribu-datagov` | Existe; evaluado para el filtro de ACL, no lo reemplaza (defensa en profundidad) |
| `tribu-voice` | **Integrado** (`backend/src/chatrag_api/voice.py`) — TTS + avatar + token efímero reales; opt-in (`CHATRAG_VOICE_ENABLED`), revisión legal confirmada (ver CLAUDE.md), contrato de red con el NIM Riva sin verificar |
| `tribu-demo-kit` | Existe (Parcial, plantilla ARM64 sin verificar). No integrado |

## Stack

- **Frontend**: Next.js 16 (App Router) + React 19 + Tailwind v4. Chat de texto
  (`src/components/chat-agent.tsx`) contra el BFF propio, sin voz cloud.
- **Backend** (`backend/`): FastAPI (`chatrag-api`), Python ≥3.11, `uv` para dependencias.
  Consume los módulos `tribu-*` como **dependencias git fijadas a una tag del SDK** (ADR-0020 del
  SDK; hoy `v1.0.0`, ver `backend/pyproject.toml`) — nunca PyPI, nunca vendorizado. El frontend
  consume `@tribu/auth` desde GitHub Packages (`.npmrc`).
- Sin proveedores cloud de voz ni de LLM: todo corre on-prem contra NIM de NVIDIA.

## Puesta en marcha (dev local)

```bash
# 1. Variables de entorno — .env.example tiene tanto las del frontend como las del backend
#    (comentadas, con su prefijo CHATRAG_*); el backend las lee de entorno, no de un .env propio
#    (ver Settings.from_env en backend/src/chatrag_api/config.py).
cp .env.example .env.local

# 2. Frontend — @tribu/auth sale de GitHub Packages (privado de la organización)
export NODE_AUTH_TOKEN=$(gh auth token)   # token con read:packages
npm install
npm run dev                    # http://localhost:3000 (o el siguiente puerto libre)

# 3. Backend — el SDK es un repo privado: basta acceso a la organización (`gh auth setup-git`).
#    tribu-audit y tribu-crypto tienen núcleo Rust: hace falta cargo.
cd backend
uv sync                        # instala tribu-* desde git (tag fijada en pyproject.toml, uv.lock)
uv run uvicorn chatrag_api.app:create_app --factory --reload --port 8080
```

Sin los NIM on-prem ni Milvus, el backend **no arranca en producción**
(`tribu_rag_retriever`/`tribu_nim_chat_generator` se construyen perezosamente en `startup`), pero
sí se puede desarrollar y testear: `create_app(retriever=..., generator=...)` acepta dobles
inyectados, que es exactamente lo que usan los tests (`backend/tests/`).

### Tests

```bash
cd backend
uv run pytest tests -q                # unitario (por defecto excluye `integration`)
uv run pytest tests -m "" -q          # todo, incluida la integración con el SDK real
# Los 2 tests de tribu-audit necesitan Postgres: CHATRAG_TEST_AUDIT_DATABASE_URL=postgresql://...
npm test                              # frontend (vitest)
```

CI (`.github/workflows/ci.yml`) corre dos jobs:

- `frontend`: `npm ci` (con `@tribu/auth` de GitHub Packages, vía `GITHUB_TOKEN`), lint,
  vitest y build. Requiere que el paquete `tribu-auth` dé acceso a este repo (Settings del
  paquete → *Manage Actions access*).
- `backend`: instala el SDK de verdad (`uv sync --frozen`), ruff, mypy --strict y pytest
  completo (unitario + integración, con un Postgres efímero para `tribu-audit`). Requiere el
  secret `TRIBU_SDK_PAT` (PAT fine-grained, `contents: read` sobre `Tribucorp/tribu-sdk`);
  sin él falla, no pasa en verde sin haber probado el SDK.

## Traza de decisión (`tribu-audit`)

Opt-in — sin `CHATRAG_AUDIT_DATABASE_URL`/`CHATRAG_AUDIT_CHAIN_KEY` (hex), el servicio usa
`NullAuditLog` (sin traza, la consulta sigue funcionando igual). Configuradas ambas, cada
`/query` queda anclado en una cadena WORM HMAC real (`tribu_audit.AuditChain`, respaldada en
Postgres) con qué se mostró y qué se bloqueó por ACL — ver `backend/src/chatrag_api/audit.py`.

## Identidad (`tribu-auth`)

`src/lib/auth.ts` instancia `createTribuAuth` (better-auth + organizations + accessControl) con
los roles de ChatRAG (`src/lib/acl.ts`: `member`, `rrhhStaff`, `finanzasStaff`,
`municipalAdmin`). El BFF (`src/lib/session.ts`) valida la sesión, resuelve el rol del usuario
en la organización `comuna-santiago` y lo traduce a `X-User-Acls`; sin sesión, 401. La home
redirige a `/login` sin sesión.

- `CHATRAG_AUTH_SECRET` obligatorio (fail-closed, sin default).
- `CHATRAG_AUTH_DEMO_SEED=1` crea la organización y 4 cuentas demo con contraseña pública —
  **solo demo**. Sin él, cualquiera puede registrarse pero solo ve citas públicas.
- Pendiente: BD real (hoy memoryAdapter: usuarios y sesiones se pierden al reiniciar) y una vía
  para asignar roles fuera del seed demo.

`CHATRAG_DEV_IDENTITY_BYPASS` en el backend sigue existiendo para llamar a `chatrag-api` sin el
frontend — **solo desarrollo local, nunca en producción**.

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
