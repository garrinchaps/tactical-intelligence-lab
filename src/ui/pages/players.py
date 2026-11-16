"""Página 5 — Jogadores: elenco por setor, substituições sugeridas, dossiê e comparador (radar com n)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ui.components import render_chart

from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.reports.report_builder import TacticalReportBuilder
from src.ui.components import comparison_table, empty_state, error_state, note, page_header, provenance_panel, source_gap
from src.ui.context import MatchContext
from src.ui.theme import PALETTE, PLOTLY_LAYOUT

SECTORS = [
    ("Goleiro & defesa", ["Goalkeeper", "Back"]),
    ("Volantes & construção", ["Defensive Midfield", "Center Midfield"]),
    ("Meias & extremos", ["Attacking Midfield", "Wing", "Left Midfield", "Right Midfield"]),
    ("Ataque", ["Forward", "Striker"]),
]
RADAR = [("passes_completed", "Passes completos"), ("press_retention_pct", "Retenção sob pressão (%)"),
         ("progressive_actions", "Ações progressivas"), ("line_breaking_passes", "Passes quebra-linhas"),
         ("xt_generated", "xT gerado"), ("ball_recoveries", "Recuperações")]
MIN_RADAR_MINUTES = 20


def _squad(ctx: MatchContext, players_df: pd.DataFrame) -> None:
    ctx.prov("elenco", "Desempenho individual", len(players_df), "PlayerTacticalEvaluator sobre os eventos da partida")
    st.markdown("#### Matriz de profundidade por setor")
    cols = st.columns(4)
    for i, (title, kws) in enumerate(SECTORS):
        sec = players_df[players_df["position_name"].apply(lambda p: any(k.lower() in str(p).lower() for k in kws))]
        rows = "".join(f'<div class="p"><b>{p.player_name}</b> <span class="m">{p.estimated_minutes_active}\'</span><br>'
                       f'<span class="m">xT +{p.xt_generated:.3f} · passe {p.pass_accuracy_pct}% · score {p.tactical_impact_score}</span></div>'
                       for p in sec.head(5).itertuples()) or '<div class="m">Sem atletas neste setor.</div>'
        cols[i].markdown(f'<div class="til-depth"><div class="h">{title}</div>{rows}</div>', unsafe_allow_html=True)

    st.markdown("#### Substituições sugeridas (queda após o minuto 60)")
    subs = PlayerTacticalEvaluator.recommend_tactical_substitutions(ctx.df, ctx.target_team)
    if subs["recommended_substitutions"]:
        for rec in subs["recommended_substitutions"]:
            note(f"⚠️ {rec['candidate_out']} ({rec['position']}) — prioridade {rec['priority_score']}",
                 f"Evidência: {' '.join(rec['tactical_reasons'])} · Perfil para entrar: {rec['ideal_replacement_profile']} · "
                 f"Risco: {' '.join(rec['structural_risks_of_substitution'])}", "warn")
    else:
        note("Sem queda crítica", "Nenhum titular teve queda técnica crítica após o minuto 60.")
    st.caption(subs["data_limitations_notice"])
    with st.expander("Tabela completa de desempenho individual"):
        comparison_table(players_df)


def _radar(players_df: pd.DataFrame, a: str, b: str) -> go.Figure:
    """Normaliza pelo máximo da equipe NA PARTIDA; o n (atletas com ≥ 20 min) aparece no título."""
    pool = players_df[players_df["estimated_minutes_active"] >= MIN_RADAR_MINUTES]
    fig = go.Figure()
    n = len(pool)
    if n < 3:
        fig.add_annotation(text=f"amostra insuficiente (n = {n} atletas com ≥ {MIN_RADAR_MINUTES} min)", showarrow=False,
                           font=dict(color=PALETTE["warning"]))
    else:
        mx = {c: max(float(pool[c].max()), 1e-4) for c, _ in RADAR}
        labels = [l for _, l in RADAR]
        for name, color, fill in ((a, "#3B82F6", "rgba(59,130,246,0.28)"), (b, "#EF4444", "rgba(239,68,68,0.25)")):
            row = players_df[players_df["player_name"] == name]
            if row.empty:
                continue
            r = row.iloc[0]
            vals = [round(100 * float(r[c]) / mx[c], 1) for c, _ in RADAR]
            fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself", fillcolor=fill,
                                          name=f"{name} ({r['estimated_minutes_active']}')", line=dict(color=color, width=2)))
    fig.update_layout(**PLOTLY_LAYOUT, height=460,
                      title=f"% do máximo da equipe nesta partida · n = {n} atletas com ≥ {MIN_RADAR_MINUTES} min",
                      polar=dict(bgcolor=PALETTE["surface"], radialaxis=dict(range=[0, 100], color=PALETTE["muted"])))
    return fig


def _scout(ctx: MatchContext, players_df: pd.DataFrame) -> None:
    a, b = st.columns([2.2, 1.0])
    player = a.selectbox("Atleta (qualquer equipe)", ctx.players)
    b.write("")
    if b.button("Gerar dossiê do atleta", type="primary", use_container_width=True) and player:
        md = TacticalReportBuilder.prepend_simulation_badge(
            TacticalReportBuilder.build_dedicated_player_scouting_report(ctx.df, player), ctx.is_sim)
        st.markdown(md)
        st.download_button(f"Baixar dossiê de {player} (.md)", data=md,
                           file_name=f"scout_{player.lower().replace(' ', '_')}.md", mime="text/markdown")
    st.markdown("#### Comparador direto (radar)")
    if len(players_df) >= 2:
        names = players_df["player_name"].tolist()
        c1, c2 = st.columns(2)
        pa = c1.selectbox("Atleta A", names, index=0)
        pb = c2.selectbox("Atleta B", names, index=1)
        ctx.prov("radar", "Radar comparativo", f"{pa} x {pb}", "percentual do máximo da equipe na partida")
        render_chart(_radar(players_df, pa, pb), use_container_width=True)
        if ctx.is_sim:
            note("Partida simulada", "Os valores individuais vêm do gerador por perfis: comparação ilustrativa.", "warn")


def _with_market_value(s: pd.DataFrame, ctx: MatchContext) -> pd.DataFrame:
    """Acrescenta o valor de mercado (Transfermarkt) pelo mapeamento de IDs da base unificada, quando existir."""
    try:
        from src.data_lake.build import market_values

        mv = market_values()
    except Exception:
        return s
    if mv.empty:
        return s
    src = ctx.bundle.source
    m = mv[mv["fonte"] == src][["nome", "valor_mercado_eur"]].drop_duplicates("nome")
    out = s.merge(m.rename(columns={"nome": "jogador", "valor_mercado_eur": "valor_mercado_eur"}), on="jogador", how="left")
    if out["valor_mercado_eur"].notna().any():
        out["valor de mercado (€ mi, Transfermarkt)"] = (out.pop("valor_mercado_eur") / 1e6).round(1)
    else:
        out = out.drop(columns=["valor_mercado_eur"])
    return out


RATING_HELP = ("Avaliação 3.0: indicadores comparados com pares da mesma função; pesos mistos quando os eventos mostram "
               "mais de um papel. A régua tem centro em P50 = 6,4 e P90 = 8,6. A nota final combina desempenho com "
               "eventos decisivos observáveis (gols, assistências, defesas-chave e pênaltis defendidos); desempenho base "
               "e impacto ficam separados. Menos de 15 min: sem nota. Dado ausente nunca vira zero; trabalho sem bola "
               "só é avaliado quando existe evidência registrada.")


def _stats_table(ctx: MatchContext) -> None:
    from src.metrics.match_facts import PLAYER_STAT_LABELS, per90
    from src.metrics.player_rating import CATEGORIES

    a, b, c = st.columns([1.4, 1.2, 1])
    from src.ui.i18n import t

    who = a.radio(t("Atletas de"), [ctx.target_team, ctx.opponent, "Ambas as equipes"], horizontal=True, key="ps_team",
                  format_func=t)
    cat = b.radio(t("Mostrar"), ["Nota", *CATEGORIES, "Tudo"], horizontal=True, key="ps_cat", format_func=t)
    mode = c.radio(t("Valores"), ["Totais", "Por 90 minutos"], horizontal=True, key="ps_mode", format_func=t)
    from src.ui.context import match_ratings

    s = match_ratings(ctx.match_id, None if who == "Ambas as equipes" else who, ctx.df)
    v2 = pd.DataFrame()
    try:
        from src.ui.context import match_ratings_v2

        v2 = match_ratings_v2(ctx.match_id, ctx.df)
    except Exception:
        v2 = pd.DataFrame()
    if s.empty:
        empty_state("Sem atletas com eventos.")
        return
    if mode == "Por 90 minutos":
        s = per90(s)
        note("Por 90 minutos", "As estatísticas são normalizadas por 90 minutos; nota, desempenho, impacto e confiança continuam na escala 0–10 original.", "warn")
    # A nota não pode ser multiplicada por 90: incorporamos o resultado 3.0 depois da normalização das contagens.
    if not v2.empty:
        cols_v2 = [c for c in ("jogador", "nota", "nota_final", "desempenho", "impacto", "confianca",
                               "confianca_pct", "classificacao", "amostra", "dim_tatica") if c in v2.columns]
        s = s.merge(v2[cols_v2].drop_duplicates("jogador"), on="jogador", how="left", suffixes=("", "_v3"))
        if "nota_v3" in s:
            s["nota"] = s["nota_v3"]
        if "nota_final" in s:
            s["nota"] = s["nota_final"]
    ctx.prov("ps_table", "Estatísticas individuais", len(s), "contagem de eventos por atleta; minutos estimados pelas substituições")
    ctx.prov("nota", "Nota final 3.0 da atuação (0–10)", "por jogador",
             "percentis por função + papéis mistos + impacto decisivo observável; dados ausentes reduzem cobertura", tier="DERIVED")
    s = _with_market_value(s, ctx)
    labels = {**PLAYER_STAT_LABELS, "nota": "Nota final 3.0 (0–10)", "setor": "Setor", "obs_nota": "Obs. da nota",
              "desempenho": "Desempenho base (0–10)", "nota_final": "Nota final (0–10)",
              "impacto": "Impacto (0–10)", "confianca": "Confiança", "confianca_pct": "Confiança (%)",
              "defesas_goleiro": "Defesas (goleiro)", "gols_sofridos_goleiro": "Gols sofridos (goleiro)"}
    base = ["jogador", "equipe", "posicao", "setor", "nota", "minutos"]
    if cat == "Nota":
        cols = base + ["desempenho", "impacto", "confianca", "confianca_pct", "classificacao", "gols", "assistencias",
                       "xg", "xt", "passes_certos", "acoes_defensivas", "passes_errados", "perdas_de_posse"]
    elif cat == "Tudo":
        cols = list(s.columns)
    else:
        cols = base + CATEGORIES[cat] + (["defesas_goleiro", "gols_sofridos_goleiro"] if cat == "Defesa" else [])
    cols = [x for x in dict.fromkeys(cols) if x in s.columns]
    order_opts = [x for x in cols if x not in ("jogador", "equipe", "posicao", "setor", "obs_nota")]
    order = st.selectbox("Ordenar por", order_opts, index=order_opts.index("nota") if "nota" in order_opts else 0,
                         format_func=lambda k: labels.get(k, k), key=f"ps_order_{cat}")
    view = s[cols].sort_values(order, ascending=False, na_position="last")
    st.caption("🏅 " + RATING_HELP)
    from src.ui.components import clickable_table

    clickable_table(view.rename(columns={"jogador": "Jogador", "equipe": "Equipe", "posicao": "Posição", **labels}),
                    f"ps_click_{cat}", "Jogador", "jogador",
                    "Contagens diretas dos eventos da partida. Assistência = último passe certo para o autor do gol.")
    st.download_button("Baixar tabela (.csv)", view.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"atletas_{ctx.match_id}.csv", mime="text/csv")
    _rating_report(ctx)


def _rating_report(ctx: MatchContext) -> None:
    """Relatório da atuação (avaliação 2.0): três números, radar das dimensões e o porquê."""
    from src.analytics.rating_v2 import report
    from src.ui.context import match_ratings_v2

    v2 = match_ratings_v2(ctx.match_id, ctx.df)
    if v2.empty:
        return
    st.markdown("#### 🏅 Relatório da atuação")
    pick = st.selectbox("Jogador", v2["jogador"].tolist(), key="rr_pick")
    ev = v2[v2["jogador"] == pick].iloc[0]["_detalhe"]
    k = st.columns(3)
    for col, lab, val, sub in ((k[0], "Desempenho", ev["desempenho"], ev["classificacao"]),
                               (k[1], "Impacto na partida", ev["impacto"], "gols, assistências e erros decisivos"),
                               (k[2], "Confiança", f"{ev['confianca_pct']}%", f"{ev['confianca']} · {ev['amostra']}")):
        col.markdown(f'<div class="til-card" style="min-height:auto"><div class="label">{lab}</div><div class="value">'
                     f'{val if val is not None else "—"}</div><div style="color:#94A3B8;font-size:.82rem">{sub}</div></div>',
                     unsafe_allow_html=True)
    a, b = st.columns([1, 1.1])
    dims = [(ev["dimensoes_pt"][d], v) for d, v in ev["dimensoes"].items()]
    obs = [(lab, v) for lab, v in dims if v is not None]
    if len(obs) >= 3:
        fig = go.Figure(go.Scatterpolar(r=[v for _, v in obs] + [obs[0][1]], theta=[l for l, _ in obs] + [obs[0][0]],
                                        fill="toself", fillcolor="rgba(34,211,238,0.25)", line=dict(color="#22D3EE", width=2),
                                        hovertemplate="%{theta}: %{r:.1f}<extra></extra>"))
        fig.update_layout(**PLOTLY_LAYOUT, height=380, title=f"Dimensões — {pick} ({ev['funcao']})",
                          polar=dict(bgcolor=PALETTE["surface"], radialaxis=dict(range=[0, 10], color=PALETTE["muted"])))
        a.plotly_chart(fig, use_container_width=True)
    with b:
        st.markdown(report(ev))
        w = ev["pesos"]
        rows = [{"Dimensão": ev["dimensoes_pt"][d], "Nota": v, "Peso na função": f"{w[d]}%"} for d, v in ev["dimensoes"].items()]
        comparison_table(pd.DataFrame(rows), "Dimensão sem dado aparece vazia e não entra na conta (o peso é redistribuído).")


def render(ctx: MatchContext) -> None:
    page_header("👤 Jogadores", f"Elenco de {ctx.target_team}, substituições, dossiê individual e comparador.", ctx)
    if not ctx.has_events:
        ps = ctx.bundle.boxscore.get("player_stats") if ctx.bundle.boxscore else None
        if ps is not None and not ps.empty:
            ctx.prov("ps", "Estatísticas individuais", len(ps), "lidas da fonte", raw=True)
            st.markdown("Estatísticas individuais da fonte (sem coordenadas):")
            flat = ps.drop(columns=["stats_json", "match_id"], errors="ignore").copy()
            extra = pd.json_normalize(flat.pop("stats")) if "stats" in flat else pd.DataFrame()
            comparison_table(pd.concat([flat.reset_index(drop=True), extra], axis=1))
            provenance_panel(ctx.registry)
        else:
            source_gap("estatísticas individuais de atletas", ctx.bundle.source,
                       "Escolha uma partida ✅ (eventos) para o scout completo.", "👤", ctx.bundle.level)
        return
    players_df = PlayerTacticalEvaluator.evaluate_team_players(ctx.df, ctx.target_team)
    from src.ui.i18n import t as _t

    t0, t1, t2 = st.tabs([_t(x) for x in ("📋 Estatísticas individuais", "🧩 Elenco & substituições", "🕵️ Dossiê & comparador")])
    with t0:
        try:
            _stats_table(ctx)
        except Exception as exc:
            error_state("Estatísticas indisponíveis", exc)
    with t1:
        try:
            _squad(ctx, players_df)
        except Exception as exc:
            error_state("Elenco indisponível", exc)
    with t2:
        try:
            _scout(ctx, players_df)
        except Exception as exc:
            error_state("Scout indisponível", exc)
    provenance_panel(ctx.registry)
