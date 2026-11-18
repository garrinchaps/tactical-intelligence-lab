"""
🧩 Padrões e histórico (rodada 5) — na página do jogo.

Com lances: bola parada, impacto das substituições e comportamento conforme o placar (desta partida).
Com estatísticas (qualquer jogo da base): identidade habitual do time, problemas que se repetem, o que este jogo teve
de diferente do habitual e jogos taticamente parecidos.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from src.ui.components import comparison_table, empty_state, note


@st.cache_data(show_spinner=False, ttl=1800, max_entries=32)
def _history(team: str, match_id: int, version: str) -> Dict[str, Any]:
    from src.analytics import team_history as TH
    from src.ui.context import get_service
    from src.ui.pages.clubs import same_team_names

    db = get_service().db
    names = same_team_names(team)
    out: Dict[str, Any] = {}
    for k, fn in (("identidade", lambda: TH.identity(db, names)), ("vulneraveis", lambda: TH.vulnerabilities(db, names)),
                  ("habito", lambda: TH.vs_habit(db, names, match_id)), ("parecidos", lambda: TH.similar(db, names, match_id))):
        try:
            out[k] = fn()
        except Exception as exc:
            out[k] = {"erro": str(exc)}
    return out


def _card(txt: str, color: str = "#22D3EE") -> None:
    st.markdown(f'<div class="fm-card" style="border-left:4px solid {color};border-radius:14px;padding:.55rem .9rem;'
                f'margin-bottom:.45rem">{txt}</div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False, ttl=1800, max_entries=24)
def _reading(match_id: int, team: str, version: str, _meta, _box):
    from src.intelligence.lab_ai.router import match_reading
    from src.ui.context import get_service

    return match_reading(_meta, None, _box, team, get_service().db)


def _ai_reading(ctx, team: str) -> None:
    """Jogo só com estatísticas: a IA do laboratório lê o jogo por inteiro (forte, atenção, explorar, trocas, fases)."""
    from src.ui.context import get_service

    meta = {**(ctx.bundle.meta or {}), "match_id": ctx.match_id, "data_source": ctx.bundle.source}
    try:
        with st.spinner("A IA do laboratório está lendo o jogo…"):
            r = _reading(int(ctx.match_id), team, get_service().db.stable_version(), meta, ctx.bundle.boxscore)
    except Exception as exc:
        st.caption(f"A leitura da IA não pôde ser montada ({exc}).")
        return
    if not r.get("blocos") and not r.get("fases"):
        return
    st.markdown("---")
    st.markdown(f"### 🧠 Leitura da IA do laboratório — {team} neste jogo")
    st.caption("Feita só com as estatísticas do jogo e a régua de milhares de jogos da base; cada número vem da fonte.")
    if r.get("fases"):
        st.markdown("**Fases do jogo (momentum da FotMob, média por 15 min):** " + " · ".join(
            f"{f['bloco']} {f['leitura']} ({f['media']:+.0f})" for f in r["fases"]))
    cols = st.columns(2)
    for i, b in enumerate(r.get("blocos") or []):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"#### {b['titulo']}")
                st.markdown(b["markdown"], unsafe_allow_html=True)


def render(ctx, team: str) -> None:
    from src.ui.context import get_service

    meta = ctx.bundle.meta or {}
    other = next((t for t in (meta.get("home_team_name"), meta.get("away_team_name")) if t and t != team), "")
    st.markdown(f"### 🧩 {team}: padrões deste jogo e do histórico")
    h = _history(team, int(ctx.match_id), get_service().db.stable_version())
    a, b = st.columns(2)
    with a:
        st.markdown("#### 🧬 Identidade habitual")
        idn = h.get("identidade") or {}
        if idn.get("tracos"):
            st.caption(f"Últimos {idn['jogos']} jogos com estatísticas ({idn['periodo'][0]} a {idn['periodo'][1]}) · {idn['referencia']}.")
            for t_ in idn["tracos"]:
                _card(f"<b>{team} {t_['traco']}</b> — {t_['metrica']}: {t_['media']} (normal {t_['referencia']}, "
                      f"{t_['dif_pct']:+.0f}%), em {t_['frequencia_pct']}% dos {t_['jogos']} jogos")
        else:
            st.caption("Nenhum traço de estilo consistente (acima/abaixo do normal em ≥ 60% dos jogos) — ou jogos com "
                       "estatísticas insuficientes." + (f" Jogos encontrados: {idn.get('jogos', 0)}." if idn else ""))
    with b:
        st.markdown("#### 🩹 Problemas que se repetem")
        vu = h.get("vulneraveis") or {}
        for p in vu.get("padroes") or []:
            _card(f"<b>{team} {p['problema']}</b> — em {p['jogos_acima']} de {p['jogos']} jogos acima do P70 da competição "
                  f"(média contra {p['media_contra']}; P70 {p['p70_da_competicao']})", "#EF4444")
        for p in vu.get("sinais") or []:
            _card(f"⚠️ Sinal (ainda não padrão): {team} {p['problema']} — {p['jogos_acima']} de {p['jogos']} jogos", "#F59E0B")
        if not (vu.get("padroes") or vu.get("sinais")):
            st.caption("Nenhum problema defensivo aparece com frequência nos jogos com estatísticas — um jogo isolado não "
                       "vira padrão.")
        if vu.get("criterio"):
            st.caption(vu["criterio"])
    hb = h.get("habito") or {}
    if hb.get("diferencas"):
        st.markdown(f"#### 🔁 O que este jogo teve de diferente do habitual de {team}")
        comparison_table(pd.DataFrame(hb["diferencas"]).rename(columns={"metrica": "Indicador", "neste_jogo": "Neste jogo",
                                                                         "habitual": "Habitual", "z": "Desvios (z)"}))
        st.caption(f"Habitual = média dos {hb['jogos_historico']} jogos anteriores com estatísticas. Só aparece o que fugiu "
                   "mais de 1,3 desvio do normal dele.")
    ps = h.get("parecidos") or {}
    if ps.get("semelhantes"):
        st.markdown("#### 🔎 Jogos taticamente parecidos")
        for s_ in ps["semelhantes"]:
            _card(f"<b>{s_['jogo']}</b> · {s_['data']} · {s_['competicao']} — estilo de <b>{s_['time_comparado']}</b> "
                  f"(distância {s_['distancia']}). Coincide em: {', '.join(s_['coincide_em'])}. Difere em: {', '.join(s_['difere_em'])}.",
                  "#A78BFA")
        st.caption(ps.get("criterio", "") + f" · base: {ps.get('base', '')}.")
    if not ctx.has_events:
        _ai_reading(ctx, team)
        note("Bola parada, substituições e placar lance a lance", "Estas três leituras precisam dos lances do jogo "
             "(nível 🟢). Este jogo tem só estatísticas — acima está tudo o que a nossa IA tira delas.", "info")
        return
    from src.analytics import match_patterns as MP

    st.markdown("---")
    t1, t2, t3 = st.tabs(["🎯 Bola parada", "🔄 Substituições", "📈 Conforme o placar"])
    with t1:
        sp = MP.set_pieces(ctx.df, team)
        if sp.get("fatia_xg_bola_parada_pct") is not None:
            st.caption(f"{sp['fatia_xg_bola_parada_pct']}% do xG de {team} veio de bola parada · segundas bolas recuperadas "
                       f"depois de escanteio/falta: {sp['segundas_bolas_recuperadas']}.")
        c1, c2 = st.columns(2)
        for col, side, title in ((c1, "ataque", f"⚔️ {team} atacando"), (c2, "defesa", f"🛡️ {team} defendendo")):
            with col:
                st.markdown(f"**{title}**")
                rows = [{"Situação": k, "Cobranças": v["cobrancas"], "Finalizações": v["finalizacoes"], "xG": v["xg"],
                         "Gols": v["gols"], "Cobrador": ", ".join(f"{n} ({c})" for n, c in v["cobradores"].items()),
                         "Para onde": ", ".join(f"{n} ({c})" for n, c in v["zonas"].items()),
                         "Quem recebe": ", ".join(f"{n} ({c})" for n, c in v["quem_recebe"].items())}
                        for k, v in (sp.get(side) or {}).items()]
                comparison_table(pd.DataFrame(rows)) if rows else st.caption("Nenhuma bola parada registrada.")
    with t2:
        si = MP.substitution_impact(ctx.df, team)
        if not si["trocas"]:
            st.caption("Sem substituições comparáveis (é preciso ao menos 4 minutos antes e depois da troca).")
        for tr in si["trocas"]:
            v = tr["variacao"]
            pick = [("Posse (%)", "posse_pct"), ("Campo rival (%)", "field_tilt_pct"), ("xT por 15'", "xt_15"),
                    ("xG por 15'", "xg_15"), ("xG sofrido por 15'", "xg_sofrido_15"), ("Pressões por 15'", "pressoes_15")]
            rows = [{"Indicador": lab, "Antes": tr["antes"].get(k), "Depois": tr["depois"].get(k), "Variação": v.get(k)} for lab, k in pick]
            st.markdown(f"**{tr['minuto']}' — entrou {', '.join(tr['entrou'])} · saiu {', '.join(tr['saiu'])}** (placar {tr['placar_na_troca']})")
            comparison_table(pd.DataFrame(rows))
            st.caption(f"Janelas de até {int(si['janela_min'])} min antes e depois · ⚠️ {tr['aviso']}.")
    with t3:
        gs = MP.game_state(ctx.df, team)["estados"]
        if not gs:
            st.caption("Sem dados suficientes.")
        else:
            labs = [("Minutos", "minutos"), ("Posse (%)", "posse_pct"), ("Campo rival (%)", "field_tilt_pct"),
                    ("xT por 15'", "xt_15"), ("Finalizações por 15'", "finalizacoes_15"), ("xG por 15'", "xg_15"),
                    ("xG sofrido por 15'", "xg_sofrido_15"), ("Pressões por 15'", "pressoes_15")]
            df = pd.DataFrame([{"Indicador": lab, **{stt.capitalize(): (round(v[k], 2) if isinstance(v.get(k), float) else v.get(k))
                                                      for stt, v in gs.items()}} for lab, k in labs])
            comparison_table(df)
            small = [k for k, v in gs.items() if v.get("amostra_pequena")]
            st.caption("Produção por 15 minutos em cada situação do placar." + (f" ⚠️ Amostra pequena: {', '.join(small)}." if small else ""))
