"""Rodada 10 — "🔬 Inteligência do jogador": lance, partida ou vários jogos, por área, com fato/padrão/interpretação/hipótese."""

from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from src.intelligence.lab_ai import availability as A
from src.intelligence.lab_ai import player_intel as P

AREAS = ["técnica", "ofensiva", "criação", "defensiva", "decisão", "risco", "eficiência", "tempo", "contexto",
         "consistência", "tendência", "amostra", "limite"]
COLORS = {"fato": "#3B82F6", "padrão": "#22D3EE", "interpretação": "#FBBF24", "hipótese": "#A78BFA"}


def statements_html(items) -> str:
    out = []
    for s in items:
        c = COLORS.get(s["tipo"], "#98A6BF")
        n = f'<span style="color:#98A6BF;font-size:.78rem"> · n={s["n"]}</span>' if s.get("n") else ""
        out.append(f'<div style="background:#0B1120;border:1px solid #1E2A44;border-left:4px solid {c};border-radius:12px;'
                   f'padding:8px 12px;margin-bottom:6px;color:#DCE6F4"><span style="color:{c};font-weight:700">'
                   f'{P.TYPE_ICON.get(s["tipo"], s["tipo"])}</span>{n}<br>{s["texto"]}</div>')
    return "".join(out)


@st.cache_data(show_spinner=False, max_entries=24)
def _multi(player: str, team: str, n: int, version: str) -> List[dict]:
    from src.data_hub.gender import comp_sql
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    db = get_service().db
    names = same_team_names(team) or [team]
    ph = ",".join("?" * len(names))
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute(
            f"SELECT match_id FROM matches m WHERE data_level = 'EVENTS' AND (home_team_name IN ({ph}) OR "
            f"away_team_name IN ({ph})){comp_sql(names, 'm')} ORDER BY match_date DESC LIMIT ?", names * 2 + [n * 2]).fetchall()]
    out = []
    for mid in ids:
        try:
            df = db.load_events(int(mid))
        except Exception:
            continue
        if df is None or df.empty or not (df["player_name"] == player).any():
            continue
        out.append(P.match_intel(df, player))
        if len(out) >= n:
            break
    return out


def render(ctx, focus: str | None = None) -> None:
    meta = {**(ctx.bundle.meta or {}), "data_source": ctx.bundle.source}
    dm = A.data_map(meta, ctx.df, ctx.bundle.boxscore)
    st.markdown("#### 🔬 Inteligência do jogador")
    with st.expander(f"🗺️ O que este jogo tem de dado — {dm['rotulo']}", expanded=not ctx.has_events):
        st.markdown(" ".join(f"{'✅' if r['disponivel'] else '⛔'} {r['analise']}<br>" for r in dm["linhas"]),
                    unsafe_allow_html=True)
        st.caption("Análise que precisa de um dado que a fonte não traz NÃO roda — aparece como 'não medido'.")
    if not ctx.has_events:
        st.info("Este jogo não tem lances com coordenadas: não dá para analisar lance a lance, corredores, sequências nem "
                "pé usado. Os números por jogador da fonte estão em 👤 Jogadores e no 📑 Relatório da IA.")
        return
    roster = P.players_with_events(ctx.df)
    teams = roster["team_name"].unique().tolist()
    a, b = st.columns([1, 2])
    team = a.radio("Time", teams, index=teams.index(focus) if focus in teams else 0, key="pi_team")
    names = roster[roster["team_name"] == team]["player_name"].tolist()
    player = b.selectbox("Jogador", names, key="pi_player")
    c, d = st.columns([1.4, 2])
    scope = c.radio("Escala", ["Um lance", "A partida", "Vários jogos"], index=1, horizontal=True, key="pi_scope")
    areas = d.multiselect("Área", AREAS, default=[], key="pi_areas", placeholder="todas as áreas")
    if scope == "Um lance":
        ka = P.key_actions(ctx.df, player, limit=20)
        if ka.empty:
            st.caption("Sem lances marcantes (finalização, passe para a área, perda, driblado) deste jogador.")
            return
        labels = [f"{int(r.minute)}' · {r.type_name}" for r in ka.itertuples()]
        pick = st.selectbox("Lance", labels, key="pi_action")
        res = P.analyze_action(ctx.df, ka.iloc[labels.index(pick)]["event_id"])
        st.markdown(statements_html(res["afirmacoes"]), unsafe_allow_html=True)
        return
    if scope == "A partida":
        res = P.match_intel(ctx.df, player)
        items = res["afirmacoes"]
    else:
        n = st.select_slider("Jogos (com lances) a considerar", [3, 5, 10, 20], value=5, key="pi_n")
        from src.ui.context import get_service

        with st.spinner("Lendo os lances dos jogos anteriores…"):
            per = _multi(player, team, int(n), get_service().db.stable_version())
        items = P.patterns(per)
    if areas:
        items = [s for s in items if s.get("area") in areas]
    order = {"fato": 0, "padrão": 1, "interpretação": 2, "hipótese": 3}
    cols = st.columns(2)
    for i, kind in enumerate(("fato", "padrão", "interpretação", "hipótese")):
        part = [s for s in items if s["tipo"] == kind]
        if part:
            with cols[0 if kind in ("fato", "padrão") else 1]:
                st.markdown(statements_html(sorted(part, key=lambda s: order[s["tipo"]])), unsafe_allow_html=True)
    if not items:
        st.caption("Nada nesta área para este jogador.")
    st.caption(A.summary_line(dm))
