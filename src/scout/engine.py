"""
Scout & Planejamento — motor contextual, explicável e conservador.
Usa dados observados do lake/SQLite; estimativas financeiras e projeções táticas são rotuladas como tais.
"""

from __future__ import annotations

from src.data_hub.gender import comp_sql
import hashlib
import json
import math
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.data_lake.ids import player_core, team_core
from src.squad.formations import FORMATIONS, fit, natural_role

ROLE_LABELS = {
    "GK": "Goleiro", "CB": "Zagueiro", "LB": "Lateral-esquerdo", "RB": "Lateral-direito",
    "LWB": "Ala-esquerdo", "RWB": "Ala-direito", "DM": "Volante", "CM": "Meia central",
    "AM": "Meia ofensivo", "LM": "Meia-esquerda", "RM": "Meia-direita",
    "LW": "Ponta-esquerda", "RW": "Ponta-direita", "ST": "Centroavante",
}
ROLE_FAMILY = {
    "GK": "GK", "CB": "DEF", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "DM": "MID", "CM": "MID", "AM": "ATT_MID", "LM": "WIDE", "RM": "WIDE",
    "LW": "WIDE", "RW": "WIDE", "ST": "ST",
}
ROLE_METRICS = {
    "GK": [("saves_p90", .30, True), ("xgot_faced_p90", .20, True),
           ("rating_media", .25, True), ("goals_conceded_p90", .15, False),
           ("errors_p90", .10, False)],
    "CB": [("def_actions_p90", .16, True), ("interceptions_p90", .16, True),
           ("clearances_p90", .08, True), ("aerials_won_p90", .14, True),
           ("line_breaking_p90", .16, True), ("dribbled_past_p90", .10, False),
           ("pass_accuracy_pct", .15, True), ("errors_p90", .10, False), ("rating_media", .15, True)],
    "FB": [("def_actions_p90", .18, True), ("interceptions_p90", .12, True),
           ("chances_created_p90", .20, True), ("xa_p90", .14, True),
           ("assists_p90", .12, True), ("sprints_p90", .12, True),
           ("pass_accuracy_pct", .12, True), ("rating_media", .15, True)],
    "DM": [("def_actions_p90", .18, True), ("interceptions_p90", .16, True), ("line_breaking_p90", .14, True),
           ("tackles_p90", .14, True), ("pass_accuracy_pct", .16, True),
           ("chances_created_p90", .12, True), ("xa_p90", .08, True),
           ("errors_p90", .10, False), ("rating_media", .15, True)],
    "MID": [("chances_created_p90", .18, True), ("xa_p90", .17, True),
            ("pass_accuracy_pct", .16, True), ("def_actions_p90", .14, True),
            ("interceptions_p90", .10, True), ("goals_p90", .10, True),
            ("xg_p90", .08, True), ("errors_p90", .07, False), ("rating_media", .15, True)],
    "ATT_MID": [("chances_created_p90", .20, True), ("xa_p90", .18, True),
                ("xg_p90", .16, True), ("goals_p90", .14, True),
                ("assists_p90", .12, True), ("shots_p90", .10, True),
                ("rating_media", .10, True)],
    "WIDE": [("xg_p90", .17, True), ("goals_p90", .15, True),
             ("xa_p90", .15, True), ("chances_created_p90", .15, True),
             ("assists_p90", .12, True), ("shots_p90", .10, True),
             ("sprints_p90", .08, True), ("rating_media", .08, True)],
    "ST": [("xg_p90", .24, True), ("goals_p90", .20, True),
           ("shots_p90", .16, True), ("shots_on_target_p90", .12, True),
           ("assists_p90", .08, True), ("chances_created_p90", .08, True),
           ("rating_media", .12, True)],
}
COUNT_KEYS = {
    "goals": "totalGoals", "assists": "goalAssists", "shots": "totalShots",
    "shots_on_target": "shotsOnTarget", "xg": "xg", "xa": "xa",
    "chances_created": "chances_created", "def_actions": "defensive_actions",
    "sprints": "sprints", "touches": "touches", "interceptions": "interceptions",
    "tackles": ("tackles", "matchstats.headers.tackles"), "recoveries": "recoveries", "clearances": "clearances",
    # rodada 22: a FotMob grava "dribbles_succeeded" e "matchstats.headers.tackles" — com só o nome antigo, dribles e
    # desarmes de TODOS os jogos da FotMob ficavam vazios no Scout. Tupla = nomes alternativos (o 1º presente vale).
    "aerials_won": "aerials_won", "dribbles": ("successful_dribbles", "dribbles_succeeded"),
    "fouls": "foulsCommitted", "errors": "errors_led_to_goal", "saves": "saves",
    "xgot_faced": "xgot_faced", "yellow_cards": "yellow_cards", "red_cards": "red_cards",
    # rodada 13: construção (zagueiro que joga, como Cubarsí, não pode ser medido só por cortes e desarmes)
    "line_breaking": "line_breaking_passes", "final_third_passes": "passes_into_final_third",
    "long_balls": "long_balls_accurate", "dribbled_past": "dribbled_past",
    # rodada 22: tentativas (para os %), perdas, presença na área — base do potencial por posição
    "passes_acc": "accurate_passes", "passes_tot": "accurate_passes_total", "duel_won": "duel_won",
    "duel_lost": "duel_lost", "aerials_tot": "aerials_won_total", "dribbles_tot": "dribbles_succeeded_total",
    "crosses_acc": "accurate_crosses", "crosses_tot": "accurate_crosses_total", "long_balls_tot": "long_balls_accurate_total",
    "dispossessed": "dispossessed", "touches_opp_box": "touches_opp_box", "was_fouled": "was_fouled",
}
P90_KEYS = ("goals", "assists", "shots", "shots_on_target", "xg", "xa", "chances_created", "def_actions", "sprints",
            "touches", "interceptions", "tackles", "recoveries", "clearances", "aerials_won", "dribbles", "fouls",
            "errors", "saves", "xgot_faced", "line_breaking", "final_third_passes", "long_balls", "dribbled_past",
            "crosses_acc", "dispossessed", "touches_opp_box", "was_fouled")


def _raw_keys(raw_key) -> tuple:
    return tuple(raw_key) if isinstance(raw_key, (tuple, list)) else (raw_key,)


def derived_rates(out):
    """% de acerto a partir das SOMAS (passe, duelo, aéreo, drible, cruzamento, bola longa, chute no alvo). Funciona
    com dict (um atleta) ou DataFrame (vários). Amostra mínima por taxa; abaixo dela fica vazio (não é zero)."""
    def rate(ok, tot, mn):
        a, b = out.get(ok), out.get(tot)
        if isinstance(out, dict):
            if a is None or b is None or not b or b < mn:
                return None
            return round(100 * float(a) / float(b), 1)
        a = pd.to_numeric(a, errors="coerce") if a is not None else None
        b = pd.to_numeric(b, errors="coerce") if b is not None else None
        if a is None or b is None:
            return pd.Series(np.nan, index=out.index)
        return (100 * a / b.where(b >= mn)).round(1)
    if isinstance(out, dict):
        dw, dl = out.get("duel_won"), out.get("duel_lost")
        out["_duel_tot"] = (dw or 0) + (dl or 0) if dw is not None or dl is not None else None
    else:
        out["_duel_tot"] = pd.to_numeric(out.get("duel_won"), errors="coerce").fillna(0) + \
            pd.to_numeric(out.get("duel_lost"), errors="coerce").fillna(0)
    rates = {"pass_rate_pct": rate("passes_acc", "passes_tot", 40), "duel_rate_pct": rate("duel_won", "_duel_tot", 15),
             "aerial_pct": rate("aerials_won", "aerials_tot", 8), "dribble_pct": rate("dribbles", "dribbles_tot", 6),
             "cross_pct": rate("crosses_acc", "crosses_tot", 8), "long_ball_pct": rate("long_balls", "long_balls_tot", 10),
             "shot_acc_pct": rate("shots_on_target", "shots", 8)}
    for k, v in rates.items():
        out[k] = v
    if isinstance(out, dict):
        out.pop("_duel_tot", None)
        if out.get("pass_accuracy_pct") is None:
            out["pass_accuracy_pct"] = rates["pass_rate_pct"]
        if out.get("duels_won_pct") is None:
            out["duels_won_pct"] = rates["duel_rate_pct"]
    else:
        out.drop(columns=["_duel_tot"], inplace=True)
        out["pass_accuracy_pct"] = pd.to_numeric(out.get("pass_accuracy_pct"), errors="coerce").combine_first(rates["pass_rate_pct"])
        out["duels_won_pct"] = pd.to_numeric(out.get("duels_won_pct"), errors="coerce").combine_first(rates["duel_rate_pct"])
    return out


