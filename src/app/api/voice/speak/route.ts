// BFF hacia `POST /voice/speak` de chatrag-api — exige sesión de tribu-auth; recibe
// {token_id, text, emotion} del navegador y reenvía tal cual (el token_id ya lo mintió
// /api/voice/session, no es un secreto del servidor); devuelve el audio (audio/wav) directo.

import { NextResponse } from "next/server";

import { backendHeaders, getSessionIdentity } from "@/lib/session";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

export async function POST(request: Request): Promise<Response> {
  const identity = await getSessionIdentity(request.headers);
  if (!identity) return NextResponse.json({ detail: "falta sesión" }, { status: 401 });

  const upstream = await fetch(`${API_URL}/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...backendHeaders(identity) },
    body: await request.text(),
  });
  if (!upstream.ok) {
    const data: unknown = await upstream.json().catch(() => null);
    return Response.json(data, { status: upstream.status });
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "audio/wav" },
  });
}
