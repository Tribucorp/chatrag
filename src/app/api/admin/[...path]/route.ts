// Proxy genérico del BFF hacia `/admin/*` de chatrag-api. A diferencia de `/api/chat/route.ts`,
// este NO adjunta ningún secreto propio: reenvía tal cual el `Authorization` que ya trae la
// petición del navegador — quien administra el panel escribe el bearer de admin
// (`CHATRAG_ADMIN_TOKEN` del backend) en la UI, el BFF solo evita que el navegador tenga que
// conocer `CHATRAG_API_URL` directamente (sigue siendo server-only, ver .env.example).

import { NextResponse } from "next/server";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

async function proxy(request: Request, path: string[]): Promise<Response> {
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
