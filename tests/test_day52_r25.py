"""Rodada 25 — motor de nota por atributos, busca de clubes, potencial para todos."""

import numpy as np
import pandas as pd

from src.scout import rating_engine as RE


def _pool(n=600, seed=3):
    rng = np.random.default_rng(seed)
    cols = ["goals_p90", "xg_p90", "shots_p90", "shots_on_target_p90", "touches_opp_box_p90", "xa_p90",
            "chances_created_p90", "assists_p90", "final_third_passes_p90", "crosses_acc_p90", "line_breaking_p90",
            "dribbles_p90", "dribble_pct", "was_fouled_p90", "dispossessed_p90", "long_balls_p90", "long_ball_pct",
            "pass_rate_pct", "passes_acc_p90", "tackles_p90", "interceptions_p90", "recoveries_p90", "def_actions_p90",
            "duel_rate_pct", "clearances_p90", "dribbled_past_p90", "duel_won_p90", "aerials_won_p90", "aerial_pct",
            "errors_p90", "fouls_p90", "touches_p90", "shot_acc_pct"]
    d = pd.DataFrame(rng.uniform(0, 1, size=(n, len(cols))), columns=cols)
    d["papel"] = rng.choice(["DM", "CM", "ST", "LW", "CB", "RB", "AM"], n)
    d["minutos_12m"] = 2500
    d["minutos_ponderados"] = 3000
    d["rating_12m"] = 7.0
    d["_lvl"] = .7
    d["valor_mercado_eur"] = 1e6
    return d


def _with(d, **kw):
    row = {c: .5 for c in d.columns if c not in ("papel",)}
    row.update({"minutos_12m": 2500, "minutos_ponderados": 3000, "rating_12m": 7.0, "_lvl": .7, "valor_mercado_eur": 1e6})
    row.update(kw)
    d.loc[len(d)] = row
    return len(d) - 1


def test_destroyer_and_organizer_both_rated_high_without_creation():
    d = _pool()
    hi = .99
    dest = _with(d, papel="DM", tackles_p90=hi, interceptions_p90=hi, recoveries_p90=hi, def_actions_p90=hi,
                 duel_rate_pct=hi, duel_won_p90=hi, aerials_won_p90=.9, aerial_pct=.9, dribbled_past_p90=.01,
                 xa_p90=.05, chances_created_p90=.05, goals_p90=.01)
    org = _with(d, papel="DM", line_breaking_p90=hi, final_third_passes_p90=hi, long_balls_p90=hi, long_ball_pct=hi,
                pass_rate_pct=hi, passes_acc_p90=hi, dispossessed_p90=.01, errors_p90=.01, interceptions_p90=.8)
    avg = _with(d, papel="DM")
    out = RE.compute(d)
    b = out["ovr2_bruto"]
    assert b[dest] > b[avg] + 8 and b[org] > b[avg] + 5          # volante marcador não perde por não criar
    assert "Destruidor" in out.at[dest, "estilo"].split(" · ")[0] or "Combate" in out.at[dest, "estilo"]


def test_market_value_does_not_change_the_rating_and_small_samples_are_pulled_to_the_middle():
    d = _pool()
    a = _with(d, papel="ST", goals_p90=.99, xg_p90=.99, shots_on_target_p90=.99, valor_mercado_eur=1e5)
    b = _with(d, papel="ST", goals_p90=.99, xg_p90=.99, shots_on_target_p90=.99, valor_mercado_eur=2e8)
    c = _with(d, papel="ST", goals_p90=.99, xg_p90=.99, shots_on_target_p90=.99, minutos_ponderados=160, minutos_12m=160)
    out = RE.compute(d)
    assert abs(out.at[a, "ovr2_bruto"] - out.at[b, "ovr2_bruto"]) < 1e-9
    assert out.at[c, "atr2_SHO"] < out.at[a, "atr2_SHO"] - 15 and out.at[c, "confianca_nota"] < out.at[a, "confianca_nota"]


