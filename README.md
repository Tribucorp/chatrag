# Asistente de Voz · Chile 🇨🇱

Demo de **agente de voz conversacional sobre Chile** con interfaz limpia.
Misma arquitectura que el proyecto *socios*: **ElevenLabs Conversational AI**
(agente + RAG gestionados) con un front Next.js que conecta la voz en tiempo
real vía WebSocket.

```
Navegador (Next.js)  ──websocket──►  ElevenLabs Conversational AI Agent
   src/components/voice-agent.tsx          ├─ System prompt (experto en Chile)
                                           ├─ Knowledge Base / RAG (carpeta /knowledge)
                                           └─ TTS + STT + manejo de turnos
```

## Stack
- **Next.js 16** (App Router) + React 19 + Tailwind v4
- **@11labs/client** para la conversación de voz
- **ElevenLabs Conversational AI** para agente, RAG, voz y transcripción

## Puesta en marcha

```bash
npm install

# 1. Crea el agente de Chile en ElevenLabs (escribe el agent_id en .env)
npm run agent:create

# 2. Sube la base de conocimiento (RAG) sobre Chile
npm run kb:upload

# 3. Arranca el front
npm run dev      # http://localhost:3000
```

> La `ELEVENLABS_API_KEY` ya está en `.env` (reutilizada del proyecto *socios*).
> El `agent:create` crea un **agente nuevo dedicado a Chile**, sin tocar el
> agente X9 de socios.

## Estructura
- `src/app/page.tsx` — interfaz limpia (orbe de voz + transcripción).
- `src/components/voice-agent.tsx` — lógica de la conversación de voz.
- `scripts/create-agent.ts` — crea/actualiza el agente y su prompt + RAG.
- `scripts/upload-kb.ts` — sube `/knowledge/*.md` a la base de conocimiento.
- `knowledge/` — documentos fuente del RAG (geografía, historia, cultura,
  gastronomía, economía/turismo, curiosidades). Edítalos y vuelve a correr
  `npm run kb:upload` para actualizar lo que el agente sabe.

## Personalizar
- **Prompt / voz / modelo:** edita `scripts/create-agent.ts` y corre
  `npm run agent:update`.
- **Conocimiento:** añade archivos a `knowledge/` y corre `npm run kb:upload`.
