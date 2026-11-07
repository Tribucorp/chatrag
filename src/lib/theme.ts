// Tipos y funciones puras de theming — SIN "use client": las usa tanto el Server Component
// (`layout.tsx`, para las variables CSS) como el contexto de cliente (`theme-context.tsx`).
// Un archivo "use client" no puede exportar una función plana consumible desde un Server
// Component (solo componentes/hooks) — de ahí la separación.

export type Theme = {
  app_name: string;
  logo_url: string | null;
  color_accent: string;
  color_accent_secondary: string;
  color_background: string;
  font_family: string;
  density: "compact" | "comfortable";
  bubble_style: "rounded" | "square";
  eyebrow_text: string;
  heading_text: string;
  description_text: string;
  // Voz (ver backend/voice.py): voice_id DEBE ser uno del catálogo stock real de tribu_voice —
  // si no lo es, /voice/session falla-cerrado con 503 en vez de sintetizar con una voz inventada.
  voice_id: string;
};

// Catálogo stock real de tribu_voice (ver ~/repositorio/tribu-sdk/python/tribu-voice) — mismo
// conjunto que valida `VoiceBrand.voice_id` en el backend. Un despliegue con su propio Riva
// reemplaza este catálogo de ejemplo, no el campo `voice_id` en sí.
export const VOICE_STOCK_CATALOG: { id: string; label: string }[] = [
  { id: "es-419.Female-1", label: "Español latam — mujer" },
  { id: "es-ES.Female-1", label: "Español españa — mujer" },
  { id: "es-ES.Male-1", label: "Español españa — hombre" },
  { id: "en-US.Female-1", label: "Inglés EE.UU. — mujer" },
];

export const DEFAULT_THEME: Theme = {
  app_name: "ChatRAG",
  logo_url: null,
  color_accent: "#3b82f6",
  color_accent_secondary: "#d52b1e",
  color_background: "#050505",
  font_family: "system-ui, -apple-system, sans-serif",
  density: "comfortable",
  bubble_style: "rounded",
  eyebrow_text: "Ilustre Municipalidad de Santiago",
  heading_text: "Asistente de la comuna de Santiago",
  description_text:
    "Asistente oficial de la comuna de Santiago de Chile. Consúltame sobre trámites y " +
    "servicios municipales, direcciones del municipio, el alcalde Mario Desbordes o " +
    "cualquier información del sitio munistgo.cl. Escribe tu pregunta y te respondo con " +
    "el enlace directo del trámite y su fuente.",
  voice_id: "es-419.Female-1",
};

/** CSS custom properties a partir del tema — se aplican inline en `<html>` desde el server
 * component (`layout.tsx`), así que ya están presentes en el primer paint (sin flash). */
export function themeCssVars(theme: Theme): Record<string, string> {
  return {
    "--chatrag-accent": theme.color_accent,
    "--chatrag-accent-secondary": theme.color_accent_secondary,
    "--chatrag-bg": theme.color_background,
    "--chatrag-font": theme.font_family,
    "--chatrag-radius": theme.bubble_style === "square" ? "0.375rem" : "1rem",
    "--chatrag-gap": theme.density === "compact" ? "0.5rem" : "1rem",
    "--chatrag-padding": theme.density === "compact" ? "0.625rem" : "1rem",
  };
}
