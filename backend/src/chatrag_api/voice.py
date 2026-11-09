"""Interfaz de voz de ChatRAG sobre `tribu-voice` (síntesis TTS + avatar/marca + token efímero,
todo real y auditado — ver `~/repositorio/tribu-sdk/python/tribu-voice/`) más un cliente de ASR
propio de ChatRAG (reconocimiento de voz **no** es parte de `tribu-voice`: ese módulo solo cubre
salida — TTS, avatar, medición — nunca entrada de audio, precisamente porque §8.16 de las
Product-Specific Terms de NVIDIA prohíbe inferir el estado afectivo del interlocutor a partir de
audio de entrada; este cliente de ASR solo transcribe texto, nunca analiza tono/emoción).

Bloqueo legal: el propio README de `tribu-voice` decía "pendiente firma de abogado" cuando se
revisó el código fuente real (15-sep-2026); Javier confirmó explícitamente, dos veces, que esa
firma existe fuera de este repo. Lo que NO cambia con esa confirmación —porque no es un bloqueo
temporal de revisión, es una restricción estructural del propio `tribu_voice`— es: solo voces
**stock** del catálogo (`StockVoice`, nunca un campo de voz de referencia) y ninguna entrada de
audio del usuario usada para inferir su estado emocional.

Contrato de red **sin verificar contra un NIM Riva real** (no hay ninguna imagen NIM de Riva
pineada en ningún sitio del SDK, ver CLAUDE.md) — `RivaVoiceSynthesizer`/`RivaAsrClient` asumen
el mismo patrón `/v1/...` OpenAI-compatible que el resto de NIMs de este proyecto (chat, embed,
rerank), por consistencia con esa convención, NO porque esté confirmado en documentación real de
Riva. Confirmar contra el NIM real antes de desplegar (mismo criterio que
`nim_rerank_model_id` en `config.py`: convención razonable, no un hecho verificado)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from tribu_http.client import TribuHttpClient
    from tribu_voice import AgentFace, EphemeralToken, TokenScope

from pydantic import BaseModel, ConfigDict

from chatrag_api.theme import Theme


class VoiceDisabledError(RuntimeError):
    """Se intentó usar la voz con el flag apagado. Fail-closed: mientras
    `CHATRAG_VOICE_ENABLED` no esté en `1`, no se sirve voz — sea por bloqueo legal pendiente o
    porque el operador de este despliegue concreto no la quiere encendida."""

    def __init__(self) -> None:
        super().__init__(
            "voz deshabilitada (CHATRAG_VOICE_ENABLED=0). Cuando se active: solo voces stock "
            "de tribu-voice, nunca clonación; nunca se infiere el estado emocional del usuario "
            "a partir de su audio — eso es una restricción estructural, no una configuración."
        )


class VoiceTokenError(RuntimeError):
    """Token de sesión de voz inválido, caducado, o sin el alcance necesario — envuelve
    `TokenExpiredError`/`InsufficientScopeError`/`UnknownFaceError` de `tribu_voice` (mismo
    principio que el resto del módulo: la capa pública de ChatRAG no expone tipos de tribu_voice
    directamente, solo primitivos, así que el Protocol de abajo no necesita que el paquete esté
    instalado para que mypy lo resuelva)."""


class VoiceConfigError(RuntimeError):
    """`Theme.voice_id` (configurable desde `/admin/theme`) no está en el catálogo stock real
    de `tribu_voice` — envuelve el `pydantic.ValidationError` que lanza `VoiceBrand` al
    construirse. Fail-closed: no se sintetiza con una voz inventada; el admin tiene que elegir
    una del catálogo real."""


class VoiceSessionInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    token_id: str
    face_id: str
    expires_at: float


Emotion = Literal["neutral", "calm", "happy"]


class SpeakRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    token_id: str
    text: str
    emotion: Emotion = "neutral"


class VoiceService(Protocol):
    """Contrato mínimo del servicio de voz. Lo implementa `TribuVoiceService` en producción y
    `FakeVoiceService` en tests — mismo patrón que `Retriever`/`ChatGenerator`/`Ingestor`."""

    async def mint_session(self) -> VoiceSessionInfo: ...

    async def speak(self, *, token_id: str, text: str, emotion: Emotion) -> bytes:
        """Devuelve audio sintetizado. Lanza `VoiceTokenError` si el token no es válido."""
        ...

    async def transcribe(self, *, token_id: str, audio: bytes, content_type: str) -> str:
        """Transcribe audio a texto. Lanza `VoiceTokenError` si el token no es válido."""
        ...


class FakeVoiceService:
    """Doble de test: no toca ningún NIM ni tribu_voice. `spoken`/`transcribed` registran las
    llamadas para que un test afirme sobre ellas."""

    def __init__(self) -> None:
        self.spoken: list[tuple[str, Emotion]] = []
        self.transcribed: list[bytes] = []
        self._tokens: set[str] = set()

    async def mint_session(self) -> VoiceSessionInfo:
        token_id = str(uuid.uuid4())
        self._tokens.add(token_id)
        return VoiceSessionInfo(token_id=token_id, face_id="santiago", expires_at=time.time() + 300)

    async def speak(self, *, token_id: str, text: str, emotion: Emotion) -> bytes:
        if token_id not in self._tokens:
            raise VoiceTokenError(f"token desconocido: {token_id}")
        self.spoken.append((text, emotion))
        return f"[audio:{emotion}:{text}]".encode()

    async def transcribe(self, *, token_id: str, audio: bytes, content_type: str) -> str:
        if token_id not in self._tokens:
            raise VoiceTokenError(f"token desconocido: {token_id}")
        self.transcribed.append(audio)
        return "(transcripción de prueba)"


class TribuVoiceService:  # pragma: no cover - requiere el NIM Riva real
    """Adaptador de producción. Import perezoso de `tribu_voice`/`tribu_http` completo (mismo
    motivo que el resto del backend: los tests corren sin el NIM).

    Registro de tokens **en memoria, sin firmar** — `tribu_voice` deja la firma real
    (Ed25519/JWT) explícitamente para `tribu-auth` (ver su docstring), que solo existe en
    TypeScript (`@tribu/auth`) — no hay firma equivalente consumible desde este backend Python. Mientras tanto, esto es la máquina
    de estados de validez (`check_token`, real) sin la garantía criptográfica de que el
    `token_id` no se pueda adivinar/forjar — aceptable para un piloto de un solo proceso, no
    para producción multi-instancia (un token minteado en un worker no lo reconoce otro)."""

    def __init__(
        self,
        *,
        nim_tts_url: str,
        nim_asr_url: str,
        allowed_hosts: frozenset[str],
        get_theme: Callable[[], Awaitable[Theme]],
    ) -> None:
        self._nim_tts_url = nim_tts_url.rstrip("/")
        self._nim_asr_url = nim_asr_url.rstrip("/")
        self._allowed_hosts = allowed_hosts
        self._get_theme = get_theme
        self._tokens: dict[str, EphemeralToken] = {}
        self._http: TribuHttpClient | None = None

    def _ensure_http(self) -> TribuHttpClient:
        if self._http is None:
            from tribu_http.client import TribuHttpClient
            from tribu_http.egress import EgressAllowlist

            self._http = TribuHttpClient(EgressAllowlist(allowed_hosts=self._allowed_hosts))
        return self._http

    async def _build_face_from_theme(self) -> AgentFace:
        """Cara única de ChatRAG, construida en cada llamada (no cacheada) a partir del tema
        actual (`Theme.app_name` de marca, `Theme.voice_id` de voz — configurable desde
        `/admin/theme` sin redeploy). Reconstruir en cada sesión, en vez de cachear al primer
        uso, es lo que hace que un cambio de voz en el admin aplique a la siguiente sesión sin
        reiniciar el proceso."""

        from pydantic import ValidationError
        from tribu_voice import AgentFace, VoiceBrand

        theme = await self._get_theme()
        try:
            brand = VoiceBrand(brand_name=theme.app_name, voice_id=theme.voice_id)
        except ValidationError as exc:
            raise VoiceConfigError(
                f"Theme.voice_id={theme.voice_id!r} no está en el catálogo stock de tribu_voice "
                "— elige una voz válida desde /admin/theme."
            ) from exc
        return AgentFace(face_id="default", avatar_id="orb", brand=brand)

    async def mint_session(self) -> VoiceSessionInfo:
        from tribu_voice import TokenScope, mint_ephemeral_token

        face = await self._build_face_from_theme()
        now = time.time()
        token = mint_ephemeral_token(
            token_id=str(uuid.uuid4()),
            face=face,
            scope=TokenScope.SPEAK,  # cubre LISTEN implícito + turnos de conversación por voz
            now=now,
            ttl_seconds=300,
        )
        self._tokens[token.token_id] = token
        return VoiceSessionInfo(
            token_id=token.token_id,
            face_id=face.face_id,
            expires_at=token.expires_at,
        )

    def _check(self, token_id: str, *, required_scope: TokenScope) -> EphemeralToken:
        from tribu_voice import (
            InsufficientScopeError,
            TokenExpiredError,
            check_token,
        )

        token = self._tokens.get(token_id)
        if token is None:
            raise VoiceTokenError(f"token desconocido o no minteado por este proceso: {token_id}")
        try:
            check_token(token, now=time.time(), required_scope=required_scope)
        except (TokenExpiredError, InsufficientScopeError) as exc:
            raise VoiceTokenError(str(exc)) from exc
        return token

    async def speak(self, *, token_id: str, text: str, emotion: Emotion) -> bytes:
        from tribu_voice import (
            SpeechRequest,
            SsmlEmotion,
            TokenScope,
        )

        self._check(token_id, required_scope=TokenScope.SPEAK)
        # Se re-deriva del tema actual (no del que había al mintear la sesión): si el admin
        # cambió la voz entre `mint_session` y `speak`, usa la vigente — el token solo
        # garantiza que la sesión es válida (alcance/caducidad), no fija qué voz sonará.
        face = await self._build_face_from_theme()
        request = SpeechRequest(text=text, brand=face.brand, emotion=SsmlEmotion(emotion))

        http = self._ensure_http()
        # Contrato sin verificar (ver docstring del módulo): asume forma OpenAI-compatible
        # como el resto de NIMs de este proyecto, no confirmado contra un NIM Riva TTS real.
        response = await http.post(
            f"{self._nim_tts_url}/v1/audio/speech",
            json={
                "input": request.text,
                "voice": request.brand.voice_id,
                "response_format": "wav",
            },
        )
        response.raise_for_status()
        return response.content

    async def transcribe(self, *, token_id: str, audio: bytes, content_type: str) -> str:
        from tribu_voice import TokenScope

        self._check(token_id, required_scope=TokenScope.SPEAK)
        http = self._ensure_http()
        # Contrato sin verificar (ver docstring del módulo): mismo shape que la API de
        # transcripción de OpenAI (multipart, campo "file"), convención habitual en NIMs de
        # ASR — no confirmado contra un NIM Riva ASR real.
        response = await http.post(
            f"{self._nim_asr_url}/v1/audio/transcriptions",
            files={"file": ("audio", audio, content_type)},
        )
        response.raise_for_status()
        data = response.json()
        text: str = data["text"]
        return text


def tribu_voice_service(
    *,
    nim_tts_url: str,
    nim_asr_url: str,
    allowed_hosts: frozenset[str],
    get_theme: Callable[[], Awaitable[Theme]],
) -> VoiceService:
    return TribuVoiceService(
        nim_tts_url=nim_tts_url,
        nim_asr_url=nim_asr_url,
        allowed_hosts=allowed_hosts,
        get_theme=get_theme,
    )
