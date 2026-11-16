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
