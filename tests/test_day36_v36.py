"""v36: ESPN sem travar no HTTP 400, assistente respondendo o alvo, treino controlado, nota por atuação."""
import time
from datetime import date

import pytest

from src.data_hub.db import DataHubDB


@pytest.fixture()
def db(tmp_path):
    return DataHubDB(db_path=str(tmp_path / "hub.db"), schema_path="database/schema.sql")


class _Resp:
    def __init__(self, code, data=None):
        self.status_code, self._d, self.url = code, data, "u"

    def json(self):
        return self._d

    def raise_for_status(self):
        from src.data_hub import net
        if self.status_code >= 400:
            raise net.HTTPStatusError(self.status_code, self.url)


def test_http_400_is_not_retried_and_is_remembered(tmp_path, monkeypatch):
    from src.data_hub import http as H

    calls, sleeps = [], []
    monkeypatch.setattr(H.net, "get", lambda *a, **k: calls.append(1) or _Resp(400))
    monkeypatch.setattr(H.time, "sleep", lambda s: sleeps.append(s))
    c = H.PoliteHttpClient("t400", cache_dir=tmp_path, min_interval_s=0)
    with pytest.raises(H.ClientRefused):
        c.get_json("https://x/y", {"dates": "20190308-20190314"})
    assert len(calls) == 1 and not [s for s in sleeps if s >= 1]        # sem repetir com espera
    with pytest.raises(H.ClientRefused):
        c.get_json("https://x/y", {"dates": "20190308-20190314"})
    assert len(calls) == 1                                              # recusa lembrada: nem chama a rede


def test_espn_backfill_skips_refused_year_quickly(db, monkeypatch):
    from src.data_hub.http import ClientRefused
    from src.data_hub.sources.espn import EspnProvider

    p = EspnProvider(db, enabled=True)
    n = []

    def refuse(*a, **k):
        n.append(1)
        raise ClientRefused(400, "HTTP 400")
    p.scoreboard = refuse
    p._get = refuse
    msgs = []
    t0 = time.time()
    out = p.backfill(["bra.1"], since_year=2019, until=date(2020, 12, 31), progress=msgs.append)
    assert time.time() - t0 < 2
    assert out["errors"] == 0 and out["recusados"] == 12               # 6 meses por ano, depois pula o ano
    assert any("pulando para 2020" in m for m in msgs) and len(n) <= 12 * 3


# ------------------------------------------------------------------ assistente: perguntas com alvo
@pytest.fixture(scope="module")
def match():
    import json
    from pathlib import Path

    from src.data_hub.registry import DataLevel
    from src.data_hub.sources.wyscout import WyscoutConverter
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    payload = json.loads((Path(__file__).parent / "fixtures" / "wyscout_2058017_excerpt.json").read_text(encoding="utf-8"))
    df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(WyscoutConverter.convert(payload, 1)))
    return df, EventPreprocessor.build_possession_chains(df), {"match_id": 1, "data_level": DataLevel.EVENTS}


@pytest.fixture(autouse=True)
def _no_log(tmp_path, monkeypatch):
    import src.intelligence.dynamic_analyst as D

    monkeypatch.setattr(D, "MISSES_PATH", str(tmp_path / "misses.jsonl"))


def _ask(m, q, team="France"):
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst

    df, chains, meta = m
    return DynamicTacticalAnalyst(api_key="").answer(q, team, meta, df, chains, prefer_llm=False)


GENERIC = "Com a bola — "


def test_parser_routes_targeted_questions():
    from src.intelligence.query_understanding import QueryUnderstanding as Q

    r = ["Gerard Martín", "Kylian Mbappé", "Pedri"]
    t = ["Real Madrid", "Barcelona"]
    assert Q.parse("qual foi o jogador com mais xG gerado no jogo?", r, t).ranking_metric == "xg"
    assert Q.parse("quem foram os jogadores com maior perigo gerado?", r, t).ranking_metric == "perigo"
    assert Q.parse("o mbappe jogou esse jogo?", r, t).ask == "presence"
    assert Q.parse("o vini jr jogou esse jogo?", r, t).attribute == "vini jr"
    assert Q.parse("qual foi a maior falha do real madrid no jogo taticamente falando?", r, t).ask == "weakness"
    assert Q.parse("e sobre o gerard martin, ele teve quantos erros na partida?", r, t).ask == "errors"
    assert Q.parse("quem errou mais passes?", r, t).ranking_metric == "passes_errados"


def test_targeted_questions_never_fall_back_to_summary(match):
    for q in ["qual foi o jogador com mais xG gerado no jogo?", "quem foram os jogadores com maior perigo gerado?",
              "o mbappe jogou esse jogo?", "qual foi a maior falha da croacia no jogo taticamente falando?",
              "quantos erros o pogba teve?", "qual foi o ponto forte da franca?"]:
        md = _ask(match, q)["report_markdown"]
        assert GENERIC not in md, q


