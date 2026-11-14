"""v27: camada de rede única — tempo-limite, backoff exponencial, redação de segredos, cota e lote assíncrono."""
import sys
import types

import pytest

from src.data_hub import net


def test_redact_removes_env_secrets_and_patterns(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "abc123secretvalue")
    msg = ("erro em https://x.io/v3?key=zzz999&league=71 headers x-apisports-key: abc123secretvalue "
           "Bearer eyJhbGciOi.tok token=qq " + net.GOOGLE_KEY_PREFIX + "B" * 30)
    out = net.redact(msg)
    for leak in ("abc123secretvalue", "zzz999", "eyJhbGciOi", net.GOOGLE_KEY_PREFIX + "B", "token=qq"):
        assert leak not in out
    assert "league=71" in out                          # o resto da mensagem continua legível


def test_get_retries_with_exponential_backoff_then_succeeds(monkeypatch):
    calls, sleeps = [], []
    seq = [net.Response(503, b""), net.Response(429, b"", {"Retry-After": "7"}), net.Response(200, b'{"ok": 1}')]
    monkeypatch.setattr(net, "_send", lambda u, p, h, t: (calls.append(t), seq.pop(0))[1])
    r = net.get("https://exemplo/x", sleep=sleeps.append, backoff=1.0)
    assert r.json() == {"ok": 1} and calls == [15.0, 15.0, 15.0]   # tempo-limite padrão 15 s
    assert sleeps == [1.0, 7.0]                                    # 2^0 · 1 s; depois respeita Retry-After


def test_get_does_not_retry_client_errors(monkeypatch):
    n = []
    monkeypatch.setattr(net, "_send", lambda *a: (n.append(1), net.Response(404, b"", url="https://x/y?key=SEGREDO1"))[1])
    r = net.get("https://x/y", sleep=lambda s: None)
    assert r.status_code == 404 and len(n) == 1
    with pytest.raises(net.HTTPStatusError) as e:
        r.raise_for_status()
    assert "SEGREDO1" not in str(e.value)


def test_network_error_message_is_redacted(monkeypatch, tmp_path):
    monkeypatch.setattr(net, "LOG_FILE", tmp_path / "log.txt")

    def boom(*a):
        raise OSError("timed out talking to https://api/x?apikey=TOPSECRET42")
    monkeypatch.setattr(net, "_send", boom)
    with pytest.raises(net.NetError) as e:
        net.get("https://api/x?apikey=TOPSECRET42", sleep=lambda s: None)
    assert "TOPSECRET42" not in str(e.value)


def test_log_never_writes_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", net.GOOGLE_KEY_PREFIX + "Q" * 35)
    f = tmp_path / "sync_log.txt"
    net.log("teste", "falhou com chave " + net.GOOGLE_KEY_PREFIX + "Q" * 35, path=f)
    assert "QQQQ" not in f.read_text(encoding="utf-8")


def test_fetch_many_async_path_limits_concurrency(monkeypatch):
    """Com httpx presente, baixa em paralelo limitado (aqui um httpx falso para não depender da rede)."""
    import asyncio

    state = {"now": 0, "max": 0}

    class FakeResp:
        def __init__(self, url):
            self.status_code, self.content, self.headers, self.url = 200, url.encode(), {}, url

    class AsyncClient:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.01)
            state["now"] -= 1
            return FakeResp(url)

    fake = types.SimpleNamespace(AsyncClient=AsyncClient, HTTPError=Exception, Client=None)
    monkeypatch.setitem(sys.modules, "httpx", fake)
    urls = [f"https://h/{i}" for i in range(7)]
    out = net.fetch_many(urls, max_concurrency=2)
    assert set(out) == set(urls) and all(out[u].content == u.encode() for u in urls)
    assert state["max"] == 2


def test_api_futebol_stops_gracefully_at_daily_quota(tmp_path, monkeypatch):
    from src.data_hub.db import DataHubDB
    from src.data_hub.http import QuotaExceeded
    from src.data_hub.sources.api_futebol import ApiFutebolProvider

    db = DataHubDB(db_path=str(tmp_path / "h.db"), schema_path="database/schema.sql")
    p = ApiFutebolProvider(api_key="k-teste", db=db, daily_quota=2, min_interval_s=0)
    monkeypatch.setattr(net, "_send", lambda *a: net.Response(200, b"[]"))
    p._get("/a")
    p._get("/b")
    with pytest.raises(QuotaExceeded):
        p._get("/c")


def test_api_football_sync_recent_stops_at_quota(tmp_path, monkeypatch):
    from src.data_hub.db import DataHubDB
    from src.data_hub.http import QuotaExceeded
    from src.data_hub.sources.api_football import ApiFootballProvider

    db = DataHubDB(db_path=str(tmp_path / "h.db"), schema_path="database/schema.sql")
    p = ApiFootballProvider(db, api_key="k-teste")
    n = []

    def q(*a, **k):
        n.append(1)
        raise QuotaExceeded("Cota diária de 100 requisições da fonte 'api_football' esgotada.")
    monkeypatch.setattr(p, "_get", q)
    monkeypatch.setattr(net, "LOG_FILE", tmp_path / "log.txt")
    out = p.sync_recent(days_back=1)
    assert out.get("cota_atingida") == 1 and len(n) == 1      # parou na primeira recusa, sem insistir
