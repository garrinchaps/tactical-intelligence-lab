"""
Rede de seleção de conteúdo da IA do laboratório (regressão logística em NumPy) + aprendizado das frases.

* v000 = pesos iniciais escritos à mão (o que um analista olharia primeiro: número fora da curva, que casa com a
  pergunta, grande diferença para o rival).
* Cada resposta da IA registra os fatos que mostrou (data/learning/lab_ai_shown.jsonl). Quando você avalia a resposta
  (👍/👎 no Assistente), aqueles fatos viram exemplos rotulados.
* `train()` ajusta os pesos (descida de gradiente com L2 puxando para a versão atual), separa 20% das respostas
  avaliadas para teste e só PROMOVE a versão nova se ela errar menos nesse teste (log-loss). Tudo fica registrado em
  models/registry/lab_ai/registry.json.
* As frases-modelo do redator aprendem por "bandido de Thompson": cada frase acumula 👍/👎 das respostas em que
  apareceu; frase com mais aprovação tende a ser escolhida mais vezes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from src.intelligence.lab_ai.facts import CATS, FEATURE_NAMES, N_FEATURES

ROOT = Path("models/registry/lab_ai")
SHOWN_PATH = Path("data/learning/lab_ai_shown.jsonl")
FEEDBACK_PATH = Path("data/learning/feedback.jsonl")
MIN_RATED = 20

PRIOR = np.array([-1.5, 2.5, 1.2, 0.3, 3.0, 0.0, 0.6, 0.3] +
                 [{"padrão": 0.5, "individual": -0.2, "disciplina": -1.2, "goleiro": -0.4, "ataque": 0.3,
                   "criação": 0.2}.get(c, 0.0) for c in CATS], float)
assert len(PRIOR) == N_FEATURES


def _read_jsonl(p: Path) -> List[Dict[str, Any]]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            if isinstance(r, dict):
                out.append(r)
        except ValueError:
            continue
    return out


class Selector:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else ROOT
        self.meta_path = self.root / "registry.json"
        self.meta = json.loads(self.meta_path.read_text(encoding="utf-8")) if self.meta_path.exists() else {
            "champion": 0, "versions": [{"version": 0, "created": "inicial", "weights": PRIOR.tolist(),
                                         "origin": "pesos iniciais (regras de analista)", "n_rated": 0,
                                         "test_logloss": None}], "templates": {}}

    # ------------------------------------------------------------------ uso
    @property
    def weights(self) -> np.ndarray:
        v = next(x for x in self.meta["versions"] if x["version"] == self.meta["champion"])
        w = np.asarray(v["weights"], float)
        return w if len(w) == N_FEATURES else PRIOR

    @property
    def version(self) -> int:
        return int(self.meta["champion"])

    def score(self, X: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(X @ self.weights, -30, 30)))

    def pick_template(self, slot: str, options: List[str], rng: np.random.Generator) -> int:
        """Thompson: sorteia de Beta(1+👍, 1+👎) de cada frase e usa a maior."""
        st = self.meta.get("templates", {})
        draws = [rng.beta(1 + st.get(f"{slot}:{i}", [0, 0])[0], 1 + st.get(f"{slot}:{i}", [0, 0])[1])
                 for i in range(len(options))]
        return int(np.argmax(draws))

    def _write(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------ treino
    @staticmethod
    def dataset(shown_path: Path = SHOWN_PATH, feedback_path: Path = FEEDBACK_PATH):
        ratings = {}
        for r in _read_jsonl(feedback_path):
            if r.get("interaction_id") and r.get("rating") in ("positive", "negative"):
                ratings[str(r["interaction_id"])] = 1 if r["rating"] == "positive" else 0
        X, y, groups, tmpl = [], [], [], []
        for row in _read_jsonl(shown_path):
            iid = str(row.get("interaction_id"))
            if iid not in ratings:
                continue
            for f in row.get("facts") or []:
                feats = f.get("features")
                if isinstance(feats, list) and len(feats) == N_FEATURES:
                    X.append(feats)
                    y.append(ratings[iid])
                    groups.append(iid)
            tmpl.append((row.get("templates") or [], ratings[iid]))
        return np.asarray(X, float).reshape(-1, N_FEATURES), np.asarray(y, float), np.asarray(groups), tmpl

    @staticmethod
    def _fit(X, y, w0, l2=0.5, lr=0.1, epochs=400):
        w = w0.copy()
        for _ in range(epochs):
            p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
            g = X.T @ (p - y) / max(len(y), 1) + l2 * (w - w0) / max(len(y), 1)
            w -= lr * g
        return w

    @staticmethod
    def _logloss(X, y, w):
        p = np.clip(1 / (1 + np.exp(-np.clip(X @ w, -30, 30))), 1e-6, 1 - 1e-6)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    def train(self, shown_path: Path = SHOWN_PATH, feedback_path: Path = FEEDBACK_PATH, seed: int = 7) -> Dict[str, Any]:
        X, y, groups, tmpl = self.dataset(shown_path, feedback_path)
        # frases: contagem de 👍/👎 sempre atualizada (é estatística, não troca de modelo)
        counts: Dict[str, List[int]] = {}
        for ids, lab in tmpl:
            for t in ids:
                c = counts.setdefault(t, [0, 0])
                c[0 if lab else 1] += 1
        self.meta["templates"] = counts
        n_rated = int(len(np.unique(groups))) if len(groups) else 0
        if n_rated < MIN_RATED or len(np.unique(y)) < 2:
            self._write()
            return {"promoted": False, "n_rated": n_rated,
                    "reason": f"são precisas pelo menos {MIN_RATED} respostas avaliadas, com 👍 e 👎 "
                              f"(agora: {n_rated}). As frases já aprenderam com as avaliações que existem."}
        ug = np.unique(groups)
        rng = np.random.default_rng(seed)
        test_g = set(rng.choice(ug, size=max(1, int(round(len(ug) * 0.2))), replace=False))
        te = np.isin(groups, list(test_g))
        w0 = self.weights
        w = self._fit(X[~te], y[~te], w0)
        ll_new, ll_old = self._logloss(X[te], y[te], w), self._logloss(X[te], y[te], w0)
        promoted = ll_new < ll_old - 1e-4
        v = max(x["version"] for x in self.meta["versions"]) + 1
        self.meta["versions"].append({"version": v, "created": time.strftime("%Y-%m-%d %H:%M"), "weights": w.tolist(),
                                      "origin": "treino com avaliações", "n_rated": n_rated, "n_facts": int(len(y)),
                                      "test_logloss": round(ll_new, 5), "champion_logloss": round(ll_old, 5),
                                      "promoted": bool(promoted)})
        if promoted:
            self.meta["champion"] = v
        self._write()
        return {"promoted": bool(promoted), "version": v, "n_rated": n_rated, "test_logloss": round(ll_new, 5),
                "champion_logloss": round(ll_old, 5),
                "reason": ("promovida: errou menos nas respostas de teste" if promoted else
                           "rejeitada: não errou menos que a versão atual nas respostas de teste")}

    def weight_table(self) -> List[Dict[str, Any]]:
        return [{"o que a IA olha": n, "peso": round(float(w), 2)} for n, w in zip(FEATURE_NAMES, self.weights)]


def log_shown(interaction_id: str, question: str, facts: List[Dict[str, Any]], templates: List[str],
              path: Path = SHOWN_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"interaction_id": interaction_id, "question": question[:300], "facts": facts,
                             "templates": templates, "created": time.strftime("%Y-%m-%d %H:%M:%S")},
                            ensure_ascii=False) + "\n")
