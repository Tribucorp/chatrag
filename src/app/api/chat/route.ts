// BFF entre el navegador y `chatrag-api` (backend/src/chatrag_api). El navegador nunca habla
// directo con el backend ni declara su propia identidad: aquí se valida la sesión real de
// tribu-auth, se resuelve el rol del usuario y se adjuntan X-User-Id/X-User-Acls y el bearer de
// servicio (`CHATRAG_SERVICE_BEARER_TOKEN`, server-only) — ver src/lib/session.ts.
//
// `CHATRAG_API_URL` es server-only (a diferencia de la antigua `NEXT_PUBLIC_CHATRAG_API_URL`,
// que exponía la URL del backend al navegador) — ver .env.example.

import { NextResponse } from "next/server";

import { backendHeaders, getSessionIdentity } from "@/lib/session";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

export async function POST(request: Request): Promise<Response> {
  const identity = await getSessionIdentity(request.headers);
  if (!identity) {
    return NextResponse.json({ detail: "falta sesión" }, { status: 401 });
  }

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

  const upstream = await fetch(`${API_URL}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...backendHeaders(identity) },
    body: JSON.stringify({ question }),
  });

  const data: unknown = await upstream.json().catch(() => null);
  return NextResponse.json(data, { status: upstream.status });
}
