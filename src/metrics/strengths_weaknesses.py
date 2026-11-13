"""
Módulo de Pontos Fortes e Fracos (estilo Football Manager Data Hub) — Camada 5.4

Compara um atleta (por função/posição) ou uma equipe com uma base de referência
construída a partir das partidas REAIS do StatsBomb Open Data já armazenadas no
SQLite local. Cada métrica vira um percentil contextual:

* atletas: métricas normalizadas por 90 minutos (ou taxas), comparadas apenas com
  atletas do mesmo grupo de função (ex.: Pontas com Pontas);
* equipes: métricas coletivas por partida, comparadas com todas as equipes da base.

Partidas simuladas (catálogo do Brasileirão) nunca entram na referência.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

from src.data_hub.registry import source_from_internal_id
from src.ingestion.brazil_and_multi_source import BrasileiraoAndMultiSourceProvider
from src.metrics.player_evaluator import PlayerTacticalEvaluator
from src.metrics.tactical_metrics import TacticalMetricsEngine
from src.metrics.xt_model import ExpectedThreatModel
from src.preprocessing.event_cleaner import EventPreprocessor

STRENGTH_PERCENTILE = 70.0
WEAKNESS_PERCENTILE = 30.0
MIN_PLAYER_MINUTES = 30
MIN_GROUP_SAMPLE = 8

# --------------------------------------------------------------------------- funções
POSITION_GROUPS: Dict[str, str] = {
    "Goalkeeper": "Goleiro",
    "Center Back": "Zagueiro",
    "Left Center Back": "Zagueiro",
    "Right Center Back": "Zagueiro",
    "Left Back": "Lateral / Ala",
    "Right Back": "Lateral / Ala",
    "Left Wing Back": "Lateral / Ala",
    "Right Wing Back": "Lateral / Ala",
    "Center Defensive Midfield": "Volante",
    "Left Defensive Midfield": "Volante",
    "Right Defensive Midfield": "Volante",
    "Center Midfield": "Meia Central",
    "Left Center Midfield": "Meia Central",
    "Right Center Midfield": "Meia Central",
    "Left Midfield": "Meia Central",
    "Right Midfield": "Meia Central",
    "Center Attacking Midfield": "Meia Ofensivo",
    "Left Attacking Midfield": "Meia Ofensivo",
    "Right Attacking Midfield": "Meia Ofensivo",
    "Left Wing": "Ponta",
    "Right Wing": "Ponta",
    "Center Forward": "Centroavante",
    "Left Center Forward": "Centroavante",
    "Right Center Forward": "Centroavante",
    "Secondary Striker": "Centroavante",
}

# (chave, rótulo, direção: +1 maior é melhor / -1 menor é melhor, tipo)
PLAYER_METRICS: List[Tuple[str, str, int, str]] = [
    ("progressive_actions", "Ações progressivas /90", 1, "per90"),
    ("line_breaking_passes", "Passes que quebram linhas /90", 1, "per90"),
    ("zone_14_entries", "Bolas na Zona 14 /90", 1, "per90"),
    ("box_entries", "Entradas na área /90", 1, "per90"),
    ("xt_generated", "xT gerado /90", 1, "per90"),
    ("xg", "xG /90", 1, "per90"),
    ("shots", "Finalizações /90", 1, "per90"),
    ("defensive_actions", "Ações defensivas /90", 1, "per90"),
    ("ball_recoveries", "Recuperações de bola /90", 1, "per90"),
    ("counterpress_actions", "Contrapressão /90", 1, "per90"),
    ("turnovers", "Perdas de posse /90", -1, "per90"),
    ("pass_accuracy_pct", "Precisão de passe (%)", 1, "rate"),
    ("press_retention_pct", "Retenção sob pressão (%)", 1, "rate"),
]

# (seção do sumário, chave, rótulo, direção)
TEAM_METRICS: List[Tuple[str, str, str, int]] = [
    ("offensive_organization", "total_xg", "xG criado", 1),
    ("offensive_organization", "total_shots", "Finalizações", 1),
    ("offensive_organization", "penalty_box_entries", "Entradas na área", 1),
    ("offensive_organization", "zone_14_entries", "Bolas na Zona 14", 1),
    ("offensive_organization", "overall_pass_completion_pct", "Precisão de passe (%)", 1),
    ("offensive_organization", "buildup_turnovers_in_own_third", "Perdas no terço defensivo", -1),
    ("midfield_control", "field_tilt_pct", "Field Tilt (%)", 1),
    ("midfield_control", "press_resistance_completion_pct", "Resistência à pressão (%)", 1),
    ("defensive_organization", "ppda", "PPDA (menor = pressão mais intensa)", -1),
    ("defensive_organization", "xg_conceded", "xG cedido", -1),
    ("defensive_organization", "shots_conceded", "Finalizações cedidas", -1),
    ("defensive_organization", "zone_14_entries_conceded", "Zona 14 cedida", -1),
    ("defensive_transition", "post_loss_5s_recovery_pct", "Recuperação em 5s após perda (%)", 1),
    ("offensive_transition", "counter_efficiency_pct", "Eficiência de contra-ataque (%)", 1),
]


GROUP_PLURALS: Dict[str, str] = {
    "Goleiro": "goleiros",
    "Zagueiro": "zagueiros",
    "Lateral / Ala": "laterais/alas",
    "Volante": "volantes",
    "Meia Central": "meias centrais",
    "Meia Ofensivo": "meias ofensivos",
    "Ponta": "pontas",
    "Centroavante": "centroavantes",
    "Outros": "atletas",
}


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text


def position_group(position_name: Optional[str]) -> str:
    return POSITION_GROUPS.get(str(position_name or ""), "Outros")


# ----------------------------------------------------------------- base de referência
class ReferenceBaselineBuilder:
    """Constrói (e guarda em JSON) a base de referência a partir do SQLite local."""

    DEFAULT_CACHE = Path("data/processed/reference_baselines.json")

    @staticmethod
    def available_real_match_ids(db_path: str = "database/tactical_lab.db") -> List[int]:
        path = Path(db_path)
        if not path.exists():
            return []
        with sqlite3.connect(str(path)) as conn:
            rows = conn.execute("SELECT DISTINCT match_id FROM events").fetchall()
        ids = sorted(int(r[0]) for r in rows)
        return [m for m in ids if source_from_internal_id(m) in ("statsbomb", "wyscout")]

    @staticmethod
    def player_rows_from_match(df_events: pd.DataFrame, match_id: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for team in df_events["team_name"].dropna().unique():
            players = PlayerTacticalEvaluator.evaluate_team_players(df_events, str(team))
            if players is None or players.empty:
                continue
            for _, p in players.iterrows():
                minutes = float(p.get("estimated_minutes_active", 0) or 0)
                if minutes < MIN_PLAYER_MINUTES:
                    continue
                row: Dict[str, Any] = {
                    "match_id": int(match_id),
                    "source": source_from_internal_id(int(match_id)),
                    "team_name": str(team),
                    "player_name": str(p["player_name"]),
                    "position_name": str(p.get("position_name", "")),
                    "group": position_group(p.get("position_name")),
                    "minutes": round(minutes, 1),
                }
                row.update(StrengthsWeaknessesEngine.player_metric_values(p))
                rows.append(row)
        return rows

    @staticmethod
    def team_rows_from_match(
        df_events: pd.DataFrame, df_chains: pd.DataFrame, match_id: int
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for team in df_events["team_name"].dropna().unique():
            summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
                df_events, df_chains, str(team)
            )
            row: Dict[str, Any] = {"match_id": int(match_id), "team_name": str(team),
                                   "source": source_from_internal_id(int(match_id))}
            row.update(StrengthsWeaknessesEngine.team_metric_values(summary))
            rows.append(row)
        return rows

    @classmethod
    def build(
        cls,
        load_events_fn,
        match_ids: Iterable[int],
        cache_path: Optional[Path] = None,
        previous: Optional[Dict[str, Any]] = None,
        max_new: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        `load_events_fn(match_id)` devolve o DataFrame bruto de eventos.
        Incremental: partidas já processadas em `previous` não são refeitas; no máximo
        `max_new` partidas novas por chamada (o restante entra nas próximas).
        """
        prev = previous or {}
        player_rows: List[Dict[str, Any]] = list(prev.get("players", []))
        team_rows: List[Dict[str, Any]] = list(prev.get("teams", []))
        used: List[int] = list(prev.get("match_ids", []))
        attempted = set(prev.get("attempted_ids", []))
        pending = [int(m) for m in match_ids if int(m) not in attempted]
        if max_new is not None:
            pending = pending[:max_new]
        for mid in pending:
            attempted.add(mid)
            if source_from_internal_id(mid) not in ("statsbomb", "wyscout"):
                continue
            try:
                raw = load_events_fn(int(mid))
                if raw is None or raw.empty:
                    continue
                df = ExpectedThreatModel.enrich_events_with_xt(
                    EventPreprocessor.process_match_events(raw)
                )
                chains = EventPreprocessor.build_possession_chains(df)
                player_rows.extend(cls.player_rows_from_match(df, int(mid)))
                team_rows.extend(cls.team_rows_from_match(df, chains, int(mid)))
                used.append(int(mid))
            except Exception:
                continue

        baselines = {
            "source": "Partidas reais com eventos (StatsBomb Open Data + Wyscout Public Dataset) no SQLite local",
            "match_ids": used,
            "attempted_ids": sorted(attempted),
            "players": player_rows,
            "teams": team_rows,
        }
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(baselines, ensure_ascii=False), encoding="utf-8")
        return baselines

    @classmethod
    def load_or_build(
        cls,
        load_events_fn,
        db_path: str = "database/tactical_lab.db",
        cache_path: Optional[Path] = None,
        max_new: int = 150,
    ) -> Dict[str, Any]:
        cache_path = cache_path or cls.DEFAULT_CACHE
        wanted = cls.available_real_match_ids(db_path)
        cached: Dict[str, Any] = {}
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                cached = {}
        if cached and set(wanted) <= set(cached.get("attempted_ids", [])):
            return cached
        return cls.build(load_events_fn, wanted, cache_path=cache_path, previous=cached, max_new=max_new)


