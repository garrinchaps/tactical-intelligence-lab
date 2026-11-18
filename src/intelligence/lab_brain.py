"""
Rodada 13 — o "cérebro" do laboratório: UMA IA com vários módulos, um botão para treinar tudo e um único lugar
para o 👍/👎 de qualquer análise do app.

Como funciona (linguagem simples):
* Cada análise que aparece na tela (um confronto do pré-jogo, uma resposta do Assistente, uma fraqueza do rival, uma
  indicação do Scout) tem um TIPO (ex.: confronto "drible", resposta "substituição").
* Quando você aprova ou reprova, o cérebro guarda isso numa contagem por tipo (distribuição Beta — "acertos e erros").
* Na próxima vez, os tipos mais aprovados sobem na lista e os reprovados descem (peso entre 0,6 e 1,4). É
  aprendizado por reforço simples: o app aprende o que é útil PARA VOCÊ, sem mudar nenhum número dos jogos.
* "Treinar tudo" roda, em ordem: o seletor de fatos do Assistente (com as avaliações), a rede de perigo (com os
  parâmetros que a própria IA sugere a partir do último treino), e refaz as réguas da base (jogadores, confrontos,
  notas) que todos os módulos usam.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path("data/learning")
STATE = ROOT / "brain.json"
LOG = ROOT / "feedback_global.jsonl"
PRIOR = 2.0                     # começa neutro: 2 aprovações e 2 reprovações imaginárias

MODULES = {
    "assistente": "Assistente (respostas do chat)",
    "confrontos": "Pré-jogo — confrontos meu time × rival",
    "fragilidades": "Diagnóstico do rival (onde atacar)",
    "scout": "Scout (indicações de contratação)",
    "relatorio": "Relatório e leitura do jogo",
}


def _load() -> Dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"tipos": {}, "treinos": []}


def _save(d: Dict[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def feedback(module: str, kind: str, positive: bool, context: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    d = _load()
    key = f"{module}:{kind}"
    t = d["tipos"].setdefault(key, {"a": 0, "b": 0})
    t["a" if positive else "b"] += 1
    _save(d)
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": datetime.now(timezone.utc).isoformat(timespec="seconds"), "modulo": module,
                                "tipo": kind, "positivo": bool(positive), "contexto": context or {}},
                               ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    return {"peso": weight(module, kind)}


def weight(module: str, kind: str) -> float:
    """Média da Beta(a+2, b+2) levada para 0,6–1,4 (1,0 = neutro)."""
    t = _load()["tipos"].get(f"{module}:{kind}") or {"a": 0, "b": 0}
    mean = (t["a"] + PRIOR) / (t["a"] + t["b"] + 2 * PRIOR)
    return round(0.6 + 0.8 * mean, 3)


def table() -> List[Dict[str, Any]]:
    rows = []
    for key, t in sorted(_load()["tipos"].items()):
        mod, kind = key.split(":", 1)
        rows.append({"módulo": MODULES.get(mod, mod), "tipo de análise": kind, "👍": t["a"], "👎": t["b"],
                     "peso atual": weight(mod, kind)})
    return rows


def train_all(db, progress: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
    """Treina/atualiza todos os módulos treináveis, um depois do outro. Cada etapa falha sozinha sem parar as outras."""
    say = progress or (lambda m: None)
    out: List[Dict[str, Any]] = []

    def step(name: str, fn: Callable[[], str]) -> None:
        t0 = time.time()
        say(f"{name}…")
        try:
            msg = fn()
            out.append({"módulo": name, "resultado": msg, "segundos": round(time.time() - t0, 1), "ok": True})
        except Exception as exc:                       # noqa: BLE001
            out.append({"módulo": name, "resultado": f"não rodou: {exc}", "segundos": round(time.time() - t0, 1),
                        "ok": False})

    def selector() -> str:
        from src.intelligence.lab_ai import trainer as TR
        from src.intelligence.lab_ai.selector import Selector

        sel = Selector()
        sug = TR.suggest(sel.meta["versions"][-1])["sugerido"]
        r = TR.train(learning_rate=sug["learning_rate"], l2=sug["l2"], epochs=sug["epochs"], sel=sel)
        return r.get("reason", "treinado") + (f" ({r['n_perguntas']} perguntas)" if r.get("n_perguntas") else "")

    def danger() -> str:
        from src.intelligence.course import suggest_next_experiment
        from src.machine_learning.model_registry import DangerModelRegistry

        reg = DangerModelRegistry()
        last = (reg.meta.get("versions") or [{}])[-1]
        sug = suggest_next_experiment(last)["sugerido"]
        data = DangerModelRegistry.dataset()
        res = reg.train_round(data, list(sug["hidden"]), learning_rate=float(sug["learning_rate"]),
                              epochs=int(sug["epochs"]), l2=float(sug["l2"]))
        r = res if isinstance(res, dict) else getattr(res, "__dict__", {})
        return (f"parâmetros sugeridos {sug['hidden']} · η {sug['learning_rate']} · λ {sug['l2']} → "
                f"{'PROMOVIDA' if r.get('promoted') else 'rejeitada'}: {r.get('reason', '')}")

    def rulers() -> str:
        from src.intelligence.lab_ai import reference as LR
        from src.squad import matchups as MU

        n1 = len(LR.build(db))
        n2 = len(MU.reference(db, force=True))
        return f"régua dos jogos: {n1} números · régua dos confrontos: {n2} jogadores"

    def player_index() -> str:
        from src.ui.pages import players_search as PS

        df = PS.build_player_index(db)
        PS.save_player_index(df)
        return f"índice de busca: {len(df)} jogadores"

    step("Assistente — seletor de fatos (👍/👎)", selector)
    step("Rede de perigo (parâmetros sugeridos pela própria IA)", danger)
    step("Réguas da base (jogos e confrontos)", rulers)
    step("Índice de jogadores da busca", player_index)
    d = _load()
    d["treinos"] = (d.get("treinos") or [])[-19:] + [{"quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                      "etapas": out}]
    _save(d)
    return out
