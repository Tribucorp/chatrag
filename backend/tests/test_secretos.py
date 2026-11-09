from __future__ import annotations

import stat

from chatrag_api.secretos import (
    GENERATED,
    MINIO_USER,
    ensure_secrets,
    read_secret,
    secret_from_env_or_dir,
)


def test_genera_todos_los_secretos_0600_en_dir_0700(tmp_path):
    d = tmp_path / "secretos"
    ensure_secrets(d)
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    for name in [*GENERATED, MINIO_USER]:
        f = d / name
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
        assert len(f.read_text()) >= 12
    assert read_secret(d, MINIO_USER).startswith("chatrag-")  # type: ignore[union-attr]


def test_es_idempotente_y_no_rota_secretos_existentes(tmp_path):
    ensure_secrets(tmp_path)
    antes = {n: read_secret(tmp_path, n) for n in GENERATED}
    ensure_secrets(tmp_path)
    assert {n: read_secret(tmp_path, n) for n in GENERATED} == antes


def test_secretos_distintos_entre_si(tmp_path):
    ensure_secrets(tmp_path)
    valores = [read_secret(tmp_path, n) for n in GENERATED]
    assert len(set(valores)) == len(valores)


def test_la_variable_de_entorno_gana_al_fichero(tmp_path, monkeypatch):
    ensure_secrets(tmp_path)
    monkeypatch.setenv("CHATRAG_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("CHATRAG_ADMIN_TOKEN", raising=False)
    assert secret_from_env_or_dir("CHATRAG_ADMIN_TOKEN", "admin_token") == read_secret(
        tmp_path, "admin_token"
    )
    monkeypatch.setenv("CHATRAG_ADMIN_TOKEN", "del-entorno")
    assert secret_from_env_or_dir("CHATRAG_ADMIN_TOKEN", "admin_token") == "del-entorno"


def test_sin_directorio_ni_entorno_no_hay_secreto(monkeypatch):
    monkeypatch.delenv("CHATRAG_SECRETS_DIR", raising=False)
    monkeypatch.delenv("CHATRAG_ADMIN_TOKEN", raising=False)
    assert secret_from_env_or_dir("CHATRAG_ADMIN_TOKEN", "admin_token") is None
