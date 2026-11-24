import numpy as np
import pandas as pd

from src.scout import engine as scout_engine


def test_merge_verificado_junta_transferencia_e_preserva_clube_observado():
    players = pd.DataFrame([
        {
            "nome": "Kaiki", "_core": "kaiki", "clube": "Cruzeiro", "papel": "LB",
            "fotmob_id": 12345, "nascimento": "2003-03-23", "nacionalidade": "Brazil", "clube_observado": False,
            "ultimo_jogo": "2026-02-01", "minutos_12m": 3176, "qualidade": np.nan, "potencial": np.nan,
        },
        {
            "nome": "Kaiki", "_core": "kaiki", "clube": "Como", "papel": "LB",
            "fotmob_id": 12345, "nascimento": None, "nacionalidade": None, "clube_observado": True,
            "ultimo_jogo": "2026-10-01", "minutos_12m": 3828, "qualidade": 77, "potencial": 77,
        },
    ])

    merged = scout_engine.merge_verified_player_duplicates(players)

    assert len(merged) == 1
    assert merged.iloc[0]["clube"] == "Como"
    assert merged.iloc[0]["qualidade"] == 77
    assert merged.iloc[0]["potencial"] == 77


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


def test_elenco_prefere_alias_e_clube_a_um_pid_transfermarkt_legado(monkeypatch):
    from src.scout import snapshot as S
    from src.ui.pages.squad import apply_scout_overall

    calls = []

    def find_player(core, names=None, club="", pid="", age=None):
        calls.append({"core": core, "names": names, "club": club, "pid": pid, "age": age})
        if pid:
            # Simula o comportamento antigo: o ID da ficha TM encontra o registro legado.
            return {"nome": "Otávio", "clube": "Cruzeiro", "qualidade": 65, "potencial": 71}
        # Alias consolidado da busca manual: ficha completa FotMob, com nota correta.
        return {"nome": "Otávio Costa", "apelidos_core": "otavio", "clube": "Cruzeiro",
                "qualidade": 64, "potencial": 86}

    monkeypatch.setattr(S, "find_player", find_player)
    squad = pd.DataFrame([{
        "nome": "Otávio", "transfermarkt_id": 123, "nota": 65, "nota_base": "estimativa local",
    }])

    result = apply_scout_overall(squad, "Cruzeiro")

    assert result.loc[0, "nota"] == 64
    assert result.loc[0, "qualidade"] == 64
    assert result.loc[0, "potencial"] == 86
    assert result.loc[0, "nota_base"] == "Overall do Scout"
    assert len(calls) == 1
    assert calls[0]["pid"] == ""
    assert calls[0]["names"] == ["Otávio"]
    assert calls[0]["club"] == "Cruzeiro"



def test_merge_roster_prioriza_alias_canonico_quando_chave_curta_colide(monkeypatch):
    from src.ui.pages import scout as scout_page

    # Fotografia com a ficha curta antiga e a ficha completa da mesma goleira.
    universe = pd.DataFrame([
        {"nome": "Otávio", "_core": "otavio", "clube": "Cruzeiro", "papel": "GK", "idade": 20,
         "qualidade": 65, "potencial": 71, "minutos_12m": 3150, "rating_12m": 7.15},
        {"nome": "Otávio Costa", "_core": "otavio costa", "clube": "Cruzeiro", "papel": "GK", "idade": 20,
         "qualidade": 64, "potencial": 86, "minutos_12m": 3465, "rating_12m": 7.16, "fotmob_id": 12345},
    ])
    roster = pd.DataFrame([{
        "nome": "Otávio", "papel": "GK", "idade": 20, "qualidade": 65, "potencial": 71,
        "minutos_12m": 3150, "rating_12m": 7.15, "valor_mercado_eur": 500000,
    }])
    def fill_with_stale_club_values(frame, _universe, _team):
        frame = frame.copy()
        frame.loc[0, "qualidade"] = 65
        frame.loc[0, "potencial"] = 71
        frame.loc[0, "minutos_12m"] = 3150
        frame.loc[0, "rating_12m"] = 7.15
        return frame

    monkeypatch.setattr(scout_page, "_fill_from_club_games", fill_with_stale_club_values)

    result = scout_page._merge_roster(roster, universe, "Cruzeiro", "test-alias-precedence-v3")

    assert result.loc[0, "qualidade"] == 64
    assert result.loc[0, "potencial"] == 86
    assert result.loc[0, "minutos_12m"] == 3465
    assert result.loc[0, "rating_12m"] == 7.16

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

def test_id_estavel_unifica_atleta_mesmo_com_mudanca_de_funcao():
    players = pd.DataFrame([
        {"nome": "Atleta Exemplo", "clube": "Clube A", "papel": "LB", "fotmob_id": 999,
         "nascimento": "2002-01-01", "nacionalidade": "Brazil", "clube_observado": False},
        {"nome": "Atleta Exemplo", "clube": "Clube B", "papel": "CB", "fotmob_id": 999,
         "nascimento": "2002-01-01", "nacionalidade": "Brazil", "clube_observado": True},
    ])

    merged = scout_engine.merge_verified_player_duplicates(players)

    assert len(merged) == 1
    assert merged.iloc[0]["clube"] == "Clube B"

