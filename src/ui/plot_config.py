"""
Rodada 20 — gráficos sem barra de ferramentas e sem zoom.

A barra do Plotly (câmera, lupa, setas, casinha) aparecia por cima dos títulos e, no celular, qualquer toque
arrastava/ampliava o campinho. Aqui o `plotly_chart` do Streamlit é envolvido UMA vez: toda figura sai sem a barra,
sem zoom por rolagem/duplo toque e com os eixos travados (o passar do dedo/mouse continua mostrando os valores).
"""

from __future__ import annotations

NO_TOOLS = {"displayModeBar": False, "scrollZoom": False, "doubleClick": False, "showTips": False}


def lock_figure(figure):
    try:
        import plotly.graph_objects as go

        fig = go.Figure(figure)
        fig.update_layout(dragmode=False)
        fig.update_xaxes(fixedrange=True)
        fig.update_yaxes(fixedrange=True)
        return fig
    except Exception:
        return figure


def install() -> None:
    import streamlit as st
    from streamlit.delta_generator import DeltaGenerator

    if getattr(DeltaGenerator.plotly_chart, "_til_locked", False):
        return
    original = DeltaGenerator.plotly_chart

    def plotly_chart(self, figure_or_data, *args, **kwargs):
        cfg = dict(kwargs.pop("config", None) or {})
        for k, v in NO_TOOLS.items():
            cfg.setdefault(k, v)
        kwargs["config"] = cfg
        return original(self, lock_figure(figure_or_data), *args, **kwargs)

    plotly_chart._til_locked = True
    DeltaGenerator.plotly_chart = plotly_chart
    st.plotly_chart = lambda *a, **k: plotly_chart(st._main, *a, **k)
