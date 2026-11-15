"""
Vínculo jogador-clube (`player_club_tenure`) — v36, item B3.

Cada linha: transfermarkt_id, nome, clube_id, start_date, end_date (vazio = vínculo ativo), type
(definitivo | emprestimo | retorno), confidence_tier e origem do dado.

De onde vem (nesta ordem de força):
1. OBSERVED  — transferências do Transfermarkt (`tm_transferencias`): data e clubes exatos.
2. INFERRED  — aparições jogo a jogo (`tm_aparicoes`): o vínculo vai do 1º ao último jogo pelo clube; uma passagem
               curta (≤ 400 dias) entre duas pelo MESMO clube vira "emprestimo" e a volta vira "retorno".
3. UNKNOWN   — só o cadastro diz que o jogador é do clube, sem transferência nem jogo nos últimos 365 dias.
               NÃO entra no elenco até confirmação (aparece à parte, como "não confirmado").

Nada é inventado: datas vêm de transferências ou jogos; sem nenhum dos dois, o vínculo fica UNKNOWN.
"""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

import pandas as pd

LOAN_MAX_DAYS = 400
STALE_DAYS = 365
COLS = ["transfermarkt_id", "nome", "clube_id", "start_date", "end_date", "type", "confidence_tier", "origem"]


def _tid(x: Any) -> str:
    return str(x).replace(".0", "") if x is not None and str(x) not in ("", "nan", "None", "NaT") else ""


def _typed(rows: List[dict]) -> List[dict]:
    """A → B (curto) → A: B é empréstimo, a volta para A é retorno."""
    rows = sorted(rows, key=lambda r: r["start_date"])
    for i in range(1, len(rows) - 1):
        a, b, c = rows[i - 1], rows[i], rows[i + 1]
        if a["clube_id"] == c["clube_id"] != b["clube_id"] and b["end_date"]:
            days = (pd.Timestamp(b["end_date"]) - pd.Timestamp(b["start_date"])).days
            if days <= LOAN_MAX_DAYS:
                b["type"], c["type"] = "emprestimo", "retorno"
    return rows


def from_transfers(transfers: Optional[pd.DataFrame]) -> pd.DataFrame:
    if transfers is None or transfers.empty:
        return pd.DataFrame(columns=COLS)
    t = transfers.assign(tid=transfers["transfermarkt_id"].map(_tid), d=pd.to_datetime(transfers["data"], errors="coerce"))
    t = t.dropna(subset=["d"]).sort_values(["tid", "d"])
    out = []
    for tid, g in t.groupby("tid"):
        rows = []
        recs = g.to_dict("records")
        for i, r in enumerate(recs):
            nxt = recs[i + 1]["d"] if i + 1 < len(recs) else None
            rows.append({"transfermarkt_id": tid, "nome": r.get("nome"), "clube_id": _tid(r.get("para_clube_id")),
                         "start_date": r["d"].date().isoformat(), "end_date": nxt.date().isoformat() if nxt is not None else "",
                         "type": "definitivo", "confidence_tier": "OBSERVED", "origem": "transferências (Transfermarkt)"})
        out += _typed(rows)
    return pd.DataFrame(out, columns=COLS)


def from_appearances(apps: Optional[pd.DataFrame]) -> pd.DataFrame:
    if apps is None or apps.empty:
        return pd.DataFrame(columns=COLS)
    a = apps.assign(tid=apps["transfermarkt_id"].map(_tid), cl=apps["clube_id"].map(_tid),
                    d=pd.to_datetime(apps["data"], errors="coerce")).dropna(subset=["d"]).sort_values(["tid", "d"])
    out = []
    for tid, g in a.groupby("tid"):
        run = (g["cl"] != g["cl"].shift()).cumsum()              # sequências seguidas pelo mesmo clube
        rows = []
        stints = list(g.groupby(run))
        for k, (_, s) in enumerate(stints):
            last = k == len(stints) - 1
            rows.append({"transfermarkt_id": tid, "nome": s["nome"].iloc[-1] if "nome" in s else "", "clube_id": s["cl"].iloc[0],
                         "start_date": s["d"].min().date().isoformat(),
                         "end_date": "" if last else s["d"].max().date().isoformat(),
                         "type": "definitivo", "confidence_tier": "INFERRED", "origem": "jogos (Transfermarkt)"})
        out += _typed(rows)
    return pd.DataFrame(out, columns=COLS)


def build_tenures(transfers: Optional[pd.DataFrame], apps: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Transferências quando existem; jogos completam os atletas sem transferência registrada."""
    tr = from_transfers(transfers)
    ap = from_appearances(apps)
    if not tr.empty:
        ap = ap[~ap["transfermarkt_id"].isin(set(tr["transfermarkt_id"]))]
    return pd.concat([tr, ap], ignore_index=True)


def active_on(tenures: pd.DataFrame, club_id: Any, on: Optional[date] = None) -> pd.DataFrame:
    """Vínculos ativos com o clube na data (start ≤ data e, se houver fim, fim > data)."""
    if tenures is None or tenures.empty:
        return pd.DataFrame(columns=COLS)
    d = pd.Timestamp(on or date.today())
    t = tenures[tenures["clube_id"] == _tid(club_id)]
    s = pd.to_datetime(t["start_date"], errors="coerce")
    e = pd.to_datetime(t["end_date"].replace("", None), errors="coerce")
    return t[(s <= d) & (e.isna() | (e > d))]


def classify_squad(squad: pd.DataFrame, tenures: pd.DataFrame, club_id: Any, apps: Optional[pd.DataFrame] = None,
                   on: Optional[date] = None) -> pd.DataFrame:
    """
    Marca cada atleta do elenco cadastrado com o vínculo: OBSERVED/INFERRED (ativo hoje) ou UNKNOWN. Quem tem vínculo
    com OUTRO clube ativo hoje sai do elenco ("saiu"). UNKNOWN = sem transferência e sem jogo nos últimos 365 dias.
    """
    if squad is None or squad.empty:
        return squad
    sq = squad.copy()
    today = pd.Timestamp(on or date.today())
    act_here = active_on(tenures, club_id, on)
    here_ids = set(act_here["transfermarkt_id"])
    tiers, types, status = [], [], []
    recent = set()
    if apps is not None and not apps.empty:
        a = apps.assign(d=pd.to_datetime(apps["data"], errors="coerce"))
        recent = set(a.loc[a["d"] >= today - pd.Timedelta(days=STALE_DAYS), "transfermarkt_id"].map(_tid))
    for r in sq.to_dict("records"):
        tid = _tid(r.get("transfermarkt_id"))
        mine = tenures[tenures["transfermarkt_id"] == tid] if tid and tenures is not None and not tenures.empty else pd.DataFrame()
        if tid in here_ids:
            row = act_here[act_here["transfermarkt_id"] == tid].iloc[-1]
            tiers.append(row["confidence_tier"]), types.append(row["type"]), status.append("no elenco")
        elif not mine.empty and not active_on(mine, mine["clube_id"].iloc[-1], on).empty \
                and mine["clube_id"].iloc[-1] != _tid(club_id):
            tiers.append(mine["confidence_tier"].iloc[-1]), types.append(mine["type"].iloc[-1]), status.append("saiu")
        elif tid in recent or r.get("origem") == "adicionado por você":
            tiers.append("INFERRED"), types.append("definitivo"), status.append("no elenco")
        else:
            tiers.append("UNKNOWN"), types.append(""), status.append("não confirmado")
    sq["confidence_tier"], sq["vinculo"], sq["situacao"] = tiers, types, status
    return sq
