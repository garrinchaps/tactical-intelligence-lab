"""Rodada 21: contas individuais (senha/convite/cookie), dicas variadas do pré-jogo, telas de carregamento por área."""
import time

import numpy as np
import pandas as pd


def test_accounts_create_verify_invite_and_block(tmp_path, monkeypatch):
    from src.ui import accounts as A

    db = tmp_path / "c.db"
    monkeypatch.setenv("TIL_CONVITE", "futebol2026")
    assert "convite" in A.create_account("Ana", "ana@x.com", "senha1234", "errado", path=db)
    assert A.create_account("Ana", "ana@x.com", "senha1234", "futebol2026", path=db) == ""
    assert "Já existe" in A.create_account("Ana", "ANA@x.com", "senha1234", "futebol2026", path=db)
    assert A.verify("ana@x.com", "senha1234", path=db) == ""
    assert A.verify("ana@x.com", "outra", path=db) != ""
    A.set_status("ana@x.com", "bloqueada", path=db)
    assert "bloqueada" in A.verify("ana@x.com", "senha1234", path=db)
    rows = A.list_accounts(path=db)
    assert rows[0]["email"] == "ana@x.com" and "senha1234" not in str(rows)        # senha nunca aparece
    assert len(A.create_account("B", "b@x.com", "curta", "futebol2026", path=db)) > 0  # senha curta recusada


def test_google_accounts_registered(tmp_path):
    from src.ui import accounts as A

    db = tmp_path / "c.db"
    assert A.register_google("Prof@Uni.br", "Professor", path=db) == ""
    assert A.list_accounts(path=db)[0]["metodo"] == "google"
    assert A.is_active("prof@uni.br", path=db)


def test_signed_cookie_token():
    from src.ui import accounts as A

    key = b"k" * 32
    tok = A.make_token("ana@x.com", secret=key)
    assert A.read_token(tok, secret=key) == "ana@x.com"
    assert A.read_token(tok, secret=b"z" * 32) is None                  # assinatura errada
    assert A.read_token(tok[:-2] + "00", secret=key) is None
    assert A.read_token(A.make_token("ana@x.com", days=-1, secret=key), secret=key) is None   # vencido


def test_accounts_mode_flag(monkeypatch):
    from src.ui import gate

    monkeypatch.setenv("TIL_CONTAS", "1")
    assert gate.accounts_mode()
    monkeypatch.setenv("TIL_CONTAS", "0")
    assert not gate.accounts_mode()


def test_google_login_config_file():
    import tomllib

    from src.tools.configurar_login import build

    d = tomllib.loads(build("https://pc.tail.ts.net/", "cid", "sec", "cookie"))
    assert d["auth"]["redirect_uri"] == "https://pc.tail.ts.net/oauth2callback"
    assert d["auth"]["google"]["server_metadata_url"].startswith("https://accounts.google.com")


def _ref(n=200, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({c: rng.uniform(0, 1, n) for c in ("crs_p90", "aer_pct", "lb_p90", "tob_p90", "duel_pct",
                                                           "off_p90", "disp_p90", "crs_pct")})


def test_combo_findings_cross_and_offside():
    from src.squad import matchups as MU

    ref = _ref()
    my_xi = [{"papel": "RB", "jogador": "Lateral Bom"}, {"papel": "ST", "jogador": "Centroavante Alto"}]
    rv_xi = [{"papel": "CB", "jogador": "Zagueiro Baixo"}, {"papel": "ST", "jogador": "Atacante Banheira"}]
    ms = pd.DataFrame([{"player_name": "Lateral Bom", "mins": 1800, "jogos": 20, "crs_p90": .99, "crs_pct": .9},
                       {"player_name": "Centroavante Alto", "mins": 1800, "jogos": 20, "aer_pct": .95}])
    rs = pd.DataFrame([{"player_name": "Zagueiro Baixo", "mins": 1800, "jogos": 20, "aer_pct": .05},
                       {"player_name": "Atacante Banheira", "mins": 1800, "jogos": 20, "off_p90": .99, "off": 12}])
    out = MU.combo_findings(my_xi, rv_xi, ms, rs, ref, "Nós", "Eles")
    kinds = {x["dimensao"] for x in out["forcar"]} | {x["dimensao"] for x in out["proteger"]}
    assert "cruzamento" in kinds and "impedimento" in kinds


def test_diverse_caps_same_kind():
    from src.squad import matchups as MU

    items = [{"dimensao": "drible"}] * 4 + [{"dimensao": "aereo"}]
    out = MU._diverse(items, per_kind=2)
    assert [x["dimensao"] for x in out] == ["drible", "drible", "aereo"]


def test_loading_screen_per_area():
    from src.ui import loading as L

    a, b = L.overlay_html("scout"), L.overlay_html("rankings")
    assert "Garimpando" in a and "Ordenando" in b and a != b
    assert "til-overlay" in L.overlay_html("tela-desconhecida")
