"""
Scout & Planejamento — motor contextual, explicável e conservador.
Usa dados observados do lake/SQLite; estimativas financeiras e projeções táticas são rotuladas como tais.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import date, datetime, timedelta
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
    "CB": [("def_actions_p90", .22, True), ("interceptions_p90", .18, True),
           ("clearances_p90", .18, True), ("aerials_won_p90", .17, True),
           ("pass_accuracy_pct", .15, True), ("errors_p90", .10, False)],
    "FB": [("def_actions_p90", .18, True), ("interceptions_p90", .12, True),
           ("chances_created_p90", .20, True), ("xa_p90", .14, True),
           ("assists_p90", .12, True), ("sprints_p90", .12, True),
           ("pass_accuracy_pct", .12, True)],
    "DM": [("def_actions_p90", .22, True), ("interceptions_p90", .18, True),
           ("tackles_p90", .14, True), ("pass_accuracy_pct", .16, True),
           ("chances_created_p90", .12, True), ("xa_p90", .08, True),
           ("errors_p90", .10, False)],
    "MID": [("chances_created_p90", .18, True), ("xa_p90", .17, True),
            ("pass_accuracy_pct", .16, True), ("def_actions_p90", .14, True),
            ("interceptions_p90", .10, True), ("goals_p90", .10, True),
            ("xg_p90", .08, True), ("errors_p90", .07, False)],
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
    "tackles": "tackles", "recoveries": "recoveries", "clearances": "clearances",
    "aerials_won": "aerials_won", "dribbles": "successful_dribbles",
    "fouls": "foulsCommitted", "errors": "errors_led_to_goal", "saves": "saves",
    "xgot_faced": "xgot_faced", "yellow_cards": "yellow_cards", "red_cards": "red_cards",
}
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
    ratings = pd.to_numeric(rows.get("rating"), errors="coerce")
    valid = ratings.notna() & (mins > 0)
    out["rating_media"] = round(float(np.average(ratings[valid], weights=mins[valid])), 2) if valid.any() else None
    out["ultimo_jogo"] = _safe_str(rows["match_date"].max()) if "match_date" in rows else ""
    date_values = rows["match_date"].dropna().astype(str) if "match_date" in rows else pd.Series(dtype=str)
    latest = rows.loc[date_values.idxmax()] if not date_values.empty else (rows.iloc[-1] if len(rows) else {})
    out["ultimo_time"] = _safe_str(latest.get("team_name", "")) if isinstance(latest, pd.Series) else ""
    out["ultima_competicao"] = _safe_str(latest.get("competition_name", "")) if isinstance(latest, pd.Series) else ""

    # load_player_history injeta _parsed_stats por jogador. Isso evita fazer json.loads repetidamente
    # em cada métrica, temporada e janela de 12 meses. Chamadas externas continuam aceitando stats_json.
    if "_parsed_stats" in rows:
        parsed_stats = [x if isinstance(x, dict) else {} for x in rows["_parsed_stats"].tolist()]
    else:
        parsed_stats = [_json_obj(x) for x in rows.get("stats_json", pd.Series(dtype=object)).tolist()]

    for out_key, raw_key in COUNT_KEYS.items():
        vals = [_num(item.get(raw_key)) for item in parsed_stats]
        vals = [value for value in vals if value is not None]
        out[out_key] = float(sum(vals)) if vals else None
    if out["minutos"] > 0:
        for k in ("goals", "assists", "shots", "shots_on_target", "xg", "xa", "chances_created",
                  "def_actions", "sprints", "touches", "interceptions", "tackles", "recoveries",
                  "clearances", "aerials_won", "dribbles", "fouls", "errors", "saves", "xgot_faced"):
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
    out["ultimo_jogo"] = grouped["match_date"].max().astype(str)

    metric_names = list(COUNT_KEYS)
    metric_sums = grouped[metric_names].sum(min_count=1)
    for name in metric_names:
        out[name] = metric_sums[name]

    for name in ("goals", "assists", "shots", "shots_on_target", "xg", "xa",
                 "chances_created", "def_actions", "sprints", "touches", "interceptions",
                 "tackles", "recoveries", "clearances", "aerials_won", "dribbles",
                 "fouls", "errors", "saves", "xgot_faced"):
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

    # Uma única ordenação atende forma dos últimos cinco jogos e seleção do registro mais recente.
    chronological = rows.sort_values("match_date", ascending=True, kind="stable")
    forms = chronological.groupby(
        group_keys, dropna=False, sort=False, observed=True
    )["_rating_num"].agg(
        lambda values: [round(float(value), 2) for value in values.dropna().tail(5)]
    )
    out["forma_5"] = forms.reindex(out.index)

    latest = (
        chronological.drop_duplicates(group_keys, keep="last")
        .set_index(group_keys)
    )
    out["ultimo_time"] = latest["team_name"].reindex(out.index).fillna("")
    out["ultima_competicao"] = latest["competition_name"].reindex(out.index).fillna("")
    return out


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
    query = """
        SELECT p.match_id, p.team_name, p.player_name, p.position, p.minutes, p.rating, p.stats_json,
               m.match_date, m.season_name, m.competition_name, m.home_team_name, m.away_team_name
        FROM match_player_stats p
        JOIN matches m ON m.match_id = p.match_id
        WHERE m.match_date >= ? AND COALESCE(p.minutes, 0) > 0
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
                report("Identificando atletas ativos nos últimos 180 dias...")
                active_since = (date.today() - timedelta(days=180)).isoformat()
                active_rows = pd.read_sql_query(
                    """
                    SELECT p.player_name, p.match_id, SUM(COALESCE(p.minutes, 0)) AS minutes
                    FROM matches AS m
                    CROSS JOIN match_player_stats AS p INDEXED BY idx_pstats_match
                    WHERE p.match_id = m.match_id
                      AND m.match_date >= ?
                      AND COALESCE(p.minutes, 0) > 0
                      AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
                    GROUP BY p.player_name, p.match_id
                    """,
                    conn,
                    params=[active_since],
                )
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
                        (active_totals["minutos"] >= 450) & (active_totals["jogos"] >= 4)
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

    duplicate_mask = raw.duplicated(["_core", "_fixture", "_club_core"], keep=False)
    raw["_richness"] = 0
    if duplicate_mask.any():
        # Riqueza só é necessária para escolher entre duplicatas do mesmo jogo real.
        raw.loc[duplicate_mask, "_richness"] = raw.loc[duplicate_mask, "stats_json"].map(
            lambda value: len(_json_obj(value))
        )
    raw = raw.sort_values(["_richness", "minutes"], ascending=False).drop_duplicates(
        ["_core", "_fixture", "_club_core"], keep="first"
    )

    # Decodifica cada JSON uma única vez e transforma as métricas em colunas numéricas.
    # As somas por carreira, temporada e 12 meses passam a ser feitas pelo groupby vetorizado.
    stat_fields = list(dict.fromkeys(
        list(COUNT_KEYS.values()) +
        ["accurate_passes_pct", "pass_accuracy", "pass_accuracy_pct",
         "duels_won_pct", "duelsWonPercentage"]
    ))
    report(f"Decodificando métricas JSON de {len(raw):,} registros...")
    stat_frame = pd.DataFrame.from_records(
        raw["stats_json"].map(_json_obj).tolist(), columns=stat_fields
    )
    report("Convertendo métricas JSON para colunas numéricas...")
    for out_key, raw_key in COUNT_KEYS.items():
        raw[out_key] = _history_numeric(stat_frame[raw_key]) if raw_key in stat_frame else np.nan

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
    raw["_rating_num"] = pd.to_numeric(raw["rating"], errors="coerce")
    valid_minutes = raw["_minutes_num"].where(raw["_rating_num"].notna(), 0)
    raw["_rating_minutes"] = valid_minutes
    raw["_rating_weight"] = raw["_rating_num"].fillna(0) * valid_minutes

    report("Calculando totais da carreira por jogador...")
    career = _history_group_totals(raw, ["_core"])

    report("Calculando totais por temporada...")
    raw["_season_group"] = raw["season_name"].where(
        raw["season_name"].notna(), "__SEASON_NOT_IDENTIFIED__"
    )
    season_totals = _history_group_totals(raw, ["_core", "_season_group"])
    if not season_totals.empty:
        season_rows = season_totals.reset_index()
        season_rows["temporada"] = season_rows["_season_group"].replace(
            {"__SEASON_NOT_IDENTIFIED__": "não identificada"}
        )
        season_rows = season_rows.sort_values(
            ["_core", "temporada"], ascending=True, kind="stable"
        )
        season_by_core = {
            core: group.drop(columns=["_core", "_season_group"]).to_dict("records")
            for core, group in season_rows.groupby("_core", sort=False)
        }
    else:
        season_by_core = {}

    report("Calculando janela dos últimos 12 meses...")
    recent_cutoff = (pd.Timestamp.today().normalize() - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    recent_rows = raw.loc[raw["match_date"].astype(str) >= recent_cutoff]
    recent_totals = _history_group_totals(recent_rows, ["_core"]) if not recent_rows.empty else pd.DataFrame()

    ordered = raw.sort_values("match_date", ascending=False, kind="stable")
    latest = ordered.drop_duplicates("_core", keep="first").set_index("_core")
    recent_games = ordered.groupby("_core", sort=False, group_keys=False).head(15)
    games_by_core = {
        core: group[["match_date", "team_name", "competition_name", "minutes", "rating", "stats_json"]]
        .to_dict("records")
        for core, group in recent_games.groupby("_core", sort=False)
    }
    positions = raw.groupby("_core", sort=False)["position"].agg(
        lambda values: values.dropna().astype(str).mode().iloc[0]
        if values.dropna().size else ""
    )

    recent_by_core = recent_totals.to_dict("index") if not recent_totals.empty else {}
    season_by_core = season_by_core or {}
    summaries = []
    career_by_core = career.to_dict("index") if not career.empty else {}
    for core, all_data in career_by_core.items():
        recent = recent_by_core.get(core, {})
        all_data["nome_observado"] = _safe_str(latest.at[core, "player_name"])
        all_data["posicao_observada"] = _safe_str(positions.get(core, ""))
        all_data["nacionalidade_observada"] = None
        all_data.update({
            "minutos_12m": int(recent.get("minutos", 0) or 0),
            "jogos_12m": int(recent.get("jogos", 0) or 0),
            "rating_12m": recent.get("rating_media"),
            "gols_12m": recent.get("goals"),
            "assistencias_12m": recent.get("assists"),
            "xg_12m": recent.get("xg"),
            "xa_12m": recent.get("xa"),
            "historico_temporadas": season_by_core.get(core, [])[-5:],
            "ultimos_jogos": games_by_core.get(core, []),
        })
        summaries.append({"core": core, **all_data})

    result = pd.DataFrame(summaries)
    report(f"Histórico agregado: {len(result):,} jogadores")
    return result


def _history_map(history: Optional[pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
    if history is None or history.empty or "core" not in history:
        return {}
    return {str(r["core"]): r.to_dict() for _, r in history.iterrows()}


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

    # Homônimos no catálogo Transfermarkt continuam sem receber estatísticas ambíguas.
    duplicated_core = p["_core"].duplicated(keep=False)
    history_cores = set(history_frame["core"].astype(str)) if not history_frame.empty else set()
    has_history = p["_core"].astype(str).isin(history_cores)
    attach_mask = has_history & ~duplicated_core

    if history_columns and attach_mask.any():
        base_columns = set(p.columns)
        attach = history_frame[history_frame["core"].isin(p.loc[attach_mask, "_core"])].copy()
        attach["__history_present"] = True
        rename = {col: f"__history_{col}" for col in history_columns}
        attach = attach.rename(columns=rename)
        p = p.merge(attach, left_on="_core", right_on="core", how="left",
                    sort=False, validate="many_to_one")
        matched = p["__history_present"].fillna(False).astype(bool)
        for col in history_columns:
            hist_col = f"__history_{col}"
            if hist_col in p:
                if col in base_columns:
                    p[col] = p[hist_col].where(matched, p[col])
                else:
                    p[col] = p[hist_col]
                p.drop(columns=[hist_col], inplace=True)
        p.drop(columns=["core", "__history_present"], errors="ignore", inplace=True)
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

    duplicated_after_merge = p["_core"].duplicated(keep=False)
    ambiguous = duplicated_after_merge & p["_core"].astype(str).isin(history_cores)
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
            else:
                p["valor_tm_media_12m"] = np.nan
                p["valor_tm_ultima_avaliacao"] = np.nan
                p["variacao_tm_12m_pct"] = np.nan
    # Amplia o universo com atletas ausentes do cadastro TM, mas observados recentemente em escalações
    # e com exposição mínima. Sem idade, contrato ou valor publicados, esses campos ficam vazios.
    if history is not None and not history.empty and "core" in history:
        known = set(p["_core"].dropna().astype(str))
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
            & (extra_last_game >= pd.Timestamp.today().normalize() - pd.Timedelta(days=180))
            & (extra_minutes >= 450)
            & (extra_games >= 4)
        )
        observed = []
        for item in extra_history.loc[extra_mask].drop(columns=["_scout_core"]).to_dict("records"):
            core = _safe_str(item.get("core"))
            name = _safe_str(item.get("nome_observado"))
            role = _role(item.get("posicao_observada"), "")
            if not name or not role:
                continue
            record = {col: None for col in p.columns}
            record.update({"nome": name, "clube": _safe_str(item.get("ultimo_time")),
                           "posicao": _safe_str(item.get("posicao_observada")), "funcao": _safe_str(item.get("posicao_observada")),
                           "nacionalidade": None, "nascimento": None, "idade": np.nan,
                           "valor_mercado_eur": np.nan, "fim_contrato": pd.NaT,
                           "transfermarkt_id": None, "clube_id": None, "papel": role, "_role": role,
                           "_core": core, "clube_observado": True,
                           "fonte_clube_observado": "últimas partidas disponíveis; sem cadastro TM",
                           "sem_cadastro_mercado": True})
            for key, value in item.items():
                if key not in ("core", "historico_temporadas", "ultimos_jogos", "nome_observado", "posicao_observada"):
                    record[key] = value
            record["historico_temporadas"] = json.dumps(item.get("historico_temporadas", []), ensure_ascii=False, default=str)
            record["ultimos_jogos"] = json.dumps(item.get("ultimos_jogos", []), ensure_ascii=False, default=str)
            record["idade"] = np.nan
            record["valor_mercado_eur"] = np.nan
            record["fim_contrato"] = pd.NaT
            record["clube_valor_total_eur"] = np.nan
            observed.append(record)
            known.add(core)
        if observed:
            p = pd.concat([p, pd.DataFrame(observed)], ignore_index=True, sort=False)
    for col in ("minutos", "jogos", "rating_media", "minutos_12m", "jogos_12m", "rating_12m"):
        if col not in p:
            p[col] = np.nan
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
    d["nota_media_temporada"] = pd.to_numeric(d["rating_12m"].combine_first(d["rating_media"]), errors="coerce")
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
            mins = _num(d.at[row_idx, "minutos_12m"]) or _num(d.at[row_idx, "minutos"]) or 0
            coverage = min(1.0, len(items) / max(3.0, len(specs) * .55))
            exposure = min(1.0, mins / max(float(min_minutes) * 2.0, 1.0))
            confidence = .55 * exposure + .45 * coverage
            shrink = .38 + .62 * confidence
            d.at[row_idx, "qualidade"] = round(50 + (raw - 50) * shrink, 1)
            d.at[row_idx, "confianca_pct"] = round(confidence * 100)
    # Potencial de revenda: indicador exploratório, separado da qualidade atual.
    age = pd.to_numeric(d["idade"], errors="coerce")
    market = pd.to_numeric(d["valor_mercado_eur"], errors="coerce")
    market_pct = market.groupby(d["papel"]).rank(pct=True) * 100
    quality = pd.to_numeric(d["qualidade"], errors="coerce")
    age_upside = ((25 - age) / 8 * 100).clip(0, 100)
    d["potencial_revenda"] = (0.58 * quality + 0.27 * age_upside + 0.15 * (100 - market_pct)).where(
        age.le(23) & quality.notna())
    d["projecao_valorizacao_24m_pct"] = ((d["potencial_revenda"] - 55) * 1.1).clip(0, 50).round(0)
    d["potencial_natureza"] = "heurística de triagem; não é previsão de preço"
    return d



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
    out.loc[only_external, "qualidade"] = matched[only_external]
    out["fonte_qualidade"] = np.select(
        [both, only_external, stat.notna()],
        ["82% métricas estatísticas + 18% nota externa",
         "nota externa isolada; confiança baixa", "métricas estatísticas por posição"],
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
              AND COALESCE(data_level,'') IN ('EVENTS','BOXSCORE')
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
            WHERE l.team_name IN ({ph}) AND TRIM(COALESCE(l.coach,''))<> ''
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
        for role in ("GK", "CB", "LB", "RB", "DM", "CM", "AM", "LW", "RW", "ST"):
            count = int(counts.get(role, 0))
            q = _num(avg.get(role))
            shortage = 100 if count == 0 else 72 if count == 1 else 38 if count == 2 else 0
            low_quality = max(0, 65 - q) * 1.05 if q is not None else 8
            if shortage + low_quality >= 45:
                needs.append({"papel": role, "urgencia": min(100, shortage * .58 + low_quality * .42),
                              "motivo": f"profundidade atual: {count} atleta(s) cadastrados nesta função" +
                                        (f"; qualidade média estimada {q:.0f}/100" if q is not None else "; desempenho individual com pouca cobertura")})
    # deduplica funções e preserva a prioridade mais alta
    merged: Dict[str, Dict[str, Any]] = {}
    for item in needs:
        role = item["papel"]
        if role not in merged or item["urgencia"] > merged[role]["urgencia"]:
            merged[role] = item
    needs = sorted(merged.values(), key=lambda x: x["urgencia"], reverse=True)
    squad_style = _derive_style(own, against)
    squad_style["fonte"] = "até 50 partidas recentes com estatísticas disponíveis" if sample.get("n") else "sem amostra suficiente"
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
        style["contexto_tecnico"] = "identidade observada do clube; não há amostra histórica suficiente do treinador para projetar mudanças"
    return {
        "partidas_analisadas": sample.get("n", 0), "baseline_competicoes": sample.get("competicoes", []),
        "medias_pro": own, "medias_contra": against, "referencia": baseline, "necessidades": needs,
        "estilo": style, "treinador": coach,
        "ultima_partida": _safe_str(matches["match_date"].max()) if not matches.empty else None,
    }


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
    return {"tracos": style or ["identidade ainda sem amostra estatística suficiente"],
            "posse_media": poss, "precisao_passe": pass_acc, "passes_jogo": passes,
            "cruzamentos_jogo": crosses, "finalizacoes_jogo": shots,
            "limite": "não há tracking/vídeo; estilo é inferido apenas por estatísticas disponíveis"}


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
                WHERE l.team_name IN ({ph}) AND m.match_date>=date('now','-180 days')
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
    proxy = median_fee or (max_fee * .55 if max_fee else None) or (xi_value * .22 if xi_value else None) or \
            (squad_value * .10 if squad_value else None)
    low = proxy * .55 if proxy else None
    high = proxy * 1.65 if proxy else None
    return {
        "valor_elenco_eur": float(squad_value) if squad_value else None,
        "valor_xi_eur": float(xi_value) if xi_value else None,
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
    c_lang = set().union(*[v for k, v in LANGUAGES.items() if any(k in part for part in c_parts)]) if c_parts else set()
    b_lang = set().union(*[v for k, v in LANGUAGES.items() if k in b]) if b else set()
    if c_lang & b_lang:
        return 88, "idioma compartilhado pode facilitar comunicação e adaptação"
    if any(x in " ".join(c_parts) for x in ("argentina", "uruguay", "chile", "paraguay", "colombia", "ecuador", "peru")) and b == "brazil":
        return 75, "contexto sul-americano pode reduzir distância cultural; idioma continua diferente"
    return 52, "não há evidência suficiente para presumir adaptação cultural"


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
    affinity, affinity_note = _affinity(candidate.get("nacionalidade"), buyer_country)
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
    score = (.30 * finance + .18 * usage + .16 * tier + .14 * contract_score + .12 * affinity + .10 * 72) - foreign_penalty
    score = int(round(float(np.clip(score, 0, 100))))
    label = "Viável" if score >= 76 else "Oportunidade de empréstimo" if loan_opportunity and score >= 50 else "Alvo difícil / sonho"
    reasons = [
        f"Financeiro: {finance:.0f}/100 — {price_basis}.",
        (f"Utilização recente: {mins:.0f} minutos nos últimos 12 meses; " +
         ("perfil de empréstimo pode fazer sentido." if loan_opportunity else "minutagem considerada na negociação."))
        if minutes_known else "Minutagem recente indisponível; não foi presumido que o atleta esteja encostado.",
        f"Contrato: {months_left:.1f} mês(es) restante(s)." if months_left is not None else "Prazo contratual indisponível.",
        f"Adaptação: {affinity_note}.", f"Escada de mercado: {tier_note}.", foreign_note,
    ]
    return {"score": score, "rotulo": label, "taxa_estimada_eur": fee, "base_taxa": price_basis,
            "meses_contrato": months_left, "oportunidade_emprestimo": loan_opportunity,
            "financeiro": round(finance), "porte": round(tier), "contrato": round(contract_score),
            "afinidade": affinity, "penalidade_estrangeiros": foreign_penalty, "regra_estrangeiros": rule,
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
    return penalty


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
        eligible = eligible[~eligible["historico_ambiguo"].fillna(False)]
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
        candidates["_scout_pre"] = (.43 * q + .19 * candidates["_scout_role_fit"] * 100 +
                                     .16 * usage + .12 * contract_score + .10 * finance)
        candidates = candidates.sort_values("_scout_pre", ascending=False).head(max(20, int(max_per_position)))
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
            score = (.29 * sporting + .24 * realism["score"] + .18 * tactical["score"] +
                     .13 * chemistry_score["score"] + .10 * need_score + .06 * (role_fit * 100))
            score += _feedback_adjust(feedback_reason, realism, c)
            if quality is None:
                score -= 8
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
    out = pd.DataFrame(rows).sort_values(["score_scout", "realismo"], ascending=False)
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
