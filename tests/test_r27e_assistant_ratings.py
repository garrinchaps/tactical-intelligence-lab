"""Rodada 27e — raciocínio do Assistente, trava do jogo do chat, ajustes de nota e treino evolutivo."""

import numpy as np
import pandas as pd


def _box():
    rows = []
    stats = {"possession_pct": (36, 64), "xg": (.87, .60), "shots_total": (10, 14), "shots_on_target": (7, 3),
             "shots_inside_box": (6, 8), "shots_outside_box": (4, 6), "shots_blocked": (1, 2), "big_chances": (2, 1),
             "big_chances_missed": (1, 0), "passes_accurate": (288, 571), "pass_accuracy_pct": (78, 88),
             "passes_own_half": (167, 322), "passes_opp_half": (121, 249), "touches_opp_box": (17, 17),
             "fouls": (13, 11), "yellow_cards": (1, 1), "red_cards": (0, 0), "duels_won": (43, 54),
             "tackles_won": (12, 10), "interceptions": (9, 4), "aerials_won": (16, 27), "corners": (3, 3),
             "xg_set_play": (.12, .13), "xgot": (1.25, .97), "long_balls_accurate": (17, 36)}
    disp = {"long_balls_accurate": ("17 (33%)", "36 (60%)"), "aerials_won": ("16 (37%)", "27 (63%)")}
    for k, (a, b) in stats.items():
        da, db_ = disp.get(k, (str(a), str(b)))
        rows += [{"team_name": "Botafogo", "stat_key": k, "value": a, "display_value": da},
                 {"team_name": "Grêmio", "stat_key": k, "value": b, "display_value": db_}]
    tl = pd.DataFrame([{"minute": 30, "team_name": "Botafogo", "player_name": "Danilo", "related_player": "", "event_type": "Goal"},
                       {"minute": 36, "team_name": "Grêmio", "player_name": "Jovane", "related_player": "", "event_type": "Goal"},
                       {"minute": 52, "team_name": "Botafogo", "player_name": "Montoro", "related_player": "", "event_type": "Goal"},
                       {"minute": None, "team_name": "Grêmio", "player_name": "Tetê", "related_player": "Pavón",
                        "event_type": "Substitution"},
                       {"minute": 79, "team_name": "Botafogo", "player_name": "Danilo", "related_player": "", "event_type": "Goal"},
                       {"minute": 80, "team_name": "Grêmio", "player_name": "Braithwaite", "related_player": "", "event_type": "Goal"}])
    lu = pd.DataFrame([{"team_name": "Botafogo", "player_name": "x", "formation": "4-2-3-1"},
                       {"team_name": "Grêmio", "player_name": "y", "formation": "3-4-2-1"}])
    return {"team_stats": pd.DataFrame(rows), "timeline": tl, "lineups": lu, "player_stats": pd.DataFrame()}


META = {"match_id": 0, "home_team_name": "Botafogo", "away_team_name": "Grêmio", "home_score": 3, "away_score": 2,
        "data_source": "fotmob"}


def test_reasoning_detects_and_crosses_numbers():
    from src.intelligence.lab_ai import reasoning as R

    assert R.detect("A posse de bola indica controle do jogo?") == ["controle"]
    assert R.detect("quantas finalizações no gol?") == ["no_gol"]            # não é "finalizações" genérico
    assert "faltas" in R.detect("por que tantas faltas? ordene as hipóteses")
    assert R.detect("o que faltou para o Grêmio?") == []                      # "faltou" não é falta
    a = R.answer("A posse de bola indica controle do jogo?", META, None, _box())
    md = a["markdown"]
    assert "Grêmio" in md and "64%" in md and "xG" in md and "não" in md.lower()   # posse ≠ controle, com chances
    f = R.answer("por que tantas faltas?", META, None, _box())["markdown"]
    assert "Hipóteses" in f and "não medível" in f                             # hipóteses ordenadas + limite
    m = R.answer("o Botafogo mereceu vencer?", META, None, _box())["markdown"]
    assert "Botafogo" in m and "chances" in m


def test_reasoning_formation_and_missing_minutes():
    from src.intelligence.lab_ai import reasoning as R

    fm = R.answer("4-2-3-1 x 3-4-2-1: quem leva vantagem?", META, None, _box())["markdown"]
    assert "3-4-2-1" in fm and "2 contra 1" in fm
    sb = R.answer("as substituições mudaram o jogo?", META, None, _box())["markdown"]
    assert "None'" not in sb and "minuto não informado" in sb
    assert R.minute(None) == "" and R.minute(45.0) == "45'"


def test_player_question_goes_to_ranking():
    from src.intelligence.lab_ai import reasoning as R

    assert R.answer("qual jogador mais driblou?", META, None, _box()) is None
    assert R.asks_player_ranking("qual jogador mais finalizou?")
    assert not R.asks_player_ranking("quem finalizou com mais qualidade?")