def test_polyvalence_bonus_and_relevant_deficiency():
    d = _pool()
    off = [c for c in d.columns if c not in ("papel", "minutos_12m", "minutos_ponderados", "rating_12m", "_lvl",
                                              "valor_mercado_eur", "dispossessed_p90", "errors_p90", "fouls_p90",
                                              "dribbled_past_p90")]
    allround = _with(d, papel="LW", **{k: .97 for k in off})
    nothing = _with(d, papel="ST", goals_p90=.01, xg_p90=.01, shots_p90=.01, shots_on_target_p90=.01, shot_acc_pct=.01,
                    touches_opp_box_p90=.01)
    out = RE.compute(d)
    assert out.at[allround, "ovr2_bonus_polivalencia"] >= 1.0
    assert out.at[nothing, "ovr2_penal_deficiencia"] > 0


def test_weak_league_difficulty_is_bounded():
    d = _pool()
    strong = _with(d, papel="ST", goals_p90=.95, xg_p90=.95, _lvl=.95)
    weak = _with(d, papel="ST", goals_p90=.95, xg_p90=.95, _lvl=.2)
    out = RE.compute(d)
    gap = out.at[strong, "atr2_SHO"] - out.at[weak, "atr2_SHO"]
    assert 0 < gap <= 14


def test_club_search_options_are_clean():
    from src.ui.pages.squad import clean_team_options as c

    assert c("cruzeiro", ["Cruzeiro", "Cruzeiro (W)", "Cruzeiro EC", 'Futbolnyi klub "Lokomotiv" Moskva',
                          "Cruzeiro Esporte Clube"], {"Cruzeiro": 900, "Cruzeiro (W)": 80, "Cruzeiro EC": 40},
             {"Cruzeiro": "Brazil", "Cruzeiro EC": "Brazil"}) == ["Cruzeiro"]
    assert c("barcelona", ["FC Barcelona", "Barcelona", "Barcelona SC", "Barcelona U19"],
             {"Barcelona": 900, "Barcelona SC": 300, "Barcelona U19": 10},
             {"Barcelona": "Spain", "Barcelona SC": "Ecuador"}) == ["Barcelona", "Barcelona SC"]


def test_potential_for_young_without_rating_is_estimated_and_marked():
    from src.scout import potential as POT

    u = pd.DataFrame({"papel": ["DM", "DM", "CB"], "idade": [18, 19, 31], "qualidade": [np.nan, 70.0, np.nan],
                      "minutos_12m": [120, 2000, 0], "selecao_base_jogos": [6, 0, 0], "selecao_base_pct": [90, np.nan, np.nan]})
    p = POT.compute(u)
    assert pd.notna(p.at[0, "potencial"]) and bool(p.at[0, "potencial_estimado_sem_nota"])
    assert "ESTIMADO" in p.at[0, "potencial_porque"]
    assert pd.isna(p.at[2, "potencial"])                                     # veterano sem dado: lacuna
    assert p.at[1, "potencial"] >= 70


def test_team_mechanisms_need_evidence_and_mirror():
    from src.squad import patterns as PT

    ref = {"posse_pct": 50, "pct_bolas_longas": 10, "cruzamentos": 15, "toques_area": 22, "xg": 1.3, "ppda_aprox": 10}
    me = {"jogos": 15, "perfil": {"posse_pct": 42, "pct_bolas_longas": 13, "cruzamentos": 19, "toques_area": 27,
                                  "ppda_aprox": 8, "pct_xg_bola_parada": 38}}
    rv = {"jogos": 14, "perfil": {"posse_pct": 61, "pct_bolas_longas": 7, "xg_contra": 1.6, "cruzamentos_contra": 19,
                                  "ppda_aprox": 11}}
    f = PT.mechanisms("Nós", "Eles", me, rv, ref, attack=True)
    kinds = {x["dimensao"]: x for x in f}
    assert "transicao" in kinds and kinds["transicao"]["nivel"] == "escancarado"
    assert "pressao_saida" in kinds and "cruzamento" in kinds and "bola_parada" in kinds
    assert all(x["passos"] and x["evidencia"] and x["confianca"] == "alta" for x in f)
    neutral = {"jogos": 15, "perfil": dict(ref, xg_contra=1.3, cruzamentos_contra=15)}
    assert PT.mechanisms("Nós", "Eles", neutral, neutral, ref, attack=True) == []      # sem evidência, sem dica


