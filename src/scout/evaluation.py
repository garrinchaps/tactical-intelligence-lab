"""
Rodada 16 — AVALIAÇÃO DE JOGADORES em várias perguntas separadas (diagnóstico em docs/DIAGNOSTICO_AVALIACAO.md).

Uma nota única misturava produção, fama de mercado, nível do clube e potencial. Aqui cada pergunta tem a SUA avaliação,
com amostra mínima própria, e nada é obrigatório: cada função usa só as métricas que a competição dele realmente tem.

Pipeline (só dados da base; nada inventado):
  1. jogo a jogo (`player_games`): números por jogador (FotMob/ESPN), titular × reserva, adversário, casa/fora, posse do
     próprio time no jogo, força do adversário (PageRank da competição);
  2. uso (`usage`): jogos, minutos, titularidades, entradas, % dos minutos do time;
  3. produção por 90 com AJUSTE DE POSSE nas ações defensivas e FATIA do jogador na produção do time;
  4. percentil DENTRO da mesma função e da mesma competição (métrica ausente = não avaliada, pesos redistribuídos);
  5. avaliações: desempenho por 90 · temporada · regularidade · impacto · contra fortes · potencial · revelação ·
     custo-benefício · geral entre ligas (ajuste de nível ESTIMADO);
  6. função tática pelo perfil de ações; pontos fortes, limitações e o que "não é observado" com os dados abertos.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

OUT_PATH = Path("data/processed/evaluations.parquet")
META_PATH = Path("data/processed/evaluations.json")

# chave curta → (chave na FotMob, rótulo em português, maior é melhor?)
METRICS: Dict[str, tuple] = {
    "goals": ("totalGoals", "gols", True), "assists": ("goalAssists", "assistências", True),
    "xg": ("xg", "xG", True), "xa": ("xa", "xA (assistência esperada)", True),
    "shots": ("totalShots", "finalizações", True), "sot": ("shotsOnTarget", "finalizações no alvo", True),
    "chances": ("chances_created", "chances criadas", True), "drb": ("dribbles_succeeded", "dribles certos", True),
    "drb_t": ("dribbles_succeeded_total", "dribles tentados", True), "tob": ("touches_opp_box", "toques na área rival", True),
    "ft3": ("passes_into_final_third", "passes para o terço final", True),
    "lbp": ("line_breaking_passes", "passes que quebram linhas", True),
    "pass": ("accurate_passes", "passes certos", True), "pass_t": ("accurate_passes_total", "passes tentados", True),
    "lb": ("long_balls_accurate", "bolas longas certas", True), "crs": ("accurate_crosses", "cruzamentos certos", True),
    "rec": ("recoveries", "recuperações", True), "int": ("interceptions", "interceptações", True),
    "tkl": ("matchstats.headers.tackles", "desarmes", True), "clr": ("clearances", "cortes", True),
    "blk": ("shot_blocks", "bloqueios de chute", True), "aer": ("aerials_won", "duelos aéreos ganhos", True),
    "aer_t": ("aerials_won_total", "duelos aéreos disputados", True), "duel_w": ("duel_won", "duelos ganhos", True),
    "duel_l": ("duel_lost", "duelos perdidos", False), "drb_past": ("dribbled_past", "vezes driblado", False),
    "disp": ("dispossessed", "perdas de posse no drible", False), "fouled": ("was_fouled", "faltas sofridas", True),
    "saves": ("saves", "defesas", True), "prevented": ("goals_prevented", "gols evitados", True),
    "err": ("errors_led_to_goal", "erros que viraram gol", False),
}
LABEL = {k: v[1] for k, v in METRICS.items()}
LABEL.update({"pass_pct": "% de passes certos", "drb_pct": "% de dribles certos", "aer_pct": "% de duelos aéreos ganhos",
              "duel_pct": "% de duelos ganhos", "def_adj": "ações defensivas (ajustadas pela posse)",
              "share_att": "fatia da produção ofensiva do time", "rating": "nota média da FotMob"})

FAMILY_OF = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "DM": "DM", "CM": "CM",
             "AM": "AM", "LM": "WIDE", "RM": "WIDE", "LW": "WIDE", "RW": "WIDE", "ST": "ST", "CF": "ST"}
FAMILY_PT = {"GK": "goleiro", "CB": "zagueiro", "FB": "lateral", "DM": "volante", "CM": "meia central",
             "AM": "meia ofensivo", "WIDE": "ponta", "ST": "centroavante"}
# pesos por família (métricas "_p90" por 90 minutos; "_pct" eficiência). Só entram as disponíveis.
WEIGHTS = {
    "GK": {"prevented_p90": .45, "saves_p90": .25, "pass_pct": .15, "err_p90": .15},
    "CB": {"aer_pct": .14, "aer_p90": .08, "def_adj": .16, "clr_p90": .08, "blk_p90": .05, "duel_pct": .14,
           "lbp_p90": .14, "pass_pct": .1, "drb_past_p90": .07, "err_p90": .04},
    "FB": {"chances_p90": .14, "xa_p90": .1, "crs_p90": .08, "ft3_p90": .1, "def_adj": .16, "duel_pct": .12,
           "drb_past_p90": .1, "pass_pct": .1, "drb_p90": .05, "aer_pct": .05},
    "DM": {"def_adj": .2, "duel_pct": .12, "lbp_p90": .15, "pass_pct": .15, "ft3_p90": .12, "drb_past_p90": .08,
           "aer_pct": .06, "chances_p90": .07, "err_p90": .05},
    "CM": {"lbp_p90": .14, "ft3_p90": .14, "chances_p90": .14, "xa_p90": .1, "pass_pct": .1, "def_adj": .12,
           "duel_pct": .08, "xg_p90": .08, "drb_p90": .05, "goals_p90": .05},
    "AM": {"chances_p90": .18, "xa_p90": .18, "xg_p90": .14, "goals_p90": .1, "drb_p90": .1, "tob_p90": .1,
           "ft3_p90": .1, "assists_p90": .05, "disp_p90": .05},
    "WIDE": {"xg_p90": .14, "goals_p90": .14, "xa_p90": .14, "chances_p90": .14, "drb_p90": .14, "drb_pct": .05,
             "tob_p90": .1, "assists_p90": .08, "crs_p90": .04, "disp_p90": .03},
    "ST": {"goals_p90": .22, "xg_p90": .2, "sot_p90": .1, "tob_p90": .1, "xa_p90": .08, "chances_p90": .07,
           "assists_p90": .05, "aer_pct": .06, "duel_pct": .05, "rec_p90": .04, "fouled_p90": .03},
}
NOT_OBSERVED = ["pressão sem a bola", "movimentação sem a bola", "posicionamento defensivo", "velocidade e distância"
                " percorrida (só onde a liga mede)"]

# nível das competições — ESTIMATIVA declarada (0–1), refinada pelos jogadores que atuaram em duas competições
TIERS = [
    (r"champions league", 1.0), (r"premier league", 1.0), (r"la ?liga", .96), (r"^bundesliga|germany.*bundesliga", .95),
    (r"brasileir[aã]o s[ée]rie a|campeonato brasileiro s[ée]rie a", .8),
    (r"brasileir[aã]o s[ée]rie b|campeonato brasileiro s[ée]rie b", .6),
    (r"brasileir[aã]o s[ée]rie c|campeonato brasileiro s[ée]rie c", .48),
    (r"^serie a$|italy|it[aá]lia", .93), (r"ligue 1", .9), (r"europa league", .9), (r"primeira liga|liga portugal", .82),
    (r"eredivisie", .8), (r"libertadores", .82),
    # rodada 27: Arábia/Emirados/Catar ANTES da liga belga — "Saudi Pro League" e "Emirados — Pro League" caíam em
    # "pro league" (Bélgica, 0,76) e os veteranos de lá subiam na lista dos melhores do mundo
    (r"saudi|ar[aá]bia", .64), (r"emirados|emirates|\buae\b|catar|qatar|stars league", .52),
    (r"championship", .78), (r"conference league", .78), (r"jupiler|b[ée]lgica|belgian|^pro league$", .76),
    (r"copa do brasil", .75), (r"s[üu]per lig|turquia", .75), (r"liga profesional|argentina", .74),
    (r"sul-americana|sudamericana", .72), (r"liga mx|m[ée]xico", .72), (r"\bmls\b|major league", .7),
    (r"s[ée]rie b", .6), (r"primera nacional", .55), (r"s[ée]rie c", .48),
    (r"s[ée]rie d", .38), (r"paragu|urugu|chile|col[ôo]mbia|equador|ecuador|peru", .6), (r"bol[ií]via|venezuela", .5),
]


def _fold(s: Any) -> str:
    # rodada 27: "premier-league"/"super-lig" (endereço do Transfermarkt) viram "premier league"/"super lig" — antes
    # não batiam com nenhuma regra e a Premier League ficava com o nível padrão (0,60, igual à Série B)
    t = unicodedata.normalize("NFKD", str(s or "").lower()).encode("ascii", "ignore").decode()
    return " ".join(t.replace("-", " ").replace("_", " ").split())


def prior_level(comp: str) -> float:
    c = _fold(comp)
    for pat, v in TIERS:
        if re.search(_fold(pat), c):
            return v
    return .6


# ------------------------------------------------------------------ 1. jogo a jogo
def player_games(db, days: int = 400) -> pd.DataFrame:
    from src.data_hub.gender import comp_sql

    since = (date.today() - timedelta(days=int(days))).isoformat()
    cols = ", ".join(f"json_extract(p.stats_json, '$.\"{k}\"') AS {short}" for short, (k, _, _) in METRICS.items())
    q = f"""SELECT p.match_id, p.team_name, p.player_name, p.position, p.minutes, p.rating, {cols},
                   m.match_date, m.competition_name AS comp, m.season_name AS season, m.home_team_name, m.away_team_name,
                   m.home_score, m.away_score, l.starter, l.lpos, s.value AS team_poss
            FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id
            LEFT JOIN (SELECT match_id, player_name, MAX(is_starter) AS starter, MAX(position) AS lpos FROM match_lineups
                       WHERE match_id IN (SELECT match_id FROM matches WHERE match_date >= ?)
                       GROUP BY match_id, player_name) l ON l.match_id = p.match_id AND l.player_name = p.player_name
            LEFT JOIN match_team_stats s ON s.match_id = p.match_id AND s.team_name = p.team_name
                   AND s.stat_key = 'possession_pct'
            WHERE m.match_date >= ? AND COALESCE(p.minutes, 0) > 0{comp_sql([], "m")}
              AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')"""
    with db.connect() as conn:
        g = pd.read_sql_query(q, conn, params=[since, since])
    if g.empty:
        return g
    from src.data_lake.ids import player_core, team_core
    from src.squad.formations import natural_role
    from src.squad.planner import national_team_key

    g = g[~g["team_name"].map(lambda t: bool(national_team_key(str(t or ""))))].copy()   # seleção não entra
    g["core"] = g["player_name"].map(player_core)
    g["day"] = g["match_date"].astype(str).str[:10]
    num = list(METRICS) + ["minutes", "rating", "team_poss"]
    for c in num:
        g[c] = pd.to_numeric(g[c], errors="coerce")
    # mesmo jogo em duas fontes (ESPN e FotMob): fica a linha com mais números
    g["_n"] = g[list(METRICS)].notna().sum(axis=1)
    g = g.sort_values(["_n", "minutes"], ascending=False).drop_duplicates(["core", "day"]).drop(columns="_n")
    home = g["team_name"].map(team_core) == g["home_team_name"].map(team_core)
    g["home"] = home
    g["opponent"] = np.where(home, g["away_team_name"], g["home_team_name"])
    gf = np.where(home, g["home_score"], g["away_score"]).astype(float)
    ga = np.where(home, g["away_score"], g["home_score"]).astype(float)
    g["result"] = np.where(gf > ga, "V", np.where(gf == ga, "E", "D"))
    g["starter"] = pd.to_numeric(g["starter"], errors="coerce")
    g["starter"] = g["starter"].fillna((g["minutes"] >= 60).astype(float))   # sem escalação: 60+ min ≈ titular
    # posição: a da ESCALAÇÃO (desenho do jogo) primeiro; a do número por jogador só se não houver; "D?/M?/F?" = só setor
    pos = g["lpos"].where(g["lpos"].notna() & (g["lpos"].astype(str).str.strip() != ""), g["position"])
    g["role"] = pos.map(lambda p: natural_role(str(p or ""), str(p or "")))
    g.loc[g["role"].astype(str).str.endswith("?"), "role"] = ""
    return g.reset_index(drop=True)


