"""Página 2 — Redes de Passes & xT (topologia NetworkX e progressão)."""

from __future__ import annotations

import streamlit as st

from src.evaluation.inspection import centrality_comparison
from src.ingestion.brazil_and_multi_source import PlayerNameNormalizer
from src.metrics.xt_model import ExpectedThreatModel
from src.networks.pass_network import PassingNetworkAnalyzer
from src.ui import charts
from src.ui.components import comparison_table, empty_state, error_state, metric_card, page_header, provenance_panel
from src.ui.context import MatchContext


def render(ctx: MatchContext) -> None:
    page_header("🕸️ Redes de Passes & xT", "Quem conecta a equipe, por onde a bola progride e quanto de ameaça cada ação gera.", ctx)
    if not ctx.has_events:
        empty_state("Precisa de eventos com coordenadas", "Esta partida só tem boxscore.", "🕸️",
                    "Escolha uma partida ✅ (StatsBomb ou Wyscout) na barra lateral.")
        return
    team, df = ctx.target_team, ctx.df
    a, b = st.columns([2, 1])
    until_sub = a.toggle("Rede até a 1ª substituição (estrutura dos titulares)", value=True)
    min_pass = int(b.number_input("Mínimo de passes por conexão", min_value=1, max_value=10, value=2))
    try:
        net = PassingNetworkAnalyzer.build_pass_network(df, team, until_first_sub=until_sub, min_pass_count=min_pass)
        gm = net["graph_metrics"]
        xt = ExpectedThreatModel.compute_team_xt_summary(df, team)
    except Exception as exc:
        error_state("Não foi possível montar a rede", exc)
        return
    c = st.columns(4)
    with c[0]:
        metric_card("Estrutura em posse", gm.get("inferred_positional_structure", "—"),
                    ctx.prov("estrutura", "Estrutura", gm.get("inferred_positional_structure"),
                             "agrupamento das posições médias dos atletas na rede"), f"até {gm.get('analyzed_until_minute', 90)}'")
    with c[1]:
        nm = PlayerNameNormalizer.to_common_name(str(gm.get("primary_bridge_player_betweenness", "—")))
        metric_card("Pivô (betweenness)", nm, ctx.prov("pivo", "Pivô", nm, "maior betweenness na rede de passes"),
                    f"score {gm.get('primary_bridge_score', 0)}", "pos")
    with c[2]:
        nm2 = PlayerNameNormalizer.to_common_name(str(gm.get("primary_gravity_playmaker_pagerank", "—")))
        metric_card("Centro de gravidade (PageRank)", nm2, ctx.prov("pagerank", "PageRank", nm2, "maior PageRank ponderado"),
                    f"share máx. {gm.get('max_player_pass_share_pct', 0)}%")
    with c[3]:
        v = round(xt.get("total_xt_generated", 0.0), 3)
        metric_card("xT gerado", f"+{v}", ctx.prov("xt", "xT gerado", v, "Σ ΔxT positivo de passes e conduções (grade 12×8)"),
                    f"densidade {gm.get('network_density', 0)}", "pos", unit="xT")
    l, r = st.columns(2)
    with l:
        st.plotly_chart(charts.pass_network(net, f"Rede de passes — {team} (tamanho = passes; cor = betweenness)"),
                        use_container_width=True)
    with r:
        st.plotly_chart(charts.xt_progression(df, team, f"60 ações de maior ΔxT — {team} (verde: passe · amarelo: condução)"),
                        use_container_width=True)

    st.markdown("##### Grau ponderado × betweenness ponderada por xT")
    comp = centrality_comparison(df, team)
    if comp.empty:
        empty_state("Sem passes certos suficientes para comparar centralidades.", icon="📉")
    else:
        ctx.prov("centralidades", "Centralidades", f"{len(comp)} atletas",
                 "grau = passes dados+recebidos; betweenness com distância 1/(passes·(1+10·xT médio))")
        x, y = st.columns([1.2, 1])
        x.plotly_chart(charts.centrality_compare(comp, "Centralidade por atleta (normalizada pelo máximo da equipe)"),
                       use_container_width=True)
        with y:
            comparison_table(comp, "Quando os rankings divergem, o atleta é mais (ou menos) decisivo para ligar a "
                                   "construção às zonas de ameaça do que o volume de passes sugere.")
    provenance_panel(ctx.registry)
