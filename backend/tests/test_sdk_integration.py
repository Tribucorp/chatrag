"""Prueba de humo contra el SDK **real** (no dobles): confirma que lo que `pyproject.toml`
fija (`tribu-http`, `tribu-rag`, tag del SDK) existe de verdad con la forma que
`chatrag_api.rag`/`chatrag_api.ingest` usan — firmas comprobadas con `inspect.signature().bind`,
sin red (no hay NIM ni Milvus de staging).

Marcada `integration` — no corre en el job unitario (`addopts = "-m 'not integration'"` en
pyproject.toml). Requiere el SDK instalado de verdad (dependencias git, ADR-0020 del SDK): `uv run pytest -m
integration`, o el paso de integración del job `backend` de CI.

Esto es justo lo que faltaba: antes de este archivo, `tribu_rag_retriever` y
`_TribuNimChatGenerator` estaban marcados `pragma: no cover` y el SDK nunca se instalaba
en CI (`uv pip install --no-deps -e .`) — cero código del SDK se ejecutaba nunca, ni siquiera
para detectar que `import tribu_rag` falla.

No llama a un NIM ni a un índice reales (no hay uno de staging fijo conocido desde este repo):
valida instalación + forma de la API. Cuando exista un NIM/índice de prueba, extender con una
llamada real a `.retrieve()` / `.generate()`.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("tribu_rag", reason="requiere el SDK instalado (uv sync)")
pytest.importorskip("tribu_http", reason="requiere el SDK instalado (uv sync)")

pytestmark = pytest.mark.integration


def test_tribu_rag_expone_lo_que_usa_el_retriever_de_produccion():
    """No existe un `HybridRetriever` en tribu-rag (ver docstring de `rag._TribuRagRetriever`):
    la composición embed → Milvus híbrido → rerank la hace el producto con estas piezas."""

    from tribu_rag.embeddings import IndexMetadata, verify_dimension_guard
    from tribu_rag.milvus_store import MilvusVectorStore
    from tribu_rag.nim_client import NimEmbeddingProvider
    from tribu_rag.rerank_client import NimRerankClient, rerank_chunks

    for simbolo in (IndexMetadata, verify_dimension_guard, NimRerankClient, rerank_chunks):
        assert callable(simbolo)
    for metodo in ("query_hybrid", "upsert", "read_index_metadata", "write_index_metadata"):
        assert callable(getattr(MilvusVectorStore, metodo))
    assert callable(NimEmbeddingProvider.embed)


def test_tribu_http_expone_cliente_y_egress_allowlist():
    from tribu_http.client import TribuHttpClient
    from tribu_http.egress import EgressAllowlist

    assert callable(TribuHttpClient)
    assert callable(EgressAllowlist)


def test_constructores_del_sdk_aceptan_los_argumentos_que_pasa_chatrag():
    """Mismos argumentos que `rag.tribu_rag_retriever` e `ingest._build_clients`: si el SDK
    renombra o quita un parámetro, `bind` lanza `TypeError` aquí en vez de en producción."""

    from tribu_http.client import TribuHttpClient
    from tribu_rag.milvus_store import MilvusVectorStore
    from tribu_rag.nim_client import NimEmbeddingProvider
    from tribu_rag.rerank_client import NimRerankClient

    http = object()
    inspect.signature(TribuHttpClient).bind(object(), timeout=300.0)
    inspect.signature(NimEmbeddingProvider).bind(
        http, base_url="http://nim-embed", model_id="m", dimension=2048, input_type="query"
    )
    inspect.signature(MilvusVectorStore).bind(object(), embedding_dim=2048)
    inspect.signature(NimRerankClient).bind(http, base_url="http://nim-rerank", model_id="m")

