/**
 * Traduce el rol de organización (better-auth/tribu-auth) del usuario a la lista de ACLs que
 * el backend espera en `X-User-Acls` (ver `backend/src/chatrag_api/app.py` → `current_user`).
 * Único punto de esta traducción — deliberadamente sin dependencias de `@tribu/auth` para que
 * sea testeable sin resolver el paquete SDK (consumido hoy como `file:` a TS sin compilar).
 *
 * Vocabulario de ACL = el mismo que ya usa `backend/src/chatrag_api/rag.py` (`required_acl`):
 * etiquetas libres de producto, no genéricas del SDK.
 */

const ROLE_ACLS: Readonly<Record<string, readonly string[]>> = {
  member: [],
  rrhhStaff: ["rrhh"],
  finanzasStaff: ["finanzas"],
  municipalAdmin: ["rrhh", "finanzas"],
};

export function rolesToAcls(role: string | null | undefined): string[] {
  if (!role) return [];
  return [...(ROLE_ACLS[role] ?? [])];
}
