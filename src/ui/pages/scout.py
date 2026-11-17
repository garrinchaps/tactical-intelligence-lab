"""Sala de Scout & Planejamento — mercado, elenco, diagnóstico e simulação."""

from __future__ import annotations

import io
import json
import re
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from src.scout import engine as E
from src.squad import data as D
from src.ui.components import comparison_table, empty_state, page_header
from src.ui.nav import back_button, open_view, param


@st.cache_data(show_spinner=False, ttl=1200, max_entries=3)
def _market_data(version: str):
    from src.ui.context import get_service

    players, clubs = D.table("tm_jogadores"), D.table("tm_clubes")
    if players.empty:
        return {"universe": pd.DataFrame(), "clubs": clubs, "status": "Base de mercado indisponível."}
    last = pd.to_numeric(players.get("ultima_temporada"), errors="coerce")
    if last.notna().any():
        players = players[(last >= last.max() - 2) |
                          players.get("clube_id", pd.Series("", index=players.index)).astype(str).str.strip().ne("")]
    history = E.load_player_history(get_service().db, days=1825)
    universe = E.add_quality_scores(E.build_market_universe(players, history))
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


def _merge_roster(roster, universe):
    if roster is None or roster.empty:
        return pd.DataFrame()
    from src.data_lake.ids import player_core

    r = roster.copy()
    r["_core"] = r["nome"].map(player_core)
    if universe is not None and not universe.empty:
        lookup = universe.drop_duplicates("_core").set_index("_core")
        cols = [x for x in ("qualidade", "confianca_pct", "rating_media", "rating_12m", "minutos_12m",
                            "jogos_12m", "nacionalidade", "valor_mercado_eur", "fim_contrato",
                            "goals_p90", "assists_p90", "xg_p90", "xa_p90", "chances_created_p90",
                            "def_actions_p90", "sprints_p90", "historico_temporadas", "ultimos_jogos")
                if x in lookup]
        for col in cols:
            mapped = r["_core"].map(lookup[col])
            r[col] = r[col].combine_first(mapped) if col in r else mapped
    if "qualidade" not in r:
        r["qualidade"] = pd.to_numeric(r.get("nota"), errors="coerce")
    else:
        r["qualidade"] = pd.to_numeric(r["qualidade"], errors="coerce").combine_first(
            pd.to_numeric(r.get("nota"), errors="coerce"))
    return r


@st.cache_data(show_spinner=False, ttl=900, max_entries=16)
def _diagnosis(team, version, roster_records):
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    club = E.market_club(D.table("tm_clubes"), team)
    transfers = D.table("tm_transferencias", None, "para_clube_id", [club["transfermarkt_id"]]) \
        if club and club.get("transfermarkt_id") is not None else pd.DataFrame()
    return E.diagnose_club(get_service().db, same_team_names(team), pd.DataFrame(roster_records),
                           D.table("tm_clubes"), transfers)


def _club_squad(team, version, universe):
    try:
        from src.ui.pages.squad import _squad
        data = _squad(team, version)
        return {**data, "squad": _merge_roster(data.get("squad"), universe)}
    except Exception:
        from src.ui.context import get_service
        from src.ui.pages.clubs import same_team_names
        club = E.market_club(D.table("tm_clubes"), team)
        roster = E.current_roster(get_service().db, club, same_team_names(team), D.table("tm_jogadores"), universe)
        return {"squad": _merge_roster(roster, universe), "club": club, "fonte": "Transfermarkt + escalações"}


