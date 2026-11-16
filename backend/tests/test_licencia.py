"""Puerta de licencia por host (licencia.py) contra el binding Rust real de tribu-licensing:
los sobres se firman con `tribu_licensing.sign_payload` y se verifican con `verify_envelope`.
`cryptography` solo genera el par de claves (lado emisor), igual que en los tests del SDK."""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from pathlib import Path

import pytest
import tribu_licensing as tl
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from chatrag_api import _licencia_horneada, licencia
from chatrag_api.app import create_app
from chatrag_api.config import Settings, _parse_public_keys
from chatrag_api.licencia import (
    LICENSE_FORMAT,
    LicenseConfig,
    LicenseGate,
    resolve_config,
    verificar,
)
from chatrag_api.models import Citation

NOW = 1_800_000_000
DIA = 86_400
KEY_ID = "chatrag-test"


class FakeRetriever:
    async def retrieve(
        self, question: str, *, top_k: int, requester_roles: frozenset[str]
    ) -> list[Citation]:
        return [
            Citation(
                chunk_id="c1",
                source_uri="https://www.munistgo.cl/tramite",
                text="El trámite se hace en línea.",
                score=0.9,
            )
        ]


class FakeGenerator:
    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        return "Se hace en línea [1]."


def _claves() -> tuple[bytes, bytes]:
    priv = Ed25519PrivateKey.generate()
    raw_priv = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    raw_pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return raw_priv, raw_pub


def _host(root: Path, machine_id: str, macs: Sequence[str]) -> Path:
    (root / "etc").mkdir(parents=True)
    (root / "etc/machine-id").write_text(machine_id + "\n")
    for i, mac in enumerate(macs):
        iface = root / f"sys/class/net/eth{i}"
        iface.mkdir(parents=True)
        (iface / "address").write_text(mac + "\n")
    return root


def _hashes(root: Path) -> list[str]:
    return list(tl.collect_host_component_hashes(root).hashes)


def _sobre(
    priv: bytes,
    *,
    hashes: Sequence[str] | None,
    required: int | None = None,
    issued: int = NOW - DIA,
    expires: int = NOW + 30 * DIA,
    grace: int = 7 * DIA,
    key_id: str = KEY_ID,
    fmt: str = LICENSE_FORMAT,
) -> str:
    payload: dict[str, object] = {
        "license_id": "lic-001",
        "tenant_id": "partner-demo",
        "site_id": "SITIO-01",
        "issued_at_unix": issued,
        "expires_at_unix": expires,
        "grace_period_seconds": grace,
        "features": ["chatrag"],
    }
    if hashes is not None:
        payload["fingerprint"] = {
            "hashes": sorted(hashes),
            "required_matches": required if required is not None else len(hashes),
        }
    raw = json.dumps(payload).encode()
    return json.dumps(
        {
            "format": fmt,
            "key_id": key_id,
            "payload_b64": base64.b64encode(raw).decode(),
            "signature_hex": tl.sign_payload(priv, raw).hex(),
        }
    )


class Reloj:
    """Reloj de pared y monotónico controlables."""

    def __init__(self, wall: float = NOW) -> None:
        self.wall = wall
        self.mono = 1000.0

    def avanzar(self, segundos: float) -> None:
        self.wall += segundos
        self.mono += segundos


@pytest.fixture
def escenario(tmp_path: Path):
    priv, pub = _claves()
    host = _host(
        tmp_path / "host",
        "4c4c4544003a5a10804eb2c04f4e3332",
        ["3c:ec:ef:12:34:56", "3c:ec:ef:12:34:57"],
    )
    license_file = tmp_path / "license.json"
    state_file = tmp_path / "estado.json"

    def config(**overrides: object) -> LicenseConfig:
        base: dict[str, object] = {
            "enforced": True,
            "trusted_keys": {KEY_ID: pub},
            "license_file": str(license_file),
            "host_root": str(host),
            "state_file": str(state_file),
            "horneada": False,
        }
        base.update(overrides)
        return LicenseConfig(**base)  # type: ignore[arg-type]

    return {
        "priv": priv,
        "pub": pub,
        "host": host,
        "license_file": license_file,
        "state_file": state_file,
        "config": config,
    }


