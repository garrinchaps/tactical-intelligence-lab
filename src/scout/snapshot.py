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

import numpy as np
import pandas as pd

SNAP_PATH = Path("data/processed/scout_universe_v13.pkl")   # v13: nota por atributos da posição (sem valor de mercado)
META_PATH = Path("data/processed/scout_universe_v9.json")
OLD_SNAPS = [Path("data/processed/scout_universe_v12.pkl"), Path("data/processed/scout_universe_v11.pkl"), Path("data/processed/scout_universe_v10.pkl"), Path("data/processed/scout_universe_v9.pkl"), Path("data/processed/scout_universe_v8.pkl"), Path("data/processed/scout_universe_v7.pkl"), Path("data/processed/scout_universe_v6.pkl"), Path("data/processed/scout_universe_v5.pkl"), Path("data/processed/scout_universe_v4.pkl"), Path("data/processed/scout_universe_v3.pkl"), Path("data/processed/scout_universe_v2.pkl"),
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
    universe = E.fill_homonyms_from_club(db, universe)   # rodada 20: homônimos pelos jogos do próprio clube
    # rodada 10: a qualidade usa o nível do clube (valor do elenco), então vem DEPOIS de juntar os clubes
    universe = E.add_quality_scores(universe)
    universe = E.merge_external_ratings(universe, D.external_ratings())
    universe = E.merge_rankings(universe, _evaluations())
    universe = E.canonical_clubs(universe)               # rodada 20: um nome por clube ("Cruzeiro" × "Cruzeiro EC")
    caps = E.youth_caps(db)
    universe = E.merge_youth(universe, caps)  # rodada 20: seleções de base → potencial e característica
    try:                                       # rodada 22: quem só tem jogos de base entra com qualidade ESTIMADA
        extra = E.youth_only_players(universe, caps)
        if not extra.empty:
            universe = pd.concat([universe, extra], ignore_index=True, sort=False)
    except Exception:
        pass
    try:                                                 # rodada 20: o mercado é masculino (jogadoras de mesmo clube fora)
        from src.data_hub.gender import drop_women_players

        universe = drop_women_players(universe, db)
    except Exception:
        pass
    from src.scout.overall import finalize_overall
    from src.scout.traits import add_traits

    universe = add_traits(finalize_overall(universe))   # rodada 20: overall 0–100 calibrado com craques de referência
    universe = with_attributes(universe)                # rodada 23: atributos 1–20 estilo FM (medidos)
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
            for c in ("caracteristicas", "caracteristicas_top", "precocidade", "qualidade", "qualidade_base", "confianca_pct", "potencial_revenda", "projecao_valorizacao_24m_pct", "potencial_teto",
                      "qualidade_estatistica", "nota_externa", "fontes_nota_externa", "fonte_qualidade"):
                if c in u:
                    u = u.drop(columns=[c])
            try:
                from src.squad import data as D

                ext = D.external_ratings()
            except Exception:
                ext = None
            from src.scout.overall import finalize_overall
            from src.scout.traits import add_traits

            u2 = E.merge_rankings(E.merge_external_ratings(E.add_quality_scores(u), ext), _evaluations())
            u2 = E.canonical_clubs(u2)
            try:
                from src.data_hub.gender import drop_women_players
                from src.data_hub.db import DataHubDB

                u2 = drop_women_players(u2, DataHubDB())
            except Exception:
                pass
            data["universe"] = with_attributes(add_traits(finalize_overall(u2)))
            data["parcial"] = True          # fotografia antiga reaproveitada: faltam os jogadores novos (refazer)
            save(data)
            return data
        except Exception:
            continue
    return None


def with_attributes(u: pd.DataFrame) -> pd.DataFrame:
    """Rodada 23: junta os atributos 1–20 (src/scout/attributes.py). Falha aqui nunca derruba a fotografia."""
    try:
        from src.scout import attributes as AT

        a = AT.compute(u)
        u = u.drop(columns=[c for c in a.columns if c in u], errors="ignore")
        return pd.concat([u, a], axis=1)
    except Exception:
        return u


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


_MEMO: Dict[str, Any] = {}


def cached_universe() -> Optional[pd.DataFrame]:
    """Rodada 23: o universo do Scout UMA vez por processo (relido só quando a fotografia muda no disco). Antes cada tela
    passava pelo cache do Streamlit, que copia o DataFrame inteiro a cada uso. NÃO altere o DataFrame devolvido."""
    try:
        stamp = SNAP_PATH.stat().st_mtime if SNAP_PATH.exists() else None
    except OSError:
        stamp = None
    if _MEMO.get("stamp") == stamp and "u" in _MEMO:
        return _MEMO["u"]
    data = load()
    u = data.get("universe") if isinstance(data, dict) else None
    _MEMO.update(stamp=stamp, u=u, data=data)
    return u


def cached_data() -> Optional[Dict[str, Any]]:
    cached_universe()
    return _MEMO.get("data")


def _index() -> Dict[str, Any]:
    """Rodada 25: índices núcleo-do-nome → linhas e pid → linha, montados UMA vez por fotografia. Antes cada busca de
    jogador varria o universo inteiro (60 mil+ linhas) — o campinho com 22 nomes fazia 22 varreduras."""
    u = cached_universe()
    if u is None or u.empty:
        return {}
    if _MEMO.get("idx_for") is u:
        return _MEMO["idx"]
    by_core: Dict[str, list] = {}
    if "_core" in u:
        for i, c in zip(u.index, u["_core"].astype(str)):
            by_core.setdefault(c, []).append(i)
    by_pid = dict(zip(u["pid"].astype(str), u.index)) if "pid" in u else {}
    _MEMO["idx"] = {"core": by_core, "pid": by_pid}
    _MEMO["idx_for"] = u
    return _MEMO["idx"]


def quality_map() -> Dict[str, Dict[str, float]]:
    """"núcleo|clube" → qualidade e potencial (uma vez por fotografia; Rankings e campinho leem daqui)."""
    u = cached_universe()
    if u is None or u.empty:
        return {"q": {}, "p": {}}
    if _MEMO.get("qmap_for") is u:
        return _MEMO["qmap"]
    from src.data_lake.ids import team_core

    clubs = u["clube"].fillna("").astype(str)
    cmap = {c: team_core(c) for c in clubs.unique()}
    key = u["_core"].astype(str) + "|" + clubs.map(cmap)
    pot = u["potencial"] if "potencial" in u else u.get("potencial_teto", pd.Series(np.nan, index=u.index))
    out = {"q": dict(zip(key, pd.to_numeric(u.get("qualidade"), errors="coerce"))),
           "p": dict(zip(key, pd.to_numeric(pot, errors="coerce")))}
    _MEMO["qmap"], _MEMO["qmap_for"] = out, u
    return out


def find_player(core: str, names: Optional[list] = None, club: str = "", pid: str = "") -> Optional[Dict[str, Any]]:
    """Linha do universo do atleta. Rodada 24: pelo identificador único (pid) quando vier; senão núcleo de nome e,
    havendo homônimo, SÓ o do clube informado (sem clube que confira → nenhum, para não mostrar a nota de outro)."""
    u = cached_universe()
    if u is None or u.empty:
        return None
    from src.data_lake.ids import player_core

    idx = _index()
    if pid and pid in idx.get("pid", {}):
        return u.loc[idx["pid"][pid]].to_dict()

    cores = {core} | {player_core(n) for n in (names or [])}
    rows = [i for c in cores for i in idx.get("core", {}).get(str(c), [])]
    if not rows:
        return None
    hit = u.loc[sorted(set(rows))]
    if len(hit) > 1 and club and "clube" in hit:
        from src.data_lake.ids import team_core

        same = hit[hit["clube"].fillna("").map(lambda c: team_core(str(c))) == team_core(club)]
        if same.empty and "clube_tm" in hit:
            same = hit[hit["clube_tm"].fillna("").map(lambda c: team_core(str(c))) == team_core(club)]
        if same.empty:
            return None
        hit = same
    m = pd.to_numeric(hit.get("minutos_12m"), errors="coerce").fillna(0) if "minutos_12m" in hit else pd.Series(0, index=hit.index)
    return hit.loc[m.idxmax()].to_dict()


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
