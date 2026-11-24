import pandas as pd

from src.scout.engine import _boolean_mask


def test_boolean_mask_handles_sqlite_integer_flags():
    values = pd.Series([0, 1, None, 0, 1], dtype="Int64")
    assert _boolean_mask(values).tolist() == [False, True, False, False, True]


def test_boolean_mask_handles_text_flags_without_truthy_false_strings():
    values = pd.Series(["false", "TRUE", "0", "sim", None, "não"], dtype="string")
    assert _boolean_mask(values).tolist() == [False, True, False, True, False, False]


def test_boolean_mask_preserves_boolean_flags():
    values = pd.Series([False, True, None], dtype="boolean")
    assert _boolean_mask(values).tolist() == [False, True, False]


def test_team_match_filter_exposes_all_data_depths():
    from src.ui.pages.clubs import filter_team_matches

    matches = pd.DataFrame({
        "match_id": [1, 2, 3, 4],
        "data_level": ["EVENTS", "BOXSCORE", "RESULT", "EVENTS"],
    })

    assert filter_team_matches(matches)["match_id"].tolist() == [1, 2, 3, 4]
    assert filter_team_matches(matches, "Somente com lances")["match_id"].tolist() == [1, 4]
    assert filter_team_matches(matches, "Somente com estatísticas")["match_id"].tolist() == [2]
    assert filter_team_matches(matches, "Somente placares")["match_id"].tolist() == [3]

def test_national_team_roster_excludes_foreign_and_unknown_nationalities():
    from src.squad.planner import filter_national_team_players, national_team_key

    players = pd.DataFrame({
        "nome": ["Vinícius", "Mbappé", "Sem cadastro"],
        "nacionalidade": ["Brazil", "France", None],
    })
    assert national_team_key("Brasil") == "brazil"
    filtered = filter_national_team_players(players, "Brazil")
    assert filtered["nome"].tolist() == ["Vinícius"]


def test_club_roster_is_not_filtered_as_a_national_team():
    from src.squad.planner import filter_national_team_players

    players = pd.DataFrame({"nome": ["Jogador"], "nacionalidade": ["France"]})
    assert filter_national_team_players(players, "Fluminense")["nome"].tolist() == ["Jogador"]


def test_fotmob_international_friendlies_are_in_automatic_catalog():
    from src.data_hub.sources.fotmob import LEAGUES, PRIORITY

    assert LEAGUES[114] == "Amistosos internacionais"
    assert 114 in PRIORITY


def test_find_player_resolves_unique_short_name_only_with_matching_club(monkeypatch):
    from src.scout import snapshot as S

    universe = pd.DataFrame({
        "_core": ["otavio costa", "otavio silva"],
        "clube": ["Cruzeiro", "Atlético"],
        "clube_tm": ["Cruzeiro", "Atlético"],
        "qualidade": [64, 70],
        "potencial": [86, 80],
        "minutos_12m": [3465, 2000],
    }, index=[10, 20])
    index = {"core": {}, "pid": {}}
    monkeypatch.setattr(S, "cached_universe", lambda: universe)
    monkeypatch.setattr(S, "_index", lambda: index)

    found = S.find_player("otavio", ["Otávio"], "Cruzeiro")
    assert found["qualidade"] == 64
    assert found["potencial"] == 86
    assert found["clube"] == "Cruzeiro"

    assert S.find_player("otavio", ["Otávio"], "Flamengo") is None


def test_scout_roster_name_resolution_handles_short_names_and_ambiguity():
    from src.ui.pages.scout import _resolve_roster_name_cores

    resolved = _resolve_roster_name_cores(
        ["Otávio", "Leonardo", "M. Henrique", "João"],
        ["Otávio Costa", "Leonardo Nascimento", "Matheus Henrique", "João Pedro", "João Victor"],
    )
    assert resolved["Otávio"] == "Otávio Costa"
    assert resolved["Leonardo"] == "Leonardo Nascimento"
    assert resolved["M. Henrique"] == "Matheus Henrique"
    assert "João" not in resolved  # nome ambíguo não é associado por chute



