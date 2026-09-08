import { toNextJsHandler } from "better-auth/next-js";
import { auth } from "@/lib/auth";
import { ensureDemoSeed } from "@/lib/seed-demo";

// Siembra las cuentas demo (ver seed-demo.ts) antes de servir cualquier endpoint de auth —
// necesario para que el login del demo funcione contra el adapter en memoria sin un paso de
// arranque separado.
void ensureDemoSeed();

export const { GET, POST } = toNextJsHandler(auth);
