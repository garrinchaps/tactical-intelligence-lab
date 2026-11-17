import pandas as pd

from src.scout.engine import (
    _foreign_rule, build_market_universe, build_simulation, transfer_realism,
    add_quality_scores, recommend,
)


def test_market_universe_merges_season_history_and_preserves_missing_values():
    market = pd.DataFrame([{
        "nome": "Player Alpha", "clube": "Club A", "posicao": "Centre-Forward",
        "funcao": "Centre-Forward", "nascimento": "2002-01-01", "valor_mercado_eur": 2_000_000,
        "fim_contrato": "2027-06-30", "transfermarkt_id": "10", "clube_id": "1",
    }])
    history = pd.DataFrame([{
        "core": "player alpha", "minutos": 1800, "jogos": 25, "rating_media": 7.1,
        "minutos_12m": 1200, "jogos_12m": 15, "rating_12m": 7.2, "goals_p90": .55,
        "historico_temporadas": [{"temporada": "2025", "jogos": 10}],
        "ultimos_jogos": [],
    }])
    out = build_market_universe(market, history)
    assert out.loc[0, "rating_media"] == 7.1
    assert out.loc[0, "valor_mercado_eur"] == 2_000_000
    assert pd.isna(out.loc[0, "xg"]) if "xg" in out else True


def test_realism_score_is_bounded_and_contract_opportunity_is_explained():
    player = {"valor_mercado_eur": 5_000_000, "fim_contrato": "2027-02-01",
              "minutos_12m": 350, "qualidade": 82, "nacionalidade": "Argentina"}
    buyer = {"orcamento_proxy_eur": 4_000_000, "valor_elenco_eur": 30_000_000}
    score = transfer_realism(player, buyer, "Brazil", "Brasileirão Série A", 2027, foreign_count=8)
    assert 0 <= score["score"] <= 100
    assert score["oportunidade_emprestimo"] is True
    assert score["regra_estrangeiros"]["limite"] == 8
    assert any("Contrato" in x for x in score["motivos"])


def test_brazil_foreign_limit_is_season_sensitive():
    assert _foreign_rule("Brasileirão Série A", 2026)["limite"] == 9
    assert _foreign_rule("Brasileirão Série A", 2027)["limite"] == 8
    assert _foreign_rule("Premier League", 2027) is None


def test_simulation_returns_projected_delta_and_not_a_fact():
    roster = pd.DataFrame([
        {"nome": "A", "papel": "ST", "qualidade": 60, "xg_p90": .2, "chances_created_p90": .1},
        {"nome": "B", "papel": "LW", "qualidade": 62, "xg_p90": .3, "chances_created_p90": .2},
        {"nome": "C", "papel": "RW", "qualidade": 63, "xg_p90": .25, "chances_created_p90": .2},
        {"nome": "D", "papel": "CM", "qualidade": 64, "xg_p90": .1, "chances_created_p90": .4},
        {"nome": "E", "papel": "CM", "qualidade": 65, "xg_p90": .1, "chances_created_p90": .3},
        {"nome": "F", "papel": "DM", "qualidade": 62, "xg_p90": .0, "chances_created_p90": .1},
        {"nome": "G", "papel": "LB", "qualidade": 61, "xg_p90": .0, "chances_created_p90": .1},
        {"nome": "H", "papel": "RB", "qualidade": 63, "xg_p90": .0, "chances_created_p90": .1},
        {"nome": "I", "papel": "CB", "qualidade": 64, "xg_p90": .0, "chances_created_p90": .0},
        {"nome": "J", "papel": "CB", "qualidade": 65, "xg_p90": .0, "chances_created_p90": .0},
        {"nome": "K", "papel": "GK", "qualidade": 66, "xg_p90": .0, "chances_created_p90": .0},
    ])
    candidate = {"nome": "New", "papel": "ST", "qualidade": 85, "xg_p90": .8,
                 "chances_created_p90": .2}
    result = build_simulation(roster, candidate=candidate, sold_name="A")
    assert result["xi_depois"]
    assert "projeção" in result["limite"].lower()


def test_quality_does_not_turn_transfer_value_into_performance_rating():
    players = pd.DataFrame([{
        "nome": "Unknown", "papel": "ST", "valor_mercado_eur": 80_000_000,
        "minutos": None, "minutos_12m": None, "rating_media": None,
    }])
    scored = add_quality_scores(players)
    assert pd.isna(scored.loc[0, "qualidade"])



