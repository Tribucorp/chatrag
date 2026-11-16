from collections.abc import Mapping, Sequence

from chatrag_api.audit import NullAuditLog
from chatrag_api.models import Citation, Query, UserContext
from chatrag_api.rag import answer_query


class FakeRetriever:
    def __init__(self, citations: Sequence[Citation]) -> None:
        self._citations = list(citations)

    async def retrieve(
        self, question: str, *, top_k: int, requester_roles: frozenset[str]
    ) -> Sequence[Citation]:
        return self._citations[:top_k]


class FakeGenerator:
    async def generate(self, question: str, citations: Sequence[Citation]) -> str:
        return "resumen de prueba"


class SpyAuditLog:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Mapping[str, object]]] = []

    async def record(self, *, actor_id: str, action: str, payload: Mapping[str, object]) -> None:
        self.calls.append((actor_id, action, payload))


async def test_null_audit_log_no_hace_nada():
    # Solo confirma que satisface el Protocol sin explotar -- es el default cuando la
    # auditoría no está configurada (ver config.py: audit_database_url/audit_chain_key).
    await NullAuditLog().record(actor_id="u", action="x", payload={})


async def test_registra_abstencion_con_lo_bloqueado_por_acl():
    user = UserContext(user_id="u1", acls=frozenset())
    retr = FakeRetriever(
        [Citation(text="secreto", source_uri="doc://fin", score=0.9, required_acl=frozenset({"finanzas"}))]
    )
    audit = SpyAuditLog()
    await answer_query(retr, FakeGenerator(), Query(question="¿nómina?"), user, audit_log=audit)

    assert len(audit.calls) == 1
    actor_id, action, payload = audit.calls[0]
    assert actor_id == "u1"
    assert action == "chatrag.query.abstained"
    assert payload["blocked"] == [{"source_uri": "doc://fin", "required_acl": ["finanzas"]}]


async def test_registra_respuesta_con_lo_mostrado_y_lo_bloqueado():
    user = UserContext(user_id="u1", acls=frozenset({"rrhh"}))
    retr = FakeRetriever(
        [
            Citation(text="público", source_uri="doc://pub", score=0.9),
            Citation(
                text="secreto", source_uri="doc://fin", score=0.95, required_acl=frozenset({"finanzas"})
            ),
        ]
    )
    audit = SpyAuditLog()
    await answer_query(retr, FakeGenerator(), Query(question="¿nómina?"), user, audit_log=audit)

    assert len(audit.calls) == 1
    _actor_id, action, payload = audit.calls[0]
    assert action == "chatrag.query.answered"
    assert payload["shown"] == ["doc://pub"]
    assert payload["blocked"] == [{"source_uri": "doc://fin", "required_acl": ["finanzas"]}]


async def test_sin_audit_log_usa_null_audit_log_sin_fallar():
    user = UserContext(user_id="u1", acls=frozenset())
    retr = FakeRetriever([Citation(text="x", source_uri="doc://p", score=0.9)])
    answer = await answer_query(retr, FakeGenerator(), Query(question="¿horario?"), user)
    assert answer.abstained is False