def opponent_strength(db, comps: Sequence[str], days: int = 400) -> Dict[tuple, float]:
    """Força 0–100 de cada time POR competição (PageRank dos resultados), para classificar o adversário de cada jogo."""
    from src.analytics.pagerank import team_strength

    since = (date.today() - timedelta(days=int(days))).isoformat()
    out: Dict[tuple, float] = {}
    comps = [c for c in dict.fromkeys(comps) if c]
    if not comps:
        return out
    ph = ",".join("?" * len(comps))
    with db.connect() as conn:
        m = pd.read_sql_query(f"SELECT competition_name AS comp, home_team_name, away_team_name, home_score, away_score "
                              f"FROM matches WHERE match_date >= ? AND competition_name IN ({ph}) AND home_score IS NOT NULL",
                              conn, params=[since, *comps])
    for comp, grp in m.groupby("comp"):
        st = team_strength(grp)
        for r in st.itertuples():
            out[(comp, r.time)] = float(r.forca_pagerank)
    return out


# ------------------------------------------------------------------ 2–3. uso + produção
def aggregate(g: pd.DataFrame, strength: Dict[tuple, float]) -> pd.DataFrame:
    if g.empty:
        return pd.DataFrame()
    g = g.copy()
    g["opp_str"] = [strength.get((c, o)) for c, o in zip(g["comp"], g["opponent"])]
    # adversário forte = terço de cima da força na competição
    g["opp_rank"] = g.groupby("comp")["opp_str"].rank(pct=True)
    g["vs_strong"] = g["opp_rank"] >= 2 / 3
    g["vs_weak"] = g["opp_rank"] <= 1 / 3
    # fatia da produção ofensiva do time em cada jogo (xG + xA)
    g["att"] = g["xg"].fillna(0) + g["xa"].fillna(0)
    team_att = g.groupby(["match_id", "team_name"])["att"].transform("sum")
    g["share_att_g"] = np.where(team_att > 0, g["att"] / team_att, np.nan)
    g["team_rating"] = g.groupby(["match_id", "team_name"])["rating"].transform("mean")
    # ações defensivas ajustadas pela posse: quem defende pouco porque o time tem a bola não é punido
    poss_opp = (100 - g["team_poss"]).clip(lower=20)
    defs = g[["tkl", "int", "rec"]].sum(axis=1, min_count=1)
    g["def_raw"] = defs
    g["def_adj_g"] = np.where(g["team_poss"].notna(), defs * 50 / poss_opp, defs)
    key = ["core", "comp", "season", "team_name"]
    G = g.groupby(key, sort=False)
    out = G.agg(player_name=("player_name", lambda x: x.mode().iat[0]), games=("match_id", "size"),
                minutes=("minutes", "sum"), starts=("starter", lambda x: int((x >= 1).sum())),
                last_game=("day", "max")).reset_index()
    out["subs"] = out["games"] - out["starts"]
    role_mode = g[g["role"].astype(str) != ""].groupby(key)["role"].agg(lambda x: x.mode().iat[0])
    out["role"] = pd.Series(out.set_index(key).index.map(role_mode), index=out.index).fillna("")
    # rodada 19: só entrou do banco nesta competição → usa a posição dele nos OUTROS jogos (qualquer competição)
    core_mode = g[g["role"].astype(str) != ""].groupby("core")["role"].agg(lambda x: x.mode().iat[0])
    blank = out["role"] == ""
    out.loc[blank, "role"] = out.loc[blank, "core"].map(core_mode).fillna("")
    out["family"] = out["role"].map(FAMILY_OF).fillna("")
    tg = g.groupby(["comp", "season", "team_name"])["match_id"].nunique()
    out["team_games"] = pd.Series(out.set_index(["comp", "season", "team_name"]).index.map(tg), index=out.index
                                  ).fillna(out["games"]).astype(int)
    out["min_share"] = (out["minutes"] / (out["team_games"] * 90).clip(lower=1)).clip(upper=1).round(3)
    # números: a fonte publica a métrica para o jogador? então ausente no jogo = 0 (a FotMob omite zero)
    has_any = g[list(METRICS)].notna().any(axis=1)
    g["_cov_min"] = g["minutes"].where(has_any, 0)
    cov = G["_cov_min"].sum().values
    for m in METRICS:
        published = G[m].count().values > 0
        tot = G[m].sum(min_count=1).fillna(0).values
        out[f"{m}_tot"] = np.where(published, tot, np.nan)
        out[f"{m}_p90"] = np.where(published, tot * 90 / np.clip(cov, 1, None), np.nan)
    def ratio(a, b, minimum=5):
        ta, tb = out[f"{a}_tot"], out[f"{b}_tot"]
        return (100 * ta / tb).where(tb >= minimum)
    out["pass_pct"], out["drb_pct"], out["aer_pct"] = ratio("pass", "pass_t"), ratio("drb", "drb_t"), ratio("aer", "aer_t")
    dsum = out["duel_w_tot"] + out["duel_l_tot"]
    out["duel_pct"] = (100 * out["duel_w_tot"] / dsum).where(dsum >= 10)
    dmin = g["minutes"].where(g["def_adj_g"].notna(), 0)
    g["_dw"] = g["def_adj_g"].fillna(0)
    out["def_adj"] = (G["_dw"].sum().values * 90 / np.clip(g.assign(_dm=dmin).groupby(key, sort=False)["_dm"].sum().values,
                                                          1, None))
    out.loc[g.assign(_dm=dmin).groupby(key, sort=False)["_dm"].sum().values <= 0, "def_adj"] = np.nan
    out["share_att"] = G["share_att_g"].mean().values
    rated = g[(g["minutes"] >= 20) & g["rating"].notna()]
    R = rated.groupby(key)
    _idx = out.set_index(key).index

    class _I:                                         # idx.map(...) devolvendo Series alinhada a `out`
        @staticmethod
        def map(obj):
            return pd.Series(_idx.map(obj), index=out.index)

    idx = _I()
    out["rating"] = idx.map(R["rating"].mean())
    out["rating_sd"] = idx.map(R["rating"].std()).where(idx.map(R.size()).fillna(0) >= 3)
    out["rating_games"] = idx.map(R.size()).fillna(0).astype(int)
    out["good_games"] = idx.map(rated.assign(_g=rated["rating"] >= 7.0).groupby(key)["_g"].sum()).fillna(0).astype(int)
    out["rating_vs_team"] = idx.map((rated["rating"] - rated["team_rating"]).groupby([rated[k] for k in key]).mean())
    g["_ga"] = g["goals"].fillna(0) + g["assists"].fillna(0)
    for tag, mask in (("strong", g["vs_strong"]), ("weak", g["vs_weak"]), ("home", g["home"]), ("away", ~g["home"])):
        part = g[mask & (g["minutes"] >= 20)]
        P = part.groupby(key)
        out[f"games_{tag}"] = idx.map(P.size()).fillna(0).astype(int)
        out[f"rating_{tag}"] = idx.map(P["rating"].mean())
        pm = idx.map(P["minutes"].sum())
        out[f"ga90_{tag}"] = idx.map(P["_ga"].sum()) * 90 / pm.where(pm > 0)
    last5 = rated.sort_values("day").groupby(key).tail(5).groupby(key)
    l5 = idx.map(last5["rating"].mean())
    n5 = idx.map(last5.size()).fillna(0)
    out["trend"] = (l5 - out["rating"]).where(n5 >= 3)
    out["n_metrics"] = out[[f"{m}_p90" for m in METRICS]].notna().sum(axis=1)
    return out


