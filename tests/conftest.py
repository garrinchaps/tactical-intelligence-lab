"""H3: nenhum teste pode acessar a internet nem gastar cota de API (a rede real é bloqueada aqui)."""
import pytest


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    from src.data_hub import net

    def bloqueado(url, *a, **k):
        raise net.NetError(f"rede bloqueada nos testes (tentou {str(url)[:60]})")
    monkeypatch.setattr(net, "_send", bloqueado)
    yield


@pytest.fixture(autouse=True)
def _sem_catalogo_em_disco(monkeypatch):
    """Rodada 22: o catálogo em memória/disco é por processo — nos testes cada banco temporário começa do zero."""
    monkeypatch.setenv("TIL_CATALOGO_DISCO", "0")
    from src.data_hub.db import DataHubDB

    DataHubDB._CAT.clear()
    yield
    DataHubDB._CAT.clear()