def test_find_player_rejects_a_single_exact_name_from_the_wrong_club(monkeypatch):
    from src.scout import snapshot as S

    universe = pd.DataFrame({
        "_core": ["otavio"], "nome": ["Otávio"], "clube": ["Porto"],
        "clube_tm": ["Porto"], "qualidade": [82], "potencial": [85],
        "minutos_12m": [3000],
    }, index=[1])
    monkeypatch.setattr(S, "cached_universe", lambda: universe)
    monkeypatch.setattr(S, "_index", lambda: {"core": {"otavio": [1]}, "pid": {}})

    assert S.find_player("otavio", ["Otávio"], "Cruzeiro") is None


def test_find_player_discards_wrong_pid_and_resolves_same_club_full_name(monkeypatch):
    from src.scout import snapshot as S

    universe = pd.DataFrame({
        "_core": ["otavio", "otavio costa"],
        "nome": ["Otávio", "Otávio Costa"],
        "clube": ["Porto", "Cruzeiro"],
        "clube_tm": ["Porto", "Cruzeiro"],
        "idade": [31, 20],
        "pid": ["tm-old", "tm-current"],
        "qualidade": [82, 64], "potencial": [84, 86],
        "minutos_12m": [3000, 3465],
    }, index=[1, 2])
    index = {"core": {"otavio": [1], "otavio costa": [2]},
             "pid": {"tm-old": 1, "tm-current": 2}}
    monkeypatch.setattr(S, "cached_universe", lambda: universe)
    monkeypatch.setattr(S, "_index", lambda: index)

    found = S.find_player("otavio", ["Otávio"], "Cruzeiro", pid="tm-old", age=20)
    assert found["nome"] == "Otávio Costa"
    assert found["qualidade"] == 64
    assert found["potencial"] == 86


def test_source_profile_lookup_never_uses_same_name_from_another_club():
    from src.ui.pages.players_search import _source_rows_for_player

    rows = pd.DataFrame({
        "transfermarkt_id": [111, 222],
        "nome": ["Otávio", "Otávio Costa"],
        "clube": ["FC Porto", "Cruzeiro"],
        "nascimento": ["1995-02-09", "2006-04-10"],
    })
    found = _source_rows_for_player(rows, ["Otávio"], "Cruzeiro", "transfermarkt_id", expected_age=20)
    assert found["transfermarkt_id"].astype(str).tolist() == ["222"]

    wrong_only = _source_rows_for_player(rows.iloc[[0]], ["Otávio"], "Cruzeiro", "transfermarkt_id", expected_age=20)
    assert wrong_only.empty


def test_source_profile_lookup_rejects_multiple_transfermarkt_ids_for_same_club():
    from src.ui.pages.players_search import _source_rows_for_player

    rows = pd.DataFrame({
        "transfermarkt_id": [222, 333],
        "nome": ["Otávio Costa", "Otávio Costa"],
        "clube": ["Cruzeiro", "Cruzeiro"],
        "nascimento": ["2006-04-10", "2006-04-10"],
    })
    found = _source_rows_for_player(rows, ["Otávio"], "Cruzeiro", "transfermarkt_id", expected_age=20)
    assert found.empty


def test_scout_roster_name_resolution_rejects_age_conflict():
    from src.ui.pages.scout import _resolve_roster_name_cores

    resolved = _resolve_roster_name_cores(
        ["Otávio"], ["Otávio Costa"],
        roster_ages={"Otávio": 20}, scout_ages={"Otávio Costa": [31]},
    )
    assert "Otávio" not in resolved


def test_find_player_does_not_treat_transfermarkt_past_club_as_current_club(monkeypatch):
    from src.scout import snapshot as S

    universe = pd.DataFrame({
        "_core": ["otavio costa"], "nome": ["Otávio Costa"],
        "clube": ["Cruzeiro"], "clube_tm": ["FC Porto"], "idade": [20],
        "qualidade": [64], "potencial": [86], "minutos_12m": [3465],
    }, index=[1])
    monkeypatch.setattr(S, "cached_universe", lambda: universe)
    monkeypatch.setattr(S, "_index", lambda: {"core": {"otavio costa": [1]}, "pid": {}})

    assert S.find_player("otavio costa", ["Otávio Costa"], "Cruzeiro", age=20)["qualidade"] == 64
    assert S.find_player("otavio costa", ["Otávio Costa"], "FC Porto", age=20) is None


