"""
Testes Automatizados do Dia 10: Validação de Geração de Relatórios Técnicos,
Roteador de Perguntas em Linguagem Natural e Guardrail Anti-Alucinação Numérica.
"""

from pathlib import Path
import pandas as pd
import pytest
from src.preprocessing.event_cleaner import EventPreprocessor
from src.reports.report_builder import (
    NumericHallucinationGuard,
    QueryIntentRouter,
    TacticalReportBuilder,
)
from src.intelligence.llm_analyst import GenerativeTacticalAnalyst


def test_query_intent_router_classifications():
    """Verifica se diferentes comandos em linguagem natural são roteados para o módulo correto."""
    assert (
        QueryIntentRouter.detect_focus("Analise toda a organização defensiva desta equipe.")
        == "DEFENSIVE_VULNERABILITIES"
    )
    assert (
        QueryIntentRouter.detect_focus("Como devemos pressionar a saída de bola?")
        == "PRESSING_AND_BUILDUP"
    )
    assert (
        QueryIntentRouter.detect_focus("Sugira uma substituição para melhorar a construção.")
        == "SUBSTITUTIONS_AND_SQUAD"
    )
    assert (
        QueryIntentRouter.detect_focus("Monte um plano de jogo completo para enfrentar essa equipe.")
        == "COMPLETE_REPORT"
    )


def test_report_generation_and_anti_hallucination_guard(tmp_path: Path):
    """
    Garante que:
    1. O relatório gerado a partir dos dados reais/sintéticos tem 0 números inventados (is_grounded=True).
    2. Se um texto contiver um percentual fictício (ex: 99.87% ou 58.62%) que não está nos dados,
       o NumericHallucinationGuard detecta a alucinação imediatamente.
    """
    rows = []
    for i in range(20):
        rows.append(
            {
                "event_id": f"r_{i}",
                "match_id": 1010,
                "period": 1,
                "index_num": i + 1,
                "minute": 5 + i,
                "second": 0,
                "possession": 1 + (i // 5),
                "possession_team_name": "Equipe Alfa" if i % 2 == 0 else "Equipe Beta",
                "team_name": "Equipe Alfa" if i % 2 == 0 else "Equipe Beta",
                "player_name": f"Jogador {i % 5}",
                "pass_recipient_name": f"Jogador {(i + 1) % 5}",
                "position_name": "Center Midfield",
                "type_name": "Pass",
                "pass_outcome_name": None,
                "x": 35.0 + i * 2.0,
                "y": 25.0 + i * 1.5,
                "end_x": 48.0 + i * 2.0,
                "end_y": 30.0 + i * 1.5,
                "under_pressure": 0,
            }
        )

    df_enriched = EventPreprocessor.process_match_events(pd.DataFrame(rows))
    df_chains = EventPreprocessor.build_possession_chains(df_enriched)

    evidence = TacticalReportBuilder.assemble_evidence_package(
        df_events=df_enriched,
        df_chains=df_chains,
        target_team="Equipe Alfa",
        match_id=1010,
        user_query="Como explorar os espaços defensivos?",
    )

    analyst = GenerativeTacticalAnalyst(api_key=None)  # Força motor local determinístico
    res = analyst.generate_tactical_report(evidence, prefer_llm=False)

    assert res["engine_used"] == "LOCAL_DETERMINISTIC_ENGINE"
    assert res["hallucination_audit"]["is_grounded"] is True
    assert "RELATÓRIO DE INTELIGÊNCIA TÁTICA" in res["report_markdown"]

    # Testa exportação Markdown e HTML
    out_files = TacticalReportBuilder.export_report_files(
        res["report_markdown"], output_prefix=str(tmp_path / "laudo_alfa")
    )
    assert Path(out_files["markdown_path"]).exists()
    assert Path(out_files["html_path"]).exists()

    # Simula uma alucinação numérica proposital (ex: percentual fictício 58.62% e 97.43%)
    fake_hallucinated_text = (
        "Em 58,62% das situações observadas e 97.43% dos cruzamentos, houve falha."
    )
    fake_audit = NumericHallucinationGuard.audit_text_numbers(
        fake_hallucinated_text, evidence
    )
    assert fake_audit["is_grounded"] is False
    assert len(fake_audit["unverified_decimals"]) == 2