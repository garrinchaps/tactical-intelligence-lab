"""👤 Tela do jogador — perfil, valor de mercado, temporada e TODOS os jogos com lances. Aberta pela busca única."""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from src.ui.components import render_chart

from src.ui.components import comparison_table, empty_state, hero
from src.ui.crests import crest_img


def _norm(s: str) -> str:
    from src.data_lake.ids import player_core

    return player_core(s)


INDEX_PATH = __import__("pathlib").Path("data/processed/player_index.parquet")


@st.cache_data(show_spinner=False)
def player_index(version: str) -> pd.DataFrame:
    """
    Rodada 12: o índice de jogadores é PESADO (soma todos os lances da base e une as grafias de ~100 mil nomes).
    Antes era refeito a cada 15 min dentro da tela. Agora fica salvo em data/processed/player_index.parquet: a tela só
    lê o arquivo; o processo de fundo o refaz 1x por dia, com a tela parada. Sem arquivo, monta uma vez e salva.
    """
    try:
        if INDEX_PATH.exists():
            return pd.read_parquet(INDEX_PATH)
    except Exception:
        pass
    from src.ui.context import get_service

    df = build_player_index(get_service().db)
    save_player_index(df)
    return df


def save_player_index(df: pd.DataFrame) -> None:
    try:
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = INDEX_PATH.with_suffix(".tmp")
        df.astype({c: "string" for c in df.columns if df[c].dtype == object}).to_parquet(tmp, index=False)
        __import__("os").replace(tmp, INDEX_PATH)
    except Exception:
        pass


