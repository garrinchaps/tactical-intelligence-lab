"""
Profundidade de dados por partida (nível 0 a 4) — v36, item B6 (e base do D5).

    0 · Resultado ............................. só placar e informações básicas
    1 · Estatísticas do time .................. finalizações, posse, escanteios... (coletivas)
    2 · Escalação e números individuais ....... quem jogou e/ou estatísticas por jogador
    3 · Lances com coordenadas ................ evento a evento (StatsBomb, Wyscout, OpenPlay)
    4 · Tracking físico ........................ velocidade/distância (nenhuma fonte aberta tem hoje)

Dado ausente nunca vira zero: o nível diz o que EXISTE, não preenche o que falta.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional

LABELS = {0: "Resultado", 1: "Estatísticas do time", 2: "Escalação e números individuais",
          3: "Lances com coordenadas", 4: "Tracking físico"}
ICONS = {0: "📄", 1: "📊", 2: "👥", 3: "🟢", 4: "🛰️"}


def depth_of(
    level: str,
    has_team_stats: Optional[bool] = None,
    has_individual: Optional[bool] = None,
    has_tracking: bool = False,
) -> int:
    """Classifica pela evidência observada; usa data_level como fallback só sem flags de conteúdo.

    Importante: BOXSCORE é um rótulo amplo. Não prova, sozinho, que uma linha de estatísticas
    esteja realmente gravada. Quando o chamador consulta o banco, deve passar True/False explícitos.
    """
    if has_tracking:
        return 4
    if str(level).upper() in ("EVENTS", "UPLOAD"):
        return 3
    if has_individual:
        return 2
    if has_team_stats:
        return 1
    if has_team_stats is None and has_individual is None and str(level).upper() == "BOXSCORE":
        return 1
    return 0


def depth_for_matches(db, match_ids: Iterable[int]) -> Dict[int, int]:
    """Nível de cada partida consultando o que existe no banco (estatísticas, escalações, números individuais)."""
    ids = [int(x) for x in match_ids]
    if not ids:
        return {}
    out: Dict[int, int] = {}
    with db.connect() as conn:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            ph = ",".join("?" * len(chunk))

            def has(table):
                try:
                    return {r[0] for r in conn.execute(f"SELECT DISTINCT match_id FROM {table} WHERE match_id IN ({ph})", chunk)}
                except Exception:
                    return set()
            lv = dict(conn.execute(f"SELECT match_id, data_level FROM matches WHERE match_id IN ({ph})", chunk).fetchall())
            ts, lu, ps = has("match_team_stats"), has("match_lineups"), has("match_player_stats")
            for m in chunk:
                out[m] = depth_of(lv.get(m, "RESULT"), m in ts, m in lu or m in ps)
    return out


def badge(depth: int) -> str:
    return f"{ICONS.get(depth, '')} Nível {depth} · {LABELS.get(depth, '?')}"
