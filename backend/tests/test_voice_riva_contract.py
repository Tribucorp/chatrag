"""Contrato de cable con los NIM de Riva (Magpie TTS / Parakeet ASR), con un HTTP falso que
registra exactamente lo que se envía. El contrato es el del despliegue real en GB10 de X9Voz
y la guía de Speech NIM — ver docstring de `chatrag_api.voice`."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from typing import Any

import pytest

pytest.importorskip("tribu_voice", reason="requiere el SDK instalado (uv sync)")

from chatrag_api.theme import Theme
from chatrag_api.voice import (
    MAX_TTS_CHUNK_CHARS,
    TTS_SAMPLE_RATE_HZ,
    TribuVoiceService,
    VoiceBackendError,
    VoiceConfigError,
    pcm_from_wav,
    text_for_speech,
    wav_from_pcm,
)


def _wav(pcm: bytes, rate: int = TTS_SAMPLE_RATE_HZ) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


@dataclass
class _Resp:
    status_code: int = 200
    content: bytes = b""
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode(errors="replace")

    def json(self) -> dict[str, Any]:
        return self.payload


class _FakeHttp:
    def __init__(self, responses: list[_Resp]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = responses

    async def post(self, url: str, **kwargs: Any) -> _Resp:
        self.calls.append({"url": url, **kwargs})
        return self._responses.pop(0)


def _service(http: _FakeHttp, voice_id: str = "es-419.Female-1") -> TribuVoiceService:
    async def get_theme() -> Theme:
        return Theme(voice_id=voice_id)

    svc = TribuVoiceService(
        nim_tts_url="http://nim-tts:9000",
        nim_asr_url="http://nim-asr:9000",
        allowed_hosts=frozenset({"nim-tts", "nim-asr"}),
        get_theme=get_theme,
    )
    svc._http = http  # type: ignore[assignment]  # doble del TribuHttpClient
    return svc


def test_text_for_speech_quita_markdown_y_urls():
    assert text_for_speech("**Capital:** Santiago. Ver https://munistgo.cl/x") == [
        "Capital: Santiago. Ver"
    ]


def test_text_for_speech_trocea_sin_pasar_del_maximo():
    texto = ("Frase de prueba con varias palabras. " * 40).strip()
    chunks = text_for_speech(texto)
    assert len(chunks) > 1
    assert all(0 < len(c) <= MAX_TTS_CHUNK_CHARS for c in chunks)
    assert " ".join(chunks) == texto


def test_text_for_speech_corta_frases_sin_puntuacion_mas_largas_que_el_maximo():
    chunks = text_for_speech("palabra " * 100)
    assert all(len(c) <= MAX_TTS_CHUNK_CHARS for c in chunks)


def test_pcm_wav_ida_y_vuelta_y_formato_inesperado_falla():
    assert pcm_from_wav(wav_from_pcm(b"\x01\x00" * 10)) == b"\x01\x00" * 10
    with pytest.raises(VoiceBackendError):
        pcm_from_wav(_wav(b"\x00\x00", rate=16_000))
    with pytest.raises(VoiceBackendError):
        pcm_from_wav(b"no es un wav")


async def test_speak_usa_synthesize_multipart_con_voz_magpie_y_concatena():
    http = _FakeHttp([_Resp(content=_wav(b"\x01\x00")), _Resp(content=_wav(b"\x02\x00"))])
    svc = _service(http)
    token = (await svc.mint_session()).token_id
    texto = "Primera frase. " * 25 + "Segunda parte final."
    audio = await svc.speak(token_id=token, text=texto, emotion="neutral")

    assert len(http.calls) == len(text_for_speech(texto)) == 2
    call = http.calls[0]
    assert call["url"] == "http://nim-tts:9000/v1/audio/synthesize"
    form = {k: v[1] for k, v in call["files"].items()}
    assert form["voice"] == "Magpie-Multilingual.ES-US.Isabela"
    assert form["language"] == "es-US"
    assert form["sample_rate_hz"] == str(TTS_SAMPLE_RATE_HZ)
    assert pcm_from_wav(audio) == b"\x01\x00\x02\x00"


async def test_speak_con_emocion_distinta_de_neutral_falla_cerrado():
    http = _FakeHttp([])
    svc = _service(http)
    token = (await svc.mint_session()).token_id
    with pytest.raises(VoiceConfigError):
        await svc.speak(token_id=token, text="hola", emotion="happy")  # type: ignore[arg-type]
    assert http.calls == []


async def test_speak_con_voz_stock_sin_equivalente_magpie_falla_cerrado():
    http = _FakeHttp([])
    svc = _service(http, voice_id="en-US.Female-1")
    token = (await svc.mint_session()).token_id
    with pytest.raises(VoiceConfigError):
        await svc.speak(token_id=token, text="hello", emotion="neutral")
    assert http.calls == []


async def test_speak_error_del_nim_es_voice_backend_error():
    http = _FakeHttp([_Resp(status_code=500, content=b"boom")])
    svc = _service(http)
    token = (await svc.mint_session()).token_id
    with pytest.raises(VoiceBackendError):
        await svc.speak(token_id=token, text="hola", emotion="neutral")


async def test_transcribe_manda_wav_y_language_y_devuelve_texto():
    http = _FakeHttp([_Resp(payload={"text": "hola municipio"})])
    svc = _service(http)
    token = (await svc.mint_session()).token_id
    texto = await svc.transcribe(token_id=token, audio=b"RIFF...", content_type="audio/wav")

    assert texto == "hola municipio"
    call = http.calls[0]
    assert call["url"] == "http://nim-asr:9000/v1/audio/transcriptions"
    assert call["files"]["file"] == ("audio.wav", b"RIFF...", "audio/wav")
    assert call["data"] == {"language": "es-US"}
