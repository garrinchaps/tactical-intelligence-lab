"""
Rodada 20/21 — OVERALL 0–100 do Scout (escala tipo FC), calibrado com craques de referência E com tetos.

Rodada 21 (pedido do usuário): "90+ é craque mundial" — a régua anterior dava 89+ aos 25 primeiros de CADA posição
(~175 jogadores) e a reputação ainda pesava para quem jogou pouco (Maddison com 229 min = 88).

Componentes (percentil dentro da família de posição; o que falta não vira zero):
  R  reputação ajustada pela idade (valor atual ou 80% do pico de 3 anos; veterano não é punido pela idade)
  P  desempenho na função (números por 90 encolhidos pelos minutos × nível) + nota dos Rankings + nota externa
  T  nota média da FotMob nos últimos 12 meses, ajustada pelo nível da liga (só com 450+ min)
  L  nível da liga/clube
Z = média ponderada (a reputação vale menos para quem jogou pouco). Z é padronizado DENTRO da família (as posições
competem em pé de igualdade) e encolhido pela DISPONIBILIDADE (minutos do ano / 1.800). O overall sai da COLOCAÇÃO
GLOBAL nessa régua: só ~10 jogadores do mundo passam de 90, ~40 de 87, ~80 de 85, ~400 de 80; o resto segue uma curva
tipo FC (mediana ≈ 62). Teto por posição (lateral ≤ 90, goleiro ≤ 91…).

Calibração: grade de pesos (wR, wP, wT, wL) escolhida para (1) pôr os CRAQUES DE REFERÊNCIA no alto e (2) respeitar os
TETOS de referência (jogadores que o usuário apontou como 83–85/85–88 no máximo), mantendo correlação ≥ 0,55 com o
desempenho de quem joga muito. Relatório em data/processed/overall_calibration.json e no Scout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

CALIB_PATH = Path("data/processed/overall_calibration.json")
DEFAULT_WEIGHTS = {"wR": .35, "wP": .25, "wT": .25, "wL": .15}

REFERENCE_STARS: List[str] = [
    "Kylian Mbappé", "Erling Haaland", "Harry Kane", "Michael Olise", "Vinicius Junior", "Raphinha", "Jude Bellingham",
    "Thibaut Courtois", "Pedri", "Lamine Yamal", "Lionel Messi", "Khvicha Kvaratskhelia", "Ousmane Dembélé", "Vitinha",
    "Joshua Kimmich", "Julián Álvarez", "Gabriel Magalhães", "Martin Ødegaard", "Declan Rice", "Lautaro Martínez",
    "Bruno Guimarães", "Bruno Fernandes", "Désiré Doué", "Nuno Mendes", "Achraf Hakimi", "Yan Diomande", "Florian Wirtz",
    "Isco", "Virgil van Dijk", "Fermín López", "Luis Díaz", "Dayot Upamecano", "Nico Paz",
    "Nicolò Barella", "João Neves", "Enzo Fernández", "Ryan Gravenberch", "Trent Alexander-Arnold", "Marc Cucurella",
    "Pau Cubarsí", "Willian Pacho",
]

# tetos apontados pelo usuário (rodada 21): bons jogadores, mas não craques mundiais — no máximo isto
REFERENCE_CEILINGS: Dict[str, int] = {
    "James Maddison": 85, "Santiago Giménez": 85, "Gabriel Jesus": 85, "Benjamin Šeško": 85, "Dušan Vlahović": 85,
    "Frenkie de Jong": 85, "Jarrad Branthwaite": 85, "Jamal Musiala": 85, "Alexander Isak": 85, "Serge Gnabry": 85,
    "Marcus Rashford": 85, "Christopher Nkunku": 85, "Hugo Ekitiké": 85, "Maxence Lacroix": 87,
}

FAMILY = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "DM": "MID", "CM": "MID",
          "AM": "AM", "LM": "WIDE", "RM": "WIDE", "LW": "WIDE", "RW": "WIDE", "ST": "ST"}

# teto por família (no FC os melhores laterais ficam abaixo dos melhores atacantes)
FAMILY_CAP = {"ST": 94, "WIDE": 93, "AM": 92, "MID": 92, "CB": 92, "GK": 91, "FB": 90}

# colocação GLOBAL (régua padronizada por posição) → overall. Calibrada para um universo de ~20 mil jogadores; em
# universos menores a colocação é reescalada (o 1º de uma base pequena não vira 94 automaticamente).
LADDER_R = [1, 2, 3, 5, 10, 20, 40, 80, 150, 300, 600, 1200]
LADDER_O = [94, 93, 92, 91, 90, 88.5, 87, 85, 83, 81, 78, 75]
N_REF = 20000
# abaixo da escada: percentil (dentro do resto) → overall
REST_P = [0.0, .05, .25, .50, .75, .90, 1.0]
REST_O = [38, 46, 55, 62, 68, 72, 75]
# legado (rodada 20) — mantido para leitura de relatórios antigos
CURVE_P = [0.0, .05, .20, .40, .60, .75, .85, .92, .96, .985, .995, .9985, 1.0]
CURVE_O = [38, 46, 54, 60, 65, 69, 73, 77, 81, 85, 88, 90.5, 94]


def _col(u: pd.DataFrame, name: str) -> pd.Series:
    """Coluna numérica (ou toda vazia, se a fonte não traz) — nunca um escalar solto."""
    if name in u:
        return pd.to_numeric(u[name], errors="coerce")
    return pd.Series(np.nan, index=u.index, dtype=float)


def age_factor(age: pd.Series) -> pd.Series:
    """Corrige o valor de mercado pela idade: ≥ 28 anos o mercado desconta a idade (×1 a ×2,1 aos 37); ≤ 22 o preço
    embute projeção (×0,75 aos 18)."""
    a = pd.to_numeric(age, errors="coerce")
    up = 1 + .12 * (a - 27).clip(lower=0, upper=10)
    down = 1 - .05 * (23 - a).clip(lower=0, upper=5)
    return (up * down).fillna(1.0)


def _pct(values: pd.Series, groups: pd.Series, reference: Optional[pd.DataFrame] = None, col: str = "") -> pd.Series:
    """Percentil (0–100) dentro da família; com `reference`, contra a distribuição de referência (mesma régua)."""
    v = pd.to_numeric(values, errors="coerce")
    if reference is None:
        return v.groupby(groups).rank(pct=True) * 100
    out = pd.Series(np.nan, index=v.index)
    for fam, idx in v.groupby(groups).groups.items():
        ref = pd.to_numeric(reference.loc[reference["_fam"] == fam, col], errors="coerce").dropna().sort_values().values
        if not len(ref):
            continue
        x = v.loc[idx]
        out.loc[idx] = np.searchsorted(ref, x.values, side="right") / len(ref) * 100
        out.loc[idx[x.isna()]] = np.nan
    return out


def components(u: pd.DataFrame, reference: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """R, P, T, L, disponibilidade e peso dos minutos por atleta (sem os pesos)."""
    d = pd.DataFrame(index=u.index)
    d["_fam"] = (u["papel"] if "papel" in u else pd.Series("", index=u.index)).map(FAMILY).fillna("")
    val = _col(u, "valor_mercado_eur")
    peak = _col(u, "valor_pico_3a_eur") * .8
    rep_val = pd.concat([val, peak], axis=1).max(axis=1, skipna=True)
    rep_val = rep_val.where(rep_val > 0)
    d["_rep_val"] = np.log1p(rep_val * age_factor(_col(u, "idade")))
    raw = _col(u, "_perf_raw")
    conf = _col(u, "_conf").fillna(0)
    lvl = _col(u, "_lvl")
    lvl = lvl.fillna(_col(u, "nivel_competicao_principal")).fillna(.45).clip(0, 1)
    perf = 50 + (raw - 50) * conf
    d["_perf_adj"] = perf * (.55 + .45 * lvl)
    d["_rank_nota"] = _col(u, "nota_rankings")
    d["_ext"] = _col(u, "nota_externa")
    m12 = _col(u, "minutos_12m").fillna(0)
    rating = _col(u, "rating_12m")
    # nota FotMob ajustada pela liga: 0,9 ponto entre a liga mais forte e a mais fraca (7,3 na Premier ≈ 7,8 abaixo)
    d["_rating_adj"] = (rating + .9 * (lvl - .7)).where(m12 >= 450)
    d["L"] = (lvl * 100).round(1)
    d["_m"] = .35 + .65 * (m12 / 1350).clip(0, 1)
    d["_avail"] = (m12 / 1800).clip(0, 1)
    d["_elig"] = raw.notna() | rep_val.notna()
    if "qualidade" in u:                                  # quem a régua antiga deixou sem nota (0 min no ano, sem dado)
        d["_elig"] &= pd.to_numeric(u["qualidade"], errors="coerce").notna()
    ref = reference
    d["R"] = _pct(d["_rep_val"].where(d["_elig"]), d["_fam"], ref, "_rep_val")
    p_stats = _pct(d["_perf_adj"].where(d["_elig"]), d["_fam"], ref, "_perf_adj")
    p_rank = _pct(d["_rank_nota"].where(d["_elig"]), d["_fam"], ref, "_rank_nota")
    p_ext = _pct(d["_ext"].where(d["_elig"]), d["_fam"], ref, "_ext")
    parts = pd.concat([p_stats.rename("s"), p_rank.rename("r"), p_ext.rename("e")], axis=1)
    w = pd.DataFrame({"s": .6 * parts["s"].notna(), "r": .3 * parts["r"].notna(), "e": .1 * parts["e"].notna()})
    d["P"] = (parts.fillna(0) * w).sum(axis=1) / w.sum(axis=1).replace(0, np.nan)
    d["T"] = _pct(d["_rating_adj"].where(d["_elig"]), d["_fam"], ref, "_rating_adj")
    return d


def zscore(c: pd.DataFrame, w: Dict[str, float]) -> pd.Series:
    """Média ponderada dos componentes disponíveis (0–100). A reputação pesa menos para quem jogou pouco."""
    has_r, has_t, has_p = c["R"].notna(), c["T"].notna() if "T" in c else pd.Series(False, index=c.index), c["P"].notna()
    wr = w.get("wR", 0) * c["_m"] * has_r
    wt = w.get("wT", 0) * has_t
    wp = w.get("wP", 0) * has_p
    num = wr * c["R"].fillna(0) + wt * c.get("T", pd.Series(0, index=c.index)).fillna(0) + wp * c["P"].fillna(0) \
        + w.get("wL", 0) * c["L"]
    den = wr + wt + wp + w.get("wL", 0)
    z = num / den.replace(0, np.nan)
    return z.where(c["_elig"] & (has_p | has_r | has_t))


def standardize(z: pd.Series, comps: pd.DataFrame, fam_stats: Optional[Dict[str, Any]] = None) -> tuple:
    """Z → régua padronizada por família, encolhida pela disponibilidade. Devolve (s, estatísticas da família)."""
    if fam_stats is None:
        g = z.groupby(comps["_fam"])
        fam_stats = {f: (float(m), float(sd) if sd and sd > 0 else 1.0) for f, m, sd in zip(g.mean().index, g.mean(), g.std())}
    mu = comps["_fam"].map(lambda f: fam_stats.get(f, (50.0, 15.0))[0])
    sd = comps["_fam"].map(lambda f: fam_stats.get(f, (50.0, 15.0))[1])
    s = (z - mu) / sd
    avail = comps["_avail"] ** .7
    s = s * (.45 + .55 * avail)                          # quem jogou pouco no ano não chega ao topo
    return s, fam_stats


def ladder(s: pd.Series, ref_sorted: Optional[np.ndarray] = None) -> pd.Series:
    """Colocação global → overall. `ref_sorted` = régua de referência (ordem crescente) para medir outro grupo."""
    pool = np.sort(s.dropna().values) if ref_sorted is None else ref_sorted
    n = len(pool)
    out = pd.Series(np.nan, index=s.index)
    if n == 0:
        return out
    ok = s.notna()
    rank = n - np.searchsorted(pool, s[ok].values, side="right") + 1          # 1 = melhor
    scale = max(1.0, N_REF / max(n, 1))                                     # base pequena: reescala a colocação
    r_eff = np.maximum(rank * scale, 1.0)
    top_r = LADDER_R[-1]
    lad = np.interp(np.log(r_eff), np.log(LADDER_R), LADDER_O)
    n_rest = max(n * scale - top_r, 1.0)
    p_rest = np.clip(1 - (r_eff - top_r) / n_rest, 0, 1)
    rest = np.interp(p_rest, REST_P, REST_O)
    out.loc[ok] = np.where(r_eff <= top_r, lad, rest)
    return out


def curve(p: pd.Series) -> pd.Series:
    """(legado) percentil (0–1) → overall."""
    return pd.Series(np.interp(p.fillna(np.nan).values, CURVE_P, CURVE_O), index=p.index).where(p.notna()).round(0)


def _resolve(u: pd.DataFrame, names: Sequence[str]) -> Dict[str, int]:
    """Craque de referência → linha do universo (homônimo: o de maior valor de mercado)."""
    from src.data_lake.ids import player_core

    core = u["_core"].astype(str) if "_core" in u else u["nome"].map(player_core)
    val = _col(u, "valor_mercado_eur").fillna(0)
    out = {}
    for n in names:
        c = player_core(n)
        hit = core[core == c]
        if hit.empty:
            continue
        out[n] = int(val.loc[hit.index].idxmax())
    return out


def _overall(comps: pd.DataFrame, w: Dict[str, float]) -> pd.Series:
    s, _ = standardize(zscore(comps, w), comps)
    ovr = ladder(s)
    cap = comps["_fam"].map(FAMILY_CAP).fillna(92)
    return ovr.clip(upper=cap).round(0)


def calibrate(u: pd.DataFrame, comps: pd.DataFrame, anchors: Sequence[str] = REFERENCE_STARS,
              ceilings: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Grade de pesos: craques no alto (média do overall, contado até 92) − 3 × o quanto os nomes com TETO passam do
    teto; exige correlação ≥ 0,55 com o desempenho entre quem jogou 1.800+ min no ano."""
    ceilings = REFERENCE_CEILINGS if ceilings is None else ceilings
    found = _resolve(u, anchors)
    capped = _resolve(u, list(ceilings))
    m12 = _col(u, "minutos_12m").fillna(0)
    regulars = comps.index[(m12 >= 1800) & comps["P"].notna()]
    best, best_obj, grid = dict(DEFAULT_WEIGHTS), -1e9, []
    for wR in (.2, .3, .4, .5):
        for wT in (.15, .25, .35):
            for wL in (.10, .15):
                wP = round(1 - wR - wT - wL, 2)
                if wP < .1:
                    continue
                w = {"wR": wR, "wP": wP, "wT": wT, "wL": wL}
                ovr = _overall(comps, w)
                stars = [min(float(ovr.loc[i]), 92.0) for i in found.values() if pd.notna(ovr.loc[i])]
                excess = [max(0.0, float(ovr.loc[i]) - ceilings[n]) for n, i in capped.items() if pd.notna(ovr.loc[i])]
                z = zscore(comps, w)
                corr = float(z.loc[regulars].corr(comps.loc[regulars, "P"], method="spearman")) if len(regulars) > 20 else 1.0
                ok = corr >= .55 or not np.isfinite(corr)
                obj = (np.mean(stars) if stars else 0.0) - 3 * (np.mean(excess) if excess else 0.0) - (0 if ok else 50)
                grid.append({**w, "craques_overall_medio": round(float(np.mean(stars)), 1) if stars else None,
                             "tetos_estourados_medio": round(float(np.mean(excess)), 2) if excess else 0.0,
                             "correlacao_desempenho": round(corr, 3) if np.isfinite(corr) else None, "aceito": bool(ok)})
                if obj > best_obj:
                    best, best_obj = w, obj
    return {"pesos": best, "grade": grid, "encontrados": found, "tetos": capped}


