"""
Fatos de um jogo para a IA do laboratório — de QUALQUER nível de dado:
  * lances com coordenadas (StatsBomb/Wyscout/OpenPlay): estatísticas do time calculadas dos lances + números por
    jogador + inversões de jogo (ver switches.py);
  * estatísticas da partida (FotMob/ESPN/API-Football): `match_team_stats` + números por jogador da FotMob.
Cada fato traz o valor, o do adversário, a régua da base (percentil) e de que lado do campo/fase ele fala.
Valor que a fonte não mede não vira fato (lacuna ≠ zero).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.intelligence.lab_ai import reference as R

CATS = ["ataque", "criação", "posse", "defesa", "duelos", "bola parada", "disciplina", "goleiro", "individual", "padrão"]

# chave → (rótulo, categoria, sentido: +1 = mais é melhor para quem faz, -1 = mais é pior, 0 = neutro, palavras da pergunta)
KEY_META: Dict[str, tuple] = {
    "xg": ("xG (qualidade das chances)", "ataque", 1, "xg chance chances perigo perigoso finaliz"),
    "npxg": ("xG sem pênaltis", "ataque", 1, "xg chance perigo"),
    "xgot": ("xG no alvo (xGOT)", "ataque", 1, "xgot chute goleiro alvo"),
    "xg_open_play": ("xG de bola rolando", "ataque", 1, "jogada trama rolando"),
    "xg_set_play": ("xG de bola parada", "bola parada", 1, "bola parada escanteio falta"),
    "shots_total": ("finalizações", "ataque", 1, "finaliz chute chutes atac"),
    "shots_on_target": ("finalizações no gol", "ataque", 1, "alvo gol chute"),
    "shots_inside_box": ("finalizações dentro da área", "ataque", 1, "área chute"),
    "shots_outside_box": ("finalizações de fora da área", "ataque", 0, "fora longe chute"),
    "big_chances": ("grandes chances", "ataque", 1, "chance clara grande"),
    "big_chances_missed": ("grandes chances perdidas", "ataque", -1, "perdeu desperdiç eficiên"),
    "touches_opp_box": ("toques na área rival", "ataque", 1, "área presença infiltra"),
    "possession_pct": ("posse de bola (%)", "posse", 0, "posse bola controle domínio"),
    "passes_total": ("passes", "posse", 0, "passe passes troca"),
    "passes_accurate": ("passes certos", "posse", 1, "passe"),
    "pass_accuracy_pct": ("precisão de passe (%)", "posse", 1, "passe precisão erro"),
    "passes_opp_half": ("passes no campo de ataque", "posse", 1, "campo ataque territ"),
    "long_balls_total": ("bolas longas", "posse", 0, "longa ligação direta profundidade"),
    "long_balls_accurate": ("bolas longas certas", "posse", 1, "longa ligação profundidade"),
    "crosses_total": ("cruzamentos", "criação", 0, "cruzam lateral ponta área"),
    "crosses_accurate": ("cruzamentos certos", "criação", 1, "cruzam"),
    "switches": ("inversões de jogo", "criação", 1, "invers lado virada troca"),
    "through_balls": ("passes em profundidade", "criação", 1, "profundidade costas enfiada"),
    "dribbles_completed": ("dribles certos", "criação", 1, "drible 1x1 individual"),
    "corners": ("escanteios", "bola parada", 1, "escanteio bola parada"),
    "tackles_won": ("desarmes certos", "defesa", 1, "desarme marca"),
    "tackles_total": ("desarmes tentados", "defesa", 0, "desarme"),
    "interceptions": ("interceptações", "defesa", 1, "intercept marca leitura"),
    "clearances": ("cortes", "defesa", 0, "corte afast defesa área"),
    "blocks": ("bloqueios", "defesa", 1, "bloqueio"),
    "shots_blocked": ("finalizações bloqueadas", "defesa", 0, "bloque"),
    "pressures": ("pressões no portador", "defesa", 1, "press pressão marcação alta"),
    "duels_won": ("duelos ganhos", "duelos", 1, "duelo disputa"),
    "ground_duels_won": ("duelos no chão ganhos", "duelos", 1, "duelo chão"),
    "aerials_won": ("duelos aéreos ganhos", "duelos", 1, "aéreo cabeça alto"),
    "fouls": ("faltas cometidas", "disciplina", -1, "falta violência"),
    "yellow_cards": ("cartões amarelos", "disciplina", -1, "cartão amarelo"),
    "red_cards": ("cartões vermelhos", "disciplina", -1, "vermelho expuls"),
    "offsides": ("impedimentos", "ataque", -1, "impedimento"),
    "saves": ("defesas do goleiro", "goleiro", 0, "goleiro defesa"),
}

SAFE_EVENT_REF = {"shots_total", "shots_on_target", "xg", "corners", "shots_inside_box", "shots_outside_box"}

PLAYER_KEYS: Dict[str, tuple] = {   # FotMob → (rótulo, categoria, sentido)
    "xg": ("xG", "ataque", 1), "xa": ("xA (passes para chute)", "criação", 1), "totalShots": ("finalizações", "ataque", 1),
    "chances_created": ("chances criadas", "criação", 1), "passes_into_final_third": ("passes no terço final", "criação", 1),
    "line_breaking_passes": ("passes que quebram linhas", "criação", 1), "dribbles_succeeded": ("dribles certos", "criação", 1),
    "touches_opp_box": ("toques na área rival", "ataque", 1), "recoveries": ("recuperações de bola", "defesa", 1),
    "matchstats.headers.tackles": ("desarmes", "defesa", 1), "interceptions": ("interceptações", "defesa", 1),
    "duel_won": ("duelos ganhos", "duelos", 1), "duel_lost": ("duelos perdidos", "duelos", -1),
    "aerials_won": ("aéreos ganhos", "duelos", 1), "dribbled_past": ("vezes driblado", "defesa", -1),
    "dispossessed": ("perdas de posse", "posse", -1), "saves": ("defesas", "goleiro", 1),
}


@dataclass
class Fact:
    key: str
    label: str
    category: str
    team: str
    opponent: str
    value: float
    opp_value: Optional[float] = None
    pct: Optional[float] = None            # régua da base: % dos jogos com número menor
    sense: int = 0
    keywords: str = ""
    player: Optional[str] = None
    share: Optional[float] = None          # fatia do total do time (jogador)
    n_ref: int = 0
    origin: str = ""                       # de onde veio o número
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def fid(self) -> str:
        return hashlib.md5(f"{self.key}|{self.team}|{self.player}".encode()).hexdigest()[:10]

    def to_dict(self) -> Dict[str, Any]:
        return {**asdict(self), "fid": self.fid}


# ---------------------------------------------------------------------------------------------------- lances
def team_stats_from_events(df: pd.DataFrame) -> pd.DataFrame:
    """Mesmas chaves da FotMob, calculadas dos lances (o que dá para medir com coordenadas)."""
    rows = []
    if df is None or df.empty:
        return pd.DataFrame(columns=["team_name", "stat_key", "value"])
    d = df[df["period"].fillna(1) <= 4]
    passes_all = d[d["type_name"] == "Pass"]
    tot_pass = max(len(passes_all), 1)
    for team, g in d.groupby("team_name"):
        shots = g[g["type_name"] == "Shot"]
        p = g[g["type_name"] == "Pass"]
        ok = p["pass_outcome_name"].isna()
        inbox = (g["x"] >= 102) & g["y"].between(18, 62)
        vals = {
            "shots_total": len(shots),
            "shots_on_target": int(shots["shot_outcome_name"].isin(["Goal", "Saved", "Saved To Post"]).sum()),
            "xg": float(pd.to_numeric(shots["shot_statsbomb_xg"], errors="coerce").fillna(0).sum()),
            "shots_inside_box": int(((shots["x"] >= 102) & shots["y"].between(18, 62)).sum()),
            "shots_outside_box": int((~((shots["x"] >= 102) & shots["y"].between(18, 62))).sum()),
            "possession_pct": round(100 * len(p) / tot_pass, 1),
            "passes_total": len(p), "passes_accurate": int(ok.sum()),
            "pass_accuracy_pct": round(100 * ok.mean(), 1) if len(p) else None,
            "passes_opp_half": int((p["x"] >= 60).sum()),
            "crosses_total": int(p["is_pass_cross"].fillna(False).astype(bool).sum()) if "is_pass_cross" in p else None,
            "switches": int(p["is_pass_Switch"].fillna(False).astype(bool).sum()) if "is_pass_Switch" in p else None,
            "through_balls": int(p["is_pass_through_ball"].fillna(False).astype(bool).sum()) if "is_pass_through_ball" in p else None,
            "long_balls_total": int((pd.to_numeric(p["pass_length"], errors="coerce") >= 32).sum()),
            "corners": int((p["pass_type_name"] == "Corner").sum()),
            "fouls": int((g["type_name"] == "Foul Committed").sum()),
            "interceptions": int((g["type_name"] == "Interception").sum()),
            "clearances": int((g["type_name"] == "Clearance").sum()),
            "blocks": int((g["type_name"] == "Block").sum()),
            "pressures": int((g["type_name"] == "Pressure").sum()),
            "tackles_won": int(((g["duel_type_name"] == "Tackle") &
                                g["duel_outcome_name"].isin(["Won", "Success", "Success In Play", "Success Out"])).sum()),
            "touches_opp_box": int((inbox & g["type_name"].isin(["Pass", "Carry", "Ball Receipt*", "Shot", "Dribble"])).sum()),
            "yellow_cards": int(g["foul_committed_card_name"].isin(["Yellow Card", "Second Yellow"]).sum())
            if "foul_committed_card_name" in g else None,
        }
        for k, v in vals.items():
            if v is not None:
                rows.append({"team_name": team, "stat_key": k, "value": float(v)})
    return pd.DataFrame(rows)


def player_stats_from_events(df: pd.DataFrame) -> pd.DataFrame:
    """Números por jogador a partir dos lances, nas mesmas chaves da FotMob quando existe equivalente."""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df[df["player_name"].notna()]
    rows = []
    for (team, pl), g in d.groupby(["team_name", "player_name"]):
        shots = g[g["type_name"] == "Shot"]
        p = g[g["type_name"] == "Pass"]
        rows.append({"team_name": team, "player_name": pl, "stats": {
            "xg": float(pd.to_numeric(shots["shot_statsbomb_xg"], errors="coerce").fillna(0).sum()),
            "totalShots": len(shots),
            "passes_into_final_third": int(((p["x"] < 80) & (pd.to_numeric(p["end_x"], errors="coerce") >= 80)
                                            & p["pass_outcome_name"].isna()).sum()),
            "touches_opp_box": int(((g["x"] >= 102) & g["y"].between(18, 62)).sum()),
            "interceptions": int((g["type_name"] == "Interception").sum()),
            "recoveries": int((g["type_name"] == "Ball Recovery").sum()),
            "matchstats.headers.tackles": int((g["duel_type_name"] == "Tackle").sum()),
            "dribbled_past": int((g["type_name"] == "Dribbled Past").sum()),
            "dispossessed": int((g["type_name"] == "Dispossessed").sum()),
            "pressures": int((g["type_name"] == "Pressure").sum()),
        }})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------- montagem
def _player_frame(box: Dict[str, Any], df: Optional[pd.DataFrame]) -> pd.DataFrame:
    ps = (box or {}).get("player_stats")
    if ps is not None and getattr(ps, "empty", True) is False and "stats" in ps:
        return ps[["team_name", "player_name", "stats"]]
    return player_stats_from_events(df)


def match_facts(meta: Dict[str, Any], df: Optional[pd.DataFrame] = None, box: Optional[Dict[str, Any]] = None,
                db=None) -> List[Fact]:
    """Todos os fatos do jogo, dos dois times (time e jogadores)."""
    ref = R.load(db)
    h, a = meta.get("home_team_name", ""), meta.get("away_team_name", "")
    ts = (box or {}).get("team_stats")
    has_events = df is not None and not df.empty
    if has_events:
        ts = team_stats_from_events(df)
        origin = "lances do jogo"
    else:
        origin = f"estatísticas da partida ({meta.get('data_source') or 'fonte'})"
    facts: List[Fact] = []
    if ts is not None and not getattr(ts, "empty", True):
        t = ts.copy()
        t["value"] = pd.to_numeric(t["value"], errors="coerce")
        piv = t.dropna(subset=["value"]).pivot_table(index="stat_key", columns="team_name", values="value", aggfunc="first")
        teams = [x for x in piv.columns]
        for key, row in piv.iterrows():
            if key not in KEY_META:
                continue
            label, cat, sense, kw = KEY_META[key]
            for tm in teams:
                v = row.get(tm)
                if v is None or pd.isna(v):
                    continue
                opp = next((o for o in teams if o != tm), None)
                ov = row.get(opp) if opp is not None else None
                # a régua vem de estatísticas de outras fontes: com lances, só entram números de MESMA definição
                use_ref = not has_events or key in SAFE_EVENT_REF
                facts.append(Fact(key, label, cat, tm, opp or "", float(v),
                                  None if ov is None or pd.isna(ov) else float(ov),
                                  R.percentile(ref, key, float(v)) if use_ref else None, sense, kw,
                                  n_ref=R.sample_size(ref, key) if use_ref else 0, origin=origin))
    pf = _player_frame(box or {}, df)
    if pf is not None and not pf.empty:
        for team, g in pf.groupby("team_name"):
            opp = next((x for x in (h, a) if x and x != team), "")
            stats = pd.DataFrame([dict(s or {}) for s in g["stats"]], index=g["player_name"].values)
            for k, (label, cat, sense) in PLAYER_KEYS.items():
                if k not in stats:
                    continue
                col = pd.to_numeric(stats[k], errors="coerce")
                if col.notna().sum() == 0 or (col.fillna(0) <= 0).all():
                    continue
                tot = float(col.fillna(0).sum())
                who = col.idxmax() if sense >= 0 else col.idxmax()
                v = float(col.max())
                facts.append(Fact(f"p:{k}", label, "individual" if cat not in ("goleiro",) else cat, team, opp, v,
                                  sense=sense, keywords=f"jogador quem {label}", player=str(who),
                                  share=round(v / tot, 3) if tot > 0 else None, origin=origin,
                                  extra={"categoria_jogo": cat, "segundo": (str(col.drop(who).idxmax()), float(col.drop(who).max()))
                                         if col.drop(who).notna().any() else None}))
    if has_events:
        try:
            from src.intelligence.lab_ai.switches import switch_facts

            facts += switch_facts(df, h, a)
        except Exception:
            pass
    try:                                                 # seleções em português na exibição (France → França)
        from src.ui.names import pt

        for f in facts:
            f.team, f.opponent = pt(f.team), pt(f.opponent)
    except Exception:
        pass
    return facts


STOP = {"quem", "qual", "quais", "como", "quantas", "quantos", "quanto", "quanta", "jogo", "time", "mais", "menos", "partida", "foi", "teve", "fez", "melhor",
        "pior", "contra", "sobre", "isso", "essa", "esse", "para", "pelo", "pela", "onde", "quando", "muito", "jogador"}


def _stem(t: str) -> str:
    return t[:5] if len(t) >= 5 else t


def matches(question_tokens: List[str], text: str) -> bool:
    """A pergunta fala deste número? (mesmo começo de palavra: 'reagiu' ~ 'reação', 'aéreos' ~ 'aéreo')."""
    import unicodedata as _u

    kw = {_stem(w) for w in re.findall(r"[a-z0-9]+", _u.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode())
          if len(w) >= 3}
    return any(_stem(t) in kw for t in question_tokens if len(t) >= 4 and t not in STOP)


def topical(question_tokens: List[str]) -> List[str]:
    """Números que a pergunta cita (rótulos), para dizer 'não tenho isso medido' quando o jogo não traz."""
    content = [t for t in question_tokens if len(t) >= 4 and t not in STOP]
    scored = []
    for label, _c, _s, kw in KEY_META.values():
        hits = sum(matches([t], f"{label} {kw}") for t in content)
        if hits and hits >= min(2, len(content)):
            scored.append((hits, label))
    if not scored:
        return []
    best = max(h for h, _ in scored)
    return list(dict.fromkeys(l for h, l in scored if h == best))[:2]


def features(f: Fact, question_tokens: List[str], focus_team: Optional[str]) -> np.ndarray:
    """Vetor que a rede de seleção usa para decidir se o fato entra na resposta."""
    ext = abs((f.pct if f.pct is not None else 50.0) - 50.0) / 50.0
    if f.opp_value is not None:
        scale = max(abs(f.value), abs(f.opp_value), 1.0)
        diff = float(np.tanh(2 * (f.value - f.opp_value) / scale))
    else:
        diff = float(f.share or 0) * 2 - 0.5
    match = float(matches(question_tokens, f.keywords + " " + f.label))
    cat = [float(f.category == c) for c in CATS]
    return np.array([1.0, ext, abs(diff), diff * (f.sense or 0), match, float(f.player is not None),
                     float(focus_team is not None and f.team == focus_team), float(f.pct is not None), *cat], float)


N_FEATURES = 8 + len(CATS)
FEATURE_NAMES = ["viés", "fora da curva", "diferença p/ rival", "vantagem (sentido)", "casa com a pergunta",
                 "é de jogador", "é do time em foco", "tem régua"] + [f"cat:{c}" for c in CATS]
