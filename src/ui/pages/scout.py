"""Sala de Scout & Planejamento — mercado, elenco, diagnóstico e simulação."""

from __future__ import annotations

import html
import io
import json
import re
from typing import Any, Dict, List, Optional
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from src.ui.perf import timed as _perf_timed

from src.scout import engine as E
from src.ui.context import heavy_cache as _heavy_cache
from src.squad import data as D
from src.ui.components import styled_dataframe, comparison_table, empty_state, page_header
from src.ui.nav import back_button, open_view, param


def _market_data(version: str):
    """Rodada 7: lê a fotografia pronta do universo (instantâneo); só monta na hora se ainda não existir nenhuma.
    Rodada 23: cópia ÚNICA em memória por processo (`snapshot.cached_data`) — o cache do Streamlit copiava o universo
    inteiro (dezenas de milhares de jogadores × centenas de colunas) a cada clique. Não altere o que volta daqui."""
    from src.scout import snapshot as S
    from src.ui.context import get_service

    data = S.cached_data()
    if data is not None:
        return data
    data = S.build_universe(get_service().db)
    try:
        S.save(data)
    except Exception:
        pass
    return data


def _market_data_legacy(version: str):
    from src.ui.context import get_service

    players, clubs = D.table("tm_jogadores"), D.table("tm_clubes")
    last = (pd.to_numeric(players["ultima_temporada"], errors="coerce")
            if "ultima_temporada" in players else pd.Series(dtype=float))

    # Mantém o universo de mercado já utilizado pela interface, inclusive jogadores com
    # clube_id e temporadas antigas. O carregamento estatístico pesado recebe apenas
    # atletas com temporada recente; os demais ativos são descobertos pelo histórico local
    # (450 minutos e 4 jogos nos últimos 180 dias) dentro de load_player_history.
    history_players = players
    if not players.empty and last.notna().any():
        history_players = players.loc[last >= last.max() - 2].copy()
        players = players[(last >= last.max() - 2) |
                          players.get("clube_id", pd.Series("", index=players.index)).astype(str).str.strip().ne("")]

    history = E.load_player_history(
        get_service().db, days=1825,
        player_names=history_players.get("nome", pd.Series(dtype=str))
    )
    valuations = D.table("tm_valores", ["transfermarkt_id", "data", "valor_mercado_eur"])
    universe = E.add_quality_scores(E.build_market_universe(players, history, valuations))
    # Notas externas (ex.: Simonetti) corroboram a qualidade sem substituir métricas observadas.
    universe = E.merge_external_ratings(universe, D.external_ratings())
    if not clubs.empty:
        from src.data_lake.ids import team_core
        club_rows = clubs.copy()
        if {"transfermarkt_id", "valor_total_eur"} <= set(club_rows.columns):
            cv_id = club_rows.drop_duplicates("transfermarkt_id").set_index(
                club_rows["transfermarkt_id"].astype(str))["valor_total_eur"].to_dict()
            universe["clube_valor_total_eur"] = universe["clube_id"].astype(str).map(cv_id)
        if "nome" in club_rows:
            club_rows["_club_core"] = club_rows["nome"].map(team_core)
            if "valor_total_eur" in club_rows:
                cv_name = club_rows.drop_duplicates("_club_core").set_index("_club_core")["valor_total_eur"].to_dict()
                by_name = universe["clube"].map(team_core).map(cv_name)
                universe["clube_valor_total_eur"] = by_name.combine_first(
                    universe.get("clube_valor_total_eur", pd.Series(index=universe.index, dtype=float)))
            for source, target in (("liga", "clube_liga"), ("pais", "clube_pais")):
                if source in club_rows:
                    mapping = club_rows.drop_duplicates("_club_core").set_index("_club_core")[source].to_dict()
                    universe[target] = universe["clube"].map(team_core).map(mapping)
    stamp = pd.to_datetime(players.get("ingestao_utc"), errors="coerce").max() if "ingestao_utc" in players else None
    return {"universe": universe, "clubs": clubs, "status": "carregado",
            "atualizacao": str(stamp) if stamp is not None and pd.notna(stamp) else "sem carimbo"}


@_perf_timed("scout._rank_candidates")
@_heavy_cache(show_spinner=False, ttl=900, max_entries=16)
def _rank_candidates(version, team, country, competition, season, rejected, feedback_reason,
                     _pool, _needs, _financial, _roster, needs_key=None):
    """Reaproveita o ranking caro entre interações; a revisão invalida quando o histórico muda.
    rodada 13: `needs_key` (posições pedidas) entra na chave do cache — antes `_needs` não era considerado e a
    lista "Três melhores por posição" devolvia sempre o ranking da 1ª busca (laterais e outras posições vazias)."""
    return E.recommend(_pool, _needs, _financial, country, competition, roster=_roster,
                       rejected=rejected, feedback_reason=feedback_reason, season=season)


SECTORS = [("🧤 Goleiros", {"GK"}), ("🛡️ Defesa", {"CB", "LB", "RB", "LWB", "RWB"}),
           ("⚙️ Meio-campo", {"DM", "CM", "AM", "LM", "RM"}), ("⚡ Ataque", {"LW", "RW", "ST"})]


def _window_cards(roster, decisions, loans=None):
    """
    Rodada 11: janela de transferências em cartões por setor DENTRO de um formulário — nada recarrega até
    "Finalizar planejamento". Emprestados ao clube: comprar / deixar acabar / renovar. Emprestados pelo clube: seção
    própria (reintegrar / vender / renovar).
    """
    from src.squad.matchday import canonical_names

    loans = loans or []
    l_in = {x["name"]: x for x in loans if x.get("direction") == "in"}
    l_out = [x for x in loans if x.get("direction") == "out"]
    canon = canonical_names(roster["nome"].astype(str).tolist(), list(l_in)) if l_in else {}
    rows = []
    r = roster.copy()
    r["_q"] = pd.to_numeric(r.get("qualidade"), errors="coerce")
    # rodada 19: o mesmo atleta vindo de duas fontes aparecia 2× (e quebrava a chave "scout_dec_gabriel_oliveira");
    # homônimos de idades diferentes continuam separados
    _age = pd.to_numeric(r.get("idade"), errors="coerce").round(0)
    r = r.assign(_age=_age).sort_values("_q", ascending=False, na_position="last") \
         .drop_duplicates(["nome", "_age"]).drop(columns="_age")
    used_keys: Dict[str, int] = {}
    known = set().union(*[s_ for _, s_ in SECTORS])
    # sem posição exata: usa o setor informado pela FotMob (goleiros/defensores/meias/atacantes) só para agrupar
    gmap = {"keepers": "GK", "defenders": "CB", "midfielders": "CM", "attackers": "ST"}
    if "grupo" in r:
        r["papel"] = [p_ if isinstance(p_, str) and p_ in known else gmap.get(str(g), p_)
                      for p_, g in zip(r["papel"], r["grupo"])]
    groups = SECTORS + [("❔ Posição não identificada", None)]
    base_opts = ["Fica", "Vender", "Emprestar"]
    loan_opts = ["Comprar em definitivo", "Deixar o empréstimo acabar", "Renovar empréstimo"]
    color = {"Fica": "#22C55E", "Vender": "#EF4444", "Emprestar": "#FBBF24", "Comprar em definitivo": "#22D3EE",
             "Deixar o empréstimo acabar": "#EF4444", "Renovar empréstimo": "#A78BFA", "Reintegrar": "#22C55E"}
    with st.form("scout_window_form", border=False):
        tabs_ = st.tabs([f"{label} ({int((r['papel'].isin(roles) if roles else ~r['papel'].isin(known)).sum())})"
                         for label, roles in groups] + [f"🔁 Emprestados pelo clube ({len(l_out)})"])
        picks = {}
        for tab, (label, roles) in zip(tabs_, groups):
            with tab:
                part = r[r["papel"].isin(roles)] if roles else r[~r["papel"].isin(known)]
                part = part.sort_values("_q", ascending=False, na_position="last")
                if part.empty:
                    st.caption("Ninguém neste setor.")
                    continue
                cols = st.columns(3)
                for k, p in enumerate(part.to_dict("records")):
                    name = str(p["nome"])
                    loan = l_in.get(canon.get(name, name))
                    opts = loan_opts if loan else base_opts
                    cur = decisions.get(name, opts[1] if loan else "Fica")
                    cur = cur if cur in opts else opts[0]
                    q = p.get("_q")
                    age = pd.to_numeric(pd.Series([p.get("idade")]), errors="coerce").iloc[0]
                    badge = (f'<div style="color:#C4B5FD;font-size:.78rem">🔁 emprestado pelo {html.escape(str(loan.get("other_club") or "?"))}'
                             f' até {html.escape(str(loan.get("to_date") or "?"))}</div>' if loan else "")
                    with cols[k % 3]:
                        st.markdown(
                            f'<div style="background:#0B1120;border:1px solid #1E2A44;border-left:4px solid {color.get(cur, "#22C55E")};'
                            f'border-radius:14px;padding:10px 12px;margin-bottom:6px">'
                            f'<div style="font-weight:700;color:#F5F7FB">{html.escape(name)}</div>'
                            f'<div style="color:#98A6BF;font-size:.82rem">{html.escape(_role(p.get("papel")))}'
                            f'{f" · {int(age)} anos" if pd.notna(age) else ""}</div>{badge}'
                            f'<div style="display:flex;gap:14px;margin-top:4px;font-size:.85rem;color:#DCE6F4">'
                            f'<span>⭐ {f"{q:.0f}" if pd.notna(q) else "—"}</span><span>💶 {_money(p.get("valor_mercado_eur"))}</span>'
                            f'</div></div>', unsafe_allow_html=True)
                        base_key = f"scout_dec_{_slug(name)}"
                        n_used = used_keys.get(base_key, 0)
                        used_keys[base_key] = n_used + 1
                        label_name = name if not n_used else f"{name} ({n_used + 1})"
                        picks[label_name] = (st.radio("Decisão", opts, index=opts.index(cur),
                                                      key=base_key if not n_used else f"{base_key}_{n_used}",
                                                      horizontal=not loan, label_visibility="collapsed"), p)
        with tabs_[-1]:
            if not l_out:
                st.caption("Nenhum jogador do clube emprestado a outro time (segundo a FotMob).")
            out_opts = ["Reintegrar", "Vender", "Renovar empréstimo"]
            cols = st.columns(3)
            for k, x in enumerate(l_out):
                name = str(x["name"])
                cur = decisions.get(f"out::{name}", "Renovar empréstimo")
                with cols[k % 3]:
                    st.markdown(f'<div style="background:#0B1120;border:1px solid #1E2A44;border-left:4px solid #A78BFA;'
                                f'border-radius:14px;padding:10px 12px;margin-bottom:6px"><div style="font-weight:700;color:#F5F7FB">'
                                f'{html.escape(name)}</div><div style="color:#98A6BF;font-size:.82rem">no {html.escape(str(x.get("other_club") or "?"))}'
                                f' até {html.escape(str(x.get("to_date") or "?"))}</div></div>', unsafe_allow_html=True)
                    picks[f"out::{name}"] = (st.radio("Decisão", out_opts, index=out_opts.index(cur),
                                                      key=f"scout_out_{_slug(name)}", label_visibility="collapsed"), {})
        done = st.form_submit_button("✅ Finalizar planejamento", type="primary", use_container_width=True)
    if done:
        for name, (choice, _) in picks.items():
            decisions[name] = choice
        st.session_state["scout_plan_final"] = True
        st.success("Planejamento registrado — o elenco planejado aparece logo abaixo.")
    for name, choice in decisions.items():
        if name.startswith("out::"):
            if choice != "Renovar empréstimo":
                rows.append({"Jogador": name[5:], "Decisão": choice + " (emprestado pelo clube)", "Valor referência": "—"})
            continue
        if choice in ("Fica", "Renovar empréstimo"):
            continue
        p = picks.get(name, (None, {}))[1] or {}
        rows.append({"Jogador": name, "Decisão": choice, "Valor referência": _money(p.get("valor_mercado_eur"))})
    return rows


