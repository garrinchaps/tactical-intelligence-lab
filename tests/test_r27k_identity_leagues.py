"""Rodada 27k — grafias oficiais do clube, mesmo atleta em duas linhas, liga do clube, referências de nota, limpeza."""
import pandas as pd

from src.data_lake.ids import team_core
from src.scout import engine as E
from src.scout import overall as O


def test_official_club_names_share_core():
    pairs = [("Grêmio", "Grêmio Foot-Ball Porto Alegrense"), ("Internacional", "Sport Club Internacional"),
             ("Corinthians", "Sport Club Corinthians Paulista"), ("Botafogo", "Botafogo de Futebol e Regatas"),
             ("Boca Juniors", "Club Atlético Boca Juniors"), ("CRB", "Clube de Regatas Brasil")]
    for a, b in pairs:
        assert team_core(a) == team_core(b)
    assert team_core("Brasil") != team_core("CRB")            # seleção ≠ CRB
    assert team_core("Botafogo-SP") != team_core("Botafogo")   # clubes diferentes continuam separados


def _u(rows):
    u = pd.DataFrame(rows)
    u["_core"] = u["nome"].map(E.player_core)
    return u


def test_same_player_two_club_spellings_becomes_one():
    u = _u([dict(nome="Tiaguinho", clube="Grêmio", papel="ST", idade=19, minutos_12m=800, fotmob_id=1, valor_mercado_eur=None),
            dict(nome="Tiaguinho", clube="Grêmio Foot-Ball Porto Alegrense", papel="ST", idade=19, minutos_12m=0,
                 fotmob_id=None, valor_mercado_eur=2e6),
            dict(nome="Raykkonen", clube="Internacional", papel="LW", idade=18, minutos_12m=300, fotmob_id=5),
            dict(nome="Raykkonen", clube="Sport Club Internacional", papel="LW", idade=18, minutos_12m=250, fotmob_id=None)])
    out = E.merge_club_aliases(E.canonical_clubs(u))
    assert sorted(out["nome"]) == ["Raykkonen", "Tiaguinho"]
    assert out.loc[out["nome"] == "Tiaguinho", "valor_mercado_eur"].iloc[0] == 2e6


def test_two_real_namesakes_with_different_ids_stay_apart():
    u = _u([dict(nome="Gabriel", clube="Flamengo", papel="CB", idade=25, minutos_12m=900, fotmob_id=1),
            dict(nome="Gabriel", clube="Flamengo", papel="ST", idade=27, minutos_12m=900, fotmob_id=2)])
    assert len(E.merge_club_aliases(u)) == 2


def test_cup_is_never_the_club_league():
    u = pd.DataFrame(dict(nome=list("abcd"), clube=["Botafogo"] * 3 + ["Shakhtar Donetsk"],
                          clube_liga=["CONMEBOL Sul-Americana", "Brasileirão Série A", "Brasileirão Série A", "Premier Liga"],
                          clube_pais=["Brasil"] * 3 + ["Ucrânia"]))
    out = E.fix_club_leagues(u)
    assert set(out.loc[out["clube"] == "Botafogo", "clube_liga"]) == {"Brasileirão Série A"}
    assert out.loc[3, "clube_liga"] == "Ucrânia — Premier Liga"


def test_reference_anchor_pulls_listed_player_and_respects_ceiling():
    u = _u([dict(nome="Thibaut Courtois", qualidade=84.0, minutos_12m=3000, fonte_qualidade=""),
            dict(nome="Daniel Batz", qualidade=85.0, minutos_12m=2000, fonte_qualidade=""),
            dict(nome="Fulano Qualquer", qualidade=70.0, minutos_12m=2000, fonte_qualidade="")])
    out = O.anchor_to_references(u, potential=False)
    assert out.loc[0, "qualidade"] >= 88
    assert out.loc[1, "qualidade"] <= O.REFERENCE_CEILINGS["Daniel Batz"]
    assert out.loc[2, "qualidade"] == 70.0
    assert "referência" in out.loc[0, "fonte_qualidade"]


def test_ambiguous_single_name_is_not_anchored():
    u = _u([dict(nome="Tadeu", qualidade=80.0, minutos_12m=3000), dict(nome="Tadeu", qualidade=60.0, minutos_12m=500)])
    out = O.anchor_to_references(u, potential=False)
    assert list(out["qualidade"]) == [80.0, 60.0]


def test_cleanup_never_lists_main_db_as_copy(tmp_path, monkeypatch):
    from src.tools import limpeza as L

    monkeypatch.setattr(L, "ROOT", tmp_path)
    (tmp_path / "database").mkdir()
    main = tmp_path / "database" / "tactical_lab.db"
    main.write_bytes(b"x")
    (tmp_path / "tactical_lab_cloud_snapshot.db").write_bytes(b"x")
    (tmp_path / "tactical_lab_cloud_snapshot.db.gz").write_bytes(b"x")
    monkeypatch.setattr(L, "_main_db", lambda: main)
    names = [p.name for p in L._copy_candidates()]
    assert names == ["tactical_lab_cloud_snapshot.db"]          # nunca o principal, nunca o .gz
