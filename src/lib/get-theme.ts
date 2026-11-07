import "server-only";

import { DEFAULT_THEME, type Theme } from "./theme";

const API_URL = process.env.CHATRAG_API_URL ?? "http://localhost:8080";

/** Fetch SSR del tema, server-only (usa `CHATRAG_API_URL` directo, sin pasar por el BFF — es
 * el propio servidor de Next.js el que llama, no el navegador). Nunca revienta el layout: si
 * el backend no responde (o no está desplegado todavía), cae al tema por defecto — el sitio
 * debe pintar igual aunque el panel de administración esté caído. */
export async function getTheme(): Promise<Theme> {
  try {
    const resp = await fetch(`${API_URL}/theme`, {
      // El tema puede cambiar desde /admin sin redeploy — no cachear entre requests.
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (!resp.ok) return DEFAULT_THEME;
    return (await resp.json()) as Theme;
  } catch {
    return DEFAULT_THEME;
  }
}
