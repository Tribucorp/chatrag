# ChatRAG 🇨🇱

**ChatRAG** es un asistente de voz conversacional con RAG, de **Tribucorp**.
Este repo contiene el caso de uso desplegado para la **comuna de Santiago de
Chile** (Ilustre Municipalidad de Santiago — [munistgo.cl](https://www.munistgo.cl/)),
con una interfaz limpia tipo orbe. Hablas con él y te ayuda con **trámites,
servicios municipales, direcciones del municipio, el alcalde** e información del
sitio. Cuando un trámite tiene una página, **te pasa el enlace directo** como
tarjeta clickeable.

Misma arquitectura que el proyecto *socios* (partner-portal): **ElevenLabs
Conversational AI** gestionado (agente + RAG en el dashboard) con un front
Next.js que conecta la voz en tiempo real por WebSocket.

> **En producción:** https://asistente-voz-chile.vercel.app

```
Navegador (Next.js)  ──websocket──►  ElevenLabs Conversational AI Agent
  src/components/voice-agent.tsx          ├─ System prompt (comuna de Santiago, ámbito restringido)
        │                                 ├─ Knowledge Base / RAG (~142 docs)
        │                                 │     ├─ 139 páginas de munistgo.cl
        │                                 │     ├─ Wikipedia: comuna de Santiago + Mario Desbordes
        │                                 │     └─ Pago de multas/TAG → tramites.munistgo.cl/pagotag
        │                                 ├─ Tool "mostrar_enlace" (enlaces de trámites)
        │                                 └─ TTS + STT + manejo de turnos
        └──◄ tool call: mostrar_enlace(url, titulo) ──┘   → tarjeta clickeable en la UI
```

## Qué hace

- 🎙️ **Voz conversacional en tiempo real** (STT + TTS + turnos los gestiona ElevenLabs).
- 🏛️ **Ámbito municipal estricto**: solo responde sobre la comuna de Santiago,
  su alcalde y temas del sitio; declina amablemente lo que esté fuera.
- 📚 **RAG sobre munistgo.cl**: ~142 documentos indexados (páginas del sitio +
  Wikipedia de la comuna y del alcalde + pago de multas).
- 🔗 **Enlaces de trámites**: el agente llama a la herramienta `mostrar_enlace`
  y el front muestra una **tarjeta clickeable** con el enlace directo
  (p. ej. pago de multas/TAG → `https://tramites.munistgo.cl/pagotag/`).
- 📝 **Transcripción en vivo** de la conversación.

## Stack

- **Next.js 16** (App Router) + React 19 + Tailwind v4
- **@11labs/client** para la conversación de voz
- **ElevenLabs Conversational AI** para agente, RAG, voz, transcripción y tools
- Desplegado en **Vercel** (team Tribucorp)

## Puesta en marcha

```bash
npm install

# 1. Crea/actualiza el agente municipal en ElevenLabs (escribe el agent_id en .env)
npm run agent:create        # crear nuevo  |  agent:update si ya existe

# 2. (Opcional) Sube la base de conocimiento base (carpeta /knowledge)
npm run kb:upload

# 3. Rastrea munistgo.cl e ingiere páginas de servicios/trámites al RAG
npm run kb:crawl            # SITE_MAX=140 por defecto

# 4. Arranca el front
npm run dev                 # http://localhost:3000
```

> La `ELEVENLABS_API_KEY` se reutiliza de la cuenta del proyecto *socios*
> (en `.env`, **no** versionado). El agente municipal es **independiente** del
> agente X9 de socios.

## Configuración del agente (estado actual)

| Campo | Valor |
|-------|-------|
| Agente | `agent_4601kv6z80g6f758mp1ppxhqawhq` ("Comuna de Santiago - Asistente de Voz") |
| LLM | `gemini-2.5-flash` · idioma `es` · RAG activado |
| Voz (TTS) | `rBqbBncz61jpuaOTI1GW` (Juan Manuel – conversacional, español LatAm) |
| Tool | `mostrar_enlace` (`tool_2401kv725wx1f70v4c5d6jvzp1qv`) |
| RAG | ~142 docs (`usage_mode: auto`, embeddings `e5_mistral_7b_instruct`) |

## Estructura

```
src/
  app/
    page.tsx              Interfaz limpia (orbe + intro municipal)
    layout.tsx            Metadatos + fondo aurora
    globals.css           Estilos del orbe y animaciones
  components/
    voice-agent.tsx       Lógica de voz + clientTools (mostrar_enlace) + tarjetas de enlace
scripts/
  create-agent.ts         Crea/actualiza el agente (prompt municipal, voz, RAG, tool)
  upload-kb.ts            Sube /knowledge/*.md a la KB y los vincula
  crawl-site-to-kb.ts     Rastrea el sitemap de un sitio e ingiere sus páginas al RAG
knowledge/                Docs base opcionales (markdown)
```

## Cómo se construyó (resumen del proyecto)

1. **Scaffold** Next.js 16 + interfaz de voz limpia (orbe animado, transcripción).
2. **Agente ElevenLabs** creado por API con RAG + voz en español (sin tocar socios).
3. **Voz** ajustada a una conversacional neutra latinoamericana.
4. **Reenfoque municipal**: identidad y ámbito restringidos a la comuna de Santiago;
   se retiraron los documentos generales de Chile.
5. **RAG del sitio**: `crawl-site-to-kb.ts` descubre URLs por el `wp-sitemap.xml`,
   filtra servicios/trámites (descarta noticias datadas), ingiere, vincula e indexa.
6. **Herramienta de enlaces**: `mostrar_enlace` registrada en el agente +
   implementada en el front como tarjetas clickeables.
7. **Enlaces específicos**: docs de texto que mapean un trámite a su URL
   (ej. pago de multas/TAG).
8. **Deploy** en Vercel (team Tribucorp) + repo en GitHub `Tribucorp/chatrag`.

## Personalizar

- **Más páginas del sitio al RAG:** `SITE_MAX=300 npm run kb:crawl`
  (o `SITEMAP=https://otro-sitio.cl/wp-sitemap.xml npm run kb:crawl`).
- **Añadir un enlace de trámite concreto:** crea un documento de texto en la KB
  que mapee el trámite a su URL, vincúlalo al agente e indéxalo (ver el patrón
  de "pago de multas").
- **Prompt / voz / identidad:** edita `scripts/create-agent.ts` y corre
  `npm run agent:update`.
- Los cambios de agente/RAG son **server-side** (no requieren redeploy del front).
  Cambios de front: `vercel deploy --prod --yes --scope tribucorp`.

## Notas

- "Toda la web" de munistgo.cl son ~6.956 URLs (mayormente noticias antiguas);
  el crawler ingiere el subconjunto evergreen de servicios/trámites para mantener
  el RAG útil y dentro de los límites de la cuenta. El tope y los filtros son
  configurables.
- La conexión automática GitHub↔Vercel requiere instalar la app de Vercel en la
  organización **Tribucorp** de GitHub (paso manual de una vez). Mientras tanto,
  el deploy se hace por CLI.
