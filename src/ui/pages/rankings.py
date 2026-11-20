"""🏆 Rankings e avaliação de jogadores (rodada 16) — avaliações SEPARADAS, por competição, posição e função tática,
com a ficha explicável de cada jogador. As contas estão em src/scout/evaluation.py."""

from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st

from src.ui.perf import timed as _perf_timed

from src.scout import evaluation as EV
from src.ui.components import hero, note, styled_dataframe
from src.ui.gate import visitor_blocked as _vb

EVALS = {
    "🏅 Melhores da temporada": ("temporada", "desempenho por 90 + uso (≥ 900 min e ≥ 35% dos minutos do time)"),
    "⚡ Desempenho por 90": ("desempenho_90", "produção por 90 na função, puxada à média com poucos minutos"),
    "📈 Mais regulares": ("regularidade", "% de jogos com nota ≥ 7 e pouca oscilação (≥ 8 jogos)"),
    "🎯 Maior impacto no time": ("impacto", "fatia da produção do time + nota acima dos companheiros + uso (≥ 600 min)"),
    "💪 Contra adversários fortes": ("contra_fortes", "nota contra o terço mais forte da competição (≥ 3 jogos)"),
    "🌱 Maior potencial": ("potencial", "≤ 23 anos: desempenho + uso + idade (≥ 450 min)"),
    "✨ Revelações": ("revelacao", "≤ 21 anos: desempenho contra jovens da mesma função (≥ 600 min)"),
    "💶 Custo-benefício": ("custo_beneficio", "desempenho acima do que o valor de mercado indica (≥ 900 min)"),
    "🌍 Geral entre ligas": ("geral_entre_ligas", "temporada × nível ESTIMADO da competição (comparação entre ligas)"),
}
FAM = {"": "Todas", **EV.FAMILY_PT}


@_perf_timed("rankings._data")
@st.cache_data(show_spinner=False, max_entries=4, persist="disk")
def _data(day: str, stamp: str):
    res = EV.load()
    if res is None:
        from src.ui.context import get_service

        res = EV.build(get_service().db)
        EV.save(res)
        res = EV.load() or res
    return res


def _stamp() -> str:
    try:
        return str(int(EV.OUT_PATH.stat().st_mtime))
    except OSError:
        return "0"


