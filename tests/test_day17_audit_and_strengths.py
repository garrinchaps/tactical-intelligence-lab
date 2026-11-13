"""
Dia 17 — Correções de auditoria e página de Pontos Fortes e Fracos.

Cobre:
1. Transparência de dados simulados (renomeação + detecção + selo nos relatórios).
2. Guardião anti-alucinação: inteiros críticos e nomes de atletas.
3. Diferenças de porcentagem expressas em pontos percentuais (pp).
4. Carregamento offline do report_builder sem a biblioteca do Gemini.
5. Motor de Pontos Fortes e Fracos (percentis contextuais).
"""

import subprocess
import sys
import textwrap

import pandas as pd
import pytest

from src.ingestion.brazil_and_multi_source import (
    SIMULATED_DATA_BADGE,
    BrasileiraoAndMultiSourceProvider,
)
from src.metrics.strengths_weaknesses import StrengthsWeaknessesEngine
from src.metrics.xt_model import ExpectedThreatModel
from src.preprocessing.event_cleaner import EventPreprocessor
from src.reports.report_builder import NumericHallucinationGuard, TacticalReportBuilder


@pytest.fixture(scope="module")
def simulated_match():
    raw = BrasileiraoAndMultiSourceProvider.generate_simulated_match_events(
        "Cruzeiro", "Atlético-MG", 880001
    )
    df = ExpectedThreatModel.enrich_events_with_xt(
        EventPreprocessor.process_match_events(raw)
    )
    chains = EventPreprocessor.build_possession_chains(df)
    return df, chains


def test_simulated_generator_is_renamed_and_detected():
    assert hasattr(BrasileiraoAndMultiSourceProvider, "generate_simulated_match_events")
    assert not hasattr(BrasileiraoAndMultiSourceProvider, "generate_authentic_match_events")
    assert BrasileiraoAndMultiSourceProvider.is_simulated_match(880001) is True
    assert BrasileiraoAndMultiSourceProvider.is_simulated_match(3869685) is False
    assert BrasileiraoAndMultiSourceProvider.is_simulated_match("abc") is False


def test_report_starts_with_simulation_badge(simulated_match):
    df, chains = simulated_match
    evidence = TacticalReportBuilder.assemble_evidence_package(
        df, chains, "Cruzeiro", match_id=880001,
        user_query="Como anular o Matheus Pereira?", is_simulation=True,
    )
    md = TacticalReportBuilder.build_deterministic_markdown_report(evidence)
    assert SIMULATED_DATA_BADGE in md.splitlines()[0]
    # idempotente
    again = TacticalReportBuilder.prepend_simulation_badge(md, True)
    assert again.count(SIMULATED_DATA_BADGE) == md.count(SIMULATED_DATA_BADGE)


def test_deterministic_report_is_fully_grounded_and_uses_pp(simulated_match):
    df, chains = simulated_match
    evidence = TacticalReportBuilder.assemble_evidence_package(
        df, chains, "Cruzeiro", match_id=880001,
        user_query="Como anular o Matheus Pereira?", is_simulation=True,
    )
    md = TacticalReportBuilder.build_deterministic_markdown_report(evidence)
    audit = NumericHallucinationGuard.audit_text_numbers(md, evidence)
    assert audit["is_grounded"] is True, audit
    assert audit["verified_integers_count"] > 0
    assert " pp" in md
    assert "diferença de **" in md and "%**), tendo" not in md
    dossier = evidence["focused_player_deep_dive"][0]
    assert dossier["pressure_evidence_grade"] in {"FORTE", "MODERADA", "LIMITADA"}


