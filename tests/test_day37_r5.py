"""Rodada 5: posições cruzando fontes, jogo hipotético, novos módulos táticos."""
import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.registry import to_internal_id


def _game(db, src, sid, date, opp, players, form="4-3-3"):
    mid = to_internal_id(src, sid)
    db.upsert_matches([{"match_id": mid, "source_match_id": str(sid), "competition_name": "La Liga", "season_name": "2026",
                        "match_date": date, "home_team_name": "Barcelona", "away_team_name": opp, "home_score": 2,
                        "away_score": 0, "status": "FT", "data_source": src, "data_level": "BOXSCORE"}])
    db.save_boxscore(mid, {"team_stats": [], "timeline": [], "player_stats": [],
                           "lineups": [{"team_name": "Barcelona", "player_name": n, "shirt_number": "", "position": p,
                                        "is_starter": 1, "formation": form, "coach": ""} for n, p in players]})
    return mid


ESPN_XI = [("Joan García", "G"), ("João Cancelo", "LB"), ("Gerard Martín", "CD-L"), ("Pau Cubarsí", "CD-R"),
           ("Jules Koundé", "RB"), ("Rodri", "CM"), ("Pedri", "LM"), ("Fermín López", "RM"), ("Anthony Gordon", "LF"),
           ("Raphinha", "F"), ("Lamine Yamal", "RF")]
GENERIC = {"G": "G", "LB": "D", "CD-L": "D", "CD-R": "D", "RB": "D", "CM": "M", "LM": "M", "RM": "M", "LF": "F", "F": "F", "RF": "F"}


def test_positions_generic_sources_do_not_move_players(tmp_path):
    from src.squad import matchday as M

    db = DataHubDB(tmp_path / "t.db")
    for i, d in enumerate(["2026-10-10", "2026-10-17", "2026-10-25", "2026-10-31"]):
        _game(db, "espn", 1000 + i, d, f"Rival {i}", ESPN_XI)
        # o MESMO jogo pela API-Football, com posição genérica (G/D/M/F) — antes contava em dobro e virava ST/CB
        _game(db, "api_football", 2000 + i, d, f"Rival {i}", [(n, GENERIC[p]) for n, p in ESPN_XI])
    # jogos só na API-Football (genéricos): não podem tirar o Yamal da ponta
    for i, d in enumerate(["2026-09-01", "2026-09-08", "2026-09-15"]):
        _game(db, "api_football", 3000 + i, d, f"Outro {i}", [(n, GENERIC[p]) for n, p in ESPN_XI])
    info = M.player_table(db, ["Barcelona"])
    assert len(info["jogos"]) == 7                     # 4 duplicados contam uma vez + 3 só da API-Football
    pl = info["jogadores"].set_index("nome")
    assert pl.loc["Lamine Yamal", "papel"] == "RW" and pl.loc["Jules Koundé", "papel"] == "RB"
    assert pl.loc["Raphinha", "papel"] == "ST" and pl.loc["Anthony Gordon", "papel"] == "LW"
    assert pl.loc["Pedri", "papel"] == "CM"            # LM da ESPN no 4-3-3 com pontas = meia central
    xi, form = M.xi_for(info, "4-3-3", "provavel")
    got = {p["jogador"]: p["papel"] for p in xi}
    assert got["Lamine Yamal"] == "RW" and got["Raphinha"] == "ST" and got["Anthony Gordon"] == "LW"
    assert got["Jules Koundé"] == "RB" and got["Pau Cubarsí"] == "CB"


def test_generic_only_player_keeps_sector_but_not_exact_fit():
    from src.squad.formations import fit
    from src.squad.positions import classify, player_roles

    assert classify("F", "api_football") == ("F?", False)
    assert classify("F", "espn") == ("ST", True)
    assert classify("Right Winger", "transfermarkt") == ("RW", True)
    assert classify("RAMF", "wyscout") == ("RW", True)
    assert fit("ST", "F?") < 1.0 and fit("GK", "F?") == 0.0
    starts = pd.DataFrame({"data": ["2026-01-01", "2026-01-08"], "papel": [None, None], "papel_generico": ["F?", "F?"]})
    roles, main, origem = player_roles(starts, tm_role="RW")
    assert main == "RW" and "Transfermarkt" in origem


# ------------------------------------------------------------------ FotMob
def _p(name, pid, x, y, starter=True):
    return {"id": pid, "name": name, "positionId": pid, "usualPlayingPositionId": 1, "shirtNumber": "1",
            "horizontalLayout": {"x": x, "y": y}, "performance": {"rating": 7.1, "events": [{"type": "yellowCard", "time": 30}]}}


