// Augmenta los tipos de Auth.js v5. Extensión ".ts" a propósito, no ".d.ts": el `include` de
// tsconfig.json (`**/*.ts`) no recoge archivos ".d.ts" sueltos salvo que algo los importe
// (como hace next-env.d.ts) — con ".ts" normal, `src/app/api/chat/route.ts` lo trae solo con
// importarlo, sin tocar tsconfig.json.
//
// `next-auth` solo re-exporta `Session`/`User` con `export type { ... } from "@auth/core/types"`
// (no los declara localmente), así que hay que augmentar `@auth/core/types` directo — augmentar
// `"next-auth"` no fusiona con lo que de verdad devuelve `auth()`.

declare module "@auth/core/types" {
  interface User {
    acls?: string[];
  }
}

declare module "@auth/core/jwt" {
  interface JWT {
    acls?: string[];
  }
}

export {};
