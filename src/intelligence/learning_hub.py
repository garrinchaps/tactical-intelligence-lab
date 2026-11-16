"""Registro central de uso e feedback da inteligência do laboratório.

Perguntas e avaliações humanas ajudam a encontrar lacunas e montar casos de teste.
Elas NÃO viram exemplos supervisionados automaticamente: só dados com rótulo verificável
(partida, ação e resultado observado) podem atualizar pesos de modelos.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

INTERACTIONS_PATH = Path("data/learning/interactions.jsonl")
FEEDBACK_PATH = Path("data/learning/feedback.jsonl")


def _append(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _read(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            if isinstance(row, dict):
                yield row


def record_interaction(
    query: str,
    result: Dict[str, Any],
    meta: Optional[Dict[str, Any]] = None,
    path: Optional[Path | str] = None,
) -> str:
    """Registra uma pergunta sem guardar o texto completo da resposta nem credenciais."""
    interaction_id = uuid.uuid4().hex
    meta = meta or {}
    evidence = result.get("evidence") or {}
    blocks = evidence.get("blocos") or {}
    scope = result.get("scope") or {}
    audit = result.get("hallucination_audit") or {}
    md = evidence.get("metadata") or {}
    used_danger = any("perigo" in str(k).lower() or "danger" in str(k).lower() for k in blocks)

    row = {
        "interaction_id": interaction_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": str(query or "")[:500],
        "match_id": meta.get("match_id") or md.get("match_id"),
        "data_source": meta.get("data_source") or md.get("data_source"),
        "data_level": meta.get("data_level") or md.get("data_level"),
        "engine": str(result.get("engine_used") or ""),
        "intent": scope.get("ask"),
        "category": scope.get("category"),
        "evidence_blocks": sorted(str(k)[:100] for k in blocks),
        "evidence_used": bool(evidence),
        "danger_model_evidence_present": used_danger,
        "numbers_checked": int(audit.get("numbers_total") or audit.get("verified_decimals_count", 0)
                                + audit.get("verified_integers_count", 0) or 0),
        "grounded": bool(audit.get("is_grounded", True)),
        "latency_s": result.get("latency_s"),
        "trained_from_this_question": False,
        "learning_status": "registrada_para_auditoria",
        "training_note": "Pergunta não é rótulo de treino; exige feedback revisado e resultado verificável.",
    }
    _append(Path(path) if path is not None else INTERACTIONS_PATH, row)
    return interaction_id


def record_feedback(
    interaction_id: str,
    rating: str | int,
    note: str = "",
    path: Optional[Path | str] = None,
) -> None:
    """Guarda avaliação humana como pendente de revisão; não altera pesos de modelos."""
    value = {0: "negative", 1: "positive"}.get(rating, str(rating).strip().lower())
    if value in ("up", "thumbs_up", "positive"):
        value = "positive"
    elif value in ("down", "thumbs_down", "negative"):
        value = "negative"
    else:
        raise ValueError("rating deve ser positive/negative ou 1/0")
    if not interaction_id:
        raise ValueError("interaction_id vazio")
    _append(Path(path) if path is not None else FEEDBACK_PATH, {
        "interaction_id": str(interaction_id),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rating": value,
        "note": str(note or "")[:1000],
        "status": "pendente_de_revisao",
        "updates_model_weights": False,
    })


def feedback_ids(path: Optional[Path | str] = None) -> set[str]:
    source = Path(path) if path is not None else FEEDBACK_PATH
    return {str(r.get("interaction_id")) for r in _read(source) if r.get("interaction_id")}


def has_feedback(interaction_id: str, path: Optional[Path | str] = None) -> bool:
    return str(interaction_id) in feedback_ids(path)


def learning_summary(
    interactions_path: Optional[Path | str] = None,
    feedback_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Resumo agregado para o painel Bastidores; não expõe as perguntas individuais."""
    ip = Path(interactions_path) if interactions_path is not None else INTERACTIONS_PATH
    fp = Path(feedback_path) if feedback_path is not None else FEEDBACK_PATH
    total = grounded = generic = danger = 0
    for row in _read(ip):
        total += 1
        grounded += int(bool(row.get("grounded", True)))
        generic += int(row.get("intent") is None or row.get("category") == "off_topic")
        danger += int(bool(row.get("danger_model_evidence_present")))
    positive = negative = pending = 0
    for row in _read(fp):
        positive += int(row.get("rating") == "positive")
        negative += int(row.get("rating") == "negative")
        pending += int(row.get("status") == "pendente_de_revisao")
    return {
        "questions_recorded": total,
        "grounded_questions": grounded,
        "generic_or_unclassified": generic,
        "danger_model_questions": danger,
        "positive_feedback": positive,
        "negative_feedback": negative,
        "feedback_pending_review": pending,
        "questions_that_changed_weights": 0,
        "feedback_that_changed_weights": 0,
    }
