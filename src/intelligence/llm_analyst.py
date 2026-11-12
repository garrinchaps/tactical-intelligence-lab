"""
Módulo de Inteligência Generativa Condicionada por Evidências e Alinhada ao Comando (Camada 6.4)
Conecta ao Google Gemini (gratuito via google-genai) priorizando a resposta cirúrgica
ao `user_query` (incluindo dossiê de jogadores específicos) e fallback determinístico offline.
"""

import json
import os
from typing import Any, Dict, Optional
from dotenv import load_dotenv

from src.reports.report_builder import (
    NumericHallucinationGuard,
    TacticalReportBuilder,
)

load_dotenv()


class GenerativeTacticalAnalyst:
    """
    Orquestrador do Analista Virtual de Inteligência Tática.
    Garante alinhamento semântico estrito à pergunta do usuário (`user_query`)
    e validação matemática anti-alucinação.
    """

    SYSTEM_INSTRUCTION = """Você é o Analista Chefe de Desempenho e Inteligência Tática do sistema TACTICAL INTELLIGENCE LAB.
Sua missão é responder DIRETAMENTE, CIRURGICAMENTE e COM PROFUNDIDADE TÁTICA à pergunta específica do usuário (`user_query`), utilizando exclusivamente as evidências matemáticas fornecidas.

REGRAS OBRIGATÓRIAS DE ALINHAMENTO SEMÂNTICO E ANTI-ALUCINAÇÃO:
1. PRIORIDADE MÁXIMA AO COMANDO DO USUÁRIO: Abra o relatório com uma seção intitulada '## 🎯 RESPOSTA TÁTICA DIRETA À SOLICITAÇÃO' respondendo exatamente ao que foi perguntado.
2. SE O USUÁRIO PERGUNTAR SOBRE UM JOGADOR ESPECÍFICO (ex: 'anular o Messi', 'marcar o Mbappé', 'comparar volantes'): Utilize os dados de `focused_player_deep_dive` para detalhar onde ele atua (centroide x, y, terço e corredor), quem é o Principal Abastecedor dele (`primary_feeder_teammate`), quem ele mais aciona (`primary_target_teammate`), sua queda de precisão sob pressão e prescreva o Plano A e Alternativa B para neutralizá-lo ou potencializá-lo.
3. NUNCA invente percentuais, contagens, coordenadas, nomes de jogadores, substituições ou acontecimentos. Utilize EXCLUSIVAMENTE os números presentes no JSON de Evidências.
4. Informe sempre a Fase do Jogo, o Setor/Corredor, a Frequência/Taxa exata, o Tamanho da Amostra (N) e o Grau de Evidência (FORTE, MODERADA ou LIMITADA).
5. Quando não houver dados de rastreamento contínuo (tracking 360) ou dados fisiológicos/GPS de fadiga, declare essa limitação explicitamente.
"""

    def __init__(
        self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"
    ) -> None:
        raw_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if (
            raw_key
            and "coloque_sua_chave" not in raw_key.lower()
            and len(raw_key.strip()) > 15
        ):
            self.api_key: Optional[str] = raw_key.strip()
        else:
            self.api_key = None
        self.model_name = model_name

    def generate_tactical_report(
        self,
        evidence_package: Dict[str, Any],
        prefer_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Gera o relatório tático a partir do pacote de evidências já calculado,
        customizando o texto para responder ao `user_query`.
        """
        deterministic_md = TacticalReportBuilder.build_deterministic_markdown_report(
            evidence_package
        )

        if not prefer_llm or not self.api_key:
            audit = NumericHallucinationGuard.audit_text_numbers(
                deterministic_md, evidence_package
            )
            return {
                "engine_used": "LOCAL_DETERMINISTIC_ENGINE",
                "report_markdown": deterministic_md,
                "hallucination_audit": audit,
            }

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            meta = evidence_package["metadata"]
            focused_players = evidence_package.get("focused_player_deep_dive", [])

            user_prompt = (
                f"COMANDO PRIORITÁRIO DO USUÁRIO (RESPONDA DIRETAMENTE A ISTO):\n"
                f"\"{meta['user_query']}\"\n"
                f"FOCO SEMÂNTICO DETECTADO: {meta['detected_focus']}\n"
                f"JOGADORES ESPECÍFICOS IDENTIFICADOS NA PERGUNTA: {meta.get('matched_players_in_query', [])}\n\n"
                f"DOSSIÊ PROFUNDO DOS JOGADORES CITADOS (SE HOUVER):\n"
                f"{json.dumps(focused_players, ensure_ascii=False, indent=2)}\n\n"
                f"PACOTE COMPLETO E IMUTÁVEL DE EVIDÊNCIAS DA PARTIDA (JSON):\n"
                f"{json.dumps(evidence_package, ensure_ascii=False, indent=2)}\n\n"
                f"Redija o relatório técnico em Markdown respondendo prioritariamente à pergunta acima e mantendo 100% de fidelidade numérica ao JSON."
            )

            response = client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.SYSTEM_INSTRUCTION,
                    temperature=0.1,
                ),
            )

            llm_text = response.text if response and response.text else ""
            if not llm_text.strip():
                raise RuntimeError("Resposta vazia da API generativa.")

            audit = NumericHallucinationGuard.audit_text_numbers(
                llm_text, evidence_package
            )

            if not audit["is_grounded"] and len(audit["unverified_decimals"]) > 2:
                return {
                    "engine_used": "LOCAL_DETERMINISTIC_FALLBACK_AFTER_AUDIT_BLOCK",
                    "report_markdown": deterministic_md,
                    "hallucination_audit": NumericHallucinationGuard.audit_text_numbers(
                        deterministic_md, evidence_package
                    ),
                }

            return {
                "engine_used": f"GEMINI_API ({self.model_name})",
                "report_markdown": llm_text,
                "hallucination_audit": audit,
            }

        except Exception as err:
            audit = NumericHallucinationGuard.audit_text_numbers(
                deterministic_md, evidence_package
            )
            return {
                "engine_used": f"LOCAL_DETERMINISTIC_FALLBACK ({type(err).__name__})",
                "report_markdown": deterministic_md,
                "hallucination_audit": audit,
            }