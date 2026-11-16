import "server-only";

import { nextCookies } from "better-auth/next-js";
// `@tribu/auth` = alias npm de `@tribucorp/tribu-auth` (GitHub Packages, ver .npmrc y
// package.json) — el paquete publicado trae su `dist/` compilado, sin rutas `file:` al SDK.
import { createTribuAuth } from "@tribu/auth";

// Vocabulario de ACL y roles propios de ChatRAG — `tribu-auth` es agnóstico de producto. Viven
// en `acl.ts`, la misma tabla que usa el BFF para armar `X-User-Acls`: una sola fuente.
import { ACL_STATEMENTS, ROLE_GRANTS } from "./acl";

function buildAuth() {
  const secret = process.env.CHATRAG_AUTH_SECRET;
  if (!secret) {
    // Fail-closed: sin secreto no hay sesiones firmadas — nunca un default silencioso.
    throw new Error(
      "CHATRAG_AUTH_SECRET no está definida — genera una con `openssl rand -base64 32` y " +
        "ponla en tu .env (ver .env.example). No hay default: sin secreto, no hay sesiones.",
    );
  }
  return createTribuAuth({
    appName: process.env.NEXT_PUBLIC_APP_NAME ?? "ChatRAG",
    baseURL: process.env.CHATRAG_AUTH_URL ?? "http://localhost:3000",
    secret,
    accessControlStatements: ACL_STATEMENTS,
    roles: ROLE_GRANTS,
    // Sin esto better-auth usa "owner", un rol que no existe en ROLE_GRANTS: quien crea la
    // organización (el seed demo) se quedaría sin ninguna ACL.
    creatorRole: "municipalAdmin",
    // TODO(persistencia): sin `database`, `createTribuAuth` usa su memoryAdapter — usuarios y
    // sesiones se pierden al reiniciar. Vale para el piloto; producción necesita una BD real.
    plugins: [nextCookies()],
  });
}

// Next.js bundla Route Handlers y Server Components en grafos de módulos separados: este
// archivo se evalúa una vez POR GRAFO y, con el adapter en memoria, cada evaluación tendría su
// propia "BD" aislada (un login vía `/api/auth/*` no existiría para `getSession()` en un Server
// Component). Se memoiza en `globalThis`, compartido por todo el proceso Node. Bug real
// encontrado end-to-end en el PR #15, no una precaución teórica.
declare global {
  var __chatragAuth: ReturnType<typeof buildAuth> | undefined;
}

export const auth = globalThis.__chatragAuth ?? buildAuth();
globalThis.__chatragAuth = auth;
