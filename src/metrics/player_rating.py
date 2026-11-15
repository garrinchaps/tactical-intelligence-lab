"""
Nota de 0 a 10 por atuação — própria do laboratório (no espírito de Opta/Sofascore, mas com regras abertas).

Como a nota é feita (tudo a partir dos lances da partida, nada inventado):
1. Cada jogador parte de 6,0 e desconta o que um jogador comum do setor soma no mesmo tempo (EXPECTED_PER90):
   quem só cumpre tabela fica perto de 6,5–7; quem decide sobe.
2. Cada ação soma ou subtrai um peso. Os pesos dependem do SETOR em que ele jogou naquela partida
   (goleiro, defesa, meio, ataque), para não punir um zagueiro por não finalizar nem um atacante por não desarmar.
3. Acertos pesam mais que erros: cada erro comum custa só uma fração (ERROR_SHARE) do seu peso; só o que muda o
   jogo (erro que deu finalização ao rival, expulsão, gol sofrido pelo goleiro) entra com peso cheio.
4. Minutos: a soma vem das ações do tempo jogado. Com menos de 30 min a nota é puxada para 6,0 (pouca amostra);
   com menos de 10 min não há nota (como nos sites de referência).
5. Curva suave (tangente hiperbólica): somar pontos fica mais difícil perto do 10; a nota fica entre 3,0 e 10,0,
   arredondada a uma casa.
Partidas sem lances do jogador NÃO geram nota — e por isso não entram na média dele.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

BASE = 6.0
MIN_MINUTES = 10
FULL_SAMPLE_MINUTES = 30
ERROR_SHARE = 0.5           # um erro comum custa metade do seu peso (acertos pesam mais que erros)

# pesos por ação e por setor: (goleiro, defesa, meio, ataque)
POSITIVE: Dict[str, tuple] = {
    "gols": (1.2, 1.2, 1.1, 1.0),
    "assistencias": (0.8, 0.8, 0.7, 0.7),
    "passes_decisivos": (0.25, 0.3, 0.25, 0.2),
    "xg": (0.35, 0.35, 0.35, 0.3),             # por 1,0 de xG (premia chegar à chance, mesmo sem gol)
    "xt": (0.35, 0.5, 0.45, 0.35),             # por 1,0 de xT (passes/conduções que aproximam do gol)
    "passes_certos": (0.006, 0.006, 0.007, 0.005),
    "passes_progressivos": (0.04, 0.05, 0.04, 0.03),
    "quebras_de_linha": (0.03, 0.04, 0.04, 0.03),
    "finalizacoes_no_alvo": (0.0, 0.1, 0.1, 0.12),
    "dribles": (0.0, 0.06, 0.07, 0.07),
    "desarmes": (0.08, 0.14, 0.11, 0.09),
    "interceptacoes": (0.1, 0.13, 0.11, 0.09),
    "recuperacoes": (0.05, 0.06, 0.06, 0.06),
    "faltas_sofridas": (0.0, 0.03, 0.04, 0.05),
    "defesas_goleiro": (0.35, 0.0, 0.0, 0.0),
}
NEGATIVE: Dict[str, tuple] = {               # valores já negativos; multiplicados por ERROR_SHARE abaixo
    "passes_errados": (-0.012, -0.015, -0.012, -0.008),
    "perdas_sem_passe": (-0.05, -0.05, -0.04, -0.03),    # domínio errado, desarmado, drible sem sucesso
    "duelos_perdidos": (-0.06, -0.07, -0.05, -0.04),
    "faltas_cometidas": (-0.05, -0.05, -0.05, -0.05),
    "cartoes_amarelos": (-0.3, -0.3, -0.3, -0.3),
}
HEAVY: Dict[str, tuple] = {                  # não são reduzidos: mudam o jogo
    "erros_diretos": (-1.0, -1.0, -0.9, -0.8),
    "cartoes_vermelhos": (-1.5, -1.5, -1.5, -1.5),
    "gols_sofridos_goleiro": (-0.35, 0.0, 0.0, 0.0),
}
SECTORS = ("goleiro", "defesa", "meio", "ataque")
# o que um jogador "comum" do setor soma a cada 90 min só por estar em campo (passes certos, recuperações...).
# É descontado para que a nota mediana de um titular fique perto de 6,7 em todos os setores — sem injustiça de posição.
# Calibração PROVISÓRIA: mediana menos 0,53 em 73 atuações (≥ 45 min) de 3 jogos da Copa 2022 (StatsBomb).
EXPECTED_PER90 = {"goleiro": 0.3, "defesa": 0.9, "meio": 1.4, "ataque": 1.0}

CATEGORIES: Dict[str, list] = {
    "Ataque": ["gols", "assistencias", "finalizacoes", "finalizacoes_no_alvo", "xg", "passes_decisivos", "dribles",
               "faltas_sofridas"],
    "Passe": ["passes", "passes_certos", "precisao_passe_pct", "passes_errados", "passes_progressivos",
              "quebras_de_linha", "cruzamentos", "xt", "conducoes"],
    "Defesa": ["desarmes", "interceptacoes", "recuperacoes", "pressoes", "acoes_defensivas"],
    "Duelos e erros": ["duelos_perdidos", "perdas_de_posse", "erros_diretos", "faltas_cometidas", "cartoes_amarelos",
                       "cartoes_vermelhos"],
}


def sector(position: Any) -> str:
    p = str(position or "").lower()
    if "goalkeeper" in p or "goleiro" in p or p in ("gk", "g"):
        return "goleiro"
    if any(k in p for k in ("back", "defender", "zagueiro", "lateral", "center back", "wing back")) or p in ("d", "cb", "lb", "rb"):
        return "defesa"
    if any(k in p for k in ("forward", "striker", "atacante", "centroavante", "winger", "wing")) or p in ("f", "st", "cf", "lw", "rw"):
        return "ataque"
    return "meio"


def _gk_extras(df: pd.DataFrame) -> pd.DataFrame:
    """
    Defesas e gols sofridos do goleiro, a partir das finalizações do rival (vale para qualquer fonte com lances):
    finalização no alvo que não virou gol = defesa. Atribuídas ao goleiro que estava em campo naquele minuto.
    """
    from src.metrics.match_facts import _minutes, _regular

    cols = ["jogador", "defesas_goleiro", "gols_sofridos_goleiro"]
    if df is None or df.empty or "type_name" not in df:
        return pd.DataFrame(columns=cols)
    d = _regular(df)
    pos = d["position_name"].astype(str) if "position_name" in d else pd.Series("", index=d.index)
    gks = d[pos.str.contains("Goalkeeper|Goleiro", case=False) & d["player_name"].notna()]
    shots = d[d["type_name"] == "Shot"]
    out = []
    for team, g in gks.groupby("team_name"):
        span = g.groupby("player_name")["minute"].agg(["min", "max"])
        faced = shots[shots["team_name"] != team]
        oc = faced["shot_outcome_name"].astype(str) if "shot_outcome_name" in faced else pd.Series("", index=faced.index)
        for name, (a, b) in span.iterrows():
            w = faced[(faced["minute"] >= (0 if len(span) == 1 else a)) & (faced["minute"] <= (999 if len(span) == 1 else b))]
            o = oc.loc[w.index]
            out.append({"jogador": name, "defesas_goleiro": int(o.isin(["Saved", "Saved To Post", "Saved Off Target"]).sum()),
                        "gols_sofridos_goleiro": int((o == "Goal").sum())})
    return pd.DataFrame(out, columns=cols)


def rate_row(r: Dict[str, Any]) -> Dict[str, Any]:
    """Nota de uma linha de `player_match_stats` (+ extras do goleiro). Devolve nota e as partes da conta."""
    mins = float(r.get("minutos") or 0)
    sec = sector(r.get("posicao"))
    i = SECTORS.index(sec)
    if mins < MIN_MINUTES:
        return {"nota": None, "setor": sec, "motivo": f"menos de {MIN_MINUTES} min em campo"}
    vals = dict(r)
    vals["perdas_sem_passe"] = max(float(vals.get("perdas_de_posse") or 0) - float(vals.get("passes_errados") or 0), 0)
    parts = {"acertos": 0.0, "erros": 0.0, "decisivos": 0.0}
    for k, w in POSITIVE.items():
        parts["acertos"] += float(vals.get(k) or 0) * w[i]
    for k, w in NEGATIVE.items():
        parts["erros"] += float(vals.get(k) or 0) * w[i] * ERROR_SHARE
    for k, w in HEAVY.items():
        parts["decisivos"] += float(vals.get(k) or 0) * w[i]
    raw = parts["acertos"] + parts["erros"] + parts["decisivos"] - EXPECTED_PER90[sec] * mins / 90.0
    raw *= min(1.0, mins / FULL_SAMPLE_MINUTES)
    # curva suave: os primeiros pontos sobem rápido, chegar a 10 exige uma atuação histórica
    nota = float(np.clip(BASE + (4.0 * np.tanh(raw / 3.0) if raw >= 0 else 3.0 * np.tanh(raw / 2.0)), 3.0, 10.0))
    return {"nota": round(nota, 1), "setor": sec, "acertos": round(parts["acertos"], 2), "erros": round(parts["erros"], 2),
            "decisivos": round(parts["decisivos"], 2), "poucos_minutos": mins < FULL_SAMPLE_MINUTES,
            "motivo": "poucos minutos: nota puxada para 6,0" if mins < FULL_SAMPLE_MINUTES else ""}


def match_ratings(df: Optional[pd.DataFrame], team: Optional[str] = None) -> pd.DataFrame:
    """Tabela de estatísticas da partida com a nota de cada jogador (só quem tem lances na partida)."""
    from src.metrics.match_facts import player_match_stats

    st = player_match_stats(df, team)
    if st.empty:
        return st
    st = st[~st["jogador"].astype(str).str.lower().isin(["não identificado", "nao identificado", "unknown", ""])]
    gk = _gk_extras(df)
    st = st.merge(gk, on="jogador", how="left")
    for c in ("defesas_goleiro", "gols_sofridos_goleiro"):
        st[c] = st[c].fillna(0).astype(int)
    rated = [rate_row(r) for r in st.to_dict("records")]
    st.insert(3, "nota", [x["nota"] for x in rated])
    st.insert(4, "setor", [x["setor"] for x in rated])
    st["obs_nota"] = [x.get("motivo", "") for x in rated]
    return st.sort_values(["nota", "minutos"], ascending=[False, False], na_position="last").reset_index(drop=True)


def average_rating(per_match: pd.DataFrame) -> Dict[str, Any]:
    """
    Média da nota de um jogador em várias partidas. Recebe linhas com a coluna `nota` (None = sem nota).
    Partidas sem lances do jogador nem chegam aqui; as que têm nota None (menos de 10 min) ficam fora da média.
    """
    if per_match is None or per_match.empty or "nota" not in per_match:
        return {"media": None, "jogos_com_nota": 0}
    v = pd.to_numeric(per_match["nota"], errors="coerce").dropna()
    return {"media": round(float(v.mean()), 2) if len(v) else None, "jogos_com_nota": int(len(v)),
            "jogos_sem_nota": int(per_match["nota"].isna().sum())}