def test_same_defender_cards_are_merged():
    from src.squad.matchups import merge_same_defender

    items = [{"tipo": "duelo", "defensor": "Zé", "titulo": "Drible no 1×1", "evidencia": "a", "nivel": "claro", "score": 50},
             {"tipo": "duelo", "defensor": "Zé", "titulo": "Duelo físico", "evidencia": "b", "nivel": "claro", "score": 40},
             {"tipo": "duelo", "defensor": "Outro", "titulo": "Aéreo", "evidencia": "c", "nivel": "claro", "score": 30}]
    out = merge_same_defender(items)
    assert len(out) == 2 and out[0]["nivel"] == "escancarado" and any("Outra fraqueza" in p for p in out[0]["passos"])


def test_mononym_needs_club_or_birth_and_minutes_cap():
    from src.data_lake.ids import player_core
    from src.scout import engine as E
    from src.scout.overall import minutes_cap

    p = pd.DataFrame([{"nome": "Saúl", "clube": "Real Oviedo", "posicao": "Midfield", "funcao": "Central Midfield",
                       "nacionalidade": "Spain", "nascimento": "1985-03-01"}])
    p["_core"] = p["nome"].map(player_core)
    hist = pd.DataFrame([{"core": "saul", "core_nome": "saul", "ultimo_time": "Flamengo", "posicao_observada": "CM",
                          "nascimento_fm": None, "nacionalidade_fm": "Spain"}])
    assert E.match_market_to_history(p, hist).isna().all()                 # outro Saúl: não junta
    hist2 = hist.assign(ultimo_time="Real Oviedo")
    assert E.match_market_to_history(p, hist2).tolist() == ["saul"]        # mesmo clube: junta
    cap = minutes_cap(pd.DataFrame({"minutos_12m": [39, 0, 900, 2500]}))
    assert cap.iloc[0] == 72 and cap.iloc[1] == 72 and 72 < cap.iloc[2] < 99 and cap.iloc[3] == 99


def test_assistant_network_training_and_champion_scoring(tmp_path):
    import json

    from src.intelligence.lab_ai import trainer as TR
    from src.intelligence.lab_ai.facts import N_FEATURES
    from src.intelligence.lab_ai.selector import Selector

    rng = np.random.default_rng(0)
    key = TR._label_key("quem errou mais passes?")
    assert key
    shown = tmp_path / "shown.jsonl"
    with shown.open("w", encoding="utf-8") as fh:
        for q in range(60):
            facts = []
            for k in range(5):
                f = rng.normal(size=N_FEATURES).tolist()
                if k == 0:
                    f[0] = 3.0                                   # o fato certo tem um sinal forte
                facts.append({"key": key if k == 0 else f"k{k}", "features": f})
            fh.write(json.dumps({"interaction_id": f"q{q}", "question": "quem errou mais passes?", "facts": facts}) + "\n")
    fb = tmp_path / "fb.jsonl"
    fb.write_text("", encoding="utf-8")
    sel = Selector(root=tmp_path)
    r = TR.train_network([8], epochs=10, batch=16, sel=sel, shown_path=shown, feedback_path=fb)
    assert "reason" in r and r.get("n_perguntas") == 60
    v = [x for x in sel.meta["versions"] if x.get("mlp")]
    assert v and v[-1]["mlp"]["layers"] == [N_FEATURES, 8, 1]
    if v:
        sel.meta["champion"] = v[-1]["version"]
        p = sel.score(rng.normal(size=(4, N_FEATURES)))
        assert p.shape == (4,) and np.all((p > 0) & (p < 1))


def test_score_probabilities_and_knockout():
    from src.analytics import score_probs as SP

    m = SP.score_matrix(1.8, 0.9)
    assert abs(m.sum() - 1) < 1e-9
    o = SP.outcome(m)
    assert o["mandante"] > o["visitante"] and abs(sum(o.values()) - 1) < 1e-9
    xg = SP.expected_goals({"jogos": 20, "ataque": 2.0, "defesa": .8}, {"jogos": 20, "ataque": 1.0, "defesa": 1.6})
    assert xg["mandante"] > xg["visitante"]
    adv = SP.advance(m, 1.8, .9, agg_home=0)
    assert adv["mandante"] > o["mandante"] and abs(adv["mandante"] + adv["visitante"] - 1) < 1e-9
    adv2 = SP.advance(m, 1.8, .9, agg_home=-3)                 # perdeu a ida por 3: chance cai muito
    assert adv2["mandante"] < adv["mandante"]