def build_player_index(db) -> pd.DataFrame:
    """Uma linha por (nome, fonte): eventos do banco + FotMob (boxscore) + Transfermarkt + Understat + Simonetti (quando houver)."""
    rows: List[Dict] = []
    with db.connect() as conn:
        try:
            ev = pd.read_sql_query("SELECT player_name AS nome, team_name AS clube, COUNT(DISTINCT match_id) AS jogos "
                                   "FROM events WHERE player_name IS NOT NULL GROUP BY player_name, team_name", conn)
            rows += [{"nome": r.nome, "clube": r.clube, "fonte": "eventos (StatsBomb/Wyscout)", "jogos": int(r.jogos)}
                     for r in ev.itertuples()]
        except Exception:
            pass
        # Índice também inclui atletas com estatísticas de boxscore (FotMob), mesmo sem eventos com coordenadas.
        try:
            fm = pd.read_sql_query(
                "SELECT s.player_name AS nome, s.team_name AS clube, COUNT(DISTINCT s.match_id) AS jogos "
                "FROM match_player_stats s JOIN matches m ON m.match_id = s.match_id "
                "WHERE m.data_source = 'fotmob' AND s.player_name IS NOT NULL "
                "GROUP BY s.player_name, s.team_name", conn)
            rows += [{"nome": r.nome, "clube": r.clube, "fonte": "FotMob (estatísticas)", "jogos": int(r.jogos)}
                     for r in fm.itertuples()]
        except Exception:
            pass
    try:
        from src.data_lake.lake import Lake

        lake = Lake(sqlite_path=None)
        if lake.exists("tm_jogadores"):
            cols = ["nome", "clube", "ultima_temporada"]
            try:
                tm = lake.read("tm_jogadores", cols + ["nascimento", "nacionalidade"])
            except Exception:
                tm = lake.read("tm_jogadores", cols)
            tm = tm[pd.to_numeric(tm["ultima_temporada"], errors="coerce").fillna(0) >= 2015]
            rows += [{"nome": r.nome, "clube": r.clube, "fonte": "Transfermarkt", "jogos": None,
                      "nascimento": str(getattr(r, "nascimento", "") or "")[:10],
                      "nacionalidade": getattr(r, "nacionalidade", None)} for r in tm.itertuples()]
        if lake.exists("us_jogadores"):
            us = lake.read("us_jogadores", ["nome", "clube"]).drop_duplicates()
            rows += [{"nome": r.nome, "clube": r.clube, "fonte": "Understat", "jogos": None} for r in us.itertuples()]
    except Exception:
        pass
    df = pd.DataFrame(rows)
    if not df.empty:
        from src.data_hub.player_resolver import resolve, save_candidates

        df["core"] = df["nome"].map(_norm)
        df = df[df["core"] != ""].copy()
        if "nascimento" not in df:
            df["nascimento"] = ""
        # B4: mesma pessoa só com nome + confirmação (nascimento, nacionalidade, clube/seleção em comum);
        # pares duvidosos vão para player_merge_candidates em vez de serem fundidos
        df["pessoa"], review = resolve(df)
        try:
            save_candidates(db, review)
        except Exception:
            pass
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
           WHERE e.player_name = ? GROUP BY e.match_id ORDER BY m.match_date DESC"""
    with get_service().db.connect() as conn:
        try:
            return pd.read_sql_query(q, conn, params=(name,))
        except Exception:
            return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=3600, max_entries=128)
def player_match_rating(match_id: int, names: tuple) -> Optional[Dict]:
    """Nota 0–10 do atleta numa partida com lances (None = a partida não tem lances dele → fora da média)."""
    from src.analytics.rating_v2 import match_ratings_v2
    from src.ui.context import load_bundle, processed_events

    try:
        b = load_bundle(int(match_id))
        if b.events is None or b.events.empty:
            return None
        df, _ = processed_events(int(match_id), b.events)
        r = match_ratings_v2(df)
    except Exception:
        return None
    hit = r[r["jogador"].isin(names)] if not r.empty else r
    if hit.empty and not r.empty:                    # nome completo no banco × nome comum na partida processada
        from src.data_lake.ids import player_core

        wanted = [player_core(n).split() for n in names]

        def same(j):
            t = player_core(j).split()
            return any(t and w and t[0] == w[0] and (set(t) <= set(w) or set(w) <= set(t)) for w in wanted)
        hit = r[r["jogador"].map(same)]
        if len(hit) > 1:
            return None                              # ambíguo: melhor sem nota do que nota de outro jogador
    if hit.empty:
        return None
    x = hit.iloc[0]
    value = x.get("nota", x.get("nota_final"))
    return {
        "nota": None if value is None or pd.isna(value) else float(value),
        "desempenho": None if pd.isna(x.get("desempenho")) else float(x.get("desempenho")),
        "impacto": None if pd.isna(x.get("impacto")) else float(x.get("impacto")),
        "confianca": x.get("confianca"),
        "minutos": float(x["minutos"]),
        "setor": x.get("funcao", x.get("posicao", "")),
    }


def _ratings_block(pm: pd.DataFrame, names: List[str]) -> Dict[int, Dict]:
    from src.analytics.rating_v2 import RATING_ENGINE_VERSION

    key = "pl_ratings_" + RATING_ENGINE_VERSION + "_" + "|".join(sorted(names))
    if st.button("🏅 Calcular a nota em cada jogo (até os 10 mais recentes)", key=key + "_go"):
        out = {}
        bar = st.progress(0.0, text="abrindo as partidas…")
        ids = pm["match_id"].astype(int).tolist()[:10]
        for i, mid in enumerate(ids, 1):
            out[mid] = player_match_rating(mid, tuple(names))
            bar.progress(i / len(ids), text=f"{i}/{len(ids)} partidas")
        bar.empty()
        st.session_state[key] = out
    got = st.session_state.get(key) or {}
    if got:
        from src.analytics.player_ratings import player_average

        rows = pd.DataFrame([{"match_id": k, **v} for k, v in got.items() if v])
        avg = player_average(rows) if not rows.empty else player_average(pd.DataFrame(columns=["nota", "minutos"]))
        skipped = sum(1 for v in got.values() if not v)
        k1, k2, k3 = st.columns(3)
        k1.metric("Nota média (0–10)", "—" if avg["media"] is None else f"{avg['media']:.1f}",
                  help="Média só das partidas com lances do jogador e pelo menos 10 minutos em campo.")
        k2.metric("Minutos nesses jogos", f"{avg['minutos']}")
        k3.metric("Jogos na média", f"{avg['jogos_com_nota']} (mínimo {avg['minimo']})")
        if avg["aviso"]:
            st.warning(avg["aviso"].capitalize() + (f" — média provisória {avg['media_bruta']:.1f}." if avg["media_bruta"] else "."))
        st.caption((f"{skipped} jogo(s) sem lances do jogador ficaram fora da média (nunca contam como zero). " if skipped else "")
                   + "Nota 3.0: desempenho por função + impacto decisivo (gols, defesas-chave e disputa de pênaltis), sem transformar dado ausente em zero.")
    return got


def render(_ctx=None) -> None:
    from src.ui import nav
    from src.ui.context import get_service

    nav.back_button(key="player_back")
    core, given = nav.param("core"), nav.param("name")
    if not (core or given):
        empty_state("Nenhum jogador escolhido", "Use o 🔎 Buscar e clique no jogador.", "👤")
        return
    idx = player_index(get_service().db.stable_version())
    core = core or _norm(given)
    if not idx.empty:
        person = core if core in set(idx["pessoa"]) else next(iter(idx.loc[idx["core"] == core, "pessoa"]), core)
        hit = idx[idx["pessoa"] == person]
    else:
        hit = idx
    if hit.empty:
        empty_state("Jogador sem dados na base", "", "👤", "Abra partidas com eventos ou sincronize Transfermarkt/Understat.")
        return
    p = {"core": core, "nome": min(hit["nome"], key=len), "nome_longo": max(hit["nome"], key=len),
         "clube": next((x for x in list(hit.loc[hit["fonte"] == "Transfermarkt", "clube"]) + list(hit["clube"])
                        if isinstance(x, str) and x), ""),
         "fontes": ", ".join(sorted(set(hit["fonte"])))}
    names = hit["nome"].unique().tolist()
    st.markdown(f'<div class="til-profile">{crest_img(p["clube"] or "?", "lg")}<div><div class="n">{p["nome"]}</div>'
                f'<div class="d">{p["nome_longo"] if p["nome_longo"] != p["nome"] else ""} · {p["clube"]} · fontes: {p["fontes"]}</div>'
                f'</div></div>', unsafe_allow_html=True)
    favorites = st.session_state.setdefault("til_favorite_players", [])
    is_favorite = any(x.get("core") == p["core"] for x in favorites)
    if st.button("⭐ Remover dos alvos" if is_favorite else "☆ Adicionar aos alvos de análise",
                 key=f"til_fav_{p['core']}"):
        if is_favorite:
            st.session_state["til_favorite_players"] = [x for x in favorites if x.get("core") != p["core"]]
        else:
            st.session_state["til_favorite_players"] = favorites + [{"core": p["core"], "nome": p["nome"],
                                                                       "clube": p["clube"]}]
        st.rerun()
    if p["clube"]:
        nav.link(f"🛡️ Ver o time: {p['clube']}", "time", key="player_team", name=p["clube"])
    t0, t1, t5, t4, t2, t3 = st.tabs(["📋 Visão geral (olheiro)", "🗓️ Jogos com todos os lances", "📊 Scout por 90 min",
                                      "📚 Carreira (Transfermarkt)", "💶 Perfil e valor", "📈 Temporada (Understat)"],
                                     key=f"player_tabs_{p['core']}", on_change="rerun")
    with t0:
        if t0.open is not False:          # rodada 23: visão geral estilo FM com números medidos
            _player_card(p["nome"], tuple(names), p["clube"])
            from src.scout import snapshot as S
            from src.ui import player_fm

            row = S.find_player(p["core"], names, p["clube"])
            if row:
                from src.analytics.rating_v2 import RATING_ENGINE_VERSION

                form = _form_data(tuple(names), get_service().db.stable_version() + ":" + RATING_ENGINE_VERSION, p["clube"] or "")
                player_fm.overview(row, key=f"pfm_{p['core']}", form=form)
            else:
                st.caption("Atributos, capacidade e potencial aparecem quando o atleta está no universo do Scout (jogou "
                           "minutos medidos pela FotMob/ESPN no último ano).")
    with t5:
        _scout_tab(names)
    with t4:
        _career_tab(p["core"])
    with t1:
        frames = [player_matches(n) for n in names]
        pm = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
        if not pm.empty:                                   # B4: mesmo jogo em duas fontes conta uma vez
            from src.data_hub.player_resolver import merge_match_rows

            pm = merge_match_rows(pm)
        if pm.empty:
            empty_state("Nenhum jogo com lances deste atleta na base", "", "🗓️",
                        "Os jogos com todos os lances vêm da StatsBomb/Wyscout.")
        else:
            pm = pm.sort_values("match_date", ascending=False)
            k = st.columns(5)
            k[0].metric("Jogos", len(pm))
            k[1].metric("Gols", int(pm["gols"].sum()))
            k[2].metric("xG", round(float(pm["xg"].sum()), 2))
            k[3].metric("Passes certos", f"{int(pm['passes_certos'].sum())} de {int(pm['passes'].sum())}")
            k[4].metric("Finalizações", int(pm["finalizacoes"].sum()))
            notes = _ratings_block(pm, names)
            for i, r in enumerate(pm.to_dict("records")):
                a, b = st.columns([8, 1.3])
                nt = (notes.get(int(r["match_id"])) or {}).get("nota") if notes else None
                score = f"{int(r['home_score'])} – {int(r['away_score'])}" if pd.notna(r["home_score"]) else "x"
                a.markdown(f'<div class="til-result"><div class="tm r">{r["home_team_name"]}</div><div class="sc">{score}</div>'
                           f'<div class="tm">{r["away_team_name"]}</div><div class="meta">{r["competition_name"]}<br>'
                           f'{r["match_date"]} · {int(r["acoes"])} ações · {int(r["gols"] or 0)} gol(s) · xG {r["xg"]}'
                           + (f' · 🏅 {nt:.1f}' if nt is not None else '') + '</div></div>',
                           unsafe_allow_html=True)
                b.write("")
                if b.button("Analisar →", key=f"pl_open_{r['match_id']}_{i}", use_container_width=True, type="primary"):
                    st.session_state["team_focus"] = r["team_name"]
                    nav.open_view("jogo", match_id=int(r["match_id"]))
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
                from src.squad import data as D

                v = D.table("tm_valores", None, "transfermarkt_id", [x["transfermarkt_id"]]).sort_values("data")
                if not v.empty:
                    from src.ui import charts

                    render_chart(charts.lines(v.assign(valor=v["valor_mercado_eur"] / 1e6), "data", ["valor"],
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


# ------------------------------------------------------------------------------------------------ scout e carreira
SCOUT_SQL = """
SELECT e.match_id, MIN(e.minute) AS m0, MAX(e.minute) AS m1, COUNT(*) AS acoes,
  SUM(e.type_name = 'Pass') AS passes, SUM(e.type_name = 'Pass' AND e.pass_outcome_name IS NULL) AS passes_certos,
  SUM(e.type_name = 'Pass' AND e.pass_outcome_name IS NULL AND e.end_x >= 80) AS passes_certos_terco_final,
  SUM(e.type_name = 'Pass' AND e.x < 60) AS passes_proprio_campo,
  SUM(e.type_name = 'Pass' AND e.pass_outcome_name IS NULL AND e.x < 60) AS passes_certos_proprio_campo,
  SUM(e.type_name = 'Pass' AND COALESCE(e.pass_length, 0) >= 32) AS bolas_longas,
  SUM(e.type_name = 'Pass' AND COALESCE(e.pass_length, 0) >= 32 AND e.pass_outcome_name IS NULL) AS bolas_longas_certas,
  SUM(e.type_name = 'Pass' AND e.is_pass_cross = 1) AS cruzamentos,
  SUM(e.type_name = 'Pass' AND e.is_pass_cross = 1 AND e.pass_outcome_name IS NULL) AS cruzamentos_certos,
  SUM(e.type_name = 'Pass' AND e.is_pass_through_ball = 1) AS passes_em_profundidade,
  SUM(e.type_name = 'Shot') AS finalizacoes,
  SUM(e.type_name = 'Shot' AND e.shot_outcome_name IN ('Goal', 'Saved', 'Saved To Post')) AS finalizacoes_no_gol,
  SUM(e.type_name = 'Shot' AND e.shot_outcome_name = 'Goal') AS gols,
  SUM(e.type_name = 'Shot' AND e.shot_outcome_name = 'Goal' AND e.x >= 102 AND e.y BETWEEN 18 AND 62) AS gols_dentro_da_area,
  SUM(e.type_name = 'Shot' AND e.shot_outcome_name = 'Goal' AND e.shot_body_part_name = 'Head') AS gols_de_cabeca,
  SUM(e.type_name = 'Shot' AND e.shot_type_name = 'Penalty') AS penaltis,
  ROUND(SUM(CASE WHEN e.type_name = 'Shot' THEN COALESCE(e.shot_statsbomb_xg, 0) ELSE 0 END), 3) AS xg,
  SUM(e.type_name = 'Dribble') AS dribles, SUM(e.type_name = 'Duel') AS duelos,
  SUM(e.type_name = 'Duel' AND e.duel_outcome_name IN ('Won', 'Success', 'Success In Play', 'Success Out')) AS duelos_ganhos,
  SUM(e.type_name = 'Duel' AND e.duel_type_name LIKE 'Aerial%') AS duelos_aereos,
  SUM(e.type_name = 'Duel' AND e.duel_type_name = 'Aerial Won') AS duelos_aereos_ganhos,
  SUM(e.type_name = 'Duel' AND e.duel_type_name = 'Tackle') AS desarmes,
  SUM(e.type_name = 'Interception') AS interceptacoes, SUM(e.type_name = 'Clearance') AS cortes,
  SUM(e.type_name = 'Block') AS bloqueios, SUM(e.type_name = 'Ball Recovery') AS recuperacoes,
  SUM(e.type_name = 'Ball Recovery' AND e.x >= 80) AS recuperacoes_no_ataque,
  SUM(e.type_name = 'Dispossessed') + SUM(e.type_name = 'Miscontrol') +
    SUM(e.type_name = 'Pass' AND e.pass_outcome_name IS NOT NULL) AS perdas_de_posse,
  SUM(e.type_name = 'Foul Committed') AS faltas_cometidas, SUM(e.type_name = 'Foul Won') AS faltas_sofridas,
  SUM(e.type_name = 'Error') AS erros,
  SUM(e.foul_committed_card_name LIKE '%Yellow%') AS amarelos, SUM(e.foul_committed_card_name LIKE '%Red%') AS vermelhos
