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

SNAP_PATH = Path("data/processed/scout_universe_v22.pkl")   # v22: recalcula OVR ao atualizar o motor, preservando potencial
META_PATH = Path("data/processed/scout_universe_v9.json")
OLD_SNAPS = [Path("data/processed/scout_universe_v21.pkl"), Path("data/processed/scout_universe_v20.pkl"), Path("data/processed/scout_universe_v19.pkl"), Path("data/processed/scout_universe_v18.pkl"), Path("data/processed/scout_universe_v17.pkl"), Path("data/processed/scout_universe_v16.pkl"), Path("data/processed/scout_universe_v15.pkl"), Path("data/processed/scout_universe_v14.pkl"), Path("data/processed/scout_universe_v13.pkl"), Path("data/processed/scout_universe_v12.pkl"), Path("data/processed/scout_universe_v11.pkl"), Path("data/processed/scout_universe_v10.pkl"), Path("data/processed/scout_universe_v9.pkl"), Path("data/processed/scout_universe_v8.pkl"), Path("data/processed/scout_universe_v7.pkl"), Path("data/processed/scout_universe_v6.pkl"), Path("data/processed/scout_universe_v5.pkl"), Path("data/processed/scout_universe_v4.pkl"), Path("data/processed/scout_universe_v3.pkl"), Path("data/processed/scout_universe_v2.pkl"),
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
    try:                                       # rodada 27e: convocações para a seleção PRINCIPAL → potencial
        universe = E.merge_senior(universe, E.senior_caps(db))
    except Exception:
        pass
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

    try:                                                 # identidade de atleta: aliases locais + duplicatas verificadas entre clubes
        universe = E.merge_club_aliases(universe)
        universe = E.merge_verified_player_duplicates(E.merge_cross_source_duplicates(universe))
    except Exception:
        pass
    universe = add_traits(finalize_overall(universe))   # rodada 20: overall 0–100 calibrado com craques de referência
    universe = with_attributes(universe)                # rodada 23: atributos 1–20 estilo FM (medidos)
    stamp = pd.to_datetime(players.get("ingestao_utc"), errors="coerce").max() if "ingestao_utc" in players else None
    return {"universe": universe, "clubs": clubs, "status": "carregado", "identidade": IDENTITY_VERSION,
            "atualizacao": str(stamp) if stamp is not None and pd.notna(stamp) else "sem carimbo"}


def _evaluations():
    """Avaliações da tela Rankings (data/processed/evaluations.parquet); vazio se ainda não calculadas."""
    try:
        from src.scout import evaluation as EV

        res = EV.load()
        return res["jogadores"] if res else None
    except Exception:
        return None


def slim(u: pd.DataFrame) -> pd.DataFrame:
    """Rodada 26: fotografia mais leve (abre e cabe na memória muito mais rápido) sem tirar nada que alguma tela usa:
    os últimos jogos perdem o stats_json de cada partida (não é exibido em lugar nenhum), colunas internas de cálculo
    que nenhuma tela lê saem (tipos dos números não mudam: nada quebra)."""
    if u is None or u.empty:
        return u
    u = u.copy()
    if "ultimos_jogos" in u:
        def _strip(v):
            if not isinstance(v, str) or "stats_json" not in v:
                return v
            try:
                games = json.loads(v)
                for g in games if isinstance(games, list) else []:
                    if isinstance(g, dict):
                        g.pop("stats_json", None)
                return json.dumps(games, ensure_ascii=False, default=str)
            except Exception:
                return v
        u["ultimos_jogos"] = u["ultimos_jogos"].map(_strip)
    drop = [c for c in u.columns if c.startswith("__history_") or c in ("_raw_stats", "stats_json")]
    u = u.drop(columns=drop, errors="ignore")
    return u


def save(data: Dict[str, Any]) -> Dict[str, Any]:
    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data.get("universe"), pd.DataFrame):
        data = {**data, "universe": slim(data["universe"])}
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


def newest_old() -> Optional[Path]:
    """A fotografia anterior mais nova que existe no disco (ou None)."""
    for old in OLD_SNAPS:
        if old.exists():
            return old
    return None


