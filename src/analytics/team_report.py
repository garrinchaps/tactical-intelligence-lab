"""
Rodada 23 — RELATÓRIO DO OLHEIRO de um time (inspirado no Football Manager, mas com números medidos):

  strengths_weaknesses()  → pontos fortes e fraquezas: cada estatística por jogo contra os OUTROS times das mesmas
                            competições (colocação "3º de 20", valor e média da liga) — só o que é claramente fora do normal;
  key_players()           → melhor marcador, mais assistências, melhor nota média, mais vezes melhor em campo, mais passes
                            certos %, jogadores usados (números por jogador dos últimos jogos);
  team_ranks()            → gols marcados/sofridos, xG, posse, cartões com a colocação na competição atual;
  squad_facts()           → "Factos": mais jovem/velho, idade média, mais baixo/alto, altura média, mais valioso, valor
                            médio, nacionalidades, % de nacionais — e a média da liga (universo do Scout) ao lado;
  report()                → tudo junto + treinador, desenho preferido, mentalidade e tipo de pressão (identidade tática).

Nada inventado: o que a fonte não mede fica de fora (ex.: salário, capitão — nenhuma fonte aberta traz de forma confiável).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

# (coluna f_/c_, maior é melhor?, ícone, nome, como dizer quando é FORTE, como dizer quando é FRACO)
METRICS = [
    ("f_xg", True, "🎯", "Criação de chances", "cria muito perigo (xG alto)", "cria pouco perigo (xG baixo)"),
    ("f_big_chances", True, "💥", "Grandes chances", "chega muito em chance clara", "quase não cria chance clara"),
    ("f_xg_set_play", True, "🚩", "Bola parada ofensiva", "perigosa na bola parada", "cria pouco na bola parada"),
    ("f_touches_opp_box", True, "📦", "Presença na área", "vive dentro da área rival", "pouca presença na área rival"),
    ("f_crosses_accurate", True, "↪️", "Cruzamentos", "cruza bem e com frequência", "cruza pouco/mal"),
    ("f_pass_accuracy_pct", True, "🔗", "Passe", "time de passe muito seguro", "erra muitos passes"),
    ("f_possession_pct", True, "⚽", "Posse de bola", "controla a bola", "fica pouco com a bola"),
    ("f_aerials_won", True, "🗼", "Jogo aéreo", "ganha muitos duelos aéreos", "perde no jogo aéreo"),
    ("f_tackles_won", True, "🛡️", "Desarme", "desarma muito", "desarma pouco"),
    ("f_interceptions", True, "👁️", "Antecipação", "intercepta muito (lê as linhas de passe)", "intercepta pouco"),
    ("c_xg", False, "🧱", "Defesa (xG cedido)", "cede pouquíssimo perigo", "cede muito perigo"),
    ("c_big_chances", False, "🚨", "Chances claras cedidas", "quase não cede chance clara", "cede muita chance clara"),
    ("c_xg_set_play", False, "🚩", "Bola parada defensiva", "segura na bola parada defensiva", "sofre na bola parada defensiva"),
    ("c_shots_inside_box", False, "🥅", "Proteção da área", "rival finaliza pouco de dentro da área", "deixa finalizar de dentro da área"),
    ("c_crosses_total", False, "↩️", "Cruzamentos cedidos", "deixa cruzar pouco", "sofre muitos cruzamentos"),
    ("f_fouls", False, "🟨", "Disciplina", "faz poucas faltas", "faz muitas faltas"),
]


def _team_avgs(db, competitions: Sequence[str], limit: int = 3000) -> pd.DataFrame:
    """Média por TIME (a favor e contra) nas mesmas competições — base da colocação."""
    from src.analytics import team_history as TH

    if not competitions:
        return pd.DataFrame()
    ph = ",".join("?" * len(competitions))
    with db.connect() as conn:
        s = pd.read_sql_query(
            f"SELECT s.match_id, s.team_name, s.stat_key, s.value FROM match_team_stats s WHERE s.match_id IN ("
            f"SELECT match_id FROM matches WHERE competition_name IN ({ph}) ORDER BY match_date DESC LIMIT {int(limit)}) "
            f"AND s.stat_key IN ({','.join('?' * len(TH.KEYS))})", conn, params=list(competitions) + TH.KEYS)
    if s.empty:
        return pd.DataFrame()
    s["value"] = pd.to_numeric(s["value"], errors="coerce")
    w = s.pivot_table(index=["match_id", "team_name"], columns="stat_key", values="value", aggfunc="first").reset_index()
    opp = w.rename(columns={"team_name": "opp"}).add_prefix("c_").rename(columns={"c_match_id": "match_id", "c_opp": "opp"})
    j = w.add_prefix("f_").rename(columns={"f_match_id": "match_id", "f_team_name": "team_name"}).merge(opp, on="match_id")
    j = j[j["team_name"] != j["opp"]]
    g = j.groupby("team_name")
    avg = g.mean(numeric_only=True)
    avg["jogos"] = g.size()
    return avg[avg["jogos"] >= 3].drop(columns=["match_id"], errors="ignore")


def strengths_weaknesses(db, names: Sequence[str], n: int = 20, top: int = 3) -> Dict[str, Any]:
    from src.analytics import team_history as TH

    m = TH._matches(db, list(names), n)
    v = TH._vectors(db, m, list(names))
    if v.empty:
        return {"fortes": [], "fracos": [], "jogos": 0}
    comps = v["competition_name"].dropna().value_counts().index[:3].tolist()
    avgs = _team_avgs(db, comps)
    mine = {c: float(pd.to_numeric(v[c], errors="coerce").mean()) for c, *_ in METRICS if c in v}
    out_s, out_w = [], []
    for col, hib, ic, title, good, bad in METRICS:
        x = mine.get(col)
        if x is None or np.isnan(x) or avgs.empty or col not in avgs:
            continue
        others = pd.to_numeric(avgs[col], errors="coerce").dropna()
        if len(others) < 6:
            continue
        vals = list(others.values) + [x]
        rank = 1 + sum(1 for o in others.values if (o > x if hib else o < x))
        n_t = len(others) + 1
        med = float(np.median(vals))
        item = {"icone": ic, "titulo": title, "valor": round(x, 2), "media": round(med, 2), "posicao": rank, "de": n_t}
        # rodada 23: entre os ~30% melhores/piores da competição (o FM sempre mostra alguns de cada lado)
        if rank <= max(2, round(n_t * .3)):
            out_s.append({**item, "texto": f"{good}: {x:.2f} por jogo, {rank}º de {n_t} (média {med:.2f})", "forca": rank / n_t})
        elif rank >= n_t - max(1, round(n_t * .3)) + 1:
            out_w.append({**item, "texto": f"{bad}: {x:.2f} por jogo, {rank}º de {n_t} (média {med:.2f})", "forca": 1 - rank / n_t})
    out_s.sort(key=lambda d: d["forca"])
    out_w.sort(key=lambda d: d["forca"])
    return {"fortes": out_s[:top], "fracos": out_w[:top], "jogos": int(len(v)), "competicoes": comps}


def key_players(db, names: Sequence[str], n: int = 20) -> Dict[str, Any]:
    """Destaques pelos números por jogador dos últimos `n` jogos do time (FotMob/ESPN)."""
    from src.data_hub.gender import comp_sql

    ph = ",".join("?" * len(names))
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(
                f"SELECT p.match_id, p.player_name, p.rating, p.minutes, p.stats_json FROM match_player_stats p "
                f"WHERE p.team_name IN ({ph}) AND p.match_id IN (SELECT m.match_id FROM matches m WHERE "
                f"(m.home_team_name IN ({ph}) OR m.away_team_name IN ({ph})){comp_sql(names, 'm')} "
                f"ORDER BY m.match_date DESC LIMIT {int(n)})", conn, params=list(names) * 3)
    except Exception:
        return {}
    if d.empty:
        return {}
    st = [json.loads(x or "{}") for x in d["stats_json"]]
    d["gols"] = [float(s.get("totalGoals") or 0) for s in st]
    d["assist"] = [float(s.get("goalAssists") or 0) for s in st]
    d["pc"] = [float(s.get("accurate_passes") or 0) for s in st]
    d["pt"] = [float(s.get("accurate_passes_total") or 0) for s in st]
    d["nota"] = pd.to_numeric(d["rating"], errors="coerce")
    d["min"] = pd.to_numeric(d["minutes"], errors="coerce").fillna(0)
    g = d.groupby("player_name")
    agg = pd.DataFrame({"jogos": g["match_id"].nunique(), "gols": g["gols"].sum(), "assist": g["assist"].sum(),
                        "nota": g["nota"].mean(), "min": g["min"].sum(), "pc": g["pc"].sum(), "pt": g["pt"].sum()})
    agg["passe_pct"] = (100 * agg["pc"] / agg["pt"].where(agg["pt"] >= 60))
    motm = d.dropna(subset=["nota"]).sort_values("nota", ascending=False).drop_duplicates("match_id")["player_name"].value_counts()

    def top(col, fmt, min_games=1, cond=None):
        t = agg[agg["jogos"] >= min_games]
        if cond is not None:
            t = t[cond(t)]
        t = t.dropna(subset=[col])
        if t.empty or not (t[col] > 0).any():
            return None
        r = t.sort_values([col, "min"], ascending=False).iloc[0]
        return {"nome": r.name, "valor": fmt(r[col]), "jogos": int(r["jogos"])}
    out = {"usados": int(len(agg)), "jogos": int(d["match_id"].nunique()),
           "melhor_marcador": top("gols", lambda x: f"{int(x)} gol" + ("s" if int(x) != 1 else "")),
           "mais_assistencias": top("assist", lambda x: f"{int(x)} assistência" + ("s" if int(x) != 1 else "")),
           "melhor_nota": top("nota", lambda x: f"nota {x:.2f}", min_games=max(3, int(d['match_id'].nunique() * .3))),
           "mais_passes_pct": top("passe_pct", lambda x: f"{x:.0f}% de passes certos", min_games=3),
           "mais_minutos": top("min", lambda x: f"{int(x)} min")}
    if not motm.empty:
        out["mais_melhor_em_campo"] = {"nome": motm.index[0], "valor": f"{int(motm.iloc[0])}× melhor nota do time no jogo",
                                       "jogos": int(agg.loc[motm.index[0], "jogos"]) if motm.index[0] in agg.index else None}
    return out


def unify_names(m: pd.DataFrame) -> pd.DataFrame:
    """Mesma partida de várias fontes = 1 (`one_per_game`) e o mesmo time com grafias diferentes (Atlético-MG ×
    Atlético Mineiro) vira um nome só — senão a tabela tem 22 times numa liga de 20."""
    from src.ui.pages.search_all import _team_canon, one_per_game

    if m.empty:
        return m
    m = one_per_game(m)
    canon = _team_canon()
    allnames = pd.concat([m["home_team_name"], m["away_team_name"]])
    key = allnames.map(canon)
    rep = allnames.groupby(key).agg(lambda s: s.value_counts().index[0])
    to_rep = {n: rep[canon(n)] for n in allnames.unique()}
    m = m.assign(home_team_name=m["home_team_name"].map(to_rep), away_team_name=m["away_team_name"].map(to_rep))
    m.attrs["rep"] = to_rep
    return m


def position_history(m: pd.DataFrame, names: set) -> List[Dict[str, Any]]:
    """Posição do time na tabela depois de cada jogo dele (temporada em ordem de data). Incremental: soma pontos/saldo
    jogo a jogo e só ordena nas datas em que o time jogou (antes recalculava a tabela inteira a cada data)."""
    m = m.dropna(subset=["home_score", "away_score"]).sort_values("match_date")
    pts: Dict[str, List[int]] = {}
    out = []
    dates = m["match_date"].astype(str).values
    hs, as_ = m["home_score"].astype(int).values, m["away_score"].astype(int).values
    ht, at = m["home_team_name"].values, m["away_team_name"].values
    n = len(m)
    played = {d for d, h, a in zip(dates, ht, at) if h in names or a in names}
    for i in range(n):
        for team, gf, ga in ((ht[i], hs[i], as_[i]), (at[i], as_[i], hs[i])):
            p = pts.setdefault(team, [0, 0, 0])
            p[0] += 3 if gf > ga else 1 if gf == ga else 0
            p[1] += gf - ga
            p[2] += gf
        last_of_day = i == n - 1 or dates[i + 1] != dates[i]
        if last_of_day and dates[i] in played:
            mine = next((t for t in pts if t in names), None)
            if mine is None:
                continue
            key = pts[mine]
            pos = 1 + sum(1 for t, v in pts.items() if t != mine and (v[0], v[1], v[2]) > (key[0], key[1], key[2]))
            out.append({"data": dates[i][:10], "posicao": pos, "times": len(pts)})
    return out


def results_and_fixtures(db, names: Sequence[str], n: int = 4) -> Dict[str, Any]:
    """Últimos resultados e próximos jogos do time (catálogo + calendário ESPN/FotMob)."""
    cat = db.catalog_memo(db.stable_version())
    mine = cat[(cat["home_team_name"].isin(names) | cat["away_team_name"].isin(names)) & cat["home_score"].notna()]
    mine = unify_names(mine.sort_values("match_date", ascending=False).head(n * 3)).sort_values("match_date", ascending=False).head(n)
    res = []
    for r in mine.itertuples():
        home = r.home_team_name in names or r.home_team_name in {mine.attrs.get("rep", {}).get(x, x) for x in names}
        gf, ga = (r.home_score, r.away_score) if home else (r.away_score, r.home_score)
        res.append({"data": str(r.match_date)[:10], "local": "C" if home else "F",
                    "adversario": r.away_team_name if home else r.home_team_name, "placar": f"{int(gf)}–{int(ga)}",
                    "resultado": "V" if gf > ga else "E" if gf == ga else "D", "competicao": r.competition_name,
                    "match_id": int(r.match_id)})
    try:
        from src.squad.matchday import next_fixtures

        fx = next_fixtures(db, list(names), n)
    except Exception:
        fx = pd.DataFrame()
    nxt = [] if fx is None or fx.empty else [
        {"data": str(r.kickoff)[:16].replace("T", " "), "local": "C" if r.home in names else "F",
         "adversario": r.away if r.home in names else r.home, "competicao": r.competition} for r in fx.itertuples()]
    return {"resultados": res, "proximos": nxt}


def team_ranks(db, names: Sequence[str]) -> Dict[str, Any]:
    """Gols marcados/sofridos e pontos na competição/temporada mais recente do time, com a colocação."""
    from src.ui.context import get_service  # noqa: F401 (import tardio só para garantir o catálogo em memória)
    from src.ui.pages.competition import standings

    cat = db.catalog_memo(db.stable_version())
    mine = cat[(cat["home_team_name"].isin(names) | cat["away_team_name"].isin(names)) & cat["home_score"].notna()]
    if mine.empty:
        return {}
    last = mine.sort_values("match_date", ascending=False).iloc[0]
    comp, season = last["competition_name"], last["season_name"]
    m = cat[(cat["competition_name"] == comp) & (cat["season_name"] == season) & cat["home_score"].notna()]
    m = m.sort_values("match_date", ascending=False).head(1200)        # uma temporada tem no máximo ~400 jogos
    m = unify_names(m)
    rep = m.attrs.get("rep", {})
    t = standings(m)
    if t.empty:
        return {}
    mine_names = set(names) | {m_.get(n, n) for m_ in (rep,) for n in names}
    row = t[t["time"].isin(mine_names)]
    if row.empty:
        return {}
    r = row.iloc[0]
    n_t = len(t)
    jj = t["J"].replace(0, np.nan)
    gp_rank = 1 + int(((t["GP"] / jj) > r["GP"] / max(r["J"], 1)).sum())
    gc_rank = 1 + int(((t["GC"] / jj) < r["GC"] / max(r["J"], 1)).sum())
    def lab(k):
        return "Melhor" if k == 1 else "Pior" if k == n_t else f"{k}º melhor"
    hist = position_history(m, set(names) | {m.attrs.get("rep", {}).get(x, x) for x in names})
    return {"historico_posicao": hist, "competicao": comp, "temporada": season, "posicao": int(r["#"]), "times": n_t, "pontos": int(r["P"]),
            "jogos": int(r["J"]), "gols_pro": int(r["GP"]), "gols_pro_rank": lab(gp_rank), "gols_contra": int(r["GC"]),
            "gols_contra_rank": lab(gc_rank), "tabela": t}


def squad_facts(roster: pd.DataFrame, universe: Optional[pd.DataFrame], liga: str = "") -> List[Dict[str, Any]]:
    """'Factos' do elenco atual (FotMob) e a média da liga (universo do Scout) ao lado."""
    if roster is None or roster.empty:
        return []
    r = roster.copy()
    birth = pd.to_datetime(r.get("birth"), errors="coerce")
    r["idade"] = ((pd.Timestamp(date.today()) - birth).dt.days / 365.25)
    r["alt"] = pd.to_numeric(r.get("height"), errors="coerce").where(lambda x: x.between(150, 215))
    r["val"] = pd.to_numeric(r.get("market_value"), errors="coerce")
    nat = r.get("country", pd.Series("", index=r.index)).fillna("").astype(str)
    lg = pd.DataFrame()
    if universe is not None and liga and "clube_liga" in universe:
        lg = universe[universe["clube_liga"].astype(str) == liga]

    def fmt_age(a):
        return f"{int(a)} anos" if a == a else "—"

    def who(col, fn):
        t = r.dropna(subset=[col])
        if t.empty:
            return "—"
        x = t.loc[getattr(t[col], fn)()]
        return x
    out = []
    if r["idade"].notna().any():
        yo, ol = who("idade", "idxmin"), who("idade", "idxmax")
        out.append({"fato": "Jogador mais jovem", "a": f"{fmt_age(yo['idade'])} — {yo['name']}", "b": ""})
        out.append({"fato": "Jogador mais velho", "a": f"{fmt_age(ol['idade'])} — {ol['name']}", "b": ""})
        lg_age = pd.to_numeric(lg.get("idade"), errors="coerce").mean() if not lg.empty else np.nan
        out.append({"fato": "Média de idades", "a": f"{r['idade'].mean():.1f}", "b": f"{lg_age:.1f}" if lg_age == lg_age else "—"})
    if r["alt"].notna().any():
        lo, hi = who("alt", "idxmin"), who("alt", "idxmax")
        out.append({"fato": "Jogador mais baixo", "a": f"{lo['alt']:.0f} cm — {lo['name']}", "b": ""})
        out.append({"fato": "Jogador mais alto", "a": f"{hi['alt']:.0f} cm — {hi['name']}", "b": ""})
        lg_h = pd.to_numeric(lg.get("altura_cm"), errors="coerce").mean() if not lg.empty else np.nan
        out.append({"fato": "Altura média", "a": f"{r['alt'].mean():.0f} cm", "b": f"{lg_h:.0f} cm" if lg_h == lg_h else "—"})
    if r["val"].notna().any():
        mv = who("val", "idxmax")
        out.append({"fato": "Mais valioso", "a": f"€ {mv['val'] / 1e6:.1f} mi — {mv['name']}", "b": ""})
        lg_v = pd.to_numeric(lg.get("valor_mercado_eur"), errors="coerce").mean() if not lg.empty else np.nan
        out.append({"fato": "Valor médio", "a": f"€ {r['val'].mean() / 1e6:.1f} mi",
                    "b": f"€ {lg_v / 1e6:.1f} mi" if lg_v == lg_v else "—"})
    if nat.str.len().gt(0).any():
        top_nat = nat[nat != ""].value_counts()
        out.append({"fato": "Nacionalidades representadas", "a": str(int(top_nat.size)), "b": ""})
        out.append({"fato": "Tendência para jogadores nacionais", "a": f"{100 * top_nat.iloc[0] / top_nat.sum():.0f}% ({top_nat.index[0]})", "b": ""})
    lesoes = r[r.get("lesao", pd.Series("", index=r.index)).fillna("").astype(str) != ""]
    out.append({"fato": "Lesionados agora", "a": str(len(lesoes)), "b": ""})
    return out


def coach_profile(ident: Dict[str, Any]) -> Dict[str, Any]:
    """Treinador, desenho preferido, mentalidade (pela posse) e tipo de pressão (pelo PPDA) — com a base."""
    cur = ident.get("treinador_atual") or {}
    st_ = ident.get("estatisticas") or {}
    p, ref = st_.get("perfil") or {}, st_.get("referencia") or {}
    ment, press = "—", "—"
    if p.get("posse_pct") is not None and ref.get("posse_pct"):
        d = p["posse_pct"] - ref["posse_pct"]
        ment = "Proativa (quer a bola)" if d >= 5 else "Cautelosa (abre mão da bola)" if d <= -5 else "Equilibrada"
    m = (ident.get("lances") or {}).get("medias") or {}
    ppda = m.get("ppda") if m.get("ppda") is not None else p.get("ppda_aprox")
    ref_ppda = ref.get("ppda_aprox")
    if ppda is not None and ref_ppda:
        press = ("Com mais frequência (pressiona alto)" if ppda <= ref_ppda * .85 else
                 "Raramente (espera atrás)" if ppda >= ref_ppda * 1.15 else "Moderada")
    return {"treinador": cur.get("treinador") or "não informado pela fonte", "desde": cur.get("de"),
            "jogos": cur.get("jogos"), "formacao": cur.get("desenho_mais_usado") or "—", "mentalidade": ment,
            "pressao": press, "ppda": ppda}


def report(db, names: Sequence[str], n: int = 20) -> Dict[str, Any]:
    from src.analytics import tactical_identity as TI

    names = list(dict.fromkeys(names))
    ident = TI.identity(db, names, n)
    for c in ident.get("treinadores") or []:
        c.pop("match_ids", None)
    out = {"forcas": strengths_weaknesses(db, names, n), "jogadores": key_players(db, names, n),
           "treinador": coach_profile(ident), "identidade_resumo": ident.get("resumo") or []}
    try:
        out["ranks"] = team_ranks(db, names)
    except Exception:
        out["ranks"] = {}
    try:
        out["calendario"] = results_and_fixtures(db, names)
    except Exception:
        out["calendario"] = {}
    return out
