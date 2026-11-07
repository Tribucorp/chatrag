from fastapi.testclient import TestClient

from chatrag_api import admin
from chatrag_api.app import create_app
from chatrag_api.config import Settings
from chatrag_api.ingest import FakeIngestor, IngestReport


class _NullRetriever:
    async def retrieve(self, question, *, top_k, requester_roles):
        return []


class _NullGenerator:
    async def generate(self, question, citations):
        return ""


def _client(
    *,
    admin_token: str | None = "s3cr3t0",
    knowledge_dir: str = "/tmp",
    theme_file: str = "/tmp/chatrag-test-theme-unused.json",
) -> TestClient:
    settings = Settings(
        app_name="ChatRAG-test",
        admin_token=admin_token,
        knowledge_dir=knowledge_dir,
        theme_file=theme_file,
    )
    app = create_app(settings=settings, retriever=_NullRetriever(), generator=_NullGenerator())
    return TestClient(app)


def test_admin_sin_token_configurado_responde_503():
    client = _client(admin_token=None)
    resp = client.get("/admin/index-status", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 503


def test_admin_sin_bearer_responde_401():
    client = _client()
    resp = client.get("/admin/index-status")
    assert resp.status_code == 401


def test_admin_con_bearer_incorrecto_responde_401():
    client = _client()
    resp = client.get(
        "/admin/index-status", headers={"Authorization": "Bearer incorrecto"}
    )
    assert resp.status_code == 401


def test_index_status_con_bearer_correcto(tmp_path):
    (tmp_path / "a.md").write_text("hola\n\nmundo")
    client = _client(knowledge_dir=str(tmp_path))
    resp = client.get(
        "/admin/index-status", headers={"Authorization": "Bearer s3cr3t0"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_files"] == ["a.md"]
    assert body["tenant_id"] == "chatrag-santiago"


def test_reindex_usa_el_ingestor_inyectado(tmp_path):
    (tmp_path / "a.md").write_text("hola\n\nmundo")
    (tmp_path / "b.md").write_text("otro doc")
    client = _client(knowledge_dir=str(tmp_path))
    fake = FakeIngestor()
    client.app.dependency_overrides[admin.get_ingestor] = lambda: fake  # type: ignore[attr-defined]
    try:
        resp = client.post("/admin/reindex", headers={"Authorization": "Bearer s3cr3t0"})
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert resp.status_code == 200
    reports = [IngestReport(**r) for r in resp.json()]
    assert {r.document_id for r in reports} == {"a.md", "b.md"}
    assert fake.calls == [tmp_path]


def test_reindex_sin_knowledge_dir_responde_404():
    client = _client(knowledge_dir="/no/existe/de/verdad")
    resp = client.post("/admin/reindex", headers={"Authorization": "Bearer s3cr3t0"})
    assert resp.status_code == 404


def test_audit_sin_configurar_responde_503():
    client = _client()
    resp = client.get("/admin/audit", headers={"Authorization": "Bearer s3cr3t0"})
    assert resp.status_code == 503


def test_theme_get_devuelve_el_default_sin_fichero_todavia(tmp_path):
    client = _client(theme_file=str(tmp_path / "theme.json"))
    resp = client.get("/admin/theme", headers={"Authorization": "Bearer s3cr3t0"})
    assert resp.status_code == 200
    assert resp.json()["app_name"] == "ChatRAG"


def test_theme_put_persiste_y_get_lo_devuelve(tmp_path):
    client = _client(theme_file=str(tmp_path / "theme.json"))
    put_resp = client.put(
        "/admin/theme",
        headers={"Authorization": "Bearer s3cr3t0"},
        json={"app_name": "Municipalidad Demo", "color_accent": "#00ff00"},
    )
    assert put_resp.status_code == 200

    get_resp = client.get("/admin/theme", headers={"Authorization": "Bearer s3cr3t0"})
    assert get_resp.json()["app_name"] == "Municipalidad Demo"
    assert get_resp.json()["color_accent"] == "#00ff00"


def test_theme_sin_bearer_responde_401(tmp_path):
    client = _client(theme_file=str(tmp_path / "theme.json"))
    resp = client.get("/admin/theme")
    assert resp.status_code == 401


def test_upload_source_ingesta_un_solo_documento_y_lo_persiste(tmp_path):
    client = _client(knowledge_dir=str(tmp_path))
    fake = FakeIngestor()
    client.app.dependency_overrides[admin.get_ingestor] = lambda: fake  # type: ignore[attr-defined]
    try:
        resp = client.post(
            "/admin/sources",
            headers={"Authorization": "Bearer s3cr3t0"},
            json={"document_id": "nueva.md", "text": "contenido\n\nsegundo párrafo"},
        )
    finally:
        client.app.dependency_overrides.clear()  # type: ignore[attr-defined]

    assert resp.status_code == 200
    report = IngestReport(**resp.json())
    assert report.document_id == "nueva.md"
    assert report.chunks == 2
    # se persiste en knowledge_dir para que un futuro /admin/reindex también lo recoja
    assert (tmp_path / "nueva.md").read_text(encoding="utf-8") == "contenido\n\nsegundo párrafo"


def test_upload_source_rechaza_document_id_con_ruta(tmp_path):
    client = _client(knowledge_dir=str(tmp_path))
    resp = client.post(
        "/admin/sources",
        headers={"Authorization": "Bearer s3cr3t0"},
        json={"document_id": "../fuera.md", "text": "x"},
    )
    assert resp.status_code == 400
    assert not (tmp_path.parent / "fuera.md").exists()


def test_upload_source_rechaza_extension_distinta_de_md(tmp_path):
    client = _client(knowledge_dir=str(tmp_path))
    resp = client.post(
        "/admin/sources",
        headers={"Authorization": "Bearer s3cr3t0"},
        json={"document_id": "script.sh", "text": "x"},
    )
    assert resp.status_code == 400


def test_conversations_sin_bearer_responde_401():
    client = _client()
    resp = client.get("/admin/conversations")
    assert resp.status_code == 401


def test_conversations_devuelve_lo_registrado_en_query(tmp_path):
    from chatrag_api.models import Citation

    class _OneCitationRetriever:
        async def retrieve(self, question, *, top_k, requester_roles):
            return [Citation(text="x", source_uri="doc://p", title="p", score=0.9)]

    class _EchoGenerator:
        async def generate(self, question, citations):
            return "respuesta de prueba"

    settings = Settings(
        app_name="ChatRAG-test",
        admin_token="s3cr3t0",
        dev_identity_bypass="dev-local",
        knowledge_dir=str(tmp_path),
        theme_file=str(tmp_path / "theme.json"),
    )
    app = create_app(
        settings=settings, retriever=_OneCitationRetriever(), generator=_EchoGenerator()
    )
    client = TestClient(app)

    query_resp = client.post("/query", json={"question": "¿horario?"})
    assert query_resp.status_code == 200

    conv_resp = client.get(
        "/admin/conversations", headers={"Authorization": "Bearer s3cr3t0"}
    )
    assert conv_resp.status_code == 200
    entries = conv_resp.json()
    assert len(entries) == 1
    assert entries[0]["question"] == "¿horario?"
    assert entries[0]["answer"] == "respuesta de prueba"
    assert entries[0]["abstained"] is False
    assert entries[0]["citations_shown"] == ["doc://p"]

    metrics_resp = client.get("/admin/metrics", headers={"Authorization": "Bearer s3cr3t0"})
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["total_queries"] == 1
    assert metrics["total_answered"] == 1
    assert metrics["total_abstained"] == 0
    assert metrics["top_sources"][0]["source_uri"] == "doc://p"


def test_metrics_sin_bearer_responde_401():
    client = _client()
    resp = client.get("/admin/metrics")
    assert resp.status_code == 401
