"""
Encontra, dentro de uma pergunta em linguagem natural, a partida de que ela fala.

"Na final da Copa de 2022, como a Argentina pressionou a França?" → times {Argentina, France}, ano 2022 →
partida mais rica do catálogo entre os dois (eventos > boxscore > placar). Com um time só e "último jogo",
"ontem" etc. → o jogo mais recente dele. Sem time citado → None (o chat continua na partida aberta).

Busca por n-gramas da pergunta num índice de nomes normalizados (sem acento, sem FC/EC…), incluindo os nomes em
português das seleções (Brasil → Brazil, França → France…).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd

from src.data_hub.search import LEVEL_RANK, SOURCE_RANK, TEAM_ALIASES, norm
from src.data_lake.ids import team_core

AMBIGUOUS = {"inter", "real", "sporting", "athletic", "atletico", "united", "city", "nacional", "independiente",
             "america", "universidad", "union", "racing", "olympique", "dynamo", "rapid", "national", "brasil"}
MONTH_ROUND = re.compile(r"\b(final|semifinal|semi-final|quartas|oitavas|decisao|decisão)\b")


@dataclass
class LocatedMatch:
    match_id: int
    teams: List[str]
    year: Optional[int]
    label: str
    candidates: pd.DataFrame = field(default_factory=pd.DataFrame)


def build_index(catalog: pd.DataFrame) -> Dict[str, List[str]]:
    names = pd.unique(pd.concat([catalog["home_team_name"], catalog["away_team_name"]]).dropna())
    idx: Dict[str, List[str]] = {}
    for n in names:
        for key in {team_core(n), norm(n)}:
            if key and len(key) >= 3:
                idx.setdefault(key, []).append(n)
    for pt, en in TEAM_ALIASES.items():                     # nomes em português das seleções
        for e in en:
            if e in names:
                idx.setdefault(norm(pt), []).append(e)
    return idx


def find_teams(question: str, index: Dict[str, List[str]]) -> List[List[str]]:
    """Grupos de nomes do catálogo citados na pergunta (um grupo por time), na ordem em que aparecem."""
    toks = re.findall(r"[a-z0-9']+(?:-[a-z0-9]+)*", norm(question))
    found, used = [], set()
    for size in (4, 3, 2, 1):
        for i in range(len(toks) - size + 1):
            if any(j in used for j in range(i, i + size)):
                continue
            gram = " ".join(toks[i:i + size])
            if size == 1 and (gram in AMBIGUOUS and gram not in ("brasil",) or len(gram) < 4):
                continue
            hit = index.get(gram) or index.get(team_core(gram))
            if hit:
                found.append((i, sorted(set(hit))))
                used.update(range(i, i + size))
    found.sort()
    groups: List[List[str]] = []
    for _, g in found:
        if g not in groups:
            groups.append(g)
    return groups[:2]


def locate(question: str, catalog: pd.DataFrame, index: Optional[Dict[str, List[str]]] = None,
           today: Optional[date] = None) -> Optional[LocatedMatch]:
    if catalog is None or catalog.empty:
        return None
    index = index or build_index(catalog)
    t = norm(question)
    groups = find_teams(question, index)
    if not groups:
        return None
    ym = re.search(r"\b(18[7-9]\d|19\d\d|20[0-4]\d)\b", t)
    year = int(ym.group(1)) if ym else None
    c = catalog
    a = set(groups[0])
    if len(groups) >= 2:
        b = set(groups[1])
        sel = c[(c["home_team_name"].isin(a) & c["away_team_name"].isin(b)) | (c["home_team_name"].isin(b) & c["away_team_name"].isin(a))]
    else:
        sel = c[c["home_team_name"].isin(a) | c["away_team_name"].isin(a)]
        recent = re.search(r"\bultim[oa]|\bontem\b|\bhoje\b|\brecente|\bdomingo\b|\bsabado\b|\brodada\b", t)
        if not recent and not year:
            return None                                       # um time só, sem indicação de qual jogo
        if re.search(r"\bontem\b", t):
            d = (today or date.today()) - timedelta(days=1)
            sel = sel[sel["match_date"].astype(str) == d.isoformat()]
    if year is not None:
        sel = sel[sel["match_date"].astype(str).str[:4] == str(year)]
    if sel.empty:
        return None
    sel = sel.copy()
    sel["lr"] = sel["data_level"].map(LEVEL_RANK).fillna(0)
    sel["sr"] = sel["data_source"].map(SOURCE_RANK).fillna(0)
    if MONTH_ROUND.search(t) and "round_name" in sel:            # "final", "semifinal": prefere a fase citada
        r = sel[sel["round_name"].astype(str).str.lower().str.contains("final")]
        sel = r if not r.empty else sel
    sel = sel.sort_values(["match_date", "lr", "sr"], ascending=[False, False, False])
    best = sel.iloc[0]
    hs, as_ = best.get("home_score"), best.get("away_score")
    score = f"{int(hs)}–{int(as_)}" if pd.notna(hs) and pd.notna(as_) else "x"
    return LocatedMatch(int(best["match_id"]), [", ".join(g[:1]) for g in groups], year,
                        f"{best['home_team_name']} {score} {best['away_team_name']} · {best['competition_name']} · {best['match_date']}",
                        sel.head(6))