# ------------------------------------------------------------------ 4. percentis e avaliações
def _pct_within(df: pd.DataFrame, col: str, by: List[str], higher: bool = True) -> pd.Series:
    v = pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(np.nan, index=df.index)
    p = v.groupby([df[b] for b in by]).rank(pct=True) * 100
    return p if higher else 100 - p


def league_factors(players: pd.DataFrame) -> pd.DataFrame:
    """Nível de cada competição: estimativa prévia (TIERS) corrigida pelos MESMOS jogadores que atuaram em duas
    competições na janela (diferença de nota média FotMob, ≥ 270 min em cada). Encolhida para a estimativa prévia pelo
    número de pares: com poucos pares, vale a estimativa; com muitos, os dados."""
    comps = sorted(players["comp"].dropna().unique())
    prior = {c: prior_level(c) for c in comps}
    p = players[(players["minutes"] >= 270) & players["rating"].notna()]
    pairs: Dict[str, List[float]] = {c: [] for c in comps}
    for core, x in p.groupby("core"):
        if x["comp"].nunique() < 2:
            continue
        xs = x.groupby("comp")["rating"].mean()
        mean = xs.mean()
        for c, v in xs.items():
            # nota acima da média do próprio jogador = competição mais fácil para ele
            pairs[c].append(float(v - mean))
    rows = []
    for c in comps:
        d = pairs[c]
        n = len(d)
        est = prior[c] - 0.25 * float(np.mean(d)) if n else prior[c]   # +0,4 de nota ≈ −0,1 de nível
        w = n / (n + 20)
        lvl = float(np.clip((1 - w) * prior[c] + w * est, .25, 1.0))
        rows.append({"comp": c, "nivel": round(lvl, 3), "nivel_previo": prior[c], "pares": n,
                     "base": "estimativa prévia" if n == 0 else f"prévia + {n} jogador(es) em duas competições"})
    return pd.DataFrame(rows)


