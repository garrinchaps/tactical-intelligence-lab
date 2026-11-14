"""v27: cobertura honesta, validação de domínio, duplicatas SHA-256 e restrições de dependências."""
import re
from pathlib import Path

import pandas as pd
import pytest

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


def _m(mid, src, lvl, h="A", a="B", comp="Liga X", season="2024/25", d="2024-09-01"):
    return {"match_id": mid, "home_team_name": h, "away_team_name": a, "match_date": d, "home_score": 1, "away_score": 0,
            "competition_name": comp, "season_name": season, "country_name": "", "status": "FT",
            "data_source": src, "data_level": lvl}


def test_coverage_counts_levels_and_flags_gaps(db, tmp_path):
    from src.data_hub.coverage import collect, render, summarize

    db.upsert_matches([_m(2_000_000_001, "fdcouk", DataLevel.BOXSCORE), _m(2_000_000_002, "fdcouk", DataLevel.BOXSCORE, h="C"),
                       _m(3_000_000_001, "openfootball", DataLevel.RESULT, comp="Liga Y")])
    db.save_boxscore(2_000_000_001, {"team_stats": [{"team_name": "A", "stat_key": "shots_total", "stat_label": "x", "value": 9}],
                                     "lineups": [], "timeline": []})
    data = collect(str(db.db_path))
    s = summarize(data)
    row = s["comp"].set_index("competição").loc["Liga X"]
    assert row["ESTATÍSTICAS"] == 2 and row["SÓ PLACAR"] == 0
    assert "posse" in row["estatísticas ausentes"] and "chutes" not in row["estatísticas ausentes"]
    assert s["comp"].set_index("competição").loc["Liga Y", "estatísticas ausentes"] == "n/a"
    inc = s["inconsistencias"]                                 # 2_000_000_002 é BOXSCORE sem números
    assert len(inc) == 1 and int(inc.iloc[0]["partidas"]) == 1
    md = render(data)
    assert "## Por competição e temporada" in md and f"{len(data['rows'])} partidas reais" in md
    assert db.reconcile_levels() == 1 and db.get_match(2_000_000_002)["data_level"] == DataLevel.RESULT


def test_coverage_on_empty_db(tmp_path):
    import sqlite3

    from src.data_hub.coverage import collect, render

    p = tmp_path / "vazio.db"
    con = sqlite3.connect(str(p))
    con.executescript(Path("database/schema.sql").read_text(encoding="utf-8"))
    con.executescript("CREATE TABLE IF NOT EXISTS match_team_stats (match_id, team_name, stat_key, stat_label, value, display_value);")
    con.close()
    assert "base está vazia" in render(collect(str(p)))


def test_project_never_imports_pyyaml_or_bs4():
    pat = re.compile(r"^\s*(import|from)\s+(yaml|bs4)\b", re.M)
    offenders = [str(p.relative_to(ROOT)) for p in list((ROOT / "src").rglob("*.py")) + [ROOT / "app.py"]
                 if pat.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "pyyaml" not in req and "beautifulsoup" not in req and "bs4" not in req


def test_backup_copies_data_and_sqlite(tmp_path):
    import sqlite3

    from src.tools.backup_local import backup

    (tmp_path / "data" / "x").mkdir(parents=True)
    (tmp_path / "data" / "x" / "f.txt").write_text("ok", encoding="utf-8")
    (tmp_path / "database").mkdir()
    c = sqlite3.connect(str(tmp_path / "database" / "t.db"))
    c.execute("CREATE TABLE a(x)"); c.execute("INSERT INTO a VALUES (7)"); c.commit(); c.close()
    d = backup(root=tmp_path)
    assert (d / "data" / "x" / "f.txt").read_text(encoding="utf-8") == "ok"
    assert sqlite3.connect(str(d / "database" / "t.db")).execute("SELECT x FROM a").fetchone() == (7,)
