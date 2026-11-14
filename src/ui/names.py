"""Nomes de seleções em português — só na exibição (os dados guardam o nome original da fonte)."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict

PT: Dict[str, str] = {
    "Brazil": "Brasil", "Argentina": "Argentina", "France": "França", "England": "Inglaterra", "Germany": "Alemanha",
    "Spain": "Espanha", "Italy": "Itália", "Portugal": "Portugal", "Netherlands": "Holanda", "Belgium": "Bélgica",
    "Croatia": "Croácia", "Uruguay": "Uruguai", "Colombia": "Colômbia", "Chile": "Chile", "Paraguay": "Paraguai",
    "Peru": "Peru", "Ecuador": "Equador", "Venezuela": "Venezuela", "Bolivia": "Bolívia", "Mexico": "México",
    "United States": "Estados Unidos", "USA": "Estados Unidos", "Canada": "Canadá", "Costa Rica": "Costa Rica",
    "Panama": "Panamá", "Honduras": "Honduras", "Jamaica": "Jamaica", "Morocco": "Marrocos", "Senegal": "Senegal",
    "Tunisia": "Tunísia", "Cameroon": "Camarões", "Ghana": "Gana", "Nigeria": "Nigéria", "Egypt": "Egito",
    "Algeria": "Argélia", "Ivory Coast": "Costa do Marfim", "Côte d'Ivoire": "Costa do Marfim",
    "South Africa": "África do Sul", "Mali": "Mali", "Japan": "Japão", "South Korea": "Coreia do Sul",
    "Korea Republic": "Coreia do Sul", "Australia": "Austrália", "Iran": "Irã", "Saudi Arabia": "Arábia Saudita",
    "Qatar": "Catar", "China PR": "China", "Switzerland": "Suíça", "Denmark": "Dinamarca", "Sweden": "Suécia",
    "Norway": "Noruega", "Poland": "Polônia", "Serbia": "Sérvia", "Wales": "País de Gales", "Scotland": "Escócia",
    "Northern Ireland": "Irlanda do Norte", "Republic of Ireland": "Irlanda", "Ireland": "Irlanda", "Austria": "Áustria",
    "Czech Republic": "República Tcheca", "Czechia": "República Tcheca", "Hungary": "Hungria", "Slovakia": "Eslováquia",
    "Slovenia": "Eslovênia", "Romania": "Romênia", "Ukraine": "Ucrânia", "Russia": "Rússia", "Turkey": "Turquia",
    "Türkiye": "Turquia", "Turkiye": "Turquia", "Greece": "Grécia", "Georgia": "Geórgia", "Albania": "Albânia",
    "Iceland": "Islândia", "Finland": "Finlândia", "Bulgaria": "Bulgária", "Bosnia and Herzegovina": "Bósnia",
    "North Macedonia": "Macedônia do Norte", "Montenegro": "Montenegro", "Israel": "Israel",
    "New Zealand": "Nova Zelândia", "Soviet Union": "União Soviética", "West Germany": "Alemanha Ocidental",
    "East Germany": "Alemanha Oriental", "Yugoslavia": "Iugoslávia", "Czechoslovakia": "Tchecoslováquia",
}
# preposição "de" + artigo: "do Brasil", "da Croácia", "dos Estados Unidos" (sem artigo: Portugal, Israel…)
DE = {"do": ["Brasil", "Uruguai", "México", "Japão", "Canadá", "Chile", "Peru", "Equador", "Paraguai", "Irã", "Catar",
             "Senegal", "Egito", "Panamá", "País de Gales", "Mali"],
      "dos": ["Estados Unidos"],
      "da": ["Argentina", "França", "Inglaterra", "Alemanha", "Espanha", "Itália", "Holanda", "Bélgica", "Croácia",
             "Colômbia", "Bolívia", "Venezuela", "Costa Rica", "Tunísia", "Nigéria", "Argélia", "Costa do Marfim",
             "África do Sul", "Coreia do Sul", "Austrália", "Arábia Saudita", "China", "Suíça", "Dinamarca", "Suécia",
             "Noruega", "Polônia", "Sérvia", "Escócia", "Irlanda do Norte", "Irlanda", "Áustria", "República Tcheca",
             "Hungria", "Eslováquia", "Eslovênia", "Romênia", "Ucrânia", "Rússia", "Turquia", "Grécia", "Geórgia",
             "Albânia", "Islândia", "Finlândia", "Bulgária", "Bósnia", "Macedônia do Norte", "Nova Zelândia",
             "União Soviética", "Alemanha Ocidental", "Alemanha Oriental", "Iugoslávia", "Tchecoslováquia", "Jamaica"]}
_ART = {n: a for a, ns in DE.items() for n in ns}
_SUFFIX = re.compile(r"^(?P<base>.+?)(?P<suf>\s+(?:Women's|Women|U17|U20|U21|U23))$")


@lru_cache(maxsize=4096)
def pt(name) -> str:
    """'Brazil' → 'Brasil'; 'Brazil Women's' → 'Brasil (fem.)'; clubes ficam como estão."""
    if not isinstance(name, str) or not name:
        return name if isinstance(name, str) else ""
    if name in PT:
        return PT[name]
    m = _SUFFIX.match(name)
    if m and m.group("base") in PT:
        suf = m.group("suf").strip()
        return f"{PT[m.group('base')]} ({'fem.' if suf.startswith('Women') else suf})"
    return name


def pt_text(text: str, names) -> str:
    """Troca no texto os nomes das seleções citadas (só palavras inteiras; nomes mais longos primeiro)."""
    if not text:
        return text
    for n in sorted({n for n in names if isinstance(n, str) and (pt(n) != n or n in PT)}, key=len, reverse=True):
        p = pt(n)
        art = _ART.get(p.split(" (")[0])              # "do", "da", "dos" ou None (Portugal, Israel…)
        if art:
            a = art[1:]                               # "o", "a", "os"
            for prep, rep in (("de", art), ("contra", f"contra {a}"), ("para", f"para {a}"), ("com", f"com {a}")):
                text = re.sub(rf"(?<![\wÀ-ÿ]){prep} {re.escape(n)}(?![\wÀ-ÿ])", f"{rep} {p}", text)
        text = re.sub(rf"(?<![\wÀ-ÿ]){re.escape(n)}(?![\wÀ-ÿ])", p, text)
    return text