def test_otavio_prioriza_ficha_completa_sem_puxar_overall_antigo():
    games = '[{"match_date":"2026-10-01"},{"match_date":"2026-10-08"}]'
    players = pd.DataFrame([
        {"nome": "Otávio", "clube": "Cruzeiro", "papel": "GK", "idade": 20,
         "minutos_12m": 3150, "ultimos_jogos": games, "qualidade": 65, "potencial": 71,
         "valor_mercado_eur": 500000, "fotmob_id": None},
        {"nome": "Otávio Costa", "clube": "Cruzeiro", "papel": "GK", "idade": 20,
         "minutos_12m": 3465, "ultimos_jogos": games, "qualidade": 64, "potencial": 86,
         "valor_mercado_eur": np.nan, "fotmob_id": 12345},
    ])

    merged = scout_engine.merge_club_aliases(players)

    assert len(merged) == 1
    assert merged.iloc[0]["nome"] == "Otávio Costa"
    assert merged.iloc[0]["qualidade"] == 64
    assert merged.iloc[0]["potencial"] == 86
    assert merged.iloc[0]["valor_mercado_eur"] == 500000
    assert "otavio" in merged.iloc[0]["apelidos_core"]



def test_player_index_rebuilds_when_persisted_cache_version_is_stale(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from src.ui.pages import players_search as P
    import src.ui.context as context

    monkeypatch.setattr(P, "INDEX_PATH", tmp_path / "player_index.parquet")
    monkeypatch.setattr(P, "INDEX_META_PATH", tmp_path / "player_index.meta.json")
    P.INDEX_PATH.write_bytes(b"stale parquet placeholder")
    P.INDEX_META_PATH.write_text(json.dumps({"version": "database-v1"}), encoding="utf-8")
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: (_ for _ in ()).throw(AssertionError("stale cache was read")))

    built = []
    saved = []
    expected = pd.DataFrame([{"nome": "Kaiki", "pessoa": "kaiki"}])
    monkeypatch.setattr(P, "build_player_index", lambda db: built.append(db) or expected)
    monkeypatch.setattr(P, "save_player_index", lambda frame, version="": saved.append((frame, version)))
    monkeypatch.setattr(context, "get_service", lambda: SimpleNamespace(db="current-db"))
    P.player_index.clear()

    result = P.player_index("database-v2")
    assert result.equals(expected)
    assert built == ["current-db"]
    assert saved and saved[0][1] == "database-v2"
    P.player_index.clear()


def test_kaiki_como_cruzeiro_duplicate_is_unified_and_david_kaiki_stays_separate():
    from src.scout import engine as E

    players = pd.DataFrame([
        {"nome": "Kaiki", "_core": "kaiki", "clube": "Como", "papel": "LB", "posicao": "LB",
         "idade": np.nan, "nacionalidade": "Brazil", "fotmob_id": 123, "transfermarkt_id": None,
         "minutos_12m": 3828, "rating_12m": 7.38, "qualidade": 77, "potencial": 86, "ultimos_jogos": "[]"},
        {"nome": "Kaiki", "_core": "kaiki", "clube": "Cruzeiro", "papel": "LB", "posicao": "LB",
         "idade": 23, "nacionalidade": "Brazil", "fotmob_id": np.nan, "transfermarkt_id": 456,
         "minutos_12m": 3176, "rating_12m": 7.23, "qualidade": np.nan, "potencial": np.nan, "ultimos_jogos": "[]"},
        {"nome": "David Kaiki", "_core": "david kaiki", "clube": "Batman Petrolspor", "papel": "RW", "posicao": "RW",
         "idade": 22, "nacionalidade": "Brazil", "fotmob_id": 789, "transfermarkt_id": 999,
         "minutos_12m": 334, "rating_12m": 6.53, "qualidade": 55, "potencial": 60, "ultimos_jogos": "[]"},
    ])

    merged = E.merge_cross_source_duplicates(players)

    assert len(merged) == 2
    kaiki = merged.loc[merged["_core"] == "kaiki"].iloc[0]
    assert kaiki["clube"] == "Como"
    assert kaiki["qualidade"] == 77
    assert kaiki["potencial"] == 86
    assert kaiki["idade"] == 23
    assert kaiki["transfermarkt_id"] == 456
    assert "David Kaiki" in merged["nome"].tolist()


def test_kaiki_como_cruzeiro_merge_rejects_conflicting_stable_ids():
    from src.scout import engine as E

    players = pd.DataFrame([
        {"nome": "Kaiki", "_core": "kaiki", "clube": "Como", "papel": "LB", "idade": 23,
         "nacionalidade": "Brazil", "fotmob_id": 123, "transfermarkt_id": 111, "minutos_12m": 3828, "ultimos_jogos": "[]"},
        {"nome": "Kaiki", "_core": "kaiki", "clube": "Cruzeiro", "papel": "LB", "idade": 23,
         "nacionalidade": "Brazil", "fotmob_id": 123, "transfermarkt_id": 222, "minutos_12m": 3176, "ultimos_jogos": "[]"},
    ])

    merged = E.merge_cross_source_duplicates(players)

    assert len(merged) == 2


