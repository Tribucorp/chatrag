import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { Home } from "@/components/home";
import { auth } from "@/lib/auth";
import { ensureAuthReady } from "@/lib/auth-ready";

// Server Component: la sesión de tribu-auth se valida en el servidor antes de pintar el chat.
// El BFF (`/api/chat`, `/api/voice/*`) vuelve a validarla en cada petición — esto solo evita
// mostrar una pantalla que respondería 401.
export default async function Page() {
  await ensureAuthReady();
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");
  // La voz se decide en tiempo de ejecución (env del contenedor / variables de la solución en el
  // portal), no al compilar: el pipeline del marketplace no pasa build-args propios.
  return (
    <Home
      email={session.user.email}
      voiceEnabled={process.env.CHATRAG_VOICE_ENABLED === "1"}
    />
  );
}
