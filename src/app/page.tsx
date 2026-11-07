import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { Home } from "@/components/home";
import { auth } from "@/lib/auth";

// Server Component: la sesión de tribu-auth se valida en el servidor antes de pintar el chat.
// El BFF (`/api/chat`, `/api/voice/*`) vuelve a validarla en cada petición — esto solo evita
// mostrar una pantalla que respondería 401.
export default async function Page() {
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) redirect("/login");
  return <Home email={session.user.email} />;
}
