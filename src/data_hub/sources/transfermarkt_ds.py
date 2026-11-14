"""
Transfermarkt via transfermarkt-datasets (github.com/dcaribou/transfermarkt-datasets).

Em vez de raspar o Transfermarkt (bloqueia robôs e proíbe a coleta nos termos), usa o conjunto público que o
projeto mantém e atualiza toda semana: clubes, jogadores, valores de mercado históricos, jogos e aparições, em
CSVs gzip num bucket público. O conector baixa só o que mudou (cabeçalhos ETag/Last-Modified) uma vez por dia.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd

BASE = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"
FILES = ("competitions", "clubs", "players", "player_valuations", "games")
CACHE = Path("data/raw/transfermarkt")
LICENSE = "transfermarkt-datasets (dados públicos do Transfermarkt compilados por dcaribou) — citar a fonte"


class TransfermarktDatasets:
    source = "transfermarkt"
    enabled = True

    def __init__(self, cache_dir: Path = CACHE, base: str = BASE):
        self.cache = Path(cache_dir)
        self.base = base

    def _download(self, name: str, max_age_s: float = 24 * 3600) -> Path:
        import requests

        self.cache.mkdir(parents=True, exist_ok=True)
        f = self.cache / f"{name}.csv.gz"
        meta = self.cache / f"{name}.meta.json"
        if f.exists() and time.time() - f.stat().st_mtime < max_age_s:
            return f
        headers = {"User-Agent": "TacticalIntelligenceLab/1.0 (uso acadêmico)"}
        if meta.exists():
            m = json.loads(meta.read_text())
            if m.get("etag"):
                headers["If-None-Match"] = m["etag"]
        r = requests.get(f"{self.base}/{name}.csv.gz", headers=headers, timeout=120)
        if r.status_code == 304 and f.exists():
            f.touch()
            return f
        r.raise_for_status()
        f.write_bytes(r.content)
        meta.write_text(json.dumps({"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified")}))
        return f

    @staticmethod
    def read(path: Path) -> pd.DataFrame:
        return pd.read_csv(path, compression="gzip", low_memory=False)

    # ------------------------------------------------------------- normalização
    @staticmethod
    def clubs_frame(clubs: pd.DataFrame, comps: pd.DataFrame) -> pd.DataFrame:
        c = clubs.merge(comps[["competition_id", "name", "country_name"]].rename(
            columns={"competition_id": "domestic_competition_id", "name": "liga"}), on="domestic_competition_id", how="left")
        keep = {"club_id": "transfermarkt_id", "name": "nome", "liga": "liga", "country_name": "pais",
                "total_market_value": "valor_total_eur", "squad_size": "elenco", "average_age": "idade_media",
                "stadium_name": "estadio", "stadium_seats": "capacidade", "coach_name": "tecnico", "last_season": "ultima_temporada"}
        return c[[k for k in keep if k in c.columns]].rename(columns=keep)

    @staticmethod
    def players_frame(players: pd.DataFrame) -> pd.DataFrame:
        keep = {"player_id": "transfermarkt_id", "name": "nome", "date_of_birth": "nascimento", "position": "posicao",
                "sub_position": "funcao", "foot": "pe", "height_in_cm": "altura_cm", "country_of_citizenship": "nacionalidade",
                "current_club_id": "clube_id", "current_club_name": "clube", "market_value_in_eur": "valor_mercado_eur",
                "highest_market_value_in_eur": "maior_valor_eur", "contract_expiration_date": "fim_contrato",
                "last_season": "ultima_temporada"}
        p = players[[k for k in keep if k in players.columns]].rename(columns=keep)
        if "nascimento" in p:
            p["nascimento"] = p["nascimento"].astype(str).str[:10]
        return p

    @staticmethod
    def valuations_frame(vals: pd.DataFrame) -> pd.DataFrame:
        keep = {"player_id": "transfermarkt_id", "date": "data", "market_value_in_eur": "valor_mercado_eur",
                "current_club_id": "clube_id"}
        return vals[[k for k in keep if k in vals.columns]].rename(columns=keep)

    @staticmethod
    def games_frame(games: pd.DataFrame) -> pd.DataFrame:
        keep = {"game_id": "transfermarkt_id", "competition_id": "competicao_id", "season": "temporada", "round": "rodada",
                "date": "data", "home_club_name": "mandante", "away_club_name": "visitante", "home_club_goals": "gols_mandante",
                "away_club_goals": "gols_visitante", "stadium": "estadio", "attendance": "publico", "referee": "arbitro",
                "home_club_formation": "formacao_mandante", "away_club_formation": "formacao_visitante",
                "home_club_manager_name": "tecnico_mandante", "away_club_manager_name": "tecnico_visitante"}
        return games[[k for k in keep if k in games.columns]].rename(columns=keep)

    # --------------------------------------------------------------------- sync
    def sync(self, lake, progress: Optional[Callable[[str], None]] = None, max_age_s: float = 24 * 3600) -> Dict[str, int]:
        say = progress or (lambda m: None)
        raw = {}
        for name in FILES:
            try:
                raw[name] = self.read(self._download(name, max_age_s))
                say(f"  transfermarkt: {name} ({len(raw[name])} linhas)")
            except Exception as exc:
                say(f"  transfermarkt: {name} indisponível ({exc})")
        out = {"tabelas": 0}
        prov = dict(source="Transfermarkt (transfermarkt-datasets)", connector="TransfermarktDatasets", license=LICENSE)
        if "clubs" in raw and "competitions" in raw:
            lake.write("tm_clubes", self.clubs_frame(raw["clubs"], raw["competitions"]), **prov)
            out["tabelas"] += 1
        if "players" in raw:
            lake.write("tm_jogadores", self.players_frame(raw["players"]), **prov)
            out["tabelas"] += 1
        if "player_valuations" in raw:
            lake.write("tm_valores", self.valuations_frame(raw["player_valuations"]), mirror_sqlite=False, **prov)
            out["tabelas"] += 1
        if "games" in raw:
            lake.write("tm_jogos", self.games_frame(raw["games"]), mirror_sqlite=False, **prov)
            out["tabelas"] += 1
        if "competitions" in raw:
            lake.write("tm_competicoes", raw["competitions"], **prov)
        out["updated"] = out["tabelas"]
        return out
