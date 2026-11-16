import asyncio
from collections.abc import Sequence

from fastapi.testclient import TestClient

from chatrag_api.app import create_app
from chatrag_api.config import Settings
from chatrag_api.models import Citation


class FakeRetriever:
    def __init__(self, citations: Sequence[Citation]) -> None:
        self._citations = list(citations)

    async def retrieve(
        self, question: str, *, top_k: int, requester_roles: frozenset[str]
    ) -> Sequence[Citation]:
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


def test_theme_publico_sin_auth_devuelve_el_default():
    # Sin theme.json en el repo (fallback de JsonFileThemeStore) esto es siempre el default —
    # a propósito no escribe nada (GET, nunca PUT), así que no ensucia el repo real al testear.
    client = _client([])
    resp = client.get("/theme")
    assert resp.status_code == 200
    assert resp.json()["app_name"] == "ChatRAG"


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
            text="secreto", source_uri="doc://fin", score=0.9, required_acl=frozenset({"finanzas"})
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
            required_acl=frozenset({"finanzas"}),
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
            text="secreto", source_uri="doc://fin", score=0.95, required_acl=frozenset({"finanzas"})
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


def test_query_sin_service_bearer_configurado_no_lo_exige():
    # Comportamiento actual preservado: sin service_bearer_token, ninguna cabecera Authorization
    # hace falta (default None = sin cambios respecto a antes de esta dependencia).
    client = _client([Citation(text="x", source_uri="doc://p", score=0.9)])
    resp = client.post(
        "/query", json={"question": "¿horario?"}, headers={"X-User-Id": "u1"}
    )
    assert resp.status_code == 200


def test_query_con_service_bearer_configurado_exige_bearer_correcto():
    settings = Settings(app_name="ChatRAG-test", service_bearer_token="s3cr3t0")
    app = create_app(
        settings=settings,
        retriever=FakeRetriever([Citation(text="x", source_uri="doc://p", score=0.9)]),
        generator=FakeGenerator(),
    )
    client = TestClient(app)

    sin_bearer = client.post(
        "/query", json={"question": "¿horario?"}, headers={"X-User-Id": "u1"}
    )
    assert sin_bearer.status_code == 401

    bearer_incorrecto = client.post(
        "/query",
        json={"question": "¿horario?"},
        headers={"X-User-Id": "u1", "Authorization": "Bearer incorrecto"},
    )
    assert bearer_incorrecto.status_code == 401

    bearer_correcto = client.post(
        "/query",
        json={"question": "¿horario?"},
        headers={"X-User-Id": "u1", "Authorization": "Bearer s3cr3t0"},
    )
    assert bearer_correcto.status_code == 200


def test_toda_respuesta_trae_x_request_id():
    client = _client([])
    resp = client.get("/health")
    assert resp.headers["x-request-id"]  # 12 chars hex, ver middleware.py


def test_rate_limit_devuelve_429_al_superar_el_maximo():
    settings = Settings(
        app_name="ChatRAG-test",
        dev_identity_bypass="dev-local",
        rate_limit_max_requests=1,
        rate_limit_window_seconds=60,
    )
    app = create_app(
        settings=settings,
        retriever=FakeRetriever([Citation(text="x", source_uri="doc://p", score=0.9)]),
        generator=FakeGenerator(),
    )
    client = TestClient(app)

    primera = client.post("/query", json={"question": "¿horario?"})
    assert primera.status_code == 200
    segunda = client.post("/query", json={"question": "¿horario de nuevo?"})
    assert segunda.status_code == 429


def test_rate_limit_desactivado_con_max_requests_cero():
    settings = Settings(
        app_name="ChatRAG-test", dev_identity_bypass="dev-local", rate_limit_max_requests=0
    )
    app = create_app(
        settings=settings,
        retriever=FakeRetriever([Citation(text="x", source_uri="doc://p", score=0.9)]),
        generator=FakeGenerator(),
    )
    client = TestClient(app)
    for _ in range(5):
        assert client.post("/query", json={"question": "¿horario?"}).status_code == 200


def test_query_con_timeout_responde_504():
    class SlowRetriever:
        async def retrieve(self, question, *, top_k, requester_roles):
            await asyncio.sleep(10)
            return []

    settings = Settings(
        app_name="ChatRAG-test", dev_identity_bypass="dev-local", query_timeout_seconds=0.05
    )
    app = create_app(settings=settings, retriever=SlowRetriever(), generator=FakeGenerator())
    client = TestClient(app)
    resp = client.post("/query", json={"question": "¿horario?"})
    assert resp.status_code == 504


def test_query_con_fallo_del_retriever_responde_502():
    class BrokenRetriever:
        async def retrieve(self, question, *, top_k, requester_roles):
            raise ConnectionError("NIM inalcanzable")

    settings = Settings(app_name="ChatRAG-test", dev_identity_bypass="dev-local")
    app = create_app(settings=settings, retriever=BrokenRetriever(), generator=FakeGenerator())
    client = TestClient(app)
    resp = client.post("/query", json={"question": "¿horario?"})
    assert resp.status_code == 502
