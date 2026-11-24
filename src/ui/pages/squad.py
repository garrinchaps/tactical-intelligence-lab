"""
📋 Escalação — elenco atual, nota do laboratório, campinho com a escalação provável / melhor possível / ajustada
ao adversário, plano de jogo pelos últimos 1/3/5/10/20 jogos e cadastro de atletas próprios.
"""

from __future__ import annotations

from src.data_hub.gender import comp_sql
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ui.perf import timed as _perf_timed

from src.ui.components import render_chart

from src.squad import data as D
from src.squad.formations import FORMATIONS, ROLE_PT, fit, natural_role
from src.squad.planner import (apply_transfers, best_xi, lab_rating, matchup_plan, plan_bonus, probable_xi, season_usage,
                               squad_frame,
                               team_profile)
from src.ui.components import comparison_table, empty_state, hero, note
from src.ui.theme import PALETTE as P

N_OPTIONS = [1, 3, 5, 10, 20]


# ------------------------------------------------------------------------------------------------ seleção de time
def _team_options(q: str, limit: int = 25) -> List[str]:
    from src.ui.context import get_service

    return _team_options_cached((q or "").strip().lower(), int(limit), get_service().db.stable_version())


@st.cache_data(show_spinner=False, max_entries=256)
def _team_options_cached(q: str, limit: int, version: str) -> List[str]:
    """Rodada 10: o mesmo texto não é recalculado (antes cada atualização da tela comparava milhares de nomes)."""
    from src.data_hub.search import fast_scores
    from src.ui.pages.search_all import team_table

    t = team_table(version, False)
    names = set(t["nome"].tolist()) if not t.empty else set()
    cl = D.clubs()
    if not cl.empty:
        names |= set(cl["nome"].astype(str))
    if not q.strip():
        top = t.sort_values("jogos", ascending=False)["nome"].head(limit).tolist() if not t.empty else []
        return top
    sc = fast_scores(q, list(names))
    ranked = [n for n, v in sorted(sc.items(), key=lambda kv: -kv[1]) if v >= 0.6]
    games = dict(zip(t["nome"], t["jogos"])) if not t.empty else {}
    country = dict(zip(t["nome"], t["pais"])) if not t.empty and "pais" in t else {}
    return clean_team_options(q, ranked, games, country)[:limit]


def clean_team_options(q: str, ranked: List[str], games: dict, country: Optional[dict] = None) -> List[str]:
    """Rodada 25: um nome por clube na busca. Antes "cruzeiro" trazia Cruzeiro, Cruzeiro (W), Cruzeiro EC, Cruzeiro
    Esporte Clube e até o Lokomotiv. Regras (conferidas, não chute):
      * time feminino/base sai, salvo se a pergunta pedir (o mesmo nome do clube masculino com "(W)", "Feminino"…);
      * grafias do MESMO clube (mesmo núcleo do nome e mesmo país dos jogos) viram uma — fica a com mais jogos;
        núcleo igual em país diferente (Barcelona × Barcelona SC do Equador) continua separado;
      * nome sem nenhuma palavra que comece como a busca sai (o Lokomotiv vinha por semelhança de letras);
      * nome do cadastro sem nenhum jogo na base, quando já existe o clube com jogos, sai (é só um apelido)."""
    from src.data_hub.gender import is_women_team
    from src.data_lake.ids import team_core
    import re as _re
    import unicodedata as _ud

    country = country or {}

    def norm(x):
        return "".join(c for c in _ud.normalize("NFKD", str(x).lower()) if not _ud.combining(c))
    qn = norm(q).strip()
    want_w = bool(_re.search(r"femin|women|\(w\)|sub|u2|u1", qn))
    q_tokens = [w for w in _re.split(r"[^a-z0-9]+", qn) if len(w) >= 3]
    out, seen_core = [], {}
    # quem tem jogos (e país conhecido) vem primeiro: apelidos sem jogos só se juntam depois, sem apagar o país
    ranked = sorted(ranked, key=lambda n: (games.get(n, 0) <= 0, not country.get(n)))
    for n in ranked:
        if not want_w and is_women_team([n]):
            continue
        if not want_w and _re.search(r"\b(u-?1\d|u-?2[0-3]|sub-?\d\d|youth|reserves?|ii|b team)\b", norm(n)):
            continue
        toks = [w for w in _re.split(r"[^a-z0-9]+", norm(n)) if w]
        if q_tokens and not any(any(t.startswith(qt) or qt.startswith(t) and len(t) >= 3 for t in toks) for qt in q_tokens):
            continue
        core = team_core(n)
        key = (core, country.get(n) or "")
        prev = next((k for k in seen_core if k[0] == core and (not k[1] or not key[1] or k[1] == key[1])), None)
        if prev is not None:
            i = seen_core[prev]
            if games.get(n, 0) > games.get(out[i], 0):
                out[i] = n
            continue
        seen_core[key] = len(out)
        out.append(n)
    with_games = {team_core(n) for n in out if games.get(n, 0) > 0}
    return [n for n in out if games.get(n, 0) > 0 or team_core(n) not in with_games]  # relevância já veio do ranking


def _picker(label: str, key: str, default: str = "") -> Optional[str]:
    """Busca só ao apertar Enter/Buscar (rodada 10); antes de digitar, sugere os times com mais jogos na base."""
    c1, c2 = st.columns([1, 1.4])
    with c1.form(f"{key}_form", border=False):
        q = st.text_input(label, value=st.session_state.get(f"{key}_q", default), key=f"{key}_q",
                          placeholder="digite o nome e aperte Enter")
        st.form_submit_button("🔎 Buscar", use_container_width=True)
    opts = _team_options(q)
    if not opts:
        c2.caption("Nenhum time com esse nome na base.")
        return None
    if st.session_state.get(f"{key}_pick") not in opts:
        st.session_state.pop(f"{key}_pick", None)
    # rodada 20: nada escolhido de fábrica — só calcula depois que o time é escolhido
    return c2.selectbox("Escolha", opts, key=f"{key}_pick", label_visibility="hidden", index=None,
                        placeholder="Escolha o time")


# ------------------------------------------------------------------------------------------------ dados do time
def apply_scout_overall(squad: pd.DataFrame, team: str) -> pd.DataFrame:
    """Substitui a nota paralela do elenco pelo overall oficial do universo do Scout quando houver correspondência segura."""
    if squad is None or squad.empty:
        return squad
    try:
        from src.data_lake.ids import player_core
        from src.scout import snapshot as S
    except Exception:
        return squad
    out = squad.copy()
    for i, player in out.iterrows():
        name = str(player.get("nome") or "").strip()
        if not name or name.casefold() in {"nan", "none"}:
            continue
        # A ficha do elenco (Transfermarkt) pode carregar um ID antigo que não corresponde à
        # linha consolidada do Scout (ex.: Otávio → Otávio Costa, perfil com histórico FotMob).
        # Nome/alias + clube devem prevalecer; passar pid primeiro fazia find_player retornar
        # imediatamente a ficha legada 65/71, sem validar nome ou clube.
        row = S.find_player(player_core(name), [name], str(team or ""), age=player.get("idade"))
        if not row:
            continue
        quality = pd.to_numeric(pd.Series([row.get("qualidade")]), errors="coerce").iloc[0]
        if pd.notna(quality):
            out.at[i, "nota"] = round(float(quality))
            out.at[i, "qualidade"] = round(float(quality))
            out.at[i, "nota_base"] = "Overall do Scout"
            out.at[i, "nota_fonte"] = "Scout"
        potential = pd.to_numeric(pd.Series([row.get("potencial")]), errors="coerce").iloc[0]
        if pd.notna(potential):
            out.at[i, "potencial"] = round(float(potential))
    return out


