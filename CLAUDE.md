# CLAUDE.md — ChatRAG (piloto de adopción del Tribu SDK)

> Constitución del repo. Si algo contradice este documento, gana este documento (y se discute
> con Javier). **La constitución de la plataforma es el Tribu SDK**
> (`~/repositorio/tribu-sdk/CLAUDE.md`); este documento solo añade lo específico del producto.

## Qué es

Asistente RAG de la comuna de Santiago (Chile): responde sobre trámites y servicios municipales
con **citas verificables**, sobre el corpus de `munistgo.cl`. Es el **piloto nº1 de adopción del
Tribu SDK** — su feedback define la DX del SDK.

## Arquitectura

- **Frontend** (`src/`): Next.js 16 + React 19. Chat de texto contra el backend, con modo de
  voz opcional (`/voice/*`, gateado por `NEXT_PUBLIC_VOICE_ENABLED`); muestra las citas con su
  fuente. **Sin proveedores cloud de voz** (se retiró ElevenLabs) — la voz, cuando está
  encendida, es Riva on-prem vía `tribu-voice`, nunca una API cloud. Panel de administración en
  `/admin` (ingesta/reindex del RAG, estado del índice, auditoría), `/admin/theme` (theming:
  colores, logo, tipografía, densidad, estilo de burbuja, copy de la cabecera, y qué voz stock
  usa el asistente — ver `backend/src/chatrag_api/theme.py`) y `/admin/conversations` (vista
  operativa de conversaciones recientes + métricas de consumo del RAG, sobre un buffer en
  memoria — `conversations.py` — distinto del audit trail), todos protegidos por
  `CHATRAG_ADMIN_TOKEN`.