def test_cross_source_duplicate_reconciliation_is_generic():
    from src.scout import engine as E

    players = pd.DataFrame([
        {"nome": "Player Alpha", "_core": "player alpha", "clube": "Club A", "papel": "RW",
         "idade": 24.0, "nacionalidade": "Brazil", "fotmob_id": 100, "transfermarkt_id": None,
         "clube_observado": True, "ultimo_jogo": "2026-10-05", "minutos_12m": 1500,
         "qualidade": 81, "potencial": 88},
        {"nome": "Player Alpha", "_core": "player alpha", "clube": "Club B", "papel": "RW",
         "idade": 24.5, "nacionalidade": "Brasil", "fotmob_id": np.nan, "transfermarkt_id": 200,
         "clube_observado": False, "ultimo_jogo": "2026-09-01", "minutos_12m": 900,
         "qualidade": np.nan, "potencial": np.nan},
    ])

    merged = E.merge_cross_source_duplicates(players)

    assert len(merged) == 1
    assert merged.iloc[0]["clube"] == "Club A"
    assert merged.iloc[0]["qualidade"] == 81
    assert merged.iloc[0]["potencial"] == 88
    assert pd.to_numeric(merged.iloc[0]["transfermarkt_id"]) == 200


def test_cross_source_reconciliation_rejects_homonyms_and_biographical_conflicts():
    from src.scout import engine as E

    rows = [
        {"nome": "Player Country", "_core": "player country", "clube": "Club A", "papel": "ST",
         "idade": 24, "nacionalidade": "Brazil", "fotmob_id": 1, "transfermarkt_id": None},
        {"nome": "Player Country", "_core": "player country", "clube": "Club B", "papel": "ST",
         "idade": 24, "nacionalidade": "Argentina", "fotmob_id": None, "transfermarkt_id": 2},
        {"nome": "Player Age", "_core": "player age", "clube": "Club C", "papel": "CM",
         "idade": 19, "nacionalidade": "Brazil", "fotmob_id": 3, "transfermarkt_id": None},
        {"nome": "Player Age", "_core": "player age", "clube": "Club D", "papel": "CM",
         "idade": 28, "nacionalidade": "Brazil", "fotmob_id": None, "transfermarkt_id": 4},
        {"nome": "Player Role", "_core": "player role", "clube": "Club E", "papel": "RW",
         "idade": 22, "nacionalidade": "Brazil", "fotmob_id": 5, "transfermarkt_id": None},
        {"nome": "Player Role", "_core": "player role", "clube": "Club F", "papel": "CB",
         "idade": 22, "nacionalidade": "Brazil", "fotmob_id": None, "transfermarkt_id": 6},
    ]
    merged = E.merge_cross_source_duplicates(pd.DataFrame(rows))

    assert len(merged) == 6


def test_cross_source_reconciliation_leaves_ambiguous_three_way_match_separate():
    from src.scout import engine as E

    players = pd.DataFrame([
        {"nome": "Player Ambiguous", "_core": "player ambiguous", "clube": "Club A", "papel": "AM",
         "idade": 25, "nacionalidade": "Brazil", "fotmob_id": 10, "transfermarkt_id": None},
        {"nome": "Player Ambiguous", "_core": "player ambiguous", "clube": "Club B", "papel": "AM",
         "idade": 25, "nacionalidade": "Brazil", "fotmob_id": None, "transfermarkt_id": 20},
        {"nome": "Player Ambiguous", "_core": "player ambiguous", "clube": "Club C", "papel": "AM",
         "idade": 25, "nacionalidade": "Brazil", "fotmob_id": None, "transfermarkt_id": 30},
    ])

    merged = E.merge_cross_source_duplicates(players)

    assert len(merged) == 3


def test_verified_identity_rejects_transitive_cluster_with_conflicting_provider_ids():
    from src.scout import engine as E

    players = pd.DataFrame([
        {"nome": "Player Stable", "_core": "player stable", "clube": "Club A", "papel": "ST",
         "fotmob_id": 555, "transfermarkt_id": 100, "nascimento": "2001-01-01",
         "nacionalidade": "Brazil"},
        {"nome": "Player Stable", "_core": "player stable", "clube": "Club B", "papel": "ST",
         "fotmob_id": 555, "transfermarkt_id": None, "nascimento": "2001-01-01",
         "nacionalidade": "Brazil"},
        {"nome": "Player Stable", "_core": "player stable", "clube": "Club C", "papel": "ST",
         "fotmob_id": 555, "transfermarkt_id": 300, "nascimento": "2001-01-01",
         "nacionalidade": "Brazil"},
    ])

    merged = E.merge_verified_player_duplicates(players)

    assert len(merged) == 2