@st.cache_data(show_spinner=False, max_entries=16)
def _nat_market(version, country, team_key, _universe, _roster):
    return E.nationality_market(_universe, country, _roster)


@st.cache_data(show_spinner=False, ttl=3600, max_entries=16)
def _loans(team, version):
    out = []
    try:
        from src.ui.context import get_service
        from src.ui.pages.clubs import same_team_names

        out = list(get_service().fotmob.loans(same_team_names(team)) or [])
    except Exception:
        out = []
    known = {(x.get("name"), x.get("direction")) for x in out}
    return out + [x for x in _manual_loans(team) if (x["name"], x["direction"]) not in known]


def _not_ours(df, team, version, roster=None):
    """Rodada 20: nunca sugere ao clube quem ele mesmo emprestou (nem quem já é do elenco)."""
    if df is None or df.empty:
        return df
    from src.data_lake.ids import player_core as _pc

    own = {_pc(x.get("name")) for x in _loans(team, version) if x.get("direction") == "out"}
    if roster is not None and not roster.empty and "nome" in roster:
        own |= set(roster["nome"].astype(str).map(_pc))
    own.discard("")
    if not own:
        return df
    core = df["_core"].astype(str) if "_core" in df else df["nome"].astype(str).map(_pc)
    return df[~core.isin(own)]


MANUAL_LOANS_DDL = ("CREATE TABLE IF NOT EXISTS scout_manual_loans (club TEXT, name TEXT, direction TEXT, other_club TEXT, "
                    "to_date TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (club, name, direction))")


def _manual_loans(team):
    """rodada 13: empréstimos registrados à mão (quando a FotMob não traz) — ficam no banco local."""
    try:
        from src.ui.context import get_service

        with get_service().db.connect() as conn:
            conn.execute(MANUAL_LOANS_DDL)
            rows = conn.execute("SELECT name, direction, other_club, to_date FROM scout_manual_loans WHERE club = ?",
                                (team,)).fetchall()
        return [{"name": n, "direction": d, "other_club": o, "to_date": t or "—", "manual": True} for n, d, o, t in rows]
    except Exception:
        return []


def _manual_loan_form(team, roster):
    with st.expander("➕ Registrar empréstimo à mão (quando a fonte não trouxer)"):
        st.caption("Use para gerir quem veio emprestado ao clube (comprar / deixar acabar / renovar) e quem o clube "
                   "emprestou (reintegrar / vender / renovar). Fica salvo no banco local.")
        with st.form(f"scout_manual_loan_{_slug(team)}", border=False):
            a, b, c, d = st.columns([1.2, 1.4, 1.4, 1])
            direction = a.radio("Tipo", ["Veio emprestado", "Emprestado pelo clube"], key="sml_dir")
            names = roster["nome"].astype(str).tolist() if roster is not None and not roster.empty else []
            if direction == "Veio emprestado" and names:
                name = b.selectbox("Jogador do elenco", names, key="sml_name_in")
            else:
                name = b.text_input("Nome do jogador", key="sml_name_out")
            other = c.text_input("Clube dono / clube onde está", key="sml_other")
            until = d.text_input("Até (ex.: 2026-12-31)", key="sml_until")
            ok = st.form_submit_button("Salvar empréstimo")
        if ok and str(name).strip():
            from src.ui.context import get_service

            with get_service().db.connect() as conn:
                conn.execute(MANUAL_LOANS_DDL)
                conn.execute("INSERT OR REPLACE INTO scout_manual_loans (club, name, direction, other_club, to_date) "
                             "VALUES (?,?,?,?,?)", (team, str(name).strip(), "in" if direction == "Veio emprestado" else "out",
                                                     other.strip() or "?", until.strip() or None))
            _loans.clear()
            st.success(f"Empréstimo de {name} registrado — aparece nos cartões da janela.")
            st.rerun()
        man = _manual_loans(team)
        if man:
            st.caption("Registrados à mão: " + "; ".join(f"{x['name']} ({'veio do' if x['direction'] == 'in' else 'está no'} "
                                                        f"{x['other_club']})" for x in man))


def _club_averages_chart(diagnosis, team):
    """
    Rodada 11: em vez da tabela, barras divergentes — quanto o clube está acima/abaixo da média da competição em cada
    número, já com o SENTIDO certo (xG a favor alto é bom; xG contra alto é ruim) e o valor real na legenda.
    """
    import plotly.graph_objects as go

    from src.ui.components import render_chart

    ref = diagnosis.get("referencia") or {}
    specs = [("A favor", diagnosis.get("medias_pro") or {}, [("xg", "xG criado", 1), ("shots_total", "Finalizações", 1),
             ("shots_on_target", "No alvo", 1), ("possession_pct", "Posse", 0), ("passes_total", "Passes", 0),
             ("crosses_total", "Cruzamentos", 0), ("interceptions", "Interceptações", 1), ("tackles_won", "Desarmes certos", 1)]),
             ("Contra", diagnosis.get("medias_contra") or {}, [("xg", "xG cedido", -1), ("shots_total", "Finalizações sofridas", -1),
             ("shots_on_target", "No alvo sofridas", -1)])]
    rows = []
    for side, src, keys in specs:
        for k, label, sense in keys:
            v, b = src.get(k), ref.get(k)
            if v is None or b in (None, 0):
                continue
            pct = 100 * (float(v) - float(b)) / abs(float(b))
            good = None if sense == 0 else (pct * sense > 0)
            rows.append((label, pct, good, float(v), float(b)))
    if not rows:
        st.caption("Sem referência da competição para comparar.")
        return
    rows.sort(key=lambda r: r[1])
    colors = ["#94A3B8" if g is None else ("#22C55E" if g else "#EF4444") for _, _, g, _, _ in rows]
    fig = go.Figure(go.Bar(x=[r[1] for r in rows], y=[r[0] for r in rows], orientation="h", marker_color=colors,
                           text=[f"{r[3]:.1f} por jogo (média da competição {r[4]:.1f})" for r in rows], textposition="auto",
                           hovertemplate="%{y}: %{x:+.0f}% em relação à média<extra></extra>"))
    fig.add_vline(x=0, line_color="#98A6BF", line_width=1)
    fig.update_layout(height=max(260, 34 * len(rows)), margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title="% acima (+) ou abaixo (−) da média da competição")
    render_chart(fig, use_container_width=True, key=f"scout_avg_{_slug(team)}")
    st.caption("🟢 melhor que a média · 🔴 pior que a média · cinza = estilo (nem bom nem ruim por si só). "
               f"Base: {diagnosis.get('partidas_analisadas', 0)} jogos do clube com estatísticas e as mesmas competições "
               "nos últimos 12 meses como referência.")


def _sim_radar(deltas, team):
    """Rodada 11: radar sobreposto antes × depois (cada eixo normalizado pelo maior dos dois valores)."""
    import plotly.graph_objects as go

    from src.ui.components import render_chart

    if not deltas:
        return
    labels = [d["indicador"] for d in deltas]
    top = [max(abs(float(d["antes"])), abs(float(d["depois"])), 1e-9) * 1.15 for d in deltas]
    fig = go.Figure()
    for key, name, color in (("antes", "XI atual", "#98A6BF"), ("depois", "XI com a mudança", "#22D3EE")):
        vals = [float(d[key]) / t * 100 for d, t in zip(deltas, top)]
        fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=labels + labels[:1], fill="toself", name=name,
                                      line_color=color, opacity=.75,
                                      hovertext=[f"{d['indicador']}: {d[key]}" for d in deltas] + [""], hoverinfo="text"))
    fig.update_layout(height=380, polar=dict(radialaxis=dict(visible=False, range=[0, 100])), margin=dict(l=40, r=40, t=20, b=20))
    render_chart(fig, use_container_width=True, key=f"scout_radar_{_slug(team)}")
    ups = [f"{d['indicador']} {d['variacao_pct']:+.0f}%" for d in deltas if d.get("variacao_pct") not in (None, 0)]
    if ups:
        st.caption("Variação do XI: " + " · ".join(ups) + ". Projeção pela composição do time, não resultado de jogo.")


def _overall_explainer():
    """Rodada 20: como a nota 0–100 é feita + conferência com os craques de referência."""
    from src.scout import overall as O

    rep = O.load_report()
    with st.expander("ℹ️ Como a nota (overall 0–100) é feita" + (f" — {rep['resumo']}" if rep else ""), expanded=False):
        w = (rep or {}).get("pesos") or O.DEFAULT_WEIGHTS
        st.markdown("\n".join([
            f"- **Reputação ajustada pela idade ({w.get('wR', 0):.0%})** — valor de mercado (ou 80% do pico de 3 anos), "
            "corrigido pela idade; vale bem menos para quem jogou pouco no ano.",
            f"- **Desempenho na função ({w.get('wP', 0):.0%})** — números por 90 da posição (encolhidos pelos minutos) "
            "levados ao nível da liga, + nota dos Rankings + nota externa.",
            f"- **Nota da FotMob ajustada pela liga ({w.get('wT', 0):.0%})** — média dos últimos 12 meses (450+ min).",
            f"- **Nível da liga e do clube ({w.get('wL', 0):.0%})**.",
            "- **Disponibilidade**: tudo é encolhido pelos minutos do ano (1.800 min = régua cheia) — quem jogou pouco não "
            "chega ao topo, por melhor que seja o nome.",
            "- **Escala pela colocação no mundo**: só ~10 jogadores passam de 90, ~40 de 87, ~80 de 85, ~400 de 80; "
            "mediana ≈ 62. As posições são padronizadas (competem em pé de igualdade) e têm teto (lateral ≤ 90, goleiro ≤ 91).",
            "- **Calibração**: os pesos são escolhidos para pôr os craques de referência no alto e respeitar os TETOS que "
            "você apontou (ex.: Maddison, Isak, Gnabry, Ekitiké ≤ 85; Lacroix ≤ 87), sem perder a ligação com o desempenho.",
            "- **Correção aprendida (rodada 22)**: ~130 jogadores com nota-alvo de REFERÊNCIA (aproximação de consenso, "
            "editável em `REFERENCE_TARGETS`) ensinam onde a régua erra de forma sistemática — idade, liga, minutos, "
            "posição. A correção vale para TODOS (não é ajuste nome a nome) e é testada fora da amostra (aprende numa "
            "metade, mede na outra).",
            "- **Potencial (ao lado)**: overall de hoje + espaço de crescimento da idade × talento medido (produção na "
            "função com pesos por posição, nota, minutos × nível do time, valor para a idade, toques, seleção de base, "
            "físico). É projeção, não fato."]))
        if rep and rep.get("erro_medio_alvos") is not None:
            st.caption(f"Erro médio contra as notas-alvo de referência: {rep['erro_medio_alvos']} ponto(s).")
        if rep and rep.get("alvos"):
            ta = pd.DataFrame(rep["alvos"]).rename(columns={"craque": "Jogador", "posicao": "Posição", "overall": "Nossa nota",
                                                             "alvo": "Referência", "diferenca": "Diferença",
                                                             "minutos_12m": "Min. 12 meses"})
            ta = ta.sort_values("Diferença", key=lambda x: -x.abs(), na_position="last")
            st.markdown("**Nossa nota × referência (maiores diferenças primeiro)**")
            styled_dataframe(ta[[c for c in ("Jogador", "Posição", "Nossa nota", "Referência", "Diferença", "Min. 12 meses")
                                 if c in ta]].head(40), hide_index=True, use_container_width=True)
        if rep and rep.get("distribuicao"):
            d = rep["distribuicao"]
            st.caption(f"No universo atual: {d.get('90+')} jogadores com 90+ · {d.get('87+')} com 87+ · {d.get('85+')} com "
                       f"85+ · {d.get('80+')} com 80+ · mediana {d.get('mediana')}.")
        if rep and rep.get("tetos"):
            tt = pd.DataFrame(rep["tetos"]).rename(columns={"craque": "Jogador", "overall": "Overall", "teto": "Teto",
                                                             "minutos_12m": "Min. 12 meses"})
            st.markdown("**Tetos de referência**")
            styled_dataframe(tt[[c for c in ("Jogador", "Overall", "Teto", "Min. 12 meses") if c in tt]],
                             hide_index=True, use_container_width=True)
        if rep and rep.get("craques"):
            t = pd.DataFrame(rep["craques"]).rename(columns={"craque": "Craque", "posicao": "Posição", "overall": "Overall",
                                                              "minutos_12m": "Min. 12 meses"})
            st.markdown("**Craques de referência**")
            styled_dataframe(t[[c for c in ("Craque", "Posição", "Overall", "Min. 12 meses") if c in t]], hide_index=True,
                             use_container_width=True)
            if rep.get("nao_encontrados"):
                st.caption("Fora do universo agora (sem cadastro ou sem jogos recentes na base): "
                           + ", ".join(rep["nao_encontrados"]))


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")[:50] or "item"


