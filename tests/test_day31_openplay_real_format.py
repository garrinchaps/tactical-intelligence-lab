"""OpenPlay no formato REAL da release data-v0.1.0 (colunas conferidas com --inspecionar no PC do usuário)."""
import pandas as pd
import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


def _files(d):
    pd.DataFrame([
        {"match_id": 899244, "comp": "afcon", "season": 2015, "competition": "Africa Cup of Nations",
         "date": "2015-01-17 00:00:00", "home_team_id": 5449, "home_team": "Equatorial Guinea", "away_team_id": 1128,
         "away_team": "Congo", "home_score": 2, "away_score": 1, "home_ht_score": 1, "away_ht_score": 0, "n_events": 9},
        {"match_id": 899245, "comp": "afcon", "season": 2015, "competition": "Africa Cup of Nations",
         "date": "2015-01-17 00:00:00", "home_team": "Burkina Faso", "away_team": "Gabon", "home_score": 0,
         "away_score": 2, "n_events": 0}]).to_csv(d / "matches.csv", index=False)
    pd.DataFrame([  # sem coluna de nome do time: só id + lado; posse negativa existe no arquivo real
        {"match_id": 899244, "team_id": 5449, "side": "home", "shots": 7, "shots_on_target": 3, "passes": 317,
         "passes_completed": 239, "pass_pct": 75.4, "corners_taken": 3, "fouls_committed": 27, "possession_pct": 40.5,
         "xg": 0.65, "big_chances": 2},
        {"match_id": 899244, "team_id": 1128, "side": "away", "shots": 15, "shots_on_target": 6, "passes": 466,
         "passes_completed": 380, "pass_pct": 81.5, "corners_taken": 5, "fouls_committed": 13, "possession_pct": -28.8,
         "xg": 1.39, "big_chances": 3}]).to_csv(d / "team_match_stats.csv", index=False)
    H, A = "Equatorial Guinea", "Congo"
    e = lambda **k: {"match_id": 899244, "period": "FirstHalf", "minute": 0, "second": 0, "x": 50.0, "y": 50.0,
                     "outcome": "Successful", **k}
    ev = [e(team=H, player="Nsue", type="Start", x=0.0, y=0.0),
          e(team=H, player="Nsue", type="Pass", minute=1, end_x=70.0, end_y=20.0, q_cross=True),
          e(team=A, player="Balboa", type="Foul", minute=3, outcome="Unsuccessful"),
          e(team=H, player="Mbele", type="Foul", minute=3),
          e(team=A, player="Balboa", type="Card", minute=3, q_yellow=True),
          e(team=H, player="Nsue", type="Goal", minute=20, x=90.0, y=50.0, xg=0.4, body_part="Head"),
          e(team=A, player="Ondama", type="Goal", minute=30, x=95.0, y=50.0, q_owngoal=True),   # gol contra do Congo
          e(team=A, player="Oniangue", type="Goal", period="SecondHalf", minute=70, x=88.0, y=45.0, xg=0.76,
            q_penalty=True),
          e(team=H, player="Ibán", type="SubstitutionOn", period="SecondHalf", minute=75),
          e(team=H, player="Nsue", type="SubstitutionOff", period="SecondHalf", minute=75),
          e(team=H, player="Ibán", type="BallTouch", period="SecondHalf", minute=80),             # toque comum: fora
          e(team=A, player="X", type="SavedShot", period="PenaltyShootout", minute=121, x=88.0, y=50.0),
          e(team=H, player="Y", type="End", period="PostGame", minute=125)]
    pd.DataFrame(ev).to_csv(d / "events_afcon_2015.csv", index=False)
    pd.DataFrame([e(match_id=1, team="Z", player="Z", type="Pass")]).to_csv(d / "events_eng_1415.csv", index=False)


