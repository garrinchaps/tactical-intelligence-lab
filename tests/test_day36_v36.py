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


def test_espn_refused_year_does_not_hang(db):
    import time as _t

    from src.data_hub.http import ClientRefused
    from src.data_hub.sources.espn import EspnProvider

    p = EspnProvider(db, enabled=True)

    def refuse(*a, **k):
        raise ClientRefused(400, "HTTP 400")
    p.season_events = refuse
    t0 = _t.time()
    out = p.backfill(["bra.1"], since_year=2019, until=date(2020, 12, 31))
    assert _t.time() - t0 < 2 and out["janelas_falhas"] == 2 and out["errors"] == 2     # 1 por ano, sem martelar


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


# ------------------------------------------------------------------ nota 0–10 por atuação
@pytest.fixture(scope="module")
def final_df():
    from src.connectors.statsbomb_connector import load_demo_events
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    raw = StatsBombDataLoader._parse_raw_events(None, load_demo_events(3869685), 3869685)
    return ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(raw))


def test_rating_is_fair_and_bounded(final_df):
    from src.metrics.player_rating import match_ratings

    r = match_ratings(final_df)
    ok = r["nota"].dropna()
    assert ok.between(3, 10).all() and 6.2 <= ok.median() <= 7.2
    top = r.iloc[0]["jogador"]
    assert top in ("Lionel Messi", "Kylian Mbappé")
    assert "Não identificado" not in set(r["jogador"])
    # quem jogou menos de 10 minutos não recebe nota
    assert r.loc[r["minutos"] < 10, "nota"].isna().all()
    # goleiro: defesas e gols sofridos saem das finalizações do rival
    gk = r[r["jogador"] == "Hugo Lloris"].iloc[0]
    assert gk["setor"] == "goleiro" and gk["gols_sofridos_goleiro"] == 3


def test_substitute_minutes_use_the_events_name(final_df):
    from src.metrics.match_facts import _minutes

    m = _minutes(final_df)
    assert m["Randal Muani"] < 100                                     # entrou aos 41' (nome completo na troca)


def test_errors_weigh_less_than_hits():
    from src.metrics.player_rating import rate_row

    base = {"minutos": 90, "posicao": "Center Midfield", "passes_certos": 50, "passes_errados": 0}
    worse = {**base, "passes_errados": 10}
    better = {**base, "passes_certos": 60}
    d_err = rate_row(base)["erros"] - rate_row(worse)["erros"]          # custo de 10 passes errados
    d_hit = rate_row(better)["acertos"] - rate_row(base)["acertos"]     # ganho de 10 passes certos
    assert 0 < d_err < d_hit


def test_average_rating_ignores_matches_without_rating():
    import pandas as pd

    from src.metrics.player_rating import average_rating

    a = average_rating(pd.DataFrame({"nota": [7.0, None, 8.0]}))
    assert a == {"media": 7.5, "jogos_com_nota": 2, "jogos_sem_nota": 1}


def test_club_page_respects_top_level_filter():
    import inspect

    import src.ui.pages.clubs as C

    src = inspect.getsource(C.render)
    assert "team_matches(names, include_score_only=None)" in src          # nível do topo, não "tudo analisável"


# ------------------------------------------------------------------ atletas duplicados
def test_unify_people_merges_same_athlete_and_keeps_homonyms_apart():
    import pandas as pd

    from src.data_lake.ids import player_core, unify_people

    rows = pd.DataFrame([
        {"nome": "Lionel Andrés Messi Cuccittini", "clube": "Argentina", "fonte": "eventos", "nascimento": ""},
        {"nome": "Lionel Messi", "clube": "Inter Miami", "fonte": "Transfermarkt", "nascimento": "1987-06-24"},
        {"nome": "L. Messi", "clube": "Barcelona", "fonte": "eventos", "nascimento": ""},
        {"nome": "Kylian Mbappé Lottin", "clube": "France", "fonte": "eventos", "nascimento": ""},
        {"nome": "Kylian Mbappé", "clube": "Real Madrid", "fonte": "Transfermarkt", "nascimento": "1998-12-20"},
        # homônimos: mesmo nome, nascimentos diferentes → não juntar
        {"nome": "Danilo", "clube": "Flamengo", "fonte": "Transfermarkt", "nascimento": "1991-07-15"},
        {"nome": "Danilo", "clube": "Botafogo", "fonte": "Transfermarkt", "nascimento": "2001-04-29"},
        # curto ambíguo: dois longos possíveis → não juntar
        {"nome": "Gabriel Silva", "clube": "A", "fonte": "Transfermarkt", "nascimento": ""},
        {"nome": "Gabriel Souza Silva", "clube": "B", "fonte": "eventos", "nascimento": ""},
        {"nome": "Gabriel Lima Silva", "clube": "C", "fonte": "eventos", "nascimento": ""},
    ])
    rows["core"] = rows["nome"].map(player_core)
    p = unify_people(rows).tolist()
    assert p[0] == p[1] == p[2]                                         # Messi: 3 grafias, 1 pessoa
    assert p[3] == p[4] and p[3] != p[0]
    assert p[5] != p[6]                                                 # dois Danilos diferentes
    assert len({p[7], p[8], p[9]}) == 3                                 # ambíguo: não junta


