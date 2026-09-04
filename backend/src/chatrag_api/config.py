"""Configuración del backend de ChatRAG. Todo por entorno (k8s-ready, sin rutas de host).

Notas heredadas del SDK que se materializan aquí:
- **Dimensión de embedding 2048 por defecto** (no 1024): el ecosistema 2026 usa 2048. El guard
  dinámico de `tribu-rag` lee la dimensión real del endpoint en arranque y falla-cerrado si no
  coincide con el índice; aquí solo declaramos el valor esperado para el arranque.
- **On-prem de verdad**: los NIM (embed/rerank/chat/voz) se sirven en la GPU del cliente, nunca
  APIs cloud. No hay claves de proveedores cloud en esta config.
- **tribu-voice tras flag apagado**: `voice_enabled` arranca en `False` — bloqueo legal NVIDIA
  pendiente (Product Specific Terms §C.1.1/§C.1.2). Reemplaza al ElevenLabs del prototipo.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_EMBED_DIM = 2048


class Settings(BaseModel):
    """Ajustes del backend, cargados de entorno con `Settings.from_env()`. Inmutable."""

    model_config = ConfigDict(frozen=True)

    app_name: str = "ChatRAG"
    embed_dim: int = Field(default=DEFAULT_EMBED_DIM, gt=0)

    # Endpoints on-prem (NIM servidos en la GPU del cliente). Sin defaults cloud.
    nim_embed_url: str = "http://localhost:8002"
    nim_rerank_url: str = "http://localhost:8003"
    nim_chat_url: str = "http://localhost:8004"

    # Egress deny-by-default (tribu-http): hosts a los que el backend puede salir. Solo los
    # NIM on-prem por defecto; nada de internet abierto.
    egress_allowed_hosts: frozenset[str] = frozenset({"localhost", "127.0.0.1"})

    # Voz: apagada por defecto (bloqueo legal de tribu-voice). Cuando se apruebe, se enciende
    # por entorno; jamás clonación de voz ni reconocimiento de emociones (Riva stock).
    voice_enabled: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        """Construye desde variables de entorno, con los defaults on-prem del SDK."""

        hosts = os.environ.get("CHATRAG_EGRESS_HOSTS")
        allowed = (
            frozenset(h.strip() for h in hosts.split(",") if h.strip())
            if hosts
            else frozenset({"localhost", "127.0.0.1"})
        )
        return cls(
            app_name=os.environ.get("CHATRAG_APP_NAME", "ChatRAG"),
            embed_dim=int(os.environ.get("CHATRAG_EMBED_DIM", DEFAULT_EMBED_DIM)),
            nim_embed_url=os.environ.get("CHATRAG_NIM_EMBED_URL", "http://localhost:8002"),
            nim_rerank_url=os.environ.get("CHATRAG_NIM_RERANK_URL", "http://localhost:8003"),
            nim_chat_url=os.environ.get("CHATRAG_NIM_CHAT_URL", "http://localhost:8004"),
            egress_allowed_hosts=allowed,
            voice_enabled=os.environ.get("CHATRAG_VOICE_ENABLED", "0") == "1",
        )
