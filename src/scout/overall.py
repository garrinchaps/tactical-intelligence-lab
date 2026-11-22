"""
Rodada 20/21 — OVERALL 0–100 do Scout (escala tipo FC), calibrado com craques de referência E com tetos.

Rodada 21 (pedido do usuário): "90+ é craque mundial" — a régua anterior dava 89+ aos 25 primeiros de CADA posição
(~175 jogadores) e a reputação ainda pesava para quem jogou pouco (Maddison com 229 min = 88).

Componentes (percentil dentro da família de posição; o que falta não vira zero):
  R  reputação ajustada pela idade (valor atual ou 80% do pico de 3 anos; veterano não é punido pela idade)
  P  desempenho na função (números por 90 encolhidos pelos minutos × nível) + nota dos Rankings + nota externa
  T  nota média da FotMob nos últimos 12 meses, ajustada pelo nível da liga (só com 450+ min)
  L  nível da liga/clube
Z = média ponderada (a reputação vale menos para quem jogou pouco). Z é padronizado DENTRO da família (as posições
competem em pé de igualdade) e encolhido pela DISPONIBILIDADE (minutos do ano / 1.800). O overall sai da COLOCAÇÃO
GLOBAL nessa régua: só ~10 jogadores do mundo passam de 90, ~40 de 87, ~80 de 85, ~400 de 80; o resto segue uma curva
tipo FC (mediana ≈ 62). Teto por posição (lateral ≤ 90, goleiro ≤ 91…).

Calibração: grade de pesos (wR, wP, wT, wL) escolhida para (1) pôr os CRAQUES DE REFERÊNCIA no alto e (2) respeitar os
TETOS de referência (jogadores que o usuário apontou como 83–85/85–88 no máximo), mantendo correlação ≥ 0,55 com o
desempenho de quem joga muito. Relatório em data/processed/overall_calibration.json e no Scout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

CALIB_PATH = Path("data/processed/overall_calibration.json")
DEFAULT_WEIGHTS = {"wR": .35, "wP": .25, "wT": .25, "wL": .15}

REFERENCE_STARS: List[str] = [
    "Kylian Mbappé", "Erling Haaland", "Harry Kane", "Michael Olise", "Vinicius Junior", "Raphinha", "Jude Bellingham",
    "Thibaut Courtois", "Pedri", "Lamine Yamal", "Lionel Messi", "Khvicha Kvaratskhelia", "Ousmane Dembélé", "Vitinha",
    "Joshua Kimmich", "Julián Álvarez", "Gabriel Magalhães", "Martin Ødegaard", "Declan Rice", "Lautaro Martínez",
    "Bruno Guimarães", "Bruno Fernandes", "Désiré Doué", "Nuno Mendes", "Achraf Hakimi", "Yan Diomande", "Florian Wirtz",
    "Isco", "Virgil van Dijk", "Fermín López", "Luis Díaz", "Dayot Upamecano", "Nico Paz",
    "Nicolò Barella", "João Neves", "Enzo Fernández", "Ryan Gravenberch", "Trent Alexander-Arnold", "Marc Cucurella",
    "Pau Cubarsí", "Willian Pacho",
]

# tetos apontados pelo usuário (rodada 21): bons jogadores, mas não craques mundiais — no máximo isto
REFERENCE_CEILINGS: Dict[str, int] = {
    "James Maddison": 85, "Santiago Giménez": 85, "Gabriel Jesus": 85, "Benjamin Šeško": 85, "Dušan Vlahović": 85,
    "Frenkie de Jong": 85, "Jarrad Branthwaite": 85, "Jamal Musiala": 85, "Alexander Isak": 85, "Serge Gnabry": 85,
    "Marcus Rashford": 85, "Christopher Nkunku": 85, "Hugo Ekitiké": 85, "Maxence Lacroix": 87,
}

# rodada 22: NOTAS-ALVO de referência (aproximação de consenso — jogos de futebol/imprensa — feita para CALIBRAR, não
# é dado medido). Servem para (1) escolher os pesos e (2) aprender a CORREÇÃO dos vieses sistemáticos da régua
# (idade, liga, minutos, posição): a correção vale para TODOS os jogadores, não só para estes. Edite à vontade.
REFERENCE_TARGETS: Dict[str, int] = {
    # goleiros
    "Thibaut Courtois": 89, "Alisson": 88, "Gianluigi Donnarumma": 88, "Jan Oblak": 87, "Mike Maignan": 87,
    "David Raya": 86, "Emiliano Martínez": 86, "Gregor Kobel": 85, "Diogo Costa": 85, "Marc-André ter Stegen": 85,
    "Joan García": 84, "Unai Simón": 84, "Yann Sommer": 84, "Guglielmo Vicario": 84, "André Onana": 81,
    # zagueiros
    "Virgil van Dijk": 89, "William Saliba": 87, "Gabriel Magalhães": 87, "Rúben Dias": 87, "Antonio Rüdiger": 86,
    "Alessandro Bastoni": 86, "Marquinhos": 85, "Willian Pacho": 85, "Ibrahima Konaté": 85, "Jonathan Tah": 85,
    "Dayot Upamecano": 85, "Éder Militão": 85, "Joško Gvardiol": 85, "Pau Cubarsí": 84, "Kim Min-jae": 84,
    "Ronald Araújo": 84, "Dean Huijsen": 83, "Piero Hincapié": 83, "Maxence Lacroix": 82, "Riccardo Calafiori": 82,
    "Jarrad Branthwaite": 81, "Murillo": 81, "Luka Vušković": 77, "Mario Vušković": 75,
    # laterais
    "Achraf Hakimi": 89, "Nuno Mendes": 87, "Trent Alexander-Arnold": 86, "Marc Cucurella": 85, "Jules Koundé": 85,
    "Alejandro Grimaldo": 85, "Reece James": 85, "Jeremie Frimpong": 84, "Theo Hernández": 84, "Pedro Porro": 84,
    "Denzel Dumfries": 84, "Alphonso Davies": 84, "Alejandro Balde": 82, "Diogo Dalot": 81,
    # volantes e meias
    "Rodri": 90, "Vitinha": 89, "Pedri": 89, "Federico Valverde": 88, "Joshua Kimmich": 88, "Declan Rice": 87,
    "Moisés Caicedo": 87, "Bruno Guimarães": 86, "Nicolò Barella": 86, "João Neves": 86, "Ryan Gravenberch": 86,
    "Alexis Mac Allister": 86, "Martín Zubimendi": 86, "Enzo Fernández": 85, "Aurélien Tchouaméni": 85,
    "Scott McTominay": 85, "Frenkie de Jong": 84, "Sandro Tonali": 84, "Fermín López": 84, "Eduardo Camavinga": 83,
    "Teun Koopmeiners": 82, "Elliot Anderson": 82, "Luka Modrić": 82, "Casemiro": 80, "Kobbie Mainoo": 80,
    "Gerson": 80, "Andrey Santos": 79, "Jorginho": 79,
    # meias ofensivos
    "Jude Bellingham": 89, "Martin Ødegaard": 87, "Bruno Fernandes": 87, "Florian Wirtz": 87, "Jamal Musiala": 85,
    "Kevin De Bruyne": 85, "James Maddison": 83, "Isco": 83, "Nico Paz": 82, "Giorgian de Arrascaeta": 80,
    # pontas
    "Lamine Yamal": 90, "Ousmane Dembélé": 90, "Mohamed Salah": 89, "Raphinha": 89, "Vinicius Junior": 89,
    "Michael Olise": 88, "Bukayo Saka": 88, "Khvicha Kvaratskhelia": 87, "Luis Díaz": 86, "Désiré Doué": 85,
    "Rafael Leão": 85, "Nico Williams": 85, "Rodrygo": 84, "Bradley Barcola": 84, "Serge Gnabry": 82,
    "Marcus Rashford": 82, "Takefusa Kubo": 82, "Yan Diomande": 80, "Estêvão": 80,
    # centroavantes
    "Kylian Mbappé": 92, "Erling Haaland": 92, "Harry Kane": 91, "Lautaro Martínez": 89, "Julián Álvarez": 87,
    "Lionel Messi": 87, "Victor Osimhen": 86, "Viktor Gyökeres": 86, "Alexander Isak": 85, "Robert Lewandowski": 85,
    "Marcus Thuram": 85, "Dušan Vlahović": 83, "Hugo Ekitiké": 83, "Benjamin Šeško": 82, "Mateo Retegui": 82,
    "Santiago Giménez": 81, "Christopher Nkunku": 81, "Gabriel Jesus": 80, "Vitor Roque": 79,
}

# rodada 24: alvos acrescentados pela lista do usuário — quem estava ALTO demais (goleiros e laterais de times médios,
# veteranos) e brasileiros/sul-americanos. Mesmo papel dos anteriores: calibrar a régua, não substituir a medição.
REFERENCE_TARGETS.update({
    # goleiros que estavam inflados
    "Uğurcan Çakır": 84, "Joan García": 83, "Mile Svilar": 84, "Gregor Kobel": 84, "Caoimhín Kelleher": 82,
    "Marco Carnesecchi": 82, "Senne Lammens": 80, "Lukáš Horníček": 76, "Konstantinos Tzolakis": 74, "Hugo Souza": 76,
    "Bento": 76, "Rafael": 75, "Weverton": 76, "Fábio": 74,
    # laterais e zagueiros de clubes médios
    "Federico Dimarco": 86, "Alejandro Grimaldo": 84, "Matheus Nunes": 83, "João Cancelo": 83, "Luke Shaw": 79,
    "Maximilian Mittelstädt": 80, "David Raum": 81, "Waldemar Anton": 80, "Marcos Senesi": 79, "Jan Paul van Hecke": 80,
    "Nico Schlotterbeck": 85, "Cristian Romero": 85, "Gleison Bremer": 84, "Wesley": 80, "Vitor Reis": 76,
    "Alex Sandro": 76, "Guilherme Arana": 77, "Léo Ortiz": 78, "Fabrício Bruno": 76,
    # meias e atacantes de times médios
    "Ollie Watkins": 83, "Jarrod Bowen": 82, "Serhou Guirassy": 83, "Kiernan Dewsbury-Hall": 78, "James Garner": 79,
    "Deniz Undav": 80, "Leandro Trossard": 81,
    # veteranos (a idade não pode inflar)
    "Mohamed Salah": 87, "Casemiro": 79, "Robert Lewandowski": 84, "Luka Modrić": 81, "Neymar": 80,
    # Brasil e América do Sul
    "Matheus Pereira": 82, "Kaio Jorge": 79, "Gerson": 80, "Lucas Paquetá": 82, "Endrick": 78, "Gabriel Martinelli": 84,
    "João Pedro": 84, "Igor Thiago": 81, "Pedro": 79, "Giorgian de Arrascaeta": 81, "Estêvão": 80,
    "Bruno Henrique": 76, "Everton Ribeiro": 74, "Philippe Coutinho": 76, "Lucas Moura": 75, "Hulk": 75,
    "Gabriel Barbosa": 75, "Luiz Henrique": 79, "Savinho": 81, "Vitor Roque": 79,
})

# rodada 25: âncoras da lista do usuário (motor por atributos). Corrigem a ESCALA; não forçam a nota de ninguém.
REFERENCE_TARGETS.update({
    "Kylian Mbappé": 92, "Harry Kane": 92, "Ousmane Dembélé": 90, "Lamine Yamal": 90, "Pedri": 90,
    "Jude Bellingham": 90, "Khvicha Kvaratskhelia": 90, "Michael Olise": 89, "Luis Díaz": 89, "Nico Paz": 86,
    "Julián Álvarez": 88, "Ferran Torres": 84, "Bradley Barcola": 84, "Matheus Pereira": 82,
    "Giorgian de Arrascaeta": 82, "Neymar": 82, "Lionel Messi": 85, "Luiz Araújo": 76, "Keny Arroyo": 78,
    "Fermín López": 85, "Achraf Hakimi": 89, "Nuno Mendes": 88, "Gabriel Magalhães": 88, "Virgil van Dijk": 87,
    "Maxence Lacroix": 85, "Joshua Kimmich": 87, "Rodri": 89, "Marc Cucurella": 87, "Renan Lodi": 81,
    "Kaiki Bruno": 79, "Natanael": 71, "Gabriel Rojas": 72, "Lucas Daniel Romero": 77, "Lucas Romero": 77,
    "Thibaut Courtois": 90, "Manuel Neuer": 85, "David Raya": 88, "Zé Lucas": 70, "Kauã Moraes": 69, "Melk": 70,
    "Néiser Villarreal": 65,
    # a lista "melhores do mundo" com poucos minutos ou fora do auge não pode ficar no topo
    "Karim Benzema": 80, "Artem Dovbyk": 79, "James Maddison": 80, "Raheem Sterling": 76, "Dejan Kulusevski": 80,
    "Christian Nørgaard": 77, "Tim Kleindienst": 77, "Riyad Mahrez": 77, "Kingsley Coman": 80,
    "Kepa Arrizabalaga": 77, "Oleksandr Zinchenko": 76, "Gaëtan Laborde": 75, "Simon Banza": 76,
})

# potencial-alvo (mesma ideia: calibrar a escala do potencial dos jovens)
POTENTIAL_TARGETS: Dict[str, int] = {
    "Lamine Yamal": 95, "Nico Paz": 90, "Zé Lucas": 86, "Kaiki Bruno": 85, "Natanael": 76, "Kauã Moraes": 77,
    "Melk": 83, "Néiser Villarreal": 80,
    # rodada 26: os jovens de maior potencial do Cruzeiro (lista do usuário) e jovens de elite
    "Eduardo Pape": 84, "Keny Arroyo": 87, "Felipe Morais": 83, "Jonathan Jesus": 82, "Otávio": 85,
    "Désiré Doué": 92, "Arda Güler": 91, "Kenan Yıldız": 90, "Pau Cubarsí": 91, "Warren Zaïre-Emery": 89,
    "Lennart Karl": 90, "Franco Mastantuono": 89, "Estêvão": 90, "Endrick": 88,
}

# rodada 26: jovens de elite estavam baixos (Yamal 81, Doué 82, Güler 82) — âncoras da qualidade ATUAL
REFERENCE_TARGETS.update({
    "Désiré Doué": 86, "Arda Güler": 85, "Kenan Yıldız": 85, "Pau Cubarsí": 85, "Dean Huijsen": 83,
    "Warren Zaïre-Emery": 82, "Luka Vušković": 80, "Lennart Karl": 79, "Franco Mastantuono": 78,
    "Cristiano Ronaldo": 80, "Rodrigo De Paul": 80, "Sadio Mané": 78, "Riyad Mahrez": 76, "Leon Goretzka": 82,
    "Hakan Çalhanoğlu": 84, "Granit Xhaka": 81, "Ivan Toney": 80, "Rúben Neves": 80,
    "Sergej Milinković-Savić": 81, "Yannick Carrasco": 76, "Kingsley Coman": 79,
})

FAMILY = {"GK": "GK", "CB": "CB", "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB", "DM": "MID", "CM": "MID",
          "AM": "AM", "LM": "WIDE", "RM": "WIDE", "LW": "WIDE", "RW": "WIDE", "ST": "ST"}

# teto por família (no FC os melhores laterais ficam abaixo dos melhores atacantes)
FAMILY_CAP = {"ST": 94, "WIDE": 93, "AM": 92, "MID": 92, "CB": 91, "GK": 90, "FB": 89}

# colocação GLOBAL (régua padronizada por posição) → overall. Calibrada para um universo de ~20 mil jogadores; em
# universos menores a colocação é reescalada (o 1º de uma base pequena não vira 94 automaticamente).
LADDER_R = [1, 2, 3, 5, 10, 20, 40, 80, 150, 300, 600, 1200]
LADDER_O = [94, 93, 92, 91, 90, 88.5, 87, 85, 83, 81, 78, 75]
N_REF = 20000
# abaixo da escada: percentil (dentro do resto) → overall
REST_P = [0.0, .05, .25, .50, .75, .90, 1.0]
REST_O = [38, 46, 55, 62, 68, 72, 75]
# legado (rodada 20) — mantido para leitura de relatórios antigos
CURVE_P = [0.0, .05, .20, .40, .60, .75, .85, .92, .96, .985, .995, .9985, 1.0]
CURVE_O = [38, 46, 54, 60, 65, 69, 73, 77, 81, 85, 88, 90.5, 94]


def _col(u: pd.DataFrame, name: str) -> pd.Series:
    """Coluna numérica (ou toda vazia, se a fonte não traz) — nunca um escalar solto."""
    if name in u:
        return pd.to_numeric(u[name], errors="coerce")
    return pd.Series(np.nan, index=u.index, dtype=float)


def age_factor(age: pd.Series) -> pd.Series:
    """Corrige o valor de mercado pela idade: ≥ 28 anos o mercado desconta a idade (×1 a ×2,1 aos 37); ≤ 22 o preço
    embute projeção (×0,75 aos 18)."""
    a = pd.to_numeric(age, errors="coerce")
    # rodada 26: a lista parecia de 2022 (Messi 93, Salah 92, De Bruyne 90, Cristiano 87 aos 41) — o "desconto de
    # veterano" inflava quem já está em queda. Agora ×1,10 no máximo; e o jovem não é mais descontado (Yamal tinha 81)
    up = 1 + .02 * (a - 27).clip(lower=0, upper=5)
    return up.fillna(1.0)


def _pct(values: pd.Series, groups: pd.Series, reference: Optional[pd.DataFrame] = None, col: str = "") -> pd.Series:
    """Percentil (0–100) dentro da família; com `reference`, contra a distribuição de referência (mesma régua)."""
    v = pd.to_numeric(values, errors="coerce")
    if reference is None:
        return v.groupby(groups).rank(pct=True) * 100
    out = pd.Series(np.nan, index=v.index)
    for fam, idx in v.groupby(groups).groups.items():
        ref = pd.to_numeric(reference.loc[reference["_fam"] == fam, col], errors="coerce").dropna().sort_values().values
        if not len(ref):
            continue
        x = v.loc[idx]
        out.loc[idx] = np.searchsorted(ref, x.values, side="right") / len(ref) * 100
        out.loc[idx[x.isna()]] = np.nan
    return out


def previous_season_minutes(u: pd.DataFrame) -> pd.Series:
    """Maior minutagem entre as 3 temporadas mais recentes do histórico (só para quem jogou pouco no último ano)."""
    out = pd.Series(np.nan, index=u.index)
    if "historico_temporadas" not in u:
        return out
    m12 = _col(u, "minutos_12m").fillna(0)
    for i in u.index[m12 < 1350]:
        v = u.at[i, "historico_temporadas"]
        try:
            seasons = json.loads(v) if isinstance(v, str) else (v if isinstance(v, list) else [])
        except Exception:
            continue
        mins = [pd.to_numeric(x.get("minutos"), errors="coerce") for x in seasons[-2:] if isinstance(x, dict)]
        mins = [m for m in mins if pd.notna(m)]
        if mins:
            out.at[i] = float(max(mins))
    return out


def components(u: pd.DataFrame, reference: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """R, P, T, L, disponibilidade e peso dos minutos por atleta (sem os pesos)."""
    d = pd.DataFrame(index=u.index)
    d["_fam"] = (u["papel"] if "papel" in u else pd.Series("", index=u.index)).map(FAMILY).fillna("")
    val = _col(u, "valor_mercado_eur")
    # pico de 3 anos vale 80% até 30 anos; depois, 50% (o pico de quem tem 33+ é de outra fase da carreira)
    peak = _col(u, "valor_pico_3a_eur") * np.where(_col(u, "idade").fillna(25) >= 31, .5, .8)
    rep_val = pd.concat([val, peak], axis=1).max(axis=1, skipna=True)
    rep_val = rep_val.where(rep_val > 0)
    d["_rep_val"] = np.log1p(rep_val * age_factor(_col(u, "idade")))
    raw = _col(u, "_perf_raw")
    conf = _col(u, "_conf").fillna(0)
    lvl = _col(u, "_lvl")
    lvl = lvl.fillna(_col(u, "nivel_competicao_principal")).fillna(.45).clip(0, 1)
    perf = 50 + (raw - 50) * conf
    d["_perf_adj"] = perf * (.55 + .45 * lvl)
    d["_rank_nota"] = _col(u, "nota_rankings")
    d["_ext"] = _col(u, "nota_externa")
    m12 = _col(u, "minutos_12m").fillna(0)
    rating = _col(u, "rating_12m")
    # nota FotMob ajustada pela liga: 0,9 ponto entre a liga mais forte e a mais fraca (7,3 na Premier ≈ 7,8 abaixo)
    # rodada 26: 1,8 ponto entre a liga mais forte e a mais fraca (antes 0,9): 7,4 na MLS/Arábia ≠ 7,4 na Premier
    d["_rating_adj"] = (rating + 1.8 * (lvl - .7)).where(m12 >= 450)
    d["L"] = (lvl * 100).round(1)
    # rodada 24: craque que passou meses lesionado (Rodrygo, Militão, Alisson) não "some": a disponibilidade usa o
    # maior entre o último ano e 85% da temporada anterior — lesão longa ainda pesa, mas não apaga a qualidade
    prev = _col(u, "minutos_temporada_anterior").fillna(0)
    # rodada 25b: a temporada anterior só ajuda quem JÁ VOLTOU a jogar (300+ min no ano). Antes ela fazia Benzema (160
    # min) e Luuk de Jong (39 min) parecerem titulares e irem para o topo da lista.
    m_eff = m12.where(m12 < 300, pd.concat([m12, .5 * prev], axis=1).max(axis=1))
    d["_m"] = .35 + .65 * (m_eff / 1350).clip(0, 1)
    d["_avail"] = (m_eff / 1800).clip(0, 1)
    d["_age"] = _col(u, "idade")
    d["_elig"] = raw.notna() | rep_val.notna()
    if "qualidade" in u:                                  # quem a régua antiga deixou sem nota (0 min no ano, sem dado)
        d["_elig"] &= pd.to_numeric(u["qualidade"], errors="coerce").notna()
    ref = reference
    d["R"] = _pct(d["_rep_val"].where(d["_elig"]), d["_fam"], ref, "_rep_val")
    p_stats = _pct(d["_perf_adj"].where(d["_elig"]), d["_fam"], ref, "_perf_adj")
    p_rank = _pct(d["_rank_nota"].where(d["_elig"]), d["_fam"], ref, "_rank_nota")
    p_ext = _pct(d["_ext"].where(d["_elig"]), d["_fam"], ref, "_ext")
    parts = pd.concat([p_stats.rename("s"), p_rank.rename("r"), p_ext.rename("e")], axis=1)
    w = pd.DataFrame({"s": .6 * parts["s"].notna(), "r": .3 * parts["r"].notna(), "e": .1 * parts["e"].notna()})
    d["P"] = (parts.fillna(0) * w).sum(axis=1) / w.sum(axis=1).replace(0, np.nan)
    d["T"] = _pct(d["_rating_adj"].where(d["_elig"]), d["_fam"], ref, "_rating_adj")
    return d


def zscore(c: pd.DataFrame, w: Dict[str, float]) -> pd.Series:
    """Média ponderada dos componentes disponíveis (0–100). A reputação pesa menos para quem jogou pouco."""
    has_r, has_t, has_p = c["R"].notna(), c["T"].notna() if "T" in c else pd.Series(False, index=c.index), c["P"].notna()
    wr = w.get("wR", 0) * c["_m"] * has_r
    wt = w.get("wT", 0) * has_t
    wp = w.get("wP", 0) * has_p
    num = wr * c["R"].fillna(0) + wt * c.get("T", pd.Series(0, index=c.index)).fillna(0) + wp * c["P"].fillna(0) \
        + w.get("wL", 0) * c["L"]
    den = wr + wt + wp + w.get("wL", 0)
    z = num / den.replace(0, np.nan)
    return z.where(c["_elig"] & (has_p | has_r | has_t))


def standardize(z: pd.Series, comps: pd.DataFrame, fam_stats: Optional[Dict[str, Any]] = None) -> tuple:
    """Z → régua padronizada por família, encolhida pela disponibilidade. Devolve (s, estatísticas da família)."""
    if fam_stats is None:
        g = z.groupby(comps["_fam"])
        fam_stats = {f: (float(m), float(sd) if sd and sd > 0 else 1.0) for f, m, sd in zip(g.mean().index, g.mean(), g.std())}
    mu = comps["_fam"].map(lambda f: fam_stats.get(f, (50.0, 15.0))[0])
    sd = comps["_fam"].map(lambda f: fam_stats.get(f, (50.0, 15.0))[1])
    s = (z - mu) / sd
    s = s * comps["_fam"].map(FAMILY_SPREAD).fillna(1.0)
    avail = comps["_avail"] ** .7
    s = s * (.45 + .55 * avail)                          # quem jogou pouco no ano não chega ao topo
    if "_age" in comps:
        s = s + age_prior(comps["_age"], comps["_avail"], comps.get("L"))
    return s, fam_stats


def age_prior(age: pd.Series, avail: pd.Series, level: Optional[pd.Series] = None) -> pd.Series:
    """Rodada 26 — o que os números por jogo não medem (velocidade, explosão, recuperação): depois dos 31 o corpo cai
    mesmo quando a produção ainda aparece (−0,08 na régua por ano depois dos 31, até −0,48); um jovem de até 22 anos
    TITULAR num clube/liga forte já prova nível acima do que os números de um ano mostram (+0,035 por ano abaixo de 23).
    É uma estimativa assumida — está descrita na explicação da nota."""
    a = pd.to_numeric(age, errors="coerce")
    old = -(.08 * (a - 31).clip(lower=0, upper=6))
    lv = level.fillna(45) if level is not None else pd.Series(45.0, index=a.index)
    young = .035 * (23 - a).clip(lower=0, upper=5) * (avail.fillna(0) >= .75) * (lv >= 60)
    return (old + young).fillna(0.0)


def ladder(s: pd.Series, ref_sorted: Optional[np.ndarray] = None) -> pd.Series:
    """Colocação global → overall. `ref_sorted` = régua de referência (ordem crescente) para medir outro grupo."""
    pool = np.sort(s.dropna().values) if ref_sorted is None else ref_sorted
    n = len(pool)
    out = pd.Series(np.nan, index=s.index)
    if n == 0:
        return out
    ok = s.notna()
    rank = n - np.searchsorted(pool, s[ok].values, side="right") + 1          # 1 = melhor
    scale = max(1.0, N_REF / max(n, 1))                                     # base pequena: reescala a colocação
    r_eff = np.maximum(rank * scale, 1.0)
    top_r = LADDER_R[-1]
    lad = np.interp(np.log(r_eff), np.log(LADDER_R), LADDER_O)
    n_rest = max(n * scale - top_r, 1.0)
    p_rest = np.clip(1 - (r_eff - top_r) / n_rest, 0, 1)
    rest = np.interp(p_rest, REST_P, REST_O)
    out.loc[ok] = np.where(r_eff <= top_r, lad, rest)
    return out


def curve(p: pd.Series) -> pd.Series:
    """(legado) percentil (0–1) → overall."""
    return pd.Series(np.interp(p.fillna(np.nan).values, CURVE_P, CURVE_O), index=p.index).where(p.notna()).round(0)


def _resolve(u: pd.DataFrame, names: Sequence[str]) -> Dict[str, int]:
    """Craque de referência → linha do universo (homônimo: o de maior valor de mercado)."""
    from src.data_lake.ids import player_core

    core = u["_core"].astype(str) if "_core" in u else u["nome"].map(player_core)
    val = _col(u, "valor_mercado_eur").fillna(0)
    out = {}
    for n in names:
        c = player_core(n)
        hit = core[core == c]
        if hit.empty:
            continue
        out[n] = int(val.loc[hit.index].idxmax())
    return out


FAMS = ("GK", "CB", "FB", "MID", "AM", "WIDE", "ST")
CORR_RIDGE = 3.0
CORR_SHRINK = .85
CORR_CLIP = 1.2
# rodada 24: goleiros e laterais tinham a mesma "largura" de régua que atacantes — com ~1 goleiro em cada 11 atletas,
# o topo ficava cheio de goleiros e laterais de times médios (Çakır 91, Dimarco 88). A régua dessas famílias é
# estreitada (o melhor goleiro ainda chega ao topo da posição, mas o 15º goleiro não vira 88).
FAMILY_SPREAD = {"GK": .78, "FB": .86, "CB": .93, "MID": 1.0, "AM": 1.0, "WIDE": 1.0, "ST": 1.0}


def corr_features(comps: pd.DataFrame, age: pd.Series) -> pd.DataFrame:
    """Variáveis da correção: idade (e idade²), nível, disponibilidade, reputação, desempenho, nota e posição."""
    a = (pd.to_numeric(age, errors="coerce").fillna(26) - 26) / 5
    X = pd.DataFrame({"idade": a, "idade2": a ** 2, "nivel": comps["L"].fillna(45) / 100 - .5,
                      "disp": comps["_avail"].fillna(0) - .7, "R": comps["R"].fillna(50) / 100 - .5,
                      "P": comps["P"].fillna(50) / 100 - .5, "T": comps["T"].fillna(50) / 100 - .5,
                      "semT": comps["T"].isna().astype(float)}, index=comps.index)
    for f in FAMS:
        X[f"f_{f}"] = (comps["_fam"] == f).astype(float)
    return X


def fit_correction(s: pd.Series, ovr: pd.Series, comps: pd.DataFrame, age: pd.Series,
                   targets: Dict[str, int], idx: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """Aprende, nos jogadores de referência, quanto a régua erra em função de idade/liga/minutos/posição (em unidades
    da régua padronizada `s`, para manter a distribuição: só ~10 jogadores com 90+). Regressão ridge; None se < 25."""
    pool = pd.DataFrame({"s": s, "o": ovr}).dropna().sort_values("s")
    if len(pool) < 50:
        return None
    o_sorted, s_sorted = np.maximum.accumulate(pool["o"].values), pool["s"].values
    rows, ys = [], []
    X_all = corr_features(comps, age)
    for name, i in idx.items():
        if i not in s.index or pd.isna(s.loc[i]) or name not in targets:
            continue
        t = float(targets[name])
        s_t = float(np.interp(t, o_sorted + np.arange(len(o_sorted)) * 1e-9, s_sorted))   # régua que daria o alvo
        rows.append(X_all.loc[i].values)
        ys.append(s_t - float(s.loc[i]))
    if len(rows) < 25:
        return None
    X, y = np.asarray(rows, float), np.asarray(ys, float)
    Xb = np.column_stack([np.ones(len(X)), X])
    reg = np.eye(Xb.shape[1]) * CORR_RIDGE
    reg[0, 0] = 0
    beta = np.linalg.solve(Xb.T @ Xb + reg, Xb.T @ y)
    return {"beta": [float(b) for b in beta], "cols": ["const"] + list(X_all.columns), "n": int(len(rows)),
            "encolhimento": CORR_SHRINK, "limite": CORR_CLIP}


def apply_correction(s: pd.Series, comps: pd.DataFrame, age: pd.Series, corr: Optional[Dict[str, Any]]) -> pd.Series:
    if not corr:
        return s
    X = corr_features(comps, age)
    cols = corr.get("cols") or []
    beta = np.asarray(corr.get("beta") or [], float)
    if len(beta) != len(cols):
        return s
    Xm = np.column_stack([np.ones(len(X))] + [X[c].values if c in X else np.zeros(len(X)) for c in cols[1:]])
    c = np.clip(Xm @ beta * float(corr.get("encolhimento", CORR_SHRINK)), -float(corr.get("limite", CORR_CLIP)),
                float(corr.get("limite", CORR_CLIP)))
    return s + pd.Series(c, index=s.index).where(s.notna())


def _overall(comps: pd.DataFrame, w: Dict[str, float], corr: Optional[Dict[str, Any]] = None,
             age: Optional[pd.Series] = None) -> pd.Series:
    s, _ = standardize(zscore(comps, w), comps)
    if corr and age is not None:
        s = apply_correction(s, comps, age, corr)
    ovr = ladder(s)
    cap = comps["_fam"].map(FAMILY_CAP).fillna(92)
    return ovr.clip(upper=cap).round(0)


def all_targets() -> Dict[str, int]:
    """Alvos + tetos do usuário (teto vira alvo = teto − 1 quando o nome não tem alvo próprio)."""
    t = dict(REFERENCE_TARGETS)
    for n, cap in REFERENCE_CEILINGS.items():
        t[n] = min(t.get(n, cap - 1), cap)
    return t


def calibrate(u: pd.DataFrame, comps: pd.DataFrame, anchors: Sequence[str] = REFERENCE_STARS,
              ceilings: Optional[Dict[str, int]] = None, targets: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Grade de pesos (rodada 22): para cada combinação, aprende a correção nos jogadores de referência e mede o ERRO
    MÉDIO contra as notas-alvo (com validação: a correção é aprendida em metade e medida na outra, e vice-versa) +
    3 × o quanto os nomes com TETO passam do teto; exige correlação ≥ 0,55 com o desempenho de quem joga muito."""
    ceilings = REFERENCE_CEILINGS if ceilings is None else ceilings
    targets = all_targets() if targets is None else targets
    found = _resolve(u, anchors)
    capped = _resolve(u, list(ceilings))
    tidx = _resolve(u, list(targets))
    age = _col(u, "idade")
    m12 = _col(u, "minutos_12m").fillna(0)
    regulars = comps.index[(m12 >= 1800) & comps["P"].notna()]
    names = sorted(tidx)
    half_a, half_b = set(names[0::2]), set(names[1::2])
    best, best_obj, grid, best_corr = dict(DEFAULT_WEIGHTS), -1e9, [], None
    for wR in (.2, .3, .4, .5):
        for wT in (.15, .25, .35):
            for wL in (.10, .15):
                wP = round(1 - wR - wT - wL, 2)
                if wP < .1:
                    continue
                w = {"wR": wR, "wP": wP, "wT": wT, "wL": wL}
                z = zscore(comps, w)
                s0, _ = standardize(z, comps)
                o0 = ladder(s0)
                corr_full = fit_correction(s0, o0, comps, age, targets, tidx)
                # erro fora da amostra: aprende numa metade, mede na outra
                errs = []
                for fit_on, test_on in ((half_a, half_b), (half_b, half_a)):
                    c_half = fit_correction(s0, o0, comps, age, targets, {n: tidx[n] for n in fit_on})
                    o_half = ladder(apply_correction(s0, comps, age, c_half)).clip(
                        upper=comps["_fam"].map(FAMILY_CAP).fillna(92)).round(0)
                    errs += [abs(float(o_half.loc[tidx[n]]) - targets[n]) for n in test_on if pd.notna(o_half.loc[tidx[n]])]
                ovr = ladder(apply_correction(s0, comps, age, corr_full)).clip(
                    upper=comps["_fam"].map(FAMILY_CAP).fillna(92)).round(0)
                stars = [min(float(ovr.loc[i]), 92.0) for i in found.values() if pd.notna(ovr.loc[i])]
                excess = [max(0.0, float(ovr.loc[i]) - ceilings[n]) for n, i in capped.items() if pd.notna(ovr.loc[i])]
                corr = float(z.loc[regulars].corr(comps.loc[regulars, "P"], method="spearman")) if len(regulars) > 20 else 1.0
                ok = corr >= .55 or not np.isfinite(corr)
                mae = float(np.mean(errs)) if errs else None
                if mae is not None:
                    obj = -mae - 3 * (np.mean(excess) if excess else 0.0) - (0 if ok else 50)
                else:                                 # base sem referências suficientes: critério antigo
                    obj = (np.mean(stars) if stars else 0.0) - 3 * (np.mean(excess) if excess else 0.0) - (0 if ok else 50)
                grid.append({**w, "erro_medio_alvos": round(mae, 2) if mae is not None else None,
                             "craques_overall_medio": round(float(np.mean(stars)), 1) if stars else None,
                             "tetos_estourados_medio": round(float(np.mean(excess)), 2) if excess else 0.0,
                             "correlacao_desempenho": round(corr, 3) if np.isfinite(corr) else None, "aceito": bool(ok)})
                if obj > best_obj:
                    best, best_obj, best_corr = w, obj, corr_full
    return {"pesos": best, "correcao": best_corr, "grade": grid, "encontrados": found, "tetos": capped, "alvos": tidx}


