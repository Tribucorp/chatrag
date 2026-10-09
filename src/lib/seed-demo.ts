import "server-only";

import { auth } from "./auth";

/**
 * Cuentas y organización del DEMO (SparkHub) — SOLO para el piloto. `createTribuAuth` usa el
 * adapter en memoria por defecto (sin `database` propio en `auth.ts`), así que este estado NO
 * persiste entre reinicios del proceso: cada arranque parte de una base vacía y esta función
 * se llama una vez para poblarla. En producción, con una BD real, esto se sustituye por altas
 * reales de usuarios (no se ejecuta este seed).
 *
 * Deliberadamente NO intenta ser idempotente contra una BD persistente entre reinicios — eso
 * exigiría resolver "¿existe ya esta organización?" sin una sesión (no hay endpoint de
 * better-auth para eso: `getFullOrganization`/`setActiveOrganization` exigen sesión). Con el
 * adapter en memoria no hace falta: cada arranque es una base nueva.
 */
export const DEMO_ORG_SLUG = "comuna-santiago";

const DEMO_USERS = [
  { email: "admin@munistgo.cl", name: "Admin Municipal (demo)", role: "municipalAdmin" as const },
  { email: "rrhh@munistgo.cl", name: "Funcionaria RRHH (demo)", role: "rrhhStaff" as const },
  { email: "finanzas@munistgo.cl", name: "Funcionario Finanzas (demo)", role: "finanzasStaff" as const },
  { email: "vecino@munistgo.cl", name: "Vecino (demo)", role: "member" as const },
];

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
  if (!organization) throw new Error("seed-demo: createOrganization devolvió null inesperadamente");

  for (const demoUser of rest) {
    const signUp = await auth.api.signUpEmail({
      body: { email: demoUser.email, password: DEMO_PASSWORD, name: demoUser.name },
    });
    // `role` está tipado en `.d.ts` compilado contra los roles por defecto de better-auth
    // (member/admin/owner) — la emisión de declaraciones de tsc no preserva los nombres de rol
    // literales de `createTribuAuth` (ver nota en tribu-sdk/create-tribu-auth.ts). En runtime
    // better-auth valida el string contra los roles reales configurados (rrhhStaff, etc.), así
    // que esto es un hueco de tipos, no de comportamiento.
    await auth.api.addMember({
      body: { userId: signUp.user.id, role: demoUser.role, organizationId: organization.id },
    } as unknown as Parameters<typeof auth.api.addMember>[0]);
  }
}

/** Memoiza el seed dentro del proceso — llamable desde cualquier ruta sin sembrar dos veces. */
export function ensureDemoSeed(): Promise<void> {
  if (!seeded) {
    seeded = seedOnce().catch((err) => {
      seeded = null; // permite reintentar en la siguiente llamada si falló
      throw err;
    });
  }
  return seeded;
}
