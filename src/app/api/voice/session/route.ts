// BFF hacia `POST /voice/session` de chatrag-api — mismo patrón que /api/chat/route.ts: exige
// sesión de tribu-auth (sin ella no se mintea token de voz), y el navegador nunca conoce
// CHATRAG_API_URL ni el bearer de servicio.

import { NextResponse } from "next/server";

import { backendHeaders, getSessionIdentity } from "@/lib/session";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

export async function POST(request: Request): Promise<Response> {
  const identity = await getSessionIdentity(request.headers);
  if (!identity) return NextResponse.json({ detail: "falta sesión" }, { status: 401 });

  const upstream = await fetch(`${API_URL}/voice/session`, {
    method: "POST",
    headers: backendHeaders(identity),
  });
  const data: unknown = await upstream.json().catch(() => null);
  return NextResponse.json(data, { status: upstream.status });
}
