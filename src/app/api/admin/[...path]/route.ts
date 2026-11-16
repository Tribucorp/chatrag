// Proxy genérico del BFF hacia `/admin/*` de chatrag-api. Dos llaves independientes:
// 1. sesión de tribu-auth con el rol de administración (`ADMIN_ROLE`) (se comprueba aquí: 401 sin sesión, 403 sin
//    el rol), y
// 2. el bearer de admin del backend (`CHATRAG_ADMIN_TOKEN`), que quien administra escribe en la
//    UI y este proxy reenvía tal cual — el BFF no lo conoce ni lo inventa.
// El navegador nunca conoce `CHATRAG_API_URL` (server-only, ver .env.example).

import { NextResponse } from "next/server";

import { getSessionIdentity } from "@/lib/session";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

async function proxy(request: Request, path: string[]): Promise<Response> {
  const identity = await getSessionIdentity(request.headers);
  if (!identity) return NextResponse.json({ detail: "falta sesión" }, { status: 401 });
  if (!identity.isAdmin) {
    return NextResponse.json({ detail: "requiere el rol de administración" }, { status: 403 });
  }

  const search = new URL(request.url).search;
  const upstreamUrl = `${API_URL}/admin/${path.join("/")}${search}`;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const authorization = request.headers.get("authorization");
  if (authorization) headers.Authorization = authorization;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : undefined,
  });

  const data: unknown = await upstream.json().catch(() => null);
  return NextResponse.json(data, { status: upstream.status });
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  return proxy(request, (await params).path);
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  return proxy(request, (await params).path);
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<Response> {
  return proxy(request, (await params).path);
}