def test_guard_catches_invented_integers_and_players(simulated_match):
    df, chains = simulated_match
    evidence = TacticalReportBuilder.assemble_evidence_package(
        df, chains, "Cruzeiro", match_id=880001, user_query="Análise geral"
    )
    roster = evidence["metadata"]["match_player_roster"]
    assert "Matheus Pereira" in roster

    fake_count = "O Matheus Pereira cometeu 977 perdas de posse."
    audit = NumericHallucinationGuard.audit_text_numbers(fake_count, evidence)
    assert audit["is_grounded"] is False
    assert any(x.startswith("977") for x in audit["unverified_integers"])

    fake_player = "A saída passa por Cristiano Ronaldo e por **Neymar** no corredor esquerdo."
    audit = NumericHallucinationGuard.audit_text_numbers(fake_player, evidence)
    assert "Cristiano Ronaldo" in audit["unverified_player_names"]
    assert "Neymar" in audit["unverified_player_names"]

    real_player = "Matheus Pereira e Lucas Romero aparecem no Corredor Central."
    audit = NumericHallucinationGuard.audit_text_numbers(real_player, evidence)
    assert audit["unverified_player_names"] == []


def test_report_builder_imports_without_gemini_library():
    """Simula ambiente sem google-genai: o import do report_builder não pode quebrar."""
    code = textwrap.dedent(
        """
        import builtins, sys
        real_import = builtins.__import__
        def blocked(name, *a, **k):
            if name == "google" or name.startswith("google."):
                raise ImportError("google-genai indisponível (teste offline)")
            return real_import(name, *a, **k)
        builtins.__import__ = blocked
        from src.reports.report_builder import TacticalReportBuilder
        from src.intelligence.llm_analyst import GenerativeTacticalAnalyst
        print("OK")
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd="."
    )
    assert out.returncode == 0, out.stderr
    assert "OK" in out.stdout


def _synthetic_baselines():
    players, teams = [], []
    for i in range(20):
        players.append(
            {
                "match_id": 1000 + i,
                "group": "Meia Ofensivo",
                "player_name": f"Ref {i}",
                "minutes": 90,
                "progressive_actions": 4.0 + i * 0.2,
                "line_breaking_passes": 3.0 + i * 0.2,
                "zone_14_entries": 1.0 + i * 0.1,
                "box_entries": 1.0 + i * 0.1,
                "xt_generated": 0.5 + i * 0.05,
                "xg": 0.05 + i * 0.01,
                "shots": 1.0 + i * 0.1,
                "defensive_actions": 10.0 + i,
                "ball_recoveries": 3.0 + i * 0.2,
                "counterpress_actions": 3.0 + i * 0.2,
                "turnovers": 8.0 + i * 0.2,
                "pass_accuracy_pct": 75.0 + i * 0.5,
                "press_retention_pct": 70.0 + i,
            }
        )
    return {"match_ids": list(range(1000, 1020)), "players": players, "teams": teams}


def test_strengths_and_weaknesses_engine(simulated_match):
    df, _ = simulated_match
    analysis = StrengthsWeaknessesEngine.analyze_player(
        df, "Matheus Pereira", _synthetic_baselines(), exclude_match_id=880001
    )
    assert analysis["group"] == "Meia Ofensivo"
    assert analysis["reference_players_n"] == 20
    all_items = analysis["strengths"] + analysis["weaknesses"] + analysis["neutral"]
    assert all_items, "deveria haver métricas comparáveis"
    for item in analysis["strengths"]:
        assert item["percentile"] >= 70
    for item in analysis["weaknesses"]:
        assert item["percentile"] <= 30
    # perdas de posse: menor é melhor
    turn = [d for d in all_items if d["metric"] == "turnovers"]
    assert turn and turn[0]["higher_is_better"] is False

    md = StrengthsWeaknessesEngine.build_interpretation_markdown(analysis, is_simulation=True)
    assert "Resumo executivo" in md
    evidence = {
        "metadata": {"match_player_roster": ["Matheus Pereira"], "target_team": "Cruzeiro",
                     "opponent_team": ""},
        "analysis": analysis,
    }
    assert NumericHallucinationGuard.audit_text_numbers(md, evidence)["is_grounded"] is True