@_perf_timed("squad._squad")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")  # rodada 14: sobrevive ao fechar o app
def _squad(team: str, version: str) -> Dict[str, Any]:
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    names = same_team_names(team)
    club = D.match_club(team)
    tm = D.table("tm_jogadores", None, "clube_id", [club["transfermarkt_id"]]) if club else pd.DataFrame()
    added = D.added_players()
    sq = squad_frame(tm, [club["transfermarkt_id"]] if club else [], [team] + names, added)
    source = "Transfermarkt" if club and not tm.empty else ""
    changes: List[Dict[str, Any]] = []
    unconfirmed = pd.DataFrame()
    if club:                                             # v36: janelas de transferência e empréstimos pelos jogos
        try:
            cid = club["transfermarkt_id"]
            own = D.table("tm_aparicoes", None, "clube_id", [cid])
            ids = sq["transfermarkt_id"].dropna().tolist() if "transfermarkt_id" in sq else []
            mine = D.table("tm_aparicoes", None, "transfermarkt_id", ids) if ids else pd.DataFrame()
            arrivals = own["transfermarkt_id"].dropna().unique().tolist() if not own.empty else []
            tmp = D.table("tm_jogadores", None, "transfermarkt_id", arrivals) if arrivals else pd.DataFrame()
            if not own.empty and arrivals:              # quem chegou mas já jogou por outro depois não entra
                late = D.table("tm_aparicoes", None, "transfermarkt_id", arrivals)
                mine = pd.concat([mine, late], ignore_index=True) if not mine.empty else late
                own = own[~own["transfermarkt_id"].isin(_left_after(late, cid))]
            sq, changes = apply_transfers(sq, cid, own, mine, tmp)
            # B3: vínculo jogador-clube (transferências + jogos); sem informação = UNKNOWN, fora do elenco
            from src.squad.tenure import build_tenures, classify_squad

            ids_all = sq["transfermarkt_id"].dropna().tolist() if "transfermarkt_id" in sq else []
            trf = D.table("tm_transferencias", None, "transfermarkt_id", ids_all) if ids_all else pd.DataFrame()
            sq = classify_squad(sq, build_tenures(trf, mine), cid, mine)
            unconfirmed = sq[sq["situacao"] == "não confirmado"]
            # rodada 13: quem tem histórico de jogos mas não entra em campo há mais de 300 dias (aposentado, falecido,
            # afastado ou fora dos planos — ex.: Diogo Jota, Izquierdoz) sai do elenco quando não há lista oficial
            if mine is not None and not mine.empty and "transfermarkt_id" in sq:
                last_seen = pd.to_datetime(mine["data"], errors="coerce").groupby(
                    mine["transfermarkt_id"].astype(str)).max()
                lim = pd.Timestamp(date.today()) - pd.Timedelta(days=300)
                stale = sq["transfermarkt_id"].astype(str).map(last_seen)
                gone = stale.notna() & (stale < lim)
                for r in sq[gone].to_dict("records"):
                    changes.append({"nome": r["nome"], "mudanca": "saiu", "motivo":
                                    f"sem jogar desde {pd.Timestamp(stale[sq['nome'] == r['nome']].iloc[0]).date()} "
                                    "(aposentado, afastado ou fora do elenco)"})
                sq.loc[gone, "situacao"] = "inativo"
            for r in sq[sq["situacao"] == "saiu"].to_dict("records"):
                changes.append({"nome": r["nome"], "mudanca": "saiu", "motivo": "vínculo ativo com outro clube"})
            sq = sq[sq["situacao"] == "no elenco"].reset_index(drop=True)
        except Exception:
            changes = []
    if sq.empty or len(sq) < 11:                         # clube fora do Transfermarkt: elenco pelas escalações da base
        local = D.squad_from_db(get_service().db, names)
        if not local.empty:
            from src.squad.planner import filter_national_team_players, national_team_key

            if national_team_key(team):
                # As escalações históricas identificam quem atuou pela seleção, mas não provam
                # a nacionalidade. Cruza com o cadastro do Transfermarkt e exclui desconhecidos.
                nationality_catalog = D.table("tm_jogadores", ["nome", "nacionalidade"])
                if not nationality_catalog.empty and "nacionalidade" in nationality_catalog:
                    nationality_catalog = nationality_catalog.drop_duplicates("nome", keep="last")
                    local = local.merge(nationality_catalog[["nome", "nacionalidade"]], on="nome", how="left")
                local = filter_national_team_players(local, team)
                added = filter_national_team_players(added, team)
            if not local.empty:
                sq = squad_frame(local, [], [local["clube"].iloc[0]], added)
                source = "escalações da base + nacionalidade confirmada"
    from src.squad.planner import apply_official_roster, filter_national_team_players, national_team_key
    if national_team_key(team):
        sq = filter_national_team_players(sq, team)
    else:                                                # rodada 8: elenco inscrito hoje (FotMob) manda
        try:
            from src.squad import matchday as M

            official = M.fotmob_roster(get_service().db, [team] + names)
            if not official.empty:
                sq, extra = apply_official_roster(sq, official)
                changes = [c for c in changes if c.get("nome") not in {e["nome"] for e in extra}] + extra
                source = (source + " + " if source else "") + "elenco atual da FotMob"
        except Exception:
            pass

    usage = pd.DataFrame()
    if "transfermarkt_id" in sq and sq["transfermarkt_id"].notna().any():
        ap = D.table("tm_aparicoes", None, "transfermarkt_id", sq["transfermarkt_id"].dropna().tolist())
        usage = season_usage(ap, sq["transfermarkt_id"].dropna().tolist(),
                             since=(date.today() - timedelta(days=365)).isoformat())
    performance = pd.DataFrame()
    if not sq.empty:
        try:
            # Reutiliza a mesma régua 2.0 por posição usada nas páginas de jogadores e de partida.
            from src.squad import matchday as M

            performance = M.player_table(get_service().db, names, n=10, tm_values=tm).get("jogadores", pd.DataFrame())
        except Exception:
            performance = pd.DataFrame()
    rated = lab_rating(sq, D.tm_reference(), usage, D.external_ratings(), player_performance=performance) \
        if not sq.empty else sq
    rated = apply_scout_overall(rated, team)
    return {"squad": rated, "club": club, "names": names, "fonte": source or "—", "mudancas": changes,
            "nao_confirmados": unconfirmed[[c for c in ("nome", "posicao", "ultima_temporada") if c in unconfirmed]]
            if not unconfirmed.empty else unconfirmed}


@st.cache_data(show_spinner=False, max_entries=48, persist="disk")  # rodada 14: sobrevive ao fechar o app
def _attributes(team: str, version: str) -> pd.DataFrame:
    """Perfil de cada atleta nos últimos 15 jogos com números por jogador (FotMob), em 0–1 RELATIVO AO PRÓPRIO ELENCO."""
    import json

    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    names = same_team_names(team)
    ph = ",".join("?" * len(names))
    q = (f"SELECT p.player_name, p.minutes, p.stats_json FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id "
         f"WHERE p.team_name IN ({ph}) AND p.match_id IN (SELECT DISTINCT p2.match_id FROM match_player_stats p2 JOIN matches m2 "
         f"ON m2.match_id = p2.match_id WHERE p2.team_name IN ({ph}){comp_sql(names, 'm2')} ORDER BY m2.match_date DESC LIMIT 15)")
    try:
        with get_service().db.connect() as conn:
            d = pd.read_sql_query(q, conn, params=names * 2)
    except Exception:
        return pd.DataFrame()
    if d.empty:
        return d
    keys = {"drible": ["dribbles_succeeded"], "cruzamento": ["accurate_crosses"], "aereo": ["aerials_won"],
            "finalizacao": ["totalShots", "xg"], "pressao": ["recoveries", "matchstats.headers.tackles"]}
    rows = []
    for r in d.itertuples():
        try:
            st_ = json.loads(r.stats_json or "{}")
        except Exception:
            st_ = {}
        row = {"nome": r.player_name, "min": float(r.minutes or st_.get("minutes") or 0)}
        for a, ks in keys.items():
            vals = [st_.get(k) for k in ks if st_.get(k) is not None]
            row[a] = float(sum(float(v) for v in vals)) if vals else None
        rows.append(row)
    t = pd.DataFrame(rows)
    g = t.groupby("nome").agg({"min": "sum", **{a: lambda s: s.sum(min_count=1) for a in keys}})
    g = g[g["min"] >= 90]
    for a in keys:
        per90 = g[a] * 90 / g["min"]
        g[a] = per90.rank(pct=True)                       # 0–1 dentro do elenco; sem número → vazio (vale 0,5 no GA)
    return g.drop(columns=["min"]).reset_index()


def _ga_section(team: str, rival: str, squad: pd.DataFrame, formation: str, version: str) -> None:
    """Rodada 9: algoritmo genético — escalação que soma qualidade × encaixe com o ataque às fraquezas do rival."""
    from src.squad.genetic import LineupGA
    from src.ui import vuln_view
    from src.ui.pages.clubs import same_team_names as _stn

    st.markdown(f"##### 🧬 Escalação para machucar {rival} (algoritmo genético)")
    if squad is None or squad.empty or len(squad) < 11:
        st.caption("Elenco com menos de 11 atletas: não dá para montar a escalação.")
        return
    try:
        found = vuln_view._findings(tuple(_stn(rival)), tuple(_stn(team)), version).get("achados", [])
    except Exception:
        found = []
    sq = squad.copy()
    at = _attributes(team, version)
    if not at.empty:
        from src.squad.matchday import canonical_names

        cmap = canonical_names(at["nome"].tolist(), sq["nome"].tolist())
        at["nome"] = at["nome"].map(lambda x: cmap.get(x, x))
        sq = sq.merge(at.drop_duplicates("nome"), on="nome", how="left", suffixes=("", "_perf"))
    with st.spinner("Evoluindo 150 gerações de escalações…"):
        try:
            r = LineupGA(sq, formation, found, seed=42).run()
        except Exception as exc:
            st.caption(f"Não foi possível rodar o algoritmo genético: {exc}")
            return
    c = st.columns(3)
    c[0].metric("Aptidão do genético", r["aptidao"], f"{r['ganho']:+.1f} vs melhor XI")
    c[1].metric("Melhor XI (húngaro) com o rival", r["aptidao_base"])
    c[2].metric("Fraquezas consideradas", len(found))
    if r["ganho"] <= 0.05:
        st.caption("O genético chegou à mesma escalação do melhor XI: para este rival, quem já é o melhor em cada vaga "
                   "também é quem mais explora as fraquezas encontradas.")
    for papel, de, para in r["mudancas"]:
        st.markdown(f"- **{papel}**: sai {de}, entra **{para}**")
    tab = pd.DataFrame([{"vaga": x["papel_pt"], "jogador": x["jogador"], "encaixe": x["encaixe"],
                         "bônus contra o rival": x["bonus"], "por quê": "; ".join(x["porque"]) or "—"} for x in r["xi"]])
    comparison_table(tab, "Aptidão = Σ nota × encaixe + bônus por explorar cada fraqueza (gravidade × perfil do atleta, "
                          "relativo ao próprio elenco, nos últimos 15 jogos com números individuais). Sem número do atleta, "
                          "o perfil vale neutro.")


def _left_after(apps: pd.DataFrame, club_id) -> List[Any]:
    """Atletas cujo último jogo foi por outro clube (para não 'trazer de volta' quem já saiu)."""
    from src.squad.planner import _tid

    if apps is None or apps.empty:
        return []
    a = apps.assign(d=pd.to_datetime(apps["data"], errors="coerce")).sort_values("d").groupby("transfermarkt_id").tail(1)
    return a.loc[a["clube_id"].map(_tid) != _tid(club_id), "transfermarkt_id"].tolist()


@_perf_timed("squad._profile")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")  # rodada 14: sobrevive ao fechar o app
def _profile(team: str, n: int, version: str) -> Dict[str, Any]:
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    svc = get_service()
    db = svc.db
    names = same_team_names(team)
    m = D.recent_matches(db, names, max(n * 4, 20))     # sobra: o perfil usa os N mais recentes COM estatística
    if not m.empty:                                    # jogos com lances ainda não abertos: carrega uma vez
        D.ensure_events(svc, m.head(n).loc[lambda x: x["data_level"] == "EVENTS", "match_id"].tolist(), limit=n)
    if m.empty:
        return {"n": 0, "jogos": [], "a_favor": {}, "contra": {}, "corredores": {}}
    # D5: só jogos com profundidade ≥ 2 (escalação/números individuais ou lances com coordenadas)
    from src.data_hub.depth import depth_for_matches

    all_ids = [int(x) for ids in m["ids"] for x in (ids if isinstance(ids, list) else [ids])] if "ids" in m else \
        m["match_id"].astype(int).tolist()
    dep = depth_for_matches(db, all_ids)
    m = m.assign(profundidade=[max(dep.get(int(x), 0) for x in (ids if isinstance(ids, list) else [mid]))
                               for ids, mid in zip(m.get("ids", m["match_id"]), m["match_id"])])
    shallow = int((m["profundidade"] < 2).sum())
    m = m[m["profundidade"] >= 2]
    if m.empty:
        return {"n": 0, "jogos": [], "a_favor": {}, "contra": {}, "corredores": {}, "rasos": shallow}
    st_ = D.merged_stats(db, m, names)
    comps = m["competition_name"].dropna().unique().tolist()
    base = D.baseline(db, comps, (pd.to_datetime(m["match_date"].min()) - pd.Timedelta(days=60)).strftime("%Y-%m-%d"),
                      str(m["match_date"].max()))
    prof = team_profile(m, st_, [names[0]] if not st_.empty else names, base, n)
    prof["rasos"] = shallow
    prof["criterio"] = "jogos recentes com escalação/números individuais ou lances (nível ≥ 2); " + prof.get("criterio", "")
    used = {g["match_id"] for g in prof["jogos"]}
    ev_ids = m.loc[(m["data_level"] == "EVENTS") & m["match_id"].isin(used), "match_id"].tolist()
    prof["corredores"] = D.attack_corridors(db, ev_ids, names)
    prof["competicoes"] = comps
    return prof