def _bar(label: str, v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return (f'<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><div style="width:170px;color:#98A6BF;'
                f'font-size:.82rem">{label}</div><div style="color:#64748B;font-size:.8rem">amostra insuficiente</div></div>')
    v = float(v)
    color = "#22C55E" if v >= 70 else ("#22D3EE" if v >= 50 else ("#F59E0B" if v >= 35 else "#EF4444"))
    return (f'<div style="display:flex;gap:8px;align-items:center;margin:3px 0"><div style="width:170px;color:#CBD5E1;'
            f'font-size:.82rem">{label}</div><div style="flex:1;background:#0F1A2E;border-radius:6px;height:12px">'
            f'<div style="width:{max(min(v, 100), 2):.0f}%;background:{color};height:12px;border-radius:6px"></div></div>'
            f'<div style="width:38px;text-align:right;font-weight:700">{v:.0f}</div></div>')


def _card(title: str, items, color: str) -> str:
    li = "".join(f"<li style='margin:2px 0'>{html.escape(str(x))}</li>" for x in items) or \
        "<li style='color:#64748B'>nada fora da curva com os dados disponíveis</li>"
    return (f'<div style="background:#0B1120;border:1px solid #1E2A44;border-left:4px solid {color};border-radius:12px;'
            f'padding:.6rem .9rem;margin-bottom:.5rem"><div style="font-weight:800;margin-bottom:4px">{title}</div>'
            f'<ul style="margin:0 0 0 1rem;padding:0;font-size:.86rem">{li}</ul></div>')


def with_scout_quality(df: pd.DataFrame, name_col: str = "player_name", team_col: str = "team_name") -> pd.DataFrame:
    """Rodada 24: qualidade e potencial vêm do universo do Scout (nome + clube; homônimo sem clube que confira = vazio)."""
    out = df.copy()
    out["qualidade_scout"], out["potencial_scout"] = np.nan, np.nan
    try:
        from src.data_lake.ids import player_core, team_core
        from src.scout import snapshot as S

        qm = S.quality_map()
        q, pp = qm["q"], qm["p"]
        k = out[name_col].map(lambda n: player_core(str(n))) + "|" + out[team_col].fillna("").map(lambda c: team_core(str(c)))
        out["qualidade_scout"] = k.map(q).round(0)
        out["potencial_scout"] = k.map(pp).round(0)
    except Exception:
        pass
    return out


def render(_ctx=None) -> None:
    hero("Scout · avaliação", "Rankings que respondem perguntas diferentes",
         "Melhor da temporada não é o mesmo que maior potencial, nem o mesmo que quem rende contra os fortes. Cada "
         "avaliação tem a sua amostra mínima, compara só jogadores da mesma função e da mesma competição, e usa apenas "
         "as estatísticas que aquela competição realmente tem.")
    from datetime import date

    with st.spinner("Carregando as avaliações…"):
        res = _data(str(date.today()), _stamp())
    ev = res.get("jogadores") if isinstance(res, dict) else None
    if ev is None or ev.empty:
        st.info("Ainda não há jogos com números por jogador suficientes para avaliar. Baixe os detalhes da FotMob "
                "(`python -m src.data_hub.sync --only fotmob_jogos --limite 3000`).")
        return
    a, b, c = st.columns([1.6, 1.4, 1])
    st.session_state.setdefault("rk_eval", "🌍 Geral entre ligas")   # rodada 22: visão conjunta (todas as ligas) por padrão
    pick = a.selectbox("Avaliação", list(EVALS), key="rk_eval")
    col, crit = EVALS[pick]
    comps = ev["comp"].value_counts()
    # rodada 22: visão conjunta é o padrão — vazio = TODAS as competições (antes abria só na Série A)
    chosen = b.multiselect("Competições", comps.index.tolist(), default=[], key="rk_comps",
                           format_func=lambda c_: f"{c_} ({comps[c_]})", placeholder="todas as competições")
    fam = c.selectbox("Posição", list(FAM), format_func=FAM.get, key="rk_fam")
    d, e, f = st.columns(3)
    funcs = sorted(ev.loc[ev["family"] == fam, "funcao"].dropna().unique()) if fam else []
    func = d.selectbox("Função tática", ["Todas"] + funcs, key="rk_func", disabled=not fam)
    min_min = e.slider("Minutos mínimos", 0, 3000, 0, 90, key="rk_min")
    max_age = f.slider("Idade máxima", 16, 40, 40, key="rk_age")
    st.caption(f"Critério: {crit}. Em ‘🌍 Geral entre ligas’ o nível de cada competição é uma ESTIMATIVA (ver abaixo).")
    v = ev.copy()
    if chosen and col != "geral_entre_ligas":
        v = v[v["comp"].isin(chosen)]
    elif not chosen and col != "geral_entre_ligas":
        st.caption("Todas as competições juntas: nesta avaliação cada nota é relativa à PRÓPRIA competição (P90 da Série C "
                   "não é igual a P90 da Premier League). Para comparar ligas de níveis diferentes use 🌍 Geral entre ligas.")
    if fam:
        v = v[v["family"] == fam]
    if func != "Todas":
        v = v[v["funcao"] == func]
    v = v[v["minutes"] >= min_min]
    if max_age < 40:
        v = v[v["idade"].fillna(99) <= max_age]
    base_v = v
    v = v.dropna(subset=[col]).sort_values([col, "minutes"], ascending=False)
    if v.empty and col != "desempenho_90":
        note("Ninguém atende ao critério desta avaliação neste recorte",
             f"{crit}. Mostrando o ‘⚡ Desempenho por 90’ (com 450+ min) enquanto a temporada não acumula amostra.", "info")
        col, pick = "desempenho_90", "⚡ Desempenho por 90"
        v = base_v[base_v["minutes"] >= 450].dropna(subset=[col]).sort_values([col, "minutes"], ascending=False)
    if v.empty:
        note("Ninguém atende a este recorte", "Amplie a competição, a posição ou os minutos.", "info")
        return
    show = v.head(100).assign(**{"% min. do time": (100 * v["min_share"]).round(0),
                                 "idade": pd.to_numeric(v["idade"], errors="coerce").round(0)})
    show = with_scout_quality(show)          # rodada 24: a MESMA qualidade do Scout/elenco/página do jogador
    table = show[["player_name", "team_name", "comp", "funcao", "idade", "qualidade_scout", "potencial_scout", "games",
                  "minutes", "starts", "subs", "% min. do time", col, "desempenho_90", "confianca_amostra"]].rename(columns={
        "qualidade_scout": "Qualidade", "potencial_scout": "Potencial",
        "player_name": "Jogador", "team_name": "Time", "comp": "Competição", "funcao": "Função", "idade": "Idade",
        "games": "Jogos", "minutes": "Minutos", "starts": "Titular", "subs": "Entrou", col: pick.split(" ", 1)[1],
        "desempenho_90": "Desempenho/90", "confianca_amostra": "Amostra"})
    styled_dataframe(table.loc[:, ~table.columns.duplicated()], hide_index=True, use_container_width=True)
    st.markdown("### 🔎 Ficha do jogador")
    who = st.selectbox("Jogador", [f"{r.player_name} — {r.team_name} ({r.comp})" for r in v.head(100).itertuples()],
                       key="rk_who")
    row = v.head(100).iloc[[f"{r.player_name} — {r.team_name} ({r.comp})" for r in v.head(100).itertuples()].index(who)]
    _profile(row.to_dict(), ev)
    with st.expander("📏 Nível das competições (estimativa) e validação do ranking"):
        niv = pd.DataFrame(res.get("niveis") or [])
        if not niv.empty:
            styled_dataframe(niv.rename(columns={"comp": "Competição", "nivel": "Nível usado", "nivel_previo": "Estimativa prévia",
                                                 "pares": "Jogadores em 2 competições", "base": "Base"}),
                             hide_index=True, use_container_width=True)
        val = res.get("validacao") or {}
        st.markdown(f"- **Estabilidade entre turnos** (nota nos jogos ímpares × pares, correlação de postos): "
                    f"{val.get('estabilidade_turnos', '—')} em {val.get('estabilidade_n', 0)} jogadores — quanto mais "
                    "perto de 1, mais a avaliação reflete o jogador e não o acaso.")
        st.markdown(f"- **Jogadores sem minutos em ‘Melhores da temporada’:** {val.get('sem_minutos_no_ranking', '—')} "
                    f"(deve ser 0) · **reservas (< 35% dos minutos):** {val.get('reservas_no_ranking_temporada', '—')} (deve ser 0)")
        st.markdown(f"- **Média do desempenho por cobertura de dados:** {val.get('media_por_cobertura', {})} — se a "
                    "competição com mais estatísticas tivesse vantagem, a média da ‘completa’ ficaria bem acima.")
        st.caption(f"Gerado em {res.get('gerado', '—')} com {res.get('jogos', '—')} jogos em {res.get('segundos', '—')} s. "
                   "O processo de fundo refaz uma vez por dia.")
    if st.button("🔄 Recalcular agora", key="rk_rebuild") and not _vb("O recálculo"):
        from src.ui.context import get_service

        with st.spinner("Recalculando todas as avaliações…"):
            EV.save(EV.build(get_service().db))
        _data.clear()
        st.rerun()


def _profile(row, ev) -> None:
    p = EV.profile(row, ev)
    left, right = st.columns([1, 1.3])
    with left:
        st.markdown(f"<div style='font-size:1.35rem;font-weight:800'>{html.escape(row['player_name'])}</div>"
                    f"<div style='color:#98A6BF'>{html.escape(str(row['team_name']))} · {html.escape(str(row['comp']))} · "
                    f"<b style='color:#22D3EE'>{html.escape(str(row['funcao']))}</b>"
                    + (f" · {row['idade']:.0f} anos" if pd.notna(row.get("idade")) else "") + "</div>"
                    f"<div style='font-size:.8rem;color:#7C8BA5;margin:.3rem 0 .6rem'>{html.escape(p['amostra'])}</div>",
                    unsafe_allow_html=True)
        bars = "".join(_bar(lbl.split(" ", 1)[1], row.get(c)) for lbl, (c, _) in EVALS.items())
        st.markdown(bars, unsafe_allow_html=True)
    with right:
        st.markdown(_card("✅ Principais qualidades", p["fortes"], "#22C55E"), unsafe_allow_html=True)
        st.markdown(_card("⚠️ Limitações", p["limitacoes"], "#EF4444"), unsafe_allow_html=True)
        st.markdown(_card("🧭 Contexto (adversários, casa/fora, protagonismo, fase)", p["contexto"], "#22D3EE"),
                    unsafe_allow_html=True)
        st.markdown(_card("🏟️ Tende a render mais em", p["rende_mais_em"], "#A78BFA"), unsafe_allow_html=True)
        miss = p["nao_avaliado_por_falta_de_dado"]
        st.caption(("Não avaliado (a competição não publica): " + ", ".join(miss) + ". " if miss else "")
                   + "Não observável com dados abertos: " + ", ".join(p["nao_observavel"]) + ".")
    same = ev[(ev["family"] == row["family"]) & (ev["funcao"] == row["funcao"])].dropna(subset=["geral_entre_ligas"])
    if len(same) > 1:
        st.markdown("**Comparação com a mesma função (todas as competições, régua ‘geral entre ligas’)**")
        top = same.sort_values("geral_entre_ligas", ascending=False).head(8)
        styled_dataframe(top[["player_name", "team_name", "comp", "minutes", "desempenho_90", "geral_entre_ligas"]].rename(
            columns={"player_name": "Jogador", "team_name": "Time", "comp": "Competição", "minutes": "Minutos",
                     "desempenho_90": "Desempenho/90", "geral_entre_ligas": "Geral entre ligas"}),
            hide_index=True, use_container_width=True)
