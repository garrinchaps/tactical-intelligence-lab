import numpy as np
import pandas as pd

from src.scout import engine as scout_engine


def test_merge_verificado_junta_transferencia_e_preserva_clube_observado():
    players = pd.DataFrame([
        {
            "nome": "Kaiki", "_core": "kaiki", "clube": "Cruzeiro", "papel": "LB",
            "nascimento": "2003-03-23", "nacionalidade": "Brazil", "clube_observado": False,
            "ultimo_jogo": "2026-02-01", "minutos_12m": 3176, "qualidade": 77, "potencial": 77,
        },
        {
            "nome": "Kaiki", "_core": "kaiki", "clube": "Como", "papel": "LB",
            "nascimento": "2003-03-23", "nacionalidade": "Brazil", "clube_observado": True,
            "ultimo_jogo": "2026-10-01", "minutos_12m": 3828, "qualidade": 75, "potencial": 86,
        },
    ])

    merged = scout_engine.merge_verified_player_duplicates(players)

    assert len(merged) == 1
    assert merged.iloc[0]["clube"] == "Como"
    assert merged.iloc[0]["qualidade"] == 77
    assert merged.iloc[0]["potencial"] == 86


def test_merge_verificado_nao_confunde_homonimos_com_nascimentos_diferentes():
    players = pd.DataFrame([
        {"nome": "Arthur", "clube": "Palmeiras", "papel": "CM", "nascimento": "2000-01-01",
         "nacionalidade": "Brazil"},
        {"nome": "Arthur", "clube": "Outro Clube", "papel": "CM", "nascimento": "2001-01-01",
         "nacionalidade": "Brazil"},
    ])

    merged = scout_engine.merge_verified_player_duplicates(players)

    assert len(merged) == 2


def test_snapshot_busca_alias_do_nome_curto(monkeypatch):
    from src.scout import snapshot as S

    universe = pd.DataFrame([{
        "_core": "otavio costa", "apelidos_core": "otavio", "pid": "fm123",
        "nome": "Otávio Costa", "clube": "Cruzeiro", "qualidade": 64,
        "potencial": 86, "minutos_12m": 3465,
    }])
    monkeypatch.setattr(S, "cached_universe", lambda: universe)
    S._MEMO.clear()
    try:
        row = S.find_player("otavio", ["Otávio"], "Cruzeiro")
        assert row is not None
        assert row["nome"] == "Otávio Costa"
        assert row["qualidade"] == 64
    finally:
        S._MEMO.clear()


def test_campinho_exibe_o_overall_exato_do_scout(monkeypatch):
    from src.scout import snapshot as S
    from src.ui.matchday_view import unified_quality

    monkeypatch.setattr(S, "find_player", lambda *args, **kwargs: {"qualidade": 77})
    result = unified_quality([{"jogador": "Atleta", "nota": 7.2, "encaixe": 0.25}], "Clube")

    assert result[0]["qualidade"] == 77
    assert result[0]["qualidade_fonte"] == "Overall do Scout"


def test_elenco_usa_overall_e_potencial_do_scout(monkeypatch):
    from src.scout import snapshot as S
    from src.ui.pages.squad import apply_scout_overall

    monkeypatch.setattr(S, "find_player", lambda *args, **kwargs: {"qualidade": 64, "potencial": 86})
    squad = pd.DataFrame([{
        "nome": "Otávio", "transfermarkt_id": 123, "nota": 65, "nota_base": "estimativa local",
    }])

    result = apply_scout_overall(squad, "Cruzeiro")

    assert result.loc[0, "nota"] == 64
    assert result.loc[0, "qualidade"] == 64
    assert result.loc[0, "potencial"] == 86
    assert result.loc[0, "nota_base"] == "Overall do Scout"


def test_cartao_scout_nao_exibe_nan_como_posicao():
    from src.ui.pages.scout import _missing_value, _role

    assert _missing_value(np.nan)
    assert _missing_value("nan")
    assert _role(np.nan) == "Posição não identificada"


def test_placar_so_identifica_jogo_sem_despejar_estatisticas():
    from src.intelligence.player_line import is_match_intro, match_intro

    teams = ["Santos", "Grêmio"]
    question = "Santos 0 x 2 Grêmio 2026"
    assert is_match_intro(question, teams)

    answer = match_intro({}, {
        "home_team_name": "Santos", "away_team_name": "Grêmio",
        "home_score": 0, "away_score": 2,
        "competition_name": "Brasileirão Série A", "match_date": "2026-11-24",
    }, [])
    assert "Jogo identificado" in answer
    assert "Santos 0–2 Grêmio" in answer
    assert "Estatística" not in answer
    assert "Gols:" not in answer
    assert "|" not in answer


def test_chat_remove_tag_sub_mantendo_texto_legivel():
    from src.ui.pages.assistant import _chat_text

    assert _chat_text("Weverton <sub>em 90 min</sub>") == "Weverton em 90 min"

def test_merge_aliases_preserva_aliases_de_outras_fichas():
    players = pd.DataFrame([
        {"nome": "Bruno", "clube": "Clube A", "papel": "CM", "idade": 27,
         "minutos_12m": 0, "ultimos_jogos": None, "apelidos_core": None},
        {"nome": "Bruno Fernandes", "clube": "Clube A", "papel": "CM", "idade": 27,
         "minutos_12m": 1800, "ultimos_jogos": None, "apelidos_core": None},
        {"nome": "Lucas Silva", "clube": "Clube B", "papel": "CM", "idade": 29,
         "minutos_12m": 800, "ultimos_jogos": None, "apelidos_core": "lucas|lucas silva"},
    ])

    merged = scout_engine.merge_club_aliases(players)

    assert len(merged) == 2
    preserved = merged.loc[merged["nome"] == "Lucas Silva", "apelidos_core"].iloc[0]
    assert "lucas" in preserved
    assert "lucas silva" in preserved