def _gate(cfg: LicenseConfig, reloj: Reloj | None = None) -> LicenseGate:
    reloj = reloj or Reloj()
    return LicenseGate.from_config(cfg, wall_clock=lambda: reloj.wall, monotonic=lambda: reloj.mono)


def _client(gate: LicenseGate, **settings: object) -> TestClient:
    app = create_app(
        settings=Settings(rate_limit_max_requests=0, **settings),  # type: ignore[arg-type]
        retriever=FakeRetriever(),
        generator=FakeGenerator(),
        license_gate=gate,
    )
    return TestClient(app)


# --- Sin puerta: comportamiento de siempre ---------------------------------------------------


def test_por_defecto_la_puerta_esta_desactivada():
    gate = LicenseGate.from_config(resolve_config(Settings()))
    assert gate.estado() == "desactivada"
    client = _client(gate, dev_identity_bypass="dev")
    assert client.get("/health").json()["licencia"] == {"estado": "desactivada"}
    assert client.post("/query", json={"question": "¿cómo?"}).status_code == 200


# --- Licencia válida ---------------------------------------------------------------------------


def test_licencia_valida_deja_servir_y_persiste_el_reloj(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]))
    )
    gate = _gate(escenario["config"]())
    assert gate.estado() == "valida"
    assert json.loads(escenario["state_file"].read_text()) == {"last_seen_unix": NOW}

    client = _client(gate, dev_identity_bypass="dev")
    salud = client.get("/health").json()["licencia"]
    assert salud["estado"] == "valida"
    assert salud["site_id"] == "SITIO-01"
    assert "hashes" not in json.dumps(salud)
    assert client.post("/query", json={"question": "¿cómo?"}).status_code == 200


def test_huella_tolerante_a_un_componente_cambiado(escenario):
    hashes = _hashes(escenario["host"])  # machine-id + 2 MAC
    otro = _hashes(_host(escenario["host"].parent / "otro", "a" * 32, ["00:11:22:33:44:55"]))
    # Licencia emitida con una MAC que ya no está (tarjeta cambiada): 2 de 3 bastan.
    licencia_hashes = hashes[:2] + otro[:1]
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=licencia_hashes, required=2)
    )
    assert _gate(escenario["config"]()).estado() == "valida"


# --- Modo inerte -------------------------------------------------------------------------------


def _assert_inerte(gate: LicenseGate, motivo: str) -> None:
    assert gate.estado() == "inerte"
    assert gate.motivo == motivo


def test_sin_fichero_de_licencia_es_inerte_y_solo_responde_lo_permitido(escenario):
    gate = _gate(escenario["config"]())
    _assert_inerte(gate, "sin_licencia")

    client = _client(gate, dev_identity_bypass="dev", admin_token="adm")
    r = client.post("/query", json={"question": "¿cómo?"})
    assert r.status_code == 503
    assert r.json()["licencia"] == "sin_licencia"
    assert "x-request-id" in r.headers
    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["licencia"]["estado"] == "inerte"
    assert client.get("/theme").status_code == 200
    # Lista blanca, no lista negra: lo demás de /admin y rutas desconocidas también caen.
    assert (
        client.get("/admin/index-status", headers={"Authorization": "Bearer adm"}).status_code
        == 503
    )
    assert client.get("/no-existe").status_code == 503
    assert client.get("/docs").status_code == 503


def test_admin_licencia_devuelve_la_solicitud_de_huella_en_modo_inerte(escenario):
    gate = _gate(escenario["config"]())
    client = _client(gate, admin_token="adm", license_host_root=str(escenario["host"]))
    assert client.get("/admin/licencia").status_code == 401
    r = client.get("/admin/licencia", headers={"Authorization": "Bearer adm"})
    assert r.status_code == 200
    body = r.json()
    assert body["puerta"]["motivo"] == "sin_licencia"
    assert body["solicitud"]["format"] == "tribu-host-component/v1"
    assert body["solicitud"]["hashes"] == _hashes(escenario["host"])


