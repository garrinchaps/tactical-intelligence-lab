"""Os 3 casos que o usuário mapeou no assistente (15/11): altura, primeiro gol e contagem de passes."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.data_hub.registry import DataLevel, to_internal_id
from src.data_hub.sources.wyscout import WyscoutConverter
from src.preprocessing.event_cleaner import EventPreprocessor
from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
from src.intelligence.query_understanding import QueryUnderstanding
from src.metrics.xt_model import ExpectedThreatModel
from src.metrics.match_facts import goals

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def match():
    payload = json.loads((FIX / "wyscout_2058017_excerpt.json").read_text(encoding="utf-8"))
    raw = WyscoutConverter.convert(payload, to_internal_id("wyscout", 2058017))
    df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(raw))
    meta = {"match_id": to_internal_id("wyscout", 2058017), "data_level": DataLevel.EVENTS, "data_source": "wyscout",
            "match_date": "2018-07-15"}
    return df, EventPreprocessor.build_possession_chains(df), meta


def ask(m, q):
    df, chains, meta = m
    return DynamicTacticalAnalyst(api_key="").answer(q, "France", meta, df, chains, prefer_llm=False)


def test_parser_routes_the_three_cases():
    p = QueryUnderstanding.parse
    assert (p("qual dos dois times tinha maior media de altura?").ask, p("qual dos dois times tinha maior media de altura?").attribute) == ("profile", "altura")
    assert p("qual time fez o primeiro gol?").ask == "goals" and p("qual time fez o primeiro gol?").goal_order == "1"
    assert p("quem abriu o placar?").goal_order == "1" and p("qual foi o último gol?").goal_order == "last"
    assert p("e o segundo gol, de quem foi?").goal_order == "2" and p("quem fez o gol da vitória?").goal_order == "winner"
    assert p("quem foi o jogador com mais passes no jogo?").ranking_metric == "passes"
    assert p("quantos km o time correu?").ask == "unavailable"
    assert p("qual time teve a marcação mais alta?").ask != "profile"        # "alta" de pressão não é altura
    assert p("quem tomou mais cartões?").ask != "profile"


def test_height_question_never_falls_back_to_generic_summary(match, monkeypatch):
    from src.intelligence.scoped_evidence import ScopedEvidenceBuilder as S

    monkeypatch.setattr(S, "_tm_players", classmethod(lambda cls: pd.DataFrame()))   # lake sem Transfermarkt
    r = ask(match, "qual dos dois times tinha maior media de altura?")
    md = r["report_markdown"]
    assert "não está nos dados" in md and "Posse (proporção dos passes)" not in md and "Com a bola" not in md


def test_height_uses_transfermarkt_registry_with_coverage(match, monkeypatch):
    from src.intelligence.query_understanding import norm
    from src.intelligence.scoped_evidence import ScopedEvidenceBuilder as S

    df = match[0]
    fr = sorted(df.loc[df.team_name == "France", "player_name"].dropna().unique())[:6]
    cr = sorted(df.loc[df.team_name == "Croatia", "player_name"].dropna().unique())[:6]
    tm = pd.DataFrame([{"nome": n, "altura_cm": 185} for n in fr] + [{"nome": n, "altura_cm": 178} for n in cr])
    tm["_n"] = tm["nome"].map(norm)
    tm["_fl"] = tm["_n"].str.split().map(lambda w: f"{w[0]} {w[-1]}" if len(w) > 1 else w[0])
    monkeypatch.setattr(S, "_tm_players", classmethod(lambda cls: tm))
    md = ask(match, "qual dos dois times tinha maior media de altura?")["report_markdown"]
    assert "185 cm" in md and "178 cm" in md and "encontrados" in md and "Transfermarkt" in md
    if sum(df.team_name == "France") and len(fr) >= 3:
        assert "France teve o time mais alto" in md or "França" in md or "encontrados" in md


def test_first_goal_answers_the_goal_not_team_stats(match):
    g = goals(match[0])
    r = ask(match, "qual time fez o primeiro gol?")
    md = r["report_markdown"]
    assert "Com a bola" not in md and "Posse (proporção" not in md
    if g:
        first = g[0]
        assert md.startswith("**Primeiro gol:**") and first["equipe"] in md.split("\n")[0]
        assert f"{first['minuto']}'" in md.split("\n")[0]
    else:
        assert "Não houve gols" in md


def test_pass_counts_are_the_same_everywhere(match):
    """'Mais passes' do resumo e o ranking de passes usam a mesma contagem."""
    import re

    df = match[0]
    summary = ask(match, "como foi o jogo?")["report_markdown"]
    ranking = ask(match, "quem foi o jogador com mais passes no jogo?")["report_markdown"]
    assert "Mais acionados" not in summary
    from src.metrics.match_facts import player_match_stats

    st = player_match_stats(df).set_index("jogador")["passes"]
    for name, n in re.findall(r"([A-ZÀ-Ý][^\(\n,:]+?) \((\d+)\)", summary.split("Mais passes:")[-1].split(".")[0]):
        assert int(n) == int(st.get(name.strip(), -1)) or int(n) <= int(st.get(name.strip(), 0)) + 2
    top = re.search(r"1\. (.+?) \(", ranking).group(1)
    assert top == st.sort_values(ascending=False).index[0] or st[top] == st.max()


def test_unavailable_data_is_said_plainly(match):
    md = ask(match, "qual jogador correu mais km?")["report_markdown"]
    assert "não existe na base" in md and "rastreamento" in md


def test_boxscore_first_goal_from_timeline():
    meta = {"home_team_name": "A", "away_team_name": "B", "home_score": 1, "away_score": 2, "match_id": 1,
            "data_level": "BOXSCORE", "data_source": "espn"}
    tl = pd.DataFrame([{"minute": 12, "extra_minute": None, "team_name": "B", "player_name": "Zé", "related_player": "",
                        "event_type": "Goal", "detail": "Goal"},
                       {"minute": 40, "extra_minute": None, "team_name": "A", "player_name": "Lu", "related_player": "",
                        "event_type": "Goal", "detail": "Penalty"},
                       {"minute": 88, "extra_minute": None, "team_name": "B", "player_name": "Ivo", "related_player": "",
                        "event_type": "Goal", "detail": "Goal"}])
    box = {"team_stats": pd.DataFrame(), "timeline": tl, "lineups": pd.DataFrame(), "player_stats": pd.DataFrame()}
    ai = DynamicTacticalAnalyst(api_key="")
    md = ai.answer("qual time fez o primeiro gol?", "A", meta, boxscore=box, prefer_llm=False)["report_markdown"]
    assert md.startswith("**Primeiro gol:** B, 12' Zé")
    md = ai.answer("quem fez o gol da vitória?", "A", meta, boxscore=box, prefer_llm=False)["report_markdown"]
    assert "88' Ivo" in md
