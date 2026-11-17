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
