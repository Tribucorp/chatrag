// Proxy genérico del BFF hacia `/admin/*` de chatrag-api. La llave es la sesión de tribu-auth
// con el rol de administración (`ADMIN_ROLE`): 401 sin sesión, 403 sin el rol. Con ella, el BFF
// añade el bearer de admin del backend (`CHATRAG_ADMIN_TOKEN`, variable o fichero de secretos de
// primer arranque, src/lib/secrets.ts) — quien administra no lo escribe ni lo ve. Cualquier
// `Authorization` que mande el navegador se descarta.
// El navegador nunca conoce `CHATRAG_API_URL` ni `CHATRAG_ADMIN_TOKEN` (ver .env.example).

import { NextResponse } from "next/server";

import { adminToken } from "@/lib/secrets";
import { getSessionIdentity } from "@/lib/session";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

async function proxy(request: Request, path: string[]): Promise<Response> {
  const identity = await getSessionIdentity(request.headers);
  if (!identity) return NextResponse.json({ detail: "falta sesión" }, { status: 401 });
  if (!identity.isAdmin) {
    return NextResponse.json({ detail: "requiere el rol de administración" }, { status: 403 });
  }

  // Se lee en cada petición: la build no ve el secreto, y en MarketplaceForge el fichero aparece
  // cuando la api termina de generarlo en su primer arranque.
  const token = adminToken();
  if (!token) {
    return NextResponse.json(
      { detail: "el frontend no tiene CHATRAG_ADMIN_TOKEN configurado" },
      { status: 503 }
    );
  }

  const search = new URL(request.url).search;
  const upstreamUrl = `${API_URL}/admin/${path.join("/")}${search}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };

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