def test_fotmob_layout_role_reads_exact_position():
    from src.data_hub.sources.fotmob import layout_role

    f = "4-2-3-1"
    assert layout_role(_p("gk", 11, .10, .5), f) == "GK"
    assert layout_role(_p("rb", 32, .29, .88), f) == "RB" and layout_role(_p("lb", 38, .29, .12), f) == "LB"
    assert layout_role(_p("cb", 34, .29, .62), f) == "CB"
    assert layout_role(_p("dm", 64, .48, .70), f) == "DM"
    assert layout_role(_p("rw", 83, .68, .84), f) == "RW" and layout_role(_p("am", 85, .68, .50), f) == "AM"
    assert layout_role(_p("st", 115, .87, .50), f) == "ST"
    assert layout_role(_p("rwb", 52, .50, .90), "3-4-3") == "RWB"
    assert layout_role({"name": "x", "positionId": 1000}, f) is None     # sem layout: não inventa posição


def test_fotmob_parse_match_and_details():
    from src.data_hub.sources.fotmob import FotmobProvider

    done, fut = FotmobProvider.parse_match({"id": "5", "home": {"name": "A", "id": 1}, "away": {"name": "B", "id": 2},
                                            "status": {"utcTime": "2026-11-14T22:00:00Z", "finished": True, "scoreStr": "2 - 1"}},
                                           268, "2026")
    assert done["home_score"] == 2 and done["away_score"] == 1 and done["match_id"] == 12_000_000_005 and fut is None
    done, fut = FotmobProvider.parse_match({"id": "6", "home": {"name": "A"}, "away": {"name": "B"},
                                            "status": {"utcTime": "2026-12-01T22:00:00Z"}}, 268, "2026")
    assert done is None and fut["league"] == "fotmob:268"
    d = {"header": {"teams": [{"name": "A", "id": 1}, {"name": "B", "id": 2}]},
         "content": {"stats": {"Periods": {"All": {"stats": [{"key": "top_stats", "stats": [
             {"key": "expected_goals", "stats": ["1.20", "0.40"]}, {"key": "accurate_passes", "stats": ["300 (80%)", "200 (70%)"]},
             {"key": "physical_metrics_distance_covered", "stats": [110000, 108000]}]}]}}},
             "lineup": {"homeTeam": {"name": "A", "formation": "4-2-3-1", "starters": [_p("Gk A", 11, .1, .5), _p("Rw A", 83, .68, .84)],
                                     "subs": [], "unavailable": [{"name": "Lesionado", "unavailability": {"type": "injury", "expectedReturn": "Doubtful"}}]},
                        "awayTeam": {"name": "B", "formation": "4-4-2", "starters": [], "subs": []}},
             "playerStats": {"83": {"name": "Rw A", "teamName": "A", "stats": [{"stats": {"Goals": {"key": "goals", "stat": {"value": 1}},
                                                                                      "xA": {"key": "expected_assists", "stat": {"value": 0.3}}}}]}},
             "shotmap": {"shots": [{"teamId": 1, "playerName": "Rw A", "min": 10, "x": 105, "y": 34, "expectedGoals": 0.5,
                                    "eventType": "Goal", "isOnTarget": True}]},
             "matchFacts": {"events": {"events": [{"type": "Goal", "time": 10, "isHome": True, "player": {"name": "Rw A"}}]}}}}
    box, shots, unav = FotmobProvider.parse_details(d, 12_000_000_005)
    st = {(r["team_name"], r["stat_key"]): r["value"] for r in box["team_stats"]}
    assert st[("A", "xg")] == 1.2 and st[("A", "pass_accuracy_pct")] == 80 and st[("B", "distance_m")] == 108000
    assert {(r["player_name"], r["position"]) for r in box["lineups"]} == {("Gk A", "GK"), ("Rw A", "RW")}
    assert box["player_stats"][0]["stats"]["totalGoals"] == 1 and box["player_stats"][0]["rating"] == 7.1
    assert shots[0]["x"] == 120 and shots[0]["y"] == 40 and shots[0]["xg"] == 0.5
    assert unav["A"][0]["volta"] == "Doubtful"
    assert any(e["event_type"] == "Yellow Card" for e in box["timeline"]) and any(e["event_type"] == "Goal" for e in box["timeline"])


def test_fotmob_ids_and_fixture_dedup(tmp_path):
    from src.data_hub.registry import source_from_internal_id
    from src.data_hub.sources.espn import EspnProvider
    from src.squad.matchday import next_fixtures

    assert source_from_internal_id(12_000_000_005) == "fotmob" and source_from_internal_id(11_000_000_005) == "openplay"
    db = DataHubDB(tmp_path / "f.db")

    class _S:
        pass
    s = _S(); s.db = db
    rows = [{"match_id": 500_000_001, "league": "bra.1", "competition": "Brasileirão", "kickoff": "2099-11-18T22:00Z",
             "home": "Cruzeiro", "away": "Palmeiras", "home_id": 0, "away_id": 0, "status": "S", "venue": ""},
            {"match_id": 12_000_000_001, "league": "fotmob:268", "competition": "Brasileirão", "kickoff": "2099-11-18T22:00:00Z",
             "home": "Cruzeiro", "away": "Palmeiras", "home_id": 0, "away_id": 0, "status": "S", "venue": ""}]
    EspnProvider.save_fixtures(s, rows)
    fx = next_fixtures(db, ["Cruzeiro"])
    assert len(fx) == 1 and fx.iloc[0]["league"] == "bra.1"


