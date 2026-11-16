"""Theming de ChatRAG: identidad visual configurable sin redeploy — logo, colores, tipografía,
densidad de layout, estilo de burbuja de chat, y la copy de la cabecera (eyebrow/título/
descripción, ver `page.tsx`). Deliberadamente **no** un sistema de plugins arbitrario
(layout/componentes intercambiables por código): un conjunto cerrado de tokens de diseño,
editable desde `/admin/theme` (`admin.py`) y leído por el frontend en cada request SSR
(`GET /theme`, público, sin auth — lo necesita cualquier visitante para pintar la página).

El título (`heading_text`) se degrada completo con el gradiente de acento — antes, con copy
fija, solo "comuna de Santiago" llevaba el gradiente y "Asistente de la" no; con texto libre no
hay forma genérica de saber qué palabra resaltar, así que se simplifica a "todo el título" en
vez de intentar adivinar qué sub-frase es la interesante.

Persistencia: Postgres (misma base que `tribu-audit`, si `CHATRAG_AUDIT_DATABASE_URL` está
configurada — reutilizar la conexión existente en vez de exigir una base propia solo para el
tema) con fallback a un fichero JSON versionable (`theme.json` por defecto) cuando no hay
Postgres. Ninguno de los dos es una dependencia dura: sin nada configurado, `JsonFileThemeStore`
sigue funcionando (crea el fichero al primer `set`), así que ChatRAG nunca deja de arrancar por
falta de tema."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class Theme(BaseModel):
    """Tokens de diseño de ChatRAG. Conjunto cerrado a propósito (ver docstring del módulo) —
    añadir un token nuevo es una decisión de producto, no una entrada de config libre."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_name: str = "ChatRAG"
    logo_url: str | None = None
    color_accent: str = "#3b82f6"
    color_accent_secondary: str = "#d52b1e"
    color_background: str = "#050505"
    font_family: str = "system-ui, -apple-system, sans-serif"
    density: Literal["compact", "comfortable"] = "comfortable"
    bubble_style: Literal["rounded", "square"] = "rounded"

    # Copy de la cabecera (src/app/page.tsx) — antes hardcoded, ahora editable desde
    # /admin/theme sin redeploy. Los defaults son la copy original de la comuna de Santiago.
    eyebrow_text: str = "Ilustre Municipalidad de Santiago"
    heading_text: str = "Asistente de la comuna de Santiago"
    description_text: str = (
        "Asistente oficial de la comuna de Santiago de Chile. Consúltame sobre trámites y "
        "servicios municipales, direcciones del municipio, el alcalde Mario Desbordes o "
        "cualquier información del sitio munistgo.cl. Escribe tu pregunta y te respondo con "
        "el enlace directo del trámite y su fuente."
    )

    # Voz (ver voice.py): qué voz STOCK de tribu_voice usa el asistente y con qué marca —
    # `app_name` de arriba ya hace de nombre de marca (`VoiceBrand.brand_name`), no se duplica
    # aquí. `voice_id` DEBE estar en el catálogo stock real (`tribu_voice.stock_voice_ids()`);
    # si no lo está, `TribuVoiceService.mint_session()` falla-cerrado en vez de sintetizar con
    # una voz inventada. El catálogo de ejemplo de tribu_voice (4 voces es/en) es el que valida
    # hoy — un despliegue real con su propio Riva reemplaza ese catálogo, no este campo.
    voice_id: str = "es-419.Female-1"


_DEFAULT_THEME = Theme()


class ThemeStore(Protocol):
    """Contrato mínimo de persistencia del tema. Lo implementan `JsonFileThemeStore` (fallback
    sin infraestructura) y `PostgresThemeStore` (cuando hay Postgres real) — mismo patrón de
    Protocol + doble que `Retriever`/`AuditLog`/`Ingestor`."""

    async def get(self) -> Theme: ...
    async def set(self, theme: Theme) -> None: ...


class InMemoryThemeStore:
    """Doble de test: nada persiste entre procesos, solo vive en el objeto."""

    def __init__(self, initial: Theme | None = None) -> None:
        self._theme = initial or _DEFAULT_THEME

    async def get(self) -> Theme:
        return self._theme

    async def set(self, theme: Theme) -> None:
        self._theme = theme


class JsonFileThemeStore:
    """Fallback sin infraestructura: un fichero JSON en disco. `get()` devuelve el tema por
    defecto si el fichero no existe todavía (nunca falla el arranque por falta de tema);
    `set()` lo crea/sobrescribe. No hay concurrencia real que proteger aquí — es una acción de
    administración manual, no un camino caliente de `/query`."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def get(self) -> Theme:
        if not self._path.is_file():
            return _DEFAULT_THEME
        return Theme.model_validate_json(self._path.read_text(encoding="utf-8"))

    async def set(self, theme: Theme) -> None:
        self._path.write_text(theme.model_dump_json(indent=2), encoding="utf-8")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chatrag_theme (
    id INTEGER PRIMARY KEY DEFAULT 1,
    theme_json TEXT NOT NULL,
    CONSTRAINT chatrag_theme_singleton CHECK (id = 1)
);
"""


class PostgresThemeStore:  # pragma: no cover - requiere Postgres real
    """Adaptador de producción: una sola fila (`id=1`, forzado por constraint — el tema es
    singleton, no hay múltiples temas por ahora) en la misma Postgres que `tribu-audit`. Import
    perezoso de `asyncpg` (mismo motivo que `audit.py`: los tests corren sin una base real)."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def get(self) -> Theme:
        import asyncpg  # type: ignore

        conn = await asyncpg.connect(self._database_url)
        try:
            await conn.execute(_SCHEMA)
            row = await conn.fetchrow("SELECT theme_json FROM chatrag_theme WHERE id = 1")
        finally:
            await conn.close()
        if row is None:
            return _DEFAULT_THEME
        return Theme.model_validate_json(row["theme_json"])

    async def set(self, theme: Theme) -> None:
        import asyncpg  # mypy: módulo ya visto arriba

        conn = await asyncpg.connect(self._database_url)
        try:
            await conn.execute(_SCHEMA)
            await conn.execute(
                "INSERT INTO chatrag_theme (id, theme_json) VALUES (1, $1) "
                "ON CONFLICT (id) DO UPDATE SET theme_json = EXCLUDED.theme_json",
                theme.model_dump_json(),
            )
        finally:
            await conn.close()


def get_theme_store(*, audit_database_url: str | None, theme_file: Path) -> ThemeStore:
    """Postgres si `CHATRAG_AUDIT_DATABASE_URL` está configurada (misma base que tribu-audit —
    ver docstring del módulo), fichero JSON si no."""

    if audit_database_url is not None:
        return PostgresThemeStore(audit_database_url)
    return JsonFileThemeStore(theme_file)
