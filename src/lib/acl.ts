/**
 * Roles de ChatRAG y su traducción a ACLs. ÚNICA fuente de verdad: `auth.ts` entrega
 * `ROLE_GRANTS` a `createTribuAuth` (lo que better-auth aplica) y el BFF usa `rolesToAcls`
 * para armar `X-User-Acls` hacia el backend (`backend/src/chatrag_api/app.py` → `current_user`).
 * Sin dependencias de `@tribu/auth` ni "server-only", para que sea testeable sola.
 *
 * Vocabulario de ACL = el de `backend/src/chatrag_api/rag.py` (`required_acl`).
 */

// Etiquetas de los documentos internos (cabecera `acl:` del corpus). Lo público no lleva etiqueta:
// el backend se la añade a todo usuario (`rag.PUBLIC_ACL`).
export const ACL_STATEMENTS = { chatragAcl: ["soporte", "comercial"] } as const;

type Acl = (typeof ACL_STATEMENTS)["chatragAcl"][number];

export const ROLE_GRANTS: Record<string, { chatragAcl: Acl[] }> = {
  cliente: { chatragAcl: [] }, // solo la base de conocimiento pública
  tecnico: { chatragAcl: ["soporte"] }, // + procedimientos internos de soporte
  comercial: { chatragAcl: ["comercial"] }, // + tarifas y contratos
  adminSoporte: { chatragAcl: ["soporte", "comercial"] }, // todo + /admin
};

/** Fail-closed: sin rol, o con un rol desconocido, ninguna ACL extra (solo citas públicas). */
export function rolesToAcls(role: string | null | undefined): string[] {
  if (!role || !Object.hasOwn(ROLE_GRANTS, role)) return [];
  return [...ROLE_GRANTS[role].chatragAcl];
}

/** Único rol con acceso a /admin (ingesta, tema, conversaciones). Además del bearer de admin del
 * backend (`CHATRAG_ADMIN_TOKEN`): dos llaves distintas, sesión con rol + secreto de operación. */
export const ADMIN_ROLE = "adminSoporte";

export function isAdminRole(role: string | null | undefined): boolean {
  return role === ADMIN_ROLE;
}
