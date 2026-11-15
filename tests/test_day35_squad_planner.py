"""Planejador de escalação: elenco, nota, melhor XI, provável XI, perfil e plano contra o adversário."""
import pandas as pd
import pytest

from src.squad.formations import FORMATIONS, fit, natural_role
from src.squad.planner import (best_xi, lab_rating, matchup_plan, plan_bonus, probable_xi, season_usage, squad_frame,
                               team_profile)

NAMES = ["Ana Lima", "Bruno Reis", "Caio Prado", "Davi Souto", "Enzo Mota", "Fabio Leal", "Gil Rocha", "Hugo Melo",
         "Ivo Nunes", "Joao Paiva", "Kaio Brito", "Luis Cunha", "Mauro Dias", "Nico Vaz", "Otto Sena", "Paulo Faro",
         "Quico Lobo", "Rui Matos", "Saulo Neri", "Tito Lago", "Ugo Pires", "Vitor Sa", "Wesley Ramos"]
POS = [("Goalkeeper", 2), ("Centre-Back", 4), ("Left-Back", 2), ("Right-Back", 2), ("Defensive Midfield", 2),
       ("Central Midfield", 3), ("Attacking Midfield", 1), ("Left Winger", 2), ("Right Winger", 2), ("Centre-Forward", 3)]


def _tm():
    rows, i = [], 0
    for pos, k in POS:
        for j in range(k):
            i += 1
            rows.append({"transfermarkt_id": i, "nome": NAMES[i - 1], "clube": "Time A", "clube_id": 10,
                         "posicao": "x", "funcao": pos, "nascimento": f"{1990 + i % 12}-05-01",
                         "altura_cm": 180 + (i % 3) * 5 + (8 if pos == "Centre-Back" and j == 0 else 0),
                         "valor_mercado_eur": (j + 1) * 5e6 + i * 1e5, "ultima_temporada": 2026})
    rows.append({"transfermarkt_id": 999, "nome": "Ex-atleta", "clube": "Time A", "clube_id": 10, "funcao": "Centre-Forward",
                 "valor_mercado_eur": 9e7, "ultima_temporada": 2023})
    return pd.DataFrame(rows)


def test_positions_and_fit():
    assert natural_role("Left Winger") == "LW" and natural_role("", "Defender") == "CB" and natural_role("ST") == "ST"
    assert fit("LB", "LB") == 1.0 and fit("LB", "LWB") > fit("LB", "CB") > fit("LB", "ST") and fit("GK", "ST") == 0
    assert all(len(v) == 11 and sum(r == "GK" for r, _, _ in v) == 1 for v in FORMATIONS.values())


def test_squad_rating_and_best_xi():
    tm = _tm()
    added = pd.DataFrame([{"nome": "Cria da base", "clube": "Time A", "funcao": "Centre-Forward", "nota_manual": 99}])
    sq = squad_frame(tm, [10], ["Time A"], added)
    assert "Ex-atleta" not in set(sq["nome"]) and "Cria da base" in set(sq["nome"])           # só o elenco atual
    usage = season_usage(pd.DataFrame([{"transfermarkt_id": 23, "data": "2026-09-01", "minutos": 900, "gols": 6,
                                        "assistencias": 2}]), sq["transfermarkt_id"].dropna(), since="2025-11-01")
    rated = lab_rating(sq, reference=tm, usage=usage)
    assert rated.loc[rated.nome == "Cria da base", "nota"].iloc[0] == 99
    assert rated["nota"].between(0, 100).all() and (rated["nota_base"] != "").all()
    xi = best_xi(rated, "4-3-3")
    assert len(xi) == 11 and len({p["jogador"] for p in xi}) == 11
    gk = next(p for p in xi if p["papel"] == "GK")
    assert rated.set_index("nome").loc[gk["jogador"], "papel"] == "GK"
    assert any(p["jogador"] == "Cria da base" for p in xi)                                   # nota 99 entra
    locked = best_xi(rated, "4-3-3", locked={10: "Ana Lima"})
    assert locked[10]["jogador"] == "Ana Lima"


