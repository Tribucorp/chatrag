from chatrag_api.conversations import ConversationLog


def test_record_y_recent_devuelve_lo_mas_reciente_primero():
    log = ConversationLog(max_entries=10)
    log.record(user_id="u1", question="¿q1?", answer="a1", abstained=False)
    log.record(user_id="u1", question="¿q2?", answer="a2", abstained=False)

    entries = log.recent()
    assert [e.question for e in entries] == ["¿q2?", "¿q1?"]


def test_recent_respeta_el_limite():
    log = ConversationLog(max_entries=10)
    for i in range(5):
        log.record(user_id="u1", question=f"¿q{i}?", answer="a", abstained=False)

    assert len(log.recent(limit=2)) == 2


def test_buffer_circular_descarta_las_mas_antiguas_pero_los_contadores_no_se_capan():
    log = ConversationLog(max_entries=2)
    for i in range(5):
        log.record(user_id="u1", question=f"¿q{i}?", answer="a", abstained=False)

    entries = log.recent()
    assert [e.question for e in entries] == ["¿q4?", "¿q3?"]  # solo caben 2
    assert log.metrics().total_answered == 5  # el contador acumulado no se capa


def test_metrics_calcula_tasa_de_abstencion_y_top_sources():
    log = ConversationLog(max_entries=10)
    log.record(
        user_id="u1", question="q1", answer="a1", abstained=False,
        citations_shown=("doc://a", "doc://b"),
    )
    log.record(
        user_id="u1", question="q2", answer="a2", abstained=False,
        citations_shown=("doc://a",),
    )
    log.record(user_id="u1", question="q3", answer="", abstained=True)

    metrics = log.metrics()
    assert metrics.total_queries == 3
    assert metrics.total_answered == 2
    assert metrics.total_abstained == 1
    assert metrics.abstention_rate == 1 / 3
    assert metrics.top_sources[0].source_uri == "doc://a"
    assert metrics.top_sources[0].count == 2


def test_metrics_sin_consultas_no_divide_por_cero():
    log = ConversationLog(max_entries=10)
    metrics = log.metrics()
    assert metrics.total_queries == 0
    assert metrics.abstention_rate == 0.0
