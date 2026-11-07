"""Traza de decisión de ChatRAG sobre `tribu-audit` (cadena WORM HMAC real vía PyO3, no una
reimplementación). API confirmada leyendo el código fuente real del SDK (no el corpus de x9,
que se rehusó por falta de referencia): `tribu_audit.AuditChain`/`AuditEntry`/`append_entry`/
`reconstruct_entry`/`verify_chain` en `tribu-sdk/python/tribu-audit/python/tribu_audit/
__init__.pyi`.

`tribu_audit.AuditChain` es explícitamente **solo la parte en memoria** (su propio README:
"referencia testeable, no un backend persistente/replicado"). El patrón de producción real
—confirmado en `tribu-sdk/python/tribu-spark-firma/src/tribu_spark_firma/
persistent_audit_chain.py`, el único consumidor real del SDK que persiste esta cadena— es
respaldarla con Postgres: cargar y verificar la cadena completa al arrancar
(`reconstruct_entry` + `verify_chain`, fail-closed) y persistir cada entrada nueva
(`append_entry` + `chain.push`) según se genera. Este módulo replica ESE PATRÓN con tabla y
código propios de ChatRAG — no importa `tribu_spark_firma` (es código de otro producto sobre
el SDK, no un módulo del SDK; CLAUDE.md prohíbe vendorizar/copiar código del SDK, y por
extensión, de otro producto)."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping
from typing import Protocol


class AuditLog(Protocol):
    """Contrato mínimo de traza de decisión. Lo implementa `TribuPostgresAuditLog` en
    producción y `NullAuditLog`/un doble en los tests."""

    async def record(self, *, actor_id: str, action: str, payload: Mapping[str, object]) -> None:
        """Registra una decisión. `payload` debe ser serializable a JSON."""
        ...


class NullAuditLog:
    """Sin traza — el default mientras `CHATRAG_AUDIT_DATABASE_URL`/`CHATRAG_AUDIT_CHAIN_KEY`
    no estén configurados. No falla la consulta por falta de auditoría: la traza es una
    capa adicional de compliance, no una condición de disponibilidad del RAG."""

    async def record(self, *, actor_id: str, action: str, payload: Mapping[str, object]) -> None:
        return None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chatrag_audit_entries (
    seq BIGSERIAL PRIMARY KEY,
    entry_id TEXT UNIQUE NOT NULL,
    case_token TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    recorded_at_unix BIGINT NOT NULL,
    prev_hash BYTEA NOT NULL,
    entry_hash BYTEA NOT NULL
);
"""