def history_cache_revision(db: Any) -> str:
    """Revisão seletiva: logs e sincronizações alheias não invalidam o histórico do Scout."""
    getter = getattr(db, "get_state", None)
    if callable(getter):
        try:
            revision = getter("cache", "player_history_revision")
            if revision is not None:
                return f"player-history:{revision}"
        except Exception:
            pass

    import time

    raw_path = getattr(db, "db_path", None)
    if raw_path is None:
        raw_path = getattr(db, "path", None)
    if raw_path is None or str(raw_path) == ":memory:":
        return f"uncacheable:{time.monotonic_ns()}"

    try:
        path = Path(raw_path).expanduser().resolve()
        path.stat()
    except (OSError, TypeError, ValueError):
        return f"uncacheable:{time.monotonic_ns()}"

    files = []
    for suffix in ("", "-wal", "-journal"):
        candidate = Path(f"{path}{suffix}")
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            files.append((suffix, False, None, None, None))
        except OSError:
            return f"uncacheable:{time.monotonic_ns()}"
        else:
            files.append((
                suffix, True, int(stat.st_size),
                int(stat.st_mtime_ns), int(stat.st_ctime_ns),
            ))

    if not files[0][1]:
        return f"uncacheable:{time.monotonic_ns()}"

    payload = json.dumps(
        {"path": str(path), "files": files},
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


LANGUAGES = {
    "brazil": {"portugues"}, "portugal": {"portugues"}, "angola": {"portugues"},
    "argentina": {"espanhol"}, "uruguay": {"espanhol"}, "chile": {"espanhol"},
    "paraguay": {"espanhol"}, "colombia": {"espanhol"}, "ecuador": {"espanhol"},
    "peru": {"espanhol"}, "bolivia": {"espanhol"}, "venezuela": {"espanhol"},
    "spain": {"espanhol"}, "mexico": {"espanhol"}, "france": {"frances"},
    "belgium": {"frances", "neerlandes"}, "senegal": {"frances"},
    "england": {"ingles"}, "ireland": {"ingles"}, "united states": {"ingles"},
    "scotland": {"ingles"}, "wales": {"ingles"}, "nigeria": {"ingles"},
    "ghana": {"ingles"}, "germany": {"alemao"}, "austria": {"alemao"},
    "switzerland": {"alemao", "frances", "italiano"}, "italy": {"italiano"},
    "netherlands": {"neerlandes"}, "sweden": {"sueco"}, "norway": {"noruegues"},
    "denmark": {"dinamarques"}, "croatia": {"croata"}, "serbia": {"servio"},
    "japan": {"japones"}, "south korea": {"coreano"},
}
BR_COMP_TOKENS = ("brasileirao", "campeonato brasileiro")


def _num(value: Any) -> Optional[float]:
    if value is None or value is pd.NA:
        return None
    try:
        if isinstance(value, str):
            s = value.strip().replace(",", ".")
            if not s or s in {"-", "—", "nan", "None", "null"}:
                return None
            m = re.search(r"-?\d+(?:\.\d+)?", s)
            return float(m.group(0)) if m else None
        x = float(value)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _json_obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        out = json.loads(value or "{}")
        return out if isinstance(out, dict) else {}
    except (TypeError, ValueError):
        return {}


def _safe_str(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _boolean_mask(values: pd.Series) -> pd.Series:
    """Normaliza flags vindas de CSV/SQLite (bool, 0/1 ou texto) para máscara booleana."""
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_numeric(values, errors="coerce").fillna(0).ne(0)
    return values.astype("string").str.strip().str.casefold().isin({"1", "true", "yes", "sim", "y"})


def _role(value: Any, funcao: Any = None) -> str:
    role = natural_role(_safe_str(funcao), _safe_str(value))
    return role if role in ROLE_LABELS else ""


def _role_family(role: str) -> str:
    return ROLE_FAMILY.get(role, "OTHER")


def _money(value: Any) -> Optional[float]:
    """Converte taxas Transfermarkt em euros; desconhecido/emprestado/livre permanece None."""
    if value is None:
        return None
    if isinstance(value, (int, float, np.number)):
        x = _num(value)
        return x if x is not None and x >= 0 else None
    s = str(value).strip().lower()
    if not s or any(k in s for k in ("loan", "emprest", "free", "livre", "sem custo", "?", "undisclosed")):
        return None
    s = s.replace("€", "").replace("eur", "").replace(" ", "").replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)(m|bn|k)?", s)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2)
    return n * (1e9 if unit == "bn" else 1e6 if unit == "m" else 1e3 if unit == "k" else 1.0)


def _player_season_totals(rows: pd.DataFrame) -> Dict[str, Any]:
    """Resume uma amostra sem reabrir o mesmo JSON para cada indicador."""
    out: Dict[str, Any] = {}
    mins = pd.to_numeric(rows.get("minutes"), errors="coerce").fillna(0)
    total_minutes = float(mins.sum())
    out["minutos"] = int(total_minutes)
    out["jogos"] = int(rows["match_id"].nunique()) if "match_id" in rows else len(rows)
    rating_column = "rating_ajustada" if "rating_ajustada" in rows else "rating"
    ratings = pd.to_numeric(rows.get(rating_column), errors="coerce")
    valid = ratings.notna() & (mins > 0)
    out["rating_media"] = round(float(np.average(ratings[valid], weights=mins[valid])), 2) if valid.any() else None
    out["ultimo_jogo"] = _safe_str(rows["match_date"].max()) if "match_date" in rows else ""
    date_values = rows["match_date"].dropna().astype(str) if "match_date" in rows else pd.Series(dtype=str)
    from src.squad.planner import national_team_key

    club_only = rows[~rows["team_name"].map(lambda t: bool(national_team_key(str(t or ""))))] if "team_name" in rows else rows
    if not club_only.empty:                              # seleção não é clube
        rows_c = club_only
        date_values = rows_c["match_date"].dropna().astype(str) if "match_date" in rows_c else pd.Series(dtype=str)
    else:
        rows_c = rows
    latest = rows_c.loc[date_values.idxmax()] if not date_values.empty else (rows_c.iloc[-1] if len(rows_c) else {})
    out["ultimo_time"] = _safe_str(latest.get("team_name", "")) if isinstance(latest, pd.Series) else ""
    out["ultima_competicao"] = _safe_str(latest.get("competition_name", "")) if isinstance(latest, pd.Series) else ""

    # load_player_history injeta _parsed_stats por jogador. Isso evita fazer json.loads repetidamente
    # em cada métrica, temporada e janela de 12 meses. Chamadas externas continuam aceitando stats_json.
    if "_parsed_stats" in rows:
        parsed_stats = [x if isinstance(x, dict) else {} for x in rows["_parsed_stats"].tolist()]
    else:
        parsed_stats = [_json_obj(x) for x in rows.get("stats_json", pd.Series(dtype=object)).tolist()]

    for out_key, raw_key in COUNT_KEYS.items():
        keys = _raw_keys(raw_key)
        vals = [next((_num(item.get(k)) for k in keys if _num(item.get(k)) is not None), None) for item in parsed_stats]
        vals = [value for value in vals if value is not None]
        out[out_key] = float(sum(vals)) if vals else None
    if out["minutos"] > 0:
        for k in P90_KEYS:
            v = out.get(k)
            out[k + "_p90"] = round(v * 90 / total_minutes, 3) if v is not None else None
    out["pass_accuracy_pct"] = None
    out["duels_won_pct"] = None
    for stat_key in ("accurate_passes_pct", "pass_accuracy", "pass_accuracy_pct"):
        vals = [_num(item.get(stat_key)) for item in parsed_stats]
        vals = [v for v in vals if v is not None]
        if vals:
            out["pass_accuracy_pct"] = round(float(np.mean(vals)), 2)
            break
    for stat_key in ("duels_won_pct", "duelsWonPercentage"):
        vals = [_num(item.get(stat_key)) for item in parsed_stats]
        vals = [v for v in vals if v is not None]
        if vals:
            out["duels_won_pct"] = round(float(np.mean(vals)), 2)
            break
    derived_rates(out)
    # O histórico pode chegar sem ordenação global (evita ordenar centenas de milhares de linhas no SQL).
    # A forma deve sempre refletir os cinco jogos mais recentes, independentemente da ordem de entrada.
    if "match_date" in rows:
        form_rows = pd.DataFrame({"match_date": rows["match_date"].astype(str), "rating": ratings})
        form_rows = form_rows.sort_values("match_date", ascending=True, kind="stable")
        form_values = pd.to_numeric(form_rows["rating"], errors="coerce").dropna().tail(5)
    else:
        form_values = ratings.dropna().tail(5)
    out["forma_5"] = [round(float(x), 2) for x in form_values.tolist()]
    return out


def _history_numeric(values: pd.Series) -> pd.Series:
    """Conversão numérica vetorizada equivalente ao _num usado nas estatísticas JSON."""
    numeric = pd.to_numeric(values, errors="coerce")
    needs_parse = numeric.isna() & values.notna()
    if needs_parse.any():
        text = values.loc[needs_parse].astype(str).str.strip().str.replace(",", ".", regex=False)
        text = text.mask(text.str.lower().isin({"", "-", "—", "nan", "none", "null"}))
        extracted = text.str.extract(r"(-?\d+(?:\.\d+)?)", expand=False)
        numeric.loc[needs_parse] = pd.to_numeric(extracted, errors="coerce")
    return numeric


def _history_group_totals(rows: pd.DataFrame, group_keys: List[str]) -> pd.DataFrame:
    """Agrega métricas de vários atletas/temporadas em operações vetorizadas do Pandas."""
    if rows.empty:
        return pd.DataFrame()

    grouped = rows.groupby(group_keys, dropna=False, sort=False, observed=True)
    out = pd.DataFrame(index=grouped.size().index)

    out["minutos"] = grouped["_minutes_num"].sum().fillna(0).astype(int)
    out["jogos"] = grouped["match_id"].nunique().astype(int)

    weighted = grouped["_rating_weight"].sum()
    weight_minutes = grouped["_rating_minutes"].sum()
    out["rating_media"] = (weighted / weight_minutes.replace(0, np.nan)).round(2)
    if {"_opponent_minutes", "_opponent_level_weight", "_opponent_adjustment_weight"} <= set(rows.columns):
        opponent_minutes = grouped["_opponent_minutes"].sum().replace(0, np.nan)
        out["nivel_adversario_medio"] = (grouped["_opponent_level_weight"].sum() / opponent_minutes).round(1)
        out["ajuste_adversario_medio"] = (grouped["_opponent_adjustment_weight"].sum() / opponent_minutes).round(3)
    else:
        out["nivel_adversario_medio"] = np.nan
        out["ajuste_adversario_medio"] = np.nan
    out["ultimo_jogo"] = grouped["match_date"].max().astype(str)

    metric_names = list(COUNT_KEYS)
    metric_sums = grouped[metric_names].sum(min_count=1)
    for name in metric_names:
        out[name] = metric_sums[name]

    for name in P90_KEYS:
        out[name + "_p90"] = (
            out[name] * 90 / out["minutos"].replace(0, np.nan)
        ).round(3)

    pass_means = grouped[["_pass_accurate_passes_pct", "_pass_pass_accuracy",
                          "_pass_pass_accuracy_pct"]].mean()
    pass_accuracy = pass_means["_pass_accurate_passes_pct"]
    pass_accuracy = pass_accuracy.combine_first(pass_means["_pass_pass_accuracy"])
    pass_accuracy = pass_accuracy.combine_first(pass_means["_pass_pass_accuracy_pct"])
    out["pass_accuracy_pct"] = pass_accuracy.round(2)

    duel_means = grouped[["_duels_duels_won_pct", "_duels_duelsWonPercentage"]].mean()
    duels = duel_means["_duels_duels_won_pct"].combine_first(
        duel_means["_duels_duelsWonPercentage"]
    )
    out["duels_won_pct"] = duels.round(2)
    derived_rates(out)

    # Uma única ordenação atende forma dos últimos cinco jogos e seleção do registro mais recente.
    chronological = rows.sort_values("match_date", ascending=True, kind="stable")
    # Reduz cada grupo a no máximo cinco avaliações válidas antes de construir as listas.
    # A implementação anterior executava uma função Python sobre todo o histórico de cada
    # atleta, mesmo descartando quase todas as linhas com tail(5).
    form_rows = chronological.loc[
        chronological["_rating_num"].notna(), group_keys + ["_rating_num"]
    ]
    form_rows = form_rows.groupby(
        group_keys, dropna=False, sort=False, observed=True
    ).tail(5)
    forms = form_rows.groupby(
        group_keys, dropna=False, sort=False, observed=True
    )["_rating_num"].agg(list).reindex(out.index)
    out["forma_5"] = forms.map(
        lambda values: [round(float(value), 2) for value in values]
        if isinstance(values, list) else []
    )

    # rodada 10: clube atual = último jogo por CLUBE (jogo de seleção não muda o clube: Yamal não é "do Spain")
    from src.squad.planner import national_team_key

    club_rows = chronological[~chronological["team_name"].map(lambda t: bool(national_team_key(str(t or ""))))]
    latest = (
        (club_rows if not club_rows.empty else chronological).drop_duplicates(group_keys, keep="last")
        .set_index(group_keys)
    )
    out["ultimo_time"] = latest["team_name"].reindex(out.index).fillna("")
    out["ultima_competicao"] = latest["competition_name"].reindex(out.index).fillna("")
    # rodada 27: todos os clubes por que ele jogou (para confirmar o cadastro do Transfermarkt que ainda mostra o clube
    # ANTERIOR — Zé Lucas no Sport já jogando pelo Cruzeiro ficava sem valor de mercado)
    try:
        if not club_rows.empty:
            cmap = {t: team_core(str(t)) for t in club_rows["team_name"].dropna().unique()}
            tmp = club_rows[group_keys].copy()
            tmp["_tc"] = club_rows["team_name"].map(cmap).fillna("")
            tmp = tmp[tmp["_tc"] != ""].drop_duplicates()
            th = tmp.groupby(group_keys, dropna=False, sort=False, observed=True)["_tc"].agg(
                lambda x: "|".join(sorted(set(x))))
            out["times_hist"] = th.reindex(out.index).fillna("")
    except Exception:
        pass
    return out


def fill_positions_from_lineups(db, raw: pd.DataFrame) -> pd.DataFrame:
    """Rodada 19: os números por jogador da FotMob vêm SEM posição (só o goleiro é marcado), mas a escalação do mesmo
    jogo traz a posição exata (CB, DM, RW…). Completa a posição vazia pela escalação — sem isso, quem só aparece na
    FotMob (Série B/C, ligas sul-americanas) ficava sem posição e era descartado do Scout."""
    if raw is None or raw.empty or "position" not in raw:
        return raw
    pos = raw["position"].fillna("").astype(str).str.strip()
    empty = pos.isin(["", "SUB", "?"])
    if not empty.any():
        return raw
    ids = sorted({int(x) for x in raw.loc[empty, "match_id"].dropna().unique()})
    if not ids:
        return raw
    try:
        with db.connect() as conn:
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pos_ids (match_id INTEGER PRIMARY KEY)")
            conn.execute("DELETE FROM _pos_ids")
            conn.executemany("INSERT OR IGNORE INTO _pos_ids VALUES (?)", [(i,) for i in ids])
            lu = pd.read_sql_query(
                """SELECT l.match_id, l.player_name, l.position FROM _pos_ids AS t
                   JOIN match_lineups AS l ON l.match_id = t.match_id
                   WHERE l.position IS NOT NULL AND TRIM(l.position) NOT IN ('', 'SUB', 'Sub')""", conn)
            conn.execute("DROP TABLE IF EXISTS _pos_ids")
    except Exception:
        return raw
    if lu.empty:
        return raw
    lu = lu.drop_duplicates(["match_id", "player_name"])
    key = dict(zip(zip(lu["match_id"].astype("int64"), lu["player_name"].astype(str)), lu["position"].astype(str)))
    out = raw.copy()
    idx = out.index[empty]
    fill = [key.get((int(m), str(n)), "") if pd.notna(m) else "" for m, n in zip(out.loc[idx, "match_id"], out.loc[idx, "player_name"])]
    out.loc[idx, "position"] = [f if f else o for f, o in zip(fill, pos.loc[idx])]
    return out


ACTIVE_DAYS = 365          # rodada 24: janela para "atleta ativo" (entra no universo mesmo sem cadastro de mercado)
ACTIVE_MIN_MINUTES = 90    # basta um jogo inteiro no último ano


def load_player_history(db, days: int = 900, player_names: Optional[Iterable[str]] = None,
                        progress: Optional[Callable[[str], None]] = None) -> pd.DataFrame:
    """Resume histórico completo dos atletas relevantes sem carregar todo o universo de aparições.

    Quando recebe nomes do catálogo de mercado, localiza primeiro as identidades presentes no banco
    e os atletas sem cadastro que atingiram a exposição mínima nos últimos 180 dias. Depois busca
    os cinco anos completos apenas dessas identidades. Chamadas antigas sem player_names preservam
    o comportamento de carregar todo o histórico.
    """
    report = progress if callable(progress) else (lambda _message: None)
    since = (date.today() - timedelta(days=int(days))).isoformat()
    # rodada 10: só competições masculinas (o mercado do Transfermarkt é masculino; nomes iguais não se misturam)
    query = f"""
        SELECT p.match_id, p.team_name, p.player_name, p.position, p.minutes, p.rating, p.stats_json,
               m.match_date, m.season_name, m.competition_name, m.home_team_name, m.away_team_name
        FROM match_player_stats p
        JOIN matches m ON m.match_id = p.match_id
        WHERE m.match_date >= ? AND COALESCE(p.minutes, 0) > 0{comp_sql([], "m")}
          AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
    """
    try:
        with db.connect() as conn:
            if player_names is None:
                raw = pd.read_sql_query(query, conn, params=[since])
            else:
                target_cores = {
                    player_core(name) for name in player_names
                    if name is not None and not pd.isna(name) and player_core(name)
                }

                # O índice começa por player_name: esta consulta percorre apenas o índice
                # compacto e dispensa 749 mil buscas individuais na tabela matches.
                report("Lendo nomes distintos registrados no banco...")
                known_names = [
                    str(row[0]) for row in conn.execute(
                        """SELECT DISTINCT player_name FROM match_player_stats
                           WHERE player_name IS NOT NULL AND TRIM(player_name) <> ''"""
                    )
                ]
                report(f"Nomes encontrados no banco: {len(known_names):,}")

                # Descobre jogadores sem cadastro Transfermarkt por jogos/minutos recentes.
                # CROSS JOIN fixa matches como tabela externa: usa o índice de data e consulta
                # as estatísticas pelo match_id, em vez de varrer o índice de todos os atletas.
                report("Identificando atletas ativos nos últimos 365 dias...")
                # rodada 24: todo atleta com minutos no último ano entra (antes 450 min e 4 jogos em 180 dias — a
                # Série B e as ligas sul-americanas ficavam com poucas centenas de jogadores)
                active_since = (date.today() - timedelta(days=ACTIVE_DAYS)).isoformat()
                has_covering_index = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                    ("idx_pstats_match_player_minutes",),
                ).fetchone() is not None
                if has_covering_index:
                    active_query = """
                        SELECT p.player_name, p.match_id, SUM(p.minutes) AS minutes
                        FROM matches AS m
                        CROSS JOIN match_player_stats AS p INDEXED BY idx_pstats_match_player_minutes
                        WHERE p.match_id = m.match_id
                          AND m.match_date >= ?
                          AND p.minutes > 0
                          AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
                        GROUP BY p.player_name, p.match_id
                    """
                else:
                    active_query = """
                        SELECT p.player_name, p.match_id, SUM(COALESCE(p.minutes, 0)) AS minutes
                        FROM matches AS m
                        CROSS JOIN match_player_stats AS p INDEXED BY idx_pstats_match
                        WHERE p.match_id = m.match_id
                          AND m.match_date >= ?
                          AND COALESCE(p.minutes, 0) > 0
                          AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
                        GROUP BY p.player_name, p.match_id
                    """
                active_rows = pd.read_sql_query(active_query, conn, params=[active_since])
                if active_rows.empty:
                    active_cores = set()
                else:
                    # Normaliza antes de aplicar a exposição mínima: o mesmo atleta pode
                    # aparecer com grafias diferentes em fontes distintas.
                    active_rows["_core"] = active_rows["player_name"].map(player_core)
                    active_totals = active_rows.groupby("_core").agg(
                        minutos=("minutes", "sum"),
                        jogos=("match_id", "nunique"),
                    )
                    active_cores = set(active_totals.index[
                        (active_totals["minutos"] >= ACTIVE_MIN_MINUTES) & (active_totals["jogos"] >= 1)
                    ])
                report(f"Atletas ativos elegíveis: {len(active_cores):,}")
                relevant_cores = target_cores | active_cores
                selected_names = sorted({
                    name for name in known_names if player_core(name) in relevant_cores
                })

                report(f"Nomes selecionados para histórico: {len(selected_names):,}")
                if not selected_names:
                    return pd.DataFrame()

                # A tabela temporária evita limites de parâmetros SQL e permite começar pelos
                # nomes elegíveis usando idx_pstats_player, sem cortar o histórico de cinco anos.
                conn.execute(
                    "CREATE TEMP TABLE scout_relevant_players (player_name TEXT PRIMARY KEY)"
                )
                conn.executemany(
                    "INSERT OR IGNORE INTO scout_relevant_players (player_name) VALUES (?)",
                    [(name,) for name in selected_names],
                )
                selected_query = """
                    SELECT p.match_id, p.team_name, p.player_name, p.position, p.minutes, p.rating, p.stats_json,
                           m.match_date, m.season_name, m.competition_name, m.home_team_name, m.away_team_name
                    FROM scout_relevant_players AS r
                    CROSS JOIN match_player_stats AS p INDEXED BY idx_pstats_player
                    JOIN matches AS m ON m.match_id = p.match_id
                    WHERE p.player_name = r.player_name
                      AND m.match_date >= ?
                      AND COALESCE(p.minutes, 0) > 0
                      AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
                """
                report("Carregando partidas dos atletas selecionados...")
                raw = pd.read_sql_query(selected_query, conn, params=[since])
                report(f"Registros históricos carregados: {len(raw):,}")
    except Exception as exc:
        report(f"Falha ao consultar o histórico do Scout: {type(exc).__name__}: {exc}")
        return pd.DataFrame()
    if raw.empty:
        report("Nenhum registro de histórico encontrado para os jogadores selecionados.")
        return raw

    try:                                                 # rodada 20: seleção de base conta como PROMESSA, não como clube
        from src.data_hub.sources.fotmob import YOUTH_NAMES

        raw = raw[~raw["competition_name"].isin(YOUTH_NAMES)]
    except Exception:
        pass
    if raw.empty:
        return raw
    raw = fill_positions_from_lineups(db, raw)
    report("Normalizando nomes e partidas do histórico...")
    # Normaliza cada nome/clube uma única vez, não uma vez por aparição do jogador.
    player_names = raw["player_name"].dropna().drop_duplicates().tolist()
    player_map = {name: player_core(name) for name in player_names}
    raw["_core"] = raw["player_name"].map(player_map)

    club_values = pd.concat(
        [raw["team_name"], raw["home_team_name"], raw["away_team_name"]],
        ignore_index=True,
    ).dropna().drop_duplicates().tolist()
    club_map = {name: team_core(name) for name in club_values}
    raw["_club_core"] = raw["team_name"].map(club_map)
    raw = assign_person_ids(raw)

    # A chave do confronto depende só dos metadados da partida; calculá-la no nível de match_id
    # elimina um apply(axis=1) sobre centenas de milhares de aparições.
    fixtures = raw[["match_id", "match_date", "home_team_name", "away_team_name"]].drop_duplicates("match_id").copy()
    home = fixtures["home_team_name"].map(club_map).fillna("")
    away = fixtures["away_team_name"].map(club_map).fillna("")
    swap = home > away
    first = home.where(~swap, away)
    second = away.where(~swap, home)
    fixtures["_fixture"] = fixtures["match_date"].astype(str).str[:10] + "|" + first + "|" + second
    fixture_map = fixtures.set_index("match_id")["_fixture"]
    raw["_fixture"] = raw["match_id"].map(fixture_map)

    duplicate_mask = raw.duplicated(["_pid", "_fixture", "_club_core"], keep=False)
    raw["_richness"] = 0
    if duplicate_mask.any():
        # Riqueza só é necessária para escolher entre duplicatas do mesmo jogo real.
        raw.loc[duplicate_mask, "_richness"] = raw.loc[duplicate_mask, "stats_json"].map(
            lambda value: len(_json_obj(value))
        )
    raw = raw.sort_values(["_richness", "minutes"], ascending=False).drop_duplicates(
        ["_pid", "_fixture", "_club_core"], keep="first"
    )

    # Decodifica cada JSON uma única vez e transforma as métricas em colunas numéricas.
    # As somas por carreira, temporada e 12 meses passam a ser feitas pelo groupby vetorizado.
    stat_fields = list(dict.fromkeys(
        [k for v in COUNT_KEYS.values() for k in _raw_keys(v)] +
        ["accurate_passes_pct", "pass_accuracy", "pass_accuracy_pct",
         "duels_won_pct", "duelsWonPercentage"]
    ))
    report(f"Decodificando métricas JSON de {len(raw):,} registros...")
    stat_frame = pd.DataFrame.from_records(
        raw["stats_json"].map(_json_obj).tolist(), columns=stat_fields, index=raw.index
    )
    report("Convertendo métricas JSON para colunas numéricas...")
    for out_key, raw_key in COUNT_KEYS.items():
        col = pd.Series(np.nan, index=raw.index)
        for k in _raw_keys(raw_key):
            if k in stat_frame:
                col = col.combine_first(_history_numeric(stat_frame[k]))
        raw[out_key] = col

    for field in ("accurate_passes_pct", "pass_accuracy", "pass_accuracy_pct"):
        raw[f"_pass_{field}"] = (
            _history_numeric(stat_frame[field]) if field in stat_frame else np.nan
        )
    for field in ("duels_won_pct", "duelsWonPercentage"):
        raw[f"_duels_{field}"] = (
            _history_numeric(stat_frame[field]) if field in stat_frame else np.nan
        )
    del stat_frame

    raw["_minutes_num"] = pd.to_numeric(raw["minutes"], errors="coerce").fillna(0)
    raw["_rating_source"] = pd.to_numeric(raw["rating"], errors="coerce")

    # Ajusta a nota média de cada atuação pelo Elo pré-jogo do adversário. O cálculo é em lote
    # (uma vez por partida/equipe, nunca uma consulta por jogador) e falha em modo neutro.
    try:
        from src.analytics.opponent_strength import opponent_strength_for_matches

        match_teams = raw[["match_id", "team_name"]].drop_duplicates()
        strength_map = opponent_strength_for_matches(db, match_teams.itertuples(index=False, name=None))
        keys = [(int(mid), str(team or "")) for mid, team in
                raw[["match_id", "team_name"]].itertuples(index=False, name=None)]
        raw["_opponent_adjustment"] = [strength_map.get(k, {}).get("ajuste", 0.0) for k in keys]
        raw["_opponent_level"] = [strength_map.get(k, {}).get("nivel") for k in keys]
    except Exception as exc:
        report(f"Contexto de adversários indisponível; mantendo notas originais: {type(exc).__name__}: {exc}")
        raw["_opponent_adjustment"] = 0.0
        raw["_opponent_level"] = np.nan

    raw["_rating_num"] = raw["_rating_source"] + pd.to_numeric(
        raw["_opponent_adjustment"], errors="coerce"
    ).fillna(0)
    raw["rating_ajustada"] = raw["_rating_num"].round(2)
    valid_minutes = raw["_minutes_num"].where(raw["_rating_num"].notna(), 0)
    raw["_rating_minutes"] = valid_minutes
    raw["_rating_weight"] = raw["_rating_num"].fillna(0) * valid_minutes
    opponent_level = pd.to_numeric(raw["_opponent_level"], errors="coerce")
    raw["_opponent_minutes"] = raw["_minutes_num"].where(opponent_level.notna(), 0)
    raw["_opponent_level_weight"] = opponent_level.fillna(0) * raw["_opponent_minutes"]
    raw["_opponent_adjustment_weight"] = pd.to_numeric(raw["_opponent_adjustment"], errors="coerce").fillna(0) * raw["_opponent_minutes"]

    report("Calculando totais da carreira por jogador...")
    career = _history_group_totals(raw, ["_pid"])
    # rodada 25: números por 90 com PESO NO TEMPO — último ano vale 1, de 1 a 2 anos 0,6, de 2 a 5 anos 0,25 (por
    # minuto). Lesão longa não apaga o jogador (os anos anteriores ainda contam) e a temporada atual manda.
    try:
        age_days = (pd.Timestamp.today().normalize() - pd.to_datetime(raw["match_date"], errors="coerce")).dt.days
        tw = np.where(age_days <= 365, 1.0, np.where(age_days <= 730, .6, .25))
        mins_w = (raw["_minutes_num"] * tw).groupby(raw["_pid"]).sum()
        career["minutos_ponderados"] = mins_w.reindex(career.index).round(0)
        rate_pairs = {"pass_rate_pct": ("passes_acc", "passes_tot"), "duel_rate_pct": ("duel_won", "_dt"),
                      "aerial_pct": ("aerials_won", "aerials_tot"), "dribble_pct": ("dribbles", "dribbles_tot"),
                      "cross_pct": ("crosses_acc", "crosses_tot"), "long_ball_pct": ("long_balls", "long_balls_tot"),
                      "shot_acc_pct": ("shots_on_target", "shots")}
        tmp = pd.DataFrame({"_pid": raw["_pid"]})
        tmp["_dt"] = (raw["duel_won"].fillna(0) + raw["duel_lost"].fillna(0)) * tw
        for k in set(P90_KEYS) | {"passes_acc", "passes_tot", "duel_won", "aerials_tot", "dribbles_tot", "crosses_tot",
                                  "long_balls_tot"}:
            if k in raw:
                tmp[k] = pd.to_numeric(raw[k], errors="coerce") * tw
        sums = tmp.groupby("_pid").sum(min_count=1)
        for k in P90_KEYS:
            if k in sums:
                career[f"{k}_p90w"] = (sums[k] * 90 / mins_w.replace(0, np.nan)).reindex(career.index).round(3)
        if "passes_acc" in sums:
            career["passes_acc_p90w"] = (sums["passes_acc"] * 90 / mins_w.replace(0, np.nan)).reindex(career.index).round(2)
        if "duel_won" in sums:
            career["duel_won_p90w"] = (sums["duel_won"] * 90 / mins_w.replace(0, np.nan)).reindex(career.index).round(2)
        for out_k, (a, b) in rate_pairs.items():
            if a in sums and b in sums:
                career[f"{out_k}_w"] = (100 * sums[a] / sums[b].where(sums[b] >= 6)).reindex(career.index).round(1)
    except Exception as exc:
        report(f"Peso no tempo indisponível ({type(exc).__name__}); usando os totais do período: {exc}")

    report("Calculando totais por temporada...")
    raw["_season_group"] = raw["season_name"].where(
        raw["season_name"].notna(), "__SEASON_NOT_IDENTIFIED__"
    )
    season_totals = _history_group_totals(raw, ["_pid", "_season_group"])
    if not season_totals.empty:
        season_rows = season_totals.reset_index()
        season_rows["temporada"] = season_rows["_season_group"].replace(
            {"__SEASON_NOT_IDENTIFIED__": "não identificada"}
        )
        season_rows = season_rows.sort_values(
            ["_pid", "temporada"], ascending=True, kind="stable"
        )
        season_by_core = {
            core: group.drop(columns=["_pid", "_season_group"]).to_dict("records")
            for core, group in season_rows.groupby("_pid", sort=False)
        }
    else:
        season_by_core = {}

    report("Calculando janela dos últimos 12 meses...")
    recent_cutoff = (pd.Timestamp.today().normalize() - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    recent_rows = raw.loc[raw["match_date"].astype(str) >= recent_cutoff]
    recent_totals = _history_group_totals(recent_rows, ["_pid"]) if not recent_rows.empty else pd.DataFrame()

    ordered = raw.sort_values("match_date", ascending=False, kind="stable")
    latest = ordered.drop_duplicates("_pid", keep="first").set_index("_pid")
    recent_games = ordered.groupby("_pid", sort=False, group_keys=False).head(15)
    games_by_core = {
        # rodada 26: sem o stats_json de cada jogo (nenhuma tela usa e deixava a fotografia do Scout gigante)
        core: group[["match_date", "team_name", "competition_name", "minutes", "rating",
                     "rating_ajustada", "_opponent_level", "_opponent_adjustment"]]
        .to_dict("records")
        for core, group in recent_games.groupby("_pid", sort=False)
    }
    # rodada 19: registro sem posição (FotMob só marca o goleiro nos números por jogador) não vota na posição
    _pos = raw["position"].fillna("").astype(str).str.strip()
    _pos = _pos[~_pos.isin(["", "SUB", "Sub", "sub", "?"])]
    positions = (_pos.groupby(raw.loc[_pos.index, "_pid"], sort=False).agg(lambda v: v.mode().iloc[0])
                 if len(_pos) else pd.Series(dtype=str))

    recent_by_core = recent_totals.to_dict("index") if not recent_totals.empty else {}
    season_by_core = season_by_core or {}
    summaries = []
    career_by_core = career.to_dict("index") if not career.empty else {}
    for core, all_data in career_by_core.items():
        recent = recent_by_core.get(core, {})
        all_data["nome_observado"] = _safe_str(latest.at[core, "player_name"])
        all_data["posicao_observada"] = _safe_str(positions.get(core, ""))
        all_data["nacionalidade_observada"] = None
        all_data["pid"] = core
        all_data["core_nome"] = _safe_str(latest.at[core, "_core"])
        all_data["fotmob_id"] = latest.at[core, "_fid"] if "_fid" in latest else None
        all_data.update({
            "minutos_12m": int(recent.get("minutos", 0) or 0),
            "jogos_12m": int(recent.get("jogos", 0) or 0),
            "rating_12m": recent.get("rating_media"),
            "nivel_adversario_12m": recent.get("nivel_adversario_medio"),
            "ajuste_adversario_12m": recent.get("ajuste_adversario_medio"),
            "gols_12m": recent.get("goals"),
            "assistencias_12m": recent.get("assists"),
            "xg_12m": recent.get("xg"),
            "xa_12m": recent.get("xa"),
            "historico_temporadas": season_by_core.get(core, [])[-5:],
            "ultimos_jogos": games_by_core.get(core, []),
        })
        summaries.append({"core": core, **all_data})

    result = pd.DataFrame(summaries)
    if not result.empty:
        # rodada 24: "core" continua sendo o núcleo do nome quando só existe UMA pessoa com ele; homônimos (dois
        # "Otávio" com ids diferentes na FotMob, ou o mesmo nome em clubes diferentes sem id) ficam separados
        dup = result["core_nome"].duplicated(keep=False)
        result["core"] = result["core_nome"].where(~dup, result["core_nome"] + "#" + result["pid"].astype(str))
        result["homonimo"] = dup
        result = attach_roster_identity(db, result)
    report(f"Histórico agregado: {len(result):,} jogadores")
    return result


def assign_person_ids(raw: pd.DataFrame) -> pd.DataFrame:
    """Rodada 24 — identidade da PESSOA em cada registro de jogo, nunca só pelo nome.

    1) registro com id do atleta na FotMob → "fm<id>" (o mesmo id junta grafias diferentes);
    2) registro sem id (ESPN, API-Football…) → o id FotMob do MESMO nome no MESMO clube, se houver um só;
    3) sem id e sem casamento pelo clube, mas o nome tem id em outro clube → pessoa separada "nm:<nome>|<clube>"
       (pode ser homônimo; só se junta quando nome, clube e época batem);
    4) nome que nunca aparece com id → "nm:<nome>" (comportamento antigo das bases sem id)."""
    r = raw
    sj = r["stats_json"].astype(str) if "stats_json" in r else pd.Series("", index=r.index)
    fid = pd.to_numeric(sj.str.extract(r'"fotmob_id"\s*:\s*"?(\d+)', expand=False), errors="coerce")
    r["_fid"] = fid
    has = fid.notna()
    pid = pd.Series("fm" + fid.astype("Int64").astype(str), index=r.index).where(has, "")
    if has.any():
        w = r.loc[has, ["_core", "_club_core", "_fid"]]
        g = w.groupby(["_core", "_club_core"])["_fid"].agg(["first", "nunique"])
        by_club = g["first"].where(g["nunique"] == 1)
        club_key = list(zip(r["_core"], r["_club_core"].fillna("")))
        hit = pd.Series([by_club.get(k, np.nan) for k in club_key], index=r.index)
        cores_with_id = set(w["_core"])
        none = ~has
        ok = none & hit.notna()
        pid[ok] = "fm" + hit[ok].astype("int64").astype(str)
        r.loc[ok, "_fid"] = hit[ok]
        other = none & ~ok & r["_core"].isin(cores_with_id)
        pid[other] = "nm:" + r.loc[other, "_core"].astype(str) + "|" + r.loc[other, "_club_core"].fillna("").astype(str)
    rest = pid.eq("")
    pid[rest] = "nm:" + r.loc[rest, "_core"].astype(str)
    r["_pid"] = pid
    # o núcleo de nome exibido de cada pessoa = o mais comum entre os registros dela (grafias diferentes, mesma pessoa)
    cnt = r.groupby(["_pid", "_core"]).size().reset_index(name="n").sort_values("n", kind="stable")
    mode_core = cnt.drop_duplicates("_pid", keep="last").set_index("_pid")["_core"]
    r["_core"] = r["_pid"].map(mode_core)
    return r


def attach_roster_identity(db, hist: pd.DataFrame) -> pd.DataFrame:
    """Nascimento, país, valor, altura, posição e clube inscrito pelo elenco da FotMob (mesmo id do atleta)."""
    cols = {"birth": "nascimento_fm", "country": "nacionalidade_fm", "market_value": "valor_fm",
            "height": "altura_fm", "position": "posicao_fm", "team": "clube_fm"}
    for c in cols.values():
        if c not in hist:
            hist[c] = None
    ids = pd.to_numeric(hist.get("fotmob_id"), errors="coerce")
    if ids.notna().sum() == 0:
        return hist
    try:
        with db.connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'fotmob_rosters'").fetchone():
                return hist
            ro = pd.read_sql_query("SELECT player_id, team, birth, country, market_value, height, position, fetched_at "
                                   "FROM fotmob_rosters", conn)
    except Exception:
        return hist
    if ro.empty:
        return hist
    try:
        from src.squad.planner import national_team_key

        ro = ro[[not national_team_key(str(t or "")) for t in ro["team"]]]
    except Exception:
        pass
    ro = ro.sort_values("fetched_at").drop_duplicates("player_id", keep="last").set_index("player_id")
    key = ids.astype("Int64")
    for src_col, dst in cols.items():
        hist[dst] = key.map(ro[src_col]).where(key.notna(), None)
    return hist


def _history_map(history: Optional[pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
    if history is None or history.empty or "core" not in history:
        return {}
    return {str(r["core"]): r.to_dict() for _, r in history.iterrows()}


def _fam_of(pos: Any) -> str:
    r = _role(pos, "") if _safe_str(pos) else ""
    return "GK" if r == "GK" else ("" if not r else "OUT")


# só palavras que não identificam o clube ("Atlético", "Real", "Sporting" identificam: Nacional ≠ Atlético Nacional)
_GENERIC_CLUB = {"club", "clube", "fc", "sc", "ac", "cd", "ca", "esporte", "de", "do", "da", "futebol", "football"}
_CLUB_SUFFIX = {"club", "clube", "esporte", "de", "do", "da", "futebol", "football", "balompie", "futbol", "calcio", "sad", "saf", "sau", "regatas", "e", "y", "gremio",
                                "recreativo", "associacao", "associação", "sociedade", "esportiva"}


def _club_like(a: str, b: str) -> bool:
    """Rodada 27: mesmo clube com nome mais curto/mais longo ("real betis" × "real betis balompie",
    "zenit st petersburg" × "zenit sankt petersburg") — palavras próprias em comum, sem contar as genéricas."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if long_.startswith(short + " "):           # só quando o que sobra é "enfeite" do nome (Balompié, Futebol Clube…)
        extra = set(long_[len(short):].split())
        return extra <= _CLUB_SUFFIX
    ta = {w for w in a.split() if w not in _GENERIC_CLUB and len(w) >= 3}
    tb = {w for w in b.split() if w not in _GENERIC_CLUB and len(w) >= 3}
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= .66


def match_market_to_history(p: pd.DataFrame, hist: pd.DataFrame) -> pd.Series:
    """Rodada 24 — cadastro (Transfermarkt) × pessoas do histórico. Nunca só pelo nome:
    nascimento diferente (> 13 meses) ou goleiro × jogador de linha = pessoas diferentes; clube igual, nascimento igual
    e nacionalidade igual somam confiança. Nome repetido no cadastro só casa com confiança (clube ou nascimento) e
    cada pessoa do histórico vai para no máximo uma linha do cadastro. Sem casamento seguro, os dois ficam separados."""
    out = pd.Series([None] * len(p), index=p.index, dtype=object)
    if hist is None or hist.empty or "core" not in hist:
        return out
    h = hist.copy()
    if "core_nome" not in h:
        h["core_nome"] = h["core"]
    h["core_nome"] = h["core_nome"].fillna(h["core"]).astype(str)
    cand_by_name: Dict[str, List[Dict[str, Any]]] = {}
    for rec in h[[c for c in ("core", "core_nome", "ultimo_time", "clube_fm", "posicao_observada", "posicao_fm",
                              "nascimento_fm", "nacionalidade_fm", "minutos_12m", "times_hist") if c in h]].to_dict("records"):
        cand_by_name.setdefault(rec["core_nome"], []).append(rec)
    # rodada 27: o nome muda entre as fontes ("Kaiki" × "Kaiki Bruno", "Gleison Bremer" × "Bremer", "Khéphren
    # Thuram-Ulien" × "Khéphren Thuram"). Índice por palavra do nome para achar esses casos — só valem com o CLUBE
    # conferindo (e sem nascimento/posição em conflito).
    tok_index: Dict[str, List[Dict[str, Any]]] = {}
    for recs in cand_by_name.values():
        for rec in recs:
            for w in set(str(rec["core_nome"]).split()):
                if len(w) >= 4:
                    tok_index.setdefault(w, []).append(rec)
    tm_dup = p["_core"].duplicated(keep=False)
    births = pd.to_datetime(p.get("nascimento"), errors="coerce")
    scored: List[Tuple[float, Any, str]] = []
    for i, core, club, pos, fun, nat, dup in zip(p.index, p["_core"].astype(str), p["clube"], p["posicao"], p["funcao"],
                                                 p["nacionalidade"], tm_dup):
        club_c = team_core(_safe_str(club)) if _safe_str(club) else ""
        fam = "GK" if _role(pos, fun) == "GK" else "OUT"
        b0 = births.get(i)
        nat_c = _country_core(nat) if _safe_str(nat) else ""

        def fuzzy_cands():
            mine = set(core.split())
            pool = {id(r): r for w in mine if len(w) >= 4 for r in tok_index.get(w, [])}.values()
            return [r for r in pool if r["core_nome"] != core and
                    (mine < set(str(r["core_nome"]).split()) or set(str(r["core_nome"]).split()) < mine)]

        cands = cand_by_name.get(core)
        fuzzy = False
        if not cands:
            cands, fuzzy = fuzzy_cands(), True
            if not cands or len(cands) > 40:
                continue
        options = _market_options(cands, fuzzy, club_c, fam, b0, nat_c)
        if not options and not fuzzy:
            # rodada 27e: o nome exato existe, mas é OUTRA pessoa (o "Otávio" do Paris FC) — tenta o nome mais longo do
            # mesmo clube ("Otavio Costa", goleiro do Cruzeiro), que antes nunca era tentado
            fc = fuzzy_cands()
            if fc and len(fc) <= 40:
                options = _market_options(fc, True, club_c, fam, b0, nat_c)
                cands = fc
        if not options:
            continue
        options.sort(key=lambda t: -t[0])
        best = options[0]
        tie = len(options) > 1 and options[1][0] == best[0]
        # rodada 25b: nome de UMA palavra (Saúl, Fred, Gerson, Otávio) é homônimo em potencial mesmo quando só aparece
        # uma vez no cadastro — juntar só com clube ou nascimento conferindo (Saúl de 41 anos era outro Saúl)
        mononym = len(core.split()) == 1
        if mononym and best[0] < 2:
            continue
        if dup or len(cands) > 1:
            if best[0] < 2 or tie:
                continue                                        # homônimo sem confirmação: fica separado
        scored.append((best[0], i, best[1]))
    taken: set = set()
    for score, i, key in sorted(scored, key=lambda t: -t[0]):
        if key in taken:
            continue
        taken.add(key)
        out.at[i] = key
    return out


def _market_options(cands, fuzzy, club_c, fam, b0, nat_c):
    """Pontua cada pessoa candidata do histórico para uma linha do cadastro (ver match_market_to_history)."""
    options = []
    if True:
        for c in cands:
            score = 0.0
            b1 = pd.to_datetime(c.get("nascimento_fm"), errors="coerce")
            if pd.notna(b0) and pd.notna(b1):
                if abs((b0 - b1).days) > 400:
                    continue                                    # outra pessoa
                score += 3
            cf = _fam_of(c.get("posicao_fm")) or _fam_of(c.get("posicao_observada"))
            if cf and cf != fam:
                continue                                        # goleiro × linha
            clubs = {team_core(_safe_str(c.get(k))) for k in ("ultimo_time", "clube_fm") if _safe_str(c.get(k))}
            past = {x for x in str(c.get("times_hist") or "").split("|") if x}
            same_club = bool(club_c) and any(_club_like(club_c, x) for x in clubs | past)
            if fuzzy and not same_club:
                continue                                        # nome diferente só junta com o clube conferindo
            if same_club:
                score += 2
            n1 = _country_core(c.get("nacionalidade_fm")) if _safe_str(c.get("nacionalidade_fm")) else ""
            if nat_c and n1:
                if nat_c == n1 or n1 in nat_c or nat_c in n1:
                    score += 1
                elif not same_club and score < 3:
                    continue                                    # país e clube diferentes, sem nascimento: não junta
            options.append((score, c["core"]))
    return options


def build_market_universe(tm_players: Optional[pd.DataFrame], history: Optional[pd.DataFrame] = None,
                          club_values: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Universo de atletas: cadastro de mercado + histórico estatístico multi-clube."""
    p = tm_players.copy() if tm_players is not None else pd.DataFrame()
    for col in ("nome", "clube", "posicao", "funcao", "nascimento", "nacionalidade", "transfermarkt_id",
                "clube_id", "valor_mercado_eur", "fim_contrato", "ultima_temporada"):
        if col not in p:
            p[col] = pd.Series(dtype=object)
    p["nome"] = p["nome"].fillna("").astype(str)
    p = p[p["nome"].str.strip() != ""].copy()
    for col in ("historico_temporadas", "ultimos_jogos", "clube_tm", "clube_observado", "fonte_clube_observado",
                "historico_ambiguo", "sem_cadastro_mercado"):
        if col not in p:
            p[col] = None
    p["_core"] = p["nome"].map(player_core)
    p["_role"] = [_role(x, y) for x, y in zip(p["posicao"], p["funcao"])]
    p["papel"] = p["_role"]
    p["funcao_legivel"] = p["_role"].map(ROLE_LABELS).fillna(p["funcao"].fillna(""))
    born = pd.to_datetime(p["nascimento"], errors="coerce")
    p["idade"] = ((pd.Timestamp.today().normalize() - born).dt.days / 365.25).round(1)
    p["valor_mercado_eur"] = pd.to_numeric(p["valor_mercado_eur"], errors="coerce")
    p["fim_contrato"] = pd.to_datetime(p["fim_contrato"], errors="coerce")
    # Cruza o histórico por chave em uma operação vetorizada.
    # A implementação anterior percorria o catálogo inteiro com iterrows() e atualizava célula por célula.
    history_frame = history.copy() if history is not None and not history.empty and "core" in history else pd.DataFrame()
    history_columns: List[str] = []
    if not history_frame.empty:
        history_frame["core"] = history_frame["core"].map(_safe_str)
        history_frame = history_frame[history_frame["core"] != ""].drop_duplicates("core", keep="last")
        history_columns = [col for col in history_frame.columns if col != "core"]
        for col in history_columns:
            if col not in p:
                p[col] = None

    # rodada 24: cada linha do cadastro só recebe o histórico de UMA pessoa e só quando a identidade confere —
    # mesmo nome + (clube, nascimento, posição de goleiro × linha, nacionalidade). Homônimo vira perfil próprio.
    p["_hkey"] = None
    p["historico_ambiguo"] = False
    if history_columns:
        p["_hkey"] = match_market_to_history(p, history_frame)
    matched = p["_hkey"].notna()
    if history_columns and matched.any():
        base_columns = set(p.columns)
        attach = history_frame[history_frame["core"].isin(set(p.loc[matched, "_hkey"]))].copy()
        attach["__history_present"] = True
        rename = {col: f"__history_{col}" for col in history_columns}
        attach = attach.rename(columns=rename)
        p = p.merge(attach, left_on="_hkey", right_on="core", how="left", sort=False, validate="many_to_one")
        matched = p["__history_present"].fillna(False).astype(bool)
        for col in history_columns:
            hist_col = f"__history_{col}"
            if hist_col in p:
                if col in base_columns:
                    p[col] = p[hist_col].where(matched, p[col])
                else:
                    p[col] = p[hist_col]
                p = p.drop(columns=[hist_col])
        p = p.drop(columns=["core", "__history_present"], errors="ignore")
    else:
        matched = pd.Series(False, index=p.index)

    # As coleções continuam serializadas como JSON, como espera o restante do Scout.
    for col in ("historico_temporadas", "ultimos_jogos"):
        if col not in p:
            p[col] = "[]"
        else:
            p.loc[~matched, col] = "[]"
            p.loc[matched, col] = p.loc[matched, col].map(
                lambda value: json.dumps(value if isinstance(value, (list, dict)) else [],
                                         ensure_ascii=False, default=str)
            )
    history_names = set(history_frame["core_nome"].astype(str)) if "core_nome" in history_frame else \
        (set(history_frame["core"].astype(str)) if not history_frame.empty else set())
    ambiguous = ~matched & p["_core"].astype(str).isin(history_names) & p["_core"].duplicated(keep=False)
    p.loc[ambiguous, "historico_ambiguo"] = True
    no_history = ~matched & ~ambiguous
    p.loc[no_history, "clube_observado"] = False
    p.loc[no_history, "fonte_clube_observado"] = "cadastro Transfermarkt"

    # Se o cadastro de mercado ficou atrasado, usa o clube da última partida recente como observação,
    # preservando o clube do Transfermarkt em clube_tm.
    if "ultimo_jogo" in p and "ultimo_time" in p:
        observed_club = p["ultimo_time"].map(_safe_str)
        last_game = pd.to_datetime(p["ultimo_jogo"], errors="coerce")
        recent = matched & observed_club.ne("") & last_game.notna() & (
            last_game >= pd.Timestamp.today().normalize() - pd.Timedelta(days=150)
        )
        not_recent = matched & ~recent
        p.loc[recent, "clube_tm"] = p.loc[recent, "clube"]
        p.loc[recent, "clube"] = observed_club.loc[recent]
        p.loc[recent, "clube_observado"] = True
        p.loc[recent, "fonte_clube_observado"] = "última partida FotMob nos últimos 150 dias"
        p.loc[not_recent, "clube_observado"] = False
        p.loc[not_recent, "fonte_clube_observado"] = "cadastro Transfermarkt"
    if club_values is not None and not club_values.empty:
        vals = club_values.copy()
        if {"transfermarkt_id", "valor_mercado_eur"} <= set(vals.columns):
            vals["valor_mercado_eur"] = pd.to_numeric(vals["valor_mercado_eur"], errors="coerce")
            vals = vals.dropna(subset=["valor_mercado_eur"])
            if "data" in vals:
                vals["_data"] = pd.to_datetime(vals["data"], errors="coerce")
                vals = vals.sort_values("_data")
            else:
                vals = vals.sort_values("valor_mercado_eur")
            latest = vals.drop_duplicates("transfermarkt_id", keep="last")
            vmap = latest.set_index(latest["transfermarkt_id"].astype(str))["valor_mercado_eur"].to_dict()
            p["_valor_historico"] = p["transfermarkt_id"].astype(str).map(vmap)
            p["valor_tm_atual"] = p["valor_mercado_eur"]
            p["valor_mercado_eur"] = p["valor_mercado_eur"].combine_first(p["_valor_historico"])
            if "data" in vals:
                cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=365)
                recent = vals[vals["_data"] >= cutoff]
                if not recent.empty:
                    med = recent.groupby(recent["transfermarkt_id"].astype(str))["valor_mercado_eur"].median().to_dict()
                    latest_recent = recent.drop_duplicates("transfermarkt_id", keep="last")
                    latest_recent_map = latest_recent.set_index(latest_recent["transfermarkt_id"].astype(str))[
                        "valor_mercado_eur"].to_dict()
                    first_recent = recent.drop_duplicates("transfermarkt_id", keep="first")
                    first_recent_map = first_recent.set_index(first_recent["transfermarkt_id"].astype(str))[
                        "valor_mercado_eur"].to_dict()
                    p["valor_tm_media_12m"] = p["transfermarkt_id"].astype(str).map(med)
                    p["valor_tm_ultima_avaliacao"] = p["transfermarkt_id"].astype(str).map(latest_recent_map)
                    first_value = p["transfermarkt_id"].astype(str).map(first_recent_map)
                    last_value = p["valor_tm_ultima_avaliacao"]
                    p["variacao_tm_12m_pct"] = ((last_value - first_value) / first_value.abs().replace(0, np.nan) * 100).round(1)
                cut3 = pd.Timestamp.today().normalize() - pd.Timedelta(days=3 * 365)
                v3 = vals[vals["_data"] >= cut3]
                if not v3.empty:
                    p["valor_pico_3a_eur"] = p["transfermarkt_id"].astype(str).map(
                        v3.groupby(v3["transfermarkt_id"].astype(str))["valor_mercado_eur"].max().to_dict())
            else:
                p["valor_tm_media_12m"] = np.nan
                p["valor_tm_ultima_avaliacao"] = np.nan
                p["variacao_tm_12m_pct"] = np.nan
    # Amplia o universo com atletas ausentes do cadastro TM, mas observados recentemente em escalações
    # e com exposição mínima. Sem idade, contrato ou valor publicados, esses campos ficam vazios.
    if history is not None and not history.empty and "core" in history:
        known = set(p["_hkey"].dropna().astype(str)) if "_hkey" in p else set(p["_core"].dropna().astype(str))
        # Filtra vetorialmente o histórico antes de montar os atletas sem cadastro de mercado.
        extra_history = history.copy()
        extra_history["_scout_core"] = extra_history["core"].map(_safe_str)
        extra_last_game = pd.to_datetime(
            extra_history.get("ultimo_jogo", pd.Series(index=extra_history.index, dtype=object)),
            errors="coerce",
        )
        extra_minutes = pd.to_numeric(
            extra_history.get("minutos_12m", pd.Series(0, index=extra_history.index)), errors="coerce"
        ).fillna(0)
        extra_games = pd.to_numeric(
            extra_history.get("jogos_12m", pd.Series(0, index=extra_history.index)), errors="coerce"
        ).fillna(0)
        extra_mask = (
            extra_history["_scout_core"].ne("")
            & ~extra_history["_scout_core"].isin(known)
            & extra_last_game.notna()
            & (extra_last_game >= pd.Timestamp.today().normalize() - pd.Timedelta(days=ACTIVE_DAYS + 35))
            & (extra_minutes >= ACTIVE_MIN_MINUTES)
            & (extra_games >= 1)
        )
        observed = []
        for item in extra_history.loc[extra_mask].drop(columns=["_scout_core"]).to_dict("records"):
            core = _safe_str(item.get("core"))
            name = _safe_str(item.get("nome_observado"))
            pos_obs = _safe_str(item.get("posicao_observada")) or _safe_str(item.get("posicao_fm"))
            role = _role(pos_obs, "") if pos_obs else ""
            if not name or not role:
                continue
            item["posicao_observada"] = pos_obs
            record = {col: None for col in p.columns}
            record.update({"nome": name, "clube": _safe_str(item.get("clube_fm")) or _safe_str(item.get("ultimo_time")),
                           "posicao": _safe_str(item.get("posicao_observada")), "funcao": _safe_str(item.get("posicao_observada")),
                           "nacionalidade": None, "nascimento": None, "idade": np.nan,
                           "valor_mercado_eur": np.nan, "fim_contrato": pd.NaT,
                           "transfermarkt_id": None, "clube_id": None, "papel": role, "_role": role,
                           "_core": _safe_str(item.get("core_nome")) or core, "_hkey": core, "clube_observado": True,
                           "fonte_clube_observado": "últimas partidas disponíveis; sem cadastro TM",
                           "sem_cadastro_mercado": True})
            for key, value in item.items():
                if key not in ("core", "historico_temporadas", "ultimos_jogos", "nome_observado", "posicao_observada"):
                    record[key] = value
            record["historico_temporadas"] = json.dumps(item.get("historico_temporadas", []), ensure_ascii=False, default=str)
            record["ultimos_jogos"] = json.dumps(item.get("ultimos_jogos", []), ensure_ascii=False, default=str)
            # rodada 24: idade, país, valor e altura pelo elenco da FotMob (mesmo id do atleta), quando existir
            born = pd.to_datetime(item.get("nascimento_fm"), errors="coerce")
            record["nascimento"] = born.date().isoformat() if pd.notna(born) else None
            record["idade"] = round((pd.Timestamp.today() - born).days / 365.25, 1) if pd.notna(born) else np.nan
            record["nacionalidade"] = _safe_str(item.get("nacionalidade_fm")) or None
            vfm = pd.to_numeric(item.get("valor_fm"), errors="coerce")
            record["valor_mercado_eur"] = float(vfm) if pd.notna(vfm) and vfm > 0 else np.nan
            hfm = pd.to_numeric(item.get("altura_fm"), errors="coerce")
            if pd.notna(hfm) and hfm > 0:
                record["altura_cm"] = float(hfm)
            if record["nacionalidade"] or pd.notna(born):
                record["fonte_identidade"] = "elenco FotMob (id do atleta)"
            record["fim_contrato"] = pd.NaT
            record["clube_valor_total_eur"] = np.nan
            observed.append(record)
            known.add(core)
        if observed:
            p = pd.concat([p, pd.DataFrame(observed)], ignore_index=True, sort=False)
    for col in ("minutos", "jogos", "rating_media", "minutos_12m", "jogos_12m", "rating_12m"):
        if col not in p:
            p[col] = np.nan
    # rodada 24: identificador único de cada perfil (id FotMob, nome+clube, ou o id do Transfermarkt)
    if "pid" not in p:
        p["pid"] = None
    tm_pid = "tm" + p["transfermarkt_id"].astype(str)
    p["pid"] = p["pid"].where(p["pid"].notna() & p["pid"].astype(str).ne("") & p["pid"].astype(str).ne("nan"),
                              tm_pid.where(p["transfermarkt_id"].notna(), "nm:" + p["_core"].astype(str) + "|"
                                           + p["clube"].map(lambda c: team_core(_safe_str(c)))))
    p["minutos"] = pd.to_numeric(p["minutos"], errors="coerce")
    p["minutos_12m"] = pd.to_numeric(p["minutos_12m"], errors="coerce")
    p["jogos"] = pd.to_numeric(p["jogos"], errors="coerce")
    p["jogos_12m"] = pd.to_numeric(p["jogos_12m"], errors="coerce")
    return p.reset_index(drop=True)


def add_quality_scores(players: pd.DataFrame, min_minutes: int = 450) -> pd.DataFrame:
    """Qualidade por posição usando percentis multi-temporada e retração por amostra/ cobertura."""
    if players is None or players.empty:
        return pd.DataFrame()
    d = players.copy()
    for col in ("papel", "minutos_12m", "minutos", "rating_12m", "rating_media", "idade", "valor_mercado_eur"):
        if col not in d:
            d[col] = np.nan
    d["qualidade"] = np.nan
    d["confianca_pct"] = 0.0
    d["_perf_raw"], d["_conf"], d["_lvl"] = np.nan, np.nan, np.nan
    d["nota_media_temporada"] = pd.to_numeric(d["rating_12m"].combine_first(d["rating_media"]), errors="coerce")
    # nível do clube (0–1): percentil do valor do elenco entre os clubes; reputação: percentil do valor na função
    level: Dict[int, float] = {}
    if "clube_valor_total_eur" in d:
        level = _level_map(d)
    mv = pd.to_numeric(d["valor_mercado_eur"], errors="coerce")
    # rodada 13: reputação = maior entre o valor atual e 80% do PICO recente (3 anos). Veterano de elite (Messi aos 39)
    # perde valor de mercado pela idade, não pela bola; o pico recente segura a reputação sem inventar nada.
    if "valor_pico_3a_eur" in d:
        peak = pd.to_numeric(d["valor_pico_3a_eur"], errors="coerce") * .8
        mv = pd.concat([mv, peak], axis=1).max(axis=1, skipna=True).where(mv.notna() | peak.notna())
    rp = np.log1p(mv).groupby(d["papel"]).rank(pct=True) * 100
    rep_pct: Dict[int, float] = {i: float(v) for i, v in rp.items() if pd.notna(v) and pd.notna(mv.get(i)) and mv.get(i) > 0}
    # Cada função tem sua própria régua. Não misturar goleiros, laterais, volantes e atacantes.
    for role, idx in d.groupby("papel", dropna=False).groups.items():
        family = _role_family(str(role))
        if family == "OTHER":
            continue
        rows = d.loc[idx]
        specs = ROLE_METRICS.get(str(role), ROLE_METRICS.get(family, []))
        if not specs:
            continue
        contributions: Dict[int, List[Tuple[float, float]]] = {}
        for metric, weight, high in specs:
            if metric not in d:
                continue
            values = pd.to_numeric(rows[metric], errors="coerce")
            valid = values.notna()
            if int(valid.sum()) < 5:
                continue
            ranks = values[valid].rank(pct=True, method="average") * 100
            if not high:
                ranks = 100 - ranks + (100 / max(int(valid.sum()), 1))
            for row_idx, score in ranks.items():
                contributions.setdefault(row_idx, []).append((float(score), float(weight)))
        for row_idx in idx:
            items = contributions.get(row_idx) or []
            if len(items) < 2:
                continue
            total_w = sum(w for _, w in items)
            raw = sum(s * w for s, w in items) / total_w
            m12, mall = _num(d.at[row_idx, "minutos_12m"]), _num(d.at[row_idx, "minutos"])
            # rodada 13: 0 minuto no último ano NÃO cai para o histórico antigo inteiro (Adryelson aparecia com 88% de
            # confiança e 0 min). Minutos antigos contam 1/3.
            mins = (m12 if m12 is not None else 0) + max((mall or 0) - (m12 or 0), 0) / 3
            coverage = min(1.0, len(items) / max(3.0, len(specs) * .55))
            # rodada 10: encolhimento bayesiano pelos MINUTOS — 21 min não pode virar nota 82; com 900 min a
            # produção vale metade, com 2.700 min (uma temporada de titular) vale 3/4
            exposure = mins / (mins + 900.0)
            confidence = exposure * (.6 + .4 * coverage)
            perf = 50 + (raw - 50) * confidence
            # nível da competição: os mesmos números contra adversários fracos valem menos (proxy = valor do elenco do
            # clube no Transfermarkt, em percentil entre os clubes)
            lvl = level.get(row_idx)
            if lvl is not None:
                # quem DOMINA a própria liga (percentil ≥ 92 com amostra boa) perde menos pelo nível: ele seria bom
                # em qualquer lugar; números medianos numa liga fraca valem bem menos
                factor = .5 + .5 * lvl
                if raw >= 92 and confidence >= .55:
                    factor = max(factor, .8)
                perf = 50 + (perf - 50) * factor
            # reputação de mercado na mesma função (o mercado já precifica nível e regularidade) — só quando existe
            rep = rep_pct.get(row_idx)
            # rodada 13: sem minutos medidos E sem valor de mercado não há o que avaliar — antes virava "48" (puro
            # preenchimento) e dezenas de jovens apareciam com a mesma nota. Agora fica sem nota (lacuna é lacuna).
            if mins < 90 and rep is None:
                continue
            # rodada 16: 0 minuto no ÚLTIMO ANO = fora da avaliação (Adryelson, Payet, Hübers apareciam com 74–78)
            if m12 is not None and m12 <= 0:
                continue
            lvl100 = 100 * lvl if lvl is not None else 45.0
            # rodada 13: jovem já muito valorizado na função (topo do mercado aos ≤ 23) — o mercado enxerga seleção,
            # liderança e projeção que as estatísticas abertas não mostram (ex.: Cubarsí); pesa mais a reputação
            age_i = _num(d.at[row_idx, "idade"])
            w_rep = .45 if (rep is not None and rep >= 85 and age_i is not None and age_i <= 23) else .3
            # rodada 16: a fama de mercado pesa na proporção dos minutos recentes (Darwin com 376 min, Messi com 335 min
            # e Maddison com 229 min ficavam no topo pela reputação). Com 1.350+ min no ano vale o peso cheio.
            w_rep *= min(1.0, (m12 or 0) / 1350.0)
            q = (.9 - w_rep) * perf + w_rep * (rep if rep is not None else lvl100) + .1 * lvl100
            d.at[row_idx, "qualidade"] = round(q, 1)
            d.at[row_idx, "confianca_pct"] = round(confidence * 100)
            # rodada 20: componentes guardados para o overall 0–100 (finalize_overall)
            d.at[row_idx, "_perf_raw"] = round(raw, 2)
            d.at[row_idx, "_conf"] = round(confidence, 3)
            if lvl is not None:
                d.at[row_idx, "_lvl"] = round(lvl, 3)
    # Potencial de revenda: indicador exploratório, separado da qualidade atual.
    age = pd.to_numeric(d["idade"], errors="coerce")
    market = pd.to_numeric(d["valor_mercado_eur"], errors="coerce")
    market_pct = market.groupby(d["papel"]).rank(pct=True) * 100
    quality = pd.to_numeric(d["qualidade"], errors="coerce")
    # rodada 11: TETO projetado = qualidade atual + crescimento esperado até ~26 anos. Nunca fica abaixo da qualidade.
    # Cresce mais quem já produz cedo (confiança alta) e em nível mais alto; é projeção, não certeza.
    conf = pd.to_numeric(d["confianca_pct"], errors="coerce").fillna(0) / 100
    lvl_s = pd.Series({i: v for i, v in level.items()}, dtype=float).reindex(d.index).fillna(.5)
    years = (26 - age.fillna(30)).clip(lower=0, upper=9)
    # rodada 13: PRECOCIDADE — o que separa promessa de jovem comum: valor de mercado alto para a idade (o mercado vê
    # seleção de base, capitania, propostas) e minutos de profissional cedo, comparados com quem tem a mesma idade.
    prec = precocity(d)
    d["precocidade"] = prec.round(0)
    growth = years * (.9 + 1.2 * conf + 1.6 * prec.fillna(30) / 100) * (.7 + .5 * lvl_s)
    d["potencial_teto"] = np.ceil((quality + growth).clip(upper=96)).where(quality.notna())   # inteiro, nunca abaixo
    d["potencial_revenda"] = (0.55 * d["potencial_teto"] + 0.25 * ((25 - age) / 8 * 100).clip(0, 100)
                              + 0.20 * (100 - market_pct)).where(age.le(23) & quality.notna()).round(1)
    d["projecao_valorizacao_24m_pct"] = ((d["potencial_teto"] - quality) * 2.2 + (100 - market_pct) * .15).clip(0, 60
                                         ).where(age.le(23) & quality.notna()).round(0)
    d["potencial_natureza"] = "projeção pela idade, produção e nível; não é previsão de preço"
    return d



def _level_map(d: pd.DataFrame) -> Dict[int, float]:
    """Nível 0–1 de cada atleta: 45% clube (valor do elenco entre clubes) + 55% LIGA (mediana do valor dos clubes da
    competição, entre as competições). Flamengo é forte no Brasil, mas o Brasileirão fica abaixo da Premier League."""
    cv = pd.to_numeric(d["clube_valor_total_eur"], errors="coerce")
    if "clube" not in d:
        return {}
    clubs = pd.DataFrame({"clube": d["clube"], "v": cv}).dropna().drop_duplicates("clube")
    if clubs.empty:
        return {}
    club_pct = clubs.set_index("clube")["v"].rank(pct=True)
    out = d["clube"].map(club_pct)
    comp_col = next((c for c in ("clube_liga", "liga_clube", "ultima_competicao") if c in d and d[c].notna().any()), None)
    if comp_col:
        tmp = pd.DataFrame({"clube": d["clube"], "comp": d[comp_col].astype(str), "v": cv}).dropna()
        tmp = tmp[tmp["comp"].str.strip().ne("")].drop_duplicates("clube")
        lg = tmp.groupby("comp")["v"].agg(["median", "size"])
        lg = lg[lg["size"] >= 4]
        if len(lg) >= 3:
            lg_pct = lg["median"].rank(pct=True)
            club_comp = tmp.set_index("clube")["comp"]
            league = d["clube"].map(club_comp).map(lg_pct)
            out = (.45 * out + .55 * league).where(league.notna(), out)
    return {i: float(v) for i, v in out.items() if pd.notna(v)}


def precocity(d: pd.DataFrame) -> pd.Series:
    """0–100 entre atletas da MESMA idade (±1 ano): 60% valor de mercado, 40% minutos de profissional no último ano.
    Só para quem tem até 23 anos; sem valor nem minutos = desconhecido (NaN), nunca zero."""
    age = pd.to_numeric(d.get("idade"), errors="coerce")
    val = pd.to_numeric(d.get("valor_mercado_eur"), errors="coerce")
    mins = pd.to_numeric(d.get("minutos_12m"), errors="coerce")
    out = pd.Series(np.nan, index=d.index)
    young = age.le(23)
    for a in sorted(age[young].dropna().round().unique()):
        peers = (age.round() - a).abs().le(1)
        rows = young & age.round().eq(a)
        vp = np.log1p(val[peers]).rank(pct=True).reindex(d.index)
        mp = mins[peers].rank(pct=True).reindex(d.index)
        score = (.6 * vp.fillna(mp) + .4 * mp.fillna(vp)) * 100
        out[rows] = score[rows]
    return out


def merge_external_ratings(players: pd.DataFrame, ratings: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Cruza notas externas (ex.: Simonetti) sem substituir a leitura estatística própria."""
    if players is None or players.empty:
        return pd.DataFrame() if players is None else players
    out = players.copy()
    out["qualidade_estatistica"] = pd.to_numeric(out.get("qualidade"), errors="coerce")
    out["nota_externa"] = np.nan
    out["fontes_nota_externa"] = ""
    if ratings is None or ratings.empty or not {"nome", "nota"} <= set(ratings.columns):
        out["fonte_qualidade"] = np.where(out["qualidade_estatistica"].notna(),
                                          "métricas estatísticas por posição", "sem avaliação confiável")
        return out
    ext = ratings.copy()
    ext["_core"] = ext["nome"].map(player_core)
    ext["nota"] = pd.to_numeric(ext["nota"], errors="coerce")
    ext = ext[(ext["_core"] != "") & ext["nota"].between(0, 100)]
    if "fonte" in ext:
        ext = ext.groupby("_core").agg(
            nota_externa=("nota", "median"),
            fontes_nota_externa=("fonte", lambda x: " · ".join(sorted(set(x.dropna().astype(str)))))
        )
    else:
        ext = ext.groupby("_core").agg(nota_externa=("nota", "median"))
        ext["fontes_nota_externa"] = ""
    out["_external_core"] = out["_core"] if "_core" in out else out["nome"].map(player_core)
    duplicated = out["_external_core"].duplicated(keep=False)
    matched = out["_external_core"].map(ext["nota_externa"])
    source = out["_external_core"].map(ext["fontes_nota_externa"])
    if "historico_ambiguo" in out:
        blocked = out["historico_ambiguo"].fillna(False).astype(bool)
        matched = matched.mask(blocked)
        source = source.mask(blocked)
    else:
        matched = matched.mask(duplicated)
        source = source.mask(duplicated)
    out["nota_externa"] = matched
    out["fontes_nota_externa"] = source.fillna("")
    stat = pd.to_numeric(out["qualidade_estatistica"], errors="coerce")
    both = stat.notna() & matched.notna()
    only_external = stat.isna() & matched.notna()
    # Nota externa tem peso de corroborar, não dominar a produção observada.
    out.loc[both, "qualidade"] = (.82 * stat[both] + .18 * matched[both]).round(1)
    # rodada 11: sem números próprios, a nota externa sozinha vale metade (puxada para a média): ela não viu os jogos
    out.loc[only_external, "qualidade"] = (50 + (matched[only_external] - 50) * .5).round(1)
    out["fonte_qualidade"] = np.select(
        [both, only_external, stat.notna()],
        ["82% métricas estatísticas + 18% nota externa",
         "nota externa isolada (puxada à média); confiança baixa", "métricas estatísticas por posição"],
        default="sem avaliação confiável",
    )
    if "confianca_pct" in out:
        out.loc[only_external, "confianca_pct"] = 25
        out.loc[both, "confianca_pct"] = np.minimum(
            100, pd.to_numeric(out.loc[both, "confianca_pct"], errors="coerce").fillna(0) + 8)
    out = out.drop(columns=["_external_core"], errors="ignore")
    return out

def market_club(tm_clubs: Optional[pd.DataFrame], club_name: str) -> Optional[Dict[str, Any]]:
    if tm_clubs is None or tm_clubs.empty:
        return None
    target = team_core(club_name)
    if not target:
        return None
    c = tm_clubs.copy()
    c["_core"] = c["nome"].map(team_core)
    hit = c[c["_core"] == target]
    if hit.empty:
        # correspondência aproximada só é aceita quando há tokens distintivos suficientes
        toks = set(target.split())
        scores = c["_core"].map(lambda x: len(toks & set(str(x).split())) / max(len(toks | set(str(x).split())), 1))
        hit = c[scores >= .88]
    return hit.iloc[0].to_dict() if not hit.empty else None


def _market_freshness(df: pd.DataFrame) -> Dict[str, Any]:
    stamp = None
    if df is not None and not df.empty:
        for col in ("ingestao_utc", "data"):
            if col in df:
                x = pd.to_datetime(df[col], errors="coerce").max()
                if pd.notna(x):
                    stamp = x.isoformat()
                    break
    return {"ultima_referencia": stamp, "status": "data disponível" if stamp else "sem carimbo de atualização"}


def _team_matches(db, aliases: Sequence[str], n: int = 50) -> pd.DataFrame:
    names = list(dict.fromkeys([str(x) for x in aliases if x]))
    if not names:
        return pd.DataFrame()
    ph = ",".join("?" for _ in names)
    q = f"""SELECT match_id, match_date, competition_name, season_name, data_level,
                   home_team_name, away_team_name, home_score, away_score
            FROM matches WHERE (home_team_name IN ({ph}) OR away_team_name IN ({ph}))
              AND home_score IS NOT NULL AND away_score IS NOT NULL
              AND COALESCE(data_level,'') IN ('EVENTS','BOXSCORE'){comp_sql(names, "")}
            ORDER BY match_date DESC LIMIT ?"""
    try:
        with db.connect() as conn:
            m = pd.read_sql_query(q, conn, params=names + names + [max(int(n) * 3, n)])
    except Exception:
        return pd.DataFrame()
    if m.empty:
        return m
    m["_fixture"] = m.apply(lambda r: str(r["match_date"])[:10] + "|" + "|".join(sorted(
        (team_core(r["home_team_name"]), team_core(r["away_team_name"])))), axis=1)
    return m.sort_values("data_level", key=lambda s: s.map({"EVENTS": 0, "BOXSCORE": 1}).fillna(9)).drop_duplicates(
        "_fixture", keep="first").sort_values("match_date", ascending=False).head(n).drop(columns="_fixture")


def _coach_profile(db, names: Sequence[str], matches: pd.DataFrame) -> Dict[str, Any]:
    aliases = list(dict.fromkeys(names))
    if not aliases:
        return {"nome": None, "jogos": 0, "origem": "não identificado"}
    ph = ",".join("?" for _ in aliases)
    q = f"""SELECT DISTINCT m.match_id, m.match_date, l.coach, l.team_name
            FROM match_lineups l JOIN matches m ON m.match_id=l.match_id
            WHERE l.team_name IN ({ph}) AND TRIM(COALESCE(l.coach,''))<> ''{comp_sql(aliases, "m")}
            ORDER BY m.match_date DESC"""
    try:
        with db.connect() as conn:
            cur = pd.read_sql_query(q, conn, params=aliases)
    except Exception:
        cur = pd.DataFrame()
    if cur.empty:
        return {"nome": None, "jogos": 0, "origem": "sem escalações com técnico registrado"}
    # O técnico em exercício é o nome da escalação mais recente, não o que acumulou mais partidas antigas.
    cur = cur.sort_values("match_date", ascending=False)
    coach = str(cur.iloc[0]["coach"])
    current = cur[cur["coach"] == coach]
    if current["match_id"].nunique() >= 5:
        return {"nome": coach, "jogos": int(current["match_id"].nunique()), "origem": "jogos recentes no clube",
                "partidas_no_clube": int(current["match_id"].nunique())}
    # Técnico novo: usa a amostra histórica dele em outros clubes, se houver; não mistura como se fosse o estilo atual.
    q2 = """SELECT DISTINCT m.match_id, m.match_date, l.coach, l.team_name
            FROM match_lineups l JOIN matches m ON m.match_id=l.match_id
            WHERE l.coach=? AND m.match_date >= date('now','-5 years')
            ORDER BY m.match_date DESC"""
    try:
        with db.connect() as conn:
            past = pd.read_sql_query(q2, conn, params=[coach])
    except Exception:
        past = pd.DataFrame()
    return {"nome": coach, "jogos": int(current["match_id"].nunique()), "origem": "histórico do técnico em outros clubes",
            "partidas_no_clube": int(current["match_id"].nunique()),
            "partidas_historicas": int(past["match_id"].nunique()) if not past.empty else 0,
            "clubes_anteriores": sorted(set(past["team_name"]) - set(aliases))[:8] if not past.empty else []}


def _stats_for_matches(db, matches: pd.DataFrame, aliases: Sequence[str]) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, Any]]:
    if matches is None or matches.empty:
        return {}, {}, {"n": 0, "baseline_n": 0}
    ids = [int(x) for x in matches["match_id"].tolist()]
    ph = ",".join("?" for _ in ids)
    try:
        with db.connect() as conn:
            stats = pd.read_sql_query(
                f"SELECT match_id,team_name,stat_key,value FROM match_team_stats WHERE match_id IN ({ph})",
                conn, params=ids)
    except Exception:
        stats = pd.DataFrame()
    if stats.empty:
        return {}, {}, {"n": 0, "baseline_n": 0}
    names = {team_core(x) for x in aliases}
    rows_for, rows_against = [], []
    comps = matches["competition_name"].dropna().astype(str).unique().tolist()
    by_game = stats.groupby("match_id")
    for row in matches.itertuples():
        own = by_game.get_group(row.match_id) if row.match_id in by_game.groups else pd.DataFrame()
        mine = own[own["team_name"].map(team_core).isin(names)]
        other = own[~own.index.isin(mine.index)]
        f = dict(zip(mine["stat_key"], pd.to_numeric(mine["value"], errors="coerce")))
        a = dict(zip(other["stat_key"], pd.to_numeric(other["value"], errors="coerce")))
        home = team_core(row.home_team_name) in names
        gf, ga = (row.home_score, row.away_score) if home else (row.away_score, row.home_score)
        f["goals"] = _num(gf)
        a["goals"] = _num(ga)
        rows_for.append(f)
        rows_against.append(a)
    def mean(frame):
        d = pd.DataFrame(frame)
        return {k: round(float(pd.to_numeric(d[k], errors="coerce").mean()), 3)
                for k in d.columns if pd.to_numeric(d[k], errors="coerce").notna().sum() >= 3}
    own_avg, against_avg = mean(rows_for), mean(rows_against)
    baseline: Dict[str, float] = {}
    if comps:
        cph = ",".join("?" for _ in comps)
        start = (pd.to_datetime(matches["match_date"], errors="coerce").max() - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
        q = f"""SELECT s.stat_key,AVG(s.value) AS media,COUNT(*) AS n
                FROM match_team_stats s JOIN matches m ON m.match_id=s.match_id
                WHERE m.competition_name IN ({cph}) AND m.match_date>=?
                GROUP BY s.stat_key HAVING COUNT(*)>=8"""
        try:
            with db.connect() as conn:
                ref = pd.read_sql_query(q, conn, params=comps + [start])
            baseline = dict(zip(ref["stat_key"], pd.to_numeric(ref["media"], errors="coerce")))
        except Exception:
            baseline = {}
    return own_avg, against_avg, {"n": len(rows_for), "baseline_n": len(baseline), "competicoes": comps}



def _coach_history_style(db, coach_name: str, current_aliases: Sequence[str], limit: int = 50) -> Dict[str, Any]:
    """Estilo observado do treinador em partidas de outros clubes; não é perfil genérico inventado."""
    try:
        with db.connect() as conn:
            rows = pd.read_sql_query(
                """SELECT DISTINCT m.match_id,m.match_date,l.team_name
                   FROM match_lineups l JOIN matches m ON m.match_id=l.match_id
                   WHERE l.coach=? AND m.match_date>=date('now','-5 years')
                     AND COALESCE(m.data_level,'') IN ('EVENTS','BOXSCORE')
                   ORDER BY m.match_date DESC""", conn, params=[coach_name])
    except Exception:
        return {"jogos": 0, "tracos": [], "origem": "histórico indisponível"}
    if rows.empty:
        return {"jogos": 0, "tracos": [], "origem": "sem histórico de escalações do técnico"}
    current = {team_core(x) for x in current_aliases}
    rows["_team_core"] = rows["team_name"].map(team_core)
    rows = rows[~rows["_team_core"].isin(current)].drop_duplicates(["match_id", "_team_core"]).head(limit)
    if rows.empty:
        return {"jogos": 0, "tracos": [], "origem": "sem partidas anteriores identificadas"}
    ids = rows["match_id"].astype(int).unique().tolist()
    ph = ",".join("?" for _ in ids)
    try:
        with db.connect() as conn:
            stats = pd.read_sql_query(
                f"SELECT match_id,team_name,stat_key,value FROM match_team_stats WHERE match_id IN ({ph})",
                conn, params=ids)
    except Exception:
        stats = pd.DataFrame()
    if stats.empty:
        return {"jogos": int(rows["match_id"].nunique()), "tracos": [],
                "origem": "histórico de jogos encontrado, mas sem estatísticas comparáveis"}
    own_rows, against_rows = [], []
    for _, rec in rows.iterrows():
        part = stats[stats["match_id"] == rec["match_id"]]
        mine = part[part["team_name"].map(team_core) == rec["_team_core"]]
        other = part[~part.index.isin(mine.index)]
        if mine.empty or other.empty:
            continue
        own_rows.append(dict(zip(mine["stat_key"], pd.to_numeric(mine["value"], errors="coerce"))))
        against_rows.append(dict(zip(other["stat_key"], pd.to_numeric(other["value"], errors="coerce"))))
    own = {k: float(pd.to_numeric(pd.Series([r.get(k) for r in own_rows]), errors="coerce").mean())
           for k in set().union(*(r.keys() for r in own_rows))} if own_rows else {}
    against = {k: float(pd.to_numeric(pd.Series([r.get(k) for r in against_rows]), errors="coerce").mean())
               for k in set().union(*(r.keys() for r in against_rows))} if against_rows else {}
    style = _derive_style(own, against)
    return {"jogos": int(rows["match_id"].nunique()), "tracos": style.get("tracos", []),
            "medias_pro": own, "medias_contra": against,
            "clubes_anteriores": sorted(rows["team_name"].dropna().astype(str).unique().tolist())[:8],
            "origem": "estatísticas de partidas anteriores do treinador",
            "limite": "amostra histórica de outros clubes; não representa automaticamente o elenco atual"}

def diagnose_club(db, aliases: Sequence[str], roster: Optional[pd.DataFrame] = None,
                  tm_clubs: Optional[pd.DataFrame] = None, tm_transfers: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    matches = _team_matches(db, aliases, 50)
    own, against, sample = _stats_for_matches(db, matches, aliases)
    coach = _coach_profile(db, aliases, matches)
    used = roles_used(db, aliases)                       # rodada 11: funções que o time realmente escala
    needs = []
    baseline = {}
    if matches is not None and not matches.empty:
        _, _, _ = own, against, sample
        # Rebusca as médias de competição na mesma janela para expor diferenças no dossiê.
        comps = sample.get("competicoes") or []
        if comps:
            cph = ",".join("?" for _ in comps)
            start = (pd.to_datetime(matches["match_date"], errors="coerce").max() - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
            q = f"""SELECT s.stat_key,AVG(s.value) AS media FROM match_team_stats s
                    JOIN matches m ON m.match_id=s.match_id
                    WHERE m.competition_name IN ({cph}) AND m.match_date>=? GROUP BY s.stat_key"""
            try:
                with db.connect() as conn:
                    baseline = dict(conn.execute(q, comps + [start]).fetchall())
            except Exception:
                baseline = {}
    def delta(key: str, against_side: bool = False):
        v = (against if against_side else own).get(key)
        b = baseline.get(key)
        if v is None or b is None or not b:
            return None
        return (float(v) - float(b)) / abs(float(b))
    defensive = max([x for x in (delta("xg", True), delta("shots_total", True),
                                  delta("shots_on_target", True), delta("goals", True)) if x is not None] or [0])
    attacking = max([-x for x in (delta("xg"), delta("shots_total"), delta("shots_on_target")) if x is not None] or [0])
    build = max([-x for x in (delta("possession_pct"), delta("pass_accuracy_pct"), delta("passes_total")) if x is not None] or [0])
    if defensive > .08:
        needs.append({"papel": "CB", "urgencia": min(100, 48 + defensive * 180), "motivo": "o time cede volume/qualidade de finalizações acima da referência",
                      "evidencias": {k: against.get(k) for k in ("xg", "shots_total", "shots_on_target", "goals") if k in against}})
        needs.append({"papel": "DM", "urgencia": min(95, 42 + defensive * 140), "motivo": "proteção à frente da área e recuperação da segunda bola são prioridades",
                      "evidencias": {k: own.get(k) for k in ("interceptions", "tackles_won") if k in own}})
    if attacking > .08:
        needs.append({"papel": "ST", "urgencia": min(100, 46 + attacking * 170), "motivo": "produção ofensiva abaixo da referência das competições analisadas",
                      "evidencias": {k: own.get(k) for k in ("xg", "shots_total", "shots_on_target", "goals") if k in own}})
        needs.append({"papel": "AM", "urgencia": min(88, 38 + attacking * 115), "motivo": "criação e chegada ao último terço podem elevar o volume ofensivo"})
    if build > .08:
        build_urgency = min(95, 42 + build * 150)
        build_evidence = {k: own.get(k) for k in ("possession_pct", "passes_total", "pass_accuracy_pct") if k in own}
        needs.append({"papel": "CM", "urgencia": build_urgency, "motivo": "circulação e retenção de bola abaixo da referência competitiva",
                      "evidencias": build_evidence})
        for fullback in ("LB", "RB"):
            needs.append({"papel": fullback, "urgencia": min(80, 35 + build * 100),
                          "motivo": "laterais com qualidade de apoio podem dar saída, amplitude e progressão",
                          "evidencias": build_evidence})
    squad = roster if roster is not None else pd.DataFrame()
    if not squad.empty:
        counts = squad["papel"].value_counts().to_dict() if "papel" in squad else {}
        avg = squad.groupby("papel")["qualidade"].mean().to_dict() if "qualidade" in squad and "papel" in squad else {}
        for role in (sorted(used) if used else ("GK", "CB", "LB", "RB", "DM", "CM", "AM", "LW", "RW", "ST")):
            count = int(counts.get(role, 0))
            q = _num(avg.get(role))
            shortage = 100 if count == 0 else 72 if count == 1 else 38 if count == 2 else 0
            low_quality = max(0, 65 - q) * 1.05 if q is not None else 8
            if shortage + low_quality >= 45:
                needs.append({"papel": role, "urgencia": min(100, shortage * .58 + low_quality * .42),
                              "motivo": f"profundidade atual: {count} atleta(s) cadastrados nesta função" +
                                        (f"; qualidade média estimada {q:.0f}/100" if q is not None else "; desempenho individual com pouca cobertura")})
    # rodada 11: carência só nas posições que o time USA. Se o técnico não joga com meia central, "meia central" não é
    # carência — a necessidade vira a função equivalente do desenho dele (volante ou meia ofensivo).
    if used:
        equiv = {"CM": ["DM", "AM"], "AM": ["CM", "LW", "RW"], "DM": ["CM"], "LB": ["LWB", "LM"], "RB": ["RWB", "RM"],
                 "LWB": ["LB"], "RWB": ["RB"], "LW": ["LM", "AM"], "RW": ["RM", "AM"], "LM": ["LW", "LWB"],
                 "RM": ["RW", "RWB"], "ST": ["AM"]}
        mapped = []
        for item in needs:
            r = item["papel"]
            if r in used:
                mapped.append(item)
                continue
            alt = next((a for a in equiv.get(r, []) if a in used), None)
            if alt:
                mapped.append({**item, "papel": alt, "motivo": item["motivo"] + f" (o time não usa {ROLE_LABELS.get(r, r)}; "
                                                                             f"vira {ROLE_LABELS.get(alt, alt)} no desenho dele)"})
        needs = mapped
    # deduplica funções e preserva a prioridade mais alta
    merged: Dict[str, Dict[str, Any]] = {}
    for item in needs:
        role = item["papel"]
        if role not in merged or item["urgencia"] > merged[role]["urgencia"]:
            merged[role] = item
    needs = sorted(merged.values(), key=lambda x: x["urgencia"], reverse=True)
    squad_style = _derive_style(own, against)
    n_games = int(sample.get("n") or 0)
    # rodada 11: 8 jogos já formam identidade; de 30 a 50 ela fica detalhada; abaixo de 8, leitura superficial
    squad_style["nivel_identidade"] = ("detalhada" if n_games >= 30 else "inicial" if n_games >= 8 else "superficial")
    squad_style["fonte"] = (f"{n_games} partidas recentes com estatísticas — identidade "
                            f"{squad_style['nivel_identidade']}" if n_games else "sem partidas com estatísticas")
    squad_style["formacoes"] = used_formations(db, aliases)
    coach_style = {"jogos": 0, "tracos": []}
    if coach.get("nome") and coach.get("jogos", 0) <= 5:
        coach_style = _coach_history_style(db, coach["nome"], aliases, 50)
    if coach_style.get("jogos", 0) >= 5 and coach_style.get("tracos"):
        merged_traits = list(dict.fromkeys((coach_style.get("tracos") or []) + (squad_style.get("tracos") or [])))
        style = {**squad_style, "tracos": merged_traits[:6],
                 "tracos_tecnico": coach_style.get("tracos", []),
                 "tracos_observados_no_elenco": squad_style.get("tracos", []),
                 "fonte_tecnico": coach_style.get("origem"),
                 "amostra_tecnico": coach_style.get("jogos"),
                 "clubes_anteriores_tecnico": coach_style.get("clubes_anteriores", []),
                 "contexto_tecnico": "projeção inicial: características históricas do treinador combinadas com o retrato estatístico do elenco atual",
                 "limite": "a projeção depende de adaptação, reforços, disponibilidade e mudança de contexto"}
    else:
        style = squad_style
        style["contexto_tecnico"] = ("identidade observada nos jogos recentes do clube (o treinador atual ainda tem poucos "
                                     "jogos registrados em outros clubes para comparar)")
    return {
        "partidas_analisadas": sample.get("n", 0), "baseline_competicoes": sample.get("competicoes", []),
        "medias_pro": own, "medias_contra": against, "referencia": baseline, "necessidades": needs,
        "estilo": style, "treinador": coach,
        "ultima_partida": _safe_str(matches["match_date"].max()) if not matches.empty else None,
    }


def roles_used(db, aliases: Sequence[str], n: int = 20, min_share: float = .15) -> set:
    """Funções que o time escala como titular em pelo menos 15% dos últimos jogos com escalação."""
    try:
        from src.squad.matchday import recent_lineups

        lu = recent_lineups(db, list(aliases), n)
    except Exception:
        return set()
    if lu is None or lu.empty or "papel" not in lu:
        return set()
    st_ = lu[lu["titular"] == 1]
    games = max(1, st_["match_id"].nunique())
    share = st_.drop_duplicates(["match_id", "papel"]).groupby("papel")["match_id"].nunique() / games
    return {r for r, v in share.items() if isinstance(r, str) and v >= min_share and not r.endswith("?")}


def used_formations(db, aliases: Sequence[str], n: int = 20) -> List[Tuple[str, int]]:
    try:
        from src.squad.matchday import recent_lineups

        lu = recent_lineups(db, list(aliases), n)
    except Exception:
        return []
    if lu is None or lu.empty:
        return []
    f = lu.drop_duplicates("match_id")["formation"].dropna().astype(str)
    return [(k, int(v)) for k, v in f.value_counts().head(3).items()]


def _derive_style(own: Dict[str, float], against: Dict[str, float]) -> Dict[str, Any]:
    poss = own.get("possession_pct")
    pass_acc = own.get("pass_accuracy_pct")
    passes = own.get("passes_total")
    crosses = own.get("crosses_total")
    shots = own.get("shots_total")
    style = []
    if poss is not None and poss >= 54 and (pass_acc is None or pass_acc >= 80):
        style.append("posse e construção")
    if poss is not None and poss < 47 and shots is not None and shots >= 11:
        style.append("transição e ataque vertical")
    if crosses is not None and crosses >= 16:
        style.append("amplitude e cruzamentos")
    if passes is not None and passes >= 450:
        style.append("circulação de passes")
    if against.get("shots_total") is not None and against["shots_total"] <= 10:
        style.append("proteção de área consistente")
    # rodada 26: mais traços SÓ com os números de cada jogo — a leitura não depende de vídeo
    def g(d, *keys):
        for k in keys:
            v = d.get(k)
            if v is not None and v == v:
                return float(v)
        return None
    defa = sum(x for x in (g(own, "tackles_won", "tackles"), g(own, "interceptions"), g(own, "fouls")) if x is not None)
    opp_passes = g(against, "passes_total", "passes")
    ppda = opp_passes / defa if opp_passes and defa else None
    if ppda is not None:
        style.append("pressão alta (deixa o rival trocar poucos passes)" if ppda <= 9 else
                     "marca mais atrás e espera o rival" if ppda >= 14 else "pressão média")
    lb, lb_tot = g(own, "long_balls_accurate_total", "long_balls_total"), passes
    if lb and lb_tot and lb / lb_tot >= .12:
        style.append("jogo direto (muitas bolas longas)")
    sib, st_ = g(own, "shots_inside_box"), shots
    if sib and st_ and sib / st_ >= .7:
        style.append("finaliza de perto (entra na área antes de chutar)")
    elif sib and st_ and sib / st_ <= .5:
        style.append("chuta muito de fora")
    tob = g(own, "touches_opp_box")
    if tob is not None and tob >= 28:
        style.append("presença constante na área rival")
    soc, sic = g(against, "shots_outside_box"), g(against, "shots_inside_box")
    if soc and sic and soc / (soc + sic) >= .45:
        style.append("bloco que protege a área (o rival só chuta de fora)")
    bc = g(against, "big_chances")
    if bc is not None and bc >= 2.5:
        style.append("cede chances claras com frequência")
    return {"tracos": style or ["identidade ainda sem amostra estatística suficiente"],
            "posse_media": poss, "precisao_passe": pass_acc, "passes_jogo": passes,
            "cruzamentos_jogo": crosses, "finalizacoes_jogo": shots, "ppda_aprox": round(ppda, 1) if ppda else None,
            "limite": ("leitura feita só com os números de cada jogo (posse, passes, pressão aproximada pelo PPDA, bolas "
                       "longas, cruzamentos, onde finaliza e onde deixa finalizar) — não depende de vídeo")}


def current_roster(db, club: Optional[Dict[str, Any]], aliases: Sequence[str],
                   tm_players: Optional[pd.DataFrame], universe: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Elenco composto: cadastro TM + aparições recentes + escalações reais no Data Hub."""
    frames = []
    if tm_players is not None and not tm_players.empty:
        p = tm_players.copy()
        if club and club.get("transfermarkt_id") is not None and "clube_id" in p:
            p = p[p["clube_id"].astype(str).str.replace(r"\.0$", "", regex=True) ==
                  str(club["transfermarkt_id"]).replace(".0", "")]
        elif aliases and "clube" in p:
            cores = {team_core(x) for x in aliases}
            p = p[p["clube"].map(team_core).isin(cores)]
        if not p.empty:
            frames.append(p)
    names = list(dict.fromkeys(aliases))
    if names:
        ph = ",".join("?" for _ in names)
        q = f"""SELECT l.player_name AS nome,l.position AS posicao,l.team_name AS clube,
                       COUNT(DISTINCT l.match_id) AS jogos_recentes,MAX(m.match_date) AS ultima_aparicao
                FROM match_lineups l JOIN matches m ON m.match_id=l.match_id
                WHERE l.team_name IN ({ph}) AND m.match_date>=date('now','-180 days'){comp_sql(names, "m")}
                GROUP BY l.player_name,l.position,l.team_name"""
        try:
            with db.connect() as conn:
                lu = pd.read_sql_query(q, conn, params=names)
        except Exception:
            lu = pd.DataFrame()
        if not lu.empty:
            lu["funcao"] = lu["posicao"]
            frames.append(lu)
    if not frames:
        return pd.DataFrame()
    roster = pd.concat(frames, ignore_index=True, sort=False)
    roster["nome"] = roster["nome"].fillna("").astype(str)
    roster = roster[roster["nome"].str.strip() != ""].copy()
    roster["_core"] = roster["nome"].map(player_core)
    roster = roster.sort_values(["ultima_aparicao"] if "ultima_aparicao" in roster else ["nome"],
                                ascending=False, na_position="last").drop_duplicates("_core", keep="first")
    roster["papel"] = [_role(x, y) for x, y in zip(roster.get("posicao", pd.Series("", index=roster.index)),
                                                  roster.get("funcao", pd.Series("", index=roster.index)))]
    if universe is not None and not universe.empty:
        lookup = universe.drop_duplicates("_core").set_index("_core")
        for col in ("idade", "nacionalidade", "valor_mercado_eur", "fim_contrato", "transfermarkt_id",
                    "qualidade", "confianca_pct", "rating_media", "rating_12m"):
            if col in lookup:
                roster[col] = roster["_core"].map(lookup[col])
        for col in set(COUNT_KEYS) | {k + "_p90" for k in COUNT_KEYS} | {"minutos", "minutos_12m", "jogos", "jogos_12m"}:
            if col in lookup:
                roster[col] = roster["_core"].map(lookup[col])
    return roster.reset_index(drop=True)


def buyer_financial_profile(db, club: Optional[Dict[str, Any]], roster: pd.DataFrame,
                            tm_transfers: Optional[pd.DataFrame], season: Optional[int] = None) -> Dict[str, Any]:
    year = int(season or date.today().year)
    squad_value = pd.to_numeric(roster.get("valor_mercado_eur"), errors="coerce").sum() if not roster.empty else 0
    top = roster.sort_values("qualidade", ascending=False, na_position="last").head(11) if not roster.empty else roster
    xi_value = pd.to_numeric(top.get("valor_mercado_eur"), errors="coerce").sum() if not top.empty else 0
    club_id = str((club or {}).get("transfermarkt_id") or "")
    fees = []
    if tm_transfers is not None and not tm_transfers.empty and club_id:
        t = tm_transfers.copy()
        incoming = t[t.get("para_clube_id", pd.Series("", index=t.index)).astype(str).str.replace(r"\.0$", "", regex=True) == club_id]
        dates = pd.to_datetime(incoming.get("data"), errors="coerce")
        incoming = incoming[dates >= pd.Timestamp.today().normalize() - pd.Timedelta(days=365 * 5)]
        fees = [_money(x) for x in incoming.get("taxa_eur", pd.Series(dtype=object))]
        fees = [x for x in fees if x is not None and x > 0]
    median_fee = float(np.median(fees)) if fees else None
    max_fee = float(max(fees)) if fees else None
    # rodada 27: a MEDIANA das compras subestimava o clube (Cruzeiro com 4,2 mi, mas já pagou ~20 mi): muitas compras
    # baratas puxam a mediana para baixo. Capacidade = o que o clube JÁ PROVOU que paga numa compra grande — 85% da
    # maior taxa ou o percentil 80 das compras (o que for maior), conferido pelo valor do elenco titular.
    p80 = float(np.percentile(fees, 80)) if len(fees) >= 3 else None
    by_fees = max([x for x in (.85 * max_fee if max_fee else None, p80) if x], default=None)
    by_squad = (xi_value * .12) if xi_value else ((squad_value * .08) if squad_value else None)
    proxy = by_fees or by_squad
    if by_fees and by_squad:
        proxy = max(by_fees, .6 * by_squad)
    low = (median_fee or (proxy * .3 if proxy else None)) if proxy else None
    high = max(proxy * 1.25, max_fee or 0) if proxy else None
    vals = pd.to_numeric(roster.get("valor_mercado_eur"), errors="coerce").dropna() if not roster.empty else pd.Series(dtype=float)
    quals = pd.to_numeric(roster.get("qualidade"), errors="coerce").dropna() if not roster.empty else pd.Series(dtype=float)
    return {
        "valor_elenco_eur": float(squad_value) if squad_value else None,
        "valor_xi_eur": float(xi_value) if xi_value else None,
        # rodada 22: o jogador mais valioso e o melhor do elenco — base do "bom senso" (estrela fora do patamar do clube)
        "maior_valor_jogador_eur": float(vals.max()) if len(vals) else None,
        "melhor_qualidade_elenco": float(quals.max()) if len(quals) else None,
        "taxa_mediana_5_anos_eur": median_fee, "maior_taxa_5_anos_eur": max_fee,
        "transferencias_pagas_amostra": len(fees),
        "orcamento_proxy_eur": proxy, "faixa_proxy_eur": [low, high] if low is not None else None,
        "natureza": "estimativa de capacidade de investimento; não é orçamento oficial nem inclui salários",
        "temporada_planejada": year,
    }


def _affinity(candidate_nationality: Any, buyer_country: Any) -> Tuple[int, str]:
    c = _country_core(candidate_nationality)
    b = _country_core(buyer_country)
    if not c or not b:
        return 50, "nacionalidade/idioma sem dados suficientes"
    c_parts = [_country_core(x) for x in re.split(r"[,;/|]", c)]
    if b in c_parts or c == b:
        return 100, "mesmo país do clube: sem barreira de idioma, cultura ou vaga de estrangeiro"
    c_lang = set().union(*[v for k, v in LANGUAGES.items() if any(k in part for part in c_parts)]) if c_parts else set()
    b_lang = set().union(*[v for k, v in LANGUAGES.items() if k in b]) if b else set()
    if c_lang & b_lang:
        return 88, "idioma compartilhado pode facilitar comunicação e adaptação"
    if any(x in " ".join(c_parts) for x in ("argentina", "uruguay", "chile", "paraguay", "colombia", "ecuador", "peru")) and b == "brazil":
        return 75, "contexto sul-americano pode reduzir distância cultural; idioma continua diferente"
    return 52, "não há evidência suficiente para presumir adaptação cultural"


def _first_nat(v: Any) -> str:
    s_ = _safe_str(v)
    return re.split(r"[,;/|]", s_)[0].strip() if s_ else ""


def nationality_market(pool: pd.DataFrame, buyer_country: Any, roster: Optional[pd.DataFrame] = None) -> Dict[str, Tuple[int, str]]:
    """
    Rodada 11 — quão COMUM é cada nacionalidade na liga do clube comprador (elencos do Transfermarkt), mais o próprio
    elenco do clube. Um irlandês ou um norueguês no Brasil existe, mas é raríssimo; argentinos e colombianos são comuns.
    Devolve nacionalidade → (adaptação 0–100, explicação). Mesmo país = 100.
    """
    b = _country_core(buyer_country)
    out: Dict[str, Tuple[int, str]] = {}
    if pool is None or pool.empty or "nacionalidade" not in pool:
        return out
    nat = pool["nacionalidade"].map(_first_nat)
    country_col = pool["clube_pais"] if "clube_pais" in pool else pd.Series("", index=pool.index)
    in_league = country_col.astype(str).map(_country_core) == b if b else pd.Series(False, index=pool.index)
    league_n = int(in_league.sum())
    share = nat[in_league].value_counts(normalize=True) if league_n >= 50 else pd.Series(dtype=float)
    club_nats = set()
    if roster is not None and not roster.empty and "nacionalidade" in roster:
        club_nats = set(roster["nacionalidade"].dropna().map(_first_nat))
    for n in nat.dropna().unique():
        if not n or n == "nan":
            continue
        if _country_core(n) == b:
            out[n] = (100, "mesmo país do clube")
            continue
        sh = float(share.get(n, 0.0))
        if league_n < 50:
            base, why = _affinity(n, buyer_country)[0], "sem amostra da liga; só idioma/região"
        else:
            base = 92 if sh >= .03 else 84 if sh >= .01 else 70 if sh >= .003 else 52 if sh >= .001 else 34 if sh > 0 else 18
            why = (f"{100 * sh:.1f}% dos jogadores da liga do clube são desta nacionalidade" if sh > 0 else
                   "praticamente nenhum jogador desta nacionalidade na liga do clube — chegada seria exceção")
        lang, _ = _affinity(n, buyer_country)
        if lang >= 75:
            base += 6
        if n in club_nats:
            base += 8
            why += "; o clube já tem atletas deste país"
        out[n] = (int(min(98, base)), why)
    return out


def career_context(candidate: Dict[str, Any], buyer: Dict[str, Any]) -> Tuple[int, str]:
    """
    Rodada 11 — contexto de carreira: titular no auge num clube muito mais rico raramente desce de patamar (Vini Jr.,
    Raphinha); veterano voltando para casa é comum (Payet, Paquetá foram exceções e são tratados como exceção).
    """
    age = _num(candidate.get("idade"))
    mins = _num(candidate.get("minutos_12m")) or _num(candidate.get("minutos")) or 0
    seller = _num(candidate.get("clube_valor_total_eur"))
    buyer_v = _num(buyer.get("valor_elenco_eur"))
    if not seller or not buyer_v:
        return 60, "porte dos clubes indisponível; contexto de carreira neutro"
    ratio = seller / buyer_v
    starter = mins >= 1800
    if ratio >= 3 and starter and (age or 26) <= 29:
        return 12, "titular no auge em clube muito maior — descer de patamar agora seria exceção rara"
    if ratio >= 3 and starter and (age or 26) <= 32:
        return 38, "titular em clube muito maior, já perto do fim do auge — possível só com contexto especial"
    if ratio >= 3 and (age or 26) >= 33:
        return 66, "veterano em clube maior — volta para casa ou fim de carreira é um caminho comum"
    if ratio >= 3 and not starter:
        return 58, "reserva em clube muito maior — pode buscar minutos (empréstimo ou venda)"
    if ratio >= 1.5:
        return 55 if starter else 68, "clube vendedor maior — exige proposta forte ou oportunidade de contrato"
    return 85, "clube vendedor de porte igual ou menor — passo natural na carreira"


def _country_core(value: Any) -> str:
    raw = _safe_str(value).lower().strip()
    aliases = {
        "brasil": "brazil", "brasileiro": "brazil", "brasileira": "brazil", "brazilian": "brazil",
        "argentino": "argentina", "argentina": "argentina", "argentinian": "argentina",
        "uruguaio": "uruguay", "uruguayan": "uruguay", "ingles": "england", "inglês": "england",
        "english": "england", "espanhol": "spain", "spanish": "spain", "alemao": "germany",
        "alemão": "germany", "german": "germany", "italiano": "italy", "italian": "italy",
        "frances": "france", "francês": "france", "french": "france", "portugues": "portugal",
        "português": "portugal", "portuguese": "portugal",
    }
    return aliases.get(raw, raw)


def is_foreign_player(nationality: Any, buyer_country: Any) -> Optional[bool]:
    """Retorna None se não há nacionalidade confiável; duplas cidadanias são consideradas."""
    buyer = _country_core(buyer_country)
    raw = _safe_str(nationality)
    if not buyer or not raw:
        return None
    countries = [_country_core(x) for x in re.split(r"[,;/|]", raw) if x.strip()]
    countries = [x for x in countries if x]
    if not countries:
        return None
    return buyer not in countries


def _foreign_rule(competition: str, season: int) -> Optional[Dict[str, Any]]:
    import unicodedata

    raw = _safe_str(competition).lower()
    c = "".join(ch for ch in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(ch))
    if any(x in c for x in BR_COMP_TOKENS):
        if season <= 2026:
            return {"limite": 9, "status": "regra vigente consultada para 2026", "unidade": "relacionados por partida"}
        if season == 2027:
            return {"limite": 8, "status": "redução aprovada; confirmar regulamento específico de 2027", "unidade": "relacionados por partida"}
        if season == 2028:
            return {"limite": 7, "status": "projeção aprovada; confirmar regulamento específico", "unidade": "relacionados por partida"}
        if season == 2029:
            return {"limite": 6, "status": "projeção aprovada; confirmar regulamento específico", "unidade": "relacionados por partida"}
        return {"limite": 5, "status": "projeção aprovada; confirmar regulamento específico", "unidade": "relacionados por partida"}
    return None


def star_gap(candidate: Dict[str, Any], buyer: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """
    Rodada 22 — BOM SENSO de patamar (o "Neymar no América-MG"). Não temos salários; o melhor sinal aberto de salário e
    de fama é o MAIOR valor de mercado da carreira (Transfermarkt) comparado com o jogador mais valioso do comprador,
    mais a distância entre a qualidade do atleta e a do melhor jogador do elenco. Devolve (teto do realismo, porquê) ou
    (None, '') quando não há sinal. Volta ao clube formador e fim de carreira existem — são EXCEÇÃO, não sugestão.
    """
    peak = max([v for v in (_num(candidate.get("maior_valor_eur")), _num(candidate.get("valor_pico_3a_eur")),
                            _num(candidate.get("valor_mercado_eur"))) if v] or [0.0])
    top = _num(buyer.get("maior_valor_jogador_eur"))
    if not top:
        sv = _num(buyer.get("valor_elenco_eur"))
        top = sv / 12 if sv else None
    cap, why = None, ""
    if peak and top:
        r = peak / max(top, 1.0)
        if r >= 8 and peak >= 20e6:
            cap, why = 18, (f"estrela fora do patamar: já valeu € {peak / 1e6:.0f} mi, {r:.0f}× o jogador mais valioso do "
                            "clube — salário e fama fora de alcance (só voltaria em exceção, como fim de carreira em casa)")
        elif r >= 4 and peak >= 10e6:
            cap, why = 40, (f"patamar muito acima: pico de € {peak / 1e6:.0f} mi, {r:.1f}× o mais valioso do elenco — "
                            "salário provavelmente fora do teto do clube")
        elif r >= 2.5 and peak >= 6e6:
            cap, why = 62, f"acima do patamar salarial do elenco (pico {r:.1f}× o mais valioso) — negociação difícil"
    q, best = _num(candidate.get("qualidade")), _num(buyer.get("melhor_qualidade_elenco"))
    if q is not None and best is not None and q - best >= 15:
        c2 = 35 if q - best >= 20 else 50
        if cap is None or c2 < cap:
            cap, why = c2, f"qualidade {q:.0f} contra {best:.0f} do melhor jogador do elenco — muito acima do nível do clube"
    return cap, why


def transfer_realism(candidate: Dict[str, Any], buyer: Dict[str, Any], buyer_country: str = "",
                     competition: str = "", season: Optional[int] = None, foreign_count: int = 0) -> Dict[str, Any]:
    """Score heurístico 0–100; fator por fator explicado, sem inventar salários ou orçamento."""
    year = int(season or date.today().year)
    market = _num(candidate.get("valor_mercado_eur"))
    contract = pd.to_datetime(candidate.get("fim_contrato"), errors="coerce")
    days_left = int((contract - pd.Timestamp.today().normalize()).days) if pd.notna(contract) else None
    months_left = days_left / 30.44 if days_left is not None else None
    proxy = _num(buyer.get("orcamento_proxy_eur"))
    # Valor pedido aproximado, nunca apresentado como taxa confirmada.
    if market is None:
        fee = None
        price_basis = "sem valor de mercado confiável; taxa não estimada"
    elif months_left is not None and months_left < 0:
        fee = 0.0
        price_basis = "contrato cadastrado como expirado; possível agente livre, sem incluir luvas/salários"
    elif months_left is not None and months_left <= 6:
        fee = market * .28
        price_basis = "estimativa de oportunidade por contrato perto do fim"
    elif months_left is not None and months_left <= 12:
        fee = market * .48
        price_basis = "estimativa com contrato entrando no último ano"
    elif (_num(candidate.get("minutos_12m")) or 0) < 600:
        fee = market * .72
        price_basis = "estimativa de desconto por baixa utilização recente"
    else:
        fee = market * 1.18
        price_basis = "estimativa de taxa acima da referência de mercado"
    if proxy and fee is not None:
        ratio = fee / max(proxy, 1.0)
        finance = float(np.clip(100 - max(0, ratio - .18) * 72, 8, 96))
    else:
        finance = 48.0
    mins_raw = _num(candidate.get("minutos_12m"))
    if mins_raw is None:
        mins_raw = _num(candidate.get("minutos"))
    minutes_known = mins_raw is not None
    mins = mins_raw or 0
    quality = _num(candidate.get("qualidade"))
    usage = (float(np.clip(70 - max(0, mins - 1800) / 90 + min(25, max(0, 900 - mins) / 36), 18, 88))
             if minutes_known else 48.0)
    loan_opportunity = (minutes_known and (
                        (mins < 700 and quality is not None and quality >= 65) or
                        (months_left is not None and months_left <= 12 and mins < 1500 and quality is not None and quality >= 60)))
    if loan_opportunity:
        usage = min(96, usage + 10)
    nm = buyer.get("nat_market") or {}
    nat0 = _first_nat(candidate.get("nacionalidade"))
    affinity, affinity_note = nm.get(nat0) or _affinity(candidate.get("nacionalidade"), buyer_country)
    career, career_note = career_context(candidate, buyer)
    rule = _foreign_rule(competition, year)
    foreign_penalty = 0
    foreign_note = "regra estrangeira não identificada para esta competição"
    foreign_status = is_foreign_player(candidate.get("nacionalidade"), buyer_country)
    if rule and foreign_status is True:
        foreign_penalty = 24 if foreign_count >= int(rule["limite"]) - 1 else 8 if foreign_count >= int(rule["limite"]) - 3 else 0
        foreign_note = f"{foreign_count} estrangeiro(s) identificados no elenco; limite indicativo {rule['limite']} ({rule['status']})"
    elif foreign_status is None:
        foreign_note = "nacionalidade não confirmada; não foi aplicada penalidade de estrangeiro"
    # Distância entre o porte de quem vende e o comprador, usada como sinal e não como veto.
    seller_value = _num(candidate.get("clube_valor_total_eur"))
    buyer_value = _num(buyer.get("valor_elenco_eur"))
    tier = 58.0
    tier_note = "porte dos clubes não comparável com os dados disponíveis"
    if seller_value and buyer_value and buyer_value > 0:
        ratio = seller_value / buyer_value
        tier = float(np.clip(88 - max(0, ratio - 1) * 19, 18, 92))
        if ratio > 3:
            tier_note = "clube vendedor tem elenco muito mais valioso; só tende a avançar com contexto excepcional"
        elif ratio > 1.5:
            tier_note = "diferença de porte exige oportunidade contratual ou negociação criativa"
        else:
            tier_note = "porte financeiro relativo parece compatível"
    contract_score = 52
    if months_left is not None:
        contract_score = 95 if months_left <= 6 else 83 if months_left <= 12 else 60 if months_left <= 24 else 42
    # Jogador muito utilizado em clube de porte muito maior é mais difícil de tirar.
    if mins >= 2400 and tier < 35:
        tier -= 12
    foreign_count = int(buyer.get("estrangeiros_atual", foreign_count) or 0)
    # rodada 11: nacionalidade (mercado da liga) e contexto de carreira pesam muito mais — antes um irlandês ou um
    # alemão saía "Viável" para o Cruzeiro só por caber no orçamento
    score = (.22 * finance + .12 * usage + .10 * tier + .10 * contract_score + .24 * affinity + .17 * career
             + .05 * 72) - foreign_penalty
    if affinity < 40:                                     # nacionalidade quase inexistente na liga: exceção, não regra
        score = min(score, 55)
    if career < 30:                                       # titular no auge em clube muito maior
        score = min(score, 45)
    star_cap, star_note = star_gap(candidate, buyer)
    if star_cap is not None:
        score = min(score, star_cap)
    score = int(round(float(np.clip(score, 0, 100))))
    label = ("Fora da realidade do clube" if star_cap is not None and star_cap <= 20 else
             "Viável" if score >= 76 else "Oportunidade de empréstimo" if loan_opportunity and score >= 50 else "Alvo difícil / sonho")
    reasons = [
        f"Financeiro: {finance:.0f}/100 — {price_basis}.",
        (f"Utilização recente: {mins:.0f} minutos nos últimos 12 meses; " +
         ("perfil de empréstimo pode fazer sentido." if loan_opportunity else "minutagem considerada na negociação."))
        if minutes_known else "Minutagem recente indisponível; não foi presumido que o atleta esteja encostado.",
        f"Contrato: {months_left:.1f} mês(es) restante(s)." if months_left is not None else "Prazo contratual indisponível.",
        f"Adaptação ({affinity}/100): {affinity_note}.", f"Contexto de carreira ({career}/100): {career_note}.",
        f"Escada de mercado: {tier_note}.", foreign_note,
    ] + ([f"Bom senso de patamar: {star_note}."] if star_note else [])
    return {"score": score, "rotulo": label, "taxa_estimada_eur": fee, "base_taxa": price_basis,
            "meses_contrato": months_left, "oportunidade_emprestimo": loan_opportunity,
            "financeiro": round(finance), "porte": round(tier), "contrato": round(contract_score),
            "afinidade": affinity, "carreira": career, "penalidade_estrangeiros": foreign_penalty, "regra_estrangeiros": rule,
            "teto_patamar": star_cap, "patamar": star_note,
            "motivos": reasons}


def tactical_compatibility(candidate: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibilidade de capacidades observadas com traços do clube; sem tracking, não simula posicionamento."""
    traits = set(style.get("tracos") or [])
    selected: List[Tuple[str, float, float]] = []
    if "posse e construção" in traits or "circulação de passes" in traits:
        selected += [("pass_accuracy_pct", 1.0, 100.0), ("chances_created_p90", .9, 5.0), ("xa_p90", .8, .8)]
    if "transição e ataque vertical" in traits:
        selected += [("sprints_p90", .8, 25.0), ("xg_p90", 1.0, .8), ("goals_p90", .8, .8)]
    if "amplitude e cruzamentos" in traits:
        selected += [("chances_created_p90", .9, 5.0), ("assists_p90", .8, .5), ("sprints_p90", .6, 25.0)]
    if not selected:
        selected = [("rating_media", 1.0, 10.0), ("def_actions_p90", .6, 12.0),
                    ("chances_created_p90", .6, 5.0)]
    vals = []
    evidence = []
    for key, weight, ceiling in selected:
        value = _num(candidate.get(key))
        if value is None:
            continue
        normalized = float(np.clip(value / ceiling * 100, 0, 100))
        vals.append((normalized, weight))
        evidence.append({"metrica": key, "valor": value, "peso": weight})
    if not vals:
        return {"score": 50, "label": "dados táticos insuficientes", "evidencias": [],
                "confianca": "baixa", "metodo": "sem métricas observadas para os traços do clube"}
    raw = float(np.average([v for v, _ in vals], weights=[w for _, w in vals]))
    quality = _num(candidate.get("qualidade"))
    # A técnica individual é uma parte; o encaixe de indicadores com a identidade pesa mais.
    score = int(round(np.clip(.35 * (quality if quality is not None else 50) + .65 * raw, 0, 100)))
    return {"score": score, "label": "alto" if score >= 75 else "moderado" if score >= 58 else "baixo",
            "evidencias": evidence, "confianca": "média" if len(vals) >= 2 else "baixa",
            "metodo": "índice de capacidades observadas compatíveis com o estilo; não mede movimentos sem bola"}


def chemistry(candidate: Dict[str, Any], roster: pd.DataFrame) -> Dict[str, Any]:
    """Complementaridade por função e indicadores agregados; não presume movimentos sem tracking."""
    if roster is None or roster.empty:
        return {"score": 50, "companheiros": [], "limite": "sem elenco comparável"}
    role = _safe_str(candidate.get("papel"))
    candidates = []
    for _, mate in roster.iterrows():
        mr = _safe_str(mate.get("papel"))
        if not mr or mr == role:
            continue
        score = 50
        reason = "complementaridade funcional provável"
        if role in ("LB", "RB", "LWB", "RWB") and mr in ("LW", "RW", "LM", "RM"):
            score, reason = 76, "lateral e ponta ocupam corredores complementares"
        elif role in ("LW", "RW", "LM", "RM") and mr in ("LB", "RB", "LWB", "RWB"):
            score, reason = 76, "ponta e lateral podem alternar amplitude e apoio"
        elif role == "ST" and mr in ("ATT_MID", "MID"):
            score, reason = 79, "meia pode alimentar a zona de finalização do atacante"
        elif role in ("ATT_MID", "MID") and mr == "ST":
            score, reason = 79, "atacante oferece profundidade para o criador"
        elif role == "DM" and mr in ("CB", "MID"):
            score, reason = 72, "volante pode proteger a linha defensiva e liberar o meio-campista"
        elif role == "CB" and mr == "DM":
            score, reason = 72, "zagueiro e volante podem dividir proteção central"
        else:
            continue
        # Ajuste se houver prova de criação/produção do companheiro.
        creator = _num(mate.get("chances_created_p90")) or _num(mate.get("xa_p90")) or 0
        if role == "ST" and creator > 0:
            score += 5
        candidates.append({"nome": _safe_str(mate.get("nome")), "papel": mr,
                           "score": min(95, score), "motivo": reason})
    candidates.sort(key=lambda x: -x["score"])
    return {"score": int(round(np.mean([x["score"] for x in candidates[:3]]))) if candidates else 50,
            "companheiros": candidates[:3],
            "limite": "sinergia estatística/funcional aproximada; confirmar no vídeo e no modelo de jogo"}


def _feedback_adjust(reason: str, realism: Dict[str, Any], candidate: Dict[str, Any]) -> float:
    r = _safe_str(reason).lower()
    penalty = 0.0
    if "caro" in r and realism.get("financeiro", 50) < 75:
        penalty -= 24
    if "velho" in r and (_num(candidate.get("idade")) or 0) > 27:
        penalty -= 22
    if "físico" in r:
        physical_fields = ("altura_cm", "height_cm", "sprints_p90", "aerials_won_p90", "duels_won_pct")
        if not any(_num(candidate.get(k)) is not None for k in physical_fields):
            penalty -= 8
    if "estrangeiro" in r and realism.get("penalidade_estrangeiros", 0):
        penalty -= 20
    if "característica" in r:
        penalty -= 5
    # rodada 13: "não é bom o suficiente / não agrega" e "pior que o titular" sobem a régua de qualidade
    if ("agrega" in r or "suficiente" in r or "titular" in r) and (_num(candidate.get("qualidade")) or 0) < 72:
        penalty -= 18
    if "fase" in r and (_num(candidate.get("rating_12m")) or 7) < 6.9:
        penalty -= 14
    if "estilo" in r:
        penalty -= 6
    return penalty


def why_chosen(player: Dict[str, Any], roster: Optional[pd.DataFrame] = None) -> Dict[str, List[str]]:
    """Porquês da indicação e pontos de atenção, em linguagem de futebol, a partir dos números do próprio dossiê."""
    pro: List[str] = []
    con: List[str] = []
    role = _safe_str(player.get("papel_alvo") or player.get("papel"))
    label = ROLE_LABELS.get(role, role or "posição")
    q = _num(player.get("qualidade"))
    if player.get("motivo_principal"):
        pro.append(f"Resolve uma carência: {player['motivo_principal']}.")
    if roster is not None and not roster.empty and q is not None and {"papel", "qualidade"} <= set(roster.columns):
        same = roster[roster["papel"] == role].copy()
        same["qualidade"] = pd.to_numeric(same["qualidade"], errors="coerce")
        same = same.dropna(subset=["qualidade"]).sort_values("qualidade", ascending=False)
        if not same.empty:
            top = same.iloc[0]
            diff = q - float(top["qualidade"])
            if diff >= 3:
                pro.append(f"Chega como titular: qualidade {q:.0f} contra {float(top['qualidade']):.0f} de "
                           f"{top.get('nome')}, hoje o melhor {label.lower()} do elenco.")
            elif diff >= -3:
                pro.append(f"Briga direto pela vaga com {top.get('nome')} ({float(top['qualidade']):.0f}) — "
                           "aumenta a concorrência e a profundidade.")
            else:
                con.append(f"Abaixo do titular atual ({top.get('nome')}, {float(top['qualidade']):.0f}): entra como "
                           "opção de banco/rodízio.")
        else:
            pro.append(f"O elenco não tem {label.lower()} de origem com números medidos — preenche um buraco.")
    for t in (player.get("caracteristicas") or [])[:4]:
        if isinstance(t, dict):
            pro.append(f"{t.get('emoji', '')} {t.get('nome')}: {t.get('porque')}.")
    r = player.get("realismo") if isinstance(player.get("realismo"), dict) else {}
    sc = _num(r.get("score"))
    if sc is not None:
        (pro if sc >= 70 else con).append(f"Viabilidade {sc:.0f}% ({r.get('rotulo', '')}) — "
                                          + "; ".join((r.get("motivos") or [])[:2]))
    fit_ = player.get("compatibilidade") if isinstance(player.get("compatibilidade"), dict) else {}
    fs = _num(fit_.get("score"))
    if fs is not None:
        (pro if fs >= 65 else con).append(f"Encaixe no estilo do time: {fs:.0f}% ({fit_.get('label', '')}).")
    age = _num(player.get("idade"))
    pot = _num(player.get("potencial_teto"))
    if age is not None and age <= 23 and pot is not None and q is not None and pot - q >= 5:
        pro.append(f"Margem de evolução: teto projetado {pot:.0f} (hoje {q:.0f}) aos {age:.0f} anos.")
    if age is not None and age >= 31:
        con.append(f"{age:.0f} anos: contrato curto e queda física provável nas próximas temporadas.")
    conf = _num(player.get("confianca_pct"))
    if conf is not None and conf < 45:
        con.append(f"Poucos minutos medidos (confiança {conf:.0f}%): a nota pode mudar bastante com mais jogos.")
    rt = _num(player.get("rating_12m"))
    if rt is not None and rt < 6.8:
        con.append(f"Fase fraca: nota média {rt:.2f} nos últimos 12 meses.")
    mins = _num(player.get("minutos_12m"))
    if mins is not None and mins < 900:
        con.append(f"Jogou pouco no último ano ({mins:.0f} min).")
    return {"porque": pro, "atencao": con}


def recommend(players: pd.DataFrame, needs: Sequence[Dict[str, Any]], buyer: Dict[str, Any],
              buyer_country: str = "", competition: str = "", roster: Optional[pd.DataFrame] = None,
              rejected: Optional[Iterable[str]] = None, feedback_reason: str = "",
              season: Optional[int] = None, max_per_position: int = 120) -> pd.DataFrame:
    if players is None or players.empty or not needs:
        return pd.DataFrame()
    rejected_cores = {player_core(x) for x in (rejected or [])}
    target_roles = {_safe_str(n.get("papel")) for n in needs if _safe_str(n.get("papel"))}
    allowed_roles = {role for role in ROLE_LABELS if any(fit(target, role) >= .60 for target in target_roles)}
    eligible = players[players["papel"].isin(allowed_roles)].copy() if "papel" in players else players.iloc[0:0]
    if eligible.empty:
        return pd.DataFrame()
    own_cores = {team_core(x) for x in (buyer.get("club_aliases") or [])}
    if own_cores and "clube" in eligible:
        eligible = eligible[~eligible["clube"].map(team_core).isin(own_cores)]
    if "historico_ambiguo" in eligible:
        eligible = eligible.loc[~_boolean_mask(eligible["historico_ambiguo"])]
    if rejected_cores and "_core" in eligible:
        eligible = eligible[~eligible["_core"].astype(str).isin(rejected_cores)]
    if eligible.empty:
        return pd.DataFrame()

    # Pré-seleção vetorial: evita fazer centenas de milhares de cálculos de dossiê a cada clique.
    # O corte inicial combina qualidade, encaixe, contrato/minutagem e affordability; o ranking completo
    # só é calculado para o grupo mais promissor de cada posição.
    rows = []
    buyer_budget = _num(buyer.get("orcamento_proxy_eur"))
    for need in needs:
        role = _safe_str(need.get("papel"))
        if not role:
            continue
        candidates = eligible.copy()
        candidates["_scout_role_fit"] = candidates["papel"].map(lambda x: float(fit(role, _safe_str(x))))
        candidates = candidates[candidates["_scout_role_fit"] >= .60]
        if candidates.empty:
            continue
        q = pd.to_numeric(candidates.get("qualidade", pd.Series(np.nan, index=candidates.index)), errors="coerce").fillna(48)
        mins = pd.to_numeric(candidates.get("minutos_12m", pd.Series(np.nan, index=candidates.index)), errors="coerce")
        if "minutos" in candidates:
            mins = mins.combine_first(pd.to_numeric(candidates["minutos"], errors="coerce"))
        usage = pd.Series(48.0, index=candidates.index)
        known_mins = mins.notna()
        usage.loc[known_mins] = (70 - (mins[known_mins] - 1800).clip(lower=0) / 90 +
                                 (900 - mins[known_mins]).clip(lower=0, upper=900) / 36).clip(18, 88)
        contract = pd.to_datetime(candidates.get("fim_contrato", pd.Series(pd.NaT, index=candidates.index)), errors="coerce")
        months = (contract - pd.Timestamp.today().normalize()).dt.days / 30.44
        contract_score = pd.Series(50.0, index=candidates.index)
        contract_score.loc[months.notna() & (months <= 6)] = 95
        contract_score.loc[months.notna() & (months > 6) & (months <= 12)] = 83
        contract_score.loc[months.notna() & (months > 12) & (months <= 24)] = 60
        contract_score.loc[months.notna() & (months > 24)] = 42
        market = pd.to_numeric(candidates.get("valor_mercado_eur", pd.Series(np.nan, index=candidates.index)), errors="coerce")
        finance = pd.Series(48.0, index=candidates.index)
        if buyer_budget:
            ratio = market / max(buyer_budget, 1.0)
            finance.loc[market.notna()] = (100 - (ratio.loc[market.notna()] - .18).clip(lower=0) * 72).clip(8, 96)
        # rodada 11: a nacionalidade (quão comum é na liga do clube) já entra no corte inicial — antes o corte só via
        # qualidade, e os 20 melhores do mundo na posição eram quase todos inviáveis para o clube
        nm = buyer.get("nat_market") or {}
        nat0 = candidates.get("nacionalidade", pd.Series("", index=candidates.index)).map(_first_nat)
        aff = nat0.map(lambda n: (nm.get(n) or (50, ""))[0]).astype(float)
        candidates["_scout_pre"] = (.34 * q + .15 * candidates["_scout_role_fit"] * 100 + .12 * usage +
                                     .09 * contract_score + .10 * finance + .20 * aff)
        # rodada 22: estrela fora do patamar do clube sai do corte inicial (o "Neymar no América-MG")
        top_v = _num(buyer.get("maior_valor_jogador_eur")) or ((_num(buyer.get("valor_elenco_eur")) or 0) / 12) or None
        if top_v:
            peak = pd.concat([pd.to_numeric(candidates.get(k, pd.Series(np.nan, index=candidates.index)), errors="coerce")
                              for k in ("maior_valor_eur", "valor_pico_3a_eur", "valor_mercado_eur")], axis=1).max(axis=1)
            gap = peak / max(top_v, 1.0)
            candidates.loc[(gap >= 8) & (peak >= 20e6), "_scout_pre"] -= 40
            candidates.loc[(gap >= 4) & (gap < 8) & (peak >= 10e6), "_scout_pre"] -= 15
        # não sugerir quem não melhora o time: abaixo do titular atual da posição só entra jovem promissor ou oportunidade
        starter_q = None
        if roster is not None and not roster.empty and {"papel", "qualidade"} <= set(roster.columns):
            rq = pd.to_numeric(roster.loc[roster["papel"] == role, "qualidade"], errors="coerce").dropna()
            starter_q = float(rq.max()) if len(rq) else None
        if starter_q is not None:
            age_c = pd.to_numeric(candidates.get("idade", pd.Series(np.nan, index=candidates.index)), errors="coerce")
            pot = pd.to_numeric(candidates.get("potencial_teto", pd.Series(np.nan, index=candidates.index)), errors="coerce")
            keep = (q >= starter_q - 2) | ((age_c <= 21) & (pot.fillna(q) >= starter_q)) | (contract_score >= 83)
            candidates = candidates[keep]
            if candidates.empty:
                continue
        candidates = candidates.sort_values("_scout_pre", ascending=False).head(max(60, int(max_per_position)))
        for c in candidates.drop(columns=["_scout_pre"]).to_dict("records"):
            role_fit = float(c.pop("_scout_role_fit", 0))
            realism = transfer_realism(c, buyer, buyer_country, competition, season,
                                       foreign_count=int(buyer.get("estrangeiros_atual", 0) or 0))
            tactical = tactical_compatibility(c, buyer.get("estilo") or {"tracos": []})
            chemistry_score = chemistry(c, roster)
            quality = _num(c.get("qualidade"))
            sample_conf = _num(c.get("confianca_pct")) or 0
            sporting = quality if quality is not None else 48
            need_score = float(need.get("urgencia") or 50)
            score = (.27 * sporting + .32 * realism["score"] + .15 * tactical["score"] +
                     .11 * chemistry_score["score"] + .10 * need_score + .05 * (role_fit * 100))
            score += _feedback_adjust(feedback_reason, realism, c)
            if quality is None:
                score -= 8
            if realism.get("teto_patamar") is not None and realism["teto_patamar"] <= 20:
                score -= 20                                # estrela fora do patamar: no máximo como "sonho" no fim da lista
            rows.append({
                **c, "papel_alvo": role, "papel_alvo_label": ROLE_LABELS.get(role, role),
                "urgencia": need_score, "encaixe_posicao": round(role_fit * 100),
                "realismo": realism, "compatibilidade": tactical, "sinergia": chemistry_score,
                "score_scout": round(float(np.clip(score, 0, 100)), 1),
                "qualidade_dados_pct": round(sample_conf),
                "potencial_revenda": _num(c.get("potencial_revenda")),
                "projecao_valorizacao_24m_pct": _num(c.get("projecao_valorizacao_24m_pct")),
                "motivo_principal": need.get("motivo", ""),
            })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    # "realismo" é um dicionário por linha: empate na nota fazia o pandas comparar dicionários e quebrar a aba.
    # Desempate pela pontuação numérica do realismo (mesmo critério de antes, sem o erro).
    out["_realismo_score"] = [float((r or {}).get("score") or 0) if isinstance(r, dict) else 0.0 for r in out["realismo"]]
    out = out.sort_values(["score_scout", "_realismo_score"], ascending=False).drop(columns=["_realismo_score"])
    return out.drop_duplicates("_core", keep="first").reset_index(drop=True)


def shortlist_by_position(ranked: pd.DataFrame, role: str, limit: int = 3) -> pd.DataFrame:
    if ranked is None or ranked.empty:
        return pd.DataFrame()
    return ranked[ranked["papel_alvo"] == role].head(limit).copy()


def build_simulation(roster: pd.DataFrame, candidate: Optional[Dict[str, Any]] = None,
                     sold_name: Optional[str] = None, formation: str = "4-3-3") -> Dict[str, Any]:
    """Simulação comparativa do XI; todos os deltas são projeções baseadas na amostra, não previsão do jogo."""
    from src.squad.planner import best_xi
    def prepare(d):
        x = d.copy()
        if x.empty:
            return x
        x["nome"] = x["nome"].astype(str)
        x["papel"] = x.get("papel", pd.Series("", index=x.index)).fillna("")
        x["nota"] = pd.to_numeric(x.get("qualidade"), errors="coerce")
        x["nota"] = x["nota"].fillna(45)
        return x
    before = prepare(roster if roster is not None else pd.DataFrame())
    after = before.copy()
    if sold_name and not after.empty:
        after = after[after["nome"] != sold_name].copy()
    if candidate:
        add = pd.DataFrame([candidate]).rename(columns={"nome": "nome"})
        if "papel" not in add:
            add["papel"] = add.get("papel_alvo", "")
        add["nota"] = _num(candidate.get("qualidade")) or 45
        if not after.empty:
            after = pd.concat([after, add], ignore_index=True, sort=False)
        else:
            after = add
    def xi(d):
        if d.empty:
            return []
        return best_xi(d, formation)
    xi_before, xi_after = xi(before), xi(after)
    metric_keys = {
        "Qualidade média (0–100)": "qualidade",
        "xG por 90 (índice)": "xg_p90", "Criação por 90 (índice)": "chances_created_p90",
        "Ações defensivas por 90": "def_actions_p90", "Progressão por passe (proxy)": "xa_p90",
    }
    def average(d, slots):
        names = [x.get("jogador") for x in slots if x.get("jogador")]
        part = d[d["nome"].isin(names)] if not d.empty and names else pd.DataFrame()
        vals = {}
        for label, key in metric_keys.items():
            if not part.empty and key in part:
                s = pd.to_numeric(part[key], errors="coerce").dropna()
                if len(s):
                    vals[label] = round(float(s.mean()), 2)
        return vals
    b = average(before, xi_before)
    a = average(after, xi_after)
    deltas = []
    for k in metric_keys:
        if k in b and k in a:
            delta = a[k] - b[k]
            pct = delta / abs(b[k]) * 100 if b[k] else None
            deltas.append({"indicador": k, "antes": b[k], "depois": a[k], "variacao": round(delta, 2),
                           "variacao_pct": round(pct, 1) if pct is not None else None})
    return {"formacao": formation, "xi_antes": xi_before, "xi_depois": xi_after,
            "medias_antes": b, "medias_depois": a, "deltas": deltas,
            "limite": "projeção de composição do XI a partir dos dados disponíveis; não estima resultado em campo"}


def ensure_scout_tables(db) -> None:
    with db.connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS scout_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT, criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            clube TEXT NOT NULL, jogador TEXT NOT NULL, papel TEXT, motivo TEXT NOT NULL,
            score REAL, fonte_dados TEXT DEFAULT 'Scout contextual'
        );
        CREATE INDEX IF NOT EXISTS idx_scout_feedback_club ON scout_feedback(clube,papel,motivo);
        CREATE TABLE IF NOT EXISTS scout_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, clube TEXT NOT NULL, nome TEXT NOT NULL,
            payload_json TEXT NOT NULL, atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
VOTES_DDL = ("CREATE TABLE IF NOT EXISTS scout_player_votes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
             "criado_em TEXT DEFAULT CURRENT_TIMESTAMP, clube TEXT, jogador TEXT NOT NULL, core TEXT NOT NULL, voto INTEGER)")


def record_vote(db, club: str, player: str, vote: bool) -> None:
    """Rodada 20: 👍/👎 numa sugestão — opinião sobre o JOGADOR (é bom / não é), sem precisar adicionar nem descartar."""
    with db.connect() as conn:
        conn.execute(VOTES_DDL)
        conn.execute("INSERT INTO scout_player_votes (clube, jogador, core, voto) VALUES (?,?,?,?)",
                     (club, player, player_core(player), 1 if vote else 0))


def player_votes(db) -> Dict[str, Tuple[int, int]]:
    """core → (👍, 👎) somando todos os clubes (a opinião é sobre a qualidade do atleta, não sobre o encaixe)."""
    try:
        with db.connect() as conn:
            conn.execute(VOTES_DDL)
            rows = conn.execute("SELECT core, SUM(voto), SUM(1 - voto) FROM scout_player_votes GROUP BY core").fetchall()
    except Exception:
        return {}
    return {r[0]: (int(r[1] or 0), int(r[2] or 0)) for r in rows}


def apply_votes(ranked: pd.DataFrame, votes: Dict[str, Tuple[int, int]], col: str = "score_scout") -> pd.DataFrame:
    """Cada 👍 líquido vale +3 no índice da sugestão (teto ±9) — ajusta a ordem sem apagar ninguém."""
    if ranked is None or ranked.empty or not votes:
        return ranked
    r = ranked.copy()
    core = r["_core"].astype(str) if "_core" in r else r["nome"].map(player_core)
    net = core.map(lambda c: votes.get(c, (0, 0))[0] - votes.get(c, (0, 0))[1]).astype(float)
    r["votos_scout"] = core.map(lambda c: votes.get(c, (0, 0)))
    if col in r:
        r[col] = pd.to_numeric(r[col], errors="coerce").fillna(0) + (3 * net).clip(-9, 9)
        r = r.sort_values(col, ascending=False)
    return r


def record_rejection(db, club: str, player: str, role: str, reason: str, score: Optional[float] = None) -> None:
    ensure_scout_tables(db)
    with db.connect() as conn:
        conn.execute("INSERT INTO scout_feedback (clube,jogador,papel,motivo,score) VALUES (?,?,?,?,?)",
                     (club, player, role, reason, score))


def rejection_preferences(db, club: str, limit: int = 12) -> Dict[str, Any]:
    """Resume as últimas recusas do clube para recalibrar a busca seguinte."""
    ensure_scout_tables(db)
    try:
        with db.connect() as conn:
            rows = pd.read_sql_query(
                """SELECT motivo,papel,COUNT(*) AS ocorrencias,MAX(criado_em) AS mais_recente
                   FROM scout_feedback WHERE clube=?
                   GROUP BY motivo,papel ORDER BY mais_recente DESC LIMIT ?""",
                conn, params=[club, int(limit)])
    except Exception:
        return {"motivos": [], "amostra": 0}
    if rows.empty:
        return {"motivos": [], "amostra": 0}
    reasons = []
    for row in rows.to_dict("records"):
        reasons.extend([_safe_str(row.get("motivo"))] * min(3, int(row.get("ocorrencias") or 1)))
    try:
        with db.connect() as conn:
            names = pd.read_sql_query(
                """SELECT jogador,MAX(criado_em) AS mais_recente FROM scout_feedback
                   WHERE clube=? GROUP BY jogador ORDER BY mais_recente DESC LIMIT 80""",
                conn, params=[club])
    except Exception:
        names = pd.DataFrame(columns=["jogador"])
    return {"motivos": reasons, "amostra": int(rows["ocorrencias"].sum()),
            "posicoes": rows.to_dict("records"),
            "jogadores_recusados": names["jogador"].dropna().astype(str).tolist() if not names.empty else []}


def save_plan(db, club: str, name: str, payload: Dict[str, Any]) -> int:
    ensure_scout_tables(db)
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO scout_plans (clube,nome,payload_json) VALUES (?,?,?)", (club, name, encoded))
        return int(cur.lastrowid)


def export_markdown(club: str, financial: Dict[str, Any], roster_decisions: Dict[str, str],
                    signings: Sequence[Dict[str, Any]], simulation: Optional[Dict[str, Any]] = None) -> str:
    def euros(v):
        return "—" if _num(v) is None else f"€ {_num(v)/1e6:.2f} mi"
    lines = [f"# Dossiê de Scout — {club}", "", f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
             "", "## Janela planejada", ""]
    for name, decision in roster_decisions.items():
        lines.append(f"- {name}: {decision}")
    lines += ["", "## Contratações simuladas", ""]
    if not signings:
        lines.append("- Nenhuma contratação adicionada.")
    for p in signings:
        lines.append(f"- **{p.get('nome')}** — {p.get('papel_alvo_label') or p.get('funcao_legivel') or p.get('papel')} | "
                     f"qualidade {p.get('qualidade', '—')} | realismo {((p.get('realismo') or {}).get('score', '—'))}% | "
                     f"taxa estimada {euros((p.get('realismo') or {}).get('taxa_estimada_eur'))}")
    lines += ["", "## Referência financeira", "",
              f"- Valor estimado do elenco: {euros(financial.get('valor_elenco_eur'))}",
              f"- Faixa de investimento proxy: " +
              (f"{euros(financial['faixa_proxy_eur'][0])} a {euros(financial['faixa_proxy_eur'][1])}"
               if financial.get("faixa_proxy_eur") else "indisponível"),
              "- Não representa orçamento oficial nem inclui salários."]
    if simulation:
        lines += ["", "## Simulação do XI", ""]
        for d in simulation.get("deltas", []):
            lines.append(f"- {d['indicador']}: {d['antes']} → {d['depois']} ({d['variacao']:+})")
        lines.append(f"- Limite: {simulation.get('limite')}")
    return "\n".join(lines)


# ------------------------------------------------------------------ rodada 13: números do elenco pelo PRÓPRIO clube
def club_player_stats(db, team_names: Sequence[str], days: int = 365) -> pd.DataFrame:
    """Minutos, jogos, nota e números por 90 de cada atleta DESTE clube nos últimos `days` dias.

    O histórico global do Scout é ligado pelo nome; nomes comuns (Matheus Pereira, Lucas Silva, William) têm
    homônimos e ficavam sem números. Aqui a busca é pelos jogos do próprio clube — sem ambiguidade."""
    names = [str(n) for n in team_names if n]
    if not names:
        return pd.DataFrame()
    since = (date.today() - timedelta(days=int(days))).isoformat()
    ph = ",".join("?" * len(names))
    q = f"""SELECT p.match_id, p.team_name, p.player_name, p.minutes, p.rating, p.stats_json, m.match_date,
                   m.competition_name
            FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id
            WHERE p.team_name IN ({ph}) AND m.match_date >= ? AND COALESCE(p.minutes, 0) > 0{comp_sql([], "m")}"""
    try:
        with db.connect() as conn:
            raw = pd.read_sql_query(q, conn, params=[*names, since])
    except Exception:
        return pd.DataFrame()
    if raw.empty:
        return pd.DataFrame()
    raw["_core"] = raw["player_name"].map(player_core)
    # mesmo jogo vindo de duas fontes (ESPN e FotMob) conta uma vez: fica a linha com mais minutos
    raw["_d"] = raw["match_date"].astype(str).str[:10]
    raw = raw.sort_values("minutes", ascending=False).drop_duplicates(["_core", "_d"])
    rows = []
    for core, g in raw.groupby("_core"):
        t = _player_season_totals(g)
        t.update({"_core": core, "nome_jogos": g["player_name"].mode().iat[0],
                  "minutos_12m": t.get("minutos"), "jogos_12m": t.get("jogos"), "rating_12m": t.get("rating_media")})
        rows.append(t)
    return pd.DataFrame(rows)


def roster_quality(roster: pd.DataFrame, universe: pd.DataFrame, per_role: int = 1200) -> pd.DataFrame:
    """Qualidade do elenco calculada na MESMA régua do mercado (pares da função no universo), para quem teve os números
    preenchidos pelos jogos do clube. Amostra até `per_role` pares por função (rápido; percentis estáveis)."""
    if roster is None or roster.empty or universe is None or universe.empty or "papel" not in roster:
        return pd.DataFrame()
    roles = set(roster["papel"].dropna().astype(str))
    pool = universe[universe["papel"].isin(roles)]
    m = pd.to_numeric(pool.get("minutos_12m"), errors="coerce").fillna(0)
    pool = pool[m >= 450]
    pool = pool.groupby("papel", group_keys=False).apply(lambda g: g.sample(min(len(g), per_role), random_state=1))
    r = roster.copy()
    r["_roster_row"] = True
    pool = pool.copy()
    pool["_roster_row"] = False
    both = pd.concat([pool, r], ignore_index=True, sort=False)
    q = add_quality_scores(both)
    try:                                                 # rodada 20: mesma escala do mercado (overall contra o universo)
        from src.scout.overall import finalize_overall

        if "_ovr_z" in universe:
            q = finalize_overall(q.drop(columns=["qualidade_base"], errors="ignore"), reference=universe)
    except Exception:
        pass
    try:
        from src.scout.traits import add_traits

        q = add_traits(q)
    except Exception:
        pass
    keep = [c for c in ("qualidade", "confianca_pct", "potencial_teto", "precocidade", "caracteristicas",
                        "caracteristicas_top") if c in q]
    out = q.loc[q["_roster_row"] == True, keep]  # noqa: E712
    out.index = r.index
    return out


# ------------------------------------------------------------------ rodada 19: avaliação dos Rankings no Scout
SA_COUNTRY_WORDS = ("argentin", "paragua", "urugua", "chile", "colomb", "colômb", "equador", "ecuador", "peru", "bolivia",
                    "bolívia", "conmebol", "copa américa", "recopa",
                    "venezuel", "libertadores", "sudamericana", "sul-americana", "liga profesional", "primera division",
                    "primera división", "liga betplay", "liga pro", "liga 1")


ORIGIN_PARENTS = {
    # rodada 24: "América do Sul" inclui o Brasil; "Brasil (todas)" junta as séries; "Todas" = todo o universo
    "Brasil (todas as séries)": ("Brasil · Série A e copas", "Brasil · Série B", "Brasil · Série C", "Brasil · Série D"),
    "América do Sul (com Brasil)": ("Brasil · Série A e copas", "Brasil · Série B", "Brasil · Série C", "Brasil · Série D",
                                    "América do Sul"),
}


def origin_options(present: Iterable[str]) -> List[str]:
    present = [str(x) for x in present if str(x)]
    return ["Todas"] + list(ORIGIN_PARENTS) + sorted(set(present))


def origin_match(series: pd.Series, choice: str) -> pd.Series:
    if choice in ("", "Todas"):
        return pd.Series(True, index=series.index)
    allowed = ORIGIN_PARENTS.get(choice, (choice,))
    return series.astype(str).isin(allowed)


def origin_group_full(comp: Any, country: Any = None) -> str:
    """origin_group + país do clube quando a liga não diz (cadastro com código de liga, clube sem liga)."""
    g = origin_group(comp)
    if g not in ("Europa e outras", "Sem liga identificada"):
        return g
    c = _safe_str(country).lower()
    if c in ("brazil", "brasil"):
        return "Brasil · Série A e copas" if g == "Europa e outras" and "2" not in _safe_str(comp) else "Brasil · Série B"
    if any(w in c for w in SA_COUNTRY_WORDS) or c in ("venezuela", "bolivia", "bolívia", "peru", "colombia", "colômbia"):
        return "América do Sul"
    if c in ("united states", "usa", "estados unidos", "mexico", "méxico", "canada", "canadá"):
        return "América do Norte"
    return g


def origin_group(comp: Any) -> str:
    """Atalho de origem para o filtro do Scout (pelo nome da competição/liga)."""
    s = _safe_str(comp).lower()
    if not s:
        return "Sem liga identificada"
    if s in ("bra1", "bra2", "bra3"):
        return {"bra1": "Brasil · Série A e copas", "bra2": "Brasil · Série B", "bra3": "Brasil · Série C"}[s]
    if "série b" in s or "serie b" in s and ("brasil" in s or "brazil" in s):
        return "Brasil · Série B"
    if "série c" in s or "serie c" in s and ("brasil" in s or "brazil" in s):
        return "Brasil · Série C"
    if "série d" in s or "serie d" in s and ("brasil" in s or "brazil" in s):
        return "Brasil · Série D"
    if "brasileir" in s or "série a" in s or "copa do brasil" in s or "supercopa do brasil" in s or "paulist" in s \
            or any(w in s for w in ("carioca", "mineiro", "gaúcho", "gaucho", "nordeste", "baiano", "goiano")):
        return "Brasil · Série A e copas"
    if any(w in s for w in SA_COUNTRY_WORDS):
        return "América do Sul"
    if any(w in s for w in ("mls", "liga mx", "usl", "méxico", "mexico")):
        return "América do Norte"
    return "Europa e outras"


def merge_rankings(universe: pd.DataFrame, evals: Optional[pd.DataFrame]) -> pd.DataFrame:
    """
    Junta a avaliação da tela Rankings (percentil dentro da função e da competição, levada à régua de nível da
    competição — `geral_entre_ligas`) à qualidade do Scout. Peso da avaliação: 25% a 45%, crescendo com os minutos
    (1.800 min = peso cheio). Homônimos ficam de fora (não chuta). Também completa idade, valor e liga de quem não está
    no Transfermarkt (elenco da FotMob / Wikidata) e marca a competição principal.
    """
    if universe is None or universe.empty:
        return universe
    u = universe.copy()
    for c in ("nota_rankings", "competicao_principal", "funcao_rankings", "nivel_competicao_principal"):
        if c not in u:
            u[c] = np.nan if c.startswith(("nota", "nivel")) else ""
    if evals is not None and not evals.empty and "core" in evals:
        e = evals.copy()
        e["minutes"] = pd.to_numeric(e["minutes"], errors="coerce").fillna(0)
        e = e.sort_values("minutes", ascending=False).drop_duplicates("core", keep="first")
        lvl = pd.to_numeric(e.get("nivel_competicao"), errors="coerce").fillna(.5)
        d90 = pd.to_numeric(e.get("desempenho_90"), errors="coerce")
        nota = pd.to_numeric(e.get("geral_entre_ligas"), errors="coerce")
        nota = nota.fillna((d90 * (.45 + .55 * lvl)).where(e["minutes"] >= 450))
        e["_nota"] = nota.round(1)
        e = e.set_index("core")
        core = u["_core"].astype(str) if "_core" in u else u["nome"].map(player_core)
        blocked = core.duplicated(keep=False)
        if "historico_ambiguo" in u:
            blocked = blocked | u["historico_ambiguo"].fillna(False).astype(bool)
        ok = core.isin(e.index) & ~blocked
        take = core.where(ok)
        u["nota_rankings"] = take.map(e["_nota"])
        u["competicao_principal"] = take.map(e["comp"]).fillna(u["competicao_principal"].fillna(""))
        if "funcao" in e:
            u["funcao_rankings"] = take.map(e["funcao"]).fillna("")
        u["nivel_competicao_principal"] = take.map(e.get("nivel_competicao"))
        mins = take.map(e["minutes"]).fillna(0)
        for src_col, dst in (("idade", "idade"), ("valor_eur", "valor_mercado_eur")):
            if src_col in e and dst in u:
                cur = pd.to_numeric(u[dst], errors="coerce")
                u[dst] = cur.where(cur.notna(), pd.to_numeric(take.map(e[src_col]), errors="coerce"))
        q = pd.to_numeric(u.get("qualidade"), errors="coerce")
        n = pd.to_numeric(u["nota_rankings"], errors="coerce")
        w = (.25 + .20 * (mins / 1800).clip(0, 1))
        both = q.notna() & n.notna()
        only = q.isna() & n.notna()
        u.loc[both, "qualidade"] = ((1 - w[both]) * q[both] + w[both] * n[both]).round(1)
        u.loc[only, "qualidade"] = (50 + (n[only] - 50) * .8).round(1)       # só a avaliação: puxada à média
        src = u.get("fonte_qualidade", pd.Series("", index=u.index)).fillna("").astype(str)
        u.loc[both, "fonte_qualidade"] = src[both] + " · com " + (w[both] * 100).round().astype(int).astype(str) + \
            "% da avaliação dos Rankings"
        u.loc[only, "fonte_qualidade"] = "avaliação dos Rankings (percentil na função × nível da competição)"
    liga = u.get("clube_liga", pd.Series("", index=u.index)).fillna("").astype(str)
    last_comp = u.get("ultima_competicao", pd.Series("", index=u.index)).fillna("").astype(str)
    main_comp = u["competicao_principal"].fillna("").astype(str)
    # rodada 24: clube trocado pelo da última partida (Casemiro no Inter Miami) → a liga é a do jogo recente, não a
    # liga do clube antigo ("Premier League" ao lado do Inter Miami)
    observed = u.get("clube_observado", pd.Series(False, index=u.index)).fillna(False).astype(bool)
    fallback = np.where(observed & (last_comp != ""), last_comp, np.where(main_comp != "", main_comp, last_comp))
    u["clube_liga"] = liga.where(liga.str.strip() != "", pd.Series(fallback, index=u.index))
    # rodada 27: clube homônimo de outro país no cadastro (Mauro Coronel no "Nacional" do Paraguai aparecia na Liga
    # Portugal, liga do CD Nacional): se a liga NACIONAL dos jogos recentes é de outro país, valem os jogos
    try:
        from src.data_hub.gender import comp_country

        cc_liga = u["clube_liga"].map(lambda x: comp_country(x) if isinstance(x, str) else None)
        cc_last = last_comp.map(lambda x: comp_country(x) if x else None)
        clash = cc_liga.notna() & cc_last.notna() & (cc_liga != cc_last)
        u.loc[clash, "clube_liga"] = last_comp[clash]
    except Exception:
        pass
    try:                                                   # rodada 27: um nome por liga
        from src.scout.evaluation import canonical_league

        _m = {x: canonical_league(x) for x in u["clube_liga"].dropna().unique()}
        u["clube_liga"] = u["clube_liga"].map(lambda x: _m.get(x, x))
    except Exception:
        pass
    pais = u.get("clube_pais", pd.Series(None, index=u.index))
    u["origem"] = [origin_group_full(l, c) for l, c in zip(u["clube_liga"], pais)]
    return u


# ------------------------------------------------------------------ rodada 20: clube com um nome só e homônimos pelo clube
def canonical_clubs(universe: pd.DataFrame) -> pd.DataFrame:
    """O mesmo clube aparecia com dois nomes ("Cruzeiro" pela FotMob, "Cruzeiro Esporte Clube" pelo Transfermarkt) e o
    elenco ficava partido em dois no filtro "Clube atual". Escolhe UM nome por clube (o mais usado nos jogos recentes)."""
    if universe is None or universe.empty or "clube" not in universe:
        return universe
    u = universe.copy()
    club = u["clube"].fillna("").astype(str)
    core = club.map(lambda c: team_core(c) if c else "")
    # rodada 25: núcleo igual em REGIÕES diferentes não é o mesmo clube ("Barcelona" da Espanha × "Barcelona SC" do
    # Equador — Raphinha e Pedri apareciam no Barcelona SC)
    liga = u.get("clube_liga", pd.Series("", index=u.index))
    pais = u.get("clube_pais", pd.Series(None, index=u.index))
    region = pd.Series([origin_group_full(l, p).split(" · ")[0] for l, p in zip(liga, pais)], index=u.index)
    base = core.copy()
    unk = region.eq("Sem liga identificada")
    if (~unk).any():                       # sem liga: fica com a região mais comum desse nome
        dom = pd.DataFrame({"c": base[~unk], "r": region[~unk]}).value_counts().reset_index().drop_duplicates("c")
        region = region.where(~unk, base.map(dict(zip(dom["c"], dom["r"]))).fillna("Sem liga identificada"))
    core = core.where(core == "", core + "|" + region)
    observed = u.get("clube_observado", pd.Series(False, index=u.index)).fillna(False).astype(bool)
    pref = pd.DataFrame({"core": core, "club": club, "obs": observed.astype(int)})
    pref = pref[pref["core"] != ""]
    if pref.empty:
        return u
    best = (pref.groupby(["core", "club"]).agg(obs=("obs", "sum"), n=("obs", "size")).reset_index()
            .sort_values(["core", "obs", "n"], ascending=[True, False, False]).drop_duplicates("core"))
    name_of = dict(zip(best["core"], best["club"]))
    new = core.map(name_of)
    change = new.notna() & (new != club) & (club != "")
    if "clube_tm" in u:
        u.loc[change & u["clube_tm"].isna(), "clube_tm"] = club[change & u["clube_tm"].isna()]
    u.loc[change, "clube"] = new[change]
    # rodada 27: nomes que existem em dois países — o da liga do jogador manda (Raphinha, Olmo e De Jong apareciam no
    # "Barcelona SC" do Equador mesmo com a liga "laliga")
    for name, home_region, other in (("Barcelona SC", "América do Sul", "Barcelona"),):
        hit = u["clube"].eq(name) & region.ne(home_region) & ~region.eq("Sem liga identificada")
        if hit.any():
            u.loc[hit, "clube"] = other
    return u


def fill_homonyms_from_club(db, universe: pd.DataFrame, days: int = 365) -> pd.DataFrame:
    """Homônimos (dois "Matheus Pereira") não recebem o histórico somado pelo nome — que mistura os dois. Aqui cada um
    recebe minutos, jogos e nota dos jogos do PRÓPRIO clube no último ano (nome + clube), só se ainda estiver sem."""
    if universe is None or universe.empty:
        return universe
    u = universe.copy()
    mins = pd.to_numeric(u.get("minutos_12m"), errors="coerce")
    dup = u["_core"].duplicated(keep=False) if "_core" in u else pd.Series(False, index=u.index)
    amb = u.get("historico_ambiguo", pd.Series(False, index=u.index)).fillna(False).astype(bool)
    need = (dup | amb) & (mins.isna() | (mins <= 0))
    if not need.any():
        return u
    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        with db.connect() as conn:
            g = pd.read_sql_query(
                f"""SELECT p.player_name, p.team_name, SUM(COALESCE(p.minutes,0)) AS mins, COUNT(DISTINCT p.match_id) AS games,
                           SUM(p.rating * COALESCE(p.minutes,0)) / NULLIF(SUM(CASE WHEN p.rating IS NOT NULL THEN p.minutes END),0) AS rating
                    FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id
                    WHERE m.match_date >= ? AND COALESCE(p.minutes,0) > 0{comp_sql([], "m")}
                    GROUP BY p.player_name, p.team_name""", conn, params=[since])
    except Exception:
        return u
    if g.empty:
        return u
    g["core"] = g["player_name"].map(player_core)
    g["club_core"] = g["team_name"].map(team_core)
    g = g.groupby(["core", "club_core"], as_index=False).agg(mins=("mins", "sum"), games=("games", "sum"),
                                                            rating=("rating", "mean"))
    key = dict(zip(zip(g["core"], g["club_core"]), g[["mins", "games", "rating"]].itertuples(index=False, name=None)))
    for i in u.index[need]:
        for club_col in ("clube", "clube_tm"):
            c = _safe_str(u.at[i, club_col]) if club_col in u else ""
            hit = key.get((str(u.at[i, "_core"]), team_core(c))) if c else None
            if hit:
                m_, g_, r_ = hit
                u.at[i, "minutos_12m"] = m_
                u.at[i, "jogos_12m"] = g_
                if pd.notna(r_):
                    u.at[i, "rating_12m"] = round(float(r_), 2)
                if pd.isna(pd.to_numeric(u.at[i, "minutos"], errors="coerce")) if "minutos" in u else True:
                    u.at[i, "minutos"] = m_
                    u.at[i, "jogos"] = g_
                u.at[i, "fonte_clube_observado"] = "jogos do próprio clube (homônimo separado pelo clube)"
                break
    return u


def youth_caps(db) -> pd.DataFrame:
    """Rodada 20: jogos por SELEÇÃO DE BASE (Mundial Sub-20/Sub-17, Sul-Americano Sub-20, Euros de base) por atleta —
    entra no POTENCIAL e vira característica; não mistura com os números de clube."""
    try:
        from src.data_hub.sources.fotmob import YOUTH_NAMES
    except Exception:
        return pd.DataFrame()
    names = sorted(YOUTH_NAMES)
    ph = ",".join("?" * len(names))
    try:
        with db.connect() as conn:
            r = pd.read_sql_query(
                f"""SELECT player_name, competition_name, COUNT(DISTINCT match_id) AS jogos, AVG(nota) AS nota,
                           MAX(fid) AS fotmob_id, MAX(selecao) AS selecao, MAX(dia) AS ultimo_base FROM (
                        SELECT p.player_name, m.competition_name, m.match_id, p.rating AS nota,
                               CAST(json_extract(p.stats_json, '$.fotmob_id') AS INTEGER) AS fid, p.team_name AS selecao,
                               m.match_date AS dia
                        FROM match_player_stats p
                        JOIN matches m ON m.match_id = p.match_id
                        WHERE m.competition_name IN ({ph}) AND COALESCE(p.minutes, 0) > 0
                        UNION
                        SELECT l.player_name, m.competition_name, m.match_id, NULL AS nota, NULL AS fid, l.team_name,
                               m.match_date AS dia
                        FROM match_lineups l
                        JOIN matches m ON m.match_id = l.match_id
                        WHERE m.competition_name IN ({ph}) AND l.is_starter = 1)
                    GROUP BY player_name, competition_name""", conn, params=[*names, *names])
    except Exception:
        return pd.DataFrame()
    if r.empty:
        return r
    r["core"] = r["player_name"].map(player_core)
    # rodada 22: "os melhores de cada seleção e competição" — percentil da nota DENTRO da competição de base (≥ 2 jogos)
    r["nota"] = pd.to_numeric(r["nota"], errors="coerce")
    r["pct"] = r["nota"].where(r["jogos"] >= 2).groupby(r["competition_name"]).rank(pct=True) * 100
    # rodada 27: idade ESTIMADA pela categoria — quem jogou o Mundial Sub-17 em 2025 tem no máximo 17 + (hoje − 2025)
    lim = r["competition_name"].astype(str).str.extract(r"(?:Sub|U)-?\s?(\d{2})", expand=False)
    lim = pd.to_numeric(lim, errors="coerce").where(lambda x: x.between(15, 23))
    yrs = (pd.Timestamp.today() - pd.to_datetime(r["ultimo_base"], errors="coerce")).dt.days / 365.25
    r["idade_max_base"] = (lim + yrs).round(1)
    out = r.groupby("core").agg(selecao_base_jogos=("jogos", "sum"), idade_max_base=("idade_max_base", "min"),
                                selecao_base_comp=("competition_name", lambda x: " · ".join(sorted(set(x)))),
                                selecao_base_nota=("nota", "mean"), selecao_base_pct=("pct", "max"),
                                fotmob_id=("fotmob_id", "max"), selecao=("selecao", "first"),
                                sub17=("competition_name", lambda x: any("17" in str(c) for c in x)))
    out = out.reset_index()
    # rodada 22: o MESMO atleta no clube — pelo id da FotMob (nunca só pelo nome): elenco atual (fotmob_rosters) e o
    # último jogo dele por um CLUBE (números por jogador com o mesmo fotmob_id)
    try:
        out["player_name"] = out["core"].map(r.drop_duplicates("core").set_index("core")["player_name"])
        out = out.merge(youth_identities(db, out["fotmob_id"].dropna().astype("int64").tolist(),
                                         out["player_name"].dropna().tolist()), on="fotmob_id", how="left")
    except Exception:
        pass
    return out


SENIOR_COMP = r"(?i)world cup|copa do mundo|qualif|elimin|friendl|amistos|copa am|nations league|liga das na|euro\b|" \
              r"european championship|gold cup|africa cup|african nations|asian cup|concacaf|conmebol|finalissima"
YOUTH_TEAM = r"(?i)\b(u-?\d{2}|sub-?\d{2}|olympic|olimpic|women|feminin)\b"


def senior_caps(db, years: int = 3) -> pd.DataFrame:
    """Rodada 27e — jogos pela SELEÇÃO PRINCIPAL (adulta) nos últimos anos, por atleta (id da FotMob quando há).
    Ser convocado para a seleção principal aos 20 anos (Otávio, goleiro do Cruzeiro) é dos sinais mais fortes de
    potencial que existem; antes só a base (Sub-17/Sub-20) entrava."""
    from src.squad.planner import national_team_key

    since = (pd.Timestamp.today() - pd.Timedelta(days=365 * years)).date().isoformat()
    try:
        with db.connect() as conn:
            r = pd.read_sql_query(
                """SELECT p.player_name, p.team_name, m.competition_name, m.match_id, m.match_date, p.minutes, p.rating,
                          CAST(json_extract(p.stats_json, '$.fotmob_id') AS INTEGER) AS fotmob_id
                   FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id
                   WHERE m.match_date >= ? AND COALESCE(p.minutes, 0) > 0""", conn, params=(since,))
            lu = pd.read_sql_query(
                """SELECT l.player_name, l.team_name, m.competition_name, m.match_id, m.match_date, NULL AS minutes,
                          NULL AS rating, NULL AS fotmob_id
                   FROM match_lineups l JOIN matches m ON m.match_id = l.match_id
                   WHERE m.match_date >= ? AND l.is_starter = 1""", conn, params=(since,))
    except Exception:
        return pd.DataFrame()
    r = pd.concat([r, lu[~lu["match_id"].isin(r["match_id"])]], ignore_index=True)
    if r.empty:
        return pd.DataFrame()
    r = r[r["competition_name"].astype(str).str.contains(SENIOR_COMP, regex=True)
          & ~r["competition_name"].astype(str).str.contains(YOUTH_TEAM, regex=True)
          & ~r["team_name"].astype(str).str.contains(YOUTH_TEAM, regex=True)]
    if r.empty:
        return pd.DataFrame()
    teams = pd.Series(r["team_name"].unique())
    nat = dict(zip(teams, teams.map(national_team_key)))
    r = r.assign(pais=r["team_name"].map(nat))
    r = r[r["pais"].fillna("") != ""]
    if r.empty:
        return pd.DataFrame()
    r["core"] = r["player_name"].map(player_core)
    out = r.groupby("core").agg(selecao_principal_jogos=("match_id", "nunique"),
                                selecao_principal_min=("minutes", lambda x: float(pd.to_numeric(x, errors="coerce").sum())),
                                selecao_principal=("team_name", "first"), selecao_principal_pais=("pais", "first"),
                                selecao_principal_ultimo=("match_date", "max"),
                                fotmob_id=("fotmob_id", "max")).reset_index()
    return out


def merge_senior(universe: pd.DataFrame, caps: pd.DataFrame) -> pd.DataFrame:
    """Liga as convocações ao atleta: pelo id da FotMob; sem id, só núcleo de nome ÚNICO e com a nacionalidade da
    seleção conferindo (nunca um homônimo de outro país)."""
    if universe is None or universe.empty or caps is None or caps.empty:
        return universe
    u = universe.copy()
    cols = ["selecao_principal_jogos", "selecao_principal_min", "selecao_principal", "selecao_principal_ultimo"]
    by_id = caps.dropna(subset=["fotmob_id"]).drop_duplicates("fotmob_id").set_index("fotmob_id")
    fid = pd.to_numeric(u.get("fotmob_id"), errors="coerce") if "fotmob_id" in u else pd.Series(np.nan, index=u.index)
    core = u["_core"].astype(str) if "_core" in u else u["nome"].map(player_core)
    from src.squad.planner import national_team_key

    nat = u.get("nacionalidade", pd.Series("", index=u.index)).map(lambda x: national_team_key(str(x or "")))
    unique = ~core.duplicated(keep=False)
    by_core = caps.drop_duplicates("core").set_index("core")
    for c in cols:
        v_id = fid.map(by_id[c]) if c in by_id else pd.Series(np.nan, index=u.index)
        country_ok = core.map(by_core["selecao_principal_pais"]).eq(nat) | nat.eq("")
        v_core = core.where(unique & country_ok).map(by_core[c]) if c in by_core else pd.Series(np.nan, index=u.index)
        u[c] = v_id.combine_first(v_core)
    return u


def youth_identities(db, ids: List[int], names: Optional[List[str]] = None) -> pd.DataFrame:
    """fotmob_id → clube atual, nascimento, país, valor, altura e posição (elenco FotMob) ou, sem elenco, o último clube
    em que ele jogou (números por jogador). Seleção não conta como clube."""
    cols = ["fotmob_id", "clube_base", "nascimento_base", "pais_base", "valor_base", "altura_base", "posicao_base"]
    ids = sorted({int(i) for i in ids if pd.notna(i) and int(i) > 0})
    if not ids:
        return pd.DataFrame(columns=cols)
    from src.squad.planner import national_team_key

    with db.connect() as conn:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _y_ids (i INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM _y_ids")
        conn.executemany("INSERT OR IGNORE INTO _y_ids VALUES (?)", [(i,) for i in ids])
        has_ro = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'fotmob_rosters'").fetchone()
        try:
            if not has_ro:                       # (uma consulta que falha desfaz a tabela temporária)
                raise LookupError("sem elencos da FotMob")
            ro = pd.read_sql_query("SELECT r.player_id AS fotmob_id, r.team AS clube_base, r.birth AS nascimento_base, "
                                   "r.country AS pais_base, r.market_value AS valor_base, r.height AS altura_base, "
                                   "r.position AS posicao_base, r.fetched_at FROM fotmob_rosters r "
                                   "JOIN _y_ids y ON y.i = r.player_id", conn)
        except Exception:
            ro = pd.DataFrame(columns=cols + ["fetched_at"])
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _y_names (n TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM _y_names")
        conn.executemany("INSERT OR IGNORE INTO _y_names VALUES (?)", [(n,) for n in (names or [])])
        # pelo índice de nome (só as linhas desses atletas) e conferindo o id da FotMob — homônimo não entra
        last = pd.read_sql_query(
            "SELECT CAST(json_extract(p.stats_json, '$.fotmob_id') AS INTEGER) AS fotmob_id, p.team_name, m.match_date "
            "FROM _y_names y JOIN match_player_stats p ON p.player_name = y.n JOIN matches m ON m.match_id = p.match_id "
            "WHERE CAST(json_extract(p.stats_json, '$.fotmob_id') AS INTEGER) IN (SELECT i FROM _y_ids)", conn)
    ro = ro[[not national_team_key(str(t or "")) for t in ro["clube_base"]]] if not ro.empty else ro
    ro = ro.sort_values("fetched_at").drop_duplicates("fotmob_id", keep="last").drop(columns=["fetched_at"], errors="ignore")
    if not last.empty:
        last = last[[not national_team_key(str(t or "")) for t in last["team_name"]]]
        last = last.sort_values("match_date").drop_duplicates("fotmob_id", keep="last")
        miss = last[~last["fotmob_id"].isin(ro["fotmob_id"])].rename(columns={"team_name": "clube_base"})
        ro = pd.concat([ro, miss[["fotmob_id", "clube_base"]]], ignore_index=True)
    return ro.reindex(columns=cols)


def merge_youth(universe: pd.DataFrame, caps: pd.DataFrame) -> pd.DataFrame:
    """Liga os jogos de base ao atleta (só núcleo de nome ÚNICO no universo e idade ≤ 24 ou desconhecida)."""
    if universe is None or universe.empty or caps is None or caps.empty:
        return universe
    u = universe.copy()
    core = u["_core"].astype(str) if "_core" in u else u["nome"].map(player_core)
    age = pd.to_numeric(u.get("idade"), errors="coerce") if "idade" in u else pd.Series(np.nan, index=u.index)
    ok = ~core.duplicated(keep=False) & (age.isna() | age.le(24))
    caps = caps.drop_duplicates("core")
    c = caps.set_index("core")
    # rodada 22: nome repetido no universo deixa de ser descartado quando o CLUBE confere (id da FotMob → clube)
    if "clube_base" in c and "clube" in u:
        from src.data_lake.ids import team_core

        club_of = c["clube_base"].dropna().map(lambda x: team_core(str(x)))
        same_club = [bool(cc in club_of.index and team_core(str(cl or "")) == club_of.get(cc)) for cc, cl in zip(core, u["clube"])]
        ok = ok | (pd.Series(same_club, index=u.index) & (age.isna() | age.le(24)))
    for col in ("selecao_base_jogos", "selecao_base_comp", "selecao_base_nota", "selecao_base_pct", "selecao",
                "idade_max_base"):
        if col in c:
            u[col] = core.where(ok).map(c[col])
    # rodada 27: sem data de nascimento em nenhuma fonte → idade ESTIMADA pela categoria de base (limite da categoria
    # + anos desde o último jogo, menos meio ano), marcada como estimativa
    if "idade_max_base" in u:
        est = (pd.to_numeric(u["idade_max_base"], errors="coerce") - .5).round(0)
        miss = pd.to_numeric(u.get("idade"), errors="coerce").isna() & est.notna()
        u.loc[miss, "idade"] = est[miss]
        u.loc[miss, "idade_estimada"] = "pela categoria de base"
    return u


YOUTH_LEVEL = {"sub20": (50.0, 72.0), "sub17": (46.0, 66.0)}


def youth_only_players(universe: pd.DataFrame, caps: pd.DataFrame) -> pd.DataFrame:
    """Rodada 22: atletas de seleção de base que NÃO estão no universo (não têm jogos de clube na base). Entram com o
    clube pelo id da FotMob e uma QUALIDADE ESTIMADA pelo nível de base — a nota na competição de base vira um overall
    num intervalo baixo (Sub-20: 50–72 · Sub-17: 46–66), porque jogar bem na base não é jogar bem entre profissionais.
    Sempre marcado como estimativa; sem nota na base, sem qualidade (lacuna)."""
    if caps is None or caps.empty:
        return pd.DataFrame()
    have = set(universe["_core"].astype(str)) if universe is not None and "_core" in universe else set()
    y = caps[~caps["core"].astype(str).isin(have)].copy()
    if y.empty:
        return pd.DataFrame()
    birth = pd.to_datetime(y.get("nascimento_base"), errors="coerce") if "nascimento_base" in y else pd.Series(pd.NaT, index=y.index)
    age = ((pd.Timestamp.today() - birth).dt.days / 365.25).round(1)
    if "idade_max_base" in y:                       # rodada 27: sem nascimento → idade estimada pela categoria
        age = age.fillna((pd.to_numeric(y["idade_max_base"], errors="coerce") - .5).round(0))
    lo_hi = np.where(y["sub17"].fillna(False), "sub17", "sub20")
    lo = np.array([YOUTH_LEVEL[k][0] for k in lo_hi])
    hi = np.array([YOUTH_LEVEL[k][1] for k in lo_hi])
    pct = pd.to_numeric(y.get("selecao_base_pct"), errors="coerce")
    q = pd.Series(lo + (hi - lo) * (pct / 100), index=y.index).where(pct.notna())
    out = pd.DataFrame({
        "nome": y["player_name"].values if "player_name" in y else y["core"].values, "_core": y["core"].values,
        "clube": y.get("clube_base"), "idade": age.values, "nacionalidade": y.get("pais_base"),
        "valor_mercado_eur": pd.to_numeric(y.get("valor_base"), errors="coerce"),
        "altura_cm": pd.to_numeric(y.get("altura_base"), errors="coerce"),
        "papel": [_role(p) if isinstance(p, str) and p else "" for p in y.get("posicao_base", pd.Series("", index=y.index))],
        "qualidade": q.round(0).values, "selecao_base_jogos": y["selecao_base_jogos"].values,
        "selecao_base_comp": y["selecao_base_comp"].values, "selecao_base_pct": pct.values,
        "selecao": y.get("selecao"),
        "fonte_qualidade": "ESTIMADA pela seleção de base (nota na competição de base levada ao nível de base)",
        "so_base": True}, index=y.index)
    return out.reset_index(drop=True)


# ================================================================== rodada 27: números da seleção de base no perfil
YOUTH_STAT_KEYS = [("Gols", ("goals", "totalGoals")), ("Assistências", ("assists", "goalAssists", "goal_assist")),
                   ("xG", ("xg", "expected_goals")), ("xA", ("xa", "expected_assists")),
                   ("Chances criadas", ("chances_created",)), ("Dribles certos", ("dribbles_succeeded",)),
                   ("Passes no terço final", ("passes_into_final_third",)), ("Desarmes", ("matchstats.headers.tackles", "tackles")),
                   ("Interceptações", ("interceptions",)), ("Recuperações", ("recoveries",)),
                   ("Duelos ganhos", ("duel_won",)), ("Aéreos ganhos", ("aerials_won",)), ("Toques", ("touches",))]


def youth_profile(db, names: List[str]) -> Dict[str, Any]:
    """Jogos do atleta por SELEÇÃO DE BASE e base de clubes (Mundial Sub-17/20, Sul-Americano, Euros, Youth League…):
    por competição (jogos, minutos, titular, nota média) e os números somados e por 90. Fica no perfil dele — separado
    dos números de clube (jogar bem na base não é jogar bem entre profissionais)."""
    try:
        from src.data_hub.sources.fotmob import YOUTH_NAMES
    except Exception:
        return {}
    names = [str(n) for n in names if n]
    if not names:
        return {}
    comps = sorted(YOUTH_NAMES)
    ph_n, ph_c = ",".join("?" * len(names)), ",".join("?" * len(comps))
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(
                f"SELECT m.match_id, m.match_date, m.competition_name, p.team_name, p.minutes, p.rating, p.stats_json, "
                f"(SELECT MAX(l.is_starter) FROM match_lineups l WHERE l.match_id = p.match_id AND l.player_name = p.player_name) AS titular "
                f"FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id "
                f"WHERE p.player_name IN ({ph_n}) AND m.competition_name IN ({ph_c}) ORDER BY m.match_date DESC",
                conn, params=names + comps)
    except Exception:
        return {}
    if d.empty:
        return {}
    d = d.drop_duplicates("match_id")
    tot = {lab: 0.0 for lab, _ in YOUTH_STAT_KEYS}
    seen = {lab: False for lab, _ in YOUTH_STAT_KEYS}
    for js in d["stats_json"].dropna():
        try:
            j = json.loads(js)
        except Exception:
            continue
        for lab, keys in YOUTH_STAT_KEYS:
            v = next((j.get(k) for k in keys if j.get(k) is not None), None)
            try:
                if v is not None:
                    tot[lab] += float(v)
                    seen[lab] = True
            except (TypeError, ValueError):
                pass
    mins = float(pd.to_numeric(d["minutes"], errors="coerce").fillna(0).sum())
    by = (d.assign(minutes=pd.to_numeric(d["minutes"], errors="coerce"), rating=pd.to_numeric(d["rating"], errors="coerce"))
          .groupby(["competition_name", "team_name"])
          .agg(jogos=("match_id", "nunique"), minutos=("minutes", "sum"), titular=("titular", "sum"),
               nota=("rating", "mean"), ultimo=("match_date", "max")).reset_index()
          .sort_values("ultimo", ascending=False))
    numbers = [{"Número": lab, "Total": round(tot[lab], 2), "Por 90": round(tot[lab] * 90 / mins, 2) if mins >= 90 else None}
               for lab, _ in YOUTH_STAT_KEYS if seen[lab]]
    return {"jogos": int(d["match_id"].nunique()), "minutos": int(mins), "por_competicao": by, "numeros": numbers,
            "nota": float(pd.to_numeric(d["rating"], errors="coerce").mean()) if d["rating"].notna().any() else None}


def _game_dates(v) -> set:
    try:
        g = json.loads(v) if isinstance(v, str) else v
    except Exception:
        return set()
    return {str(x.get("match_date"))[:10] for x in g if isinstance(x, dict) and x.get("match_date")} if isinstance(g, list) else set()


def _absorb(d: pd.DataFrame, keep, gone) -> None:
    """Completa a linha que fica com o que só a outra tem; valor e potencial = o maior dos dois."""
    for col in d.columns:
        if col.startswith("_"):
            continue
        v0 = d.at[keep, col]
        if not isinstance(v0, (list, dict, tuple)) and pd.isna(v0):
            v = d.at[gone, col]
            if not (isinstance(v, float) and np.isnan(v)):
                d.at[keep, col] = v
    for col in ("valor_mercado_eur", "potencial", "potencial_teto", "qualidade"):
        if col in d:
            a_, b_ = pd.to_numeric(pd.Series([d.at[keep, col], d.at[gone, col]]), errors="coerce")
            if pd.notna(b_) and (pd.isna(a_) or b_ > a_):
                d.at[keep, col] = b_


def merge_club_aliases(u: pd.DataFrame) -> pd.DataFrame:
    """Rodada 27g — o MESMO atleta em duas linhas do mercado no mesmo clube: uma só do cadastro (sem minutos: "Otávio",
    Transfermarkt) e outra dos jogos ("Otavio Costa", FotMob, 3.465 min, potencial 86). O elenco pegava a do cadastro
    (65/71, € 500 mil). Junta só quando é seguro: mesmo clube, mesma família (goleiro × linha), um nome contido no
    outro (palavras), idade igual ±1 quando as duas existem e UMA das linhas sem minutos no ano. A linha com jogos fica;
    da outra vêm o que falta (valor, contrato, nascimento) e o nome curto vira apelido (`apelidos_core`)."""
    if u is None or u.empty or not {"nome", "clube"} <= set(u.columns):
        return u
    d = u.copy()
    core = d["_core"].astype(str) if "_core" in d else d["nome"].map(player_core)
    d["_core"] = core
    club = d["clube"].fillna("").astype(str).map(lambda c: team_core(c) if c else "")
    fam = d.get("papel", pd.Series("", index=d.index)).fillna("").astype(str).map(lambda r: "GK" if r == "GK" else "OUT")
    mins = pd.to_numeric(d.get("minutos_12m"), errors="coerce").fillna(0)
    age = pd.to_numeric(d.get("idade"), errors="coerce")
    drop, aliases = set(), {}
    key = club + "|" + fam
    for _k, idx in d[club != ""].groupby(key[club != ""]).groups.items():
        if len(idx) < 2:
            continue
        idx = list(idx)
        empty = [i for i in idx if mins[i] <= 0]
        played = [i for i in idx if mins[i] > 0]
        # rodada 27i: as DUAS linhas com jogos (ESPN "Otávio" 3.150 min × FotMob "Otavio Costa" 3.465 min) — é o mesmo
        # atleta quando os jogos coincidem (mesmas datas = os mesmos jogos vistos por duas fontes) e: é goleiro (só um
        # joga por partida) ou só uma das linhas tem o id da FotMob (fontes diferentes). A de menos minutos vira apelido.
        both = []
        for e in played:
            te = set(core[e].split())
            by_name = [p for p in played if p != e and (te < set(core[p].split()))]
            if len(by_name) != 1:
                continue
            p = by_name[0]
            if pd.notna(age[e]) and pd.notna(age[p]) and abs(age[e] - age[p]) > 1.2:
                continue
            de, dp = _game_dates(d.at[e, "ultimos_jogos"] if "ultimos_jogos" in d else None), \
                _game_dates(d.at[p, "ultimos_jogos"] if "ultimos_jogos" in d else None)
            if not de or not dp or len(de & dp) < .6 * min(len(de), len(dp)):
                continue
            fid = d.get("fotmob_id")
            one_id = fid is not None and (pd.notna(fid[e]) != pd.notna(fid[p]))
            if fam[e] == "GK" or one_id:
                keep, gone = (p, e) if mins[p] >= mins[e] else (e, p)
                both.append((gone, keep))
        for gone, keep in both:
            if gone in drop or keep in drop:
                continue
            _absorb(d, keep, gone)
            aliases.setdefault(keep, []).append(core[gone])
            drop.add(gone)
        if not empty or not played:
            continue
        for e in empty:
            te = set(core[e].split())
            if not te:
                continue
            by_name = [p for p in played if (te < set(core[p].split()) or set(core[p].split()) < te)]
            if len(by_name) != 1:
                continue                                   # nenhum ou dois "Gabriel …" com jogos: fica separado
            cands = [p for p in by_name if p not in drop
                     and not (pd.notna(age[e]) and pd.notna(age[p]) and abs(age[e] - age[p]) > 1.2)]
            if len(cands) != 1:
                continue                                   # nenhum ou ambíguo (dois "Gabriel …"): fica separado
            p = cands[0]
            _absorb(d, p, e)
            aliases.setdefault(p, []).append(core[e])
            drop.add(e)
    if not drop:
        return u
    d["apelidos_core"] = pd.Series({i: "|".join(v) for i, v in aliases.items()}).reindex(d.index)
    return d.drop(index=list(drop))