def _dossier(player, roster):
    def unpack(v):
        try:
            return json.loads(v) if isinstance(v, str) else (v or [])
        except Exception:
            return []
    hist, recent = unpack(player.get("historico_temporadas")), unpack(player.get("ultimos_jogos"))
    metrics = [
        ("Minutos 12m", player.get("minutos_12m", player.get("minutos"))),
        ("Jogos 12m", player.get("jogos_12m", player.get("jogos"))),
        ("Nota média 12m", player.get("rating_12m", player.get("rating_media"))),
        ("Gols/90", player.get("goals_p90")), ("Assistências/90", player.get("assists_p90")),
        ("xG/90", player.get("xg_p90")), ("xA/90", player.get("xa_p90")),
        ("Criação/90", player.get("chances_created_p90")), ("Ações defensivas/90", player.get("def_actions_p90")),
    ]
    comparison_table(pd.DataFrame([{"Indicador": k, "Valor": "—" if v is None or pd.isna(v) else round(float(v), 3)}
                                   for k, v in metrics]))
    if hist:
        d = pd.DataFrame(hist)
        cols = [c for c in ("temporada", "jogos", "minutos", "rating_media", "goals", "assists", "xg", "xa") if c in d]
        comparison_table(d[cols].rename(columns={"temporada":"Temporada","jogos":"Jogos","minutos":"Minutos",
            "rating_media":"Nota média","goals":"Gols","assists":"Assistências","xg":"xG","xa":"xA"}))
    if recent:
        d = pd.DataFrame(recent)
        cols = [c for c in ("match_date","team_name","competition_name","minutes","rating") if c in d]
        comparison_table(d[cols].rename(columns={"match_date":"Data","team_name":"Clube",
            "competition_name":"Competição","minutes":"Minutos","rating":"Nota"}).head(15))
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


def _add_player(player, plan_key):
    current = st.session_state.setdefault(plan_key, [])
    if not any(x.get("_core") == player.get("_core") for x in current):
        current.append(json.loads(json.dumps(player, default=str)))
    st.success(f"{player.get('nome')} adicionado ao plano.")


