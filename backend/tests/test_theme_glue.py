from pathlib import Path

from chatrag_api.theme import InMemoryThemeStore, JsonFileThemeStore, Theme, get_theme_store


async def test_json_store_devuelve_el_default_si_no_existe_el_fichero(tmp_path: Path):
    store = JsonFileThemeStore(tmp_path / "theme.json")
    theme = await store.get()
    assert theme == Theme()


async def test_json_store_persiste_y_relee(tmp_path: Path):
    path = tmp_path / "theme.json"
    store = JsonFileThemeStore(path)
    custom = Theme(app_name="Municipalidad Demo", color_accent="#00ff00")
    await store.set(custom)

    assert path.is_file()
    reloaded = await JsonFileThemeStore(path).get()
    assert reloaded == custom


async def test_in_memory_store_get_set():
    store = InMemoryThemeStore()
    assert await store.get() == Theme()
    custom = Theme(density="compact")
    await store.set(custom)
    assert await store.get() == custom


def test_get_theme_store_usa_json_sin_postgres(tmp_path: Path):
    store = get_theme_store(audit_database_url=None, theme_file=tmp_path / "theme.json")
    assert isinstance(store, JsonFileThemeStore)
