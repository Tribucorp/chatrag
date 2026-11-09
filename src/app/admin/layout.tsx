import { headers } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { getSessionIdentity } from "@/lib/session";

// Server Component: todo /admin/* exige sesión de tribu-auth con rol de administración (`ADMIN_ROLE`, acl.ts) antes de
// pintar nada. El proxy /api/admin/* lo vuelve a comprobar en cada petición (esto solo evita
// mostrar un panel que respondería 403), y el backend sigue exigiendo su bearer de admin.
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const identity = await getSessionIdentity(await headers());
  if (!identity) redirect("/login");
  if (!identity.isAdmin) {
    return (
      <main className="relative z-10 flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
        <h1 className="text-2xl font-semibold">Acceso restringido</h1>
        <p className="max-w-sm text-sm text-white/55">
          El panel de administración requiere el rol de administración. Tu sesión (
          {identity.email}) no lo tiene.
        </p>
        <Link href="/" className="text-xs text-white/45 underline decoration-white/20 hover:text-white/70">
          Volver al asistente
        </Link>
      </main>
    );
  }
  return children;
}