def test_probable_xi_prefers_frequent_starters():
    sq = lab_rating(squad_frame(_tm(), [10], []), reference=_tm())
    games = [{"jogo": g, "data": f"2026-10-{g:02d}", "jogador": n, "titular": 1}
             for g in range(1, 6) for n in ["Caio Prado", "Ugo Pires", "Ana Lima"]]
    xi, info = probable_xi(pd.DataFrame(games), sq, "4-4-2", 5)
    names = {p["jogador"] for p in xi}
    assert {"Caio Prado", "Ugo Pires", "Ana Lima"} <= names and info["jogos_considerados"] == 5
    assert info["titulares_frequentes"]["Caio Prado"] == 5


def _matches_stats(team, opp_cross, n=6):
    m, s = [], []
    for i in range(n):
        mid = 100 + i
        m.append({"match_id": mid, "match_date": f"2026-10-{i + 1:02d}", "home_team_name": team, "away_team_name": f"X{i}",
                  "home_score": 2, "away_score": 1})
        for k, v in {"shots_total": 15, "crosses_total": opp_cross, "possession_pct": 62, "fouls": 10}.items():
            s.append({"match_id": mid, "team_name": team, "stat_key": k, "value": v})
        for k, v in {"shots_total": 18, "crosses_total": 30, "corners": 9}.items():
            s.append({"match_id": mid, "team_name": f"X{i}", "stat_key": k, "value": v})
    return pd.DataFrame(m), pd.DataFrame(s)


def test_profile_and_plan():
    base = {"shots_total": 12, "crosses_total": 15, "possession_pct": 50, "fouls": 12, "corners": 5, "goals": 1.3}
    m, s = _matches_stats("Rival", 28)
    theirs = team_profile(m, s, ["Rival"], base, 5)
    assert theirs["n"] == 5 and theirs["a_favor"]["crosses_total"]["dif_pct"] == pytest.approx(87, abs=1)
    m2, s2 = _matches_stats("Nós", 26)
    ours = team_profile(m2, s2, ["Nós"], base, 5)
    plan = matchup_plan(ours, theirs, "Nós", "Rival")
    assert any(d["chave"] == "crosses_total" for d in plan["neutralizar"])                   # rival cruza muito
    ex = next(d for d in plan["explorar"] if d["chave"] == "crosses_total")                  # e deixa cruzar
    assert ex["nossa_forca"] and ex["nossa_forca"]["chave"] == "crosses_total"               # e nós cruzamos bem
    sq = lab_rating(squad_frame(_tm(), [10], []), reference=_tm())
    bonus, why = plan_bonus(sq, plan)
    tall_cb = sq[(sq.papel == "CB") & (sq.altura_cm >= 188)]["nome"].tolist()
    assert tall_cb and all(bonus.get(n, 0) > 0 for n in tall_cb) and why


def test_profile_without_stats_is_empty_not_invented():
    m, _ = _matches_stats("Rival", 28)
    p = team_profile(m, pd.DataFrame(columns=["match_id", "team_name", "stat_key", "value"]), ["Rival"], {}, 5)
    assert p["n"] == 0 and p["a_favor"] == {}


