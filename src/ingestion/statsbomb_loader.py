"""
Módulo de Ingestão e Persistência de Dados Esportivos (Camada 1)
Conecta ao StatsBomb Open Data, gerencia cache local em disco e persiste no SQLite.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests


class StatsBombDataLoader:
    """
    Gerencia o download, cache local, padronização e armazenamento em SQLite
    dos dados de eventos e partidas do StatsBomb Open Data e arquivos externos.
    """

    BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

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
        """Retorna uma conexão SQLite configurada."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_database(self) -> None:
        """Inicializa as tabelas do banco de dados a partir do arquivo schema.sql."""
        if not self.schema_path.exists():
            raise FileNotFoundError(
                f"Arquivo de schema SQL não encontrado em: {self.schema_path}"
            )
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        with self._get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    def _fetch_json_with_cache(self, relative_endpoint: str, cache_filename: str) -> List[Dict]:
        """
        Busca um arquivo JSON do repositório StatsBomb Open Data.
        Se já existir em data/raw/, carrega do disco instantaneamente (modo offline).
        """
        cache_file = self.raw_dir / cache_filename
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        url = f"{self.BASE_URL}/{relative_endpoint}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        return data

    def fetch_competitions(self) -> pd.DataFrame:
        """Retorna todas as competições e temporadas gratuitas disponíveis no StatsBomb."""
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
        """
        Baixa a lista de partidas de uma competição/temporada e salva os metadados no SQLite.
        Exemplo clássico: Copa do Mundo 2022 -> competition_id=43, season_id=106.
        Bayer Leverkusen Bundesliga 2023/2024 -> competition_id=9, season_id=281.
        """
        endpoint = f"matches/{competition_id}/{season_id}.json"
        cache_name = f"matches_{competition_id}_{season_id}.json"
        raw_matches = self._fetch_json_with_cache(endpoint, cache_name)

        parsed_rows = []
        for m in raw_matches:
            comp = m.get("competition", {})
            season = m.get("season", {})
            home = m.get("home_team", {})
            away = m.get("away_team", {})
            stadium = m.get("stadium", {}) or {}
            referee = m.get("referee", {}) or {}

            parsed_rows.append(
                {
                    "match_id": int(m["match_id"]),
                    "competition_id": int(comp.get("competition_id", competition_id)),
                    "competition_name": comp.get("competition_name", "Unknown"),
                    "season_id": int(season.get("season_id", season_id)),
                    "season_name": season.get("season_name", "Unknown"),
                    "match_date": m.get("match_date"),
                    "home_team_id": int(home.get("home_team_id", 0)),
                    "home_team_name": home.get("home_team_name", "Home"),
                    "away_team_id": int(away.get("away_team_id", 0)),
                    "away_team_name": away.get("away_team_name", "Away"),
                    "home_score": int(m.get("home_score", 0)),
                    "away_score": int(m.get("away_score", 0)),
                    "stadium_name": stadium.get("name"),
                    "referee_name": referee.get("name"),
                    "has_360_data": 0,
                }
            )

        df_matches = pd.DataFrame(parsed_rows)
        if not df_matches.empty:
            self._upsert_matches(df_matches)

        return df_matches.sort_values("match_date").reset_index(drop=True)

    def _upsert_matches(self, df_matches: pd.DataFrame) -> None:
        """Insere ou atualiza partidas na tabela matches do SQLite."""
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
                        int(row["competition_id"]),
                        str(row["competition_name"]),
                        int(row["season_id"]),
                        str(row["season_name"]),
                        str(row["match_date"]),
                        int(row["home_team_id"]),
                        str(row["home_team_name"]),
                        int(row["away_team_id"]),
                        str(row["away_team_name"]),
                        int(row["home_score"]),
                        int(row["away_score"]),
                        row["stadium_name"],
                        row["referee_name"],
                        int(row.get("has_360_data", 0)),
                    ),
                )
            conn.commit()

    def ingest_match_events(self, match_id: int, force_reload: bool = False) -> pd.DataFrame:
        """
        Extrai todos os eventos de uma partida (passes, chutes, conduções, pressão, tática),
        normaliza as coordenadas (x, y, end_x, end_y) e salva no banco SQLite.
        """
        if not force_reload:
            cached_db = self.load_events_from_db(match_id)
            if not cached_db.empty:
                return cached_db

        endpoint = f"events/{match_id}.json"
        cache_name = f"events_{match_id}.json"
        raw_events = self._fetch_json_with_cache(endpoint, cache_name)

        df_events = self._parse_raw_events(raw_events, match_id)
        self._save_events_to_db(df_events, match_id)
        return df_events

    def _parse_raw_events(self, raw_events: List[Dict], match_id: int) -> pd.DataFrame:
        """Converte a lista de dicionários JSON aninhados do StatsBomb em tabela relacional."""
        rows = []
        for ev in raw_events:
            loc = ev.get("location")
            x = float(loc[0]) if isinstance(loc, list) and len(loc) >= 2 else np.nan
            y = float(loc[1]) if isinstance(loc, list) and len(loc) >= 2 else np.nan

            end_x, end_y = np.nan, np.nan
            ev_type = ev.get("type", {}).get("name", "Unknown")

            # Extração de atributos de Passe
            pass_dict = ev.get("pass", {}) or {}
            if ev_type == "Pass" and "end_location" in pass_dict:
                end_loc = pass_dict["end_location"]
                if isinstance(end_loc, list) and len(end_loc) >= 2:
                    end_x, end_y = float(end_loc[0]), float(end_loc[1])

            # Extração de atributos de Condução (Carry)
            carry_dict = ev.get("carry", {}) or {}
            if ev_type == "Carry" and "end_location" in carry_dict:
                end_loc = carry_dict["end_location"]
                if isinstance(end_loc, list) and len(end_loc) >= 2:
                    end_x, end_y = float(end_loc[0]), float(end_loc[1])

            # Extração de atributos de Finalização (Shot)
            shot_dict = ev.get("shot", {}) or {}
            if ev_type == "Shot" and "end_location" in shot_dict:
                end_loc = shot_dict["end_location"]
                if isinstance(end_loc, list) and len(end_loc) >= 2:
                    end_x, end_y = float(end_loc[0]), float(end_loc[1])

            duel_dict = ev.get("duel", {}) or {}
            interception_dict = ev.get("interception", {}) or {}
            recovery_dict = ev.get("ball_recovery", {}) or {}
            foul_dict = ev.get("foul_committed", {}) or {}
            sub_dict = ev.get("substitution", {}) or {}
            tactics_dict = ev.get("tactics", {}) or {}

            rows.append(
                {
                    "event_id": str(ev.get("id")),
                    "match_id": int(match_id),
                    "index_num": int(ev.get("index", 0)),
                    "period": int(ev.get("period", 1)),
                    "timestamp": str(ev.get("timestamp", "00:00:00.000")),
                    "minute": int(ev.get("minute", 0)),
                    "second": int(ev.get("second", 0)),
                    "possession": int(ev.get("possession", 0)),
                    "possession_team_id": ev.get("possession_team", {}).get("id"),
                    "possession_team_name": ev.get("possession_team", {}).get("name"),
                    "team_id": int(ev.get("team", {}).get("id", 0)),
                    "team_name": str(ev.get("team", {}).get("name", "Unknown")),
                    "player_id": ev.get("player", {}).get("id"),
                    "player_name": ev.get("player", {}).get("name"),
                    "position_name": ev.get("position", {}).get("name"),
                    "type_name": ev_type,
                    "play_pattern_name": ev.get("play_pattern", {}).get("name"),
                    "under_pressure": 1 if ev.get("under_pressure") else 0,
                    "counterpress": 1 if ev.get("counterpress") else 0,
                    "x": x,
                    "y": y,
                    "end_x": end_x,
                    "end_y": end_y,
                    "pass_length": pass_dict.get("length"),
                    "pass_angle": pass_dict.get("angle"),
                    "pass_recipient_id": pass_dict.get("recipient", {}).get("id"),
                    "pass_recipient_name": pass_dict.get("recipient", {}).get("name"),
                    "pass_height_name": pass_dict.get("height", {}).get("name"),
                    "pass_body_part": pass_dict.get("body_part", {}).get("name"),
                    "pass_type_name": pass_dict.get("type", {}).get("name"),
                    "pass_outcome_name": pass_dict.get("outcome", {}).get("name"),
                    "is_pass_Switch": 1 if pass_dict.get("switch") else 0,
                    "is_pass_cross": 1 if pass_dict.get("cross") else 0,
                    "is_pass_through_ball": 1 if pass_dict.get("through_ball") else 0,
                    "shot_statsbomb_xg": shot_dict.get("statsbomb_xg"),
                    "shot_outcome_name": shot_dict.get("outcome", {}).get("name"),
                    "shot_body_part_name": shot_dict.get("body_part", {}).get("name"),
                    "shot_type_name": shot_dict.get("type", {}).get("name"),
                    "duel_type_name": duel_dict.get("type", {}).get("name"),
                    "duel_outcome_name": duel_dict.get("outcome", {}).get("name"),
                    "interception_outcome_name": interception_dict.get("outcome", {}).get("name"),
                    "ball_recovery_failure": 1 if recovery_dict.get("recovery_failure") else 0,
                    "foul_committed_card_name": foul_dict.get("card", {}).get("name"),
                    "substitution_replacement_name": sub_dict.get("replacement", {}).get("name"),
                    "tactics_formation": tactics_dict.get("formation"),
                }
            )

        return pd.DataFrame(rows)

    def _save_events_to_db(self, df_events: pd.DataFrame, match_id: int) -> None:
        """Persiste o DataFrame de eventos no SQLite de forma transacional."""
        with self._get_connection() as conn:
            # Garante que a partida exista na tabela pai caso o usuário tenha chamado direto pelo match_id
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

    def load_events_from_db(self, match_id: int) -> pd.DataFrame:
        """Carrega os eventos de uma partida diretamente do banco SQLite."""
        with self._get_connection() as conn:
            query = "SELECT * FROM events WHERE match_id = ? ORDER BY index_num ASC"
            return pd.read_sql_query(query, conn, params=(int(match_id),))

    def load_multiple_matches_events(self, match_ids: List[int]) -> pd.DataFrame:
        """Carrega eventos de várias partidas para análise longitudinal de tendências."""
        if not match_ids:
            return pd.DataFrame()
        placeholders = ",".join(["?"] * len(match_ids))
        with self._get_connection() as conn:
            query = f"SELECT * FROM events WHERE match_id IN ({placeholders}) ORDER BY match_id, index_num ASC"
            return pd.read_sql_query(query, conn, params=[int(m) for m in match_ids])

    def ingest_custom_csv_or_json(self, file_path: str, match_id: int = 999001) -> pd.DataFrame:
        """
        Permite importar arquivos CSV ou JSON externos fornecidos pelo usuário.
        Valida colunas mínimas (team_name, type_name, x, y) e salva no banco SQLite.
        """
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