def test_chat_locks_current_match():
    from src.intelligence.match_locator import LocatedMatch, should_switch

    cur = {"match_id": 1, "home_team_name": "Atlético Madrid", "away_team_name": "Real Madrid", "match_date": "2026-09-20"}
    L = lambda mid, teams: LocatedMatch(mid, teams, None, "x")
    assert not should_switch("no último minuto o Atlético Madrid pressionou?", L(2, ["Atlético Madrid"]), cur)
    assert not should_switch("o Atlético Madrid foi melhor que o Real Madrid?", L(3, ["Atlético Madrid", "Real Madrid"]), cur)
    assert should_switch("Flamengo x Palmeiras 2025: quem criou mais?", L(4, ["Flamengo", "Palmeiras"]), cur)
    assert not should_switch("o Flamengo e o Palmeiras jogam como?", L(4, ["Flamengo", "Palmeiras"]), cur)
    assert should_switch("trocar de jogo: Flamengo e Palmeiras", L(4, ["Flamengo", "Palmeiras"]), cur)
    assert should_switch("Flamengo x Palmeiras", L(4, ["Flamengo", "Palmeiras"]), None)


def test_brazil_bump_small_and_keeps_world_top():
    from src.scout.overall import brazil_bump

    u = pd.DataFrame({"clube_liga": ["Brasileirão Série A", "Brasileirão Série A", "Brasileirão Série B", "Premier League",
                                     "Brasileirão Série A"]})
    q = pd.Series([80.0, 66.0, 70.0, 88.0, 86.0])
    out = brazil_bump(u, q)
    assert out[0] == 83 and out[1] == 67            # +3 no topo do Brasil, +1 embaixo
    assert 71 <= out[2] <= 72                       # Série B +1 a +2
    assert out[3] == 88 and out[4] == 86            # mundo e quem já passa de 84 não mudam
    assert brazil_bump(u, pd.Series([83.0, 60, 60, 60, 60]))[0] == 84        # nunca passa de 84


def test_top_potential_order_uses_current_quality():
    from src.scout.overall import top_potential_ladder

    raw = pd.Series({"Diomande": 96.0, "Yamal": 95.0, "Outro": 89.0})
    q = pd.Series({"Diomande": 80.0, "Yamal": 91.0, "Outro": 84.0})
    key = raw + .6 * (q - 82).clip(lower=0)
    out = top_potential_ladder(raw, key)
    assert out["Yamal"] == 95 and out["Diomande"] < 95
    assert all(float(v).is_integer() for v in out.values)


def test_senior_call_up_floor():
    from src.scout.potential import senior_floor

    u = pd.DataFrame({"selecao_principal_jogos": [1, np.nan, 2], "idade": [20, 20, 27], "selecao_principal": ["Brazil", "", "Brazil"],
                      "qualidade": [74, 74, 80]})
    fl = senior_floor(u)
    assert fl[0] >= 83 and np.isnan(fl[1]) and np.isnan(fl[2])     # jovem convocado ganha piso; sem convocação/27 anos não


def test_contract_score_recalibrated():
    from src.scout.attributes import contract_score, verdict

    good = contract_score({"qualidade": 79, "idade": 25, "score_scout": 42}, starter=76)
    assert good >= 70 and verdict(good)[1].startswith("Seria uma boa")
    same = contract_score({"qualidade": 76, "idade": 26, "score_scout": 35}, starter=76)
    assert 58 <= same < 70                                        # igual ao titular = razoável, não "não recomendado"
    kid = contract_score({"qualidade": 70, "idade": 19, "potencial": 86, "score_scout": 40}, starter=76)
    assert kid >= 55


def test_suggest_next_changes_every_training():
    from src.intelligence.lab_ai import trainer as TR

    h = {"train_loss": [.7, .6, .55, .53, .52], "val_loss": [.7, .62, .58, .57, .565]}
    vs = [{"version": 1, "learning_rate": .1, "l2": .01, "epochs": 200, "params": {"batch": 256, "seed": 7},
           "val_logloss": .6, "history": h}]
    seen = set()
    for i in range(4):
        s = TR.suggest_next(vs)["sugerido"]
        key = tuple(sorted(s.items()))
        assert key not in seen
        seen.add(key)
        vs.append({"version": i + 2, "learning_rate": s["learning_rate"], "l2": s["l2"], "epochs": s["epochs"],
                   "params": {k: s[k] for k in ("batch", "patience", "lr_decay", "seed")}, "val_logloss": .6 - .005 * i,
                   "history": h})


def test_market_match_tries_longer_name_of_same_club():
    from src.scout.engine import match_market_to_history

    p = pd.DataFrame({"_core": ["otavio"], "clube": ["Cruzeiro"], "posicao": ["Goalkeeper"], "funcao": ["Goalkeeper"],
                      "nacionalidade": ["Brazil"], "nascimento": [None]})
    hist = pd.DataFrame({"core": ["otavio", "otavio costa"], "core_nome": ["otavio", "otavio costa"],
                         "ultimo_time": ["Paris FC", "Cruzeiro"], "posicao_fm": ["CM", "GK"],
                         "clube_fm": ["Paris FC", "Cruzeiro"], "posicao_observada": ["CM", "GK"],
                         "nascimento_fm": [None, None], "nacionalidade_fm": ["Brazil", "Brazil"], "minutos_12m": [900, 1500],
                         "times_hist": ["", ""]})
    assert match_market_to_history(p, hist).iloc[0] == "otavio costa"
