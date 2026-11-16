"""
Inteligência histórica do time (rodada 5) — usa as ESTATÍSTICAS por jogo (ESPN, FotMob, API-Football…), que existem
para dezenas de milhares de jogos, sem carregar lances.

  identity()            → estilo habitual (posse, jogo direto, cruzamentos, onde finaliza, bola parada, marcação),
                          cada traço com a frequência em que apareceu (consistência), contra a média das mesmas competições;
  vulnerabilities()     → problemas que se REPETEM (só vira "padrão" com ≥ 4 jogos e em ≥ 60% deles; menos que isso é sinal);
  vs_habit()            → pós-jogo: o que este jogo teve de diferente do habitual do time;
  similar()             → jogos taticamente parecidos (vetor de estilo dos dois lados, padronizado), com o que coincide
                          e o que difere — nunca só placar ou formação.

Leitura honesta: métricas de fontes diferentes só entram quando a definição é a mesma chave interna; amostras pequenas
são marcadas; nada aqui é tracking (altura da linha, compactação) — isso não existe nas fontes abertas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

KEYS = ["possession_pct", "pass_accuracy_pct", "passes_total", "long_balls_accurate", "crosses_accurate", "crosses_total",
        "shots_total", "shots_on_target", "shots_inside_box", "shots_outside_box", "xg", "xg_set_play", "big_chances",
        "touches_opp_box", "corners", "tackles_won", "interceptions", "clearances", "fouls", "aerials_won", "saves"]
LABEL = {"possession_pct": "posse de bola (%)", "pass_accuracy_pct": "acerto de passe (%)", "passes_total": "passes",
         "long_balls_accurate": "bolas longas certas", "crosses_accurate": "cruzamentos certos", "crosses_total": "cruzamentos",
         "shots_total": "finalizações", "shots_on_target": "finalizações no alvo", "shots_inside_box": "finalizações de dentro da área",
         "shots_outside_box": "finalizações de fora", "xg": "xG", "xg_set_play": "xG de bola parada", "big_chances": "grandes chances",
         "touches_opp_box": "toques na área rival", "corners": "escanteios", "tackles_won": "desarmes", "interceptions": "interceptações",
         "clearances": "cortes", "fouls": "faltas", "aerials_won": "duelos aéreos ganhos", "saves": "defesas do goleiro",
         "pct_dentro_area": "% das finalizações de dentro da área", "pct_xg_bola_parada": "% do xG em bola parada",
         "pct_bolas_longas": "% de bolas longas nos passes"}


def _matches(db, names: Sequence[str], n: int = 20, before: Optional[str] = None) -> pd.DataFrame:
    """Jogos do time com estatísticas (≥ 5 chaves), um por data (a versão mais rica quando há duas fontes)."""
    ph = ",".join("?" * len(names))
    q = (f"SELECT m.match_id, m.match_date, m.home_team_name, m.away_team_name, m.home_score, m.away_score, m.competition_name, "
         f"COUNT(DISTINCT s.stat_key) AS nkeys FROM matches m JOIN match_team_stats s ON s.match_id = m.match_id "
         f"WHERE (m.home_team_name IN ({ph}) OR m.away_team_name IN ({ph})) " + ("AND m.match_date < ? " if before else "") +
         f"GROUP BY m.match_id HAVING nkeys >= 5 ORDER BY m.match_date DESC LIMIT {int(n) * 3}")
    params = list(names) * 2 + ([before] if before else [])
    with db.connect() as conn:
        m = pd.read_sql_query(q, conn, params=params)
    if m.empty:
        return m
    m = m.sort_values(["match_date", "nkeys"], ascending=[False, False])
    m = m.assign(dt=pd.to_datetime(m["match_date"], errors="coerce"))
    from src.data_hub.registry import source_from_internal_id as _src

    keep, last, last_src = [], None, None
    for r in m.itertuples():       # mesmo jogo em duas fontes = data ±1 dia e fontes DIFERENTES (fica o mais rico)
        if last is not None and pd.notna(r.dt) and abs((r.dt - last).days) <= 1 and _src(r.match_id) != last_src:
            continue
        keep.append(r.match_id)
        last, last_src = r.dt, _src(r.match_id)
    return m[m["match_id"].isin(keep)].drop(columns=["dt"]).head(int(n))


def _vectors(db, m: pd.DataFrame, names: Sequence[str]) -> pd.DataFrame:
    """Uma linha por jogo: métricas a favor (f_) e contra (c_), já com proporções úteis."""
    if m.empty:
        return pd.DataFrame()
    ids = m["match_id"].astype(int).tolist()
    ph = ",".join("?" * len(ids))
    with db.connect() as conn:
        s = pd.read_sql_query(f"SELECT match_id, team_name, stat_key, value FROM match_team_stats WHERE match_id IN ({ph}) "
                              f"AND stat_key IN ({','.join('?' * len(KEYS))})", conn, params=ids + KEYS)
    rows = []
    for mid, g in s.groupby("match_id"):
        mine = g[g["team_name"].isin(names)]
        other = g[~g["team_name"].isin(names)]
        if mine.empty or other.empty:
            continue
        a = dict(zip(mine["stat_key"], pd.to_numeric(mine["value"], errors="coerce")))
        b = dict(zip(other["stat_key"], pd.to_numeric(other["value"], errors="coerce")))
        r = {"match_id": int(mid), **{f"f_{k}": a.get(k) for k in KEYS}, **{f"c_{k}": b.get(k) for k in KEYS}}
        for p, src in (("f_", a), ("c_", b)):
            sh, ins = src.get("shots_total"), src.get("shots_inside_box")
            r[p + "pct_dentro_area"] = 100 * ins / sh if sh and ins is not None else None
            xg, sp = src.get("xg"), src.get("xg_set_play")
            r[p + "pct_xg_bola_parada"] = 100 * sp / xg if xg and sp is not None else None
            pt, lb = src.get("passes_total"), src.get("long_balls_accurate")
            r[p + "pct_bolas_longas"] = 100 * lb / pt if pt and lb is not None else None
        rows.append(r)
    v = pd.DataFrame(rows)
    return m[["match_id", "match_date", "home_team_name", "away_team_name", "home_score", "away_score", "competition_name"]] \
        .merge(v, on="match_id", how="inner")


def _reference(db, competitions: Sequence[str], limit: int = 600) -> pd.DataFrame:
    """Média por time-jogo nas mesmas competições (a régua do 'acima/abaixo do normal')."""
    if not competitions:
        return pd.DataFrame()
    ph = ",".join("?" * len(competitions))
    with db.connect() as conn:
        s = pd.read_sql_query(
            f"SELECT s.match_id, s.team_name, s.stat_key, s.value FROM match_team_stats s WHERE s.match_id IN ("
            f"SELECT match_id FROM matches WHERE competition_name IN ({ph}) ORDER BY match_date DESC LIMIT {int(limit)}) "
            f"AND s.stat_key IN ({','.join('?' * len(KEYS))})", conn, params=list(competitions) + KEYS)
    if s.empty:
        return pd.DataFrame()
    w = s.pivot_table(index=["match_id", "team_name"], columns="stat_key", values="value", aggfunc="first").reset_index()
    if "shots_total" in w and "shots_inside_box" in w:
        w["pct_dentro_area"] = 100 * w["shots_inside_box"] / w["shots_total"].replace(0, np.nan)
    if "xg" in w and "xg_set_play" in w:
        w["pct_xg_bola_parada"] = 100 * w["xg_set_play"] / w["xg"].replace(0, np.nan)
    if "passes_total" in w and "long_balls_accurate" in w:
        w["pct_bolas_longas"] = 100 * w["long_balls_accurate"] / w["passes_total"].replace(0, np.nan)
    return w


TRAITS = [  # (coluna, sentido, limiar relativo, texto)
    ("possession_pct", +1, 0.12, "gosta de ter a bola"), ("possession_pct", -1, 0.12, "abre mão da posse e espera"),
    ("pct_bolas_longas", +1, 0.25, "joga mais direto, com bolas longas"),
    ("crosses_total", +1, 0.25, "ataca muito pelos lados, com cruzamentos"),
    ("pct_dentro_area", +1, 0.10, "trabalha a jogada até finalizar de perto"),
    ("pct_dentro_area", -1, 0.12, "finaliza muito de fora da área"),
    ("pct_xg_bola_parada", +1, 0.35, "depende bastante da bola parada"),
    ("touches_opp_box", +1, 0.20, "vive dentro da área rival"),
    ("tackles_won", +1, 0.20, "desarma muito (marcação agressiva no duelo)"),
    ("interceptions", +1, 0.25, "intercepta muito (lê as linhas de passe)"),
    ("fouls", +1, 0.25, "faz muitas faltas"),
]
VULNS = [  # problemas recorrentes (métricas CONTRA o time)
    ("c_shots_inside_box", "cede finalizações de dentro da área"), ("c_big_chances", "cede grandes chances"),
    ("c_crosses_total", "sofre muitos cruzamentos"), ("c_xg_set_play", "é vulnerável em bola parada"),
    ("c_touches_opp_box", "deixa o rival tocar muito na própria área"), ("c_xg", "cede muito xG"),
    ("c_shots_on_target", "sofre muitas finalizações no alvo"),
]


def _ref_series(ref: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(ref[col], errors="coerce").dropna() if col in ref else pd.Series(dtype=float)


def identity(db, names: Sequence[str], n: int = 15) -> Dict[str, Any]:
    m = _matches(db, names, n)
    v = _vectors(db, m, names)
    if v.empty:
        return {"jogos": 0, "tracos": []}
    ref = _reference(db, v["competition_name"].dropna().unique().tolist())
    out = []
    for col, sign, thr, text in TRAITS:
        fc = "f_" + col
        if fc not in v or col not in ref:
            continue
        vals = pd.to_numeric(v[fc], errors="coerce").dropna()
        r = _ref_series(ref, col)
        if len(vals) < 3 or len(r) < 20 or not r.mean():
            continue
        mean, rmean = float(vals.mean()), float(r.mean())
        rel = (mean - rmean) / abs(rmean)
        freq = float(((vals - rmean) * sign > 0).mean())
        if rel * sign >= thr and freq >= 0.6:
            out.append({"traco": text, "metrica": LABEL.get(col, col),
                        "media": round(mean, 2), "referencia": round(rmean, 2), "dif_pct": round(100 * rel, 1),
                        "frequencia_pct": round(100 * freq), "jogos": int(len(vals))})
    seen, uniq = set(), []
    for t in sorted(out, key=lambda t: -abs(t["dif_pct"])):
        key = t["metrica"]
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    return {"jogos": int(len(v)), "periodo": [str(v["match_date"].min()), str(v["match_date"].max())], "tracos": uniq,
            "referencia": f"média dos times nas mesmas competições ({', '.join(v['competition_name'].dropna().unique()[:3])})"}


def vulnerabilities(db, names: Sequence[str], n: int = 15) -> Dict[str, Any]:
    m = _matches(db, names, n)
    v = _vectors(db, m, names)
    if v.empty:
        return {"jogos": 0, "padroes": [], "sinais": []}
    ref = _reference(db, v["competition_name"].dropna().unique().tolist())
    pad, sig = [], []
    for col, text in VULNS:
        base = col[2:]
        if col not in v or base not in ref:
            continue
        vals = pd.to_numeric(v[col], errors="coerce").dropna()
        r = _ref_series(ref, base)
        if len(vals) < 2 or len(r) < 20:
            continue
        p70 = float(r.quantile(0.7))
        hits = int((vals > p70).sum())
        item = {"problema": text, "metrica": LABEL.get(base, base), "jogos_acima": hits, "jogos": int(len(vals)),
                "frequencia_pct": round(100 * hits / len(vals)), "media_contra": round(float(vals.mean()), 2),
                "p70_da_competicao": round(p70, 2)}
        if len(vals) >= 4 and hits / len(vals) >= 0.6:
            pad.append(item)
        elif hits >= 2 and hits / len(vals) >= 0.4:
            sig.append(item)
    pad.sort(key=lambda x: -x["frequencia_pct"])
    sig.sort(key=lambda x: -x["frequencia_pct"])
    return {"jogos": int(len(v)), "padroes": pad, "sinais": sig,
            "criterio": "padrão = acima do P70 da competição em ≥ 60% de pelo menos 4 jogos; sinal = ≥ 40% e ≥ 2 jogos"}


def vs_habit(db, names: Sequence[str], match_id: int, n: int = 15) -> Dict[str, Any]:
    """Pós-jogo: diferenças deste jogo em relação ao habitual do time (os 15 jogos anteriores com estatísticas)."""
    with db.connect() as conn:
        row = conn.execute("SELECT match_date FROM matches WHERE match_id = ?", (int(match_id),)).fetchone()
    if not row:
        return {"diferencas": []}
    this = _vectors(db, _matches_by_id(db, int(match_id)), names)
    hist = _vectors(db, _matches(db, names, n, before=row[0]), names)
    if this.empty or len(hist) < 4:
        return {"diferencas": [], "jogos_historico": int(len(hist))}
    t = this.iloc[0]
    diffs = []
    for col in [c for c in this.columns if c.startswith(("f_", "c_"))]:
        vals = pd.to_numeric(hist.get(col), errors="coerce").dropna()
        x = pd.to_numeric(pd.Series([t[col]]), errors="coerce").iloc[0]
        if len(vals) < 4 or pd.isna(x) or not vals.std():
            continue
        z = (float(x) - float(vals.mean())) / float(vals.std())
        if abs(z) >= 1.3:
            base = col[2:]
            diffs.append({"metrica": ("a favor: " if col.startswith("f_") else "contra: ") + LABEL.get(base, base.replace("_", " ")),
                          "neste_jogo": round(float(x), 2), "habitual": round(float(vals.mean()), 2), "z": round(z, 2)})
    diffs.sort(key=lambda d: -abs(d["z"]))
    return {"diferencas": diffs[:6], "jogos_historico": int(len(hist))}


def _matches_by_id(db, match_id: int) -> pd.DataFrame:
    with db.connect() as conn:
        return pd.read_sql_query("SELECT match_id, match_date, home_team_name, away_team_name, home_score, away_score, "
                                 "competition_name FROM matches WHERE match_id = ?", conn, params=(int(match_id),))


SIM_COLS = ["possession_pct", "pass_accuracy_pct", "pct_bolas_longas", "crosses_total", "pct_dentro_area", "shots_total",
            "xg", "touches_opp_box", "tackles_won", "interceptions"]


def similar(db, names: Sequence[str], match_id: int, k: int = 3, pool: int = 1500) -> Dict[str, Any]:
    """Jogos com estilo parecido ao deste time neste jogo (com e sem a bola, dos dois lados), na base inteira."""
    this = _vectors(db, _matches_by_id(db, int(match_id)), names)
    if this.empty:
        return {"semelhantes": []}
    with db.connect() as conn:
        s = pd.read_sql_query(
            f"SELECT s.match_id, s.team_name, s.stat_key, s.value FROM match_team_stats s WHERE s.match_id IN ("
            f"SELECT match_id FROM match_team_stats GROUP BY match_id HAVING COUNT(DISTINCT stat_key) >= 8 "
            f"ORDER BY match_id DESC LIMIT {int(pool)}) AND s.stat_key IN ({','.join('?' * len(KEYS))})", conn, params=KEYS)
    if s.empty:
        return {"semelhantes": []}
    w = s.pivot_table(index=["match_id", "team_name"], columns="stat_key", values="value", aggfunc="first").reset_index()
    w["pct_dentro_area"] = 100 * w.get("shots_inside_box", np.nan) / w.get("shots_total", pd.Series(np.nan, index=w.index)).replace(0, np.nan)
    w["pct_bolas_longas"] = 100 * w.get("long_balls_accurate", np.nan) / w.get("passes_total", pd.Series(np.nan, index=w.index)).replace(0, np.nan)
    cols = [c for c in SIM_COLS if c in w]
    t = this.iloc[0]
    tv = np.array([pd.to_numeric(pd.Series([t.get("f_" + c)]), errors="coerce").iloc[0] for c in cols], dtype=float)
    ok = ~np.isnan(tv)
    if ok.sum() < 5:
        return {"semelhantes": [], "motivo": "este jogo tem poucas estatísticas para comparar estilo"}
    cols = [c for c, o in zip(cols, ok) if o]
    tv = tv[ok]
    X = w[cols].apply(pd.to_numeric, errors="coerce")
    X = X[X.notna().sum(axis=1) == len(cols)]
    meta = w.loc[X.index, ["match_id", "team_name"]]
    mu, sd = X.mean(), X.std().replace(0, 1)
    Z = (X - mu) / sd
    tz = (tv - mu.values) / sd.values
    dist = np.sqrt(((Z.values - tz) ** 2).mean(axis=1))
    meta = meta.assign(dist=dist)
    meta = meta[meta["match_id"] != int(match_id)].sort_values("dist").head(k * 4)
    with db.connect() as conn:
        info = pd.read_sql_query(f"SELECT match_id, match_date, home_team_name, away_team_name, home_score, away_score, competition_name "
                                 f"FROM matches WHERE match_id IN ({','.join('?' * len(meta))})", conn,
                                 params=meta["match_id"].astype(int).tolist()) if len(meta) else pd.DataFrame()
    out, seen = [], set()
    for r in meta.itertuples():
        inf = info[info["match_id"] == r.match_id]
        if inf.empty:
            continue
        i0 = inf.iloc[0]
        key = (str(i0["match_date"]), r.team_name)
        if key in seen:
            continue
        seen.add(key)
        zr = Z.loc[(w["match_id"] == r.match_id) & (w["team_name"] == r.team_name)].iloc[0].values if \
            ((w["match_id"] == r.match_id) & (w["team_name"] == r.team_name)).any() else None
        same, diff = [], []
        if zr is not None:
            d = np.abs(zr - tz)
            order = np.argsort(d)
            same = [LABEL.get(cols[j], cols[j]) for j in order[:3]]
            diff = [LABEL.get(cols[j], cols[j]) for j in order[-2:]]
        out.append({"jogo": f"{i0['home_team_name']} {i0['home_score']} x {i0['away_score']} {i0['away_team_name']}",
                    "data": str(i0["match_date"]), "competicao": i0["competition_name"], "time_comparado": r.team_name,
                    "distancia": round(float(r.dist), 2), "coincide_em": same, "difere_em": diff, "match_id": int(r.match_id)})
        if len(out) >= k:
            break
    return {"semelhantes": out, "base": f"{len(Z)} atuações com estatísticas", "variaveis": cols,
            "criterio": "distância média entre as estatísticas padronizadas (0 = idêntico); só o estilo do time, não o placar"}
