"""Motor da IA do laboratório: responde perguntas, escreve o relatório completo e registra o que mostrou."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.intelligence.lab_ai import writer as W
from src.intelligence.lab_ai.facts import Fact, features, match_facts
from src.intelligence.lab_ai.selector import Selector, log_shown

PLAN_WORDS = ("explor", "plano", "estrat", "como ganhar", "como vencer", "fraquez", "machuc", "atacar", "neutraliz",
              "corrig", "melhorar", "como parar", "anular")


def _tokens(q: str) -> List[str]:
    q = unicodedata.normalize("NFKD", (q or "").lower()).encode("ascii", "ignore").decode()
    return [t for t in re.findall(r"[a-z0-9]+", q)]


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def _teams_focus(meta: Dict[str, Any], focus: Optional[str], question: str):
    """Times em português; o foco é o time CITADO na pergunta, senão o escolhido na tela."""
    try:
        from src.ui.names import pt
    except Exception:
        pt = lambda x: x                                  # noqa: E731
    raw = [t for t in (meta.get("home_team_name"), meta.get("away_team_name")) if t]
    teams = [pt(t) for t in raw]
    q = _fold(question)
    named = [pt(r) for r in raw if _fold(r) in q or _fold(pt(r)) in q]
    if len(named) == 1:
        # "como explorar/atacar/parar a França" → a França é o RIVAL; o foco é o outro time
        pos = min((q.find(_fold(x)) for x in (named[0], *[r for r in raw if pt(r) == named[0]]) if q.find(_fold(x)) >= 0),
                  default=-1)
        before = q[:pos] if pos >= 0 else ""
        if re.search(r"(explor|atac|machuc|parar|anular|neutraliz|venc|ganhar d|bater|contra)\w*\s+(o |a |os |as )?$",
                     before.strip() + " "):
            other = [t for t in teams if t != named[0]]
            return teams, (other[0] if other else named[0])
        return teams, named[0]
    f = pt(focus) if focus else None
    return teams, (f if f in teams else (teams[0] if teams else None))


def select(facts: List[Fact], question: str, focus: Optional[str], selector: Selector, k: int = 6,
           max_player: int = 3) -> List[tuple]:
    toks = [_fold(t) for t in _tokens(question)]
    folded = []
    for f in facts:
        f2 = f
        f2.keywords = _fold(f.keywords)
        folded.append(f2)
    if not folded:
        return []
    X = np.vstack([features(f, toks, focus) for f in folded])
    p = selector.score(X)
    # o que casa com a pergunta vem primeiro (coluna 4 = "casa com a pergunta"); dentro de cada grupo, o placar da rede
    who = any(t in ("quem", "jogador", "jogadores") for t in toks)
    order = sorted(range(len(folded)), key=lambda i: (-X[i][4], -(X[i][5] if who else 0), -p[i]))
    out, keys, n_pl, per_cat = [], set(), 0, {}
    for i in order:
        f = folded[i]
        k_ = (f.key, f.team, f.player is None)
        if k_ in keys:
            continue
        if f.player and n_pl >= max_player:
            continue
        if X[i][4] == 0 and per_cat.get(f.category, 0) >= 2:       # variedade: no máx. 2 fatos por fase
            continue
        out.append((f, float(p[i]), X[i]))
        keys.add(k_)
        per_cat[f.category] = per_cat.get(f.category, 0) + 1
        n_pl += int(bool(f.player))
        if len(out) >= k:
            break
    return out


def answer(question: str, meta: Dict[str, Any], df: Optional[pd.DataFrame], box: Optional[Dict[str, Any]],
           focus: Optional[str], db=None, interaction_id: Optional[str] = None, k: int = 6) -> Dict[str, Any]:
    facts = match_facts(meta, df, box, db)
    teams, focus = _teams_focus(meta, focus, question)
    rival = next((t for t in teams if t != focus), "")
    sel = Selector()
    chosen = select(facts, question, focus, sel, k=k)
    from src.intelligence.lab_ai.facts import topical

    toks = [_fold(t) for t in _tokens(question)]
    asked = topical(toks)
    gap = ""
    if asked and not any(x[2][4] for x in chosen):       # a pergunta fala de um número que este jogo não mede
        gap = (f"Não tenho **{', '.join(dict.fromkeys(asked))}** medido neste jogo (a fonte não traz esse número). "
               f"O que os dados mostram:\n\n")
    seed = int(hashlib.md5((question + str(meta.get("match_id"))).encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    wants_plan = any(w in _fold(question) for w in PLAN_WORDS)
    md, templates = W.compose(question, [c[0] for c in chosen], facts, focus or "", rival, sel, rng, wants_plan)
    md = gap + md
    shown = [{"fid": f.fid, "key": f.key, "team": f.team, "player": f.player, "score": round(s, 4),
              "features": [round(float(x), 4) for x in X]} for f, s, X in chosen]
    if interaction_id:
        try:
            log_shown(interaction_id, question, shown, templates)
        except Exception:
            pass
    return {"markdown": md, "facts": shown, "templates": templates, "version": sel.version, "n_facts": len(facts),
            "engine": f"IA DO LABORATÓRIO v{sel.version:03d}"}


def report(meta: Dict[str, Any], df: Optional[pd.DataFrame], box: Optional[Dict[str, Any]], focus: Optional[str],
           db=None) -> Dict[str, Any]:
    """Relatório completo do jogo: tudo o que a IA sabe, organizado por fase, com leitura e como explorar."""
    facts = match_facts(meta, df, box, db)
    teams, focus = _teams_focus(meta, focus, "")
    focus = focus or ""
    rival = next((t for t in teams if t != focus), "")
    sel = Selector()
    X = np.vstack([features(f, [], focus) for f in facts]) if facts else np.zeros((0, 1))
    p = sel.score(X) if len(facts) else np.array([])
    ranked = [f for _, f in sorted(zip(-p, facts), key=lambda t: t[0])] if len(facts) else []
    by_cat: Dict[str, List[Fact]] = {}
    for f in ranked:
        if f.player or f.key.startswith("sw:"):
            continue
        by_cat.setdefault(f.category, []).append(f)
    sections = []
    for cat in ("ataque", "criação", "posse", "defesa", "duelos", "bola parada", "disciplina", "goleiro"):
        fs = [f for f in by_cat.get(cat, []) if f.team == focus]
        if not fs:
            continue
        lines = [W.line(f) for f in fs[:6]]
        strong = [f.label for f in fs if W.verdict(f) == "forte"]
        weak = [f.label for f in fs if W.verdict(f) == "fraco"]
        read = []
        if strong:
            read.append("melhor que o rival em " + ", ".join(strong[:3]))
        if weak:
            read.append("pior em " + ", ".join(weak[:3]))
        sections.append({"titulo": cat.capitalize(), "linhas": lines, "leitura": "; ".join(read)})
    players = {t: [W.line(f) for f in ranked if f.player and f.team == t][:8] for t in teams}
    sw = {f.team: f.extra for f in facts if f.key == "sw:reacao"}
    plan = W.explore_lines(sorted(facts, key=lambda f: -abs((f.pct or 50) - 50)), focus, rival, k=8)
    level = "lances com coordenadas" if df is not None and not getattr(df, "empty", True) else "estatísticas da partida"
    limits = ["Postura corporal, orientação do corpo e posicionamento sem a bola exigem vídeo ou tracking — as fontes "
              "abertas não trazem; aqui só entra o que os dados medem."]
    if level != "lances com coordenadas":
        limits.append("Sem lances com coordenadas: inversões, redes de passe e mapas não podem ser calculados neste jogo.")
    return {"foco": focus, "rival": rival, "nivel": level, "secoes": sections, "jogadores": players,
            "inversoes": sw, "plano": plan, "limites": limits, "versao": sel.version, "n_fatos": len(facts)}
