import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Asistente de la comuna de Santiago",
  description:
    "Asistente de la Municipalidad de Santiago de Chile — trámites, servicios municipales, direcciones y alcalde. RAG on-prem con citas verificables (Tribu SDK).",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>
        <div className="aurora" aria-hidden />
        {children}
      </body>
    </html>
  );
}
