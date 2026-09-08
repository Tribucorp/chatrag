import { NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { DEMO_ORG_SLUG } from "@/lib/seed-demo";
import { rolesToAcls } from "@/lib/acl";

/**
 * BFF entre el navegador y `chatrag-api`: el navegador ya NO llama al backend directamente
 * (no hay `NEXT_PUBLIC_CHATRAG_API_URL` en el cliente). Esta ruta valida la sesión real
 * (tribu-auth/better-auth), resuelve el rol del usuario en la organización del demo y traduce
 * eso a `X-User-Id`/`X-User-Acls` — las mismas cabeceras que `current_user()` del backend ya
 * esperaba (antes solo alcanzables vía `CHATRAG_DEV_IDENTITY_BYPASS`).
 */
export async function POST(request: Request): Promise<Response> {
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) {
    return NextResponse.json({ detail: "falta sesión" }, { status: 401 });
  }

  // Resuelve el rol del usuario en la organización única del demo. Si no es miembro (p.ej. un
  // vecino recién registrado que nunca se unió), no es un error — simplemente no tiene ACLs
  // extra y solo verá citas públicas, igual que el backend ya trata cualquier ACL desconocida.
  let role: string | null = null;
  try {
    await auth.api.setActiveOrganization({
      headers: request.headers,
      body: { organizationSlug: DEMO_ORG_SLUG },
    });
    const activeRole = await auth.api.getActiveMemberRole({ headers: request.headers });
    role = activeRole.role;
  } catch {
    role = null;
  }

  const body = await request.json();
  const apiUrl = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

  const backendRes = await fetch(`${apiUrl}/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": session.user.id,
      "X-User-Acls": rolesToAcls(role).join(","),
    },
    body: JSON.stringify(body),
  });

  const data = await backendRes.json();
  return NextResponse.json(data, { status: backendRes.status });
}