# ------------------------------------------------------------------------------------------------ campinho
ROLE_SHORT = {"GK": "GOL", "CB": "ZAG", "LB": "LE", "RB": "LD", "LWB": "ALE", "RWB": "ALD", "DM": "VOL", "CM": "MC",
              "AM": "MEI", "LM": "ME", "RM": "MD", "LW": "PE", "RW": "PD", "ST": "CA"}


def draw_players(fig: go.Figure, xi: List[Dict[str, Any]], team_color: str = "#3B82F6", vertical: bool = False) -> None:
    """
    Jogadores no estilo cartão (FM/FC): círculo na cor do time com a nota dentro, ANEL pela adequação à vaga
    (verde = posição dele, âmbar = adaptado, vermelho = improvisado), sigla da vaga em cima e nome numa etiqueta escura.
    """
    ring = lambda e: "#22C55E" if (e or 0) >= 0.85 else ("#F59E0B" if (e or 0) >= 0.6 else "#EF4444")
    for p in xi:
        x, y = (p["y"], p["x"]) if vertical else (p["x"], p["y"])
        up = 1 if vertical else -1                     # "acima" do círculo: +y no campo em pé, −y no deitado (eixo invertido)
        nota = p.get("qualidade", p.get("nota"))
        hover = (f"<b>{p.get('jogador') or 'vaga livre'}</b><br>{p['papel_pt']}"
                 + (f" · origem: {p.get('papel_natural')}" if p.get("papel_natural") else "")
                 + (f"<br>qualidade {nota} · fase {p.get('fase')}" if nota is not None else "")
                 + (f"<br>chance de começar {p.get('prob_titular')}%" if p.get("prob_titular") is not None else "")
                 + (f"<br>encaixe na vaga {p.get('encaixe')}" if p.get("encaixe") is not None else ""))
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers", showlegend=False, hovertext=[hover], hoverinfo="text",
                                 marker=dict(size=34 if vertical else 40, color=team_color if p.get("jogador") else "#1E2A44",
                                             line=dict(color=ring(p.get("encaixe")) if p.get("jogador") else "#64748B",
                                                       width=3.5))))
        txt = f"{float(nota):.1f}" if nota is not None and p.get("jogador") else ("?" if not p.get("jogador") else "–")
        fig.add_annotation(x=x, y=y, text=f"<b>{txt}</b>", showarrow=False, font=dict(color="#FFFFFF", size=12))
        fig.add_annotation(x=x, y=y + up * 6.2, text=ROLE_SHORT.get(p["papel"], p["papel"]), showarrow=False,
                           font=dict(color="#94A3B8", size=9))
        name = (p.get("jogador") or "vaga").split(" ")
        short = name[-1] if len(name[-1]) > 3 or len(name) == 1 else " ".join(name[-2:])
        fig.add_annotation(x=x, y=y - up * 6.8, text=f"<b>{short}</b>", showarrow=False, font=dict(color="#F5F7FB", size=11),
                           bgcolor="rgba(9,13,22,0.88)", bordercolor="#1E2A44", borderpad=3, borderwidth=1)


def _pitch(xi: List[Dict[str, Any]], plan: Optional[Dict[str, Any]], rival_corr: Dict[str, Any], title: str,
           team_color: str = "#3B82F6", vertical: bool = False) -> go.Figure:
    from src.ui import charts

    if vertical:                                      # meia tela: campo em pé, atacando para cima
        fig = charts.pitch_vertical(title=title)
        draw_players(fig, xi, team_color, vertical=True)
        return fig

    fig = charts.pitch(title=title, height=560)
    # neutralizar: corredor por onde o rival mais chega ao último terço (visto do nosso campo de defesa)
    if rival_corr.get("ataca_por"):
        side, pct = max(rival_corr["ataca_por"].items(), key=lambda kv: kv[1])
        y0, y1 = {"esquerda": (53.3, 80), "centro": (26.7, 53.3), "direita": (0, 26.7)}[side]   # espelhado
        fig.add_shape(type="rect", x0=0, x1=40, y0=y0, y1=y1, fillcolor="rgba(239,68,68,0.16)",
                      line=dict(color=P["secondary"], width=1, dash="dot"), layer="below")
        fig.add_annotation(x=20, y=(y0 + y1) / 2, text=f"⛔ rival chega por aqui ({pct:.0f}%)", showarrow=False,
                           font=dict(color=P["secondary"], size=11))
    if rival_corr.get("sofre_por"):
        side, pct = max(rival_corr["sofre_por"].items(), key=lambda kv: kv[1])
        y = {"esquerda": 12, "centro": 40, "direita": 68}[side]
        fig.add_annotation(x=112, y=y, ax=70, ay=y, xref="x", yref="y", axref="x", ayref="y", showarrow=True,
                           arrowhead=3, arrowwidth=3, arrowcolor=P["accent"], text="")
        fig.add_annotation(x=92, y=y - 5 if y > 10 else y + 5, text=f"explorar: rival sofre por aqui ({pct:.0f}%)",
                           showarrow=False, font=dict(color=P["accent"], size=11))
    from src.ui.drag_pitch import pitch_tips

    for t in pitch_tips(plan):                        # mais leitura além das setas: E/N/F/C com o número que sustenta
        fig.add_trace(go.Scatter(x=[t["x"]], y=[t["y"]], mode="markers+text", text=[t["marca"]], showlegend=False,
                                 marker=dict(size=20, color=t["cor"], opacity=0.85, line=dict(color="#090D16", width=1)),
                                 textfont=dict(color="#090D16", size=10), hovertext=[t["texto"]], hoverinfo="text"))
    draw_players(fig, xi, team_color)
    return fig


def _plan_text(plan: Dict[str, Any], why: List[str]) -> str:
    lines = []
    if plan["neutralizar"]:
        lines.append("**Para neutralizar " + plan["rival"] + ":**")
        lines += [f"- {d['acao']} _(média {d['media']} contra {d['referencia']} da referência, "
                  f"{d['dif_pct']:+.0f}%)_" for d in plan["neutralizar"]]
    if plan["explorar"]:
        lines.append("**Para explorar:**")
        for d in plan["explorar"]:
            ally = d.get("nossa_forca")
            extra = (f" — e é justamente um ponto forte de {plan['nos']} ({ally['rotulo'].lower()} {ally['media']}, "
                     f"{ally['dif_pct']:+.0f}% acima da referência)") if ally else ""
            lines.append(f"- {d['acao']}{extra} _(rival: {d['rotulo'].lower()} {d['media']}, {d['dif_pct']:+.0f}%)_")
    if why:
        lines.append("**Ajustes na escalação:** " + "; ".join(why) + ".")
    if not lines:
        lines.append("Os números do rival nos jogos escolhidos ficaram perto da média das competições — sem um traço "
                     "marcante para atacar ou neutralizar. Aumente o número de jogos.")
    return "\n".join(lines)


def _traits_table(items: List[Dict[str, Any]], better_word: str) -> pd.DataFrame:
    return pd.DataFrame([{"Indicador": d["rotulo"], "Média": d["media"], "Referência": d["referencia"],
                          better_word: f"{d['dif_pct']:+.0f}%", "Jogos": d["jogos"]} for d in items])


# ------------------------------------------------------------------------------------------------ próximo jogo
@_perf_timed("squad._matchday")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")  # rodada 14: sobrevive ao fechar o app
def _matchday(team: str, version: str, n: int, target_competition: Optional[str] = None) -> Dict[str, Any]:
    from src.squad import matchday as M
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    names = same_team_names(team)
    tm = D.table("tm_jogadores", ["nome", "valor_mercado_eur", "ultima_temporada", "funcao", "posicao"])
    if not tm.empty:
        tm = tm[pd.to_numeric(tm["ultima_temporada"], errors="coerce").fillna(0) >= date.today().year - 2]
    db = get_service().db
    try:                                    # rodada 5: sem escalações recentes → baixa NA HORA os últimos jogos na FotMob
        ph = ",".join("?" * len(names))
        with db.connect() as conn:
            recent = conn.execute(f"SELECT COUNT(DISTINCT l.match_id) FROM match_lineups l JOIN matches m ON m.match_id = "
                                  f"l.match_id WHERE l.team_name IN ({ph}) AND m.match_date >= date('now', '-45 days'){comp_sql(names, 'm')}",
                                  list(names)).fetchone()[0]
        if recent < 4 and get_service().fotmob.enabled:
            # rodada 27f: baixa em SEGUNDO PLANO (antes era dentro do clique: 1–5 min na Escalação)
            from src.ui import bg_fetch

            svc_ = get_service()
            bg_fetch.schedule("teams:" + "|".join(sorted(names)), lambda: svc_.fotmob.ensure_teams(list(names), n=12))
    except Exception:
        pass
    info = M.player_table(db, names, n=n, tm_values=tm, target_competition=target_competition)
    return {"info": info, "names": names}


@st.cache_data(show_spinner=False, ttl=900, max_entries=32)
def _preview(match_id: int, league: str, names: tuple) -> Dict[str, Any]:
    """Pré-jogo da ESPN (escalação oficial ~1 h antes + notícias dos clubes); cache de 15 min."""
    from src.ui.context import get_service

    try:
        svc = get_service()
        if not svc.espn.enabled:
            return {}
        roster_names = []
        from src.ui import bg_fetch                      # rodada 27f: ESPN em segundo plano, a tela não espera

        if not bg_fetch.in_ui():
            return svc.espn.preview(match_id, league, list(names) + roster_names)
        return bg_fetch.value(f"preview:{match_id}", lambda: svc.espn.preview(match_id, league, list(names))) or {}
    except Exception:
        return {}


