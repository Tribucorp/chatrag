"""Valores de la puerta de licencia HORNEADOS en la build (ver licencia.py).

En el repositorio este fichero deja la puerta apagada: desarrollo, tests y la imagen normal
(`deploy/Dockerfile.backend`) corren sin licencia. `deploy/Dockerfile.backend.protegido` lo
SOBREESCRIBE antes de compilar con Nuitka (queda dentro del `.so` de `chatrag_api`), con la
puerta obligatoria y las claves públicas de confianza. Que esto no venga del entorno es el
punto: en la imagen que se entrega a terceros, `CHATRAG_LICENSE_ENFORCEMENT=0` o una clave
pública propia no pueden desactivar la puerta.
"""

from __future__ import annotations

# True solo en la imagen protegida: la puerta no se puede apagar por entorno.
ENFORCED: bool = False
# key_id -> clave pública Ed25519 (32 bytes, hex). Con ENFORCED=True, las ÚNICAS de confianza.
TRUSTED_KEYS_HEX: dict[str, str] = {}
# Fichero del anti-rollback de reloj (último instante visto). Con ENFORCED=True es obligatorio.
STATE_FILE: str | None = None
