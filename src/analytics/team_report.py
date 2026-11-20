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


def season_start(season_name: Any, last_date: Any) -> Optional[str]:
    """Início da temporada: "2025/2026" → 01/07/2025; "2026" → 01/01/2026; sem nome → None."""
    import re

    s = str(season_name or "")
    m = re.search(r"(20\d\d)\s*[/-]\s*(20)?\d\d", s)
    if m:
        return f"{m.group(1)}-07-01"
    m = re.search(r"(20\d\d)", s)
    if m:
        return f"{m.group(1)}-01-01"
    d = pd.to_datetime(last_date, errors="coerce")
    return None if pd.isna(d) else f"{d.year}-01-01"


def team_games_with_players(db, names: Sequence[str], limit: int = 160) -> pd.DataFrame:
    """Jogos do time QUE TÊM números por jogador dele, um por partida real (a mesma partida em duas fontes conta 1:
    fica a versão com mais atletas medidos)."""
    from src.data_hub.gender import comp_sql
    from src.data_lake.ids import team_core

    ph = ",".join("?" * len(names))
    with db.connect() as conn:
        m = pd.read_sql_query(
            f"""SELECT m.match_id, m.match_date, m.season_name, m.competition_name, m.home_team_name, m.away_team_name,
                       (SELECT COUNT(*) FROM match_player_stats p WHERE p.match_id = m.match_id AND p.team_name IN ({ph})) AS n_pl
                FROM matches m WHERE (m.home_team_name IN ({ph}) OR m.away_team_name IN ({ph})){comp_sql(names, 'm')}
                  AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
                ORDER BY m.match_date DESC LIMIT {int(limit) * 3}""", conn, params=list(names) * 3)
    m = m[m["n_pl"] > 0].copy()
    if m.empty:
        return m
    own = {team_core(x) for x in names}
    other = [team_core(a) if team_core(h) in own else team_core(h) for h, a in zip(m["home_team_name"], m["away_team_name"])]
    day = pd.to_datetime(m["match_date"], errors="coerce").dt.normalize()
    m["_key"] = [f"{o}|{d.toordinal() // 2 if pd.notna(d) else i}" for i, (o, d) in enumerate(zip(other, day))]
    m = m.sort_values("n_pl", ascending=False).drop_duplicates("_key").sort_values("match_date", ascending=False)
    return m.head(int(limit))


