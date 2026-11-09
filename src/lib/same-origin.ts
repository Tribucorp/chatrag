/**
 * Protección CSRF de /api/auth/*: si la petición trae `Origin`, tiene que ser exactamente el
 * mismo host al que va dirigida (el `Host` con el que el navegador llegó al equipo: su IP en la
 * red del cliente, un nombre DNS…). Con la `baseURL` dinámica de better-auth (auth.ts) esto
 * sustituye a una lista fija de orígenes de confianza sin abrirla a cualquier origen http.
 * Sin `Origin` (curl, peticiones del propio servidor) no hay navegador ajeno que proteger.
 */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  const host = request.headers.get("host");
  if (!host) return false;
  try {
    const parsed = new URL(origin);
    return (parsed.protocol === "http:" || parsed.protocol === "https:") && parsed.host === host;
  } catch {
    return false;
  }
}