def test_real_format_stats_levels_and_events(db, tmp_path, monkeypatch):
    from src.data_hub.service import MatchDataService
    from src.data_hub.sources.openplay import OpenPlayProvider

    d = tmp_path / "op"
    d.mkdir()
    _files(d)
    out = OpenPlayProvider(db, path=str(d)).sync()
    assert out["partidas"] == 2
    cat = db.catalog("data_source = 'openplay'").set_index("source_match_id")
    assert cat.loc["899244", "data_level"] == DataLevel.EVENTS
    assert cat.loc["899245", "data_level"] == DataLevel.RESULT               # n_events = 0 → não é EVENTOS
    mid = int(cat.loc["899244", "match_id"])
    ts = db.load_boxscore(mid)["team_stats"]
    get = lambda team, key: ts[(ts.team_name == team) & (ts.stat_key == key)]["value"].tolist()
    assert get("Equatorial Guinea", "shots_total") == [7] and get("Congo", "passes_accurate") == [380]
    assert get("Equatorial Guinea", "possession_pct") == [40.5]
    assert get("Congo", "possession_pct") == []                               # -28,8% é descartado, não corrigido
    assert get("Equatorial Guinea", "fouls") == [27] and get("Equatorial Guinea", "ht_goals") == [1]
    assert get("Congo", "big_chances") == [3]

    monkeypatch.setenv("OPENPLAY_PATH", str(d))
    ev = MatchDataService(db).load(mid).events
    types = ev["type_name"].tolist()
    assert "Start" not in types and "Miscontrol" not in types and len(ev[ev.period == 5]) == 1
    assert types.count("Foul Committed") == 1 and types.count("Foul Won") == 1
    fc = ev[ev.type_name == "Foul Committed"].iloc[0]
    assert fc.team_name == "Congo"                                             # quem cometeu, não quem sofreu
    card = ev[ev.type_name == "Bad Behaviour"].iloc[0]
    assert card.foul_committed_card_name == "Yellow Card" and card.player_name == "Balboa"
    og = ev[ev.type_name == "Own Goal Against"]
    assert len(og) == 1 and og.iloc[0].team_name == "Congo"
    sub = ev[ev.type_name == "Substitution"].iloc[0]
    assert sub.player_name == "Nsue" and sub.substitution_replacement_name == "Ibán"
    pen = ev[(ev.type_name == "Shot") & (ev.period == 2)].iloc[0]
    assert pen.shot_type_name == "Penalty" and pen.shot_outcome_name == "Goal"
    head = ev[(ev.type_name == "Shot") & (ev.player_name == "Nsue")].iloc[0]
    assert head.shot_body_part_name == "Head" and head.shot_statsbomb_xg == pytest.approx(0.4)
    assert ev[ev.type_name == "Pass"].iloc[0].is_pass_cross == 1

    from src.metrics.match_facts import goals
    g = goals(ev)
    assert (sum(x["equipe"] == "Equatorial Guinea" for x in g), sum(x["equipe"] == "Congo" for x in g)) == (2, 1)


def test_own_goal_convention_is_fixed_by_official_score():
    from src.data_hub.sources.openplay import OpenPlayProvider

    df = pd.DataFrame([
        {"type_name": "Shot", "shot_outcome_name": "Goal", "team_name": "A", "period": 1, "team_id": 1},
        {"type_name": "Own Goal Against", "shot_outcome_name": None, "team_name": "A", "period": 2, "team_id": 1}])
    # placar oficial 2-0 para A: o gol contra só pode ser de B → arquivo usou a convenção oposta
    fixed = OpenPlayProvider.check_own_goals(df, "A", "B", 2, 0)
    assert fixed.iloc[1]["team_name"] == "B"
    # placar 1-1: o registro já está certo, nada muda
    assert OpenPlayProvider.check_own_goals(df, "A", "B", 1, 1).iloc[1]["team_name"] == "A"
    # nenhum dos dois bate: não mexe (não inventa)
    assert OpenPlayProvider.check_own_goals(df, "A", "B", 5, 5).iloc[1]["team_name"] == "A"


def test_converter_upgrade_clears_old_cached_events(db, tmp_path):
    from src.data_hub.sources.openplay import CONVERTER_VERSION, OpenPlayProvider

    d = tmp_path / "op"
    d.mkdir()
    _files(d)
    p = OpenPlayProvider(db, path=str(d))
    p.sync()
    mid = int(db.catalog("data_source = 'openplay'").set_index("source_match_id").loc["899244", "match_id"])
    db.save_events(mid, pd.DataFrame([{"event_id": "old", "match_id": mid, "index_num": 1, "period": 1, "minute": 0,
                                       "second": 0, "team_id": 1, "team_name": "x", "type_name": "Pass"}]))
    db.set_state("openplay", "converter", "1")
    msgs = []
    p.sync(progress=msgs.append)
    assert not db.has_events(mid) and db.get_state("openplay", "converter") == CONVERTER_VERSION
    assert any("refeitos" in m for m in msgs)