def test_recent_match_history_can_supply_players_missing_from_transfermarket():
    history = pd.DataFrame([{
        "core": "player beta",
        "nome_observado": "Player Beta",
        "posicao_observada": "Centre-Forward",
        "ultimo_time": "Club B",
        "ultimo_jogo": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "minutos": 1600,
        "jogos": 20,
        "minutos_12m": 1500,
        "jogos_12m": 18,
        "rating_media": 7.0,
        "rating_12m": 7.1,
        "historico_temporadas": [],
        "ultimos_jogos": [],
    }])
    out = build_market_universe(pd.DataFrame(), history)
    assert len(out) == 1
    assert out.loc[0, "nome"] == "Player Beta"
    assert out.loc[0, "papel"] == "ST"
    assert out.loc[0, "clube"] == "Club B"
    assert pd.isna(out.loc[0, "valor_mercado_eur"])
    assert bool(out.loc[0, "sem_cadastro_mercado"]) is True


def test_external_rating_is_a_secondary_signal_not_a_market_value_proxy():
    from src.scout.engine import merge_external_ratings

    players = pd.DataFrame([
        {"nome": "Player Gamma", "_core": "player gamma", "qualidade": 80.0, "confianca_pct": 70},
        {"nome": "Player Delta", "_core": "player delta", "qualidade": None, "confianca_pct": 0},
    ])
    ratings = pd.DataFrame([
        {"nome": "Player Gamma", "nota": 60.0, "fonte": "sm_ratings"},
        {"nome": "Player Delta", "nota": 75.0, "fonte": "sm_ratings"},
    ])
    out = merge_external_ratings(players, ratings)
    assert out.loc[0, "qualidade"] == 76.4
    assert out.loc[0, "nota_externa"] == 60.0
    assert out.loc[1, "qualidade"] == 75.0
    assert out.loc[1, "confianca_pct"] == 25


def test_unknown_minutes_do_not_create_a_false_loan_opportunity():
    player = {"valor_mercado_eur": 2_000_000, "fim_contrato": None,
              "minutos_12m": None, "minutos": None, "qualidade": 82}
    buyer = {"orcamento_proxy_eur": 5_000_000, "valor_elenco_eur": 40_000_000}
    result = transfer_realism(player, buyer, "Brazil", "Brasileirão Série A", 2027)
    assert result["oportunidade_emprestimo"] is False
    assert any("Minutagem recente indisponível" in x for x in result["motivos"])


def test_italian_serie_a_does_not_receive_brazilian_foreign_player_rule():
    assert _foreign_rule("Serie A", 2027) is None



def test_como_1907_alias_resolves_to_same_club_identity():
    from src.data_lake.ids import team_core

    assert team_core("Como 1907") == team_core("Como")


def test_foreign_nationality_check_handles_brazilian_and_dual_nationality():
    from src.scout.engine import is_foreign_player

    assert is_foreign_player("Brazil", "Brasil") is False
    assert is_foreign_player("Argentina, Italy", "Brazil") is True
    assert is_foreign_player(None, "Brazil") is None



def test_player_season_totals_reuses_preparsed_stats_without_changing_results():
    import json

    from src.scout.engine import _json_obj, _player_season_totals

    rows = pd.DataFrame([
        {
            "match_id": 1, "match_date": "2026-11-15", "team_name": "Club A",
            "competition_name": "League", "minutes": 90, "rating": 8.0,
            "stats_json": json.dumps({
                "totalGoals": 1, "xg": 0.6, "accurate_passes_pct": 80,
                "duels_won_pct": 55,
            }),
        },
        {
            "match_id": 2, "match_date": "2026-11-16", "team_name": "Club A",
            "competition_name": "League", "minutes": 60, "rating": 7.0,
            "stats_json": json.dumps({
                "goalAssists": 1, "xg": 0.4, "pass_accuracy": 88,
                "duelsWonPercentage": 65,
            }),
        },
    ])

    expected = _player_season_totals(rows)
    prepared = rows.copy()
    prepared["_parsed_stats"] = prepared["stats_json"].map(_json_obj)
    actual = _player_season_totals(prepared)

    assert actual == expected
    assert actual["minutos"] == 150
    assert actual["jogos"] == 2
    assert actual["goals"] == 1.0
    assert actual["assists"] == 1.0
    assert actual["xg"] == 1.0
    assert actual["pass_accuracy_pct"] == 80.0
    assert actual["duels_won_pct"] == 55.0