def _player_card(player, roster, team, idx, plan_key, rejected_key):
    name = str(player.get("nome") or "Jogador")
    r = player.get("realismo") or {}
    s = int(r.get("score") or 0)
    tag = "viable" if s >= 76 else "loan" if s >= 56 or r.get("oportunidade_emprestimo") else "dream"
    quality = player.get("qualidade")
    quality = "sem nota" if quality is None or pd.isna(quality) else f"{float(quality):.0f}/100"
    position = player.get("papel_alvo_label") or _role(player.get("papel"))
    st.markdown(
        f'<div class="scout-player"><div class="scout-avatar">{_initials(name)}</div><div class="scout-main">'
        f'<div class="scout-name">{name}</div><div class="scout-sub">{position} · {player.get("clube") or "Clube não identificado"} · '
        f'{player.get("idade") if pd.notna(player.get("idade")) else "idade n/d"} anos · {player.get("nacionalidade") or "nacionalidade n/d"}</div>'
        f'<div class="scout-tags"><span class="scout-tag {tag}">{r.get("rotulo","Sem estimativa")} · {s}%</span>'
        f'<span class="scout-tag neutral">Compatibilidade {(player.get("compatibilidade") or {}).get("score","—")}%</span>'
        f'<span class="scout-tag neutral">Qualidade {quality}</span></div></div>'
        f'<div class="scout-value">{_money(player.get("valor_mercado_eur"))}<small>valor de referência</small></div></div>',
        unsafe_allow_html=True)
    a, b = st.columns([1.1, 1.1])
    if a.button("＋ Adicionar ao plano", key=f"scout_add_{_slug(name)}_{idx}", type="primary", use_container_width=True):
        _add_player(player, plan_key)
        st.rerun()
    if b.button("Abrir perfil ↗", key=f"scout_open_{_slug(name)}_{idx}", use_container_width=True):
        open_view("jogador", name=name, core=player.get("_core"))
    with st.expander("Ver dossiê completo da IA"):
        _dossier(player, roster)
    with st.expander("Descartar e recalcular"):
        reason = st.selectbox("Motivo", ["Muito caro","Muito velho","Perfil físico inadequado",
            "Limite de estrangeiros","Quero outra característica","Não é prioridade","Outro motivo"],
            key=f"scout_reason_{_slug(name)}_{idx}")
        if st.button("Descartar este alvo", key=f"scout_reject_{_slug(name)}_{idx}"):
            from src.ui.context import get_service
            E.record_rejection(get_service().db, team, name, str(player.get("papel_alvo") or ""),
                               reason, float(player.get("score_scout") or 0))
            rejected = st.session_state.setdefault(rejected_key, [])
            if name not in rejected:
                rejected.append(name)
            st.rerun()


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
    version = service.db.stable_version()
    prefill = str(param("club", "") or st.session_state.get("scout_selected_club", ""))
    try:
        with st.spinner("Carregando mercado e histórico estatístico disponível..."):
            data = _market_data(version)
    except Exception as exc:
        st.error(f"Erro ao carregar os dados de mercado: {exc}")
        return
    universe, clubs = data["universe"], data["clubs"]
    q = st.text_input("Pesquisar clube", value=prefill, placeholder="Ex.: Cruzeiro, Flamengo, Como 1907")
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
    default = prefill if prefill in options else options[0]
    team = st.selectbox("Clube a planejar", options, index=options.index(default), key="scout_club_choice")
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
    financial["estilo"] = diagnosis.get("estilo") or {}
    financial["club_aliases"] = aliases
    foreign_count = 0
    if not roster.empty and country and "nacionalidade" in roster:
        foreign_count = int(sum(1 for n in roster["nacionalidade"].dropna().astype(str)
                                if E.is_foreign_player(n, country) is True))
    financial["estrangeiros_atual"] = foreign_count

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
        needs = [{"papel": r, "urgencia": 55, "motivo": "profundidade posicional reduzida"}
                 for r in ("GK","CB","LB","RB","DM","CM","AM","LW","RW","ST") if int(counts.get(r, 0)) < 2]
    with st.spinner("Classificando qualidade, realismo, encaixe e sinergia..."):
        ranked = E.recommend(pool, needs, financial, country, competition, roster=roster,
                             rejected=st.session_state[rejected_key], season=next_season) \
            if not pool.empty else pd.DataFrame()

    tabs = st.tabs(["Diagnóstico", "IA · Top 5", "Busca manual", "Joias U23", "Planejamento"])
    with tabs[0]:
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
        st.markdown("#### Identidade tática e treinador")
        style = diagnosis.get("estilo") or {}
        st.write(" · ".join(style.get("tracos") or ["Amostra insuficiente"]))
        st.caption(style.get("fonte","") + " · " + style.get("contexto_tecnico","") + " · " + style.get("limite",""))
        if style.get("tracos_tecnico"):
            st.write("**Padrões anteriores do treinador:** " + " · ".join(style["tracos_tecnico"]))
            st.caption(f"{style.get('amostra_tecnico',0)} jogos anteriores · "
                       + ", ".join(style.get("clubes_anteriores_tecnico",[])))
        coach = diagnosis.get("treinador") or {}
        st.write(f"**Técnico identificado:** {coach.get('nome') or 'não identificado'} · "
                 f"{coach.get('jogos',0)} jogos observados no clube")
        st.markdown("#### Médias do clube nas partidas disponíveis")
        labels = {"xg":"xG","shots_total":"Finalizações","shots_on_target":"No alvo","possession_pct":"Posse (%)",
                  "passes_total":"Passes","crosses_total":"Cruzamentos","interceptions":"Interceptações","tackles_won":"Desarmes certos"}
        rows = []
        for side, source in (("A favor", diagnosis.get("medias_pro") or {}),
                             ("Contra", diagnosis.get("medias_contra") or {})):
            for key, value in source.items():
                if key in labels:
                    rows.append({"Lado": side, "Indicador": labels[key], "Média/jogo": value,
                                 "Referência": (diagnosis.get("referencia") or {}).get(key)})
        if rows:
            comparison_table(pd.DataFrame(rows))
        if not roster.empty:
            st.markdown("#### Elenco e notas")
            show = roster.copy()
            show["Posição"] = show["papel"].map(E.ROLE_LABELS).fillna("—")
            cols = [x for x in ("nome","Posição","idade","qualidade","confianca_pct","valor_mercado_eur",
                                "minutos_12m","rating_12m") if x in show]
            display = show[cols].rename(columns={"nome":"Jogador","idade":"Idade","qualidade":"Qualidade",
                "confianca_pct":"Confiança (%)","valor_mercado_eur":"Valor de mercado","minutos_12m":"Minutos 12m",
                "rating_12m":"Nota média 12m"})
            if "Valor de mercado" in display:
                display["Valor de mercado"] = display["Valor de mercado"].map(_money)
            st.dataframe(display.sort_values("Qualidade", ascending=False, na_position="last"),
                         use_container_width=True, hide_index=True)
            selected = st.selectbox("Abrir jogador do elenco", ["—"] + roster["nome"].astype(str).tolist(),
                                    key="scout_roster_select")
            if selected != "—" and st.button("Abrir perfil ↗", key="scout_roster_link"):
                open_view("jogador", name=selected)
        else:
            st.warning("O elenco atual não pôde ser confirmado. As sugestões serão limitadas à cobertura do catálogo.")
        if financial.get("faixa_proxy_eur"):
            lo, hi = financial["faixa_proxy_eur"]
            st.markdown("#### Capacidade financeira estimada")
            st.write(f"Faixa proxy: **{_money(lo)} a {_money(hi)}**.")
            st.caption(financial["natureza"] + f" · {financial.get('transferencias_pagas_amostra',0)} taxas pagas na amostra.")
        else:
            st.info("Não há histórico financeiro suficiente para estimar capacidade de investimento.")
    with tabs[1]:
        st.markdown("#### Cinco nomes priorizados")
        st.caption("Qualidade estatística por função + urgência + realismo + compatibilidade + sinergia. Abra cada dossiê para ver as evidências.")
        if ranked.empty:
            empty_state("Ainda não há candidatos suficientes",
                "Sincronize jogadores/valores do Transfermarkt e estatísticas individuais. A busca manual continua disponível.", "🎯")
        else:
            for idx, row in ranked.head(5).iterrows():
                _player_card(row.to_dict(), roster, team, int(idx), plan_key, rejected_key)
            st.markdown("#### Três melhores por posição")
            roles = list(dict.fromkeys(ranked["papel_alvo"].tolist()))
            role = st.selectbox("Posição", roles, format_func=_role, key="scout_top3_role")
            fa, fb, fc = st.columns(3)
            age_band = fa.slider("Faixa etária", 16, 40, (18, 30), key="scout_ai_age")
            quality_floor = fb.slider("Qualidade mínima", 0, 100, 55, key="scout_ai_quality")
            maximum_fee = fc.number_input("Valor máximo (€ mi)", 0.0, 500.0, 30.0, key="scout_ai_max_value")
            filt3 = ranked[ranked["papel_alvo"] == role].copy()
            filt3 = filt3[pd.to_numeric(filt3["idade"], errors="coerce").between(*age_band)]
            filt3 = filt3[pd.to_numeric(filt3["qualidade"], errors="coerce").fillna(0) >= quality_floor]
            filt3 = filt3[pd.to_numeric(filt3["valor_mercado_eur"], errors="coerce").fillna(0) <= maximum_fee * 1e6]
            nations = ["Todas"] + sorted(filt3["nacionalidade"].dropna().astype(str).unique().tolist())
            nation = st.selectbox("Nacionalidade desejada", nations, key="scout_ai_nation")
            if nation != "Todas":
                filt3 = filt3[filt3["nacionalidade"].astype(str) == nation]
            for idx, row in filt3.head(3).iterrows():
                _player_card(row.to_dict(), roster, team, int(idx)+100, plan_key, rejected_key)
            if filt3.empty:
                st.info("Nenhum atleta atende aos filtros atuais. Amplie a faixa ou use a busca manual.")
    with tabs[2]:
        st.markdown("#### Filtros de jogador")
        if pool.empty:
            empty_state("Universo de jogadores indisponível", "Sincronize o catálogo Transfermarkt.", "👥")
        else:
            c1,c2,c3,c4 = st.columns(4)
            roles = ["Todas"] + sorted(pool["papel"].dropna().unique().tolist())
            rf = c1.selectbox("Posição", roles, format_func=lambda x: "Todas" if x=="Todas" else _role(x))
            amin = c2.number_input("Idade mínima", 15, 40, 18)
            amax = c3.number_input("Idade máxima", 16, 50, 35)
            qmin = c4.slider("Qualidade mínima", 0, 100, 0)
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
            filt = pool.copy()
            if rf!="Todas": filt=filt[filt["papel"]==rf]
            filt=filt[pd.to_numeric(filt["idade"],errors="coerce").between(amin,amax)]
            filt=filt[pd.to_numeric(filt["qualidade"],errors="coerce").fillna(0)>=qmin]
            if nat!="Todas": filt=filt[filt["nacionalidade"].astype(str)==nat]
            if league_filter!="Todas" and "clube_liga" in filt:
                filt=filt[filt["clube_liga"].astype(str)==league_filter]
            if seller!="Todos": filt=filt[filt["clube"].astype(str)==seller]
            values=pd.to_numeric(filt["valor_mercado_eur"],errors="coerce").fillna(0)
            filt=filt[values.between(vmin*1e6,vmax*1e6)]
            filt=filt.sort_values("qualidade",ascending=False,na_position="last")
            st.caption(f"{len(filt):,} atletas dentro dos filtros.".replace(",","."))
            cols = [x for x in ("nome","papel","idade","clube","nacionalidade","valor_mercado_eur",
                                "qualidade","confianca_pct","minutos_12m","rating_12m") if x in filt]
            display=filt[cols].rename(columns={"nome":"Jogador","papel":"Posição","idade":"Idade","clube":"Clube",
                "nacionalidade":"Nacionalidade","valor_mercado_eur":"Valor (€)","qualidade":"Qualidade",
                "confianca_pct":"Confiança (%)","minutos_12m":"Minutos 12m","rating_12m":"Nota 12m"}).head(100)
            if "Valor (€)" in display: display["Valor (€)"]=display["Valor (€)"].map(_money)
            st.dataframe(display,use_container_width=True,hide_index=True)
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
    with tabs[3]:
        st.markdown("#### Joias subvalorizadas e potencial")
        st.caption("Triagem de atletas até 23 anos, com qualidade baseada em dados observados e valor comparado aos pares. O upside é heurístico, não previsão de preço.")
        gems=pool.copy()
        if not gems.empty and "potencial_revenda" in gems:
            gems=gems[pd.to_numeric(gems["idade"],errors="coerce").le(23) &
                      pd.to_numeric(gems["potencial_revenda"],errors="coerce").notna()]
            gems=gems.sort_values(["potencial_revenda","confianca_pct"],ascending=False).head(30)
        if gems.empty:
            empty_state("Nenhuma joia com amostra mínima", "Só aparecem jovens com dados estatísticos suficientes.", "💎")
        else:
            table=gems.rename(columns={"nome":"Jogador","papel":"Posição","idade":"Idade","clube":"Clube",
                "qualidade":"Qualidade","confianca_pct":"Confiança (%)","potencial_revenda":"Potencial /100",
                "projecao_valorizacao_24m_pct":"Upside estimado 24m (%)","valor_mercado_eur":"Valor (€)"})
            keep=[x for x in ("Jogador","Posição","Idade","Clube","Qualidade","Confiança (%)",
                              "Potencial /100","Upside estimado 24m (%)","Valor (€)") if x in table]
            table=table[keep].copy()
            if "Posição" in table: table["Posição"]=table["Posição"].map(E.ROLE_LABELS).fillna(table["Posição"])
            if "Valor (€)" in table: table["Valor (€)"]=table["Valor (€)"].map(_money)
            st.dataframe(table,use_container_width=True,hide_index=True)
            name=st.selectbox("Escolher joia",gems["nome"].astype(str).tolist(),key="scout_gem_pick")
            if st.button("Adicionar joia ao plano",key="scout_gem_add"):
                p=gems[gems["nome"].astype(str)==name].iloc[0].to_dict()
                p["papel_alvo"]=p.get("papel"); p["papel_alvo_label"]=_role(p.get("papel"))
                p["realismo"]=E.transfer_realism(p,financial,country,competition,season=next_season)
                p["compatibilidade"]=E.tactical_compatibility(p,diagnosis.get("estilo") or {})
                p["sinergia"]=E.chemistry(p,roster)
                _add_player(p,plan_key); st.rerun()
    with tabs[4]:
        st.markdown("#### Janela de transferências")
        if not roster.empty:
            st.caption("Marque quem fica, sai ou deve ser emprestado. Vendas usam deságio estimado.")
            rows=[]
            for p in roster.sort_values("qualidade",ascending=False,na_position="last").to_dict("records"):
                name=str(p["nome"])
                choice=st.selectbox(f"{name} · {_role(p.get('papel'))}",["Fica","Vender","Emprestar"],
                    index=["Fica","Vender","Emprestar"].index(decisions.get(name,"Fica")),
                    key=f"scout_dec_{_slug(name)}")
                decisions[name]=choice
                if choice!="Fica":
                    rows.append({"Jogador":name,"Decisão":choice,"Valor referência":_money(p.get("valor_mercado_eur"))})
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
        if st.button("⚽ Simular antes vs. depois",key="scout_sim",type="primary"):
            player=next((p for p in plan if p.get("nome")==entry),None) if entry!="Nenhuma" else None
            simulation=E.build_simulation(roster,player,outgoing if outgoing!="Nenhum" else None,formation)
            st.session_state["scout_sim_"+_slug(team)]=simulation
        simulation=st.session_state.get("scout_sim_"+_slug(team))
        if simulation:
            a,b=st.columns(2)
            with a:
                st.markdown("**XI atual**")
                comparison_table(pd.DataFrame([{"Vaga":p.get("papel_pt"),"Jogador":p.get("jogador"),"Nota":p.get("nota")}
                                               for p in simulation["xi_antes"]]))
            with b:
                st.markdown("**XI depois**")
                comparison_table(pd.DataFrame([{"Vaga":p.get("papel_pt"),"Jogador":p.get("jogador"),"Nota":p.get("nota")}
                                               for p in simulation["xi_depois"]]))
            if simulation.get("deltas"):
                st.dataframe(pd.DataFrame(simulation["deltas"]),use_container_width=True,hide_index=True)
                chart=pd.DataFrame(simulation["deltas"]).set_index("indicador")[["antes","depois"]]
                st.bar_chart(chart)
            st.caption(simulation.get("limite",""))
        incoming=sum(float((p.get("realismo") or {}).get("taxa_estimada_eur") or 0) for p in plan)
        sales=0.0
        if not roster.empty:
            for name,decision in decisions.items():
                if decision=="Vender":
                    row=roster[roster["nome"]==name]
                    value=pd.to_numeric(row["valor_mercado_eur"],errors="coerce").iloc[0] if not row.empty else np.nan
                    if pd.notna(value): sales+=float(value)*.60
        st.metric("Saldo estimado da janela",_money(sales-incoming),
                  help="Vendas estimadas a 60% do valor de referência menos taxas estimadas.")
        st.caption("Sem salários e orçamento oficial: as faixas são proxies e podem divergir da negociação real.")
        decisions_clean={k:v for k,v in decisions.items() if v!="Fica"}
        markdown=E.export_markdown(team,financial,decisions_clean,plan,simulation)
        a,b=st.columns(2)
        a.download_button("⇩ Dossiê Markdown",markdown,file_name=f"scout_{_slug(team)}.md",
                          mime="text/markdown",use_container_width=True)
        pdf=_pdf_bytes(markdown)
        if pdf:
            b.download_button("⇩ Relatório PDF",pdf,file_name=f"scout_{_slug(team)}.pdf",
                              mime="application/pdf",use_container_width=True)
        else:
            b.caption("Para PDF, instale a dependência reportlab.")
        if st.button("💾 Salvar planejamento",key="scout_save"):
            plan_id=E.save_plan(service.db,team,f"Janela {date.today().year}",{
                "decisoes":decisions_clean,"contratacoes":plan,"simulacao":simulation,
                "saldo_estimado_eur":sales-incoming,"financeiro":financial})
            st.success(f"Planejamento salvo no banco local · ID {plan_id}.")