def test_source_profile_short_name_uses_age_to_disambiguate_same_club_candidates():
    from src.ui.pages.players_search import _source_rows_for_player

    rows = pd.DataFrame({
        "transfermarkt_id": [222, 333],
        "nome": ["Otávio Costa", "Otávio Silva"],
        "clube": ["Cruzeiro", "Cruzeiro"],
        "nascimento": ["2006-04-10", "1995-02-09"],
    })
    found = _source_rows_for_player(rows, ["Otávio"], "Cruzeiro", "transfermarkt_id", expected_age=20)
    assert found["transfermarkt_id"].astype(str).tolist() == ["222"]


def test_scout_roster_short_name_uses_age_to_disambiguate_same_club_candidates():
    from src.ui.pages.scout import _resolve_roster_name_cores

    resolved = _resolve_roster_name_cores(
        ["Otávio"], ["Otávio Costa", "Otávio Silva"],
        roster_ages={"Otávio": 20}, scout_ages={"Otávio Costa": [20], "Otávio Silva": [31]},
    )
    assert resolved["Otávio"] == "Otávio Costa"



def test_player_resolver_merges_single_token_alias_only_with_shared_source_id():
    from src.data_hub.player_resolver import resolve

    confirmed = pd.DataFrame([
        {"nome": "Kaiki", "core": "kaiki", "clube": "Cruzeiro", "fonte": "FotMob",
         "fotmob_id": "fm-123", "nascimento": "", "nacionalidade": "Brazil"},
        {"nome": "David Kaiki", "core": "david kaiki", "clube": "Cruzeiro", "fonte": "FotMob",
         "fotmob_id": "fm-123", "nascimento": "", "nacionalidade": "Brazil"},
    ])
    people, _ = resolve(confirmed)
    assert people.nunique() == 1


def test_player_resolver_keeps_same_surname_profiles_separate_without_identity_evidence():
    from src.data_hub.player_resolver import resolve

    uncertain = pd.DataFrame([
        {"nome": "Kaiki", "core": "kaiki", "clube": "Cruzeiro", "fonte": "FotMob",
         "fotmob_id": "fm-123", "nascimento": "", "nacionalidade": "Brazil"},
        {"nome": "David Kaiki", "core": "david kaiki", "clube": "Batman Petrolspor", "fonte": "FotMob",
         "fotmob_id": "fm-456", "nascimento": "", "nacionalidade": "Brazil"},
    ])
    people, _ = resolve(uncertain)
    assert people.nunique() == 2


def test_player_resolver_can_confirm_single_token_alias_with_same_birth_date():
    from src.data_hub.player_resolver import resolve

    rows = pd.DataFrame([
        {"nome": "Kaiki", "core": "kaiki", "clube": "Cruzeiro", "fonte": "FotMob",
         "nascimento": "2003-03-01", "nacionalidade": "Brazil"},
        {"nome": "David Kaiki", "core": "david kaiki", "clube": "Cruzeiro", "fonte": "Transfermarkt",
         "nascimento": "2003-03-01", "nacionalidade": "Brazil"},
    ])
    people, _ = resolve(rows)
    assert people.nunique() == 1


def test_player_resolver_can_reconcile_duplicate_provider_ids_with_same_biography():
    from src.data_hub.player_resolver import resolve

    rows = pd.DataFrame([
        {"nome": "Kaiki", "core": "kaiki", "clube": "Cruzeiro", "fonte": "FotMob",
         "fotmob_id": "fm-old", "nascimento": "2003-03-01", "nacionalidade": "Brazil"},
        {"nome": "David Kaiki", "core": "david kaiki", "clube": "Cruzeiro", "fonte": "FotMob",
         "fotmob_id": "fm-new", "nascimento": "2003-03-01", "nacionalidade": "Brazil"},
    ])
    people, _ = resolve(rows)
    assert people.nunique() == 1
