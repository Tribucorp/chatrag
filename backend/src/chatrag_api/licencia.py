"""Puerta de licencia por host de la imagen de ChatRAG que se entrega a terceros.

Por qué existe: la imagen protegida (`deploy/Dockerfile.backend.protegido`) quita el código
fuente legible, pero no impide copiar la imagen a otra máquina. Esta puerta liga la ejecución
a un **sobre de licencia Ed25519** emitido por Tribu (`tribu-licensing`) que fija el sitio, la
caducidad y la **huella del host** (`fingerprint`: hashes `tribu-host-component/v1` de
machine-id, seriales NVMe, MAC físicas y serial DMI). Si algo no cuadra, el servicio cae a
**modo inerte**: degradación declarada, no un crash. `/health`, `/theme` y `/admin/licencia`
siguen respondiendo y todo lo demás devuelve 503. Es el mismo patrón que la puerta del nodo
x9 del SDK (`tribu_mcp_server/node_license.py`, `deploy/x9-node/EMPAQUE_PROTEGIDO.md`).

Qué decide Rust y qué decide este módulo:
- La crate (`tribu_licensing.verify_envelope`) verifica el sobre entero: `format`, `key_id` de
  confianza, firma sobre los bytes exactos del payload y esquema estricto, incluida la forma de
  la huella. El estado `valid/grace/expired` y el anti-rollback del reloj
  (`check_clock_rollback`) también se deciden en la crate. Aquí no se reimplementa nada de eso.
- Lo único que se decide en este módulo es la comparación de conjuntos de la huella: cuántos
  hashes del host aparecen entre los de la licencia, frente a `required_matches`. La crate solo
  la expone dentro de `unseal`, que abre artefactos sellados, y ChatRAG no sella nada. Los
  hashes del host también los calcula la crate (`collect_host_component_hashes`).

Configuración: la obligatoriedad, las claves públicas de confianza y el fichero de estado van
**horneados** en la imagen protegida (`_licencia_horneada`, compilado por Nuitka), no en el
entorno. En el repositorio la puerta está apagada y, para desarrollo, se puede encender por
entorno (`CHATRAG_LICENSE_ENFORCEMENT=1` + `CHATRAG_LICENSE_PUBLIC_KEYS`). Por entorno solo
se eligen dónde está el sobre (`CHATRAG_LICENSE_FILE`) y la raíz de los montajes del host
(`CHATRAG_LICENSE_HOST_ROOT`).

Reloj: tras el arranque, el «ahora» de la puerta es el reloj de pared del arranque más el
tiempo monotónico transcurrido, así que atrasar el reloj del sistema con el servicio en marcha
no alarga la licencia. Entre arranques, el último instante visto se persiste (`STATE_FILE`) y
`check_clock_rollback` rechaza un reloj que haya retrocedido.

Límites (los mismos que declara el SDK): quien tenga root en el host puede falsear los
montajes de la huella con los valores del host licenciado, si los conoce, o borrar el fichero
de estado. La puerta sube el coste de copiar la imagen; no lo hace imposible.

`chatrag-licencia huella` imprime la solicitud de licencia (los hashes de este host) y
`chatrag-licencia estado` evalúa la puerta tal como lo haría el servicio.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tribu_licensing as tl
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from chatrag_api import _licencia_horneada
from chatrag_api.config import Settings

logger = logging.getLogger("chatrag_api.licencia")

# `format` del sobre: una licencia de otro producto firmada con la misma clave no vale aquí.
LICENSE_FORMAT = "chatrag-license/v1"
HOST_COMPONENT_FORMAT = "tribu-host-component/v1"
# Rutas que siguen vivas en modo inerte: diagnóstico y lo justo para pintar la página. Todo lo
# demás se bloquea, incluidas las que no existan: lista blanca, no lista negra.
INERT_ALLOWED_PATHS = frozenset({"/health", "/theme", "/admin/licencia"})
# Cada cuánto, como mucho, se persiste el último instante visto con el servicio en marcha.
PERSIST_EVERY_SECONDS = 600

INERT_MESSAGE = (
    "ChatRAG está en modo inerte: no hay una licencia válida para este equipo. El servicio "
    "queda deshabilitado hasta que se instale una licencia ligada a este host. Contacta con "
    "tu proveedor."
)

EstadoPuerta = Literal["desactivada", "valida", "gracia", "inerte"]

# Motivos de inerte (estables, para soporte). Los de la verificación del sobre son los códigos
# de la crate (`malformed`, `unknown_key`, `invalid_signature`, `invalid_payload`).
MOTIVOS: dict[str, str] = {
    "sin_claves": "no hay claves públicas de confianza configuradas",
    "sin_licencia": "no se encontró el fichero de licencia",
    "licencia_ilegible": "no se pudo leer el fichero de licencia",
    "sin_estado": "falta el fichero de estado del reloj",
    "estado_ilegible": "el fichero de estado del reloj está dañado o no se puede leer",
    "estado_no_persistible": "no se pudo guardar el estado del reloj",
    "reloj_atrasado": "el reloj del sistema retrocedió respecto al último arranque",
    "malformed": "el sobre de licencia está mal formado",
    "unknown_key": "la licencia está firmada con una clave que no es de confianza",
    "invalid_signature": "la firma de la licencia no verifica",
    "invalid_payload": "el contenido de la licencia no es válido",
    "sin_huella": "la licencia no está ligada a ningún host",
    "otro_host": "la licencia es de otro equipo (la huella del host no coincide)",
    "caducada": "la licencia ha caducado (y su periodo de gracia también)",
}


@dataclass(frozen=True)
class LicenseConfig:
    """Configuración efectiva de la puerta (horneada o, en desarrollo, del entorno)."""

    enforced: bool
    trusted_keys: Mapping[str, bytes]
    license_file: str | None
    host_root: str
    state_file: str | None
    horneada: bool


def resolve_config(settings: Settings) -> LicenseConfig:
    """Lo horneado manda: si la build fijó `ENFORCED`, el entorno no puede apagar la puerta,
    cambiar las claves de confianza ni quitar el fichero de estado."""

    if _licencia_horneada.ENFORCED:
        return LicenseConfig(
            enforced=True,
            trusted_keys={
                key_id: bytes.fromhex(hex_key)
                for key_id, hex_key in _licencia_horneada.TRUSTED_KEYS_HEX.items()
            },
            license_file=settings.license_file,
            host_root=settings.license_host_root,
            state_file=_licencia_horneada.STATE_FILE,
            horneada=True,
        )
    return LicenseConfig(
        enforced=settings.license_enforced,
        trusted_keys=dict(settings.license_public_keys),
        license_file=settings.license_file,
        host_root=settings.license_host_root,
        state_file=settings.license_state_file,
        horneada=False,
    )


def huella_coincide(fingerprint: tl.Fingerprint, host_hashes: Sequence[str]) -> bool:
    """`required_matches` de entre los hashes de la licencia están en este host. Tolerante a
    cambios de hardware dentro de lo que la licencia permite (p. ej. una tarjeta de red)."""

    return len(set(fingerprint.hashes) & set(host_hashes)) >= fingerprint.required_matches


@dataclass(frozen=True)
class Verificacion:
    """Resultado de verificar el sobre en un instante: la licencia o el motivo del rechazo."""

    licencia: tl.SignedLicense | None
    motivo: str | None


def verificar(
    envelope: str | bytes,
    trusted_keys: Mapping[str, bytes],
    host_hashes: Sequence[str],
    now_unix: int,
) -> Verificacion:
    """Pura (sin E/S): sobre + claves + hashes del host + instante → licencia o motivo."""

    try:
        signed = tl.verify_envelope(envelope, trusted_keys, expected_format=LICENSE_FORMAT)
    except tl.LicenseEnvelopeError as exc:
        return Verificacion(None, exc.code or "invalid_payload")
    fingerprint = signed.entitlements.fingerprint
    if fingerprint is None:
        return Verificacion(None, "sin_huella")
    if not huella_coincide(fingerprint, host_hashes):
        return Verificacion(None, "otro_host")
    if signed.state_at(now_unix) == "expired":
        return Verificacion(signed, "caducada")
    return Verificacion(signed, None)


def _leer_last_seen(state_file: Path) -> int:
    """0 si el fichero no existe (primer arranque). Lanza `ValueError`/`OSError` si existe y
    está dañado o no se puede leer: eso es fail-closed, no un primer arranque."""

    try:
        raw = state_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return 0
    data = json.loads(raw)
    value = data.get("last_seen_unix") if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("last_seen_unix inválido")
    return value


def _guardar_last_seen(state_file: Path, last_seen: int) -> None:
    tmp = state_file.with_name(state_file.name + ".tmp")
    tmp.write_text(json.dumps({"last_seen_unix": last_seen}), encoding="utf-8")
    os.replace(tmp, state_file)


class LicenseGate:
    """Estado de la puerta durante la vida del proceso. La verificación criptográfica y la de
    la huella se hacen una vez en el arranque (`from_config`); la caducidad se reevalúa en
    cada petición con el reloj monotónico."""

    def __init__(
        self,
        *,
        enforced: bool,
        licencia: tl.SignedLicense | None = None,
        motivo: str | None = None,
        state_file: Path | None = None,
        last_seen: int = 0,
        horneada: bool = False,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enforced = enforced
        self.horneada = horneada
        self._licencia = licencia
        self._motivo = motivo
        self._state_file = state_file
        self._monotonic = monotonic
        self._start_wall = int(wall_clock())
        self._start_mono = monotonic()
        self._last_persisted = last_seen

    @classmethod
    def desactivada(cls) -> LicenseGate:
        return cls(enforced=False)

    @classmethod
    def from_config(
        cls,
        config: LicenseConfig,
        *,
        wall_clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> LicenseGate:
        """Evalúa la puerta en el arranque (E/S: sobre, montajes del host, estado del reloj)."""

        if not config.enforced:
            return cls.desactivada()

        def inerte(motivo: str, last_seen: int = 0) -> LicenseGate:
            logger.error("licencia: modo INERTE (%s: %s)", motivo, MOTIVOS.get(motivo, motivo))
            return cls(
                enforced=True,
                motivo=motivo,
                state_file=state_file,
                last_seen=last_seen,
                horneada=config.horneada,
                wall_clock=wall_clock,
                monotonic=monotonic,
            )

        state_file = Path(config.state_file) if config.state_file else None
        if not config.trusted_keys:
            return inerte("sin_claves")
        if state_file is None and config.horneada:
            return inerte("sin_estado")

        now = int(wall_clock())
        last_seen = 0
        if state_file is not None:
            try:
                last_seen = _leer_last_seen(state_file)
            except (OSError, ValueError):
                return inerte("estado_ilegible")
            try:
                tl.check_clock_rollback(last_seen, now)
            except tl.ClockRollbackError:
                return inerte("reloj_atrasado", last_seen)
        else:
            logger.warning("licencia: sin CHATRAG_LICENSE_STATE_FILE, sin anti-rollback de reloj")

        if not config.license_file:
            return inerte("sin_licencia", last_seen)
        try:
            envelope = Path(config.license_file).read_bytes()
        except FileNotFoundError:
            return inerte("sin_licencia", last_seen)
        except OSError:
            return inerte("licencia_ilegible", last_seen)

        host = tl.collect_host_component_hashes(config.host_root)
        for skipped in host.skipped:
            logger.info("licencia: componente %s omitido (%s)", skipped.source, skipped.reason)
        resultado = verificar(envelope, config.trusted_keys, list(host.hashes), now)
        if resultado.motivo is not None:
            return inerte(resultado.motivo, last_seen)

        gate = cls(
            enforced=True,
            licencia=resultado.licencia,
            state_file=state_file,
            last_seen=last_seen,
            horneada=config.horneada,
            wall_clock=wall_clock,
            monotonic=monotonic,
        )
        if not gate._persistir(now):
            return inerte("estado_no_persistible", last_seen)
        assert resultado.licencia is not None
        logger.info(
            "licencia: %s válida para el sitio %s hasta %s",
            resultado.licencia.license.license_id,
            resultado.licencia.entitlements.site_id,
            resultado.licencia.license.expires_at_unix,
        )
        return gate

    def now(self) -> int:
        """Reloj de pared del arranque + tiempo monotónico: inmune a atrasar el reloj después."""

        return self._start_wall + int(self._monotonic() - self._start_mono)

    def _persistir(self, now: int) -> bool:
        if self._state_file is None:
            return True
        try:
            _guardar_last_seen(self._state_file, max(now, self._last_persisted))
        except OSError:
            logger.exception("licencia: no se pudo persistir el estado del reloj")
            return False
        self._last_persisted = max(now, self._last_persisted)
        return True

    def estado(self) -> EstadoPuerta:
        if not self.enforced:
            return "desactivada"
        if self._motivo is not None or self._licencia is None:
            return "inerte"
        now = self.now()
        state = self._licencia.state_at(now)
        if state == "expired":
            self._motivo = "caducada"
            logger.error("licencia: modo INERTE (caducada)")
            return "inerte"
        if now - self._last_persisted >= PERSIST_EVERY_SECONDS and not self._persistir(now):
            self._motivo = "estado_no_persistible"
            return "inerte"
        return "gracia" if state == "grace" else "valida"

    @property
    def motivo(self) -> str | None:
        return self._motivo

    def permite(self, path: str) -> bool:
        return self.estado() != "inerte" or path in INERT_ALLOWED_PATHS

    def resumen(self) -> dict[str, object]:
        """Lo que ven `/health` y `/admin/licencia`. Sin hashes ni secretos."""

        estado = self.estado()
        out: dict[str, object] = {"estado": estado}
        if not self.enforced:
            return out
        out["horneada"] = self.horneada
        if self._motivo is not None:
            out["motivo"] = self._motivo
            out["detalle"] = MOTIVOS.get(self._motivo, self._motivo)
        if self._licencia is not None:
            out["license_id"] = self._licencia.license.license_id
            out["site_id"] = self._licencia.entitlements.site_id
            out["expires_at_unix"] = self._licencia.license.expires_at_unix
            out["grace_period_seconds"] = self._licencia.license.grace_period_seconds
        return out


class LicenseGateMiddleware(BaseHTTPMiddleware):
    """503 en modo inerte para todo lo que no esté en `INERT_ALLOWED_PATHS`."""

    def __init__(self, app: object, *, gate: LicenseGate) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._gate = gate

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not self._gate.permite(request.url.path):
            return JSONResponse(
                {"detail": INERT_MESSAGE, "licencia": self._gate.motivo}, status_code=503
            )
        return await call_next(request)


def solicitud_de_huella(host_root: str) -> dict[str, object]:
    """Lo que el operador envía a Tribu para pedir una licencia para este host."""

    host = tl.collect_host_component_hashes(host_root)
    return {
        "format": HOST_COMPONENT_FORMAT,
        "hashes": list(host.hashes),
        "componentes": [{"tipo": c.kind, "origen": c.source} for c in host.components],
        "omitidos": [
            {"tipo": s.kind, "origen": s.source, "motivo": s.reason} for s in host.skipped
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    """`chatrag-licencia huella|estado`. Sale con 1 si `estado` da inerte."""

    parser = argparse.ArgumentParser(prog="chatrag-licencia", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="orden", required=True)
    huella = sub.add_parser("huella", help="imprime la solicitud de licencia de este host")
    huella.add_argument("--raiz", default=None, help="raíz de los montajes del host")
    sub.add_parser("estado", help="evalúa la puerta como lo haría el servicio")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    if args.orden == "huella":
        raiz = args.raiz or settings.license_host_root
        json.dump(solicitud_de_huella(raiz), sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0
    gate = LicenseGate.from_config(resolve_config(settings))
    json.dump(gate.resumen(), sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 1 if gate.estado() == "inerte" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