# ------------------------------------------------------------------ escalação: transferências e empréstimos
def test_apply_transfers_removes_departures_and_adds_arrivals():
    from datetime import date

    import pandas as pd

    from src.squad.planner import apply_transfers

    sq = pd.DataFrame([{"transfermarkt_id": 1, "nome": "Kaiki", "funcao": "Left-Back", "posicao": "Defender"},
                       {"transfermarkt_id": 2, "nome": "Titular Fixo", "funcao": "Centre-Back", "posicao": "Defender"},
                       {"transfermarkt_id": 3, "nome": "Emprestado", "funcao": "Centre-Forward", "posicao": "Attack"}])
    apps = pd.DataFrame([
        {"transfermarkt_id": 1, "clube_id": 10, "data": "2026-03-01", "nome": "Kaiki"},
        {"transfermarkt_id": 1, "clube_id": 99, "data": "2026-08-20", "nome": "Kaiki"},      # foi vendido
        {"transfermarkt_id": 2, "clube_id": 10, "data": "2026-11-01", "nome": "Titular Fixo"},
        {"transfermarkt_id": 3, "clube_id": 10, "data": "2026-05-01", "nome": "Emprestado"},
        {"transfermarkt_id": 3, "clube_id": 77, "data": "2026-10-01", "nome": "Emprestado"},  # emprestado
    ])
    own = pd.DataFrame([{"transfermarkt_id": 2, "clube_id": 10, "data": "2026-11-01", "nome": "Titular Fixo"},
                        {"transfermarkt_id": 5, "clube_id": 10, "data": "2026-10-20", "nome": "Reforço"}])   # chegou
    tm = pd.DataFrame([{"transfermarkt_id": 5, "nome": "Reforço", "funcao": "Central Midfield", "posicao": "Midfield",
                        "nascimento": "2000-01-01"}])
    out, ch = apply_transfers(sq, 10, own, apps, tm, ref=date(2026, 11, 15))
    assert set(out["nome"]) == {"Titular Fixo", "Reforço"}
    assert {(c["nome"], c["mudanca"]) for c in ch} == {("Kaiki", "saiu"), ("Emprestado", "saiu"), ("Reforço", "chegou")}


def test_profile_ignores_old_and_thin_matches():
    import pandas as pd

    from src.squad.planner import team_profile

    m = pd.DataFrame([{"match_id": i, "match_date": d, "home_team_name": "Nós", "away_team_name": "X", "home_score": 1,
                       "away_score": 0, "data_level": "BOXSCORE"} for i, d in
                      [(1, "2026-11-01"), (2, "2026-10-20"), (3, "2024-01-01")]])
    rich = ["shots_total", "shots_on_target", "fouls", "corners", "possession_pct"]
    s = pd.DataFrame([{"match_id": 1, "team_name": "Nós", "stat_key": k, "value": 10} for k in rich] +
                     [{"match_id": 2, "team_name": "Nós", "stat_key": "shots_total", "value": 99}] +     # dado ralo
                     [{"match_id": 3, "team_name": "Nós", "stat_key": k, "value": 50} for k in rich])    # antigo
    p = team_profile(m, s, ["Nós"], {}, 5)
    assert [g["match_id"] for g in p["jogos"]] == [1] and p["descartados_por_dado_incompleto"] == 1


def test_drag_pitch_html_and_tips():
    from src.squad.formations import FORMATIONS
    from src.ui.drag_pitch import html, pitch_tips

    xi = [{"jogador": f"J{i}", "nota": 70, "papel_pt": "x", "encaixe": 1} for i in range(11)]
    plan = {"explorar": [{"chave": "crosses_total", "acao": "cruzar", "rotulo": "Cruzamentos cedidos", "media": 20, "dif_pct": 40}],
            "neutralizar": [{"chave": "corners", "acao": "a", "rotulo": "Escanteios", "media": 7, "dif_pct": 30}],
            "nossos_fortes": [{"chave": "shots_total", "rotulo": "Finalizações", "media": 15, "dif_pct": 20}],
            "nossos_fracos": [{"chave": "xg", "rotulo": "xG cedido", "media": 1.6, "dif_pct": 25}]}
    tips = pitch_tips(plan)
    assert [t["marca"] for t in tips] == ["E1", "N1", "F1", "C1"] and all("%" in t["texto"] for t in tips)
    page = html("Time", "4-3-3", xi, [{"nome": "R1", "nota": 60}], tips)
    assert "%%DATA%%" not in page and all(f in page for f in FORMATIONS) and "localStorage" in page


