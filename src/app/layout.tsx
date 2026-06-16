import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Asistente de Voz · Chile",
  description:
    "Agente de voz conversacional sobre Chile — geografía, historia, cultura y datos del país. Powered by ElevenLabs.",
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
