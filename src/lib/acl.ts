/**
 * Roles de ChatRAG y su traducción a ACLs. ÚNICA fuente de verdad: `auth.ts` entrega
 * `ROLE_GRANTS` a `createTribuAuth` (lo que better-auth aplica) y el BFF usa `rolesToAcls`
 * para armar `X-User-Acls` hacia el backend (`backend/src/chatrag_api/app.py` → `current_user`).
 * Sin dependencias de `@tribu/auth` ni "server-only", para que sea testeable sola.
 *
 * Vocabulario de ACL = el de `backend/src/chatrag_api/rag.py` (`required_acl`).
 */

export const ACL_STATEMENTS = { chatragAcl: ["rrhh", "finanzas"] } as const;

type Acl = (typeof ACL_STATEMENTS)["chatragAcl"][number];

export const ROLE_GRANTS: Record<string, { chatragAcl: Acl[] }> = {
  member: { chatragAcl: [] },
  rrhhStaff: { chatragAcl: ["rrhh"] },
  finanzasStaff: { chatragAcl: ["finanzas"] },
  municipalAdmin: { chatragAcl: ["rrhh", "finanzas"] },
};

/** Fail-closed: sin rol, o con un rol desconocido, ninguna ACL extra (solo citas públicas). */
export function rolesToAcls(role: string | null | undefined): string[] {
  if (!role || !Object.hasOwn(ROLE_GRANTS, role)) return [];
  return [...ROLE_GRANTS[role].chatragAcl];
}
