"""
Rodada 24 — dicas táticas INDIVIDUAIS para "Onde ganhar o jogo" / "Onde atacar".

O pedido: nada de texto-modelo igual para situações diferentes ("é muito driblado" em todo cartão). Cada dica é montada
com o que é próprio DAQUELE confronto:

  * o lado do campo (pela função do defensor: lateral-esquerdo deles = nosso lado direito) e quem do nosso time está
    nesse corredor para apoiar (lateral para ultrapassar, meia para tabelar, centroavante para atacar o cruzamento);
  * o perfil COMPLETO do nosso atacante (as 2 coisas em que ele é mais forte além da dimensão do cartão) e o segundo
    ponto fraco do defensor — vira a jogada concreta ("recebe aberto, puxa para dentro no pé bom e finaliza");
  * o desenho do nosso time (3 zagueiros = alas fazem a amplitude; 4-3-3 = ponta aberto; 4-2-3-1 = meia por dentro);
  * o modelo de jogo do rival pelos números (posse, pressão, bola longa, cruzamentos sofridos): se ele tem a bola, a
    jogada nasce na TRANSIÇÃO; se ele se fecha, em ataque POSICIONAL; se pressiona alto, a bola nas costas sai mais cedo;
  * o tamanho da vantagem (diferença de percentil) decide o tom: "força principal do jogo" × "opção para variar".

Nada é inventado: cada frase cita um número medido ou diz que não há medida. É texto gerado por regras sobre os
números de cada par — não é uma IA generativa.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

# métricas do ATACANTE que descrevem o perfil (coluna da régua → como jogar com isso)
ATT_TRAITS = {
    "drb_p90": ("drible", "parte para cima no 1×1"),
    "crs_p90": ("cruzamento", "chega ao fundo e cruza"),
    "cc_p90": ("criação", "acha o passe para o companheiro finalizar"),
    "xg_p90": ("finalização", "chega para finalizar"),
    "tob_p90": ("presença de área", "aparece dentro da área"),
    "aer_pct": ("jogo aéreo", "ganha pelo alto"),
    "fouled_p90": ("sofrer faltas", "cava faltas em velocidade"),
    "lbp_p90": ("passe que quebra linhas", "rompe linhas com passe"),
    "rec_p90": ("recuperação", "rouba bolas no campo de ataque"),
}
# métricas do DEFENSOR (coluna, quanto MAIOR pior?) → como isso aparece no jogo
DEF_FLAWS = {
    "drb_past_p90": (True, "é driblado com frequência"),
    "aer_pct": (False, "perde pelo alto"),
    "duel_pct": (False, "perde duelos no chão"),
    "int_p90": (False, "intercepta pouco (deixa o passe entrar)"),
    "disp_p90": (True, "perde a bola quando pressionado"),
    "fouls_p90": (True, "faz muitas faltas"),
    "tkl_p90": (False, "desarma pouco"),
}
SIDE = {  # função do defensor deles → nosso lado e corredor
    "LB": ("direito", "corredor direito"), "LWB": ("direito", "corredor direito"), "LM": ("direito", "corredor direito"),
    "RB": ("esquerdo", "corredor esquerdo"), "RWB": ("esquerdo", "corredor esquerdo"), "RM": ("esquerdo", "corredor esquerdo"),
    "CB": ("central", "meio da área"), "DM": ("central", "entrelinhas"), "CM": ("central", "entrelinhas"),
}
SUPPORT = {  # nosso lado → funções que apoiam
    "direito": ["RB", "RWB", "RM", "CM", "AM"], "esquerdo": ["LB", "LWB", "LM", "CM", "AM"],
    "central": ["AM", "CM", "ST", "CF"],
}
ROLE_PT = {"RB": "lateral-direito", "LB": "lateral-esquerdo", "RWB": "ala direito", "LWB": "ala esquerdo",
           "RM": "meia direito", "LM": "meia esquerdo", "CM": "meia", "AM": "meia ofensivo", "DM": "volante",
           "ST": "centroavante", "CF": "centroavante", "RW": "ponta direita", "LW": "ponta esquerda", "CB": "zagueiro"}


def _pct(ref: pd.DataFrame, col: str, value: Any) -> Optional[float]:
    from src.squad.matchups import _pct as base

    return base(ref, col, value)


def _profile(row: Optional[Dict[str, Any]], ref: pd.DataFrame, skip: str = "") -> List[tuple]:
    """As forças do atacante (percentil ≥ 65), da maior para a menor, sem a dimensão do cartão."""
    if not row:
        return []
    out = []
    for col, (name, how) in ATT_TRAITS.items():
        if col == skip:
            continue
        p = _pct(ref, col, row.get(col))
        if p is not None and p >= 65:
            out.append((p, name, how, col))
    return sorted(out, reverse=True)


def _flaws(row: Optional[Dict[str, Any]], ref: pd.DataFrame, skip: str = "") -> List[tuple]:
    if not row:
        return []
    out = []
    for col, (bad_high, text) in DEF_FLAWS.items():
        if col == skip:
            continue
        p = _pct(ref, col, row.get(col))
        if p is None:
            continue
        badness = p if bad_high else 100 - p
        if badness >= 65:
            out.append((badness, text, col))
    return sorted(out, reverse=True)


def scheme_note(formation: str, side: str) -> str:
    f = str(formation or "")
    if f.startswith("3") or f.startswith("5"):
        return ("com três zagueiros, o ala desse lado dá a amplitude e libera o ponta/meia para atacar por dentro"
                if side != "central" else "com três zagueiros, um deles pode sair conduzindo e criar superioridade no meio")
    if "4-3-3" in f:
        return ("no 4-3-3 o ponta fica aberto e o meia interior do lado ataca o espaço entre lateral e zagueiro"
                if side != "central" else "no 4-3-3 os dois meias interiores chegam na entrada da área para o rebote")
    if "4-2-3-1" in f:
        return ("no 4-2-3-1 o meia central encosta desse lado para formar triângulo com o ponta e o lateral"
                if side != "central" else "no 4-2-3-1 o meia ofensivo joga nas costas dos volantes deles")
    if "4-4-2" in f or "4-1-" in f:
        return ("no 4-4-2 a dupla de ataque se divide: um fixa os zagueiros, o outro cai nesse lado"
                if side != "central" else "no 4-4-2 os dois atacantes atacam zagueiros diferentes para tirar a cobertura")
    return ""


def rival_context(profile: Dict[str, Any], reference: Dict[str, Any]) -> Dict[str, str]:
    """Modelo de jogo do rival pelos números (estatísticas por jogo) → momento em que a dica rende mais."""
    p, r = profile or {}, reference or {}

    def rel(k):
        a, b = p.get(k), r.get(k)
        try:
            return (float(a) - float(b)) / abs(float(b)) if a is not None and b not in (None, 0) else None
        except (TypeError, ValueError):
            return None
    out = {}
    pos = rel("posse_pct")
    if pos is not None and pos >= .1:
        out["momento"] = (f"eles ficam com a bola ({p.get('posse_pct'):.0f}% de posse): a jogada nasce na TRANSIÇÃO, "
                          "logo depois de recuperar, antes de a linha deles se recompor")
    elif pos is not None and pos <= -.1:
        out["momento"] = (f"eles abrem mão da bola ({p.get('posse_pct'):.0f}% de posse) e se fecham: a jogada é de ATAQUE "
                          "POSICIONAL — paciência, circular até o lado dele e acelerar só quando o 1×1 estiver montado")
    ppda = rel("ppda_aprox")
    if ppda is not None and ppda <= -.15:
        out["pressao"] = "eles pressionam alto: a bola nas costas sai cedo, de primeira, antes da pressão fechar"
    elif ppda is not None and ppda >= .15:
        out["pressao"] = "eles marcam mais atrás: haverá tempo para receber de frente — o risco é o bloco baixo fechado"
    cr = rel("cruzamentos_contra")
    if cr is not None and cr >= .15:
        out["cruzamento"] = f"eles já sofrem {p.get('cruzamentos_contra'):.1f} cruzamentos por jogo (acima da média)"
    return out


def _pick(options: Sequence[str], key: str) -> str:
    """Variação estável (mesmo confronto = mesma frase; confrontos diferentes = frases diferentes)."""
    h = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    return options[h % len(options)]


def individualize(item: Dict[str, Any], att_xi: List[Dict[str, Any]], att_row: Optional[Dict[str, Any]],
                  def_row: Optional[Dict[str, Any]], ref: pd.DataFrame, formation: str = "",
                  rival: Optional[Dict[str, str]] = None, attack: bool = True) -> Dict[str, Any]:
    """Reescreve `acao` do cartão com o contexto do par (perfil, lado, apoio, esquema, rival) e guarda `passos`."""
    an, dn = item.get("atacante") or "", item.get("defensor") or ""
    if not an or not dn:
        return item
    dim_col = {"drible": "drb_p90", "aereo": "aer_pct", "faltas": "fouled_p90", "duelo": "duel_pct",
               "presenca": "tob_p90", "pressao": "rec_p90"}.get(str(item.get("dimensao")), "")
    def_col = {"drible": "drb_past_p90", "aereo": "aer_pct", "faltas": "fouls_p90", "duelo": "duel_pct",
               "presenca": "int_p90", "pressao": "disp_p90"}.get(str(item.get("dimensao")), "")
    side, lane = SIDE.get(str(item.get("papel_defensor") or "").upper(), ("central", "meio"))
    strengths = _profile(att_row, ref, dim_col)
    flaws = _flaws(def_row, ref, def_col)
    helpers = [s for s in att_xi if s.get("jogador") and s.get("jogador") != an
               and str(s.get("papel") or "").upper() in SUPPORT.get(side, [])]
    helper = helpers[0] if helpers else None
    gap = float(item.get("gap") or 0)
    tone = ("é a vantagem mais clara do jogo — repetir até eles mudarem" if gap >= 60 else
            "é uma vantagem real — usar nos momentos certos" if gap >= 45 else "é uma opção para variar o ataque")
    steps: List[str] = []
    who = f"{an} ({ROLE_PT.get(str(item.get('papel_atacante') or '').upper(), 'atacante')})"
    if attack:
        steps.append(f"Onde: pelo nosso lado {side} ({lane}), em cima de {dn}." if side != "central"
                     else f"Onde: por dentro, em cima de {dn}.")
        if strengths:
            p, name, how, _ = strengths[0]
            extra = f" e também em {strengths[1][1]}" if len(strengths) > 1 else ""
            steps.append(f"Como: {who} é forte em {name}{extra} (melhor que {p:.0f}% da base) — "
                         + _pick([f"a jogada termina quando ele {how}.", f"depois de vencer {dn}, ele {how}.",
                                  f"o lance ideal é ganhar de {dn} e, em seguida, ele {how}."], an + dn + "c"))
        else:
            steps.append(f"Como: {who} não tem outra força clara medida além desta — a jogada termina em passe simples "
                         "para quem chega de trás.")
        if flaws:
            steps.append(f"Reforço: {dn} também {flaws[0][1]} (pior que {flaws[0][0]:.0f}% da base) — "
                         + _pick(["dá para insistir mais de uma vez no mesmo lance.",
                                  "se ele errar a primeira, a segunda bola ainda está aberta.",
                                  "o técnico deles tende a mandar ajuda para esse lado; aí o espaço abre do outro."],
                                 dn + "f"))
        if helper:
            hrole = ROLE_PT.get(str(helper.get("papel") or "").upper(), "companheiro")
            hint = ("passa por fora para tirar a cobertura" if hrole.startswith(("lateral", "ala")) else
                    "encosta para tabelar e devolver nas costas" if "meia" in hrole else "ataca a área para o cruzamento")
            steps.append(f"Apoio: {helper['jogador']} ({hrole}) {hint}.")
        note = scheme_note(formation, side)
        if note:
            steps.append("Esquema: " + note + ".")
        if rival:
            for k in ("momento", "pressao") if item.get("dimensao") != "aereo" else ("cruzamento", "momento"):
                if rival.get(k):
                    steps.append("Momento: " + rival[k] + ".")
                    break
        head = _pick([f"{an} contra {dn}: {tone}.", f"Confronto {an} × {dn} — {tone}.",
                      f"Pelo lado de {dn}, {an} {tone.replace('é a', 'tem a').replace('é uma', 'tem uma')}."], an + dn)
        item["acao"] = "FORÇAR: " + head
    else:
        steps.append(f"Quem: {an} ({item.get('papel_atacante') or 'atacante'} deles) em cima de {dn}, no nosso lado "
                     f"{'esquerdo' if side == 'direito' else 'direito' if side == 'esquerdo' else 'central'}.")
        if strengths:
            steps.append(f"O perigo: além disso, ele é forte em {strengths[0][1]} — "
                         + _pick(["não basta tirar o drible, é preciso fechar o passe seguinte.",
                                  "a cobertura tem de chegar antes do segundo movimento.",
                                  "o volante do lado fecha a linha de passe por dentro."], an + "p"))
        if helper:
            steps.append(f"Ajuda: {helper['jogador']} fica mais perto de {dn} nesse lado (dobra de marcação).")
        if flaws:
            steps.append(f"Atenção: {dn} também {flaws[0][1]}; evitar deixá-lo isolado no 1×1.")
        item["acao"] = f"PROTEGER: {an} × {dn} — {tone.replace('vantagem', 'ameaça')}."
    item["passos"] = steps
    return item


def individualize_all(items: List[Dict[str, Any]], my_xi, rv_xi, ms, rs, ref, formation: str = "",
                      rival: Optional[Dict[str, str]] = None, attack: bool = True) -> List[Dict[str, Any]]:
    from src.squad.matchups import _stats_row

    att_xi = my_xi if attack else rv_xi
    a_st, d_st = (ms, rs) if attack else (rs, ms)
    out = []
    for it in items:
        if it.get("tipo") == "duelo":
            try:
                it = individualize(dict(it), att_xi, _stats_row(a_st, it.get("atacante")), _stats_row(d_st, it.get("defensor")),
                                   ref, formation, rival, attack)
            except Exception:
                pass
        out.append(it)
    return out
