"""
Algoritmo genético de escalação (rodada 9) — a escalação que mais "machuca" as fraquezas do adversário.

Cromossomo: um atleta diferente para cada uma das 11 vagas da formação.
Aptidão (fitness), toda explicada:
    Σ nota × encaixe na vaga                          (a mesma conta do melhor XI atual, algoritmo húngaro)
  + Σ bônus de exploração                             (fraqueza do rival × atleta certo na vaga certa)
  − penalidades                                       (lesionado/suspenso escalado)
Fraquezas vêm de `src/analytics/vulnerabilities.py` (lado = lado DO RIVAL; o lado esquerdo deles é atacado pela nossa
direita). Atributos do atleta usados no bônus quando existem (0–1): drible, cruzamento, aereo, finalizacao, pressao,
altura_cm; sem o atributo, vale 0,5 (neutro) — nunca inventamos um número alto.
Operadores: seleção por torneio (k=3), cruzamento uniforme com reparo (sem atleta repetido), mutação por troca de vagas
e por entrada do banco, elitismo (2), semente fixa (reprodutível).
Comparação honesta: o melhor XI do algoritmo húngaro é ótimo para a parte "nota × encaixe"; o genético só vale a pena
se a aptidão COMPLETA (com o rival) dele for maior. O resultado mostra as duas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.squad.formations import FORMATIONS, ROLE_PT, fit

BONUS = 10.0          # pontos de "nota" (escala 0–100) por fraqueza de gravidade 100 explorada pelo atleta ideal
ATTRS = ("drible", "cruzamento", "aereo", "finalizacao", "pressao")


def _side_of_slot(y: float) -> Optional[str]:
    return "esquerda" if y < 26.7 else ("direita" if y > 53.3 else None)


def _rules(f: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Fraqueza → [(tipo de vaga, atributo que explora)]; tipo: 'lado' (corredor oposto), 'area', 'meia', 'frente'."""
    t = (f.get("titulo") or "").lower()
    if "driblado" in t or "desarma pouco" in t or "perde muitos duelos" in t:
        return [("lado", "drible")]
    if "quase não defende" in t:
        return [("lado_def", "cruzamento")]
    if "aéreo" in t or "zagueiro baixo" in t:
        return [("area", "aereo")]
    if "cruzamentos" in t:
        return [("area", "aereo"), ("ponta", "cruzamento")]
    if "contra-ataque" in t:
        return [("frente", "drible")]
    if "chutar de fora" in t:
        return [("meia", "finalizacao")]
    if "saída de bola" in t:
        return [("frente", "pressao")]
    if "chutes pelo lado" in t:
        return [("lado", "finalizacao")]
    return []


def _attr(row: Dict[str, Any], a: str) -> float:
    v = row.get(a)
    if a == "aereo" and (v is None or v != v):
        h = row.get("altura_cm")
        if h is not None and h == h:
            return float(np.clip((float(h) - 175) / 20, 0, 1))
    try:
        v = float(v)
        return float(np.clip(v, 0, 1)) if v == v else 0.5
    except (TypeError, ValueError):
        return 0.5


def bonus_matrix(slots, players: List[Dict[str, Any]], findings: Sequence[Dict[str, Any]]):
    """B[i, j] = bônus por colocar o atleta j na vaga i; e o porquê de cada bônus."""
    B = np.zeros((len(slots), len(players)))
    why: Dict[Tuple[int, int], List[str]] = {}
    for f in findings or []:
        g = float(f.get("gravidade") or 50) / 100.0
        rival_side = f.get("lado")
        for kind, attr in _rules(f):
            for i, (role, x, y) in enumerate(slots):
                side = _side_of_slot(y)
                ok = False
                if kind == "lado":       # corredor deles = nosso lado oposto, do meio para frente
                    opp = {"esquerda": "direita", "direita": "esquerda"}.get(rival_side or "")
                    ok = role in ("LW", "RW", "LM", "RM", "LWB", "RWB") and side is not None and (opp is None or side == opp)
                elif kind == "lado_def":  # o ponta deles não volta: nosso lateral daquele corredor sobe
                    opp = {"esquerda": "direita", "direita": "esquerda"}.get(rival_side or "")
                    ok = role in ("LB", "RB", "LWB", "RWB") and (opp is None or side == opp)
                elif kind == "area":
                    ok = role in ("ST",)
                elif kind == "ponta":
                    ok = role in ("LW", "RW", "LM", "RM", "LWB", "RWB")
                elif kind == "meia":
                    ok = role in ("AM", "CM")
                elif kind == "frente":
                    ok = role in ("ST", "LW", "RW", "AM")
                if not ok:
                    continue
                for j, p in enumerate(players):
                    b = BONUS * g * _attr(p, attr) * fit(role, p.get("papel") or "")
                    if b > 0.2:
                        B[i, j] += b
                        why.setdefault((i, j), []).append(f"{f.get('titulo')} → {attr}")
    return B, why


