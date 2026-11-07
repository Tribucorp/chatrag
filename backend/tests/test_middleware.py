from chatrag_api.middleware import RateLimiter


def test_rate_limiter_permite_hasta_el_maximo():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.allow("ip1", now=0.0) is True
    assert limiter.allow("ip1", now=0.1) is True
    assert limiter.allow("ip1", now=0.2) is True
    assert limiter.allow("ip1", now=0.3) is False  # 4ª en la ventana: rechazada


def test_rate_limiter_es_por_clave():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("ip1", now=0.0) is True
    assert limiter.allow("ip2", now=0.0) is True  # otra IP, su propia cuota
    assert limiter.allow("ip1", now=0.1) is False


def test_rate_limiter_libera_tras_la_ventana():
    limiter = RateLimiter(max_requests=1, window_seconds=10)
    assert limiter.allow("ip1", now=0.0) is True
    assert limiter.allow("ip1", now=5.0) is False  # todavía dentro de la ventana
    assert limiter.allow("ip1", now=10.1) is True  # la ventana ya expiró
