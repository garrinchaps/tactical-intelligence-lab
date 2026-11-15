"""
Glossário (v36, F4): cada sigla com uma frase simples e um botão "o que é isto?".
"""

from __future__ import annotations

from typing import Iterable

GLOSSARY = {
    "xG": "Gols esperados: a chance de cada finalização virar gol (0 a 1), pela distância, ângulo e tipo do lance. "
          "Somar o xG diz quantos gols as chances “valiam”.",
    "xT": "Ameaça esperada: quanto um passe ou condução aproximou a bola de uma zona de onde costuma sair gol. "
          "Mede quem faz o time chegar perto da área, mesmo sem finalizar.",
    "PPDA": "Passes que o rival troca na saída de bola para cada ação defensiva sua no campo dele. Quanto MENOR, mais "
            "forte e alta a pressão.",
    "Field Tilt": "De todos os passes no terço final do campo, a fatia do time. Mostra quem empurrou o outro para trás.",
    "r": "Coeficiente de correlação: vai de −1 a +1. Perto de +1, as duas coisas sobem juntas; perto de −1, quando uma "
         "sobe a outra desce; perto de 0, não há relação. Correlação não é causalidade: andar junto não prova que uma "
         "coisa causa a outra.",
    "Percentil": "Posição entre jogos parecidos: percentil 80 = melhor que 80% das atuações da referência.",
    "Nota": "Nota de 0 a 10 do laboratório, só com os lances do jogo, com pesos diferentes para cada posição.",
}


def explain(term: str) -> str:
    return GLOSSARY.get(term, "")


def what_is(terms: Iterable[str], key: str) -> None:
    """Botão discreto que abre a explicação das siglas usadas na tela."""
    import streamlit as st

    terms = [t for t in terms if t in GLOSSARY]
    if not terms:
        return
    with st.popover("❓ O que é isto? (" + ", ".join(terms) + ")"):
        for t in terms:
            st.markdown(f"**{t}** — {GLOSSARY[t]}")
