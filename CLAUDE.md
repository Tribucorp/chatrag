# CLAUDE.md — ChatRAG (piloto de adopción del Tribu SDK)

> Constitución del repo. Si algo contradice este documento, gana este documento (y se discute
> con Javier). **La constitución de la plataforma es el Tribu SDK**
> (`~/repositorio/tribu-sdk/CLAUDE.md`); este documento solo añade lo específico del producto.

## Qué es

Asistente RAG de la comuna de Santiago (Chile): responde sobre trámites y servicios municipales
con **citas verificables**, sobre el corpus de `munistgo.cl`. Es el **piloto nº1 de adopción del
Tribu SDK** — su feedback define la DX del SDK.

## Arquitectura

- **Frontend** (`src/`): Next.js 16 + React 19. Chat de texto contra el backend; muestra las
  citas con su fuente. **Sin proveedores cloud de voz** (se retiró ElevenLabs).
- **Backend** (`backend/`): FastAPI (`chatrag-api`) que consume los módulos del SDK como
  **wheels del registry privado** (nunca vendorizar ni copiar código del SDK):
  - `tribu-rag` — recuperación híbrida (dimensión **2048**, guard dinámico), pre-filtrado por
    tenant, Contextual Retrieval.
  - `tribu-http` — cliente único, **egress deny-by-default** hacia los NIM on-prem.
  - `tribu-auth` — SSO; produce el `UserContext` (identidad + ACLs) que valida el servidor.
  - `tribu-observability` — trazas de decisión, Prometheus.
  - `tribu-voice` — **STUB APAGADO** (bloqueo legal NVIDIA; Riva stock, jamás clonación).
  - `tribu-demo-kit` — plantilla de demo.

## Reglas propias (además de las del SDK)

- **Citas o abstención**: toda respuesta va con procedencia (`source_uri`); si tras el filtrado
  por ACL no queda base accesible, el backend **se abstiene** en vez de inventar.
- **ACL de la fuente en el servidor**: el filtrado de qué puede ver el usuario ocurre en el
  backend (`rag.filter_by_acl`), nunca en el cliente.
- **Voz apagada por defecto** (`CHATRAG_VOICE_ENABLED`/`NEXT_PUBLIC_VOICE_ENABLED`): no se sirve
  voz hasta que pase la revisión legal de `tribu-voice`.
- **On-prem de verdad**: NIM embed/rerank/chat en la GPU del cliente; sin APIs cloud.
- **Dimensión de embedding 2048** — al integrar `tribu-rag`, revisar que el índice y el endpoint
  coincidan (el guard dinámico falla-cerrado si no).

## Legado

`legacy/elevenlabs-kb/` conserva el tooling del prototipo anterior (ElevenLabs). No se ejecuta;
la ingesta pasa a `tribu-rag`. Se elimina cuando esa ingesta esté cableada.

## Documentación de negocio

No se duplica aquí: vive en `01_PRODUCTOS/FORGE/40_CHATRAG/` (plan, mercado, VPack).
