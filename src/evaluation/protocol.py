"""
Protocolo de avaliação com baselines obrigatórios (Seção 8).

A) Perigo de posse — quatro modelos lado a lado, validação cruzada k-fold AGRUPADA POR PARTIDA
   (GroupKFold: nenhuma partida aparece no treino e na validação ao mesmo tempo):
     Baseline 0  classe majoritária (score constante → AUC = 0,5 por definição)
     Baseline 1  regressão logística com distância, ângulo e passes na posse
     Modelo A    XGBoost com todas as variáveis
     Modelo B    rede neural própria (NumPy) com todas as variáveis
   Métricas: AUC-ROC por fold (média ± desvio), prevalência da classe positiva, ganho absoluto
   sobre cada baseline. Ganho < 0,03 de AUC sobre a logística é declarado como MARGINAL.

B) Grafo de passes — baseline (grau ponderado) × modelo (betweenness ponderada por xT).
   Centralidades calculadas no 1º tempo; avaliadas no 2º tempo para não haver vazamento.
   Alvo: a cada toque de um atleta fora do terço final no 2º tempo, a posse chega ao terço
   final depois desse toque? Score = centralidade do atleta. AUC por equipe-partida.

Uso: python -m src.evaluation.protocol --max-matches 64
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.machine_learning.danger_dataset import BASELINE_FEATURES, FEATURES
from src.machine_learning.neural_net import NeuralNetwork

REPORT_DIR = Path("models/evaluation")
MARGINAL = 0.03
XGB_PARAMS = {"n_estimators": 300, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.9,
              "colsample_bytree": 0.9, "random_state": 42}
NN_PARAMS = {"layers": [len(FEATURES), 32, 16, 1], "learning_rate": 0.05, "l2": 1e-3, "epochs": 30, "batch_size": 512}


def xgboost_impl() -> str:
    try:
        import xgboost

        version = getattr(xgboost, "__version__", None)
        return f"xgboost {version}" if version else "substituto (xgboost indisponível no ambiente)"
    except Exception:
        return "indisponível"


def _make_xgb():
    from xgboost import XGBClassifier

    try:
        return XGBClassifier(**XGB_PARAMS, eval_metric="logloss", tree_method="hist")
    except TypeError:
        return XGBClassifier(n_estimators=XGB_PARAMS["n_estimators"], max_depth=XGB_PARAMS["max_depth"],
                             learning_rate=XGB_PARAMS["learning_rate"], random_state=42)


# --------------------------------------------------------------------- A
def evaluate_danger(data: pd.DataFrame, k: int = 5, seed: int = 42, nn_epochs: Optional[int] = None) -> Dict[str, Any]:
    data = data.dropna(subset=FEATURES + ["target"]).reset_index(drop=True)
    X = data[FEATURES].to_numpy(float)
    Xb = data[BASELINE_FEATURES].to_numpy(float)
    y = data["target"].to_numpy(int)
    groups = data["match_id"].to_numpy()
    n_matches = len(np.unique(groups))
    k = min(k, n_matches)
    prevalence = float(y.mean())
    folds: List[Dict[str, Any]] = []
    oof = {"lr": np.zeros(len(y)), "xgb": np.zeros(len(y)), "nn": np.zeros(len(y))}
    nn_hist = None
    last_xgb = None
    for f, (tr, va) in enumerate(GroupKFold(n_splits=k).split(X, y, groups)):
        lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(Xb[tr], y[tr])
        p_lr = lr.predict_proba(Xb[va])[:, 1]
        xgb = _make_xgb().fit(X[tr], y[tr])
        p_xgb = xgb.predict_proba(X[va])[:, 1]
        nn = NeuralNetwork(NN_PARAMS["layers"], NN_PARAMS["learning_rate"], NN_PARAMS["l2"], seed=seed + f,
                           feature_names=FEATURES)
        nn.fit(X[tr], y[tr], epochs=nn_epochs or NN_PARAMS["epochs"], batch_size=NN_PARAMS["batch_size"],
               X_val=X[va], y_val=y[va])
        p_nn = nn.predict_proba(X[va])
        oof["lr"][va], oof["xgb"][va], oof["nn"][va] = p_lr, p_xgb, p_nn
        folds.append({"fold": f + 1, "n_val": int(len(va)), "partidas_val": int(len(np.unique(groups[va]))),
                      "prevalencia_val": round(float(y[va].mean()), 4),
                      "auc_baseline0": 0.5,
                      "auc_logistica": round(float(roc_auc_score(y[va], p_lr)), 4),
                      "auc_xgboost": round(float(roc_auc_score(y[va], p_xgb)), 4),
                      "auc_rede_neural": round(float(roc_auc_score(y[va], p_nn)), 4)})
        nn_hist, last_xgb = nn.history, xgb

    fd = pd.DataFrame(folds)

    def ms(col: str) -> Dict[str, float]:
        return {"media": round(float(fd[col].mean()), 4), "desvio": round(float(fd[col].std(ddof=1)), 4) if len(fd) > 1 else 0.0}

    res = {"baseline0": ms("auc_baseline0"), "logistica": ms("auc_logistica"), "xgboost": ms("auc_xgboost"),
           "rede_neural": ms("auc_rede_neural")}
    gains = {}
    for model in ("xgboost", "rede_neural"):
        g_b1 = round(res[model]["media"] - res["logistica"]["media"], 4)
        gains[model] = {"sobre_baseline0": round(res[model]["media"] - 0.5, 4), "sobre_logistica": g_b1,
                        "interpretacao": ("ganho MARGINAL (< 0,03 de AUC sobre a logística)" if g_b1 < MARGINAL
                                          else "ganho relevante (≥ 0,03 de AUC sobre a logística)")}
    thr = prevalence
    cm = confusion_matrix(y, (oof["xgb"] >= thr).astype(int)).tolist()
    return {
        "amostras": int(len(y)), "partidas": int(n_matches), "k_folds": int(k), "prevalencia_positiva": round(prevalence, 4),
        "split": "GroupKFold por partida (nenhuma partida no treino e na validação ao mesmo tempo)",
        "variaveis": FEATURES, "variaveis_baseline1": BASELINE_FEATURES,
        "densidade_360_pct": round(100 * float((data["density_source"] == "statsbomb_360").mean()), 1)
        if "density_source" in data else None,
        "auc": res, "ganhos": gains, "folds": folds,
        "matriz_confusao_xgboost_oof": {"limiar": round(thr, 4), "matriz": cm,
                                        "ordem": "[[VN, FP], [FN, VP]] — previsões fora da amostra (out-of-fold)"},
        "xgboost_impl": xgboost_impl(), "xgboost_params": XGB_PARAMS, "rede_neural_params": NN_PARAMS,
        "rede_neural_historico_ultimo_fold": nn_hist,
        "_last_xgb": last_xgb,
    }


# --------------------------------------------------------------------- B
def _half_network(df: pd.DataFrame, team: str) -> Dict[str, Dict[str, float]]:
    p = df[(df["team_name"] == team) & (df["period"] == 1) & (df["type_name"] == "Pass") &
           (df["is_pass_completed"] == 1) & df["pass_recipient_name"].notna() & df["player_name"].notna()]
    if p.empty:
        return {}
    gain = p.get("delta_xt", pd.Series(0.0, index=p.index)).clip(lower=0).fillna(0)
    edges = p.assign(g=gain).groupby(["player_name", "pass_recipient_name"]).agg(n=("g", "size"), xt=("g", "mean"))
    G = nx.DiGraph()
    for (a, b), r in edges.iterrows():
        strength = r["n"] * (1.0 + 10.0 * r["xt"])        # passes valorizados pela ameaça gerada
        G.add_edge(a, b, n=r["n"], dist=1.0 / strength)
    deg = dict(G.degree(weight="n"))
    btw = nx.betweenness_centrality(G, weight="dist", normalized=True)
    return {"grau": deg, "betweenness_xt": btw}


def evaluate_graph(processed: Dict[int, pd.DataFrame], min_events: int = 30) -> Dict[str, Any]:
    rows = []
    for mid, df in processed.items():
        for team in df["team_name"].dropna().unique():
            cent = _half_network(df, team)
            if not cent:
                continue
            d2 = df[(df["period"] == 2) & (df["possession_team_name"] == team)].sort_values("index_num")
            touches = []
            for _, g in d2.groupby("possession"):
                xs = g["x"].to_numpy(float)
                reached = np.zeros(len(g), dtype=int)
                future_max = np.maximum.accumulate(np.nan_to_num(xs[::-1], nan=-1))[::-1]
                for i in range(len(g)):
                    reached[i] = int(i + 1 < len(g) and future_max[i + 1] >= 80) if i + 1 < len(g) else 0
                for i, r in enumerate(g.itertuples(index=False)):
                    if r.team_name == team and isinstance(r.player_name, str) and r.x == r.x and r.x < 80 \
                            and r.player_name in cent["grau"]:
                        touches.append((cent["grau"][r.player_name], cent["betweenness_xt"].get(r.player_name, 0.0), reached[i]))
            if len(touches) < min_events:
                continue
            t = np.array(touches)
            if len(np.unique(t[:, 2])) < 2:
                continue
            rows.append({"match_id": mid, "equipe": team, "toques": len(t), "prevalencia": round(float(t[:, 2].mean()), 4),
                         "auc_grau": round(float(roc_auc_score(t[:, 2], t[:, 0])), 4),
                         "auc_betweenness_xt": round(float(roc_auc_score(t[:, 2], t[:, 1])), 4)})
    fr = pd.DataFrame(rows)
    if fr.empty:
        return {"equipes_partidas": 0}
    diff = fr["auc_betweenness_xt"] - fr["auc_grau"]
    mean_diff = float(diff.mean())
    return {
        "equipes_partidas": int(len(fr)),
        "alvo": "a posse chega ao terço final (x ≥ 80) depois do toque do atleta (2º tempo)",
        "centralidades": "calculadas no 1º tempo (rede de passes certos); betweenness com distância 1/(passes·(1+10·xT médio))",
        "auc_grau": {"media": round(float(fr["auc_grau"].mean()), 4), "desvio": round(float(fr["auc_grau"].std(ddof=1)), 4)},
        "auc_betweenness_xt": {"media": round(float(fr["auc_betweenness_xt"].mean()), 4),
                               "desvio": round(float(fr["auc_betweenness_xt"].std(ddof=1)), 4)},
        "diferenca_media": round(mean_diff, 4),
        "betweenness_vence_em_pct": round(100 * float((diff > 0).mean()), 1),
        "interpretacao": ("betweenness ponderada por xT SUPERA o grau neste alvo" if mean_diff >= 0.01 else
                          "betweenness ponderada por xT NÃO supera o grau neste alvo (diferença < 0,01 de AUC)"),
        "por_equipe_partida": rows,
    }


# ----------------------------------------------------------------- relatório
def write_report(danger: Dict[str, Any], graph: Dict[str, Any], out_dir: Path = REPORT_DIR) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    danger = {k: v for k, v in danger.items() if not k.startswith("_")}
    payload = {"gerado_em": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "perigo_de_posse": danger,
               "grafo_de_passes": graph}
    jp = out_dir / "protocol_report.json"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    a = danger["auc"]
    lines = [
        "# Relatório do protocolo de avaliação", "",
        f"Gerado em {payload['gerado_em']} por `python -m src.evaluation.protocol`.", "",
        "## A) Perigo de posse", "",
        f"- Amostras: **{danger['amostras']}** ações de **{danger['partidas']}** partidas; prevalência da classe positiva: "
        f"**{100 * danger['prevalencia_positiva']:.1f}%**.",
        f"- Validação: {danger['split']}, k = {danger['k_folds']}.",
        f"- Densidade de adversários medida pelo StatsBomb 360 em {danger.get('densidade_360_pct')}% das ações (restante: proxy).",
        f"- Implementação do Modelo A: {danger['xgboost_impl']}.", "",
        "| Modelo | AUC-ROC (média ± desvio) | Ganho sobre B0 | Ganho sobre B1 |", "|---|---|---|---|",
        f"| Baseline 0 — classe majoritária | {a['baseline0']['media']:.3f} | — | — |",
        f"| Baseline 1 — logística (distância, ângulo, passes) | {a['logistica']['media']:.3f} ± {a['logistica']['desvio']:.3f} | "
        f"{a['logistica']['media'] - 0.5:+.3f} | — |",
        f"| Modelo A — XGBoost | {a['xgboost']['media']:.3f} ± {a['xgboost']['desvio']:.3f} | "
        f"{danger['ganhos']['xgboost']['sobre_baseline0']:+.3f} | {danger['ganhos']['xgboost']['sobre_logistica']:+.3f} |",
        f"| Modelo B — rede neural própria | {a['rede_neural']['media']:.3f} ± {a['rede_neural']['desvio']:.3f} | "
        f"{danger['ganhos']['rede_neural']['sobre_baseline0']:+.3f} | {danger['ganhos']['rede_neural']['sobre_logistica']:+.3f} |",
        "", f"- XGBoost: {danger['ganhos']['xgboost']['interpretacao']}.",
        f"- Rede neural: {danger['ganhos']['rede_neural']['interpretacao']}.", "",
    ]
    if graph.get("equipes_partidas"):
        lines += ["## B) Grafo de passes", "",
                  f"- Alvo: {graph['alvo']}.", f"- {graph['centralidades']}.",
                  f"- {graph['equipes_partidas']} equipes-partidas avaliadas.", "",
                  "| Score | AUC (média ± desvio) |", "|---|---|",
                  f"| Baseline — grau ponderado | {graph['auc_grau']['media']:.3f} ± {graph['auc_grau']['desvio']:.3f} |",
                  f"| Modelo — betweenness ponderada por xT | {graph['auc_betweenness_xt']['media']:.3f} ± {graph['auc_betweenness_xt']['desvio']:.3f} |",
                  "", f"- Diferença média: {graph['diferenca_media']:+.3f}; betweenness vence em {graph['betweenness_vence_em_pct']}% "
                      f"das equipes-partidas. **Conclusão:** {graph['interpretacao']}.", ""]
    mp = out_dir / "protocol_report.md"
    mp.write_text("\n".join(lines), encoding="utf-8")
    return {"json": jp, "md": mp}


def train_final_models(data: pd.DataFrame, out_dir: Path = Path("models/trained"), nn_epochs: Optional[int] = None) -> Dict[str, Path]:
    """Treina XGBoost e rede neural em TODO o dataset (para a página de inspeção) e salva."""
    import joblib

    out_dir.mkdir(parents=True, exist_ok=True)
    d = data.dropna(subset=FEATURES + ["target"])
    X, y = d[FEATURES].to_numpy(float), d["target"].to_numpy(int)
    xgb = _make_xgb().fit(X, y)
    joblib.dump({"model": xgb, "features": FEATURES, "params": XGB_PARAMS, "impl": xgboost_impl()},
                out_dir / "danger_xgb.joblib")
    nn = NeuralNetwork(NN_PARAMS["layers"], NN_PARAMS["learning_rate"], NN_PARAMS["l2"], seed=42, feature_names=FEATURES)
    nn.fit(X, y, epochs=nn_epochs or NN_PARAMS["epochs"], batch_size=NN_PARAMS["batch_size"])
    return {"xgb": out_dir / "danger_xgb.joblib", "nn": nn.save(out_dir / "danger_nn.npz")}


def main() -> None:
    from src.data_hub.db import DataHubDB
    from src.data_hub.sources.statsbomb import StatsBombProvider
    from src.machine_learning.danger_dataset import build_dataset
    from src.metrics.xt_model import ExpectedThreatModel
    from src.preprocessing.event_cleaner import EventPreprocessor

    ap = argparse.ArgumentParser(description="Roda o protocolo de avaliação com baselines.")
    ap.add_argument("--competition", default="FIFA World Cup", help="competição do catálogo StatsBomb")
    ap.add_argument("--season", default="2022", help="temporada do catálogo StatsBomb")
    ap.add_argument("--max-matches", type=int, default=64)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()
    db = DataHubDB()
    sb = StatsBombProvider(db)
    cat = db.catalog("data_source = 'statsbomb' AND competition_name = ? AND season_name = ?",
                     (args.competition, args.season))
    if cat.empty:
        print("Competição não encontrada no catálogo: rode antes `python -m src.data_hub.sync --only statsbomb`.")
        return
    ids = [int(m) for m in cat["match_id"].tolist()][: args.max_matches]
    print(f"{len(ids)} partidas de {args.competition} {args.season}. Baixando eventos e dados 360 que faltarem...")

    def load(mid: int) -> pd.DataFrame:
        return db.load_events(mid) if db.has_events(mid) else sb.load_events(mid)

    data = build_dataset(ids, load, sb.load_360, progress=print)
    full = Path("data/processed/danger_full.csv.gz")      # a página Rede Neural treina com estes exemplos
    full.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(full, index=False, compression="gzip")
    danger = evaluate_danger(data, k=args.k)
    processed = {mid: ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(load(mid)))
                 for mid in ids}
    graph = evaluate_graph(processed)
    paths = write_report(danger, graph)
    models = train_final_models(data)
    print(paths["md"].read_text(encoding="utf-8"))
    print(f"Modelos finais salvos em: {models['xgb']} e {models['nn']}")


if __name__ == "__main__":
    main()