def test_data_layer_db_profile(tmp_path):
    from src.data_hub.db import DataHubDB
    from src.data_hub.registry import DataLevel
    from src.squad import data as D

    db = DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")
    recs, boxes = [], []
    for i in range(6):
        for src, base, lvl in (("fdcouk", 2_000_000_000, DataLevel.BOXSCORE), ("espn", 500_000_000, DataLevel.BOXSCORE)):
            mid = base + 10 + i
            recs.append({"match_id": mid, "home_team_name": "Rival", "away_team_name": f"T{i}",
                         "match_date": f"2026-10-{i + 1:02d}", "home_score": 1, "away_score": 0, "competition_name": "Liga",
                         "season_name": "2026", "data_source": src, "data_level": lvl})
            st = [{"team_name": "Rival", "stat_key": "shots_total", "stat_label": "x", "value": 20 if src == "fdcouk" else 99},
                  {"team_name": f"T{i}", "stat_key": "shots_total", "stat_label": "x", "value": 8}]
            if src == "espn":
                st.append({"team_name": "Rival", "stat_key": "passes_total", "stat_label": "x", "value": 600})
            boxes.append((mid, {"team_stats": st, "lineups": [], "timeline": []}))
    db.upsert_matches(recs)
    for mid, b in boxes:
        db.save_boxscore(mid, b)
    m = D.recent_matches(db, ["Rival"], 5)
    assert len(m) == 5 and all(len(x) == 2 for x in m["ids"])                 # 2 fontes da mesma partida, 1 linha
    s = D.merged_stats(db, m, ["Rival"])
    mine = s[s.team_name == "Rival"]
    assert set(mine["stat_key"]) == {"shots_total", "passes_total"}            # estatísticas das duas fontes juntas
    base = D.baseline(db, ["Liga"], "2026-01-01", "2026-12-31")
    assert base["shots_total"] > 0 and base["goals"] == 0.5
    from src.squad.planner import team_profile

    p = team_profile(m, s, ["Rival"], base, 5, min_stat_keys=2)   # v36: limiar de "dado completo" ajustável
    assert p["n"] == 5 and p["a_favor"]["passes_total"]["media"] == 600
    assert team_profile(m, s, ["Rival"], base, 5)["n"] == 0             # só 2 números por jogo: não define perfil


def test_lake_table_filter_and_added_players(tmp_path, monkeypatch):
    from src.data_lake import lake as L
    from src.squad import data as D

    lk = L.Lake(root=tmp_path / "lake", sqlite_path=None)
    monkeypatch.setattr(D, "lake", lambda: lk)
    D._MEM.clear()
    lk.write("tm_aparicoes", pd.DataFrame({"transfermarkt_id": [1, 1, 2], "minutos": [90, 45, 90]}), mirror_sqlite=False)
    assert D.table("tm_aparicoes", None, "transfermarkt_id", [1])["minutos"].sum() == 135
    D.add_player({"nome": "Zé Novo", "clube": "Time A", "funcao": "Centre-Forward", "nota_manual": 77})
    D.add_player({"nome": "Zé Novo", "clube": "Time A", "funcao": "Left Winger", "nota_manual": 80})   # atualiza
    a = D.added_players()
    assert len(a) == 1 and a.iloc[0]["funcao"] == "Left Winger"
    D.remove_added("Zé Novo", "Time A")
    assert D.added_players().empty


def test_stable_version_holds_during_external_sync(tmp_path):
    """Sincronização em outro terminal: a tela não relê o catálogo a cada clique (versão estável por 10 min)."""
    import sqlite3

    from src.data_hub.db import DataHubDB

    db = DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")
    v1 = db.stable_version(probe_s=0)
    with sqlite3.connect(str(tmp_path / "hub.db")) as c:            # outro processo gravando (sem passar pela classe)
        c.execute("INSERT INTO matches (match_id, competition_name, season_name, home_team_name, away_team_name, "
                  "data_source, data_level) VALUES (2000000999, 'L', '2026', 'A', 'B', 'fdcouk', 'RESULT')")
    assert db.stable_version(probe_s=0) == v1 and db.has_pending_update()
    assert db.stable_version(probe_s=0, settle_s=0) != v1                 # passado o intervalo, adota
    v2 = db.stable_version(probe_s=0)
    db.upsert_matches([{"match_id": 2000001000, "home_team_name": "C", "away_team_name": "D", "data_source": "fdcouk",
                        "data_level": "RESULT", "competition_name": "L", "season_name": "2026", "match_date": "2026-01-01"}])                         # gravação da própria tela: vê na hora
    assert db.stable_version(probe_s=0) != v2


def test_bundle_parts_are_plain_and_picklable():
    import pickle

    from src.data_hub.service import MatchBundle

    b = MatchBundle(1, {"a": 1}, "EVENTS", "openplay", events=pd.DataFrame({"x": [1]}), boxscore={"t": pd.DataFrame()})
    parts = {"match_id": b.match_id, "meta": dict(b.meta), "level": b.level, "source": b.source, "events": b.events,
             "boxscore": dict(b.boxscore), "notes": list(b.notes)}
    assert MatchBundle(**pickle.loads(pickle.dumps(parts))).source == "openplay"
