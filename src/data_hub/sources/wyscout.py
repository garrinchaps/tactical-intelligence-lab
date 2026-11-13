"""
Wyscout Public Dataset (Pappalardo et al., 2019 — CC BY 4.0).

1.941 partidas com eventos granulares: Premier League, La Liga, Serie A, Bundesliga e
Ligue 1 (2017/18), Copa do Mundo 2018 e Euro 2016. Lido do repositório processado
koenvo/wyscout-soccer-match-event-dataset (formato Wyscout v2) e convertido para o
esquema interno de eventos (coordenadas StatsBomb 120 x 80).

Diferenças importantes em relação ao StatsBomb (documentadas para a análise):
* não há eventos de "Pressure" nem a marcação under_pressure → métricas de pressão ficam vazias;
* não há xG → usamos o xG estimado do laboratório (src/data_hub/xg.py);
* a posição exata do atleta não existe (só GK/DF/MD/FW) → posição inferida pela localização média;
* o recebedor do passe é inferido pelo evento seguinte do mesmo time (passe certo).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.http import PoliteHttpClient
from src.data_hub.registry import DataLevel, to_internal_id
from src.data_hub.xg import estimate_xg

RAW_BASE = "https://raw.githubusercontent.com/koenvo/wyscout-soccer-match-event-dataset/main/processed-v2"

COMPETITIONS = {
    "matches_England.json": ("Premier League", "2017/2018", "England", 9001),
    "matches_Spain.json": ("La Liga", "2017/2018", "Spain", 9002),
    "matches_Italy.json": ("Serie A", "2017/2018", "Italy", 9003),
    "matches_Germany.json": ("1. Bundesliga", "2017/2018", "Germany", 9004),
    "matches_France.json": ("Ligue 1", "2017/2018", "France", 9005),
    "matches_World_Cup.json": ("FIFA World Cup", "2018", "International", 9006),
    "matches_European_Championship.json": ("UEFA Euro", "2016", "Europe", 9007),
}

PERIODS = {"1H": (1, 0), "2H": (2, 45), "E1": (3, 90), "E2": (4, 105), "P": (5, 120)}

_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")


def fix_text(s: Any) -> str:
    """Decodifica sequências '\\u00e9' que vêm literais no dataset."""
    if s is None:
        return ""
    return _UESC.sub(lambda m: chr(int(m.group(1), 16)), str(s)).strip()


def _tags(ev: Dict[str, Any]) -> set:
    return {t.get("id") for t in ev.get("tags", []) or []}


def _xy(pos: List[Dict[str, Any]], i: int):
    if not pos or len(pos) <= i:
        return np.nan, np.nan
    p = pos[i]
    if p.get("x") is None or p.get("y") is None:
        return np.nan, np.nan
    return float(p["x"]) * 1.2, float(p["y"]) * 0.8


class WyscoutConverter:
    """Converte o JSON de uma partida Wyscout v2 para o DataFrame interno de eventos."""

    PASS_TYPES = {"Corner": "Corner", "Free Kick": "Free Kick", "Free kick cross": "Free Kick",
                  "Throw in": "Throw-in", "Goal kick": "Goal Kick"}
    PATTERNS = {"Corner": "From Corner", "Free Kick": "From Free Kick", "Free kick cross": "From Free Kick",
                "Throw in": "From Throw In", "Goal kick": "From Goal Kick"}

    @classmethod
    def convert(cls, payload: Dict[str, Any], internal_match_id: int) -> pd.DataFrame:
        teams = {int(k): fix_text(v["team"]["name"]) for k, v in payload.get("teams", {}).items()}
        players: Dict[int, Dict[str, Any]] = {}
        for _tid, plist in payload.get("players", {}).items():
            for item in plist:
                p = item.get("player", item)
                short = fix_text(p.get("shortName"))
                first, last = fix_text(p.get("firstName")).split(), fix_text(p.get("lastName")).split()
                if short and "." not in short:
                    name = short  # nome de jogo (ex.: "David Silva", "Neymar")
                elif first and last:
                    particles = {"de", "da", "do", "dos", "das", "di", "van", "von", "der", "den", "le", "la", "del", "ter"}
                    if last[0].lower() in particles:
                        # "Kevin De Bruyne", "Rajiv van La Parra": sobrenome composto fica inteiro
                        name = f"{first[0]} {' '.join(last)}"
                    else:
                        name = f"{first[0]} {last[0]}"  # "Sergio Leonel Agüero del Castillo" -> "Sergio Agüero"
                else:
                    name = short or " ".join(first + last)
                players[int(p["wyId"])] = {"name": name, "role": (p.get("role") or {}).get("code2", "")}

        events = sorted(
            payload.get("events", []),
            key=lambda e: (PERIODS.get(e.get("matchPeriod"), (9, 0))[0], float(e.get("eventSec", 0))),
        )
        rows: List[Dict[str, Any]] = []
        controlling = {"Pass", "Shot", "Carry", "Ball Receipt*", "Miscontrol"}
        poss_id, poss_team, poss_pattern, cur_period = 0, None, "Regular Play", None

        for idx, ev in enumerate(events):
            period, offset = PERIODS.get(ev.get("matchPeriod"), (1, 0))
            if period == 5:
                continue  # disputa de pênaltis fica fora da análise tática
            sec = float(ev.get("eventSec", 0.0))
            team = teams.get(int(ev.get("teamId", 0)), str(ev.get("teamId")))
            pid = int(ev.get("playerId") or 0)
            pinfo = players.get(pid, {"name": "", "role": ""})
            tags = _tags(ev)
            name, sub = ev.get("eventName", ""), ev.get("subEventName", "")
            x, y = _xy(ev.get("positions"), 0)
            ex, ey = _xy(ev.get("positions"), 1)

            row: Dict[str, Any] = {
                "event_id": f"wy_{ev.get('id', idx)}",
                "match_id": int(internal_match_id),
                "index_num": idx + 1,
                "period": period,
                "timestamp": f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{sec % 60:06.3f}",
                "minute": int(sec // 60) + offset,
                "second": int(sec % 60),
                "team_id": int(ev.get("teamId", 0)),
                "team_name": team,
                "player_id": pid or None,
                "player_name": pinfo["name"] or None,
                "position_name": pinfo["role"],  # substituído pela posição inferida depois
                "under_pressure": 0,
                "counterpress": 0,
                "x": x, "y": y, "end_x": np.nan, "end_y": np.nan,
                "pass_outcome_name": None,
                "play_pattern_name": "Regular Play",
            }
            accurate = 1801 in tags
            inaccurate = 1802 in tags

            if name == "Pass" or (name == "Free Kick" and sub in cls.PASS_TYPES) or \
                    (name == "Free Kick" and sub == "Free Kick"):
                row.update(type_name="Pass", end_x=ex, end_y=ey,
                           pass_type_name=cls.PASS_TYPES.get(sub),
                           pass_outcome_name="Incomplete" if inaccurate else None,
                           is_pass_cross=int(sub in ("Cross", "Free kick cross")),
                           is_pass_through_ball=int(sub == "Smart pass" or 901 in tags),
                           pass_height_name="High Pass" if sub in ("High pass", "Launch", "Cross") else "Ground Pass",
                           pass_body_part="Head" if sub == "Head pass" else None)
                if not np.isnan(x) and not np.isnan(ex):
                    row["pass_length"] = float(np.hypot(ex - x, ey - y))
                    row["pass_angle"] = float(np.arctan2(ey - y, ex - x))
                    row["is_pass_Switch"] = int(abs(ey - y) >= 40)
            elif name == "Shot" or (name == "Free Kick" and sub in ("Free kick shot", "Penalty")):
                outcome = "Goal" if 101 in tags else ("Blocked" if 2101 in tags else ("Saved" if accurate else "Off T"))
                body = "Head" if 403 in tags else ("Left Foot" if 401 in tags else ("Right Foot" if 402 in tags else None))
                is_pen = sub == "Penalty"
                row.update(type_name="Shot", end_x=120.0, end_y=40.0, shot_outcome_name=outcome,
                           shot_body_part_name=body,
                           shot_type_name="Penalty" if is_pen else ("Free Kick" if name == "Free Kick" else "Open Play"),
                           shot_statsbomb_xg=estimate_xg(x, y, is_header=(body == "Head"), is_penalty=is_pen))
            elif name == "Duel":
                won = 703 in tags
                if sub == "Ground attacking duel":
                    row.update(type_name="Dribble", duel_outcome_name="Won" if won else "Lost")
                else:
                    row.update(type_name="Duel",
                               duel_type_name={"Air duel": "Aerial", "Ground defending duel": "Tackle",
                                               "Ground loose ball duel": "Loose Ball"}.get(sub, sub),
                               duel_outcome_name="Won" if won else ("Lost" if 701 in tags else "Neutral"))
            elif name == "Others on the ball":
                if 1401 in tags:
                    row.update(type_name="Interception", interception_outcome_name="Won")
                elif sub == "Clearance":
                    row.update(type_name="Clearance")
                elif sub == "Acceleration":
                    row.update(type_name="Carry", end_x=ex, end_y=ey)
                else:
                    row.update(type_name="Ball Receipt*")
            elif name == "Foul":
                card = "Red Card" if 1701 in tags else ("Second Yellow" if 1703 in tags else
                                                         ("Yellow Card" if 1702 in tags else None))
                row.update(type_name="Foul Committed", foul_committed_card_name=card)
            elif name in ("Save attempt", "Goalkeeper leaving line"):
                row.update(type_name="Goal Keeper")
            elif name == "Offside":
                row.update(type_name="Offside")
            else:
                continue

            # gol contra (tag 102): registrado como no StatsBomb
            if 102 in tags:
                rows.append({**row, "event_id": row["event_id"] + "_og", "type_name": "Own Goal Against",
                             "end_x": np.nan, "end_y": np.nan, "pass_outcome_name": None})

            # interceptação marcada em passe → evento de interceptação real separado
            if row["type_name"] == "Pass" and 1401 in tags:
                rows.append({**row, "event_id": row["event_id"] + "_int", "type_name": "Interception",
                             "interception_outcome_name": "Won", "end_x": np.nan, "end_y": np.nan,
                             "pass_outcome_name": None, "pass_type_name": None})

            # posse de bola: muda quando outro time controla a bola
            if cur_period != period:
                cur_period, poss_team = period, None
            if row["type_name"] in controlling and team != poss_team:
                poss_id += 1
                poss_team = team
                poss_pattern = cls.PATTERNS.get(sub, "From Counter" if 1901 in tags else "Regular Play")
            row["possession"] = max(poss_id, 1)
            row["possession_team_name"] = poss_team or team
            row["play_pattern_name"] = poss_pattern
            rows.append(row)

        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["index_num"] = range(1, len(df) + 1)
        cls._infer_recipients(df)
        cls._infer_positions(df, players)
        return df

    @staticmethod
    def _infer_recipients(df: pd.DataFrame) -> None:
        recips: List[Optional[str]] = [None] * len(df)
        names = df["player_name"].tolist()
        teams = df["team_name"].tolist()
        types = df["type_name"].tolist()
        outcomes = df.get("pass_outcome_name", pd.Series([None] * len(df))).tolist()
        periods = df["period"].tolist()
        for i in range(len(df)):
            if types[i] != "Pass" or not pd.isna(outcomes[i]):
                continue
            for j in range(i + 1, min(i + 4, len(df))):
                if periods[j] != periods[i]:
                    break
                if teams[j] == teams[i] and isinstance(names[j], str) and names[j] and names[j] != names[i]:
                    recips[i] = names[j]
                    break
                if teams[j] != teams[i] and types[j] not in ("Duel", "Foul Committed"):
                    break
        df["pass_recipient_name"] = recips

    @staticmethod
    def _infer_positions(df: pd.DataFrame, players: Dict[int, Dict[str, Any]]) -> None:
        """
        Posição aproximada a partir do papel (GK/DF/MD/FW) e da localização média.
        Defensores: ordenados pela posição lateral média dentro do próprio time
        (pontas da linha = laterais, miolo = zagueiros). Meio/ataque: "aberto" só nos
        corredores laterais do laboratório (y < 18 ou y > 62).
        """
        roles = {v["name"]: v["role"] for v in players.values()}
        located = df.dropna(subset=["x", "y"])
        loc = located.groupby("player_name")[["x", "y"]].mean()
        counts = located.groupby("player_name").size()
        team_of = df.dropna(subset=["player_name"]).groupby("player_name")["team_name"].first()
        result: Dict[str, str] = {}

        for team in df["team_name"].dropna().unique():
            defs = [n for n in loc.index if roles.get(n) == "DF" and team_of.get(n) == team and counts.get(n, 0) >= 8]
            defs.sort(key=lambda n: loc.loc[n, "y"])
            if len(defs) >= 4:
                result[defs[0]] = "Left Back"
                result[defs[-1]] = "Right Back"
                middle = defs[1:-1]
                for k, n in enumerate(middle):
                    result[n] = "Left Center Back" if k < len(middle) / 2 else "Right Center Back"
            elif defs:
                labels = {1: ["Center Back"], 2: ["Left Center Back", "Right Center Back"],
                          3: ["Left Center Back", "Center Back", "Right Center Back"]}[len(defs)]
                for n, lab in zip(defs, labels):
                    result[n] = lab

        def infer(name: Any) -> str:
            role = roles.get(name, "")
            if role == "GK":
                return "Goalkeeper"
            if name in result:
                return result[name]
            if name not in loc.index:
                return {"DF": "Center Back", "MD": "Center Midfield", "FW": "Center Forward"}.get(role, "Unknown")
            ax, ay = loc.loc[name, "x"], loc.loc[name, "y"]
            wide_left, wide_right = ay < 18, ay > 62
            if role == "DF":
                if wide_left or wide_right:
                    return "Left Back" if wide_left else "Right Back"
                return "Left Center Back" if ay < 40 else "Right Center Back"
            if role == "MD":
                if (wide_left or wide_right) and ax >= 60:
                    return "Left Wing" if wide_left else "Right Wing"
                if wide_left or wide_right:
                    return "Left Midfield" if wide_left else "Right Midfield"
                if ax < 50:
                    return "Center Defensive Midfield"
                if ax >= 68:
                    return "Center Attacking Midfield"
                return "Left Center Midfield" if ay < 40 else "Right Center Midfield"
            if role == "FW":
                if wide_left or wide_right:
                    return "Left Wing" if wide_left else "Right Wing"
                return "Center Forward"
            return "Unknown"

        df["position_name"] = df["player_name"].apply(infer)


class WyscoutProvider:
    source = "wyscout"

    def __init__(self, db: DataHubDB, client: Optional[PoliteHttpClient] = None):
        self.db = db
        self.client = client or PoliteHttpClient("wyscout", db=db, min_interval_s=0.3)

    @staticmethod
    def parse_index(markdown: str) -> List[Dict[str, Any]]:
        """Lê a tabela do README (ID | Label | Data | Arquivo) e monta o catálogo."""
        records: List[Dict[str, Any]] = []
        rx = re.compile(r"^\|\[(\d+)\]\([^)]*\)\|(.+?)\|(.+?)\|(\S+?)\|\s*$")
        for line in markdown.splitlines():
            m = rx.match(line.strip())
            if not m:
                continue
            wy_id, label, date_txt, src_file = m.groups()
            comp = COMPETITIONS.get(src_file.strip())
            if not comp:
                continue
            lm = re.match(r"(.+?) - (.+?), (\d+) - (\d+)", fix_text(label))
            if not lm:
                continue
            home, away, hs, as_ = lm.groups()
            try:
                date_iso = datetime.strptime(date_txt.split(" at ")[0].strip(), "%B %d, %Y").strftime("%Y-%m-%d")
            except ValueError:
                date_iso = ""
            records.append({
                "match_id": to_internal_id("wyscout", int(wy_id)),
                "source_match_id": wy_id,
                "competition_id": comp[3],
                "competition_name": comp[0],
                "season_id": int(comp[1][:4]),
                "season_name": comp[1],
                "country_name": comp[2],
                "match_date": date_iso,
                "home_team_name": home.strip(),
                "away_team_name": away.strip(),
                "home_score": int(hs),
                "away_score": int(as_),
                "data_source": "wyscout",
                "data_level": DataLevel.EVENTS,
                "extra": {"penalties": "(P)" in label},
            })
        return records

    def sync_catalog(self) -> Dict[str, int]:
        """O dataset é estático: o índice é baixado uma vez e guardado em cache permanente."""
        markdown = self.fetch_index()
        return self.db.upsert_matches(self.parse_index(markdown))

    def fetch_index(self) -> str:
        cache = self.client.cache_dir / "index_README.md"
        if cache.exists():
            return cache.read_text(encoding="utf-8")
        import requests

        resp = requests.get(f"{RAW_BASE}/README.md", headers=self.client.headers, timeout=30)
        resp.raise_for_status()
        cache.write_text(resp.text, encoding="utf-8")
        return resp.text

    def load_events(self, match_id: int) -> pd.DataFrame:
        wy_id = int(match_id) - 10_000_000
        payload = self.client.get_json(f"{RAW_BASE}/files/{wy_id}.json", max_age_s=None)
        df = WyscoutConverter.convert(payload, int(match_id))
        if not df.empty:
            if self.db.get_match(match_id) is None:
                teams = df["team_name"].dropna().unique().tolist()
                self.db.upsert_matches([{
                    "match_id": int(match_id), "data_source": "wyscout", "data_level": DataLevel.EVENTS,
                    "competition_name": "Wyscout Public Dataset",
                    "home_team_name": teams[0] if teams else "", "away_team_name": teams[1] if len(teams) > 1 else "",
                }])
            self.db.save_events(match_id, df)
        return df
