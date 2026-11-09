"""Secretos de primer arranque (despliegue de MarketplaceForge, `compose.spec.yaml`).

En el marketplace no hay `.env`: el `env` del `compose.spec.yaml` es literal y no admite
`${VAR}`. Con `CHATRAG_GENERATE_SECRETS=1`, chatrag-api crea en `CHATRAG_SECRETS_DIR` (un volumen
con nombre que comparten api, frontend, MinIO y Milvus) los secretos que falten, una sola vez:

- `service_bearer_token` — BFF → chatrag-api.
- `admin_token` — bearer del backend para `/admin/*` (el BFF lo añade tras comprobar el rol).
- `auth_secret` — firma de sesiones de tribu-auth (frontend).
- `minio_user` / `minio_password` — credenciales de MinIO, que también usa Milvus.

Ficheros 0600 creados con O_EXCL (dos arranques simultáneos no se pisan: el segundo lee lo que
escribió el primero). Una variable de entorno con el mismo nombre (`CHATRAG_SERVICE_BEARER_TOKEN`,
…) siempre gana: el despliegue con `.env` de GB10 sigue funcionando igual. Nunca se registran
los valores.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

GENERATED: dict[str, int] = {
    # nombre → bytes de entropía (token_urlsafe)
    "service_bearer_token": 32,
    "admin_token": 32,
    "auth_secret": 32,
    "minio_password": 24,
}
MINIO_USER = "minio_user"


def _write_once(path: Path, value: str) -> None:
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return  # otro arranque lo creó antes: se respeta el suyo
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)


def ensure_secrets(directory: Path) -> None:
    """Crea los secretos que falten en `directory` (0700). Idempotente."""

    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # El volumen ya existe como punto de montaje (mkdir no cambia sus permisos): se ajustan.
    directory.chmod(0o700)
    for name, nbytes in GENERATED.items():
        _write_once(directory / name, secrets.token_urlsafe(nbytes))
    # MinIO exige un usuario de ≥3 caracteres; uno propio en vez del `minioadmin` por defecto.
    _write_once(directory / MINIO_USER, f"chatrag-{secrets.token_hex(6)}")


def read_secret(directory: Path | None, name: str) -> str | None:
    """Valor del secreto `name`, o None si no hay directorio o no existe todavía."""

    if directory is None:
        return None
    try:
        value = (directory / name).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return value or None


def secret_from_env_or_dir(env_name: str, file_name: str) -> str | None:
    """`env_name` si está definida; si no, el fichero de `CHATRAG_SECRETS_DIR`."""

    if value := os.environ.get(env_name):
        return value
    raw_dir = os.environ.get("CHATRAG_SECRETS_DIR")
    return read_secret(Path(raw_dir) if raw_dir else None, file_name)