IDENTITY_VERSION = "r27k"          # muda quando as regras de "mesmo atleta" mudam


def load() -> Optional[Dict[str, Any]]:
    if not SNAP_PATH.exists():
        # A mudança do motor exige recalcular as notas da fotografia anterior. A migração é feita uma única vez,
        # salva em SNAP_PATH e evita que a interface continue servindo OVR antigo indefinidamente.
        upgraded = _upgrade_old()
        if upgraded is not None:
            return upgraded
        # Se a migração falhar, preserva a disponibilidade da tela com o instantâneo anterior, marcado como parcial.
        old = newest_old()
        if old is None:
            return None
        try:
            data = pd.read_pickle(old)
        except Exception:
            return None
        if isinstance(data, dict):
            data["parcial"] = True
            data["fotografia_antiga"] = old.name
            try:
                u = data.get("universe")
                if isinstance(u, pd.DataFrame):
                    from src.scout.engine import merge_club_aliases, merge_verified_player_duplicates

                    u = merge_club_aliases(u)
                    data["universe"] = merge_verified_player_duplicates(u)   # a junção entre fontes fica para a nova
            except Exception:
                pass
        return data
    try:
        data = pd.read_pickle(SNAP_PATH)
    except Exception:
        return None
    try:                                   # rodada 26: fotografia antiga (com stats_json dos jogos) → enxuga UMA vez
        u = data.get("universe") if isinstance(data, dict) else None
        if isinstance(u, pd.DataFrame) and "ultimos_jogos" in u and \
                u["ultimos_jogos"].head(200).astype(str).str.contains("stats_json", regex=False).any():
            data["universe"] = slim(u)
            tmp = SNAP_PATH.with_suffix(".tmp")
            pd.to_pickle(data, tmp)
            os.replace(tmp, SNAP_PATH)
    except Exception:
        pass
    try:                                   # normaliza aliases e IDs — UMA vez; a fotografia unificada volta ao disco
        u = data.get("universe") if isinstance(data, dict) else None
        if isinstance(u, pd.DataFrame) and data.get("identidade") != IDENTITY_VERSION:
            from src.scout.engine import merge_club_aliases, merge_verified_player_duplicates

            u = merge_club_aliases(u)
            from src.scout.engine import merge_cross_source_duplicates

            data["universe"] = merge_verified_player_duplicates(merge_cross_source_duplicates(u))
            data["identidade"] = IDENTITY_VERSION
            try:                           # rodada 27j: grava a fotografia já unificada (próximas aberturas: 0 s)
                tmp = SNAP_PATH.with_suffix(".tmp")
                pd.to_pickle(data, tmp)
                os.replace(tmp, SNAP_PATH)
            except Exception:
                pass
    except Exception:
        pass
    try:                                   # rodada 27: um nome por liga também na fotografia já pronta (só em memória)
        u = data.get("universe") if isinstance(data, dict) else None
        if isinstance(u, pd.DataFrame):
            from src.scout.evaluation import canonical_league

            for col in ("clube_liga", "liga", "liga_clube"):
                if col in u:
                    m = {x: canonical_league(x) for x in u[col].dropna().unique()}
                    u[col] = u[col].map(lambda x, m=m: m.get(x, x))
    except Exception:
        pass
    return data


POTENTIAL_COLUMNS = (
    "potencial", "potencial_teto", "potencial_crescimento", "potencial_revenda",
    "projecao_valorizacao_24m_pct", "potencial_natureza", "potencial_piso_base",
    "potencial_porque", "potencial_confianca_pct", "precocidade",
)


