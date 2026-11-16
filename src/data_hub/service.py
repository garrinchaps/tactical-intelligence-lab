"""
Serviço de partidas: dado um match_id interno, entrega tudo o que existe sobre a
partida no nível de dado correto (eventos, boxscore, só placar ou simulação).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.registry import (
    BADGES, LEVEL_DESCRIPTIONS, SOURCES, DataLevel, badge_for, source_from_internal_id,
)
from src.data_hub.search import UniversalMatchFinder
from src.data_hub.sources.api_football import ApiFootballProvider
from src.data_hub.sources.espn import EspnProvider
from src.data_hub.sources.fdcouk import FootballDataCoUkProvider
from src.data_hub.sources.football_data import FootballDataProvider
from src.data_hub.sources.statsbomb import StatsBombProvider
from src.data_hub.sources.wyscout import WyscoutProvider


@dataclass
class MatchBundle:
    match_id: int
    meta: Dict[str, Any]
    level: str
    source: str
    events: Optional[pd.DataFrame] = None
    boxscore: Dict[str, Any] = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def badge(self) -> str:
        return badge_for(self.level)

    @property
    def level_description(self) -> str:
        return LEVEL_DESCRIPTIONS.get(self.level, "")

    @property
    def source_label(self) -> str:
        return SOURCES[self.source].label if self.source in SOURCES else self.source.capitalize()

    @property
    def has_events(self) -> bool:
        return self.events is not None and not self.events.empty

    @property
    def is_simulated(self) -> bool:
        return self.level == DataLevel.SIMULATED


def _same(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b or (len(a) > 3 and len(b) > 3 and (a in b.split() or b in a.split() or a.startswith(b) or b.startswith(a))):
        return True
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio() >= 0.86


ESPN_KEYWORDS = [
    (("brasileir", "serie a", "série a", "brazil"), "bra.1"), (("brasileir", "serie b", "série b"), "bra.2"),
    (("copa do brasil",), "bra.copa_do_brazil"), (("libertadores",), "conmebol.libertadores"),
    (("sudamericana", "sul-americana"), "conmebol.sudamericana"), (("premier league",), "eng.1"),
    (("la liga", "laliga", "primera division", "primera división"), "esp.1"), (("serie a", "italy"), "ita.1"),
    (("bundesliga",), "ger.1"), (("ligue 1",), "fra.1"), (("primeira liga", "liga portugal"), "por.1"),
    (("eredivisie",), "ned.1"), (("mls", "major league soccer"), "usa.1"),
    (("champions league",), "uefa.champions"), (("europa league",), "uefa.europa"),
    (("world cup", "copa do mundo"), "fifa.world"), (("liga profesional", "argentin"), "arg.1"),
]


def espn_league_for(meta: Dict[str, Any]) -> Optional[str]:
    txt = f"{meta.get('competition_name', '')} {meta.get('country_name', '')}".lower()
    if "women" in txt or "feminin" in txt:
        return None
    if "brasil" in txt or "brazil" in txt:
        if "copa do brasil" in txt:
            return "bra.copa_do_brazil"
        return "bra.2" if ("serie b" in txt or "série b" in txt) else "bra.1"
    if "ital" in txt and "serie a" in txt:
        return "ita.1"
    for keys, lg in ESPN_KEYWORDS:
        if lg in ("bra.1", "bra.2", "ita.1"):
            continue
        if any(k in txt for k in keys):
            return lg
    return None


class MatchDataService:
    _espn_tried: set = set()

    def __init__(self, db: Optional[DataHubDB] = None):
        self.db = db or DataHubDB()
        self.statsbomb = StatsBombProvider(self.db)
        self.wyscout = WyscoutProvider(self.db)
        self.api_football = ApiFootballProvider(self.db)
        self.football_data = FootballDataProvider(self.db)
        self.espn = EspnProvider(self.db)
        from src.data_hub.sources.fotmob import FotmobProvider

        self.fotmob = FotmobProvider(self.db)
        self.fdcouk = FootballDataCoUkProvider(self.db)
        from src.data_hub.sources.openfootball import OpenFootballProvider

        self.openfootball = OpenFootballProvider(self.db)
        self.finder = UniversalMatchFinder(self.db, providers={
            "api_football": self.api_football, "espn": self.espn, "football_data": self.football_data,
        })

    def providers_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            "statsbomb": {"enabled": True, "note": "sem chave"},
            "wyscout": {"enabled": True, "note": "sem chave"},
            "api_football": {"enabled": self.api_football.enabled,
                             "quota_left": self.api_football.client.quota_left() if self.api_football.enabled else None},
            "football_data": {"enabled": self.football_data.enabled},
            "espn": {"enabled": self.espn.enabled},
            "fdcouk": {"enabled": True, "note": "sem chave"},
            "openfootball": {"enabled": True, "note": "sem chave (CC0)"},
        }

    def load(self, match_id: int, _redirect_ok: bool = True) -> MatchBundle:
        mid = int(match_id)
        meta = self.db.get_match(mid) or {}
        source = meta.get("data_source") or source_from_internal_id(mid)
        level = meta.get("data_level") or DataLevel.EVENTS

        if source in ("statsbomb", "wyscout") or (source == "openplay" and level == DataLevel.EVENTS):
            events = self.db.load_events(mid) if self.db.has_events(mid) else None
            if events is None or events.empty:
                if source == "openplay":
                    from src.data_hub.sources.openplay import OpenPlayProvider

                    provider = OpenPlayProvider(self.db)
                else:
                    provider = self.statsbomb if source == "statsbomb" else self.wyscout
                events = provider.load_events(mid)
            meta = self.db.get_match(mid) or meta
            return MatchBundle(mid, meta, DataLevel.EVENTS, source, events=events)

        if source == "simulated":
            from src.ingestion.statsbomb_loader import StatsBombDataLoader

            loader = StatsBombDataLoader()
            events = loader.ingest_match_events(mid) if mid < 900_000 else loader.generate_tactical_simulation_match(
                home_team=meta.get("home_team_name", "Equipe A"),
                away_team=meta.get("away_team_name", "Equipe B"), match_id=mid)
            return MatchBundle(mid, meta, DataLevel.SIMULATED, "simulated", events=events)

        if source == "upload":
            return MatchBundle(mid, meta, DataLevel.UPLOAD, "upload", events=self.db.load_events(mid))

        notes = []
        if source in ("api_football", "espn") and not self.db.has_boxscore(mid):
            try:
                (self.api_football.ingest_fixture if source == "api_football" else self.espn.ingest_event)(mid)
            except Exception as exc:
                notes.append(f"Não foi possível baixar o boxscore agora: {exc}")
        meta = self.db.get_match(mid) or meta
        box = self.db.load_boxscore(mid)
        if box["team_stats"].empty and _redirect_ok:
            # Só placar? Procura a MESMA partida em outra base que tenha estatísticas.
            sib = self.stats_sibling(mid, meta)
            if sib is not None and sib.get("data_level") == DataLevel.EVENTS:
                bundle = self.load(int(sib["match_id"]), _redirect_ok=False)
                bundle.notes = list(bundle.notes or []) + [
                    f"Esta partida também existe em {sib['data_source']} com eventos completos — abrindo a versão mais rica."]
                return bundle
            if sib is not None:
                box, how = self._merge_sibling_stats(mid, meta, box, sib)
                notes.append(how)
            elif self.espn.enabled:
                got = self._espn_on_demand(mid, meta)
                if got is not None:
                    box, how = self._merge_sibling_stats(mid, meta, box, got)
                    notes.append(how)
        has_team_stats = not box["team_stats"].empty
        has_player_data = any(
            k in box and box[k] is not None and not box[k].empty
            for k in ("lineups", "player_stats")
        )
        # BOXSCORE precisa abranger também jogos com escalação/números individuais,
        # mesmo quando a fonte não publica estatísticas coletivas.
        has_analysis_data = has_team_stats or has_player_data
        level = DataLevel.BOXSCORE if has_analysis_data else DataLevel.RESULT
        if meta and meta.get("data_level") != level:
            self.db.set_level(mid, level)
        if not has_team_stats and has_player_data:
            notes.append("Há escalações e/ou números individuais, mas não estatísticas coletivas do time.")
        elif not has_analysis_data:
            notes.append("Esta partida só tem placar/gols: não há estatísticas coletivas nem números individuais "
                         "em nenhuma fonte local. Ative uma fonte de estatísticas quando disponível.")
        return MatchBundle(mid, meta, level, source, boxscore=box, notes=notes)

    # ------------------------------------------------- mesma partida, outra base
    def stats_sibling(self, mid: int, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Mesma data (±1 dia) e mesmas equipes em outra fonte com eventos ou estatísticas."""
        from src.data_lake.ids import team_core

        d = str(meta.get("match_date") or "")[:10]
        h, a = team_core(meta.get("home_team_name")), team_core(meta.get("away_team_name"))
        if not d or not h or not a:
            return None
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT m.match_id, m.home_team_name, m.away_team_name, m.data_source, m.data_level,
                          (
                            EXISTS(SELECT 1 FROM match_team_stats s WHERE s.match_id = m.match_id)
                            OR EXISTS(SELECT 1 FROM match_lineups l WHERE l.match_id = m.match_id)
                            OR EXISTS(SELECT 1 FROM match_player_stats p WHERE p.match_id = m.match_id)
                          ) AS has_box_data
                   FROM matches m
                   WHERE m.match_id != ?
                     AND m.match_date BETWEEN date(?, '-1 day') AND date(?, '+1 day')
                     AND (m.data_level = 'EVENTS' OR
                          EXISTS(SELECT 1 FROM match_team_stats s WHERE s.match_id = m.match_id)
                          OR EXISTS(SELECT 1 FROM match_lineups l WHERE l.match_id = m.match_id)
                          OR EXISTS(SELECT 1 FROM match_player_stats p WHERE p.match_id = m.match_id))""",
                (int(mid), d, d)).fetchall()
        best, best_rank = None, -1
        for r in rows:
            rh, ra = team_core(r[1]), team_core(r[2])
            if not ((_same(rh, h) and _same(ra, a)) or (_same(rh, a) and _same(ra, h))):
                continue
            rank = 2 if r[4] == DataLevel.EVENTS else (1 if r[5] else 0)
            if rank > best_rank and rank > 0:
                best = {"match_id": r[0], "home_team_name": r[1], "away_team_name": r[2],
                        "data_source": r[3], "data_level": r[4]}
                best_rank = rank
        return best

    def _merge_sibling_stats(self, mid: int, meta: Dict[str, Any], box: Dict[str, Any], sib: Dict[str, Any]):
        """Copia estatísticas (e o que faltar) da partida-irmã, renomeando as equipes para os nomes desta."""
        from src.data_lake.ids import team_core

        other = self.db.load_boxscore(int(sib["match_id"]))
        names = {}
        for side in ("home_team_name", "away_team_name"):
            mine = meta.get(side)
            for s2 in ("home_team_name", "away_team_name"):
                if _same(team_core(sib.get(s2)), team_core(mine)):
                    names[sib.get(s2)] = mine
        ren = lambda df: df.assign(team_name=df["team_name"].map(lambda t: names.get(t, t))) if not df.empty else df
        merged = dict(box)
        # Preserva o que a partida atual já tem e preenche somente as lacunas com a fonte irmã.
        # Uma fonte que só tem escalações não pode apagar o boxscore coletivo já gravado.
        for k in ("team_stats", "lineups", "timeline", "player_stats"):
            current = merged.get(k)
            incoming = other.get(k)
            current_empty = current is None or getattr(current, "empty", True)
            incoming_has_data = incoming is not None and not getattr(incoming, "empty", True)
            if current_empty and incoming_has_data:
                merged[k] = ren(incoming)
        try:
            payload = {k: v.drop(columns=[c for c in ("match_id", "id") if c in v.columns]).to_dict("records")
                       for k, v in merged.items() if hasattr(v, "to_dict")}
            if "player_stats" in payload:
                for p in payload["player_stats"]:
                    if isinstance(p.get("stats"), str):
                        try:
                            p["stats"] = json.loads(p["stats"])
                        except Exception:
                            p["stats"] = {}
            self.db.save_boxscore(mid, payload)
            has_team = not merged["team_stats"].empty
            has_individual = any(not merged[k].empty for k in ("lineups", "player_stats"))
            self.db.set_level(mid, DataLevel.BOXSCORE if (has_team or has_individual) else DataLevel.RESULT)
        except Exception:
            pass
        return merged, f"Dados adicionais trazidos da mesma partida na base {sib['data_source']} (data e equipes conferidas)."

    def _espn_on_demand(self, mid: int, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Consulta o placar da ESPN no dia do jogo e baixa o resumo com estatísticas (só se a liga for coberta)."""
        from datetime import date as _date, timedelta as _td
        from src.data_lake.ids import team_core

        league = espn_league_for(meta)
        d = str(meta.get("match_date") or "")[:10]
        if not league or not d or d < "2003-01-01" or int(mid) in MatchDataService._espn_tried:
            return None
        MatchDataService._espn_tried.add(int(mid))      # uma tentativa por jogo por sessão
        cl = self.espn.client
        old_t, old_r = cl.timeout_s, getattr(cl, "max_retries", 1)
        cl.timeout_s, cl.max_retries = 8.0, 1               # sob demanda: rápido ou nada
        try:
            day = _date.fromisoformat(d)
            recs = self.espn.scoreboard(league, day - _td(days=1), day + _td(days=1))
        except Exception:
            return None
        finally:
            cl.timeout_s, cl.max_retries = old_t, old_r
        h, a = team_core(meta.get("home_team_name")), team_core(meta.get("away_team_name"))
        for r in recs:
            rh, ra = team_core(r.get("home_team_name")), team_core(r.get("away_team_name"))
            if (_same(rh, h) and _same(ra, a)) or (_same(rh, a) and _same(ra, h)):
                try:
                    self.db.upsert_matches([r])
                    self.espn.ingest_event(int(r["match_id"]))
                except Exception:
                    return None
                if self.db.has_boxscore(int(r["match_id"])):
                    return {"match_id": r["match_id"], "home_team_name": r["home_team_name"],
                            "away_team_name": r["away_team_name"], "data_source": "espn", "data_level": DataLevel.BOXSCORE}
        return None
