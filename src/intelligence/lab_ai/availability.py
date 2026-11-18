"""
Mapa de dados de um jogo (rodada 10): o que a fonte deste jogo MEDE e o que NÃO mede — antes de qualquer análise.

Três níveis de dado (do mais pobre ao mais rico):
  1. estatísticas agregadas (time e/ou jogador): totais, sem onde nem quando;
  2. eventos com coordenadas: onde, quando, sequência, origem/destino, pé (se a fonte informa), pressão;
  3. tracking/vídeo: velocidade, aceleração, orientação do corpo, movimentação sem bola — NÃO existe aberto.
Cada análise declara de qual nível precisa; sem o nível, ela não roda (lacuna ≠ zero).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

ANALYSES = [
    # (nome, nível exigido, coluna/condição extra)
    ("placar e gols", 0, None),
    ("estatísticas do time (finalizações, posse, passes…)", 1, "team"),
    ("números por jogador (passes, duelos, desarmes…)", 1, "player"),
    ("onde cada ação aconteceu (corredores, terços, zonas)", 2, None),
    ("sequências: o que veio antes e depois de cada ação", 2, None),
    ("passes progressivos, que entram no terço final e na área", 2, None),
    ("perdas de bola e o que o rival fez depois", 2, None),
    ("reação às inversões de jogo", 2, None),
    ("pé usado no passe/chute", 2, "pass_body_part"),
    ("ação sob pressão do adversário", 2, "under_pressure"),
    ("xG por finalização", 2, "shot_statsbomb_xg"),
    ("distância percorrida / sprints", 1, "physical"),
    ("velocidade, aceleração, orientação do corpo, movimentação sem bola", 3, None),
]


def data_map(meta: Dict[str, Any], df: Optional[pd.DataFrame], box: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    box = box or {}
    ts, ps = box.get("team_stats"), box.get("player_stats")
    has_team = ts is not None and not getattr(ts, "empty", True)
    has_player = ps is not None and not getattr(ps, "empty", True)
    has_events = df is not None and not getattr(df, "empty", True) and "x" in df and df["x"].notna().any()
    physical = False
    if has_player and "stats" in ps:
        physical = any(isinstance(s, dict) and (s.get("distance_m") or s.get("sprints")) for s in ps["stats"])
    level = 2 if has_events else (1 if (has_team or has_player) else 0)

    def col_ok(c: str) -> bool:
        return bool(has_events and c in df and df[c].notna().any() and (df[c].astype(str).str.strip() != "").any())

    rows: List[Dict[str, Any]] = []
    for name, need, extra in ANALYSES:
        ok = level >= need
        if extra == "team":
            ok = has_team or has_events
        elif extra == "player":
            ok = has_player or has_events
        elif extra == "physical":
            ok = physical
        elif extra and need == 2:
            ok = ok and col_ok(extra)
        rows.append({"analise": name, "disponivel": bool(ok)})
    n_team = int(ts["stat_key"].nunique()) if has_team and "stat_key" in ts else 0
    n_players = int(ps["player_name"].nunique()) if has_player and "player_name" in ps else 0
    n_events = int(len(df)) if has_events else 0
    label = {0: "📄 só placar", 1: "📊 estatísticas (sem coordenadas)", 2: "🟢 lances com coordenadas"}[level]
    return {"nivel": level, "rotulo": label, "linhas": rows, "n_estatisticas_time": n_team,
            "n_jogadores_com_numeros": n_players, "n_eventos": n_events, "fonte": meta.get("data_source") or "—",
            "fisico": physical}


def summary_line(dm: Dict[str, Any]) -> str:
    """Uma linha honesta para o rodapé das respostas."""
    parts = [f"Dados deste jogo: {dm['rotulo']}"]
    if dm["n_eventos"]:
        parts.append(f"{dm['n_eventos']} lances")
    if dm["n_estatisticas_time"]:
        parts.append(f"{dm['n_estatisticas_time']} estatísticas de time")
    if dm["n_jogadores_com_numeros"]:
        parts.append(f"números de {dm['n_jogadores_com_numeros']} jogadores")
    missing = [r["analise"] for r in dm["linhas"] if not r["disponivel"]]
    txt = " · ".join(parts)
    if missing:
        txt += ". Não medido aqui: " + "; ".join(missing[:4]) + ("…" if len(missing) > 4 else "")
    return txt + "."