def test_compare_player_cut():
    import pandas as pd

    from src.ui.pages.compare import player_cut

    pm = pd.DataFrame({"match_id": [1, 2, 3, 4, 5, 6, 7], "gols": [1] * 7})
    d = pd.DataFrame({"match_id": [1, 2, 3, 4, 5, 6, 7],
                      "match_date": ["2026-01-0%d" % i for i in range(1, 8)],
                      "season_name": ["2024/25"] * 3 + ["2025/26"] * 4})
    assert player_cut(pm, d, "Último jogo")["match_id"].tolist() == [7]
    assert len(player_cut(pm, d, "Últimos 5 jogos")) == 5
    assert set(player_cut(pm, d, "Temporada mais recente")["match_id"]) == {4, 5, 6, 7}


def test_on_field_has_eleven_at_any_minute(final_df):
    from src.metrics.match_facts import on_field

    for team in ("Argentina", "France"):
        for minute in (5, 45, 70, 100, 118):
            f = on_field(final_df, team, minute)
            assert len(f["jogadores"]) == 11, (team, minute, f)
    f = on_field(final_df, "France", 45)                                 # Dembélé e Giroud saíram aos 40/41'
    assert "Randal Muani" in f["jogadores"] and "Ousmane Dembélé" not in f["jogadores"]
    assert f["de"] <= 45 < f["ate"]


# ------------------------------------------------------------------ B3: vínculo jogador-clube
def test_tenure_loan_return_and_unknown():
    from datetime import date

    import pandas as pd

    from src.squad.tenure import active_on, build_tenures, classify_squad

    apps = pd.DataFrame([
        # Kaiki: Cruzeiro → emprestado (curto) → volta ao Cruzeiro em 2026
        {"transfermarkt_id": 1, "clube_id": 10, "data": "2025-02-01", "nome": "Kaiki"},
        {"transfermarkt_id": 1, "clube_id": 55, "data": "2025-08-01", "nome": "Kaiki"},
        {"transfermarkt_id": 1, "clube_id": 55, "data": "2026-01-10", "nome": "Kaiki"},
        {"transfermarkt_id": 1, "clube_id": 10, "data": "2026-08-01", "nome": "Kaiki"},
        {"transfermarkt_id": 3, "clube_id": 10, "data": "2026-10-01", "nome": "Titular"},
    ])
    # Rodri: transferência registrada do Barcelona B (20) para outro clube — não é do Barcelona
    tr = pd.DataFrame([{"transfermarkt_id": 2, "nome": "Rodri", "data": "2019-07-01", "de_clube_id": 20, "para_clube_id": 30},
                       {"transfermarkt_id": 2, "nome": "Rodri", "data": "2024-07-01", "de_clube_id": 30, "para_clube_id": 40}])
    ten = build_tenures(tr, apps)
    k = ten[ten["transfermarkt_id"] == "1"].sort_values("start_date")
    assert k["type"].tolist() == ["definitivo", "emprestimo", "retorno"]
    assert set(active_on(ten, 10, date(2026, 11, 15))["transfermarkt_id"]) == {"1", "3"}
    assert active_on(ten, 20, date(2026, 11, 15)).empty                  # Rodri fora
    sq = pd.DataFrame([{"transfermarkt_id": 1, "nome": "Kaiki"}, {"transfermarkt_id": 2, "nome": "Rodri"},
                       {"transfermarkt_id": 3, "nome": "Titular"}, {"transfermarkt_id": 9, "nome": "Sem informação"}])
    c = classify_squad(sq, ten, 10, apps, date(2026, 11, 15)).set_index("nome")
    assert c.loc["Kaiki", "situacao"] == "no elenco" and c.loc["Kaiki", "vinculo"] == "retorno"
    assert c.loc["Rodri", "situacao"] == "saiu"
    assert c.loc["Sem informação", "confidence_tier"] == "UNKNOWN" and c.loc["Sem informação", "situacao"] == "não confirmado"


