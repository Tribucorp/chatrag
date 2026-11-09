"""Cabecera de los documentos del corpus: `source:` → `source_uri` citable, `acl:` → etiquetas."""

from __future__ import annotations

from chatrag_api.ingest import parse_front_matter, split_front_matter


def test_source_pasa_a_source_uri_y_no_al_texto():
    doc = "---\nsource: https://www.dell.com/support/\n---\n\n# iDRAC\n\nCuerpo."
    meta, body = parse_front_matter(doc)
    assert meta.source == "https://www.dell.com/support/"
    assert meta.acl == frozenset()
    assert body == "# iDRAC\n\nCuerpo."


def test_acl_de_la_cabecera():
    meta, _ = parse_front_matter("---\nacl: soporte, Comercial\n---\nx")
    assert meta.acl == frozenset({"soporte", "comercial"})


def test_acl_mal_formada_no_vuelve_publico_el_documento():
    meta, _ = parse_front_matter("---\nacl: soporte, ../x\n---\nx")
    assert meta.acl == frozenset({"acl-invalida"})
    # `acl:` presente pero vacía: ambiguo → tampoco público.
    meta, _ = parse_front_matter("---\nacl: ,\n---\nx")
    assert meta.acl == frozenset({"acl-invalida"})


def test_source_con_esquema_no_http_se_ignora():
    source, body = split_front_matter("---\nsource: javascript:alert(1)\n---\nTexto")
    assert source is None and body == "Texto"
    assert split_front_matter("Sin cabecera") == (None, "Sin cabecera")


def test_source_kb_para_la_base_de_conocimiento_propia():
    meta, _ = parse_front_matter("---\nsource: kb://ventisca/escalado\nacl: soporte\n---\nx")
    assert meta.source == "kb://ventisca/escalado"
    assert meta.acl == frozenset({"soporte"})
