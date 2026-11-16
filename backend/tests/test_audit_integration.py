"""Prueba de humo contra `tribu-audit` real + Postgres real (no dobles) — mismo patrón que
`test_sdk_integration.py`. API de `tribu_audit` confirmada leyendo el código fuente real del
SDK en `~/repositorio/tribu-sdk/python/tribu-audit/`; el patrón de persistencia replica
`tribu-sdk/python/tribu-spark-firma/src/tribu_spark_firma/persistent_audit_chain.py` (el único
consumidor real del SDK que respalda `AuditChain` en Postgres) — ver `chatrag_api/audit.py`.

Marcada `integration`. Además del SDK instalado (`tribu_audit`), necesita una Postgres real:
`CHATRAG_TEST_AUDIT_DATABASE_URL` (DSN de una base vacía o descartable — el test hace
`DROP TABLE IF EXISTS chatrag_audit_entries` al empezar). Sin esa env var, se skippea — no
inventa un Postgres local. En CI, el job `backend-integration` la provee vía un servicio
`postgres` (ver .github/workflows/ci.yml).
"""

from __future__ import annotations

import os
import secrets

import pytest

pytest.importorskip("tribu_audit", reason="requiere el SDK instalado (uv sync)")
pytest.importorskip("asyncpg", reason="driver de Postgres")

pytestmark = pytest.mark.integration

_TEST_DB_URL = os.environ.get("CHATRAG_TEST_AUDIT_DATABASE_URL")


@pytest.mark.skipif(not _TEST_DB_URL, reason="CHATRAG_TEST_AUDIT_DATABASE_URL no configurada")
async def test_round_trip_persiste_y_reverifica_la_cadena_real():
    import asyncpg

    from chatrag_api.audit import TribuPostgresAuditLog

    assert _TEST_DB_URL is not None  # para mypy/el type-checker de este archivo
    chain_key = secrets.token_bytes(32)

    conn = await asyncpg.connect(_TEST_DB_URL)
    try:
        await conn.execute("DROP TABLE IF EXISTS chatrag_audit_entries")
    finally:
        await conn.close()

    log = TribuPostgresAuditLog(_TEST_DB_URL, chain_key=chain_key)
    await log.connect()  # tabla vacía: no hay nada que reverificar todavía
    try:
        await log.record(
            actor_id="u1", action="chatrag.query.answered", payload={"question": "¿horario?"}
        )
        await log.record(
            actor_id="u2", action="chatrag.query.abstained", payload={"question": "¿nómina?"}
        )
    finally:
        await log.aclose()

    # Reabrir desde cero: rehidrata desde Postgres (reconstruct_entry) y reverifica la cadena
    # completa (verify_chain) — si algo se corrompió al guardar, esto explota fail-closed.
    log2 = TribuPostgresAuditLog(_TEST_DB_URL, chain_key=chain_key)
    await log2.connect()
    await log2.aclose()


@pytest.mark.skipif(not _TEST_DB_URL, reason="CHATRAG_TEST_AUDIT_DATABASE_URL no configurada")
async def test_chain_key_incorrecta_falla_cerrado_al_reabrir():
    import asyncpg
    import tribu_audit

    from chatrag_api.audit import TribuPostgresAuditLog

    assert _TEST_DB_URL is not None

    conn = await asyncpg.connect(_TEST_DB_URL)
    try:
        await conn.execute("DROP TABLE IF EXISTS chatrag_audit_entries")
    finally:
        await conn.close()

    log = TribuPostgresAuditLog(_TEST_DB_URL, chain_key=secrets.token_bytes(32))
    await log.connect()
    try:
        await log.record(actor_id="u1", action="x", payload={})
    finally:
        await log.aclose()

    otra_clave = TribuPostgresAuditLog(_TEST_DB_URL, chain_key=secrets.token_bytes(32))
    with pytest.raises(tribu_audit.ChainVerificationError):
        await otra_clave.connect()
