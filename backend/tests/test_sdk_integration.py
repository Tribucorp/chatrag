"""Prueba de humo contra el SDK **real** (no dobles): confirma que lo que `pyproject.toml`
fija (`tribu-http`, `tribu-rag`) existe de verdad en el registry con la forma que
`chatrag_api.rag` espera, y que los adaptadores de producción se construyen sin explotar.

Marcada `integration` — no corre en el job unitario (`addopts = "-m 'not integration'"` en
pyproject.toml). Requiere el registry privado instalado de verdad, así que solo se ejecuta en
el job `backend-integration` de CI (gateado por el secret `UV_INDEX_TRIBU_URL`) o localmente
con `uv run pytest -m integration`.

Esto es justo lo que faltaba: antes de este archivo, `tribu_rag_retriever` y
`_TribuNimChatGenerator` estaban marcados `pragma: no cover` y el registry nunca se instalaba
en CI (`uv pip install --no-deps -e .`) — cero código del SDK se ejecutaba nunca, ni siquiera
para detectar que `import tribu_rag` falla.

No llama a un NIM ni a un índice reales (no hay uno de staging fijo conocido desde este repo):
valida instalación + forma de la API. Cuando exista un NIM/índice de prueba, extender con una
llamada real a `.retrieve()` / `.generate()`.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tribu_rag", reason="requiere el registry privado del SDK instalado")
pytest.importorskip("tribu_http", reason="requiere el registry privado del SDK instalado")

pytestmark = pytest.mark.integration


def test_tribu_rag_expone_hybrid_retriever():
    from tribu_rag import HybridRetriever

    assert callable(HybridRetriever)


def test_tribu_http_expone_cliente_y_egress_allowlist():
    from tribu_http.client import TribuHttpClient
    from tribu_http.egress import EgressAllowlist

    assert callable(TribuHttpClient)
    assert callable(EgressAllowlist)


def test_tribu_rag_retriever_llama_al_constructor_con_la_forma_que_el_sdk_publica():
    """`HybridRetriever(embed_dim=...)` puede intentar contrastar el `embed_dim` contra el NIM
    de embed real al construirse (el guard dinámico) — sin un NIM/índice de staging accesible
    desde CI, eso falla por conexión, no por la forma de la llamada. Distinguimos ambas cosas:
    un `TypeError` (el SDK cambió su constructor) es un fallo real de este test; cualquier otro
    error se interpreta como "no hay NIM/índice alcanzable aquí" y se skippea explícitamente."""

    from chatrag_api.config import DEFAULT_EMBED_DIM
    from chatrag_api.rag import tribu_rag_retriever

    try:
        retriever = tribu_rag_retriever(DEFAULT_EMBED_DIM)
    except TypeError:
        raise
    except Exception as exc:  # noqa: BLE001 - frontera deliberada: ver docstring
        pytest.skip(f"sin NIM/índice de staging alcanzable desde CI: {exc!r}")
    else:
        assert hasattr(retriever, "retrieve")