def _preserve_existing_potential(source: pd.DataFrame, recalculated: pd.DataFrame) -> pd.DataFrame:
    """Preserva as projeções que já estavam na fotografia ao recalcular somente o OVR."""
    if source is None or recalculated is None or recalculated.empty:
        return recalculated
    out = recalculated.copy()
    for column in POTENTIAL_COLUMNS:
        if column not in source:
            continue
        previous = source[column].reindex(out.index)
        if column in out:
            out[column] = previous.combine_first(out[column])
        else:
            out[column] = previous
    return out


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
            saved_potential = u[[c for c in POTENTIAL_COLUMNS if c in u]].copy()
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

            recalculated = _preserve_existing_potential(saved_potential, E.add_quality_scores(u))
            u2 = E.merge_rankings(E.merge_external_ratings(recalculated, ext), _evaluations())
            u2 = E.canonical_clubs(u2)
            try:
                from src.data_hub.gender import drop_women_players
                from src.data_hub.db import DataHubDB

                u2 = drop_women_players(u2, DataHubDB())
            except Exception:
                pass
            u2 = E.merge_club_aliases(u2)
            u2 = E.merge_verified_player_duplicates(E.merge_cross_source_duplicates(u2))
            data["universe"] = with_attributes(add_traits(finalize_overall(u2, recompute_potential=False)))
            data["identidade"] = IDENTITY_VERSION
            data["parcial"] = True          # OVR recalculado sobre fotografia antiga; refazer ingestão completa depois
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
    """Índices por nome, alias e PID, montados uma vez por fotografia."""
    from src.data_lake.ids import player_core

    u = cached_universe()
    if u is None or u.empty:
        return {}
    if _MEMO.get("idx_for") is u:
        return _MEMO["idx"]
    by_core: Dict[str, list] = {}
    if "_core" in u:
        for i, c in zip(u.index, u["_core"].astype(str)):
            by_core.setdefault(c, []).append(i)
    if "apelidos_core" in u:
        for i, aliases in u["apelidos_core"].items():
            if aliases is None or (isinstance(aliases, float) and pd.isna(aliases)):
                continue
            values = aliases if isinstance(aliases, (list, tuple, set)) else str(aliases).split("|")
            for alias in values:
                alias_core = player_core(str(alias))
                if alias_core and alias_core.casefold() not in {"nan", "none"}:
                    by_core.setdefault(alias_core, []).append(i)
    by_core = {k: list(dict.fromkeys(v)) for k, v in by_core.items()}
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
    from src.data_lake.ids import player_core, team_core

    clubs = u["clube"].fillna("").astype(str)
    cmap = {c: team_core(c) for c in clubs.unique()}
    key = u["_core"].astype(str) + "|" + clubs.map(cmap)
    pot = u["potencial"] if "potencial" in u else u.get("potencial_teto", pd.Series(np.nan, index=u.index))
    qv, pv = pd.to_numeric(u.get("qualidade"), errors="coerce"), pd.to_numeric(pot, errors="coerce")
    out = {"q": dict(zip(key, qv)), "p": dict(zip(key, pv))}
    # Os mesmos aliases usados pela busca manual também encontram o overall neste mapa.
    if "apelidos_core" in u:
        for i, aliases in u["apelidos_core"].items():
            if aliases is None or (isinstance(aliases, float) and pd.isna(aliases)):
                continue
            values = aliases if isinstance(aliases, (list, tuple, set)) else str(aliases).split("|")
            for alias in values:
                a = player_core(str(alias))
                if a and a.casefold() not in {"nan", "none"}:
                    k = f"{a}|{cmap.get(str(clubs.loc[i]), team_core(str(clubs.loc[i])))}"
                    out["q"][k], out["p"][k] = qv.loc[i], pv.loc[i]
    # rodada 27: nome ÚNICO no universo (sem homônimo) também vale sem o clube — o Rankings mostra o clube da
    # competição (Salah no Liverpool) e o Scout o clube atual; antes a qualidade ficava vazia
    core = u["_core"].astype(str)
    uniq = ~core.duplicated(keep=False)
    out["uq"] = dict(zip(core[uniq], qv[uniq]))
    out["up"] = dict(zip(core[uniq], pv[uniq]))
    _MEMO["qmap"], _MEMO["qmap_for"] = out, u
    return out