# ------------------------------------------------------------------ B4: homônimos
def test_player_resolver_needs_more_than_the_name():
    import pandas as pd

    from src.data_hub.player_resolver import merge_match_rows, resolve

    idx = pd.DataFrame([
        {"nome": "Lionel Andrés Messi Cuccittini", "clube": "Argentina", "fonte": "eventos"},
        {"nome": "Lionel Andrés Messi Cuccittini", "clube": "Barcelona", "fonte": "eventos"},
        {"nome": "Lionel Messi", "clube": "Inter Miami", "fonte": "Transfermarkt", "nascimento": "1987-06-24",
         "nacionalidade": "Argentina"},
        {"nome": "L. Messi", "clube": "Barcelona", "fonte": "eventos"},
        {"nome": "Kylian Mbappé Lottin", "clube": "France", "fonte": "eventos"},
        {"nome": "Kylian Mbappé", "clube": "Real Madrid", "fonte": "Transfermarkt", "nascimento": "1998-12-20",
         "nacionalidade": "France"},
        # mesmo nome, nada que confirme: NÃO funde, vai para revisão
        {"nome": "Gabriel Souza", "clube": "Time A", "fonte": "eventos"},
        {"nome": "Gabriel Souza Lima", "clube": "Time B", "fonte": "eventos"},
        # homônimos com nascimentos diferentes
        {"nome": "Danilo", "clube": "Flamengo", "fonte": "Transfermarkt", "nascimento": "1991-07-15"},
        {"nome": "Danilo", "clube": "Botafogo", "fonte": "Transfermarkt", "nascimento": "2001-04-29"},
    ])
    p, review = resolve(idx)
    p = p.tolist()
    assert p[0] == p[1] == p[2] == p[3]                                  # Messi: seleção + clube + abreviado
    assert p[4] == p[5]
    assert p[6] != p[7] and set(review["a"]) >= {"Gabriel Souza"}       # só o nome: revisão, sem fusão
    assert p[8] != p[9]
    rows = pd.DataFrame([
        {"match_date": "2022-12-18", "home_team_name": "Argentina", "away_team_name": "France", "acoes": 120},
        {"match_date": "2022-12-19", "home_team_name": "Argentina", "away_team_name": "France", "acoes": 30},  # outra fonte
        {"match_date": "2022-12-13", "home_team_name": "Argentina", "away_team_name": "Croatia", "acoes": 90}])
    m = merge_match_rows(rows)
    assert len(m) == 2 and m["acoes"].max() == 120                      # mesma partida conta uma vez


# ------------------------------------------------------------------ C: notas
def test_c6_defender_not_below_wasteful_striker():
    from src.analytics.player_ratings import rate_row

    zagueiro = {"minutos": 90, "posicao": "Center Back", "finalizacoes": 0, "passes": 50, "passes_certos": 45,
                "passes_errados": 5, "perdas_de_posse": 5}
    atacante = {"minutos": 90, "posicao": "Center Forward", "finalizacoes": 2, "finalizacoes_no_alvo": 0, "passes": 20,
                "passes_certos": 12, "passes_errados": 8, "perdas_de_posse": 8}
    assert rate_row(zagueiro)["nota"] >= rate_row(atacante)["nota"]


def test_c2_peers_and_c4_minimum_sample():
    import pandas as pd

    from src.analytics.player_ratings import MIN_PEERS, normalize_by_peers, player_average

    r = pd.DataFrame({"competicao": ["Liga"] * MIN_PEERS + ["Copa"] * 3, "setor": ["defesa"] * (MIN_PEERS + 3),
                      "nota": [6.0] * MIN_PEERS + [8.0] * 3})
    n = normalize_by_peers(r)
    assert n.loc[n["competicao"] == "Liga", "nota"].eq(6.7).all()           # recentrado pelos pares
    assert n.loc[n["competicao"] == "Copa", "nota"].eq(8.0).all()           # poucos pares: não mexe
    avg = player_average(pd.DataFrame({"nota": [7.0, None], "minutos": [90, 5]}))
    assert avg["media"] is None and "amostra insuficiente" in avg["aviso"] and avg["minutos"] == 90
    avg = player_average(pd.DataFrame({"nota": [7.0, 8.0, 6.0], "minutos": [90, 90, 90]}))
    assert avg["media"] == 7.0 and avg["jogos_com_nota"] == 3


# ------------------------------------------------------------------ D/B6: profundidade e diagnóstico
def test_depth_levels(db):
    from src.data_hub.depth import depth_for_matches, depth_of
    from src.data_hub.registry import DataLevel

    assert depth_of("RESULT") == 0 and depth_of("BOXSCORE", True) == 1 and depth_of("BOXSCORE", True, True) == 2
    assert depth_of("EVENTS") == 3 and depth_of("EVENTS", has_tracking=True) == 4
    base = {"home_team_name": "A", "away_team_name": "B", "match_date": "2026-10-01", "home_score": 1, "away_score": 0,
            "competition_name": "L", "season_name": "2026", "status": "FT", "data_source": "espn"}
    db.upsert_matches([{**base, "match_id": 1, "data_level": DataLevel.RESULT},
                       {**base, "match_id": 2, "data_level": DataLevel.BOXSCORE},
                       {**base, "match_id": 3, "data_level": DataLevel.BOXSCORE}])
    db.save_boxscore(2, {"team_stats": [{"team_name": "A", "stat_key": "shots_total", "stat_label": "x", "value": 5}],
                         "lineups": [], "timeline": []})
    db.save_boxscore(3, {"team_stats": [{"team_name": "A", "stat_key": "shots_total", "stat_label": "x", "value": 5}],
                         "lineups": [{"team_name": "A", "player_name": "J", "shirt_number": "9", "position": "F",
                                      "is_starter": 1, "formation": "", "coach": ""}], "timeline": []})
    assert depth_for_matches(db, [1, 2, 3]) == {1: 0, 2: 1, 3: 2}


