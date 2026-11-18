"""
Redator da IA do laboratório: transforma os fatos escolhidos em texto de analista (dados → texto).
Os números vêm dos fatos (nunca do redator); as frases-modelo variam e aprendem com as avaliações.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.intelligence.lab_ai.facts import Fact

OPENINGS = [
    "Pelos números, {lead}",
    "O dado que mais pesa aqui: {lead}",
    "Direto ao ponto: {lead}",
]
CLOSINGS = [
    "Em resumo: {txt}",
    "Resumindo para o vestiário: {txt}",
    "Em uma frase: {txt}",
]

# como explorar quando o RIVAL está mal num número (ou como corrigir quando é o nosso time)
EXPLOIT: Dict[str, Tuple[str, str]] = {
    "aerials_won": ("atacar a área com cruzamento e bola alongada — o rival perdeu o jogo aéreo",
                    "evitar bola alta na própria área e treinar a disputa aérea"),
    "duels_won": ("buscar o 1x1 e a segunda bola — o rival perde duelos", "aproximar dois jogadores na disputa"),
    "ground_duels_won": ("conduzir para cima do marcador no chão", "melhorar o corpo a corpo no chão"),
    "tackles_won": ("atrair o desarme e sair em velocidade — o rival desarma pouco", "encurtar a distância para o portador"),
    "interceptions": ("passes verticais entre as linhas — o rival intercepta pouco", "fechar as linhas de passe por dentro"),
    "pass_accuracy_pct": ("pressionar a saída de bola — o rival erra passes", "dar mais opções curtas a quem sai jogando"),
    "possession_pct": ("deixar a bola com o rival e sair no contra-ataque", "ter mais calma com a bola"),
    "shots_on_target": ("o rival quase não acerta o gol: dá para adiantar a linha e pressionar", "trabalhar a jogada até a área"),
    "xg": ("o rival cria pouco: subir a linha e pressionar alto", "criar chances mais limpas (entrar na área)"),
    "big_chances_missed": ("o rival desperdiça: a defesa pode arriscar mais", "repetir a finalização em treino"),
    "fouls": ("conduzir em velocidade para cavar faltas perto da área", "menos faltas desnecessárias"),
    "crosses_accurate": ("o rival cruza mal: deixar o cruzamento e fechar por dentro", "melhorar a qualidade do cruzamento"),
    "long_balls_accurate": ("o rival não acerta a ligação direta: subir a linha", "variar mais curto"),
    "touches_opp_box": ("o rival quase não pisa na área: dá para subir o bloco", "levar mais gente para dentro da área"),
    "pressures": ("o rival pressiona pouco: sair jogando desde o goleiro", "subir a pressão no portador"),
    "switches": ("o rival inverte pouco: dá para fechar o lado da bola com mais gente", "inverter mais para achar o lado fraco"),
}


def _n(v: Optional[float], key: str = "") -> str:
    if v is None:
        return "—"
    if key.endswith("pct") or "%" in key:
        return f"{v:.0f}%"
    if "xg" in key.lower() or "xa" in key.lower():
        return f"{v:.2f}"
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


_KEEP = {"de", "da", "do", "das", "dos", "no", "na", "nos", "nas", "sem", "xg", "gol", "área", "rival", "jogo", "goleiro",
         "portador", "parada", "rolando", "chances)"}


def agree(label: str, v: Optional[float]) -> str:
    """Concordância: '1 cartões vermelhos' → '1 cartão vermelho'."""
    if v is None or abs(float(v) - 1.0) > 1e-9 or "%" in label or "xg" in label.lower():
        return label
    out = []
    for w in label.split():
        lw = w.lower()
        if lw in _KEEP or len(w) <= 3 or "(" in w:
            out.append(w)
        elif lw.endswith("ões"):
            out.append(w[:-3] + "ão")
        elif lw.endswith("s"):
            out.append(w[:-1])
        else:
            out.append(w)
    return " ".join(out)


def ruler(f: Fact) -> str:
    if f.pct is None:
        return ""
    if f.pct >= 50:
        return f" — maior que em {f.pct:.0f}% dos jogos da base"
    return f" — menor que em {100 - f.pct:.0f}% dos jogos da base"


def verdict(f: Fact) -> Optional[str]:
    """+1 = ponto forte de quem fez, -1 = ponto fraco, None = neutro/sem contraste."""
    if f.sense == 0 or f.opp_value is None:
        if f.pct is not None and f.sense:
            return "forte" if (f.pct - 50) * f.sense > 25 else ("fraco" if (f.pct - 50) * f.sense < -25 else None)
        return None
    d = (f.value - f.opp_value) * f.sense
    if abs(f.value - f.opp_value) < max(1.0, 0.15 * max(abs(f.value), abs(f.opp_value))):
        return None
    return "forte" if d > 0 else "fraco"


def line(f: Fact) -> str:
    if f.key == "sw:reacao":
        e = f.extra
        txt = (f"**{f.team}** sofreu {e['total']} inversões de jogo de {f.opponent}; em {e['sem_reacao']} delas ninguém "
               f"chegou na bola em 5 s")
        if e.get("avanco_sem_reacao") is not None:
            txt += f" e, nesses casos, o ataque chegou ao último terço {e['avanco_sem_reacao']:.0f}% das vezes"
        if e.get("lado_mais_fragil"):
            txt += f". Lado que mais sofreu: o {e['lado_mais_fragil']} do ataque rival"
        sl = e.get("mais_lento")
        if sl:
            txt += f". Mais lento a reagir: {sl['jogador']} ({sl['tempo médio (s)']:.1f} s em média)"
        return txt + "."
    if f.player:
        s = f"**{f.player}** ({f.team}) liderou em {f.label}: {_n(f.value, f.key)}"
        if f.share:
            s += f" ({100 * f.share:.0f}% do time)"
        sec = (f.extra or {}).get("segundo")
        if sec and sec[1] and sec[1] > 0:
            s += f"; depois vem {sec[0]} ({_n(sec[1], f.key)})"
        return s + "."
    s = f"**{f.team}**: {_n(f.value, f.key)} {agree(f.label, f.value)}"
    if f.opp_value is not None:
        s += f" contra {_n(f.opp_value, f.key)} de {f.opponent}"
    return s + ruler(f) + "."


def explore_lines(facts: List[Fact], focus: str, rival: str, k: int = 4) -> List[str]:
    out, seen = [], set()
    for f in facts:
        if f.player or f.key in seen:
            continue
        v = verdict(f)
        # fraqueza de verdade: pior que o rival E (quando há régua) fraco também contra os jogos da base
        if v == "fraco" and f.pct is not None and f.sense and (f.pct - 50) * f.sense > -10:
            v = None
        if f.key == "sw:reacao" and f.team == rival and f.extra.get("total"):
            e = f.extra
            side = e.get("lado_mais_fragil")
            out.append(f"Inverter rápido{(' para o lado ' + side) if side else ''}: {rival} deixou "
                       f"{e['sem_reacao']} de {e['total']} inversões sem ninguém na bola em 5 s.")
            seen.add(f.key)
        elif f.team == rival and v == "fraco" and f.key in EXPLOIT:
            out.append(EXPLOIT[f.key][0][0].upper() + EXPLOIT[f.key][0][1:] + f" ({rival}: {_n(f.value, f.key)} {agree(f.label, f.value)}).")
            seen.add(f.key)
        elif f.team == focus and v == "fraco" and f.key in EXPLOIT:
            out.append(f"Corrigir em {focus}: {EXPLOIT[f.key][1]} ({_n(f.value, f.key)} {agree(f.label, f.value)}).")
            seen.add(f.key)
        if len(out) >= k:
            break
    return out


def compose(question: str, chosen: List[Fact], all_facts: List[Fact], focus: str, rival: str, selector,
            rng: np.random.Generator, wants_plan: bool) -> Tuple[str, List[str]]:
    used_t: List[str] = []
    if not chosen:
        return ("Não tenho números deste jogo para responder isso — a fonte só traz o placar. "
                "Abra um jogo com 📊 estatísticas ou 🟢 lances."), used_t
    lead = line(chosen[0]).replace("**", "")
    i = selector.pick_template("abertura", OPENINGS, rng)
    used_t.append(f"abertura:{i}")
    parts = [OPENINGS[i].format(lead=lead)]
    if len(chosen) > 1:
        parts.append("\n**O que os números mostram**\n\n" + "\n".join(f"- {line(f)}" for f in chosen[1:]))
    strong = [f for f in chosen if f.team == focus and verdict(f) == "forte" and not f.player]
    weak = [f for f in chosen if f.team == focus and verdict(f) == "fraco" and not f.player]
    leitura = []
    if strong:
        leitura.append(f"{focus} se impôs em " + ", ".join(f.label for f in strong[:3]) + ".")
    if weak:
        leitura.append(f"Ficou devendo em " + ", ".join(f.label for f in weak[:3]) + ".")
    if leitura:
        parts.append("\n**Leitura tática**\n\n" + " ".join(leitura))
    ex = explore_lines(sorted(all_facts, key=lambda f: -abs((f.pct or 50) - 50)), focus, rival) if wants_plan else \
        explore_lines(chosen, focus, rival, k=2)
    if ex:
        parts.append("\n**Como explorar / corrigir**\n\n" + "\n".join(f"- {x}" for x in ex))
    j = selector.pick_template("fecho", CLOSINGS, rng)
    used_t.append(f"fecho:{j}")
    summ = (f"{focus} foi melhor em " + strong[0].label) if strong else (
        f"{focus} precisa melhorar em " + weak[0].label if weak else "o jogo foi equilibrado nesses números")
    parts.append("\n" + CLOSINGS[j].format(txt=summ + "."))
    return "\n".join(parts), used_t