class TribuPostgresAuditLog:  # pragma: no cover - requiere tribu-audit del registry + Postgres
    """Adaptador de producción: `tribu_audit.AuditChain` en memoria, respaldada en Postgres.
    Import perezoso de `tribu_audit`/`asyncpg` (mismo motivo que `rag.py`: que los tests del
    producto corran sin el registry privado ni una base real).

    Simplificación deliberada frente a `persistent_audit_chain.py`: persiste cada entrada
    de inmediato (`record()` hace un INSERT por llamada) en vez de acumular en el `AuditChain`
    en memoria y volcar en bloque por un bucle de polling aparte. Para el volumen de consultas
    de un piloto es más simple y no pierde entradas si el proceso muere entre solicitudes; si
    el volumen crece lo suficiente para que el INSERT por request pese, migrar al patrón de
    `persistir_nuevas()` (acumular + volcar en bloque) es el mismo `AuditChain` en memoria, sin
    tocar los call-sites de `record()`."""

    def __init__(self, database_url: str, *, chain_key: bytes) -> None:
        self._database_url = database_url
        self._chain_key = chain_key
        self._pool: object | None = None
        self._chain: object | None = None

    async def connect(self) -> None:
        """Crea el pool, la tabla si no existe, y rehidrata + verifica la cadena completa.
        Fail-closed: si la cadena reconstruida no verifica (manipulación, fila borrada a mano),
        propaga `tribu_audit.ChainVerificationError` en vez de arrancar con una traza en la que
        no se puede confiar — llamar UNA vez en el `lifespan` del servicio, antes de la primera
        consulta."""

        # Sin código entre corchetes a propósito: asyncpg (PyPI) reporta import-not-found si no
        # está instalado o import-untyped si lo está pero sin stubs — cuál de los dos depende
        # del entorno donde corra mypy, y `warn_unused_ignores` (--strict) marca como no usado
        # el código del par que no aplique en cada entorno. Un ignore sin código evita la
        # discrepancia sin tener que elegir uno.
        import asyncpg  # type: ignore
        import tribu_audit  # type: ignore[import-not-found]

        pool = await asyncpg.create_pool(self._database_url)
        self._pool = pool
        async with pool.acquire() as conn:
            await conn.execute(_SCHEMA)
            filas = await conn.fetch(
                "SELECT entry_id, case_token, actor_id, action, payload_json, "
                "recorded_at_unix, prev_hash, entry_hash FROM chatrag_audit_entries ORDER BY seq"
            )
        chain = tribu_audit.AuditChain()
        for fila in filas:
            entrada = tribu_audit.reconstruct_entry(
                fila["entry_id"],
                fila["case_token"],
                fila["actor_id"],
                fila["action"],
                fila["payload_json"],
                fila["recorded_at_unix"],
                bytes(fila["prev_hash"]),
                bytes(fila["entry_hash"]),
            )
            chain.push(entrada)
        if filas:
            tribu_audit.verify_chain(chain.entries(), self._chain_key)
        self._chain = chain

    async def record(self, *, actor_id: str, action: str, payload: Mapping[str, object]) -> None:
        import tribu_audit  # mypy ya conoce el módulo desde el import de connect() (mismo file)

        assert self._chain is not None and self._pool is not None, "connect() no se llamó"
        entrada = tribu_audit.append_entry(
            self._chain,
            self._chain_key,
            str(uuid.uuid4()),
            str(uuid.uuid4()),  # case_token: una consulta = un caso, sin correlación entre sí
            actor_id,
            action,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            int(time.time()),
        )
        self._chain.push(entrada)  # type: ignore[attr-defined]
        pool = self._pool
        async with pool.acquire() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                "INSERT INTO chatrag_audit_entries "
                "(entry_id, case_token, actor_id, action, payload_json, recorded_at_unix, "
                "prev_hash, entry_hash) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                "ON CONFLICT (entry_id) DO NOTHING",
                entrada.entry_id,
                entrada.case_token,
                entrada.actor_id,
                entrada.action,
                entrada.payload_json,
                entrada.recorded_at_unix,
                entrada.prev_hash,
                entrada.entry_hash,
            )

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()  # type: ignore[attr-defined]


async def read_recent_entries(
    database_url: str, *, limit: int = 50
) -> list[dict[str, object]]:  # pragma: no cover - requiere Postgres real
    """Lectura para `GET /admin/audit` (`admin.py`) — no pasa por `AuditLog`/`TribuPostgresAuditLog`
    a propósito: ese Protocol es sobre escribir durante una consulta (`record`), esto es una
    consulta administrativa de solo lectura, con su propia conexión efímera (no reutiliza el
    pool de `lifespan`, que puede no existir si el admin consulta el histórico sin que haya
    corrido ninguna consulta todavía). No verifica la cadena (`verify_chain`) — eso ya lo hizo
    `TribuPostgresAuditLog.connect()` al arrancar el servicio; esto es solo lectura para mostrar
    en el panel, no una re-verificación de integridad."""

    import asyncpg  # mypy: módulo ya visto arriba

    conn = await asyncpg.connect(database_url)
    try:
        filas = await conn.fetch(
            "SELECT entry_id, case_token, actor_id, action, payload_json, recorded_at_unix "
            "FROM chatrag_audit_entries ORDER BY seq DESC LIMIT $1",
            limit,
        )
    finally:
        await conn.close()
    return [
        {
            "entry_id": f["entry_id"],
            "case_token": f["case_token"],
            "actor_id": f["actor_id"],
            "action": f["action"],
            "payload": json.loads(f["payload_json"]),
            "recorded_at_unix": f["recorded_at_unix"],
        }
        for f in filas
    ]