def test_player_season_totals_form_uses_latest_matches_not_input_order():
    from src.scout.engine import _player_season_totals

    rows = pd.DataFrame([
        {"match_id": 4, "match_date": "2026-11-14", "minutes": 90, "rating": 4.0, "stats_json": "{}"},
        {"match_id": 1, "match_date": "2026-11-11", "minutes": 90, "rating": 1.0, "stats_json": "{}"},
        {"match_id": 6, "match_date": "2026-11-16", "minutes": 90, "rating": 6.0, "stats_json": "{}"},
        {"match_id": 2, "match_date": "2026-11-12", "minutes": 90, "rating": 2.0, "stats_json": "{}"},
        {"match_id": 7, "match_date": "2026-11-17", "minutes": 90, "rating": 7.0, "stats_json": "{}"},
        {"match_id": 3, "match_date": "2026-11-13", "minutes": 90, "rating": 3.0, "stats_json": "{}"},
        {"match_id": 5, "match_date": "2026-11-15", "minutes": 90, "rating": 5.0, "stats_json": "{}"},
    ])

    result = _player_season_totals(rows)

    assert result["forma_5"] == [3.0, 4.0, 5.0, 6.0, 7.0]


def test_load_player_history_does_not_sort_the_entire_database_result(monkeypatch):
    from contextlib import contextmanager
    from src.scout import engine

    class FakeDB:
        @contextmanager
        def connect(self):
            yield object()

    captured = {}

    def fake_read_sql_query(query, conn, params=None):
        captured["query"] = query
        return pd.DataFrame()

    monkeypatch.setattr(engine.pd, "read_sql_query", fake_read_sql_query)

    result = engine.load_player_history(FakeDB(), days=1825)

    assert result.empty
    assert "ORDER BY m.match_date DESC" not in captured["query"].upper()
    assert "match_date >= ?" in captured["query"]


def test_market_universe_attaches_recent_observed_club_and_keeps_market_club():
    from src.data_lake.ids import player_core

    market = pd.DataFrame([{
        "nome": "Player Current", "clube": "Old Club", "posicao": "Centre-Forward",
        "funcao": "Centre-Forward", "transfermarkt_id": "100", "clube_id": "10",
    }])
    history = pd.DataFrame([{
        "core": player_core("Player Current"), "minutos": 1800, "jogos": 20,
        "minutos_12m": 1500, "jogos_12m": 18, "ultimo_jogo": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "ultimo_time": "New Club", "nome_observado": "Player Current",
        "historico_temporadas": [{"temporada": "2026", "jogos": 20}],
        "ultimos_jogos": [{"match_date": pd.Timestamp.today().strftime("%Y-%m-%d")}],
    }])

    out = build_market_universe(market, history)

    assert out.loc[0, "clube"] == "New Club"
    assert out.loc[0, "clube_tm"] == "Old Club"
    assert bool(out.loc[0, "clube_observado"]) is True
    assert isinstance(out.loc[0, "historico_temporadas"], str)
    assert '"temporada": "2026"' in out.loc[0, "historico_temporadas"]


def test_market_universe_does_not_attach_ambiguous_history_to_homonyms():
    from src.data_lake.ids import player_core

    market = pd.DataFrame([
        {"nome": "Player Same", "clube": "Club A", "posicao": "Centre-Forward", "funcao": "Centre-Forward",
         "transfermarkt_id": "101"},
        {"nome": "Player Same", "clube": "Club B", "posicao": "Centre-Forward", "funcao": "Centre-Forward",
         "transfermarkt_id": "102"},
    ])
    history = pd.DataFrame([{
        "core": player_core("Player Same"), "minutos": 1800, "jogos": 20,
        "minutos_12m": 1500, "jogos_12m": 18, "ultimo_jogo": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "ultimo_time": "Club C", "historico_temporadas": [{"temporada": "2026"}], "ultimos_jogos": [],
    }])

    out = build_market_universe(market, history)

    assert len(out) == 2
    assert out["minutos"].isna().all()
    assert out["historico_temporadas"].tolist() == ["[]", "[]"]
    assert out["historico_ambiguo"].fillna(False).all()
