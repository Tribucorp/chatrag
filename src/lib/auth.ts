import "server-only";

import { nextCookies } from "better-auth/next-js";
// Import al `dist/` compilado, no al paquete raíz (`@tribu/auth` apunta su `main` a
// `src/index.ts` sin compilar — pensado para consumo DENTRO del workspace pnpm de tribu-sdk,
// donde vitest/tsc lo transforman al vuelo. Fuera de ese workspace, Turbopack/webpack no saben
// mapear los imports internos `./foo.js` a sus `.ts` reales). Exige `pnpm --filter @tribu/auth
// build` en tribu-sdk antes de `npm install`/`next build` aquí — documentado en README/.env.example.
import { createTribuAuth } from "@tribu/auth/dist/index.js";

// Vocabulario de ACL propio de ChatRAG — las mismas etiquetas que ya usa
// `backend/src/chatrag_api/rag.py` (`required_acl`). `tribu-auth` es framework/producto
// agnóstico: cada producto declara aquí su propio recurso/acciones, nunca al revés.
const STATEMENTS = { chatragAcl: ["rrhh", "finanzas"] } as const;

// Los roles viven en dos sitios que DEBEN coincidir: aquí (qué ACL concede cada rol, para que
// better-auth lo aplique) y `src/lib/acl.ts` → `rolesToAcls` (la misma traducción, para el BFF
// que arma `X-User-Acls`). `createTribuAuth` construye los `Role` reales por dentro a partir de
// estos datos planos — este módulo nunca importa `better-auth/plugins/access` directamente.
const roles = {
  member: { chatragAcl: [] },
  rrhhStaff: { chatragAcl: ["rrhh"] },
  finanzasStaff: { chatragAcl: ["finanzas"] },
  municipalAdmin: { chatragAcl: ["rrhh", "finanzas"] },
};

const authSecret = process.env.CHATRAG_AUTH_SECRET;
if (!authSecret) {
  // Fail-closed: sin secreto no hay sesiones firmadas de verdad — nunca arrancar con un
  // default silencioso (mismo principio que el resto del producto: `dev_identity_bypass` en
  // el backend también exige activación explícita, nunca un valor implícito).
  throw new Error(
    "CHATRAG_AUTH_SECRET no está definida — genera una con `openssl rand -base64 32` y " +
      "ponla en tu .env (ver .env.example). No hay default: sin secreto, no hay sesiones.",
  );
}

function buildAuth(secret: string) {
  return createTribuAuth({
    appName: process.env.NEXT_PUBLIC_APP_NAME ?? "ChatRAG",
    baseURL: process.env.CHATRAG_AUTH_URL ?? "http://localhost:3000",
    secret,
    accessControlStatements: STATEMENTS,
    roles,
    // Sin esto, better-auth usa su default "owner" — un nombre de rol que NO existe en `roles`
    // de arriba (los reemplazamos enteros por el vocabulario de ChatRAG), así que quien crea la
    // organización (el seed) se quedaría sin ninguna ACL. Solo importa para el demo: el único
    // que crea una organización es `seed-demo.ts`.
    creatorRole: "municipalAdmin",
    plugins: [nextCookies()],
  });
}

// Next.js bundla Route Handlers y Server Components en grafos de módulos separados: este
// archivo se evalúa una vez POR GRAFO, y con el adapter en memoria (por defecto, sin `database`
// propio) cada evaluación construiría su PROPIA "base de datos" aislada — un login hecho vía
// `/api/auth/*` (un grafo) no existiría para `auth.api.getSession()` llamado desde un Server
// Component (otro grafo). Se memoiza en `globalThis`, que sí es compartido por todo el proceso
// Node, para garantizar una única instancia real (mismo patrón que un cliente Prisma singleton
// en Next.js).
declare global {
  var __chatragAuth: ReturnType<typeof buildAuth> | undefined;
}

export const auth = globalThis.__chatragAuth ?? buildAuth(authSecret);
globalThis.__chatragAuth = auth;
