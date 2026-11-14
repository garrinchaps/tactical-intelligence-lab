"""
Dados para a página de Inspeção de Modelos e Treinamento (Seção 6).

Tudo que a página mostra sai daqui, com os hiperparâmetros expostos:
* XGBoost: importância por ganho, profundidade das árvores, ganho por split, matriz de confusão.
* K-Means: pontos das perdas de posse, rótulos, centróides, contagem por cluster, silhouette por k.
* DBSCAN: pontos das recuperações, rótulos (−1 = ruído), eps e min_samples.
* NetworkX: grau ponderado × betweenness ponderada por xT, lado a lado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import silhouette_score

TRAINED = Path("models/trained")
REPORT = Path("models/evaluation/protocol_report.json")


def load_protocol_report() -> Optional[Dict[str, Any]]:
    return json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else None


def load_danger_models() -> Dict[str, Any]:
    out: Dict[str, Any] = {"xgb": None, "nn": None}
    try:
        import joblib

        if (TRAINED / "danger_xgb.joblib").exists():
            out["xgb"] = joblib.load(TRAINED / "danger_xgb.joblib")
    except Exception as exc:
        out["xgb_error"] = str(exc)
    if (TRAINED / "danger_nn.npz").exists():
        from src.machine_learning.neural_net import NeuralNetwork

        out["nn"] = NeuralNetwork.load(TRAINED / "danger_nn.npz")
    return out


def xgb_inspection(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Importância por ganho, profundidade e ganho por split (XGBoost real ou árvores do scikit-learn)."""
    model, feats = payload["model"], payload["features"]
    params = payload.get("params", {})
    try:
        booster = model.get_booster()
        gain = booster.get_score(importance_type="gain")
        names = {f"f{i}": f for i, f in enumerate(feats)}
        imp = pd.DataFrame([{"variavel": names.get(k, k), "ganho_medio": v} for k, v in gain.items()])
        trees = booster.trees_to_dataframe()
        splits = trees[trees["Feature"] != "Leaf"].copy()
        depth = []
        for _, t in trees.groupby("Tree"):
            nodes = dict(zip(t["ID"], zip(t["Yes"], t["No"])))
            def d(node: str) -> int:
                yes, no = nodes.get(node, (None, None))
                return 0 if not isinstance(yes, str) else 1 + max(d(yes), d(no))
            depth.append(d(t["ID"].iloc[0]))
        split_gain = splits["Gain"].to_numpy(float)
        impl = "xgboost"
    except Exception:
        imp = pd.DataFrame({"variavel": feats, "ganho_medio": getattr(model, "feature_importances_", np.zeros(len(feats)))})
        depth, split_gain = [], []
        for est in np.ravel(getattr(model, "estimators_", [])):
            tr = est.tree_
            depth.append(int(tr.max_depth))
            for node in range(tr.node_count):
                l, r = tr.children_left[node], tr.children_right[node]
                if l != -1:
                    w = tr.weighted_n_node_samples
                    split_gain.append(float(w[node] * tr.impurity[node] - w[l] * tr.impurity[l] - w[r] * tr.impurity[r]))
        split_gain = np.array(split_gain)
        impl = "árvores do scikit-learn (substituto)"
    imp = imp.sort_values("ganho_medio", ascending=False).reset_index(drop=True)
    total = imp["ganho_medio"].sum() or 1.0
    imp["participacao_pct"] = (100 * imp["ganho_medio"] / total).round(1)
    return {"importancia": imp, "profundidades": depth, "ganho_por_split": split_gain, "n_arvores": len(depth),
            "params": params, "impl": payload.get("impl", impl)}


def kmeans_points(df: pd.DataFrame, team: str, k_range=range(2, 7), random_state: int = 42) -> Dict[str, Any]:
    t = df[(df["team_name"] == team) & (df["is_turnover"] == 1)].dropna(subset=["x", "y"])
    coords = t[["x", "y"]].to_numpy(float)
    if len(coords) < 6:
        return {"pontos": pd.DataFrame(), "centroides": pd.DataFrame(), "silhouette": {}, "k": 0}
    sil = {}
    best = (None, -1.0, 2)
    for k in k_range:
        if k >= len(coords):
            break
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit(coords)
        s = float(silhouette_score(coords, km.labels_))
        sil[k] = round(s, 4)
        if s > best[1]:
            best = (km, s, k)
    km = best[0]
    pts = pd.DataFrame({"x": coords[:, 0], "y": coords[:, 1], "cluster": km.labels_.astype(int),
                        "atleta": t["player_name"].to_numpy(), "minuto": t["minute"].to_numpy()})
    cen = pd.DataFrame(km.cluster_centers_, columns=["x", "y"])
    cen["cluster"] = range(len(cen))
    cen["n"] = pts.groupby("cluster").size().reindex(cen["cluster"]).fillna(0).astype(int).to_numpy()
    return {"pontos": pts, "centroides": cen, "silhouette": sil, "k": best[2],
            "params": {"algoritmo": "K-Means", "k_escolhido_por": "maior silhouette", "k_testados": list(sil),
                       "n_init": 10, "random_state": random_state, "variaveis": "x, y da perda de posse (jardas)"}}


def dbscan_points(df: pd.DataFrame, team: str, eps: float = 14.0, min_samples: int = 5) -> Dict[str, Any]:
    t = df[(df["team_name"] == team) & (df["is_ball_recovery"] == 1)].dropna(subset=["x", "y"])
    coords = t[["x", "y"]].to_numpy(float)
    if len(coords) == 0:
        return {"pontos": pd.DataFrame(), "params": {"eps": eps, "min_samples": min_samples}}
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit(coords).labels_
    pts = pd.DataFrame({"x": coords[:, 0], "y": coords[:, 1], "cluster": labels.astype(int),
                        "atleta": t["player_name"].to_numpy()})
    return {"pontos": pts, "n_ruido": int((labels == -1).sum()), "n_clusters": int(len(set(labels) - {-1})),
            "params": {"algoritmo": "DBSCAN", "eps": eps, "eps_unidade": "jardas", "min_samples": min_samples,
                       "variaveis": "x, y da recuperação de bola"}}


def centrality_comparison(df: pd.DataFrame, team: str) -> pd.DataFrame:
    p = df[(df["team_name"] == team) & (df["type_name"] == "Pass") & (df["is_pass_completed"] == 1) &
           df["pass_recipient_name"].notna() & df["player_name"].notna()]
    if p.empty:
        return pd.DataFrame()
    gain = p.get("delta_xt", pd.Series(0.0, index=p.index)).clip(lower=0).fillna(0)
    edges = p.assign(g=gain).groupby(["player_name", "pass_recipient_name"]).agg(n=("g", "size"), xt=("g", "mean"))
    G = nx.DiGraph()
    for (a, b), r in edges.iterrows():
        G.add_edge(a, b, n=float(r["n"]), dist=1.0 / (r["n"] * (1.0 + 10.0 * r["xt"])))
    deg = dict(G.degree(weight="n"))
    btw = nx.betweenness_centrality(G, weight="dist", normalized=True)
    out = pd.DataFrame({"atleta": list(G.nodes()), "grau_ponderado": [deg[n] for n in G.nodes()],
                        "betweenness_xt": [round(btw[n], 4) for n in G.nodes()]})
    out["rank_grau"] = out["grau_ponderado"].rank(ascending=False, method="min").astype(int)
    out["rank_betweenness"] = out["betweenness_xt"].rank(ascending=False, method="min").astype(int)
    return out.sort_values("betweenness_xt", ascending=False).reset_index(drop=True)
