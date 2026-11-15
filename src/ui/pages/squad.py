"""
📋 Escalação — elenco atual, nota do laboratório, campinho com a escalação provável / melhor possível / ajustada
ao adversário, plano de jogo pelos últimos 1/3/5/10/20 jogos e cadastro de atletas próprios.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.squad import data as D
from src.squad.formations import FORMATIONS, ROLE_PT, fit, natural_role
from src.squad.planner import (best_xi, lab_rating, matchup_plan, plan_bonus, probable_xi, season_usage, squad_frame,
                               team_profile)
from src.ui.components import comparison_table, empty_state, hero, note
from src.ui.theme import PALETTE as P

N_OPTIONS = [1, 3, 5, 10, 20]


# ------------------------------------------------------------------------------------------------ seleção de time
def _team_options(q: str, limit: int = 25) -> List[str]:
    from src.data_hub.search import fast_scores
    from src.ui.context import get_service
    from src.ui.pages.search_all import team_table

    t = team_table(get_service().db.stable_version(), False)
    names = set(t["nome"].tolist()) if not t.empty else set()
    cl = D.clubs()
    if not cl.empty:
        names |= set(cl["nome"].astype(str))
    if not q.strip():
        top = t.sort_values("jogos", ascending=False)["nome"].head(limit).tolist() if not t.empty else []
        return top
    sc = fast_scores(q, list(names))
    return [n for n, v in sorted(sc.items(), key=lambda kv: -kv[1]) if v >= 0.6][:limit]


def _picker(label: str, key: str, default: str = "") -> Optional[str]:
    c1, c2 = st.columns([1, 1.4])
    q = c1.text_input(label, value=st.session_state.get(f"{key}_q", default), key=f"{key}_q",
                      placeholder="digite o nome do time")
    opts = _team_options(q)
    if not opts:
        c2.caption("Nenhum time com esse nome na base.")
        return None
    return c2.selectbox("Escolha", opts, key=f"{key}_pick", label_visibility="hidden")


# ------------------------------------------------------------------------------------------------ dados do time
@st.cache_data(show_spinner=False, ttl=900, max_entries=16)
def _squad(team: str, version: str) -> Dict[str, Any]:
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    names = same_team_names(team)
    club = D.match_club(team)
    tm = D.table("tm_jogadores", None, "clube_id", [club["transfermarkt_id"]]) if club else pd.DataFrame()
    added = D.added_players()
    sq = squad_frame(tm, [club["transfermarkt_id"]] if club else [], [team] + names, added)
    source = "Transfermarkt" if club and not tm.empty else ""
    if sq.empty or len(sq) < 11:                         # clube fora do Transfermarkt: elenco pelas escalações da base
        local = D.squad_from_db(get_service().db, names)
        if not local.empty:
            sq = squad_frame(local, [], [local["clube"].iloc[0]], added)
            source = "escalações dos jogos na base (ESPN, API-Football, súmulas)"
    usage = pd.DataFrame()
    if "transfermarkt_id" in sq and sq["transfermarkt_id"].notna().any():
        ap = D.table("tm_aparicoes", None, "transfermarkt_id", sq["transfermarkt_id"].dropna().tolist())
        usage = season_usage(ap, sq["transfermarkt_id"].dropna().tolist(),
                             since=(date.today() - timedelta(days=365)).isoformat())
    rated = lab_rating(sq, D.tm_reference(), usage, D.external_ratings()) if not sq.empty else sq
    return {"squad": rated, "club": club, "names": names, "fonte": source or "—"}


@st.cache_data(show_spinner=False, ttl=900, max_entries=32)
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
    st_ = D.merged_stats(db, m, names)
    comps = m["competition_name"].dropna().unique().tolist()
    base = D.baseline(db, comps, (pd.to_datetime(m["match_date"].min()) - pd.Timedelta(days=60)).strftime("%Y-%m-%d"),
                      str(m["match_date"].max()))
    prof = team_profile(m, st_, [names[0]] if not st_.empty else names, base, n)
    used = {g["match_id"] for g in prof["jogos"]}
    ev_ids = m.loc[(m["data_level"] == "EVENTS") & m["match_id"].isin(used), "match_id"].tolist()
    prof["corredores"] = D.attack_corridors(db, ev_ids, names)
    prof["competicoes"] = comps
    return prof


# ------------------------------------------------------------------------------------------------ campinho
def _pitch(xi: List[Dict[str, Any]], plan: Optional[Dict[str, Any]], rival_corr: Dict[str, Any], title: str) -> go.Figure:
    from src.ui import charts

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
    xs = [p["x"] for p in xi]
    ys = [p["y"] for p in xi]
    labels = [(p["jogador"] or "—").split(" ")[-1] if p["jogador"] else "vaga" for p in xi]
    hover = [f"{p['papel_pt']}: {p['jogador'] or '—'}<br>nota {p['nota'] if p['nota'] is not None else '—'}"
             f" · encaixe {p['encaixe'] if p['encaixe'] is not None else '—'} (origem: {p['papel_natural'] or '—'})"
             for p in xi]
    colors = [P["primary"] if (p["encaixe"] or 0) >= 0.85 else (P["warning"] if (p["encaixe"] or 0) >= 0.6 else P["danger"])
              for p in xi]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers+text", text=labels, textposition="bottom center",
                             marker=dict(size=30, color=colors, line=dict(color="#E2E8F0", width=2)),
                             textfont=dict(color="#F5F7FB", size=12), hovertext=hover, hoverinfo="text",
                             showlegend=False))
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="text", showlegend=False, hoverinfo="skip",
                             text=[f"{int(p['nota'])}" if p.get("nota") is not None else "" for p in xi],
                             textfont=dict(color="#FFFFFF", size=11)))
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


# ------------------------------------------------------------------------------------------------ página
def render(_ctx=None) -> None:
    from src.ui.context import get_service

    hero("Escalação", "Monte o time para o próximo jogo",
         "Elenco atual (Transfermarkt + atletas que você cadastrar), nota do laboratório, escalação provável, a melhor "
         "possível e a ajustada ao adversário — com o plano de jogo tirado dos últimos jogos do rival.")
    version = get_service().db.stable_version()
    a, b = st.columns(2)
    with a:
        team = _picker("Meu time", "sq_team")
    with b:
        rival = _picker("Adversário", "sq_rival")
    c1, c2, c3 = st.columns([1.2, 1.2, 2])
    formation = c1.selectbox("Formação", list(FORMATIONS), key="sq_form")
    n = c2.select_slider("Últimos jogos", N_OPTIONS, value=5, key="sq_n")
    mode = c3.radio("Escalação", ["Provável", "Melhor possível", "Contra o adversário"], horizontal=True, key="sq_mode",
                    help="Provável: quem mais começou jogando nos últimos jogos. Melhor possível: maior nota × encaixe "
                         "na posição. Contra o adversário: a melhor, com ajustes pelo plano de jogo.")
    if not team:
        empty_state("Escolha o seu time", "Digite o nome no campo 'Meu time'.", "📋")
        return
    with st.spinner("Montando elenco e perfis..."):
        sq = _squad(team, version)
        mine = _profile(team, n, version)
        theirs = _profile(rival, n, version) if rival else None
    squad = sq["squad"]
    plan = matchup_plan(mine, theirs, team, rival) if theirs else None

    t1, t2, t3, t4, t5 = st.tabs(["🧩 Campinho", "🎯 Plano de jogo", "👥 Elenco e notas", "➕ Adicionar atleta",
                                  "💾 Escalações salvas"])
    with t1:
        if squad.empty:
            empty_state("Sem elenco para este time", f"Fonte procurada: Transfermarkt e escalações da base.", "👥",
                        "O Transfermarkt aberto cobre as principais ligas europeias. Para outros clubes, cadastre os "
                        "atletas na aba ➕ ou sincronize jogos com escalação (ESPN histórico).")
        else:
            why: List[str] = []
            info: Dict[str, Any] = {}
            if mode == "Provável":
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
                names = ["—"] + squad.sort_values("nota", ascending=False, na_position="last")["nome"].tolist()
                cols = st.columns(4)
                for i, p in enumerate(xi):
                    k = f"sq_slot_{team}_{formation}_{mode}_{i}"
                    cur = p["jogador"] if p["jogador"] in names else "—"
                    pick = cols[i % 4].selectbox(f"{p['papel_pt']} ({i + 1})", names, index=names.index(cur), key=k)
                    if pick != p["jogador"]:
                        row = squad[squad["nome"] == pick]
                        p.update(jogador=None if pick == "—" else pick,
                                 nota=None if row.empty or pd.isna(row.iloc[0]["nota"]) else float(row.iloc[0]["nota"]),
                                 encaixe=None if row.empty else round(fit(p["papel"], row.iloc[0]["papel"]), 2),
                                 papel_natural=None if row.empty else ROLE_PT.get(row.iloc[0]["papel"], "—"))
            corr = (theirs or {}).get("corredores") or {}
            st.plotly_chart(_pitch(xi, plan, corr, f"{team} — {formation} ({mode.lower()})"), use_container_width=True)
            vals = [p["nota"] for p in xi if p.get("nota") is not None]
            k = st.columns(4)
            k[0].metric("Nota média do XI", f"{sum(vals) / len(vals):.0f}" if vals else "—")
            k[1].metric("Fora de posição", sum(1 for p in xi if (p.get("encaixe") or 0) < 0.85 and p["jogador"]))
            k[2].metric("Elenco disponível", len(squad))
            if mode == "Provável":
                k[3].metric("Jogos usados", info.get("jogos_considerados", 0))
            st.caption("🔵 na posição de origem · 🟡 adaptado · 🔴 improvisado. O número no círculo é a nota do "
                       "laboratório. Fonte do elenco: " + sq["fonte"] + ".")
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
        if not rival:
            empty_state("Escolha o adversário", "O plano compara os últimos jogos dos dois times.", "🎯")
        elif not theirs or not theirs.get("n"):
            empty_state(f"Sem jogos com estatísticas de {rival}", "", "🎯",
                        "O plano usa jogos com estatísticas ou lances. Sincronize a liga do adversário.")
        else:
            st.markdown(f"#### {team} x {rival} — últimos {theirs['n']} jogo(s) do rival e {mine.get('n', 0)} nossos")
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
                st.plotly_chart(_corridor_bars(corr), use_container_width=True)
            st.markdown("**Jogos considerados**")
            comparison_table(pd.DataFrame(theirs["jogos"]).drop(columns=["match_id"]), "")
    with t3:
        if squad.empty:
            empty_state("Sem elenco", "", "👥")
        else:
            show = squad.assign(posicao_pt=squad["papel"].map(ROLE_PT).fillna("—"),
                                valor=(pd.to_numeric(squad["valor_mercado_eur"], errors="coerce") / 1e6).round(1))
            cols = {"nome": "Atleta", "posicao_pt": "Posição", "idade": "Idade", "altura_cm": "Altura (cm)", "pe": "Pé",
                    "valor": "Valor (€ mi)", "nota": "Nota", "nota_base": "Base da nota",
                    "minutos_temporada": "Min. (12 meses)", "gols_temporada": "Gols", "assist_temporada": "Assist.",
                    "origem": "Origem"}
            comparison_table(show[[c for c in cols if c in show.columns]].rename(columns=cols)
                             .sort_values("Nota", ascending=False, na_position="last"),
                             "Nota do laboratório (0–100): valor de mercado comparado com a mesma posição + minutos e "
                             "participação em gols nos últimos 12 meses + nota externa quando houver. É uma estimativa: "
                             "a base de cada nota aparece ao lado.")
            pick = st.selectbox("Ver a carreira de", squad["nome"].tolist(), key="sq_career")
            from src.ui import nav

            nav.link(f"👤 Abrir {pick}", "jogador", key="sq_open_player", name=pick)
    with t4:
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

    st.plotly_chart(_layout(fig, "Média por jogo — a favor", 380, barmode="group"), use_container_width=True)


def _corridor_bars(corr: Dict[str, Any]) -> go.Figure:
    from src.ui.charts import _layout

    sides = ["esquerda", "centro", "direita"]
    fig = go.Figure([go.Bar(name="ataca por", x=sides, y=[corr["ataca_por"].get(s, 0) for s in sides],
                            marker_color=P["secondary"]),
                     go.Bar(name="sofre por", x=sides, y=[corr.get("sofre_por", {}).get(s, 0) for s in sides],
                            marker_color=P["accent"])])
    return _layout(fig, "% das ações que chegam ao último terço, por corredor", 320, barmode="group")
