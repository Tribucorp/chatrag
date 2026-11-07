// BFF entre el navegador y `chatrag-api` (backend/src/chatrag_api). El navegador ya NO habla
// directo con el backend (ver `chat-agent.tsx`): aquí es donde se adjunta el bearer de
// servicio (`CHATRAG_SERVICE_BEARER_TOKEN`, server-only) y la identidad real de la sesión —
// nunca la declara el cliente. Sin sesión, no se manda X-User-Id/X-User-Acls: el backend ya
// falla-cerrado en ese caso (`current_user` en app.py), así que este route no necesita
// replicar esa lógica, solo no inventar una identidad que no tiene.
//
// `CHATRAG_API_URL` es server-only (a diferencia de la antigua `NEXT_PUBLIC_CHATRAG_API_URL`,
// que exponía la URL del backend al navegador) — ver .env.example.

import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";
const SERVICE_BEARER_TOKEN = process.env.CHATRAG_SERVICE_BEARER_TOKEN;

export async function POST(request: Request): Promise<Response> {
  let question: string;
  try {
    const body = (await request.json()) as { question?: unknown };
    if (typeof body.question !== "string" || body.question.trim() === "") {
      return NextResponse.json({ detail: "falta 'question'" }, { status: 400 });
    }
    question = body.question;
  } catch {
    return NextResponse.json({ detail: "cuerpo inválido" }, { status: 400 });
  }

  const session = await auth();

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (SERVICE_BEARER_TOKEN) {
    headers.Authorization = `Bearer ${SERVICE_BEARER_TOKEN}`;
  }
  if (session?.user?.id) {
    headers["X-User-Id"] = session.user.id;
    headers["X-User-Acls"] = (session.user.acls ?? []).join(",");
  }

  const upstream = await fetch(`${API_URL}/query`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question }),
  });

  const data: unknown = await upstream.json().catch(() => null);
  return NextResponse.json(data, { status: upstream.status });
}
