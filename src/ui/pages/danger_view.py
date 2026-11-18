"""
Rodada 8 — a rede neural do laboratório (modelo campeão de "perigo da posse") na página do jogo.

Para cada passe/condução, a rede estima a chance de a posse terminar em finalização da equipe. Aqui ela vira:
quem mais criou perigo, de onde saíram as ações perigosas e o total de perigo de cada time.
Só existe em jogos com todos os lances (coordenadas); jogos só com estatísticas não têm ações para avaliar.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ui.components import comparison_table, render_chart


@st.cache_data(show_spinner=False, max_entries=12)
def _scored(match_id: int, champ_key: str, _df: pd.DataFrame) -> pd.DataFrame:
    from src.machine_learning.model_registry import champion_cached, score_actions

    return score_actions(_df, champion_cached())


def _champ_key() -> str:
    from src.machine_learning.model_registry import ROOT

    p = ROOT / "registry.json"
    return str(p.stat().st_mtime) if p.exists() else "0"


def _pt(name: str) -> str:
    try:
        from src.ui.names import pt

        return pt(name)
    except Exception:
        return name


def render(ctx, focus: str | None = None) -> None:
    from src.machine_learning.model_registry import DANGER_THRESHOLD, danger_by_player, model_card

    st.markdown("#### 🧠 Perigo criado — rede neural do laboratório")
    if not ctx.has_events:
        st.info("A rede neural avalia cada passe e condução pela posição no campo, distância e ângulo do gol, "
                "pressão de adversários e passes na jogada. Este jogo não tem os lances com coordenadas — só "
                "estatísticas —, então não há ações para ela avaliar. Use a seção 📊 Resumo/👤 Jogadores (FotMob).")
        return
    card = model_card() or {}
    with st.spinner("A rede está avaliando cada ação do jogo…"):
        try:
            sco = _scored(int(ctx.match_id), _champ_key(), ctx.df)
        except Exception as exc:
            st.warning(f"Não foi possível avaliar as ações: {type(exc).__name__}.")
            return
    if sco is None or sco.empty:
        st.info("Nenhuma ação avaliável (passes/conduções com posição) neste jogo.")
        return
    st.caption(f"Modelo em uso: {card.get('versao', '—')} · AUC de validação {card.get('auc_validacao', '—')} · "
               f"treinado com {card.get('partidas_de_treino', '—')} partidas. Cada número é uma ESTIMATIVA da chance "
               f"de a jogada terminar em finalização; ação 'perigosa' = chance ≥ {int(100 * DANGER_THRESHOLD)}%.")
    teams = [t for t in sco["team_name"].dropna().unique()]
    cols = st.columns(max(1, len(teams)))
    for col, t in zip(cols, teams):
        s = sco[sco["team_name"] == t]
        col.metric(f"{_pt(t)} — ações perigosas", int((s["p_perigo"] >= DANGER_THRESHOLD).sum()),
                   help=f"Passes e conduções com chance estimada ≥ {int(100 * DANGER_THRESHOLD)}% de a jogada terminar em finalização.")
        col.caption(f"em {len(s)} ações avaliadas · chance média por ação {100 * s['p_perigo'].mean():.1f}%")
    side = st.radio("Time", teams, horizontal=True, key="danger_team", format_func=_pt,
                    index=teams.index(focus) if focus in teams else 0)
    s = sco[sco["team_name"] == side]
    top = danger_by_player(s, side, 10)
    if top:
        by = s.groupby("player_name")["p_perigo"].sum()
        comparison_table(pd.DataFrame([{"jogador": r["jogador"], "ações perigosas": r["acoes_perigosas"],
                                        "ações avaliadas": r["acoes"], "índice de perigo": round(float(by.get(r["jogador"], 0)), 2),
                                        "maior chance (%)": r["maior_chance_pct"]} for r in top]),
                         "Quem mais colocou o time perto do chute, segundo a rede. Índice de perigo = soma das chances "
                         "das ações do jogador (serve para comparar jogadores do mesmo jogo, não é nº de chutes).")
    else:
        st.caption("Nenhuma ação passou do limiar de perigo para este time.")
    from src.ui.charts import pitch

    fig = pitch(title=f"De onde saíram as ações de {_pt(side)} (cor = chance estimada de virar finalização)", height=480)
    ss = s.dropna(subset=["x", "y"]).sort_values("p_perigo")
    fig.add_trace(go.Scatter(x=ss["x"], y=ss["y"], mode="markers",
                             marker=dict(size=5 + 22 * ss["p_perigo"], color=ss["p_perigo"], cmin=0, cmax=0.6,
                                         colorscale=[[0, "#1E2A44"], [0.5, "#22D3EE"], [1, "#EF4444"]],
                                         line=dict(width=0), opacity=0.85,
                                         colorbar=dict(title="chance", tickformat=".0%")),
                             text=[f"{p} · {m}' · {v:.0%}" for p, m, v in zip(ss["player_name"], ss["minute"], ss["p_perigo"])],
                             hoverinfo="text", showlegend=False))
    render_chart(fig)
