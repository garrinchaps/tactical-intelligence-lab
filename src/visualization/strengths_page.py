"""
Página 7 — Pontos Fortes e Fracos (percentil contextual).

Cada métrica mostra valor, mediana da referência, percentil, faixa (elite ≥ P90, forte ≥ P70, normal,
fraco ≤ P30, alerta ≤ P10) e o tamanho da amostra de referência (n). Com n < MIN_GROUP_SAMPLE a métrica
não recebe percentil: aparece como "amostra insuficiente" — e o radar só desenha o que tem amostra.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.intelligence.llm_analyst import GenerativeTacticalAnalyst
from src.metrics.strengths_weaknesses import (ALERT_PERCENTILE, ELITE_PERCENTILE, MIN_GROUP_SAMPLE, MIN_PLAYER_MINUTES,
                                              STRENGTH_PERCENTILE, WEAKNESS_PERCENTILE, ReferenceBaselineBuilder,
                                              StrengthsWeaknessesEngine)
from src.ui.components import comparison_table, empty_state, error_state, kpi, note, provenance_panel
from src.ui.theme import PALETTE, PLOTLY_LAYOUT

TIER_ORDER = ["elite", "forte", "normal", "fraco", "alerta", "amostra insuficiente"]


@st.cache_data(show_spinner=False)
def _cached_baselines(_load_events_fn: Callable, cache_key: str) -> Dict[str, Any]:
    return ReferenceBaselineBuilder.load_or_build(_load_events_fn)


def _items_df(items: List[Dict[str, Any]], technical: bool = False) -> pd.DataFrame:
    """Tabela para leitura rápida; `technical=True` mostra percentil, faixa e n (painel de detalhes)."""
    E = StrengthsWeaknessesEngine
    if technical:
        cols = ["Métrica", "Valor", "Mediana ref.", "Percentil", "Faixa", "n ref."]
        if not items:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame([{"Métrica": d["label"], "Valor": d["value"], "Mediana ref.": d.get("reference_median"),
                              "Percentil": d.get("percentile"), "Faixa": d.get("tier"), "n ref.": d.get("reference_n")}
                             for d in items])
    cols = ["Métrica", "No jogo", "Jogo típico", "Leitura"]
    if not items:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame([{"Métrica": d["label"], "No jogo": d["value"], "Jogo típico": d.get("reference_median"),
                          "Leitura": E.rank_phrase(d) or E.compare_words(d["value"], d.get("reference_median"))}
                         for d in items])


def radar(analysis: Dict[str, Any]) -> go.Figure:
    """Radar de percentis — só com métricas que têm n ≥ mínimo; o n entra no rótulo de cada eixo."""
    items = analysis["strengths"] + analysis["neutral"] + analysis["weaknesses"]
    labels = [d["label"] for d in items]
    values = [d["percentile"] for d in items]
    fig = go.Figure()
    if len(labels) >= 3:
        fig.add_trace(go.Scatterpolar(r=values + values[:1], theta=labels + labels[:1], fill="toself",
                                      name=analysis["entity"], line=dict(color=PALETTE["primary"], width=2),
                                      fillcolor="rgba(34,197,94,0.18)"))
        fig.add_trace(go.Scatterpolar(r=[50] * (len(labels) + 1), theta=labels + labels[:1], name="jogo típico",
                                      line=dict(color=PALETTE["muted"], dash="dot", width=1)))
    n_ins = len(analysis.get("insufficient", []))
    title = "Perfil do jogo (50 = jogo típico da base)" + (f" · {n_ins} métrica(s) sem base suficiente" if n_ins else "")
    fig.update_layout(**PLOTLY_LAYOUT, title=title, height=480,
                      polar=dict(bgcolor=PALETTE["surface"],
                                 radialaxis=dict(range=[0, 100], tickvals=[10, 30, 50, 70, 90], color=PALETTE["muted"]),
                                 angularaxis=dict(color=PALETTE["text"])))
    if len(labels) < 3:
        fig.add_annotation(text="amostra insuficiente para o radar (menos de 3 métricas com n ≥ "
                                f"{MIN_GROUP_SAMPLE})", showarrow=False, font=dict(color=PALETTE["warning"]))
    return fig


def render_strengths_weaknesses_page(ctx, load_events_fn: Callable, competition_of: Optional[Dict[int, str]] = None) -> None:
    df_events, target_team = ctx.df, ctx.target_team
    _how = (f"Percentil contra a mesma função (atletas, por 90 min, mínimo {MIN_PLAYER_MINUTES} min) ou contra todas "
         f"as equipes da referência. Faixas: elite ≥ P{ELITE_PERCENTILE:.0f} · forte ≥ P{STRENGTH_PERCENTILE:.0f} · "
         f"fraco ≤ P{WEAKNESS_PERCENTILE:.0f} · alerta ≤ P{ALERT_PERCENTILE:.0f}. Com menos de {MIN_GROUP_SAMPLE} "
         "referências a métrica não recebe percentil (amostra insuficiente). A referência usa partidas com eventos do "
         "banco local, sempre da mesma família de fonte (StatsBomb com StatsBomb, Wyscout com Wyscout, OpenPlay com OpenPlay).")
    a, b, c = st.columns([0.9, 2.0, 1.1])
    mode = a.radio("Analisar", ["Atleta", "Equipe"], horizontal=True)
    if mode == "Atleta":
        pl = df_events.loc[df_events["team_name"].notna(), ["player_name", "team_name"]].dropna().drop_duplicates()
        pl = pl[~pl["player_name"].astype(str).str.lower().isin(["não identificado", "nao identificado", "unknown"])]
        options = [f"{r.player_name} — {r.team_name}" for r in pl.itertuples()]
        idx = next((i for i, o in enumerate(options) if o.endswith(f"— {target_team}")), 0)
        chosen = b.selectbox("Atleta", options, index=idx) if options else None
        entity = chosen.split(" — ")[0] if chosen else None
    else:
        teams = df_events["team_name"].dropna().unique().tolist()
        entity = b.selectbox("Equipe", teams, index=teams.index(target_team) if target_team in teams else 0)
    use_llm = c.checkbox("Interpretação com Gemini (auditada pelo guard)", value=False)
    if not entity:
        empty_state("Nenhum atleta disponível nesta partida.")
        return
    try:
        with st.spinner("Montando a base de referência..."):
            ids = ReferenceBaselineBuilder.available_real_match_ids()
            baselines = _cached_baselines(load_events_fn, ",".join(map(str, ids)))
    except Exception as exc:
        error_state("Não foi possível montar a base de referência", exc)
        return
    if not baselines.get("match_ids"):
        empty_state("Base de referência vazia", "Abra ou sincronize partidas com eventos para formar a referência.", "📚",
                    "Na página Catálogo & Dados, sincronize a Copa 2022 (StatsBomb).")
        return
    try:
        if mode == "Atleta":
            an = StrengthsWeaknessesEngine.analyze_player(df_events, entity, baselines, exclude_match_id=int(ctx.match_id),
                                                         competition_of=competition_of)
        else:
            an = StrengthsWeaknessesEngine.analyze_team(df_events, ctx.chains, entity, baselines,
                                                       exclude_match_id=int(ctx.match_id))
    except Exception as exc:
        error_state(f"Não foi possível comparar '{entity}'", exc)
        return

    n_ref = an.get("reference_players_n", an.get("reference_teams_n", 0))
    prov = ctx.prov(f"sw_{entity}", f"Percentis de {entity}", n_ref,
                    f"percentil contextual contra {an['comparison_scope']} ({an['league_scope']}), n = {n_ref}")
    st.caption(f"Comparado com {n_ref} {an['comparison_scope']} de {an['reference_matches_n']} jogos reais "
               f"({an['league_scope']})" + (f" · {an['minutes']} min em campo" if "minutes" in an else ""))
    if an["evidence_grade"] == "LIMITADA":
        note("Base pequena", "Pouco tempo em campo ou poucos jogos para comparar: leia como indicação.", "warn")

    from src.ui.components import metric_bars
    from src.ui.glossary import what_is

    what_is(["Percentil", "xT", "PPDA", "Field Tilt", "xG"], key=f"sw_gloss_{entity}")
    tab1, tab4, tab2, tab3 = st.tabs(["🟢🔴 Fortes e fracos", "📊 Todas as métricas (fora da curva)",
                                      "🧠 Gráfico e interpretação", "🔬 Métricas avançadas"])
    with tab4:
        _outlier_tab(ctx, mode, entity)
    with tab1:
        s, w = st.columns(2)
        with s:
            st.markdown("#### 🟢 O que funcionou")
            metric_bars(an["strengths"], "forte", "Nada muito acima do normal neste jogo.")
        with w:
            st.markdown("#### 🔴 O que precisa melhorar")
            metric_bars(an["weaknesses"], "fraco", "Nada muito abaixo do normal neste jogo.")
    with tab2:
        r, t = st.columns([1.1, 1.0])
        r.plotly_chart(radar(an), use_container_width=True)
        with t:
            st.markdown("#### 🧠 Interpretação")
            res = GenerativeTacticalAnalyst().interpret_strengths_weaknesses(an, is_simulation=ctx.is_sim, prefer_llm=use_llm)
            st.caption(f"Motor: {res['engine_used']}" + (f" · guard: {res['guard_outcome']}" if res.get("guard_outcome") else ""))
            st.markdown(res["report_markdown"])
    with tab3:
        st.caption(_how)
        comparison_table(_items_df(an["strengths"] + an["neutral"] + an["weaknesses"], technical=True))
        if an.get("insufficient"):
            comparison_table(_items_df(an["insufficient"], technical=True), f"n < {MIN_GROUP_SAMPLE}: sem percentil.")
    provenance_panel(ctx.registry)


def _outlier_tab(ctx, mode: str, entity: str) -> None:
    """
    Todos os indicadores da avaliação 2.0 (≈35 por jogador), cada um contra jogadores da MESMA função, mostrando só o que
    foge da curva (≥ P85 ou ≤ P15). No modo equipe, a mesma régua aplicada a cada titular: quem puxa o time para cima/baixo.
    """
    from src.analytics.rating_v2 import outliers
    from src.ui.components import metric_bars
    from src.ui.context import match_ratings_v2

    v2 = match_ratings_v2(ctx.match_id, ctx.df)
    if v2.empty:
        st.caption("Sem lances suficientes para a avaliação 2.0.")
        return
    if mode == "Atleta":
        hit = v2[v2["jogador"] == entity]
        if hit.empty:
            st.caption("Atleta sem avaliação nesta partida (pouco tempo em campo).")
            return
        ev = hit.iloc[0]["_detalhe"]
        o = outliers(ev)
        st.caption(f"{len(ev['base'])} indicadores comparados com {ev['pares']} atuações de {ev['funcao']}s. "
                   "Só aparece o que está acima do P85 ou abaixo do P15 (já no sentido 'bom': menos perdas = melhor).")
        a, b = st.columns(2)
        to_items = lambda xs: [{"label": x["rotulo"], "value": round(float(x["valor"]), 2) if x["valor"] is not None else "—",
                                "percentile": x["percentil"], "reference_median": round(float(x["mediana_pares"]), 2)
                                if x.get("mediana_pares") is not None else "—"} for x in xs]
        with a:
            st.markdown("#### 🟢 Fora da curva para cima")
            metric_bars(to_items(o["fortes"]), "forte", "Nada acima do P85 nesta partida.")
        with b:
            st.markdown("#### 🔴 Fora da curva para baixo")
            metric_bars(to_items(o["fracos"]), "fraco", "Nada abaixo do P15 nesta partida.")
        return
    team = v2[(v2["equipe"] == entity) & v2["desempenho"].notna()]
    rows = []
    for r in team.itertuples():
        o = outliers(r._detalhe)
        if o["fortes"]:
            x = o["fortes"][0]
            rows.append({"label": f"{r.jogador}: {x['rotulo']}", "value": round(float(x['valor']), 2), "percentile": x["percentil"],
                         "reference_median": round(float(x["mediana_pares"]), 2) if x.get("mediana_pares") is not None else "—",
                         "_kind": "forte"})
        if o["fracos"]:
            x = o["fracos"][0]
            rows.append({"label": f"{r.jogador}: {x['rotulo']}", "value": round(float(x['valor']), 2), "percentile": x["percentil"],
                         "reference_median": round(float(x["mediana_pares"]), 2) if x.get("mediana_pares") is not None else "—",
                         "_kind": "fraco"})
    a, b = st.columns(2)
    with a:
        st.markdown(f"#### 🟢 Quem puxou {entity} para cima")
        metric_bars(sorted([r for r in rows if r["_kind"] == "forte"], key=lambda r: -r["percentile"]), "forte")
    with b:
        st.markdown(f"#### 🔴 Onde {entity} ficou abaixo")
        metric_bars(sorted([r for r in rows if r["_kind"] == "fraco"], key=lambda r: r["percentile"]), "fraco")
    st.caption("Cada linha = o indicador mais fora da curva de cada titular, comparado com jogadores da mesma função.")