# ------------------------------------------------------------------ Rodada 5: padrões e histórico
def test_match_patterns_on_world_cup_final():
    from src.connectors.statsbomb_connector import load_demo_events
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.analytics import match_patterns as MP
    from src.preprocessing.event_cleaner import EventPreprocessor

    df = EventPreprocessor.process_match_events(StatsBombDataLoader._parse_raw_events(None, load_demo_events(3869685), 3869685))
    sp = MP.set_pieces(df, "Argentina")
    assert sp["ataque"]["escanteio"]["cobradores"] == {"Lionel Messi": 6}          # Messi bateu os 6 escanteios
    subs = MP.substitution_impact(df, "France")["trocas"]
    first = subs[0]
    assert first["minuto"] == 41 and set(first["saiu"]) == {"Ousmane Dembélé", "Olivier Giroud"}
    assert first["placar_na_troca"] == "0 x 2" and "não causa" in first["aviso"]
    assert first["variacao"]["posse_pct"] > 10                    # a França passou a ter mais a bola depois das trocas
    gs = MP.game_state(df, "France")["estados"]
    assert set(gs) <= {"vencendo", "empatando", "perdendo"} and "perdendo" in gs
    assert abs(sum(v["minutos"] for v in gs.values()) - 124) < 6   # 120 + acréscimos, sem a disputa de pênaltis


def _team_game(db, mid, date, home, away, hs, as_, stats_h, stats_a, comp="Liga X"):
    db.upsert_matches([{"match_id": mid, "source_match_id": str(mid), "competition_name": comp, "season_name": "2026",
                        "match_date": date, "home_team_name": home, "away_team_name": away, "home_score": hs, "away_score": as_,
                        "status": "FT", "data_source": "espn", "data_level": "BOXSCORE"}])
    from src.data_hub.boxscore import stat_row

    rows = [stat_row(home, k, v) for k, v in stats_h.items()] + [stat_row(away, k, v) for k, v in stats_a.items()]
    db.save_boxscore(mid, {"team_stats": [r for r in rows if r], "lineups": [], "timeline": [], "player_stats": []})


def test_team_history_identity_vulnerability_similar(tmp_path):
    from src.analytics import team_history as TH

    db = DataHubDB(tmp_path / "h.db")
    base = {"possession_pct": 50, "pass_accuracy_pct": 80, "passes_total": 400, "long_balls_accurate": 30, "crosses_total": 15,
            "shots_total": 12, "shots_inside_box": 7, "xg": 1.2, "touches_opp_box": 20, "tackles_won": 15, "interceptions": 8}
    mid = 500_200_000
    # 30 jogos de outros times = régua da competição
    for i in range(30):
        _team_game(db, mid + i, f"2026-0{1 + i % 9}-{10 + i % 18:02d}", f"T{i}", f"U{i}", 1, 1, base,
                   {**base, "possession_pct": 50 + (i % 5) - 2, "crosses_total": 14 + i % 4})
    # o time: muita posse em todos os jogos e sofre MUITOS cruzamentos em quase todos
    for j in range(6):
        _team_game(db, mid + 100 + j, f"2026-10-{j + 1:02d}", "Alvo", f"R{j}", 2, 1,
                   {**base, "possession_pct": 68 + j % 3}, {**base, "possession_pct": 32 - j % 3, "crosses_total": 30 + j})
    idn = TH.identity(db, ["Alvo"])
    assert idn["jogos"] == 6 and any(t["traco"] == "gosta de ter a bola" and t["frequencia_pct"] == 100 for t in idn["tracos"])
    vu = TH.vulnerabilities(db, ["Alvo"])
    assert any(p["problema"] == "sofre muitos cruzamentos" for p in vu["padroes"])
    hab = TH.vs_habit(db, ["Alvo"], mid + 105)
    assert "diferencas" in hab and hab["jogos_historico"] >= 4
    sim = TH.similar(db, ["Alvo"], mid + 105, k=2)
    assert sim["semelhantes"] and sim["semelhantes"][0]["time_comparado"] == "Alvo"     # os mais parecidos são dele mesmo
    assert all(s["match_id"] != mid + 105 for s in sim["semelhantes"])


def test_benchmark_compares_models_on_same_folds():
    import pandas as pd

    from src.machine_learning.benchmark import DEMO, run

    d = pd.read_csv(DEMO)
    small = d[d["match_id"].isin(sorted(d["match_id"].unique())[:16])]
    res = run(small, k=3, epochs=5, n_boot=30)
    names = [r["modelo"] for r in res["resultados"]]
    assert any(n.startswith("Rede neural") for n in names) and any("logística" in n for n in names)
    floor = next(r for r in res["resultados"] if r["modelo"].startswith("Taxa constante"))
    assert all(r["auc"] >= floor["auc"] - 0.05 for r in res["resultados"])
    assert all("veredito" in r for r in res["resultados"] if not r["modelo"].startswith(("Taxa", "Regressão logística (todas")))