def _xi_cards(xi: List[Dict[str, Any]], color: str) -> None:
    rows = []
    for p in sorted(xi, key=lambda q: -q["x"]):
        if not p.get("jogador"):
            continue
        why = " · ".join(p.get("porque") or [])
        chips = "".join(
            f'<span style="background:#111A2E;border:1px solid #1E2A44;border-radius:999px;padding:1px 8px;margin-left:6px;'
            f'font-size:.75rem;color:{c}">{lab} {v}</span>'
            for lab, v, c in (("qualidade", p.get("qualidade"), "#22D3EE"), ("fase", p.get("fase"), "#A78BFA"),
                              ("titular", f'{p.get("prob_titular")}%' if p.get("prob_titular") is not None else None, "#FBBF24"),
                              ("encaixe", p.get("encaixe"), "#22C55E")) if v is not None)
        d = p.get("destaques") or {}
        box = lambda items, bg, bd, icon: "".join(
            f'<div style="background:{bg};border:1px solid {bd};border-radius:10px;padding:5px 9px;margin:4px 6px 0 0;'
            f'display:inline-block;font-size:.85rem;color:#F1F5F9"><b>{icon} {x["rotulo"]}</b> {x["valor"]} '
            f'<span style="opacity:.8">(melhor que {x["percentil"]}% da função)</span></div>' for x in items)
        hl = ""
        if d.get("fortes") or d.get("fracos"):
            hl = ('<div style="margin-top:6px">' + box(d.get("fortes") or [], "rgba(34,197,94,.14)", "#22C55E", "✅")
                  + box(d.get("fracos") or [], "rgba(239,68,68,.14)", "#EF4444", "⚠️") + "</div>"
                  + f'<div style="color:#64748B;font-size:.75rem;margin-top:3px">números por jogador de {d["jogos"]} jogos ({d["minutos"]} min) — só os jogos em que a fonte publicou estatística individual, '
                  f'contra {_pl(d["funcao"])} de outros jogos</div>')
        rows.append(f'<div style="border-left:4px solid {color};background:#0F1626;border-radius:12px;padding:9px 12px;'
                    f'margin-bottom:8px"><b style="font-size:1rem;color:#F5F7FB">{p["papel_pt"]}: {p["jogador"]}</b>{chips}{hl}'
                    f'<div style="color:#CBD5E1;font-size:.82rem;margin-top:5px">{why}</div></div>')
    st.markdown("".join(rows), unsafe_allow_html=True)


@st.cache_data(show_spinner=False, ttl=1800)
def _teams_with_lineups(days: int = 400) -> List[str]:
    """Times com escalação na base no último ano (adversários possíveis do jogo hipotético)."""
    from src.ui.context import get_service

    try:
        with get_service().db.connect() as conn:
            rows = conn.execute("SELECT DISTINCT l.team_name FROM match_lineups l JOIN matches m ON m.match_id = l.match_id "
                                "WHERE m.match_date >= date('now', ?) ORDER BY l.team_name", (f"-{int(days)} days",)).fetchall()
    except Exception:
        return []
    return [r[0] for r in rows if r[0]]


def _grouped(rows, field: str) -> str:
    """Rodada 10: 'Motivo: nome1, nome2…' em vez de repetir a mesma frase para cada atleta."""
    from collections import OrderedDict

    g: "OrderedDict[str, list]" = OrderedDict()
    for r in rows:
        g.setdefault(str(getattr(r, field)), []).append(str(r.nome))
    return " · ".join(f"**{k}**: {', '.join(v)}" for k, v in g.items())


@st.cache_data(show_spinner=False, max_entries=64, persist="disk")
def _predict_cached(home, away, home_names, away_names, comp, kickoff, kind, version):
    from src.analytics import score_probs as SP
    from src.ui.context import get_service

    return SP.predict(get_service().db, home, away, list(home_names), list(away_names), comp, kickoff, kind)


def _probabilities(team, rival, my_names, rv_names, f, version, w) -> None:
    """Rodada 25b: placares mais prováveis (estilo Sofascore), vitória/empate/derrota e classificação/título."""
    import plotly.graph_objects as go

    home_is_me = f is None or str(f["home"]) in my_names
    home, away = (team, rival) if home_is_me else (rival, team)
    hn, an = (my_names, rv_names) if home_is_me else (rv_names, my_names)
    comp = str(f["competition"]) if f is not None else ""
    kick = str(f["kickoff"]) if f is not None else ""
    kinds = {"auto": "Detectar sozinho", "pontos": "Campeonato (pontos)", "unico": "Mata-mata (jogo único)",
             "volta": "Mata-mata (jogo de volta)", "final": "Final"}
    with st.expander("🎲 Probabilidades do jogo — placares, resultado e classificação", expanded=True):
        kind = st.selectbox("Tipo de jogo", list(kinds), format_func=kinds.get, key=f"{w}_kind_{team}",
                            help="Em mata-mata o empate vai para prorrogação/pênaltis; no jogo de volta o placar da ida "
                                 "(achado na base) entra na conta; na final a classificação é o título.")
        r = _predict_cached(home, away, tuple(hn), tuple(an), comp, kick, kind, version)
        if not r.get("ok"):
            st.caption(f"Sem probabilidades: {r.get('motivo')}.")
            return
        res, xg = r["resultado"], r["gols_esperados"]
        c = st.columns(3)
        c[0].metric(f"Vitória {home}", f"{100 * res['mandante']:.0f}%")
        c[1].metric("Empate", f"{100 * res['empate']:.0f}%")
        c[2].metric(f"Vitória {away}", f"{100 * res['visitante']:.0f}%")
        if r.get("classificacao"):
            cl = r["classificacao"]
            word = "título" if r.get("titulo") else "classificação"
            ida = r.get("ida")
            st.markdown(f"**Chance de {word}:** {home} **{100 * cl['mandante']:.0f}%** × {away} "
                        f"**{100 * cl['visitante']:.0f}%** — {100 * cl['prorrogacao_ou_penaltis']:.0f}% de ir para "
                        "prorrogação/pênaltis" + (f" · ida em {ida['data']}: {home} {ida['gols_mandante_hoje']} x "
                                                   f"{ida['gols_visitante_hoje']} {away}" if ida else ""))
        m = np.array(r["matriz"])[:6, :6]
        fig = go.Figure(go.Heatmap(z=100 * m, x=[str(j) for j in range(6)], y=[str(i) for i in range(6)],
                                   colorscale=[[0, "#0B1120"], [.5, "#1D4ED8"], [1, "#22D3EE"]], showscale=False,
                                   text=[[f"{100 * v:.1f}%" for v in row] for row in m], texttemplate="%{text}",
                                   hovertemplate=f"{home} %{{y}} x %{{x}} {away}: %{{text}}<extra></extra>"))
        fig.update_layout(height=330, paper_bgcolor="#090D16", plot_bgcolor="#090D16", font=dict(color="#F5F7FB"),
                          margin=dict(l=50, r=10, t=30, b=40), title=dict(text="Probabilidade de cada placar", font=dict(size=13)),
                          xaxis=dict(title=f"gols {away}"), yaxis=dict(title=f"gols {home}", autorange="reversed"))
        a, b = st.columns([1.5, 1])
        a.plotly_chart(fig, use_container_width=True, key=f"{w}_probmap_{team}")
        b.markdown("**Placares mais prováveis**")
        b.markdown("\n".join(f"- {home} {p['placar'].split(' x ')[0]} x {p['placar'].split(' x ')[1]} {away}: "
                              f"**{100 * p['prob']:.1f}%**" for p in r["placares"][:6]))
        b.caption(f"Gols esperados: {home} {xg['mandante']:.2f} × {xg['visitante']:.2f} {away} · mais de 2,5 gols "
                  f"{100 * r['over_2_5']:.0f}% · ambos marcam {100 * r['ambos_marcam']:.0f}%")
        bs = r.get("base") or {}
        st.caption("ESTIMATIVA: força de cada time nos últimos 20 jogos com estatísticas (70% gols esperados + 30% gols, "
                   "puxada para a média com poucos jogos), mando de campo ±10%, placares por Poisson com correção de "
                   "Dixon-Coles para placares baixos. Base: " + " · ".join(
                       f"{k}: {v.get('jogos', 0)} jogos ({v.get('com_xg', 0)} com xG)" for k, v in bs.items()) +
                   ". Não considera desfalques nem a escalação do dia.")


