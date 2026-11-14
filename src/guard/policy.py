"""
Módulo 7.4 — Policy.

1ª geração → auditoria. Se houver número NÃO RASTREÁVEL (ou atleta fora do elenco):
bloqueia e regenera UMA vez com contexto mais restrito (lista fechada de números e nomes
permitidos). Se a 2ª geração também falhar: resposta degradada, declarada ao usuário
(texto do redator local + aviso explícito). Toda execução registra as taxas antes/depois.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from src.guard.metrics import GuardMetricsLog, GuardRunMetrics

DEGRADED_NOTICE = ("⚠️ **Resposta degradada:** a IA generativa citou números ou atletas que não constam nos dados "
                   "desta partida, duas vezes seguidas. Por segurança, abaixo está a resposta do redator local, "
                   "que só usa valores calculados.")


@dataclass
class PolicyResult:
    text: str
    outcome: str
    attempts: int
    audit: Dict[str, Any]
    first_audit: Dict[str, Any]
    metrics: GuardRunMetrics


def restricted_instruction(audit: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    """Instrução extra para a 2ª tentativa: o que foi rejeitado e a lista fechada de valores permitidos."""
    from src.guard.ground_truth import GroundTruthSet

    gt = GroundTruthSet.from_evidence(evidence)
    allowed = sorted({f"{f.value:g}" for f in gt.facts if "#texto" not in f.path})[:400]
    roster = (evidence.get("metadata") or {}).get("match_player_roster", [])
    bad = [c["numero"] for c in audit.get("classificacao", []) if c["classe"] == "NÃO RASTREÁVEL"]
    return ("ATENÇÃO — a resposta anterior foi BLOQUEADA pelo validador numérico. "
            f"Números rejeitados: {bad}. Nomes rejeitados: {audit.get('unverified_player_names', [])}.\n"
            "Reescreva usando SOMENTE números desta lista fechada (copie exatamente) e SOMENTE atletas do elenco.\n"
            f"Números permitidos: {', '.join(allowed)}\nAtletas permitidos: {', '.join(roster[:80])}\n"
            "Não faça contas além de diferença ou razão entre dois valores da lista.")


class GuardPolicy:
    def __init__(self, auditor: Callable[[str, Dict[str, Any]], Dict[str, Any]],
                 metrics_log: Optional[GuardMetricsLog] = None):
        self.auditor = auditor
        self.log = metrics_log

    def run(self, generate: Callable[[Optional[str]], str], evidence: Dict[str, Any],
            fallback_text: str, engine: str) -> PolicyResult:
        text1 = generate(None)
        a1 = self.auditor(text1, evidence)
        if a1["is_grounded"]:
            return self._done(text1, "APROVADO_1A", 1, a1, a1, engine)
        try:
            text2 = generate(restricted_instruction(a1, evidence))
            a2 = self.auditor(text2, evidence)
        except Exception:
            text2, a2 = "", {"is_grounded": False}
        if a2.get("is_grounded"):
            return self._done(text2, "APROVADO_REGENERADO", 2, a2, a1, engine)
        degraded = f"{DEGRADED_NOTICE}\n\n{fallback_text}"
        a3 = self.auditor(fallback_text, evidence)
        a3["blocked_llm_audit"] = a1
        return self._done(degraded, "DEGRADADO", 2, a3, a1, engine)

    def _done(self, text, outcome, attempts, audit, first, engine) -> PolicyResult:
        m = GuardRunMetrics(
            engine=engine, attempts=attempts, outcome=outcome,
            numbers_before=first.get("numbers_total", 0), untraceable_before=first.get("untraceable_count", 0),
            numbers_after=audit.get("numbers_total", 0), untraceable_after=audit.get("untraceable_count", 0),
            derived_after=audit.get("derived_count", 0),
            names_flagged_before=len(first.get("unverified_player_names", [])))
        audit["guard_metrics"] = m.as_dict()
        if self.log:
            self.log.log(m)
        return PolicyResult(text, outcome, attempts, audit, first, m)
