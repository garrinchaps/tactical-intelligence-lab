"""Rodada 12: roteador do Assistente, matéria de IA aplicada (Q2–Q12), tabela com colunas booleanas."""

import numpy as np
import pandas as pd


def _box():
    rows = []
    for team, players in (("T1", [("A", 3, 10, 90, 7.9), ("B", 0, 25, 90, 6.1)]),
                          ("T2", [("C", 1, 5, 90, 6.8), ("D", 4, 2, 30, 7.2)])):
        for name, drib, passes, mins, rat in players:
            rows.append({"team_name": team, "player_name": name, "minutes": mins, "rating": rat,
                         "stats_json": {"dribbles_succeeded": drib, "accurate_passes": passes,
                                        "accurate_passes_total": passes + 5, "minutes": mins}})
    return {"players": pd.DataFrame(rows)}


def test_split_questions_only_when_each_part_has_subject():
    from src.intelligence.lab_ai.router import split_questions

    assert len(split_questions("quem driblou mais e quem sofreu mais dribles?")) == 2
    assert split_questions("o messi jogou?") == ["o messi jogou?"]


def test_router_returns_none_for_classic_questions():
    from src.intelligence.lab_ai import router as R

    meta = {"home_team_name": "T1", "away_team_name": "T2"}
    assert R.route("o messi jogou?", meta, None, {}, "T1", None) is None


def test_momentum_phases_sign_follows_team():
    from src.intelligence.lab_ai.router import momentum_phases

    extra = {"times": ["T1", "T2"], "momentum": [[m, 40.0 if m < 45 else -40.0] for m in range(90)]}
    home = momentum_phases(extra, "T1")
    away = momentum_phases(extra, "T2")
    assert home[0]["leitura"] == "por cima" and away[0]["leitura"] == "sob pressão"
    assert home[-1]["leitura"] == "sob pressão"


def test_mamdani_centroid_and_sugeno():
    from src.intelligence import course as C

    m = C.mamdani_centroid(70, 85)
    assert 60 < m["centroide"] < 100
    u, agg = m["universo"], m["agregada"]
    assert abs(m["centroide"] - float((u * agg).sum() / agg.sum())) < 0.01
    s = C.sugeno_same_rules(70, 85)
    assert 60 < s["saida"] <= 95
    low = C.mamdani_centroid(10, 10)
    assert low["centroide"] < m["centroide"]


def test_fuzzy_is_not_probability():
    from src.intelligence import course as C

    q = C.fuzzy_vs_probability(82)
    assert q["fuzzy"]["alto"] > 0 and q["probabilidade_proximo_passe"] == 0.82


def test_xor_needs_hidden_layer():
    from src.intelligence import course as C

    rows = C.xor_forward()
    assert [round(r["saída"]) for r in rows] == [0, 1, 1, 0]
    assert C.xor_linear_best()["acertos"] == 3


def test_gradient_step_reduces_loss_and_matches_formula():
    from src.intelligence import course as C

    g = C.gradient_step([1.0, 2.0], [0.1, -0.2], 0.0, 1.0, 0.5)
    a = 1 / (1 + np.exp(0.3))
    assert abs(g["a"] - a) < 1e-4
    assert np.allclose(g["dL/dw"], [(a - 1) * 1, (a - 1) * 2], atol=1e-4)
    assert g["perda nova"] < g["perda"]


def test_curve_diagnosis_and_suggestion():
    from src.intelligence import course as C

    over = {"train_loss": list(np.linspace(0.5, 0.2, 30)),
            "val_loss": list(np.r_[np.linspace(0.5, 0.35, 10), np.linspace(0.35, 0.45, 20)])}
    assert C.diagnose_curve(over)["diagnostico"] == "sobreajuste"
    s = C.suggest_next_experiment({"hidden": [32, 16], "learning_rate": 0.01, "l2": 1e-4, "epochs": 30, "history": over})
    assert s["sugerido"]["l2"] > 1e-4 and s["sugerido"]["hidden"] == [16, 8]
    good = {"train_loss": list(np.linspace(0.5, 0.36, 20)), "val_loss": list(np.linspace(0.5, 0.37, 20))}
    assert C.diagnose_curve(good)["diagnostico"] == "equilibrado"
    flat = {"train_loss": [0.5] * 20, "val_loss": [0.5] * 20}
    assert C.diagnose_curve(flat)["diagnostico"] == "subajuste"


def test_confusion_and_accuracy_paradox():
    from src.intelligence import course as C

    y = [1] * 10 + [0] * 90
    lazy = C.confusion(y, [0.0] * 100)
    assert lazy["acuracia"] == 0.9 and lazy["revocacao"] == 0.0 and lazy["VP"] == 0
    p = [0.9] * 8 + [0.1] * 2 + [0.8] * 4 + [0.1] * 86
    c = C.confusion(y, p, 0.5)
    assert (c["VP"], c["FN"], c["FP"], c["VN"]) == (8, 2, 4, 86)
    assert abs(c["precisao"] - 8 / 12) < 1e-3 and abs(c["revocacao"] - 0.8) < 1e-3


def test_selection_probabilities_and_mutation():
    from src.intelligence import course as C

    rows = C.roulette_vs_tournament([10, 8, 5, 2, 1], 3)
    assert abs(sum(r["roleta %"] for r in rows) - 100) < 0.5
    assert abs(sum(r["torneio k=3 %"] for r in rows) - 100) < 0.5
    assert rows[-1]["torneio k=3 %"] == 0
    assert C.expected_mutations(18, 1 / 18)["esperado de bits mutados"] == 1.0
    assert C.penalized_fitness(790, 1, 1000)["f'(x) = f(x) − R·violações"] == -210


def test_example_ga_converges_monotonically_and_skips_injured():
    from src.intelligence import course as C

    r = C.run_example_ga(generations=40, pop=30)
    h = r["historico"]
    assert all(b >= a - 1e-9 for a, b in zip(h, h[1:]))      # elitismo
    assert "Atleta 14" not in {x["jogador"] for x in r["xi"]}  # lesionado (R = 1000)
    assert r["R"] == 1000.0


def test_heat_ignores_boolean_columns():
    from src.ui.components import zebra

    df = pd.DataFrame({"promovida": [True, False], "AUC": [0.6, 0.62]})
    zebra(df).to_html()            # não pode levantar TypeError (numpy boolean subtract)