def _next_match_tab(team: str, version: str, n: int, kind: str = "prox") -> None:
    """Rodada 10: 'prox' = próximo jogo do calendário (sem perguntar o adversário); 'hyp' = jogo hipotético."""
    from src.squad import matchday as M
    from src.ui.context import get_service

    me = _matchday(team, version, n)
    fx = M.next_fixtures(get_service().db, me["names"]) if kind == "prox" else pd.DataFrame()
    pv: Dict[str, Any] = {}
    w = "nx" if kind == "prox" else "hy"
    if kind == "prox":
        if fx.empty:
            empty_state("Sem próximos jogos no calendário", "O calendário vem da ESPN (temporada atual). Use o jogo "
                        "hipotético para montar contra qualquer adversário.", "📅",
                        "python -m src.data_hub.sync --only espn_temporada")
            return
        labels = [f"{r.kickoff[:10]} {r.kickoff[11:16]} · {r.home} x {r.away} · {r.competition}" for r in fx.itertuples()]
        lab = st.selectbox("Próximo jogo", labels, key=f"nx_pick_{team}")
        f = fx.iloc[labels.index(lab)]
        rival = f["away"] if f["home"] in me["names"] else f["home"]
        if st.button(f"🔎 Analisar este jogo (plano de jogo e escalação contra {rival})", type="primary",
                     key=f"nx_analyse_{team}"):
            st.session_state["sq_rival_choice"], st.session_state["sq_rival_src"] = rival, "próximo jogo"
            st.rerun()
    else:
        opts = [t for t in _teams_with_lineups() if t not in me["names"]]
        if not opts:
            empty_state("Sem adversários com escalação na base", "Baixe resumos de jogos recentes.", "🧪",
                        "python -m src.data_hub.sync --only espn_resumos")
            return
        with st.form(f"hy_form_{team}", border=False):
            q = st.text_input("Adversário hipotético (digite e aperte Enter)", key=f"nx_hq_{team}")
            st.form_submit_button("🔎 Buscar adversário")
        flt = [t for t in opts if q.strip().lower() in t.lower()] if q.strip() else opts
        rival = st.selectbox("Adversário", flt or opts, key=f"nx_hyp_{team}")
        if st.button(f"🔎 Analisar este jogo (plano de jogo e escalação contra {rival})", type="primary",
                     key=f"hy_analyse_{team}"):
            st.session_state["sq_rival_choice"], st.session_state["sq_rival_src"] = rival, "jogo hipotético"
            st.session_state[f"hy_go_{team}"] = rival
            st.rerun()
        if st.session_state.get(f"hy_go_{team}") != rival:   # rodada 11: só calcula depois de confirmar (era pesado)
            st.caption("Escolha o adversário e clique em 'Analisar este jogo' — a análise completa só roda depois disso.")
            return
        st.caption("Jogo hipotético: mesma leitura do próximo jogo (provável, desfalques, fragilidades e plano), sem "
                   "escalação oficial nem notícias, que só existem para jogos marcados.")
        f = None
    version = _tv(team, rival)                           # rodada 14: muda quando QUALQUER um dos dois ganha dado novo
    rv = _matchday(rival, version, n)
    # Recalcula a disponibilidade com o torneio do próximo jogo; amarelos/vermelhos de outra competição não contaminam o XI.
    target_comp = str(f["competition"]) if f is not None and f.get("competition") else None
    if target_comp:
        me = _matchday(team, version, n, target_comp)
        rv = _matchday(rival, version, n, target_comp)
    a, b = me["info"], rv["info"]
    if (a["jogadores"] is None or a["jogadores"].empty) or (b["jogadores"] is None or b["jogadores"].empty):
        note("Faltam escalações recentes", "Baixe os resumos dos jogos (estatísticas + escalações): "
             "`python -m src.data_hub.sync --only espn_resumos` e os elencos: `--only espn_elencos`.", "warn")
    for nm, inf in ((team, a), (rival, b)):
        if not inf.get("jogos"):
            note(f"{nm}: nenhuma escalação recente na base",
                 "Sem escalações, a provável abaixo usa só o elenco e a posição de cadastro (qualidade e chance de começar "
                 "ficam perto de zero — não é uma avaliação dos jogadores). A FotMob está baixando os jogos em segundo "
                 "plano; volte em alguns minutos.", "warn")
        elif (inf.get("dias_desde_ultima_escalacao") or 0) > 30:
            note(f"{nm}: escalações desatualizadas",
                 f"A escalação mais recente na base é de {inf['dias_desde_ultima_escalacao']} dias atrás. Quem não está no "
                 "elenco atual já sai da conta, mas a titularidade pode estar velha.", "warn")
    st.caption(f"Base: últimos {len(a['jogos'])} jogos de {team} e {len(b['jogos'])} de {rival} com escalação · "
               f"elenco: {a['fonte_elenco']} / {b['fonte_elenco']}. Provável = quem tem começado jogando, sem lesionados "
               "e suspensos — a escalação oficial só sai cerca de 1 h antes do jogo.")
    if f is not None:
        pv = _preview(int(f["match_id"]), str(f["league"]), tuple(me["names"] + rv["names"]))
    off = pv.get("oficial") or {}
    off_me = next((v for k, v in off.items() if k in me["names"]), None)
    off_rv = next((v for k, v in off.items() if k in rv["names"]), None)
    if off:
        st.success("✅ A ESPN já publicou a escalação OFICIAL deste jogo — ela substitui a provável abaixo.")
    # ---------------------------------------------------------------- rodada 13: layout novo (nada removido)
    from src.ui import matchday_view as MV

    xr, fr = M.official_xi(b, off_rv) if off_rv else M.xi_for(b, None, "provavel")
    weak = M.sector_weaknesses(b, rival)
    form_me = st.session_state.get("nx_form") or None
    when = f"{str(f['kickoff'])[:10]} {str(f['kickoff'])[11:16]}" if f is not None else "jogo hipotético"
    comp_txt = str(f["competition"]) if f is not None else ""
    home_is_team = True
    if f is not None:
        try:
            home_is_team = str(f.get("home")) in set(me["names"]) or str(f.get("away")) not in set(me["names"])
        except Exception:                             # noqa: BLE001
            home_is_team = True
    st.markdown(MV.hero(team, rival, when, comp_txt, "✅ escalações OFICIAIS publicadas" if off else
                        "escalações prováveis (a oficial sai ~1 h antes)", team_home=home_is_team),
                unsafe_allow_html=True)
    _probabilities(team, rival, me["names"], rv["names"], f, version, w)       # rodada 25b
    mode = st.radio("Nossa escalação", ["Provável", "Melhor contra o rival"], horizontal=True, key=f"{w}_mode")
    if off_me and mode == "Provável":
        xm, fm = M.official_xi(a, off_me)
    else:
        xm, fm = M.xi_for(a, form_me, "provavel" if mode == "Provável" else "melhor")
    try:
        from src.squad import matchups as MU

        mu = _matchups(team, rival, tuple(me["names"]), tuple(rv["names"]), version,
                       tuple((x.get("papel"), x.get("jogador"), x.get("x"), x.get("y")) for x in xm),
                       tuple((x.get("papel"), x.get("jogador"), x.get("x"), x.get("y")) for x in xr),
                       str(fm or ""), str(fr or ""))
    except Exception as exc:                          # noqa: BLE001
        mu = {"forcar": [], "proteger": [], "estilo": [], "evitar": [], "base": f"confrontos indisponíveis ({exc})"}
    flags = {}
    for i, x in enumerate(mu["forcar"][:6], 1):
        if x.get("defensor"):
            flags.setdefault(x["defensor"], i)
    pc, sc = st.columns([1.05, 1])
    with pc:
        st.markdown(MV.double_pitch(xm, xr, f"{team} ({fm})", f"{rival} ({fr})", flags), unsafe_allow_html=True)
        st.caption("Número no círculo = qualidade (0–100, a mesma do Scout; com * = estimada pela escalação, sem nota no Scout). Anel laranja com número = defensor deles que a IA marcou "
                   "como alvo (ver o confronto com o mesmo número ao lado). Passe o mouse para ver nome e posição.")
    with sc:
        st.markdown("#### ⚔️ Onde ganhar o jogo")
        st.caption("Nossa qualidade contra o defeito deles, pelos últimos jogos: duelos 1×1, combinações (cruzamento + "
                   "cabeceio, bola longa nas costas, pressão no pivô…) e de onde saem os gols deles. No máximo 2 dicas do "
                   "mesmo tipo. 🔥 = escancarado (topo × fundo da base); ✅ = claro. " + mu.get("base", ""))
        if not (mu["forcar"] or mu["estilo"]):
            st.info("Nenhum confronto com vantagem clara nos números dos últimos jogos — veja 'Onde atacar' para as "
                    "fragilidades gerais do rival.")
        for i, x in enumerate(mu["forcar"][:6], 1):
            st.markdown(MV.finding_card(i, x, "forcar"), unsafe_allow_html=True)
            _brain_buttons("confrontos", x.get("dimensao", "duelo"), f"{w}_mu_{i}", x)
        for x in mu["estilo"][:3]:
            st.markdown(MV.finding_card("★", x, "estilo"), unsafe_allow_html=True)
    if mu["proteger"] or mu["evitar"]:
        st.markdown("#### 🛡️ Onde NÃO deixar o jogo ir (força deles × nosso ponto fraco)")
        cols = st.columns(2)
        for i, x in enumerate((mu["proteger"][:4] + mu["evitar"][:2]), 1):
            with cols[(i - 1) % 2]:
                st.markdown(MV.finding_card(i, x, "proteger" if x.get("tipo") == "duelo" else "evitar"),
                            unsafe_allow_html=True)
    tabs = st.tabs(["🧭 Onde atacar", "👥 Escalações e porquês", "🔍 Leitura do rival", "🩹 Onde sofremos",
                    "✏️ Editar o campinho"] + (["📰 Notícias"] if pv.get("noticias") else []) + ["🧠 Modelo de jogo do rival",
                                                                                                    "📋 Relatório do olheiro"],
                   key=f"{w}_tabs", on_change="rerun")
    with tabs[-1]:                                     # rodada 23: relatório do olheiro do rival estilo FM
        if tabs[-1].open is not False:          # rodada 27e: só a aba aberta é montada
            from src.ui import team_report_view

            team_report_view.render(rival, rv["names"], version, key=f"{w}_tr", my_team=team, my_names=me["names"])
    with tabs[-2]:                                     # rodada 22: identidade tática do rival + plano por fase
        if tabs[-2].open is not False:          # rodada 27e: só a aba aberta é montada
            from src.ui import identity_view
            from src.analytics import tactical_identity as TI

            identity_view.render(rival, rv["names"], version, key=f"{w}_rival")
            try:
                plan = TI.opposition_plan(identity_view._data(tuple(rv["names"]), version, 20))
            except Exception:
                plan = []
            if plan:
                st.markdown(f"##### ♟️ Plano contra o modelo de jogo de {rival}")
                for x in plan:
                    st.markdown(f"- **{x['fase']}** — {x['acao']} *(base: {x['base']})*")
    with tabs[0]:
        if tabs[0].open is not False:          # rodada 27e: só a aba aberta é montada
            from src.ui import vuln_view

            out_rv = b["jogadores"][b["jogadores"]["indisponivel"].astype(bool)]["nome"].tolist() \
                if not b["jogadores"].empty and "indisponivel" in b["jogadores"] else []
            vuln_view.render(rival, rv["names"], me["names"], version, where=w,
                             lineup=[x.get("jogador") for x in xr if x.get("jogador")], out=out_rv)
    with tabs[1]:
        if tabs[1].open is not False:          # rodada 27e: só a aba aberta é montada
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"#### 🔵 {team} — {mode.lower()} ({fm})")
                out = a["jogadores"][a["jogadores"]["indisponivel"].astype(bool)] if not a["jogadores"].empty else a["jogadores"]
                if len(out):
                    st.markdown(f"**Nossos desfalques ({len(out)}):** " + "; ".join(f"{r.nome} ({r.indisponivel})" for r in out.itertuples()))
                dv = a["jogadores"][a["jogadores"]["duvida"].astype(bool)] if "duvida" in a["jogadores"] else a["jogadores"].iloc[0:0]
                if len(dv):
                    st.markdown(f"**Nossas dúvidas ({len(dv)}):** " + _grouped(dv.itertuples(), "duvida"))
                st.markdown("**Por que cada jogador nosso foi escolhido**")
                _xi_cards(xm, "#22D3EE")
            with c2:
                st.markdown(f"#### 🔴 {rival} provável ({fr})")
                out = b["jogadores"][b["jogadores"]["indisponivel"].astype(bool)] if not b["jogadores"].empty else b["jogadores"]
                if len(out):
                    st.markdown(f"**Desfalques ({len(out)}):** " + "; ".join(f"{r.nome} ({r.indisponivel})" for r in out.itertuples()))
                dv = b["jogadores"][b["jogadores"].get("duvida", "").astype(bool)] if "duvida" in b["jogadores"] else b["jogadores"].iloc[0:0]
                if len(dv):
                    st.markdown(f"**Dúvidas ({len(dv)}):** " + _grouped(dv.itertuples(), "duvida"))
                st.markdown("**Por que cada jogador do rival deve começar**")
                _xi_cards(xr, "#EF4444")
    with tabs[2]:
        if tabs[2].open is not False:          # rodada 27e: só a aba aberta é montada
            k1, k2 = st.columns(2)
            with k1:
                st.markdown("**Fragilidades por setor (dados dos últimos jogos)**")
                for wk in weak[:6] or []:
                    st.markdown(f'<div class="fm-card" style="border-left:4px solid #F59E0B;border-radius:14px;padding:.55rem .9rem;'
                                f'margin-bottom:.45rem">⚠️ {wk["texto"]}</div>', unsafe_allow_html=True)
                if not weak:
                    st.caption("Nenhuma fragilidade clara por setor nos jogos recentes (sem desfalques, posições estáveis).")
            with k2:
                st.markdown("**Quem decide do lado deles**")
                for t in M.threats(b):
                    st.markdown(f'<div class="fm-card" style="border-left:4px solid #EF4444;border-radius:14px;padding:.55rem .9rem;'
                                f'margin-bottom:.45rem">🎯 <b>{t["nome"]}</b> ({t["papel"] or "?"}{", lado " + t["lado"] if t["lado"] else ""}): '
                                f'{t["gols"]} gols e {t["assistencias"]} assistências nos últimos {len(b["jogos"])} jogos</div>',
                                unsafe_allow_html=True)
            try:                                           # rodada 5: estilo habitual e problemas que se repetem (pré-jogo)
                from src.ui.pages.patterns import _history

                hx = _history(rival, int(f["match_id"]) if f is not None else 0, version)
                idn, vu = hx.get("identidade") or {}, hx.get("vulneraveis") or {}
                if idn.get("tracos") or vu.get("padroes") or vu.get("sinais"):
                    st.markdown(f"**🧬 Como {rival} costuma jogar e onde costuma sofrer** (últimos {idn.get('jogos', 0)} jogos com estatísticas)")
                    for t_ in idn.get("tracos") or []:
                        st.markdown(f"- {rival} {t_['traco']} — {t_['metrica']} {t_['media']} (normal {t_['referencia']}), em "
                                    f"{t_['frequencia_pct']}% dos jogos")
                    for p_ in vu.get("padroes") or []:
                        st.markdown(f"- 🩹 **Padrão:** {p_['problema']} ({p_['jogos_acima']} de {p_['jogos']} jogos) — explore isso")
                    for p_ in vu.get("sinais") or []:
                        st.markdown(f"- ⚠️ Sinal: {p_['problema']} ({p_['jogos_acima']} de {p_['jogos']} jogos)")
            except Exception:
                pass
            lu = b["escalacoes"]
            if lu is not None and not lu.empty:
                with st.expander(f"Últimos jogos de {rival} usados na leitura"):
                    g = lu.drop_duplicates("match_id")[["data", "adversario", "home_score", "away_score", "competition_name", "formation"]]
                    comparison_table(g.rename(columns={"data": "Data", "adversario": "Adversário", "home_score": "Mandante",
                                                       "away_score": "Visitante", "competition_name": "Competição",
                                                       "formation": "Formação"}))
    with tabs[3]:
        if tabs[3].open is not False:          # rodada 27e: só a aba aberta é montada
            from src.ui import vuln_view

            st.caption(f"Onde {team} sofre — pontos a corrigir antes do jogo.")
            out_me = a["jogadores"][a["jogadores"]["indisponivel"].astype(bool)]["nome"].tolist() \
                if not a["jogadores"].empty and "indisponivel" in a["jogadores"] else []
            vuln_view.render(team, me["names"], rv["names"], version, mine=True, where=w,
                             lineup=[x.get("jogador") for x in xm if x.get("jogador")], out=out_me)
    with tabs[4]:
        if tabs[4].open is not False:          # rodada 27e: só a aba aberta é montada
            c1, c2 = st.columns(2)
            with c1:
                import streamlit.components.v1 as components

                from src.ui import drag_pitch

                used = {x.get("jogador") for x in xm}
                pl = a["jogadores"] if a["jogadores"] is not None else pd.DataFrame()
                bench = [{"nome": r["nome"], "nota": r.get("qualidade"), "papel_pt": str(r.get("papel") or "")}
                         for r in pl.to_dict("records") if r.get("nome") not in used and not r.get("indisponivel")][:14]
                components.html(drag_pitch.html(team, fm, xm, bench, M.weakness_tips(weak, b) if weak else []), height=760)
                st.caption("Arraste, troque com o banco e mude a formação. As mudanças ficam neste navegador (não alteram a base).")
            with c2:
                render_chart(_pitch(xr, None, {}, f"{rival} — provável ({fr})", team_color="#EF4444", vertical=True),
                             use_container_width=True, key=f"{w}_pitch_r")
                st.caption("Dentro do círculo: qualidade (0–100). Anel: 🟢 posição dele · 🟠 adaptado · 🔴 improvisado.")
    if pv.get("noticias"):
        with tabs[5]:
            if tabs[5].open is not False:
                st.caption("Notícia, não dado confirmado.")
                for nw in pv["noticias"]:
                    st.markdown(f"**{nw['titulo']}** · {nw['data']}  \n{nw['resumo']}")


