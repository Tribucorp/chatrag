// Scaffold de Auth.js v5 (NextAuth). Provee `auth()` para que el BFF
// (`src/app/api/chat/route.ts`) derive la identidad real del usuario en vez de dejar que el
// navegador la declare — ver CLAUDE.md ("ACL de la fuente en el servidor") y
// `backend/src/chatrag_api/app.py: current_user` (fail-closed sin X-User-Id).
//
// TODO(identidad real): sin `providers` configurado, `auth()` siempre devuelve `null` — nadie
// puede autenticarse todavía. Esto es deliberado: no hay un proveedor SSO/OIDC del ecosistema
// Tribucorp confirmado para ChatRAG (el proyecto hermano "socios" tampoco lo tiene cerrado, ver
// docs/SEMILLAS.md vía x9). Añadir aquí el provider real (Credentials u OIDC) es lo único que
// falta para que `answer_query` reciba ACLs reales en vez de operar siempre en modo abstención
// (sin X-User-Id, el backend responde 401 salvo `CHATRAG_DEV_IDENTITY_BYPASS`).
//
// Mientras tanto, el resto del wiring (secret, sesión JWT, forma de la respuesta) ya queda
// listo para que activar un provider sea el único paso pendiente.

import NextAuth from "next-auth";

import "./auth-types";

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Nombre no estándar (`CHATRAG_AUTH_SECRET` en vez de `AUTH_SECRET`) porque este repo
  // prefija sus variables con `CHATRAG_` (ver .env.example) — Auth.js no lo detecta solo, así
  // que se pasa explícito.
  secret: process.env.CHATRAG_AUTH_SECRET,
  // Detrás de un proxy (Vercel, k8s ingress) sin `AUTH_URL` estándar: confiar en los headers
  // del request para construir la URL canónica en vez de exigir esa env var.
  trustHost: true,
  session: { strategy: "jwt" },
  providers: [
    // TODO(identidad real): añadir el provider del SSO/OIDC de Tribucorp aquí cuando exista,
    // o un CredentialsProvider si el arranque es con usuario/password. Ver el TODO de arriba.
  ],
  callbacks: {
    // Traslada `acls` del perfil del provider a la sesión. Hoy no hay provider que las
    // pueble, así que `session.user.acls` queda siempre en `[]` — el backend ya trata "sin
    // ACLs" como "sin base accesible" y se abstiene (fail-closed), nunca inventa acceso.
    jwt({ token, profile }) {
      if (profile && "acls" in profile) {
        token.acls = profile.acls as string[];
      }
      return token;
    },
    session({ session, token }) {
      if (token.sub) {
        session.user.id = token.sub;
      }
      session.user.acls = (token.acls as string[] | undefined) ?? [];
      return session;
    },
  },
});
