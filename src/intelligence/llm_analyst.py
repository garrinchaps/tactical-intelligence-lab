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

    SYSTEM_INSTRUCTION = """Você é o Analista Chefe de Desempenho do TACTICAL INTELLIGENCE LAB.
Responda à pergunta do usuário (`user_query`) de forma direta, técnica e densa em dados, usando EXCLUSIVAMENTE o JSON de evidências.

FORMATO OBRIGATÓRIO (Markdown, sem introdução, sem saudação, sem repetir a pergunta):
## 🎯 Resposta direta
- 3 a 6 tópicos curtos. Cada tópico traz: o fato, o número exato do JSON, a fase do jogo, o setor/corredor e o tamanho da amostra (N).
## 🛠️ Plano de ação
1. Plano A — uma ação concreta e o dado que a justifica.
2. Plano B — alternativa e o gatilho para usá-la.
## 📌 Resumo executivo para a comissão técnica
Duas ou três frases simples, sem jargão, com a decisão recomendada.

REGRAS ANTI-ALUCINAÇÃO:
1. NUNCA invente números, minutos, contagens, coordenadas, nomes de atletas, substituições ou lances. Só cite atletas presentes em `metadata.match_player_roster`.
2. Copie os números exatamente como aparecem no JSON (mesmas casas decimais).
3. Diferença entre duas porcentagens se escreve em pontos percentuais (pp), nunca em %.
4. Classifique o grau de evidência (FORTE, MODERADA ou LIMITADA) quando N for pequeno (menos de 30 ações).
5. Se `metadata.is_simulation_data` for verdadeiro, a primeira linha deve ser: ⚠️ [DADOS SIMULADOS / MODELAGEM PROBABILÍSTICA].
6. Sem dados de tracking 360 ou GPS, declare essa limitação em uma linha ao falar de fadiga ou espaço sem bola.
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
                f"Responda no FORMATO OBRIGATÓRIO, direto ao ponto, com 100% de fidelidade numérica e nominal ao JSON."
            )

            from src.guard.metrics import GuardMetricsLog
            from src.guard.policy import GuardPolicy

            def generate(extra):
                response = client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt if not extra else f"{extra}\n\n{user_prompt}",
                    config=types.GenerateContentConfig(system_instruction=self.SYSTEM_INSTRUCTION, temperature=0.1),
                )
                text = response.text if response and response.text else ""
                if not text.strip():
                    raise RuntimeError("Resposta vazia da API generativa.")
                return text

            pol = GuardPolicy(NumericHallucinationGuard.audit_text_numbers, GuardMetricsLog()).run(
                generate, evidence_package, fallback_text=deterministic_md, engine=f"GEMINI_API ({self.model_name})")
            if pol.outcome == "DEGRADADO":
                return {"engine_used": "RESPOSTA DEGRADADA (motor local após 2 bloqueios)", "report_markdown": pol.text,
                        "hallucination_audit": pol.audit, "guard_outcome": pol.outcome,
                        "guard_metrics": pol.metrics.as_dict()}
            return {
                "engine_used": f"GEMINI_API ({self.model_name})" + (" — regenerado com contexto restrito"
                                                                    if pol.outcome == "APROVADO_REGENERADO" else ""),
                "report_markdown": TacticalReportBuilder.prepend_simulation_badge(
                    pol.text, bool(meta.get("is_simulation_data", False))),
                "hallucination_audit": pol.audit, "guard_outcome": pol.outcome, "guard_metrics": pol.metrics.as_dict(),
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

    # ------------------------------------------------------------------
    # Pontos Fortes e Fracos (página estilo FM Data Hub)
    # ------------------------------------------------------------------
    def interpret_strengths_weaknesses(
        self,
        analysis: Dict[str, Any],
        is_simulation: bool = False,
        prefer_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Gera a interpretação textual da comparação contextual. Usa o Gemini quando
        disponível, audita números e nomes com o guardião e recua para o texto
        determinístico se a auditoria reprovar.
        """
        from src.metrics.strengths_weaknesses import StrengthsWeaknessesEngine

        deterministic_md = StrengthsWeaknessesEngine.build_interpretation_markdown(
            analysis, is_simulation=is_simulation
        )
        evidence = {
            "metadata": {
                "match_player_roster": [analysis.get("entity", "")]
                if analysis.get("mode") == "player"
                else [],
                "target_team": analysis.get("team_name", ""),
                "opponent_team": "",
                "is_simulation_data": bool(is_simulation),
                "user_query": "",
            },
            "analysis": analysis,
        }
        local = {
            "engine_used": "LOCAL_DETERMINISTIC_ENGINE",
            "report_markdown": deterministic_md,
            "hallucination_audit": NumericHallucinationGuard.audit_text_numbers(
                deterministic_md, evidence
            ),
        }
        if not prefer_llm or not self.api_key:
            return local

        try:
            from google import genai
            from google.genai import types

            prompt = (
                "Interprete a comparação abaixo entre o desempenho observado e a referência "
                "de elite da mesma função (percentil 100 = melhor da base). Formato: "
                "'## ✅ Pontos fortes' (até 4 tópicos), '## ⚠️ Pontos fracos' (até 4 tópicos), "
                "'## 📌 Resumo executivo' (2 frases simples). Cada tópico cita o valor, a mediana "
                "da referência e o percentil EXATAMENTE como no JSON. Não cite nenhum outro "
                "atleta, número ou fato.\n\n"
                f"{json.dumps(analysis, ensure_ascii=False, indent=1)}"
            )
            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.SYSTEM_INSTRUCTION, temperature=0.1
                ),
            )
            text = response.text if response and response.text else ""
            if not text.strip():
                raise RuntimeError("Resposta vazia da API generativa.")
            audit = NumericHallucinationGuard.audit_text_numbers(text, evidence)
            if not audit["is_grounded"]:
                local["engine_used"] = "LOCAL_DETERMINISTIC_FALLBACK_AFTER_AUDIT_BLOCK"
                local["hallucination_audit"]["blocked_llm_audit"] = audit
                return local
            return {
                "engine_used": f"GEMINI_API ({self.model_name})",
                "report_markdown": TacticalReportBuilder.prepend_simulation_badge(
                    text, is_simulation
                ),
                "hallucination_audit": audit,
            }
        except Exception as err:
            local["engine_used"] = f"LOCAL_DETERMINISTIC_FALLBACK ({type(err).__name__})"
            return local
