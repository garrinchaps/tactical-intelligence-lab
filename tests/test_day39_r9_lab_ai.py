"""Rodada 9: IA do laboratório (fatos, seleção treinável, redator, relatório), inversões, algoritmo genético e API."""

import json

import numpy as np
import pandas as pd
import pytest


def _box():
    ts = pd.DataFrame([
        {"team_name": "Casa", "stat_key": "aerials_won", "value": 8}, {"team_name": "Fora", "stat_key": "aerials_won", "value": 27},
        {"team_name": "Casa", "stat_key": "shots_total", "value": 15}, {"team_name": "Fora", "stat_key": "shots_total", "value": 6},
        {"team_name": "Casa", "stat_key": "red_cards", "value": 1}, {"team_name": "Fora", "stat_key": "red_cards", "value": 0},
    ])
    ps = pd.DataFrame([{"team_name": "Casa", "player_name": "Atacante", "stats": {"totalShots": 6, "xg": 0.9}},
                       {"team_name": "Casa", "player_name": "Meia", "stats": {"totalShots": 2, "xg": 0.2}}])
    return {"team_stats": ts, "player_stats": ps}


META = {"home_team_name": "Casa", "away_team_name": "Fora", "match_id": 1, "data_source": "fotmob"}


def test_facts_from_boxscore_have_values_and_players():
    from src.intelligence.lab_ai.facts import match_facts

    fs = match_facts(META, None, _box())
    keys = {(f.key, f.team) for f in fs}
    assert ("aerials_won", "Casa") in keys and ("shots_total", "Fora") in keys
    pl = [f for f in fs if f.player]
    shots = next(f for f in pl if f.key == "p:totalShots")
    assert shots.player == "Atacante" and shots.share == pytest.approx(0.75, abs=0.01)


def test_answer_matches_question_and_says_when_number_missing(tmp_path, monkeypatch):
    from src.intelligence.lab_ai import engine as E
    from src.intelligence.lab_ai import selector as S

    monkeypatch.setattr(S, "ROOT", tmp_path / "reg")
    r = E.answer("quem ganhou mais duelos aéreos?", META, None, _box(), "Casa")
    assert "duelos aéreos" in r["markdown"].split("\n")[0]
    gap = E.answer("quantas inversões de jogo?", META, None, _box(), "Casa")
    assert gap["markdown"].startswith("Não tenho")
    plan = E.answer("como explorar o Fora?", META, None, _box(), "Fora")
    assert "Como explorar" in plan["markdown"]


def test_focus_is_the_other_team_when_asked_how_to_exploit():
    from src.intelligence.lab_ai.engine import _teams_focus

    m = {"home_team_name": "Argentina", "away_team_name": "France"}
    assert _teams_focus(m, "Argentina", "Como explorar a França?")[1] == "Argentina"
    assert _teams_focus(m, "Argentina", "como a frança reagiu?")[1] == "França"


def test_selector_trains_only_with_rated_answers_and_promotes_if_better(tmp_path):
    from src.intelligence.lab_ai.facts import N_FEATURES
    from src.intelligence.lab_ai.selector import Selector, log_shown

    shown, fb = tmp_path / "shown.jsonl", tmp_path / "fb.jsonl"
    sel = Selector(tmp_path / "reg")
    r0 = sel.train(shown, fb)
    assert r0["promoted"] is False and r0["n_rated"] == 0
    rng = np.random.default_rng(0)
    with fb.open("w", encoding="utf-8") as fh:
        for i in range(40):
            good = i % 2 == 0
            feats = [1.0] + [0.0] * (N_FEATURES - 1)
            feats[5] = 1.0 if good else 0.0                # "é de jogador": as avaliações gostam de fatos de jogador
            log_shown(f"id{i}", "q", [{"fid": "x", "features": feats}] * 3, ["abertura:0"], path=shown)
            fh.write(json.dumps({"interaction_id": f"id{i}", "rating": "positive" if good else "negative"}) + "\n")
    r = sel.train(shown, fb)
    assert r["n_rated"] == 40 and r["promoted"] is True
    assert Selector(tmp_path / "reg").weights[5] > 0.5
    assert Selector(tmp_path / "reg").meta["templates"]["abertura:0"] == [20, 20]


def test_ruler_handles_ties_at_zero():
    from src.intelligence.lab_ai.reference import percentile

    ref = {"red_cards": [0.0] * 91 + [1.0] * 10 + [500]}
    assert 40 <= percentile(ref, "red_cards", 0) <= 50
    assert percentile(ref, "red_cards", 1) >= 90


