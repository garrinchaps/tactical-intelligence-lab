"""
Comparação honesta de modelos para o "perigo da posse" (rodada 5).

Pergunta: a rede neural (MLP NumPy) é mesmo a ferramenta certa, ou um modelo mais simples faz igual?
Todos os modelos usam AS MESMAS dobras (GroupKFold por partida — nenhuma partida aparece no treino e na validação da
mesma dobra), as mesmas variáveis e as mesmas métricas:
  * AUC (separa jogada perigosa de não perigosa), Brier e log loss (qualidade da probabilidade), ECE (calibração:
    quando o modelo diz 30%, acontece ~30%?);
  * teste pareado por PARTIDA (bootstrap): a diferença de AUC para a regressão logística só conta se o intervalo de
    95% não cruzar o zero.
Modelos: taxa constante (piso), regressão logística só com distância/ângulo/passes, regressão logística completa,
floresta aleatória, gradient boosting (HistGradientBoosting do scikit-learn — mesma família do XGBoost/LightGBM, sem
dependência nova) e a rede neural do laboratório.
Também mede a importância de cada variável por permutação no melhor modelo de árvores (mostra variáveis que não ajudam).

Uso: python -m src.machine_learning.benchmark            (amostra de demonstração da Copa 2022)
     python -m src.machine_learning.benchmark --dados caminho.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.machine_learning.danger_dataset import BASELINE_FEATURES, FEATURES

DEMO = Path("data/demo/danger_sample_wc2022.csv.gz")
OUT = Path("data/processed/benchmark_perigo.json")


def _ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(float(y[m].mean()) - float(p[m].mean()))
    return float(e)


def _models(seed: int) -> Dict[str, Any]:
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "Regressão logística (distância, ângulo, passes)": ("base", make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))),
        "Regressão logística (todas as variáveis)": ("all", make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))),
        "Floresta aleatória": ("all", RandomForestClassifier(n_estimators=200, min_samples_leaf=20, n_jobs=-1, random_state=seed)),
        "Gradient boosting (família XGBoost)": ("all", HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                                                                      min_samples_leaf=40, random_state=seed)),
    }


def run(data: pd.DataFrame, k: int = 5, seed: int = 42, mlp_hidden: Optional[List[int]] = None, epochs: int = 60,
        n_boot: int = 300) -> Dict[str, Any]:
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    from sklearn.model_selection import GroupKFold

    from src.machine_learning.neural_net import NeuralNetwork

    d = data.copy()
    # Amostras anteriores à v37 não têm o indicador de origem da densidade.
    if "density_is_360" not in d:
        d["density_is_360"] = d["density_source"].eq("statsbomb_360").astype(float) if "density_source" in d else 0.0
    d = d.dropna(subset=FEATURES + ["target"]).reset_index(drop=True)
    X, Xb = d[FEATURES].to_numpy(float), d[BASELINE_FEATURES].to_numpy(float)
    y, g = d["target"].to_numpy(int), d["match_id"].to_numpy()
    k = min(k, len(np.unique(g)))
    preds: Dict[str, np.ndarray] = {"Taxa constante (piso)": np.zeros(len(d))}
    models = _models(seed)
    for name in list(models) + ["Rede neural do laboratório (MLP)"]:
        preds[name] = np.zeros(len(d))
    for tr, va in GroupKFold(n_splits=k).split(X, y, g):
        preds["Taxa constante (piso)"][va] = y[tr].mean()
        for name, (fs, mdl) in models.items():
            A = Xb if fs == "base" else X
            mdl.fit(A[tr], y[tr])
            preds[name][va] = mdl.predict_proba(A[va])[:, 1]
        # rede: parada antecipada numa fatia do TREINO (nunca na validação)
        rng = np.random.default_rng(seed)
        tg = np.unique(g[tr])
        stop_g = set(rng.choice(tg, size=max(1, len(tg) // 8), replace=False))
        st_ = np.isin(g[tr], list(stop_g))
        net = NeuralNetwork([X.shape[1]] + (mlp_hidden or [32, 16]) + [1], learning_rate=0.001, l2=1e-4, seed=seed,
                            feature_names=FEATURES)
        net.fit(X[tr][~st_], y[tr][~st_], epochs=epochs, batch_size=256, optimizer="adam",
                X_stop=X[tr][st_], y_stop=y[tr][st_], patience=10)
        preds["Rede neural do laboratório (MLP)"][va] = np.asarray(net.predict_proba(X[va])).ravel()
    rows = []
    for name, p in preds.items():
        p = np.clip(p, 1e-6, 1 - 1e-6)
        auc = roc_auc_score(y, p) if len(set(y)) > 1 and p.std() > 0 else 0.5
        rows.append({"modelo": name, "auc": round(float(auc), 4), "brier": round(float(brier_score_loss(y, p)), 4),
                     "log_loss": round(float(log_loss(y, p)), 4), "ece": round(_ece(y, p), 4)})
    # bootstrap pareado POR PARTIDA: diferença de AUC contra a regressão logística completa
    ref = "Regressão logística (todas as variáveis)"
    matches = np.unique(g)
    rng = np.random.default_rng(seed)
    by = {m: np.where(g == m)[0] for m in matches}
    for r in rows:
        if r["modelo"] in (ref, "Taxa constante (piso)"):
            continue
        diffs = []
        for _ in range(n_boot):
            idx = np.concatenate([by[m] for m in rng.choice(matches, size=len(matches), replace=True)])
            if len(set(y[idx])) < 2:
                continue
            diffs.append(roc_auc_score(y[idx], preds[r["modelo"]][idx]) - roc_auc_score(y[idx], preds[ref][idx]))
        lo, hi = (np.percentile(diffs, [2.5, 97.5]) if diffs else (0, 0))
        r["dif_auc_vs_logistica"] = round(float(np.mean(diffs)) if diffs else 0.0, 4)
        r["ic95"] = [round(float(lo), 4), round(float(hi), 4)]
        r["veredito"] = "melhor que a logística" if lo > 0 else "pior que a logística" if hi < 0 else "empate estatístico"
    # importância por permutação no gradient boosting (o mais flexível entre os de árvore)
    imp = {}
    try:
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.inspection import permutation_importance

        tr, va = next(GroupKFold(n_splits=k).split(X, y, g))
        gb = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, min_samples_leaf=40, random_state=seed).fit(X[tr], y[tr])
        pi = permutation_importance(gb, X[va], y[va], scoring="roc_auc", n_repeats=5, random_state=seed)
        imp = {f: round(float(v), 4) for f, v in sorted(zip(FEATURES, pi.importances_mean), key=lambda kv: -kv[1])}
    except Exception:
        pass
    rows.sort(key=lambda r: -r["auc"])
    best = rows[0]
    mlp = next(r for r in rows if r["modelo"].startswith("Rede neural"))
    useless = [f for f, v in imp.items() if v <= 0.001]
    concl = (f"Melhor AUC: {best['modelo']} ({best['auc']}). A rede neural ficou com {mlp['auc']} — "
             f"{mlp.get('veredito', '—')} (IC95 da diferença {mlp.get('ic95')}).")
    if useless:
        concl += f" Variáveis que quase não ajudam: {', '.join(useless)} — o teto vem mais das variáveis do que do modelo."
    return {"partidas": int(len(matches)), "acoes": int(len(d)), "positivos_pct": round(100 * float(y.mean()), 1),
            "dobras": k, "resultados": rows, "importancia_permutacao": imp, "conclusao": concl,
            "fonte_densidade": d["density_source"].value_counts().to_dict() if "density_source" in d else {}}


def main() -> None:
    ap = argparse.ArgumentParser(description="Compara a rede neural com modelos mais simples (mesmas dobras e métricas).")
    ap.add_argument("--dados", default=str(DEMO), help="CSV com as colunas do danger_dataset (padrão: amostra da Copa 2022)")
    ap.add_argument("--epocas", type=int, default=60)
    a = ap.parse_args()
    res = run(pd.read_csv(a.dados), epochs=a.epocas)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{res['partidas']} partidas · {res['acoes']} ações · {res['positivos_pct']}% positivas · {res['dobras']} dobras por partida")
    for r in res["resultados"]:
        print(f"  {r['modelo']:<48} AUC {r['auc']:.4f}  Brier {r['brier']:.4f}  ECE {r['ece']:.4f}  {r.get('veredito', '')}")
    print(res["conclusao"])
    print(f"(salvo em {OUT})")


if __name__ == "__main__":
    main()
