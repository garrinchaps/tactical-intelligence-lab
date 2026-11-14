"""
Gráficos interativos (Plotly) com o tema único. Coordenadas de campo no padrão StatsBomb
(120 × 80 jardas); eixos com unidades explícitas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.ui.theme import PALETTE, PLOTLY_LAYOUT

P = PALETTE
CLUSTER_COLORS = ["#22C55E", "#38BDF8", "#FBBF24", "#A78BFA", "#F472B6", "#F97316", "#2DD4BF", "#E879F9"]


def _layout(fig: go.Figure, title: str, height: int = 420, **kw) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT, title=dict(text=title, x=0.01, font=dict(size=15)), height=height, **kw)
    return fig


def pitch(fig: Optional[go.Figure] = None, title: str = "", height: int = 460) -> go.Figure:
    """Campo 120×80 desenhado com shapes (gramado, linhas, áreas, círculo central)."""
    fig = fig or go.Figure()
    line = dict(color=P["pitch_line"], width=1.6)
    shapes = [
        dict(type="rect", x0=0, y0=0, x1=120, y1=80, line=line, fillcolor=P["pitch"], layer="below"),
        dict(type="line", x0=60, y0=0, x1=60, y1=80, line=line, layer="below"),
        dict(type="circle", x0=50, y0=30, x1=70, y1=50, line=line, layer="below"),
        dict(type="rect", x0=0, y0=18, x1=18, y1=62, line=line, layer="below"),
        dict(type="rect", x0=102, y0=18, x1=120, y1=62, line=line, layer="below"),
        dict(type="rect", x0=0, y0=30, x1=6, y1=50, line=line, layer="below"),
        dict(type="rect", x0=114, y0=30, x1=120, y1=50, line=line, layer="below"),
        dict(type="line", x0=40, y0=0, x1=40, y1=80, line=dict(color=P["pitch_line"], width=0.8, dash="dot"), layer="below"),
        dict(type="line", x0=80, y0=0, x1=80, y1=80, line=dict(color=P["pitch_line"], width=0.8, dash="dot"), layer="below"),
    ]
    fig.update_layout(shapes=shapes)
    fig.update_xaxes(range=[-2, 122], showgrid=False, zeroline=False, title="comprimento (jardas) → ataque")
    fig.update_yaxes(range=[82, -2], showgrid=False, zeroline=False, title="largura (jardas)", scaleanchor="x", scaleratio=1)
    return _layout(fig, title, height)


def pass_network(net: Dict[str, Any], title: str) -> go.Figure:
    nodes, edges = net.get("nodes_df", pd.DataFrame()), net.get("edges_df", pd.DataFrame())
    fig = pitch(title=title, height=520)
    if nodes is None or nodes.empty:
        return fig
    pos = {r.player_name: (r.avg_x, r.avg_y) for r in nodes.itertuples()}
    if edges is not None and not edges.empty:
        wcol = next((c for c in ("pass_count", "weight", "passes") if c in edges.columns), None)
        src = next((c for c in ("passer", "source", "player_name") if c in edges.columns), None)
        dst = next((c for c in ("receiver", "target", "pass_recipient_name") if c in edges.columns), None)
        if wcol and src and dst:
            mx = max(edges[wcol].max(), 1)
            for r in edges.itertuples():
                a, b = getattr(r, src), getattr(r, dst)
                if a in pos and b in pos:
                    w = getattr(r, wcol)
                    fig.add_trace(go.Scatter(x=[pos[a][0], pos[b][0]], y=[pos[a][1], pos[b][1]], mode="lines",
                                             line=dict(color="rgba(56,189,248,0.55)", width=0.6 + 6 * w / mx),
                                             hoverinfo="text", text=f"{a} → {b}: {w} passes", showlegend=False))
    size_col = "passes_made" if "passes_made" in nodes.columns else None
    sizes = 14 + 26 * (nodes[size_col] / max(nodes[size_col].max(), 1)) if size_col else 20
    color = nodes["betweenness_centrality"] if "betweenness_centrality" in nodes.columns else P["primary"]
    fig.add_trace(go.Scatter(
        x=nodes["avg_x"], y=nodes["avg_y"], mode="markers+text", text=nodes["player_name"].str.split().str[-1],
        textposition="top center", textfont=dict(size=11, color=P["text"]),
        marker=dict(size=sizes, color=color, colorscale="Greens", line=dict(color=P["text"], width=1),
                    colorbar=dict(title="betweenness", thickness=10) if size_col else None),
        hovertext=[f"{r.player_name}<br>passes: {getattr(r, 'passes_made', '-')}<br>betweenness: "
                   f"{getattr(r, 'betweenness_centrality', 0):.3f}" for r in nodes.itertuples()],
        hoverinfo="text", showlegend=False))
    return fig


def xt_progression(df: pd.DataFrame, team: str, title: str) -> go.Figure:
    fig = pitch(title=title, height=480)
    d = df[(df["team_name"] == team) & df["type_name"].isin(["Pass", "Carry"]) & (df.get("is_pass_completed", 1) != 0)]
    d = d[d.get("delta_xt", 0) > 0].dropna(subset=["x", "y", "end_x", "end_y"]).sort_values("delta_xt", ascending=False).head(60)
    if d.empty:
        return fig
    mx = d["delta_xt"].max()
    for r in d.itertuples():
        fig.add_annotation(x=r.end_x, y=r.end_y, ax=r.x, ay=r.y, xref="x", yref="y", axref="x", ayref="y",
                           showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1 + 3 * r.delta_xt / mx,
                           arrowcolor="rgba(34,197,94,0.75)" if r.type_name == "Pass" else "rgba(251,191,36,0.75)")
    fig.add_trace(go.Scatter(x=d["x"], y=d["y"], mode="markers", marker=dict(size=6, color=P["primary"]),
                             hovertext=[f"{r.player_name} ({r.type_name})<br>ΔxT +{r.delta_xt:.3f}<br>minuto {r.minute}"
                                        for r in d.itertuples()], hoverinfo="text", showlegend=False))
    return fig


def kmeans_scatter(km: Dict[str, Any], title: str) -> go.Figure:
    fig = pitch(title=title)
    pts, cen = km.get("pontos", pd.DataFrame()), km.get("centroides", pd.DataFrame())
    if pts is None or pts.empty:
        return fig
    for c, g in pts.groupby("cluster"):
        n = int((cen.loc[cen["cluster"] == c, "n"].iloc[0])) if not cen.empty else len(g)
        fig.add_trace(go.Scatter(x=g["x"], y=g["y"], mode="markers", name=f"cluster {c} (n={n})",
                                 marker=dict(size=9, color=CLUSTER_COLORS[c % 8], opacity=0.8),
                                 hovertext=[f"{a} · {m}'" for a, m in zip(g["atleta"], g["minuto"])], hoverinfo="text"))
    fig.add_trace(go.Scatter(x=cen["x"], y=cen["y"], mode="markers+text", name="centróides",
                             marker=dict(symbol="x", size=18, color=P["text"], line=dict(width=2)),
                             text=[f"C{c}" for c in cen["cluster"]], textposition="bottom center"))
    return fig


def dbscan_scatter(db: Dict[str, Any], title: str) -> go.Figure:
    fig = pitch(title=title)
    pts = db.get("pontos", pd.DataFrame())
    if pts is None or pts.empty:
        return fig
    noise = pts[pts["cluster"] == -1]
    fig.add_trace(go.Scatter(x=noise["x"], y=noise["y"], mode="markers", name=f"ruído (n={len(noise)})",
                             marker=dict(size=8, color=P["danger"], symbol="x-thin", line=dict(width=2))))
    for c, g in pts[pts["cluster"] >= 0].groupby("cluster"):
        fig.add_trace(go.Scatter(x=g["x"], y=g["y"], mode="markers", name=f"armadilha {c} (n={len(g)})",
                                 marker=dict(size=10, color=CLUSTER_COLORS[c % 8], opacity=0.85)))
    return fig


def bar_h(df: pd.DataFrame, x: str, y: str, title: str, xtitle: str, color: str = None, height: int = 380) -> go.Figure:
    d = df.sort_values(x)
    fig = go.Figure(go.Bar(x=d[x], y=d[y], orientation="h", marker_color=color or P["primary"],
                           text=[f"{v:.1f}" if isinstance(v, float) else v for v in d[x]], textposition="outside"))
    fig.update_xaxes(title=xtitle)
    return _layout(fig, title, height)


def histogram(values, title: str, xtitle: str, nbins: int = 30, color: str = None) -> go.Figure:
    fig = go.Figure(go.Histogram(x=values, nbinsx=nbins, marker_color=color or P["secondary"]))
    fig.update_xaxes(title=xtitle)
    fig.update_yaxes(title="frequência")
    return _layout(fig, title, 320)


def confusion(cm: List[List[int]], title: str) -> go.Figure:
    z = np.array(cm)
    labels = [["VN", "FP"], ["FN", "VP"]]
    text = [[f"{labels[i][j]}<br>{z[i][j]}" for j in range(2)] for i in range(2)]
    fig = go.Figure(go.Heatmap(z=z, x=["previsto: sem perigo", "previsto: perigo"], y=["real: sem perigo", "real: perigo"],
                               text=text, texttemplate="%{text}", colorscale="Blues", showscale=False))
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, title, 340)


def loss_curve(history: Dict[str, List[float]], title: str) -> go.Figure:
    fig = go.Figure()
    ep = list(range(1, len(history.get("train_loss", [])) + 1))
    fig.add_trace(go.Scatter(x=ep, y=history.get("train_loss", []), mode="lines+markers", name="treino",
                             line=dict(color=P["primary"], width=2)))
    if history.get("val_loss"):
        fig.add_trace(go.Scatter(x=ep, y=history["val_loss"], mode="lines+markers", name="validação",
                                 line=dict(color=P["secondary"], width=2, dash="dot")))
    fig.update_xaxes(title="época")
    fig.update_yaxes(title="perda (entropia cruzada binária)")
    return _layout(fig, title, 340)


def nn_architecture(net, max_per_layer: int = 12, min_abs_weight: float = 0.0, title: str = "") -> go.Figure:
    """
    Arquitetura desenhada: neurônios por camada e conexões pai→filho com espessura ∝ |peso|
    (verde = peso positivo, vermelho = negativo). Camadas largas mostram os `max_per_layer`
    neurônios com maior soma de |pesos|, indicando quantos foram omitidos.
    """
    sizes = net.layer_sizes
    keep: List[List[int]] = []
    for l, s in enumerate(sizes):
        if s <= max_per_layer:
            keep.append(list(range(s)))
            continue
        if l == 0:
            score = np.abs(net.weights[0]).sum(axis=1)
        else:
            score = np.abs(net.weights[l - 1]).sum(axis=0) + (np.abs(net.weights[l]).sum(axis=1) if l < len(sizes) - 1 else 0)
        keep.append(sorted(np.argsort(-score)[:max_per_layer].tolist()))
    pos = {}
    for l, idxs in enumerate(keep):
        n = len(idxs)
        for rank, k in enumerate(idxs):
            pos[(l, k)] = (l, (rank - (n - 1) / 2) * 1.0)
    fig = go.Figure()
    allw = np.concatenate([np.abs(W).ravel() for W in net.weights])
    wmax = float(allw.max()) if allw.size else 1.0
    for l in range(len(sizes) - 1):
        W = net.weights[l]
        for p in keep[l]:
            for c in keep[l + 1]:
                w = float(W[p, c])
                if abs(w) < min_abs_weight:
                    continue
                (x0, y0), (x1, y1) = pos[(l, p)], pos[(l + 1, c)]
                fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", hoverinfo="text",
                                         text=f"{net.neuron_label(f'L{l}N{p}')} → {net.neuron_label(f'L{l + 1}N{c}')}: peso {w:+.3f}",
                                         line=dict(width=0.3 + 4.5 * abs(w) / wmax,
                                                   color="rgba(34,197,94,0.55)" if w > 0 else "rgba(248,113,113,0.55)"),
                                         showlegend=False))
    for l, idxs in enumerate(keep):
        xs = [pos[(l, k)][0] for k in idxs]
        ys = [pos[(l, k)][1] for k in idxs]
        labels = [net.neuron_label(f"L{l}N{k}") for k in idxs]
        bias = ["" if l == 0 else f"<br>viés {net.biases[l - 1][0, k]:+.3f}" for k in idxs]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text" if l in (0, len(sizes) - 1) else "markers",
                                 text=labels, textposition="middle left" if l == 0 else "middle right",
                                 marker=dict(size=16, color=P["secondary"] if l == 0 else (P["warning"] if l == len(sizes) - 1 else P["primary"]),
                                             line=dict(color=P["text"], width=1)),
                                 hovertext=[f"{lab} (L{l}N{k}){b}" for lab, k, b in zip(labels, idxs, bias)],
                                 hoverinfo="text", showlegend=False))
        omitted = sizes[l] - len(idxs)
        fig.add_annotation(x=l, y=max(ys) + 1.2, text=f"camada {l}<br>{sizes[l]} neurônios" +
                           (f"<br>({omitted} omitidos)" if omitted else ""), showarrow=False, font=dict(color=P["muted"], size=11))
    fig.update_xaxes(visible=False, range=[-1.2, len(sizes) - 0.2])
    fig.update_yaxes(visible=False)
    return _layout(fig, title or "Arquitetura e conexões pai → filho", 560)


def centrality_compare(df: pd.DataFrame, title: str) -> go.Figure:
    d = df.head(14).iloc[::-1]
    fig = go.Figure()
    gmax = max(d["grau_ponderado"].max(), 1)
    bmax = max(d["betweenness_xt"].max(), 1e-9)
    fig.add_trace(go.Bar(y=d["atleta"], x=d["grau_ponderado"] / gmax, orientation="h", name="grau ponderado (normalizado)",
                         marker_color=P["secondary"], hovertext=[f"grau {v:g}" for v in d["grau_ponderado"]], hoverinfo="text+y"))
    fig.add_trace(go.Bar(y=d["atleta"], x=d["betweenness_xt"] / bmax, orientation="h", name="betweenness ponderada por xT (normalizada)",
                         marker_color=P["primary"], hovertext=[f"betweenness {v:.3f}" for v in d["betweenness_xt"]], hoverinfo="text+y"))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="valor ÷ máximo da equipe")
    return _layout(fig, title, 520)


def heatmap_grid(z: pd.DataFrame, title: str, colorbar: str, text: Optional[np.ndarray] = None) -> go.Figure:
    fig = go.Figure(go.Heatmap(z=z.values, x=[str(c) for c in z.columns], y=[str(i) for i in z.index],
                               colorscale="Greens", colorbar=dict(title=colorbar), text=text,
                               texttemplate="%{text}" if text is not None else None))
    return _layout(fig, title, 380)


def ci_bars(df: pd.DataFrame, title: str, unit: str) -> go.Figure:
    d = df[df["value"].notna()]
    fig = go.Figure(go.Bar(x=d["zone"], y=d["value"], marker_color=P["warning"],
                           error_y=dict(type="data", symmetric=False, array=d["ci_high"] - d["value"],
                                        arrayminus=d["value"] - d["ci_low"], color=P["text"]),
                           hovertext=[f"{r.zone}: {r.value:g} (IC 95% {r.ci_low:g}–{r.ci_high:g}, n={r.n})" for r in d.itertuples()],
                           hoverinfo="text"))
    fig.update_yaxes(title=unit)
    fig.update_xaxes(title="zona (terço–faixa, referencial da equipe)")
    return _layout(fig, title, 380)


def grouped_bars(rows: pd.DataFrame, category: str, series: List[str], title: str, height: int = 420,
                 horizontal: bool = True) -> go.Figure:
    """Barras agrupadas: uma barra por série (equipe, partida ou atleta) para cada categoria (indicador)."""
    colors = [P["primary"], P["secondary"], P["warning"], "#C084FC", "#F472B6", "#94A3B8", "#FB923C", "#2DD4BF"]
    fig = go.Figure()
    for i, s in enumerate(series):
        vals = pd.to_numeric(rows[s], errors="coerce")
        if horizontal:
            fig.add_trace(go.Bar(y=rows[category], x=vals, name=str(s), orientation="h", marker_color=colors[i % len(colors)],
                                 text=[f"{v:g}" if pd.notna(v) else "" for v in vals], textposition="outside"))
        else:
            fig.add_trace(go.Bar(x=rows[category], y=vals, name=str(s), marker_color=colors[i % len(colors)]))
    fig.update_layout(barmode="group")
    if horizontal:
        fig.update_yaxes(autorange="reversed")
    return _layout(fig, title, height)


def lines(df: pd.DataFrame, x: str, ys: List[str], title: str, ytitle: str = "", height: int = 380) -> go.Figure:
    colors = [P["primary"], P["secondary"], P["warning"], "#C084FC", "#F472B6", "#94A3B8"]
    fig = go.Figure()
    for i, c in enumerate(ys):
        fig.add_trace(go.Scatter(x=df[x], y=df[c], name=c, mode="lines+markers", line=dict(color=colors[i % len(colors)], width=2)))
    fig.update_yaxes(title=ytitle)
    return _layout(fig, title, height)


def radar(values: Dict[str, List[float]], labels: List[str], title: str, height: int = 460) -> go.Figure:
    colors = [P["secondary"], P["warning"], P["primary"], "#C084FC"]
    fig = go.Figure()
    for i, (name, v) in enumerate(values.items()):
        fig.add_trace(go.Scatterpolar(r=list(v) + list(v[:1]), theta=labels + labels[:1], fill="toself", name=name,
                                      line=dict(color=colors[i % len(colors)], width=2)))
    fig.update_layout(polar=dict(bgcolor=P["surface"], radialaxis=dict(range=[0, 100], color=P["muted"])))
    return _layout(fig, title, height)


def shot_map(shots: pd.DataFrame, home: str, title: str) -> go.Figure:
    """Finalizações no campo: mandante atacando para a direita, visitante para a esquerda; tamanho ∝ xG; ★ = gol."""
    fig = pitch(title=title)
    for side, color in (("h", P["secondary"]), ("a", P["warning"])):
        s = shots[shots["lado"] == side]
        if s.empty:
            continue
        x = s["x"] if side == "h" else 120 - s["x"]
        y = s["y"] if side == "h" else 80 - s["y"]
        goal = s["resultado"].isin(["gol"])
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="markers", name=str(s["equipe"].iloc[0]),
            marker=dict(size=8 + 40 * s["xg"].clip(0, 1), color=color, line=dict(color=P["text"], width=goal.map({True: 2.5, False: 0.5})),
                        symbol=["star" if g else "circle" for g in goal], opacity=0.85),
            hovertext=[f"{r.minuto}' {r.jogador} — {r.resultado}, xG {r.xg:.2f} ({r.situacao})" for r in s.itertuples()],
            hoverinfo="text"))
    return fig