def test_licencia_de_otro_host_es_inerte(escenario):
    otro = _hashes(_host(escenario["host"].parent / "otro", "b" * 32, ["00:11:22:33:44:66"]))
    escenario["license_file"].write_text(_sobre(escenario["priv"], hashes=otro))
    _assert_inerte(_gate(escenario["config"]()), "otro_host")


def test_licencia_sin_huella_es_inerte(escenario):
    escenario["license_file"].write_text(_sobre(escenario["priv"], hashes=None))
    _assert_inerte(_gate(escenario["config"]()), "sin_huella")


def test_licencia_firmada_con_otra_clave_es_inerte(escenario):
    otra_priv, _ = _claves()
    escenario["license_file"].write_text(_sobre(otra_priv, hashes=_hashes(escenario["host"])))
    _assert_inerte(_gate(escenario["config"]()), "invalid_signature")


def test_key_id_desconocido_es_inerte(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]), key_id="otro")
    )
    _assert_inerte(_gate(escenario["config"]()), "unknown_key")


def test_licencia_de_otro_producto_es_inerte(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]), fmt="visionforge-license/v1")
    )
    gate = _gate(escenario["config"]())
    assert gate.estado() == "inerte"
    assert gate.motivo in {"malformed", "invalid_payload"}


def test_sobre_basura_es_inerte(escenario):
    escenario["license_file"].write_text("no es json")
    _assert_inerte(_gate(escenario["config"]()), "malformed")


def test_sin_claves_de_confianza_es_inerte(escenario):
    _assert_inerte(_gate(escenario["config"](trusted_keys={})), "sin_claves")


# --- Caducidad y reloj ---------------------------------------------------------------------------


def test_en_gracia_sigue_sirviendo_y_luego_cae(escenario):
    escenario["license_file"].write_text(
        _sobre(
            escenario["priv"],
            hashes=_hashes(escenario["host"]),
            issued=NOW - 10 * DIA,
            expires=NOW - DIA,
        )
    )
    reloj = Reloj()
    gate = _gate(escenario["config"](), reloj)
    assert gate.estado() == "gracia"
    reloj.avanzar(7 * DIA)
    _assert_inerte(gate, "caducada")


def test_caducada_del_todo_al_arrancar_es_inerte(escenario):
    escenario["license_file"].write_text(
        _sobre(
            escenario["priv"],
            hashes=_hashes(escenario["host"]),
            issued=NOW - 60 * DIA,
            expires=NOW - 30 * DIA,
        )
    )
    _assert_inerte(_gate(escenario["config"]()), "caducada")


def test_caduca_con_el_servicio_en_marcha_aunque_se_atrase_el_reloj(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]), expires=NOW + DIA, grace=0)
    )
    reloj = Reloj()
    gate = _gate(escenario["config"](), reloj)
    assert gate.estado() == "valida"
    reloj.mono += 2 * DIA  # pasa el tiempo...
    reloj.wall -= 365 * DIA  # ...pero alguien atrasa el reloj de pared: no cuenta
    _assert_inerte(gate, "caducada")


def test_reloj_atrasado_entre_arranques_es_inerte(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]))
    )
    escenario["state_file"].write_text(json.dumps({"last_seen_unix": NOW + 10 * DIA}))
    _assert_inerte(_gate(escenario["config"]()), "reloj_atrasado")


def test_estado_del_reloj_danado_es_inerte(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]))
    )
    escenario["state_file"].write_text("{roto")
    _assert_inerte(_gate(escenario["config"]()), "estado_ilegible")


def test_estado_no_persistible_es_inerte(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]))
    )
    cfg = escenario["config"](state_file=str(escenario["host"] / "no-existe" / "estado.json"))
    _assert_inerte(_gate(cfg), "estado_no_persistible")