def test_rival_diagnosis_has_two_and_two_with_origin():
    import pandas as pd

    from src.squad.planner import rival_diagnosis, team_profile

    m = pd.DataFrame([{"match_id": i, "match_date": f"2026-10-0{i}", "home_team_name": "Rival", "away_team_name": f"X{i}",
                       "home_score": 1, "away_score": 1, "data_level": "EVENTS"} for i in range(1, 6)])
    vals = {"crosses_total": 30, "shots_total": 20, "pass_accuracy_pct": 70, "fouls": 20, "possession_pct": 50}
    s = pd.DataFrame([{"match_id": i, "team_name": "Rival", "stat_key": k, "value": v + (5 if i == 3 else 0)}
                      for i in range(1, 6) for k, v in vals.items()] +
                     [{"match_id": i, "team_name": f"X{i}", "stat_key": "shots_total", "value": 6} for i in range(1, 6)])
    base = {"crosses_total": 15, "shots_total": 12, "pass_accuracy_pct": 82, "fouls": 12, "possession_pct": 50}
    dg = rival_diagnosis(team_profile(m, s, ["Rival"], base, 5))
    assert dg["suficiente"] and len(dg["fortalezas"]) >= 2 and len(dg["vulnerabilidades"]) >= 2
    assert all("contra X" in d["origem"] for d in dg["fortalezas"] + dg["vulnerabilidades"])
    assert not any("zona 14" in d["texto"].lower() for d in dg["fortalezas"])
    assert rival_diagnosis({"n": 0, "a_favor": {}, "contra": {}})["aviso"].startswith("base insuficiente")


# ------------------------------------------------------------------ E: analista
def test_latency_is_measured_and_logged(match, tmp_path, monkeypatch):
    import src.intelligence.dynamic_analyst as D

    monkeypatch.setattr(D, "LATENCY_PATH", str(tmp_path / "lat.jsonl"))
    r = _ask(match, "quem fez mais passes?")
    assert isinstance(r["latency_s"], float) and r["latency_s"] < D.LATENCY_GOAL_S
    assert D.read_latency()[-1]["pergunta"] == "quem fez mais passes?"


def test_says_no_data_when_source_lacks_it(match):
    df = match[0]
    if (df["type_name"] == "Pressure").any():
        pytest.skip("fonte do teste registra pressões")
    md = _ask(match, "quem fez mais pressões?")["report_markdown"]
    assert "Não tenho esse dado" in md and "zero" in md


# ------------------------------------------------------------------ F: idioma e glossário
def test_i18n_and_glossary():
    from src.ui.glossary import GLOSSARY
    from src.ui.i18n import t

    assert t("Buscar", "en") == "Search" and t("Buscar", "es") == "Buscar" and t("Buscar", "pt") == "Buscar"
    assert t("frase sem tradução", "en") == "frase sem tradução"                 # nunca some
    assert "causalidade" in GLOSSARY["r"] and "−1 a +1" in GLOSSARY["r"]
    assert {"xT", "xG", "PPDA", "Field Tilt", "r"} <= set(GLOSSARY)


# ------------------------------------------------------------------ B7: divergência registrada
def test_divergence_is_recorded_never_averaged(db):
    from src.data_hub.consolidate import compare, record_divergences
    from src.data_hub.registry import DataLevel

    def m(mid, src):
        return {"match_id": mid, "home_team_name": "Flamengo", "away_team_name": "Palmeiras", "match_date": "2024-06-15",
                "home_score": 2, "away_score": 1, "competition_name": "x", "season_name": "2024", "status": "FT",
                "data_source": src, "data_level": DataLevel.BOXSCORE}
    db.upsert_matches([m(7_000_008_500, "brasileirao"), m(500_000_123, "espn")])
    s = lambda v: {"team_name": "Flamengo", "stat_key": "shots_total", "stat_label": "Finalizações", "value": v}
    db.save_boxscore(7_000_008_500, {"team_stats": [s(15)], "lineups": [], "timeline": []})
    db.save_boxscore(500_000_123, {"team_stats": [s(19)], "lineups": [], "timeline": []})
    assert record_divergences(db, 7_000_008_500) == 1
    with db.connect() as c:
        row = c.execute("SELECT fonte_primaria, valor, outras FROM source_divergences").fetchone()
    assert row[0] == "brasileirao" and row[1] == 15 and "espn 19" in row[2]          # primária vale; nada de 17
    assert compare(db, 7_000_008_500).iloc[0]["valor"] == 15


def test_crest_never_breaks_and_uses_local_cache(tmp_path, monkeypatch):
    import src.tools.cache_crests as C
    import src.ui.crests as K

    monkeypatch.setattr(C, "CREST_DIR", tmp_path)
    K._local.cache_clear()
    url = K.crest_url("Clube Inventado FC")
    assert url.startswith("data:image/svg+xml")                          # sem escudo: monograma, nunca quebra
    C.local_path("Cruzeiro").write_bytes(b"\x89PNG" + b"0" * 400)
    K._local.cache_clear()
    assert K.crest_url("Cruzeiro").startswith("data:image/png;base64,")   # cache local tem prioridade
    import pandas as pd

    cat = pd.DataFrame({"home_team_name": ["Cruzeiro", "Qarabag"], "away_team_name": ["Flamengo", "Sabah"],
                        "competition_name": ["Brasileirão Série A", "Azerbaijan Premier League"],
                        "match_date": ["2026-05-01", "2026-05-01"]})
    assert C.priority_teams(cat) == ["Cruzeiro", "Flamengo"]             # Azerbaijão fora da prioridade


