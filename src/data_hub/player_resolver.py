"""
Resolução de homônimos e fusão de atletas entre fontes — v36, item B4.

Chave de identidade: nome normalizado + data de nascimento + nacionalidade + primeiro clube profissional.
NUNCA só o nome. Cada par candidato recebe uma pontuação:

    nome igual (ou curto ⊂ completo / abreviado, com UM único candidato) ........ +0,45
    mesma data de nascimento .................................................... +0,40   (datas diferentes → nunca)
    mesma nacionalidade ......................................................... +0,15   (diferentes → nunca)
    mesmo primeiro clube profissional ........................................... +0,10
    clube/seleção em comum (ex.: jogou pela Argentina e a nacionalidade é Argentina) +0,30
    jogaram pela mesma equipe no MESMO jogo (são duas pessoas) .................. nunca

≥ MERGE_AT → mesma pessoa (fundida). Entre REVIEW_AT e MERGE_AT → `player_merge_candidates` (revisão, não funde).
Fundir soma estatísticas SEM duplicar partidas: a mesma partida em duas fontes (mesma data ±1 dia e mesmos times)
conta uma vez só (`merge_match_rows`).
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

from src.data_lake.ids import norm, player_core, team_core

MERGE_AT = 0.75
REVIEW_AT = 0.45
NAME_SCORE = 0.45


def _toks(name: str) -> List[str]:
    return [t for t in re.split(r"[\s\-\.]+", norm(name)) if t]


def profiles(idx: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por grafia (core): nomes, clubes/seleções, nascimento, nacionalidade, 1º clube, jogos (data|time)."""
    d = idx.copy()
    for c in ("nascimento", "nacionalidade", "primeiro_clube", "jogos_chave"):
        if c not in d:
            d[c] = None
    d["core"] = d.get("core", d["nome"].map(player_core))
    d = d[d["core"].astype(str) != ""]

    def first(s):
        v = [x for x in s if isinstance(x, str) and x.strip()]
        return v[0] if len(set(v)) == 1 else ("" if not v else "|CONFLITO|")

    def union(s):
        out: Set[str] = set()
        for x in s:
            if isinstance(x, (set, list, tuple)):
                out |= set(x)
        return out
    g = d.groupby("core")
    return pd.DataFrame({
        "nomes": g["nome"].agg(lambda s: sorted(set(map(str, s)))),
        "clubes": g["clube"].agg(lambda s: {team_core(x) for x in s if isinstance(x, str) and x}),
        "nascimento": g["nascimento"].agg(lambda s: first([str(x)[:10] for x in s if isinstance(x, str) and len(str(x)) >= 8])),
        "nacionalidade": g["nacionalidade"].agg(lambda s: first([norm(x) for x in s if isinstance(x, str)])),
        "primeiro_clube": g["primeiro_clube"].agg(lambda s: first([team_core(x) for x in s if isinstance(x, str)])),
        "jogos_chave": g["jogos_chave"].agg(union),
    }).reset_index()


def score(a: Dict, b: Dict, name_score: float) -> Tuple[float, List[str]]:
    """Pontuação de identidade entre dois perfis; -1 = certamente pessoas diferentes."""
    why = [f"nome ({name_score:.2f})"]
    s = name_score
    for field, w, lab in (("nascimento", 0.40, "nascimento"), ("nacionalidade", 0.15, "nacionalidade"),
                          ("primeiro_clube", 0.10, "1º clube")):
        x, y = a.get(field) or "", b.get(field) or ""
        if "|CONFLITO|" in (x, y):
            continue
        if x and y:
            if x != y:
                return -1.0, [f"{lab} diferente"]
            s += w
            why.append(lab)
    if a.get("jogos_chave") and b.get("jogos_chave") and set(a["jogos_chave"]) & set(b["jogos_chave"]):
        return -1.0, ["jogaram juntos no mesmo jogo"]
    teams_a = set(a.get("clubes") or set()) | ({a["nacionalidade"]} if a.get("nacionalidade") else set())
    teams_b = set(b.get("clubes") or set()) | ({b["nacionalidade"]} if b.get("nacionalidade") else set())
    if (set(a.get("clubes") or ()) & teams_b) or (set(b.get("clubes") or ()) & teams_a):
        s += 0.30
        why.append("clube/seleção em comum")
    return round(s, 2), why


def candidate_pairs(prof: pd.DataFrame) -> List[Tuple[int, int, float]]:
    """Pares a comparar (sem todos-contra-todos): mesmo core, curto ⊂ completo e abreviado ("L. Messi")."""
    toks = {i: r.core.split() for i, r in prof.iterrows()}
    raw = {i: _toks(r.nomes[0]) for i, r in prof.iterrows()}
    by_first_tok: Dict[Tuple[str, str], List[int]] = {}
    by_ini_tok: Dict[Tuple[str, str], List[int]] = {}
    for i, t in toks.items():
        if len(t) >= 2:
            for x in set(t[1:]):
                by_first_tok.setdefault((t[0], x), []).append(i)
                by_ini_tok.setdefault((t[0][0], x), []).append(i)
    pairs = []
    for i, t in toks.items():
        if len(t) >= 2:
            cands = [j for j in by_first_tok.get((t[0], t[-1]), []) if j != i and len(toks[j]) > len(t) and set(t) <= set(toks[j])]
            if len(cands) == 1:
                pairs.append((i, cands[0], NAME_SCORE))
            elif cands:
                pairs += [(i, j, NAME_SCORE - 0.15) for j in cands]   # ambíguo: nome vale menos
        r = raw[i]
        if len(r) == 2 and len(r[0]) == 1:                    # abreviado: decidido depois das outras fusões
            pairs += [(i, j, -1.0) for j in by_ini_tok.get((r[0], r[1]), []) if j != i]
    return pairs


