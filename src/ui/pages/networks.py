"""Página 2 — Redes de Passes & xT (topologia NetworkX e progressão)."""

from __future__ import annotations

import streamlit as st

from src.evaluation.inspection import centrality_comparison
from src.ingestion.brazil_and_multi_source import PlayerNameNormalizer
from src.metrics.xt_model import ExpectedThreatModel
from src.networks.pass_network import PassingNetworkAnalyzer
from src.ui import charts
from src.ui.components import comparison_table, empty_state, error_state, metric_card, page_header, provenance_panel, source_gap
from src.ui.context import MatchContext


VIEWS = {
    "min": "Os 11 em campo num minuto",
    "xi": "Os 11 titulares até a 1ª troca",
    "xi_full": "Os 11 titulares, jogo inteiro",
    "all": "Jogo inteiro, com quem entrou (marcado à parte)",
}


def render(ctx: MatchContext) -> None:
    from src.metrics.match_facts import lineup_split

    page_header("🕸️ Como o time trocou passes", "Quem organiza o jogo, quem liga a defesa ao ataque e quais jogadas "
                "mais aproximaram a bola do gol.", ctx)
    if not ctx.has_events:
        source_gap("eventos com coordenadas", ctx.bundle.source,
                   "Escolha uma partida ✅ (StatsBomb ou Wyscout) no topo.", "🕸️", ctx.bundle.level)
        return
    team, df = ctx.target_team, ctx.df
    starters, came_in = lineup_split(df, team)
    a, b = st.columns([2, 1])
    from src.ui.i18n import t

    view = a.radio(t("Quem aparece no campinho"), list(VIEWS), format_func=lambda k: t(VIEWS[k]), horizontal=True,
                   help="Com as trocas, o campinho chegava a ter 16 jogadores. Por padrão mostramos só o XI que "
                        "começou; na última opção, quem entrou aparece com bolinha vazada.")
    min_pass = int(b.number_input("Ligação só aparece com pelo menos … passes", min_value=1, max_value=10, value=2))
    from src.metrics.match_facts import on_field

    field = None
    d_net = df
    if view == "min":
        last = int(df["minute"].max()) if "minute" in df else 90
        minute = st.slider("Minuto do recorte", 0, max(last, 1), min(30, last), key="net_minute",
                           help="Mostra quem estava em campo neste minuto e como esses jogadores trocaram passes "
                                "enquanto estiveram juntos (da troca anterior até a seguinte).")
        field = on_field(df, team, minute)
        d_net = df[(df["minute"] >= field["de"]) & (df["minute"] < field["ate"])]
        st.caption(f"Em campo aos {minute}': {len(field['jogadores'])} jogadores · trecho analisado: "
                   f"{int(field['de'])}' a {int(field['ate'])}' (sem trocas no meio).")
    try:
        net = PassingNetworkAnalyzer.build_pass_network(
            d_net, team, until_first_sub=(view == "xi"), min_pass_count=min_pass,
            players_only=(field["jogadores"] if field else starters if view in ("xi", "xi_full") and starters else None))
        gm = net["graph_metrics"]
        xt = ExpectedThreatModel.compute_team_xt_summary(df, team)
    except Exception as exc:
        error_state("Não foi possível montar a rede", exc)
        return
    c = st.columns(4)
    with c[0]:
        metric_card("Desenho com a bola", gm.get("inferred_positional_structure", "—"),
                    ctx.prov("estrutura", "Desenho com a bola", gm.get("inferred_positional_structure"),
                             "agrupamento das posições médias dos jogadores quando o time trocava passes"),
                    f"até {gm.get('analyzed_until_minute', 90)}'")
    with c[1]:
        nm = PlayerNameNormalizer.to_common_name(str(gm.get("primary_bridge_player_betweenness", "—")))
        metric_card("Quem liga o time", nm, ctx.prov("pivo", "Quem liga o time", nm,
                                                     "jogador por onde mais passam os caminhos de passe entre os companheiros "
                                                     "(betweenness)"), f"índice {gm.get('primary_bridge_score', 0)}", "pos")
    with c[2]:
        nm2 = PlayerNameNormalizer.to_common_name(str(gm.get("primary_gravity_playmaker_pagerank", "—")))
        metric_card("Por quem a bola mais passa", nm2, ctx.prov("pagerank", "Por quem a bola mais passa", nm2,
                                                                "referência do time na troca de passes (PageRank ponderado)"),
                    f"até {gm.get('max_player_pass_share_pct', 0)}% dos passes num só jogador")
    with c[3]:
        v = round(xt.get("total_xt_generated", 0.0), 3)
        metric_card("Ameaça criada (xT)", f"+{v}", ctx.prov("xt", "Ameaça criada", v,
                                                          "soma do quanto cada passe e condução aproximou a bola do gol "
                                                          "(grade 12×8)"), "", "pos", unit="xT")
    from src.ui.glossary import what_is

    what_is(["xT"], key="net_gloss")
    subs_set = set(came_in) if view == "all" else set()
    l, r = st.columns(2)
    with l:
        st.plotly_chart(charts.pass_network(net, f"Troca de passes — {team}", subs=subs_set), use_container_width=True)
        st.caption("Bolinha maior = mais passes; verde mais forte = mais importante para ligar o time; linha mais grossa "
                   "= mais passes entre os dois.")
        if view == "all" and came_in:
            st.caption("Entraram no jogo: " + ", ".join(came_in) + ". A posição de quem entrou é a média do tempo que "
                       "jogou, por isso pode se sobrepor à de quem saiu.")
        elif came_in:
            st.caption(f"Mostrando só quem começou jogando ({len(starters)}). Quem entrou depois: "
                       + ", ".join(came_in) + ".")
    with r:
        st.plotly_chart(charts.xt_progression(df, team, f"Jogadas que mais aproximaram a bola do gol — {team}"),
                        use_container_width=True)
        st.caption("As 60 ações com maior ganho de ameaça (xT). Verde: passe · amarelo: condução.")

    st.markdown("##### Quem mais toca na bola × quem mais leva o time ao ataque")
    keep = set(field["jogadores"]) if field else set(starters) if view in ("xi", "xi_full") and starters else None
    d2 = df if keep is None else df[df["player_name"].isin(keep) | (df["team_name"] != team)]
    comp = centrality_comparison(d2, team)
    if comp.empty:
        empty_state("Sem passes certos suficientes para comparar.", icon="📉")
    else:
        ctx.prov("centralidades", "Volume × importância", f"{len(comp)} atletas",
                 "volume = passes dados+recebidos; importância = caminhos de passe que passam pelo jogador, pesando "
                 "mais os que levam a bola para zonas de ameaça (xT)")
        x, y = st.columns([1.2, 1])
        x.plotly_chart(charts.centrality_compare(comp, "Volume × importância para chegar ao ataque"), use_container_width=True)
        with y:
            nice = comp.rename(columns={"atleta": "Jogador", "grau_ponderado": "Passes dados + recebidos",
                                        "betweenness_xt": "Importância para ligar ao ataque", "rank_grau": "Posição no volume",
                                        "rank_betweenness": "Posição na importância"})
            comparison_table(nice, "Quando as duas listas não batem, o jogador pesa mais (ou menos) para levar a bola da "
                                   "saída de jogo até a área do que o número de passes sugere — é o caso do volante que toca "
                                   "pouco mas sempre para frente.")
    provenance_panel(ctx.registry)
