/**
 * Sube los documentos de la carpeta /knowledge a la base de conocimiento (RAG)
 * del agente de Chile en ElevenLabs.
 *
 *   npm run kb:upload
 */
import "dotenv/config";
import { readFileSync, readdirSync, statSync } from "fs";
import { join, basename, extname } from "path";

const API_KEY = process.env.ELEVENLABS_API_KEY ?? "";
const AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID?.trim() || "";
const KB_DIR = join(process.cwd(), "knowledge");
const EXTS = [".md", ".txt"];

if (!API_KEY) {
  console.error("Falta ELEVENLABS_API_KEY en .env");
  process.exit(1);
}
if (!AGENT_ID) {
  console.error(
    "Falta NEXT_PUBLIC_ELEVENLABS_AGENT_ID. Ejecuta antes:  npm run agent:create"
  );
  process.exit(1);
}

function getAllFiles(dir: string, exts: string[]): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === ".DS_Store") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) files.push(...getAllFiles(full, exts));
    else if (exts.includes(extname(full).toLowerCase())) files.push(full);
  }
  return files;
}

type KbEntry = { type: "file"; name: string; id: string; usage_mode: "auto" };

/** Sube un documento a la KB de la cuenta y devuelve su id. */
async function uploadFile(content: Buffer, name: string): Promise<string | null> {
  const formData = new FormData();
  formData.append("file", new Blob([content], { type: "text/plain" }), name);

  const res = await fetch(
    `https://api.elevenlabs.io/v1/convai/agents/${AGENT_ID}/add-to-knowledge-base`,
    {
      method: "POST",
      headers: { "xi-api-key": API_KEY },
      body: formData,
    }
  );
  if (!res.ok) {
    const err = await res.text();
    console.error(`  FAIL ${name}: ${err.substring(0, 120)}`);
    return null;
  }
  const data = await res.json().catch(() => ({}));
  console.log(`  ✓ ${name}`);
  // La API devuelve el id como `id` o `document_id` según versión.
  return data.id ?? data.document_id ?? null;
}

/**
 * Vincula los documentos al prompt del agente. Subir a la KB de la cuenta ya
 * NO los adjunta automáticamente: hay que enlazarlos con un PATCH para que el
 * RAG los utilice.
 */
async function attachToAgent(entries: KbEntry[]): Promise<boolean> {
  const res = await fetch(
    `https://api.elevenlabs.io/v1/convai/agents/${AGENT_ID}`,
    {
      method: "PATCH",
      headers: { "xi-api-key": API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_config: { agent: { prompt: { knowledge_base: entries } } },
      }),
    }
  );
  if (!res.ok) {
    console.error("  FAIL al vincular:", (await res.text()).substring(0, 160));
    return false;
  }
  return true;
}

async function main() {
  const files = getAllFiles(KB_DIR, EXTS);
  console.log(`Subiendo ${files.length} documentos a la KB del agente ${AGENT_ID}...`);

  const entries: KbEntry[] = [];
  for (const f of files) {
    // Sube los .md como .txt (texto plano)
    const txtName = basename(f, extname(f)) + ".txt";
    const id = await uploadFile(readFileSync(f), txtName);
    if (id) entries.push({ type: "file", name: txtName, id, usage_mode: "auto" });
    await new Promise((r) => setTimeout(r, 500));
  }

  console.log(`\n${entries.length}/${files.length} subidos. Vinculando al agente...`);
  const linked = await attachToAgent(entries);

  if (linked) {
    console.log(`Listo ✓  ${entries.length} documentos vinculados al RAG del agente.`);
    console.log("El RAG se indexa en segundo plano; en unos segundos podrá citarlos.");
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