def key_players(db, names: Sequence[str], n: int = 30, scope: str = "auto") -> Dict[str, Any]:
    """Destaques pelos números por jogador do time (FotMob/ESPN). Rodada 24: recorte coerente com a página —
    a TEMPORADA atual (se já tem ≥ 8 jogos medidos) ou os últimos `n` jogos medidos; cada partida conta uma vez e cada
    atleta é um só (grafias diferentes juntas pelo núcleo do nome). Antes: "últimos 20 jogos" incluíam jogos sem
    números por jogador e duplicatas de fonte → "28 usados em 5 jogos", Raphinha com 5 gols."""
    from src.data_lake.ids import player_core

    names = list(names)
    try:
        games = team_games_with_players(db, names)
    except Exception:
        return {}
    if games.empty:
        return {}
    start = season_start(games.iloc[0]["season_name"], games.iloc[0]["match_date"])
    season_games = games[games["match_date"].astype(str) >= start] if start else games.iloc[0:0]
    if scope == "season" or (scope == "auto" and len(season_games) >= 8):
        chosen, label = season_games, f"temporada atual (desde {pd.to_datetime(start):%d/%m/%Y})"
    else:
        chosen, label = games.head(int(n)), f"últimos {min(int(n), len(games))} jogos com números por jogador"
    ids = [int(x) for x in chosen["match_id"]]
    ph, phn = ",".join("?" * len(ids)), ",".join("?" * len(names))
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(
                f"SELECT p.match_id, p.player_name, p.rating, p.minutes, p.stats_json FROM match_player_stats p "
                f"WHERE p.match_id IN ({ph}) AND p.team_name IN ({phn})", conn, params=ids + names)
    except Exception:
        return {}
    if d.empty:
        return {}
    st_ = [json.loads(x or "{}") for x in d["stats_json"]]

    def num(s, *keys):
        for k in keys:
            v = s.get(k)
            if v not in (None, ""):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return 0.0
    d["gols"] = [num(s, "totalGoals", "goals") for s in st_]
    d["assist"] = [num(s, "goalAssists", "assists", "goal_assist") for s in st_]
    d["pc"] = [num(s, "accurate_passes") for s in st_]
    d["pt"] = [num(s, "accurate_passes_total") for s in st_]
    d["nota"] = pd.to_numeric(d["rating"], errors="coerce")
    d["min"] = pd.to_numeric(d["minutes"], errors="coerce").fillna(0)
    d = d[d["min"] > 0]
    d["_core"] = d["player_name"].map(player_core)
    d = d.sort_values("min", ascending=False).drop_duplicates(["match_id", "_core"])
    shown = d.groupby("_core")["player_name"].agg(lambda v: max(v.value_counts().index[:2], key=len))
    g = d.groupby("_core")
    agg = pd.DataFrame({"jogos": g["match_id"].nunique(), "gols": g["gols"].sum(), "assist": g["assist"].sum(),
                        "nota": g["nota"].mean(), "min": g["min"].sum(), "pc": g["pc"].sum(), "pt": g["pt"].sum()})
    agg.index = agg.index.map(shown)
    agg["passe_pct"] = (100 * agg["pc"] / agg["pt"].where(agg["pt"] >= 60))
    best = d.dropna(subset=["nota"]).sort_values("nota", ascending=False).drop_duplicates("match_id")
    motm = best["_core"].map(shown).value_counts()
    n_games = int(d["match_id"].nunique())

    def top(col, fmt, min_games=1, cond=None):
        t = agg[agg["jogos"] >= min_games]
        if cond is not None:
            t = t[cond(t)]
        t = t.dropna(subset=[col])
        if t.empty or not (t[col] > 0).any():
            return None
        r = t.sort_values([col, "min"], ascending=False).iloc[0]
        return {"nome": r.name, "valor": fmt(r[col]), "jogos": int(r["jogos"])}
    out = {"usados": int(len(agg)), "jogos": n_games, "recorte": label,
           "melhor_marcador": top("gols", lambda x: f"{int(x)} gol" + ("s" if int(x) != 1 else "")),
           "mais_assistencias": top("assist", lambda x: f"{int(x)} assistência" + ("s" if int(x) != 1 else "")),
           "melhor_nota": top("nota", lambda x: f"nota {x:.2f}", min_games=max(3, int(n_games * .3))),
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


def main_competition(db, names: Sequence[str], days: int = 400) -> str:
    """Liga do time = competição com mais jogos dele no último ano (copas e seleções ficam atrás)."""
    from src.data_hub.gender import comp_sql

    ph = ",".join("?" * len(names))
    since = (pd.Timestamp.today() - pd.Timedelta(days=days)).date().isoformat()
    try:
        with db.connect() as conn:
            c = pd.read_sql_query(
                f"SELECT competition_name AS comp, COUNT(*) AS n FROM matches WHERE match_date >= ? AND "
                f"(home_team_name IN ({ph}) OR away_team_name IN ({ph})){comp_sql(names, '')} GROUP BY competition_name "
                f"ORDER BY n DESC", conn, params=[since, *names, *names])
    except Exception:
        return ""
    if c.empty:
        return ""
    cups = c["comp"].astype(str).str.lower().str.contains("copa|cup|pokal|coupe|coppa|taça|libertadores|champions|europa|"
                                                             "sudamericana|super|amistos|friendl")
    league = c[~cups]
    return str((league if not league.empty else c).iloc[0]["comp"])


def league_rosters(db, competition: str, days: int = 400) -> pd.DataFrame:
    """Elencos inscritos (FotMob) dos clubes que jogaram a competição no último ano — a média da liga vem daqui,
    não do cadastro antigo (que tinha aposentados e reservas de 10 anos atrás: média de 31,2 anos em La Liga)."""
    if not competition:
        return pd.DataFrame()
    since = (pd.Timestamp.today() - pd.Timedelta(days=days)).date().isoformat()
    try:
        with db.connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'fotmob_rosters'").fetchone():
                return pd.DataFrame()
            teams = pd.read_sql_query(
                "SELECT DISTINCT home_team_name AS t FROM matches WHERE competition_name = ? AND match_date >= ? "
                "UNION SELECT DISTINCT away_team_name FROM matches WHERE competition_name = ? AND match_date >= ?",
                conn, params=[competition, since, competition, since])
            ro = pd.read_sql_query("SELECT team, player_id, birth, height, market_value, country, fetched_at FROM fotmob_rosters", conn)
    except Exception:
        return pd.DataFrame()
    if teams.empty or ro.empty:
        return pd.DataFrame()
    from src.data_lake.ids import team_core

    want = {team_core(str(t)) for t in teams["t"].dropna()}
    ro = ro[ro["team"].fillna("").map(lambda t: team_core(str(t)) in want)]
    return ro.sort_values("fetched_at").drop_duplicates("player_id", keep="last")


def squad_facts(roster: pd.DataFrame, universe: Optional[pd.DataFrame], liga: str = "",
                league_roster: Optional[pd.DataFrame] = None) -> List[Dict[str, Any]]:
    """'Factos' do elenco atual (FotMob) e a média da liga ao lado. Rodada 24: média da liga pelos ELENCOS INSCRITOS
    dos clubes da competição (`league_roster`); sem eles, só atletas do universo com minutos no último ano."""
    if roster is None or roster.empty:
        return []
    r = roster.copy()
    birth = pd.to_datetime(r.get("birth"), errors="coerce")
    r["idade"] = ((pd.Timestamp(date.today()) - birth).dt.days / 365.25)
    r["alt"] = pd.to_numeric(r.get("height"), errors="coerce").where(lambda x: x.between(150, 215))
    r["val"] = pd.to_numeric(r.get("market_value"), errors="coerce")
    nat = r.get("country", pd.Series("", index=r.index)).fillna("").astype(str)
    lg = pd.DataFrame()
    if league_roster is not None and not league_roster.empty:
        lb = pd.to_datetime(league_roster.get("birth"), errors="coerce")
        lg = pd.DataFrame({"idade": ((pd.Timestamp(date.today()) - lb).dt.days / 365.25),
                           "altura_cm": pd.to_numeric(league_roster.get("height"), errors="coerce").where(
                               lambda x: x.between(150, 215)),
                           "valor_mercado_eur": pd.to_numeric(league_roster.get("market_value"), errors="coerce")})
    elif universe is not None and liga and "clube_liga" in universe:
        lg = universe[universe["clube_liga"].astype(str) == liga]
        m12 = pd.to_numeric(lg.get("minutos_12m"), errors="coerce").fillna(0)
        lg = lg[m12 > 0]                                   # só quem jogou no último ano (sem aposentados do cadastro)

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
    out = {"forcas": strengths_weaknesses(db, names, n), "jogadores": key_players(db, names, max(n, 30)),
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
