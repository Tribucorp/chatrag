"use client";

// Contexto de tema en el cliente: `layout.tsx` (Server Component) hace el fetch SSR a
// `GET /theme` del backend (`src/lib/get-theme.ts`) y pasa el resultado aquí como prop inicial
// — este componente solo lo distribuye a los componentes que necesitan el valor como DATO
// (app_name, logo_url), no como variable CSS (esas ya están aplicadas inline en <html> por el
// propio layout vía `themeCssVars`, sin pasar por React). Evita un segundo fetch en el
// navegador para lo que el servidor ya resolvió.
//
// Tipos/`DEFAULT_THEME`/`themeCssVars` viven en `./theme.ts` (sin "use client") a propósito:
// un módulo "use client" no puede exportar una función plana invocable desde un Server
// Component, solo componentes/hooks — ver el build que lo confirmó.

import { createContext, useContext } from "react";

import { DEFAULT_THEME, type Theme } from "./theme";

const ThemeContext = createContext<Theme>(DEFAULT_THEME);

export function ThemeProvider({
  theme,
  children,
}: {
  theme: Theme;
  children: React.ReactNode;
}) {
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}
