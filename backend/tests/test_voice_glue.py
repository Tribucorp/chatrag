from fastapi.testclient import TestClient

from chatrag_api.app import create_app
from chatrag_api.config import Settings
from chatrag_api.voice import FakeVoiceService


class _NullRetriever:
    async def retrieve(self, question, *, top_k, requester_roles):
        return []


class _NullGenerator:
    async def generate(self, question, citations):
        return ""


def _client(*, voice_service=None) -> TestClient:
    settings = Settings(app_name="ChatRAG-test")
    app = create_app(
        settings=settings,
        retriever=_NullRetriever(),
        generator=_NullGenerator(),
        voice_service=voice_service,
    )
    return TestClient(app)


def test_voice_session_sin_servicio_responde_503():
    client = _client()
    resp = client.post("/voice/session")
    assert resp.status_code == 503


def test_voice_session_mintea_token():
    client = _client(voice_service=FakeVoiceService())
    resp = client.post("/voice/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["face_id"] == "santiago"
    assert body["token_id"]


def test_voice_speak_con_token_valido_devuelve_audio():
    fake = FakeVoiceService()
    client = _client(voice_service=fake)
    session = client.post("/voice/session").json()

    resp = client.post(
        "/voice/speak",
        json={"token_id": session["token_id"], "text": "hola", "emotion": "happy"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert resp.content == b"[audio:happy:hola]"
    assert fake.spoken == [("hola", "happy")]


def test_voice_speak_con_token_invalido_responde_401():
    client = _client(voice_service=FakeVoiceService())
    resp = client.post(
        "/voice/speak", json={"token_id": "no-existe", "text": "hola", "emotion": "neutral"}
    )
    assert resp.status_code == 401


def test_voice_transcribe_con_token_valido():
    fake = FakeVoiceService()
    client = _client(voice_service=fake)
    session = client.post("/voice/session").json()

    resp = client.post(
        "/voice/transcribe",
        content=b"audio-fake-bytes",
        headers={"x-voice-token": session["token_id"], "content-type": "audio/wav"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"text": "(transcripción de prueba)"}
    assert fake.transcribed == [b"audio-fake-bytes"]


def test_voice_transcribe_con_token_invalido_responde_401():
    client = _client(voice_service=FakeVoiceService())
    resp = client.post(
        "/voice/transcribe",
        content=b"audio",
        headers={"x-voice-token": "no-existe"},
    )
    assert resp.status_code == 401
