"""
Rodada 27e — RACIOCÍNIO do Assistente para perguntas de interpretação.

Antes, "a posse indica controle?", "quem finalizou com mais qualidade?", "por que tantas faltas?" ou "o resultado foi
justo?" caíam numa resposta de uma linha ("X teve mais Y") ou na métrica errada (finalizações no lugar de "no gol").
Aqui cada tipo de pergunta tem um raciocínio próprio que CRUZA os números do jogo:

    resposta direta → números que embasam → leitura (o que os números juntos dizem) → limite do dado

Funciona com jogos de estatísticas (FotMob/ESPN) e com jogos de lances (as mesmas chaves calculadas dos lances).
Regras do laboratório: número que a fonte não mede não vira zero; estimativa diz que é estimativa; associação não é
causa; hipóteses vêm ordenadas pela evidência e a que não dá para medir aparece como "não medível".
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


def fmt(v: Any, dec: int = 2) -> str:
    x = _f(v)
    if x is None:
        return "—"
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x))}"
    return f"{x:.{dec}f}".replace(".", ",")


def minute(v: Any) -> str:
    """Minuto legível; sem minuto na fonte → texto vazio (antes aparecia "None'")."""
    x = _f(v)
    return f"{int(x)}'" if x is not None else ""


# ------------------------------------------------------------------------------------------------- o jogo em números
@dataclass
class Game:
    home: str
    away: str
    hs: Optional[float]
    as_: Optional[float]
    meta: Dict[str, Any]
    T: Dict[str, Dict[str, float]] = field(default_factory=dict)        # chave → time → valor
    pct: Dict[str, Dict[str, float]] = field(default_factory=dict)      # chave → time → % de acerto (da fonte)
    players: pd.DataFrame = field(default_factory=pd.DataFrame)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    shots: pd.DataFrame = field(default_factory=pd.DataFrame)
    extra: Dict[str, Any] = field(default_factory=dict)
    lineups: pd.DataFrame = field(default_factory=pd.DataFrame)
    has_events: bool = False
    pt: Callable[[str], str] = lambda x: x

    @property
    def teams(self) -> List[str]:
        return [t for t in (self.home, self.away) if t]

    def other(self, t: str) -> str:
        return self.away if t == self.home else self.home

    def v(self, key: str, team: str) -> Optional[float]:
        return _f((self.T.get(key) or {}).get(team))

    def has(self, key: str) -> bool:
        d = self.T.get(key) or {}
        return all(_f(d.get(t)) is not None for t in self.teams)

    def goals(self, team: str) -> Optional[float]:
        return self.hs if team == self.home else self.as_

    def n(self, team: str) -> str:
        return f"**{self.pt(team)}**"

    @property
    def winner(self) -> Optional[str]:
        if self.hs is None or self.as_ is None or self.hs == self.as_:
            return None
        return self.home if self.hs > self.as_ else self.away

    def score(self) -> str:
        return f"{self.pt(self.home)} {fmt(self.hs)} x {fmt(self.as_)} {self.pt(self.away)}"


def _pct_from_display(d: Any) -> Optional[float]:
    m = re.search(r"\((\d+(?:[.,]\d+)?)%\)", str(d or ""))
    return float(m.group(1).replace(",", ".")) if m else None


def _timeline_from_events(df: pd.DataFrame) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return out
    d = df[df["period"].fillna(1) <= 4] if "period" in df else df
    for r in d.itertuples(index=False):
        typ = getattr(r, "type_name", None)
        mi = getattr(r, "minute", None)
        team = getattr(r, "team_name", None)
        if typ == "Shot" and getattr(r, "shot_outcome_name", None) == "Goal":
            out.append({"minute": mi, "team": team, "player": getattr(r, "player_name", None), "type": "Goal"})
        elif typ == "Own Goal For":
            out.append({"minute": mi, "team": team, "player": "gol contra", "type": "Goal"})
        elif typ == "Substitution":
            out.append({"minute": mi, "team": team, "player": getattr(r, "substitution_replacement_name", None),
                        "related": getattr(r, "player_name", None), "type": "Substitution"})
        for col in ("foul_committed_card_name", "bad_behaviour_card_name"):
            card = getattr(r, col, None)
            if isinstance(card, str) and ("Red" in card or "Second Yellow" in card):
                out.append({"minute": mi, "team": team, "player": getattr(r, "player_name", None), "type": "Red Card"})
            elif isinstance(card, str) and "Yellow" in card:
                out.append({"minute": mi, "team": team, "player": getattr(r, "player_name", None), "type": "Yellow Card"})
    return out


def build_game(meta: Dict[str, Any], df: Optional[pd.DataFrame], box: Optional[Dict[str, Any]], db=None,
               pt: Callable[[str], str] = lambda x: x) -> Game:
    home, away = meta.get("home_team_name", "") or "", meta.get("away_team_name", "") or ""
    g = Game(home, away, _f(meta.get("home_score")), _f(meta.get("away_score")), meta, pt=pt)
    g.has_events = df is not None and not getattr(df, "empty", True)
    box = box or {}
    if g.has_events:
        from src.intelligence.lab_ai.facts import team_stats_from_events

        ts = team_stats_from_events(df)
        ts["display_value"] = None
    else:
        ts = box.get("team_stats")
    if ts is not None and not getattr(ts, "empty", True):
        for r in ts.itertuples(index=False):
            val = _f(getattr(r, "value", None))
            if val is None:
                continue
            g.T.setdefault(r.stat_key, {})[r.team_name] = val
            p = _pct_from_display(getattr(r, "display_value", None))
            if p is not None:
                g.pct.setdefault(r.stat_key, {})[r.team_name] = p
    # números por jogador (FotMob) — para somar o que o time não traz (dribles tentados, aéreos, duelos perdidos)
    ps = box.get("player_stats")
    if ps is not None and not getattr(ps, "empty", True) and "stats" in ps:
        rows = []
        for r in ps.itertuples(index=False):
            s = r.stats if isinstance(r.stats, dict) else {}
            rows.append({"team": r.team_name, "player": r.player_name, "minutes": _f(getattr(r, "minutes", None))
                         if _f(getattr(r, "minutes", None)) is not None else _f(s.get("minutes")),
                         "rating": _f(getattr(r, "rating", None)), **s})
        g.players = pd.DataFrame(rows)
    tl = box.get("timeline")
    if g.has_events:
        g.timeline = _timeline_from_events(df)
    elif tl is not None and not getattr(tl, "empty", True):
        g.timeline = [{"minute": _f(r.minute), "team": r.team_name, "player": r.player_name,
                       "related": getattr(r, "related_player", None), "type": r.event_type}
                      for r in tl.itertuples(index=False)]
    lu = box.get("lineups")
    if lu is not None and not getattr(lu, "empty", True):
        g.lineups = lu
    mid = int(meta.get("match_id") or 0)
    if db is not None and mid:
        try:
            import json

            with db.connect() as conn:
                g.shots = pd.read_sql_query("SELECT * FROM match_shots WHERE match_id = ?", conn, params=(mid,))
                row = conn.execute("SELECT extra_json FROM match_extra WHERE match_id = ?", (mid,)).fetchone()
                g.extra = json.loads(row[0]) if row and row[0] else {}
        except Exception:
            pass
    if g.shots.empty and g.has_events:
        s = df[df["type_name"] == "Shot"]
        if not s.empty:
            g.shots = pd.DataFrame({"team_name": s["team_name"], "player_name": s.get("player_name"), "minute": s["minute"],
                                    "x": s["x"], "y": s["y"],
                                    "xg": pd.to_numeric(s.get("shot_statsbomb_xg"), errors="coerce"),
                                    "outcome": s.get("shot_outcome_name"), "situation": s.get("play_pattern_name"),
                                    "shot_type": s.get("shot_body_part_name")})
    return g


def _player_sum(g: Game, key: str, team: str) -> Optional[float]:
    p = g.players
    if p.empty or key not in p:
        return None
    vals = pd.to_numeric(p.loc[p["team"] == team, key], errors="coerce")
    return float(vals.sum()) if vals.notna().any() else None


def _top_players(g: Game, key: str, label: str, n: int = 3) -> Optional[str]:
    p = g.players
    if p.empty or key not in p:
        return None
    t = p.assign(vv=pd.to_numeric(p[key], errors="coerce")).dropna(subset=["vv"])
    t = t[t["vv"] > 0].sort_values(["vv", "minutes"], ascending=[False, True]).head(n)
    if t.empty:
        return None
    return f"{label}: " + "; ".join(f"{r.player} ({g.pt(r.team)}) {fmt(r.vv)}" for r in t.itertuples()) + "."


def _ratio(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if a is None or b in (None, 0) else a / b


# ------------------------------------------------------------------------------------------------- estado do jogo
def game_state(g: Game) -> Dict[str, Any]:
    """Minutos à frente/atrás/empatado de cada time e expulsões (o placar muda o comportamento dos times)."""
    goals = sorted([e for e in g.timeline if e.get("type") == "Goal" and _f(e.get("minute")) is not None],
                   key=lambda e: _f(e["minute"]))
    reds = [e for e in g.timeline if e.get("type") in ("Red Card", "Second Yellow", "RedCard")]
    end = 90.0
    lead = {t: 0.0 for t in g.teams}
    level = 0.0
    sh = sa = 0
    last = 0.0
    for e in goals + [{"minute": end, "team": None}]:
        m = min(_f(e["minute"]) or end, end)
        span = max(0.0, m - last)
        if sh > sa:
            lead[g.home] += span
        elif sa > sh:
            lead[g.away] += span
        else:
            level += span
        last = m
        if e.get("team") == g.home:
            sh += 1
        elif e.get("team") == g.away:
            sa += 1
    first = goals[0] if goals else None
    return {"lead": lead, "level": level, "goals": goals, "reds": reds, "first": first}


def _state_line(g: Game, st: Dict[str, Any]) -> Optional[str]:
    bits = []
    if st["first"] is not None:
        bits.append(f"{g.pt(st['first']['team'])} abriu o placar aos {minute(st['first']['minute'])}")
    for t in g.teams:
        if st["lead"][t] >= 20:
            bits.append(f"{g.pt(t)} passou ~{st['lead'][t]:.0f} min na frente")
    for r in st["reds"]:
        bits.append(f"{g.pt(r.get('team') or '')} teve um expulso" + (f" aos {minute(r.get('minute'))}" if minute(r.get('minute')) else "")
                    + (f" ({r.get('player')})" if r.get("player") else ""))
    return ("**Estado do jogo:** " + "; ".join(bits) + ".") if bits else None


def _behind_team(st: Dict[str, Any], g: Game) -> Optional[str]:
    """Quem passou mais tempo ATRÁS no placar (tende a ficar com a bola e se expor)."""
    t = max(g.teams, key=lambda x: st["lead"][g.other(x)], default=None)
    return t if t and st["lead"][g.other(t)] >= 20 else None


# ------------------------------------------------------------------------------------------------- probabilidades
def win_probabilities(g: Game, n: int = 6000, seed: int = 7) -> Optional[Dict[str, float]]:
    """Estimativa: cada finalização vira gol com a chance do seu xG (independentes). Sem mapa de chutes → None."""
    s = g.shots
    if s is None or s.empty or "xg" not in s:
        return None
    s = s.copy()
    s["xg"] = pd.to_numeric(s["xg"], errors="coerce")
    if "own_goal" in s:
        s = s[pd.to_numeric(s["own_goal"], errors="coerce").fillna(0) == 0]
    s = s.dropna(subset=["xg"])
    if s.empty:
        return None
    rng = np.random.default_rng(seed)
    goals = {}
    for t in g.teams:
        p = s.loc[s["team_name"] == t, "xg"].clip(0, 0.99).to_numpy()
        goals[t] = (rng.random((n, len(p))) < p).sum(axis=1) if len(p) else np.zeros(n, dtype=int)
    h, a = goals[g.home], goals[g.away]
    return {"home": float((h > a).mean()), "draw": float((h == a).mean()), "away": float((h < a).mean())}


# ------------------------------------------------------------------------------------------------- os raciocínios
Answer = Optional[str]


def _bullets(rows: List[str]) -> str:
    return "\n".join(f"- {r}" for r in rows if r)


def _block(direct: str, nums: List[str], reading: List[str], limit: Optional[str] = None,
           state: Optional[str] = None) -> str:
    out = [f"**Resposta direta:** {direct}"]
    if nums:
        out.append("**Os números:**\n" + _bullets(nums))
    if reading or state:
        out.append("**Leitura:**\n" + _bullets(([state] if state else []) + reading))
    if limit:
        out.append(f"_Limite: {limit}_")
    return "\n\n".join(out)


def _pair(g: Game, key: str, label: str, suffix: str = "", dec: int = 2) -> Optional[str]:
    if not g.has(key):
        return None
    pc = g.pct.get(key) or {}
    def one(t):
        p = pc.get(t)
        return f"{g.pt(t)} {fmt(g.v(key, t), dec)}{suffix}" + (f" ({p:.0f}% de acerto)" if p is not None else "")
    return f"{label}: " + " × ".join(one(t) for t in g.teams)


def _leader(g: Game, key: str) -> Optional[Tuple[str, float, float]]:
    if not g.has(key):
        return None
    a, b = g.v(key, g.home), g.v(key, g.away)
    if a == b:
        return None
    t = g.home if a > b else g.away
    return t, max(a, b), min(a, b)


def r_control(g: Game, q: str, focus: str) -> Answer:
    if not g.has("possession_pct") and not g.has("xg"):
        return None
    lead_pos = _leader(g, "possession_pct")
    chance_key = "xg" if g.has("xg") else ("shots_on_target" if g.has("shots_on_target") else "shots_total")
    lead_ch = _leader(g, chance_key)
    signals = [k for k in ("possession_pct", "passes_opp_half", "touches_opp_box", "shots_total", "shots_on_target",
                           "xg", "big_chances", "corners") if g.has(k)]
    score = {t: sum(1 for k in signals if g.v(k, t) > g.v(k, g.other(t))) for t in g.teams}
    st = game_state(g)
    nums = [_pair(g, "possession_pct", "Posse de bola", "%", 0), _pair(g, "passes_opp_half", "Passes no campo de ataque", dec=0),
            _pair(g, "touches_opp_box", "Toques na área rival", dec=0), _pair(g, "shots_total", "Finalizações", dec=0),
            _pair(g, "xg", "xG (qualidade das chances)"), _pair(g, "big_chances", "Grandes chances", dec=0)]
    reading = []
    if lead_pos and lead_ch and lead_pos[0] != lead_ch[0]:
        direct = (f"não. {g.n(lead_pos[0])} ficou mais com a bola ({fmt(lead_pos[1], 0)}%), mas quem controlou o que "
                  f"decide jogo — as chances — foi {g.n(lead_ch[0])} ({'xG' if chance_key == 'xg' else 'finalizações'} "
                  f"{fmt(lead_ch[1])} × {fmt(lead_ch[2])}). Posse aqui foi volume, não domínio.")
        reading.append(f"Ter a bola e não transformar em chance indica posse longe da área ou um rival que se fechou bem — "
                       f"{g.pt(lead_ch[0])} escolheu onde jogar.")
    elif lead_pos and lead_ch:
        direct = (f"sim, neste jogo a posse acompanhou o controle: {g.n(lead_pos[0])} teve mais bola "
                  f"({fmt(lead_pos[1], 0)}%) e também as melhores chances ({fmt(lead_ch[1])} × {fmt(lead_ch[2])} de "
                  f"{'xG' if chance_key == 'xg' else 'finalizações'}).")
    else:
        best = max(g.teams, key=lambda t: score[t])
        direct = f"jogo equilibrado no controle; pelos sinais somados, {g.n(best)} levou {score[best]} de {len(signals)} indicadores."
    if signals:
        reading.append("Placar de controle (quem leva cada indicador: posse, campo de ataque, área, chutes, xG, "
                       "grandes chances, escanteios): " + " × ".join(f"{g.pt(t)} {score[t]}" for t in g.teams) + ".")
    if g.has("passes_opp_half") and g.has("passes_accurate"):
        share = {t: _ratio(g.v("passes_opp_half", t), (g.v("passes_opp_half", t) or 0) + (g.v("passes_own_half", t) or 0)
                           if g.has("passes_own_half") else g.v("passes_accurate", t)) for t in g.teams}
        if all(v is not None for v in share.values()):
            reading.append("Onde a posse aconteceu: " + " × ".join(f"{g.pt(t)} {100 * share[t]:.0f}% dos passes no campo "
                                                                  f"de ataque" for t in g.teams) + ".")
    behind = _behind_team(st, g)
    if behind and lead_pos and lead_pos[0] == behind:
        reading.append(f"Parte da posse de {g.pt(behind)} vem do placar: atrás por bastante tempo, precisou ter a bola, e "
                       f"{g.pt(g.other(behind))} aceitou defender a vantagem.")
    return _block(direct, nums, reading, "posse mede tempo com a bola, não perigo; sem lances com coordenadas não dá para "
                  "ver em que zona exata cada time teve a bola (só campo de defesa × ataque e toques na área).",
                  _state_line(g, st))


def r_shots(g: Game, q: str, focus: str) -> Answer:
    if not g.has("shots_total"):
        return None
    lead = _leader(g, "shots_total")
    xs = {t: _ratio(g.v("xg", t), g.v("shots_total", t)) for t in g.teams} if g.has("xg") else {}
    nums = [_pair(g, "shots_total", "Finalizações", dec=0), _pair(g, "shots_on_target", "No gol", dec=0),
            _pair(g, "shots_inside_box", "De dentro da área", dec=0), _pair(g, "shots_outside_box", "De fora da área", dec=0),
            _pair(g, "shots_blocked", "Bloqueadas pelo rival", dec=0), _pair(g, "xg", "xG"),
            ("xG por finalização: " + " × ".join(f"{g.pt(t)} {fmt(xs[t])}" for t in g.teams)) if xs and all(xs.values()) else None]
    reading = []
    if lead is None:
        direct = f"empate em finalizações ({fmt(g.v('shots_total', g.home), 0)} para cada)."
    else:
        direct = f"{g.n(lead[0])} finalizou mais ({fmt(lead[1], 0)} × {fmt(lead[2], 0)})."
    if xs and all(xs.values()):
        best_q = max(g.teams, key=lambda t: xs[t])
        if lead and best_q != lead[0]:
            direct += (f" Mas a qualidade foi de {g.n(best_q)}: {fmt(xs[best_q])} de xG por chute contra "
                       f"{fmt(xs[g.other(best_q)])} — chutou menos, de lugares melhores.")
        elif lead:
            direct += f" E com mais qualidade também ({fmt(xs[best_q])} de xG por chute)."
        if max(xs.values()) < 0.08:
            reading.append("Os dois finalizaram mal posicionados (menos de 0,08 de xG por chute) — muito chute de longe "
                           "ou pressionado.")
    if g.has("shots_inside_box") and g.has("shots_total"):
        for t in g.teams:
            tot = g.v("shots_total", t) or 0
            if tot >= 6 and (g.v("shots_outside_box", t) or 0) / tot >= 0.5:
                reading.append(f"{g.pt(t)} chutou metade ou mais de fora da área — sinal de que não conseguiu entrar na "
                               f"área; volume de chute não é volume de perigo.")
    if g.has("shots_on_target"):
        acc = {t: _ratio(g.v("shots_on_target", t), g.v("shots_total", t)) for t in g.teams}
        if all(a is not None for a in acc.values()):
            reading.append("Pontaria: " + " × ".join(f"{g.pt(t)} {100 * acc[t]:.0f}% no gol" for t in g.teams) + ".")
    reading.append(_top_players(g, "totalShots", "Quem mais finalizou") or "")
    reading.append(_top_players(g, "xg", "Maior xG individual") or "")
    reading = [r for r in reading if r]
    return _block(direct, nums, reading, "o xG é da fonte; ele mede a chance média de gol de cada chute pela posição e "
                  "tipo, não a qualidade do batedor.")


def r_on_target(g: Game, q: str, focus: str) -> Answer:
    if not g.has("shots_on_target"):
        return None
    lead = _leader(g, "shots_on_target")
    nums = [_pair(g, "shots_on_target", "Finalizações no gol", dec=0), _pair(g, "shots_total", "Finalizações (total)", dec=0),
            _pair(g, "xgot", "xGOT (qualidade do chute que foi no gol)"), _pair(g, "saves", "Defesas do goleiro", dec=0)]
    direct = (f"{g.n(lead[0])} acertou mais o gol: {fmt(lead[1], 0)} × {fmt(lead[2], 0)}." if lead else
              f"os dois acertaram o gol {fmt(g.v('shots_on_target', g.home), 0)} vezes.")
    reading = []
    for t in g.teams:
        tot, on = g.v("shots_total", t), g.v("shots_on_target", t)
        if tot:
            reading.append(f"{g.pt(t)}: {fmt(on, 0)} de {fmt(tot, 0)} chutes no gol ({100 * on / tot:.0f}%).")
    if g.has("xgot"):
        for t in g.teams:
            gl, xgot = g.goals(t), g.v("xgot", t)
            if gl is None or xgot is None:
                continue
            diff = xgot - gl
            if diff >= 0.6:
                reading.append(f"O goleiro de {g.pt(g.other(t))} evitou cerca de {fmt(diff, 1)} gol(s) pelo xGOT: "
                               f"{g.pt(t)} chutou no gol com {fmt(xgot)} de xGOT e marcou {fmt(gl, 0)}.")
            elif diff <= -0.6:
                reading.append(f"{g.pt(t)} marcou {fmt(gl, 0)} com xGOT de {fmt(xgot)} — finalização muito acima do "
                               f"esperado (ou goleiro rival falhou).")
        if g.has("xg"):
            for t in g.teams:
                x, xo = g.v("xg", t), g.v("xgot", t)
                if x and xo is not None and xo - x >= 0.4:
                    reading.append(f"{g.pt(t)} colocou bem a bola: xGOT {fmt(xo)} maior que o xG {fmt(x)} (chutes no canto).")
    return _block(direct, nums, reading, "“no gol” conta chutes que o goleiro precisou defender ou que entraram; bola na "
                  "trave não conta.")


def r_area(g: Game, q: str, focus: str) -> Answer:
    if not g.has("shots_inside_box"):
        return None
    nums = [_pair(g, "shots_inside_box", "De dentro da área", dec=0), _pair(g, "shots_outside_box", "De fora da área", dec=0),
            _pair(g, "touches_opp_box", "Toques na área rival", dec=0)]
    s = g.shots
    reading = []
    if s is not None and not s.empty and {"x", "y", "xg"} <= set(s.columns):
        s = s.assign(xg=pd.to_numeric(s["xg"], errors="coerce"),
                     inbox=(pd.to_numeric(s["x"], errors="coerce") >= 102) & pd.to_numeric(s["y"], errors="coerce").between(18, 62))
        for t in g.teams:
            st = s[s["team_name"] == t]
            if st.empty:
                continue
            xi, xo = st.loc[st["inbox"], "xg"].sum(), st.loc[~st["inbox"], "xg"].sum()
            reading.append(f"{g.pt(t)}: {fmt(xi)} de xG nos chutes de dentro da área e {fmt(xo)} nos de fora.")
    lead_in = _leader(g, "shots_inside_box")
    direct = (f"{g.n(lead_in[0])} chegou mais vezes para chutar dentro da área ({fmt(lead_in[1], 0)} × {fmt(lead_in[2], 0)})."
              if lead_in else "os dois chutaram o mesmo número de vezes de dentro da área.")
    for t in g.teams:
        tot = (g.v("shots_inside_box", t) or 0) + (g.v("shots_outside_box", t) or 0)
        if tot >= 6 and (g.v("shots_outside_box", t) or 0) > (g.v("shots_inside_box", t) or 0):
            reading.append(f"{g.pt(t)} chutou mais de fora do que de dentro — o rival protegeu bem a área e empurrou para o chute de longe.")
    return _block(direct, nums, reading, "chute de dentro da área vale em média 3 a 4 vezes mais que o de fora; a área "
                  "vem da posição informada pela fonte.")


def r_blocked(g: Game, q: str, focus: str) -> Answer:
    if not g.has("shots_blocked"):
        return None
    lead = _leader(g, "shots_blocked")
    nums = [_pair(g, "shots_blocked", "Finalizações bloqueadas (chutes que pararam na defesa)", dec=0),
            _pair(g, "shots_total", "Finalizações", dec=0), _pair(g, "blocks", "Bloqueios feitos pela defesa", dec=0),
            _pair(g, "clearances", "Cortes", dec=0)]
    reading = []
    for t in g.teams:
        tot, b = g.v("shots_total", t), g.v("shots_blocked", t)
        if tot:
            reading.append(f"{fmt(100 * b / tot, 0)}% dos chutes de {g.pt(t)} pararam num defensor.")
    if lead:
        direct = (f"{g.n(lead[0])} teve mais chutes bloqueados ({fmt(lead[1], 0)} × {fmt(lead[2], 0)}) — {g.pt(g.other(lead[0]))} "
                  f"defendeu com gente na frente da bola.")
        reading.append("Muito chute bloqueado costuma significar finalização com a área cheia (bloco baixo do rival) ou "
                       "chute apressado sem abrir espaço antes.")
    else:
        direct = "os dois tiveram o mesmo número de chutes bloqueados."
    return _block(direct, nums, reading, "a fonte não diz quem bloqueou cada chute nem de que distância — só o total.")


def r_big_chances(g: Game, q: str, focus: str) -> Answer:
    if not g.has("big_chances"):
        return None
    nums = [_pair(g, "big_chances", "Grandes chances", dec=0), _pair(g, "big_chances_missed", "Grandes chances perdidas", dec=0),
            _pair(g, "xg", "xG")]
    lead = _leader(g, "big_chances")
    direct = (f"{g.n(lead[0])} teve mais chances claras ({fmt(lead[1], 0)} × {fmt(lead[2], 0)})." if lead else
              f"empate em grandes chances ({fmt(g.v('big_chances', g.home), 0)} para cada).")
    reading = []
    if g.has("big_chances_missed"):
        for t in g.teams:
            bc, miss = g.v("big_chances", t), g.v("big_chances_missed", t)
            if bc:
                reading.append(f"{g.pt(t)} converteu {fmt(bc - miss, 0)} de {fmt(bc, 0)} grandes chances.")
    s = g.shots
    if s is not None and not s.empty and "xg" in s:
        big = s.assign(xg=pd.to_numeric(s["xg"], errors="coerce")).query("xg >= 0.3").sort_values("minute")
        if not big.empty:
            reading.append("As chances mais claras (xG ≥ 0,30): " + "; ".join(
                f"{minute(r.minute)} {r.player_name or 'jogador não informado'} ({g.pt(r.team_name)}, xG {fmt(r.xg)}, "
                f"{_OUT.get(str(r.outcome), str(r.outcome or '—'))})" for r in big.head(8).itertuples()) + ".")
    return _block(direct, nums, reading, "“grande chance” é a classificação da fonte (situação em que se espera o gol), "
                  "não a nossa.")


_OUT = {"Goal": "gol", "AttemptSaved": "defendida", "Miss": "para fora", "Post": "na trave", "Saved": "defendida",
        "Blocked": "bloqueada", "Off T": "para fora", "Wayward": "para fora", "Saved To Post": "defendida na trave"}


def r_efficiency(g: Game, q: str, focus: str) -> Answer:
    if not g.has("xg"):
        return None
    nums = [_pair(g, "xg", "xG (gols esperados)"), _pair(g, "xg_open_play", "xG de bola rolando"),
            _pair(g, "xg_set_play", "xG de bola parada"), _pair(g, "xgot", "xGOT")]
    nums.append("Gols: " + " × ".join(f"{g.pt(t)} {fmt(g.goals(t), 0)}" for t in g.teams))
    diffs = {t: (g.goals(t) or 0) - g.v("xg", t) for t in g.teams}
    best = max(g.teams, key=lambda t: diffs[t])
    if focus in g.teams:
        d = diffs[focus]
        verdict = ("foi eficiente" if d >= 0.5 else "desperdiçou" if d <= -0.5 else "marcou dentro do esperado")
        direct = (f"{g.n(focus)} {verdict}: {fmt(g.goals(focus), 0)} gol(s) com {fmt(g.v('xg', focus))} de xG "
                  f"({'+' if d >= 0 else ''}{fmt(d, 1)}). {g.pt(g.other(focus))}: {fmt(g.goals(g.other(focus)), 0)} com "
                  f"{fmt(g.v('xg', g.other(focus)))}.")
    else:
        direct = None
    direct = direct or (f"{g.n(best)} foi o mais eficiente: {fmt(g.goals(best), 0)} gol(s) com {fmt(g.v('xg', best))} de xG "
              f"({'+' if diffs[best] >= 0 else ''}{fmt(diffs[best], 1)} acima do esperado). {g.pt(g.other(best))} fez "
              f"{fmt(g.goals(g.other(best)), 0)} com {fmt(g.v('xg', g.other(best)))}.")
    reading = []
    for t in g.teams:
        d = diffs[t]
        if d >= 0.8:
            reading.append(f"{g.pt(t)} marcou bem acima das chances — finalização caprichada, goleiro rival abaixo ou "
                           f"sorte; num jogo só não dá para separar as três coisas.")
        elif d <= -0.8:
            reading.append(f"{g.pt(t)} desperdiçou: criou para {fmt(g.v('xg', t))} gols e marcou {fmt(g.goals(t), 0)}.")
    if g.has("xgot"):
        for t in g.teams:
            x, xo = g.v("xg", t), g.v("xgot", t)
            if x and xo is not None:
                reading.append(f"{g.pt(t)}: {'chutou melhor do que a chance pedia' if xo > x + 0.2 else 'desperdiçou na batida' if xo < x - 0.2 else 'batida dentro do esperado'} (xG {fmt(x)} → xGOT {fmt(xo)}).")
    wp = win_probabilities(g)
    if wp:
        reading.append(f"Repetindo essas mesmas chances muitas vezes (estimativa pelo xG de cada chute): {g.pt(g.home)} "
                       f"venceria {100 * wp['home']:.0f}%, empate {100 * wp['draw']:.0f}%, {g.pt(g.away)} {100 * wp['away']:.0f}%.")
    return _block(direct, nums, reading, "eficiência de UM jogo é muito ruidosa; só vira padrão se repetir em vários jogos.")


def r_passes(g: Game, q: str, focus: str) -> Answer:
    if not g.has("passes_accurate"):
        return None
    nums = [_pair(g, "passes_accurate", "Passes certos", dec=0), _pair(g, "pass_accuracy_pct", "Precisão", "%", 0),
            _pair(g, "passes_own_half", "No próprio campo", dec=0), _pair(g, "passes_opp_half", "No campo de ataque", dec=0),
            _pair(g, "long_balls_accurate", "Bolas longas certas", dec=0)]
    lead = _leader(g, "passes_accurate")
    acc = _leader(g, "pass_accuracy_pct")
    direct = (f"{g.n(lead[0])} trocou mais passes ({fmt(lead[1], 0)} certos × {fmt(lead[2], 0)})" if lead else "mesmo volume de passes")
    direct += (f" e com mais precisão ({fmt(acc[1], 0)}% × {fmt(acc[2], 0)}%)." if acc and lead and acc[0] == lead[0] else
               f"; a precisão maior foi de {g.pt(acc[0])} ({fmt(acc[1], 0)}%)." if acc else ".")
    reading = []
    if g.has("passes_opp_half") and g.has("passes_own_half"):
        for t in g.teams:
            own, opp = g.v("passes_own_half", t), g.v("passes_opp_half", t)
            if own + opp:
                share = opp / (own + opp)
                reading.append(f"{g.pt(t)}: {100 * share:.0f}% dos passes no campo de ataque"
                               + (" — circulação de segurança, muito toque atrás" if share < 0.42 else
                                  " — passe com intenção, jogando no campo do rival" if share > 0.52 else "") + ".")
    if acc and lead and acc[0] == lead[0] and g.has("xg") and _leader(g, "xg") and _leader(g, "xg")[0] != lead[0]:
        reading.append("Mais passes e mais precisão sem mais xG: a troca de passes não furou a defesa — precisão alta "
                       "costuma vir de passes curtos e laterais, que quase não erram.")
    return _block(direct, nums, reading, "precisão de passe não diz o risco do passe; sem lances não dá para ver passes "
                  "progressivos nem quem quebrou linhas no time inteiro.")


def r_long_balls(g: Game, q: str, focus: str) -> Answer:
    if not g.has("long_balls_accurate"):
        return None
    nums = [_pair(g, "long_balls_accurate", "Bolas longas certas", dec=0), _pair(g, "aerials_won", "Duelos aéreos ganhos", dec=0),
            _pair(g, "possession_pct", "Posse", "%", 0)]
    pc = g.pct.get("long_balls_accurate") or {}
    tot = {t: (g.v("long_balls_accurate", t) / (pc[t] / 100)) if pc.get(t) else None for t in g.teams}
    lead = _leader(g, "long_balls_accurate")
    direct = (f"{g.n(lead[0])} acertou mais bolas longas ({fmt(lead[1], 0)} × {fmt(lead[2], 0)})." if lead else
              "os dois acertaram o mesmo número de bolas longas.")
    reading = []
    if all(v for v in tot.values()):
        for t in g.teams:
            reading.append(f"{g.pt(t)} tentou ~{tot[t]:.0f} e acertou {pc[t]:.0f}%.")
        heavy = max(g.teams, key=lambda t: tot[t])
        if g.has("passes_accurate"):
            share = tot[heavy] / max(1.0, (g.v("passes_accurate", heavy) or 0) / max(0.5, (g.pct.get("passes_accurate") or {}).get(heavy, 80) / 100))
            if share >= 0.12:
                reading.append(f"{g.pt(heavy)} jogou mais direto (~{100 * share:.0f}% dos passes foram longos) — saída que "
                               f"pula a pressão e busca a segunda bola.")
    if g.has("aerials_won") and lead:
        aer = _leader(g, "aerials_won")
        if aer and aer[0] != lead[0]:
            reading.append(f"Mas quem ganhou o jogo aéreo foi {g.pt(aer[0])} ({fmt(aer[1], 0)} × {fmt(aer[2], 0)}): bola longa "
                           f"contra uma defesa que ganha no alto vira posse devolvida.")
    tp = _top_players(g, "long_balls_accurate", "Quem mais acertou bola longa")
    if tp:
        reading.append(tp)
    return _block(direct, nums, reading, "a fonte não diz para onde foram as bolas longas (costas da defesa ou pivô).")


def r_crosses(g: Game, q: str, focus: str) -> Answer:
    if not g.has("crosses_accurate"):
        return None
    pc = g.pct.get("crosses_accurate") or {}
    nums = [_pair(g, "crosses_accurate", "Cruzamentos certos", dec=0), _pair(g, "aerials_won", "Duelos aéreos ganhos", dec=0)]
    reading = []
    for t in g.teams:
        if pc.get(t):
            reading.append(f"{g.pt(t)} tentou ~{g.v('crosses_accurate', t) / (pc[t] / 100):.0f} cruzamentos e acertou {pc[t]:.0f}%.")
    s = g.shots
    if s is not None and not s.empty and "shot_type" in s:
        for t in g.teams:
            hd = s[(s["team_name"] == t) & s["shot_type"].astype(str).str.contains("Head", case=False)]
            if len(hd):
                reading.append(f"{g.pt(t)} finalizou {len(hd)} vez(es) de cabeça (xG {fmt(pd.to_numeric(hd['xg'], errors='coerce').sum())}).")
    lead = _leader(g, "crosses_accurate")
    direct = (f"{g.n(lead[0])} acertou mais cruzamentos ({fmt(lead[1], 0)} × {fmt(lead[2], 0)})." if lead else
              "mesmo número de cruzamentos certos.")
    if any(p < 25 for p in pc.values()):
        reading.append("Acerto de cruzamento abaixo de 25% é o normal ruim do futebol: cruzar muito costuma ser sinal de "
                       "que o time não achou caminho por dentro.")
    tp = _top_players(g, "accurate_crosses", "Quem mais acertou cruzamento")
    if tp:
        reading.append(tp)
    return _block(direct, nums, reading, "a fonte não separa cruzamento rasteiro de alto nem de que lado veio.")


def r_corners(g: Game, q: str, focus: str) -> Answer:
    if not g.has("corners"):
        return None
    nums = [_pair(g, "corners", "Escanteios", dec=0), _pair(g, "xg_set_play", "xG de bola parada")]
    lead = _leader(g, "corners")
    direct = (f"{g.n(lead[0])} teve mais escanteios ({fmt(lead[1], 0)} × {fmt(lead[2], 0)})." if lead else
              f"os dois tiveram {fmt(g.v('corners', g.home), 0)} escanteios.")
    reading = []
    s = g.shots
    if s is not None and not s.empty and "situation" in s:
        for t in g.teams:
            c = s[(s["team_name"] == t) & s["situation"].astype(str).str.contains("Corner", case=False)]
            reading.append(f"{g.pt(t)}: {len(c)} finalização(ões) saindo de escanteio"
                           + (f", xG {fmt(pd.to_numeric(c['xg'], errors='coerce').sum())}" if len(c) else "") + ".")
    if lead and g.has("xg_set_play") and g.v("xg_set_play", lead[0]) < 0.2:
        reading.append(f"Escanteio a mais de {g.pt(lead[0])} não virou perigo (xG de bola parada {fmt(g.v('xg_set_play', lead[0]))}). "
                       "Escanteio é sinal de pressão no último terço, não de chance.")
    return _block(direct, nums, reading, "a fonte não diz quem cobrou nem onde a bola caiu em cada escanteio.")


def r_dribbles(g: Game, q: str, focus: str) -> Answer:
    key = "dribbles_completed"
    if not g.has(key):
        return None
    pc = g.pct.get(key) or {}
    nums = [_pair(g, key, "Dribles certos", dec=0)]
    reading = []
    for t in g.teams:
        past = _player_sum(g, "dribbled_past", g.other(t))
        if past is not None:
            reading.append(f"Defensores de {g.pt(g.other(t))} foram driblados {fmt(past, 0)} vez(es).")
    p = g.players
    if not p.empty and "dribbles_succeeded" in p:
        top = p.assign(d=pd.to_numeric(p["dribbles_succeeded"], errors="coerce")).dropna(subset=["d"]).sort_values("d", ascending=False)
        top = top[top["d"] > 0].head(3)
        if not top.empty:
            reading.append("Quem mais driblou: " + "; ".join(f"{r.player} ({g.pt(r.team)}) {fmt(r.d, 0)}" for r in top.itertuples()) + ".")
    lead = _leader(g, key)
    direct = (f"{g.n(lead[0])} driblou mais ({fmt(lead[1], 0)} × {fmt(lead[2], 0)} certos"
              + (f", {pc.get(lead[0]):.0f}% de acerto" if pc.get(lead[0]) else "") + ")." if lead else "mesmo número de dribles certos.")
    reading.append("Drible só pesa quando acontece perto da área; a fonte não diz onde foi cada um.")
    return _block(direct, nums, reading)


def r_fouls(g: Game, q: str, focus: str) -> Answer:
    if not g.has("fouls"):
        return None
    st = game_state(g)
    lead = _leader(g, "fouls")
    nums = [_pair(g, "fouls", "Faltas cometidas", dec=0), _pair(g, "yellow_cards", "Amarelos", dec=0),
            _pair(g, "red_cards", "Vermelhos", dec=0), _pair(g, "possession_pct", "Posse", "%", 0),
            _pair(g, "duels_won", "Duelos ganhos", dec=0)]
    if lead is None:
        return _block(f"as faltas foram iguais ({fmt(g.v('fouls', g.home), 0)} para cada) — nada a explicar por diferença.",
                      nums, [], None, _state_line(g, st))
    t, o = lead[0], g.other(lead[0])
    hyps: List[Tuple[int, str, str]] = []
    # H1: faltas para cortar transição
    fast = 0
    s = g.shots
    if s is not None and not s.empty and "situation" in s:
        fast = int(((s["team_name"] == o) & s["situation"].astype(str).str.contains("FastBreak|Counter", case=False)).sum())
    ev1 = []
    if g.has("possession_pct") and g.v("possession_pct", o) > g.v("possession_pct", t):
        ev1.append(f"{g.pt(o)} ficou mais com a bola ({fmt(g.v('possession_pct', o), 0)}%)")
    if fast:
        ev1.append(f"{g.pt(o)} chegou {fast} vez(es) em contra-ataque")
    hyps.append((len(ev1), "Falta tática para parar a jogada do rival (cortar transição ou parar quem conduz)",
                 "; ".join(ev1) or "sem sinal claro de transição do rival"))
    # H2: perdeu os duelos / chegou atrasado
    ev2 = []
    if g.has("duels_won") and g.v("duels_won", o) > g.v("duels_won", t):
        ev2.append(f"{g.pt(o)} ganhou mais duelos ({fmt(g.v('duels_won', o), 0)} × {fmt(g.v('duels_won', t), 0)})")
    dp = _player_sum(g, "dribbled_past", t)
    if dp and dp >= 8:
        ev2.append(f"defensores de {g.pt(t)} foram driblados {fmt(dp, 0)} vezes")
    if g.has("dribbles_completed") and g.v("dribbles_completed", o) > g.v("dribbles_completed", t):
        ev2.append(f"{g.pt(o)} driblou mais")
    hyps.append((len(ev2), "Chegava atrasado nos duelos (perdia o 1x1 e parava com falta)", "; ".join(ev2) or "duelos equilibrados"))
    # H3: placar
    ev3 = []
    if st["lead"][o] >= 20:
        ev3.append(f"{g.pt(t)} passou ~{st['lead'][o]:.0f} min atrás no placar, pressionando")
    hyps.append((len(ev3) * 2 if ev3 else 0, "Estado do jogo: atrás no placar, subiu a marcação e o choque aumentou",
                 "; ".join(ev3) or "não passou muito tempo atrás"))
    # H4: pressão alta
    ev4 = []
    if g.has("tackles_won") and g.v("tackles_won", t) > g.v("tackles_won", o):
        ev4.append(f"mais desarmes ({fmt(g.v('tackles_won', t), 0)} × {fmt(g.v('tackles_won', o), 0)})")
    if g.has("interceptions") and g.v("interceptions", t) > g.v("interceptions", o):
        ev4.append("mais interceptações")
    hyps.append((len(ev4), "Marcação agressiva / pressão alta (mais contato, mais falta)", "; ".join(ev4) or "sem sinal de marcação mais agressiva"))
    reds = [r for r in st["reds"] if r.get("team") == o]
    if reds:
        hyps.append((1, f"Jogou contra um a menos e o rival ({g.pt(o)}) recuou — mas aqui quem fez mais falta foi {g.pt(t)}", "expulsão no jogo"))
    hyps.sort(key=lambda h: -h[0])
    lines = [f"{i}. **{h[1]}** — evidência: {h[2]}." for i, h in enumerate(hyps, 1)]
    lines.append(f"{len(hyps) + 1}. **Critério do árbitro** — não medível com estes dados (a fonte não traz o lance de cada falta).")
    direct = f"{g.n(t)} fez mais faltas ({fmt(lead[1], 0)} × {fmt(lead[2], 0)}). A explicação mais provável, pela evidência, é: {hyps[0][1].lower()}."
    tp = _top_players(g, "foulsCommitted", "Quem mais fez falta")
    out = _block(direct, nums, [tp] if tp else [], None, _state_line(g, st))
    return out + "\n\n**Hipóteses, da mais para a menos provável:**\n" + "\n".join(lines) + \
        "\n\n_Limite: sem o local de cada falta, isto é hipótese ordenada pela evidência, não certeza._"


def r_defensive(g: Game, q: str, focus: str) -> Answer:
    if not (g.has("tackles_won") or g.has("interceptions")):
        return None
    nums = [_pair(g, "tackles_won", "Desarmes certos", dec=0), _pair(g, "interceptions", "Interceptações", dec=0),
            _pair(g, "clearances", "Cortes", dec=0), _pair(g, "possession_pct", "Posse", "%", 0)]
    reading = []
    if g.has("tackles_won") and g.has("interceptions"):
        for t in g.teams:
            tk, it = g.v("tackles_won", t), g.v("interceptions", t)
            style = ("mais interceptação: defendeu lendo o passe, posicionado (bloco que fecha linhas)" if it > tk * 1.2 else
                     "mais desarme: defendeu indo no corpo a corpo (pressão no portador)" if tk > it * 1.2 else
                     "equilíbrio entre ler o passe e ir no duelo")
            reading.append(f"{g.pt(t)} — {fmt(tk, 0)} desarmes × {fmt(it, 0)} interceptações: {style}.")
    if g.has("possession_pct"):
        for t in g.teams:
            opp_pos = g.v("possession_pct", g.other(t))
            acts = (g.v("tackles_won", t) or 0) + (g.v("interceptions", t) or 0)
            if opp_pos:
                reading.append(f"{g.pt(t)} fez {fmt(acts / (opp_pos / 10), 1)} ações (desarme + interceptação) a cada 10% de "
                               f"posse do rival — compara a intensidade sem o viés de quem defendeu mais tempo.")
    for key, lab in (("matchstats.headers.tackles", "Quem mais desarmou"), ("interceptions", "Quem mais interceptou")):
        tp = _top_players(g, key, lab)
        if tp:
            reading.append(tp)
    lead = _leader(g, "tackles_won") or _leader(g, "interceptions")
    direct = ("quem defende mais tempo faz mais desarme e interceptação; por isso o número cru engana. " +
              (f"{g.n(lead[0])} teve mais ações defensivas." if lead else "Os dois ficaram parecidos."))
    return _block(direct, nums, reading, "sem coordenadas não dá para saber a altura das ações (se a recuperação foi "
                  "no campo de ataque, sinal de pressão alta).")


def r_aerial(g: Game, q: str, focus: str) -> Answer:
    if not g.has("aerials_won"):
        return None
    pc = g.pct.get("aerials_won") or {}
    lead = _leader(g, "aerials_won")
    nums = [_pair(g, "aerials_won", "Duelos aéreos ganhos", dec=0), _pair(g, "long_balls_accurate", "Bolas longas certas", dec=0),
            _pair(g, "crosses_accurate", "Cruzamentos certos", dec=0), _pair(g, "clearances", "Cortes", dec=0)]
    direct = (f"{g.n(lead[0])} dominou o alto ({fmt(lead[1], 0)} × {fmt(lead[2], 0)}"
              + (f", {pc.get(lead[0]):.0f}% dos duelos" if pc.get(lead[0]) else "") + ")." if lead else "jogo aéreo equilibrado.")
    reading = []
    p = g.players
    if not p.empty and "aerials_won" in p:
        top = p.assign(a=pd.to_numeric(p["aerials_won"], errors="coerce"),
                       tot=pd.to_numeric(p.get("aerials_won_total"), errors="coerce")).dropna(subset=["a"])
        top = top[top["a"] > 0].sort_values("a", ascending=False).head(3)
        if not top.empty:
            reading.append("Quem mais ganhou no alto: " + "; ".join(
                f"{r.player} ({g.pt(r.team)}) {fmt(r.a, 0)}" + (f" de {fmt(r.tot, 0)}" if r.tot == r.tot else "") for r in top.itertuples()) + ".")
    if lead and g.has("long_balls_accurate"):
        lb = _leader(g, "long_balls_accurate")
        if lb and lb[0] == g.other(lead[0]):
            reading.append(f"{g.pt(lb[0])} insistiu na bola longa contra quem ganha no alto — escolha ruim para este jogo.")
    return _block(direct, nums, reading, "duelo aéreo inclui disputa de bola parada, cruzamento e tiro de meta — a fonte não separa.")


def _lines(formation: str) -> List[int]:
    return [int(x) for x in re.findall(r"\d", formation or "")]


def formation_of(g: Game, team: str) -> Optional[str]:
    lu = g.lineups
    if lu is None or lu.empty or "formation" not in lu:
        return None
    f = lu.loc[lu["team_name"] == team, "formation"].dropna().astype(str)
    f = f[f.str.match(r"^\d(-\d){2,4}$")]
    return f.mode().iloc[0] if not f.empty else None


def _shape(fm: str) -> Dict[str, Any]:
    ln = _lines(fm)
    if not ln:
        return {}
    back = ln[0]
    wide_mid = back == 3 and len(ln) >= 3 and ln[1] >= 4           # alas no meio (3-4-x / 3-5-x)
    front = ln[-1]
    wingers = 2 if (len(ln) >= 3 and ln[-2] == 3 and back == 4 and front == 1) or (front == 3 and back == 4) else 0
    mids = ln[1:-1]
    central_mid = (mids[0] - 2 if wide_mid else mids[0]) + sum(mids[1:]) if mids else 0
    if back == 4 and len(ln) >= 4 and ln[-2] == 3 and front == 1:
        central_mid -= 2                     # 4-2-3-1: os dois do lado da linha de 3 são pontas
    return {"back": back, "central": central_mid, "front": front, "wide": "alas" if back == 3 else "laterais",
            "wingers": wingers, "lines": ln}


def r_formation(g: Game, q: str, focus: str) -> Answer:
    asked = re.findall(r"\b\d-\d-\d(?:-\d)?\b", q)
    fms = {t: formation_of(g, t) for t in g.teams}
    hypothetical = False
    if len(asked) >= 2 and (not all(fms.values()) or set(asked[:2]) != set(fms.values())):
        # o usuário pergunta por desenhos que não são os informados no jogo → teoria do confronto entre os dois desenhos
        pair, hypothetical = {g.home: asked[0], g.away: asked[1]}, True
    else:
        pair = fms
    if not all(pair.values()):
        return ("**Resposta direta:** a fonte não informou o desenho tático dos dois times neste jogo, então não dá para "
                "comparar formações sem inventar.")
    a, b = g.teams
    sa, sb = _shape(pair[a]), _shape(pair[b])
    if not sa or not sb:
        return None
    nums = [f"{g.pt(a)}: {pair[a]} · {g.pt(b)}: {pair[b]}" + (" (os desenhos da sua pergunta)" if hypothetical else
                                                              " (desenho de saída informado pela fonte)")]
    if hypothetical and all(fms.values()):
        nums.append(f"No jogo, a fonte registrou {g.pt(a)} no {fms[a]} e {g.pt(b)} no {fms[b]}.")
    reading = []
    if sa["lines"] == sb["lines"]:
        reading.append("Desenhos iguais (espelhados): cada jogador tem um adversário direto, então o jogo se decide nos "
                       "duelos individuais e em quem sai da sua posição para criar superioridade."
                       + (f" Duelos ganhos: {g.pt(a)} {fmt(g.v('duels_won', a), 0)} × {fmt(g.v('duels_won', b), 0)} {g.pt(b)}."
                          if g.has("duels_won") else ""))
    if sa["central"] != sb["central"]:
        more = a if sa["central"] > sb["central"] else b
        reading.append(f"Meio-campo por dentro: {g.pt(more)} tem {max(sa['central'], sb['central'])} jogadores centrais contra "
                       f"{min(sa['central'], sb['central'])} — tende a ganhar a superioridade no meio e circular por dentro.")
    for t, s, so in ((a, sa, sb), (b, sb, sa)):
        if s["back"] == 3 and so["back"] == 4 and so["wingers"]:
            reading.append(f"Pelos lados, o ala de {g.pt(t)} fica sozinho contra lateral + ponta de {g.pt(g.other(t))} (2 contra 1) "
                           f"— se o ponta não volta, o zagueiro do lado precisa sair na cobertura.")
        if s["back"] == 3 and so["front"] <= 2:
            reading.append(f"Os 3 zagueiros de {g.pt(t)} contra {so['front']} atacante(s) dão sobra atrás: um zagueiro pode "
                           f"sair jogando ou avançar para o meio.")
    if g.has("crosses_accurate") or g.extra.get("zonas_ataque"):
        z = (g.extra.get("zonas_ataque") or {})
        for side, t in (("home", g.home), ("away", g.away)):
            tot = ((z.get(side) or {}).get("total") or {})
            if tot:
                reading.append(f"Como {g.pt(t)} atacou de fato (FotMob): esquerda {tot.get('left')}% · meio {tot.get('center')}% · "
                               f"direita {tot.get('right')}%.")
    direct = (f"{g.pt(a)} no {pair[a]} contra {g.pt(b)} no {pair[b]}. Pela teoria do desenho, as zonas que decidem são o "
              f"meio (quantos jogam por dentro) e os lados (quem fica 2 contra 1).")
    return _block(direct, nums, reading, "o desenho é o de saída informado pela fonte; durante o jogo ele muda (ataque × "
                  "defesa) e sem lances com coordenadas não dá para medir as linhas reais — a leitura acima é teoria do "
                  "desenho conferida pelos corredores de ataque.")


def _momentum_window(g: Game, team: str, a: float, b: float) -> Optional[float]:
    mom, times = (g.extra or {}).get("momentum") or [], (g.extra or {}).get("times") or []
    if not mom or not times:
        return None
    sign = 1 if _fold(times[0]) == _fold(team) else -1
    vals = [v for m, v in mom if a <= m < b]
    return sign * float(np.mean(vals)) if len(vals) >= 3 else None


def _xg_window(g: Game, team: str, a: float, b: float) -> Optional[float]:
    s = g.shots
    if s is None or s.empty or "xg" not in s:
        return None
    m = pd.to_numeric(s["minute"], errors="coerce")
    return float(pd.to_numeric(s.loc[(s["team_name"] == team) & (m >= a) & (m < b), "xg"], errors="coerce").sum())


def r_subs(g: Game, q: str, focus: str) -> Answer:
    subs = [e for e in g.timeline if e.get("type") == "Substitution"]
    if not subs:
        return "**Resposta direta:** a fonte não registrou as substituições deste jogo — não dá para avaliar as trocas."
    lines = []
    for t in g.teams:
        mine = sorted([e for e in subs if e.get("team") == t], key=lambda e: _f(e.get("minute")) or 999)
        if not mine:
            continue
        txt = "; ".join(f"{minute(e.get('minute')) or 'minuto não informado'} entra {e.get('player') or '—'}"
                        + (f", sai {e.get('related')}" if e.get("related") else "") for e in mine)
        lines.append(f"{g.pt(t)}: {txt}.")
    reading = []
    for t in g.teams:
        mine = [e for e in subs if e.get("team") == t and _f(e.get("minute")) is not None]
        if not mine:
            continue
        m0 = min(_f(e["minute"]) for e in mine)
        before_m, after_m = _momentum_window(g, t, max(0, m0 - 15), m0), _momentum_window(g, t, m0, m0 + 15)
        bx, ax = _xg_window(g, t, max(0, m0 - 15), m0), _xg_window(g, t, m0, min(95, m0 + 15))
        bits = []
        if before_m is not None and after_m is not None:
            bits.append(f"pressão (momentum da FotMob) {before_m:+.0f} nos 15 min antes → {after_m:+.0f} nos 15 depois")
        if bx is not None and ax is not None:
            bits.append(f"xG {fmt(bx)} → {fmt(ax)}")
        gl = [e for e in g.timeline if e.get("type") == "Goal" and e.get("team") == t and (_f(e.get("minute")) or 0) >= m0]
        if gl:
            bits.append(f"{len(gl)} gol(s) depois da 1ª troca")
        if bits:
            reading.append(f"{g.pt(t)} a partir da 1ª troca ({minute(m0)}): " + "; ".join(bits) + ".")
    return _block("estas foram as mudanças e o que aconteceu depois delas.", lines, reading,
                  "o que muda depois de uma troca é ASSOCIAÇÃO, não prova de que a troca causou: o placar, o cansaço e o "
                  "rival também mudam no mesmo período.")


def r_deserved(g: Game, q: str, focus: str) -> Answer:
    if not g.has("xg") and not g.has("shots_on_target"):
        return None
    st = game_state(g)
    nums = [f"Placar: {g.score()}", _pair(g, "xg", "xG"), _pair(g, "big_chances", "Grandes chances", dec=0),
            _pair(g, "shots_on_target", "No gol", dec=0), _pair(g, "xgot", "xGOT")]
    wp = win_probabilities(g)
    signals = [k for k in ("xg", "big_chances", "shots_on_target", "xgot", "touches_opp_box") if g.has(k)]
    sc = {t: sum(1 for k in signals if g.v(k, t) > g.v(k, g.other(t))) for t in g.teams}
    better = max(g.teams, key=lambda t: sc[t]) if sc[g.home] != sc[g.away] else None
    w = g.winner
    if wp:
        pw = {g.home: wp["home"], g.away: wp["away"]}
        if w:
            direct = (f"pelas chances criadas, {g.pt(w)} vencia {100 * pw[w]:.0f}% das vezes, o rival {100 * pw[g.other(w)]:.0f}% "
                      f"e o empate {100 * wp['draw']:.0f}%. ")
            direct += ("Vitória justa pelas chances." if pw[w] >= 0.5 else
                       "Resultado dentro do possível, mas não o mais provável." if pw[w] >= 0.3 else
                       "Pelas chances, a vitória foi acima do que o jogo mostrou.")
        else:
            direct = (f"empate com {g.pt(g.home)} vencendo {100 * wp['home']:.0f}% e {g.pt(g.away)} {100 * wp['away']:.0f}% das "
                      f"simulações pelas chances.")
    else:
        direct = (f"pelos indicadores de chance, {g.n(better)} foi superior ({sc[better]} de {len(signals)})." if better else
                  "pelos indicadores de chance, o jogo foi equilibrado.")
        if w and better and better != w:
            direct += f" Mesmo assim, quem venceu foi {g.pt(w)}."
    reading = []
    if signals:
        reading.append("Indicadores de chance (xG, grandes chances, no gol, xGOT, toques na área): "
                       + " × ".join(f"{g.pt(t)} {sc[t]}" for t in g.teams) + ".")
    for r in st["reds"]:
        reading.append(f"A expulsão de {g.pt(r.get('team') or '')} ({minute(r.get('minute'))}) muda a leitura: depois dela, "
                       f"parte dos números reflete jogar com um a mais.")
    return _block(direct, nums, reading, "“merecer” aqui é medido pelas chances (xG de cada chute somado e simulado); não "
                  "inclui contexto de arbitragem nem o que não virou chute.", _state_line(g, st))


def r_no_score(g: Game, q: str, focus: str) -> Answer:
    keys = [("xg", "xG"), ("big_chances", "grandes chances"), ("shots_on_target", "chutes no gol"),
            ("touches_opp_box", "toques na área rival"), ("passes_opp_half", "passes no campo de ataque"),
            ("possession_pct", "posse"), ("corners", "escanteios"), ("aerials_won", "aéreos ganhos"), ("duels_won", "duelos ganhos")]
    keys = [(k, l) for k, l in keys if g.has(k)]
    if not keys:
        return None
    weight = {"xg": 3, "big_chances": 2, "shots_on_target": 2, "touches_opp_box": 1.5}
    pts = {t: 0.0 for t in g.teams}
    rows = []
    for k, l in keys:
        a, b = g.v(k, g.home), g.v(k, g.away)
        if a != b:
            pts[g.home if a > b else g.away] += weight.get(k, 1)
        rows.append(f"{l}: {g.pt(g.home)} {fmt(a)} × {fmt(b)} {g.pt(g.away)}")
    best = max(g.teams, key=lambda t: pts[t])
    tie = pts[g.home] == pts[g.away]
    direct = ("sem olhar o placar, o jogo fica equilibrado pelos números." if tie else
              f"sem olhar o placar, {g.n(best)} foi melhor: levou {pts[best]:.0f} de {sum(pts.values()):.0f} pontos de indicadores "
              f"(chance pesa mais que posse).")
    reading = []
    w = g.winner
    if w and not tie and w != best:
        reading.append(f"O placar foi para o outro lado ({g.score()}) — eficiência, goleiro ou um lance isolado decidiram.")
    elif w and not tie:
        reading.append(f"O placar ({g.score()}) confirma a leitura dos números.")
    return _block(direct, rows, reading, "pesos: xG 3, grandes chances 2, chutes no gol 2, toques na área 1,5, demais 1 — "
                  "critério do laboratório, explicado aqui para você poder discordar.")


def r_contradictions(g: Game, q: str, focus: str) -> Answer:
    found = []
    for t in g.teams:
        o = g.other(t)
        if g.has("possession_pct") and g.has("xg") and g.v("possession_pct", t) > 55 and g.v("xg", t) < g.v("xg", o):
            found.append(f"{g.pt(t)} teve {fmt(g.v('possession_pct', t), 0)}% de posse e MENOS xG ({fmt(g.v('xg', t))} × "
                         f"{fmt(g.v('xg', o))}) → posse sem profundidade; o rival defendeu bem e atacou melhor quando teve a bola.")
        if g.has("shots_total") and g.has("xg") and g.v("shots_total", t) > g.v("shots_total", o) and g.v("xg", t) < g.v("xg", o):
            found.append(f"{g.pt(t)} chutou mais ({fmt(g.v('shots_total', t), 0)} × {fmt(g.v('shots_total', o), 0)}) e criou "
                         f"menos perigo → volume de chute ruim (longe, bloqueado).")
        if g.has("xg") and g.goals(t) is not None and g.goals(o) is not None and g.v("xg", t) > g.v("xg", o) + 0.5 \
                and g.goals(t) < g.goals(o):
            found.append(f"{g.pt(t)} criou mais (xG {fmt(g.v('xg', t))} × {fmt(g.v('xg', o))}) e perdeu → finalização e "
                         f"goleiros decidiram, não o volume de jogo.")
        if g.has("corners") and g.has("xg_set_play") and g.v("corners", t) >= g.v("corners", o) + 3 and \
                g.v("xg_set_play", t) <= g.v("xg_set_play", o):
            found.append(f"{g.pt(t)} teve mais escanteios e menos perigo de bola parada → escanteio não virou chance.")
        if g.has("pass_accuracy_pct") and g.has("passes_opp_half") and g.v("pass_accuracy_pct", t) > g.v("pass_accuracy_pct", o) \
                and g.v("passes_opp_half", t) < g.v("passes_opp_half", o):
            found.append(f"{g.pt(t)} errou menos passes mas jogou menos no campo de ataque → precisão vinda de passe seguro, atrás.")
    if not found:
        return ("**Resposta direta:** não achei números que se contradizem neste jogo — posse, chutes, qualidade das "
                "chances e placar apontam na mesma direção.")
    return "**Resposta direta:** há sinais que parecem se contradizer — e cada um tem explicação:\n\n" + _bullets(found)


def r_causality(g: Game, q: str, focus: str) -> Answer:
    st = game_state(g)
    ex = []
    lead_pos = _leader(g, "possession_pct")
    if lead_pos and g.winner and lead_pos[0] != g.winner:
        ex.append(f"{g.pt(lead_pos[0])} teve mais posse e perdeu — isso NÃO quer dizer que a posse fez perder. Causa comum "
                  f"provável: o placar (quem está na frente entrega a bola) "
                  + (f"— {g.pt(g.winner)} ficou ~{st['lead'][g.winner]:.0f} min na frente." if st["lead"].get(g.winner, 0) >= 15 else "."))
    if [e for e in g.timeline if e.get("type") == "Substitution"]:
        ex.append("Melhora depois de uma substituição é associação: no mesmo período o rival cansa, o placar muda e o "
                  "técnico rival também mexe.")
    if g.has("fouls"):
        ex.append("Mais faltas e mais cartões andam juntos, mas não dá para dizer que um time foi 'violento': o critério do "
                  "árbitro e o tipo de jogo (transições do rival) entram no meio.")
    ex.append("Para chegar perto de causa é preciso repetição: o mesmo padrão em vários jogos do time, com e sem o fator "
              "(ex.: com e sem o jogador, com e sem posse) — um jogo isolado mostra só associação.")
    return ("**Resposta direta:** neste jogo os números mostram associações; nenhum deles, sozinho, prova causa.\n\n"
            + _bullets(ex) + ("\n\n" + _state_line(g, st) if _state_line(g, st) else ""))


def r_misreadings(g: Game, q: str, focus: str) -> Answer:
    tips = []
    if g.has("possession_pct"):
        tips.append(f"**Posse = domínio?** {g.pt(max(g.teams, key=lambda t: g.v('possession_pct', t)))} teve mais bola, mas o "
                    f"domínio se mede nas chances (xG, área, grandes chances).")
    if g.has("shots_total"):
        tips.append("**Mais chutes = mais perigo?** Só se forem de dentro da área; olhe o xG por chute.")
    if g.has("xg"):
        tips.append("**xG de um jogo como verdade?** É ruído: duas ou três chances mudam tudo. Serve para dizer o que era mais "
                    "provável, não o que 'devia' acontecer.")
    if g.has("pass_accuracy_pct"):
        tips.append("**Precisão de passe alta = time melhor?** Passe lateral não erra; precisão sem passe no campo de ataque é segurança.")
    if g.has("tackles_won"):
        tips.append("**Muitos desarmes = defesa boa?** Muitas vezes significa que o time defendeu muito tempo; compare pela posse do rival.")
    if g.has("corners"):
        tips.append("**Escanteios = chances?** Escanteio é pressão territorial; poucos viram finalização perigosa.")
    tips.append("**O placar explica tudo?** Quem está na frente muda o jeito de jogar; números de um time que ficou muito "
                "tempo atrás vêm inflados de posse e chute.")
    return "**Resposta direta:** os erros de leitura mais comuns, aplicados a este jogo:\n\n" + _bullets(tips)


def r_missing(g: Game, q: str, focus: str) -> Answer:
    has = [k for k in ("possession_pct", "xg", "xgot", "big_chances", "shots_inside_box", "passes_opp_half", "touches_opp_box",
                       "long_balls_accurate", "crosses_accurate", "aerials_won", "tackles_won", "interceptions", "fouls")
           if g.has(k)]
    from src.intelligence.lab_ai.facts import KEY_META

    measured = ", ".join(KEY_META.get(k, (k,))[0] for k in has) or "quase nada além do placar"
    missing = []
    if not g.has_events:
        missing += ["posição de cada passe e de cada recuperação (sem lances com coordenadas)", "pressão real (PPDA medido)",
                    "rede de passes e quem quebrou linhas no time todo", "altura da linha defensiva"]
    missing += ["distância percorrida e sprints (só em ligas com dado físico)", "o que o técnico pediu (intenção tática)",
                "lances sem a bola (movimentação, coberturas) — exigem vídeo ou rastreamento"]
    if g.shots is None or g.shots.empty:
        missing.append("mapa de chutes (sem xG por finalização, não dá para simular o resultado)")
    return (f"**Resposta direta:** este jogo tem {('lances com coordenadas' if g.has_events else 'estatísticas da partida')} "
            f"da fonte {g.meta.get('data_source') or '—'}.\n\n**Medido:** {measured}.\n\n**Não medido (não invento):**\n"
            + _bullets(missing))


def r_risk(g: Game, q: str, focus: str) -> Answer:
    team = focus if focus in g.teams else (g.winner or g.home)
    o = g.other(team)
    risks: List[Tuple[int, str]] = []
    s = g.shots
    if s is not None and not s.empty and "xg" in s:
        m = pd.to_numeric(s["minute"], errors="coerce")
        xg_o = pd.to_numeric(s["xg"], errors="coerce")
        late = float(xg_o[(s["team_name"] == o) & (m >= 70)].sum())
        tot = float(xg_o[s["team_name"] == o].sum())
        if tot > 0 and late / tot >= 0.45:
            risks.append((3, f"cedeu {100 * late / tot:.0f}% das chances do rival nos últimos 20 minutos (xG {fmt(late)}) — "
                             f"o time recua e passa a viver de sorte no fim"))
    if g.has("big_chances") and g.v("big_chances", o) >= 3:
        risks.append((3, f"permitiu {fmt(g.v('big_chances', o), 0)} grandes chances"))
    if g.has("xgot") and g.goals(o) is not None and g.v("xgot", o) - g.goals(o) >= 0.8:
        risks.append((2, f"o goleiro segurou ~{fmt(g.v('xgot', o) - g.goals(o), 1)} gol(s) acima do esperado — difícil repetir"))
    if g.has("yellow_cards") and g.v("yellow_cards", team) >= 4:
        risks.append((2, f"{fmt(g.v('yellow_cards', team), 0)} amarelos — risco de expulsão e de suspensão"))
    if g.has("xg_set_play") and g.v("xg_set_play", o) >= 0.5:
        risks.append((2, f"sofreu {fmt(g.v('xg_set_play', o))} de xG em bola parada"))
    p = g.players
    if not p.empty and "chances_created" in p:
        cc = p[p["team"] == team].assign(c=pd.to_numeric(p["chances_created"], errors="coerce")).dropna(subset=["c"])
        if cc["c"].sum() >= 5 and cc["c"].max() / cc["c"].sum() >= 0.45:
            top = cc.sort_values("c", ascending=False).iloc[0]
            risks.append((1, f"dependência de um criador: {top.player} fez {fmt(top.c, 0)} de {fmt(cc['c'].sum(), 0)} chances"))
    if g.has("possession_pct") and g.v("possession_pct", o) >= 60:
        risks.append((1, f"passou o jogo sem a bola ({fmt(g.v('possession_pct', team), 0)}% de posse) — depende de defender "
                         f"bem por muito tempo e de acertar os contra-ataques"))
    if g.has("shots_total") and g.v("shots_total", o) >= 14:
        risks.append((1, f"cedeu {fmt(g.v('shots_total', o), 0)} finalizações"))
    if g.has("aerials_won") and g.v("aerials_won", o) >= 1.4 * max(1.0, g.v("aerials_won", team)):
        risks.append((1, f"perdeu o jogo aéreo ({fmt(g.v('aerials_won', team), 0)} × {fmt(g.v('aerials_won', o), 0)}) — "
                         f"cruzamento e bola parada contra são o ponto sensível"))
    if g.goals(team) is not None and g.goals(o) is not None and g.goals(team) - g.goals(o) == 1 and g.has("xg") \
            and abs(g.v("xg", team) - g.v("xg", o)) < 0.4:
        risks.append((2, "venceu por um gol com chances parecidas às do rival (xG "
                         f"{fmt(g.v('xg', team))} × {fmt(g.v('xg', o))}) — vitória que pode virar empate com pouco"))
    if not risks:
        return (f"**Resposta direta:** não vejo risco alto para {g.pt(team)} nos números deste jogo — chances cedidas, "
                f"bola parada e cartões dentro do normal.")
    risks.sort(key=lambda r: -r[0])
    level = "alto" if risks[0][0] >= 3 else "médio" if risks[0][0] == 2 else "baixo, com pontos de atenção"
    return (f"**Resposta direta:** risco {level} para {g.pt(team)}. O que pesa, do mais grave para o menos:\n\n"
            + "\n".join(f"{i}. {r[1]}." for i, r in enumerate(risks, 1))
            + "\n\n_Limite: risco aqui é o que se repetiria se o próximo jogo fosse parecido; num jogo só, é sinal, não padrão._")


def r_state(g: Game, q: str, focus: str) -> Answer:
    st = game_state(g)
    line = _state_line(g, st)
    if not line:
        return None
    reading = []
    for r in st["reds"]:
        rm = _f(r.get("minute"))
        if rm is None:
            continue
        t = r.get("team")
        for tm in g.teams:
            b, a = _xg_window(g, tm, 0, rm), _xg_window(g, tm, rm, 100)
            if b is not None and a is not None:
                reading.append(f"{g.pt(tm)}: xG {fmt(b)} antes da expulsão ({fmt(b / max(rm, 1) * 10)} a cada 10 min) → "
                               f"{fmt(a)} depois ({fmt(a / max(95 - rm, 1) * 10)} a cada 10 min).")
        reading.append(f"Com um a menos, {g.pt(t)} costuma abrir mão da bola e se fechar — a posse e os chutes do rival "
                       f"depois do minuto {int(rm)} vêm inflados por isso.")
    goals = st["goals"]
    if goals:
        reading.append("Gols: " + "; ".join(f"{minute(e['minute'])} {e.get('player') or 'autor não informado'} ({g.pt(e.get('team') or '')})"
                                           for e in goals) + ".")
    return "**Resposta direta:** " + line.replace("**Estado do jogo:** ", "") + ("\n\n**Leitura:**\n" + _bullets(reading) if reading else "")


def _window_stats(g: Game, a: float, b: float) -> Dict[str, Dict[str, float]]:
    """Chutes, xG e pressão (momentum) de cada time entre os minutos a e b."""
    out: Dict[str, Dict[str, float]] = {}
    s = g.shots
    for t in g.teams:
        d: Dict[str, float] = {}
        if s is not None and not s.empty:
            m = pd.to_numeric(s["minute"], errors="coerce")
            part = s[(s["team_name"] == t) & (m >= a) & (m < b)]
            d["chutes"] = float(len(part))
            if "xg" in part:
                d["xg"] = float(pd.to_numeric(part["xg"], errors="coerce").sum())
        mo = _momentum_window(g, t, a, b)
        if mo is not None:
            d["pressao"] = mo
        out[t] = d
    return out


def _fmt_window(g: Game, w: Dict[str, Dict[str, float]]) -> str:
    bits = []
    for t in g.teams:
        d = w.get(t) or {}
        if not d:
            continue
        txt = f"{g.pt(t)} {fmt(d.get('chutes'), 0)} chute(s)" if "chutes" in d else g.pt(t)
        if "xg" in d:
            txt += f" (xG {fmt(d['xg'])})"
        bits.append(txt)
    p = {t: (w.get(t) or {}).get("pressao") for t in g.teams}
    dom = [t for t in g.teams if p.get(t) is not None and p[t] > 15]
    tail = f"; quem pressionava: {g.pt(dom[0])}" if dom else ""
    return " × ".join(bits) + tail if bits else ""


def r_story(g: Game, q: str, focus: str) -> Answer:
    """A HISTÓRIA do jogo trecho a trecho: entre um gol e outro, quem chutou, com que perigo e quem pressionava —
    responde 'por que virou', 'por que saiu atrás', 'por que os gols saíram tão rápido', 'onde virou'."""
    st = game_state(g)
    goals = st["goals"]
    if not goals:
        return None
    marks = [0.0] + [float(_f(e["minute"])) for e in goals] + [95.0]
    lines = []
    sh = sa = 0
    for i, e in enumerate(goals):
        a, b = marks[i], marks[i + 1]
        w = _window_stats(g, a, b)
        win = _fmt_window(g, w)
        if e.get("team") == g.home:
            sh += 1
        else:
            sa += 1
        lines.append(f"**{minute(e['minute'])} gol de {g.pt(e.get('team') or '')}** ({e.get('player') or 'autor não informado'}) "
                     f"→ {fmt(sh, 0)} x {fmt(sa, 0)}" + (f". Antes dele ({int(a)}'–{int(b)}'): {win}" if win else ""))
    w_end = _window_stats(g, marks[-2], 95)
    end = _fmt_window(g, w_end)
    if end:
        lines.append(f"Depois do último gol ({int(marks[-2])}' ao fim): {end}")
    reading = []
    early = [e for e in goals if (_f(e["minute"]) or 99) <= 15]
    if len(early) >= 2:
        reading.append(f"Dois gols nos primeiros 15 minutos: o time que levou ainda não tinha se organizado sem a bola — "
                       f"gol cedo costuma vir de bola parada, erro na saída ou transição rápida; a fonte não traz o tipo de "
                       f"jogada de cada gol, só o minuto e o autor.")
    if len(goals) >= 2 and len(early) < 2:
        gap = (_f(goals[1]["minute"]) or 0) - (_f(goals[0]["minute"]) or 0)
        if 0 <= gap <= 10:
            reading.append(f"Os dois primeiros gols saíram com {gap:.0f} min de diferença: logo depois de um gol o time que "
                           f"marcou relaxa ou o que sofreu se lança — os minutos seguintes a um gol são os mais abertos do jogo.")
    s = g.shots
    if s is not None and not s.empty and "situation" in s and (early or len(goals) >= 2):
        early = early or goals[:2]
        for e in early:
            m = pd.to_numeric(s["minute"], errors="coerce")
            hit = s[(s["team_name"] == e.get("team")) & ((m - (_f(e["minute"]) or 0)).abs() <= 1)
                    & s["outcome"].astype(str).str.contains("Goal", case=False)]
            if len(hit):
                r = hit.iloc[0]
                reading.append(f"Gol dos {minute(e['minute'])}: {SIT.get(str(r.get('situation')), str(r.get('situation')))}, "
                               f"xG {fmt(r.get('xg'))} ({'chance clara' if (_f(r.get('xg')) or 0) >= .3 else 'chance difícil'}).")
    # virada
    first = goals[0]["team"]
    w = g.winner
    if w and first and w != first:
        reading.append(f"{g.pt(w)} saiu atrás e virou: depois do 1º gol, quem precisava do resultado ficou com a bola "
                       f"e foi empurrando o rival para trás — veja o volume de chutes de cada trecho acima.")
        if g.has("possession_pct") and g.has("shots_total"):
            reading.append(f"No jogo todo: {g.pt(w)} {fmt(g.v('possession_pct', w), 0)}% de posse e {fmt(g.v('shots_total', w), 0)} "
                           f"chutes contra {fmt(g.v('shots_total', g.other(w)), 0)} — a virada veio de insistência, não de um lance isolado.")
    for r in st["reds"]:
        mm = minute(r.get("minute"))
        reading.append(f"Expulsão de {r.get('player') or 'um jogador'} ({g.pt(r.get('team') or '')})"
                       + (f" aos {mm}" if mm else " (a fonte não informou o minuto)") + " — muda o resto do jogo.")
    subs = [e for e in g.timeline if e.get("type") == "Substitution" and _f(e.get("minute")) is not None]
    if subs and w and first and w != first:
        before = [e for e in subs if e.get("team") == w and _f(e["minute"]) <= max(marks[1:-1] or [90])]
        if before:
            reading.append("Trocas de " + g.pt(w) + " antes da reação: " + "; ".join(
                f"{minute(e['minute'])} entra {e.get('player') or '—'}" for e in before[:4]) + " (associação, não prova de causa).")
    z = (g.extra or {}).get("zonas_ataque") or {}
    if z and re.search(r"\bonde\b|lado|corredor|setor", q):
        for side, t in (("home", g.home), ("away", g.away)):
            sh2 = ((z.get(side) or {}).get("secondHalf") or {})
            if sh2:
                reading.append(f"Por onde {g.pt(t)} atacou no 2º tempo (FotMob): esquerda {sh2.get('left')}% · meio "
                               f"{sh2.get('center')}% · direita {sh2.get('right')}%.")
    direct = (f"{g.score()}. " + (f"{g.pt(first)} abriu o placar aos {minute(goals[0]['minute'])}" if first else "")
              + (f" e {g.pt(w)} virou." if w and w != first else "."))
    return _block(direct, lines, reading, "a fonte de estatísticas não traz o lance de cada gol (tipo de jogada, quem "
                  "errou); a leitura usa minuto, autor, chutes/xG por trecho e a pressão (momentum) da FotMob.")


SIT = {"RegularPlay": "jogada trabalhada", "FastBreak": "contra-ataque", "SetPiece": "bola parada",
       "FromCorner": "escanteio", "Penalty": "pênalti", "FreeKick": "falta direta", "ThrowInSetPiece": "lateral"}


def r_advice(g: Game, q: str, focus: str) -> Answer:
    """Conselho ao treinador de um time, tirado dos números deste jogo (o que deixou o rival fazer, o que repetir)."""
    team = focus if focus in g.teams else (g.other(g.winner) if g.winner else g.home)
    o = g.other(team)
    tips: List[Tuple[int, str]] = []
    st = game_state(g)
    if g.has("possession_pct") and g.v("possession_pct", o) >= 62:
        tips.append((3, f"**Não entregar a bola por inteiro:** {g.pt(o)} teve {fmt(g.v('possession_pct', o), 0)}% de posse. "
                        f"Na frente do placar, ter 3–4 passes de saída (goleiro, zagueiros e um volante que se ofereça) "
                        f"tira o rival do campo de ataque por alguns minutos."))
    if g.has("shots_total") and g.v("shots_total", o) >= 15:
        tips.append((3, f"**Defender mais longe da área:** cedeu {fmt(g.v('shots_total', o), 0)} finalizações"
                        + (f" ({fmt(g.v('shots_inside_box', o), 0)} de dentro da área)" if g.has("shots_inside_box") else "")
                        + ". Subir o bloco 5–10 m e encurtar entre linhas reduz o chute dentro da área."))
    if g.has("corners") and g.v("corners", o) >= 7:
        tips.append((2, f"**Bola parada:** {fmt(g.v('corners', o), 0)} escanteios contra — cada corte para a linha de fundo vira "
                        f"um escanteio; marcação mista na área e um homem na entrada para a segunda bola."))
    if g.has("fouls") and g.v("fouls", team) >= 15:
        tips.append((2, f"**Menos faltas:** {fmt(g.v('fouls', team), 0)} faltas"
                        + (f" e {fmt(g.v('yellow_cards', team), 0)} amarelos" if g.has("yellow_cards") else "")
                        + " — com amarelado, o defensor perde o bote; trocar quem está pendurado antes do 60'."))
    if g.has("crosses_accurate") and (g.pct.get("crosses_accurate") or {}).get(o) is not None and g.has("aerials_won") \
            and g.v("aerials_won", o) > g.v("aerials_won", team):
        tips.append((2, f"**Jogo aéreo:** {g.pt(o)} ganhou mais no alto ({fmt(g.v('aerials_won', o), 0)} × "
                        f"{fmt(g.v('aerials_won', team), 0)}) — evitar cruzamento sem pressão no cruzador."))
    w_lead = st["lead"].get(team, 0)
    if w_lead >= 20 and g.winner == o:
        tips.append((3, f"**Gerir a vantagem:** {g.pt(team)} ficou ~{w_lead:.0f} min na frente e perdeu. Troca para fechar "
                        f"(um volante a mais ou um zagueiro) logo depois do gol do rival, não no fim; e manter um atacante "
                        f"rápido para o contra-ataque — sem ameaça na frente o rival sobe todo mundo."))
    if g.has("xg") and g.v("xg", o) >= 2:
        tips.append((2, f"**Chances claras cedidas:** xG {fmt(g.v('xg', o))} do rival — não é azar, é volume de chance boa; o ajuste "
                        f"é na proteção da área (zagueiros não saem do lugar, volantes fecham o corredor central)."))
    if g.has("shots_total") and g.has("xg") and g.v("shots_total", team) >= 10 and \
            g.v("xg", team) / max(g.v("shots_total", team), 1) < .065:
        tips.append((2, f"**Chutar de lugar melhor:** {fmt(g.v('shots_total', team), 0)} finalizações para só {fmt(g.v('xg', team))} "
                        f"de xG — muito chute de fora ou travado. Rodar mais a bola até achar o passe para dentro da área."))
    if g.has("possession_pct") and g.has("xg") and g.v("possession_pct", team) >= 58 and g.v("xg", team) < g.v("xg", o):
        tips.append((3, f"**Posse com mais profundidade:** {fmt(g.v('possession_pct', team), 0)}% de bola e menos xG que o rival "
                        f"({fmt(g.v('xg', team))} × {fmt(g.v('xg', o))}). Mais gente atacando o espaço atrás da linha e "
                        f"menos passe lateral na intermediária."))
    if g.has("shots_on_target") and g.has("shots_total") and g.v("shots_total", o) >= 6 and \
            g.v("shots_on_target", o) / max(g.v("shots_total", o), 1) >= .5:
        tips.append((2, f"**Pressão no chutador:** o rival acertou o gol em {fmt(g.v('shots_on_target', o), 0)} de "
                        f"{fmt(g.v('shots_total', o), 0)} chutes — chegou livre para finalizar; o bote tem que ser antes do chute."))
    if g.has("aerials_won") and g.v("aerials_won", team) >= 1.3 * max(1.0, g.v("aerials_won", o)):
        tips.append((1, f"**Usar o que funcionou:** ganhou o jogo aéreo ({fmt(g.v('aerials_won', team), 0)} × "
                        f"{fmt(g.v('aerials_won', o), 0)}) — mais bola parada ofensiva e cruzamento para a segunda trave."))
    if g.has("shots_total") and g.has("xg") and g.v("shots_total", team) >= 10 and \
            g.v("xg", team) / max(g.v("shots_total", team), 1) < .065:
        tips.append((2, f"**Chutar de lugar melhor:** {fmt(g.v('shots_total', team), 0)} finalizações para só {fmt(g.v('xg', team))} "
                        f"de xG — muito chute de fora ou travado. Rodar mais a bola até achar o passe para dentro da área."))
    if g.has("possession_pct") and g.has("xg") and g.v("possession_pct", team) >= 58 and g.v("xg", team) < g.v("xg", o):
        tips.append((3, f"**Posse com mais profundidade:** {fmt(g.v('possession_pct', team), 0)}% de bola e menos xG que o rival "
                        f"({fmt(g.v('xg', team))} × {fmt(g.v('xg', o))}). Mais gente atacando o espaço atrás da linha e "
                        f"menos passe lateral na intermediária."))
    if g.has("shots_on_target") and g.has("shots_total") and g.v("shots_total", o) >= 6 and \
            g.v("shots_on_target", o) / max(g.v("shots_total", o), 1) >= .5:
        tips.append((2, f"**Pressão no chutador:** o rival acertou o gol em {fmt(g.v('shots_on_target', o), 0)} de "
                        f"{fmt(g.v('shots_total', o), 0)} chutes — chegou livre para finalizar; o bote tem que ser antes do chute."))
    if g.has("aerials_won") and g.v("aerials_won", team) >= 1.3 * max(1.0, g.v("aerials_won", o)):
        tips.append((1, f"**Usar o que funcionou:** ganhou o jogo aéreo ({fmt(g.v('aerials_won', team), 0)} × "
                        f"{fmt(g.v('aerials_won', o), 0)}) — mais bola parada ofensiva e cruzamento para a segunda trave."))
    reds = [r for r in st["reds"] if r.get("team") == o]
    if reds:
        tips.append((1, f"O rival teve expulsão ({reds[0].get('player') or '—'}): com um a mais, acelerar o jogo pelos lados."))
    if not tips:
        return (f"**Resposta direta:** nos números deste jogo não aparece um ponto fraco claro de {g.pt(team)} — o resultado "
                f"saiu de detalhes (eficiência, um lance).")
    tips.sort(key=lambda t: -t[0])
    return (f"**Resposta direta:** para {g.pt(team)}, pelos números deste jogo ({g.score()}), o que eu mudaria:\n\n"
            + "\n".join(f"{i}. {t[1]}" for i, t in enumerate(tips[:5], 1))
            + "\n\n_Limite: conselho pelas estatísticas do jogo (posse, chutes, escanteios, faltas, aéreo, placar); a fonte "
              "não mostra a posição de cada jogador, então ajuste fino de linha e marcação é sugestão, não medição._")


# ------------------------------------------------------------------------------------------------- detecção
TOPICS: List[Tuple[str, str, Callable]] = [
    ("conselho", r"sugest|\bdica|conselh|o que (o |a )?\w* ?(deveria|devia|poderia|precisa)|como (evitar|nao tomar|segurar|"
                 r"impedir|nao sofrer)|para nao (tomar|sofrer|levar)|o que fazer|o que mudar", r_advice),
    ("historia", r"vir(ou|ada|ar)\b|sai(u|r) (na frente|atras|perdendo)|comec\w* perdendo|gols? (tao |muito )?rapid|"
                 r"primeiros? (dois )?gols?|como (sairam|saiu|foram|aconteceram) os gols|por ?que (sofreu|tomou|levou)|"
                 r"reag(iu|ir)|reacao|empatou|onde (o \w+ )?vir", r_story),
    ("risco", r"\brisco|arrisc|vulnerav|corre perigo", r_risk),
    ("contradicao", r"contradi|paradox|nao bate|incoeren|conflit|parece estranho|nao faz sentido", r_contradictions),
    ("causalidade", r"causalidade|correlac|e causa|foi a causa|causou|relacao de causa|causa e efeito", r_causality),
    ("erros_leitura", r"erros? de (interpretac|leitura|analise)|interpret\w* errad|leitura errad|armadilha|engan", r_misreadings),
    ("ausentes", r"ausent|dados? (faltando|que falta|que nao)|lacuna|nao (foi |e )?medid|limitac\w* (dos|de) dados|"
                 r"o que (nao|voce nao) (da|consegue|sabe)", r_missing),
    ("sem_placar", r"sem (olhar|saber|considerar|ver|levar em conta) o (placar|resultado)|ignorando o (placar|resultado)|"
                   r"desconsider\w* o (placar|resultado)|se nao soubesse o (placar|resultado)", r_no_score),
    ("mereceu", r"merec|resultado (foi )?(justo|injusto)|foi justo|justica|injust|refletiu|placar (justo|mentiroso)", r_deserved),
    ("estado", r"vermelho|expuls|um a menos|inferioridade|superioridade numerica|estado do jogo", r_state),
    ("formacao", r"\b\d-\d-\d(-\d)?\b|formac|esquema tatico|sistema tatico|desenho tatico", r_formation),
    ("substituicao", r"substitui\w* (mudaram|mudou|funcion|deram|deu certo|impact|efeito|ajudar|melhor)|"
                     r"(impacto|efeito) das? (substitui|troca|mexida)|as (trocas|mexidas|substituicoes)\b(?!.*sugere)", r_subs),
    ("faltas", r"\bfaltas?\b(?! de\b)(?!ram)|faltoso", r_fouls),
    ("defesa", r"intercept|desarm", r_defensive),
    ("aereo", r"aere|cabec|bola alta|jogo alto", r_aerial),
    ("drible", r"drible|driblou|1x1|um contra um", r_dribbles),
    ("escanteio", r"escanteio|corner|bola parada", r_corners),
    ("cruzamento", r"cruzam|cruzou", r_crosses),
    ("bola_longa", r"bolas? longas?|lancament|ligacao direta|chutao", r_long_balls),
    ("grandes", r"grandes? chances?|chances? clara|chances? de gol", r_big_chances),
    ("bloqueadas", r"bloquead|bloqueio", r_blocked),
    ("area", r"dentro da area|fora da area|de longe|de fora", r_area),
    ("no_gol", r"\bno gol\b|no alvo|na direcao do gol|enquadrad|acert\w* o gol|trabalho ao goleiro|exigiu (do|o) goleiro", r_on_target),
    ("eficiencia", r"eficien|\bxg\b|gols? esperad|aproveit|conver|sorte|azar", r_efficiency),
    ("passes", r"\bpasses?\b|precisao|troca de passe", r_passes),
    ("finalizacoes", r"finaliz|chut|arremat", r_shots),
    ("controle", r"\bposse\b|controle|controlou|dominou|dominio|mandou no jogo|territor", r_control),
]
GENERIC_SHOTS = {"no_gol", "area", "bloqueadas", "grandes", "eficiencia"}
INTERPRETIVE = r"\bpor ?que\b|\bpq\b|indica|significa|explica|interpret|mostra|diz sobre|qualidade|melhor|controle|" \
               r"justo|merec|analis|avali|compar|leitura|hipotes|o que (isso|esse|essa)|como (foi|voce ve|le)|\?"


def detect(question: str) -> List[str]:
    q = " " + re.sub(r"[^a-z0-9\- ]", " ", _fold(question)) + " "
    found = [name for name, pat, _ in TOPICS if re.search(pat, q)]
    if "finalizacoes" in found and GENERIC_SHOTS & set(found):
        found.remove("finalizacoes")
    if "controle" in found and ("passes" in found):
        found.remove("passes")
    if "faltas" in found and re.search(r"o que (faltou|falta)|faltando", q):
        found.remove("faltas")
    return found[:3]


def asks_player_ranking(question: str) -> bool:
    """Pergunta explícita por JOGADOR ("qual jogador mais driblou?") → ranking por jogador (direct.py).
    "Quem driblou mais?" fica aqui: responde pelo time e mostra os jogadores que puxaram o número."""
    q = _fold(question)
    return bool(re.search(r"\bqual jogador\b|\bquais jogadores\b|\bque jogador\b|\bjogador(es)?\b|\batleta", q)) \
        and not re.search(r"qual time|que time|qual equipe", q)


def answer(question: str, meta: Dict[str, Any], df, box, focus: str = "", db=None,
           pt: Callable[[str], str] = lambda x: x) -> Optional[Dict[str, Any]]:
    """Resposta interpretativa ou None (a pergunta não é deste tipo, ou o jogo não tem os números)."""
    topics = detect(question)
    if not topics:
        return None
    single_metric = topics[0] in ("passes", "finalizacoes", "escanteio", "cruzamento", "drible", "aereo", "defesa",
                                  "bola_longa", "faltas", "no_gol", "area", "bloqueadas", "grandes")
    if asks_player_ranking(question) and single_metric and len(topics) == 1:
        return None                         # "quem mais driblou?" → ranking por jogador (direct.py)
    g = build_game(meta, df, box, db, pt)
    if not g.teams:
        return None
    fq = _fold(question)
    # rodada 27i: grafia aproximada também vale ("villareal" = Villarreal): basta o começo da palavra do time
    named = [t for t in g.teams if any(w in fq or (len(w) >= 6 and w[:5] in fq) for w in _fold(t).split() if len(w) >= 4)
             or _fold(pt(t)) in fq]
    focus = named[0] if len(named) == 1 else focus
    fns = {n: fn for n, _, fn in TOPICS}
    parts = []
    for name in topics:
        try:
            md = fns[name](g, fq, focus)
        except Exception as exc:                 # um raciocínio que quebra não derruba a resposta (registro p/ diagnóstico)
            _log_error(name, exc)
            md = None
        if md:
            parts.append((name, md))
    if not parts:
        return None
    src = "lances do jogo" if g.has_events else f"estatísticas da partida ({meta.get('data_source') or 'fonte'})"
    if len(parts) == 1:
        md = parts[0][1]
    else:
        md = "\n\n---\n\n".join(f"#### {_TITLE.get(n, n)}\n\n{m}" for n, m in parts)
    return {"markdown": md + f"\n\n_Fonte: {src}; {g.score()}._", "intent": "raciocinio:" + "+".join(n for n, _ in parts)}


def _log_error(name: str, exc: Exception) -> None:
    try:
        import traceback
        from pathlib import Path

        Path("data/learning").mkdir(parents=True, exist_ok=True)
        with open("data/learning/lab_ai_erros.log", "a", encoding="utf-8") as fh:
            fh.write(f"raciocinio {name}: " + traceback.format_exc()[-1500:] + "\n")
    except Exception:
        pass


_TITLE = {"conselho": "Conselho ao treinador", "historia": "A história do jogo", "risco": "Risco", "contradicao": "Números que parecem se contradizer", "causalidade": "Correlação × causa",
          "erros_leitura": "Erros de interpretação", "ausentes": "Dados ausentes", "sem_placar": "Sem olhar o placar",
          "mereceu": "Quem mereceu", "estado": "Estado do jogo", "formacao": "Formações", "substituicao": "Substituições",
          "faltas": "Faltas", "defesa": "Desarmes × interceptações", "aereo": "Jogo aéreo", "drible": "Dribles",
          "escanteio": "Escanteios", "cruzamento": "Cruzamentos", "bola_longa": "Bolas longas", "grandes": "Grandes chances",
          "bloqueadas": "Finalizações bloqueadas", "area": "Dentro × fora da área", "no_gol": "Finalizações no gol",
          "eficiencia": "Eficiência (xG)", "passes": "Passes", "finalizacoes": "Finalizações", "controle": "Posse × controle"}
