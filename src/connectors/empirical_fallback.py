"""
EmpiricalFallback (Módulo 3.4) e incerteza do gerador de partidas simuladas.

1) EmpiricalFallback — gerador "EmpiricalBootstrap-v1"
   Amostragem por bootstrap com reposição (B = 100) sobre a distribuição empírica de
   eventos REAIS do StatsBomb (tier OFFICIAL) presentes no banco local, estratificada por
   zona do campo (terço × faixa lateral, no referencial da equipe), contexto de placar
   (perdendo / empatando / vencendo) e faixa de minuto (0–15, …, 75–90+). Cada estrato é
   reamostrado separadamente, preservando seu tamanho. Saída: valor central (estimativa na
   amostra original) + IC 95% (percentis 2,5 e 97,5 das B réplicas), sempre com
   confidence_tier = SIMULATED, persistidos na tabela simulated_estimates.

2) SimulationUncertainty — partidas do gerador por perfis (BrasileiraoProfileGenerator)
   Re-simula a mesma partida com B sementes e reporta mediana e IC 95% das métricas-chave.

Formulação obrigatória na interface: "IC 95% da reamostragem, condicionado à distribuição
empírica de referência" — mede a incerteza do gerador, não a incerteza sobre o jogo real.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.canonical.schema import make_aggregate_frame, utc_now_iso

POOL_PATH = Path("data/processed/empirical_pool.csv.gz")
SIM_CACHE_DIR = Path("data/processed/sim_uncertainty")
GENERATOR = "EmpiricalBootstrap-v1"
SIM_GENERATOR = "BrasileiraoProfileGenerator"
CI_TEXT = "IC 95% da reamostragem, condicionado à distribuição empírica de referência"

THIRDS = [("defensivo", 0, 40), ("médio", 40, 80), ("ofensivo", 80, 121)]
LANES = [("esquerda", 0, 26.67), ("centro", 26.67, 53.33), ("direita", 53.33, 81)]
ZONES = [f"{t}-{l}" for t, _, _ in THIRDS for l, _, _ in LANES]
SCORE_CTX = ("perdendo", "empatando", "vencendo")
MINUTE_BANDS = ("0-15", "15-30", "30-45", "45-60", "60-75", "75-90+")

METRICS: Dict[str, Dict[str, str]] = {
    "pass_completion_pct": {"label": "Acerto de passe (%)", "rows": "passes", "unit": "%"},
    "progressive_pass_pct": {"label": "Passes progressivos (%)", "rows": "passes", "unit": "%"},
    "turnover_rate_pct": {"label": "Perda de posse por ação (%)", "rows": "acoes", "unit": "%"},
    "xt_per_action": {"label": "xT por ação com bola", "rows": "acoes_xt", "unit": "xT"},
    "xg_per_shot": {"label": "xG por finalização", "rows": "finalizacoes", "unit": "xG"},
}


def _zone(x: float, y: float) -> str:
    t = next(n for n, lo, hi in THIRDS if lo <= x < hi) if 0 <= x <= 120 else "médio"
    l = next(n for n, lo, hi in LANES if lo <= y < hi) if 0 <= y <= 80 else "centro"
    return f"{t}-{l}"


def _band(minute: int) -> str:
    return MINUTE_BANDS[min(int(minute) // 15, 5)]


class EmpiricalFallback:
    def __init__(self, pool: pd.DataFrame, db_path: Optional[Path | str] = None):
        self.pool = pool
        self.db_path = Path(db_path) if db_path else None

    # ---------------------------------------------------------- referência
    @staticmethod
    def pool_rows_from_match(df_proc: pd.DataFrame, match_id: int, home_team: str) -> pd.DataFrame:
        """Linhas do pool a partir de eventos JÁ processados (EventPreprocessor + xT)."""
        d = df_proc[(df_proc["period"] <= 4) & df_proc["x"].notna() & df_proc["y"].notna()].copy()
        if d.empty:
            return pd.DataFrame()
        # placar antes de cada evento, do ponto de vista de quem executa
        teams = d["team_name"].dropna().unique().tolist()
        goals = {t: 0 for t in teams}
        diffs = []
        for r in d.itertuples(index=False):
            other = next((t for t in teams if t != r.team_name), None)
            diffs.append(goals.get(r.team_name, 0) - goals.get(other, 0))
            if r.type_name == "Shot" and getattr(r, "shot_outcome_name", None) == "Goal":
                goals[r.team_name] = goals.get(r.team_name, 0) + 1
            elif r.type_name == "Own Goal Against" and other:
                goals[other] = goals.get(other, 0) + 1
        d["score_diff"] = diffs
        ball = d["type_name"].isin(["Pass", "Carry", "Dribble", "Shot"])
        out = pd.DataFrame({
            "match_id": int(match_id),
            "zone": [_zone(x, y) for x, y in zip(d["x"], d["y"])],
            "score_ctx": np.select([d["score_diff"] < 0, d["score_diff"] > 0], ["perdendo", "vencendo"], "empatando"),
            "minute_band": d["minute"].fillna(0).astype(int).map(_band),
            "is_pass": (d["type_name"] == "Pass").astype(int),
            "pass_ok": ((d["type_name"] == "Pass") & (d.get("is_pass_completed", 0) == 1)).astype(int),
            "progressive": ((d["type_name"] == "Pass") & (d.get("is_progressive_action", 0) == 1)).astype(int),
            "is_action": ball.astype(int),
            "turnover": (ball & (d.get("is_turnover", 0) == 1)).astype(int),
            "delta_xt": np.where(ball & d["type_name"].isin(["Pass", "Carry"]), d.get("delta_xt", 0.0), np.nan),
            "is_shot": (d["type_name"] == "Shot").astype(int),
            "xg": np.where(d["type_name"] == "Shot", d.get("shot_statsbomb_xg", np.nan), np.nan),
        })
        return out

    @classmethod
    def build_pool(cls, match_ids: List[int], load_events_fn: Callable[[int], pd.DataFrame],
                   home_of: Callable[[int], str], save: bool = True) -> pd.DataFrame:
        from src.metrics.xt_model import ExpectedThreatModel
        from src.preprocessing.event_cleaner import EventPreprocessor

        parts = []
        for mid in match_ids:
            raw = load_events_fn(int(mid))
            if raw is None or raw.empty:
                continue
            proc = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(raw))
            parts.append(cls.pool_rows_from_match(proc, int(mid), home_of(int(mid))))
        pool = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if save and not pool.empty:
            POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
            pool.to_csv(POOL_PATH, index=False, compression="gzip")
        return pool

    @classmethod
    def from_cache(cls, db_path: Optional[Path | str] = None) -> Optional["EmpiricalFallback"]:
        if not POOL_PATH.exists():
            return None
        return cls(pd.read_csv(POOL_PATH), db_path=db_path)

    # ----------------------------------------------------------- bootstrap
    @staticmethod
    def _rows_and_values(pool: pd.DataFrame, metric: str) -> pd.DataFrame:
        if metric == "pass_completion_pct":
            sub = pool[pool["is_pass"] == 1].assign(v=lambda d: d["pass_ok"] * 100.0)
        elif metric == "progressive_pass_pct":
            sub = pool[pool["is_pass"] == 1].assign(v=lambda d: d["progressive"] * 100.0)
        elif metric == "turnover_rate_pct":
            sub = pool[pool["is_action"] == 1].assign(v=lambda d: d["turnover"] * 100.0)
        elif metric == "xt_per_action":
            sub = pool[pool["delta_xt"].notna()].assign(v=lambda d: d["delta_xt"])
        elif metric == "xg_per_shot":
            sub = pool[(pool["is_shot"] == 1) & pool["xg"].notna()].assign(v=lambda d: d["xg"])
        else:
            raise ValueError(f"métrica desconhecida: {metric}")
        return sub

    def estimate(self, metric: str, zone: Optional[str] = None, score_ctx: Optional[str] = None,
                 minute_band: Optional[str] = None, B: int = 100, seed: int = 42, min_n: int = 30,
                 persist: bool = True) -> Dict[str, Any]:
        sub = self._rows_and_values(self.pool, metric)
        for col, val in (("zone", zone), ("score_ctx", score_ctx), ("minute_band", minute_band)):
            if val:
                sub = sub[sub[col] == val]
        n = int(len(sub))
        base = {"metric": metric, "label": METRICS[metric]["label"], "zone": zone or "todas",
                "score_ctx": score_ctx or "todos", "minute_band": minute_band or "todas", "n": n, "B": B,
                "generator": f"{GENERATOR} (estratos zona × placar × minuto, B={B})",
                "confidence_tier": "SIMULATED", "ci_text": CI_TEXT,
                "reference_matches": int(self.pool["match_id"].nunique()) if not self.pool.empty else 0}
        if n < min_n:
            return {**base, "value": None, "ci_low": None, "ci_high": None,
                    "status": f"amostra insuficiente (n = {n} < {min_n})"}
        rng = np.random.default_rng(seed)
        total = np.zeros(B)
        for _, cell in sub.groupby(["zone", "score_ctx", "minute_band"]):
            v = cell["v"].to_numpy(dtype=float)
            idx = rng.integers(0, len(v), size=(B, len(v)))
            total += v[idx].sum(axis=1)
        reps = total / n
        value = float(sub["v"].mean())
        res = {**base, "value": round(value, 4), "ci_low": round(float(np.percentile(reps, 2.5)), 4),
               "ci_high": round(float(np.percentile(reps, 97.5)), 4), "status": "ok"}
        if persist:
            self.persist([res])
        return res

    def zone_grid(self, metric: str, score_ctx: Optional[str] = None, minute_band: Optional[str] = None,
                  B: int = 100, seed: int = 42) -> pd.DataFrame:
        rows = [self.estimate(metric, z, score_ctx, minute_band, B=B, seed=seed, persist=False) for z in ZONES]
        self.persist([r for r in rows if r["status"] == "ok"])
        return pd.DataFrame(rows)

    def persist(self, results: List[Dict[str, Any]]) -> int:
        if not self.db_path or not results:
            return 0
        frame = make_aggregate_frame(
            [{"entity": f"{r['zone']}|{r['score_ctx']}|{r['minute_band']}", "metric": r["metric"],
              "value": r["value"], "ci_low": r["ci_low"], "ci_high": r["ci_high"]} for r in results if r.get("value") is not None],
            source="Distribuição empírica StatsBomb Open Data (banco local)", connector="EmpiricalFallback",
            license="Derivado de StatsBomb Open Data — crédito à StatsBomb", confidence_tier="SIMULATED")
        frame["generator"] = results[0]["generator"]
        frame["n"] = [r["n"] for r in results if r.get("value") is not None]
        with sqlite3.connect(str(self.db_path)) as conn:
            frame.to_sql("simulated_estimates", conn, if_exists="append", index=False)
        return len(frame)


class SimulationUncertainty:
    """IC 95% das métricas de uma partida simulada, re-simulando com B sementes."""

    KEYS = (("defensive_organization", "ppda", "PPDA"), ("midfield_control", "field_tilt_pct", "Field Tilt (%)"),
            ("offensive_organization", "total_xg", "xG"), ("offensive_organization", "total_shots", "Finalizações"),
            ("offensive_organization", "overall_pass_completion_pct", "Precisão de passe (%)"))

    @classmethod
    def compute(cls, match_id: int, home: str, away: str, B: int = 100, use_cache: bool = True) -> Dict[str, Any]:
        from src.ingestion.brazil_and_multi_source import BrasileiraoAndMultiSourceProvider as Gen
        from src.metrics.tactical_metrics import TacticalMetricsEngine
        from src.metrics.xt_model import ExpectedThreatModel
        from src.preprocessing.event_cleaner import EventPreprocessor

        SIM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache = SIM_CACHE_DIR / f"{int(match_id)}_B{B}.json"
        if use_cache and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        samples: Dict[str, Dict[str, List[float]]] = {home: {}, away: {}}
        for b in range(B):
            raw = Gen.generate_simulated_match_events(home, away, int(match_id), seed=int(match_id) * 1000 + b)
            df = ExpectedThreatModel.enrich_events_with_xt(EventPreprocessor.process_match_events(raw))
            ch = EventPreprocessor.build_possession_chains(df)
            for team in (home, away):
                s = TacticalMetricsEngine.generate_full_match_tactical_summary(df, ch, team)
                for sec, key, _ in cls.KEYS:
                    samples[team].setdefault(key, []).append(float(s[sec][key]))
        out: Dict[str, Any] = {"match_id": int(match_id), "B": B, "generator": f"{SIM_GENERATOR} (re-simulação com B={B} sementes)",
                               "ci_text": CI_TEXT, "computed_at": utc_now_iso(), "teams": {}}
        for team in (home, away):
            out["teams"][team] = {
                key: {"label": label, "median": round(float(np.median(samples[team][key])), 2),
                      "ci_low": round(float(np.percentile(samples[team][key], 2.5)), 2),
                      "ci_high": round(float(np.percentile(samples[team][key], 97.5)), 2)}
                for _sec, key, label in cls.KEYS}
        cache.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        return out
