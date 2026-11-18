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
ELITE_PERCENTILE = 90.0
ALERT_PERCENTILE = 10.0
MIN_PLAYER_MINUTES = 45      # mínimo de minutos para entrar na referência e para ser avaliado com grau FORTE
MIN_GROUP_SAMPLE = 20        # abaixo disso: "amostra insuficiente" em vez de percentil


def percentile_tier(p: Optional[float]) -> str:
    """Faixa visual do percentil: elite / forte / mediana / fraco / alerta de vulnerabilidade."""
    if p is None:
        return "amostra insuficiente"
    if p >= ELITE_PERCENTILE:
        return "elite"
    if p >= STRENGTH_PERCENTILE:
        return "forte"
    if p > WEAKNESS_PERCENTILE:
        return "mediana"
    if p > ALERT_PERCENTILE:
        return "fraco"
    return "alerta de vulnerabilidade"

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
        return [m for m in ids if source_from_internal_id(m) in ("statsbomb", "wyscout", "openplay")]

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
            if source_from_internal_id(mid) not in ("statsbomb", "wyscout", "openplay"):
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

    TARGET_MATCHES = 1500        # rodada 7: o "jogo típico" usa pelo menos mil jogos (cresce em segundo plano)

    @classmethod
    def load_cached(cls, cache_path: Optional[Path] = None) -> Dict[str, Any]:
        """Só LÊ a referência pronta (a tela nunca monta jogos novos; quem cresce a base é o processo de fundo)."""
        cache_path = cache_path or cls.DEFAULT_CACHE
        if not cache_path.exists():
            return {}
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @classmethod
    def grow(cls, load_events_fn, db_path: str = "database/tactical_lab.db", batch: int = 100,
             target: Optional[int] = None) -> Dict[str, Any]:
        """Acrescenta até `batch` jogos novos à referência, do mais recente ao mais antigo, até `target` jogos usados."""
        target = target or cls.TARGET_MATCHES
        cached = cls.load_cached()
        if len(cached.get("match_ids", [])) >= target:
            return cached
        wanted = sorted(cls.available_real_match_ids(db_path), reverse=True)     # mais novos primeiro
        return cls.build(load_events_fn, wanted, cache_path=cls.DEFAULT_CACHE, previous=cached, max_new=batch)

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
        fam = fam if fam in ("statsbomb", "wyscout", "openplay") else "statsbomb"
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
        strengths, weaknesses, neutral, insufficient = [], [], [], []
        for key, label, direction in metric_defs:
            val = values.get(key)
            if val is None:
                continue
            ref = [r[key] for r in reference_rows if r.get(key) is not None]
            item = {"metric": key, "label": label, "value": round(float(val), 2), "reference_n": len(ref),
                    "higher_is_better": direction > 0}
            if len(ref) < MIN_GROUP_SAMPLE:
                item.update(percentile=None, reference_median=round(float(np.median(ref)), 2) if ref else None,
                            tier="amostra insuficiente")
                insufficient.append(item)
                continue
            pct = cls._percentile(float(val), ref, direction)
            item.update(percentile=pct, reference_median=round(float(np.median(ref)), 2), tier=percentile_tier(pct))
            if pct >= STRENGTH_PERCENTILE:
                strengths.append(item)
            elif pct <= WEAKNESS_PERCENTILE:
                weaknesses.append(item)
            else:
                neutral.append(item)
        strengths.sort(key=lambda d: -d["percentile"])
        weaknesses.sort(key=lambda d: d["percentile"])
        return {"strengths": strengths, "weaknesses": weaknesses, "neutral": neutral, "insufficient": insufficient}

    @classmethod
    def analyze_player(
        cls,
        df_events: pd.DataFrame,
        player_name: str,
        baselines: Dict[str, Any],
        exclude_match_id: Optional[int] = None,
        competition_of: Optional[Dict[int, str]] = None,
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

        pool = [r for r in cls._same_source_pool(baselines.get("players", []), exclude_match_id)
                if r.get("minutes", 0) >= MIN_PLAYER_MINUTES]
        group_pool = [r for r in pool if r.get("group") == group]
        league_scope = "mesma família de fonte"
        if competition_of and exclude_match_id is not None and int(exclude_match_id) in competition_of:
            comp = competition_of[int(exclude_match_id)]
            same_league = [r for r in group_pool if competition_of.get(int(r["match_id"])) == comp]
            if len(same_league) >= MIN_GROUP_SAMPLE:
                group_pool, league_scope = same_league, f"mesma competição ({comp})"
        comparison_scope = GROUP_PLURALS.get(group, "atletas")

        values = cls.player_metric_values(p)
        result = cls._classify(
            values, group_pool, [(k, lbl, d) for k, lbl, d, _ in PLAYER_METRICS]
        )
        grade = "FORTE" if minutes >= 60 else ("MODERADA" if minutes >= MIN_PLAYER_MINUTES else "LIMITADA")
        if minutes < MIN_PLAYER_MINUTES:
            grade = "LIMITADA"
        return {
            "mode": "player",
            "entity": player_name,
            "team_name": team,
            "position_name": str(p.get("position_name", "")),
            "group": group,
            "comparison_scope": comparison_scope,
            "league_scope": league_scope,
            "min_minutes": MIN_PLAYER_MINUTES,
            "min_group_sample": MIN_GROUP_SAMPLE,
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
            "league_scope": "mesma família de fonte",
            "min_group_sample": MIN_GROUP_SAMPLE,
            "reference_teams_n": len(pool),
            "reference_matches_n": len({r["match_id"] for r in pool}),
            "evidence_grade": "MODERADA" if len(pool) >= 20 else "LIMITADA",
            **result,
        }

    # ------------------------------------------------------------- interpretação
    @staticmethod
    def rank_phrase(d: Dict[str, Any]) -> str:
        """Percentil só quando conta: 'entre os 5% melhores da base' (≥ P90) ou 'entre os 10% piores' (≤ P10)."""
        import math

        p = d.get("percentile")
        if p is None:
            return ""
        if p >= 90:
            return f"entre os {max(1, math.ceil(100 - p))}% melhores da base"
        if p <= 10:
            return f"entre os {max(1, math.ceil(p))}% piores da base"
        return ""

    @staticmethod
    def compare_words(value: Any, median: Any) -> str:
        """Comparação com o jogo típico em palavras ('o dobro', 'bem abaixo')."""
        try:
            v, m = float(value), float(median)
        except (TypeError, ValueError):
            return ""
        if m <= 0:
            return "acima do normal" if v > 0 else ""
        r = v / m
        for lim, txt in ((4, "quatro vezes ou mais"), (3, "o triplo"), (2, "o dobro"), (1.3, "bem acima"), (1.0001, "acima")):
            if r >= lim:
                return txt
        for lim, txt in ((0.5, "menos da metade"), (0.75, "bem abaixo"), (0.9999, "abaixo")):
            if r <= lim:
                return txt
        return "na média"

    @classmethod
    def _fmt_item(cls, d: Dict[str, Any]) -> str:
        cw = cls.compare_words(d["value"], d.get("reference_median"))
        rk = cls.rank_phrase(d)
        typ = f"o jogo típico da base tem {d['reference_median']}"
        body = f"{cw} do normal ({typ})" if cw in ("bem acima", "acima", "bem abaixo", "abaixo") else \
            (f"{cw} do jogo típico ({d['reference_median']})" if cw else typ)
        return f"**{d['label']}: {d['value']}** — {body}" + (f"; {rk}" if rk else "") + "."

    @classmethod
    def build_interpretation_markdown(
        cls, analysis: Dict[str, Any], is_simulation: bool = False
    ) -> str:
        """Texto determinístico (todos os números saem do próprio `analysis`)."""
        lines: List[str] = []
        entity = analysis["entity"]
        if analysis["mode"] == "player":
            head = (
                f"**{entity}** ({analysis['position_name']}, {analysis['team_name']}) jogou "
                f"{int(analysis['minutes']) if float(analysis['minutes']).is_integer() else analysis['minutes']} minutos. "
                f"Abaixo, o que se destacou em relação a {analysis['reference_players_n']} {analysis['comparison_scope']} "
                f"de {analysis['reference_matches_n']} jogos reais da base."
            )
        else:
            head = (
                f"Como **{entity}** jogou, comparado com {analysis['reference_teams_n']} atuações de equipes em "
                f"{analysis['reference_matches_n']} jogos reais da base:"
            )
        lines.append(head)
        if is_simulation:
            lines.append(
                "> ⚠️ A partida analisada é SIMULADA; a comparação com a base real serve só como demonstração."
            )
        if analysis.get("insufficient"):
            lines.append("\n_Sem base de comparação suficiente para: " + ", ".join(d["label"] for d in analysis["insufficient"])
                         + "._")

        st_, wk = analysis["strengths"], analysis["weaknesses"]
        lines.append("\n### ✅ O que funcionou")
        lines.extend([f"- {cls._fmt_item(d)}" for d in st_[:5]] or ["- Nada muito acima do normal neste jogo."])
        lines.append("\n### ⚠️ O que precisa melhorar")
        lines.extend([f"- {cls._fmt_item(d)}" for d in wk[:5]] or ["- Nada muito abaixo do normal neste jogo."])

        lines.append("\n### 📌 Resumo")
        if st_ and wk:
            lines.append(
                f"O ponto forte foi {_lower_first(st_[0]['label'])} ({st_[0]['value']}); o que mais preocupa é "
                f"{_lower_first(wk[0]['label'])} ({wk[0]['value']})."
            )
        elif st_:
            lines.append(
                f"Atuação sem fragilidades marcantes, com destaque para {_lower_first(st_[0]['label'])} ({st_[0]['value']})."
            )
        elif wk:
            lines.append(
                f"Nada se destacou para cima; o primeiro ajuste é {_lower_first(wk[0]['label'])} ({wk[0]['value']})."
            )
        else:
            lines.append("Atuação dentro do normal em tudo o que dá para comparar.")
        if analysis.get("evidence_grade") == "LIMITADA":
            lines.append("\n_Pouco tempo em campo ou base pequena: leia como indicação._")
        return "\n".join(lines)