# ------------------------------------------------------------------------ motor
class StrengthsWeaknessesEngine:
    """Transforma métricas em percentis contextuais e separa fortes / fracos."""

    @staticmethod
    def player_metric_values(p: Any) -> Dict[str, Optional[float]]:
        minutes = float(p.get("estimated_minutes_active", 0) or 0)
        values: Dict[str, Optional[float]] = {}
        for key, _label, _direction, kind in PLAYER_METRICS:
            raw = p.get(key, None)
            if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                values[key] = None
                continue
            if kind == "per90":
                values[key] = round(float(raw) * 90.0 / minutes, 3) if minutes > 0 else None
            else:
                values[key] = round(float(raw), 2)
        # retenção sob pressão só faz sentido com amostra mínima
        if float(p.get("pressured_passes", 0) or 0) < 5:
            values["press_retention_pct"] = None
        if float(p.get("passes_attempted", 0) or 0) < 10:
            values["pass_accuracy_pct"] = None
        return values

    @staticmethod
    def team_metric_values(summary: Dict[str, Any]) -> Dict[str, Optional[float]]:
        values: Dict[str, Optional[float]] = {}
        for section, key, _label, _direction in TEAM_METRICS:
            val = summary.get(section, {}).get(key, None)
            values[key] = None if val is None else round(float(val), 3)
        return values

    @staticmethod
    def _same_source_pool(rows: List[Dict[str, Any]], exclude_match_id: Optional[int]) -> List[Dict[str, Any]]:
        """
        Compara com partidas da mesma família de fonte (StatsBomb com StatsBomb, Wyscout com
        Wyscout), porque as fontes registram ações defensivas e pressão de forma diferente.
        Partidas simuladas/enviadas usam a referência StatsBomb.
        """
        rows = [r for r in rows if r.get("match_id") != exclude_match_id]
        if exclude_match_id is None:
            return rows
        fam = source_from_internal_id(int(exclude_match_id))
        fam = fam if fam in ("statsbomb", "wyscout") else "statsbomb"
        same = [r for r in rows if r.get("source", "statsbomb") == fam]
        return same if len(same) >= 2 * MIN_GROUP_SAMPLE else rows

    @staticmethod
    def _percentile(value: float, reference: List[float], direction: int) -> float:
        pct = float(percentileofscore(reference, value, kind="mean"))
        return round(pct if direction > 0 else 100.0 - pct, 1)

    @classmethod
    def _classify(
        cls,
        values: Dict[str, Optional[float]],
        reference_rows: List[Dict[str, Any]],
        metric_defs: List[Tuple[str, str, int]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        strengths, weaknesses, neutral = [], [], []
        for key, label, direction in metric_defs:
            val = values.get(key)
            ref = [r[key] for r in reference_rows if r.get(key) is not None]
            if val is None or len(ref) < MIN_GROUP_SAMPLE:
                continue
            item = {
                "metric": key,
                "label": label,
                "value": round(float(val), 2),
                "reference_median": round(float(np.median(ref)), 2),
                "reference_n": len(ref),
                "percentile": cls._percentile(float(val), ref, direction),
                "higher_is_better": direction > 0,
            }
            if item["percentile"] >= STRENGTH_PERCENTILE:
                strengths.append(item)
            elif item["percentile"] <= WEAKNESS_PERCENTILE:
                weaknesses.append(item)
            else:
                neutral.append(item)
        strengths.sort(key=lambda d: -d["percentile"])
        weaknesses.sort(key=lambda d: d["percentile"])
        return {"strengths": strengths, "weaknesses": weaknesses, "neutral": neutral}

    @classmethod
    def analyze_player(
        cls,
        df_events: pd.DataFrame,
        player_name: str,
        baselines: Dict[str, Any],
        exclude_match_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        team_series = df_events.loc[df_events["player_name"] == player_name, "team_name"].dropna()
        if team_series.empty:
            raise ValueError(f"Atleta '{player_name}' não encontrado nos eventos.")
        team = str(team_series.iloc[0])
        players = PlayerTacticalEvaluator.evaluate_team_players(df_events, team)
        row = players[players["player_name"] == player_name]
        if row.empty:
            raise ValueError(f"Sem métricas individuais para '{player_name}'.")
        p = row.iloc[0]
        group = position_group(p.get("position_name"))
        minutes = float(p.get("estimated_minutes_active", 0) or 0)

        pool = cls._same_source_pool(baselines.get("players", []), exclude_match_id)
        group_pool = [r for r in pool if r.get("group") == group]
        comparison_scope = GROUP_PLURALS.get(group, "atletas")
        if len(group_pool) < MIN_GROUP_SAMPLE:
            group_pool = [r for r in pool if r.get("group") not in ("Goleiro",)]
            comparison_scope = "atletas de linha (amostra da função insuficiente)"

        values = cls.player_metric_values(p)
        result = cls._classify(
            values, group_pool, [(k, lbl, d) for k, lbl, d, _ in PLAYER_METRICS]
        )
        grade = "FORTE" if minutes >= 60 else ("MODERADA" if minutes >= MIN_PLAYER_MINUTES else "LIMITADA")
        return {
            "mode": "player",
            "entity": player_name,
            "team_name": team,
            "position_name": str(p.get("position_name", "")),
            "group": group,
            "comparison_scope": comparison_scope,
            "minutes": round(minutes, 1),
            "reference_players_n": len(group_pool),
            "reference_matches_n": len({r["match_id"] for r in group_pool}),
            "evidence_grade": grade,
            **result,
        }

    @classmethod
    def analyze_team(
        cls,
        df_events: pd.DataFrame,
        df_chains: pd.DataFrame,
        team_name: str,
        baselines: Dict[str, Any],
        exclude_match_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        summary = TacticalMetricsEngine.generate_full_match_tactical_summary(
            df_events, df_chains, team_name
        )
        values = cls.team_metric_values(summary)
        pool = cls._same_source_pool(baselines.get("teams", []), exclude_match_id)
        result = cls._classify(
            values, pool, [(k, lbl, d) for _s, k, lbl, d in TEAM_METRICS]
        )
        return {
            "mode": "team",
            "entity": team_name,
            "team_name": team_name,
            "group": "Equipe",
            "comparison_scope": "equipes",
            "reference_teams_n": len(pool),
            "reference_matches_n": len({r["match_id"] for r in pool}),
            "evidence_grade": "MODERADA" if len(pool) >= 20 else "LIMITADA",
            **result,
        }

    # ------------------------------------------------------------- interpretação
    @staticmethod
    def _fmt_item(d: Dict[str, Any]) -> str:
        return (
            f"**{d['label']}**: {d['value']} (mediana da referência {d['reference_median']}, "
            f"percentil {d['percentile']})"
        )

    @classmethod
    def build_interpretation_markdown(
        cls, analysis: Dict[str, Any], is_simulation: bool = False
    ) -> str:
        """Texto determinístico (todos os números saem do próprio `analysis`)."""
        lines: List[str] = []
        entity = analysis["entity"]
        if analysis["mode"] == "player":
            head = (
                f"**{entity}** ({analysis['position_name']}, {analysis['team_name']}) foi comparado com "
                f"**{analysis['reference_players_n']}** {analysis['comparison_scope']} em "
                f"**{analysis['reference_matches_n']}** partidas reais da base, com "
                f"**{analysis['minutes']}** minutos em campo (evidência **{analysis['evidence_grade']}**)."
            )
        else:
            head = (
                f"**{entity}** foi comparada com **{analysis['reference_teams_n']}** atuações de equipes em "
                f"**{analysis['reference_matches_n']}** partidas reais da base "
                f"(evidência **{analysis['evidence_grade']}**)."
            )
        lines.append(head)
        if is_simulation:
            lines.append(
                "> ⚠️ A partida analisada é SIMULADA; a comparação com a base real serve só como demonstração."
            )

        st_, wk = analysis["strengths"], analysis["weaknesses"]
        lines.append("\n### ✅ Onde está acima do padrão")
        lines.extend([f"- {cls._fmt_item(d)}" for d in st_[:5]] or ["- Nenhuma métrica acima do percentil 70."])
        lines.append("\n### ⚠️ Onde está abaixo do padrão")
        lines.extend([f"- {cls._fmt_item(d)}" for d in wk[:5]] or ["- Nenhuma métrica abaixo do percentil 30."])

        lines.append("\n### 📌 Resumo executivo")
        if st_ and wk:
            lines.append(
                f"Ponto mais forte: {_lower_first(st_[0]['label'])} (percentil {st_[0]['percentile']}). "
                f"Principal ponto de atenção: {_lower_first(wk[0]['label'])} (percentil {wk[0]['percentile']})."
            )
        elif st_:
            lines.append(
                f"Perfil sem fraquezas marcantes; destaque para {_lower_first(st_[0]['label'])} "
                f"(percentil {st_[0]['percentile']})."
            )
        elif wk:
            lines.append(
                f"Nenhum destaque acima do padrão; corrigir primeiro {_lower_first(wk[0]['label'])} "
                f"(percentil {wk[0]['percentile']})."
            )
        else:
            lines.append("Desempenho dentro da faixa normal da referência em todas as métricas comparáveis.")
        lines.append(
            "\n*Percentil = posição em relação à referência (100 = melhor da base). "
            "Fonte da referência: StatsBomb Open Data.*"
        )
        return "\n".join(lines)
