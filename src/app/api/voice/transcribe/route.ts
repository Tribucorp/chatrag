// BFF hacia `POST /voice/transcribe` de chatrag-api — reenvía el audio crudo del navegador
// (grabado con MediaRecorder) tal cual, con el token de voz en X-Voice-Token.

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";
const SERVICE_BEARER_TOKEN = process.env.CHATRAG_SERVICE_BEARER_TOKEN;

export async function POST(request: Request): Promise<Response> {
  const audio = await request.arrayBuffer();
  const voiceToken = request.headers.get("x-voice-token");
  const contentType = request.headers.get("content-type") ?? "audio/webm";

  const headers: Record<string, string> = { "Content-Type": contentType };
  if (voiceToken) headers["X-Voice-Token"] = voiceToken;
  if (SERVICE_BEARER_TOKEN) headers.Authorization = `Bearer ${SERVICE_BEARER_TOKEN}`;

  const upstream = await fetch(`${API_URL}/voice/transcribe`, {
    method: "POST",
    headers,
    body: audio,
  });
  const data: unknown = await upstream.json().catch(() => null);
  return Response.json(data, { status: upstream.status });
}
