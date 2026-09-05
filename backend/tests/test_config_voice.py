import pytest

from chatrag_api.config import DEFAULT_EMBED_DIM, Settings
from chatrag_api.voice import VoiceDisabledError, VoiceSession


def test_default_embed_dim_es_2048():
    assert DEFAULT_EMBED_DIM == 2048
    assert Settings().embed_dim == 2048


def test_from_env_defaults_on_prem(monkeypatch):
    for var in (
        "CHATRAG_APP_NAME",
        "CHATRAG_EMBED_DIM",
        "CHATRAG_VOICE_ENABLED",
        "CHATRAG_EGRESS_HOSTS",
    ):
        monkeypatch.delenv(var, raising=False)
    settings = Settings.from_env()
    assert settings.voice_enabled is False  # tribu-voice apagado por defecto
    assert "localhost" in settings.egress_allowed_hosts
    assert settings.nim_embed_url.startswith("http://")


def test_voice_flag_por_entorno(monkeypatch):
    monkeypatch.setenv("CHATRAG_VOICE_ENABLED", "1")
    assert Settings.from_env().voice_enabled is True


def test_voice_session_apagada_falla_cerrado():
    session = VoiceSession(enabled=False)
    assert session.enabled is False
    with pytest.raises(VoiceDisabledError):
        session.start()
