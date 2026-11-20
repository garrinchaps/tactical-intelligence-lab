"""Rodada 19: posições da FotMob pela escalação, Rankings no Scout, origem, cookie do visitante, modo congelado,
ESPN sem id, erros antigos no painel e registro do pré-aquecimento."""
import pandas as pd
import pytest

from src.scout import engine as E


class _DB:
    def __init__(self, path):
        import sqlite3
        self.path = str(path)
        c = sqlite3.connect(self.path)
        c.execute("CREATE TABLE match_lineups (match_id INTEGER, team_name TEXT, player_name TEXT, shirt_number INT, "
                  "position TEXT, is_starter INT, formation TEXT, coach TEXT)")
        c.executemany("INSERT INTO match_lineups VALUES (?,?,?,?,?,?,?,?)",
                      [(1, "A", "Fulano", 9, "ST", 1, "", ""), (1, "A", "Beltrano", 5, "SUB", 0, "", ""),
                       (2, "A", "Fulano", 9, "LW", 1, "", "")])
        c.commit(); c.close()

    def connect(self):
        import sqlite3
        from contextlib import contextmanager

        @contextmanager
        def cm():
            c = sqlite3.connect(self.path)
            try:
                yield c
                c.commit()
            finally:
                c.close()
        return cm()


def test_positions_filled_from_lineups(tmp_path):
    raw = pd.DataFrame({"match_id": [1, 2, 1], "player_name": ["Fulano", "Fulano", "Beltrano"],
                        "position": ["", None, ""]})
    out = E.fill_positions_from_lineups(_DB(tmp_path / "x.db"), raw)
    assert out["position"].tolist()[:2] == ["ST", "LW"]
    assert out["position"].iloc[2] == ""                      # reserva sem posição continua sem (não chuta)


def test_origin_groups():
    assert E.origin_group("Brasileirão Série B") == "Brasil · Série B"
    assert E.origin_group("Brasileirão Série C") == "Brasil · Série C"
    assert E.origin_group("Paraguai — Primera División") == "América do Sul"
    assert E.origin_group("Serie B") == "Europa e outras"     # Série B italiana não vira brasileira
    assert E.origin_group(None) == "Sem liga identificada"


def test_merge_rankings_blends_and_fills():
    u = pd.DataFrame({"nome": ["Ana Silva", "Bia Souza", "Bia Souza", "Caio Lima"],
                      "_core": ["ana silva", "bia souza", "bia souza", "caio lima"],
                      "qualidade": [60.0, 70.0, 70.0, None], "idade": [None, 25, 30, None],
                      "valor_mercado_eur": [None, 1e6, 2e6, None], "clube_liga": ["", "La Liga", "La Liga", ""],
                      "ultima_competicao": ["Brasileirão Série B", "", "", "Paraguai — Primera División"]})
    ev = pd.DataFrame({"core": ["ana silva", "bia souza", "caio lima"], "comp": ["Brasileirão Série B", "La Liga",
                       "Paraguai — Primera División"], "minutes": [1800, 2000, 900], "geral_entre_ligas": [80.0, 40.0, None],
                       "desempenho_90": [80, 40, 70], "nivel_competicao": [.6, 1.0, .5], "funcao": ["", "", ""],
                       "idade": [21.0, None, 19.0], "valor_eur": [3e5, None, None]})
    out = E.merge_rankings(u, ev)
    assert out.loc[0, "qualidade"] == pytest.approx(.55 * 60 + .45 * 80, abs=.1)   # 1.800 min = peso cheio (45%)
    assert out.loc[0, "idade"] == 21.0 and out.loc[0, "valor_mercado_eur"] == 3e5    # completados (FotMob/Wikidata)
    assert out.loc[1, "qualidade"] == 70.0 and pd.isna(out.loc[1, "nota_rankings"])   # homônimo: não mistura
    assert pd.notna(out.loc[3, "qualidade"])                    # só a avaliação: entra puxada à média
    assert out.loc[0, "origem"] == "Brasil · Série B" and out.loc[3, "origem"] == "América do Sul"


def test_gate_cookie_token():
    from src.ui import gate

    t = gate.token("2026-11-19", expected="segredo")
    assert "segredo" not in t and len(t) == 40
    assert gate.cookie_ok(gate.token(expected="segredo"), expected="segredo")
    assert not gate.cookie_ok(gate.token(expected="outra"), expected="segredo")
    assert not gate.cookie_ok("", expected="segredo")


def test_frozen_mode_blocks_network_and_freezes_versions(monkeypatch, tmp_path):
    from src.data_hub import activity, net
    from src.data_hub.db import DataHubDB

    monkeypatch.setenv("TIL_CONGELADO", "1")
    assert activity.network_blocked("https://www.fotmob.com/api/x")
    assert not activity.network_blocked("https://raw.githubusercontent.com/statsbomb/x.json")
    with pytest.raises(net.NetError):
        net._blocked("https://site.api.espn.com/x")
    db = DataHubDB(db_path=tmp_path / "f.db", schema_path="database/schema.sql")
    assert db.team_version(["Flamengo"]).endswith("congelado")
    monkeypatch.setenv("TIL_CONGELADO", "0")
    assert not activity.network_blocked("https://www.fotmob.com/api/x")


def test_espn_item_without_id_is_skipped():
    from src.data_hub.sources.espn import EspnProvider

    assert EspnProvider.parse_scoreboard_event({"competitions": [{}]}, "bra.1") is None
    assert EspnProvider.parse_fixture({"date": "2026-11-20"}, "bra.1") is None


def test_health_marks_old_errors():
    from src.data_hub import health

    errs = pd.DataFrame([{"message": "database is locked", "finished_at": "2026-11-18 10:00:00", "started_at": None}])
    assert health._err_text(errs, "OK").startswith("[antigo")
    assert not health._err_text(errs, "ERRO").startswith("[antigo")
    assert health._err_text(errs.iloc[0:0], "OK") == ""


def test_warmup_remembers_recent(monkeypatch, tmp_path):
    from src.ui import warmup

    monkeypatch.setattr(warmup, "RECENT_PATH", tmp_path / "r.json")
    for mid in (1, 2, 1):
        warmup.remember("jogo", mid)
    warmup.remember("time", "Flamengo")
    d = warmup._read_recent()
    assert d["jogos"] == [1, 2] and d["times"] == ["Flamengo"]
    names = [n for n, _ in warmup._plan()]
    # rodada 22: os passos não mostram nomes de times nem números de jogos (pedido do usuário)
    assert any(n.startswith("Times que você abriu") for n in names) and any(n.startswith("Jogos que você abriu") for n in names)
    assert not any("Flamengo" in n for n in names)


def test_lock_retry(monkeypatch):
    import sqlite3

    from src.data_hub import sync

    calls = {"n": 0}

    def job():
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return {"added": 1}

    assert sync._with_lock_retry(job, "x", lambda m: None, waits=(0,)) == {"added": 1}
    assert calls["n"] == 2