# ------------------------------------------------------------------ B2: política de atualização
def test_sync_policy_incremental_live_freeze(db):
    from datetime import date, datetime, timedelta, timezone

    from src.data_hub import sync_policy as P

    assert P.kind("LIVE") == "ao_vivo" and P.kind("FT") == "encerrada" and P.kind("NS") == "futura"
    assert P.kind("FT", frozen=True) == "congelada"
    assert not P.fetch_stats("futura") and not P.fetch_stats("congelada") and P.fetch_stats("ao_vivo")
    today = date(2026, 11, 15)
    assert P.window(db, "espn", "bra.1", today) == (today - timedelta(days=3), today)            # sem histórico
    P.mark_synced(db, "espn", "bra.1", datetime(2026, 11, 10, tzinfo=timezone.utc))
    assert P.window(db, "espn", "bra.1", today) == (date(2026, 11, 8), today)                     # incremental
    P.mark_synced(db, "espn", "bra.1", datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert P.window(db, "espn", "bra.1", today)[0] == today - timedelta(days=30)                  # nunca a temporada
    P.freeze(db, [42])
    assert P.is_frozen(db, 42) and not P.is_frozen(db, 43)
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    P.mark_synced(db, "espn", "eng.1", now - timedelta(hours=1))
    P.mark_synced(db, "espn", "esp.1", now - timedelta(hours=4))
    assert P.due_fixtures(db, "espn", ["eng.1", "esp.1"], now) == ["esp.1"]                       # 3 h


def test_espn_live_tick_freezes_finished_match(db):
    from src.data_hub.sources.espn import EspnProvider

    p = EspnProvider(db, enabled=True)
    ev = lambda i, done, state: {"id": i, "date": "2026-11-15T19:00Z", "season": {"year": 2026}, "competitions": [{
        "status": {"type": {"completed": done, "state": state}},
        "competitors": [{"homeAway": "home", "score": "1", "team": {"displayName": "Cruzeiro"}},
                        {"homeAway": "away", "score": "0", "team": {"displayName": "Atlético-MG"}}]}]}
    p._get = lambda *a, **k: {"events": [ev(1, False, "in"), ev(2, True, "post"), ev(3, False, "pre")]}
    ingested = []

    def fake_ingest(mid):
        ingested.append(mid)
        db.save_boxscore(mid, {"team_stats": [{"team_name": "Cruzeiro", "stat_key": "shots_total", "value": 9}],
                               "lineups": [], "timeline": []})
        from src.data_hub import sync_policy as P
        P.freeze(db, [mid])
    p.ingest_event = fake_ingest
    out = p.live_tick(["bra.1"])
    assert out["ao_vivo"] == 1 and out["encerrados"] == 1 and ingested == [500_000_002]          # fixture (pre) ignorada
    assert db.get_match(500_000_001)["status"] == "LIVE"
    p.live_tick(["bra.1"])
    assert ingested == [500_000_002]                                                            # congelado: não repete


# ------------------------------------------------------------------ G: painel de fontes
def test_source_health_and_background_jobs(db):
    import time as _t

    from src.data_hub import health
    from src.data_hub.registry import DataLevel

    base = {"home_team_name": "A", "away_team_name": "B", "match_date": "2026-10-01", "home_score": 1, "away_score": 0,
            "competition_name": "L", "season_name": "2026", "status": "FT"}
    db.upsert_matches([{**base, "match_id": 500_000_001, "data_source": "espn", "data_level": DataLevel.BOXSCORE},
                       {**base, "match_id": 100_000_001, "data_source": "api_football", "data_level": DataLevel.RESULT}])
    with db.connect() as c:
        c.execute("INSERT INTO sync_runs (source, started_at, finished_at, status, message) VALUES "
                  "('espn', datetime('now'), datetime('now'), 'OK', '')")
        c.execute("INSERT INTO sync_runs (source, started_at, finished_at, status, message) VALUES "
                  "('api_football', datetime('now'), datetime('now'), 'ERRO', 'Cota diária esgotada')")
    db.register_api_call("api_football", 37)
    h = health.source_health(db).set_index("fonte")
    assert h.loc["espn", "status"].startswith("✅") and h.loc["espn", "com estatísticas"] == 1
    assert h.loc["api_football", "status"].startswith("⚠️") and "Cota" in h.loc["api_football", "erro mais recente"]
    assert h.loc["api_football", "cota hoje"] == "37/100"
    assert health.start_job("t", lambda say: (_t.sleep(0.3), say("ok"))) is True
    assert health.start_job("t", lambda say: None) is False                         # não duplica, não trava
    _t.sleep(0.6)
    assert not health.jobs()["t"]["running"] and health.jobs()["t"]["log"] == ["ok"]


# ------------------------------------------------------------------ A5/H1: filtro de nível vai na consulta ao banco
def test_level_filter_goes_into_the_sql(monkeypatch):
    import src.ui.context as C

    seen = {}
    monkeypatch.setattr(C, "_catalog_cached", lambda version, where, params: seen.setdefault("where", where))

    class FakeFinder:
        only_real = True
        levels = None
        only_analyzable = True

    class FakeDB:
        def stable_version(self):
            return "v"

    class FakeSvc:
        finder, db = FakeFinder(), FakeDB()
    monkeypatch.setattr(C, "get_service", lambda: FakeSvc())
    monkeypatch.setattr(C, "chosen_levels", lambda: ("EVENTS",))
    monkeypatch.setattr(C, "only_real", lambda: True)
    C.cached_catalog()
    w = seen["where"]
    assert "data_level IN ('EVENTS'" in w and "BOXSCORE" not in w and "'RESULT'" not in w


def test_guard_count_never_derives_from_a_decimal():
    from src.reports.report_builder import NumericHallucinationGuard as G

    ev = {"metadata": {"match_player_roster": ["Matheus Pereira"]},
          "blocos": {"x": {"eventos": 948, "xt": 39.23, "passes": 51}}}
    assert not G.audit_text_numbers("O Matheus Pereira cometeu 987 perdas de posse.", ev)["is_grounded"]  # 948 + 39,23
    assert G.audit_text_numbers("Foram 999 ações no total.", ev)["is_grounded"]                         # 948 + 51


# ------------------------------------------------------------------ rodada 3: perguntas táticas reais do usuário
TACTICAL_QS = [
    ("como eu poderia fazer para explorar mais as dificuldades defensivas da frança?", "attack_plan", "explorar a defesa"),
    ("como eu poderia anular o harry kane nessa partida?", "plan", "não está nesta partida"),
    ("como o messi foi? ele fez gol?", None, "Sim, Lionel Messi marcou"),
    ("Em quais corredores a França conseguiu progredir com mais facilidade: lateral, central ou meio-espaço?", "corridors", "Por onde"),
    ("A Argentina sofreu mais com bolas nas costas da defesa, infiltrações entre os zagueiros ou jogadas pelos lados?",
     "conceded_how", "Como Argentina sofreu"),
    ("Quais defensores argentinos tiveram maior participação nos erros que originaram situações perigosas?", "ranking", "Erros dos defensores"),
    ("Como a França explorou os espaços deixados entre a linha defensiva e os meio-campistas argentinos?", "between_lines", "entre as linhas"),
    ("A França teve menos posse mas marcou três. O que explica essa diferença de eficiência?", "efficiency", "Eficiência"),
    ("Em quais momentos da partida a França conseguiu quebrar a organização defensiva argentina?", "moments", "Momentos do jogo"),
    ("Identifique os padrões de movimentação que antecederam os gols franceses.", "goal_buildup", "Como nasceram os gols"),
    ("Construa um diagnóstico individual dos defensores argentinos, apontando vulnerabilidades e possíveis correções.",
     "defenders_diag", "Diagnóstico individual"),
    ("Identifique quais combinações de jogadores produziram maior progressão territorial e perigo ofensivo.", "combinations", "Duplas"),
    ("Compare os comportamentos ofensivos de Messi e Di María nessa partida.", None, "Lado a lado"),
]


@pytest.mark.parametrize("q,ask,needle", TACTICAL_QS)
def test_tactical_questions_have_own_answer(final_df, q, ask, needle):
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
    from src.preprocessing.event_cleaner import EventPreprocessor

    meta = {"match_id": 3869685, "data_level": "EVENTS", "home_team_name": "Argentina", "away_team_name": "France"}
    r = DynamicTacticalAnalyst(api_key="").answer(q, "Argentina", meta, final_df, EventPreprocessor.build_possession_chains(final_df),
                                                  prefer_llm=False)
    md = r["report_markdown"]
    assert r["scope"]["ask"] == ask and needle in md, md[:300]
    assert not (r["evidence"] or {}).get("escopo", {}).get("resumo_generico")
    assert "Com a bola — " not in md                                     # sem despejar o bloco do time
    assert r["hallucination_audit"]["is_grounded"]


# ------------------------------------------------------------------ escalação com dados reais recentes
def test_matchday_probable_xi_uses_recent_lineups_and_excludes_injured(db):
    import json as _j

    from src.data_hub.registry import DataLevel
    from src.squad import matchday as M

    xi_pos = [("Goleiro", "G"), ("LatEsq", "LB"), ("Zag1", "CD-L"), ("Zag2", "CD-R"), ("LatDir", "RB"), ("Vol1", "DM"),
              ("Vol2", "CM-L"), ("Meia", "AM"), ("PontaE", "AM-L"), ("PontaD", "AM-R"), ("Centroavante", "F")]
    recs, n = [], 6
    for i in range(n):
        mid = 500_100_000 + i
        recs.append({"match_id": mid, "home_team_name": "Cruzeiro", "away_team_name": f"R{i}", "match_date": f"2026-10-{10 + i}",
                     "home_score": 1, "away_score": 0, "competition_name": "Brasileirão", "season_name": "2026",
                     "status": "FT", "data_source": "espn", "data_level": DataLevel.BOXSCORE})
    db.upsert_matches(recs)
    for i in range(n):
        mid = 500_100_000 + i
        lu = [{"team_name": "Cruzeiro", "player_name": p, "shirt_number": "", "position": pos, "is_starter": 1,
               "formation": "4-2-3-1", "coach": ""} for p, pos in xi_pos]
        lu.append({"team_name": "Cruzeiro", "player_name": "Reserva", "shirt_number": "", "position": "SUB", "is_starter": 0,
                   "formation": "4-2-3-1", "coach": ""})
        ps = [{"team_name": "Cruzeiro", "player_name": "Centroavante", "position": "F", "minutes": None, "rating": None,
               "stats": {"totalGoals": 1, "goalAssists": 0}}]
        db.save_boxscore(mid, {"team_stats": [], "lineups": lu, "timeline": [], "player_stats": ps})
    with db.connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS espn_rosters (team_id INTEGER, team TEXT, league TEXT, athlete_id INTEGER, "
                  "name TEXT, birth TEXT, citizenship TEXT, position TEXT, jersey TEXT, status TEXT, injuries TEXT, "
                  "fetched_at TEXT, PRIMARY KEY (team_id, athlete_id))")
        rows = [(1, "Cruzeiro", "bra.1", k, p, "2000-01-01", "Brazil", pos, "", "Active",
                 _j.dumps([{"status": "Out"}]) if p == "PontaD" else "[]", "2026-11-16") for k, (p, pos) in enumerate(xi_pos)]
        rows.append((1, "Cruzeiro", "bra.1", 99, "Reserva", "2001-01-01", "Brazil", "M", "", "Active", "[]", "2026-11-16"))
        c.executemany("INSERT INTO espn_rosters VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    info = M.player_table(db, ["Cruzeiro"], n=10)
    assert info["formacao"] == "4-2-3-1" and len(info["jogos"]) == n
    pl = info["jogadores"].set_index("nome")
    assert pl.loc["Centroavante", "gols"] == n and pl.loc["PontaD", "indisponivel"]
    xi, form = M.xi_for(info, None, "provavel")
    names = {p["jogador"] for p in xi}
    assert form == "4-2-3-1" and "PontaD" not in names and "Centroavante" in names          # lesionado fora
    st = next(p for p in xi if p["jogador"] == "Centroavante")
    assert any("5 dos últimos 5 como titular" in r for r in st["porque"]) and any("gol" in r for r in st["porque"])
    # só a vaga do lesionado (sem outro ponta no elenco) precisa de adaptação; o resto na posição de origem
    assert sum((p["encaixe"] or 0) >= 0.85 for p in xi if p["jogador"]) >= 10


def test_key_starter_who_missed_last_game_stays_probable():
    import pandas as pd

    from src.squad import matchday as M

    base = dict(lado="", setor="meio", jogos_temporada=10, jogos_relacionado=10, gols_ult5=0, assist_ult5=0,
                finalizacoes=0, amarelos=0, indisponivel="", no_elenco_atual=True, idade=28, valor=None, nota_base="")
    rows = [dict(base, nome="Matheus Pereira", papel="AM", titular_temporada=9, titular_ult5=4, titular_ultimos=9,
                 comecou_ultimo=False, gols=5, assistencias=6, posicoes={"AM": 9}, qualidade=9.0, fase=7.0),
            dict(base, nome="Reserva Meia", papel="AM", titular_temporada=2, titular_ult5=1, titular_ultimos=2,
                 comecou_ultimo=True, gols=0, assistencias=0, posicoes={"AM": 2}, qualidade=2.0, fase=3.0),
            dict(base, nome="Zagueiro Bom", papel="CB", titular_temporada=10, titular_ult5=5, titular_ultimos=10,
                 comecou_ultimo=True, gols=0, assistencias=0, posicoes={"CB": 10}, qualidade=8.0, fase=8.0)]
    df = pd.DataFrame(rows)
    df["prob_titular"] = [round(100 * (0.5 * r.titular_temporada / 10 + 0.35 * r.titular_ult5 / 5 + 0.15 * r.comecou_ultimo))
                          for r in df.itertuples()]
    xi, _ = M.xi_for({"jogadores": df, "jogos": list(range(10)), "formacao": "4-2-3-1"}, "4-2-3-1", "provavel")
    am = next(p for p in xi if p["papel"] == "AM")
    assert am["jogador"] == "Matheus Pereira"                                        # não perde a vaga por 1 jogo
    st_ = next(p for p in xi if p["papel"] == "ST")
    assert st_["jogador"] != "Zagueiro Bom"                                          # zagueiro não vira centroavante
