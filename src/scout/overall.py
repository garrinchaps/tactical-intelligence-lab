"""
Rodada 20 — OVERALL 0–100 do Scout (escala tipo FC), calibrado com craques de referência.

Por que mudou: a nota antiga era um percentil encolhido duas vezes (minutos e nível) e misturado com reputação; tudo
ficava espremido entre 50 e 80 — Mbappé e Haaland com 79, Kane com 79, abaixo de nomes com 300 minutos.

Como é agora (tudo com dado observado; o que falta não vira zero):
  1. REPUTAÇÃO ajustada pela idade (R): maior entre o valor atual e 80% do pico de 3 anos, corrigido pela idade — o
     veterano perde valor de mercado pela idade, não pela bola (Kane, Messi, Modrić); o jovem carrega prêmio de projeção
     (que vai para o POTENCIAL, não para a nota de hoje). Percentil dentro da mesma família de posição.
  2. DESEMPENHO (P): números por 90 da função (encolhidos pelos minutos), levados ao nível da liga/clube; somados à nota
     dos Rankings (percentil dentro da competição × nível) e, se houver, à nota externa. Percentil na família.
  3. NÍVEL (L): força da liga e do clube (0–100).
  Z = (wR·R·m + wP·P + wL·L) / (wR·m + wP + wL), m = peso da reputação pelos minutos do ano (metade com pouco minuto).
  Overall = curva tipo FC sobre o percentil de Z na família (mediana ≈ 63, top 1% ≈ 86+, os melhores 90–94).

Calibração: os pesos (wR, wP, wL) são escolhidos numa grade para colocar os CRAQUES DE REFERÊNCIA (lista abaixo, pedida
pelo usuário) no topo da posição, com a trava de que a nota continue acompanhando o desempenho de quem joga muito
(correlação ≥ 0,55 com P entre quem tem 1.800+ min) — para não ser injusto com quem rende e vale pouco no mercado.
O relatório fica em data/processed/overall_calibration.json e aparece no Scout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

CALIB_PATH = Path("data/processed/overall_calibration.json")
DEFAULT_WEIGHTS = {"wR": .5, "wP": .35, "wL": .15}

REFERENCE_STARS: List[str] = [
    "Kylian Mbappé", "Erling Haaland", "Harry Kane", "Michael Olise", "Vinicius Junior", "Raphinha", "Jude Bellingham",
    "Thibaut Courtois", "Pedri", "Lamine Yamal", "Lionel Messi", "Khvicha Kvaratskhelia", "Ousmane Dembélé", "Vitinha",
    "Joshua Kimmich", "Julián Álvarez", "Gabriel Magalhães", "Martin Ødegaard", "Declan Rice", "Lautaro Martínez",
    "Bruno Guimarães", "Bruno Fernandes", "Désiré Doué", "Nuno Mendes", "Achraf Hakimi", "Yan Diomande", "Florian Wirtz",
    "Isco", "Virgil van Dijk", "Fermín López", "Luis Díaz", "Jamal Musiala", "Dayot Upamecano", "Nico Paz",
    "Nicolò Barella", "João Neves", "Enzo Fernández", "Ryan Gravenberch", "Trent Alexander-Arnold", "Marc Cucurella",
    "Pau Cubarsí", "Willian Pacho",
]

FAMILY = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "DM": "MID", "CM": "MID",
          "AM": "AM", "LM": "WIDE", "RM": "WIDE", "LW": "WIDE", "RW": "WIDE", "ST": "ST"}

# teto por família (no FC os melhores laterais ficam abaixo dos melhores atacantes)
FAMILY_CAP = {"ST": 94, "WIDE": 93, "AM": 92, "MID": 92, "CB": 92, "GK": 91, "FB": 90}

# percentil na família → overall (tipo FC)
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
    """R, P, L e peso dos minutos por atleta (sem os pesos)."""
    d = pd.DataFrame(index=u.index)
    d["_fam"] = u.get("papel", pd.Series("", index=u.index)).map(FAMILY).fillna("")
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
    d["L"] = (lvl * 100).round(1)
    m12 = _col(u, "minutos_12m").fillna(0)
    d["_m"] = .5 + .5 * (m12 / 1350).clip(0, 1)
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
    return d


def zscore(c: pd.DataFrame, w: Dict[str, float]) -> pd.Series:
    has_r = c["R"].notna()
    wr = w["wR"] * c["_m"] * has_r
    num = wr * c["R"].fillna(0) + w["wP"] * c["P"].fillna(50) + w["wL"] * c["L"]
    den = wr + w["wP"] + w["wL"]
    z = num / den
    return z.where(c["_elig"] & (c["P"].notna() | has_r))


def curve(p: pd.Series) -> pd.Series:
    """Percentil (0–1) → overall tipo FC."""
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


def calibrate(u: pd.DataFrame, comps: pd.DataFrame, anchors: Sequence[str] = REFERENCE_STARS) -> Dict[str, Any]:
    """Grade de pesos: maximiza o percentil médio dos craques na família, exigindo correlação ≥ 0,55 com o desempenho
    entre quem jogou 1.800+ min no ano."""
    found = _resolve(u, anchors)
    idx = [i for i in found.values() if pd.notna(comps.at[i, "R"]) or pd.notna(comps.at[i, "P"])]
    m12 = _col(u, "minutos_12m").fillna(0)
    regulars = comps.index[(m12 >= 1800) & comps["P"].notna()]
    best, best_obj, grid = dict(DEFAULT_WEIGHTS), -1e9, []
    for wR in (.35, .45, .55, .65):
        for wL in (.10, .15, .20):
            wP = round(1 - wR - wL, 2)
            if wP < .2:
                continue
            w = {"wR": wR, "wP": wP, "wL": wL}
            z = zscore(comps, w)
            pz = z.groupby(comps["_fam"]).rank(pct=True)
            anchor_mean = float(pz.loc[idx].mean()) if idx else 0.0
            corr = float(z.loc[regulars].corr(comps.loc[regulars, "P"], method="spearman")) if len(regulars) > 20 else 1.0
            ok = corr >= .55 or not np.isfinite(corr)
            obj = anchor_mean if ok else anchor_mean - 1
            grid.append({**w, "craques_percentil_medio": round(anchor_mean * 100, 1), "correlacao_desempenho": round(corr, 3)
                         if np.isfinite(corr) else None, "aceito": bool(ok)})
            if obj > best_obj:
                best, best_obj = w, obj
    return {"pesos": best, "grade": grid, "encontrados": found}


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
    if reference is not None and "_ovr_z" in reference:
        pz = _pct(z, comps["_fam"], reference.assign(_z=reference["_ovr_z"]), "_z") / 100
    else:
        pz = z.groupby(comps["_fam"]).rank(pct=True)
    ovr = curve(pz)
    # elite pela COLOCAÇÃO na família (não depende do tamanho do grupo): 1º = 94, 2º ≈ 93, 5º ≈ 91, 10º ≈ 90, 25º ≈ 89
    ref_z = reference["_ovr_z"] if reference is not None and "_ovr_z" in reference else z
    ref_f = reference["_fam"] if reference is not None and "_fam" in reference else comps["_fam"]
    for fam, idx in z.groupby(comps["_fam"]).groups.items():
        pool = np.sort(pd.to_numeric(ref_z[ref_f == fam], errors="coerce").dropna().values)
        cap = FAMILY_CAP.get(fam, 92)
        if len(pool) < 60:                                # grupo pequeno: só o teto da posição
            ovr.loc[idx] = ovr.loc[idx].clip(upper=cap)
            continue
        zz = z.loc[idx]
        k = (len(pool) - np.searchsorted(pool, zz.values, side="right")) + (1 if reference is not None else 1)
        k = pd.Series(k, index=idx).where(zz.notna())
        elite = (cap - 1.6 * np.log(k.clip(lower=1))).where(k <= 25)
        both = pd.concat([ovr.loc[idx].clip(upper=cap - 1), elite.round(0)], axis=1).max(axis=1, skipna=True)
        ovr.loc[idx] = both.where(zz.notna())
    out["qualidade"] = ovr.where(ovr.notna(), np.nan)
    out["ovr_reputacao"] = comps["R"].round(0)
    out["ovr_desempenho"] = comps["P"].round(0)
    out["ovr_nivel"] = comps["L"]
    out["_ovr_z"] = z
    out["_fam"] = comps["_fam"]
    for c in ("_rep_val", "_perf_adj", "_rank_nota", "_ext"):     # régua para medir o elenco na mesma escala
        out[c] = comps[c]
    src = out.get("fonte_qualidade", pd.Series("", index=out.index)).fillna("").astype(str)
    out["fonte_qualidade"] = np.where(out["qualidade"].notna(),
                                      f"overall: reputação ajustada pela idade ({weights['wR']:.0%}) + desempenho na "
                                      f"função ({weights['wP']:.0%}) + nível da liga/clube ({weights['wL']:.0%})",
                                      src)
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
    rows = []
    for name, i in (report.get("encontrados") or {}).items():
        fam = u.at[i, "_fam"]
        z = u["_ovr_z"]
        pz = z[u["_fam"] == fam].rank(pct=True)
        rows.append({"craque": name, "no_universo": str(u.at[i, "nome"]), "posicao": str(u.at[i, "papel"]),
                     "overall": None if pd.isna(u.at[i, "qualidade"]) else int(u.at[i, "qualidade"]),
                     "percentil_na_posicao": None if pd.isna(pz.get(i)) else round(float(pz.get(i)) * 100, 1)})
    missing = [n for n in REFERENCE_STARS if n not in (report.get("encontrados") or {})]
    top5 = sum(1 for r in rows if (r["percentil_na_posicao"] or 0) >= 95)
    doc = {"pesos": report["pesos"], "grade": report["grade"], "craques": rows, "nao_encontrados": missing,
           "resumo": f"{top5} de {len(rows)} craques de referência no top 5% da posição"
                     + (f"; {len(missing)} não estão no universo (sem cadastro/jogos recentes)" if missing else "")}
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
