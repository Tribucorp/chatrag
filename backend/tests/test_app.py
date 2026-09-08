from collections.abc import Sequence

from fastapi.testclient import TestClient

from chatrag_api.app import create_app
from chatrag_api.config import Settings
from chatrag_api.models import Citation


class FakeRetriever:
    def __init__(self, citations: Sequence[Citation]) -> None:
        self._citations = list(citations)

    def retrieve(self, question: str, *, top_k: int) -> Sequence[Citation]:
        return self._citations[:top_k]


class FakeGenerator:
    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        return "resumen de prueba"


def _client(citations: Sequence[Citation]) -> TestClient:
    settings = Settings(app_name="ChatRAG-test")
    app = create_app(
        settings=settings, retriever=FakeRetriever(citations), generator=FakeGenerator()
    )
    return TestClient(app)


def test_health_reporta_estado_y_voz_apagada():
    client = _client([])
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["embed_dim"] == 2048  # default del SDK
    assert body["voice_enabled"] is False


def test_query_sin_identidad_es_401():
    client = _client([Citation(text="x", source_uri="doc://p", score=0.9)])
    resp = client.post("/query", json={"question": "¿horario?"})
    assert resp.status_code == 401


def test_query_sin_identidad_con_dev_bypass_no_es_401():
    settings = Settings(app_name="ChatRAG-test", dev_identity_bypass="dev-local")
    app = create_app(
        settings=settings,
        retriever=FakeRetriever([Citation(text="x", source_uri="doc://p", score=0.9)]),
        generator=FakeGenerator(),
    )
    client = TestClient(app)
    resp = client.post("/query", json={"question": "¿horario?"})
    assert resp.status_code == 200


def test_dev_bypass_no_se_activa_si_llega_identidad_real():
    settings = Settings(app_name="ChatRAG-test", dev_identity_bypass="dev-local")
    citations = [
        Citation(
            text="secreto", source_uri="doc://fin", score=0.9, required_acl="finanzas"
        ),
    ]
    app = create_app(
        settings=settings, retriever=FakeRetriever(citations), generator=FakeGenerator()
    )
    client = TestClient(app)
    resp = client.post(
        "/query",
        json={"question": "¿nómina?"},
        headers={"X-User-Id": "u1", "X-User-Acls": ""},
    )
    assert resp.json()["abstained"] is True  # el bypass no le regala ACLs a un usuario real


def test_query_devuelve_citas_filtradas_por_acl():
    citations = [
        Citation(text="público", source_uri="doc://pub", title="pub", score=0.9),
        Citation(
            text="secreto", source_uri="doc://fin", title="fin", score=0.95,
            required_acl="finanzas",
        ),
    ]
    client = _client(citations)
    resp = client.post(
        "/query",
        json={"question": "¿nómina?"},
        headers={"X-User-Id": "u1", "X-User-Acls": "rrhh"},  # no tiene 'finanzas'
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is False
    uris = [c["source_uri"] for c in body["citations"]]
    assert uris == ["doc://pub"]  # la de finanzas se filtró en el servidor


def test_query_se_abstiene_si_todo_esta_restringido():
    citations = [
        Citation(
            text="secreto", source_uri="doc://fin", score=0.95, required_acl="finanzas"
        ),
    ]
    client = _client(citations)
    resp = client.post(
        "/query",
        json={"question": "¿nómina?"},
        headers={"X-User-Id": "u1", "X-User-Acls": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["abstained"] is True