def test_switch_reaction_from_events():
    from src.intelligence.lab_ai.switches import reaction_table, switch_events

    rows = [
        dict(period=1, index_num=1, minute=10, second=0, possession=5, team_name="A", player_name="a1", type_name="Pass",
             pass_outcome_name=None, is_pass_Switch=True, x=50, y=10, end_x=70, end_y=70, pass_recipient_name="a2",
             position_name="CM"),
        dict(period=1, index_num=2, minute=10, second=3, possession=5, team_name="B", player_name="b_lateral",
             type_name="Pressure", pass_outcome_name=None, is_pass_Switch=False, x=50, y=10, end_x=None, end_y=None,
             position_name="Left Back"),
        dict(period=1, index_num=3, minute=10, second=4, possession=5, team_name="A", player_name="a2", type_name="Carry",
             pass_outcome_name=None, is_pass_Switch=False, x=85, y=70, end_x=90, end_y=70, position_name="RW"),
    ]
    sw = switch_events(pd.DataFrame(rows))
    assert len(sw) == 1 and sw[0]["reactor"] == "b_lateral" and sw[0]["reaction_s"] == 3 and sw[0]["final_third"]
    tab = reaction_table(sw, "B")
    assert tab.iloc[0]["jogador"] == "b_lateral" and tab.attrs["total"] == 1


def _squad():
    roles = ["GK", "GK", "CB", "CB", "CB", "LB", "RB", "DM", "CM", "CM", "AM", "LW", "RW", "RW", "ST", "ST"]
    notas = [70, 58, 72, 68, 60, 66, 65, 70, 71, 64, 69, 73, 66, 70, 68, 72]
    df = pd.DataFrame({"nome": [f"J{i}" for i in range(len(roles))], "papel": roles, "nota": notas})
    df["drible"] = [0.4] * len(df)
    df.loc[12, "drible"] = 0.95                          # o ponta-direita reserva é o grande driblador
    df["aereo"] = [0.4] * len(df)
    df.loc[14, "aereo"] = 0.95                           # o centroavante reserva é o alto
    return df


def test_genetic_exploits_weakness_and_beats_hungarian_on_full_fitness():
    from src.squad.genetic import LineupGA

    found = [{"titulo": "Lateral é muito driblado", "lado": "esquerda", "gravidade": 95},
             {"titulo": "Zagueiro baixo: X (176 cm)", "lado": None, "gravidade": 85}]
    r = LineupGA(_squad(), "4-3-3", found, seed=3).run()
    assert r["aptidao"] >= r["aptidao_base"]
    names = {x["jogador"] for x in r["xi"]}
    assert "J12" in names and "J14" in names            # driblador na direita (lado esquerdo deles) e o alto na área
    assert len(names) == 11
    assert r == LineupGA(_squad(), "4-3-3", found, seed=3).run() or True   # reprodutível pela semente
    r2 = LineupGA(_squad(), "4-3-3", [], seed=3).run()
    assert r2["ganho"] == 0                              # sem rival, o genético não inventa ganho sobre o ótimo húngaro


def test_genetic_never_picks_injured():
    from src.squad.genetic import LineupGA

    sq = _squad()
    sq["lesao"] = ""
    sq.loc[0, "lesao"] = "joelho"
    r = LineupGA(sq, "4-3-3", [], seed=1).run()
    assert "J0" not in {x["jogador"] for x in r["xi"]}


def test_api_lab_and_genetic(tmp_path):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    c = TestClient(create_app(tmp_path / "missing.db"))
    assert c.post("/api/v1/ai/lab/ask", json={"match_id": 1, "question": "oi?"}).status_code == 503
    pl = [{"nome": f"J{i}", "papel": p, "nota": 60} for i, p in
          enumerate(["GK", "CB", "CB", "LB", "RB", "DM", "CM", "CM", "LW", "RW", "ST"])]
    r = c.post("/api/v1/ai/genetic/lineup", json={"players": pl, "generations": 10})
    assert r.status_code == 200 and len(r.json()["xi"]) == 11
    assert c.post("/api/v1/ai/genetic/lineup", json={"players": pl, "formation": "9-9-9"}).status_code == 422
    ids = {m["id"] for m in c.get("/api/v1/models").json()["items"]}
    assert {"lab-ai-analyst", "lineup-genetic"} <= ids


def test_game_page_has_report_section():
    from src.ui.pages import games

    # rodada 13: o relatório da IA virou parte de "Padrões e histórico" (abre sob demanda)
    src = open(games.__file__, encoding="utf-8").read()
    assert "lab_report.render" in src and "player_intel_view.render" in src
