import "server-only";

import { auth } from "./auth";
import { isAdminRole, rolesToAcls } from "./acl";
import { DEMO_ORG_SLUG } from "./seed-demo";

export type SessionIdentity = {
  userId: string;
  email: string;
  role: string | null;
  acls: string[];
  isAdmin: boolean;
};

/**
 * Identidad real de la petición para el BFF: sesión de tribu-auth + rol del usuario en la
 * organización de ChatRAG, traducido a ACLs. `null` sin sesión — quien llama responde 401.
 *
 * No ser miembro de la organización (un cliente recién registrado) no es un error: no tiene
 * ACLs extra y solo verá citas públicas, igual que el backend trata cualquier ACL desconocida.
 */
export async function getSessionIdentity(headers: Headers): Promise<SessionIdentity | null> {
  const session = await auth.api.getSession({ headers });
  if (!session) return null;

  let role: string | null = null;
  try {
    await auth.api.setActiveOrganization({ headers, body: { organizationSlug: DEMO_ORG_SLUG } });
    role = (await auth.api.getActiveMemberRole({ headers })).role;
  } catch {
    role = null;
  }
  return {
    userId: session.user.id,
    email: session.user.email,
    role,
    acls: rolesToAcls(role),
    isAdmin: isAdminRole(role),
  };
}

/** Cabeceras hacia chatrag-api: bearer de servicio (si está configurado) + identidad. */
export function backendHeaders(identity: SessionIdentity | null): Record<string, string> {
  const headers: Record<string, string> = {};
  const serviceBearer = process.env.CHATRAG_SERVICE_BEARER_TOKEN;
  if (serviceBearer) headers.Authorization = `Bearer ${serviceBearer}`;
  if (identity) {
    headers["X-User-Id"] = identity.userId;
    headers["X-User-Acls"] = identity.acls.join(",");
  }
  return headers;
}