def evaluate(players: pd.DataFrame, ages: Optional[Dict[str, float]] = None,
             values: Optional[Dict[str, float]] = None, levels: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    d = players.copy()
    if d.empty:
        return d
    by = ["comp", "family"]
    perf = pd.Series(0.0, index=d.index)
    wsum = pd.Series(0.0, index=d.index)
    nused = pd.Series(0, index=d.index)
    for fam, weights in WEIGHTS.items():
        idx = d.index[d["family"] == fam]
        if not len(idx):
            continue
        for col, w in weights.items():
            if col not in d:
                continue
            base = col.replace("_p90", "")
            higher = METRICS.get(base, (None, None, True))[2] if base in METRICS else True
            p = _pct_within(d.loc[idx], col, by, higher)
            ok = p.notna()
            perf.loc[p.index[ok]] += p[ok] * w
            wsum.loc[p.index[ok]] += w
            nused.loc[p.index[ok]] += 1
    raw = (perf / wsum).where(nused >= 3)
    m = d["minutes"].fillna(0)
    d["metricas_usadas"] = nused
    d["desempenho_bruto"] = raw.round(1)
    # encolhimento bayesiano: poucos minutos puxam para a média da função NA competição
    d["desempenho_90"] = (50 + (raw - 50) * m / (m + 900)).round(1)
    usage = (d["min_share"].fillna(0).clip(0, 1) * 100)
    d["temporada"] = (0.72 * d["desempenho_90"] + 0.28 * usage).where((m >= 900) & (d["min_share"] >= 0.35)).round(1)
    rg = d["rating_games"].fillna(0)
    good = d["good_games"] / rg.replace(0, np.nan)
    stab = (1 - (d["rating_sd"] / 1.2).clip(0, 1))
    d["regularidade"] = (100 * (0.6 * good + 0.4 * stab)).where(rg >= 8).round(1)
    sh = _pct_within(d, "share_att", by)
    rv = _pct_within(d, "rating_vs_team", by)
    att_family = d["family"].isin(["AM", "WIDE", "ST", "CM"])
    d["impacto"] = (np.where(att_family, 0.4 * sh.fillna(50) + 0.25 * rv.fillna(50), 0.15 * sh.fillna(50) + 0.5 * rv.fillna(50))
                    + 0.35 * usage).round(1)
    d.loc[m < 600, "impacto"] = np.nan
    vs = _pct_within(d.assign(_r=d["rating_strong"]), "_r", by)
    d["contra_fortes"] = vs.where(d["games_strong"] >= 3).round(1)
    d["dif_fortes_fracos"] = (d["rating_strong"] - d["rating_weak"]).round(2)
    ages = ages or {}
    values = values or {}
    d["idade"] = d["core"].map(ages)
    d["valor_eur"] = d["core"].map(values)
    young = d["idade"] <= 23
    age_bonus = ((23 - d["idade"]).clip(0, 6) / 6 * 100)
    d["potencial"] = (0.5 * d["desempenho_90"] + 0.25 * usage + 0.25 * age_bonus).where(young & (m >= 450)).round(1)
    peers = d[d["idade"] <= 21]
    d["revelacao"] = np.nan
    if not peers.empty:
        rp = _pct_within(peers, "desempenho_90", ["family"])
        d.loc[rp.index, "revelacao"] = rp.where(peers["minutes"] >= 600).round(1)
    vp = np.log1p(pd.to_numeric(d["valor_eur"], errors="coerce")).groupby(d["family"]).rank(pct=True) * 100
    d["custo_beneficio"] = (50 + (d["desempenho_90"] - vp) / 2).where(vp.notna() & (m >= 900)).round(1)
    lf = league_factors(d)
    lv_map = dict(zip(lf["comp"], lf["nivel"]))
    if levels is not None and not levels.empty:           # modelo aprendido (3 anos) manda quando existe
        lv_map.update(dict(zip(levels["comp"], levels["nivel"])))
    lvl = d["comp"].map(lv_map).fillna(d["comp"].map(prior_level))
    d["nivel_competicao"] = lvl
    base = d["temporada"].fillna(d["desempenho_90"].where(m >= 900))
    # geral entre ligas: o desempenho DENTRO da competição levado à régua de nível (estimativa declarada)
    d["geral_entre_ligas"] = (base * (0.45 + 0.55 * lvl)).round(1)
    # Rodada 18: percentis da função calculados de uma vez (antes: cada jogador × todos os colegas → travava na base grande)
    pre = pd.DataFrame({c: _strict_pct(d, c) for c in FUNC_COLS}, index=d.index)
    recs = pre.to_dict("records")
    d["funcao"] = [_classify(f, (lambda c, r=r: None if pd.isna(r.get(c)) else float(r[c])))
                   for f, r in zip(d["family"], recs)]
    d["confianca_amostra"] = np.select([m >= 1800, m >= 900, m >= 450], ["alta", "média", "baixa"], "muito baixa")
    return d


def _p(df: pd.DataFrame, row, col: str, higher: bool = True) -> Optional[float]:
    if col not in df or pd.isna(row.get(col)):
        return None
    peers = pd.to_numeric(df.loc[(df["family"] == row["family"]) & (df["comp"] == row["comp"]), col], errors="coerce").dropna()
    if len(peers) < 8:
        return None
    p = float((peers < row[col]).mean() * 100)
    return p if higher else 100 - p


def _avg(*xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


FUNC_COLS = ["chances_p90", "ft3_p90", "crs_p90", "def_adj", "duel_pct", "lbp_p90", "pass_pct", "xa_p90",
             "goals_p90", "xg_p90", "tob_p90", "rec_p90", "drb_p90", "aer_pct", "clr_p90"]


def _strict_pct(df: pd.DataFrame, col: str) -> pd.Series:
    """Igual a `_p` para TODOS de uma vez: % dos colegas (mesma função e competição) com valor MENOR; vazio se < 8."""
    if col not in df:
        return pd.Series(np.nan, index=df.index)
    v = pd.to_numeric(df[col], errors="coerce")
    g = v.groupby([df["family"], df["comp"]])
    n = g.transform("count")
    r = g.rank(method="min")
    return ((r - 1) / n * 100).where(n >= 8)


def _function(row, df: pd.DataFrame) -> str:
    """Função tática pelo PERFIL de ações (não pela posição cadastrada) — versão de uma linha só."""
    return _classify(row.get("family"), lambda c: _p(df, row, c))


def _classify(f, P) -> str:
    """P(col) → percentil dentro da função (ou None)."""
    if f == "FB":
        att, de = _avg(P("chances_p90"), P("ft3_p90"), P("crs_p90")), _avg(P("def_adj"), P("duel_pct"))
        if att is not None and de is not None:
            return "lateral construtor" if att - de > 15 else ("lateral defensivo" if de - att > 15 else "lateral equilibrado")
    if f in ("DM", "CM"):
        de, org, cria = _avg(P("def_adj"), P("duel_pct")), _avg(P("lbp_p90"), P("pass_pct")), _avg(P("chances_p90"), P("xa_p90"), P("ft3_p90"))
        if de is not None and org is not None and de >= 60 and _avg(org, cria) >= 60:
            return "box-to-box"
        if de is not None and org is not None:
            if de - max(org, cria or 0) > 12:
                return "volante protetor"
            if (cria or 0) > org and (cria or 0) >= 60:
                return "meia criador"
            return "organizador"
    if f == "ST":
        fin, apo = _avg(P("goals_p90"), P("xg_p90"), P("tob_p90")), _avg(P("chances_p90"), P("xa_p90"), P("rec_p90"))
        if fin is not None and apo is not None:
            return "atacante de área" if fin - apo > 12 else ("atacante de apoio" if apo - fin > 12 else "atacante completo")
    if f == "WIDE":
        drb, fin, cri = P("drb_p90"), _avg(P("xg_p90"), P("goals_p90")), _avg(P("chances_p90"), P("xa_p90"))
        best = max([(drb or 0, "ponta driblador"), (fin or 0, "ponta finalizador"), (cri or 0, "ponta criador")])
        if best[0] >= 55:
            return best[1]
    if f == "CB":
        con, are = _avg(P("lbp_p90"), P("pass_pct")), _avg(P("aer_pct"), P("clr_p90"))
        if con is not None and are is not None:
            return "zagueiro construtor" if con - are > 12 else ("zagueiro de área" if are - con > 12 else "zagueiro completo")
    if f == "AM":
        cri, che = _avg(P("chances_p90"), P("xa_p90")), _avg(P("xg_p90"), P("tob_p90"))
        if cri is not None and che is not None:
            return "meia criador" if cri >= che else "meia que chega na área"
    if f == "GK":
        pas = P("pass_pct")
        return "goleiro que joga com os pés" if pas is not None and pas >= 70 else "goleiro de defesas"
    return FAMILY_PT.get(f, "função não identificada")


# ------------------------------------------------------------------ 5. ficha individual (explicável)
def profile(row: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    fam = row.get("family")
    strengths, weaknesses, unobserved = [], [], []
    for col in WEIGHTS.get(fam, {}):
        base = col.replace("_p90", "")
        higher = METRICS[base][2] if base in METRICS else True
        p = _p(df, row, col, higher)
        label = LABEL.get(base, LABEL.get(col, col))
        if p is None:
            unobserved.append(label)
            continue
        v = row.get(col)
        txt = f"{label}: {v:.2f}{'' if col.endswith('_p90') is False else ' por 90'} — melhor que {p:.0f}% dos " \
              f"{FAMILY_PT.get(fam, '')}s da competição"
        if p >= 80:
            strengths.append((p, txt))
        elif p <= 20:
            weaknesses.append((p, txt.replace("melhor que", "melhor que só")))
    strengths.sort(key=lambda x: -x[0])
    weaknesses.sort(key=lambda x: x[0])
    ctx = []
    if pd.notna(row.get("dif_fortes_fracos")) and row.get("games_strong", 0) >= 3 and row.get("games_weak", 0) >= 3:
        d = row["dif_fortes_fracos"]
        ctx.append(f"Contra o terço mais forte da competição a nota média é {row['rating_strong']:.2f} "
                   f"({'+' if d >= 0 else ''}{d:.2f} em relação aos jogos contra o terço mais fraco) — "
                   + ("mantém o nível em jogo grande." if d > -0.25 else "rende menos contra os fortes."))
    if pd.notna(row.get("rating_home")) and pd.notna(row.get("rating_away")) and row.get("games_away", 0) >= 3:
        ctx.append(f"Casa {row['rating_home']:.2f} × fora {row['rating_away']:.2f}.")
    if pd.notna(row.get("share_att")) and fam in ("AM", "WIDE", "ST", "CM"):
        ctx.append(f"Responde por {100 * row['share_att']:.0f}% do xG + xA do time nos jogos dele "
                   + ("— protagonista." if row["share_att"] >= .22 else "— produção dividida com o time."))
    if pd.notna(row.get("trend")):
        t = row["trend"]
        ctx.append("Fase: " + ("em alta" if t > .25 else "em queda" if t < -.25 else "estável")
                   + f" (últimos 5 jogos {t:+.2f} na nota em relação à temporada).")
    fit = []
    if any("passes" in s for _, s in strengths) or row.get("funcao") in ("organizador", "zagueiro construtor", "lateral construtor"):
        fit.append("time que tem a bola e constrói desde trás")
    if any("drible" in s or "terço final" in s for _, s in strengths):
        fit.append("time que ataca espaços e isola os pontas no 1×1")
    if any("ajustadas pela posse" in s or "duelos" in s for _, s in strengths):
        fit.append("time que defende em bloco e disputa muito a bola")
    if any("aéreos" in s for _, s in strengths):
        fit.append("time que usa bola longa e jogo aéreo")
    return {"fortes": [s for _, s in strengths[:6]], "limitacoes": [s for _, s in weaknesses[:4]],
            "nao_avaliado_por_falta_de_dado": unobserved, "nao_observavel": NOT_OBSERVED, "contexto": ctx,
            "rende_mais_em": fit or ["perfil equilibrado — sem um estilo de time claramente favorável nos números"],
            "amostra": (f"{int(row.get('games', 0))} jogos, {int(row.get('minutes', 0))} min, {int(row.get('starts', 0))} como "
                        f"titular, {int(row.get('subs', 0))} saindo do banco, {100 * row.get('min_share', 0):.0f}% dos minutos "
                        f"do time — confiança {row.get('confianca_amostra')}")}


# ------------------------------------------------------------------ validação (o ranking ficou mais justo?)
def validate(games: pd.DataFrame, ev: pd.DataFrame) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not games.empty:
        g = games[games["minutes"] >= 20].sort_values("day")
        g = g.assign(_i=g.groupby(["core", "comp"]).cumcount())
        half = g.groupby(["core", "comp", g["_i"] % 2])["rating"].mean().unstack()
        half = half.dropna()
        cnt = g.groupby(["core", "comp"]).size()
        half = half[cnt.reindex(half.index).fillna(0) >= 10] if len(half) else half
        if len(half) >= 20:
            out["estabilidade_turnos"] = round(float(half[0].rank().corr(half[1].rank())), 3)
            out["estabilidade_n"] = int(len(half))
    if not ev.empty:
        zero = ev[(ev["minutes"] <= 0) & ev["temporada"].notna()]
        out["sem_minutos_no_ranking"] = int(len(zero))
        both = ev.dropna(subset=["temporada"])
        res = both[both["min_share"] < .4]
        out["reservas_no_ranking_temporada"] = int(len(res))
        cov = ev.groupby(pd.cut(ev["n_metrics"], [-1, 8, 16, 99], labels=["básica", "média", "completa"]),
                         observed=False)["desempenho_90"].mean()
        out["media_por_cobertura"] = {str(k): (None if pd.isna(v) else round(float(v), 1)) for k, v in cov.items()}
    return out


# ------------------------------------------------------------------ montagem, idades/valores, cache
def _ages_values() -> tuple:
    try:
        from src.data_lake.ids import player_core
        from src.squad import data as D

        tm = D.table("tm_jogadores", ["nome", "nascimento", "valor_mercado_eur", "posicao", "funcao"])
    except Exception:
        return {}, {}, {}
    if tm.empty:
        return {}, {}, {}
    tm = tm.copy()
    tm["core"] = tm["nome"].astype(str).map(player_core)
    tm = tm[~tm["core"].duplicated(keep=False)]           # homônimo no cadastro: sem idade/valor (não chuta)
    born = pd.to_datetime(tm["nascimento"], errors="coerce")
    age = ((pd.Timestamp.today() - born).dt.days / 365.25).round(1)
    from src.squad.formations import natural_role

    roles = {c: natural_role(str(f or ""), str(p or "")) for c, p, f in zip(tm["core"], tm.get("posicao", ""), tm.get("funcao", ""))}
    return (dict(zip(tm["core"], age)), dict(zip(tm["core"], pd.to_numeric(tm["valor_mercado_eur"], errors="coerce"))),
            {c: r for c, r in roles.items() if r and not r.endswith("?")})


def _fotmob_ages_values(db) -> tuple:
    """Elenco ATUAL da FotMob: nascimento e valor de mercado de quem não está no Transfermarkt (Série B/C, ligas
    sul-americanas). Nome repetido em dois clubes fica de fora (não chuta)."""
    try:
        with db.connect() as conn:
            r = pd.read_sql_query("SELECT name, birth, market_value FROM fotmob_rosters", conn)
    except Exception:
        return {}, {}
    if r.empty:
        return {}, {}
    from src.data_lake.ids import player_core

    r["core"] = r["name"].astype(str).map(player_core)
    r = r[~r["core"].duplicated(keep=False)]
    born = pd.to_datetime(r["birth"], errors="coerce")
    age = ((pd.Timestamp.today() - born).dt.days / 365.25).round(1)
    return (dict(zip(r["core"], age)), dict(zip(r["core"], pd.to_numeric(r["market_value"], errors="coerce"))))


def league_model(db, years: int = 3, prior_weight: float = 15.0) -> pd.DataFrame:
    """MODELO APRENDIDO do nível das competições (rodada 16): nota de cada jogador por competição e temporada nos
    últimos `years` anos (≥ 450 min). Ajuste conjunto  nota = habilidade do jogador + facilidade da competição,
    estimado por mínimos quadrados alternados com regularização para a estimativa prévia (ridge). Quem jogou em duas
    competições (transferência, Libertadores × liga, Copa × liga) é o que liga as réguas. Facilidade alta (notas
    infladas) = nível mais baixo. Competição sem pares fica na estimativa prévia e é marcada assim."""
    since = (date.today() - timedelta(days=365 * int(years))).isoformat()
    from src.data_hub.gender import comp_sql

    q = f"""SELECT p.player_name, m.competition_name AS comp, m.season_name AS season,
                   SUM(p.rating * p.minutes) / NULLIF(SUM(CASE WHEN p.rating IS NOT NULL THEN p.minutes END), 0) AS rating,
                   SUM(p.minutes) AS mins
            FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id
            WHERE m.match_date >= ? AND p.rating IS NOT NULL AND COALESCE(p.minutes, 0) > 0{comp_sql([], "m")}
            GROUP BY p.player_name, m.competition_name, m.season_name HAVING SUM(p.minutes) >= 450"""
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(q, conn, params=[since])
    except Exception:
        return pd.DataFrame()
    if d.empty:
        return pd.DataFrame()
    from src.data_lake.ids import player_core

    d["core"] = d["player_name"].map(player_core)
    d = d.assign(_rm=d["rating"] * d["mins"]).groupby(["core", "comp"], as_index=False)[["_rm", "mins"]].sum()
    d["rating"] = d["_rm"] / d["mins"]                    # média ponderada pelos minutos (sem laço por grupo)
    d = d.drop(columns="_rm")
    comps = sorted(d["comp"].unique())
    prior = {c: prior_level(c) for c in comps}
    # prior em "pontos de nota": competição mais fraca infla a nota (~0,4 por 0,1 de nível abaixo de 0,8)
    prior_b = {c: -4.0 * (prior[c] - .8) for c in comps}
    linked = d.groupby("core")["comp"].transform("nunique") >= 2
    pairs = d[linked].groupby("comp")["core"].nunique().to_dict()
    b = pd.Series(prior_b)
    for _ in range(30):
        a = (d["rating"] - d["comp"].map(b)).groupby(d["core"]).mean()
        resid = d["rating"] - d["core"].map(a)
        num = resid.groupby(d["comp"]).sum() + prior_weight * pd.Series(prior_b)
        den = d.groupby("comp").size() + prior_weight
        b = (num / den).reindex(comps).fillna(pd.Series(prior_b))
    # ancora: a média ponderada dos níveis aprendidos igual à média da estimativa prévia (só a ORDEM e as distâncias vêm
    # dos dados)
    b = b - (b - pd.Series(prior_b)).mean()
    rows = []
    for c in comps:
        lvl = float(np.clip(.8 - b[c] / 4.0, .25, 1.0))
        n = int(pairs.get(c, 0))
        rows.append({"comp": c, "nivel": round(lvl if n >= 3 else prior[c], 3), "nivel_previo": prior[c],
                     "nivel_aprendido": round(lvl, 3), "pares": n,
                     "base": ("modelo aprendido" if n >= 3 else "estimativa prévia (menos de 3 jogadores ligando réguas)")})
    return pd.DataFrame(rows)


def build(db, days: int = 400) -> Dict[str, Any]:
    t0 = time.time()
    say = lambda m: print(f"  [{time.time() - t0:5.0f} s] {m}", flush=True)   # rodada 25c: andamento visível
    say("lendo os jogos de cada jogador (último ano)…")
    g = player_games(db, days)
    say(f"{len(g):,} atuações em {g['match_id'].nunique() if not g.empty else 0:,} jogos".replace(",", "."))
    if g.empty:
        return {"jogadores": pd.DataFrame(), "niveis": pd.DataFrame(), "validacao": {}, "segundos": 0}
    say("força dos adversários por competição…")
    st = opponent_strength(db, g["comp"].unique().tolist(), days)
    say("somando por jogador e competição…")
    agg = aggregate(g, st)
    say("idade e valor (Transfermarkt, FotMob, Wikidata)…")
    ages, values, roles = _ages_values()
    fa, fv = _fotmob_ages_values(db)                      # quem não está no Transfermarkt: elenco da FotMob
    try:                                                  # e, por último, a Wikidata (nome único de jogador)
        from src.data_hub.sources import wikidata as WD

        for k, v in WD.ages(db).items():
            fa.setdefault(k, v)
    except Exception:
        pass
    for k, v in fa.items():
        if pd.notna(v) and pd.isna(ages.get(k, np.nan)):
            ages[k] = v
    for k, v in fv.items():
        if pd.notna(v) and v > 0 and pd.isna(values.get(k, np.nan)):
            values[k] = v
    say("nível das ligas (aprendido pelos jogadores que atuaram em duas)…")
    model = league_model(db)
    say("avaliando…")
    miss = agg["family"] == ""                            # sem posição nos jogos: cadastro do Transfermarkt
    agg.loc[miss, "role"] = agg.loc[miss, "core"].map(roles).fillna("")
    agg.loc[miss, "family"] = agg.loc[miss, "role"].map(FAMILY_OF).fillna("")
    ev = evaluate(agg, ages, values, levels=model)
    return {"jogadores": ev, "niveis": model if not model.empty else league_factors(ev), "validacao": validate(g, ev),
            "segundos": round(time.time() - t0, 1), "jogos": int(g["match_id"].nunique())}


def save(res: Dict[str, Any]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ev = res["jogadores"]
    if not ev.empty:
        ev.to_parquet(OUT_PATH, index=False)
    META_PATH.write_text(json.dumps({"validacao": res.get("validacao"), "segundos": res.get("segundos"),
                                     "jogos": res.get("jogos"), "gerado": time.strftime("%Y-%m-%d %H:%M"),
                                     "niveis": res["niveis"].to_dict("records") if not res["niveis"].empty else []},
                                    ensure_ascii=False, default=str), encoding="utf-8")


def load() -> Optional[Dict[str, Any]]:
    if not OUT_PATH.exists():
        return None
    try:
        meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
        return {"jogadores": pd.read_parquet(OUT_PATH), **meta}
    except Exception:
        return None


def main() -> None:
    from src.data_hub.db import DataHubDB

    res = build(DataHubDB())
    save(res)
    print(f"Avaliações: {len(res['jogadores'])} jogador(es)-competição em {res.get('segundos')} s · "
          f"validação: {res.get('validacao')}")


if __name__ == "__main__":
    main()
