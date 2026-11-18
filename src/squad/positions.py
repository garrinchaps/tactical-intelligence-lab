"""
Posição real do jogador cruzando várias fontes (rodada 5) — corrige "jogador fora de posição" na escalação.

O problema: `match_lineups` recebe escalações de fontes diferentes e cada uma escreve a posição de um jeito.
  * ESPN (escalação do jogo): código preciso por vaga — CD-L, RB, DM, AM-R, LF, F (F = o centroavante, vaga 9)…
    mas LM/RM mudam de sentido conforme o desenho (volante no 4-2-3-1, meia central no 4-3-3, aberto no 4-1-4-1/4-4-2,
    ala com 3 zagueiros).
  * API-Football: só G / D / M / F (genérico: "F" é qualquer atacante — ponta ou centroavante).
  * StatsBomb / Wyscout / OpenPlay: nomes precisos ("Right Wing", "RAMF"…).
  * Transfermarkt: posição de cadastro do atleta ("Right Winger", "Centre-Back").
Antes, "F" genérico virava centroavante e "D" virava zagueiro → Yamal no meio do ataque, Koundé na zaga.

Regra agora:
  1. posição PRECISA (vaga real do jogo) vale 1 por jogo; a mais recente pesa um pouco mais;
  2. posição GENÉRICA (D/M/F) só diz o SETOR e só é usada se não existir nenhuma precisa;
  3. o cadastro do Transfermarkt entra como "opinião" de 2 jogos (decide quando há poucos jogos precisos);
  4. o mesmo jogo vindo de duas fontes conta UMA vez (fica a versão com posições mais precisas).
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd

GENERIC_SECTOR = {"D?": "defesa", "M?": "meio", "F?": "ataque"}

# códigos e nomes PRECISOS de todas as fontes → papel do campinho
PRECISE: Dict[str, str] = {
    # ESPN (escalação)
    "G": "GK", "GK": "GK", "CD": "CB", "CD-L": "CB", "CD-R": "CB", "CB": "CB", "LCB": "CB", "RCB": "CB", "LB": "LB",
    "RB": "RB", "LWB": "LWB", "RWB": "RWB", "DM": "DM", "CDM": "DM", "DM-L": "DM", "DM-R": "DM", "CM": "CM", "CM-L": "CM",
    "CM-R": "CM", "AM": "AM", "CAM": "AM", "AM-L": "LW", "AM-R": "RW", "LM": "LM", "RM": "RM", "LW": "LW", "RW": "RW",
    "CF": "ST", "CF-L": "ST", "CF-R": "ST", "LF": "LW", "RF": "RW", "ST": "ST", "SS": "ST",
    # Wyscout
    "LCB3": "CB", "RCB3": "CB", "LB5": "LWB", "RB5": "RWB", "DMF": "DM", "LDMF": "DM", "RDMF": "DM", "LCMF": "CM",
    "RCMF": "CM", "LCMF3": "CM", "RCMF3": "CM", "AMF": "AM", "LAMF": "LW", "RAMF": "RW", "LWF": "LW", "RWF": "RW",
    # StatsBomb / OpenPlay (nomes)
    "GOALKEEPER": "GK", "RIGHT BACK": "RB", "LEFT BACK": "LB", "RIGHT CENTER BACK": "CB", "LEFT CENTER BACK": "CB",
    "CENTER BACK": "CB", "RIGHT WING BACK": "RWB", "LEFT WING BACK": "LWB", "RIGHT DEFENSIVE MIDFIELD": "DM",
    "LEFT DEFENSIVE MIDFIELD": "DM", "CENTER DEFENSIVE MIDFIELD": "DM", "RIGHT CENTER MIDFIELD": "CM",
    "LEFT CENTER MIDFIELD": "CM", "CENTER MIDFIELD": "CM", "RIGHT MIDFIELD": "RM", "LEFT MIDFIELD": "LM",
    "RIGHT ATTACKING MIDFIELD": "RW", "LEFT ATTACKING MIDFIELD": "LW", "CENTER ATTACKING MIDFIELD": "AM",
    "RIGHT WING": "RW", "LEFT WING": "LW", "RIGHT CENTER FORWARD": "ST", "LEFT CENTER FORWARD": "ST",
    "CENTER FORWARD": "ST", "STRIKER": "ST", "SECONDARY STRIKER": "ST",
    # Transfermarkt (cadastro e escalações)
    "CENTRE-BACK": "CB", "LEFT-BACK": "LB", "RIGHT-BACK": "RB", "DEFENSIVE MIDFIELD": "DM", "CENTRAL MIDFIELD": "CM",
    "ATTACKING MIDFIELD": "AM", "LEFT WINGER": "LW", "RIGHT WINGER": "RW", "SECOND STRIKER": "ST",
    "CENTRE-FORWARD": "ST", "SWEEPER": "CB",
    # português
    "GOLEIRO": "GK", "ZAGUEIRO": "CB", "LATERAL ESQUERDO": "LB", "LATERAL DIREITO": "RB", "VOLANTE": "DM",
    "MEIA": "AM", "PONTA ESQUERDA": "LW", "PONTA DIREITA": "RW", "CENTROAVANTE": "ST",
}
GENERIC: Dict[str, str] = {"D": "D?", "M": "M?", "F": "F?", "A": "F?", "DEFENDER": "D?", "DEFENCE": "D?",
                           "MIDFIELDER": "M?", "MIDFIELD": "M?", "FORWARD": "F?", "ATTACKER": "F?", "ATTACK": "F?",
                           "DEFENSOR": "D?", "MEIO-CAMPO": "M?", "ATACANTE": "F?"}


def _source(match_id) -> str:
    try:
        from src.data_hub.registry import source_from_internal_id

        return source_from_internal_id(int(match_id))
    except Exception:
        return ""


def classify(pos: object, source: str = "") -> Tuple[Optional[str], bool]:
    """(papel, é_preciso). Na ESPN, 'F' na escalação é a vaga 9 (centroavante); nas outras fontes é genérico."""
    k = str(pos or "").strip().upper()
    if not k or k in ("SUB", "NAN", "NONE"):
        return None, False
    if k == "F" and source == "espn":
        return "ST", True
    if k in PRECISE and not (k == "G" and source not in ("espn", "")):
        return PRECISE[k], True
    if k == "G":
        return "GK", True
    if k in GENERIC:
        return GENERIC[k], False
    return None, False


def espn_lm_rm(form: str, codes: Iterable[str]) -> Optional[str]:
    """Leitura de LM/RM da ESPN pelo desenho do jogo: 'ala', 'volante', 'meia' ou None (aberto de fato)."""
    codes = {str(c).upper() for c in codes}
    if form.startswith(("3", "5")):
        return "ala"
    wide_fwd = bool(codes & {"AM-L", "AM-R", "LW", "RW", "LF", "RF"})
    if wide_fwd and form.startswith("4-2"):
        return "volante"
    if wide_fwd:
        return "meia"
    return None


def resolve_lineups(lu: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe escalações (match_id, data, jogador, pos, formation, …) de QUALQUER fonte e devolve:
      * `papel` (só quando preciso) e `papel_generico` (D?/M?/F?);
      * um jogo por data (±1 dia): quando o mesmo jogo vem de duas fontes, fica a com mais posições precisas.
    """
    if lu is None or lu.empty:
        return lu
    lu = lu.copy()
    src = lu["match_id"].map(_source)
    cls = [classify(p, s) for p, s in zip(lu["pos"], src)]
    lu["papel"] = [r if ok else None for r, ok in cls]
    lu["papel_generico"] = [r if (r and not ok) else None for r, ok in cls]
    for mid, g in lu.groupby("match_id"):
        if _source(mid) != "espn":
            continue
        idx = g.index[g["pos"].astype(str).str.upper().isin(["LM", "RM"])]
        if not len(idx):
            continue
        form = str(g["formation"].dropna().iloc[0]) if g["formation"].notna().any() else ""
        how = espn_lm_rm(form, g["pos"])
        up = lu.loc[idx, "pos"].astype(str).str.upper()
        if how == "ala":
            lu.loc[idx, "papel"] = up.map({"LM": "LWB", "RM": "RWB"})
        elif how == "volante":
            lu.loc[idx, "papel"] = "DM"
        elif how == "meia":
            lu.loc[idx, "papel"] = "CM"
    # o mesmo jogo em duas fontes: agrupa por data (±1 dia) e fica o de mais posições precisas entre os titulares
    st = lu[lu.get("titular", 1) == 1] if "titular" in lu else lu
    prec = st.groupby("match_id")["papel"].apply(lambda s: s.notna().mean()).to_dict()
    days = pd.to_datetime(lu.drop_duplicates("match_id").set_index("match_id")["data"], errors="coerce").sort_values()
    keep, last_day, best = [], None, None
    for mid, d in days.items():
        # mesma fonte nunca duplica o próprio jogo: só junta datas vizinhas vindas de fontes DIFERENTES
        if last_day is not None and pd.notna(d) and abs((d - last_day).days) <= 1 and _source(mid) != _source(best):
            if prec.get(mid, 0) > prec.get(best, 0):
                keep[-1] = mid
                best = mid
            continue
        keep.append(mid)
        last_day, best = d, mid
    keep += [m for m in lu["match_id"].unique() if m not in days.index or pd.isna(days.get(m))]
    return lu[lu["match_id"].isin(set(keep))]