def test_el_reloj_se_persiste_periodicamente(escenario):
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]))
    )
    reloj = Reloj()
    gate = _gate(escenario["config"](), reloj)
    reloj.avanzar(licencia.PERSIST_EVERY_SECONDS + 1)
    assert gate.estado() == "valida"
    last = json.loads(escenario["state_file"].read_text())["last_seen_unix"]
    assert last == NOW + licencia.PERSIST_EVERY_SECONDS + 1


# --- Horneado: el entorno no puede apagar ni redirigir la puerta ------------------------------


def test_lo_horneado_manda_sobre_el_entorno(escenario, monkeypatch):
    _, pub_horneada = _claves()
    monkeypatch.setattr(_licencia_horneada, "ENFORCED", True)
    monkeypatch.setattr(_licencia_horneada, "TRUSTED_KEYS_HEX", {"tribu": pub_horneada.hex()})
    monkeypatch.setattr(_licencia_horneada, "STATE_FILE", str(escenario["state_file"]))
    # Un tercero apaga la puerta e instala SU clave por entorno, y se firma su propia licencia.
    settings = Settings(
        license_enforced=False,
        license_public_keys={KEY_ID: escenario["pub"]},
        license_state_file=None,
        license_file=str(escenario["license_file"]),
        license_host_root=str(escenario["host"]),
    )
    escenario["license_file"].write_text(
        _sobre(escenario["priv"], hashes=_hashes(escenario["host"]))
    )
    cfg = resolve_config(settings)
    assert cfg.enforced and cfg.horneada
    assert dict(cfg.trusted_keys) == {"tribu": pub_horneada}
    assert cfg.state_file == str(escenario["state_file"])
    _assert_inerte(_gate(cfg), "unknown_key")


def test_horneada_sin_fichero_de_estado_es_inerte(escenario):
    _assert_inerte(_gate(escenario["config"](horneada=True, state_file=None)), "sin_estado")


# --- Piezas sueltas ------------------------------------------------------------------------------


def test_verificar_es_pura(escenario):
    hashes = _hashes(escenario["host"])
    sobre = _sobre(escenario["priv"], hashes=hashes)
    ok = verificar(sobre, {KEY_ID: escenario["pub"]}, hashes, NOW)
    assert ok.motivo is None and ok.licencia is not None
    assert verificar(sobre, {KEY_ID: escenario["pub"]}, [], NOW).motivo == "otro_host"


def test_parse_public_keys():
    assert _parse_public_keys("") == {}
    assert _parse_public_keys(f"a:{'00' * 32}, b:{'11' * 32}") == {
        "a": bytes(32),
        "b": bytes([0x11]) * 32,
    }
    for malo in ("sin-separador", f":{'00' * 32}", "a:00", "a:zz"):
        with pytest.raises(ValueError):
            _parse_public_keys(malo)


def test_cli_huella_imprime_la_solicitud(escenario, monkeypatch, capsys):
    monkeypatch.setenv("CHATRAG_LICENSE_HOST_ROOT", str(escenario["host"]))
    assert licencia.main(["huella"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hashes"] == _hashes(escenario["host"])
    assert {c["tipo"] for c in out["componentes"]} == {"machine-id", "mac"}


def test_cli_estado_sale_con_1_si_inerte(escenario, monkeypatch, capsys):
    monkeypatch.setenv("CHATRAG_LICENSE_ENFORCEMENT", "1")
    monkeypatch.setenv("CHATRAG_LICENSE_PUBLIC_KEYS", f"{KEY_ID}:{escenario['pub'].hex()}")
    monkeypatch.setenv("CHATRAG_LICENSE_HOST_ROOT", str(escenario["host"]))
    monkeypatch.setenv("CHATRAG_LICENSE_FILE", str(escenario["license_file"]))
    assert licencia.main(["estado"]) == 1
    assert json.loads(capsys.readouterr().out)["motivo"] == "sin_licencia"
    escenario["license_file"].write_text(
        _sobre(
            escenario["priv"], hashes=_hashes(escenario["host"]), issued=1, expires=4_000_000_000
        )
    )
    assert licencia.main(["estado"]) == 0
