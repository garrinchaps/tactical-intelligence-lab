import numpy as np
import pandas as pd

from src.scout import overall as O
from src.scout import potential as POT
from src.scout.evaluation import prior_level


def test_nivel_das_ligas_com_endereco_e_arabia():
    assert prior_level("premier-league") == 1.0
    assert prior_level("super-lig") == prior_level("Süper Lig")
    assert prior_level("Arábia Saudita — Saudi Pro League") < prior_level("campeonato-brasileiro-serie-a")
    assert prior_level("Emirados — Pro League") < prior_level("Jupiler Pro League")


def _universe():
    rng = np.random.default_rng(1)
    n = 4000
    u = pd.DataFrame(dict(nome=[f"p{i}" for i in range(n)],
                          papel=rng.choice(["ST", "RW", "CM", "CB", "LB", "GK"], n), idade=rng.integers(18, 35, n),
                          _lvl=rng.choice([.4, .6, .8, 1.0], n), valor_mercado_eur=np.exp(rng.normal(14.5, 1.3, n)),
                          rating_12m=6.6 + rng.normal(0, .35, n), minutos_12m=rng.integers(300, 4000, n),
                          _perf_raw=50 + rng.normal(0, 15, n), _conf=.8, qualidade=60))
    stars = pd.DataFrame([
        dict(nome="Craque", papel="ST", idade=26, _lvl=1.0, valor_mercado_eur=180e6, rating_12m=7.6, minutos_12m=4000,
             _perf_raw=80, _conf=.8, qualidade=60),
        dict(nome="Veterano Arabia", papel="ST", idade=31, _lvl=.6, clube_liga="Arábia Saudita — Saudi Pro League",
             valor_mercado_eur=25e6, rating_12m=7.7, minutos_12m=3400, _perf_raw=78, _conf=.8, qualidade=60)])
    return pd.concat([u, stars], ignore_index=True)


def test_valor_de_mercado_separa_o_topo():
    out = O.finalize_overall(_universe(), calibrate_now=False, weights=O.DEFAULT_WEIGHTS)
    q = out.set_index("nome")["qualidade"]
    assert q["Craque"] > q["Veterano Arabia"]
    assert q["Craque"] >= 88


def test_selecao_de_base_da_piso_de_potencial_e_qualidade_estimada():
    u = pd.DataFrame([dict(nome="Garoto", papel="CM", idade=17, qualidade=np.nan, minutos_12m=0,
                           selecao_base_jogos=6, selecao_base_comp="Copa do Mundo Sub-17", selecao="Brazil U17",
                           selecao_base_pct=85.0)])
    q = O.youth_quality(u)
    assert 52 <= float(q["qualidade"].iloc[0]) <= 70
    f = POT.youth_floor(u)
    assert float(f.iloc[0]) >= 80


def test_desenho_estimado_pela_escalacao_sem_lances(tmp_path):
    from src.analytics.tactical_identity import lineup_phases
    from src.data_hub.db import DataHubDB

    db = DataHubDB(tmp_path / "t.db")
    pos = ["GK", "LB", "CB", "CB", "RB", "DM", "DM", "LW", "AM", "RW", "ST"]
    with db.connect() as c:
        cols = [r[1] for r in c.execute("PRAGMA table_info(matches)").fetchall()]
        req = {r[1]: r for r in c.execute("PRAGMA table_info(matches)").fetchall() if r[3] and r[4] is None and not r[5]}
        row = {"match_id": 1, "match_date": "2026-11-20", "home_team_name": "Time A", "away_team_name": "Time B",
               "competition_name": "Liga X"}
        for k in req:
            row.setdefault(k, "x")
        c.execute(f"INSERT INTO matches ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", list(row.values()))
        for i, p in enumerate(pos):
            c.execute("INSERT INTO match_lineups (match_id, team_name, player_name, position, is_starter, formation) "
                      "VALUES (1, 'Time A', ?, ?, 1, '4-2-3-1')", (f"J{i}", p))
    ph = lineup_phases(db, ["Time A"], {"perfil": {"posse_pct": 58, "cruzamentos": 20, "ppda_aprox": 8},
                                         "referencia": {"posse_pct": 50, "cruzamentos": 15, "ppda_aprox": 11}})
    assert ph and len(ph["com_bola"]["posicoes"]) == 11 and ph["estimado"]
    # com a bola o lateral fica mais alto do que sem a bola
    lb = next(n for n, (x, y) in ph["com_bola"]["posicoes"].items() if n == "J1")
    assert ph["com_bola"]["posicoes"][lb][0] > ph["sem_bola"]["posicoes"][lb][0]