def _tv(*teams) -> str:
    """Versão dos caches pelos times envolvidos (muda só quando eles ganham dado novo, ou no dia seguinte)."""
    from src.ui.context import get_service

    db = get_service().db
    # "r20": apelidos aprendidos entre fontes — análises guardadas antes (rival com "0 jogos") são refeitas
    return "r27|" + ("|".join(db.team_version([t]) for t in teams if t) or db.stable_version())


def _pl(word):
    from src.analytics.vulnerabilities import _pl as plural

    return plural(word)


@st.fragment
def _brain_buttons(module: str, kind: str, key: str, ctx_info: Dict[str, Any]) -> None:
    """👍/👎 que treinam a IA do laboratório (o tipo aprovado sobe nas próximas análises).
    Rodada 21: fragmento — o clique refaz só os botões, não o pré-jogo inteiro."""
    from src.intelligence import lab_brain as LB

    a, b, _ = st.columns([.6, .6, 6])
    info = {k: ctx_info.get(k) for k in ("titulo", "atacante", "defensor", "nivel")}
    if a.button("👍", key=f"{key}_up", help="Análise útil — a IA passa a valorizar este tipo"):
        LB.feedback(module, kind, True, info)
        st.toast("Obrigado! A IA do laboratório aprendeu com isso.")
    if b.button("👎", key=f"{key}_dn", help="Não ajudou — a IA passa a mostrar menos este tipo"):
        LB.feedback(module, kind, False, info)
        st.toast("Anotado. Este tipo de análise perde peso.")


@_perf_timed("squad._matchups")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")  # rodada 14: sobrevive ao fechar o app
def _matchups(team, rival, my_names, rv_names, version, my_xi, rv_xi, formation="", rival_formation=""):
    from src.squad import matchups as MU
    from src.ui.context import get_service

    unpack = lambda xs: [{"papel": p, "jogador": j, "x": x, "y": y} for p, j, x, y in xs]
    return MU.analyze(get_service().db, team, rival, list(my_names), list(rv_names), unpack(my_xi), unpack(rv_xi),
                      str(formation or ""), str(rival_formation or ""))


