import type { Metadata } from "next";
import "./globals.css";
import { getTheme } from "@/lib/get-theme";
import { ThemeProvider } from "@/lib/theme-context";
import { themeCssVars } from "@/lib/theme";

export const metadata: Metadata = {
  title: "Asistente de soporte PowerEdge",
  description:
    "Asistente de soporte de servidores Dell PowerEdge de Ventisca TI (empresa ficticia de demo) — respuestas con fuente, RAG on-prem sobre el Tribu SDK.",
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
