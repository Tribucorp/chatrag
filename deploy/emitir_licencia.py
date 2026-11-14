"""Emisión de licencias de ChatRAG por host (lado Tribu, NUNCA en la imagen que se entrega).

Flujo:
  1. Una vez: `claves --dir ~/.tribu/chatrag-licencias --key-id chatrag-2026` genera el par
     Ed25519. La privada se queda en el equipo emisor (0600). La pública, en hex, se hornea en
     la imagen protegida: `docker build --build-arg CHATRAG_LICENSE_KEYS=chatrag-2026:<hex>`.
  2. En el host del tercero, con la imagen protegida:
       docker run --rm -v /etc/machine-id:/host/etc/machine-id:ro -v /sys:/host/sys:ro \\
         chatrag-api:protegido chatrag-licencia huella > solicitud.json
     (o `GET /admin/licencia` con el servicio ya levantado, también en modo inerte).
  3. `emitir --solicitud solicitud.json --site-id ... --tenant-id ... --dias 365` firma el sobre
     `chatrag-license/v1` con tribu_licensing.sign_payload (Rust) y comprueba que vuelve a
     verificar con verify_envelope contra ESA solicitud antes de escribirlo.
  4. El sobre se instala en el host en la ruta de CHATRAG_LICENSE_FILE
     (por defecto, en la imagen protegida, /run/chatrag/license.json).

Uso: `uv run --project backend python deploy/emitir_licencia.py ...` (necesita el grupo dev
por `cryptography`, que solo genera el par de claves).
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path

import tribu_licensing as tl
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from chatrag_api.licencia import HOST_COMPONENT_FORMAT, LICENSE_FORMAT, huella_coincide

DIA = 86_400


def _publica(raw_priv: bytes) -> bytes:
    return (
        Ed25519PrivateKey.from_private_bytes(raw_priv)
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )


def cmd_claves(args: argparse.Namespace) -> int:
    directorio = Path(args.dir).expanduser()
    directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
    privada = directorio / f"{args.key_id}.ed25519"
    if privada.exists():
        print(f"ya existe {privada}: no se sobreescribe una clave de firma", file=sys.stderr)
        return 1
    raw = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    fd = os.open(privada, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(raw.hex() + "\n")
    print(f"privada: {privada} (no sale de este equipo)")
    print(f"build-arg: CHATRAG_LICENSE_KEYS={args.key_id}:{_publica(raw).hex()}")
    return 0


def cmd_emitir(args: argparse.Namespace) -> int:
    raw_priv = bytes.fromhex(Path(args.clave_privada).expanduser().read_text().strip())
    solicitud = json.loads(Path(args.solicitud).read_text())
    if solicitud.get("format") != HOST_COMPONENT_FORMAT:
        print(f"la solicitud no es {HOST_COMPONENT_FORMAT}", file=sys.stderr)
        return 1
    hashes = sorted(set(solicitud["hashes"]))
    if not hashes:
        print("la solicitud no trae ningún componente del host: no hay a qué ligar", file=sys.stderr)
        return 1
    # Por defecto, mayoría estricta: tolera cambiar una pieza (p. ej. una NIC) sin reemitir, pero
    # no basta con clonar solo el machine-id.
    requeridos = args.requeridos or max(1, math.floor(len(hashes) / 2) + 1)
    if not 1 <= requeridos <= len(hashes):
        print(f"--requeridos debe estar entre 1 y {len(hashes)}", file=sys.stderr)
        return 1

    ahora = int(time.time())
    payload = {
        "license_id": args.license_id or f"chatrag-{uuid.uuid4()}",
        "tenant_id": args.tenant_id,
        "site_id": args.site_id,
        "issued_at_unix": ahora,
        "expires_at_unix": ahora + args.dias * DIA,
        "grace_period_seconds": args.gracia_dias * DIA,
        "features": ["chatrag"],
        "fingerprint": {"hashes": hashes, "required_matches": requeridos},
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sobre = {
        "format": LICENSE_FORMAT,
        "key_id": args.key_id,
        "payload_b64": base64.b64encode(raw).decode("ascii"),
        "signature_hex": tl.sign_payload(raw_priv, raw).hex(),
    }

    # Autocomprobación con el MISMO verificador que el servicio: si esto no pasa, no se entrega.
    signed = tl.verify_envelope(
        json.dumps(sobre), {args.key_id: _publica(raw_priv)}, expected_format=LICENSE_FORMAT
    )
    assert signed.entitlements.fingerprint is not None
    assert huella_coincide(signed.entitlements.fingerprint, hashes)
    assert signed.state_at(ahora) == "valid"

    Path(args.salida).write_text(json.dumps(sobre, indent=2) + "\n")
    print(
        f"{payload['license_id']} → {args.salida}: sitio {args.site_id}, {len(hashes)} "
        f"componentes ({requeridos} requeridos), {args.dias} días + {args.gracia_dias} de gracia"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emisión de licencias de ChatRAG por host")
    sub = parser.add_subparsers(dest="orden", required=True)

    claves = sub.add_parser("claves", help="genera el par Ed25519 del emisor")
    claves.add_argument("--dir", required=True)
    claves.add_argument("--key-id", required=True)
    claves.set_defaults(func=cmd_claves)

    emitir = sub.add_parser("emitir", help="firma una licencia para la solicitud de un host")
    emitir.add_argument("--clave-privada", required=True)
    emitir.add_argument("--key-id", required=True)
    emitir.add_argument("--solicitud", required=True, help="salida de `chatrag-licencia huella`")
    emitir.add_argument("--site-id", required=True)
    emitir.add_argument("--tenant-id", required=True)
    emitir.add_argument("--dias", type=int, required=True)
    emitir.add_argument("--gracia-dias", type=int, default=14)
    emitir.add_argument("--requeridos", type=int, default=None)
    emitir.add_argument("--license-id", default=None)
    emitir.add_argument("--salida", default="license.json")
    emitir.set_defaults(func=cmd_emitir)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
