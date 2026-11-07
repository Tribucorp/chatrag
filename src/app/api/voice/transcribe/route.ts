// BFF hacia `POST /voice/transcribe` de chatrag-api — exige sesión de tribu-auth; reenvía el
// audio crudo del navegador (grabado con MediaRecorder) tal cual, con el token de voz en
// X-Voice-Token.

import { NextResponse } from "next/server";

import { backendHeaders, getSessionIdentity } from "@/lib/session";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

export async function POST(request: Request): Promise<Response> {
  const identity = await getSessionIdentity(request.headers);
  if (!identity) return NextResponse.json({ detail: "falta sesión" }, { status: 401 });

  const headers: Record<string, string> = {
    "Content-Type": request.headers.get("content-type") ?? "audio/webm",
    ...backendHeaders(identity),
  };
  const voiceToken = request.headers.get("x-voice-token");
  if (voiceToken) headers["X-Voice-Token"] = voiceToken;

  const upstream = await fetch(`${API_URL}/voice/transcribe`, {
    method: "POST",
    headers,
    body: await request.arrayBuffer(),
  });
  const data: unknown = await upstream.json().catch(() => null);
  return Response.json(data, { status: upstream.status });
}
