"""H3: nenhum teste pode acessar a internet nem gastar cota de API (a rede real é bloqueada aqui)."""
import pytest


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    from src.data_hub import net

    def bloqueado(url, *a, **k):
        raise net.NetError(f"rede bloqueada nos testes (tentou {str(url)[:60]})")
    monkeypatch.setattr(net, "_send", bloqueado)
    yield
