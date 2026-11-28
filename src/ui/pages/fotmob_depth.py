"""
🕸️ Jogo sem lances com coordenadas, mas com os dados da FotMob (rodada 5) — em vez do aviso "sem eventos":

  * momentum minuto a minuto (quem pressionava em cada fase do jogo);
  * por onde cada time atacou (esquerda/meio/direita, por tempo);
  * xG acumulado minuto a minuto (pelo mapa de chutes) e o mapa de chutes;
  * os destaques individuais: quem mais finalizou, criou, progrediu, recuperou e ganhou duelos (números da fonte).
Tudo é dado publicado pela FotMob, marcado como tal; nada é inventado a partir do placar.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ui.components import render_chart

from src.ui.components import comparison_table, note


def _sibling_fotmob(ctx) -> int | None:
    from src.ui.context import get_service

    svc = get_service()
    if int(ctx.match_id) >= 12_000_000_000:
        return int(ctx.match_id)
    try:
        return svc.fotmob.ensure_match(int(ctx.match_id), ctx.bundle.meta or {})
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600, max_entries=32)
def _data(fm_id: int) -> Dict[str, Any]:
    from src.ui.context import get_service

    svc = get_service()
    try:
        ex = svc.fotmob.extras(fm_id)
    except Exception:
        ex = {}
    with svc.db.connect() as conn:
        shots = pd.read_sql_query("SELECT * FROM match_shots WHERE match_id = ?", conn, params=(fm_id,))
        ps = pd.read_sql_query("SELECT team_name, player_name, minutes, rating, stats_json FROM match_player_stats "
                               "WHERE match_id = ?", conn, params=(fm_id,))
    return {"extra": ex, "shots": shots, "players": ps}


PLAYER_VIEW = [  # (chave da fonte, rótulo, maior é melhor)
    ("xg", "xG", True), ("totalShots", "Finalizações", True), ("xa", "xA", True), ("chances_created", "Chances criadas", True),
    ("passes_into_final_third", "Passes no terço final", True), ("touches_opp_box", "Toques na área rival", True),
    ("dribbles_succeeded", "Dribles certos", True), ("recoveries", "Recuperações", True),
    ("matchstats.headers.tackles", "Desarmes", True), ("interceptions", "Interceptações", True),
    ("duel_won", "Duelos ganhos", True), ("aerials_won", "Duelos aéreos ganhos", True), ("dispossessed", "Perdeu a posse", False),
    ("distance_m", "Distância (m)", True), ("sprints", "Sprints", True), ("top_speed_kmh", "Velocidade máx. (km/h)", True),
]


STAT_PT = {  # chave da fonte → rótulo em português (o que não estiver aqui não aparece na tabela principal)
    "minutes": "Min", "totalGoals": "Gols", "goalAssists": "Assist.", "xg": "xG", "xa": "xA", "totalShots": "Finalizações",
    "shotsOnTarget": "No alvo", "chances_created": "Chances criadas", "passes_into_final_third": "Passes no terço final",
    "line_breaking_passes": "Quebram linhas", "accurate_passes": "Passes certos", "accurate_passes_total": "Passes tentados",
    "long_balls_accurate": "Bolas longas certas", "accurate_crosses": "Cruzamentos certos", "touches": "Toques",
    "touches_opp_box": "Toques na área rival", "dribbles_succeeded": "Dribles certos", "dribbles_succeeded_total": "Dribles tentados",
    "dispossessed": "Perdeu a posse", "matchstats.headers.tackles": "Desarmes", "interceptions": "Interceptações",
    "recoveries": "Recuperações", "clearances": "Cortes", "shot_blocks": "Chutes bloqueados", "duel_won": "Duelos ganhos",
    "duel_lost": "Duelos perdidos", "aerials_won": "Aéreos ganhos", "aerials_won_total": "Aéreos disputados",
    "ground_duels_won": "Duelos no chão ganhos", "dribbled_past": "Vezes driblado", "foulsCommitted": "Faltas cometidas",
    "was_fouled": "Faltas sofridas", "saves": "Defesas", "goals_conceded": "Gols sofridos", "saves_inside_box": "Defesas na área",
    "keeper_high_claim": "Saídas pelo alto", "punches": "Socos", "keeper_sweeper": "Saídas como líbero",
    "errors_led_to_goal": "Erros que viraram gol", "distance_m": "Distância (m)", "sprints": "Sprints",
    "top_speed_kmh": "Velocidade máx. (km/h)",
}


def player_stats_table(ps: pd.DataFrame, team: str | None = None) -> pd.DataFrame:
    """
    Números por jogador da fonte numa tabela legível: um nome por coluna (sem colunas repetidas), rótulos em
    português, só as colunas que têm algum dado, ordenada pela nota. Colunas fixas e JSON não se duplicam mais
    (antes 'minutes' vinha das duas e o Streamlit quebrava com "Duplicate column names").
    """
    rows = []
    for r in ps.to_dict("records"):
        if team and r.get("team_name") != team:
            continue
        s = r.get("stats")
        if not isinstance(s, dict):
            try:
                s = json.loads(r.get("stats_json") or "{}")
            except Exception:
                s = {}
        row = {"Jogador": r.get("player_name"), "Time": r.get("team_name"),
               "Nota da fonte": r.get("rating") if r.get("rating") is not None else s.get("rating_title")}
        for k, lab in STAT_PT.items():
            if k == "minutes":
                row[lab] = s.get("minutes", r.get("minutes"))
            else:
                row[lab] = s.get(k)
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.loc[:, ~df.columns.duplicated()].dropna(axis=1, how="all")
    for c in df.columns[2:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    sort = "Nota da fonte" if "Nota da fonte" in df else ("Min" if "Min" in df else None)
    return df.sort_values(sort, ascending=False, na_position="last").reset_index(drop=True) if sort else df


def render(ctx) -> None:
    meta = ctx.bundle.meta or {}
    home, away = meta.get("home_team_name", ""), meta.get("away_team_name", "")
    fm_id = _sibling_fotmob(ctx)
    if not fm_id:
        note("Sem lances nem detalhes da FotMob para esta partida",
             "Redes de passe e xT precisam de lances com coordenadas (StatsBomb/Wyscout/OpenPlay). A FotMob não cobre "
             "este jogo ou ainda não o baixou.", "info")
        return
    with st.spinner("Lendo os detalhes da FotMob..."):
        d = _data(int(fm_id))
    ex, shots, ps = d["extra"], d["shots"], d["players"]
    st.markdown("### 🕸️ O jogo pelos dados da FotMob")
    st.caption("Este jogo não tem todos os lances com coordenadas, então não há rede de passes nem xT. Abaixo, tudo o que a "
               "FotMob publica dele: momentum, por onde cada time atacou, chutes com xG e os números de cada jogador.")
    teams = ex.get("times") or [home, away]
    c_home, c_away = "#22D3EE", "#EF4444"
    mom = ex.get("momentum") or []
    if mom:
        m = pd.DataFrame(mom, columns=["minuto", "valor"])
        fig = go.Figure(go.Bar(x=m["minuto"], y=m["valor"], marker_color=[c_home if v >= 0 else c_away for v in m["valor"]],
                               hovertemplate="%{x}': %{y}<extra></extra>"))
        for s in (shots[shots["outcome"] == "Goal"].itertuples() if not shots.empty else []):
            fig.add_annotation(x=s.minute, y=100 if s.team_name == teams[0] else -100, text="⚽", showarrow=False)
        from src.ui import charts

        fig.update_yaxes(range=[-110, 110], title=f"↑ {teams[0]} · ↓ {teams[1] if len(teams) > 1 else ''}")
        fig.update_xaxes(title="minuto")
        render_chart(charts._layout(fig, "Momentum: quem estava por cima em cada minuto (⚽ = gol)", 300), width="stretch")
        h1 = m[m["minuto"] <= 45]["valor"].mean()
        h2 = m[m["minuto"] > 45]["valor"].mean()
        st.caption(f"Média do momentum — 1º tempo: {h1:+.0f}, 2º tempo: {h2:+.0f} (positivo = {teams[0]} por cima). "
                   "Fonte: FotMob (indicador próprio, baseado na ameaça das ações).")
    az = ex.get("zonas_ataque") or {}
    if az.get("home") or az.get("away"):
        st.markdown("#### ↔️ Por onde cada time atacou")
        cols = st.columns(2)
        for col, side, tm, colr in ((cols[0], "home", teams[0], c_home), (cols[1], "away", teams[1] if len(teams) > 1 else "", c_away)):
            z = az.get(side) or {}
            with col:
                rows = []
                for per, lab in (("total", "Jogo todo"), ("firstHalf", "1º tempo"), ("secondHalf", "2º tempo")):
                    v = z.get(per) or {}
                    if v:
                        rows.append({"Período": lab, "Esquerda %": v.get("left"), "Meio %": v.get("center"), "Direita %": v.get("right")})
                st.markdown(f"**{tm}**")
                if rows:
                    comparison_table(pd.DataFrame(rows))
                    t = z.get("total") or {}
                    if t:
                        best = max(("esquerda", t.get("left", 0)), ("meio", t.get("center", 0)), ("direita", t.get("right", 0)),
                                   key=lambda kv: kv[1] or 0)
                        st.caption(f"Atacou mais pela {best[0]} ({best[1]}% das ações de ataque).")
    if not shots.empty:
        st.markdown("#### 📈 xG acumulado")
        fig = go.Figure()
        for tm, colr in ((teams[0], c_home), (teams[1] if len(teams) > 1 else "", c_away)):
            s = shots[shots["team_name"] == tm].sort_values("minute")
            if s.empty:
                continue
            xs = [0] + s["minute"].astype(float).tolist() + [max(95.0, float(shots["minute"].max()))]
            ys = [0] + pd.to_numeric(s["xg"], errors="coerce").fillna(0).cumsum().round(2).tolist()
            ys.append(ys[-1])
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line_shape="hv", name=f"{tm} (xG {ys[-1]:.2f})",
                                     line=dict(color=colr, width=3)))
            g = s[s["outcome"] == "Goal"]
            if not g.empty:
                cum = pd.to_numeric(s["xg"], errors="coerce").fillna(0).cumsum()
                fig.add_trace(go.Scatter(x=g["minute"], y=cum.loc[g.index], mode="markers", marker=dict(size=12, symbol="star", color=colr),
                                         name=f"gols {tm}", hovertext=g["player_name"], hoverinfo="text"))
        from src.ui import charts

        render_chart(charts._layout(fig, "Chances acumuladas (xG da FotMob) ao longo do jogo", 320), width="stretch")
    if not ps.empty:
        st.markdown("#### 👤 Quem decidiu nos números")
        rows = []
        for r in ps.itertuples():
            try:
                s = json.loads(r.stats_json or "{}")
            except Exception:
                continue
            rows.append({"Jogador": r.player_name, "Time": r.team_name, "Min": s.get("minutes"),
                         "Nota FotMob": r.rating, **{lab: s.get(k) for k, lab, _ in PLAYER_VIEW}})
        df = pd.DataFrame(rows)
        df = df.dropna(axis=1, how="all")                    # sem dado físico na liga → a coluna nem aparece
        cards = []
        for k, lab, hi in PLAYER_VIEW:
            if lab not in df or df[lab].dropna().empty or not hi:
                continue
            top = df.sort_values(lab, ascending=False).iloc[0]
            if not top[lab]:
                continue
            cards.append(f'<div class="fm-card" style="border-left:4px solid {c_home if top["Time"] == teams[0] else c_away};'
                         f'border-radius:12px;padding:.5rem .8rem;margin:.25rem;display:inline-block;min-width:200px">'
                         f'<div style="color:#94A3B8;font-size:.78rem">{lab}</div><b>{top["Jogador"]}</b> '
                         f'<span style="font-size:1.15rem;font-weight:700;margin-left:6px">{round(float(top[lab]), 2)}</span>'
                         f'<div style="color:#64748B;font-size:.75rem">{top["Time"]}</div></div>')
        st.markdown("".join(cards[:10]), unsafe_allow_html=True)
        with st.expander("Tabela completa por jogador (fonte: FotMob)"):
            comparison_table(player_stats_table(ps))
        if not any(c in df for c in ("Distância (m)", "Sprints")):
            st.caption("Distância e sprints: esta liga não publica dados físicos na FotMob — por isso não aparecem (não é zero).")
    dz = ex.get("desfalques") or {}
    if any(dz.values()):
        st.markdown("#### 🚑 Desfalques informados para este jogo")
        for tm, lst in dz.items():
            if lst:
                st.markdown(f"**{tm}:** " + "; ".join(f"{u['jogador']} ({u.get('tipo') or '?'}"
                                                      + (f", volta: {u['volta']}" if u.get("volta") else "") + ")" for u in lst))
