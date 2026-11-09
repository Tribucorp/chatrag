import { toNextJsHandler } from "better-auth/next-js";

import { auth } from "@/lib/auth";
import { ensureDemoSeed } from "@/lib/seed-demo";

// Endpoints de tribu-auth (better-auth): /api/auth/sign-in/email, /sign-up/email, /sign-out…
// Antes de servir cualquiera, siembra las cuentas demo si `CHATRAG_AUTH_DEMO_SEED=1`.
const handler = toNextJsHandler(auth);

export async function GET(request: Request): Promise<Response> {
  await ensureDemoSeed();
  return handler.GET(request);
}

export async function POST(request: Request): Promise<Response> {
  await ensureDemoSeed();
  return handler.POST(request);
}
