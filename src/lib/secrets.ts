import "server-only";

import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Secreto del servidor: la variable de entorno si está definida (despliegue con `.env`); si no,
 * el fichero que generó chatrag-api en el primer arranque en `CHATRAG_SECRETS_DIR` (despliegue
 * de MarketplaceForge, ver backend/src/chatrag_api/secretos.py). Nunca se registra el valor.
 *
 * Se lee en cada llamada (sin caché): el frontend puede arrancar antes de que la api termine de
 * generar los ficheros, y en cuanto existen se usan sin reiniciar.
 */
export function readSecret(envName: string, fileName: string): string | undefined {
  const fromEnv = process.env[envName];
  if (fromEnv) return fromEnv;
  const dir = process.env.CHATRAG_SECRETS_DIR;
  if (!dir) return undefined;
  try {
    return readFileSync(path.join(dir, fileName), "utf8").trim() || undefined;
  } catch {
    return undefined;
  }
}

export const serviceBearerToken = () =>
  readSecret("CHATRAG_SERVICE_BEARER_TOKEN", "service_bearer_token");
export const adminToken = () => readSecret("CHATRAG_ADMIN_TOKEN", "admin_token");
export const authSecret = () => readSecret("CHATRAG_AUTH_SECRET", "auth_secret");
