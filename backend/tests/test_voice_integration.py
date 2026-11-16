"""Prueba de humo contra `tribu-voice` real (no dobles) — mismo patrón que
`test_guardrails_integration.py`/`test_sdk_integration.py`. API confirmada leyendo el código
fuente real del SDK en `~/repositorio/tribu-sdk/python/tribu-voice/`; el corpus de x9 no tenía
referencia documentada.

Marcada `integration`, requiere el SDK instalado (uv sync) — ver docstring de
`test_sdk_integration.py`. No llama a ningún NIM Riva real (no hay uno pineado en el SDK
todavía, ver `voice.py`): valida instalación + la máquina de estados de tokens/caras, que es lo
único que no depende de la red.
"""

from __future__ import annotations

import asyncio
import time

import pytest

pytest.importorskip("tribu_voice", reason="requiere el SDK instalado (uv sync)")

pytestmark = pytest.mark.integration


def test_face_registry_construye_la_cara_real_de_chatrag():
    from tribu_voice import AgentFace, FaceRegistry, VoiceBrand

    registry = FaceRegistry(
        faces=(
            AgentFace(
                face_id="santiago",
                avatar_id="orb",
                brand=VoiceBrand(
                    brand_name="Asistente de la comuna de Santiago", voice_id="es-419.Female-1"
                ),
            ),
        )
    )
    face = registry.face("santiago")
    assert face.brand.voice_id == "es-419.Female-1"


def test_voice_id_fuera_de_catalogo_falla_cerrado():
    # `UnknownStockVoiceError` se lanza dentro de un @field_validator de pydantic — pydantic
    # envuelve cualquier ValueError ahí en su propio ValidationError, así que lo que de verdad
    # propaga al caller es ValidationError, no la excepción original (comprobado contra el
    # paquete real; no asumido).
    from pydantic import ValidationError
    from tribu_voice import VoiceBrand

    with pytest.raises(ValidationError, match="no está en el catálogo stock"):
        VoiceBrand(brand_name="voz clonada falsa", voice_id="no-esta-en-el-catalogo")


def test_mint_y_check_token_real():
    from tribu_voice import AgentFace, TokenScope, VoiceBrand, check_token, mint_ephemeral_token

    face = AgentFace(
        face_id="santiago",
        avatar_id="orb",
        brand=VoiceBrand(brand_name="Asistente", voice_id="es-419.Female-1"),
    )
    now = time.time()
    token = mint_ephemeral_token(
        token_id="t1", face=face, scope=TokenScope.SPEAK, now=now, ttl_seconds=300
    )
    check_token(token, now=now + 10, required_scope=TokenScope.SPEAK)  # no debe lanzar


def test_check_token_caducado_falla_cerrado():
    from tribu_voice import (
        AgentFace,
        TokenExpiredError,
        TokenScope,
        VoiceBrand,
        check_token,
        mint_ephemeral_token,
    )

    face = AgentFace(
        face_id="santiago",
        avatar_id="orb",
        brand=VoiceBrand(brand_name="Asistente", voice_id="es-419.Female-1"),
    )
    now = time.time()
    token = mint_ephemeral_token(
        token_id="t1", face=face, scope=TokenScope.SPEAK, now=now, ttl_seconds=1
    )
    with pytest.raises(TokenExpiredError):
        check_token(token, now=now + 10, required_scope=TokenScope.SPEAK)


def test_tribu_voice_service_mintea_con_el_voice_id_del_tema():
    from chatrag_api.theme import Theme
    from chatrag_api.voice import TribuVoiceService

    theme = Theme(app_name="Asistente de prueba", voice_id="es-ES.Male-1")

    async def get_theme() -> Theme:
        return theme

    service = TribuVoiceService(
        nim_tts_url="http://localhost:8005",
        nim_asr_url="http://localhost:8006",
        allowed_hosts=frozenset({"localhost"}),
        get_theme=get_theme,
    )
    session = asyncio.run(service.mint_session())
    assert session.face_id == "default"

    face = asyncio.run(service._build_face_from_theme())
    assert face.brand.voice_id == "es-ES.Male-1"
    assert face.brand.brand_name == "Asistente de prueba"


def test_tribu_voice_service_con_voice_id_fuera_de_catalogo_falla_cerrado():
    from chatrag_api.theme import Theme
    from chatrag_api.voice import TribuVoiceService, VoiceConfigError

    theme = Theme(app_name="Asistente de prueba", voice_id="voz-inventada")

    async def get_theme() -> Theme:
        return theme

    service = TribuVoiceService(
        nim_tts_url="http://localhost:8005",
        nim_asr_url="http://localhost:8006",
        allowed_hosts=frozenset({"localhost"}),
        get_theme=get_theme,
    )
    with pytest.raises(VoiceConfigError, match="voz-inventada"):
        asyncio.run(service.mint_session())


def test_check_token_sin_alcance_suficiente_falla_cerrado():
    from tribu_voice import (
        AgentFace,
        InsufficientScopeError,
        TokenScope,
        VoiceBrand,
        check_token,
        mint_ephemeral_token,
    )

    face = AgentFace(
        face_id="santiago",
        avatar_id="orb",
        brand=VoiceBrand(brand_name="Asistente", voice_id="es-419.Female-1"),
    )
    now = time.time()
    token = mint_ephemeral_token(
        token_id="t1", face=face, scope=TokenScope.LISTEN, now=now, ttl_seconds=300
    )
    with pytest.raises(InsufficientScopeError):
        check_token(token, now=now, required_scope=TokenScope.SPEAK)
