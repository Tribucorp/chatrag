import "server-only";

import { getMigrations } from "better-auth/db/migration";

import { auth } from "./auth";
import { ensureDemoSeed } from "./seed-demo";

/**
 * Deja tribu-auth listo antes de la primera petición que lo use: crea/actualiza las tablas de
 * better-auth en la BD persistente (si hay `CHATRAG_AUTH_DB`) y, después, el seed demo opcional.
 * Una vez por proceso (memoizado en `globalThis`, igual que `auth`). Si la migración falla, se
 * reintenta en la siguiente petición: sin tablas no hay login posible.
 */
declare global {
  var __chatragAuthReady: Promise<void> | undefined;
}

async function prepare(): Promise<void> {
  if (process.env.CHATRAG_AUTH_DB) {
    const { runMigrations } = await getMigrations(auth.options);
    await runMigrations();
  }
  await ensureDemoSeed();
}

export function ensureAuthReady(): Promise<void> {
  globalThis.__chatragAuthReady ??= prepare().catch((err: unknown) => {
    globalThis.__chatragAuthReady = undefined;
    throw err;
  });
  return globalThis.__chatragAuthReady;
}