- **Backend** (`backend/`): FastAPI (`chatrag-api`) que consume los módulos del SDK como
  **dependencias git fijadas a una tag** (ADR-0020 del SDK, `docs/CONSUMIR_EL_SDK.md`; hoy
  **v1.0.0**, misma tag en todas las líneas de `[tool.uv.sources]`) — nunca vendorizar ni
  copiar código del SDK. `registry.tribucorp.internal` **nunca existió**; no reintroducirlo.
  Estado real: tabla «Estado real por módulo» del CLAUDE.md del SDK (se actualiza en cada
  release) — no asumir que un módulo existe, o no, solo porque se documentó aquí antes:
  - `tribu-rag` — recuperación híbrida (dimensión **2048**, guard dinámico), pre-filtrado por
    tenant, Contextual Retrieval. **Integrado** (`rag.py`, `ingest.py`). No hay un
    `HybridRetriever` en el SDK: la composición embed → Milvus híbrido → rerank es del producto.
  - `tribu-http` — cliente único, **egress deny-by-default** hacia los NIM on-prem. **Integrado**.
  - `tribu-auth` — paquete **TypeScript** (`@tribu/auth` = `npm:@tribucorp/tribu-auth`, GitHub
    Packages, `.npmrc`). **Integrado en el frontend** (`src/lib/auth.ts`, `createTribuAuth`):
    login, organización + roles (`src/lib/acl.ts`, única tabla rol → ACL). El BFF
    (`src/lib/session.ts`) valida la sesión y pasa `X-User-Id`/`X-User-Acls` al backend, que
    confía en ellas solo con el bearer de servicio (`current_user` en `app.py`). Pendiente: BD
    real (hoy memoryAdapter) y OIDC del ecosistema (no existe en el SDK). Cuentas demo solo con
    `CHATRAG_AUTH_DEMO_SEED=1`.
  - `tribu-observability` — existe (Parcial en v1.0.0), **no integrado**; la traza de decisión
    la cubre `tribu-audit`.
  - `tribu-audit` — cadena WORM HMAC real vía PyO3. **Integrado** (`audit.py`): API confirmada
    leyendo el código fuente real del SDK en disco (`~/repositorio/tribu-sdk/python/`, no el
    corpus de x9 — se rehusó por falta de referencia documentada). Opt-in vía
    `CHATRAG_AUDIT_DATABASE_URL`/`CHATRAG_AUDIT_CHAIN_KEY` (Postgres respalda el `AuditChain`
    en memoria, mismo patrón que `tribu-spark-firma/persistent_audit_chain.py`, sin importar
    ese módulo); sin configurar, `NullAuditLog` — la traza es opcional, no una dependencia dura.
  - `tribu-guardrails` — **Integrado** para dos usos concretos: `render_untrusted_as_data`
    (`tool_poisoning`) envuelve cada cita de `munistgo.cl` antes de mandarla al NIM de chat
    (`rag.py`); `check_lethal_trifecta` corre en `lifespan` contra el manifiesto real de
    ChatRAG (datos con ACL + contenido no confiable, sin comunicación externa autónoma → pasa
    sin mitigación declarada). El resto del paquete (contención de agentes, HITL, webauthn) no
    aplica: ChatRAG no ejecuta acciones, solo redacta texto anclado en citas.
  - `tribu-datagov` — existe en el SDK; evaluado para el filtrado de ACL (`rag.py:
    filter_by_acl`) y descartado como reemplazo — "reduce" pero no elimina la necesidad del
    filtro manual, que se mantiene como defensa en profundidad.
  - `tribu-voice` — **Integrado** (`voice.py`): síntesis TTS + avatar/marca + token efímero,
    todo real y auditado en el SDK — API confirmada leyendo el código fuente real
    (`~/repositorio/tribu-sdk/python/tribu-voice/`), no el corpus de x9 (se rehusó tres veces
    por falta de referencia). Revisión legal NVIDIA (Product-Specific Terms §C.1.1/§C.1.2)
    confirmada por Javier el 15-sep-2026 (el propio README del módulo decía "pendiente firma de
    abogado" en ese momento; el documento firmado vive fuera de este repo). Eso **no** cambia la
    regla dura, que es estructural en `tribu_voice`, no una config: solo voces **stock** del
    catálogo, nunca clonación; nunca se infiere la emoción del usuario a partir de su audio (el
    reconocimiento de voz es un cliente propio de ChatRAG, `RivaAsrClient`, que solo transcribe
    texto — ASR no es parte de `tribu-voice`). Contrato de red con el NIM Riva real **sin
    verificar** — no hay ninguna imagen NIM de Riva pineada en el SDK; ver docstring de
    `voice.py`.
  - `tribu-demo-kit` — existe (Parcial en v1.0.0, plantilla ARM64 sin verificar), no integrado.

## Reglas propias (además de las del SDK)

- **Citas o abstención**: toda respuesta va con procedencia (`source_uri`); si tras el filtrado
  por ACL no queda base accesible, el backend **se abstiene** en vez de inventar.
- **ACL de la fuente en el servidor**: el filtrado de qué puede ver el usuario ocurre en el
  backend (`rag.filter_by_acl`), nunca en el cliente.
- **Voz apagada por defecto** (`CHATRAG_VOICE_ENABLED`/`NEXT_PUBLIC_VOICE_ENABLED`, opt-in
  explícito por entorno) — la revisión legal ya está confirmada (ver arriba), pero la regla
  dura sigue: solo voces stock, nunca clonación, nunca inferir la emoción del usuario desde su
  audio. Eso no es negociable por configuración.
- **On-prem de verdad**: NIM embed/rerank/chat en la GPU del cliente; sin APIs cloud.
- **Dimensión de embedding 2048** — al integrar `tribu-rag`, revisar que el índice y el endpoint
  coincidan (el guard dinámico falla-cerrado si no).

## Legado

`legacy/elevenlabs-kb/` conserva el tooling del prototipo anterior (ElevenLabs). No se ejecuta;
la ingesta pasa a `tribu-rag`. Se elimina cuando esa ingesta esté cableada.

## Documentación de negocio

No se duplica aquí: vive en `01_PRODUCTOS/FORGE/40_CHATRAG/` (plan, mercado, VPack).