# ------------------------------------------------------------------------------------------------ página
def render(_ctx=None) -> None:
    from src.ui.context import get_service

    hero("Escalação", "Monte o time para o próximo jogo",
         "Elenco atual (Transfermarkt + atletas que você cadastrar), nota do laboratório, escalação provável, a melhor "
         "possível e a ajustada ao adversário — com o plano de jogo tirado dos últimos jogos do rival.")
    team = _picker("Meu time", "sq_team")
    version = _tv(team)                                  # rodada 14: versão por time (cache não cai a cada 10 min)
    from src.data_lake.ids import team_core as _tc

    if team and _tc(str(st.session_state.get("sq_rival_team") or "")) != _tc(team):   # outro time: adversário não vale mais
        st.session_state["sq_rival_team"] = team
        st.session_state.pop("sq_rival_choice", None)
    rival = st.session_state.get("sq_rival_choice")
    if not rival and team:                                         # padrão: o próximo jogo do calendário
        try:
            from src.squad import matchday as _M

            _fx = _M.next_fixtures(get_service().db, _matchday(team, version, 10)["names"], limit=1)
            if not _fx.empty:
                from src.ui.pages.clubs import same_team_names as _stn0

                rival = _fx.iloc[0]["away"] if _fx.iloc[0]["home"] in _stn0(team) else _fx.iloc[0]["home"]
                st.session_state["sq_rival_src"] = "próximo jogo"
        except Exception:
            rival = None
    if rival:
        st.caption(f"Adversário em análise no Plano de jogo e na escalação 'Contra o adversário': **{rival}** "
                   f"({st.session_state.get('sq_rival_src', 'escolhido')}). Para trocar, use as abas 🔭 Próximo jogo "
                   "ou 🧪 Jogo hipotético e clique em 'Analisar este jogo'.")
    try:
        from src.ui import bg_fetch as _bg

        if team and _bg.running_for(team):
            st.caption(f"📥 Baixando em segundo plano os jogos/elenco mais recentes de {team} — a tela já mostra o que "
                       "está na base; reabra em ~1 minuto para ver completo.")
    except Exception:
        pass
    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    formation = c1.selectbox("Formação", list(FORMATIONS), key="sq_form")
    n = c2.select_slider("Últimos jogos", N_OPTIONS, value=N_OPTIONS[-1], key="sq_n")      # rodada 22: visão conjunta
    mode = c3.radio("Escalação", ["Provável", "Melhor possível", "Contra o adversário"], horizontal=True, key="sq_mode",
                    help="Provável: quem mais começou jogando nos últimos jogos. Melhor possível: maior nota × encaixe "
                         "na posição. Contra o adversário: a melhor, com ajustes pelo plano de jogo.")
    if not team:
        empty_state("Escolha o seu time", "Digite o nome no campo 'Meu time'.", "📋")
        return
    from src.ui import warmup as _warm

    _warm.remember("time", team)
    if rival and team:
        from src.ui.pages.clubs import same_team_names

        if rival in same_team_names(team):
            st.warning(f"O adversário é o próprio {team}. Escolha outro time no campo 'Adversário' — por enquanto a "
                       "análise segue sem adversário.")
            rival = None
    with st.spinner("Montando elenco e perfis..."):
        from src.scout import snapshot as _scout_snapshot

        # Invalida o cache antigo do elenco: o resolvedor por PID podia guardar o overall 65/71 do Otávio.
        sq = _squad(team, f"{version}|{_scout_snapshot.version()}|overall-name-club-v1")
        mine = _profile(team, n, version)
        theirs = _profile(rival, n, version) if rival else None
    squad = sq["squad"]
    plan = matchup_plan(mine, theirs, team, rival) if theirs else None

    t0, th, t1, t2, t3, t4, t5 = st.tabs(["🔭 Próximo jogo", "🧪 Jogo hipotético", "🧩 Campinho", "🎯 Plano de jogo",
                                          "👥 Elenco e notas", "➕ Adicionar atleta", "💾 Escalações salvas"],
                                         key="sq_main_tabs", on_change="rerun")
    for tab_, kind_ in ((t0, "prox"), (th, "hyp")):
        with tab_:
            if tab_.open is not False:          # rodada 21: só a aba aberta é montada
                try:
                    _next_match_tab(team, version, max(n, 10), kind_)
                except Exception as exc:
                    from src.ui.components import error_state

                    error_state("Próximo jogo indisponível" if kind_ == "prox" else "Jogo hipotético indisponível", exc)
    with t1:
        if t1.open is not False:          # rodada 21: só a aba aberta é montada
            if squad.empty:
                empty_state("Sem elenco para este time", f"Fonte procurada: Transfermarkt e escalações da base.", "👥",
                            "O Transfermarkt aberto cobre as principais ligas europeias. Para outros clubes, cadastre os "
                            "atletas na aba ➕ ou sincronize jogos com escalação (ESPN histórico).")
            else:
                why: List[str] = []
                info: Dict[str, Any] = {}
                md = _matchday(team, version, max(n, 10))["info"]
                has_recent = md["jogadores"] is not None and not md["jogadores"].empty and len(md["jogos"]) >= 3
                info = {}
                pool = squad
                if has_recent and mode in ("Provável", "Melhor possível"):
                    # v36: escalações reais recentes (ESPN) — titularidade, posição, gols/assistências, lesões e suspensões
                    from src.squad import matchday as M

                    xi, _f = M.xi_for(md, formation, "provavel" if mode == "Provável" else "melhor")
                    info = {"jogos_considerados": len(md["jogos"])}
                    pool = md["jogadores"]
                    st.caption(f"Baseado nos últimos {len(md['jogos'])} jogos com escalação ({md['fonte_elenco']}). "
                               "Lesionados e suspensos ficam de fora. O porquê de cada escolha está logo abaixo do campinho.")
                elif mode == "Provável":
                    lu = D.club_lineups(sq["club"]["transfermarkt_id"], n) if sq["club"] else pd.DataFrame()
                    if lu.empty:
                        lu = D.db_lineups(get_service().db, sq["names"], n)
                    xi, info = probable_xi(lu, squad, formation, n)
                elif mode == "Contra o adversário" and plan:
                    bonus, why = plan_bonus(squad, plan)
                    xi = best_xi(squad, formation, bonus=bonus)
                else:
                    xi = best_xi(squad, formation)
                with st.expander("✏️ Ajustar à mão (troque qualquer vaga)"):
                    names = ["—"] + pool.sort_values("nota", ascending=False, na_position="last")["nome"].tolist()
                    cols = st.columns(4)
                    for i, p in enumerate(xi):
                        k = f"sq_slot_{team}_{formation}_{mode}_{i}"
                        cur = p["jogador"] if p["jogador"] in names else "—"
                        pick = cols[i % 4].selectbox(f"{p['papel_pt']} ({i + 1})", names, index=names.index(cur), key=k)
                        if pick != p["jogador"]:
                            row = pool[pool["nome"] == pick]
                            p.update(jogador=None if pick == "—" else pick,
                                     nota=None if row.empty or pd.isna(row.iloc[0]["nota"]) else float(row.iloc[0]["nota"]),
                                     encaixe=None if row.empty else round(fit(p["papel"], row.iloc[0]["papel"]), 2),
                                     papel_natural=None if row.empty else ROLE_PT.get(row.iloc[0]["papel"], "—"))
                corr = (theirs or {}).get("corredores") or {}
                interactive = st.toggle("🖐️ Campinho interativo (arrastar jogadores, trocar com o banco e de formação)",
                                        value=False, key="sq_drag")
                if interactive:
                    import streamlit.components.v1 as components

                    from src.ui import drag_pitch

                    in_xi = {p["jogador"] for p in xi if p.get("jogador")}
                    bench = [{"nome": r["nome"], "nota": None if pd.isna(r.get("nota")) else float(r["nota"]),
                              "papel_pt": ROLE_PT.get(r.get("papel"), "")}
                             for r in pool.sort_values("nota", ascending=False).to_dict("records") if r["nome"] not in in_xi]
                    components.html(drag_pitch.html(team, formation, xi, bench, drag_pitch.pitch_tips(plan, corr)), height=760)
                    st.caption("Passe o mouse nas marcas: E = explorar · N = neutralizar · F = nossa força · C = cuidado. "
                               "O que você arrasta fica salvo neste navegador; a nota média abaixo é da escalação calculada.")
                else:
                    render_chart(_pitch(xi, plan, corr, f"{team} — {formation} ({mode.lower()})"), use_container_width=True)
                    if any(p.get("porque") for p in xi):
                        with st.expander("🧠 Por que cada jogador foi escolhido", expanded=True):
                            _xi_cards(xi, "#22D3EE")
                    if plan:
                        st.caption("Marcas no campo (passe o mouse): E = explorar a fraqueza do rival · N = neutralizar a força "
                                   "dele · F = nossa força · C = cuidado com o nosso ponto fraco.")
                vals = [p["nota"] for p in xi if p.get("nota") is not None]
                k = st.columns(4)
                k[0].metric("Nota média do XI", f"{sum(vals) / len(vals):.0f}" if vals else "—")
                k[1].metric("Fora de posição", sum(1 for p in xi if (p.get("encaixe") or 0) < 0.85 and p["jogador"]))
                k[2].metric("Elenco disponível", len(squad))
                if mode == "Provável":
                    k[3].metric("Jogos usados", info.get("jogos_considerados", 0))
                st.caption("🔵 na posição de origem · 🟡 adaptado · 🔴 improvisado. O número no círculo é a nota do "
                           "laboratório. Fonte do elenco: " + sq["fonte"] + ".")
                mud = sq.get("mudancas") or []
                if mud:
                    with st.expander(f"🔁 Elenco atualizado pelos jogos: {sum(m['mudanca'] == 'saiu' for m in mud)} saída(s), "
                                     f"{sum(m['mudanca'] == 'chegou' for m in mud)} chegada(s)"):
                        st.caption("O cadastro do Transfermarkt atrasa nas janelas. Quem jogou por outro clube depois do último "
                                   "jogo por este saiu (venda ou empréstimo); quem jogou por este nos últimos 150 dias chegou.")
                        comparison_table(pd.DataFrame(mud).rename(columns={"nome": "Jogador", "mudanca": "Mudança",
                                                                            "motivo": "Por quê"}))
                nc = sq.get("nao_confirmados")
                if nc is not None and not nc.empty:
                    with st.expander(f"❔ {len(nc)} atleta(s) do cadastro sem vínculo confirmado (fora do elenco)"):
                        st.caption("Sem transferência registrada e sem jogo pelo clube nos últimos 12 meses: não dá para "
                                   "afirmar que ainda estão no clube. Cadastre-os em “Adicionar atleta” se estiverem.")
                        comparison_table(nc.rename(columns={"nome": "Atleta", "posicao": "Posição",
                                                            "ultima_temporada": "Última temporada no cadastro"}))
                if why:
                    note("Ajustes pelo adversário", "; ".join(why) + ".")
                if mode == "Provável" and not info.get("jogos_considerados"):
                    note("Sem escalações recentes", "Não há escalações dos últimos jogos deste clube na base: mostrei a melhor "
                         "possível pela nota.", "warn")
                name = st.text_input("Nome para salvar", f"{team} x {rival or 'adversário'} — {formation}", key="sq_save_name")
                if st.button("💾 Salvar esta escalação", key="sq_save"):
                    path = D.save_lineup(name, {"time": team, "adversario": rival, "formacao": formation, "modo": mode,
                                                "jogos_considerados": n, "xi": xi, "plano": plan})
                    st.success(f"Salva em {path}.")
    with t2:
        if t2.open is not False:          # rodada 21: só a aba aberta é montada
            if not rival:
                empty_state("Escolha o adversário", "O plano compara os últimos jogos dos dois times.", "🎯")
            elif not theirs or not theirs.get("n"):
                empty_state(f"Base insuficiente para diagnóstico de {rival}", "", "🎯",
                            "O plano usa só jogos recentes com escalação/números individuais ou lances (nível 2 ou mais). "
                            "Sincronize a liga do adversário.")
            else:
                st.markdown(f"#### {team} x {rival} — últimos {theirs['n']} jogo(s) do rival e {mine.get('n', 0)} nossos")
                skip = sum((x.get("descartados_por_dado_incompleto") or 0) + (x.get("rasos") or 0) for x in (theirs, mine))
                st.caption("Critério: " + (theirs.get("criterio") or "") +
                           (f". {skip} jogo(s) recente(s) com dado incompleto ficaram de fora." if skip else "."))
                from src.squad.planner import rival_diagnosis

                dg = rival_diagnosis(theirs)
                from src.ui import vuln_view
                from src.ui.pages.clubs import same_team_names as _stn

                vuln_view.render(rival, _stn(rival), _stn(team), version, where="plano")   # rodada 7: fragilidades reais por setor/jogador
                _ga_section(team, rival, squad, formation, version)          # rodada 9: algoritmo genético
                st.markdown(f"##### 🔍 Diagnóstico de {rival} pelas estatísticas do time")
                if not dg["suficiente"]:
                    st.caption("Pelas médias do time, não há 2 pontos fortes e 2 fracos claros — veja acima as fragilidades por "
                               "jogador e setor, que usam os números individuais.")
                cards = st.columns(2)
                for col, (title, items, color) in zip(cards, ((f"💪 Onde {rival} é forte", dg["fortalezas"], "#EF4444"),
                                                             (f"🎯 Onde {rival} pode ser explorado", dg["vulnerabilidades"], "#22C55E"))):
                    with col:
                        st.markdown(f"**{title}**")
                        for d in items or []:
                            st.markdown(
                                f'<div class="fm-card" style="border-left:4px solid {color};border-radius:14px;padding:.6rem .9rem;'
                                f'margin-bottom:.5rem"><b>{d["texto"].capitalize()}</b><br><span style="color:#94A3B8;'
                                f'font-size:.85rem">{d["rotulo"]}: {d["media"]} por jogo (média das mesmas competições: '
                                f'{d["referencia"]}, {d["dif_pct"]:+.0f}%) em {d["jogos"]} jogos · onde mais apareceu: '
                                f'{d["origem"]}</span></div>', unsafe_allow_html=True)
                        if not items:
                            st.caption("Nada claro o bastante nos jogos recentes.")
                from src.squad.planner import deep_tactical_signals
                signals = deep_tactical_signals(theirs)
                if signals:
                    st.markdown("##### 🧪 Sinais derivados — além do volume bruto")
                    st.caption("Indicadores calculados jogo a jogo. Não representam tracking posicional; só aparecem quando há "
                               "amostra mínima e estatísticas pareadas.")
                    signal_cols = st.columns(min(3, len(signals)))
                    for col, signal in zip(signal_cols, signals):
                        with col:
                            val = signal["valor"]
                            shown = f"{val:.2f} {signal['unidade']}"
                            st.markdown(
                                f'<div class="fm-card" style="border-top:3px solid #38BDF8;border-radius:12px;padding:.8rem;'
                                f'min-height:170px"><div style="font-size:.78rem;color:#94A3B8">{signal["titulo"]}</div>'
                                f'<div style="font-size:1.45rem;font-weight:800;color:#E0F2FE">{shown}</div>'
                                f'<div style="font-size:.78rem;color:#94A3B8">{signal["jogos"]} jogos pareados</div>'
                                f'<div style="margin-top:.55rem;font-size:.84rem">{signal["leitura"]}</div>'
                                f'<div style="margin-top:.4rem;font-size:.72rem;color:#64748B">{signal["evidencia"]}</div></div>',
                                unsafe_allow_html=True)
                st.markdown(_plan_text(plan, plan_bonus(squad, plan)[1] if not squad.empty else []))
                x, y = st.columns(2)
                with x:
                    st.markdown(f"**Pontos fortes de {rival}**")
                    comparison_table(_traits_table(plan["rival_fortes"], "Acima da média"),
                                     "Comparado com a média das mesmas competições no período.")
                    st.markdown(f"**Pontos fracos de {rival}**")
                    comparison_table(_traits_table(plan["rival_fracos"], "Abaixo do esperado"))
                with y:
                    st.markdown(f"**Pontos fortes de {team}**")
                    comparison_table(_traits_table(plan["nossos_fortes"], "Acima da média"))
                    st.markdown(f"**Pontos fracos de {team}**")
                    comparison_table(_traits_table(plan["nossos_fracos"], "Abaixo do esperado"))
                _bars(mine, theirs, team, rival)
                corr = theirs.get("corredores") or {}
                if corr.get("ataca_por"):
                    st.markdown(f"**Por onde {rival} chega ao último terço** ({corr['jogos']} jogo(s) com lances, "
                                f"{corr['acoes_ataque']} ações)")
                    render_chart(_corridor_bars(corr), use_container_width=True)
                st.markdown("**Jogos considerados**")
                comparison_table(pd.DataFrame(theirs["jogos"]).drop(columns=["match_id"]), "")
    with t3:
        if t3.open is not False:          # rodada 21: só a aba aberta é montada
            if squad.empty:
                empty_state("Sem elenco", "", "👥")
            else:
                show = squad.assign(posicao_pt=squad["papel"].map(ROLE_PT).fillna("—"),
                                    valor=(pd.to_numeric(squad["valor_mercado_eur"], errors="coerce") / 1e6).round(1))
                cols = {"nome": "Atleta", "posicao_pt": "Posição", "idade": "Idade", "altura_cm": "Altura (cm)", "pe": "Pé",
                        "valor": "Valor (€ mi)", "nota": "Overall", "potencial": "Potencial", "nota_base": "Fonte do overall",
                        "minutos_temporada": "Min. (12 meses)", "gols_temporada": "Gols", "assist_temporada": "Assist.",
                        "origem": "Origem"}
                from src.ui.components import clickable_table

                clickable_table(show[[c for c in cols if c in show.columns]].rename(columns=cols)
                                .sort_values("Overall", ascending=False, na_position="last"), "sq_click", "Atleta", "jogador", club=str(team or ""), caption=
                                 "Overall 0–100: usa a mesma nota calculada pelo Scout e exibida nos perfis de jogadores. "
                                 "Quando o atleta ainda não tem registro correspondente no Scout, a estimativa local é mantida "
                                 "e identificada na fonte do overall.")
                pick = st.selectbox("Ver a carreira de", squad["nome"].tolist(), key="sq_career")
                from src.ui import nav

                nav.link(f"👤 Abrir {pick}", "jogador", key="sq_open_player", name=pick, club=str(team or ""))
    with t4:
        if t4.open is not False:          # rodada 21: só a aba aberta é montada
            st.caption("O atleta fica salvo na sua base local (data/lake) e entra no elenco do clube informado, no "
                       "planejador e na busca de jogadores.")
            with st.form("sq_add"):
                f1, f2, f3 = st.columns(3)
                nome = f1.text_input("Nome *")
                clube = f2.text_input("Clube *", value=team or "")
                funcao = f3.selectbox("Posição", ["Goalkeeper", "Centre-Back", "Left-Back", "Right-Back", "Defensive Midfield",
                                                  "Central Midfield", "Attacking Midfield", "Left Midfield", "Right Midfield",
                                                  "Left Winger", "Right Winger", "Centre-Forward"],
                                      format_func=lambda v: ROLE_PT.get(natural_role(v), v))
                g1, g2, g3, g4 = st.columns(4)
                nasc = g1.date_input("Nascimento", value=date(2000, 1, 1), min_value=date(1960, 1, 1))
                alt = g2.number_input("Altura (cm)", 150, 210, 180)
                pe = g3.selectbox("Pé", ["right", "left", "both"], format_func={"right": "direito", "left": "esquerdo",
                                                                                "both": "ambos"}.get)
                valor = g4.number_input("Valor de mercado (€ mi)", 0.0, 300.0, 0.0, step=0.1)
                nota = st.slider("Sua nota (opcional, 0 = sem nota)", 0, 100, 0)
                obs = st.text_input("Observação")
                if st.form_submit_button("Salvar atleta", type="primary"):
                    if not nome.strip() or not clube.strip():
                        st.error("Nome e clube são obrigatórios.")
                    else:
                        D.add_player({"nome": nome.strip(), "clube": clube.strip(), "funcao": funcao, "posicao": funcao,
                                      "nascimento": nasc.isoformat(), "altura_cm": alt, "pe": pe,
                                      "valor_mercado_eur": valor * 1e6 if valor else None,
                                      "nota_manual": nota or None, "observacao": obs})
                        _squad.clear()
                        st.success(f"{nome} salvo no elenco de {clube}.")
            ad = D.added_players()
            if not ad.empty:
                comparison_table(ad.drop(columns=[c for c in ("fonte", "conector", "licenca", "ingestao_utc")
                                                  if c in ad.columns]), "Atletas cadastrados por você.")
                rm = st.selectbox("Remover", ["—"] + [f"{r.nome} ({r.clube})" for r in ad.itertuples()], key="sq_rm")
                if rm != "—" and st.button("Remover atleta", key="sq_rm_btn"):
                    r = ad.iloc[[f"{x.nome} ({x.clube})" for x in ad.itertuples()].index(rm)]
                    D.remove_added(r["nome"], r["clube"])
                    _squad.clear()
                    st.rerun()
    with t5:
        if t5.open is not False:          # rodada 21: só a aba aberta é montada
            files = D.saved_lineups()
            if not files:
                empty_state("Nenhuma escalação salva", "Use 💾 no campinho.", "💾")
            for f in files[:30]:
                import json

                d = json.loads(f.read_text(encoding="utf-8"))
                with st.expander(f"{f.stem} — {d.get('time')} x {d.get('adversario') or '—'} ({d.get('formacao')})"):
                    comparison_table(pd.DataFrame([{"Posição": p.get("papel_pt"), "Atleta": p.get("jogador"),
                                                    "Nota": p.get("nota")} for p in d.get("xi", [])]), d.get("modo", ""))


