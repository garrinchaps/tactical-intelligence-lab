"""Rodada 23 — "Relatório do olheiro" do time (página do time e pré-jogo do rival), no espírito do FM com as cores do
laboratório: pontos fortes/fraquezas com colocação na liga, jogadores-chave, lesões, treinador (desenho, mentalidade,
pressão), estatísticas com colocação, factos do elenco e comparação com o meu time."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import pandas as pd
import streamlit as st

from src.ui import fm
from src.ui.perf import timed as _perf_timed


@_perf_timed("team_report._data")
@st.cache_data(show_spinner=False, max_entries=48, persist="disk")
def _data(names: tuple, version: str) -> Dict[str, Any]:
    from src.analytics import team_report as TR
    from src.ui.context import get_service

    db = get_service().db
    r = TR.report(db, list(names), 20)
    rk = r.get("ranks") or {}
    if "tabela" in rk:
        rk["tabela"] = rk["tabela"].head(30)
    try:
        from src.squad.matchday import roster

        ro = roster(db, list(names))
    except Exception:
        ro = pd.DataFrame()
    r["elenco"] = ro
    return r


def _youth_star(names: Sequence[str]) -> Optional[Dict[str, Any]]:
    from src.scout import snapshot as S

    u = S.cached_universe()
    if u is None or u.empty or "clube" not in u:
        return None
    from src.data_lake.ids import team_core

    cores = {team_core(n) for n in names}
    t = u[u["clube"].fillna("").map(lambda c: team_core(str(c))).isin(cores)]
    age = pd.to_numeric(t.get("idade"), errors="coerce")
    t = t[age <= 21]
    if t.empty:
        return None
    pot = pd.to_numeric(t.get("potencial", t.get("potencial_teto")), errors="coerce")
    if pot.notna().sum() == 0:
        return None
    r = t.loc[pot.idxmax()]
    return {"nome": r["nome"], "valor": f"{int(r['idade'])} anos · potencial {int(pot.max())}"}


@st.cache_data(show_spinner=False, ttl=6 * 3600, max_entries=32, persist="disk")
def _league_roster(names: tuple, version: str) -> pd.DataFrame:
    from src.analytics import team_report as TR
    from src.ui.context import get_service

    db = get_service().db
    return TR.league_rosters(db, TR.main_competition(db, list(names)))


def _league_of(names: Sequence[str]) -> str:
    from src.scout import snapshot as S
    from src.data_lake.ids import team_core

    u = S.cached_universe()
    if u is None or u.empty or "clube_liga" not in u:
        return ""
    cores = {team_core(n) for n in names}
    t = u[u["clube"].fillna("").map(lambda c: team_core(str(c))).isin(cores)]
    vc = t["clube_liga"].dropna().astype(str).value_counts()
    return vc.index[0] if not vc.empty else ""


def render(team: str, names: Sequence[str], version: str, key: str, my_team: str = "", my_names: Sequence[str] = ()) -> None:
    from src.analytics import team_report as TR
    from src.scout import snapshot as S

    with st.spinner("Montando o relatório do olheiro…"):
        d = _data(tuple(names), version)
    fw = d.get("forcas") or {}
    pl = d.get("jogadores") or {}
    co = d.get("treinador") or {}
    rk = d.get("ranks") or {}
    left, right = st.columns([1.05, 1.25])
    with left:
        fm.panel("Relatório da equipe", fm.CYAN, f"últimos {fw.get('jogos', 0)} jogos com estatísticas")
        fm.icon_list([(x["icone"], f"{x['titulo']} — {x['texto']}") for x in fw.get("fortes") or []], "pro", "Pontos fortes")
        fm.icon_list([(x["icone"], f"{x['titulo']} — {x['texto']}") for x in fw.get("fracos") or []], "con", "Fraquezas")
        fm.panel("Treinador", fm.BLUE)
        fm.rank_list([("🧑‍🏫", "Treinador", f"{co.get('treinador')}" + (f" · desde {co['desde']} ({co.get('jogos')} jogos)" if co.get("desde") else "")),
                      ("📐", "Formação preferida", co.get("formacao") or "—"),
                      ("🧭", "Mentalidade de jogo", co.get("mentalidade") or "—"),
                      ("🔥", "Tipo de pressão", (co.get("pressao") or "—") + (f" · PPDA {co['ppda']:.1f}" if co.get("ppda") else ""))])
    with right:
        fm.panel("Jogadores", fm.CYAN, f"{pl.get('usados', 0)} usados em {pl.get('jogos', 0)} jogos · {pl.get('recorte', '')}")
        tiles = []
        for lab, k in (("Jogador-chave", "mais_melhor_em_campo"), ("Melhor marcador", "melhor_marcador"),
                       ("Mais assistências", "mais_assistencias"), ("Melhor nota média", "melhor_nota"),
                       ("Mais passes certos", "mais_passes_pct"), ("Mais minutos", "mais_minutos")):
            x = pl.get(k)
            if x:
                tiles.append((lab, x["nome"], x["valor"]))
        ys = _youth_star(names)
        if ys:
            tiles.append(("Jovem promessa", ys["nome"], ys["valor"]))
        fm.people_tiles(tiles, cols=4)
        ro = d.get("elenco")
        if isinstance(ro, pd.DataFrame) and not ro.empty and "lesao" in ro:
            inj = ro[ro["lesao"].fillna("").astype(str) != ""]
            fm.panel("Lesões e suspensões", fm.RED, f"{len(inj)} no elenco atual (FotMob/ESPN)")
            fm.icon_list([("🩹", f"{r.get('name') or r.get('nome')} — {r['lesao']}") for _, r in inj.head(8).iterrows()], "con")
        if rk:
            fm.panel(f"Estatísticas da equipe · {rk.get('competicao')} {rk.get('temporada')}", fm.BLUE)
            fm.rank_list([("🏆", "Posição na tabela", f"{rk['posicao']}º de {rk['times']} · {rk['pontos']} pontos em {rk['jogos']} jogos"),
                          ("⚽", "Gols marcados", f"{rk['gols_pro']} — {rk['gols_pro_rank']}"),
                          ("🧱", "Gols sofridos", f"{rk['gols_contra']} — {rk['gols_contra_rank']}")])
    ro = d.get("elenco")
    u = S.cached_universe()
    liga = _league_of(names)
    lr = _league_roster(tuple(names), version)
    facts = TR.squad_facts(ro if isinstance(ro, pd.DataFrame) else pd.DataFrame(), u, liga, lr)
    if facts:
        fm.panel("Factos do elenco atual", fm.CYAN, f"média da liga: {liga}" if liga else "")
        fm.facts_table(facts, team, f"Média da {liga}" if liga else "Liga")
    if my_team and my_names:
        try:
            mine = _data(tuple(my_names), version)
            mf = {r["fato"]: r["a"] for r in TR.squad_facts(mine.get("elenco"), None)}
            tf = {r["fato"]: r["a"] for r in facts}
            rows = [{"fato": k, "a": mf.get(k, "—"), "b": tf.get(k, "—")} for k in
                    ("Média de idades", "Altura média", "Valor médio", "Nacionalidades representadas",
                     "Tendência para jogadores nacionais", "Lesionados agora") if k in mf or k in tf]
            mc, tc = (mine.get("treinador") or {}), co
            rows.append({"fato": "Treinador desde", "a": mc.get("desde") or "—", "b": tc.get("desde") or "—"})
            fm.panel("Comparação de equipe", fm.BLUE)
            fm.facts_table(rows, my_team, team)
        except Exception:
            pass
    st.caption("Pontos fortes/fraquezas = média por jogo contra os outros times das mesmas competições (só o que fica entre "
               "os ~30% melhores/piores). Mentalidade pela posse e pressão pelo PPDA contra a média. Salário e capitão não "
               "aparecem porque nenhuma fonte aberta traz de forma confiável.")


def render_dashboard(team: str, names: Sequence[str], version: str, key: str) -> None:
    """Rodada 23 — painel do clube no espírito da tela inicial do FM: classificação, calendário e resultados, próximo
    jogo com desfalques, estatísticas com colocação, destaques dos jogadores e posições ao longo da temporada."""
    import plotly.graph_objects as go

    with st.spinner("Montando o painel do clube…"):
        d = _data(tuple(names), version)
    rk, cal, pl = d.get("ranks") or {}, d.get("calendario") or {}, d.get("jogadores") or {}
    a, b, c = st.columns([1.15, 1.25, 1.0])
    with a:
        fm.panel(f"Classificação · {rk.get('competicao', '—')}", fm.CYAN, str(rk.get("temporada") or ""))
        tab = rk.get("tabela")
        if isinstance(tab, pd.DataFrame) and not tab.empty:
            mine = set(names)
            rows = "".join(
                f'<tr style="{"background:#0E3B2E;font-weight:800" if (r.time in mine or r["#"] == rk.get("posicao")) else ""}">'
                f'<td>{r["#"]}</td><td>{fm._e(r.time)}</td><td>{r.J}</td><td>{r.V}</td><td>{r.E}</td><td>{r.D}</td>'
                f'<td>{r.SG:+d}</td><td><b>{r.P}</b></td></tr>' for _, r in tab.head(20).iterrows())
            st.markdown('<table class="fm-facts"><thead><tr><th>#</th><th>Equipe</th><th>J</th><th>V</th><th>E</th><th>D</th>'
                        f'<th>SG</th><th>PTS</th></tr></thead><tbody>{rows}</tbody></table>', unsafe_allow_html=True)
        else:
            st.caption("Sem tabela da competição atual na base.")
    with b:
        fm.panel("Calendário e resultados", fm.BLUE)
        items, subs = [], []
        dot = {"V": "🟢", "E": "🟡", "D": "🔴"}
        for r in (cal.get("resultados") or [])[::-1]:
            items.append((dot.get(r["resultado"], "•"), f"{r['data'][8:10]}/{r['data'][5:7]} · {r['local']} · {r['adversario']}  {r['placar']}"))
            subs.append(r["competicao"])
        for r in cal.get("proximos") or []:
            items.append(("📅", f"{r['data'][8:10]}/{r['data'][5:7]} {r['data'][11:16]} · {r['local']} · {r['adversario']}"))
            subs.append(r["competicao"])
        fm.icon_list(items, "neutral", sub_items=subs)
        nxt = (cal.get("proximos") or [None])[0]
        if nxt:
            ro = d.get("elenco")
            inj = ro[ro["lesao"].fillna("").astype(str) != ""] if isinstance(ro, pd.DataFrame) and "lesao" in ro else pd.DataFrame()
            fm.panel("Próximo jogo", fm.CYAN, nxt["competicao"])
            st.markdown(f'<div class="fm-verdict" style="border-color:#1E2A44;background:#0F1626"><div class="t" style="font-size:1.15rem">'
                        f'{fm._e(team if nxt["local"] == "C" else nxt["adversario"])} × {fm._e(nxt["adversario"] if nxt["local"] == "C" else team)}'
                        f'<br><small style="color:#94A3B8">{fm._e(nxt["data"])} (UTC)</small></div></div>', unsafe_allow_html=True)
            if len(inj):
                fm.icon_list([("🩹", f"{r.get('name') or r.get('nome')} — {r['lesao']}") for _, r in inj.head(5).iterrows()],
                             "con", f"Notícias da equipe — {team}")
    with c:
        fm.panel("Estatísticas da equipe", fm.BLUE)
        if rk:
            fm.rank_list([("🏆", "Posição", f"{rk['posicao']}º de {rk['times']} · {rk['pontos']} pts"),
                          ("⚽", "Gols marcados", f"{rk['gols_pro']} — {rk['gols_pro_rank']}"),
                          ("🧱", "Gols sofridos", f"{rk['gols_contra']} — {rk['gols_contra_rank']}")])
        fm.panel("Dados dos jogadores", fm.CYAN)
        lead = [("⚽", "Melhor marcador", pl.get("melhor_marcador")), ("⭐", "Melhor nota média", pl.get("melhor_nota")),
                ("🅰️", "Mais assistências", pl.get("mais_assistencias")), ("🔗", "Mais passes certos", pl.get("mais_passes_pct")),
                ("🏅", "Mais vezes melhor do time", pl.get("mais_melhor_em_campo"))]
        fm.rank_list([(ic, t, f"{x['nome']} · {x['valor']}") for ic, t, x in lead if x])
    hist = rk.get("historico_posicao") or []
    if len(hist) >= 3:
        h = pd.DataFrame(hist)
        fig = go.Figure(go.Scatter(x=h["data"], y=h["posicao"], mode="lines+markers", line=dict(color=fm.CYAN, width=3),
                                   marker=dict(size=6, color="#E2E8F0")))
        fig.update_layout(title=dict(text="Posição na liga ao longo da temporada", font=dict(size=13, color="#CBD5E1")),
                          height=230, margin=dict(l=30, r=10, t=36, b=24), paper_bgcolor="#090D16", plot_bgcolor="#0F1626",
                          yaxis=dict(autorange="reversed", gridcolor="#1E2A44", color="#94A3B8", dtick=2,
                                     range=[int(h["times"].max()) + .5, .5]),
                          xaxis=dict(gridcolor="#1E2A44", color="#94A3B8"))
        st.plotly_chart(fig, use_container_width=True, key=f"{key}_pos")
