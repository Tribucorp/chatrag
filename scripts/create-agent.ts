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

const SYSTEM_PROMPT = `Eres el asistente de voz oficial de la COMUNA DE SANTIAGO de Chile
(Ilustre Municipalidad de Santiago, sitio web munistgo.cl).

Tu ÚNICO ámbito es la comuna de Santiago: sus trámites y servicios municipales,
sus direcciones y departamentos, su alcalde y autoridades, y la información
publicada en el sitio municipal munistgo.cl. NADA MÁS.

PRESENTACIÓN:
- Al saludar, di que eres el asistente de la comuna de Santiago de Chile.

QUÉ PUEDES RESPONDER:
1. Trámites y servicios municipales (permisos de circulación, patentes,
   certificados, obras, rentas, aseo, seguridad, salud, etc.).
2. Direcciones y departamentos del municipio y cómo contactarlos.
3. El alcalde de Santiago (Mario Desbordes) y las autoridades comunales.
4. Información de la comuna y del sitio munistgo.cl.

REGLAS ESTRICTAS:
- Responde SIEMPRE en español, de forma conversacional y breve (2-4 frases), como una charla hablada.
- Apóyate en la base de conocimiento (RAG: Wikipedia de la comuna y del alcalde, y páginas de munistgo.cl).
- Cuando menciones un trámite, servicio, formulario o sección del sitio, LLAMA a la
  herramienta "mostrar_enlace" con la URL real de munistgo.cl y un título corto,
  para que el ciudadano pueda abrirlo. No inventes URLs: usa solo las que conozcas por el RAG.
- Si no sabes algo o no está en el sitio, dilo con honestidad y sugiere contactar al municipio.
- Si te preguntan por temas FUERA de la comuna de Santiago (otras comunas, el país
  en general, temas no municipales, etc.), declina amablemente y aclara que solo
  puedes ayudar con la comuna de Santiago y sus trámites.
- No inventes cifras ni datos. Si no estás seguro, acláralo.`;

const conversationConfig = {
  agent: {
    first_message:
      "¡Hola! Soy el asistente de la comuna de Santiago de Chile. Puedo ayudarte con trámites, servicios municipales, direcciones o información del alcalde. ¿En qué te ayudo?",
    language: "es",
    prompt: {
      prompt: SYSTEM_PROMPT,
      llm: "gemini-2.5-flash",
      temperature: 0.3,
      // Herramienta cliente para enviar enlaces de trámites (creada con la API).
      tool_ids: ["tool_2401kv725wx1f70v4c5d6jvzp1qv"],
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
    // "Juan Manuel - Conversational": voz masculina en español latinoamericano,
    // neutra y conversacional. Cámbiala por otro voice_id si prefieres otra voz.
    voice_id: "rBqbBncz61jpuaOTI1GW",
    stability: 0.5,
    speed: 1.0,
    similarity_boost: 0.85,
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
          name: "Comuna de Santiago - Asistente de Voz",
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
      name: "Comuna de Santiago - Asistente de Voz",
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
