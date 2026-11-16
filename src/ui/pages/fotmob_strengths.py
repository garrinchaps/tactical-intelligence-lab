"""
⚖️ Fortes e fracos em jogo SEM lances (rodada 5): estatísticas do time contra a média dos times das mesmas competições e
números de cada jogador (FotMob) contra a mesma função — só o que foge da curva aparece.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from src.ui.components import metric_bars, note


@st.cache_data(show_spinner=False, ttl=3600, max_entries=32)
def _team_view(match_id: int, team: str, comp: str, version: str) -> Dict[str, Any]:
    from src.analytics import team_history as TH
    from src.ui.context import get_service

    db = get_service().db
    with db.connect() as conn:
        s = pd.read_sql_query("SELECT team_name, stat_key, value FROM match_team_stats WHERE match_id = ?", conn, params=(match_id,))
    if s.empty:
        return {"itens": []}
    ref = TH._reference(db, [comp]) if comp else pd.DataFrame()
    mine = dict(zip(s.loc[s["team_name"] == team, "stat_key"], pd.to_numeric(s.loc[s["team_name"] == team, "value"], errors="coerce")))
    opp = dict(zip(s.loc[s["team_name"] != team, "stat_key"], pd.to_numeric(s.loc[s["team_name"] != team, "value"], errors="coerce")))
    items = []
    for k, v in mine.items():
        if k not in TH.LABEL or ref.empty or k not in ref or pd.isna(v):
            continue
        col = pd.to_numeric(ref[k], errors="coerce").dropna()
        if len(col) < 20:
            continue
        pct = 100.0 * ((col < v).sum() + 0.5 * (col == v).sum()) / len(col)
        good = pct if k not in ("fouls",) else 100 - pct
        items.append({"label": TH.LABEL[k].capitalize() + " (a favor)", "value": round(float(v), 2), "percentile": round(good),
                      "reference_median": round(float(col.median()), 2)})
    for k, v in opp.items():                                   # o que o time CEDEU (menos é melhor)
        if k not in ("shots_total", "shots_on_target", "xg", "big_chances", "touches_opp_box", "shots_inside_box") or ref.empty \
                or k not in ref or pd.isna(v):
            continue
        col = pd.to_numeric(ref[k], errors="coerce").dropna()
        if len(col) < 20:
            continue
        pct = 100.0 * ((col < v).sum() + 0.5 * (col == v).sum()) / len(col)
        items.append({"label": TH.LABEL[k].capitalize() + " cedidos", "value": round(float(v), 2), "percentile": round(100 - pct),
                      "reference_median": round(float(col.median()), 2)})
    return {"itens": items, "referencia": len(ref)}


@st.cache_data(show_spinner=False, ttl=3600, max_entries=32)
def _players(match_id: int) -> pd.DataFrame:
    from src.analytics import rating_box as RB
    from src.ui.context import get_service

    try:
        return RB.match_ratings(get_service().db, match_id)
    except Exception:
        return pd.DataFrame()


def render(ctx, team: str) -> None:
    from src.analytics.rating_v2 import outliers
    from src.ui.context import get_service
    from src.ui.pages.fotmob_depth import _sibling_fotmob

    meta = ctx.bundle.meta or {}
    fm_id = _sibling_fotmob(ctx) or int(ctx.match_id)
    st.markdown(f"### ⚖️ {team}: o que fugiu da curva neste jogo")
    tv = _team_view(int(fm_id), team, meta.get("competition_name", ""), get_service().db.stable_version())
    items = tv.get("itens") or []
    if items:
        st.caption(f"Time contra {tv.get('referencia', 0)} atuações de times nas mesmas competições (percentil já no sentido "
                   "'bom': ceder menos = melhor). Só aparece o que ficou acima do P75 ou abaixo do P25.")
        a, b = st.columns(2)
        with a:
            st.markdown("#### 🟢 Fortes")
            metric_bars(sorted([i for i in items if i["percentile"] >= 75], key=lambda i: -i["percentile"]), "forte",
                        "Nada muito acima do normal.")
        with b:
            st.markdown("#### 🔴 Fracos")
            metric_bars(sorted([i for i in items if i["percentile"] <= 25], key=lambda i: i["percentile"]), "fraco",
                        "Nada muito abaixo do normal.")
    else:
        note("Sem estatísticas suficientes", "Este jogo não tem estatísticas do time para comparar.", "info")
    pr = _players(int(fm_id))
    if pr is None or pr.empty:
        return
    mine = pr[pr["equipe"] == team] if (pr["equipe"] == team).any() else pr
    rows = []
    for r in mine.to_dict("records"):
        o = outliers(r["_detalhe"], 80, 20)
        for kind, lst in (("forte", o["fortes"][:1]), ("fraco", o["fracos"][:1])):
            for x in lst:
                rows.append({"label": f"{r['jogador']}: {x['rotulo']}", "value": round(float(x["valor"]), 2),
                             "percentile": x["percentil"], "reference_median": round(float(x["mediana_pares"]), 2)
                             if x.get("mediana_pares") is not None else "—", "_k": kind})
    if rows:
        st.markdown("#### 👤 Jogadores fora da curva (contra a mesma função, números da FotMob)")
        a, b = st.columns(2)
        with a:
            metric_bars(sorted([r for r in rows if r["_k"] == "forte"], key=lambda r: -r["percentile"]), "forte")
        with b:
            metric_bars(sorted([r for r in rows if r["_k"] == "fraco"], key=lambda r: r["percentile"]), "fraco")
