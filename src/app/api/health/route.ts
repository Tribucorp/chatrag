// Healthcheck del frontend (compose.spec.yaml): sin sesión ni llamadas al backend — solo dice
// que el servidor Next responde. `sparkd` lo usa para `dependsOn` y el rolling update.
export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json({ status: "ok" });
}
