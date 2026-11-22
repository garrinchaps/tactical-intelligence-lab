"""
Rodada 13 — CONFRONTOS do próximo jogo: a qualidade do MEU time contra o defeito do RIVAL (e o contrário).

Duas camadas, sempre com número e base:
1. Duelos individuais pelo desenho provável: meu ponta-direita × lateral-esquerdo deles, meu centroavante × zagueiros,
   meu meia × volante — e os deles contra os meus. Cada duelo é testado em vários fundamentos (drible × marcação no
   1×1, jogo aéreo, cruzamento × zagueiro fraco pelo alto, faltas sofridas × faltas cometidas, pressão × perda de bola).
2. Estilo do time × problema sistêmico do rival (últimos jogos): bola parada, cruzamentos, chutes de fora, presença na
   área, grandes chances.

Percentis = régua da base (jogadores FotMob/ESPN dos últimos 12 meses com ≥ 450 min; times nas mesmas competições).
"Escancarado" só quando a qualidade está no topo (≥ P80) E o defeito no fundo (≤ P25); "claro" com ≥ P70 e ≤ P35.
Associação, não garantia: o técnico adversário pode corrigir.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

REF_PATH = Path("data/processed/matchup_ref_v2.parquet")      # v2 (rodada 21): impedimentos, cruzamentos, bolas longas
REF_MAX_AGE_S = 86400

# chave do stats_json → nome curto
KEYS = {"dribbles_succeeded": "drb", "dribbles_succeeded_total": "drb_t", "dribbled_past": "drb_past",
        "aerials_won": "aer", "aerials_won_total": "aer_t", "duel_won": "duel_w", "duel_lost": "duel_l",
        "accurate_crosses": "crs", "chances_created": "cc", "xg": "xg", "xa": "xa", "touches_opp_box": "tob",
        "was_fouled": "fouled", "foulsCommitted": "fouls", "interceptions": "int", "dispossessed": "disp",
        "recoveries": "rec", "defensive_actions": "def", "matchstats.headers.tackles": "tkl",
        "ground_duels_won": "gd_w", "ground_duels_won_total": "gd_t",
        # rodada 21: mais fundamentos para dicas além do drible
        "Offsides": "off", "accurate_crosses_total": "crs_t", "long_balls_accurate": "lb", "long_balls_accurate_total": "lb_t",
        "line_breaking_passes": "lbp", "passes_into_final_third": "pft", "headed_clearance": "hclr", "clearances": "clr"}

FAMILY = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "DM": "MID", "CM": "MID",
          "AM": "AM", "LM": "WIDE", "RM": "WIDE", "LW": "WIDE", "RW": "WIDE", "ST": "ST", "CF": "ST"}

# catálogo de qualidades (ataque) × defeitos (defesa): (id, título, métrica do atacante, métrica do defensor,
# o defensor é RUIM quando a métrica é alta?, texto de como explorar)
DIMENSIONS = [
    ("drible", "Drible no 1×1", "drb_p90", "drb_past_p90", True,
     "isolar {att} contra {deff}: abrir o lado, receber de frente e partir no mano a mano"),
    ("aereo", "Jogo aéreo", "aer_pct", "aer_pct", False,
     "buscar {att} pelo alto: bola longa e cruzamento na direção de {deff}"),
    ("faltas", "Faltas perigosas", "fouled_p90", "fouls_p90", True,
     "provocar {deff} com {att} em velocidade: falta perto da área vira bola parada"),
    ("duelo", "Duelo físico no chão", "duel_pct", "duel_pct", False,
     "jogar no corpo a corpo: {att} ganha duelos e {deff} perde"),
    ("presenca", "Ataque à área", "tob_p90", "int_p90", False,
     "{att} vive dentro da área e {deff} intercepta pouco: atacar o espaço nas costas dele"),
    ("pressao", "Pressão na saída de bola", "rec_p90", "disp_p90", True,
     "pressionar {deff} assim que receber: {att} recupera muitas bolas e {deff} perde a posse com frequência"),
]

PAIRS_ATTACK = [  # (minha função, funções deles que marcam)
    ("RW", ["LB", "LWB", "LM"]), ("RM", ["LB", "LWB", "LM"]), ("RWB", ["LM", "LW", "LB"]),
    ("LW", ["RB", "RWB", "RM"]), ("LM", ["RB", "RWB", "RM"]), ("LWB", ["RM", "RW", "RB"]),
    ("ST", ["CB"]), ("CF", ["CB"]), ("AM", ["DM", "CM"]),
]

TEAM_PAIRS = [  # (coluna a favor, coluna contra do rival, título, como explorar)
    ("pct_xg_bola_parada", "c_xg_set_play", "Bola parada",
     "levar o jogo para escanteios e faltas laterais: é a nossa arma e o ponto fraco deles"),
    ("crosses_total", "c_crosses_total", "Jogo pelos lados com cruzamento",
     "abrir o campo e cruzar: eles costumam sofrer muitos cruzamentos"),
    ("touches_opp_box", "c_touches_opp_box", "Presença na área",
     "encher a área: eles deixam o rival tocar muito dentro da própria área"),
    ("big_chances", "c_big_chances", "Chances claras",
     "atacar o espaço com passes de ruptura: eles cedem grandes chances com frequência"),
    ("shots_outside_box", "c_shots_outside_box", "Chute de fora",
     "finalizar de média distância: eles deixam chutar de fora"),
    ("pct_bolas_longas", "c_xg", "Jogo direto",
     "bola longa nas costas: eles cedem muito xG e nós jogamos direto"),
]


# ------------------------------------------------------------------ dados
def _sum_sql(alias: str = "p") -> str:
    return ", ".join(f"SUM(COALESCE(json_extract({alias}.stats_json, '$.\"{k}\"'), 0)) AS {v}" for k, v in KEYS.items())


def _per90(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    m = pd.to_numeric(d["mins"], errors="coerce").replace(0, np.nan)
    for v in ("drb", "drb_past", "aer", "crs", "cc", "xg", "xa", "tob", "fouled", "fouls", "int", "disp", "rec", "def", "tkl",
              "off", "lb", "lbp", "pft", "hclr", "clr", "crs_t", "lb_t"):
        if v in d:
            d[f"{v}_p90"] = d[v] * 90 / m
    d["drb_pct"] = 100 * d["drb"] / d["drb_t"].replace(0, np.nan)
    d["aer_pct"] = (100 * d["aer"] / d["aer_t"].replace(0, np.nan)).where(d["aer_t"] >= 6)
    if "crs_t" in d:
        d["crs_pct"] = (100 * d["crs"] / d["crs_t"].replace(0, np.nan)).where(d["crs_t"] >= 8)
    if "lb_t" in d:
        d["lb_pct"] = (100 * d["lb"] / d["lb_t"].replace(0, np.nan)).where(d["lb_t"] >= 10)
    tot = d["duel_w"] + d["duel_l"]
    d["duel_pct"] = (100 * d["duel_w"] / tot.replace(0, np.nan)).where(tot >= 10)
    return d


def reference(db, force: bool = False) -> pd.DataFrame:
    """Régua dos jogadores (últimos 365 dias, ≥ 450 min): números somados no SQLite (json_extract), em disco por 24 h."""
    if not force and REF_PATH.exists() and time.time() - REF_PATH.stat().st_mtime < REF_MAX_AGE_S:
        try:
            return pd.read_parquet(REF_PATH)
        except Exception:
            pass
    q = f"""SELECT p.player_name, p.team_name, SUM(p.minutes) AS mins, COUNT(*) AS jogos, {_sum_sql()}
            FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id
            WHERE m.match_date >= date('now', '-365 day') AND COALESCE(p.minutes, 0) > 0
              AND p.stats_json LIKE '%dribbled_past%'
            GROUP BY p.player_name, p.team_name HAVING SUM(p.minutes) >= 450"""
    try:
        with db.connect() as conn:
            ref = pd.read_sql_query(q, conn)
    except Exception:
        return pd.DataFrame()
    ref = _per90(ref)
    try:
        REF_PATH.parent.mkdir(parents=True, exist_ok=True)
        ref.to_parquet(REF_PATH, index=False)
    except Exception:
        pass
    return ref


def team_players(db, team_names: Sequence[str], n_games: int = 30) -> pd.DataFrame:
    """Rodada 27: os 30 últimos jogos do time com números por jogador (antes 15 — a base ficava em 8–12 jogos por
    atleta), só do mesmo gênero (o time feminino com o mesmo nome não entra)."""
    names = [str(x) for x in team_names if x]
    if not names:
        return pd.DataFrame()
    ph = ",".join("?" * len(names))
    try:
        from src.data_hub.gender import comp_sql

        gsql = comp_sql(names, "m")
    except Exception:
        gsql = ""
    q = f"""SELECT p.player_name, SUM(p.minutes) AS mins, COUNT(*) AS jogos, {_sum_sql()}
            FROM match_player_stats p WHERE p.team_name IN ({ph}) AND p.match_id IN (
                SELECT m.match_id FROM matches m JOIN match_player_stats q ON q.match_id = m.match_id
                WHERE q.team_name IN ({ph}) AND q.stats_json LIKE '%dribbled_past%'{gsql}
                GROUP BY m.match_id ORDER BY m.match_date DESC LIMIT {int(n_games)})
              AND COALESCE(p.minutes, 0) > 0
            GROUP BY p.player_name"""
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(q, conn, params=names + names)
    except Exception:
        return pd.DataFrame()
    return _per90(d) if not d.empty else d


def _pct(ref: pd.DataFrame, col: str, value) -> Optional[float]:
    if value is None or pd.isna(value) or ref.empty or col not in ref:
        return None
    s = pd.to_numeric(ref[col], errors="coerce").dropna()
    if len(s) < 30:
        return None
    return float((s < value).mean() * 100)


# ------------------------------------------------------------------ fuzzy (Mamdani): quão explorável é o duelo
def fuzzy_exploit(att_pct: float, def_bad_pct: float) -> float:
    """Mamdani com centroide (matéria, Q3): entradas = força do nosso jogador e fraqueza do defensor (0–100);
    regras: forte E muito fraco → muito explorável; forte E fraco → explorável; médio E muito fraco → explorável;
    médio E fraco → pouco. Saída 0–100 (índice, não probabilidade)."""
    from src.intelligence.course import _tri

    u = np.arange(0, 101, 1.0)
    alto = lambda x: float(_tri(np.array([x]), 60, 100, 100)[0])
    medio = lambda x: float(_tri(np.array([x]), 40, 65, 85)[0])
    rules = [(min(alto(att_pct), alto(def_bad_pct)), (70, 100, 100)),
             (min(alto(att_pct), medio(def_bad_pct)), (45, 70, 90)),
             (min(medio(att_pct), alto(def_bad_pct)), (45, 70, 90)),
             (min(medio(att_pct), medio(def_bad_pct)), (10, 35, 60))]
    agg = np.zeros_like(u)
    for w, tri in rules:
        if w > 0:
            agg = np.maximum(agg, np.minimum(w, _tri(u, *tri)))
    return round(float((u * agg).sum() / agg.sum()), 1) if agg.sum() > 0 else 0.0


# ------------------------------------------------------------------ duelos individuais
def _find(xi: List[Dict[str, Any]], roles: Sequence[str]) -> List[Dict[str, Any]]:
    out = []
    for r in roles:
        out += [s for s in xi if str(s.get("papel") or "").upper() == r and s.get("jogador")]
    return out


def _stats_row(stats: pd.DataFrame, name: str) -> Optional[Dict[str, Any]]:
    if stats is None or stats.empty or not name:
        return None
    from src.data_lake.ids import player_core

    core = player_core(name)
    hit = stats[stats["player_name"].map(player_core) == core]
    if hit.empty:
        last = core.split()[-1] if core else ""
        hit = stats[stats["player_name"].map(lambda x: player_core(x).split()[-1:] == [last])] if last else hit
        if len(hit) != 1:
            return None
    r = hit.sort_values("mins", ascending=False).iloc[0].to_dict()
    return r if (r.get("mins") or 0) >= 180 else None


def _label(p: float) -> str:
    return f"melhor que {p:.0f}% da base" if p >= 50 else f"pior que {100 - p:.0f}% da base"


def duel_findings(my_xi, rv_xi, my_stats, rv_stats, ref, me: str, rival: str, attack: bool = True) -> List[Dict[str, Any]]:
    """attack=True: meus atacantes × defensores deles (onde FORÇAR); False: os deles × os meus (onde PROTEGER)."""
    a_xi, d_xi = (my_xi, rv_xi) if attack else (rv_xi, my_xi)
    a_st, d_st = (my_stats, rv_stats) if attack else (rv_stats, my_stats)
    out = []
    seen = set()
    for role, def_roles in PAIRS_ATTACK:
        for att in _find(a_xi, [role]):
            defs = _find(d_xi, def_roles)[:2]
            for dfd in defs:
                key = (att["jogador"], dfd["jogador"])
                if key in seen:
                    continue
                seen.add(key)
                ra, rd = _stats_row(a_st, att["jogador"]), _stats_row(d_st, dfd["jogador"])
                if not ra or not rd:
                    continue
                for did, title, am, dm, bad_high, how in DIMENSIONS:
                    pa = _pct(ref, am, ra.get(am))
                    pdv = _pct(ref, dm, rd.get(dm))
                    if pa is None or pdv is None:
                        continue
                    d_good = 100 - pdv if bad_high else pdv        # quão BOM o defensor é nisso (0–100)
                    if pa >= 80 and d_good <= 25:
                        level = "escancarado"
                    elif pa >= 70 and d_good <= 35:
                        level = "claro"
                    else:
                        continue
                    an, dn = att["jogador"], dfd["jogador"]
                    fz = fuzzy_exploit(pa, 100 - d_good)
                    try:
                        from src.intelligence.lab_brain import weight

                        wt = weight("confrontos", did)
                    except Exception:
                        wt = 1.0
                    out.append({
                        "fuzzy": fz, "peso_aprendido": wt, "score": round(fz * wt, 1),
                        "tipo": "duelo", "dimensao": did, "titulo": title, "nivel": level,
                        "atacante": an, "defensor": dn, "papel_atacante": role, "papel_defensor": dfd.get("papel"),
                        "lado_x": dfd.get("x"), "lado_y": dfd.get("y"), "gap": round(pa - d_good, 1),
                        "evidencia": (f"{an}: {_fmt(am, ra.get(am))} ({_label(pa)}) · {dn}: {_fmt(dm, rd.get(dm))} "
                                      f"({'ruim' if d_good <= 35 else 'fraco'} nisso — {_label(d_good)})"),
                        "acao": (("FORÇAR: " if attack else "PROTEGER: ") +
                                 (how.format(att=an, deff=dn) if attack else
                                  f"{an} ({rival}) contra {dn} — dobrar a marcação por esse lado, não deixar {dn} sozinho "
                                  f"no {title.lower()}")),
                        "base": f"{int(ra.get('jogos') or 0)} e {int(rd.get('jogos') or 0)} jogos de cada um, dentro dos 30 últimos "
                                f"jogos de cada time com números por jogador (só conta jogo em que ele entrou)",
                    })
    out.sort(key=lambda x: (x["nivel"] != "escancarado", -x["score"]))
    return out


def _fmt(metric: str, v) -> str:
    if v is None or pd.isna(v):
        return "—"
    names = {"drb_p90": "dribles certos por 90", "drb_past_p90": "vezes driblado por 90", "aer_pct": "% de duelos aéreos ganhos",
             "fouled_p90": "faltas sofridas por 90", "fouls_p90": "faltas cometidas por 90", "duel_pct": "% de duelos ganhos",
             "tob_p90": "toques na área rival por 90", "int_p90": "interceptações por 90",
             # rodada 22: todos os números que aparecem nos cartões têm nome de futebol (antes saía "rec_p90")
             "rec_p90": "recuperações de bola por 90", "disp_p90": "vezes que perdeu a bola por 90",
             "drb_pct": "% de dribles certos", "crs_p90": "cruzamentos certos por 90", "crs_t_p90": "cruzamentos tentados por 90",
             "crs_pct": "% de cruzamentos certos", "cc_p90": "chances criadas por 90", "xg_p90": "xG por 90",
             "xa_p90": "xA por 90", "def_p90": "ações defensivas por 90", "tkl_p90": "desarmes por 90",
             "off_p90": "impedimentos por 90", "lb_p90": "bolas longas certas por 90", "lb_t_p90": "bolas longas tentadas por 90",
             "lb_pct": "% de bolas longas certas", "lbp_p90": "passes que quebram linhas por 90",
             "pft_p90": "passes no terço final por 90", "hclr_p90": "cortes de cabeça por 90", "clr_p90": "cortes por 90",
             "aer_p90": "duelos aéreos ganhos por 90"}
    return f"{float(v):.1f} {names.get(metric, metric)}" if metric.endswith("_pct") else f"{float(v):.2f} {names.get(metric, metric)}"


# ------------------------------------------------------------------ estilo × problema sistêmico
def style_findings(db, my_names: Sequence[str], rv_names: Sequence[str], me: str, rival: str, n: int = 15) -> List[Dict[str, Any]]:
    from src.analytics import team_history as TH

    try:
        vm = TH._vectors(db, TH._matches(db, list(my_names), n), list(my_names))
        vr = TH._vectors(db, TH._matches(db, list(rv_names), n), list(rv_names))
    except Exception:
        return []
    if vm.empty or vr.empty:
        return []
    comps = list(dict.fromkeys(vm["competition_name"].dropna().tolist() + vr["competition_name"].dropna().tolist()))
    ref = TH._reference(db, comps)
    if ref.empty:
        return []
    out = []
    for fcol, ccol, title, how in TEAM_PAIRS:
        mine = pd.to_numeric(vm.get(f"f_{fcol}"), errors="coerce").dropna()
        theirs = pd.to_numeric(vr.get(ccol), errors="coerce").dropna()
        rs_f = pd.to_numeric(ref.get(fcol), errors="coerce").dropna()
        rs_c = pd.to_numeric(ref.get(ccol[2:]), errors="coerce").dropna()
        if len(mine) < 4 or len(theirs) < 4 or len(rs_f) < 50 or len(rs_c) < 50:
            continue
        # média de vários jogos contra a régua de jogos: usa a frequência de jogos acima da mediana (mais honesto)
        p_me = float((mine > rs_f.median()).mean() * 100)
        p_rv = float((theirs > rs_c.median()).mean() * 100)
        if p_me >= 65 and p_rv >= 65:
            level = "escancarado" if p_me >= 80 and p_rv >= 80 else "claro"
            out.append({"tipo": "estilo", "titulo": title, "nivel": level,
                        "evidencia": (f"{me}: acima do normal em {p_me:.0f}% dos últimos {len(mine)} jogos "
                                      f"(média {mine.mean():.1f}) · {rival} cede acima do normal em {p_rv:.0f}% dos últimos "
                                      f"{len(theirs)} jogos (média {theirs.mean():.1f})"),
                        "acao": "FORÇAR: " + how, "base": f"normal = mediana de {len(rs_f)} atuações nas mesmas competições"})
        # o contrário: o rival é forte nisso e nós cedemos (onde EVITAR)
        their_f = pd.to_numeric(vr.get(f"f_{fcol}"), errors="coerce").dropna()
        my_c = pd.to_numeric(vm.get(ccol), errors="coerce").dropna()
        if len(their_f) >= 4 and len(my_c) >= 4:
            q_rv = float((their_f > rs_f.median()).mean() * 100)
            q_me = float((my_c > rs_c.median()).mean() * 100)
            if q_rv >= 65 and q_me >= 65:
                out.append({"tipo": "estilo_contra", "titulo": title, "nivel": "escancarado" if min(q_rv, q_me) >= 80 else "claro",
                            "evidencia": (f"{rival}: acima do normal em {q_rv:.0f}% dos jogos · {me} cede acima do normal em "
                                          f"{q_me:.0f}% dos jogos"),
                            "acao": f"EVITAR: não dar a {rival} o jogo de {title.lower()} — é a força deles e o nosso ponto fraco",
                            "base": f"normal = mediana de {len(rs_f)} atuações nas mesmas competições"})
    out.sort(key=lambda x: (x["nivel"] != "escancarado", x["tipo"] != "estilo"))
    return out


# ------------------------------------------------------------------ rodada 21: dicas além do duelo 1×1
def _players(xi, stats, roles):
    out = []
    for s_ in _find(xi, roles):
        r = _stats_row(stats, s_["jogador"])
        if r:
            out.append((s_["jogador"], r))
    return out


def _best(cands, ref, col, min_pct=70.0):
    best = None
    for name, r in cands:
        p = _pct(ref, col, r.get(col))
        if p is not None and p >= min_pct and (best is None or p > best[2]):
            best = (name, r, p)
    return best


def _base(*rows) -> str:
    return " · ".join(f"{int(r.get('jogos') or 0)} jogos" for r in rows if r) + " recentes com números por jogador"


def combo_findings(my_xi, rv_xi, ms, rs, ref, me: str, rival: str) -> Dict[str, List[Dict[str, Any]]]:
    """Leituras que juntam dois ou três jogadores (o nosso ponto forte × o defeito deles) e alertas individuais."""
    force, protect = [], []
    if ref is None or ref.empty:
        return {"forcar": force, "proteger": protect}
    # 1. cruzamento + cabeceio contra zagueiros fracos pelo alto
    crosser = _best(_players(my_xi, ms, ["LB", "RB", "LWB", "RWB", "LW", "RW", "LM", "RM"]), ref, "crs_p90", 70)
    target = _best(_players(my_xi, ms, ["ST", "CF", "AM", "CB"]), ref, "aer_pct", 65)
    cbs = [(n, r, _pct(ref, "aer_pct", r.get("aer_pct"))) for n, r in _players(rv_xi, rs, ["CB"])]
    cbs = [c for c in cbs if c[2] is not None]
    weak_cb = min(cbs, key=lambda c: c[2]) if cbs else None
    if crosser and target and weak_cb and weak_cb[2] <= 35:
        cp = crosser[1].get("crs_pct")
        force.append({"tipo": "combo", "dimensao": "cruzamento", "titulo": "Cruzamento na área",
                      "nivel": "escancarado" if crosser[2] >= 85 and weak_cb[2] <= 20 else "claro",
                      "atacante": f"{crosser[0]} → {target[0]}", "defensor": weak_cb[0],
                      "evidencia": (f"{crosser[0]} cruza {_fmt('crs_p90', crosser[1].get('crs_p90'))}"
                                    + (f" ({cp:.0f}% certos)" if cp is not None and pd.notna(cp) else "")
                                    + f" · {target[0]} ganha {target[1].get('aer_pct'):.0f}% das bolas pelo alto · "
                                    f"{weak_cb[0]} ganha só {weak_cb[1].get('aer_pct'):.0f}% ({_label(weak_cb[2])})"),
                      "acao": (f"FORÇAR: levar a bola até {crosser[0]} e cruzar na direção de {weak_cb[0]} — "
                               f"{target[0]} atacando a primeira trave contra ele"),
                      "base": _base(crosser[1], target[1], weak_cb[1])})
    # 2. bola longa nas costas: nosso lançador + nosso jogador de profundidade × defensor que é driblado/perde duelo
    passer = _best(_players(my_xi, ms, ["CB", "DM", "CM", "GK", "LB", "RB"]), ref, "lb_p90", 75)
    runner = _best(_players(my_xi, ms, ["ST", "CF", "LW", "RW"]), ref, "tob_p90", 70)
    backs = [(n, r, _pct(ref, "duel_pct", r.get("duel_pct"))) for n, r in _players(rv_xi, rs, ["CB", "LB", "RB"])]
    backs = [b for b in backs if b[2] is not None]
    slow = min(backs, key=lambda b: b[2]) if backs else None
    if passer and runner and slow and slow[2] <= 35:
        lp = passer[1].get("lb_pct")
        force.append({"tipo": "combo", "dimensao": "bola_longa", "titulo": "Bola longa nas costas",
                      "nivel": "claro", "atacante": f"{passer[0]} → {runner[0]}", "defensor": slow[0],
                      "evidencia": (f"{passer[0]} acerta {_fmt('lb_p90', passer[1].get('lb_p90'))}"
                                    + (f" ({lp:.0f}% certas)" if lp is not None and pd.notna(lp) else "")
                                    + f" · {runner[0]}: {_fmt('tob_p90', runner[1].get('tob_p90'))} · "
                                    f"{slow[0]} ganha só {slow[1].get('duel_pct'):.0f}% dos duelos ({_label(slow[2])}). "
                                    "Velocidade não é medida pelas fontes abertas — a leitura é pelos duelos."),
                      "acao": (f"FORÇAR: atrair a pressão de um lado e virar com {passer[0]} na corrida de {runner[0]} "
                               f"às costas de {slow[0]}"),
                      "base": _base(passer[1], runner[1], slow[1])})
    # 3. alertas sobre o atacante deles que vive no limite do impedimento
    for name, r in _players(rv_xi, rs, ["ST", "CF", "LW", "RW", "AM"]):
        p = _pct(ref, "off_p90", r.get("off_p90"))
        if p is not None and p >= 85 and (r.get("off") or 0) >= 4:
            protect.append({"tipo": "alerta", "dimensao": "impedimento", "titulo": "Linha de impedimento",
                            "nivel": "claro", "atacante": name, "defensor": "nossa linha",
                            "evidencia": (f"{name}: {r.get('off_p90'):.2f} impedimentos por 90 ({_label(p)}) — "
                                          "joga colado no último defensor"),
                            "acao": (f"PROTEGER: linha alinhada e subida coordenada — {name} ataca as costas no limite; "
                                     "um zagueiro atrasado dá condição"),
                            "base": _base(r)})
            break
    # 4. nosso atacante que cai muito em impedimento (orientação)
    for name, r in _players(my_xi, ms, ["ST", "CF", "LW", "RW"]):
        p = _pct(ref, "off_p90", r.get("off_p90"))
        if p is not None and p >= 90 and (r.get("off") or 0) >= 5:
            protect.append({"tipo": "alerta", "dimensao": "impedimento_nosso", "titulo": "Nosso atacante no impedimento",
                            "nivel": "claro", "atacante": name, "defensor": "",
                            "evidencia": f"{name}: {r.get('off_p90'):.2f} impedimentos por 90 ({_label(p)})",
                            "acao": f"ORIENTAR: {name} precisa atacar a profundidade saindo de trás da linha, não parado nela",
                            "base": _base(r)})
            break
    # 5. pivô deles que perde a bola de costas → pressionar por trás
    for name, r in _players(rv_xi, rs, ["ST", "CF"]):
        pd_ = _pct(ref, "disp_p90", r.get("disp_p90"))
        pdl = _pct(ref, "duel_pct", r.get("duel_pct"))
        if pd_ is not None and pd_ >= 75 and (pdl is None or pdl <= 45):
            force.append({"tipo": "combo", "dimensao": "pivo", "titulo": "Pivô deles sob pressão",
                          "nivel": "claro", "atacante": "nossos zagueiros/volantes", "defensor": name,
                          "evidencia": (f"{name}: perde a bola {r.get('disp_p90'):.2f} vezes por 90 ({_label(pd_)})"
                                        + (f" e ganha {r.get('duel_pct'):.0f}% dos duelos" if pdl is not None else "")),
                          "acao": (f"FORÇAR: marcar {name} por trás quando ele recebe de costas — antecipar e sair rápido "
                                   "na transição"),
                          "base": _base(r)})
            break
    # 6. lateral deles que cruza muito e erra: deixar cruzar, fechar por dentro
    for name, r in _players(rv_xi, rs, ["LB", "RB", "LWB", "RWB", "LW", "RW"]):
        vol = _pct(ref, "crs_p90", r.get("crs_p90"))
        acc = _pct(ref, "crs_pct", r.get("crs_pct"))
        if vol is not None and acc is not None and (r.get("crs_t") or 0) >= 15 and acc <= 25:
            force.append({"tipo": "combo", "dimensao": "cruzamento_ruim", "titulo": "Deixar cruzar quem erra",
                          "nivel": "claro", "atacante": "nosso bloco", "defensor": name,
                          "evidencia": f"{name} tenta muitos cruzamentos e acerta só {r.get('crs_pct'):.0f}% ({_label(acc)})",
                          "acao": (f"FORÇAR: fechar o meio e empurrar o jogo deles para o lado de {name} — o cruzamento "
                                   "dele raramente encontra alguém; ganhar a segunda bola"),
                          "base": _base(r)})
            break
    return {"forcar": force, "proteger": protect}


GOAL_SITUATIONS = {"FastBreak": "contra-ataque", "FromCorner": "escanteio", "SetPiece": "bola parada",
                   "FreeKick": "falta", "ThrowInSetPiece": "lateral", "Penalty": "pênalti"}


def shot_findings(db, my_names: Sequence[str], rv_names: Sequence[str], me: str, rival: str, n: int = 20) -> Dict[str, List]:
    """Como os gols aconteceram (mapa de chutes da FotMob): de onde o rival sofre e de onde ele marca, contra o normal
    da base inteira. Ex.: '40% dos gols que eles sofreram foram de contra-ataque (normal: 12%)'."""
    out = {"forcar": [], "proteger": []}
    rv = [x for x in rv_names if x]
    if not rv:
        return out
    ph = ",".join("?" * len(rv))
    try:
        with db.connect() as conn:
            ids = [r[0] for r in conn.execute(
                f"SELECT match_id FROM matches WHERE (home_team_name IN ({ph}) OR away_team_name IN ({ph})) AND "
                f"match_id IN (SELECT DISTINCT match_id FROM match_shots) ORDER BY match_date DESC LIMIT {int(n)}",
                rv + rv).fetchall()]
            if len(ids) < 6:
                return out
            iph = ",".join("?" * len(ids))
            g = pd.read_sql_query(f"SELECT match_id, team_name, situation, shot_type FROM match_shots WHERE outcome = 'Goal' "
                                  f"AND COALESCE(own_goal, 0) = 0 AND match_id IN ({iph})", conn, params=ids)
            base = pd.read_sql_query("SELECT situation, shot_type FROM match_shots WHERE outcome = 'Goal' "
                                     "AND COALESCE(own_goal, 0) = 0", conn)
    except Exception:
        return out
    if g.empty or len(base) < 100:
        return out
    mine = g["team_name"].isin(rv)
    conceded, scored = g[~mine], g[mine]

    def share(df, col, vals):
        return float(df[col].isin(vals).mean()) if len(df) else 0.0

    checks = [("FastBreak", ["FastBreak"], "situation", "Transição rápida",
               "atacar rápido depois de recuperar — eles demoram a recompor"),
              ("bola parada", ["FromCorner", "SetPiece", "FreeKick", "ThrowInSetPiece"], "situation", "Bola parada",
               "buscar escanteios e faltas laterais: é por aí que eles mais sofrem"),
              ("cabeça", ["Header"], "shot_type", "Jogo aéreo na área",
               "cruzar e atacar a área pelo alto: muitos gols sofridos de cabeça")]
    for label, vals, col, title, how in checks:
        sc = share(conceded, col, vals)
        sb = share(base, col, vals)
        if len(conceded) >= 6 and sc >= max(1.6 * sb, sb + .12):
            out["forcar"].append({"tipo": "estilo", "dimensao": f"gols_sofridos_{label}", "titulo": title,
                                  "nivel": "escancarado" if sc >= 2.2 * sb else "claro",
                                  "evidencia": (f"{100 * sc:.0f}% dos {len(conceded)} gols que o {rival} sofreu nos últimos "
                                                f"{len(ids)} jogos com mapa de chutes (normal da base: {100 * sb:.0f}%)"),
                                  "acao": "FORÇAR: " + how, "base": "mapa de chutes da FotMob (gols contra, sem gol contra)"})
        ss = share(scored, col, vals)
        if len(scored) >= 6 and ss >= max(1.6 * sb, sb + .12):
            out["proteger"].append({"tipo": "estilo_contra", "dimensao": f"gols_feitos_{label}", "titulo": title,
                                    "nivel": "claro",
                                    "evidencia": (f"{100 * ss:.0f}% dos {len(scored)} gols do {rival} nos últimos "
                                                  f"{len(ids)} jogos (normal: {100 * sb:.0f}%)"),
                                    "acao": f"EVITAR: é a arma deles — {title.lower()} pede atenção redobrada",
                                    "base": "mapa de chutes da FotMob"})
    return out


def merge_same_defender(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rodada 25: vários duelos contra o MESMO defensor viram um cartão só, com as evidências somadas — duas fraquezas
    independentes do mesmo jogador = "escancarado" (cruzar evidências em vez de repetir 3 cartões do mesmo lateral)."""
    out, seen = [], {}
    for x in items:
        key = (x.get("tipo"), x.get("defensor")) if x.get("tipo") == "duelo" and x.get("defensor") else None
        if key is None:
            out.append(x)
            continue
        if key in seen:
            base = out[seen[key]]
            base.setdefault("evidencias_extra", []).append(f"{x.get('titulo')}: {x.get('evidencia')}")
            base["passos"] = list(base.get("passos") or []) + [f"Outra fraqueza dele: {x.get('titulo', '').lower()} — "
                                                               f"{x.get('evidencia')}"]
            base["nivel"] = "escancarado"
            base["score"] = round(float(base.get("score") or 0) + .5 * float(x.get("score") or 0), 1)
            continue
        seen[key] = len(out)
        out.append(dict(x))
    return out


