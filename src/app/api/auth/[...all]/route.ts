import { toNextJsHandler } from "better-auth/next-js";

import { auth } from "@/lib/auth";
import { ensureAuthReady } from "@/lib/auth-ready";
import { isSameOrigin } from "@/lib/same-origin";

// Endpoints de tribu-auth (better-auth): /api/auth/sign-in/email, /sign-up/email, /sign-out…
// Antes de servir cualquiera: tablas creadas (BD persistente) y, si `CHATRAG_AUTH_DEMO_SEED=1`,
// las cuentas demo.
const handler = toNextJsHandler(auth);

const forbidden = () => Response.json({ message: "origen no permitido" }, { status: 403 });

export async function GET(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return forbidden();
  await ensureAuthReady();
  return handler.GET(request);
}

export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return forbidden();
  await ensureAuthReady();
  return handler.POST(request);
}