def resolve(idx: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
    """
    Devolve (pessoa por linha de `idx`, candidatos para revisão). Linhas com o mesmo core só são a mesma pessoa se
    não houver conflito de nascimento/nacionalidade (homônimos com datas diferentes ficam separados).
    """
    if idx is None or idx.empty:
        return pd.Series(dtype=str), pd.DataFrame(columns=["a", "b", "pontos", "motivos"])
    d = idx.copy()
    d["core"] = d.get("core", d["nome"].map(player_core))
    d["nascimento"] = d.get("nascimento", "").fillna("") if "nascimento" in d else ""
    # homônimos: mesmo core com nascimentos diferentes → cada data é uma pessoa; sem data fica à parte
    dob = d["nascimento"].astype(str).str[:10].where(d["nascimento"].astype(str).str.len() >= 8, "")
    n = dob[dob != ""].groupby(d.loc[dob != "", "core"]).nunique()
    multi = set(n[n > 1].index)
    d["key"] = d["core"]
    m = d["core"].isin(multi)
    d.loc[m, "key"] = d.loc[m, "core"] + "|" + dob[m].replace("", "?")
    prof = profiles(d.assign(core=d["key"]))
    pos = {r.core: i for i, r in prof.iterrows()}
    parent = list(range(len(prof)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    review = []
    recs = prof.to_dict("records")
    pairs = candidate_pairs(prof)
    full = [p for p in pairs if p[2] >= 0]
    abbr: Dict[int, List[int]] = {}
    for i, j, _ in pairs:
        if _ < 0:
            abbr.setdefault(i, []).append(j)

    def merged_profile(r):
        members = [recs[k] for k in range(len(recs)) if root(k) == r]
        out = dict(members[0])
        out["clubes"] = set().union(*[m.get("clubes") or set() for m in members])
        for f in ("nascimento", "nacionalidade", "primeiro_clube"):
            vals = {m.get(f) for m in members if m.get(f)}
            out[f] = vals.pop() if len(vals) == 1 else ""
        return out
    for i, j, ns in full:
        if "|?" in recs[i]["core"] or "|?" in recs[j]["core"]:
            continue
        s, why = score(recs[i], recs[j], ns)
        if s >= MERGE_AT:
            ri, rj = root(i), root(j)
            if ri != rj:
                parent[rj] = ri                                # a grafia mais curta (nome comum) vira a chave
        elif s >= REVIEW_AT:
            review.append({"a": recs[i]["nomes"][0], "b": recs[j]["nomes"][0], "pontos": s, "motivos": ", ".join(why)})
    # abreviados ("L. Messi"): comparados com a PESSOA já fundida; só funde se houver uma única pessoa possível
    for i, cands in abbr.items():
        roots = sorted({root(j) for j in cands if "|?" not in recs[j]["core"]})
        ns = NAME_SCORE if len(roots) == 1 else NAME_SCORE - 0.15
        for r in roots:
            s, why = score(recs[i], merged_profile(r), ns)
            if s >= MERGE_AT and len(roots) == 1:
                parent[root(i)] = r
            elif s >= REVIEW_AT:
                review.append({"a": recs[i]["nomes"][0], "b": recs[r]["nomes"][0], "pontos": s, "motivos": ", ".join(why)})
    person = d["key"].map(lambda k: prof.loc[root(pos[k]), "core"] if k in pos else k)
    return person, pd.DataFrame(review, columns=["a", "b", "pontos", "motivos"])


def save_candidates(db, cand: pd.DataFrame) -> int:
    """Grava os pares duvidosos em `player_merge_candidates` (SQLite) para revisão — nunca funde sozinho."""
    if cand is None or cand.empty or db is None:
        return 0
    with db.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS player_merge_candidates (a TEXT, b TEXT, pontos REAL, motivos TEXT, "
                     "status TEXT DEFAULT 'pendente', PRIMARY KEY (a, b))")
        conn.executemany("INSERT OR REPLACE INTO player_merge_candidates (a, b, pontos, motivos) VALUES (?, ?, ?, ?)",
                         cand[["a", "b", "pontos", "motivos"]].itertuples(index=False, name=None))
    return int(len(cand))


def merge_match_rows(rows: pd.DataFrame, date_col: str = "match_date", teams: Iterable[str] = ("home_team_name", "away_team_name"),
                     rank_col: Optional[str] = "acoes") -> pd.DataFrame:
    """
    Estatísticas de um atleta vindas de várias fontes: a mesma partida (data ±1 dia + mesmos times) fica UMA vez,
    a versão mais rica (mais ações). Assim a fusão soma jogos diferentes sem contar o mesmo jogo duas vezes.
    """
    if rows is None or rows.empty:
        return rows
    r = rows.copy()
    h, a = list(teams)
    r["_d"] = pd.to_datetime(r[date_col], errors="coerce")
    r["_pair"] = [" x ".join(sorted((team_core(x), team_core(y)))) for x, y in zip(r[h], r[a])]
    r = r.sort_values([rank_col] if rank_col and rank_col in r else ["_d"], ascending=False)
    keep, seen = [], []
    for i, x in r.iterrows():
        dup = any(p == x["_pair"] and abs((d - x["_d"]).days) <= 1 for p, d in seen if pd.notna(d) and pd.notna(x["_d"]))
        if not dup:
            keep.append(i)
            seen.append((x["_pair"], x["_d"]))
    return r.loc[keep].drop(columns=["_d", "_pair"]).sort_values(date_col, ascending=False)
