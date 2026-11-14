"""Página 3 — Machine Learning & Inspeção de Treinamento (Seção 6) + baselines (Seção 8)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.evaluation.inspection import (centrality_comparison, dbscan_points, kmeans_points, load_danger_models,
                                       load_protocol_report, xgb_inspection)
from src.machine_learning.danger_dataset import FEATURES
from src.ui import charts
from src.ui.components import comparison_table, empty_state, error_state, kpi, note, page_header, provenance_panel
from src.ui.context import MatchContext

DEMO_SAMPLE = Path("data/demo/danger_sample_wc2022.csv.gz")


@st.cache_resource(show_spinner=False)
def _quick_xgb():
    """Treino rápido do XGBoost na amostra de demonstração (quando não há modelo salvo)."""
    from src.evaluation.protocol import XGB_PARAMS, _make_xgb, xgboost_impl

    d = pd.read_csv(DEMO_SAMPLE)
    m = _make_xgb().fit(d[FEATURES].to_numpy(float), d["target"].to_numpy(int))
    return {"model": m, "features": FEATURES, "params": XGB_PARAMS, "impl": xgboost_impl() + " · amostra de demonstração"}


def _baselines(ctx: MatchContext, report) -> None:
    st.markdown("### Protocolo de avaliação — perigo de posse")
    if not report:
        empty_state("Relatório de avaliação ainda não gerado", "Rode o protocolo uma vez no terminal.", "🧪",
                    "python -m src.evaluation.protocol  (baixa a Copa 2022 e treina os quatro modelos)")
        return
    d = report["perigo_de_posse"]
    a = d["auc"]
    src = report_prov = ctx.prov("protocolo", "Protocolo de avaliação", "AUC k-fold",
                                 f"GroupKFold por partida, k={d['k_folds']}, {d['partidas']} partidas, gerado em {report['gerado_em']}",
                                 tier="DERIVED")
    c = st.columns(4)
    with c[0]:
        kpi("ações avaliadas", f"{d['amostras']:,}".replace(",", "."), report_prov)
    with c[1]:
        kpi("partidas (split por partida)", d["partidas"], report_prov)
    with c[2]:
        kpi("prevalência da classe positiva", f"{100 * d['prevalencia_positiva']:.1f}%", report_prov)
    with c[3]:
        kpi("ações com densidade medida (360)", f"{d.get('densidade_360_pct')}%", report_prov)
    tab = pd.DataFrame([
        {"modelo": "Baseline 0 — classe majoritária", "AUC média": a["baseline0"]["media"], "desvio": 0.0, "ganho s/ B0": None, "ganho s/ B1": None},
        {"modelo": "Baseline 1 — logística (distância, ângulo, passes)", "AUC média": a["logistica"]["media"], "desvio": a["logistica"]["desvio"],
         "ganho s/ B0": round(a["logistica"]["media"] - 0.5, 4), "ganho s/ B1": None},
        {"modelo": f"Modelo A — XGBoost ({d['xgboost_impl']})", "AUC média": a["xgboost"]["media"], "desvio": a["xgboost"]["desvio"],
         "ganho s/ B0": d["ganhos"]["xgboost"]["sobre_baseline0"], "ganho s/ B1": d["ganhos"]["xgboost"]["sobre_logistica"]},
        {"modelo": "Modelo B — rede neural própria (NumPy)", "AUC média": a["rede_neural"]["media"], "desvio": a["rede_neural"]["desvio"],
         "ganho s/ B0": d["ganhos"]["rede_neural"]["sobre_baseline0"], "ganho s/ B1": d["ganhos"]["rede_neural"]["sobre_logistica"]},
    ])
    comparison_table(tab, "AUC-ROC média dos folds de validação. B0 tem AUC 0,5 por definição (score constante).")
    for model, label in (("xgboost", "XGBoost"), ("rede_neural", "Rede neural")):
        g = d["ganhos"][model]
        kind = "warn" if g["sobre_logistica"] < 0.03 else ""
        note(f"{label}: {g['interpretacao']}",
             "Ganho absoluto de AUC sobre a logística = " + f"{g['sobre_logistica']:+.3f}. " +
             ("Resultado honesto: a geometria (distância, ângulo) e o número de passes já explicam quase todo o sinal "
              "disponível neste alvo. O que os modelos não lineares acrescentam — interações espaciais e densidade de "
              "pressão — tem efeito pequeno aqui." if g["sobre_logistica"] < 0.03 else ""), kind)
    folds = pd.DataFrame(d["folds"])
    with st.expander("AUC por fold"):
        st.dataframe(folds, use_container_width=True, hide_index=True)
    g = report.get("grafo_de_passes", {})
    if g.get("equipes_partidas"):
        st.markdown("### Protocolo de avaliação — grafo de passes")
        comparison_table(pd.DataFrame([
            {"score": "Baseline — grau ponderado", "AUC média": g["auc_grau"]["media"], "desvio": g["auc_grau"]["desvio"]},
            {"score": "Modelo — betweenness ponderada por xT", "AUC média": g["auc_betweenness_xt"]["media"],
             "desvio": g["auc_betweenness_xt"]["desvio"]}]),
            f"Alvo: {g['alvo']}. {g['centralidades']}. {g['equipes_partidas']} equipes-partidas.")
        note("Conclusão do grafo", f"{g['interpretacao']} (diferença média {g['diferenca_media']:+.3f}; betweenness vence em "
             f"{g['betweenness_vence_em_pct']}% das equipes-partidas). Sem ganho no alvo, a rede deve ser lida como visualização "
             "da estrutura, não como inferência sobre progressão.", "warn" if g["diferenca_media"] < 0.01 else "")
    return report_prov


def _xgb(ctx: MatchContext, report) -> None:
    st.markdown("### XGBoost — o que o modelo aprendeu")
    models = load_danger_models()
    payload = models.get("xgb")
    if payload is None:
        if not DEMO_SAMPLE.exists():
            empty_state("Modelo XGBoost não treinado", "", "🌳", "python -m src.evaluation.protocol")
            return
        with st.spinner("Treinando XGBoost na amostra de demonstração (16 mil ações da Copa 2022)..."):
            payload = _quick_xgb()
        st.caption("Modelo salvo não encontrado: exibindo um treino rápido na amostra de demonstração.")
    try:
        x = xgb_inspection(payload)
    except Exception as exc:
        error_state("Não foi possível inspecionar o modelo", exc)
        return
    p = x["params"]
    prov = ctx.prov("xgb", "XGBoost", x["impl"], f"importância por ganho; {x['n_arvores']} árvores", tier="DERIVED")
    st.markdown("**Hiperparâmetros:** " + " · ".join(f"`{k} = {v}`" for k, v in p.items()) + f" · implementação: `{x['impl']}`")
    a, b = st.columns(2)
    a.plotly_chart(charts.bar_h(x["importancia"], "participacao_pct", "variavel", "Importância por ganho (% do ganho total)",
                                "% do ganho total"), use_container_width=True)
    if report:
        cm = report["perigo_de_posse"]["matriz_confusao_xgboost_oof"]
        b.plotly_chart(charts.confusion(cm["matriz"], f"Matriz de confusão (validação out-of-fold, limiar = prevalência {cm['limiar']:.3f})"),
                       use_container_width=True)
    c, d = st.columns(2)
    if x["profundidades"]:
        c.plotly_chart(charts.histogram(x["profundidades"], "Profundidade real das árvores", "profundidade", nbins=10),
                       use_container_width=True)
    if len(x["ganho_por_split"]):
        d.plotly_chart(charts.histogram(x["ganho_por_split"], "Ganho de informação por split", "ganho (redução da perda)", nbins=40),
                       use_container_width=True)


def _clusters(ctx: MatchContext) -> None:
    st.markdown(f"### K-Means — perdas de posse de {ctx.target_team}")
    km = kmeans_points(ctx.df, ctx.target_team)
    if km["k"] == 0:
        empty_state("Perdas de posse insuficientes para clusterizar (mínimo 6).", icon="🔵")
    else:
        ctx.prov("kmeans", "K-Means", f"k={km['k']}", "K-Means em (x, y) das perdas; k pelo maior silhouette")
        st.markdown("**Hiperparâmetros:** " + " · ".join(f"`{k} = {v}`" for k, v in km["params"].items()))
        a, b = st.columns([1.4, 1])
        a.plotly_chart(charts.kmeans_scatter(km, f"Clusters de perdas (k = {km['k']}) com centróides"), use_container_width=True)
        with b:
            st.dataframe(km["centroides"].rename(columns={"x": "centróide x (jd)", "y": "centróide y (jd)", "n": "perdas"}),
                         use_container_width=True, hide_index=True)
            st.dataframe(pd.DataFrame({"k": list(km["silhouette"]), "silhouette": list(km["silhouette"].values())}),
                         use_container_width=True, hide_index=True)

    st.markdown(f"### DBSCAN — armadilhas de pressing (recuperações de {ctx.target_team})")
    a, b = st.columns(2)
    eps = a.slider("eps (raio, jardas)", 4.0, 30.0, 14.0, 1.0)
    mins = b.slider("min_samples (pontos mínimos por núcleo)", 2, 12, 5)
    db = dbscan_points(ctx.df, ctx.target_team, eps=eps, min_samples=mins)
    if db["pontos"].empty:
        empty_state("Sem recuperações de bola registradas para esta equipe.", icon="🟠")
    else:
        ctx.prov("dbscan", "DBSCAN", f"{db['n_clusters']} núcleos", f"DBSCAN em (x, y) das recuperações, eps={eps}, min_samples={mins}")
        st.plotly_chart(charts.dbscan_scatter(db, f"DBSCAN: {db['n_clusters']} armadilhas · {db['n_ruido']} pontos de ruído "
                                                  f"(eps = {eps} jd, min_samples = {mins})"), use_container_width=True)

    st.markdown("### NetworkX — grau × betweenness ponderada por xT")
    comp = centrality_comparison(ctx.df, ctx.target_team)
    if not comp.empty:
        ctx.prov("centr_insp", "Centralidades", len(comp), "grau ponderado e betweenness com distância 1/(passes·(1+10·xT))")
        st.plotly_chart(charts.centrality_compare(comp, "Lado a lado, normalizado pelo máximo da equipe"), use_container_width=True)


def render(ctx: MatchContext) -> None:
    page_header("🤖 Machine Learning & Inspeção de Treinamento",
                "O aprendizado em funcionamento: o que cada modelo usa, como foi avaliado e com quais hiperparâmetros.", ctx)
    report = load_protocol_report()
    t1, t2, t3 = st.tabs(["📊 Avaliação com baselines", "🌳 XGBoost", "🔵 Clusters & grafo da partida"])
    with t1:
        _baselines(ctx, report)
    with t2:
        _xgb(ctx, report)
    with t3:
        if ctx.has_events:
            _clusters(ctx)
        else:
            empty_state("Esta partida não tem coordenadas", "", "🗺️", "Escolha uma partida ✅ para ver clusters e grafo.")
    provenance_panel(ctx.registry)
