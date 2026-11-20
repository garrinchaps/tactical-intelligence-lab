"""Rodada 23: recuperação dos dias com o PC desligado, atributos estilo FM, relatórios de olheiro e interface."""
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd


def test_missing_days_covers_gap_and_caps(tmp_path):
    from src.data_hub import autosync as A
    from src.data_hub import sync_policy as P
    from src.data_hub.db import DataHubDB

    db = DataHubDB(tmp_path / "m.db")
    today = date(2026, 11, 20)
    assert A.missing_days(db, today) == [date(2026, 11, 19), today]           # sem histórico: ontem e hoje
    P.mark_synced(db, "fotmob", "_resultados_dia", datetime(2026, 11, 14, 12, tzinfo=timezone.utc))
    d = A.missing_days(db, today)
    assert d[0] == date(2026, 11, 13) and d[-1] == today and len(d) == 8     # PC desligado de 14 a 20
    P.mark_synced(db, "fotmob", "_resultados_dia", datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert len(A.missing_days(db, today)) == A.CATCHUP_MAX_DAYS + 1          # no máximo 30 dias para trás


def test_refresh_recent_results_marks_and_uses_missing_days(tmp_path, monkeypatch):
    from src.data_hub import autosync as A
    from src.data_hub import sync_policy as P
    from src.data_hub.db import DataHubDB
    from src.data_hub.sources.fotmob import FotmobProvider

    db = DataHubDB(tmp_path / "r.db")
    seen = {}
    monkeypatch.setattr(FotmobProvider, "sync_dates", lambda self, days=None, progress=None: seen.setdefault("d", days) and {"partidas": 3})
    monkeypatch.setattr(A, "fotmob_enabled", lambda: True)
    from src.data_hub.sources.espn import EspnProvider

    monkeypatch.setattr(EspnProvider, "live_tick", lambda self, leagues=None: {"encerrados": 1})
    r = A.refresh_recent_results(db)
    assert r["dias"] == len(seen["d"]) >= 2 and P.last_synced(db, "fotmob", "_resultados_dia") is not None


def _uni(n=300, seed=1):
    rng = np.random.default_rng(seed)
    q = rng.normal(0, 1, n)
    return pd.DataFrame({"nome": [f"P{i}" for i in range(n)], "papel": rng.choice(["ST", "CB", "GK", "CM"], n),
                         "minutos_12m": rng.integers(0, 3500, n), "goals_p90": np.clip(.3 + .2 * q, 0, None),
                         "xg_p90": np.clip(.3 + .15 * q, 0, None), "shot_acc_pct": 40 + 10 * q, "aerial_pct": 50 + 10 * q,
                         "aerials_won_p90": 2 + q, "pass_accuracy_pct": 80 + 5 * q, "dispossessed_p90": 1 - .3 * q,
                         "saves_p90": 3 + q, "qualidade": 65 + 8 * q, "clube_liga": rng.choice(["Liga A", "Liga B"], n)})


def test_attributes_1_to_20_within_position():
    from src.scout import attributes as AT

    u = _uni()
    a = AT.compute(u)
    fin = a["atr_Finalização"].dropna()
    assert fin.between(1, 100).all() and fin.max() >= 75 and fin.min() <= 28
    few = u["minutos_12m"] < 300
    assert a.loc[few, "atr_Finalização"].isna().all()                        # sem minutos = não medido
    gk = u["papel"] == "GK"
    assert a.loc[gk, "atr_Finalização"].isna().all() and a.loc[~gk, "atr_Defesas (goleiro)"].isna().all()
    assert a["atr_Explosão (sprints)"].isna().all()                          # liga sem sprints: nada inventado
    best = a["atr_Finalização"].idxmax()
    assert u.loc[best, "goals_p90"] >= u.loc[u["papel"] == u.loc[best, "papel"], "goals_p90"].median()


def test_stars_levels_and_verdict():
    from src.scout import attributes as AT

    assert AT.stars(70, 70) == 3.0 and AT.stars(80, 70) == 5.0 and AT.stars(55, 70) == .5
    assert "bom para a Série B" == AT.level_label(72, 70, "Série B")
    assert "abaixo" in AT.level_label(60, 70, "Série B") and AT.level_label(90, 70, "x") == "nível de elite mundial"
    assert AT.verdict(90) == (90, "Seria uma excelente contratação") and AT.verdict(None)[0] is None
    refs = AT.league_reference(_uni(600))
    assert set(refs) == {"Liga A", "Liga B"}
    pros, cons = AT.pros_cons({"atr_Finalização": 88, "atr_Passe": 18, "pe": "both", "altura_cm": 192, "_fam": "CB",
                               "realismo": {"penalidade_estrangeiros": 8}})
    assert any("Finalização" in t for _, t in pros) and any("dois pés" in t for _, t in pros)
    assert any("Passe" in t for _, t in cons) and any("estrangeiros" in t for _, t in cons)


def test_team_canon_ambiguous_nickname_does_not_merge():
    from src.ui.pages.search_all import _team_canon

    c = _team_canon()
    assert c("São Paulo") != c("Fluminense")                    # "tricolor" é apelido dos dois: não traduz
    assert c("Brasil") == c("Brazil")


def _season(db):
    rows, mid = [], 500000400
    teams = ["Bahia", "Sport", "Ceará", "Vitória"]
    import itertools

    for i, (h, a) in enumerate(itertools.permutations(teams, 2)):
        mid += 1
        rows.append({"match_id": mid, "competition_name": "Série Teste", "season_name": "2026",
                     "match_date": f"2026-0{1 + i // 4}-{10 + i % 4}", "home_team_name": h, "away_team_name": a,
                     "home_score": 2 if h == "Bahia" else 1, "away_score": 0 if h == "Bahia" else 1,
                     "data_source": "espn", "data_level": "RESULT"})
    db.upsert_matches(rows)


def test_team_ranks_position_history_and_calendar(tmp_path):
    from src.analytics import team_report as TR
    from src.data_hub.db import DataHubDB

    db = DataHubDB(tmp_path / "t.db")
    _season(db)
    rk = TR.team_ranks(db, ["Bahia"])
    assert rk["posicao"] == 1 and rk["times"] == 4 and rk["gols_pro_rank"] == "Melhor"
    assert rk["historico_posicao"] and rk["historico_posicao"][-1]["posicao"] == 1
    cal = TR.results_and_fixtures(db, ["Bahia"])
    assert cal["resultados"] and cal["resultados"][0]["resultado"] in "VED"


def test_squad_facts_and_coach_profile():
    from src.analytics import team_report as TR

    ro = pd.DataFrame({"name": ["A", "B", "C"], "birth": ["2006-01-01", "1990-01-01", "2000-06-01"],
                       "height": [170, 195, 182], "market_value": [1e6, 5e6, 2e6], "country": ["Brazil", "Brazil", "Uruguay"],
                       "lesao": ["", "Joelho", ""]})
    f = {r["fato"]: r["a"] for r in TR.squad_facts(ro, None)}
    assert f["Jogador mais jovem"].endswith("A") and f["Jogador mais alto"].startswith("195")
    assert f["Lesionados agora"] == "1" and f["Nacionalidades representadas"] == "2"
    prof = TR.coach_profile({"treinador_atual": {"treinador": "X", "de": "2026-01-01", "jogos": 10, "desenho_mais_usado": "4-3-3"},
                             "estatisticas": {"perfil": {"posse_pct": 58.0, "ppda_aprox": 8.0},
                                              "referencia": {"posse_pct": 50.0, "ppda_aprox": 12.0}}})
    assert prof["mentalidade"].startswith("Proativa") and prof["pressao"].startswith("Com mais frequência")


def test_fm_components_render_without_errors():
    """Os componentes visuais novos rodam sem a sessão do Streamlit (só avisos) — pega erros que o try/except do
    dossiê esconderia (ex.: coluna com '_' some no itertuples)."""
    from src.scout import attributes as AT
    from src.ui import fm, player_fm

    row = {"nome": "Fulano", "papel": "ST", "papel_alvo": "ST", "_fam": "ST", "qualidade": 74, "potencial": 82,
           "atr_Finalização": 85, "atr_Passe": 22, "idade": 20, "minutos_12m": 2100, "rating_12m": 7.1,
           "forma_5": [7.5, 7.6, 7.4], "score_scout": 81}
    roster = pd.DataFrame({"nome": ["A", "B"], "papel": ["ST", "ST"], "qualidade": [70, 66], "potencial": [72, 75]})
    fm.panel("x"); fm.icon_list([("✅", "ok")], "pro", "Prós"); fm.rank_list([("⚽", "Gols", "10 — Melhor")])
    fm.people_tiles([("Melhor marcador", "Fulano", "10 gols")]); fm.verdict_card(*AT.verdict(81))
    fm.facts_table([{"fato": "Idade", "a": "25", "b": "26", "melhor": "a", "dif": "1"}], "Nós", "Eles")
    fm.attr_table(row); player_fm.squad_compare(row, roster, key="t")
    assert fm.ordinal_rank(3, [1, 2, 3]) == "Melhor" and fm.ordinal_rank(1, [1, 2, 3]) == "Pior"
