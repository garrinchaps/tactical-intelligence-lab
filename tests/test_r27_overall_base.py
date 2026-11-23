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
    assert float(f.iloc[0]) >= 80          # titular frequente do Brasil Sub-17 e dos melhores na nota
    u2 = u.assign(selecao="Malta U17", selecao_base_jogos=1, selecao_base_pct=np.nan)
    assert float(POT.youth_floor(u2).iloc[0]) < 70   # 1 jogo por seleção pequena: piso baixo (sem faixa fixa)


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


def test_entrosamento_prefere_dupla_que_vence_junta():
    import numpy as np

    from src.squad.matchday import chemistry_refine

    rows = []
    for g in range(15):                       # A+B começam juntos e vencem; C joga com A nos outros e perde
        win = g < 12
        partner = "B" if win else "C"
        for pl in ("A", partner, "X"):
            rows.append(dict(match_id=g, data=f"2026-10-{g + 1:02d}", home_team_name="T", away_team_name="R",
                             team_name="T", home_score=2 if win else 0, away_score=0 if win else 2, jogador=pl, titular=1))
    lu = pd.DataFrame(rows)
    slots = [("CB", 24, 30), ("CB", 24, 50)]
    names = ["A", "C", "B"]
    val = np.array([7.0, 7.4, 7.0])
    score = np.array([[7.0, 7.4, 7.0], [7.0, 7.4, 7.0]])
    best, notes = chemistry_refine({0: 0, 1: 1}, score, val, slots, names, lu)
    assert {names[j] for j in best.values()} == {"A", "B"}
    assert any("entrosamento" in t for t in notes.values())


def test_liga_de_outro_pais_sai_dos_jogos_do_time(tmp_path):
    from src.data_hub.db import DataHubDB
    from src.data_hub.gender import foreign_competitions

    db = DataHubDB(tmp_path / "t.db")
    with db.connect() as c:
        req = [r[1] for r in c.execute("PRAGMA table_info(matches)").fetchall() if r[3] and r[4] is None and not r[5]]
        for i in range(15):
            comp = "Brasileirão Série A" if i < 12 else "Liga MX"
            row = {"match_id": 100 + i, "match_date": f"2026-10-{i + 1:02d}", "home_team_name": "Santos Teste",
                   "away_team_name": f"Rival {i}", "competition_name": comp}
            for k in req:
                row.setdefault(k, "x")
            c.execute(f"INSERT INTO matches ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", list(row.values()))
    assert foreign_competitions(["Santos Teste"], db=db) == ["Liga MX"]


def test_nome_unico_de_liga():
    from src.scout.evaluation import canonical_league

    assert canonical_league("campeonato-brasileiro-serie-a") == canonical_league("Brasileirão Série A")


def test_treino_rotula_fatos_do_jogador_citado(tmp_path):
    import json

    from src.intelligence.lab_ai.selector import N_FEATURES
    from src.intelligence.lab_ai.trainer import build_dataset

    feats = [0.1] * N_FEATURES
    row = {"interaction_id": "x1", "question": "como jogou o Igor Gomes?",
           "facts": [{"key": "passes", "player": "Igor Gomes", "features": feats},
                     {"key": "passes", "player": "Bernard", "features": feats},
                     {"key": "posse", "player": None, "features": feats}]}
    shown = tmp_path / "shown.jsonl"
    shown.write_text(json.dumps(row) + "\n", encoding="utf-8")
    X, y, w, g, src = build_dataset(shown, tmp_path / "fb.jsonl")
    assert len(y) == 2 and sorted(y.tolist()) == [0.0, 1.0]


def test_so_o_primeiro_potencial_chega_a_95():
    from src.scout.overall import top_potential_ladder

    out = top_potential_ladder(pd.Series([103, 99, 98, 97, 96, 85]))
    assert (out == 95).sum() == 1 and out.iloc[-1] == 85


def test_sugestoes_por_perfil_respeitam_titular_e_verba():
    from src.ui.pages.scout import _profile_groups

    roster = pd.DataFrame({"papel": ["AM"], "qualidade": [79]})
    ranked = pd.DataFrame({
        "nome": ["Jovem", "Investe", "Pronto", "Fraco"], "papel_alvo": ["AM"] * 4,
        "idade": [19, 24, 28, 26], "qualidade": [70, 77, 82, 65], "potencial": [86, 84, 83, 66],
        "valor_mercado_eur": [3e6, 12e6, 22e6, .3e6], "score_scout": [70, 70, 70, 90]})
    g = {t: set(df["nome"]) for t, _, df in _profile_groups(ranked, roster, 20e6)}
    assert "Jovem" in g["🌱 Jovens promessas"] and "Investe" in g["📈 Para investir"]
    assert "Pronto" in g["⭐ Para chegar e jogar"]
    assert all("Fraco" not in v for v in g.values())
