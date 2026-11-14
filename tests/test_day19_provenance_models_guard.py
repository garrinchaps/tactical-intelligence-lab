"""
Dia 19 — schema canônico com proveniência, conectores, arquivos de scout, catálogo YAML, bootstrap simulado,
rede neural do zero (gradient check), guard v2 com política de regeneração e protocolo de avaliação.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.canonical.provenance import MissingProvenanceError, ProvenanceRecord, ProvenanceRegistry
from src.canonical.schema import (CANONICAL_AGGREGATE_SCHEMA, CANONICAL_EVENT_SCHEMA, PROVENANCE_FIELDS, SchemaViolation,
                                  to_canonical_events, validate)
from src.connectors.api_connector import APIConnector
from src.connectors.catalog import CatalogError, CompetitionCatalog
from src.connectors.empirical_fallback import CI_TEXT, EmpiricalFallback
from src.connectors.scout_file_parser import ScoutFileError, ScoutFileParser
from src.connectors.statsbomb_connector import load_demo_events
from src.guard.policy import GuardPolicy
from src.machine_learning.danger_dataset import FEATURES
from src.machine_learning.neural_net import NeuralNetwork
from src.reports.report_builder import NumericHallucinationGuard

FINAL = 3869685
TEMPLATES = Path("data/templates")
FIX_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def final_internal() -> pd.DataFrame:
    from src.ingestion.statsbomb_loader import StatsBombDataLoader

    raw = load_demo_events(FINAL)
    assert raw is not None, "cache de demonstração da final ausente (data/demo)"
    return StatsBombDataLoader._parse_raw_events(None, raw, FINAL)


# ----------------------------------------------------------------- 1. schema e proveniência
def test_statsbomb_demo_maps_to_valid_canonical_schema(final_internal):
    can = to_canonical_events(final_internal, "StatsBomb Open Data", "StatsBombConnector", "crédito à StatsBomb",
                              "OFFICIAL", home_team="Argentina")
    assert list(can.columns) == [f.name for f in CANONICAL_EVENT_SCHEMA]
    assert validate(can) == []
    for f in PROVENANCE_FIELDS:
        assert can[f.name].notna().all(), f"campo de proveniência '{f.name}' com nulos"
    assert set(can["confidence_tier"]) == {"OFFICIAL"}
    assert can["x"].between(0, 120).all() and can["y"].between(0, 80).all()
    assert can["score_state"].iloc[-1] == "3-3"   # final 3x3 no tempo normal + prorrogação


def test_schema_rejects_out_of_domain_and_missing_provenance(final_internal):
    can = to_canonical_events(final_internal.head(200), "StatsBomb Open Data", "StatsBombConnector", "crédito", "OFFICIAL",
                              home_team="Argentina")
    bad = can.copy()
    bad.loc[bad.index[0], "x"] = 150.0
    with pytest.raises(SchemaViolation, match="'x'"):
        validate(bad)
    bad = can.copy()
    bad["source"] = None
    with pytest.raises(SchemaViolation, match="'source'"):
        validate(bad)


def test_api_connector_aggregates_follow_aggregate_schema():
    agg = APIConnector.boxscore_to_aggregates({"match_id": "1"}, {"team_stats": [
        {"team_name": "Flamengo", "stat_key": "shots_total", "value": 14},
        {"team_name": "Palmeiras", "stat_key": "shots_total", "value": 9}]})
    assert list(agg.columns) == [f.name for f in CANONICAL_AGGREGATE_SCHEMA]
    assert validate(agg, CANONICAL_AGGREGATE_SCHEMA) == []


def test_api_connector_without_key_is_disabled(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    assert APIConnector(api_key=None).enabled is False


def test_registry_require_fails_for_metric_without_origin():
    reg = ProvenanceRegistry()
    reg.register(ProvenanceRecord("ppda", "PPDA", 3.1, "StatsBomb", "StatsBombConnector", "crédito", "DERIVED", "PPDA"))
    assert reg.require("ppda").value == 3.1
    with pytest.raises(MissingProvenanceError):
        reg.require("field_tilt")


def test_strict_mode_blocks_ui_metric_without_provenance(monkeypatch):
    pytest.importorskip("streamlit")
    from src.ui import components

    monkeypatch.setenv("TIL_STRICT_PROVENANCE", "1")
    with pytest.raises(MissingProvenanceError):
        components.metric_card("PPDA", 3.1, None)


def test_simulated_record_carries_mandatory_label():
    rec = ProvenanceRecord("x", "Acerto de passe", 81.2, "pool", "EmpiricalFallback", "crédito", "SIMULATED", "bootstrap",
                           generator="EmpiricalBootstrap-v1", ci_low=80.1, ci_high=82.4)
    label = rec.simulated_label()
    assert "SIMULADOS" in label and "EmpiricalBootstrap-v1" in label and CI_TEXT in label


# ----------------------------------------------------------------- 2. arquivos de scout e catálogo
@pytest.mark.parametrize("name,kind", [("xt_zonas_modelo.csv", "xt_zonas"), ("matriz_passes_modelo.csv", "matriz_passes"),
                                       ("metricas_equipe_modelo.csv", "metricas_equipe")])
def test_scout_templates_parse_to_canonical(name, kind):
    out = ScoutFileParser.parse((TEMPLATES / name).read_bytes(), name)
    assert kind in out["tabelas"]
    canon = out["canonico"]
    assert validate(canon, CANONICAL_AGGREGATE_SCHEMA) == []
    assert set(canon["confidence_tier"]) == {"DERIVED"}


def test_scout_parser_error_cites_file_field_value_and_line():
    csv = "equipe,zona_x,zona_y,xt\nCruzeiro,1,1,0.01\nCruzeiro,2,1,abc\n".encode()
    with pytest.raises(ScoutFileError) as e:
        ScoutFileParser.parse(csv, "meu_xt.csv")
    msg = str(e.value)
    assert "meu_xt.csv" in msg and "'xt'" in msg and "abc" in msg and "linha" in msg


def test_scout_pass_matrix_builds_graph():
    out = ScoutFileParser.parse((TEMPLATES / "matriz_passes_modelo.csv").read_bytes(), "matriz_passes_modelo.csv")
    d = out["tabelas"]["matriz_passes"]
    net = ScoutFileParser.pass_network(d, d["equipe"].iloc[0])
    assert not net["table"].empty and {"grau_ponderado", "betweenness"} <= set(net["table"].columns)


def test_competition_catalog_loads_and_validates(tmp_path):
    cc = CompetitionCatalog.load()
    assert len(cc.to_frame()) >= 100 and len(cc.teams()) >= 300
    assert not cc.query("Brasil").empty or not cc.query("Brazil").empty
    bad = tmp_path / "bad.yaml"
    bad.write_text("competicoes:\n  - id: x\n    nome: Teste\n    temporada: '2024'\n    fonte: inexistente\n"
                   "    nivel_dado: EVENTS\n    licenca: '-'\n    times: []\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        CompetitionCatalog.load([bad])


# ----------------------------------------------------------------- 3. bootstrap empírico (SIMULATED + IC)
def test_empirical_fallback_returns_simulated_with_ci(final_internal):
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    proc = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(final_internal))
    pool = EmpiricalFallback.pool_rows_from_match(proc, FINAL, "Argentina")
    fb = EmpiricalFallback(pool, db_path=None)
    r = fb.estimate("pass_completion_pct", B=100, persist=False)
    assert r["confidence_tier"] == "SIMULATED" and r["B"] == 100 and r["ci_text"] == CI_TEXT
    assert r["ci_low"] <= r["value"] <= r["ci_high"]
    assert 60 < r["value"] < 95
    tiny = fb.estimate("xg_per_shot", zone="defensivo-esquerda", B=100, persist=False)
    assert tiny["value"] is None and "amostra insuficiente" in tiny["status"]


# ----------------------------------------------------------------- 4. rede neural do zero
def _toy(n=600, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 4))
    y = ((X[:, 0] * X[:, 1] + 0.5 * X[:, 2]) > 0).astype(int)
    return X, y


def test_gradient_check_matches_numerical_gradient():
    X, y = _toy(80)
    net = NeuralNetwork([4, 6, 3, 1], learning_rate=0.1, l2=1e-3, seed=1)
    net.fit(X, y, epochs=1, batch_size=32)          # padronização ajustada
    res = net.gradient_check(X[:30], y[:30])
    assert res["max_relative_error"] < 1e-5


def test_training_loss_decreases_and_learns_nonlinear_pattern():
    from sklearn.metrics import roc_auc_score

    X, y = _toy(1200)
    net = NeuralNetwork([4, 16, 8, 1], learning_rate=0.1, seed=3)
    net.fit(X[:900], y[:900], epochs=40, batch_size=64, X_val=X[900:], y_val=y[900:])
    h = net.history["train_loss"]
    assert h[-1] < 0.85 * h[0] and all(np.diff(h[:5]) < 0.05)
    assert roc_auc_score(y[900:], net.predict_proba(X[900:])) > 0.85


def test_neurons_expose_parents_children_and_roundtrip(tmp_path):
    net = NeuralNetwork([3, 4, 1], seed=0, feature_names=["a", "b", "c"])
    neurons = net.neurons()
    hidden = [n for n in neurons if n.layer == 1]
    assert len(hidden) == 4 and all(len(n.parents) == 3 and len(n.children) == 1 for n in hidden)
    out = [n for n in neurons if n.layer == 2][0]
    assert len(out.parents) == 4 and out.children == []
    X = np.random.default_rng(0).normal(size=(40, 3))
    net.fit(X, (X[:, 0] > 0).astype(int), epochs=2, batch_size=8)
    net2 = NeuralNetwork.load(net.save(tmp_path / "nn.npz"))
    assert np.allclose(net.predict_proba(X), net2.predict_proba(X))
    assert net2.history == net.history


# ----------------------------------------------------------------- 5. guard v2 + política
EVID = {"team": {"passes": 512, "pass_completion_pct": 84.6, "shots": 14, "ppda": 9.8},
        "players": [{"player_name": "Lionel Messi", "xt": 0.412}]}


def test_guard_blocks_invented_number_and_reports_rate():
    a = NumericHallucinationGuard.audit_text_numbers("A equipe trocou 512 passes, acertou 84,6% e teve PPDA de 7,3.", EVID)
    assert a["is_grounded"] is False
    assert "7,3" in " ".join(a["unverified_decimals"])
    assert a["numbers_total"] == 3 and a["untraceable_count"] == 1
    assert a["untraceable_rate"] == pytest.approx(1 / 3, abs=1e-3)


def test_guard_accepts_exact_and_simple_derivation():
    a = NumericHallucinationGuard.audit_text_numbers(
        "Foram 512 passes com 84,6% de acerto e 14 finalizações; Messi somou 0,41 de xT.", EVID)
    assert a["is_grounded"] is True and a["untraceable_count"] == 0


@pytest.mark.parametrize("texts,expected", [
    (["Foram 512 passes."], "APROVADO_1A"),
    (["Foram 999 passes.", "Foram 512 passes."], "APROVADO_REGENERADO"),
    (["Foram 999 passes.", "Foram 777 passes."], "DEGRADADO"),
])
def test_guard_policy_outcomes(texts, expected):
    calls = []

    def generate(extra):
        calls.append(extra)
        return texts[min(len(calls) - 1, len(texts) - 1)]

    pol = GuardPolicy(NumericHallucinationGuard.audit_text_numbers, None).run(
        generate, EVID, fallback_text="Foram 512 passes.", engine="falso")
    assert pol.outcome == expected
    if expected != "APROVADO_1A":
        assert calls[1] is not None                      # 2ª chamada com contexto restrito
    if expected == "DEGRADADO":
        assert pol.metrics.rate_before == 1.0 and pol.metrics.rate_after == 0.0
        assert "512" in pol.text


# ----------------------------------------------------------------- 6. protocolo de avaliação
def test_protocol_on_demo_sample_reports_baselines_and_marginal_gain():
    from src.evaluation.protocol import evaluate_danger

    d = pd.read_csv("data/demo/danger_sample_wc2022.csv.gz")
    keep = d["match_id"].drop_duplicates().head(12)
    rep = evaluate_danger(d[d["match_id"].isin(keep)], k=3, nn_epochs=3)
    a = rep["auc"]
    assert a["baseline0"]["media"] == 0.5
    assert 0.5 < a["logistica"]["media"] < 0.9
    assert {"xgboost", "rede_neural"} <= set(rep["ganhos"])
    for g in rep["ganhos"].values():
        assert "interpretacao" in g and "sobre_logistica" in g
    assert 0 < rep["prevalencia_positiva"] < 0.5
    assert all(f["partidas_val"] >= 1 for f in rep["folds"])
    assert set(FEATURES) <= set(d.columns)


def test_catalog_loads_without_pyyaml():
    """O leitor embutido reproduz o PyYAML no formato do catálogo (Python sem pacote pronto)."""
    from src.connectors.mini_yaml import safe_load

    for f in ("config/competitions.yaml", "config/competitions.local.example.yaml"):
        doc = safe_load(Path(f).read_text(encoding="utf-8"))
        assert isinstance(doc["competicoes"], list) and doc["competicoes"]
        for e in doc["competicoes"]:
            CompetitionCatalog._validate_entry(e, f)
    assert safe_load("a: [1, 'b c']\nd:\n  - x  # nota\n") == {"a": [1, "b c"], "d": ["x"]}


# ----------------------------------------------------------------- 7. fatos da partida, analista e novas fontes
def test_goals_scorers_minutes_assists_and_shootout(final_internal):
    from src.metrics.match_facts import goal_line, goals, shootout
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(final_internal))
    g = goals(df)
    assert [(x["minuto"], x["jogador"]) for x in g] == [
        (23, "Lionel Andrés Messi Cuccittini"), (36, "Ángel Fabián Di María Hernández"), (80, "Kylian Mbappé Lottin"),
        (81, "Kylian Mbappé Lottin"), (108, "Lionel Andrés Messi Cuccittini"), (118, "Kylian Mbappé Lottin")] or \
        [x["minuto"] for x in g] == [23, 36, 80, 81, 108, 118]
    assert g[0]["tipo"] == "pênalti" and "assist." in goal_line(g[1])
    assert shootout(df) == {"Argentina": 4, "France": 2}


def test_analyst_answers_goal_and_ranking_questions(final_internal):
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(final_internal))
    a = DynamicTacticalAnalyst(api_key="")
    meta = {"match_id": FINAL, "data_level": "EVENTS", "home_team_name": "Argentina", "away_team_name": "France"}
    r = a.answer("quem fez gol nessa partida?", "Argentina", meta, df, None, prefer_llm=False)
    assert "Gols de Argentina" in r["report_markdown"] and "pênaltis" in r["report_markdown"].lower()
    r = a.answer("quem foi o jogador que mais deu passes?", "Argentina", meta, df, None, prefer_llm=False)
    assert r["report_markdown"].startswith("**Passes") and r["hallucination_audit"]["untraceable_count"] == 0
    r = a.answer("o que a argentina fez para ganhar a partifda", "Argentina", meta, df, None, prefer_llm=False)
    assert "pênaltis" in r["report_markdown"] and r["scope"]["category"] != "off_topic"


def test_query_understanding_tolerates_typos_and_teams():
    from src.intelligence.query_understanding import QueryUnderstanding as Q

    assert Q.parse("o que o brasil fez para ganhar a partifda", [], ["Brazil", "England"]).in_scope
    assert Q.parse("a coxinha é melhor que o hambúrguer?", [], ["Brazil", "England"]).category == "off_topic"
    s = Q.parse("quem mais desarmou no segundo tempo", [], None)
    assert s.ask == "ranking" and s.ranking_metric == "desarmes" and s.period == 2
    assert Q.parse("quem teve mais posse de bola?", [], None).ask is None


def test_gemini_error_is_explained():
    from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst as D

    assert "inválida" in D.explain_error(RuntimeError("400 INVALID_ARGUMENT API key not valid. API_KEY_INVALID"))
    assert "cota" in D.explain_error(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert "modelo" in D.explain_error(RuntimeError("404 NOT_FOUND models/x"))


def test_gender_split():
    from src.data_hub.gender import gender_of

    assert gender_of({"competition_name": "FA Women's Super League"}) == "feminino"
    assert gender_of({"competition_name": "La Liga", "extra_json": '{"gender": "male"}'}) == "masculino"
    assert gender_of({"competition_name": "FIFA World Cup", "extra_json": '{"gender": "female"}'}) == "feminino"
    assert gender_of({"competition_name": "Campeonato Brasileiro Série A"}) == "masculino"


def test_fdcouk_parsers():
    from src.data_hub.sources.fdcouk import FootballDataCoUkProvider as F, season_code

    assert season_code(2024) == "2425" and season_code(1999) == "9900"
    rows = F.parse_main(pd.read_csv(FIX_DIR / "fdcouk" / "E0.csv"), "E0", 2024)
    rec, box = rows[0]
    assert rec["home_team_name"] == "Man United" and rec["home_score"] == 1 and rec["match_date"] == "2024-08-16"
    assert rec["data_level"] == "BOXSCORE" and rec["match_id"] >= 2_000_000_000
    shots = {s["team_name"]: s["value"] for s in box["team_stats"] if s["stat_key"] == "shots_total"}
    assert shots == {"Man United": 14.0, "Fulham": 10.0}
    from src.data_hub.registry import source_from_internal_id

    assert source_from_internal_id(rec["match_id"]) == "fdcouk"
    assert rows[0][0]["match_id"] == F.parse_main(pd.read_csv(FIX_DIR / "fdcouk" / "E0.csv"), "E0", 2024)[0][0]["match_id"]
    ex = F.parse_extra(pd.read_csv(FIX_DIR / "fdcouk" / "BRA.csv"), "BRA")
    assert ex[1]["home_team_name"] == "Flamengo" and ex[1]["data_level"] == "RESULT" and ex[1]["season_name"] == "2024"


def test_player_match_stats_and_team_stats(final_internal):
    from src.metrics.match_facts import per90, player_match_stats, team_match_stats
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(final_internal))
    s = player_match_stats(df)
    messi = s[s["jogador"].str.contains("Messi")].iloc[0]
    assert messi["gols"] == 2 and messi["minutos"] > 100 and messi["finalizacoes"] >= messi["finalizacoes_no_alvo"]
    assert (per90(s)["passes"] >= 0).all()
    t = team_match_stats(df, "Argentina")
    assert t["gols"] == 3 and 0 < t["share_passes_pct"] < 100 and t["finalizacoes"] > 0
