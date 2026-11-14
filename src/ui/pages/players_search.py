"""👤 Jogadores — pesquisa de atletas em todas as fontes: perfil, valor de mercado, temporada e jogos com eventos."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from src.ui.components import comparison_table, empty_state, hero
from src.ui.crests import crest_img


def _norm(s: str) -> str:
    from src.data_lake.ids import player_core

    return player_core(s)


@st.cache_data(show_spinner=False, ttl=900)
def player_index(version: str) -> pd.DataFrame:
    """Uma linha por (nome, fonte): eventos do banco + Transfermarkt + Understat + Simonetti (quando houver)."""
    from src.ui.context import get_service

    rows: List[Dict] = []
    with get_service().db.connect() as conn:
        try:
            ev = pd.read_sql_query("SELECT player_name AS nome, team_name AS clube, COUNT(DISTINCT match_id) AS jogos "
                                   "FROM events WHERE player_name IS NOT NULL GROUP BY player_name, team_name", conn)
            rows += [{"nome": r.nome, "clube": r.clube, "fonte": "eventos (StatsBomb/Wyscout)", "jogos": int(r.jogos)}
                     for r in ev.itertuples()]
        except Exception:
            pass
    try:
        from src.data_lake.lake import Lake

        lake = Lake(sqlite_path=None)
        if lake.exists("tm_jogadores"):
            tm = lake.read("tm_jogadores", ["nome", "clube", "ultima_temporada"])
            tm = tm[pd.to_numeric(tm["ultima_temporada"], errors="coerce").fillna(0) >= 2015]
            rows += [{"nome": r.nome, "clube": r.clube, "fonte": "Transfermarkt", "jogos": None} for r in tm.itertuples()]
        if lake.exists("us_jogadores"):
            us = lake.read("us_jogadores", ["nome", "clube"]).drop_duplicates()
            rows += [{"nome": r.nome, "clube": r.clube, "fonte": "Understat", "jogos": None} for r in us.itertuples()]
    except Exception:
        pass
    df = pd.DataFrame(rows)
    if not df.empty:
        df["core"] = df["nome"].map(_norm)
    return df


@st.cache_data(show_spinner=False, ttl=600)
def player_matches(name: str) -> pd.DataFrame:
    """Partidas com eventos em que o atleta aparece, com contagens diretas (sem processar a partida inteira)."""
    from src.ui.context import get_service

    q = """SELECT e.match_id, m.match_date, m.home_team_name, m.away_team_name, m.home_score, m.away_score,
                  m.competition_name, e.team_name, COUNT(*) AS acoes,
                  SUM(e.type_name = 'Pass') AS passes, SUM(e.type_name = 'Pass' AND e.pass_outcome_name IS NULL) AS passes_certos,
                  SUM(e.type_name = 'Shot') AS finalizacoes, SUM(e.type_name = 'Shot' AND e.shot_outcome_name = 'Goal') AS gols,
                  ROUND(SUM(CASE WHEN e.type_name = 'Shot' THEN COALESCE(e.shot_statsbomb_xg, 0) ELSE 0 END), 2) AS xg,
                  SUM(e.type_name = 'Dribble') AS dribles, SUM(e.type_name = 'Ball Recovery') AS recuperacoes
           FROM events e JOIN matches m ON m.match_id = e.match_id
           WHERE e.player_name = ? GROUP BY e.match_id ORDER BY m.match_date DESC LIMIT 40"""
    with get_service().db.connect() as conn:
        try:
            return pd.read_sql_query(q, conn, params=(name,))
        except Exception:
            return pd.DataFrame()


def render(_ctx=None) -> None:
    from src.ui.context import get_service

    hero("Jogadores", "Pesquise atletas", "Perfil, valor de mercado (Transfermarkt), números da temporada (Understat) e "
         "todos os jogos com eventos em que ele aparece.")
    q = st.text_input("Atleta", key="pl_q", placeholder="ex.: Messi, Vinícius, Arrascaeta, Bellingham")
    if len(q.strip()) < 3:
        empty_state("Digite pelo menos 3 letras do nome", icon="👤")
        return
    idx = player_index(get_service().db.catalog_version())
    if idx.empty:
        empty_state("Ainda não há jogadores na base", "", "👤", "Abra partidas com eventos ou sincronize Transfermarkt/Understat.")
        return
    core = _norm(q)
    hit = idx[idx["core"].str.contains(core, regex=False) | idx["nome"].str.lower().str.contains(q.strip().lower(), regex=False)]
    if hit.empty:
        empty_state("Atleta não encontrado", "Confira a grafia.", "🔎")
        return
    groups = hit.groupby("core").agg(nome=("nome", lambda s: min(s, key=len)), nome_longo=("nome", lambda s: max(s, key=len)),
                                     clube=("clube", lambda s: next((x for x in s if isinstance(x, str) and x), "")),
                                     fontes=("fonte", lambda s: ", ".join(sorted(set(s)))),
                                     jogos=("jogos", "sum")).reset_index().sort_values("jogos", ascending=False).head(25)
    opt = groups.to_dict("records")
    sel = st.selectbox("Resultado", range(len(opt)), format_func=lambda i: f"{opt[i]['nome']} · {opt[i]['clube']} · {opt[i]['fontes']}")
    p = opt[sel]
    names = hit[hit["core"] == p["core"]]["nome"].unique().tolist()
    st.markdown(f'<div class="til-profile">{crest_img(p["clube"] or "?", "lg")}<div><div class="n">{p["nome"]}</div>'
                f'<div class="d">{p["nome_longo"] if p["nome_longo"] != p["nome"] else ""} · {p["clube"]} · fontes: {p["fontes"]}</div>'
                f'</div></div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["🗓️ Jogos com eventos", "💶 Perfil e valor", "📈 Temporada (Understat)"])
    with t1:
        frames = [player_matches(n) for n in names]
        pm = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
        if pm.empty:
            empty_state("Nenhuma partida com eventos para este atleta no banco", "", "🗓️",
                        "Os jogos com eventos vêm da StatsBomb/Wyscout (abra ou sincronize partidas da competição dele).")
        else:
            k = st.columns(5)
            k[0].metric("Jogos", len(pm))
            k[1].metric("Gols", int(pm["gols"].sum()))
            k[2].metric("xG", round(float(pm["xg"].sum()), 2))
            k[3].metric("Passes certos", f"{int(pm['passes_certos'].sum())} de {int(pm['passes'].sum())}")
            k[4].metric("Finalizações", int(pm["finalizacoes"].sum()))
            pm["partida"] = pm["home_team_name"] + " " + pm["home_score"].astype("Int64").astype(str) + "–" + \
                pm["away_score"].astype("Int64").astype(str) + " " + pm["away_team_name"]
            comparison_table(pm[["match_date", "partida", "competition_name", "team_name", "acoes", "passes", "passes_certos",
                                 "finalizacoes", "gols", "xg", "dribles", "recuperacoes"]]
                             .rename(columns={"match_date": "data", "competition_name": "competição", "team_name": "equipe"}),
                             "Contagens diretas dos eventos de cada partida.")
            ids = pm["match_id"].tolist()
            pick = st.selectbox("Abrir uma dessas partidas", range(len(ids)), format_func=lambda i: f"{pm.iloc[i]['match_date']} · {pm.iloc[i]['partida']}")
            if st.button("Abrir em Jogos", type="primary"):
                st.session_state["match_id"] = int(ids[pick])
                st.session_state["team_focus"] = pm.iloc[pick]["team_name"]
                st.session_state["goto"] = "jogos"
                st.rerun()
    with t2:
        try:
            from src.data_lake.lake import Lake

            lake = Lake(sqlite_path=None)
            tm = lake.read("tm_jogadores") if lake.exists("tm_jogadores") else pd.DataFrame()
        except Exception:
            tm = pd.DataFrame()
        r = tm[tm["nome"].map(_norm) == p["core"]] if not tm.empty else tm
        if r.empty:
            empty_state("Sem perfil do Transfermarkt", "", "💶", "python -m src.data_hub.sync --only transfermarkt lake")
        else:
            x = r.sort_values("ultima_temporada", ascending=False).iloc[0]
            c = st.columns(5)
            c[0].metric("Valor atual", f"€ {round((x.get('valor_mercado_eur') or 0) / 1e6, 1)} mi")
            c[1].metric("Maior valor", f"€ {round((x.get('maior_valor_eur') or 0) / 1e6, 1)} mi")
            c[2].metric("Posição", f"{x.get('funcao') or x.get('posicao') or '—'}")
            c[3].metric("Nascimento", str(x.get("nascimento", "—"))[:10])
            c[4].metric("Contrato até", str(x.get("fim_contrato", "—"))[:10])
            if lake.exists("tm_valores"):
                v = lake.read("tm_valores")
                v = v[v["transfermarkt_id"].astype(str) == str(x["transfermarkt_id"])].sort_values("data")
                if not v.empty:
                    from src.ui import charts

                    st.plotly_chart(charts.lines(v.assign(valor=v["valor_mercado_eur"] / 1e6), "data", ["valor"],
                                                 "Valor de mercado ao longo do tempo (€ mi, Transfermarkt)", "€ mi"),
                                    use_container_width=True)
    with t3:
        try:
            from src.data_lake.lake import Lake

            lake = Lake(sqlite_path=None)
            us = lake.read("us_jogadores") if lake.exists("us_jogadores") else pd.DataFrame()
        except Exception:
            us = pd.DataFrame()
        r = us[us["nome"].map(_norm) == p["core"]] if not us.empty else us
        if r.empty:
            empty_state("Sem dados do Understat", "O Understat cobre as 5 grandes ligas europeias e a Rússia.", "📈")
        else:
            cols = [c for c in ["temporada", "liga", "clube", "jogos", "minutos", "gols", "xG", "npxG", "assistencias", "xA",
                                "chutes", "passes_chave", "xGChain", "xGBuildup"] if c in r.columns]
            comparison_table(r[cols].sort_values("temporada", ascending=False), "Fonte: Understat.")