def _initials(name):
    return "".join(x[0] for x in str(name).split()[:2]).upper() or "?"


def _money(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return "Sem referência"
    if not np.isfinite(x):
        return "Sem referência"
    return f"€ {x/1e6:.1f} mi" if abs(x) >= 1e6 else f"€ {x/1e3:.0f} mil" if abs(x) >= 1e3 else f"€ {x:.0f}"


def _role(role):
    return E.ROLE_LABELS.get(str(role), str(role or "Não identificado"))


@_perf_timed("scout._merge_roster")
@_heavy_cache(show_spinner=False, ttl=900, max_entries=16)
def _merge_roster(roster, _universe, team=None, version=""):
    """rodada 13: cacheado por elenco + versão (o universo grande não entra no hash) e completado pelos jogos do clube."""
    universe = _universe
    if roster is None or roster.empty:
        return pd.DataFrame()
    from src.data_lake.ids import player_core, team_core

    r = roster.copy()
    r["_core"] = r["nome"].map(player_core)
    if universe is not None and not universe.empty:
        # rodada 24: homônimo → a linha do universo DESTE clube vem primeiro (dois "Matheus Pereira" não trocam de nota)
        if team and "clube" in universe:
            tc0 = team_core(team)
            own = universe[universe["clube"].map(lambda c: team_core(str(c)) == tc0)]
            lookup = pd.concat([own, universe]).drop_duplicates("_core").set_index("_core")
        else:
            lookup = universe.drop_duplicates("_core").set_index("_core")
        # rodada 11: nome do elenco ≠ nome do mercado ("Lucas Romero" × "Lucas Daniel Romero") — liga pela mesma regra
        # da Escalação, só entre atletas do PRÓPRIO clube (nunca junta dois jogadores diferentes por palpite)
        miss = ~r["_core"].isin(lookup.index)
        if team and miss.any() and "clube" in universe:
            from src.squad.matchday import canonical_names

            tc = team_core(team)
            mine = universe[universe["clube"].map(lambda c: team_core(str(c)) == tc)]
            if not mine.empty:
                canon = canonical_names(r.loc[miss, "nome"].astype(str).tolist(), mine["nome"].astype(str).tolist())
                r.loc[miss, "_core"] = [player_core(canon.get(n, n)) for n in r.loc[miss, "nome"].astype(str)]
        cols = [x for x in ("qualidade", "confianca_pct", "rating_media", "rating_12m", "qualidade_estatistica",
                            "nota_externa", "fontes_nota_externa", "fonte_qualidade", "minutos_12m",
                            "jogos_12m", "nacionalidade", "valor_mercado_eur", "valor_tm_atual",
                            "valor_tm_media_12m", "valor_tm_ultima_avaliacao", "variacao_tm_12m_pct", "fim_contrato",
                            "goals_p90", "assists_p90", "xg_p90", "xa_p90", "chances_created_p90",
                            "def_actions_p90", "sprints_p90", "historico_temporadas", "ultimos_jogos")
                if x in lookup]
        for col in cols:
            mapped = r["_core"].map(lookup[col])
            if col in ("qualidade", "confianca_pct", "fonte_qualidade"):     # UMA qualidade: a do universo manda
                r[col] = mapped.combine_first(r[col]) if col in r else mapped
            else:
                r[col] = r[col].combine_first(mapped) if col in r else mapped
        for col in ("potencial", "potencial_porque", "pid", "idade"):
            if col in lookup:
                mapped = r["_core"].map(lookup[col])
                r[col] = r[col].combine_first(mapped) if col in r else mapped
    r = _fill_from_club_games(r, universe, team)
    if "qualidade" not in r:
        r["qualidade"] = pd.to_numeric(r.get("nota"), errors="coerce")
    else:
        r["qualidade"] = pd.to_numeric(r["qualidade"], errors="coerce").combine_first(
            pd.to_numeric(r.get("nota"), errors="coerce"))
    return r


def _fill_from_club_games(r, universe, team):
    """rodada 13: minutos/jogos/nota/números por 90 de CADA atleta pelos jogos do próprio clube (sem confusão com
    homônimos), e a qualidade + características recalculadas na régua do mercado para esses atletas."""
    if not team or r.empty:
        return r
    try:
        from src.data_lake.ids import player_core
        from src.squad.matchday import canonical_names
        from src.ui.context import get_service
        from src.ui.pages.clubs import same_team_names

        cs = E.club_player_stats(get_service().db, same_team_names(team))
    except Exception:
        return r
    if cs is None or cs.empty:
        return r
    by_core = cs.set_index("_core")
    core = r["_core"].copy()
    miss = ~core.isin(by_core.index)
    if miss.any():
        canon = canonical_names(r.loc[miss, "nome"].astype(str).tolist(), cs["nome_jogos"].astype(str).tolist())
        core.loc[miss] = [player_core(canon.get(n, n)) for n in r.loc[miss, "nome"].astype(str)]
    hit = core.isin(by_core.index)
    if not hit.any():
        return r
    cols = ["minutos_12m", "jogos_12m", "rating_12m", "ultimo_jogo"] + [c for c in cs.columns if c.endswith("_p90")
                                                                      or c in ("pass_accuracy_pct", "duels_won_pct")]
    for c in cols:
        if c in by_core:
            vals = core.map(by_core[c])
            r[c] = vals.where(hit, r[c] if c in r else np.nan)
    r["rating_media"] = r.get("rating_12m")
    r["fonte_numeros"] = np.where(hit, "jogos do clube (12 meses)", "sem jogos do clube nos últimos 12 meses")
    # quem não jogou pelo clube no último ano: 0 minuto medido (não herda números de um homônimo)
    for c in ("minutos_12m", "jogos_12m"):
        if c in r:
            r.loc[~hit, c] = pd.to_numeric(r.loc[~hit, c], errors="coerce").where(
                r.loc[~hit].get("historico_ambiguo", pd.Series(False, index=r.loc[~hit].index)).ne(True), 0)
    try:
        # rodada 20: UMA nota por jogador — a do mercado (mesma régua em todo o app). A régua pelos jogos do clube só
        # completa quem não tem nota no mercado ou é homônimo sem números (antes sobrescrevia: 89 aqui × 66 no mercado)
        q_market = pd.to_numeric(r.get("qualidade"), errors="coerce")
        amb = r.get("historico_ambiguo", pd.Series(False, index=r.index)).fillna(False).astype(bool)
        redo = hit & (q_market.isna() | amb)
        if not redo.any():
            return r
        rq = E.roster_quality(r[redo], universe)
        for c in rq.columns:
            if c not in r:
                r[c] = pd.Series([None] * len(r), index=r.index, dtype=object) if c.startswith("caracter") else np.nan
            if c == "caracteristicas":
                for i, v in rq[c].items():
                    r.at[i, c] = v
            else:
                r.loc[rq.index, c] = rq[c]
    except Exception:
        pass
    return r


@_perf_timed("scout._diagnosis")
@_heavy_cache(show_spinner=False, ttl=900, max_entries=16)
def _diagnosis(team, version, roster_records):
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    club = E.market_club(D.table("tm_clubes"), team)
    transfers = D.table("tm_transferencias", None, "para_clube_id", [club["transfermarkt_id"]]) \
        if club and club.get("transfermarkt_id") is not None else pd.DataFrame()
    return E.diagnose_club(get_service().db, same_team_names(team), pd.DataFrame(roster_records),
                           D.table("tm_clubes"), transfers)


def _club_squad(team, version, universe):
    from src.data_hub.gender import drop_women_players
    from src.ui.context import get_service as _gs
    from src.ui.pages.clubs import same_team_names as _stn

    try:
        from src.ui.pages.squad import _squad
        data = _squad(team, version)
        sq = _merge_roster(data.get("squad"), universe, team, version)
        return {**data, "squad": drop_women_players(sq, _gs().db, _stn(team))}     # rodada 20
    except Exception:
        from src.ui.context import get_service
        from src.ui.pages.clubs import same_team_names
        club = E.market_club(D.table("tm_clubes"), team)
        roster = E.current_roster(get_service().db, club, same_team_names(team), D.table("tm_jogadores"), universe)
        return {"squad": _merge_roster(roster, universe, team, version), "club": club, "fonte": "Transfermarkt + escalações"}


def _dossier(player, roster):
    def unpack(v):
        try:
            return json.loads(v) if isinstance(v, str) else (v or [])
        except Exception:
            return []
    hist, recent = unpack(player.get("historico_temporadas")), unpack(player.get("ultimos_jogos"))
    try:                                   # rodada 23: relatório do olheiro estilo FM (veredito, estrelas, atributos)
        from src.scout import attributes as AT
        from src.ui import fm, player_fm

        v, txt = AT.verdict(player.get("score_scout"))
        fm.verdict_card(v, txt)
        player_fm.overview(player, key=f"dos_{_slug(player.get('nome'))}_{_slug(player.get('papel_alvo'))}")
        player_fm.squad_compare(player, roster, key=f"dosc_{_slug(player.get('nome'))}")
    except Exception:
        pass
    # rodada 13: o porquê vem primeiro, em cartões verdes/vermelhos; números detalhados ficam abaixo
    from src.scout.traits import traits_html

    w = E.why_chosen(player, roster)
    st.markdown("**Características (só o que se destaca na função)**")
    st.markdown(traits_html(player.get("caracteristicas") or [], None, why=True), unsafe_allow_html=True)
    ca, cb = st.columns(2)
    with ca:
        st.markdown("**✅ Por que a IA indica**")
        for x in w["porque"] or ["Encaixe com uma necessidade detectada no elenco."]:
            st.markdown(f'<div style="border-left:4px solid #22C55E;background:#0B1120;border-radius:10px;'
                        f'padding:.45rem .7rem;margin-bottom:.35rem">{html.escape(x)}</div>', unsafe_allow_html=True)
    with cb:
        st.markdown("**⚠️ Pontos de atenção**")
        for x in w["atencao"] or ["Nenhum alerta forte nos números disponíveis."]:
            st.markdown(f'<div style="border-left:4px solid #EF4444;background:#0B1120;border-radius:10px;'
                        f'padding:.45rem .7rem;margin-bottom:.35rem">{html.escape(x)}</div>', unsafe_allow_html=True)
    pot = player.get("potencial", player.get("potencial_teto"))
    if pot is not None and pd.notna(pot):
        st.markdown(f'<div style="border-left:4px solid #22D3EE;background:#0B1120;border-radius:10px;padding:.5rem .8rem;'
                    f'margin:.4rem 0">🌱 <b>Potencial {float(pot):.0f}</b> (overall hoje {player.get("qualidade", "—")}) · '
                    f'{html.escape(str(player.get("potencial_porque") or ""))}'
                    + (f' · confiança {float(player.get("potencial_confianca_pct")):.0f}%'
                       if pd.notna(player.get("potencial_confianca_pct")) else "")
                    + '<br><small style="color:#94A3B8">Potencial é projeção: idade × talento medido (produção na '
                      'função, nota, minutos × nível do time, valor para a idade, toques, base, físico).</small></div>',
                    unsafe_allow_html=True)
    st.markdown("**Números detalhados**")
    metrics = [
        ("Qualidade calculada por função", player.get("qualidade_estatistica", player.get("qualidade"))),
        ("Acerto de passe (%)", player.get("pass_accuracy_pct")), ("Duelos ganhos (%)", player.get("duels_won_pct")),
        ("Aéreos ganhos (%)", player.get("aerial_pct")), ("Dribles certos (%)", player.get("dribble_pct")),
        ("Finalizações no alvo (%)", player.get("shot_acc_pct")), ("Toques na bola/90", player.get("touches_p90")),
        ("Dribles/90", player.get("dribbles_p90")), ("Desarmes/90", player.get("tackles_p90")),
        ("Nota externa 0–100", player.get("nota_externa")),
        ("Valor TM no cadastro (€)", player.get("valor_tm_atual", player.get("valor_mercado_eur"))),
        ("Média de avaliação TM em 12m (€)", player.get("valor_tm_media_12m")),
        ("Última avaliação TM em 12m (€)", player.get("valor_tm_ultima_avaliacao")),
        ("Variação TM em 12m (%)", player.get("variacao_tm_12m_pct")),
        ("Minutos (últimos 12 meses)", player.get("minutos_12m", player.get("minutos"))),
        ("Jogos 12m", player.get("jogos_12m", player.get("jogos"))),
        ("Nota média 12m ajustada", player.get("rating_12m", player.get("rating_media"))),
        ("Nível médio dos adversários (12m, 0–100)", player.get("nivel_adversario_12m")),
        ("Ajuste médio por adversário (12m)", player.get("ajuste_adversario_12m")),
        ("Gols/90", player.get("goals_p90")), ("Assistências/90", player.get("assists_p90")),
        ("xG/90", player.get("xg_p90")), ("xA/90", player.get("xa_p90")),
        ("Criação/90", player.get("chances_created_p90")), ("Ações defensivas/90", player.get("def_actions_p90")),
    ]
    comparison_table(pd.DataFrame([{"Indicador": k, "Valor": "—" if v is None or pd.isna(v) else round(float(v), 3)}
                                   for k, v in metrics]))
    if player.get("fontes_nota_externa"):
        st.caption("Fonte(s) da nota externa: " + str(player.get("fontes_nota_externa")))
    if player.get("clube_observado") and player.get("clube_tm") and str(player.get("clube_tm")) != str(player.get("clube")):
        st.caption(f"Vínculo observado em partidas recentes: {player.get('clube')}. O cadastro Transfermarkt ainda apontava {player.get('clube_tm')}; transferência não confirmada apenas por esta evidência.")
    if hist:
        d = pd.DataFrame(hist)
        cols = [c for c in ("temporada", "jogos", "minutos", "rating_media", "nivel_adversario_medio",
                            "ajuste_adversario_medio", "goals", "assists", "xg", "xa") if c in d]
        comparison_table(d[cols].rename(columns={"temporada":"Temporada","jogos":"Jogos","minutos":"Minutos",
            "rating_media":"Nota ajustada","nivel_adversario_medio":"Nível adversário médio",
            "ajuste_adversario_medio":"Ajuste adversário","goals":"Gols","assists":"Assistências","xg":"xG","xa":"xA"}))
    if recent:
        d = pd.DataFrame(recent)
        cols = [c for c in ("match_date", "team_name", "competition_name", "minutes", "rating",
                            "rating_ajustada", "_opponent_level", "_opponent_adjustment") if c in d]
        comparison_table(d[cols].rename(columns={"match_date":"Data","team_name":"Clube",
            "competition_name":"Competição","minutes":"Minutos","rating":"Nota FotMob",
            "rating_ajustada":"Nota ajustada","_opponent_level":"Nível adversário (0–100)",
            "_opponent_adjustment":"Ajuste por adversário"}).head(15))
    realism, fit, syn = player.get("realismo") or {}, player.get("compatibilidade") or {}, player.get("sinergia") or {}
    st.markdown("**Motivo da indicação**")
    st.write(player.get("motivo_principal") or "Encaixe com uma necessidade detectada no elenco.")
    st.markdown(f"**Realismo:** {realism.get('score','—')}% · {realism.get('rotulo','sem estimativa')} · "
                f"taxa aproximada {_money(realism.get('taxa_estimada_eur'))}")
    for x in realism.get("motivos", []):
        st.write("• " + x)
    st.markdown(f"**Compatibilidade tática:** {fit.get('score','—')}% · {fit.get('label','sem dados')} · "
                f"confiança {fit.get('confianca','—')}")
    if fit.get("evidencias"):
        comparison_table(pd.DataFrame(fit["evidencias"]))
    st.markdown(f"**Encaixe com o elenco atual:** {syn.get('score','—')}%")
    for x in syn.get("companheiros", []):
        st.write(f"• **{x['nome']}** — {_role(x['papel'])}: {x['motivo']}")
    st.caption(syn.get("limite", "A sinergia é uma aproximação por posição e estatísticas; não é tracking."))


def _traits_short(player):
    from src.scout.traits import traits_html

    items = player.get("caracteristicas")
    return traits_html(items, 3) if isinstance(items, list) and items else ""


def _add_player(player, plan_key):
    current = st.session_state.setdefault(plan_key, [])
    clean = json.loads(json.dumps(player, default=str).replace("NaN", "null"))
    if not any(x.get("_core") == player.get("_core") and x.get("nome") == player.get("nome") for x in current):
        current.append(clean)
        st.toast(f"✅ {player.get('nome')} entrou no plano da janela ({len(current)} reforço(s)).")
    else:
        st.toast(f"{player.get('nome')} já está no plano.")
    st.session_state[plan_key] = current


def _ai_filter_form(key: str, nations: List[str], aff: Dict[str, Any], role_choices: Optional[List[str]] = None,
                    need_roles: Optional[List[str]] = None, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Rodada 22: os MESMOS filtros nas duas listas da IA (Top 5 e Três melhores): idade, qualidade, valor, nacionalidade
    e "incluir estrelas fora do patamar". Num formulário: só recalcula ao apertar o botão."""
    d = {"age": (16, 40), "q": 0, "fee": 0.0, "nation": "Todas", "stars": False, **(defaults or {})}
    out: Dict[str, Any] = {}
    with st.form(f"{key}_form", border=False):
        if role_choices:
            out["role"] = st.selectbox("Posição", role_choices, key=f"{key}_role",
                                       format_func=lambda r: _role(r) + ("  · carência" if r in (need_roles or []) else ""))
        fa, fb, fc = st.columns(3)
        out["age"] = fa.slider("Faixa etária", 16, 40, d["age"], key=f"{key}_age")
        out["q"] = fb.slider("Qualidade mínima", 0, 100, d["q"], key=f"{key}_quality")
        out["fee"] = fc.number_input("Valor máximo (€ mi · 0 = sem limite)", 0.0, 500.0, float(d["fee"]), key=f"{key}_max_value")
        fd, fe = st.columns([2, 1])
        out["nation"] = fd.selectbox("Nacionalidade desejada", nations, key=f"{key}_nation",
                                     format_func=lambda n: n if n == "Todas" else f"{n} · adaptação {aff[n][0]}%")
        out["stars"] = fe.toggle("Incluir estrelas fora do patamar", value=d["stars"], key=f"{key}_stars",
                                 help="Desligado: a IA não sugere quem está muito acima do patamar salarial/fama do clube.")
        st.form_submit_button("🔎 Aplicar filtros", type="primary")
    return out


def _apply_ai_filters(df: pd.DataFrame, f: Dict[str, Any]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    lo, hi = f.get("age") or (16, 40)
    if (lo > 16 or hi < 40) and "idade" in out:
        ages = np.floor(pd.to_numeric(out["idade"], errors="coerce"))        # 23,8 anos = 23 (faixa inclusiva)
        out = out[ages.isna() | ages.between(lo, hi)]
    if f.get("q") and "qualidade" in out:
        out = out[pd.to_numeric(out["qualidade"], errors="coerce").fillna(0) >= f["q"]]
    if f.get("fee") and "valor_mercado_eur" in out:
        out = out[pd.to_numeric(out["valor_mercado_eur"], errors="coerce").fillna(0) <= float(f["fee"]) * 1e6]
    if f.get("nation") and f["nation"] != "Todas" and "nacionalidade" in out:
        out = out[out["nacionalidade"].astype(str) == f["nation"]]
    if not f.get("stars") and "realismo" in out:
        out = out[[not (isinstance(r, dict) and r.get("teto_patamar") is not None and r["teto_patamar"] <= 20)
                   for r in out["realismo"]]]
    return out


def _player_card(player, roster, team, idx, plan_key, rejected_key):
    name = str(player.get("nome") or "Jogador")
    r = player.get("realismo") or {}
    score = int(r.get("score") or 0)
    tag = "viable" if score >= 76 else "loan" if r.get("oportunidade_emprestimo") else "dream"
    quality = player.get("qualidade")
    quality = "sem nota" if quality is None or pd.isna(quality) else f"{float(quality):.0f}/100"
    position = player.get("papel_alvo_label") or _role(player.get("papel"))
    club = str(player.get("clube") or "Clube não identificado")
    nationality = str(player.get("nacionalidade") or "")
    from src.ui.crests import crest_img

    club_crest = crest_img(club, "xs") if club and club != "Clube não identificado" else ""
    flag = crest_img(nationality, "xs") if nationality else ""
    player_html = (
        f'<div class="scout-player"><div class="scout-avatar">{html.escape(_initials(name))}</div>'
        f'<div class="scout-main"><div class="scout-name">{html.escape(name)}</div>'
        f'<div class="scout-sub">{html.escape(str(position))} · {club_crest} {html.escape(club)} · '
        f'{html.escape(str(int(float(player.get("idade")))) if pd.notna(player.get("idade")) else "idade n/d")} anos · '
        f'{flag} {html.escape(nationality or "nacionalidade n/d")}</div>'
        f'<div class="scout-tags"><span class="scout-tag {tag}">{html.escape(str(r.get("rotulo","Sem estimativa")))} · {score}%</span>'
        f'<span class="scout-tag neutral">Compatibilidade {(player.get("compatibilidade") or {}).get("score","—")}%</span>'
        f'<span class="scout-tag neutral">Overall {quality}</span>'
        + (f'<span class="scout-tag neutral" title="{html.escape(str(player.get("potencial_porque") or ""))}">'
           f'Potencial {float(player.get("potencial") if pd.notna(player.get("potencial")) else player.get("potencial_teto")):.0f}</span>'
           if pd.notna(player.get("potencial", player.get("potencial_teto"))) else "") + '</div>'
        f'<div style="margin-top:4px">{_traits_short(player)}</div></div>'
        f'<div class="scout-value">{_money(player.get("valor_mercado_eur"))}<small>valor de referência</small></div></div>'
    )
    st.markdown(player_html, unsafe_allow_html=True)
    a, b = st.columns([1.1, 1.1])
    in_plan = any(x.get("nome") == name for x in st.session_state.get(plan_key) or [])
    a.button("✓ No plano" if in_plan else "＋ Adicionar ao plano", key=f"scout_add_{_slug(name)}_{idx}",
             type="secondary" if in_plan else "primary", use_container_width=True, disabled=in_plan,
             on_click=_add_player, args=(player, plan_key))
    if b.button("Abrir perfil ↗", key=f"scout_open_{_slug(name)}_{idx}", use_container_width=True):
        open_view("jogador", name=name, core=player.get("_core"), club=str(player.get("clube") or ""),
                  pid=str(player.get("pid") or ""))
    # rodada 20: 👍/👎 = "esse jogador é bom / não é" — não adiciona nem descarta; reordena as próximas sugestões.
    # rodada 21: dentro de um FRAGMENTO — o clique refaz só este pedaço (antes recarregava o Scout inteiro)
    _vote_box(team, name, idx, player.get("votos_scout") or (0, 0),
              str(player.get("papel_alvo") or player.get("papel") or "sugestao"))
    with st.expander("Ver dossiê completo da IA"):
        _dossier(player, roster)
    with st.expander("Descartar e recalcular"):
        reason = st.selectbox("Motivo", ["Não é bom o suficiente / não agrega", "Pior que o titular atual",
            "Muito caro","Muito velho","Perfil físico inadequado","Fase ruim (jogando mal)","Não combina com o estilo",
            "Histórico de lesões","Salário provavelmente alto","Limite de estrangeiros","Nacionalidade/contexto inviável",
            "Quero outra característica","Não é prioridade","Outro motivo"],
            key=f"scout_reason_{_slug(name)}_{idx}")
        if st.button("Descartar este alvo", key=f"scout_reject_{_slug(name)}_{idx}"):
            from src.ui.context import get_service
            E.record_rejection(get_service().db, team, name, str(player.get("papel_alvo") or ""),
                               reason, float(player.get("score_scout") or 0))
            rejected = st.session_state.setdefault(rejected_key, [])
            if name not in rejected:
                rejected.append(name)
            st.rerun()



@st.fragment
def _vote_box(team, name, idx, votes, role):
    up, down = votes
    v1, v2 = st.columns([1, 3])
    with v1:
        vote = st.feedback("thumbs", key=f"scout_vote_{_slug(team)}_{_slug(name)}_{idx}")
    flag = f"_voted_{team}_{name}_{idx}"
    if vote is not None and not st.session_state.get(flag):
        st.session_state[flag] = True
        from src.ui.context import get_service

        E.record_vote(get_service().db, team, name, bool(vote))
        try:
            from src.intelligence import lab_brain as LB

            LB.feedback("scout", role, bool(vote), {"jogador": name, "clube": team})
        except Exception:
            pass
    if st.session_state.get(flag):
        v2.caption("✅ Voto registrado — a ordem das próximas listas já considera.")
    else:
        v2.caption("Boa sugestão? Seu voto ajusta a ordem das próximas listas (não adiciona nem descarta)."
                   + (f" Votos até aqui: 👍 {up} · 👎 {down}." if (up or down) else ""))


def _pitch_figure(xi, title):
    import plotly.graph_objects as go

    fig = go.Figure()
    line = "rgba(255,255,255,.70)"
    fig.add_shape(type="rect", x0=0, y0=0, x1=120, y1=80, line=dict(color=line, width=2))
    fig.add_shape(type="line", x0=60, y0=0, x1=60, y1=80, line=dict(color=line, width=1))
    fig.add_shape(type="circle", x0=50, y0=30, x1=70, y1=50, line=dict(color=line, width=1))
    fig.add_shape(type="rect", x0=0, y0=18, x1=18, y1=62, line=dict(color=line, width=1))
    fig.add_shape(type="rect", x0=102, y0=18, x1=120, y1=62, line=dict(color=line, width=1))
    fig.add_shape(type="rect", x0=0, y0=30, x1=6, y1=50, line=dict(color=line, width=1))
    fig.add_shape(type="rect", x0=114, y0=30, x1=120, y1=50, line=dict(color=line, width=1))
    x, y, labels, hover, sizes = [], [], [], [], []
    for p in xi or []:
        if p.get("x") is None or p.get("y") is None:
            continue
        x.append(float(p["x"]))
        y.append(float(p["y"]))
        name = str(p.get("jogador") or "Vaga em aberto")
        labels.append(name.split()[-1] if name else "—")
        hover.append(f"{p.get('papel_pt', p.get('papel',''))}<br>{name}<br>Nota: {p.get('nota','—')}")
        sizes.append(19 if p.get("jogador") else 13)
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers+text", text=labels, textposition="middle center",
        textfont=dict(color="#FFFFFF", size=10, family="Arial"),
        marker=dict(size=sizes, color="#2563EB", line=dict(color="#DBEAFE", width=2), opacity=.96),
        hovertext=hover, hoverinfo="text", showlegend=False,
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#E2E8F0")),
        height=420, margin=dict(l=8, r=8, t=40, b=8),
        paper_bgcolor="#0D1728", plot_bgcolor="#14532D",
        xaxis=dict(range=[-2,122], visible=False, fixedrange=True),
        yaxis=dict(range=[82,-2], visible=False, fixedrange=True, scaleanchor="x", scaleratio=1),
        font=dict(color="#E2E8F0"),
    )
    return fig

def _pdf_bytes(markdown):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except ImportError:
        return None
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    width, height = A4
    y = height - 48
    for raw in markdown.splitlines():
        line = raw.replace("#", "").replace("**", "").replace("*", "").strip()
        words, current = line.split(), ""
        if not line:
            y -= 9
            continue
        for word in words:
            test = (current + " " + word).strip()
            if stringWidth(test, "Helvetica", 9) > width - 84:
                pdf.setFont("Helvetica", 9)
                pdf.drawString(42, y, current)
                y -= 13
                current = word
            else:
                current = test
        pdf.setFont("Helvetica-Bold" if raw.startswith("#") else "Helvetica", 10 if raw.startswith("#") else 9)
        pdf.drawString(42, y, current[:180])
        y -= 15
        if y < 48:
            pdf.showPage()
            y = height - 48
    pdf.save()
    return out.getvalue()


def render(_ctx=None):
    from src.data_hub.search import fast_scores
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names
    from src.ui.pages.squad import _team_options
    from src.data_lake.ids import team_core

    back_button(key="scout_back")
    page_header("Scout & Planejamento", "War Room de mercado: carências do clube, alvos realistas e simulação do elenco.")
    service = get_service()
    # Mantém a renovação periódica do catálogo externo e também invalida o cache
    # imediatamente quando o SQLite principal/WAL/journal realmente muda.
    # A assinatura usa apenas metadados de arquivo: não percorre centenas de milhares de linhas.
    from src.scout import snapshot as S

    # rodada 7: versão ESTÁVEL (só muda quando a fotografia do universo é refeita, a cada ~6 h pelo processo de
    # fundo). Antes mudava a cada jogo gravado pela FotMob e a aba recalculava tudo sem nunca terminar.
    version = S.version()
    prefill = str(param("club", "") or st.session_state.get("scout_selected_club", ""))
    try:
        first = S.load() is None
        msg = ("Montando o mercado pela primeira vez (só desta vez — depois fica pronto e é atualizado em segundo plano)..."
               if first else "Abrindo o mercado...")
        with st.spinner(msg):
            data = _market_data(version)
        if first:
            version = S.version()
        if (S.meta() or {}).get("parcial") or data.get("parcial"):
            st.warning("Esta fotografia do mercado é uma versão antiga reaproveitada: faltam os jogadores das ligas "
                       "baixadas depois (Série B/C, sul-americanas). Com o app fechado, rode "
                       "`python -m src.scout.snapshot` (ou espere o processo de fundo refazer).")
        _overall_explainer()
        age = S.age_hours()
        if age is not None:
            st.caption(f"Mercado e histórico: fotografia de {age:.1f} h atrás (refeita em segundo plano a cada "
                       f"{S.max_age_hours():g} h).")
    except Exception as exc:
        st.error(f"Erro ao carregar os dados de mercado: {exc}")
        return
    universe, clubs = data["universe"], data["clubs"]
    with st.form("scout_club_form", border=False):           # rodada 10: só busca ao apertar Enter/Buscar
        fq, fb = st.columns([5, 1])
        q = fq.text_input("Pesquisar clube", value=prefill, placeholder="Ex.: Cruzeiro, Flamengo, Como 1907 — Enter para buscar")
        fb.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
        fb.form_submit_button("🔎 Buscar", use_container_width=True)
    options = _team_options(q, 30) if q.strip() else _team_options("", 30)
    if not options and not clubs.empty:
        options = clubs["nome"].astype(str).tolist()[:30]
    if q.strip() and options and q not in options:
        score = fast_scores(q, options)
        if not score or max(score.values()) < .55:
            st.info("Não localizei esse nome com segurança. Tente o nome usado no catálogo.")
    if not options:
        empty_state("Sem clubes no catálogo", "Sincronize Transfermarkt e fontes de jogos/escalações.", "🛡️")
        return
    from src.data_lake.ids import team_core
    default = prefill if prefill in options else next(
        (name for name in options if prefill and team_core(name) == team_core(prefill)), None)
    # Ao chegar pelo botão "Planejar elenco" do perfil, sincroniza a seleção com o clube clicado.
    if default and st.session_state.get("scout_club_choice") != default:
        st.session_state["scout_club_choice"] = default
    if st.session_state.get("scout_club_choice") not in options:
        st.session_state.pop("scout_club_choice", None)
    # rodada 20: nenhum clube escolhido de fábrica (antes abria o 1º da lista e já calculava tudo)
    team = st.selectbox("Clube a planejar", options, key="scout_club_choice", index=None,
                        placeholder="Escolha o clube a planejar")
    if not team:
        empty_state("Escolha o clube", "Pesquise o nome acima e selecione o clube para abrir o planejamento.", "🛡️")
        return
    st.session_state["scout_selected_club"] = team
    aliases = same_team_names(team)
    club = E.market_club(clubs, team)
    if club:
        a, b = st.columns([1, 8])
        with a:
            from src.ui.crests import crest_img
            st.markdown(crest_img(team, "lg"), unsafe_allow_html=True)
        with b:
            st.markdown(f"### {team}")
            st.caption(f"{club.get('liga') or 'Liga n/d'} · {club.get('pais') or 'País n/d'}")
        if st.button("Abrir perfil do clube ↗", key="scout_open_club"):
            open_view("time", name=team)
    else:
        st.caption("Clube sem vínculo seguro no Transfermarkt; serão usados os jogos e escalações locais disponíveis.")

    squad_data = _club_squad(team, version, universe)
    roster = squad_data.get("squad", pd.DataFrame())
    records = roster.replace({np.nan: None}).to_dict("records") if not roster.empty else []
    with st.spinner("Lendo os últimos 50 jogos, estilo, técnico e necessidades..."):
        diagnosis = _diagnosis(team, version, records)
    transfers = D.table("tm_transferencias", None, "para_clube_id", [club["transfermarkt_id"]]) \
        if club and club.get("transfermarkt_id") is not None else pd.DataFrame()
    country, competition = str((club or {}).get("pais") or ""), str((club or {}).get("liga") or "")
    next_season = st.selectbox("Temporada do planejamento",
        [date.today().year + 1, date.today().year], index=0, key="scout_target_season")
    financial = E.buyer_financial_profile(service.db, club, roster, transfers, season=next_season)
    financial["estilo"] = dict(diagnosis.get("estilo") or {})
    try:                                   # rodada 22: o MODELO DE JOGO (identidade tática) entra no encaixe tático
        from src.ui import identity_view

        _idn = identity_view._data(tuple(aliases), service.db.team_version(aliases), 20)
        words = set((_idn.get("estatisticas") or {}).get("estilo") or [])
        extra = (["posse e construção"] if "propõe o jogo (gosta da bola)" in words else []) + \
                (["transição e ataque vertical"] if ("reativo (abre mão da bola)" in words or "jogo direto" in words) else []) + \
                (["amplitude e cruzamentos"] if "ataque pelos lados com cruzamento" in words else [])
        if extra:
            financial["estilo"]["tracos"] = list(dict.fromkeys(list(financial["estilo"].get("tracos") or []) + extra))
        financial["modelo_de_jogo"] = _idn.get("contratacao") or []
    except Exception:
        pass
    financial["club_aliases"] = aliases
    foreign_count = 0
    if not roster.empty and country and "nacionalidade" in roster:
        likely = roster.copy()
        likely["_selection_score"] = (
            pd.to_numeric(likely.get("qualidade"), errors="coerce").fillna(45) * .65 +
            pd.to_numeric(likely.get("minutos_12m", pd.Series(0, index=likely.index)), errors="coerce").fillna(0).clip(0, 2500) / 2500 * 35
        )
        likely = likely.sort_values("_selection_score", ascending=False).head(23)
        foreign_count = int(sum(1 for n in likely["nacionalidade"].dropna().astype(str)
                                if E.is_foreign_player(n, country) is True))
    financial["estrangeiros_atual"] = foreign_count
    financial["nat_market"] = _nat_market(version, country, team_core(team), universe, roster)   # rodada 11
    rejected_key = "scout_rejected_" + _slug(team_core(team))
    st.session_state.setdefault(rejected_key, [])
    feedback = E.rejection_preferences(service.db, team)
    feedback_reason = " · ".join(feedback.get("motivos", []))
    allow_old_rejections = st.checkbox("Permitir novamente jogadores descartados em pesquisas anteriores",
                                       value=False, key="scout_allow_old_rejections")
    rejected_for_run = list(st.session_state[rejected_key])
    if not allow_old_rejections:
        rejected_for_run.extend(feedback.get("jogadores_recusados", []))

    pool = universe.copy() if universe is not None and not universe.empty else pd.DataFrame()
    if not pool.empty:
        pool = pool[pool["papel"].isin(E.ROLE_LABELS)].copy()
    plan_key = "scout_plan_" + _slug(team_core(team))
    rejected_key = "scout_rejected_" + _slug(team_core(team))
    decisions_key = "scout_decisions_" + _slug(team_core(team))
    st.session_state.setdefault(plan_key, [])
    st.session_state.setdefault(rejected_key, [])
    decisions = st.session_state.setdefault(decisions_key, {})
    needs = diagnosis.get("necessidades") or []
    if not needs and not roster.empty:
        counts = roster["papel"].value_counts()
        used = E.roles_used(service.db, aliases) or {"GK","CB","LB","RB","DM","CM","AM","LW","RW","ST"}
        needs = [{"papel": r, "urgencia": 55, "motivo": "profundidade posicional reduzida"}
                 for r in sorted(used) if int(counts.get(r, 0)) < 2]
    # rodada 21: a IA sugere para as carências OU para qualquer posição (reforço/concorrência), à escolha do usuário
    scope = st.segmented_control("A IA sugere para", ["Carências do elenco", "Todas as posições", "Escolher posições"],
                                 default="Carências do elenco", key="scout_need_scope") or "Carências do elenco"
    urg = {n.get("papel"): float(n.get("urgencia") or 40) for n in needs}
    if scope == "Todas as posições":
        needs = [{"papel": r, "urgencia": urg.get(r, 40),
                  "motivo": next((n.get("motivo") for n in needs if n.get("papel") == r), "reforço/concorrência na posição")}
                 for r in E.ROLE_LABELS if r in ("GK", "CB", "LB", "RB", "DM", "CM", "AM", "LW", "RW", "ST")]
    elif scope == "Escolher posições":
        picked = st.multiselect("Posições", list(E.ROLE_LABELS), default=[n.get("papel") for n in needs][:2],
                                format_func=_role, key="scout_need_pick")
        needs = [{"papel": r, "urgencia": urg.get(r, 50), "motivo": "posição escolhida por você"} for r in picked]
    with st.spinner("Classificando qualidade, realismo, encaixe e sinergia..."):
        ranked = _rank_candidates(version, team, country, competition, next_season,
                                  tuple(rejected_for_run), feedback_reason,
                                  pool, needs, financial, roster,
                                  needs_key=tuple((n.get("papel"), round(float(n.get("urgencia") or 0))) for n in needs)) \
        if not pool.empty else pd.DataFrame()
    votes = E.player_votes(service.db)
    ranked = E.apply_votes(_not_ours(ranked, team, version, roster), votes)

    # rodada 13: abas com estado (key) — "Adicionar ao plano" não joga mais o usuário de volta para a 1ª aba, e a
    # barra do plano mostra na hora quem já entrou, com atalho para o Planejamento
    tab_names = ["IA · Top 5", "Diagnóstico", "Busca manual", "Joias U23", "Planejamento"]
    plan_now = st.session_state.get(plan_key) or []
    if plan_now:
        pa, pb = st.columns([5, 1.3])
        pa.markdown('<div class="fm-card" style="border-left:4px solid #22D3EE;border-radius:12px;padding:.5rem .9rem">'
                    f'🧾 <b>Plano da janela: {len(plan_now)} reforço(s)</b> — '
                    + html.escape(", ".join(str(p.get("nome")) for p in plan_now)) + '</div>', unsafe_allow_html=True)
        pb.button("Ver planejamento →", key="scout_go_plan", use_container_width=True,
                  on_click=lambda: st.session_state.__setitem__("scout_tabs", "Planejamento"))
    tabs = st.tabs(tab_names, key="scout_tabs", default="IA · Top 5", on_change="rerun")
    with tabs[0]:
        if tabs[0].open is not False:          # rodada 21: só a aba aberta é montada
            st.markdown("#### Cinco nomes priorizados")
            if feedback.get("amostra"):
                st.caption(f"A recomendação considerou {feedback['amostra']} rejeição(ões) anteriores deste clube.")
            st.caption("Qualidade estatística por função + urgência + realismo + compatibilidade + sinergia. Abra cada dossiê para ver as evidências.")
            all_nat = sorted(pool["nacionalidade"].dropna().astype(str).unique().tolist()) if "nacionalidade" in pool else []
            nm = financial.get("nat_market") or {}
            aff = {n: nm.get(n) or E._affinity(n, country) for n in all_nat}
            nations = ["Todas"] + sorted(all_nat, key=lambda n: (-aff[n][0], n))
            if ranked.empty:
                empty_state("Ainda não há candidatos suficientes",
                    "Sincronize jogadores/valores do Transfermarkt e estatísticas individuais. A busca manual continua disponível.", "🎯")
            else:
                with st.expander("🎛️ Filtros dos cinco nomes (idade, qualidade, valor, nacionalidade)", expanded=False):
                    f5 = _ai_filter_form("scout_top5", nations, aff)
                top5 = _apply_ai_filters(ranked, f5)
                for idx, row in top5.head(5).iterrows():
                    _player_card(row.to_dict(), roster, team, int(idx), plan_key, rejected_key)
                if top5.empty:
                    st.info("Nenhum atleta atende aos filtros atuais. Amplie a faixa ou use a busca manual.")
                n_stars = len(_apply_ai_filters(ranked, {**f5, "stars": True})) - len(top5)
                if n_stars > 0 and not f5.get("stars"):
                    st.caption(f"Bom senso: {n_stars} estrela(s) acima do patamar salarial/fama do clube ficaram de fora "
                               "(ligue \"Incluir estrelas fora do patamar\" para ver).")
                st.markdown("#### Três melhores por posição")
                # rodada 10: TODAS as posições (não só as carentes) — a IA ranqueia sob demanda a posição escolhida
                need_roles = list(dict.fromkeys(ranked["papel_alvo"].tolist()))
                roles = need_roles + [r for r in E.ROLE_LABELS if r not in need_roles]
                # rodada 11/22: tudo num formulário, com os MESMOS filtros do Top 5 + a posição
                f3 = _ai_filter_form("scout_top3", nations, aff, role_choices=roles, need_roles=need_roles,
                                     defaults={"age": (18, 30), "q": 55, "fee": 30.0})
                role, age_band, quality_floor, maximum_fee, nation = f3["role"], f3["age"], f3["q"], f3["fee"], f3["nation"]
                if False:
                    base_rank = ranked
                else:
                    # rodada 11: sempre só esta posição — no ranking geral o mesmo atleta fica na posição em que pontua mais
                    # (um lateral virava "ala"/"ponta") e a lista desta posição chegava vazia
                    urg = next((float(n.get("urgencia") or 40) for n in needs if n.get("papel") == role), 40)
                    with st.spinner(f"A IA está garimpando {_role(role).lower()}s…"):
                        base_rank = _rank_candidates(version, team, country, competition, next_season,
                                                     tuple(rejected_for_run), feedback_reason, pool,
                                                     [{"papel": role, "urgencia": urg,
                                                       "motivo": next((n.get("motivo") for n in needs if n.get("papel") == role),
                                                                      "posição escolhida por você (reforço/concorrência)")}],
                                                     financial, roster, needs_key=("top3", role))
                base_rank = E.apply_votes(_not_ours(base_rank, team, version, roster), votes)
                filt3 = base_rank[base_rank["papel_alvo"] == role].copy() if not base_rank.empty else base_rank
                filt3 = _apply_ai_filters(filt3, f3)
                if nation != "Todas":
                    st.caption(f"Contexto: {aff[nation][1]}. Exceções existem, mas a IA pesa a adaptação no índice de realismo.")
                for idx, row in filt3.head(3).iterrows():
                    _player_card(row.to_dict(), roster, team, int(idx)+100, plan_key, rejected_key)
                if filt3.empty:
                    st.info("Nenhum atleta atende aos filtros atuais. Amplie a faixa ou use a busca manual.")
    with tabs[1]:
        if tabs[1].open is not False:          # rodada 21: só a aba aberta é montada
            quality = pd.to_numeric(roster.get("qualidade"), errors="coerce").mean() if not roster.empty else np.nan
            age = pd.to_numeric(roster.get("idade"), errors="coerce").mean() if not roster.empty else np.nan
            k = st.columns(5)
            k[0].metric("Jogadores", len(roster))
            k[1].metric("Qualidade média", f"{quality:.0f}/100" if pd.notna(quality) else "—")
            k[2].metric("Idade média", f"{age:.1f}" if pd.notna(age) else "—")
            k[3].metric("Valor do elenco", _money(financial.get("valor_elenco_eur")))
            k[4].metric("Jogos analisados", diagnosis.get("partidas_analisadas", 0))
            st.caption(f"Elenco: {squad_data.get('fonte','fontes locais')} · FotMob/estatísticas de partidas · "
                       "Transfermarkt/mercado e contratos. Referência de ingestão: " + data.get("atualizacao", "n/d"))
            st.markdown("#### Carências e prioridades")
            needs = diagnosis.get("necessidades") or []
            if needs:
                comparison_table(pd.DataFrame([{"Prioridade": round(float(x.get("urgencia",0))),
                    "Posição": _role(x["papel"]), "Diagnóstico": x.get("motivo"),
                    "Evidências": json.dumps(x.get("evidencias") or {}, ensure_ascii=False, default=str)} for x in needs]))
            else:
                st.info("Sem carência posicional suficientemente sustentada. Use a busca manual para explorar oportunidades.")
            if financial.get("modelo_de_jogo"):
                st.markdown("#### 🎯 O modelo de jogo pede (contratação por função)")
                for r in financial["modelo_de_jogo"]:
                    st.markdown(f"- **{r['funcao']}** — {r['porque']} · medir: {r['metricas']}")
                st.caption("Vem da identidade tática do clube (página do time › 🧭 Identidade tática). A IA usa esses traços "
                           "no encaixe tático de cada candidato.")
            st.markdown("#### Identidade tática e treinador")
            style = diagnosis.get("estilo") or {}
            lvl = style.get("nivel_identidade")
            badge = {"detalhada": "🟢 identidade detalhada (30+ jogos)", "inicial": "🟡 identidade inicial (8–29 jogos)",
                     "superficial": "🟠 leitura superficial (menos de 8 jogos)"}.get(lvl, "")
            if badge:
                st.caption(badge)
            forms = style.get("formacoes") or []
            if forms:
                st.write("**Desenhos usados:** " + " · ".join(f"{f} ({n} jogo{'s' if n != 1 else ''})" for f, n in forms))
            st.write(" · ".join(style.get("tracos") or ["Amostra insuficiente para traços de estilo"]))
            st.caption(style.get("fonte","") + " · " + style.get("contexto_tecnico","") + " · " + style.get("limite",""))
            if style.get("tracos_tecnico"):
                st.write("**Padrões anteriores do treinador:** " + " · ".join(style["tracos_tecnico"]))
                st.caption(f"{style.get('amostra_tecnico',0)} jogos anteriores · "
                           + ", ".join(style.get("clubes_anteriores_tecnico",[])))
            coach = diagnosis.get("treinador") or {}
            st.write(f"**Técnico identificado:** {coach.get('nome') or 'não identificado'} · "
                     f"{coach.get('jogos',0)} jogos observados no clube")
            st.markdown("#### O clube por jogo × a média da competição")
            _club_averages_chart(diagnosis, team)
            if not roster.empty:
                st.markdown("#### Elenco e notas")
                show = roster.copy()
                show["Posição"] = show["papel"].map(E.ROLE_LABELS).fillna("—")
                cols = [x for x in ("nome","Posição","idade","qualidade","confianca_pct","caracteristicas_top",
                                    "potencial_teto","valor_mercado_eur","jogos_12m","minutos_12m","rating_12m") if x in show]
                display = show[cols].rename(columns={"nome":"Jogador","idade":"Idade","qualidade":"Qualidade",
                    "confianca_pct":"Confiança (%)","caracteristicas_top":"Características","potencial_teto":"Potencial",
                    "valor_mercado_eur":"Valor de mercado","jogos_12m":"Jogos (12m)","minutos_12m":"Minutos (últimos 12 meses)",
                    "rating_12m":"Nota média 12m"})
                st.caption("Números de cada atleta pelos jogos do PRÓPRIO clube nos últimos 12 meses (nomes comuns não se "
                           "confundem mais com homônimos). Confiança = quanto a nota se apoia em minutos medidos: com poucos "
                           "minutos ela é puxada para a média. Características só aparecem quando o atleta está bem acima "
                           "da média da função (passe o mouse no perfil para ver o porquê).")
                if "Valor de mercado" in display:
                    display["Valor de mercado"] = display["Valor de mercado"].map(_money)
                styled_dataframe(display.sort_values("Qualidade", ascending=False, na_position="last"),
                             use_container_width=True, hide_index=True)
                selected = st.selectbox("Abrir jogador do elenco", ["—"] + roster["nome"].astype(str).tolist(),
                                        key="scout_roster_select")
                if selected != "—" and st.button("Abrir perfil ↗", key="scout_roster_link"):
                    open_view("jogador", name=selected, club=str(team or ""))
            else:
                st.warning("O elenco atual não pôde ser confirmado. As sugestões serão limitadas à cobertura do catálogo.")
            st.caption(f"Regra de estrangeiros: estimativa feita sobre até 23 atletas mais prováveis por qualidade/minutagem ({foreign_count} nacionalidade(s) estrangeira(s) identificada(s)); não equivale à lista oficial de relacionados.")
            if financial.get("faixa_proxy_eur"):
                lo, hi = financial["faixa_proxy_eur"]
                st.markdown("#### Capacidade financeira estimada")
                st.write(f"Faixa proxy: **{_money(lo)} a {_money(hi)}**.")
                st.caption(financial["natureza"] + f" · {financial.get('transferencias_pagas_amostra',0)} taxas pagas na amostra.")
            else:
                st.info("Não há histórico financeiro suficiente para estimar capacidade de investimento.")
    with tabs[2]:
        if tabs[2].open is not False:          # rodada 21: só a aba aberta é montada
            st.markdown("#### Filtros de jogador")
            if pool.empty:
                empty_state("Universo de jogadores indisponível", "Sincronize o catálogo Transfermarkt.", "👥")
            else:
                if "origem" not in pool and "clube_liga" in pool:
                    pool = pool.assign(origem=pool["clube_liga"].map(E.origin_group))
                # rodada 20: filtros num formulário — nada é pesquisado até apertar "Buscar" (antes cada mudança refazia tudo)
                with st.form("scout_manual_filters", border=False):
                    n0 = st.text_input("Nome (opcional)", placeholder="parte do nome do jogador")
                    c1,c2,c3,c4 = st.columns(4)
                    roles = ["Todas"] + sorted(pool["papel"].dropna().unique().tolist())
                    rf = c1.selectbox("Posição", roles, format_func=lambda x: "Todas" if x=="Todas" else _role(x))
                    amin = c2.number_input("Idade mínima", 15, 40, 18)
                    amax = c3.number_input("Idade máxima", 16, 50, 35)
                    qmin = c4.slider("Qualidade mínima", 0, 100, 0)
                    origins = ["Todas"] + (sorted(pool["origem"].dropna().astype(str).unique().tolist()) if "origem" in pool else [])
                    origin = st.segmented_control("Origem", origins, default="Todas", key="scout_origin") or "Todas"
                    d1,d2,d3 = st.columns(3)
                    nats = ["Todas"] + sorted(pool["nacionalidade"].dropna().astype(str).unique().tolist())
                    nat = d1.selectbox("Nacionalidade", nats)
                    leagues = ["Todas"] + sorted(pool.get("clube_liga", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
                    league_filter = d2.selectbox("Liga atual", leagues)
                    clubs_list = ["Todos"] + sorted(pool["clube"].dropna().astype(str).unique().tolist())
                    seller = d3.selectbox("Clube atual", clubs_list)
                    e1,e2 = st.columns(2)
                    max_market = pd.to_numeric(pool["valor_mercado_eur"], errors="coerce").max()
                    upper_market = float(max(1,max_market/1e6 if pd.notna(max_market) else 300))
                    vmin = e1.number_input("Valor mínimo (€ mi)", 0.0, upper_market, 0.0)
                    vmax = e2.number_input("Valor máximo (€ mi)", 0.0, upper_market, upper_market)
                    go_search = st.form_submit_button("🔎 Buscar com estes filtros", type="primary", use_container_width=True)
                if go_search:
                    st.session_state["scout_mf_on"] = True
                if not st.session_state.get("scout_mf_on"):
                    st.info("Escolha os filtros e aperte **🔎 Buscar com estes filtros**.")
                filt = pool.copy() if st.session_state.get("scout_mf_on") else pool.iloc[0:0].copy()
                if n0.strip():
                    from src.data_lake.ids import player_core as _pc

                    _k = _pc(n0)
                    filt = filt[filt["nome"].astype(str).map(_pc).str.contains(_k, regex=False, na=False)]
                if origin != "Todas" and "origem" in filt:
                    filt = filt[filt["origem"].astype(str) == origin]
                if rf!="Todas": filt=filt[filt["papel"]==rf]
                _ag=np.floor(pd.to_numeric(filt["idade"],errors="coerce")); filt=filt[_ag.isna()|_ag.between(amin,amax)]
                filt=filt[pd.to_numeric(filt["qualidade"],errors="coerce").fillna(0)>=qmin]
                if nat!="Todas": filt=filt[filt["nacionalidade"].astype(str)==nat]
                if league_filter!="Todas" and "clube_liga" in filt:
                    filt=filt[filt["clube_liga"].astype(str)==league_filter]
                if seller!="Todos": filt=filt[filt["clube"].astype(str)==seller]
                values=pd.to_numeric(filt["valor_mercado_eur"],errors="coerce").fillna(0)
                filt=filt[values.between(vmin*1e6,vmax*1e6)]
                filt=filt.sort_values("qualidade",ascending=False,na_position="last")
                st.caption(f"{len(filt):,} atletas dentro dos filtros.".replace(",","."))
                cols = [x for x in ("nome","papel","idade","clube","clube_liga","nacionalidade","valor_mercado_eur",
                                    "qualidade","nota_rankings","confianca_pct","minutos_12m","rating_12m") if x in filt]
                display=filt[cols].rename(columns={"nome":"Jogador","papel":"Posição","idade":"Idade","clube":"Clube",
                    "clube_liga":"Liga","nota_rankings":"Nota dos Rankings",
                    "nacionalidade":"Nacionalidade","valor_mercado_eur":"Valor (€)","qualidade":"Qualidade",
                    "confianca_pct":"Confiança (%)","minutos_12m":"Minutos (últimos 12 meses)","rating_12m":"Nota média (últimos 12 meses)"}).head(100)
                if "Valor (€)" in display: display["Valor (€)"]=display["Valor (€)"].map(_money)
                styled_dataframe(display,use_container_width=True,hide_index=True)
                if not filt.empty:
                    chosen=st.selectbox("Selecionar jogador",filt["nome"].astype(str).tolist(),key="scout_manual_pick")
                    p=filt[filt["nome"].astype(str)==chosen].iloc[0].to_dict()
                    p["papel_alvo"]=p.get("papel"); p["papel_alvo_label"]=_role(p.get("papel"))
                    p["realismo"]=E.transfer_realism(p,financial,country,competition,season=next_season)
                    p["compatibilidade"]=E.tactical_compatibility(p,diagnosis.get("estilo") or {})
                    p["sinergia"]=E.chemistry(p,roster)
                    with st.expander("Dossiê do jogador escolhido"):
                        _dossier(p,roster)
                    if st.button("＋ Adicionar jogador selecionado",key="scout_manual_add",type="primary"):
                        _add_player(p,plan_key); st.rerun()
            with st.expander("＋ Cadastrar atleta manualmente", expanded=False):
                st.caption("Cadastro próprio para planejamento. Sem estatísticas verificadas, a qualidade fica como não avaliada.")
                with st.form("scout_manual_create_form"):
                    ca, cb, cc = st.columns(3)
                    custom_name = ca.text_input("Nome do jogador")
                    custom_role = cb.selectbox("Posição natural", list(E.ROLE_LABELS), format_func=_role)
                    custom_age = cc.number_input("Idade", 15, 45, 22)
                    cd, ce, cf = st.columns(3)
                    custom_club = cd.text_input("Clube atual", "Sem clube informado")
                    custom_nation = ce.text_input("Nacionalidade")
                    custom_value = cf.number_input("Valor de referência (€)", min_value=0, value=0, step=100000)
                    custom_rating = st.number_input("Nota manual de qualidade (0 = sem nota)", min_value=0, max_value=100, value=0)
                    custom_obs = st.text_input("Observação de scout")
                    submitted = st.form_submit_button("Salvar jogador e adicionar ao plano", type="primary")
                if submitted:
                    if not custom_name.strip():
                        st.error("Informe o nome do jogador.")
                    else:
                        from src.data_lake.ids import player_core
                        from src.squad.formations import ROLE_PT
                        funcao = E.ROLE_LABELS.get(custom_role, custom_role)
                        birth_year = date.today().year - int(custom_age)
                        observation = (custom_obs + " · " if custom_obs else "") + "Idade declarada; data de nascimento aproximada para cadastro."
                        D.add_player({"nome": custom_name.strip(), "clube": custom_club.strip(),
                            "posicao": custom_role, "funcao": funcao, "nascimento": f"{birth_year}-07-01",
                            "valor_mercado_eur": float(custom_value) if custom_value else None,
                            "nota_manual": float(custom_rating) if custom_rating else None, "observacao": observation})
                        custom = {"nome": custom_name.strip(), "clube": custom_club.strip(), "papel": custom_role,
                            "papel_alvo": custom_role, "papel_alvo_label": _role(custom_role), "idade": int(custom_age),
                            "nacionalidade": custom_nation, "valor_mercado_eur": float(custom_value) if custom_value else None,
                            "qualidade": float(custom_rating) if custom_rating else None, "confianca_pct": 0,
                            "_core": player_core(custom_name), "historico_temporadas": "[]", "ultimos_jogos": "[]",
                            "motivo_principal": "Cadastro manual; não há estatísticas verificadas associadas.",
                            "realismo": E.transfer_realism({"valor_mercado_eur": custom_value or None,
                                "nacionalidade": custom_nation, "idade": custom_age}, financial, country, competition,
                                season=next_season),
                            "compatibilidade": {"score": 50, "label": "sem histórico estatístico", "confianca": "baixa"},
                            "sinergia": E.chemistry({"papel": custom_role}, roster)}
                        _add_player(custom, plan_key)
                        try:
                            from src.ui.pages.squad import _squad
                            _squad.clear()
                        except Exception:
                            pass
                        st.rerun()

    with tabs[3]:
        if tabs[3].open is not False:          # rodada 21: só a aba aberta é montada
            st.markdown("#### Joias subvalorizadas e potencial")
            # rodada 11: só jovens que ESTE clube consegue contratar (preço dentro do alcance, nacionalidade viável e clube
            # de origem de porte igual ou menor). Craques de elite (Yamal, Karl…) não são "joia subvalorizada" para o Cruzeiro.
            budget = float(financial.get("orcamento_proxy_eur") or 0) or None
            own_value = float(financial.get("valor_elenco_eur") or 0) or None
            # rodada 20: capacidade = maior compra dos últimos 5 anos ou topo da faixa estimada; padrão = 75% dela
            fx = financial.get("faixa_proxy_eur") or [None, None]
            capacity = max([x for x in (financial.get("maior_taxa_5_anos_eur"), fx[1], (budget or 0) * 1.5) if x] or [8e6])
            default_cap = round(max(capacity * .75, 2e6) / 1e6, 1)
            g1, g2 = st.columns([2, 1])
            cap_m = g1.slider("Valor máximo das joias (€ mi)", 0.5, float(max(60.0, round(capacity / 1e6 * 2, 0))),
                              float(default_cap), 0.5, key=f"scout_gem_cap_{_slug(team)}",
                              help=f"Capacidade estimada do clube: {_money(capacity)} (maior compra recente / faixa de "
                                   "investimento). O padrão fica em 75% dela; aumente para incluir nomes mais conhecidos.")
            keep_unknown = g2.toggle("Incluir quem não tem valor publicado", value=True, key="scout_gem_unknown",
                                     help="Série B/C e ligas sem valor no Transfermarkt — muitas vezes são as melhores pechinchas.")
            cap = cap_m * 1e6
            st.caption(f"Até 23 anos, com produção observada, valor de mercado até {_money(cap)} (capacidade estimada do "
                       f"clube: {_money(capacity)}), nacionalidade comum na liga e clube de origem de porte igual ou menor. "
                       "Teto = qualidade atual + crescimento esperado pela idade e nível — projeção, não certeza.")
            gems=_not_ours(pool.copy(), team, version, roster)
            if not gems.empty and "potencial_teto" in gems:
                ages=np.floor(pd.to_numeric(gems["idade"],errors="coerce"))
                mv=pd.to_numeric(gems["valor_mercado_eur"],errors="coerce")
                nm=financial.get("nat_market") or {}
                affs=gems["nacionalidade"].map(lambda n: (nm.get(E._first_nat(n)) or (50,""))[0])
                cv=pd.to_numeric(gems.get("clube_valor_total_eur",pd.Series(np.nan,index=gems.index)),errors="coerce")
                ok=(ages.le(23) & pd.to_numeric(gems["potencial_teto"],errors="coerce").notna()
                    & ((mv.isna() & keep_unknown) | mv.le(cap))
                    & (affs >= 45) & (cv.isna() | (own_value is None) | (cv <= (own_value or 0) * 1.5)))
                gems=gems[ok].assign(_aff=affs[ok])
                gems=gems.assign(_rank=pd.to_numeric(gems["potencial_teto"],errors="coerce")*.6
                                 + pd.to_numeric(gems["qualidade"],errors="coerce").fillna(40)*.25 + gems["_aff"]*.15)
                gems=gems.sort_values(["_rank","confianca_pct"],ascending=False).head(30)
            if gems.empty:
                empty_state("Nenhuma joia com amostra mínima", "Só aparecem jovens com dados estatísticos suficientes.", "💎")
            else:
                table=gems.rename(columns={"nome":"Jogador","papel":"Posição","idade":"Idade","clube":"Clube",
                    "nacionalidade":"Nacionalidade","qualidade":"Overall hoje","potencial_teto":"Potencial",
                    "confianca_pct":"Confiança (%)","_aff":"Adaptação (%)",
                    "projecao_valorizacao_24m_pct":"Valorização possível 24m (%)","valor_mercado_eur":"Valor (€)"})
                keep=[x for x in ("Jogador","Posição","Idade","Clube","Nacionalidade","Overall hoje","Potencial",
                                  "Confiança (%)","Adaptação (%)","Valorização possível 24m (%)","Valor (€)") if x in table]
                table=table[keep].copy()
                if "Posição" in table: table["Posição"]=table["Posição"].map(E.ROLE_LABELS).fillna(table["Posição"])
                if "Valor (€)" in table: table["Valor (€)"]=table["Valor (€)"].map(_money)
                styled_dataframe(table,use_container_width=True,hide_index=True)
                name=st.selectbox("Escolher joia",gems["nome"].astype(str).tolist(),key="scout_gem_pick")
                if st.button("Adicionar joia ao plano",key="scout_gem_add"):
                    p=gems[gems["nome"].astype(str)==name].iloc[0].to_dict()
                    p["papel_alvo"]=p.get("papel"); p["papel_alvo_label"]=_role(p.get("papel"))
                    p["realismo"]=E.transfer_realism(p,financial,country,competition,season=next_season)
                    p["compatibilidade"]=E.tactical_compatibility(p,diagnosis.get("estilo") or {})
                    p["sinergia"]=E.chemistry(p,roster)
                    _add_player(p,plan_key); st.rerun()
    with tabs[4]:
        if tabs[4].open is not False:          # rodada 21: só a aba aberta é montada
            st.markdown("#### Janela de transferências")
            if not roster.empty:
                st.caption("Marque quem fica, sai ou deve ser emprestado — por setor. Vendas usam deságio estimado.")
                _manual_loan_form(team, roster)
                rows=_window_cards(roster, decisions, _loans(team, version))
                if rows: comparison_table(pd.DataFrame(rows))
            plan=st.session_state[plan_key]
            if plan:
                comparison_table(pd.DataFrame([{"Entrada":p.get("nome"),"Posição":p.get("papel_alvo_label"),
                    "Qualidade":p.get("qualidade"),"Realismo":(p.get("realismo") or {}).get("score"),
                    "Taxa estimada":_money((p.get("realismo") or {}).get("taxa_estimada_eur"))} for p in plan]))
                remove=st.selectbox("Remover do plano",["—"]+[p.get("nome") for p in plan],key="scout_remove")
                if remove!="—" and st.button("Remover jogador",key="scout_remove_button"):
                    st.session_state[plan_key]=[p for p in plan if p.get("nome")!=remove]; st.rerun()
            else:
                st.caption("Adicione um atleta pela IA, pelos filtros ou pelo radar de joias.")
            formations=list(E.FORMATIONS)
            default_form=formations.index("4-3-3") if "4-3-3" in formations else 0
            formation=st.selectbox("Formação",formations,index=default_form,key="scout_formation")
            entry=st.selectbox("Testar contratação",["Nenhuma"]+[p.get("nome") for p in plan],key="scout_entry")
            outgoing=st.selectbox("Simular saída / venda",["Nenhum"]+(roster["nome"].astype(str).tolist() if not roster.empty else []),
                                  key="scout_outgoing")
            if st.session_state.get("scout_plan_final") or plan:
                from src.ui.plan_board import render_board

                with st.container(border=True):
                    render_board(team, roster, plan, decisions, formation)
            if st.button("⚽ Simular antes vs. depois",key="scout_sim",type="primary"):
                player=next((p for p in plan if p.get("nome")==entry),None) if entry!="Nenhuma" else None
                simulation=E.build_simulation(roster,player,outgoing if outgoing!="Nenhum" else None,formation)
                st.session_state["scout_sim_"+_slug(team)]=simulation
            simulation=st.session_state.get("scout_sim_"+_slug(team))
            if simulation:
                a,b=st.columns(2)
                with a:
                    st.markdown("**XI atual**")
                    st.plotly_chart(_pitch_figure(simulation["xi_antes"], "Antes"), use_container_width=True,
                                    config={"displayModeBar": False})
                    comparison_table(pd.DataFrame([{"Vaga":p.get("papel_pt"),"Jogador":p.get("jogador"),"Nota":p.get("nota")}
                                                   for p in simulation["xi_antes"]]))
                with b:
                    st.markdown("**XI simulado**")
                    st.plotly_chart(_pitch_figure(simulation["xi_depois"], "Depois"), use_container_width=True,
                                    config={"displayModeBar": False})
                    comparison_table(pd.DataFrame([{"Vaga":p.get("papel_pt"),"Jogador":p.get("jogador"),"Nota":p.get("nota")}
                                                   for p in simulation["xi_depois"]]))
                if simulation.get("deltas"):
                    _sim_radar(simulation["deltas"], team)
                    styled_dataframe(pd.DataFrame(simulation["deltas"]).rename(columns={"indicador":"Indicador","antes":"Antes",
                        "depois":"Depois","variacao":"Variação","variacao_pct":"Variação (%)"}),use_container_width=True,hide_index=True)
                st.caption(simulation.get("limite",""))
            incoming=sum(float((p.get("realismo") or {}).get("taxa_estimada_eur") or 0) for p in plan)
            sales=0.0
            if not roster.empty:
                for name,decision in decisions.items():
                    if decision in ("Vender","Comprar em definitivo"):
                        row=roster[roster["nome"]==name]
                        value=pd.to_numeric(row["valor_mercado_eur"],errors="coerce").iloc[0] if not row.empty else np.nan
                        if pd.notna(value):
                            if decision=="Vender": sales+=float(value)*.60
                            else: incoming+=float(value)*.90          # compra do emprestado: ~90% do valor (estimativa)
            st.metric("Saldo estimado da janela",_money(sales-incoming),
                      help="Vendas estimadas a 60% do valor de referência menos taxas estimadas.")
            st.caption("Sem salários e orçamento oficial: as faixas são proxies e podem divergir da negociação real.")
            decisions_clean={k:v for k,v in decisions.items() if v!="Fica"}
            markdown=E.export_markdown(team,financial,decisions_clean,plan,simulation)
            a,b=st.columns(2)
            a.download_button("⇩ Dossiê Markdown",markdown,file_name=f"scout_{_slug(team)}.md",
                              mime="text/markdown",use_container_width=True)
            # rodada 11: dossiê visual — campinho com o XI planejado, um cartão por chegada (porquê + viabilidade), saídas
            from src.scout import dossier_pdf as DP

            xi_plan=(simulation or {}).get("xi_depois") or (simulation or {}).get("xi_antes") or []
            if not xi_plan and not roster.empty:
                try:
                    xi_plan=E.build_simulation(roster,None,None,formation)["xi_antes"]
                except Exception:
                    xi_plan=[]
            pdf=DP.build(team, formation, xi_plan, plan, decisions, sales-incoming, next_season) or _pdf_bytes(markdown)
            if pdf:
                b.download_button("⇩ Dossiê PDF (campinho + decisões)",pdf,file_name=f"scout_{_slug(team)}.pdf",
                                  mime="application/pdf",use_container_width=True)
            else:
                b.caption("Para PDF, instale a dependência reportlab.")
            if st.button("💾 Salvar planejamento",key="scout_save"):
                plan_id=E.save_plan(service.db,team,f"Janela {date.today().year}",{
                    "decisoes":decisions_clean,"contratacoes":plan,"simulacao":simulation,
                    "saldo_estimado_eur":sales-incoming,"financeiro":financial})
                st.success(f"Planejamento salvo no banco local · ID {plan_id}.")


