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
export const DEMO_ORG_SLUG = "comuna-santiago";

export const DEMO_SEED_ENABLED = process.env.CHATRAG_AUTH_DEMO_SEED === "1";

const DEMO_USERS = [
  { email: "admin@munistgo.cl", name: "Admin Municipal (demo)", role: "municipalAdmin" },
  { email: "rrhh@munistgo.cl", name: "Funcionaria RRHH (demo)", role: "rrhhStaff" },
  { email: "finanzas@munistgo.cl", name: "Funcionario Finanzas (demo)", role: "finanzasStaff" },
  { email: "vecino@munistgo.cl", name: "Vecino (demo)", role: "member" },
] as const;

/** Misma contraseña para las 4 cuentas — demo pública, nunca credenciales reales. */
export const DEMO_PASSWORD = "vecino-demo-2026";

let seeded: Promise<void> | null = null;

async function seedOnce(): Promise<void> {
  const [creator, ...rest] = DEMO_USERS;
  const creatorSignUp = await auth.api.signUpEmail({
    body: { email: creator.email, password: DEMO_PASSWORD, name: creator.name },
  });
  const organization = await auth.api.createOrganization({
    body: {
      name: "Municipalidad de Santiago (demo)",
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

/** Memoiza el seed dentro del proceso. No hace nada si el seed demo no está activado. */
export function ensureDemoSeed(): Promise<void> {
  if (!DEMO_SEED_ENABLED) return Promise.resolve();
  if (!seeded) {
    seeded = seedOnce().catch((err: unknown) => {
      seeded = null; // permite reintentar en la siguiente llamada si falló
      throw err;
    });
  }
  return seeded;
}
