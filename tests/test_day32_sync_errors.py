"""Erros vistos no `--tudo` do usuário (14/11): cabeçalho com acento, openfootball em formato novo, parquet misto."""
import json

import pandas as pd


def test_headers_with_accents_become_ascii():
    from src.data_hub.net import ascii_headers

    h = ascii_headers({"User-Agent": "TacticalIntelligenceLab/1.0 (uso acadêmico — coleta)", "X-N": 3})
    assert h["User-Agent"] == "TacticalIntelligenceLab/1.0 (uso academico  coleta)" and h["X-N"] == "3"
    h["User-Agent"].encode("ascii")                                     # o httpx exige isso


def test_no_source_sends_accented_user_agent():
    import pathlib
    import re

    bad = [f"{p}:{i}" for p in pathlib.Path("src").rglob("*.py")
           for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
           if re.search(r'"User-Agent"\s*:\s*"[^"]*[^\x00-\x7f]', line)]
    assert not bad, bad


def test_openfootball_accepts_new_shapes(tmp_path):
    from src.data_hub.sources.openfootball import OpenFootballProvider

    d = tmp_path / "2025-26"
    d.mkdir()
    (d / "en.2.json").write_text(json.dumps([                          # só a lista de jogos, times como objeto
        {"round": "Matchday 1", "date": "2025-08-08", "team1": {"name": "Leeds"}, "team2": {"name": "Hull"},
         "score": {"ft": [2, 1]}, "goals1": [["x"]], "referees": ["Fulano"]},
        {"round": "Matchday 1", "date": "2025-08-09", "team1": "A", "team2": "B", "score": [0, 0]},
        {"round": "Matchday 2", "date": "2025-08-16", "team1": "C", "team2": "D"}]), encoding="utf-8")
    rows = OpenFootballProvider.parse_file(d / "en.2.json")
    recs = [r for r, _ in rows]
    assert [(r["home_team_name"], r["away_team_name"], r["home_score"]) for r in recs] == [("Leeds", "Hull", 2), ("A", "B", 0)]
    assert recs[0]["referee_name"] == "Fulano"


def test_lake_writes_mixed_text_columns(tmp_path):
    from src.data_lake.lake import parquet_safe

    df = pd.DataFrame({"inscritos": [12, "Javier Hernan Garcia", None], "n": [1, 2, 3], "x": [[1], {"a": 1}, None]})
    out = parquet_safe(df)
    assert out["inscritos"].tolist()[:2] == ["12", "Javier Hernan Garcia"] and pd.isna(out["inscritos"].iloc[2])
    assert out["n"].tolist() == [1, 2, 3]
    assert out["x"].tolist()[:2] == ["[1]", '{"a": 1}'] and df["inscritos"].tolist()[0] == 12   # original intacto
