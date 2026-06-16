/**
 * Crea (o actualiza) el agente de voz "Chile" en ElevenLabs Conversational AI.
 *
 * - Si NEXT_PUBLIC_ELEVENLABS_AGENT_ID está vacío -> crea uno nuevo y escribe
 *   su id en el archivo .env.
 * - Si ya existe -> hace PATCH para actualizar prompt / voz / RAG.
 *
 *   npm run agent:create
 */
import "dotenv/config";
import { readFileSync, writeFileSync, existsSync } from "fs";
import { join } from "path";

const API_KEY = process.env.ELEVENLABS_API_KEY ?? "";
const EXISTING_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID?.trim() || "";
const ENV_PATH = join(process.cwd(), ".env");

if (!API_KEY) {
  console.error("Falta ELEVENLABS_API_KEY en .env");
  process.exit(1);
}

const SYSTEM_PROMPT = `Eres "Chile", un asistente de voz experto y entusiasta sobre el país de Chile.
Conversas de forma natural, cercana y amena sobre todo lo relacionado con Chile:

1. Geografía: regiones, clima, cordillera, desierto de Atacama, Patagonia, costa.
2. Historia: pueblos originarios, independencia, siglo XX, Chile actual.
3. Cultura: literatura (Mistral, Neruda), música, cueca, fiestas patrias.
4. Gastronomía: empanadas, cazuela, pastel de choclo, vinos, pisco.
5. Economía y turismo: cobre, litio, astronomía, destinos imperdibles.
6. Curiosidades y datos del país.

REGLAS:
- Responde SIEMPRE en español de forma conversacional, como en una charla hablada.
- Sé cálido, cercano y usa un toque del carácter chileno cuando encaje, sin exagerar.
- Da respuestas concisas (2-4 frases) salvo que pidan profundizar; es una conversación por voz.
- Apóyate en la base de conocimiento (RAG) para datos concretos; si no sabes algo,
  dilo con honestidad y ofrece lo que sí sabes.
- No inventes cifras. Si no estás seguro, acláralo.
- Mantén la conversación centrada en Chile; si preguntan otra cosa, reconduce con simpatía.`;

const conversationConfig = {
  agent: {
    first_message:
      "¡Hola! Soy tu asistente de voz sobre Chile. Pregúntame lo que quieras: su geografía, historia, cultura, comida o cualquier curiosidad. ¿Por dónde partimos?",
    language: "es",
    prompt: {
      prompt: SYSTEM_PROMPT,
      llm: "gemini-2.5-flash",
      temperature: 0.4,
      rag: {
        enabled: true,
        embedding_model: "e5_mistral_7b_instruct",
        max_vector_distance: 0.7,
        max_documents_length: 50000,
        max_retrieved_rag_chunks_count: 20,
      },
    },
  },
  tts: {
    model_id: "eleven_flash_v2_5",
    // Voz en español (la misma usada en el proyecto socios). Cámbiala en el
    // dashboard si prefieres otra voz/acento.
    voice_id: "cjVigY5qzO86Huf0OWal",
    stability: 0.6,
    speed: 1.0,
    similarity_boost: 0.8,
  },
};

function writeAgentIdToEnv(id: string) {
  if (!existsSync(ENV_PATH)) return;
  const raw = readFileSync(ENV_PATH, "utf8");
  const line = `NEXT_PUBLIC_ELEVENLABS_AGENT_ID=${id}`;
  const next = /NEXT_PUBLIC_ELEVENLABS_AGENT_ID=.*/.test(raw)
    ? raw.replace(/NEXT_PUBLIC_ELEVENLABS_AGENT_ID=.*/, line)
    : raw.trimEnd() + "\n" + line + "\n";
  writeFileSync(ENV_PATH, next);
  console.log(`  → Escrito en .env: ${line}`);
}

async function main() {
  if (EXISTING_ID) {
    console.log(`Actualizando agente existente ${EXISTING_ID}...`);
    const res = await fetch(
      `https://api.elevenlabs.io/v1/convai/agents/${EXISTING_ID}`,
      {
        method: "PATCH",
        headers: {
          "xi-api-key": API_KEY,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: "Chile - Asistente de Voz",
          conversation_config: conversationConfig,
        }),
      }
    );
    const data = await res.json();
    if (!res.ok) {
      console.error("Error:", JSON.stringify(data, null, 2));
      process.exit(1);
    }
    console.log("Agente actualizado correctamente ✓");
    return;
  }

  console.log("Creando nuevo agente 'Chile'...");
  const res = await fetch("https://api.elevenlabs.io/v1/convai/agents/create", {
    method: "POST",
    headers: {
      "xi-api-key": API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: "Chile - Asistente de Voz",
      conversation_config: conversationConfig,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    console.error("Error:", JSON.stringify(data, null, 2));
    process.exit(1);
  }
  const agentId = data.agent_id;
  console.log(`Agente creado ✓  agent_id = ${agentId}`);
  writeAgentIdToEnv(agentId);
  console.log("\nAhora sube la base de conocimiento:  npm run kb:upload");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