if __name__ == "__main__":
    print("=" * 72)
    print("TACTICAL INTELLIGENCE LAB - TESTE DE INGESTÃO E BANCO SQLITE (DIA 1)")
    print("=" * 72)

    loader = StatsBombDataLoader()

    # 1. Busca a Copa do Mundo FIFA 2022 (competition_id=43, season_id=106)
    print("\n[1/3] Buscando catálogo de partidas da Copa do Mundo 2022 (StatsBomb Open Data)...")
    matches_df = loader.fetch_matches(competition_id=43, season_id=106)
    print(f"      -> {len(matches_df)} partidas catalogadas e salvas no SQLite com sucesso!")

    # 2. Seleciona a Final (Argentina vs França - match_id = 3869685)
    target_match_id = 3869685
    print(f"\n[2/3] Baixando e processando eventos espaciais da partida ID {target_match_id}...")
    events_df = loader.ingest_match_events(match_id=target_match_id)

    # 3. Exibe resumo de auditoria real extraído do banco
    print(f"\n[3/3] Auditoria dos Dados Persistidos no SQLite:")
    print(f"      -> Total de eventos registrados: {len(events_df)}")
    print(f"      -> Equipes identificadas: {events_df['team_name'].unique().tolist()}")

    passes_df = events_df[events_df["type_name"] == "Pass"]
    shots_df = events_df[events_df["type_name"] == "Shot"]
    press_df = events_df[events_df["under_pressure"] == 1]

    print(f"      -> Total de Passes com coordenadas (x, y -> end_x, end_y): {len(passes_df)}")
    print(f"      -> Total de Finalizações (Shots) com xG: {len(shots_df)}")
    print(f"      -> Ações realizadas sob pressão adversária: {len(press_df)}")
    print("\n[OK] Dia 1 concluído com sucesso! Banco SQLite pronto em: database/tactical_lab.db")