def _bars(mine: Dict[str, Any], theirs: Dict[str, Any], team: str, rival: str) -> None:
    keys = [k for k in ("goals", "xg", "shots_total", "shots_on_target", "possession_pct", "crosses_total", "corners")
            if k in theirs.get("a_favor", {}) or k in mine.get("a_favor", {})]
    if not keys:
        return
    lab = {k: (theirs["a_favor"].get(k) or mine["a_favor"].get(k))["rotulo"] for k in keys}
    fig = go.Figure()
    for who, prof, color in ((team, mine, P["primary"]), (rival, theirs, P["secondary"])):
        fig.add_trace(go.Bar(name=who, x=[lab[k] for k in keys], marker_color=color,
                             y=[(prof.get("a_favor", {}).get(k) or {}).get("media") for k in keys]))
    ref = [(theirs["a_favor"].get(k) or mine["a_favor"].get(k) or {}).get("referencia") for k in keys]
    fig.add_trace(go.Scatter(name="média das competições", x=[lab[k] for k in keys], y=ref, mode="markers",
                             marker=dict(symbol="line-ew-open", size=28, color=P["warning"], line=dict(width=3))))
    from src.ui.charts import _layout

    render_chart(_layout(fig, "Média por jogo — a favor", 380, barmode="group"), use_container_width=True)


def _corridor_bars(corr: Dict[str, Any]) -> go.Figure:
    from src.ui.charts import _layout

    sides = ["esquerda", "centro", "direita"]
    fig = go.Figure([go.Bar(name="ataca por", x=sides, y=[corr["ataca_por"].get(s, 0) for s in sides],
                            marker_color=P["secondary"]),
                     go.Bar(name="sofre por", x=sides, y=[corr.get("sofre_por", {}).get(s, 0) for s in sides],
                            marker_color=P["accent"])])
    return _layout(fig, "% das ações que chegam ao último terço, por corredor", 320, barmode="group")