def finalize_overall(u: pd.DataFrame, calibrate_now: bool = True, reference: Optional[pd.DataFrame] = None,
                     weights: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    """Recalcula `qualidade` como OVERALL 0–100. Guarda a nota antiga em `qualidade_base` e os componentes."""
    if u is None or u.empty:
        return u
    out = u.copy()
    if "qualidade_base" not in out:
        out["qualidade_base"] = pd.to_numeric(out.get("qualidade"), errors="coerce")
    comps = components(out, reference)
    report: Dict[str, Any] = {}
    if weights is None:
        if calibrate_now and reference is None:
            report = calibrate(out, comps)
            weights = report["pesos"]
        else:
            weights = load_weights()
    z = zscore(comps, weights)
    if reference is not None and "_ovr_s" in reference and "_ovr_z" in reference:
        rz = pd.to_numeric(reference["_ovr_z"], errors="coerce")
        g = rz.groupby(reference["_fam"])
        stats = {f: (float(m), float(sd) if sd and sd > 0 else 1.0) for f, m, sd in zip(g.mean().index, g.mean(), g.std())}
        s, _ = standardize(z, comps, stats)
        ovr = ladder(s, np.sort(pd.to_numeric(reference["_ovr_s"], errors="coerce").dropna().values))
    else:
        s, _ = standardize(z, comps)
        ovr = ladder(s)
    cap = comps["_fam"].map(FAMILY_CAP).fillna(92)
    out["qualidade"] = ovr.clip(upper=cap).round(0)
    out["ovr_reputacao"] = comps["R"].round(0)
    out["ovr_desempenho"] = comps["P"].round(0)
    out["ovr_nota_fotmob"] = comps["T"].round(0)
    out["ovr_nivel"] = comps["L"]
    out["ovr_disponibilidade"] = (comps["_avail"] * 100).round(0)
    out["_ovr_z"] = z
    out["_ovr_s"] = s
    out["_fam"] = comps["_fam"]
    for c in ("_rep_val", "_perf_adj", "_rank_nota", "_ext", "_rating_adj"):     # régua para medir o elenco igual
        out[c] = comps[c]
    src = out.get("fonte_qualidade", pd.Series("", index=out.index)).fillna("").astype(str)
    out["fonte_qualidade"] = np.where(
        out["qualidade"].notna(),
        f"overall: reputação ajustada pela idade ({weights.get('wR', 0):.0%}) + desempenho na função "
        f"({weights.get('wP', 0):.0%}) + nota FotMob ajustada pela liga ({weights.get('wT', 0):.0%}) + nível "
        f"({weights.get('wL', 0):.0%}), padronizado por posição e pelos minutos do ano", src)
    out = _recompute_potential(out)
    if report:
        save_report(out, report)
    return out


def _recompute_potential(d: pd.DataFrame) -> pd.DataFrame:
    """Teto = overall de hoje + crescimento esperado até ~26 anos (mesma ideia de antes, na escala nova)."""
    age = _col(d, "idade")
    q = _col(d, "qualidade")
    conf = _col(d, "confianca_pct").fillna(0) / 100
    lvl = _col(d, "_lvl").fillna(.5)
    prec = _col(d, "precocidade").fillna(30) / 100
    youth = _col(d, "selecao_base_jogos").fillna(0)
    years = (26 - age.fillna(30)).clip(lower=0, upper=9)
    growth = years * (.55 + .7 * conf + 1.0 * prec + .35 * (youth > 0)) * (.7 + .5 * lvl)
    d["potencial_teto"] = (q + growth).clip(upper=95).where(q.notna()).round(0)
    return d


def save_report(u: pd.DataFrame, report: Dict[str, Any]) -> None:
    def row(name, i, teto=None):
        q = u.at[i, "qualidade"]
        r = {"craque": name, "no_universo": str(u.at[i, "nome"]), "posicao": str(u.at[i, "papel"]),
             "overall": None if pd.isna(q) else int(q),
             "minutos_12m": None if pd.isna(_col(u, "minutos_12m").get(i)) else int(_col(u, "minutos_12m").get(i))}
        if teto is not None:
            r["teto"] = teto
        return r
    rows = [row(n, i) for n, i in (report.get("encontrados") or {}).items()]
    caps = [row(n, i, REFERENCE_CEILINGS.get(n)) for n, i in (report.get("tetos") or {}).items()]
    missing = [n for n in REFERENCE_STARS if n not in (report.get("encontrados") or {})]
    q = _col(u, "qualidade")
    dist = {"90+": int((q >= 90).sum()), "87+": int((q >= 87).sum()), "85+": int((q >= 85).sum()),
            "80+": int((q >= 80).sum()), "mediana": None if q.dropna().empty else float(q.median())}
    hi = sum(1 for r in rows if (r["overall"] or 0) >= 85)
    over = [r["craque"] for r in caps if r["overall"] is not None and r["overall"] > r["teto"]]
    doc = {"pesos": report["pesos"], "grade": report["grade"], "craques": rows, "tetos": caps, "distribuicao": dist,
           "nao_encontrados": missing,
           "resumo": f"{hi} de {len(rows)} craques com 85+ · {dist['90+']} jogadores com 90+ no universo"
                     + (f" · tetos estourados: {', '.join(over)}" if over else " · nenhum teto estourado")}
    try:
        CALIB_PATH.parent.mkdir(parents=True, exist_ok=True)
        CALIB_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass


def load_weights() -> Dict[str, float]:
    try:
        return dict(json.loads(CALIB_PATH.read_text(encoding="utf-8"))["pesos"])
    except Exception:
        return dict(DEFAULT_WEIGHTS)


def load_report() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(CALIB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