def finalize_overall(u: pd.DataFrame, calibrate_now: bool = True, reference: Optional[pd.DataFrame] = None,
                     weights: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    """Recalcula `qualidade` como OVERALL 0–100. Guarda a nota antiga em `qualidade_base` e os componentes."""
    if u is None or u.empty:
        return u
    out = u.copy()
    if "minutos_temporada_anterior" not in out:
        out["minutos_temporada_anterior"] = previous_season_minutes(out)
    if "qualidade_base" not in out:
        out["qualidade_base"] = pd.to_numeric(out.get("qualidade"), errors="coerce")
    comps = components(out, reference)
    report: Dict[str, Any] = {}
    corr = None
    # rodada 25b: o motor por atributos (rating_engine) ficou MUITO pior na base real (jogadores com 0–40 minutos e
    # ligas fracas no topo). A nota volta ao modelo anterior; os atributos/estilo do motor ficam só como LEITURA.
    try:
        from src.scout import rating_engine as RE

        eng = RE.compute(out)
        for c in eng.columns:
            if c.startswith("atr2_") or c in ("estilo", "dificuldade_ajuste"):
                out[c] = eng[c]
    except Exception:
        pass
    if weights is None:
        if calibrate_now and reference is None:
            report = calibrate(out, comps)
            weights = report["pesos"]
            corr = report.get("correcao")
        else:
            weights = load_weights()
            corr = load_correction()
    age = _col(out, "idade")
    z = zscore(comps, weights)
    if reference is not None and "_ovr_s" in reference and "_ovr_z" in reference:
        rz = pd.to_numeric(reference["_ovr_z"], errors="coerce")
        g = rz.groupby(reference["_fam"])
        stats = {f: (float(m), float(sd) if sd and sd > 0 else 1.0) for f, m, sd in zip(g.mean().index, g.mean(), g.std())}
        s, _ = standardize(z, comps, stats)
        s = apply_correction(s, comps, age, corr)
        ovr = ladder(s, np.sort(pd.to_numeric(reference["_ovr_s"], errors="coerce").dropna().values))
    else:
        s, _ = standardize(z, comps)
        s = apply_correction(s, comps, age, corr)
        ovr = ladder(s)
    cap = comps["_fam"].map(FAMILY_CAP).fillna(92)
    out["qualidade"] = ovr.clip(upper=cap).clip(upper=minutes_cap(out)).round(0)
    if "so_base" in out:                     # rodada 22: só jogos de base → fica a ESTIMADA pelo nível de base
        base_only = out["so_base"].fillna(False).astype(bool)
        out.loc[base_only, "qualidade"] = pd.to_numeric(out.loc[base_only, "qualidade_base"], errors="coerce")
    out["ovr_reputacao"] = comps["R"].round(0)
    out["ovr_desempenho"] = comps["P"].round(0)
    out["ovr_nota_fotmob"] = comps["T"].round(0)
    out["ovr_nivel"] = comps["L"]
    out["ovr_disponibilidade"] = (comps["_avail"] * 100).round(0)
    out["_ovr_z"] = z
    out["_ovr_s"] = s
    out["_fam"] = comps["_fam"]
    for c in ("_rep_val", "_perf_adj", "_rank_nota", "_ext", "_rating_adj"):     # régua para medir o elenco igual
        out[c] = comps[c]
    src = out.get("fonte_qualidade", pd.Series("", index=out.index)).fillna("").astype(str)
    out["fonte_qualidade"] = np.where(
        out["qualidade"].notna() & ~out.get("so_base", pd.Series(False, index=out.index)).fillna(False).astype(bool),
        f"overall: reputação ajustada pela idade ({weights.get('wR', 0):.0%}) + desempenho na função "
        f"({weights.get('wP', 0):.0%}) + nota FotMob ajustada pela liga ({weights.get('wT', 0):.0%}) + nível "
        f"({weights.get('wL', 0):.0%}), padronizado por posição e pelos minutos do ano; teto pela minutagem", src)
    out = _recompute_potential(out)
    if report:
        save_report(out, report)
    return out


def minutes_cap(u: pd.DataFrame) -> pd.Series:
    """Rodada 25b: teto pela minutagem do último ano — "não pode receber 91 com 120 minutos". 0–300 min → 72;
    cresce até 1.800 min, onde o teto some (99)."""
    m12 = _col(u, "minutos_12m").fillna(0)
    return (72 + 27 * ((m12 - 300) / 1500).clip(0, 1)).where(m12 < 1800, 99.0)


def calibrate_v2(u: pd.DataFrame, comps: pd.DataFrame, z: pd.Series) -> Dict[str, Any]:
    """Calibração do motor por atributos: aprende a correção de vieses (idade, nível, minutos, posição) nos jogadores
    de referência, medindo o erro FORA da amostra (aprende numa metade, mede na outra). Corrige a escala, não força
    nomes: cada jogador fica com a nota dos números dele + a correção sistemática do seu grupo."""
    targets = all_targets()
    tidx = _resolve(u, list(targets))
    age = _col(u, "idade")
    s0, _ = standardize(z, comps)
    o0 = ladder(s0)
    names = sorted(tidx)
    half_a, half_b = set(names[0::2]), set(names[1::2])
    errs = []
    cap = comps["_fam"].map(FAMILY_CAP).fillna(92)
    for fit_on, test_on in ((half_a, half_b), (half_b, half_a)):
        c_half = fit_correction(s0, o0, comps, age, targets, {n: tidx[n] for n in fit_on})
        o_half = ladder(apply_correction(s0, comps, age, c_half)).clip(upper=cap).round(0)
        errs += [abs(float(o_half.loc[tidx[n]]) - targets[n]) for n in test_on if pd.notna(o_half.loc[tidx[n]])]
    corr = fit_correction(s0, o0, comps, age, targets, tidx)
    raw_err = [abs(float(o0.loc[tidx[n]]) - targets[n]) for n in names if pd.notna(o0.loc[tidx[n]])]
    mae = float(np.mean(errs)) if errs else None
    return {"pesos": {"motor": "atributos por posição", "wR": 0.0, "wP": .75, "wT": .05, "wL": 0.0},
            "correcao": corr, "encontrados": _resolve(u, REFERENCE_STARS), "tetos": _resolve(u, list(REFERENCE_CEILINGS)),
            "alvos": tidx,
            "grade": [{"motor": "atributos", "erro_medio_alvos": round(mae, 2) if mae is not None else None,
                       "erro_sem_correcao": round(float(np.mean(raw_err)), 2) if raw_err else None,
                       "aceito": True}]}


def _recompute_potential(d: pd.DataFrame) -> pd.DataFrame:
    """Rodada 22: potencial completo (src/scout/potential.py) — idade × talento por posição, ao lado do overall."""
    try:
        from src.scout import potential as POT

        fam = d["_fam"] if "_fam" in d else None
        p = POT.compute(d, fam)
        # rodada 25: calibra o tamanho do crescimento pelos potenciais-alvo dos jovens (k entre 0,8 e 1,6)
        idx = _resolve(d, list(POTENTIAL_TARGETS))
        q = _col(d, "qualidade")
        best_k, best_e = 1.0, None
        if len(idx) >= 3:
            for k in np.arange(.8, 1.65, .05):
                errs = [abs(min(POT.POT_CAP, float(q.loc[i]) + k * float(p.at[i, "potencial_crescimento"])) - POTENTIAL_TARGETS[n])
                        for n, i in idx.items() if pd.notna(q.loc[i]) and pd.notna(p.at[i, "potencial_crescimento"])]
                e = float(np.mean(errs)) if errs else None
                if e is not None and (best_e is None or e < best_e - 1e-9):
                    best_k, best_e = float(k), e
        if best_k != 1.0:
            g = p["potencial_crescimento"] * best_k
            p["potencial"] = (q + g).clip(upper=POT.POT_CAP).where(q.notna(), p["potencial"]).round(0)
            p["potencial_crescimento"] = g.round(1)
        d.attrs["potencial_k"] = best_k
        for c in p.columns:
            d[c] = p[c]
        # potencial nunca abaixo do overall de hoje
        d["potencial"] = pd.concat([_col(d, "potencial"), q], axis=1).max(axis=1).where(_col(d, "potencial").notna())
        d["potencial_teto"] = d["potencial"]
        return d
    except Exception:
        pass
    return _recompute_potential_old(d)


def _recompute_potential_old(d: pd.DataFrame) -> pd.DataFrame:
    """(rodada 20/21) Teto = overall de hoje + crescimento esperado até ~26 anos."""
    age = _col(d, "idade")
    q = _col(d, "qualidade")
    conf = _col(d, "confianca_pct").fillna(0) / 100
    lvl = _col(d, "_lvl").fillna(.5)
    prec = _col(d, "precocidade").fillna(30) / 100
    youth = _col(d, "selecao_base_jogos").fillna(0)
    years = (26 - age.fillna(30)).clip(lower=0, upper=9)
    growth = years * (.55 + .7 * conf + 1.0 * prec + .35 * (youth > 0)) * (.7 + .5 * lvl)
    d["potencial_teto"] = (q + growth).clip(upper=95).where(q.notna()).round(0)
    return d


def save_report(u: pd.DataFrame, report: Dict[str, Any]) -> None:
    def row(name, i, teto=None):
        q = u.at[i, "qualidade"]
        r = {"craque": name, "no_universo": str(u.at[i, "nome"]), "posicao": str(u.at[i, "papel"]),
             "overall": None if pd.isna(q) else int(q),
             "minutos_12m": None if pd.isna(_col(u, "minutos_12m").get(i)) else int(_col(u, "minutos_12m").get(i))}
        if teto is not None:
            r["teto"] = teto
        return r
    rows = [row(n, i) for n, i in (report.get("encontrados") or {}).items()]
    caps = [row(n, i, REFERENCE_CEILINGS.get(n)) for n, i in (report.get("tetos") or {}).items()]
    missing = [n for n in REFERENCE_STARS if n not in (report.get("encontrados") or {})]
    q = _col(u, "qualidade")
    dist = {"90+": int((q >= 90).sum()), "87+": int((q >= 87).sum()), "85+": int((q >= 85).sum()),
            "80+": int((q >= 80).sum()), "mediana": None if q.dropna().empty else float(q.median())}
    hi = sum(1 for r in rows if (r["overall"] or 0) >= 85)
    over = [r["craque"] for r in caps if r["overall"] is not None and r["overall"] > r["teto"]]
    tg = all_targets()
    tgt_rows = []
    for n, i in (report.get("alvos") or {}).items():
        r = row(n, i)
        r["alvo"] = tg.get(n)
        r["diferenca"] = None if r["overall"] is None or r["alvo"] is None else int(r["overall"] - r["alvo"])
        tgt_rows.append(r)
    diffs = [abs(r["diferenca"]) for r in tgt_rows if r["diferenca"] is not None]
    doc = {"pesos": report["pesos"], "correcao": report.get("correcao"), "grade": report["grade"], "craques": rows,
           "tetos": caps, "alvos": tgt_rows, "erro_medio_alvos": round(float(np.mean(diffs)), 2) if diffs else None,
           "distribuicao": dist, "nao_encontrados": missing,
           "resumo": f"{hi} de {len(rows)} craques com 85+ · {dist['90+']} jogadores com 90+ no universo"
                     + (f" · tetos estourados: {', '.join(over)}" if over else " · nenhum teto estourado")}
    try:
        CALIB_PATH.parent.mkdir(parents=True, exist_ok=True)
        CALIB_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    except OSError:
        pass


def load_weights() -> Dict[str, float]:
    try:
        return dict(json.loads(CALIB_PATH.read_text(encoding="utf-8"))["pesos"])
    except Exception:
        return dict(DEFAULT_WEIGHTS)


def load_correction() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(CALIB_PATH.read_text(encoding="utf-8")).get("correcao")
    except Exception:
        return None


def load_report() -> Optional[Dict[str, Any]]:
    try:
        return json.loads(CALIB_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
