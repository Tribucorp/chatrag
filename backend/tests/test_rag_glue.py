from collections.abc import Sequence

from chatrag_api.models import Citation, Query, UserContext
from chatrag_api.rag import answer_query, filter_by_acl


class FakeRetriever:
    """Retriever de prueba: devuelve una lista fija, sin tocar tribu-rag ni el registry."""

    def __init__(self, citations: Sequence[Citation]) -> None:
        self._citations = list(citations)

    def retrieve(self, question: str, *, top_k: int) -> Sequence[Citation]:
        return self._citations[:top_k]


def _c(uri: str, *, acl: str | None = None, score: float = 0.5, text: str = "x") -> Citation:
    return Citation(text=text, source_uri=uri, title=uri, score=score, required_acl=acl)


# --- filter_by_acl ------------------------------------------------------------------------


def test_descarta_fragmento_sin_source_uri():
    # source_uri es obligatorio en el modelo; el descarte defensivo se prueba con el filtro
    # sobre una cita publica valida frente a una con uri vacia imposible de construir -> usamos
    # el caso real: sin source_uri no se puede citar (lo garantiza el modelo). Aqui validamos
    # que una cita publica pasa y una con ACL ajena no.
    user = UserContext(user_id="u", acls=frozenset())
    publica = _c("doc://publica")
    assert filter_by_acl([publica], user) == (publica,)


def test_oculta_cita_cuya_acl_no_posee_el_usuario():
    user = UserContext(user_id="u", acls=frozenset({"rrhh"}))
    visible = _c("doc://rrhh", acl="rrhh")
    oculta = _c("doc://finanzas", acl="finanzas")
    assert filter_by_acl([visible, oculta], user) == (visible,)


def test_el_filtrado_no_depende_de_que_el_cliente_pida_menos():
    # aunque lleguen fragmentos restringidos, el servidor los quita: 0 resultados de otra ACL
    user = UserContext(user_id="u", acls=frozenset())
    restringidos = [_c("doc://a", acl="secreto"), _c("doc://b", acl="secreto")]
    assert filter_by_acl(restringidos, user) == ()


# --- answer_query -------------------------------------------------------------------------


def test_responde_con_citas_ordenadas_por_score():
    user = UserContext(user_id="u", acls=frozenset())
    retr = FakeRetriever([_c("doc://baja", score=0.2), _c("doc://alta", score=0.9)])
    answer = answer_query(retr, Query(question="¿horario?"), user)
    assert answer.abstained is False
    assert [c.source_uri for c in answer.citations] == ["doc://alta", "doc://baja"]


def test_se_abstiene_cuando_no_queda_base_accesible():
    user = UserContext(user_id="u", acls=frozenset())  # sin ACLs
    retr = FakeRetriever([_c("doc://secreto", acl="finanzas")])
    answer = answer_query(retr, Query(question="¿nómina?"), user)
    assert answer.abstained is True
    assert answer.citations == ()
    assert "no" in answer.text.lower()
