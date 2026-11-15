"""
Notas de jogador (0–10) — v36, itens C1–C4.

As regras da nota de UMA atuação ficam em `src/metrics/player_rating.py` (pesos por setor: o zagueiro não perde
nota por não finalizar, o atacante não ganha muito por um desarme isolado; erros pesam metade dos acertos).
Aqui ficam as camadas por cima:

* C2 `normalize_by_peers`: compara com o grupo de PARES (mesmo setor e mesma competição), não com a média global.
  Só ajusta quando o grupo tem pelo menos MIN_PEERS atuações; com menos, mantém a nota da regra e avisa.
* C3/C4 `player_average`: partida sem dados individuais do jogador fica FORA da média (nunca vira zero); a média
  mostra sempre nota, minutos e o n de partidas — abaixo de MIN_MATCHES aparece "amostra insuficiente".
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.metrics.player_rating import (BASE, CATEGORIES, EXPECTED_PER90, MIN_MINUTES, average_rating,  # noqa: F401
                                       match_ratings, rate_row, sector)

MIN_PEERS = 20          # atuações do mesmo setor e competição para valer a comparação com os pares
MIN_MATCHES = 3         # partidas com nota para a média ser mostrada como número
PEER_CENTER = 6.7       # nota de uma atuação mediana entre os pares


def normalize_by_peers(ratings: pd.DataFrame, group_cols=("competicao", "setor"), col: str = "nota") -> pd.DataFrame:
    """
    Recentra a nota pelo grupo de pares: a mediana de cada (competição, setor) passa a valer PEER_CENTER e a escala é
    preservada (só desloca). Grupos com menos de MIN_PEERS atuações não são mexidos (`pares_ok` = False).
    """
    if ratings is None or ratings.empty or col not in ratings:
        return ratings
    df = ratings.copy()
    cols = [c for c in group_cols if c in df]
    df["nota_regra"] = df[col]
    df["pares_n"] = 0
    df["pares_ok"] = False
    if not cols:
        return df
    for _, g in df.groupby(cols, dropna=False):
        v = pd.to_numeric(g[col], errors="coerce")
        n = int(v.notna().sum())
        df.loc[g.index, "pares_n"] = n
        if n >= MIN_PEERS:
            shift = PEER_CENTER - float(v.median())
            df.loc[g.index, col] = (v + shift).clip(3.0, 10.0).round(1)
            df.loc[g.index, "pares_ok"] = True
    return df


def player_average(per_match: pd.DataFrame, min_matches: int = MIN_MATCHES) -> Dict[str, Any]:
    """
    Média de um jogador: só partidas com nota (≥ 10 min e lances do jogador). Devolve nota, minutos, n e o aviso
    "amostra insuficiente" quando n < min_matches (a média calculada fica em `media_bruta`, sem destaque).
    """
    base = average_rating(per_match)
    mins = float(pd.to_numeric(per_match.get("minutos", pd.Series(dtype=float)), errors="coerce")
                 [pd.to_numeric(per_match.get("nota", pd.Series(dtype=float)), errors="coerce").notna()].sum()) \
        if per_match is not None and not per_match.empty else 0.0
    n = base.get("jogos_com_nota", 0)
    ok = n >= min_matches
    return {"media": base["media"] if ok else None, "media_bruta": base["media"], "jogos_com_nota": n,
            "minutos": round(mins), "minimo": min_matches,
            "aviso": "" if ok else f"amostra insuficiente ({n} de {min_matches} jogos com nota)"}
