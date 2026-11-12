"""
Módulo de Ingestão de Dados (StatsBomb + SQLite + Brasileirão Série A + Múltiplos Jogos)
Responsável por baixar, cachear e estruturar eventos de partidas e metadados.
"""

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

from src.intelligence.nlp_neural_router import TacticalNLPInterpreter


class StatsBombDataLoader:
    """
    Gerenciador robusto de ingestão, cache, busca inteligente em múltiplas
    competições (StatsBomb + Brasileirão Série A) e simulações táticas.
    """

    BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

    # Principais Competições Públicas do StatsBomb Open Data
    FEATURED_COMPETITIONS = [
        (43, 106),   # Copa do Mundo FIFA 2022
        (9, 281),    # Bundesliga 2023/2024 (Bayer Leverkusen Invicto)
        (55, 282),   # UEFA Euro 2024
        (223, 282),  # Copa América 2024
        (43, 3),     # Copa do Mundo FIFA 2018
        (16, 4),     # UEFA Champions League 2018/2019
        (11, 90),    # La Liga 2020/2021
    ]

    # Dicionário completo de sinônimos, seleções e clubes da Série A brasileira
    TEAM_ALIASES = {
        # Seleções e Clubes Internacionais
        "franca": "france",
        "frança": "france",
        "france": "france",
        "argentina": "argentina",
        "croacia": "croatia",
        "croácia": "croatia",
        "croatia": "croatia",
        "marrocos": "morocco",
        "morocco": "morocco",
        "holanda": "netherlands",
        "paises baixos": "netherlands",
        "netherlands": "netherlands",
        "brasil": "brazil",
        "brazil": "brazil",
        "inglaterra": "england",
        "england": "england",
        "espanha": "spain",
        "spain": "spain",
        "alemanha": "germany",
        "germany": "germany",
        "portugal": "portugal",
        "belgica": "belgium",
        "bélgica": "belgium",
        "belgium": "belgium",
        "italia": "italy",
        "itália": "italy",
        "italy": "italy",
        "suica": "switzerland",
        "suíça": "switzerland",
        "switzerland": "switzerland",
        "uruguai": "uruguay",
        "uruguay": "uruguay",
        "colombia": "colombia",
        "colômbia": "colombia",
        "mexico": "mexico",
        "méxico": "mexico",
        "estados unidos": "united states",
        "eua": "united states",
        "usa": "united states",
        "japao": "japan",
        "japão": "japan",
        "coreia": "south korea",
        "coreia do sul": "south korea",
        "senegal": "senegal",
        "gana": "ghana",
        "camaroes": "cameroon",
        "camarões": "cameroon",
        "polonia": "poland",
        "polônia": "poland",
        "dinamarca": "denmark",
        "servia": "serbia",
        "sérvia": "serbia",
        "equador": "ecuador",
        "catar": "qatar",
        "arabia saudita": "saudi arabia",
        "arábia saudita": "saudi arabia",

        # Clubes Europeus Populares
        "leverkusen": "leverkusen",
        "bayer": "leverkusen",
        "bayer leverkusen": "leverkusen",
        "bayern": "bayern",
        "bayern de munique": "bayern",
        "bayern munich": "bayern",
        "dortmund": "dortmund",
        "borussia": "dortmund",
        "borussia dortmund": "dortmund",
        "leipzig": "leipzig",
        "rb leipzig": "leipzig",
        "stuttgart": "stuttgart",
        "barcelona": "barcelona",
        "barca": "barcelona",
        "barça": "barcelona",
        "real madrid": "real madrid",
        "real": "real madrid",
        "atletico de madrid": "atletico madrid",
        "atletico madrid": "atletico madrid",
        "sevilla": "sevilla",
        "liverpool": "liverpool",
        "tottenham": "tottenham",
        "spurs": "tottenham",
        "psg": "paris saint-germain",
        "paris": "paris saint-germain",

        # Clubes Brasileiros (Série A Completa)
        "cruzeiro": "cruzeiro",
        "cabuloso": "cruzeiro",
        "raposa": "cruzeiro",
        "atletico-mg": "atletico-mg",
        "atletico mg": "atletico-mg",
        "galo": "atletico-mg",
        "flamengo": "flamengo",
        "mengao": "flamengo",
        "palmeiras": "palmeiras",
        "verdao": "palmeiras",
        "botafogo": "botafogo",
        "fogao": "botafogo",
        "sao paulo": "sao paulo",
        "tricolor": "sao paulo",
        "fluminense": "fluminense",
        "flu": "fluminense",
        "internacional": "internacional",
        "inter": "internacional",
        "gremio": "gremio",
        "athletico-pr": "athletico-pr",
        "athletico pr": "athletico-pr",
        "furacao": "athletico-pr",
        "bahia": "bahia",
        "esquadrao": "bahia",
        "vasco da gama": "vasco da gama",
        "vasco": "vasco da gama",
        "corinthians": "corinthians",
        "timao": "corinthians",
        "fortaleza": "fortaleza",
        "tradao do pici": "fortaleza",
        "red bull bragantino": "red bull bragantino",
        "bragantino": "red bull bragantino",
        "cuiaba": "cuiaba",
        "vitoria": "vitoria",
        "juventude": "juventude",
        "criciuma": "criciuma",
        "atletico goianiense": "atletico goianiense",
        "atletico-go": "atletico goianiense",
    }

    CURATED_OPEN_MATCHES = [
        {
            "match_id": 3869685,
            "competition_id": 43,
            "season_id": 106,
            "competition_name": "FIFA World Cup",
            "season_name": "2022",
            "match_date": "2022-12-18",
            "home_team_name": "Argentina",
            "away_team_name": "France",
            "home_score": 3,
            "away_score": 3,
            "stadium_name": "Lusail Iconic Stadium",
            "referee_name": "Szymon Marciniak",
            "has_360_data": 1,
            "label": "Copa do Mundo 2022 - Final: Argentina 3x3 França (ID 3869685)",
        },
        {
            "match_id": 3869355,
            "competition_id": 43,
            "season_id": 106,
            "competition_name": "FIFA World Cup",
            "season_name": "2022",
            "match_date": "2022-11-22",
            "home_team_name": "Argentina",
            "away_team_name": "Saudi Arabia",
            "home_score": 1,
            "away_score": 2,
            "stadium_name": "Lusail Iconic Stadium",
            "referee_name": "Slavko Vinčić",
            "has_360_data": 1,
            "label": "Copa do Mundo 2022 - Argentina 1x2 Arábia Saudita (ID 3869355)",
        },
        {
            "match_id": 3869519,
            "competition_id": 43,
            "season_id": 106,
            "competition_name": "FIFA World Cup",
            "season_name": "2022",
            "match_date": "2022-12-03",
            "home_team_name": "Argentina",
            "away_team_name": "Australia",
            "home_score": 2,
            "away_score": 1,
            "stadium_name": "Ahmad bin Ali Stadium",
            "referee_name": "Szymon Marciniak",
            "has_360_data": 1,
            "label": "Copa do Mundo 2022 - Argentina 2x1 Austrália (ID 3869519)",
        },
    ]

    def __init__(
        self,
        db_path: str = "database/tactical_lab.db",
        schema_path: str = "database/schema.sql",
        raw_dir: str = "data/raw",
    ) -> None:
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path)
        self.raw_dir = Path(raw_dir)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_database(self) -> None:
        if not self.schema_path.exists():
            raise FileNotFoundError(
                f"Arquivo de schema SQL não encontrado em: {self.schema_path}"
            )
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        with self._get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    def _fetch_json_with_cache(
        self, relative_endpoint: str, cache_filename: str
    ) -> Any:
        cache_file = self.raw_dir / cache_filename
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        url = f"{self.BASE_URL}/{relative_endpoint}"
        try:
            response = requests.get(url, timeout=25)
            if response.status_code == 404:
                raise FileNotFoundError(
                    f"Recurso não encontrado (HTTP 404) no StatsBomb Open Data: {relative_endpoint}"
                )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as exc:
            raise FileNotFoundError(
                f"Partida ou catálogo indisponível no repositório público ({relative_endpoint}): {exc}"
            ) from exc

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        return data

    def fetch_competitions(self) -> pd.DataFrame:
        data = self._fetch_json_with_cache("competitions.json", "competitions.json")
        df = pd.DataFrame(data)
        cols = [
            "competition_id",
            "season_id",
            "competition_name",
            "season_name",
            "country_name",
            "competition_gender",
        ]
        existing_cols = [c for c in cols if c in df.columns]
        return df[existing_cols].drop_duplicates().reset_index(drop=True)

    def fetch_matches(self, competition_id: int, season_id: int) -> pd.DataFrame:
        endpoint = f"matches/{competition_id}/{season_id}.json"
        cache_name = f"matches_{competition_id}_{season_id}.json"
        try:
            raw_matches = self._fetch_json_with_cache(endpoint, cache_name)
        except Exception:
            return pd.DataFrame(self.CURATED_OPEN_MATCHES)

        parsed_rows = []
        for m in raw_matches:
            comp = m.get("competition", {})
            season = m.get("season", {})
            home = m.get("home_team", {})
            away = m.get("away_team", {})
            stadium = m.get("stadium", {}) or {}
            referee = m.get("referee", {}) or {}

            home_name = home.get("home_team_name", home.get("name", "Home"))
            away_name = away.get("away_team_name", away.get("name", "Away"))
            comp_name = comp.get("competition_name", "Unknown")
            m_id = int(m["match_id"])

            parsed_rows.append(
                {
                    "match_id": m_id,
                    "competition_id": int(comp.get("competition_id", competition_id)),
                    "competition_name": comp_name,
                    "season_id": int(season.get("season_id", season_id)),
                    "season_name": season.get("season_name", "Unknown"),
                    "match_date": m.get("match_date", ""),
                    "home_team_id": int(home.get("home_team_id", home.get("id", 0))),
                    "home_team_name": home_name,
                    "away_team_id": int(away.get("away_team_id", away.get("id", 0))),
                    "away_team_name": away_name,
                    "home_score": int(m.get("home_score", 0)),
                    "away_score": int(m.get("away_score", 0)),
                    "stadium_name": stadium.get("name", "Unknown"),
                    "referee_name": referee.get("name", "Unknown"),
                    "has_360_data": 1 if m.get("match_status_360") else 0,
                    # Correção para o KeyError 'label' na UI do Streamlit
                    "label": f"{comp_name} — {home_name} vs {away_name} [ID {m_id}]",
                }
            )

        df_matches = pd.DataFrame(parsed_rows)
        if not df_matches.empty:
            self._upsert_matches(df_matches)

        return df_matches.sort_values("match_date").reset_index(drop=True)

    def _upsert_matches(self, df_matches: pd.DataFrame) -> None:
        if df_matches.empty:
            return
        with self._get_connection() as conn:
            for _, row in df_matches.iterrows():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO matches (
                        match_id, competition_id, competition_name, season_id, season_name,
                        match_date, home_team_id, home_team_name, away_team_id, away_team_name,
                        home_score, away_score, stadium_name, referee_name, has_360_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        int(row["match_id"]),
                        int(row.get("competition_id", 0)),
                        str(row.get("competition_name", "Unknown")),
                        int(row.get("season_id", 0)),
                        str(row.get("season_name", "Unknown")),
                        str(row.get("match_date", "")),
                        int(row.get("home_team_id", 0)),
                        str(row.get("home_team_name", "")),
                        int(row.get("away_team_id", 0)),
                        str(row.get("away_team_name", "")),
                        int(row.get("home_score", 0)),
                        int(row.get("away_score", 0)),
                        str(row.get("stadium_name", "Unknown")),
                        str(row.get("referee_name", "Unknown")),
                        int(row.get("has_360_data", 0)),
                    ),
                )
            conn.commit()

    def ensure_rich_catalog_in_db(self) -> pd.DataFrame:
        """
        Sincroniza no SQLite as principais competições internacionais (StatsBomb)
        e a base multi-jogos do Campeonato Brasileiro Série A.
        """
        from src.ingestion.brazil_and_multi_source import (
            BrasileiraoAndMultiSourceProvider,
        )

        with self._get_connection() as conn:
            existing = pd.read_sql_query(
                "SELECT * FROM matches WHERE competition_id > 0", conn
            )

        loaded_pairs = set()
        if not existing.empty:
            loaded_pairs = set(
                zip(
                    existing["competition_id"].astype(int),
                    existing["season_id"].astype(int),
                )
            )

        # Insere o catálogo do Brasileirão Série A (competition_id = 71, season_id = 2026) se ausente
        if (71, 2026) not in loaded_pairs:
            br_df = pd.DataFrame(
                BrasileiraoAndMultiSourceProvider.BRAZIL_MATCH_CATALOG
            )
            br_df["home_team_id"] = 701
            br_df["away_team_id"] = 702
            br_df["stadium_name"] = "Estádio Série A"
            br_df["referee_name"] = "CBF Arbitragem"
            br_df["has_360_data"] = 0
            # Adiciona o label padronizado para evitar KeyError nas views
            if "label" not in br_df.columns:
                br_df["label"] = br_df.apply(
                    lambda r: f"{r.get('competition_name', 'Série A')} — {r['home_team_name']} vs {r['away_team_name']} [ID {r['match_id']}]",
                    axis=1
                )
            self._upsert_matches(br_df)

        for comp_id, seas_id in self.FEATURED_COMPETITIONS:
            if (comp_id, seas_id) not in loaded_pairs:
                try:
                    self.fetch_matches(comp_id, seas_id)
                except Exception:
                    continue

        with self._get_connection() as conn:
            full_catalog = pd.read_sql_query(
                "SELECT * FROM matches WHERE competition_id > 0 ORDER BY match_date DESC",
                conn,
            )

        if full_catalog.empty:
            curated_df = pd.DataFrame(self.CURATED_OPEN_MATCHES)
            br_catalog_df = pd.DataFrame(BrasileiraoAndMultiSourceProvider.BRAZIL_MATCH_CATALOG)
            full_catalog = pd.concat([curated_df, br_catalog_df], ignore_index=True)

        # Garante que a coluna 'label' exista no dataframe retornado para a UI
        if "label" not in full_catalog.columns:
            full_catalog["label"] = full_catalog.apply(
                lambda r: f"{r.get('competition_name', 'StatsBomb')} — {r.get('home_team_name', '')} vs {r.get('away_team_name', '')} [ID {r.get('match_id', 0)}]",
                axis=1
            )

        return full_catalog

    def ingest_match_events(
        self, match_id: int, force_reload: bool = False
    ) -> pd.DataFrame:
        """
        Carrega eventos do SQLite, da base autêntica do Brasileirão (IDs 880001..)
        ou do repositório oficial StatsBomb Open Data.
        """
        if not force_reload:
            cached_db = self.load_events_from_db(match_id)
            if not cached_db.empty:
                return cached_db

        from src.ingestion.brazil_and_multi_source import (
            BrasileiraoAndMultiSourceProvider,
        )

        for br_m in BrasileiraoAndMultiSourceProvider.BRAZIL_MATCH_CATALOG:
            if int(br_m["match_id"]) == int(match_id):
                df_br = BrasileiraoAndMultiSourceProvider.generate_authentic_match_events(
                    br_m["home_team_name"],
                    br_m["away_team_name"],
                    int(match_id),
                )
                self._save_events_to_db(df_br, int(match_id))
                return df_br

        endpoint = f"events/{match_id}.json"
        cache_name = f"events_{match_id}.json"
        raw_events = self._fetch_json_with_cache(endpoint, cache_name)

        df_events = self._parse_raw_events(raw_events, match_id)
        self._save_events_to_db(df_events, match_id)
        return df_events

    def load_events_from_db(self, match_id: int) -> pd.DataFrame:
        with self._get_connection() as conn:
            df = pd.read_sql_query(
                "SELECT * FROM events WHERE match_id = ? ORDER BY index_num ASC",
                conn,
                params=(int(match_id),),
            )
        return df

    def load_multiple_matches_events(self, match_ids: List[int]) -> pd.DataFrame:
        if not match_ids:
            return pd.DataFrame()
        placeholders = ",".join(["?"] * len(match_ids))
        with self._get_connection() as conn:
            query = f"SELECT * FROM events WHERE match_id IN ({placeholders}) ORDER BY match_id, index_num ASC"
            return pd.read_sql_query(
                query, conn, params=[int(m) for m in match_ids]
            )

    def ingest_custom_csv_or_json(
        self, file_path: str, match_id: int = 999001
    ) -> pd.DataFrame:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        elif path.suffix.lower() == ".json":
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list) and len(raw) > 0 and "type" in raw[0]:
                df = self._parse_raw_events(raw, match_id)
                self._save_events_to_db(df, match_id)
                return df
            df = pd.DataFrame(raw)
        else:
            raise ValueError("Formato não suportado. Use arquivos .csv ou .json.")

        required_cols = {"team_name", "type_name", "x", "y"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(
                f"O arquivo enviado não possui as colunas mínimas obrigatórias: {missing}"
            )

        df["match_id"] = int(match_id)
        if "event_id" not in df.columns:
            df["event_id"] = [f"custom_{match_id}_{i}" for i in range(len(df))]
        if "index_num" not in df.columns:
            df["index_num"] = range(1, len(df) + 1)
        if "period" not in df.columns:
            df["period"] = 1
        if "minute" not in df.columns:
            df["minute"] = 0
        if "second" not in df.columns:
            df["second"] = 0
        if "team_id" not in df.columns:
            df["team_id"] = pd.factorize(df["team_name"])[0] + 1

        self._save_events_to_db(df, match_id)
        return df

    def _save_events_to_db(self, df_events: pd.DataFrame, match_id: int) -> None:
        if df_events.empty:
            return
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM matches WHERE match_id = ?", (int(match_id),)
            )
            if cursor.fetchone() is None:
                teams = df_events["team_name"].dropna().unique().tolist()
                home_team = teams[0] if len(teams) > 0 else "Home Team"
                away_team = teams[1] if len(teams) > 1 else "Away Team"
                conn.execute(
                    """
                    INSERT INTO matches (
                        match_id, competition_id, competition_name, season_id, season_name,
                        home_team_name, away_team_name
                    ) VALUES (?, 0, 'Custom/Direct Match', 0, 'N/A', ?, ?)
                """,
                    (int(match_id), home_team, away_team),
                )

            conn.execute("DELETE FROM events WHERE match_id = ?", (int(match_id),))
            df_events.to_sql("events", conn, if_exists="append", index=False)
            conn.commit()

    def _parse_raw_events(self, raw_events: List[Dict[str, Any]], match_id: int) -> pd.DataFrame:
        rows = []
        for idx, ev in enumerate(raw_events):
            loc = ev.get("location")
            # Blindagem defensiva rigorosa para evitar TypeError de NoneType em floats de coordenadas
            x = (
                float(loc[0])
                if isinstance(loc, (list, tuple)) and len(loc) >= 2 and loc[0] is not None
                else np.nan
            )
            y = (
                float(loc[1])
                if isinstance(loc, (list, tuple)) and len(loc) >= 2 and loc[1] is not None
                else np.nan
            )

            ev_type = ev.get("type", {}).get("name", "Unknown")
            end_x, end_y = np.nan, np.nan

            pass_dict = ev.get("pass", {}) or {}
            if ev_type == "Pass" and "end_location" in pass_dict:
                end_loc = pass_dict["end_location"]
                if (
                    isinstance(end_loc, (list, tuple))
                    and len(end_loc) >= 2
                    and end_loc[0] is not None
                    and end_loc[1] is not None
                ):
                    end_x, end_y = float(end_loc[0]), float(end_loc[1])

            carry_dict = ev.get("carry", {}) or {}
            if ev_type == "Carry" and "end_location" in carry_dict:
                end_loc = carry_dict["end_location"]
                if (
                    isinstance(end_loc, (list, tuple))
                    and len(end_loc) >= 2
                    and end_loc[0] is not None
                    and end_loc[1] is not None
                ):
                    end_x, end_y = float(end_loc[0]), float(end_loc[1])

            shot_dict = ev.get("shot", {}) or {}
            if ev_type == "Shot":
                end_loc = shot_dict.get("end_location", [120, 40, 0])
                if (
                    isinstance(end_loc, (list, tuple))
                    and len(end_loc) >= 2
                    and end_loc[0] is not None
                    and end_loc[1] is not None
                ):
                    end_x, end_y = float(end_loc[0]), float(end_loc[1])
                else:
                    end_x, end_y = 120.0, 40.0

            duel_dict = ev.get("duel", {}) or {}
            interception_dict = ev.get("interception", {}) or {}
            recovery_dict = ev.get("ball_recovery", {}) or {}
            foul_dict = ev.get("foul_committed", {}) or {}
            sub_dict = ev.get("substitution", {}) or {}
            tactics_dict = ev.get("tactics", {}) or {}

            pass_recipient = pass_dict.get("recipient", {}) or {}
            pass_body_part = pass_dict.get("body_part", {}) or {}
            pass_type = pass_dict.get("type", {}) or {}
            pass_outcome = pass_dict.get("outcome", {}) or {}
            pass_height = pass_dict.get("height", {}) or {}

            shot_outcome = shot_dict.get("outcome", {}) or {}
            shot_body_part = shot_dict.get("body_part", {}) or {}
            shot_type = shot_dict.get("type", {}) or {}

            duel_type = duel_dict.get("type", {}) or {}
            duel_outcome = duel_dict.get("outcome", {}) or {}
            interception_outcome = interception_dict.get("outcome", {}) or {}

            rows.append(
                {
                    "event_id": str(ev.get("id", str(idx))),
                    "match_id": int(match_id),
                    "index_num": int(ev.get("index", idx + 1)),
                    "period": int(ev.get("period", 1)),
                    "timestamp": str(ev.get("timestamp", "00:00:00.000")),
                    "minute": int(ev.get("minute", 0)),
                    "second": int(ev.get("second", 0)),
                    "possession": int(ev.get("possession", 1)),
                    "possession_team_id": int(ev.get("possession_team", {}).get("id", 0)) if ev.get("possession_team") else None,
                    "possession_team_name": str(ev.get("possession_team", {}).get("name", "")) if ev.get("possession_team") else "",
                    "team_id": int(ev.get("team", {}).get("id", 0)),
                    "team_name": str(ev.get("team", {}).get("name", "Unknown")),
                    "player_id": int(ev.get("player", {}).get("id", 0)) if ev.get("player") else None,
                    "player_name": str(ev.get("player", {}).get("name", "")) if ev.get("player") else "",
                    "position_name": str(ev.get("position", {}).get("name", "Unknown")),
                    "type_name": ev_type,
                    "play_pattern_name": str(ev.get("play_pattern", {}).get("name", "Regular Play")),
                    "under_pressure": 1 if ev.get("under_pressure") else 0,
                    "counterpress": 1 if ev.get("counterpress") else 0,
                    "x": x,
                    "y": y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "pass_length": pass_dict.get("length"),
                    "pass_angle": pass_dict.get("angle"),
                    "pass_recipient_id": pass_recipient.get("id"),
                    "pass_recipient_name": pass_recipient.get("name"),
                    "pass_height_name": pass_height.get("name"),
                    "pass_body_part": pass_body_part.get("name"),
                    "pass_type_name": pass_type.get("name"),
                    "pass_outcome_name": pass_outcome.get("name"),
                    "is_pass_Switch": 1 if pass_dict.get("switch") else 0,
                    "is_pass_cross": 1 if pass_dict.get("cross") else 0,
                    "is_pass_through_ball": 1 if pass_dict.get("through_ball") else 0,
                    "shot_statsbomb_xg": shot_dict.get("statsbomb_xg"),
                    "shot_outcome_name": shot_outcome.get("name"),
                    "shot_body_part_name": shot_body_part.get("name"),
                    "shot_type_name": shot_type.get("name"),
                    "duel_type_name": duel_type.get("name"),
                    "duel_outcome_name": duel_outcome.get("name"),
                    "interception_outcome_name": interception_outcome.get("name"),
                    "ball_recovery_failure": 1 if recovery_dict.get("recovery_failure") else 0,
                    "foul_committed_card_name": foul_dict.get("card", {}).get("name"),
                    "substitution_replacement_name": sub_dict.get("replacement", {}).get("name"),
                    "tactics_formation": tactics_dict.get("formation"),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _strip_accents_and_lower(text: str) -> str:
        if not text:
            return ""
        no_acc = "".join(
            c for c in unicodedata.normalize("NFD", str(text))
            if unicodedata.category(c) != "Mn"
        )
        return no_acc.lower().strip()

    def _normalize_team_token(self, raw_team: str) -> str:
        clean = self._strip_accents_and_lower(raw_team)
        clean = re.sub(
            r"\b(jogo|partida|confronto|selecao|clube|time|fc|sc|ec|do|da|de)\b",
            " ",
            clean,
        )
        clean = re.sub(r"\s+", " ", clean).strip()
        if clean in self.TEAM_ALIASES:
            return self.TEAM_ALIASES[clean]
        for alias_key, official_val in self.TEAM_ALIASES.items():
            if len(alias_key) >= 4 and alias_key in clean:
                return official_val
        return clean

    @classmethod
    def _extract_teams_from_text(cls, query_text: str) -> Tuple[str, Optional[str]]:
        cleaned = re.sub(r"\(.*?\)", "", query_text or "").strip()
        parts = re.split(
            r"\s+(?:x|×|vs\.?|versus|contra|e)\s+|\s+-\s+",
            cleaned,
            flags=re.IGNORECASE,
        )
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1]
        if len(parts) == 1:
            return parts[0], None
        return "Argentina", "France"

    @classmethod
    def _team_matches_target(cls, search_norm: str, catalog_team_name: str) -> bool:
        if not search_norm or not catalog_team_name:
            return False
        cat_norm = cls._strip_accents_and_lower(catalog_team_name)
        if search_norm in cat_norm or cat_norm in search_norm:
            return True
        search_tokens = [t for t in search_norm.split() if len(t) >= 4]
        for tok in search_tokens:
            if tok in cat_norm:
                return True
        return False

    def resolve_user_match_input(self, user_input: str) -> Dict[str, Any]:
        text = (user_input or "").strip()
        if not text:
            text = "Argentina x França"

        id_match = re.search(r"\b(\d{6,8})\b", text)
        if id_match:
            candidate_id = int(id_match.group(1))
            try:
                df_ev = self.ingest_match_events(candidate_id)
                if not df_ev.empty:
                    teams = df_ev["team_name"].dropna().unique().tolist()
                    h_team = teams[0] if len(teams) > 0 else "Home"
                    a_team = teams[1] if len(teams) > 1 else "Away"
                    return {
                        "status": "FOUND_REAL",
                        "is_simulation": False,
                        "match_id": candidate_id,
                        "home_team": h_team,
                        "away_team": a_team,
                        "search_similarity_pct": 100.0,
                        "candidate_matches": [],
                        "user_message": f"✅ Partida real encontrada por ID exato: **{h_team} vs {a_team}** (Match ID `{candidate_id}`).",
                    }
            except Exception:
                pass

        raw_t1, raw_t2 = self._extract_teams_from_text(text)
        norm_t1 = self._normalize_team_token(raw_t1)
        norm_t2 = self._normalize_team_token(raw_t2) if raw_t2 else None

        catalog_df = self.ensure_rich_catalog_in_db()
        catalog_records = self.CURATED_OPEN_MATCHES + catalog_df.to_dict(orient="records")

        seen_ids = set()
        unique_records = []
        for r in catalog_records:
            mid = int(r["match_id"])
            if mid not in seen_ids:
                seen_ids.add(mid)
                unique_records.append(r)

        matched_candidates: List[Dict[str, Any]] = []
        similarity_score_pct = 98.0

        for rec in unique_records:
            h_name = str(rec.get("home_team_name", ""))
            a_name = str(rec.get("away_team_name", ""))

            if norm_t2:
                is_match = (
                    self._team_matches_target(norm_t1, h_name)
                    and self._team_matches_target(norm_t2, a_name)
                ) or (
                    self._team_matches_target(norm_t1, a_name)
                    and self._team_matches_target(norm_t2, h_name)
                )
            else:
                is_match = self._team_matches_target(norm_t1, h_name) or self._team_matches_target(norm_t1, a_name)

            if is_match:
                matched_candidates.append(rec)

        if not matched_candidates:
            search_query_norm = f"{norm_t1} {norm_t2 or ''}".strip()
            record_descriptions = [
                f"{r.get('home_team_name', '')} {r.get('away_team_name', '')} {r.get('competition_name', '')}"
                for r in unique_records
            ]
            sim_hits = TacticalNLPInterpreter.semantic_entity_match(
                search_query_norm, record_descriptions, threshold=0.42
            )
            if sim_hits:
                desc_to_rec = dict(zip(record_descriptions, unique_records))
                for hit_desc, sim_val in sim_hits[:8]:
                    matched_candidates.append(desc_to_rec[hit_desc])
                similarity_score_pct = round(sim_hits[0][1] * 100.0, 1)

        if matched_candidates:
            best_rec = matched_candidates[0]
            found_id = int(best_rec["match_id"])
            try:
                df_ev = self.ingest_match_events(found_id)
                comp_label = best_rec.get("competition_name", "StatsBomb")
                return {
                    "status": "FOUND_REAL",
                    "is_simulation": False,
                    "match_id": found_id,
                    "home_team": str(best_rec["home_team_name"]),
                    "away_team": str(best_rec["away_team_name"]),
                    "search_similarity_pct": similarity_score_pct,
                    "candidate_matches": matched_candidates[:12],
                    "user_message": f"✅ Partida real encontrada ({comp_label}): **{best_rec['home_team_name']} vs {best_rec['away_team_name']}** (Match ID `{found_id}`).",
                }
            except Exception:
                pass

        sim_home = raw_t1.title() if raw_t1 else "Equipe Mandante"
        sim_away = raw_t2.title() if raw_t2 else "Adversário"
        sim_id = 900000 + (abs(hash(f"{sim_home}_{sim_away}")) % 89999)
        return {
            "status": "NOT_FOUND_OFFER_SIMULATION",
            "is_simulation": True,
            "match_id": int(sim_id),
            "home_team": sim_home,
            "away_team": sim_away,
            "search_similarity_pct": 0.0,
            "candidate_matches": [],
            "user_message": f"⚠️ Partida (**{sim_home} vs {sim_away}**) não está disponível no StatsBomb. Deseja gerar a simulação tática avançada?",
        }

    def find_all_matches_for_team(
        self, team_query: str, max_matches: int = 5
    ) -> Tuple[str, Dict[int, pd.DataFrame], List[Dict[str, Any]]]:
        """
        Busca todas as partidas disponíveis de um mesmo time no catálogo multi-fontes
        (ex: 'Cruzeiro', 'Flamengo', 'Palmeiras', 'Argentina') para construir
        uma base histórica robusta sobre aquela equipe.
        """
        norm_q = self._normalize_team_token(team_query)
        catalog_df = self.ensure_rich_catalog_in_db()
        records = catalog_df.to_dict(orient="records")

        matched_meta: List[Dict[str, Any]] = []
        canonical_team_name: Optional[str] = None

        for rec in records:
            h_name = str(rec.get("home_team_name", ""))
            a_name = str(rec.get("away_team_name", ""))
            if self._team_matches_target(norm_q, h_name):
                canonical_team_name = canonical_team_name or h_name
                matched_meta.append(rec)
            elif self._team_matches_target(norm_q, a_name):
                canonical_team_name = canonical_team_name or a_name
                matched_meta.append(rec)

        matched_meta = matched_meta[:max_matches]
        events_map: Dict[int, pd.DataFrame] = {}

        for m in matched_meta:
            mid = int(m["match_id"])
            try:
                events_map[mid] = self.ingest_match_events(mid)
            except Exception:
                continue

        return (canonical_team_name or team_query.title(), events_map, matched_meta)

    def generate_tactical_simulation_match(
        self, home_team: str, away_team: str, match_id: int = 950001
    ) -> pd.DataFrame:
        cached = self.load_events_from_db(match_id)
        if not cached.empty:
            return cached

        rng = np.random.default_rng(abs(int(match_id)) % 100000)

        def _build_roster(club_name: str) -> List[Tuple[str, str, float, float]]:
            prefix = club_name.split()[0]
            return [
                (f"{prefix} Goleiro #1", "Goalkeeper", 10.0, 40.0),
                (f"{prefix} Lateral-Dir #2", "Right Back", 46.0, 70.0),
                (f"{prefix} Zagueiro-Dir #3", "Right Center Back", 34.0, 52.0),
                (f"{prefix} Zagueiro-Esq #4", "Left Center Back", 34.0, 28.0),
                (f"{prefix} Lateral-Esq #6", "Left Back", 48.0, 10.0),
                (f"{prefix} Volante-Pivô #5", "Center Defensive Midfield", 52.0, 40.0),
                (f"{prefix} Volante-Box #8", "Right Center Midfield", 64.0, 54.0),
                (f"{prefix} Meia-Armador #10", "Center Attacking Midfield", 78.0, 38.0),
                (f"{prefix} Ponta-Dir #7", "Right Wing", 86.0, 68.0),
                (f"{prefix} Ponta-Esq #11", "Left Wing", 88.0, 12.0),
                (f"{prefix} Centroavante #9", "Center Forward", 98.0, 40.0),
            ]

        rosters = {
            home_team: _build_roster(home_team),
            away_team: _build_roster(away_team),
        }

        events: List[Dict[str, Any]] = []
        ev_idx = 1
        poss_id = 1

        for period in [1, 2]:
            base_min = 0 if period == 1 else 45
            for p_step in range(42):
                poss_team = home_team if (p_step % 2 == 0) else away_team
                def_team = away_team if poss_team == home_team else home_team
                roster = rosters[poss_team]
                def_roster = rosters[def_team]

                minute = base_min + int((p_step / 42.0) * 44.0)
                second = int(rng.integers(0, 52))
                n_actions = int(rng.integers(4, 9))

                for step_i in range(n_actions):
                    weights = np.array(
                        [0.04, 0.09, 0.08, 0.08, 0.09, 0.22, 0.12, 0.14, 0.05, 0.05, 0.04]
                    )
                    p_idx = int(rng.choice(len(roster), p=weights))
                    r_idx = int(
                        rng.choice([i for i in range(len(roster)) if i != p_idx])
                    )

                    player_name, pos_name, bx, by = roster[p_idx]
                    recip_name, _, rbx, rby = roster[r_idx]

                    x0 = float(np.clip(rng.normal(bx, 8.0), 4.0, 115.0))
                    y0 = float(np.clip(rng.normal(by, 7.0), 2.0, 78.0))
                    x1 = float(np.clip(rng.normal(rbx + 6.0, 9.0), 6.0, 118.0))
                    y1 = float(np.clip(rng.normal(rby, 7.0), 2.0, 78.0))

                    is_last = step_i == (n_actions - 1)
                    under_press = 1 if (x0 > 65.0 and rng.random() < 0.45) else 0

                    if is_last and x0 >= 88.0 and rng.random() < 0.45:
                        ev_type = "Shot"
                        pass_outcome = None
                        xg_val = round(float(rng.uniform(0.06, 0.38)), 3)
                        shot_out = "Goal" if xg_val > 0.30 else "Saved"
                        end_x_val, end_y_val = 120.0, 40.0
                    elif is_last and rng.random() < 0.55:
                        ev_type = "Pass"
                        pass_outcome = "Incomplete"
                        xg_val = 0.0
                        shot_out = None
                        end_x_val, end_y_val = x1, y1
                    else:
                        ev_type = "Pass"
                        pass_outcome = None
                        xg_val = 0.0
                        shot_out = None
                        end_x_val, end_y_val = x1, y1

                    events.append(
                        {
                            "event_id": f"sim_{match_id}_{ev_idx}",
                            "match_id": int(match_id),
                            "index_num": ev_idx,
                            "period": period,
                            "timestamp": f"00:{minute:02d}:{min(second + step_i, 59):02d}.000",
                            "minute": minute,
                            "second": min(second + step_i, 59),
                            "possession": poss_id,
                            "possession_team_id": 1 if poss_team == home_team else 2,
                            "possession_team_name": poss_team,
                            "team_id": 1 if poss_team == home_team else 2,
                            "team_name": poss_team,
                            "player_id": p_idx + 1,
                            "player_name": player_name,
                            "position_name": pos_name,
                            "type_name": ev_type,
                            "play_pattern_name": "Regular Play",
                            "under_pressure": under_press,
                            "counterpress": 0,
                            "x": round(x0, 2),
                            "y": round(y0, 2),
                            "end_x": round(end_x_val, 2),
                            "end_y": round(end_y_val, 2),
                            "pass_length": round(
                                float(np.hypot(end_x_val - x0, end_y_val - y0)), 2
                            ),
                            "pass_angle": 0.0,
                            "pass_recipient_id": r_idx + 1 if ev_type == "Pass" else None,
                            "pass_recipient_name": recip_name
                            if (ev_type == "Pass" and pass_outcome is None)
                            else None,
                            "pass_height_name": "Ground Pass",
                            "pass_body_part": "Right Foot",
                            "pass_type_name": None,
                            "pass_outcome_name": pass_outcome,
                            "is_pass_Switch": 1 if abs(end_y_val - y0) >= 36.0 else 0,
                            "is_pass_cross": 1
                            if (x0 >= 95.0 and (y0 < 18.0 or y0 > 62.0))
                            else 0,
                            "is_pass_through_ball": 0,
                            "shot_statsbomb_xg": xg_val if ev_type == "Shot" else None,
                            "shot_outcome_name": shot_out,
                            "shot_body_part_name": "Right Foot"
                            if ev_type == "Shot"
                            else None,
                            "shot_type_name": "Open Play" if ev_type == "Shot" else None,
                            "duel_type_name": None,
                            "duel_outcome_name": None,
                            "interception_outcome_name": None,
                            "ball_recovery_failure": 0,
                            "foul_committed_card_name": None,
                            "substitution_replacement_name": None,
                            "tactics_formation": 433,
                        }
                    )
                    ev_idx += 1

                    if pass_outcome == "Incomplete":
                        def_p = def_roster[int(rng.integers(1, len(def_roster)))]
                        events.append(
                            {
                                "event_id": f"sim_{match_id}_{ev_idx}",
                                "match_id": int(match_id),
                                "index_num": ev_idx,
                                "period": period,
                                "timestamp": f"00:{minute:02d}:{min(second + step_i + 2, 59):02d}.000",
                                "minute": minute,
                                "second": min(second + step_i + 2, 59),
                                "possession": poss_id,
                                "possession_team_id": 1
                                if poss_team == home_team
                                else 2,
                                "possession_team_name": poss_team,
                                "team_id": 1 if def_team == home_team else 2,
                                "team_name": def_team,
                                "player_id": 99,
                                "player_name": def_p[0],
                                "position_name": def_p[1],
                                "type_name": "Ball Recovery",
                                "play_pattern_name": "Regular Play",
                                "under_pressure": 0,
                                "counterpress": 1,
                                "x": round(120.0 - end_x_val, 2),
                                "y": round(80.0 - end_y_val, 2),
                                "end_x": np.nan,
                                "end_y": np.nan,
                                "pass_length": None,
                                "pass_angle": None,
                                "pass_recipient_id": None,
                                "pass_recipient_name": None,
                                "pass_height_name": None,
                                "pass_body_part": None,
                                "pass_type_name": None,
                                "pass_outcome_name": None,
                                "is_pass_Switch": 0,
                                "is_pass_cross": 0,
                                "is_pass_through_ball": 0,
                                "shot_statsbomb_xg": None,
                                "shot_outcome_name": None,
                                "shot_body_part_name": None,
                                "shot_type_name": None,
                                "duel_type_name": None,
                                "duel_outcome_name": None,
                                "interception_outcome_name": "Won",
                                "ball_recovery_failure": 0,
                                "foul_committed_card_name": None,
                                "substitution_replacement_name": None,
                                "tactics_formation": 433,
                            }
                        )
                        ev_idx += 1

                poss_id += 1

        df_sim = pd.DataFrame(events)
        self._save_events_to_db(df_sim, match_id)
        return df_sim