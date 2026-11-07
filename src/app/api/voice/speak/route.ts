// BFF hacia `POST /voice/speak` de chatrag-api — recibe {token_id, text, emotion} del
// navegador y reenvía tal cual (el token_id ya lo mintió /api/voice/session, no es un secreto
// del servidor); devuelve el audio (audio/wav) directo, sin pasar por JSON.

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";
const SERVICE_BEARER_TOKEN = process.env.CHATRAG_SERVICE_BEARER_TOKEN;

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (SERVICE_BEARER_TOKEN) headers.Authorization = `Bearer ${SERVICE_BEARER_TOKEN}`;

  const upstream = await fetch(`${API_URL}/voice/speak`, { method: "POST", headers, body });
  if (!upstream.ok) {
    const data: unknown = await upstream.json().catch(() => null);
    return Response.json(data, { status: upstream.status });
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "audio/wav" },
  });
}
