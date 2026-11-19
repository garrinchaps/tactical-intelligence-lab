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

SNAP_PATH = Path("data/processed/scout_universe_v7.pkl")    # v7: posições da escalação (FotMob), Rankings na qualidade, origem
META_PATH = Path("data/processed/scout_universe_v7.json")
OLD_SNAPS = [Path("data/processed/scout_universe_v6.pkl"), Path("data/processed/scout_universe_v5.pkl"), Path("data/processed/scout_universe_v4.pkl"), Path("data/processed/scout_universe_v3.pkl"), Path("data/processed/scout_universe_v2.pkl"),
             Path("data/processed/scout_universe.pkl")]


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
    universe = E.build_market_universe(players, history, valuations)
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
    # rodada 10: a qualidade usa o nível do clube (valor do elenco), então vem DEPOIS de juntar os clubes
    universe = E.add_quality_scores(universe)
    universe = E.merge_external_ratings(universe, D.external_ratings())
    universe = E.merge_rankings(universe, _evaluations())
    from src.scout.traits import add_traits

    universe = add_traits(universe)
    stamp = pd.to_datetime(players.get("ingestao_utc"), errors="coerce").max() if "ingestao_utc" in players else None
    return {"universe": universe, "clubs": clubs, "status": "carregado",
            "atualizacao": str(stamp) if stamp is not None and pd.notna(stamp) else "sem carimbo"}


def _evaluations():
    """Avaliações da tela Rankings (data/processed/evaluations.parquet); vazio se ainda não calculadas."""
    try:
        from src.scout import evaluation as EV

        res = EV.load()
        return res["jogadores"] if res else None
    except Exception:
        return None


def save(data: Dict[str, Any]) -> Dict[str, Any]:
    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SNAP_PATH.with_suffix(".tmp")
    pd.to_pickle(data, tmp)
    os.replace(tmp, SNAP_PATH)
    meta = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "jogadores": int(len(data.get("universe", []))), "clubes": int(len(data.get("clubs", []))),
            "parcial": bool(data.get("parcial", False))}
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
        return _upgrade_old()
    try:
        return pd.read_pickle(SNAP_PATH)
    except Exception:
        return None


def _upgrade_old() -> Optional[Dict[str, Any]]:
    """
    Rodada 11: a fotografia nova ainda não existe — aproveita a anterior e só RECALCULA as notas (segundos), em vez de
    montar o mercado inteiro de novo dentro da tela (minutos). O processo de fundo refaz a fotografia completa depois.
    """
    from src.scout import engine as E

    for old in OLD_SNAPS:
        if not old.exists():
            continue
        try:
            data = pd.read_pickle(old)
            u = data.get("universe")
            if u is None or u.empty:
                continue
            if "valor_pico_3a_eur" not in u:
                try:
                    from src.squad import data as D

                    u = add_peak(u, D.table("tm_valores", ["transfermarkt_id", "data", "valor_mercado_eur"]))
                except Exception:
                    pass
            for c in ("caracteristicas", "caracteristicas_top", "precocidade", "qualidade", "confianca_pct", "potencial_revenda", "projecao_valorizacao_24m_pct", "potencial_teto",
                      "qualidade_estatistica", "nota_externa", "fontes_nota_externa", "fonte_qualidade"):
                if c in u:
                    u = u.drop(columns=[c])
            try:
                from src.squad import data as D

                ext = D.external_ratings()
            except Exception:
                ext = None
            from src.scout.traits import add_traits

            data["universe"] = add_traits(E.merge_rankings(E.merge_external_ratings(E.add_quality_scores(u), ext),
                                                           _evaluations()))
            data["parcial"] = True          # fotografia antiga reaproveitada: faltam os jogadores novos (refazer)
            save(data)
            return data
        except Exception:
            continue
    return None


def add_peak(u: pd.DataFrame, vals: pd.DataFrame) -> pd.DataFrame:
    """Maior valor de mercado de cada atleta nos últimos 3 anos (reputação de veteranos de elite)."""
    if vals is None or vals.empty or "transfermarkt_id" not in u:
        return u
    v = vals.copy()
    v["_d"] = pd.to_datetime(v["data"], errors="coerce")
    v["valor_mercado_eur"] = pd.to_numeric(v["valor_mercado_eur"], errors="coerce")
    v = v[v["_d"] >= pd.Timestamp.today().normalize() - pd.Timedelta(days=3 * 365)]
    peak = v.groupby(v["transfermarkt_id"].astype(str))["valor_mercado_eur"].max().to_dict()
    u = u.copy()
    u["valor_pico_3a_eur"] = u["transfermarkt_id"].astype(str).map(peak)
    return u


def version() -> str:
    """Versão ESTÁVEL para os caches da página: muda só quando a fotografia é refeita."""
    m = meta() or {}
    return f"snap:{m.get('built_at', 'none')}"


def rebuild(db) -> Dict[str, Any]:
    return save(build_universe(db))


def rebuild_if_stale(db) -> Optional[Dict[str, Any]]:
    a = age_hours()
    if a is None or a >= max_age_hours() or (meta() or {}).get("parcial"):
        return rebuild(db)
    return None


def main() -> None:
    """python -m src.scout.snapshot  → refaz a fotografia COMPLETA do Scout (com o app fechado é mais rápido)."""
    import time

    from src.data_hub.db import DataHubDB

    t0 = time.time()
    print("Montando o universo do Scout (cadastro + 5 anos de jogos + avaliações dos Rankings)... pode levar minutos.")
    m = rebuild(DataHubDB())
    data = load() or {}
    u = data.get("universe")
    print(f"Pronto em {time.time() - t0:.0f} s: {m['jogadores']:,} jogadores.".replace(",", "."))
    if u is not None and "origem" in u:
        print(u["origem"].value_counts().to_string())


if __name__ == "__main__":
    main()