def _club_scoped_rows(frame: pd.DataFrame, club: str) -> pd.DataFrame:
    """Keep only rows explicitly associated with the requested club; never accept an unverified homonym."""
    if frame is None or frame.empty or not club:
        return frame.iloc[0:0] if frame is not None else pd.DataFrame()
    from src.data_lake.ids import team_core

    requested = team_core(club)
    if not requested:
        return frame.iloc[0:0]

    def same(value):
        current = team_core(str(value)) if pd.notna(value) else ""
        return bool(current) and (current == requested or current.startswith(requested) or requested.startswith(current))

    if "clube" in frame:
        current_names = frame["clube"].fillna("").astype(str).str.strip()
        has_current = current_names.ne("")
        matched = frame["clube"].map(same)
        if "clube_tm" in frame:
            matched |= (~has_current) & frame["clube_tm"].map(same)
        return frame[matched]
    if "clube_tm" in frame:
        return frame[frame["clube_tm"].map(same)]
    return frame.iloc[0:0]


def _age_scoped_rows(frame: pd.DataFrame, age: Optional[float]) -> pd.DataFrame:
    if frame is None or frame.empty or age is None or pd.isna(age) or "idade" not in frame:
        return frame
    known = pd.to_numeric(frame["idade"], errors="coerce")
    if known.notna().any():
        return frame[known.notna() & ((known - float(age)).abs() <= 1)]
    return frame


def find_player(core: str, names: Optional[list] = None, club: str = "", pid: str = "",
                age: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Resolve um atleta sem misturar homônimos: PID, nome e idade nunca dispensam a validação do clube."""
    u = cached_universe()
    if u is None or u.empty:
        return None
    from src.data_lake.ids import player_core

    requested_names = [str(n).strip() for n in (names or []) if n and str(n).strip()]
    requested_cores = {player_core(core)} | {player_core(n) for n in requested_names}
    requested_cores.discard("")
    idx = _index()

    # PID é apenas uma pista: se apontar para outro nome, clube ou idade, é descartado e a busca continua.
    if pid and pid in idx.get("pid", {}):
        candidate = u.loc[[idx["pid"][pid]]]
        pid_name = player_core(str(candidate.iloc[0].get("nome") or candidate.iloc[0].get("_core") or ""))
        name_ok = (not requested_cores or pid_name in requested_cores or any(
            set(q.split()) < set(pid_name.split()) or set(pid_name.split()) < set(q.split())
            for q in requested_cores if q and pid_name))
        club_ok = (not club) or not _club_scoped_rows(candidate, club).empty
        age_ok = not _age_scoped_rows(candidate, age).empty
        if name_ok and club_ok and age_ok:
            return candidate.iloc[0].to_dict()

    rows = [i for c in requested_cores for i in idx.get("core", {}).get(str(c), [])]
    hit = u.loc[sorted(set(rows))] if rows else u.iloc[0:0]
    if club:
        hit = _club_scoped_rows(hit, club)
    if age is not None:
        hit = _age_scoped_rows(hit, age)

    # Apelido curto não indexado (ou índice exato apontando para um clube diferente):
    # procura um nome completo SOMENTE dentro do clube, com correspondência única.
    if hit.empty and club and "_core" in u:
        scoped = _club_scoped_rows(u, club)
        candidates = []
        for requested in requested_cores:
            tokens = set(requested.split())
            if not tokens:
                continue
            for row_index, candidate_core in scoped["_core"].astype(str).items():
                candidate_tokens = set(candidate_core.split())
                if tokens < candidate_tokens:
                    candidates.append(row_index)
        if candidates:
            possible = _age_scoped_rows(scoped.loc[sorted(set(candidates))], age)
            unique_cores = possible["_core"].astype(str).unique()
            if len(unique_cores) == 1:
                hit = possible

    if hit.empty:
        return None

    # Mais de um cadastro distinto com o mesmo nome/clube/idade é ambíguo: não escolhe pelo maior volume.
    if "_core" in hit and hit["_core"].astype(str).nunique() > 1:
        return None
    for id_column in ("pid", "transfermarkt_id"):
        if id_column in hit:
            ids = hit[id_column].dropna().astype(str).unique()
            if len(ids) > 1:
                return None
    if "nascimento" in hit:
        dates = pd.to_datetime(hit["nascimento"], errors="coerce").dropna().dt.strftime("%Y-%m-%d").unique()
        if len(dates) > 1:
            return None

    if "qualidade" in hit and len(hit) > 1:
        withq = hit[pd.to_numeric(hit["qualidade"], errors="coerce").notna()]
        if not withq.empty:
            hit = withq
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