class LineupGA:
    def __init__(self, players: pd.DataFrame, formation: str = "4-3-3", findings: Sequence[Dict[str, Any]] = (),
                 seed: int = 42, pop: int = 60, generations: int = 150, p_mut: float = 0.35, elite: int = 2):
        self.slots = FORMATIONS[formation]
        self.formation = formation
        p = players.reset_index(drop=True)
        self.players = p.to_dict("records")
        if len(self.players) < len(self.slots):
            raise ValueError(f"elenco com {len(self.players)} atletas: são precisos pelo menos {len(self.slots)}")
        nota = pd.to_numeric(p.get("nota"), errors="coerce").fillna(40).to_numpy(float)
        self.base = np.array([[nota[j] * fit(r, self.players[j].get("papel") or "") for j in range(len(p))]
                              for r, _, _ in self.slots])
        self.B, self.why = bonus_matrix(self.slots, self.players, findings)
        out = np.array([bool(str(x.get("lesao") or x.get("indisponivel") or "").strip()) for x in self.players])
        self.penalty = np.where(out, 1000.0, 0.0)
        self.rng = np.random.default_rng(seed)
        self.pop, self.generations, self.p_mut, self.elite = pop, generations, p_mut, elite
        self.history: List[float] = []

    def fitness(self, chrom: np.ndarray, with_bonus: bool = True) -> float:
        idx = np.arange(len(self.slots))
        v = self.base[idx, chrom].sum() - self.penalty[chrom].sum()
        return float(v + (self.B[idx, chrom].sum() if with_bonus else 0.0))

    def baseline(self) -> np.ndarray:
        """Melhor XI só por nota × encaixe (algoritmo húngaro) — a referência."""
        from scipy.optimize import linear_sum_assignment

        r, c = linear_sum_assignment(-(self.base - self.penalty[None, :]))
        out = np.empty(len(self.slots), int)
        out[r] = c
        return out

    def _random(self) -> np.ndarray:
        return self.rng.permutation(len(self.players))[:len(self.slots)]

    def _repair(self, child: np.ndarray) -> np.ndarray:
        seen, free = set(), [j for j in self.rng.permutation(len(self.players)) if j not in set(child.tolist())]
        for i, g in enumerate(child):
            if g in seen:
                child[i] = free.pop()
            seen.add(int(child[i]))
        return child

    def _cross(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        mask = self.rng.random(len(a)) < 0.5
        return self._repair(np.where(mask, a, b).copy())

    def _mutate(self, c: np.ndarray) -> np.ndarray:
        c = c.copy()
        if self.rng.random() < 0.5:                       # troca duas vagas
            i, k = self.rng.choice(len(c), 2, replace=False)
            c[i], c[k] = c[k], c[i]
        else:                                             # entra alguém do banco
            bench = [j for j in range(len(self.players)) if j not in set(c.tolist())]
            if bench:
                c[self.rng.integers(len(c))] = self.rng.choice(bench)
        return c

    def _tournament(self, P, fit_v, k: int = 3) -> np.ndarray:
        ids = self.rng.choice(len(P), k, replace=False)
        return P[ids[np.argmax(fit_v[ids])]]

    def run(self, seed_with_baseline: bool = True) -> Dict[str, Any]:
        base = self.baseline()
        P = ([base.copy()] if seed_with_baseline else []) + [self._random() for _ in range(self.pop - (1 if seed_with_baseline else 0))]
        P = np.array(P)
        for _ in range(self.generations):
            fv = np.array([self.fitness(c) for c in P])
            self.history.append(float(fv.max()))
            elite = P[np.argsort(-fv)[:self.elite]]
            kids = [e.copy() for e in elite]
            while len(kids) < self.pop:
                child = self._cross(self._tournament(P, fv), self._tournament(P, fv))
                if self.rng.random() < self.p_mut:
                    child = self._mutate(child)
                kids.append(child)
            P = np.array(kids)
        fv = np.array([self.fitness(c) for c in P])
        best = P[int(np.argmax(fv))]
        return {"formacao": self.formation, "xi": self._describe(best), "xi_base": self._describe(base),
                "aptidao": round(self.fitness(best), 1), "aptidao_base": round(self.fitness(base), 1),
                "so_nota_encaixe": round(self.fitness(best, False), 1),
                "so_nota_encaixe_base": round(self.fitness(base, False), 1),
                "ganho": round(self.fitness(best) - self.fitness(base), 1), "historico": self.history,
                "mudancas": [(b["papel_pt"], b["jogador"], g["jogador"])
                             for b, g in zip(self._describe(base), self._describe(best)) if b["jogador"] != g["jogador"]]}

    def _describe(self, chrom: np.ndarray) -> List[Dict[str, Any]]:
        out = []
        for i, (role, x, y) in enumerate(self.slots):
            j = int(chrom[i])
            p = self.players[j]
            out.append({"vaga": i, "papel": role, "papel_pt": ROLE_PT.get(role, role), "x": x, "y": y,
                        "jogador": p.get("nome"), "nota": p.get("nota"), "encaixe": round(fit(role, p.get("papel") or ""), 2),
                        "bonus": round(float(self.B[i, j]), 1), "porque": self.why.get((i, j), [])})
        return out
