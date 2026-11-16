"""
OpenPlay (github.com/nlbair/openplay, Noah Bair) — eventos de futebol masculino COM coordenadas e xG em cada chute,
grandes ligas europeias e copas da UEFA, de 2014/15 em diante (dezenas de milhares de jogos).

Como entra no app
  * `python -m src.data_hub.sync --only openplay` BAIXA SOZINHO a release de dados mais nova (API pública do GitHub,
    sem conta) para data/raw/openplay/ (ou OPENPLAY_PATH), retomando de onde parou se a conexão cair.
  * `python -m src.data_hub.sync --only openplay` cataloga os jogos (nível EVENTOS quando há a tabela de eventos).
  * Os lances de um jogo só são lidos quando ele é aberto (filtro direto no parquet) e ficam em cache no banco.
  * `python -m src.data_hub.sources.openplay --inspecionar` mostra as tabelas e colunas encontradas.

Os nomes de coluna são reconhecidos por sinônimos (match_id/game_id, type/event_type, x/start_x…); coordenadas
na escala 0–100 (Opta/WhoScored) são convertidas para 120×80 (escala StatsBomb usada no app).

Licença: o repositório declara CC BY 4.0 com atribuição a Noah Bair / OpenPlay, mas informa que os eventos vêm
de WhoScored/Opta (Stats Perform) e que pode haver pedido de retirada pelos donos. Uso pessoal/acadêmico.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.data_hub.registry import DataLevel, to_internal_id
from src.data_hub.tabular import (describe, find_col, normalize_columns, parse_date, stable_id, stat, to_int,
                                  to_number)

LICENSE = "OpenPlay (Noah Bair) — CC BY 4.0 declarada; eventos de origem WhoScored/Opta; uso pessoal/acadêmico"
DEFAULT_DIR = Path("data/raw/openplay")

# tipo de evento (WhoScored/Opta e variações) → tipo StatsBomb usado pelo app.
# Faltas, toques e substituições são tratados à parte em convert_events (dependem do desfecho/qualificadores).
TYPE_MAP = {
    "pass": "Pass", "offsidepass": "Pass", "shot": "Shot", "missedshots": "Shot", "savedshot": "Shot", "goal": "Shot",
    "shotonpost": "Shot", "blockedshot": "Shot", "attemptsaved": "Shot", "takeon": "Dribble", "take_on": "Dribble",
    "dribble": "Dribble", "carry": "Carry", "ballrecovery": "Ball Recovery", "ball_recovery": "Ball Recovery",
    "recovery": "Ball Recovery", "interception": "Interception", "tackle": "Duel", "aerial": "Duel",
    "challenge": "Duel", "clearance": "Clearance", "dispossessed": "Dispossessed", "pressure": "Pressure",
    "save": "Goal Keeper", "keeperpickup": "Goal Keeper", "claim": "Goal Keeper", "punch": "Goal Keeper",
    "keepersweeper": "Goal Keeper", "smother": "Goal Keeper", "blockedpass": "Block", "error": "Error",
    "shieldballopp": "Shield", "foul": "Foul", "balltouch": "BallTouch", "card": "Card",
    "substitutionoff": "SubOff", "substitutionon": "SubOn", "substitution": "SubOff",
}
SHOT_OUTCOME = {"goal": "Goal", "savedshot": "Saved", "attemptsaved": "Saved", "missedshots": "Off T",
                "shotonpost": "Post", "blockedshot": "Blocked"}
DUEL_TYPE = {"tackle": "Tackle", "aerial": "Aerial Lost", "challenge": "Tackle"}
PERIOD = {"firsthalf": 1, "secondhalf": 2, "firstperiodofextratime": 3, "secondperiodofextratime": 4,
          "penaltyshootout": 5}
SKIP_PERIODS = {"prematch", "postgame", "pregame", "postextratime"}
CONTROL = {"Pass", "Carry", "Dribble", "Shot", "Ball Recovery", "Interception"}
CONVERTER_VERSION = "2"     # muda quando a conversão de eventos melhora: os lances em cache são refeitos

# estatística por time no arquivo team_match_stats → chave usada no app (src/data_hub/boxscore.STAT_LABELS)
TEAM_STATS = [
    ("possession_pct", "possession_pct", ("possession",)), ("xg", "xg", ("expected_goals",)),
    ("shots", "shots_total", ("shots_total",)), ("shots_on_target", "shots_on_target", ()),
    ("shots_off_target", "shots_off_target", ()), ("shots_blocked", "shots_blocked", ()),
    ("shots_inside_box", "shots_inside_box", ()), ("shots_outside_box", "shots_outside_box", ()),
    ("big_chances", "big_chances", ()), ("key_passes", "key_passes", ()),
    ("passes", "passes_total", ("passes_total",)), ("passes_completed", "passes_accurate", ("passes_accurate",)),
    ("pass_pct", "pass_accuracy_pct", ("pass_accuracy",)), ("crosses", "crosses_total", ()),
    ("crosses_completed", "crosses_accurate", ()), ("long_balls", "long_balls_total", ()),
    ("long_balls_completed", "long_balls_accurate", ()), ("corners_taken", "corners", ("corners",)),
    ("dribbles_completed", "dribbles_completed", ()), ("aerials_won", "aerials_won", ()),
    ("tackles", "tackles_total", ()), ("tackles_won", "tackles_won", ()), ("interceptions", "interceptions", ()),
    ("clearances", "clearances", ()), ("saves", "saves", ()), ("offsides", "offsides", ()),
    ("fouls_committed", "fouls", ("fouls",)), ("yellow_cards", "yellow_cards", ()),
    ("red_cards", "red_cards", ("straight_red_cards",)),
]
PCT_KEYS = {"possession_pct", "pass_accuracy_pct"}


TOURNAMENTS = {"wc", "euro", "copa", "afcon", "cwc"}            # códigos de torneio: a temporada é o ano


def season_label(v: Any, comp: Any = "") -> str:
    """Código do arquivo → nome usado no resto da base: 1415 → 2014/2015 (ligas); afcon 2021 → 2021 (torneio)."""
    txt = str(v if v is not None else "").strip()
    if txt.endswith(".0"):
        txt = txt[:-2]
    if str(comp or "").lower() in TOURNAMENTS or not re.fullmatch(r"\d{4}", txt):
        return txt
    a, b = int(txt[:2]), int(txt[2:])
    return f"20{txt[:2]}/20{txt[2:]}" if (a + 1) % 100 == b else txt


def _labels() -> Dict[str, str]:
    try:
        from src.data_hub.boxscore import STAT_LABELS

        return {k: v[0] for k, v in STAT_LABELS.items()}
    except Exception:
        return {}


def _pattern(r: Dict[str, Any], col: Optional[str], q) -> str:
    """Tipo de jogada no padrão StatsBomb (Regular Play, From Corner, From Free Kick, From Throw In, From Counter)."""
    v = _key(r.get(col)) if col else ""
    if q(r, "q_fromcorner") or "corner" in v:
        return "From Corner"
    if q(r, "q_fastbreak") or "fast" in v or "counter" in v:
        return "From Counter"
    if q(r, "q_throwinsetpiece") or "throw" in v:
        return "From Throw In"
    if q(r, "q_penalty") or "penalty" in v:
        return "Other"
    if q(r, "q_setpiece") or q(r, "q_directfreekick") or "set" in v or "free" in v:
        return "From Free Kick"
    return "Regular Play"


def _key(s: Any) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum() or ch == "_")


class OpenPlayProvider:
    source = "openplay"

    def __init__(self, db=None, path: Optional[str] = None):
        self.db = db
        self.path = Path(path or os.getenv("OPENPLAY_PATH", "") or DEFAULT_DIR)
        self._catalog_map: Optional[Dict[str, tuple[str, str]]] = None

    # ---------------------------------------------------------------- arquivos
    @staticmethod
    def _kind(p: Path) -> Optional[str]:
        n = p.stem.lower()
        return ("player_match_stats" if "player" in n and "stat" in n else
                "team_match_stats" if "team" in n and "stat" in n else
                "events" if "event" in n else "shots" if "shot" in n else
                "matches" if ("match" in n or "game" in n or "fixture" in n) else None)

    def all_files(self) -> Dict[str, List[Path]]:
        """Todos os arquivos por tipo (os dados podem vir divididos por liga/temporada)."""
        out: Dict[str, List[Path]] = {}
        if not self.path.exists():
            return out
        for p in sorted(self.path.rglob("*")):
            if p.suffix.lower() in (".parquet", ".csv") and not p.name.endswith(".part"):
                k = self._kind(p)
                if k:
                    out.setdefault(k, []).append(p)
        return out

    def files(self) -> Dict[str, Path]:
        """Primeiro arquivo de cada tipo: matches / events / team_match_stats / shots / player_match_stats."""
        return {k: v[0] for k, v in self.all_files().items()}

    @property
    def enabled(self) -> bool:
        f = self.all_files()
        return bool(f.get("matches") or f.get("team_match_stats") or f.get("events"))

    # -------------------------------------------------------------- download
    REPO = "nlbair/openplay"

    def download(self, tag: Optional[str] = None, progress: Optional[Callable[[str], None]] = None,
                 kinds: Optional[List[str]] = None) -> Dict[str, Any]:
        """Baixa os arquivos da release de dados mais nova (tag 'data-…') para OPENPLAY_PATH. Sem conta no GitHub."""
        from src.data_hub import net

        say = progress or (lambda m: None)
        tag = tag or os.getenv("OPENPLAY_RELEASE") or None
        assets = net.github_release_assets(self.REPO, tag=tag, prefix="" if tag else "data-")
        assets = [a for a in assets if a["name"].lower().endswith((".parquet", ".csv", ".zip", ".csv.gz"))]
        if kinds:
            assets = [a for a in assets if self._kind(Path(a["name"])) in kinds or a["name"].lower().endswith(".zip")]
        if not assets:
            raise FileNotFoundError("OpenPlay: nenhuma release de dados com arquivos encontrada no GitHub.")
        total = sum(a["size"] for a in assets)
        say(f"  openplay: release {assets[0]['tag']} · {len(assets)} arquivo(s) · {total / 1e9:.2f} GB no total")
        self.path.mkdir(parents=True, exist_ok=True)
        got = 0
        for a in assets:
            dest = self.path / a["name"]
            net.download(a["url"], dest, expected_size=a["size"] or None, progress=say, source="openplay")
            if dest.suffix.lower() == ".zip":
                import zipfile

                with zipfile.ZipFile(dest) as z:
                    for member in z.namelist():
                        if member.lower().endswith((".parquet", ".csv")) and not (self.path / Path(member).name).exists():
                            (self.path / Path(member).name).write_bytes(z.read(member))
            got += 1
        return {"arquivos": got, "tag": assets[0]["tag"], "bytes": total}

    @staticmethod
    def _read(p: Path, columns: Optional[List[str]] = None, filters=None) -> pd.DataFrame:
        if p.suffix.lower() == ".parquet":
            try:
                import pyarrow.parquet as pq

                return pq.read_table(p, columns=columns, filters=filters).to_pandas()
            except Exception:
                df = pd.read_parquet(p)
        else:
            df = pd.read_csv(p, low_memory=False, usecols=columns)
        if filters:
            for col, op, val in filters:
                df = df[df[col].astype(str) == str(val)]
        return df

    # --------------------------------------------------------------- catálogo
    @staticmethod
    def parse_matches(m: pd.DataFrame, has_events: bool, team_stats: Optional[pd.DataFrame] = None) -> List[tuple]:
        M = normalize_columns(m)
        c_id = find_col(M, "match_id", "game_id", "id", "fixture_id")
        c_d = find_col(M, "date", "match_date", "kickoff", "start_time", "datetime")
        c_h = find_col(M, "home_team", "home", "home_team_name", "home_name")
        c_a = find_col(M, "away_team", "away", "away_team_name", "away_name")
        c_hs = find_col(M, "home_score", "home_goals", "fthg", contains=("home", "score"))
        c_as = find_col(M, "away_score", "away_goals", "ftag", contains=("away", "score"))
        c_c = find_col(M, "competition", "league", "competition_name", "tournament")
        c_s = find_col(M, "season", "season_name")
        c_comp = find_col(M, "comp")
        if not all([c_id, c_d, c_h, c_a]):
            raise ValueError(f"tabela de jogos sem id/data/times reconhecíveis: {list(M.columns)[:20]}")
        c_ht_h, c_ht_a = find_col(M, "home_ht_score"), find_col(M, "away_ht_score")
        c_n_ev = find_col(M, "n_events")
        names: Dict[tuple, str] = {}                     # (jogo, lado) → nome do time (a tabela por time só tem o id)
        for r in M.to_dict("records"):
            names[(str(r.get(c_id)), "home")], names[(str(r.get(c_id)), "away")] = str(r.get(c_h)), str(r.get(c_a))
        by = OpenPlayProvider.team_stats_by_match(team_stats, names)
        out = []
        for r in M.to_dict("records"):
            sid = str(r.get(c_id))
            for side, col in (("home", c_ht_h), ("away", c_ht_a)):
                if col:
                    s_ = stat(names[(sid, side)], "ht_goals", "Gols no 1º tempo", r.get(col))
                    if s_ and s_["value"] >= 0:
                        by.setdefault(sid, []).append(s_)
        for r in M.to_dict("records"):
            sid = str(r.get(c_id))
            d = parse_date(r.get(c_d))
            if not d:
                continue
            num = to_int(sid)
            internal = to_internal_id("openplay", num if num is not None and num < 900_000_000 else stable_id(sid))
            stats = by.get(sid, [])
            n_ev = to_int(r.get(c_n_ev)) if c_n_ev else None
            with_events = has_events and (n_ev is None or n_ev > 0)        # jogo sem lances nos arquivos não é EVENTOS
            level = DataLevel.EVENTS if with_events else (DataLevel.BOXSCORE if stats else DataLevel.RESULT)
            rec = {"match_id": internal, "home_team_name": str(r.get(c_h)), "away_team_name": str(r.get(c_a)),
                   "match_date": d, "home_score": to_int(r.get(c_hs)) if c_hs else None,
                   "away_score": to_int(r.get(c_as)) if c_as else None,
                   "competition_name": str(r.get(c_c) or "") if c_c else "", "season_name": season_label(r.get(c_s), r.get(c_comp)) if c_s else "",
                   "status": "FT", "data_source": "openplay", "data_level": level, "source_match_id": sid}
            out.append((rec, stats))
        return out

    @staticmethod
    def team_stats_by_match(team_stats: Optional[pd.DataFrame], names: Dict[tuple, str]) -> Dict[str, List[Dict]]:
        """Linhas por time → estatísticas do app. Sem coluna de nome, o time vem do lado (home/away) + tabela de jogos.
        Valores fora do domínio (ex.: posse negativa, que existe no arquivo) são descartados, nunca corrigidos."""
        by: Dict[str, List[Dict]] = {}
        if team_stats is None or team_stats.empty:
            return by
        T = normalize_columns(team_stats)
        t_id, t_team = find_col(T, "match_id", "game_id"), find_col(T, "team", "team_name")
        t_side = find_col(T, "side", "home_away", "venue", "team_side")
        if not t_id or not (t_team or t_side):
            return by
        cols = [(find_col(T, src, *alts), key) for src, key, alts in TEAM_STATS]
        cols = [(c, k) for c, k in cols if c]
        labels = _labels()
        for r in T.to_dict("records"):
            mid = str(r[t_id])
            team = str(r[t_team]) if t_team and r.get(t_team) not in (None, "") else \
                names.get((mid, str(r.get(t_side) or "").lower()))
            if not team:
                continue
            for col, key in cols:
                s_ = stat(team, key, labels.get(key, key), r.get(col))
                if not s_ or s_["value"] < 0 or (key in PCT_KEYS and s_["value"] > 100):
                    continue
                by.setdefault(mid, []).append(s_)
        return by

    def _concat(self, paths: List[Path]) -> pd.DataFrame:
        parts = [self._read(p) for p in paths]
        parts = [x for x in parts if x is not None and not x.empty]
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    @staticmethod
    def matches_from_team_stats(ts: pd.DataFrame) -> pd.DataFrame:
        """Sem tabela de jogos: monta uma a partir das linhas por time (lado mandante/visitante + gols pró)."""
        T = normalize_columns(ts)
        c_id = find_col(T, "match_id", "game_id")
        c_team = find_col(T, "team", "team_name")
        c_side = find_col(T, "side", "home_away", "venue", "is_home", "team_side")
        c_gf = find_col(T, "goals_for", "goals", "score", contains=("goals", "for"))
        c_d = find_col(T, "date", "match_date", "kickoff")
        c_c, c_s = find_col(T, "competition", "league"), find_col(T, "season")
        if not all([c_id, c_team, c_side, c_d]):
            return pd.DataFrame()
        home = T[T[c_side].astype(str).str.lower().isin(["home", "h", "true", "1", "mandante"])]
        away = T[T[c_side].astype(str).str.lower().isin(["away", "a", "false", "0", "visitante"])]
        m = home.merge(away[[c_id, c_team] + ([c_gf] if c_gf else [])], on=c_id, suffixes=("", "_away"))
        out = pd.DataFrame({"match_id": m[c_id], "date": m[c_d], "home_team": m[c_team], "away_team": m[f"{c_team}_away"]})
        if c_gf:
            out["home_score"], out["away_score"] = m[c_gf], m[f"{c_gf}_away"]
        if c_c:
            out["competition"] = m[c_c]
        if c_s:
            out["season"] = m[c_s]
        return out

    def sync(self, progress: Optional[Callable[[str], None]] = None, auto_download: bool = True) -> Dict[str, int]:
        say = progress or (lambda m: None)
        f = self.all_files()
        if not (f.get("matches") or f.get("team_match_stats")) and auto_download:
            say("  openplay: arquivos ainda não baixados — baixando a release de dados do GitHub...")
            self.download(progress=say)
            f = self.all_files()
        if not (f.get("matches") or f.get("team_match_stats")):
            raise FileNotFoundError(f"OpenPlay: nenhuma tabela de jogos em {self.path}. Baixe os .parquet da página de "
                                    "releases do github.com/nlbair/openplay e defina OPENPLAY_PATH no .env.")
        ts = self._concat(f["team_match_stats"]) if f.get("team_match_stats") else None
        m = self._concat(f["matches"]) if f.get("matches") else self.matches_from_team_stats(ts)
        rows = self.parse_matches(m, bool(f.get("events")), ts)
        r = self.db.upsert_matches([rec for rec, _ in rows])
        with self.db.connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO match_team_stats (match_id, team_name, stat_key, stat_label, value, "
                             "display_value) VALUES (?, ?, ?, ?, ?, ?)",
                             [(rec["match_id"], s["team_name"], s["stat_key"], s["stat_label"], s["value"], s["display_value"])
                              for rec, stats in rows for s in stats])
        if self.db.get_state("openplay", "converter") != CONVERTER_VERSION:
            with self.db.connect() as conn:                  # lances convertidos com a regra antiga: refaz na abertura
                n = conn.execute("DELETE FROM events WHERE match_id IN (SELECT match_id FROM matches "
                                 "WHERE data_source = 'openplay')").rowcount
            self.db.set_state("openplay", "converter", CONVERTER_VERSION)
            if n:
                say(f"  openplay: {n} lances em cache convertidos com a regra antiga — serão refeitos ao abrir o jogo")
        say(f"  openplay: {len(rows)} jogos catalogados ({'com' if f.get('events') else 'sem'} tabela de eventos)")
        return {"added": r["added"], "updated": r["updated"], "partidas": len(rows)}

    # ---------------------------------------------------------------- eventos
    @staticmethod
    def convert_events(ev: pd.DataFrame, internal_id: int, home: str = "") -> pd.DataFrame:
        """
        Eventos OpenPlay/WhoScored → esquema de eventos do app (escala 120×80, tipos StatsBomb, posses).

        Regras do formato WhoScored que mudam a análise se ignoradas:
          * falta vem em dois registros: quem cometeu (desfecho mal-sucedido) e quem sofreu (bem-sucedido);
          * gol contra é um "Goal" com o qualificador OwnGoal → vira "Own Goal Against" (não conta como chute);
          * substituição vem em dois registros (sai / entra) → um "Substitution" com o nome de quem entrou;
          * cartão é um registro próprio → "Bad Behaviour" com o cartão (não duplica a falta);
          * disputa de pênaltis = período 5 (fica fora das métricas do jogo, como no StatsBomb).
        """
        E = normalize_columns(ev)
        c = lambda *n, **k: find_col(E, *n, **k)
        c_type, c_out = c("type", "event_type", "type_name", "type_display_name"), c("outcome", "outcome_type", "result")
        c_x, c_y = c("x", "start_x", "location_x"), c("y", "start_y", "location_y")
        c_ex, c_ey = c("end_x", "endx", "pass_end_x"), c("end_y", "endy", "pass_end_y")
        c_pl, c_tm = c("player", "player_name"), c("team", "team_name")
        c_pid, c_tid = c("player_id"), c("team_id")
        c_min, c_sec, c_per = c("minute", "expanded_minute"), c("second"), c("period", "period_id", "half")
        c_xg = c("xg", "shot_xg", "expected_goals")
        c_body, c_patt = c("body_part"), c("play_pattern")
        c_len, c_ang = c("q_length", "length"), c("q_angle", "angle")
        if not c_type or not c_x:
            raise ValueError(f"eventos sem tipo/coordenadas reconhecíveis: {list(E.columns)[:25]}")
        if c_per and c_min:                                    # a ordem dos registros nem sempre é a do relógio
            order = [k for k in (c_per, c_min, c_sec) if k]
            per_rank = E[c_per].map(lambda v: PERIOD.get(_key(v), to_int(v) or 9))
            E = E.assign(_p=per_rank).sort_values(["_p"] + order[1:], kind="stable").drop(columns="_p")
        xs = pd.to_numeric(E[c_x], errors="coerce")
        opta = xs.max(skipna=True) <= 100.5                       # 0–100 → 120×80 (y invertido como no StatsBomb)
        sx = (lambda v: v * 1.2) if opta else (lambda v: v)
        sy = (lambda v: (100 - v) * 0.8) if opta else (lambda v: v)

        def q(r, name: str) -> bool:
            v = r.get(name)
            return bool(v) and not (isinstance(v, float) and pd.isna(v)) and str(v).lower() not in ("false", "0", "")

        rows: List[Dict[str, Any]] = []
        pending_off: Dict[str, List[Dict[str, Any]]] = {}          # quem saiu, à espera de quem entrou
        pending_on: Dict[str, List[Any]] = {}                      # quem entrou antes do registro de saída
        poss, poss_team, cur_period = 0, None, None
        for i, r in enumerate(E.to_dict("records")):
            raw = _key(r.get(c_type))
            t = TYPE_MAP.get(raw)
            if t is None:
                continue
            per_raw = r.get(c_per) if c_per else 1
            if _key(per_raw) in SKIP_PERIODS:
                continue
            period = PERIOD.get(_key(per_raw)) or to_int(per_raw) or 1
            outcome = _key(r.get(c_out)) if c_out else ""
            ok = outcome in ("successful", "success", "complete", "1", "true", "won")
            if t == "Foul":
                t = "Foul Won" if ok else "Foul Committed"
            elif t == "BallTouch":
                if ok or not c_out:
                    continue                                       # toque comum: não é erro de domínio
                t = "Miscontrol"
            elif t == "Shot" and raw == "goal" and q(r, "q_owngoal"):
                t = "Own Goal Against"
            x, y = to_number(r.get(c_x)), to_number(r.get(c_y)) if c_y else None
            ex = to_number(r.get(c_ex)) if c_ex else None
            ey = to_number(r.get(c_ey)) if c_ey else None
            team = str(r.get(c_tm) or "")
            row: Dict[str, Any] = {
                "event_id": f"op{internal_id}_{i}", "match_id": int(internal_id), "period": period,
                "minute": to_int(r.get(c_min)) or 0, "second": (to_int(r.get(c_sec)) or 0) if c_sec else 0,
                "team_name": team, "player_name": str(r.get(c_pl) or "") or None,
                "player_id": to_int(r.get(c_pid)) if c_pid else None, "type_name": t,
                "x": sx(x) if x is not None else np.nan, "y": sy(y) if y is not None else np.nan,
                "end_x": sx(ex) if ex is not None else np.nan, "end_y": sy(ey) if ey is not None else np.nan,
                "play_pattern_name": _pattern(r, c_patt, q)}
            if t == "Card":
                card = ("Second Yellow" if q(r, "q_secondyellow") else "Red Card" if q(r, "q_red") else
                        "Yellow Card" if q(r, "q_yellow") else None)
                if not card:
                    continue
                row.update(type_name="Bad Behaviour", foul_committed_card_name=card, x=np.nan, y=np.nan)
            elif t == "SubOff":
                row["type_name"] = "Substitution"
                came_in = pending_on.get(team) or []
                if came_in:
                    row["substitution_replacement_name"] = came_in.pop(0)
                else:
                    pending_off.setdefault(team, []).append(row)
            elif t == "SubOn":
                waiting = pending_off.get(team) or []
                if waiting:
                    waiting.pop(0)["substitution_replacement_name"] = row["player_name"]
                else:
                    pending_on.setdefault(team, []).append(row["player_name"])
                continue                                           # quem entra fica no registro de quem saiu
            elif t == "Pass":
                row["pass_outcome_name"] = None if (ok or not c_out) else "Incomplete"
                row["pass_length"], row["pass_angle"] = (to_number(r.get(c_len)) if c_len else None,
                                                         to_number(r.get(c_ang)) if c_ang else None)
                row["is_pass_cross"] = int(q(r, "q_cross"))
                row["is_pass_through_ball"] = int(q(r, "q_throughball"))
                row["pass_type_name"] = ("Corner" if q(r, "q_cornertaken") else "Free Kick" if q(r, "q_freekicktaken") else
                                         "Throw-in" if q(r, "q_throwin") else "Goal Kick" if q(r, "q_goalkick") else None)
                row["pass_height_name"] = "High Pass" if (q(r, "q_chipped") or q(r, "q_cross")) else None
                row["pass_body_part"] = "Head" if q(r, "q_headpass") else None
            elif t == "Shot":
                row["shot_outcome_name"] = ("Goal Disallowed" if q(r, "q_goaldisallowed") else
                                            SHOT_OUTCOME.get(raw) or ("Goal" if outcome == "goal" else "Off T"))
                row["shot_statsbomb_xg"] = to_number(r.get(c_xg)) if c_xg else None
                row["shot_type_name"] = ("Penalty" if q(r, "q_penalty") else "Free Kick" if q(r, "q_directfreekick")
                                         else "Open Play")
                body = str(r.get(c_body) or "") if c_body else ""
                row["shot_body_part_name"] = body if body in ("Head", "Right Foot", "Left Foot", "Other") else None
            elif t == "Duel":
                row["duel_type_name"] = DUEL_TYPE.get(raw)
                if raw == "aerial" and ok:
                    row["duel_type_name"] = "Aerial Won"
                row["duel_outcome_name"] = "Won" if ok else "Lost"
            if cur_period != row["period"]:
                cur_period, poss_team = row["period"], None
            if row["type_name"] in CONTROL and team != poss_team:
                poss += 1
                poss_team = team
            row["possession"] = max(poss, 1)
            row["possession_team_name"] = poss_team or team
            rows.append(row)
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["index_num"] = range(1, len(df) + 1)
        ids = {t: stable_id("openplay-team", t, modulo=9_000_000) for t in df["team_name"].unique()}
        df["team_id"] = df["team_name"].map(ids)                     # o banco exige id numérico do time
        df["possession_team_id"] = df["possession_team_name"].map(ids)
        try:                                       # quem recebeu cada passe (mesma regra usada no Wyscout)
            from src.data_hub.sources.wyscout import WyscoutConverter

            WyscoutConverter._infer_recipients(df)
        except Exception:
            pass
        return df

    @staticmethod
    def check_own_goals(df: pd.DataFrame, home: str, away: str, home_score: Optional[int],
                        away_score: Optional[int]) -> pd.DataFrame:
        """
        O placar dos eventos tem de bater com o placar oficial. Se só bater com os gols contra atribuídos ao outro
        time (convenção oposta de quem gerou o arquivo), troca o time desses registros; senão, não mexe.
        """
        if df is None or df.empty or home_score is None or away_score is None:
            return df
        og = df["type_name"] == "Own Goal Against"
        if not og.any():
            return df

        def score(d: pd.DataFrame) -> tuple:
            reg = d[d["period"] <= 4]
            goals = reg[(reg["type_name"] == "Shot") & (reg["shot_outcome_name"] == "Goal")]
            ogs = reg[reg["type_name"] == "Own Goal Against"]
            return (int((goals["team_name"] == home).sum() + (ogs["team_name"] == away).sum()),
                    int((goals["team_name"] == away).sum() + (ogs["team_name"] == home).sum()))

        if score(df) == (home_score, away_score):
            return df
        flipped = df.copy()
        flipped.loc[og, "team_name"] = flipped.loc[og, "team_name"].map({home: away, away: home}).fillna(
            flipped.loc[og, "team_name"])
        if "team_id" in flipped.columns:
            ids = dict(zip(df["team_name"], df["team_id"]))
            flipped.loc[og, "team_id"] = flipped.loc[og, "team_name"].map(ids)
        return flipped if score(flipped) == (home_score, away_score) else df

    @staticmethod
    def _sid_key(value: Any) -> str:
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(value).strip()

    def _events_file_for(self, sid: Any, paths: List[Path]) -> List[Path]:
        """Escolhe o parquet da competição/temporada usando um índice carregado uma única vez."""
        if self._catalog_map is None:
            catalog: Dict[str, tuple[str, str]] = {}
            for mp in self.all_files().get("matches") or []:
                try:
                    df = self._read(mp, columns=["match_id", "comp", "season"])
                except Exception:
                    continue
                if not {"match_id", "comp", "season"} <= set(df.columns):
                    continue
                for r in df[["match_id", "comp", "season"]].dropna().itertuples(index=False, name=None):
                    catalog[self._sid_key(r[0])] = (str(r[1]), str(r[2]))
            self._catalog_map = catalog
        info = self._catalog_map.get(self._sid_key(sid))
        if info:
            want = f"events_{info[0]}_{info[1]}".lower()
            first = [p for p in paths if p.stem.lower() == want]
            return first + [p for p in paths if p not in first]
        return paths

    def pending_match_ids(self, limit: Optional[int] = None) -> List[int]:
        """IDs OpenPlay com evento no catálogo, ainda não convertidos/cacheados no banco."""
        if self.db is None:
            return []
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT m.match_id FROM matches m LEFT JOIN events e ON e.match_id = m.match_id "
                "WHERE m.data_source = 'openplay' AND m.data_level = 'EVENTS' "
                "GROUP BY m.match_id HAVING COUNT(e.event_id) = 0 ORDER BY m.match_date DESC"
            ).fetchall()
        now = time.time()
        out = []
        for row in rows:
            mid = int(row[0])
            try:
                failed_at = float(self.db.get_state("openplay", f"prefetch_failed_{mid}") or 0)
            except (TypeError, ValueError):
                failed_at = 0
            if failed_at and now - failed_at < 24 * 3600:
                continue
            out.append(mid)
            if limit is not None and len(out) >= max(0, int(limit)):
                break
        return out

    def pending_count(self) -> int:
        if self.db is None:
            return 0
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM matches m LEFT JOIN events e ON e.match_id = m.match_id "
                "WHERE m.data_source = 'openplay' AND m.data_level = 'EVENTS' "
                "GROUP BY m.match_id HAVING COUNT(e.event_id) = 0"
            ).fetchall()
        return len(row)

    def prefetch_events(self, limit: int = 250, progress: Optional[Callable[[str], None]] = None,
                        stop: Optional[Callable[[], bool]] = None) -> Dict[str, int]:
        """Converte uma fatia dos jogos locais sem abrir telas; é retomável e nunca acessa a rede."""
        if self.db is None:
            raise ValueError("prefetch OpenPlay exige DataHubDB")
        say = progress or (lambda m: None)
        ids = self.pending_match_ids(limit=limit)
        loaded = failed = 0
        for i, mid in enumerate(ids, 1):
            if stop and stop():
                break
            try:
                frame = self.load_events(mid)
                if frame is not None and not frame.empty:
                    loaded += 1
            except Exception as exc:
                failed += 1
                self.db.set_state("openplay", f"prefetch_failed_{mid}", str(time.time()))
                say(f"OpenPlay {mid}: {type(exc).__name__}: {exc}")
            if i % 25 == 0:
                say(f"OpenPlay: lote {i}/{len(ids)} · convertidos {loaded} · falhas {failed}")
        return {"loaded": loaded, "failed": failed, "pending": self.pending_count(), "attempted": len(ids)}

    def load_events(self, match_id: int) -> pd.DataFrame:
        meta = self.db.get_match(int(match_id)) or {}
        paths = self.all_files().get("events") or []
        if not paths:
            raise FileNotFoundError("OpenPlay: tabela de eventos não encontrada (OPENPLAY_PATH).")
        sid = meta.get("source_match_id")
        val = int(sid) if str(sid).isdigit() else sid
        ev = pd.DataFrame()
        for p in self._events_file_for(val, paths):       # dados divididos: começa pelo arquivo da competição
            try:
                import pyarrow.parquet as pq

                cols = pq.read_schema(p).names
            except Exception:
                cols = list(self._read(p).head(0).columns)
            idc = next((c for c in cols if c.lower() in ("match_id", "game_id", "fixture_id")), None)
            if not idc:
                continue
            ev = self._read(p, filters=[(idc, "=", val)])
            if not ev.empty:
                break
        if ev.empty:
            raise ValueError(f"OpenPlay: os lances do jogo {sid} não estão nos arquivos baixados.")
        df = self.convert_events(ev, int(match_id), meta.get("home_team_name", ""))
        df = self.check_own_goals(df, meta.get("home_team_name", ""), meta.get("away_team_name", ""),
                                  to_int(meta.get("home_score")), to_int(meta.get("away_score")))
        if not df.empty:
            self.db.save_events(int(match_id), df)
        return df


def inspect(path: Optional[str] = None) -> str:
    p = OpenPlayProvider(path=path)
    f = {k: v[0] for k, v in p.all_files().items()}
    if not f:
        return f"Nenhum arquivo .parquet/.csv reconhecido em {p.path}."
    out = []
    for kind, fp in f.items():
        try:
            df = p._read(fp).head(200)
            out.append(f"[{kind}] {fp.name}\n{describe(normalize_columns(df))}")
        except Exception as exc:
            out.append(f"[{kind}] {fp.name}: erro ao ler ({exc})")
    return "\n\n".join(out)


if __name__ == "__main__":
    try:  # lê o .env (OPENPLAY_PATH, CBF_SUMULAS_PATH, caminho do banco...) também quando rodado direto
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    import sys

    print(inspect(sys.argv[2] if len(sys.argv) > 2 else None) if "--inspecionar" in sys.argv else __doc__)
