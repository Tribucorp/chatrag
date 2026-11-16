import type { Metadata } from "next";
import "./globals.css";
import { getTheme } from "@/lib/get-theme";
import { ThemeProvider } from "@/lib/theme-context";
import { themeCssVars } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Asistente de la comuna de Santiago",
  description:
    "Asistente de la Municipalidad de Santiago de Chile — trámites, servicios municipales, direcciones y alcalde. RAG on-prem con citas verificables (Tribu SDK).",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Fetch SSR (ver src/lib/get-theme.ts) — las variables CSS quedan aplicadas en <html> antes
  // del primer paint, sin flash de tema por defecto seguido de un cambio.
  const theme = await getTheme();

  return (
    <html lang="es" style={themeCssVars(theme)}>
      <body>
        <div className="aurora" aria-hidden />
        <ThemeProvider theme={theme}>{children}</ThemeProvider>
      </body>
    </html>
  );
}
