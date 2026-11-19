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
    ev_new, ev_old = evaluate(best_w, X[va], y[va], g[va], w[va]), evaluate(w0, X[va], y[va], g[va], w[va])
    a_new, a_old = ev_new.get("acerto_1o_fato"), ev_old.get("acerto_1o_fato")
    # promoção: perde menos E não acerta menos o 1º fato (a resposta não pode piorar para ganhar em perda)
    promoted = best < champ - 1e-4 and (a_new is None or a_old is None or a_new >= a_old - 1e-9)
    v = max(x["version"] for x in sel.meta["versions"]) + 1
    rec = {"version": v, "created": time.strftime("%Y-%m-%d %H:%M"), "weights": best_w.tolist(),
           "origin": "treino (avaliações + rótulo automático)" if use_weak else "treino (só avaliações)",
           "learning_rate": learning_rate, "l2": l2, "epochs": int(epochs), "epochs_run": len(hist["train_loss"]),
           "n_perguntas": int(len(ug)), "n_exemplos": int(len(y)),
           "n_avaliados": int(len(np.unique(g[src == "avaliação"]))) if len(src) else 0,
           "val_logloss": round(best, 5), "champion_logloss": round(champ, 5), "promoted": bool(promoted),
           "history": hist, "hidden": [], "test_logloss": round(best, 5),
           "metricas": ev_new, "metricas_campea": ev_old}
    sel.meta["versions"].append(rec)
    if promoted:
        sel.meta["champion"] = v
    sel._write()
    return {**{k: rec[k] for k in ("version", "promoted", "val_logloss", "champion_logloss", "n_perguntas",
                                     "n_exemplos", "n_avaliados", "epochs_run")}, "history": hist,
            "metricas": ev_new, "metricas_campea": ev_old,
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


# ------------------------------------------------------------------ rodada 14: avaliação detalhada e busca automática
def evaluate(weights: np.ndarray, X: np.ndarray, y: np.ndarray, g: np.ndarray, w: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """Métricas que dizem se a RESPOSTA acertou, não só a perda:
    * acerto do 1º fato: em cada pergunta com o fato certo marcado, o fato que a IA põe em 1º é o certo?
    * AUC (separa fato útil de fato irrelevante), precisão/revocação/F1 com limiar 0,5, log-loss."""
    from src.intelligence.course import confusion

    w = np.ones(len(y)) if w is None else w
    p = 1 / (1 + np.exp(-np.clip(X @ weights, -30, 30)))
    hits, total = 0, 0
    for q in np.unique(g):
        m = g == q
        if y[m].sum() >= 1 and (1 - y[m]).sum() >= 1:
            total += 1
            hits += int(y[m][int(np.argmax(p[m]))] == 1)
    try:
        from sklearn.metrics import roc_auc_score

        auc = float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None
    except Exception:
        auc = None
    c = confusion(y.astype(int), p, 0.5)
    return {"acerto_1o_fato": round(hits / total, 4) if total else None, "perguntas_avaliadas": total,
            "auc": None if auc is None else round(auc, 4), "precisao": c["precisao"], "revocacao": c["revocacao"],
            "f1": c["f1"], "logloss": round(_loss(X, y, w, weights), 5)}


def cross_validate(learning_rate: float, l2: float, epochs: int, folds: int = 5, use_weak: bool = True,
                   shown_path: Optional[Path] = None, feedback_path: Optional[Path] = None, seed: int = 11,
                   base: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """K dobras agrupadas por pergunta: média e desvio do acerto do 1º fato e da perda (estimativa estável)."""
    X, y, w, g, _ = build_dataset(shown_path, feedback_path, use_weak=use_weak)
    ug = np.unique(g)
    if len(ug) < folds * 2:
        return {"dobras": 0}
    rng = np.random.default_rng(seed)
    perm = rng.permutation(ug)
    base = Selector().weights if base is None else base
    acc, ll = [], []
    for k in range(folds):
        te_g = set(perm[k::folds])
        te = np.isin(g, list(te_g))
        wt = base.copy()
        idx = np.where(~te)[0]
        for _ in range(int(epochs)):
            rng.shuffle(idx)
            for s in range(0, len(idx), 256):
                b = idx[s:s + 256]
                pr = 1 / (1 + np.exp(-np.clip(X[b] @ wt, -30, 30)))
                wt -= learning_rate * (X[b].T @ (w[b] * (pr - y[b])) / max(w[b].sum(), 1e-9) + l2 * (wt - base))
        ev = evaluate(wt, X[te], y[te], g[te], w[te])
        if ev["acerto_1o_fato"] is not None:
            acc.append(ev["acerto_1o_fato"])
        ll.append(ev["logloss"])
    return {"dobras": folds, "acerto_medio": round(float(np.mean(acc)), 4) if acc else None,
            "acerto_desvio": round(float(np.std(acc)), 4) if acc else None,
            "perda_media": round(float(np.mean(ll)), 5), "perda_desvio": round(float(np.std(ll)), 5)}


def auto_search(epochs: int = 150, use_weak: bool = True, shown_path: Optional[Path] = None,
                feedback_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Busca em grade pequena (η × λ) por validação cruzada; devolve a tabela ordenada pelo acerto do 1º fato."""
    rows = []
    for lr in (0.03, 0.1, 0.3):
        for l2 in (0.001, 0.01, 0.1):
            cv = cross_validate(lr, l2, epochs, use_weak=use_weak, shown_path=shown_path, feedback_path=feedback_path)
            if cv.get("dobras"):
                rows.append({"η": lr, "λ": l2, **cv})
    rows.sort(key=lambda r: (-(r.get("acerto_medio") or 0), r.get("perda_media") or 9))
    return rows