def _diverse(items: List[Dict[str, Any]], per_kind: int = 2) -> List[Dict[str, Any]]:
    """No máximo `per_kind` dicas do MESMO tipo (antes eram 4 de drible seguidas)."""
    seen: Dict[str, int] = {}
    out = []
    for x in items:
        k = str(x.get("dimensao") or x.get("tipo"))
        if seen.get(k, 0) >= per_kind:
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(x)
    return out


_ID_MEMO: Dict[Any, Any] = {}


def _identity_memo(db, names, n: int = 15) -> Dict[str, Any]:
    """Rodada 25: modelo de jogo do time (estatísticas por jogo) uma vez por time e versão dos dados do time."""
    from src.analytics.tactical_identity import stats_identity

    try:
        ver = db.team_version(list(names))
    except Exception:
        ver = ""
    key = (tuple(sorted(names)), n, ver)
    if key not in _ID_MEMO:
        if len(_ID_MEMO) > 64:
            _ID_MEMO.clear()
        _ID_MEMO[key] = stats_identity(db, list(names), n=n)
    return _ID_MEMO[key]


def analyze(db, me: str, rival: str, my_names, rv_names, my_xi, rv_xi, formation: str = "",
            rival_formation: str = "") -> Dict[str, Any]:
    ref = reference(db)
    ms, rs = team_players(db, my_names), team_players(db, rv_names)
    force = duel_findings(my_xi, rv_xi, ms, rs, ref, me, rival, attack=True)
    protect = duel_findings(my_xi, rv_xi, ms, rs, ref, me, rival, attack=False)
    # rodada 24: cada confronto vira uma dica PRÓPRIA (perfil dos dois, lado, quem apoia, nosso desenho, modelo do rival)
    try:
        from src.squad import advice as AD

        stats_identity = _identity_memo
        rv_id = stats_identity(db, list(rv_names), n=15)
        rv_ctx = AD.rival_context(rv_id.get("perfil") or {}, rv_id.get("referencia") or {})
        me_id = stats_identity(db, list(my_names), n=15)
        me_ctx = AD.rival_context(me_id.get("perfil") or {}, me_id.get("referencia") or {})
        force = AD.individualize_all(force, my_xi, rv_xi, ms, rs, ref, formation, rv_ctx, attack=True)
        protect = AD.individualize_all(protect, my_xi, rv_xi, ms, rs, ref, rival_formation, me_ctx, attack=False)
        # rodada 25: mecanismos de time (transição, bloco baixo, lados, pressão, segunda bola, área, bola parada) com
        # evidências cruzadas — aplicam-se a qualquer jogo com estatísticas
        from src.squad import patterns as PT

        refd = rv_id.get("referencia") or me_id.get("referencia") or {}
        team_force = PT.mechanisms(me, rival, me_id, rv_id, refd, attack=True)
        team_protect = PT.mechanisms(me, rival, me_id, rv_id, refd, attack=False)
    except Exception:
        team_force, team_protect = [], []
    force, protect = merge_same_defender(force), merge_same_defender(protect)
    combos = combo_findings(my_xi, rv_xi, ms, rs, ref, me, rival)
    shots = shot_findings(db, my_names, rv_names, me, rival)
    # rodada 21: mistura os tipos — combinações e "de onde saem os gols" entram entre os duelos
    force = _diverse(sorted(force, key=lambda x: (x["nivel"] != "escancarado", -x.get("score", 0)))
                     [:2] + team_force[:2] + combos["forcar"] + shots["forcar"] + force[2:] + team_force[2:])
    protect = _diverse(team_protect[:2] + combos["proteger"] + protect + team_protect[2:])
    style = style_findings(db, my_names, rv_names, me, rival)
    style += [x for x in shots["proteger"]]
    return {"forcar": force, "proteger": protect, "estilo": [s for s in style if s["tipo"] == "estilo"],
            "evitar": [s for s in style if s["tipo"] == "estilo_contra"],
            "base": (f"régua: {len(ref)} jogadores com ≥ 450 min nos últimos 12 meses" if not ref.empty
                     else "sem régua de jogadores ainda (precisa de jogos com números por jogador)"),
            "sem_numeros": not (len(ms) and len(rs))}