def player_roles(starts: pd.DataFrame, tm_role: Optional[str] = None, roster_pos: object = None) -> Tuple[Dict[str, float], Optional[str], str]:
    """
    Posições de UM jogador nos jogos em que começou (já resolvidos). Devolve (contagem por papel, papel principal,
    origem da posição). Recência: o jogo mais recente pesa 1,0 e o mais antigo ~0,6.
    """
    cnt: Counter = Counter()
    gen: Counter = Counter()
    if starts is not None and len(starts):
        s = starts.sort_values("data", ascending=False).reset_index(drop=True)
        n = len(s)
        for i, r in s.iterrows():
            w = 1.0 - 0.4 * (i / max(n - 1, 1))
            if r.get("papel"):
                cnt[r["papel"]] += w
            elif r.get("papel_generico"):
                gen[r["papel_generico"]] += w
    origem = "escalações (posição exata)"
    if tm_role and sum(cnt.values()) < 3:
        cnt[tm_role] += 2.0
        origem = "escalações + cadastro do Transfermarkt" if sum(cnt.values()) > 2 else "cadastro do Transfermarkt"
    if not cnt:
        r_role, ok = classify(roster_pos, "roster")
        if r_role and ok:
            cnt[r_role] += 1.0
            origem = "elenco atual (FotMob/ESPN)"
        elif gen:
            g = gen.most_common(1)[0][0]
            cnt[g] += sum(gen.values())
            origem = "só setor (fonte com posição genérica)"
        elif r_role:
            cnt[r_role] += 1.0
            origem = "só setor (elenco da ESPN)"
    main = max(cnt, key=cnt.get) if cnt else None
    return {k: round(v, 2) for k, v in cnt.items()}, main, origem


# encaixe de um papel GENÉRICO numa vaga: sabe o setor, não o lado — adequado, nunca "posição de origem"
GENERIC_FIT = {"D?": {"CB": 0.6, "LB": 0.5, "RB": 0.5, "LWB": 0.45, "RWB": 0.45, "DM": 0.35},
               "M?": {"CM": 0.6, "DM": 0.55, "AM": 0.55, "LM": 0.5, "RM": 0.5},
               "F?": {"ST": 0.6, "LW": 0.55, "RW": 0.55, "AM": 0.4}}
