"""
Rodada 27 — o Assistente respondia "como jogou o Igor Gomes?" despejando as chaves da fonte ("accurate_passes 9,
accurate_passes_total 12, matchstats.headers.tackles 1, fotmob_id 902694…"). Aqui os números por jogador viram um
parágrafo em linguagem de futebol: minutos e nota, com a bola, sem a bola, duelos e um resumo — só com o que a fonte
mediu (número que não veio não é tratado como zero).

Também a RECEPÇÃO do jogo: quando a pergunta só identifica a partida ("atletico x boca juniors 2026"), em vez de
pontos fortes/fracos e a linha do tempo inteira, mostra o placar, os números principais e sugestões de pergunta.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _n(v: Any) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> str:
    f = _n(v)
    return "—" if f is None else (f"{f:.0f}" if abs(f - round(f)) < 1e-9 else f"{f:.2f}".replace(".", ","))


def _pair(p: Dict[str, Any], ok: str, tot: str) -> Optional[str]:
    a, b = _n(p.get(ok)), _n(p.get(tot))
    if a is None or b is None or b <= 0:
        return None
    return f"{_i(a)} de {_i(b)} ({100 * a / b:.0f}%)"


def player_summary(p: Dict[str, Any], team: str = "") -> str:
    """Um parágrafo por jogador, em linguagem de futebol."""
    name = p.get("jogador") or "Jogador"
    mins = _n(p.get("minutos") if p.get("minutos") is not None else p.get("minutes"))
    rating = _n(p.get("nota"))
    head = f"**{name}**" + (f" ({team})" if team else "")
    if mins is not None:
        head += f" jogou {_i(mins)} minutos"
        if mins <= 20:
            head += " — pouco tempo em campo, então os números dizem pouco"
    if rating is not None:
        head += f", nota {rating:.1f} da FotMob".replace(".", ",")
    head += "."
    attack: List[str] = []
    g, a = _n(p.get("totalGoals")), _n(p.get("goalAssists"))
    if g:
        attack.append(f"{_i(g)} gol" + ("s" if g > 1 else ""))
    if a:
        attack.append(f"{_i(a)} assistência" + ("s" if a > 1 else ""))
    sh = _n(p.get("totalShots"))
    if sh:
        on = _n(p.get("shotsOnTarget")) or 0
        attack.append(f"{_i(sh)} finalização" + ("ões" if sh > 1 else "") + f" ({_i(on)} no gol)")
    if _n(p.get("xg")):
        attack.append(f"xG {_i(p.get('xg'))}")
    if _n(p.get("chances_created")):
        attack.append(f"{_i(p.get('chances_created'))} passe(s) para finalização")
    if _n(p.get("xa")):
        attack.append(f"xA {_i(p.get('xa'))}")
    passing: List[str] = []
    a_, t_ = _n(p.get("accurate_passes")), _n(p.get("accurate_passes_total"))
    if a_ is not None and t_:
        passing.append(f"acertou {_i(a_)} de {_i(t_)} passes ({100 * a_ / t_:.0f}%)")
    if _n(p.get("passes_into_final_third")):
        passing.append(f"{_i(p.get('passes_into_final_third'))} passe(s) para o terço final")
    lb = _pair(p, "long_balls_accurate", "long_balls_accurate_total")
    if lb:
        passing.append(f"bolas longas {lb}")
    cr = _pair(p, "accurate_crosses", "accurate_crosses_total")
    if cr:
        passing.append(f"cruzamentos {cr}")
    dr = _pair(p, "dribbles_succeeded", "dribbles_succeeded_total")
    if dr:
        passing.append(f"dribles {dr}")
    if _n(p.get("touches")):
        passing.append(f"{_i(p.get('touches'))} toques na bola" + (f" ({_i(p.get('touches_opp_box'))} na área rival)"
                                                                 if _n(p.get("touches_opp_box")) else ""))
    if _n(p.get("dispossessed")):
        passing.append(f"perdeu a bola {_i(p.get('dispossessed'))} vez(es) na disputa")
    defense: List[str] = []
    for key, lab in (("matchstats.headers.tackles", "desarme(s)"), ("interceptions", "interceptação(ões)"),
                     ("recoveries", "recuperação(ões)"), ("clearances", "corte(s)"), ("shot_blocks", "chute(s) bloqueado(s)")):
        if _n(p.get(key)):
            defense.append(f"{_i(p.get(key))} {lab}")
    if _n(p.get("dribbled_past")):
        defense.append(f"foi driblado {_i(p.get('dribbled_past'))} vez(es)")
    duels: List[str] = []
    gd = _pair(p, "ground_duels_won", "ground_duels_won_total")
    if gd:
        duels.append(f"no chão ganhou {gd}")
    ae = _pair(p, "aerials_won", "aerials_won_total")
    if ae:
        duels.append(f"no alto ganhou {ae}")
    if _n(p.get("foulsCommitted")):
        duels.append(f"{_i(p.get('foulsCommitted'))} falta(s) cometida(s)")
    if _n(p.get("was_fouled")):
        duels.append(f"sofreu {_i(p.get('was_fouled'))} falta(s)")
    parts = [head]
    if attack:
        parts.append("**No ataque:** " + ", ".join(attack) + ".")
    if passing:
        parts.append("**Com a bola:** " + "; ".join(passing) + ".")
    if defense:
        parts.append("**Sem a bola:** " + ", ".join(defense) + ".")
    if duels:
        parts.append("**Duelos:** " + "; ".join(duels) + ".")
    parts.append("**Em resumo:** " + _verdict(p, rating, mins, attack, defense))
    return "\n\n".join(parts)


def _verdict(p: Dict[str, Any], rating: Optional[float], mins: Optional[float], attack, defense) -> str:
    if mins is not None and mins <= 20:
        return "entrou no fim — não dá para julgar a atuação por tão pouco tempo."
    if rating is None:
        tone = "a fonte não deu nota a ele neste jogo"
    elif rating >= 7.5:
        tone = "uma das melhores atuações da partida"
    elif rating >= 7.0:
        tone = "boa atuação"
    elif rating >= 6.5:
        tone = "atuação regular, sem destaque"
    else:
        tone = "atuação abaixo — participou pouco ou errou mais do que acertou"
    extra = []
    if not attack and (mins or 0) >= 45:
        extra.append("não criou nem finalizou")
    if len(defense) >= 3:
        extra.append("ajudou bastante sem a bola")
    return tone + (" (" + ", ".join(extra) + ")" if extra else "") + "."


INTRO_STATS = ["Posse de bola (%)", "Finalizações", "Finalizações no gol", "xG (fonte)", "Grandes chances",
               "Passes certos", "Precisão de passe (%)", "Desarmes certos", "Interceptações", "Escanteios",
               "Faltas cometidas", "Cartões amarelos", "Cartões vermelhos"]
_FILLER = {"x", "vs", "versus", "contra", "jogo", "partida", "o", "a", "de", "do", "da", "e", "no", "na", "em", "final",
           "semifinal", "ida", "volta", "fc", "sc", "mg", "pr", "rj", "sp", "rs", "ec"}


def is_match_intro(raw: str, teams: List[str]) -> bool:
    """A pergunta só identifica o jogo (times, ano, 'x')?"""
    from src.intelligence.query_understanding import norm

    t = norm(raw)
    words = [w for w in re.split(r"[^a-z0-9]+", t) if w]
    team_words = set()
    for tm in teams:
        team_words |= {w for w in re.split(r"[^a-z0-9]+", norm(tm)) if w}
    rest = [w for w in words if w not in team_words and w not in _FILLER and not re.fullmatch(r"(19|20)\d\d", w)
            and not any(w and tw.startswith(w) and len(w) >= 4 for tw in team_words)]
    return len(words) <= 9 and not rest


def match_intro(stats: Dict[str, Dict[str, Any]], meta: Dict[str, Any], goals: List[Dict[str, Any]]) -> str:
    """Placar + números principais + gols + o que dá para perguntar."""
    home, away = meta.get("home_team_name", ""), meta.get("away_team_name", "")
    out = [f"⚽ **{home} {meta.get('home_score', '')} x {meta.get('away_score', '')} {away}**"
           + (f" · {meta.get('competition_name')}" if meta.get("competition_name") else "")
           + (f" · {str(meta.get('match_date'))[:10]}" if meta.get("match_date") else ""),
           "Achei o jogo. **O que você quer saber dele?** Antes, os números principais:"]
    rows = [(lab, stats[lab]) for lab in INTRO_STATS if lab in stats]
    if rows:
        teams = list(rows[0][1].keys())
        out.append("| Estatística | " + " | ".join(teams) + " |\n|---|" + "---|" * len(teams) + "\n"
                   + "\n".join(f"| {lab} | " + " | ".join(_i(v.get(t)) for t in teams) + " |" for lab, v in rows))
    if goals:
        out.append("**Gols:** " + "; ".join(f"{g.get('minuto')}' {g.get('jogador') or 'autor não informado'} "
                                            f"({g.get('equipe')})" for g in goals) + ".")
    out.append("**Você pode perguntar, por exemplo:**\n"
               f"- por que o {away if (meta.get('away_score') or 0) > (meta.get('home_score') or 0) else home} venceu?\n"
               "- quem jogou melhor?\n- como jogou [nome do jogador]?\n"
               f"- o que o {home} deveria ter feito de diferente?\n- quais substituições você faria?")
    return "\n\n".join(out)
