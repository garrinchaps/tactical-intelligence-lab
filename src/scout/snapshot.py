"""
Fotografia do universo do Scout (rodada 7 — velocidade).

O universo (mercado do Transfermarkt + 5 anos de números por jogador + valores + notas externas + dados dos clubes)
é caro de montar: lê centenas de milhares de linhas e JSON. Antes, a aba Scout montava tudo de novo sempre que
qualquer jogo novo era gravado (a cada ~0,7 s com a FotMob ligada) — e não abria.

Agora o universo é montado UMA vez e guardado em `data/processed/scout_universe.pkl`; a aba só lê o arquivo
(instantâneo). O processo de fundo refaz a fotografia a cada SCOUT_SNAPSHOT_HOURS (padrão 6 h). A metodologia é a
mesma da página (mesmas funções do motor) — só muda QUANDO o cálculo roda.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

SNAP_PATH = Path("data/processed/scout_universe.pkl")
META_PATH = Path("data/processed/scout_universe.json")


def max_age_hours() -> float:
    try:
        return max(float(os.getenv("SCOUT_SNAPSHOT_HOURS", "6")), 0.5)
    except ValueError:
        return 6.0


def build_universe(db) -> Dict[str, Any]:
    """Mesmo cálculo que a página fazia (`_market_data`), sem Streamlit."""
    from src.scout import engine as E
    from src.squad import data as D

    players, clubs = D.table("tm_jogadores"), D.table("tm_clubes")
    last = (pd.to_numeric(players["ultima_temporada"], errors="coerce")
            if "ultima_temporada" in players else pd.Series(dtype=float))
    history_players = players
    if not players.empty and last.notna().any():
        history_players = players.loc[last >= last.max() - 2].copy()
        players = players[(last >= last.max() - 2) |
                          players.get("clube_id", pd.Series("", index=players.index)).astype(str).str.strip().ne("")]
    history = E.load_player_history(db, days=1825, player_names=history_players.get("nome", pd.Series(dtype=str)))
    valuations = D.table("tm_valores", ["transfermarkt_id", "data", "valor_mercado_eur"])
    universe = E.add_quality_scores(E.build_market_universe(players, history, valuations))
    universe = E.merge_external_ratings(universe, D.external_ratings())
    if not clubs.empty:
        from src.data_lake.ids import team_core

        club_rows = clubs.copy()
        if {"transfermarkt_id", "valor_total_eur"} <= set(club_rows.columns):
            cv_id = club_rows.drop_duplicates("transfermarkt_id").set_index(
                club_rows["transfermarkt_id"].astype(str))["valor_total_eur"].to_dict()
            universe["clube_valor_total_eur"] = universe["clube_id"].astype(str).map(cv_id)
        if "nome" in club_rows:
            club_rows["_club_core"] = club_rows["nome"].map(team_core)
            if "valor_total_eur" in club_rows:
                cv_name = club_rows.drop_duplicates("_club_core").set_index("_club_core")["valor_total_eur"].to_dict()
                by_name = universe["clube"].map(team_core).map(cv_name)
                universe["clube_valor_total_eur"] = by_name.combine_first(
                    universe.get("clube_valor_total_eur", pd.Series(index=universe.index, dtype=float)))
            for source, target in (("liga", "clube_liga"), ("pais", "clube_pais")):
                if source in club_rows:
                    mapping = club_rows.drop_duplicates("_club_core").set_index("_club_core")[source].to_dict()
                    universe[target] = universe["clube"].map(team_core).map(mapping)
    stamp = pd.to_datetime(players.get("ingestao_utc"), errors="coerce").max() if "ingestao_utc" in players else None
    return {"universe": universe, "clubs": clubs, "status": "carregado",
            "atualizacao": str(stamp) if stamp is not None and pd.notna(stamp) else "sem carimbo"}


def save(data: Dict[str, Any]) -> Dict[str, Any]:
    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SNAP_PATH.with_suffix(".tmp")
    pd.to_pickle(data, tmp)
    os.replace(tmp, SNAP_PATH)
    meta = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "jogadores": int(len(data.get("universe", []))), "clubes": int(len(data.get("clubs", [])))}
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def meta() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def age_hours() -> Optional[float]:
    m = meta()
    if not m or not SNAP_PATH.exists():
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(m["built_at"])).total_seconds() / 3600
    except Exception:
        return None


def load() -> Optional[Dict[str, Any]]:
    if not SNAP_PATH.exists():
        return None
    try:
        return pd.read_pickle(SNAP_PATH)
    except Exception:
        return None


def version() -> str:
    """Versão ESTÁVEL para os caches da página: muda só quando a fotografia é refeita."""
    m = meta() or {}
    return f"snap:{m.get('built_at', 'none')}"


def rebuild(db) -> Dict[str, Any]:
    return save(build_universe(db))


def rebuild_if_stale(db) -> Optional[Dict[str, Any]]:
    a = age_hours()
    if a is None or a >= max_age_hours():
        return rebuild(db)
    return None
