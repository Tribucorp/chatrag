import "server-only";

import { auth } from "./auth";

/**
 * Organización de ChatRAG y, SOLO si `CHATRAG_AUTH_DEMO_SEED=1`, cuatro cuentas demo con
 * contraseña pública. Opt-in explícito: unas credenciales publicadas en la pantalla de login
 * nunca deben existir por defecto en un entorno real.
 *
 * Con el memoryAdapter de `createTribuAuth` (sin `database` en `auth.ts`) nada persiste entre
 * reinicios: cada arranque parte vacío y esto se ejecuta una vez por proceso. No es idempotente
 * contra una BD persistente — al conectar una BD real, las altas pasan a ser reales y este seed
 * se retira.
 */
// Empresa FICTICIA de la demo: partner de soporte de servidores Dell PowerEdge. Dominio `.example`
// (RFC 2606): reservado, no puede corresponder a nadie real.
export const DEMO_ORG_SLUG = "ventisca-ti";
export const DEMO_ORG_NAME = "Ventisca TI (empresa ficticia de demo)";

export const DEMO_SEED_ENABLED = process.env.CHATRAG_AUTH_DEMO_SEED === "1";

const DEMO_USERS = [
  { email: "admin@ventisca-ti.example", name: "Admin de soporte (demo)", role: "adminSoporte" },
  { email: "tecnico@ventisca-ti.example", name: "Técnica de soporte (demo)", role: "tecnico" },
  { email: "comercial@ventisca-ti.example", name: "Ejecutivo comercial (demo)", role: "comercial" },
  { email: "cliente@ventisca-ti.example", name: "Cliente (demo)", role: "cliente" },
] as const;

/** Misma contraseña para las 4 cuentas — demo pública, nunca credenciales reales. */
export const DEMO_ACCOUNTS = DEMO_USERS.map((u) => u.email);

export const DEMO_PASSWORD = "ventisca-demo-2026";

// En `globalThis`, junto a la instancia de `auth` (ver auth.ts): si Next reevalúa este módulo
// (HMR en dev, otro grafo de módulos) la marca de "ya sembrado" tiene que sobrevivir igual que la
// BD en memoria; si no, el seed se repite, choca con "User already exists" y tumba el login.
declare global {
  var __chatragDemoSeed: Promise<void> | undefined;
}

async function seedOnce(): Promise<void> {
  const [creator, ...rest] = DEMO_USERS;
  const creatorSignUp = await auth.api.signUpEmail({
    body: { email: creator.email, password: DEMO_PASSWORD, name: creator.name },
  });
  const organization = await auth.api.createOrganization({
    body: {
      name: DEMO_ORG_NAME,
      slug: DEMO_ORG_SLUG,
      userId: creatorSignUp.user.id,
    },
  });
  if (!organization) throw new Error("seed-demo: createOrganization devolvió null");

  for (const demoUser of rest) {
    const signUp = await auth.api.signUpEmail({
      body: { email: demoUser.email, password: DEMO_PASSWORD, name: demoUser.name },
    });
    // El `.d.ts` publicado tipa `role` contra los roles por defecto de better-auth
    // (member/admin/owner): la emisión de declaraciones no preserva los nombres literales de
    // `createTribuAuth`. En runtime better-auth valida contra los roles reales configurados.
    await auth.api.addMember({
      body: { userId: signUp.user.id, role: demoUser.role, organizationId: organization.id },
    } as unknown as Parameters<typeof auth.api.addMember>[0]);
  }
}

/** Siembra una sola vez por proceso. Nunca lanza: un fallo del seed (p. ej. BD ya sembrada)
 * se registra y el login sigue funcionando para las cuentas que existan. */
export function ensureDemoSeed(): Promise<void> {
  if (!DEMO_SEED_ENABLED) return Promise.resolve();
  globalThis.__chatragDemoSeed ??= seedOnce().catch((err: unknown) => {
    console.error("[chatrag] seed demo de tribu-auth falló; el login sigue disponible:", err);
  });
  return globalThis.__chatragDemoSeed;
}
