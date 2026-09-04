/**
 * Rastrea un sitio web (vía su sitemap) e ingiere sus páginas en la base de
 * conocimiento (RAG) del agente de ElevenLabs, vinculándolas e indexándolas.
 *
 * Pensado para webs municipales / institucionales: prioriza páginas
 * evergreen (servicios, direcciones, trámites) y descarta noticias datadas.
 *
 *   npm run kb:crawl                  # usa los valores por defecto (munistgo.cl)
 *   SITE_MAX=80 npm run kb:crawl      # limita cuántas páginas ingerir
 *   SITEMAP=https://otra.cl/wp-sitemap.xml npm run kb:crawl
 *
 * Variables:
 *   SITEMAP    URL del sitemap índice (def: munistgo wp-sitemap.xml)
 *   SITE_MAX   máximo de páginas a ingerir esta corrida (def: 150)
 *   PREFIX     prefijo del nombre de los docs para deduplicar (def: munistgo)
 */
import "dotenv/config";

const API_KEY = process.env.ELEVENLABS_API_KEY ?? "";
const AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID?.trim() || "";
const SITEMAP =
  process.env.SITEMAP ?? "https://www.munistgo.cl/wp-sitemap.xml";
const MAX = parseInt(process.env.SITE_MAX ?? "150", 10);
const PREFIX = process.env.PREFIX ?? "munistgo";
const UA = "Mozilla/5.0 (compatible; AsistenteChileBot/1.0)";

if (!API_KEY || !AGENT_ID) {
  console.error("Faltan ELEVENLABS_API_KEY o NEXT_PUBLIC_ELEVENLABS_AGENT_ID");
  process.exit(1);
}

// Slugs que indican contenido datado / noticia / evento (se descartan)
const EXCLUDE = /(19|20)\d{2}|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|navidad|fonda|verano|invierno|primavera|saludo|aniversario|concierto|festival|cine|teatro-en|lollapalooza|formula-e|preview|-test|-demo|prueba|timeline|carrusel|galeria|fotos/i;

// Palabras que marcan contenido útil de servicio/trámite (prioridad alta)
const INCLUDE = /tramite|servicio|direccion-|permiso|patente|certificad|rentas|transito|obras|licencia|subsidio|beca|salud|seguridad|aseo|medioambiente|medio-ambiente|emprend|empleo|portal-laboral|notaria|juzgado|contacto|contactanos|organigrama|concejo|alcalde|cosoc|participacion|vecino|veci|mascota|adopta|veterinari|bibliotec|deporte|cultura|mujer|migrante|discapacidad|adulto|infancia|vivienda|arriendo|tarjeta|cementerio|matrimonio|registro/i;

async function getSitemapUrls(url: string): Promise<string[]> {
  const res = await fetch(url, { headers: { "User-Agent": UA } });
  const xml = await res.text();
  const locs = [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((m) => m[1].trim());
  // Si es un índice de sitemaps, baja un nivel (solo páginas y posts)
  if (locs.every((l) => l.includes("sitemap"))) {
    const subs = locs.filter((l) => /posts-(post|page)/.test(l));
    const all: string[] = [];
    for (const s of subs) all.push(...(await getSitemapUrls(s)));
    return all;
  }
  return locs;
}

function slug(u: string): string {
  return u.replace(/^https?:\/\/[^/]+\//, "/").replace(/\/$/, "") || "/";
}

async function createFromUrl(url: string, name: string): Promise<string | null> {
  const res = await fetch(
    "https://api.elevenlabs.io/v1/convai/knowledge-base/url",
    {
      method: "POST",
      headers: { "xi-api-key": API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ url, name }),
    }
  );
  if (!res.ok) {
    console.error(`  FAIL ${slug(url)}: ${(await res.text()).substring(0, 90)}`);
    return null;
  }
  const d = await res.json().catch(() => ({}));
  return d.id ?? d.document_id ?? null;
}

async function getAgentKb(): Promise<{ list: any[]; names: Set<string> }> {
  const res = await fetch(
    `https://api.elevenlabs.io/v1/convai/agents/${AGENT_ID}`,
    { headers: { "xi-api-key": API_KEY } }
  );
  const d = await res.json();
  const list = d.conversation_config.agent.prompt.knowledge_base ?? [];
  return { list, names: new Set(list.map((x: any) => x.name)) };
}

async function patchAgentKb(list: any[]): Promise<boolean> {
  const res = await fetch(
    `https://api.elevenlabs.io/v1/convai/agents/${AGENT_ID}`,
    {
      method: "PATCH",
      headers: { "xi-api-key": API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_config: { agent: { prompt: { knowledge_base: list } } },
      }),
    }
  );
  if (!res.ok) console.error("  PATCH falló:", (await res.text()).slice(0, 160));
  return res.ok;
}

async function ragIndex(id: string): Promise<void> {
  await fetch(
    `https://api.elevenlabs.io/v1/convai/knowledge-base/${id}/rag-index`,
    {
      method: "POST",
      headers: { "xi-api-key": API_KEY, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "e5_mistral_7b_instruct" }),
    }
  ).catch(() => {});
}

async function main() {
  console.log(`Leyendo sitemap: ${SITEMAP}`);
  const urls = await getSitemapUrls(SITEMAP);
  console.log(`URLs totales en sitemap: ${urls.length}`);

  // Filtra: incluir servicios/trámites, excluir noticias datadas
  const candidates = urls.filter((u) => {
    const s = slug(u);
    if (s === "/") return false;
    if (EXCLUDE.test(s)) return false;
    return INCLUDE.test(s);
  });
  console.log(`Candidatas (servicios/trámites evergreen): ${candidates.length}`);

  const { list, names } = await getAgentKb();
  console.log(`Docs ya en el agente: ${list.length}`);

  const toAdd = candidates
    .filter((u) => !names.has(`${PREFIX}: ${slug(u)}`))
    .slice(0, MAX);
  console.log(`A ingerir esta corrida (máx ${MAX}): ${toAdd.length}\n`);

  const newEntries: any[] = [];
  const newIds: string[] = [];
  for (const u of toAdd) {
    const name = `${PREFIX}: ${slug(u)}`;
    const id = await createFromUrl(u, name);
    if (id) {
      newEntries.push({ type: "url", name, id, usage_mode: "auto" });
      newIds.push(id);
      console.log(`  ✓ ${slug(u)}`);
    }
    await new Promise((r) => setTimeout(r, 400));
  }

  if (newEntries.length === 0) {
    console.log("\nNada nuevo que añadir.");
    return;
  }

  console.log(`\nVinculando ${newEntries.length} docs al agente...`);
  await patchAgentKb([...list, ...newEntries]);

  console.log("Disparando indexación RAG de cada doc...");
  for (const id of newIds) {
    await ragIndex(id);
    await new Promise((r) => setTimeout(r, 200));
  }

  console.log(
    `\nListo ✓  ${newEntries.length} páginas ingeridas. La indexación corre en` +
      ` segundo plano (puede tardar unos minutos en completar).`
  );
  console.log(
    `Total docs en el RAG del agente ahora: ${list.length + newEntries.length}`
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
