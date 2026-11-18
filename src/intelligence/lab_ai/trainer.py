"""
Rodada 13 — treino da IA do Assistente no MESMO molde da rede de perigo.

O que ela aprende: dado um fato do jogo (ex.: "Cruzeiro 7 chutes no gol, acima de 82% dos jogos") e uma pergunta,
qual a chance de esse fato ser o que importa para responder. É um neurônio sigmoide (regressão logística) — a Q6 da
matéria — sobre os 18 sinais que cada fato já carrega (força do número na régua, se é do time citado, categoria…).

De onde vêm os exemplos (rótulos):
1. Avaliações 👍/👎 das respostas (peso 3 — é a sua opinião direta).
2. Rótulo AUTOMÁTICO (supervisão fraca): quando a pergunta pede um número reconhecível ("quem errou mais passes",
   "bolas longas"), o fato desse número é o certo (1) e os outros fatos daquela resposta não eram o foco (0). Assim a IA
   treina com as quase 2 mil perguntas já feitas, sem precisar de 20 avaliações para começar.

Treino igual ao da rede: separação por pergunta (nenhuma pergunta no treino e na validação), descida do gradiente com
L2, curva treino × validação por época, parada antecipada (paciência), e a versão nova só vira oficial se errar menos
que a atual na MESMA validação.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from src.intelligence.lab_ai.facts import N_FEATURES
from src.intelligence.lab_ai.selector import FEEDBACK_PATH, SHOWN_PATH, Selector, _read_jsonl


def _label_key(question: str) -> Optional[str]:
    from src.intelligence.lab_ai import direct as D

    k = D.detect(question or "")
    if not k:
        return None
    return D.FACT_KEY.get(k, k)


def build_dataset(shown_path: Optional[Path] = None, feedback_path: Optional[Path] = None, use_weak: bool = True):
    shown_path, feedback_path = shown_path or SHOWN_PATH, feedback_path or FEEDBACK_PATH
    ratings = {}
    for r in _read_jsonl(feedback_path):
        if r.get("interaction_id") and r.get("rating") in ("positive", "negative"):
            ratings[str(r["interaction_id"])] = 1.0 if r["rating"] == "positive" else 0.0
    X, y, w, g, src = [], [], [], [], []
    for row in _read_jsonl(shown_path):
        iid = str(row.get("interaction_id"))
        facts = [f for f in row.get("facts") or [] if isinstance(f.get("features"), list)
                 and len(f["features"]) == N_FEATURES]
        if not facts:
            continue
        if iid in ratings:
            for f in facts:
                X.append(f["features"]); y.append(ratings[iid]); w.append(3.0); g.append(iid); src.append("avaliação")
            continue
        if not use_weak:
            continue
        key = _label_key(row.get("question", ""))
        if not key or not any(str(f.get("key")) == key for f in facts):
            continue                                     # sem número reconhecido, não há rótulo honesto
        for f in facts:
            X.append(f["features"]); y.append(1.0 if str(f.get("key")) == key else 0.0); w.append(1.0); g.append(iid)
            src.append("automático")
    return (np.asarray(X, float).reshape(-1, N_FEATURES), np.asarray(y, float), np.asarray(w, float),
            np.asarray(g), np.asarray(src))


def _loss(X, y, w, wt):
    p = np.clip(1 / (1 + np.exp(-np.clip(X @ wt, -30, 30))), 1e-6, 1 - 1e-6)
    return float(np.sum(w * -(y * np.log(p) + (1 - y) * np.log(1 - p))) / max(w.sum(), 1e-9))


def train(learning_rate: float = 0.1, l2: float = 0.01, epochs: int = 200, patience: int = 15, val_fraction: float = 0.25,
          batch: int = 256, seed: int = 7, use_weak: bool = True, sel: Optional[Selector] = None,
          shown_path: Optional[Path] = None, feedback_path: Optional[Path] = None) -> Dict[str, Any]:
    sel = sel or Selector()
    X, y, w, g, src = build_dataset(shown_path, feedback_path, use_weak=use_weak)
    ug = np.unique(g)
    if len(ug) < 5 or len(np.unique(y)) < 2:
        return {"promoted": False, "reason": f"poucos exemplos com rótulo ({len(ug)} perguntas); faça perguntas que "
                                             "peçam um número (ex.: 'quem errou mais passes?') ou avalie respostas com 👍/👎",
                "n_perguntas": int(len(ug)), "n_exemplos": int(len(y))}
    rng = np.random.default_rng(seed)
    val_g = set(rng.choice(ug, size=max(1, int(round(len(ug) * val_fraction))), replace=False))
    va = np.isin(g, list(val_g))
    w0 = sel.weights.copy()
    wt = w0.copy()
    hist = {"train_loss": [], "val_loss": []}
    best, best_w, bad = np.inf, wt.copy(), 0
    idx = np.where(~va)[0]
    for ep in range(int(epochs)):
        rng.shuffle(idx)
        for s in range(0, len(idx), batch):
            b = idx[s:s + batch]
            p = 1 / (1 + np.exp(-np.clip(X[b] @ wt, -30, 30)))
            grad = X[b].T @ (w[b] * (p - y[b])) / max(w[b].sum(), 1e-9) + l2 * (wt - w0)
            wt -= learning_rate * grad
        tr, vl = _loss(X[~va], y[~va], w[~va], wt), _loss(X[va], y[va], w[va], wt)
        hist["train_loss"].append(round(tr, 5))
        hist["val_loss"].append(round(vl, 5))
        if vl < best - 1e-5:
            best, best_w, bad = vl, wt.copy(), 0
        else:
            bad += 1
            if bad >= patience:
                break
    champ = _loss(X[va], y[va], w[va], w0)
    promoted = best < champ - 1e-4
    v = max(x["version"] for x in sel.meta["versions"]) + 1
    rec = {"version": v, "created": time.strftime("%Y-%m-%d %H:%M"), "weights": best_w.tolist(),
           "origin": "treino (avaliações + rótulo automático)" if use_weak else "treino (só avaliações)",
           "learning_rate": learning_rate, "l2": l2, "epochs": int(epochs), "epochs_run": len(hist["train_loss"]),
           "n_perguntas": int(len(ug)), "n_exemplos": int(len(y)),
           "n_avaliados": int(len(np.unique(g[src == "avaliação"]))) if len(src) else 0,
           "val_logloss": round(best, 5), "champion_logloss": round(champ, 5), "promoted": bool(promoted),
           "history": hist, "hidden": [], "test_logloss": round(best, 5)}
    sel.meta["versions"].append(rec)
    if promoted:
        sel.meta["champion"] = v
    sel._write()
    return {**{k: rec[k] for k in ("version", "promoted", "val_logloss", "champion_logloss", "n_perguntas",
                                     "n_exemplos", "n_avaliados", "epochs_run")}, "history": hist,
            "reason": ("PROMOVIDA: errou menos que a versão atual nas perguntas de validação" if promoted else
                       "rejeitada: não errou menos que a versão atual nas perguntas de validação (a atual continua)")}


def suggest(version: Dict[str, Any]) -> Dict[str, Any]:
    """Mesma leitura da curva da rede de perigo (Q7), traduzida para os parâmetros deste neurônio."""
    from src.intelligence.course import diagnose_curve

    d = diagnose_curve(version.get("history") or {})
    lr, l2, ep = float(version.get("learning_rate") or 0.1), float(version.get("l2") or 0.01), int(version.get("epochs") or 200)
    new, why = {"learning_rate": lr, "l2": l2, "epochs": ep}, []
    if d["diagnostico"] == "sobreajuste":
        new["l2"] = round(min(l2 * 5 if l2 else 0.01, 1.0), 4)
        why.append("sobreajuste → mais L2 (puxa os pesos de volta para os do analista)")
    elif d["diagnostico"] == "oscilação":
        new["learning_rate"] = round(lr / 3, 4)
        why.append("oscilação → taxa de aprendizado 3× menor")
    elif d["diagnostico"] == "subajuste":
        new["epochs"] = min(ep * 2, 1000)
        new["learning_rate"] = round(min(lr * 2, 1.0), 4)
        new["l2"] = round(l2 / 5, 5)
        why.append("subajuste → mais épocas, passo maior e menos L2")
    elif d["diagnostico"] == "equilibrado":
        why.append("curva saudável: o que mais ajuda agora são MAIS perguntas e avaliações 👍/👎")
    else:
        why.append("rode um treino para registrar a curva")
    return {"diagnostico": d, "sugerido": new, "porque": why}
