import "server-only";

import { DatabaseSync } from "node:sqlite";

import { nextCookies } from "better-auth/next-js";
// `@tribu/auth` = alias npm de `@tribucorp/tribu-auth` (GitHub Packages, ver .npmrc y
// package.json) — el paquete publicado trae su `dist/` compilado, sin rutas `file:` al SDK.
import { createTribuAuth } from "@tribu/auth";

// Vocabulario de ACL y roles propios de ChatRAG — `tribu-auth` es agnóstico de producto. Viven
// en `acl.ts`, la misma tabla que usa el BFF para armar `X-User-Acls`: una sola fuente.
import { ACL_STATEMENTS, ADMIN_ROLE, ROLE_GRANTS } from "./acl";
import { authSecret } from "./secrets";

/**
 * URL base de better-auth:
 * - `CHATRAG_AUTH_URL` fija (un dominio conocido), o
 * - dinámica: el origen se deduce de cada petición entre los `CHATRAG_ALLOWED_HOSTS` (por defecto
 *   `*`). Es lo que permite entrar por la IP del equipo en la red del cliente sin conocerla al
 *   instalar. La protección CSRF la pone /api/auth/* antes de better-auth: el `Origin` tiene
 *   que ser el mismo host de la petición (same-origin.ts), y un sitio ajeno no puede falsificar
 *   el `Origin` del navegador.
 */
function baseURL():
  | string
  | { allowedHosts: string[]; protocol: "http" | "https"; fallback: string } {
  const fixed = process.env.CHATRAG_AUTH_URL;
  if (fixed) return fixed;
  const hosts = (process.env.CHATRAG_ALLOWED_HOSTS ?? "*")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);
  return {
    allowedHosts: hosts.length ? hosts : ["*"],
    // Explícito, no "auto": better-auth decide al arrancar si la cookie de sesión es `Secure`, y
    // con "auto" en producción siempre lo es — un navegador no la envía por http://IP, que es
    // como se entra en la red del cliente. `https` si el partner pone TLS delante. Con `*`,
    // better-auth confiaría en cualquier origen de ese esquema: por eso /api/auth/* exige antes
    // que el Origin sea el mismo host de la petición (same-origin.ts).
    protocol: process.env.CHATRAG_AUTH_PROTOCOL === "https" ? "https" : "http",
    // Para las llamadas del propio servidor (seed demo), que no traen petición.
    fallback: "http://localhost:3000",
  };
}

/**
 * Usuarios y sesiones: SQLite (`node:sqlite`, sin dependencias) en `CHATRAG_AUTH_DB` — un fichero
 * en un volumen persistente. Sin esa variable, la BD en memoria de `createTribuAuth` (solo dev:
 * se pierde al reiniciar). Las tablas las crea `ensureAuthReady` (auth-ready.ts).
 */
function database(): DatabaseSync | undefined {
  const file = process.env.CHATRAG_AUTH_DB;
  return file ? new DatabaseSync(file) : undefined;
}

function buildAuth() {
  const secret = authSecret();
  if (!secret) {
    // Fail-closed: sin secreto no hay sesiones firmadas — nunca un default silencioso.
    throw new Error(
      "Falta el secreto de sesión: define CHATRAG_AUTH_SECRET (`openssl rand -base64 32`) o " +
        "CHATRAG_SECRETS_DIR con el auth_secret que genera chatrag-api en su primer arranque.",
    );
  }
  return createTribuAuth({
    appName: process.env.NEXT_PUBLIC_APP_NAME ?? "ChatRAG",
    // `TribuAuthConfig.baseURL` está tipado como string, pero se reenvía tal cual a betterAuth,
    // que acepta también la forma dinámica `{ allowedHosts }`.
    baseURL: baseURL() as string,
    secret,
    accessControlStatements: ACL_STATEMENTS,
    roles: ROLE_GRANTS,
    // Sin esto better-auth usa "owner", un rol que no existe en ROLE_GRANTS: quien crea la
    // organización (el seed demo) se quedaría sin ninguna ACL.
    creatorRole: ADMIN_ROLE,
    database: database(),
    plugins: [nextCookies()],
  });
}

// Next.js bundla Route Handlers y Server Components en grafos de módulos separados: este
// archivo se evalúa una vez POR GRAFO. Una sola instancia por proceso (en `globalThis`): con la
// BD en memoria, cada grafo tendría su propia "BD" aislada (bug real encontrado en el PR #15), y
// con SQLite, varias conexiones al mismo fichero.
declare global {
  var __chatragAuth: ReturnType<typeof buildAuth> | undefined;
}

export const auth = globalThis.__chatragAuth ?? buildAuth();
globalThis.__chatragAuth = auth;
