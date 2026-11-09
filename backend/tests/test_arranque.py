from __future__ import annotations

from types import SimpleNamespace

import pytest

from chatrag_api.arranque import seed_knowledge, warmup
from chatrag_api.ingest import IngestReport


def test_seed_copia_solo_si_knowledge_esta_vacio(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "a.md").write_text("A")
    (seed / "b.md").write_text("B")
    kb = tmp_path / "kb"
    assert seed_knowledge(kb, seed) == 2
    assert sorted(p.name for p in kb.glob("*.md")) == ["a.md", "b.md"]

    (kb / "a.md").write_text("editado desde /admin")
    assert seed_knowledge(kb, seed) == 0  # ya hay corpus: no se pisa
    assert (kb / "a.md").read_text() == "editado desde /admin"


def test_seed_sin_directorio_de_arranque_no_hace_nada(tmp_path):
    assert seed_knowledge(tmp_path / "kb", None) == 0
    assert seed_knowledge(tmp_path / "kb", tmp_path / "no-existe") == 0


class _Flaky:
    """Falla `fails` veces y luego devuelve `value`."""

    def __init__(self, fails: int, value):
        self.fails, self.value, self.calls = fails, value, 0

    async def __call__(self):
        self.calls += 1
        if self.calls <= self.fails:
            raise ConnectionError("aún no")
        return self.value


async def test_warmup_reintenta_e_ingiere_si_no_hay_indice():
    state = SimpleNamespace(retriever=None)
    retriever = object()
    build = _Flaky(2, retriever)
    exists = _Flaky(1, False)
    ingest = _Flaky(1, [IngestReport(document_id="a.md", chunks=3)])
    await warmup(state, build_retriever=build, index_exists=exists, ingest=ingest, retry_seconds=0)
    assert state.retriever is retriever
    assert (build.calls, exists.calls, ingest.calls) == (3, 2, 2)


async def test_warmup_no_reingiere_si_el_indice_existe():
    state = SimpleNamespace(retriever=None)
    ingest = _Flaky(0, [])
    await warmup(
        state,
        build_retriever=_Flaky(0, "r"),
        index_exists=_Flaky(0, True),
        ingest=ingest,
        retry_seconds=0,
    )
    assert state.retriever == "r" and ingest.calls == 0


async def test_warmup_sin_auto_ingest_no_consulta_el_indice():
    state = SimpleNamespace(retriever=None)
    exists = _Flaky(0, False)
    await warmup(state, build_retriever=_Flaky(0, "r"), index_exists=exists, ingest=None, retry_seconds=0)
    assert state.retriever == "r" and exists.calls == 0


async def test_warmup_respeta_max_attempts():
    state = SimpleNamespace(retriever=None)
    with pytest.raises(ConnectionError):
        await warmup(
            state,
            build_retriever=_Flaky(99, "r"),
            index_exists=_Flaky(0, True),
            ingest=None,
            retry_seconds=0,
            max_attempts=3,
        )
    assert state.retriever is None