FROM events e WHERE e.player_name IN ({ph}) AND e.period <= 4 GROUP BY e.match_id
"""

SCOUT_GROUPS = {
    "Atacando": [("gols", "Gols"), ("xg", "Gols esperados (xG)"), ("finalizacoes", "Finalizações"),
                 ("finalizacoes_no_gol", "Finalizações no gol"), ("gols_dentro_da_area", "Gols de dentro da área"),
                 ("gols_de_cabeca", "Gols de cabeça"), ("penaltis", "Pênaltis cobrados")],
    "Passe": [("passes", "Passes"), ("passes_certos", "Passes certos"),
              ("passes_certos_terco_final", "Passes certos no terço final"),
              ("passes_certos_proprio_campo", "Passes certos no próprio campo"), ("bolas_longas_certas", "Bolas longas certas"),
              ("cruzamentos_certos", "Cruzamentos certos"), ("passes_em_profundidade", "Passes em profundidade"),
              ("acoes", "Ações com a bola e sem a bola")],
    "Defendendo": [("desarmes", "Desarmes"), ("interceptacoes", "Interceptações"), ("cortes", "Cortes"),
                   ("bloqueios", "Bloqueios"), ("recuperacoes", "Bolas recuperadas"),
                   ("recuperacoes_no_ataque", "Bolas recuperadas no ataque"), ("erros", "Erros")],
    "Outros": [("dribles", "Dribles tentados"), ("duelos_ganhos", "Duelos ganhos"), ("duelos_aereos_ganhos", "Duelos aéreos ganhos"),
               ("perdas_de_posse", "Perdas de posse"), ("faltas_cometidas", "Faltas cometidas"),
               ("faltas_sofridas", "Faltas sofridas"), ("amarelos", "Amarelos"), ("vermelhos", "Vermelhos")],
}


@st.cache_data(show_spinner=False, ttl=900, max_entries=32)
def player_scout(names: tuple) -> pd.DataFrame:
    from src.ui.context import get_service

    ph = ",".join("?" * len(names))
    with get_service().db.connect() as conn:
        try:
            return pd.read_sql_query(SCOUT_SQL.format(ph=ph), conn, params=list(names))
        except Exception:
            return pd.DataFrame()


def _scout_tab(names: List[str]) -> None:
    sc = player_scout(tuple(names))
    if sc.empty:
        empty_state("Sem jogos com lances deste atleta", "", "📊",
                    "O scout por 90 minutos usa partidas com todos os lances (StatsBomb, Wyscout, OpenPlay). "
                    "Abra jogos do atleta para que entrem na base.")
        return
    sc = sc.fillna(0)
    minutes = (sc["m1"] - sc["m0"]).clip(lower=1, upper=125)        # tempo entre a 1ª e a última ação: estimativa
    tot_min = float(minutes.sum())
    k = st.columns(4)
    k[0].metric("Jogos", len(sc))
    k[1].metric("Minutos (estimados)", f"{tot_min:.0f}")
    k[2].metric("Minutos por jogo", f"{tot_min / len(sc):.0f}")
    k[3].metric("Gols / xG", f"{int(sc['gols'].sum())} / {sc['xg'].sum():.2f}")
    per = lambda c: sc[c].sum() / max(tot_min, 1) * 90
    pct = lambda a, b: f" ({sc[a].sum() / sc[b].sum() * 100:.0f}%)" if sc[b].sum() else ""
    pairs = {"passes_certos": ("passes_certos", "passes"), "cruzamentos_certos": ("cruzamentos_certos", "cruzamentos"),
             "bolas_longas_certas": ("bolas_longas_certas", "bolas_longas"),
             "passes_certos_proprio_campo": ("passes_certos_proprio_campo", "passes_proprio_campo"),
             "duelos_ganhos": ("duelos_ganhos", "duelos"), "duelos_aereos_ganhos": ("duelos_aereos_ganhos", "duelos_aereos"),
             "finalizacoes_no_gol": ("finalizacoes_no_gol", "finalizacoes")}
    tab_names = {"Atacando": "⚽ Ofensivo", "Passe": "🎯 Passes", "Defendendo": "🛡️ Defensivo", "Outros": "⚔️ Duelos e outros"}
    order = ["Defendendo", "Atacando", "Passe", "Outros"]                 # C5: abas Defensivo, Ofensivo, Passes
    tabs = st.tabs([tab_names[g] for g in order if g in SCOUT_GROUPS])
    for tab, group in zip(tabs, [g for g in order if g in SCOUT_GROUPS]):
        items = SCOUT_GROUPS[group]
        rows = [{"Indicador": lab, "Por 90": f"{per(key):.2f}" + (pct(*pairs[key]) if key in pairs else ""),
                 "Total": f"{sc[key].sum():.2f}" if key == "xg" else int(sc[key].sum())} for key, lab in items]
        with tab:
            comparison_table(pd.DataFrame(rows))
    st.caption("Calculado dos lances de cada jogo na base (período normal + prorrogação; sem disputa de pênaltis). "
               "Minutos estimados pelo intervalo entre a primeira e a última ação do atleta em cada jogo. "
               "Velocidade, distância e mapa de calor de rastreamento não existem nas fontes abertas.")


def _career_tab(core: str) -> None:
    from src.squad import data as D

    tm = D.table("tm_jogadores", ["transfermarkt_id", "nome", "ultima_temporada"])
    hit = tm[tm["nome"].map(_norm) == core] if not tm.empty else tm
    if hit.empty:
        empty_state("Sem cadastro no Transfermarkt", "", "📚", "python -m src.data_hub.sync --only transfermarkt")
        return
    pid = hit.sort_values("ultima_temporada", ascending=False).iloc[0]["transfermarkt_id"]
    ap = D.table("tm_aparicoes", None, "transfermarkt_id", [pid])
    if ap.empty:
        empty_state("Sem aparições jogo a jogo", "", "📚",
                    "Rode `python -m src.data_hub.sync --only transfermarkt` para baixar as aparições (carreira).")
        return
    ap = ap.copy()
    d = pd.to_datetime(ap["data"], errors="coerce")
    ap["temporada"] = [f"{y}/{y + 1}" if m >= 7 else f"{y - 1}/{y}" for y, m in zip(d.dt.year.fillna(0).astype(int),
                                                                                 d.dt.month.fillna(1).astype(int))]
    clubs = D.clubs()
    cname = dict(zip(clubs["transfermarkt_id"].astype(str), clubs["nome"])) if not clubs.empty else {}
    ap["clube"] = ap["clube_id"].astype(str).str.replace(r"\.0$", "", regex=True).map(cname).fillna("—")
    g = ap.groupby(["temporada", "clube"])
    car = pd.DataFrame({"Jogos": g.size(), "Minutos": g["minutos"].sum(), "Gols": g["gols"].sum(),
                        "Assist.": g["assistencias"].sum(), "Amarelos": g["amarelos"].sum(),
                        "Vermelhos": g["vermelhos"].sum()}).reset_index().sort_values("temporada", ascending=False)
    car["Min/jogo"] = (car["Minutos"] / car["Jogos"]).round(0)
    car["G+A por 90"] = ((car["Gols"] + car["Assist."]) / car["Minutos"].clip(lower=1) * 90).round(2)
    k = st.columns(4)
    k[0].metric("Jogos na carreira", int(car["Jogos"].sum()))
    k[1].metric("Gols", int(car["Gols"].sum()))
    k[2].metric("Assistências", int(car["Assist."].sum()))
    k[3].metric("Minutos", f"{int(car['Minutos'].sum()):,}".replace(",", "."))
    comparison_table(car.rename(columns={"temporada": "Temporada", "clube": "Clube"}),
                     "Fonte: Transfermarkt (transfermarkt-datasets), jogo a jogo, competições oficiais cobertas.")


@st.cache_data(show_spinner=False, ttl=3600, max_entries=64)
def _form_data(names: tuple, version: str, club: str = "") -> pd.DataFrame:
    from src.analytics import rating_box as RB
    from src.ui.context import get_service

    try:
        teams = None
        if club:
            from src.ui.pages.clubs import same_team_names

            teams = same_team_names(club)
        f = RB.player_form(get_service().db, list(names), 10, team_names=teams)
        return f if not f.empty or not teams else RB.player_form(get_service().db, list(names), 10)
    except Exception:
        return pd.DataFrame()


DIM_SHORT = [("ofensiva", "ATA"), ("criacao", "CRI"), ("progressao", "PRO"), ("defesa", "DEF"), ("eficiencia", "TEC"),
             ("disciplina", "DIS"), ("tatica", "TRB")]
GK_SHORT = [("defesas", "DEF"), ("aereo", "AER"), ("distribuicao", "DIS"), ("seguranca", "SEG"), ("cobertura", "COB")]


def _player_card(nome: str, names: tuple, club: str = "") -> None:
    """
    Cartão no estilo FC/FIFA: qualidade = média da nota 3.0 nos últimos jogos com números por jogador;
    fase = últimos 5; regularidade = quanto a nota oscila. Atributos = média de cada dimensão (0–10 → 0–99).
    Nada é inventado: sem jogos com números por jogador, o cartão não aparece.
    """
    from src.ui.context import get_service

    from src.analytics.rating_v2 import RATING_ENGINE_VERSION
    f = _form_data(names, get_service().db.stable_version() + ":" + RATING_ENGINE_VERSION, club or "")
    if f is None or f.empty or len(f) < 2:
        return
    score_col = "nota" if "nota" in f and f["nota"].notna().any() else "desempenho"
    scored = pd.to_numeric(f[score_col], errors="coerce").dropna()
    if scored.empty:
        return
    q = float(scored.mean())
    recent_scores = pd.to_numeric(f[score_col], errors="coerce").dropna().head(5)
    fase = float(recent_scores.mean()) if not recent_scores.empty else q
    sd = float(scored.std() or 0)
    reg = "muito regular" if sd < 0.6 else "regular" if sd < 1.0 else "oscila bastante"
    fun = f["funcao"].mode().iloc[0]
    dims = GK_SHORT if fun == "goleiro" else DIM_SHORT
    tier = "#FBBF24" if q >= 7 else "#CBD5E1" if q >= 5.5 else "#B45309"
    attrs = "".join(
        f'<div style="display:flex;justify-content:space-between;gap:8px"><span style="color:#94A3B8">{lab}</span>'
        f'<b>{int(round(9.9 * float(f[k].dropna().mean())))}</b></div>' for k, lab in dims if k in f and f[k].notna().any())
    trend = "▲" if fase - q >= 0.3 else "▼" if q - fase >= 0.3 else "●"
    tcol = "#22C55E" if trend == "▲" else "#EF4444" if trend == "▼" else "#94A3B8"
    spark_df = f.copy()
    spark_df["score_value"] = pd.to_numeric(spark_df[score_col], errors="coerce")
    spark_df = spark_df.dropna(subset=["score_value"])
    spark = " ".join(f'<span title="{game} ({day})" style="display:inline-block;width:10px;height:{int(6 + 5 * score)}px;'
                     f'background:{"#22C55E" if score >= 7.0 else "#F59E0B" if score >= 5.5 else "#EF4444"};'
                     f'border-radius:3px;margin-right:2px;vertical-align:bottom"></span>'
                     for game, day, score in zip(spark_df.iloc[::-1]["jogo"], spark_df.iloc[::-1]["data"],
                                                 spark_df.iloc[::-1]["score_value"]))
    st.markdown(
        f'<div style="display:flex;gap:18px;flex-wrap:wrap;align-items:stretch;margin:.4rem 0 1rem">'
        f'<div style="width:190px;background:linear-gradient(160deg,{tier}33,#0F1626 55%);border:2px solid {tier};'
        f'border-radius:18px;padding:14px 16px">'
        f'<div style="font-size:2.6rem;font-weight:800;line-height:1;color:{tier}">{int(round(9.9 * q))}</div>'
        f'<div style="font-size:.8rem;color:#CBD5E1;text-transform:uppercase;letter-spacing:.08em">{fun}</div>'
        f'<div style="font-weight:700;margin:6px 0 8px;color:#F5F7FB">{nome}</div>{attrs}</div>'
        f'<div style="flex:1;min-width:240px;background:#0F1626;border:1px solid #1E2A44;border-radius:18px;padding:14px 16px">'
        f'<div style="color:#94A3B8;font-size:.8rem">QUALIDADE (média de {len(f)} jogos)</div>'
        f'<div style="font-size:1.6rem;font-weight:700">{q:.1f}</div>'
        f'<div style="color:#94A3B8;font-size:.8rem;margin-top:6px">FASE (últimos {len(recent_scores)} jogos com nota) '
        f'<span style="color:{tcol}">{trend}</span></div><div style="font-size:1.3rem;font-weight:700">{fase:.1f}</div>'
        f'<div style="color:#94A3B8;font-size:.8rem;margin-top:6px">REGULARIDADE</div><div>{reg} (oscila ±{sd:.1f})</div>'
        f'<div style="margin-top:10px">{spark}</div></div></div>', unsafe_allow_html=True)
    st.caption("Cartão = nota 3.0 por estatísticas individuais (FotMob), comparada com jogadores da mesma função. A qualidade e a fase usam a nota final; os atributos mostram as dimensões observadas. Sem dados de tracking, trabalho sem bola não observado não é inventado.")
