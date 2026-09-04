"""Interfaz de voz de ChatRAG sobre `tribu-voice` — **stub apagado**.

Reemplaza al ElevenLabs del prototipo (proveedor cloud, incompatible con la constitución
on-prem del SDK). `tribu-voice` está **BLOQUEADO por revisión legal NVIDIA** (Product Specific
Terms §C.1.1 prohíbe reconocimiento de emociones; §C.1.2 restringe la clonación de voz): con
Riva, solo voces stock, nunca clonación. Hasta que la revisión pase, esta capa existe como
contrato con el flag apagado — no se despliega voz. Encenderla es una decisión de producto +
legal, por entorno (`CHATRAG_VOICE_ENABLED=1`), nunca un default.
"""

from __future__ import annotations


class VoiceDisabledError(RuntimeError):
    """Se intentó usar la voz con el flag apagado. Fail-closed: el bloqueo legal es real."""

    def __init__(self) -> None:
        super().__init__(
            "tribu-voice está deshabilitado: bloqueo legal NVIDIA pendiente (Product Specific "
            "Terms §C.1.1/§C.1.2). No se sirve voz hasta la aprobación. Reemplaza al ElevenLabs "
            "del prototipo — sin proveedores cloud de voz."
        )


class VoiceSession:
    """Sesión de voz. Con el flag apagado (por defecto) toda operación falla-cerrado. La
    implementación real se enchufará a `tribu-voice` (Riva stock, token efímero, avatar
    conmutable) cuando se levante el bloqueo legal."""

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start(self) -> str:  # pragma: no cover - la rama real requiere el registry + aprobación
        """Arranca una sesión de voz. Lanza `VoiceDisabledError` mientras el flag esté apagado."""

        if not self._enabled:
            raise VoiceDisabledError()
        from tribu_voice import RivaVoiceSession  # type: ignore[import-not-found]

        return RivaVoiceSession().mint_ephemeral_token()  # type: ignore[no-any-return]