def test_presence_says_no_when_player_absent(match):
    md = _ask(match, "o messi jogou esse jogo?")["report_markdown"]
    assert md.startswith("**Não") and "messi" in md.lower()
    assert _ask(match, "o mbappe jogou esse jogo?")["report_markdown"].startswith("**Sim.** Kylian Mbappé")


def test_errors_are_split_by_type(match):
    r = _ask(match, "quantos erros o pogba teve?")
    b = r["evidence"]["blocos"]["erros::Paul Pogba"]
    assert b["total_de_erros"] == b["passes_errados"] + b["outras_perdas_de_bola"] + b["duelos_perdidos"] + \
        b["erros_que_deram_finalizacao_ao_rival"]
    assert "Passes errados" in r["report_markdown"] and r["hallucination_audit"]["is_grounded"]


def test_generic_questions_are_logged_for_learning(match):
    import src.intelligence.dynamic_analyst as D

    _ask(match, "qual o clima do vestiario?")
    _ask(match, "qual foi o lance mais bonito do jogo?")
    rows = D.read_generic_fallbacks()
    assert rows and rows[0]["pergunta"] == "qual foi o lance mais bonito do jogo?"


# ------------------------------------------------------------------ rede neural: experimentos controlados
def test_l2_gradient_matches_loss():
    import numpy as np

    from src.machine_learning.neural_net import NeuralNetwork

    rng = np.random.default_rng(0)
    X, y = rng.normal(size=(40, 5)), (rng.random(40) > 0.6).astype(float)
    net = NeuralNetwork([5, 4, 1], learning_rate=0.01, l2=0.1, seed=1)
    net.mu, net.sigma = np.zeros((1, 5)), np.ones((1, 5))
    chk = net.gradient_check(X, y)
    assert chk["max_relative_error"] < 1e-4                           # λ·W agora bate com (λ/2)·Σ‖W‖²


def test_experiments_follow_the_plan(tmp_path, monkeypatch):
    import src.machine_learning.model_registry as R

    assert R.EXPERIMENT_ORDER[0] == "B" and R.EXPERIMENTS["B"]["hidden"] == [32, 16]
    assert R.EXPERIMENTS["D"] == {"hidden": [64, 32, 16], "learning_rate": 0.0005, "l2": 0.001}
    data = R.DangerModelRegistry.dataset()
    keep = sorted(data["match_id"].unique())[:24]
    data = data[data["match_id"].isin(keep)]
    monkeypatch.setattr(R, "EXP_EPOCHS", 3)
    seen = []
    orig = R.DangerModelRegistry.train_round

    def spy(self, *a, **k):
        seen.append((a, k))
        return orig(self, *a, **k)
    monkeypatch.setattr(R.DangerModelRegistry, "train_round", spy)
    reg = R.DangerModelRegistry(root=tmp_path / "reg")
    reg.train_round(data, [32], 0.001, 2, 1e-4, 256, seed=1, origin="campeão de teste", cv_folds=0)
    out = reg.run_experiments(data, ["B"], attempts=2)
    assert len(out) == 2 and all(r["experimento"] == "B" for r in out)
    a, k = seen[-1]
    assert a[1] == [32, 16] and a[3] == 3 and a[5] == 256
    assert k["patience"] == 10 and k["warm_start"] is False and k["optimizer"] == "adam"
    assert reg.champion_info()["version"] == 1 or out[-1]["promoted"] or out[0]["promoted"]


def test_feature_report_and_class_balance():
    import src.machine_learning.model_registry as R

    data = R.DangerModelRegistry.dataset()
    rep = R.feature_report(data)
    assert len(rep) == 14 and set(rep.columns) >= {"variavel", "auc_sozinha", "alerta"}
    bal = R.class_balance(data)
    assert 0 < bal["positivas_pct"] < 100


# ------------------------------------------------------------------ rede de passes: só o XI
def test_pass_network_can_show_only_starters(match):
    from src.metrics.match_facts import lineup_split
    from src.networks.pass_network import PassingNetworkAnalyzer
    from src.ui import charts

    df = match[0].copy()
    team = "Croatia"
    starters, came = lineup_split(df, team)
    # cria uma substituição sintética para garantir o caso "quem entrou"
    import pandas as pd

    who = starters[0]
    sub = df[df["team_name"] == team].iloc[[-1]].copy()
    sub["type_name"], sub["player_name"], sub["substitution_replacement_name"] = "Substitution", who, "Reserva Teste"
    df = pd.concat([df, sub], ignore_index=True)
    starters, came = lineup_split(df, team)
    assert came == ["Reserva Teste"] and "Reserva Teste" not in starters and len(starters) <= 11
    net = PassingNetworkAnalyzer.build_pass_network(df, team, until_first_sub=False, players_only=starters)
    assert set(net["nodes_df"]["player_name"]) <= set(starters)
    fig = charts.pass_network(net, "t", subs={"Reserva Teste"})
    assert fig.data
