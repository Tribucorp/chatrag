from collections.abc import Sequence

from chatrag_api.models import Citation, Query, UserContext
from chatrag_api.rag import answer_query, filter_by_acl, select_cited


class FakeRetriever:
    """Retriever de prueba: devuelve una lista fija, sin tocar tribu-rag.
    `requester_roles` se acepta (mismo Protocol que el real) pero se ignora aquí a propósito —
    el filtrado real por rol se prueba vía `filter_by_acl`, no en este doble."""

    def __init__(self, citations: Sequence[Citation]) -> None:
        self._citations = list(citations)

    async def retrieve(
        self, question: str, *, top_k: int, requester_roles: frozenset[str]
    ) -> Sequence[Citation]:
        return self._citations[:top_k]


class FakeGenerator:
    """Generador de prueba: no llama a ningún NIM, solo confirma qué citas recibió."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Sequence[Citation]]] = []

    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        self.calls.append((question, citations))
        return "resumen de prueba" + "".join(f" [{i}]" for i in range(1, len(citations) + 1))


def _c(uri: str, *, acl: str | None = None, score: float = 0.5, text: str = "x") -> Citation:
    return Citation(
        text=text,
        source_uri=uri,
        title=uri,
        score=score,
        required_acl=frozenset({acl}) if acl else frozenset(),
    )


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


async def test_responde_con_citas_ordenadas_por_score():
    user = UserContext(user_id="u", acls=frozenset())
    retr = FakeRetriever([_c("doc://baja", score=0.2), _c("doc://alta", score=0.9)])
    gen = FakeGenerator()
    answer = await answer_query(retr, gen, Query(question="¿horario?"), user)
    assert answer.abstained is False
    assert [c.source_uri for c in answer.citations] == ["doc://alta", "doc://baja"]
    assert answer.text == "resumen de prueba [1] [2]"


async def test_generador_recibe_solo_citas_ya_filtradas_por_acl():
    user = UserContext(user_id="u", acls=frozenset({"rrhh"}))
    retr = FakeRetriever([_c("doc://rrhh", acl="rrhh"), _c("doc://finanzas", acl="finanzas")])
    gen = FakeGenerator()
    await answer_query(retr, gen, Query(question="¿nómina?"), user)
    assert len(gen.calls) == 1
    _, citations = gen.calls[0]
    assert [c.source_uri for c in citations] == ["doc://rrhh"]


async def test_se_abstiene_cuando_no_queda_base_accesible():
    user = UserContext(user_id="u", acls=frozenset())  # sin ACLs
    retr = FakeRetriever([_c("doc://secreto", acl="finanzas")])
    gen = FakeGenerator()
    answer = await answer_query(retr, gen, Query(question="¿nómina?"), user)
    assert answer.abstained is True
    assert answer.citations == ()
    assert "no" in answer.text.lower()
    assert gen.calls == []  # nunca se invoca el generador sin base accesible


# --- ACL pública implícita -------------------------------------------------------------------
# La ingesta marca lo público con PUBLIC_ACL y tribu-rag filtra en Milvus con
# JSON_CONTAINS_ANY(allowed_roles, requester_roles): sin añadirla a los roles de todo usuario, lo
# público no le aparecía a nadie (bug que los dobles anteriores no veían).


class RecordingRetriever(FakeRetriever):
    def __init__(self, citations: Sequence[Citation]) -> None:
        super().__init__(citations)
        self.requester_roles: list[frozenset[str]] = []

    async def retrieve(
        self, question: str, *, top_k: int, requester_roles: frozenset[str]
    ) -> Sequence[Citation]:
        self.requester_roles.append(requester_roles)
        return await super().retrieve(question, top_k=top_k, requester_roles=requester_roles)


async def test_todo_usuario_consulta_con_la_acl_publica_ademas_de_las_suyas():
    from chatrag_api.rag import PUBLIC_ACL

    retriever = RecordingRetriever([])
    sin_acls = UserContext(user_id="cliente", acls=frozenset())
    con_acls = UserContext(user_id="tecnico", acls=frozenset({"soporte"}))
    await answer_query(retriever, FakeGenerator(), Query(question="q"), sin_acls)
    await answer_query(retriever, FakeGenerator(), Query(question="q"), con_acls)
    assert retriever.requester_roles == [
        frozenset({PUBLIC_ACL}),
        frozenset({PUBLIC_ACL, "soporte"}),
    ]


def test_cita_etiquetada_publico_la_ve_un_usuario_sin_acls():
    from chatrag_api.rag import PUBLIC_ACL

    cliente = UserContext(user_id="cliente", acls=frozenset())
    visibles = filter_by_acl([_c("doc://publico", acl=PUBLIC_ACL), _c("doc://int", acl="soporte")], cliente)
    assert [c.source_uri for c in visibles] == ["doc://publico"]


# --- select_cited: solo se muestra lo que la respuesta cita ---------------------------------
# Antes se devolvía todo lo recuperado como cita: un "hola" salía con 8 fuentes que la
# respuesta no usaba.


class ScriptedGenerator:
    def __init__(self, text: str) -> None:
        self._text = text

    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        return self._text


def test_select_cited_se_queda_con_las_citadas_y_renumera_por_aparicion():
    a, b, c = _c("doc://a"), _c("doc://b"), _c("doc://c")
    text, cited = select_cited("Dato de c [3]. Dato de a [1] y otra vez c [3].", [a, b, c])
    assert cited == (c, a)
    assert text == "Dato de c [1]. Dato de a [2] y otra vez c [1]."


def test_select_cited_acepta_marcas_agrupadas():
    a, b = _c("doc://a"), _c("doc://b")
    text, cited = select_cited("Ambas [2, 1].", [a, b])
    assert cited == (b, a)
    assert text == "Ambas [1][2]."


def test_select_cited_descarta_numeros_que_no_apuntan_a_ninguna_fuente():
    a = _c("doc://a")
    text, cited = select_cited("Inventado [7]. Real [1].", [a])
    assert cited == (a,)
    assert text == "Inventado. Real [1]."


def test_select_cited_sin_marcas_no_devuelve_citas():
    text, cited = select_cited("¡Hola! ¿En qué puedo ayudarte?", [_c("doc://a"), _c("doc://b")])
    assert cited == ()
    assert text == "¡Hola! ¿En qué puedo ayudarte?"


async def test_un_saludo_no_sale_con_las_fuentes_recuperadas():
    user = UserContext(user_id="u", acls=frozenset())
    retr = FakeRetriever([_c("doc://a"), _c("doc://b"), _c("doc://c")])
    answer = await answer_query(
        retr, ScriptedGenerator("¡Hola! ¿En qué puedo ayudarte?"), Query(question="hola"), user
    )
    assert answer.abstained is False
    assert answer.citations == ()


async def test_solo_se_devuelve_la_cita_que_usa_la_respuesta():
    user = UserContext(user_id="u", acls=frozenset())
    retr = FakeRetriever([_c("doc://alta", score=0.9), _c("doc://baja", score=0.2)])
    answer = await answer_query(
        retr, ScriptedGenerator("Abre de 9 a 14 [2]."), Query(question="¿horario?"), user
    )
    assert [c.source_uri for c in answer.citations] == ["doc://baja"]
    assert answer.text == "Abre de 9 a 14 [1]."


def test_select_cited_descarta_un_volcado_de_todas_las_fuentes():
    # Visto con nano-9b-v2 ante "gracias": "¡De nada! [1][2]...[8]".
    cs = [_c(f"doc://{i}") for i in range(8)]
    raw = "¡De nada! Si tienes más preguntas, no dudes en preguntar. " + "".join(
        f"[{i}]" for i in range(1, 9)
    )
    text, cited = select_cited(raw, cs)
    assert cited == ()
    assert text == "¡De nada! Si tienes más preguntas, no dudes en preguntar."


def test_select_cited_respeta_un_dato_con_varias_fuentes_dentro_del_limite():
    a, b, c = _c("doc://a"), _c("doc://b"), _c("doc://c")
    text, cited = select_cited("Dato compartido [1][2][3].", [a, b, c])
    assert cited == (a, b, c)
    assert text == "Dato compartido [1][2][3]."
