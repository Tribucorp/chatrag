// BFF hacia `POST /voice/session` de chatrag-api — mismo patrón que /api/chat/route.ts: el
// navegador nunca conoce CHATRAG_API_URL ni el bearer de servicio, solo este route.

import { NextResponse } from "next/server";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";
const SERVICE_BEARER_TOKEN = process.env.CHATRAG_SERVICE_BEARER_TOKEN;

export async function POST(): Promise<Response> {
  const headers: Record<string, string> = {};
  if (SERVICE_BEARER_TOKEN) headers.Authorization = `Bearer ${SERVICE_BEARER_TOKEN}`;

  const upstream = await fetch(`${API_URL}/voice/session`, { method: "POST", headers });
  const data: unknown = await upstream.json().catch(() => null);
  return NextResponse.json(data, { status: upstream.status });
}
