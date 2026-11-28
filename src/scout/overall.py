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

import unicodedata

import numpy as np
import pandas as pd

CALIB_PATH = Path("data/processed/overall_calibration.json")
DEFAULT_WEIGHTS = {"wR": .5, "wP": .2, "wT": .2, "wL": .1}

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

# rodada 27: lista do usuário (Brasil subestimado; a lista dos melhores do mundo ficou "praticamente perfeita" e NÃO
# deve mudar). Alvos de consenso para a correção de vieses (idade, liga, minutos, posição) — corrigem a escala do grupo
REFERENCE_TARGETS.update({
    "Lucas Daniel Romero": 78, "Lucas Romero": 78, "Matheus Pereira": 81, "Kaio Jorge": 79, "Gerson": 78,
    "Fabrício Bruno": 78, "Zé Lucas": 70, "Melk": 69, "Lorenzo": 65, "Pedro Morisco": 77, "Jonathan Jesus": 76,
    "Agustín Giay": 76, "Vitor Roque": 78, "Danilo": 79, "Gabriel Bontempo": 78, "Breno Bidon": 76,
    "Vitão": 74, "Gustavo Henrique": 70, "Kaiki Bruno": 79, "Kaiki": 79, "Mauro Coronel": 72,
    "Rômulo": 72, "Gabriel Mec": 74, "Kauã Prates": 73,
})
POTENTIAL_TARGETS.update({
    "Zé Lucas": 88, "Eduardo Pape": 88, "Kaio Jorge": 84, "Melk": 82, "Lorenzo": 80, "Vitor Roque": 86,
    "Gabriel Bontempo": 84, "Pedro Morisco": 84, "Jonathan Jesus": 84, "Agustín Giay": 83, "Gabriel Mec": 89,
    "Kauã Prates": 87, "Vitão": 85, "Gustavo Henrique": 79, "Mauro Coronel": 84, "João Alencar": 82,
})

# rodada 27k: lista do usuário (prints de 24–28/11). Goleiros: Courtois o melhor; reservas e veteranos de times médios e
# do Brasil estavam inflados. Outros supervalorizados e subvalorizados apontados nominalmente.
REFERENCE_TARGETS.update({
    "Thibaut Courtois": 90, "David Raya": 86, "Gregor Kobel": 84, "Daniel Batz": 71, "Caoimhín Kelleher": 80,
    "James Trafford": 78, "Carlos Miguel": 76, "Hugo Souza": 76, "Léo Jardim": 77, "Tiago Volpi": 74, "Tadeu": 72,
    "Helton Leite": 71, "Luan Polli": 70, "Alex Alves": 64, "Paulo Vítor": 69, "Agustín Rossi": 79,
    "Jarrod Bowen": 81, "Ivan Toney": 79, "Deniz Undav": 79, "Lionel Messi": 84, "Neymar": 79, "Lucas Paquetá": 80,
    "Manuel Locatelli": 81, "James Garner": 78, "Waldemar Anton": 79, "Christos Tzolis": 79,
    "Thiago Almada": 82, "Leandro Paredes": 82,
})
POTENTIAL_TARGETS.update({"Melk": 84})
REFERENCE_CEILINGS.update({"Daniel Batz": 73, "Alex Alves": 66})

ANCHOR_WEIGHT = .6      # peso da referência de consenso na nota final de quem está na lista (o resto = números dele)


def anchor_to_references(u: pd.DataFrame, potential: bool = True) -> pd.DataFrame:
    """Rodada 27k — os alvos de consenso só corrigiam vieses de GRUPO; jogadores apontados nominalmente pelo usuário
    continuavam longe (Courtois 84, Batz 85, Bowen 87). Agora, para quem está NA LISTA e foi achado sem ambiguidade
    (nome com 2+ palavras ou nome único no mercado, com minutos), a nota final = 40% dos números + 60% da referência;
    tetos do usuário viram limite. Marcado na explicação da nota — é ajuste por referência, não medição."""
    if u is None or u.empty or "qualidade" not in u:
        return u
    from src.data_lake.ids import player_core

    d = u.copy()
    core = d["_core"].astype(str) if "_core" in d else d["nome"].astype(str).map(player_core)
    counts = core.value_counts()
    m12 = _col(d, "minutos_12m").fillna(0)
    q = _col(d, "qualidade")
    pot = _col(d, "potencial") if ("potencial" in d and potential) else None
    src = d.get("fonte_qualidade", pd.Series("", index=d.index)).fillna("").astype(str).copy()

    def rows_for(name: str):
        c = player_core(name)
        hit = core.index[core == c]
        if len(hit) == 0:
            return []
        if len(c.split()) < 2 and counts.get(c, 0) > 1:
            played = [i for i in hit if m12[i] > 0]
            return played if len(played) == 1 else []
        if len(hit) > 1:                      # homônimo de nome completo: o de mais minutos
            return [max(hit, key=lambda i: m12[i])]
        return list(hit)

    for name, target in REFERENCE_TARGETS.items():
        for i in rows_for(name):
            if pd.isna(q[i]) or abs(float(q[i]) - target) <= 1:
                continue
            q[i] = round((1 - ANCHOR_WEIGHT) * float(q[i]) + ANCHOR_WEIGHT * target)
            src[i] = (src[i] + " · ajustada pela referência de consenso (lista de calibração)").strip(" ·")
    for name, cap in REFERENCE_CEILINGS.items():
        for i in rows_for(name):
            if pd.notna(q[i]) and q[i] > cap:
                q[i] = float(cap)
    d["qualidade"] = q
    if pot is not None:
        for name, target in POTENTIAL_TARGETS.items():
            for i in rows_for(name):
                if pd.isna(pot[i]):
                    continue
                pot[i] = round((1 - ANCHOR_WEIGHT) * float(pot[i]) + ANCHOR_WEIGHT * target)
        pot = pd.concat([pot, q], axis=1).max(axis=1).where(pot.notna())
        d["potencial"] = pot.round(0)
        if "potencial_teto" in d:
            d["potencial_teto"] = d["potencial"]
    d["fonte_qualidade"] = src
    return d


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
REST_O = [44, 51, 58, 63.5, 68.5, 72, 75]   # rodada 27: fundo menos castigado (Série B)
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
    # rodada 27: o nível pelo VALOR dos elencos põe a Arábia (Al Hilal, Al Nassr) perto das grandes ligas — mistura com
    # a tabela de nível das competições (estimativa declarada em evaluation.TIERS)
    liga = next((u[c] for c in ("clube_liga", "liga_clube", "ultima_competicao") if c in u), None)
    if liga is not None:
        try:
            from src.scout.evaluation import prior_level

            uniq = {x: prior_level(x) for x in liga.dropna().astype(str).unique() if x.strip() and x != "nan"}
            tier = liga.astype(str).map(uniq)
            lvl = (.5 * lvl + .5 * tier).where(tier.notna(), lvl).clip(0, 1)
        except Exception:
            pass
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
    # rodada 27: a nota da FotMob favorece o meia que chega à frente; o VOLANTE (destruidor/organizador) é comparado
    # só com volantes na nota (Zé Lucas, Lucas Romero e Pape ficavam baixos contra os meias de chegada)
    papel = u["papel"] if "papel" in u else pd.Series("", index=u.index)
    t_group = d["_fam"].where(papel.ne("DM"), "MID_DM")
    if ref is not None and "_fam" in ref:
        ref_t = ref.copy()
        if "papel" in ref_t:
            ref_t["_fam"] = ref_t["_fam"].where(ref_t["papel"].ne("DM"), "MID_DM")
        d["T"] = _pct(d["_rating_adj"].where(d["_elig"]), t_group, ref_t, "_rating_adj")
    else:
        d["T"] = _pct(d["_rating_adj"].where(d["_elig"]), t_group)
    # rodada 27: reputação em escala real (desvios) — contra a régua de referência quando houver
    base = ref if (ref is not None and "_rep_val" in ref and "_fam" in ref) else \
        pd.DataFrame({"_rep_val": d["_rep_val"].where(d["_elig"]), "_fam": d["_fam"]})
    zr = pd.Series(np.nan, index=d.index)
    for fam in d["_fam"].dropna().unique():
        x = pd.to_numeric(base.loc[base["_fam"] == fam, "_rep_val"], errors="coerce").dropna()
        if len(x) < 5:
            continue
        med = float(x.median())
        mad = float((x - med).abs().median()) * 1.4826 or 1.0
        m = d["_fam"] == fam
        zr.loc[m] = ((d.loc[m, "_rep_val"] - med) / mad).clip(-3, 4.5)
    d["_zR"] = zr.where(d["_elig"])
    # rodada 27i: titular SEM valor de mercado em nenhuma fonte (Pedrinho, Wendel, Nino no Zenit) ficava só com os
    # números e caía para 54–62. A reputação vira ESTIMADA: a mediana dos titulares do mesmo clube, −0,25 (prudente).
    if "clube" in u:
        club = u["clube"].fillna("").astype(str)
        starter = d["_avail"] >= .5
        med = d["_zR"].where(starter).groupby(club).transform("median")
        fill = d["_zR"].isna() & starter & med.notna() & (club != "") & d["_elig"]
        d.loc[fill, "_zR"] = med[fill] - .25
        rmed = d["R"].where(starter).groupby(club).transform("median")
        d.loc[fill & d["R"].isna(), "R"] = rmed[fill & d["R"].isna()]
        d["_R_estimada"] = fill
    return d


def _probit(pct: pd.Series) -> pd.Series:
    """Percentil (0–100) → desvios-padrão da curva normal. No percentil o topo fica espremido (P99 e P99,9 quase
    iguais); em desvios ele se abre (2,3 × 3,1) — é aí que mora a diferença entre um bom titular e um craque."""
    from scipy.stats import norm

    p = pd.to_numeric(pct, errors="coerce") / 100
    return pd.Series(norm.ppf(p.clip(.002, .998)), index=pct.index).where(p.notna())


def rep_z(c: pd.DataFrame) -> pd.Series:
    """Rodada 27: reputação em escala REAL (logaritmo do valor ajustado pela idade, padronizado por família com mediana
    e desvio robusto). Mbappé (€180 mi) fica ~2 desvios acima de um bom titular de €25 mi — no percentil os dois
    davam ~99 e o valor de mercado deixava de separar o topo (Watkins 94 × Mbappé 88)."""
    if "_zR" in c:
        return c["_zR"]
    v = pd.to_numeric(c.get("_rep_val"), errors="coerce").where(c["_elig"])
    out = pd.Series(np.nan, index=c.index)
    for fam, idx in v.groupby(c["_fam"]).groups.items():
        x = v.loc[idx].dropna()
        if len(x) < 5:
            continue
        med = float(x.median())
        mad = float((x - med).abs().median()) * 1.4826 or 1.0
        out.loc[idx] = ((v.loc[idx] - med) / mad).clip(-3, 4.5)
    return out


def zscore(c: pd.DataFrame, w: Dict[str, float]) -> pd.Series:
    """Média ponderada dos componentes disponíveis, em DESVIOS (rodada 27; antes em percentil 0–100). A reputação pesa
    menos para quem jogou pouco."""
    has_r, has_t, has_p = c["R"].notna(), c["T"].notna() if "T" in c else pd.Series(False, index=c.index), c["P"].notna()
    zr = rep_z(c)
    has_r = has_r & zr.notna()
    zt = _probit(c["T"]) if "T" in c else pd.Series(np.nan, index=c.index)
    zp = _probit(c["P"])
    zl = (pd.to_numeric(c["L"], errors="coerce").fillna(45) - 50) / 20
    wr = w.get("wR", 0) * c["_m"] * has_r
    if "_age" in c and "_fam" in c:
        # rodada 27i: goleiro de 33+ titular — o valor de mercado despenca com a idade (Fábio € 75 mil aos 46, titular
        # com 5.940 min); a reputação pesa 40% e os números em campo mandam
        vet_gk = c["_fam"].astype(str).eq("GK") & (pd.to_numeric(c["_age"], errors="coerce") >= 33) & (c["_avail"] >= .75)
        # rodada 27k: com 10% a reputação sumia e goleiro reserva de € 350 mil (Batz) ia a 85 — volta a 45%
        wr = wr.where(~vet_gk, wr * .45)
    wt = w.get("wT", 0) * has_t
    wp = w.get("wP", 0) * has_p
    num = wr * zr.fillna(0) + wt * zt.fillna(0) + wp * zp.fillna(0) + w.get("wL", 0) * zl
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
    a = .45 + .55 * avail
    # rodada 27: quem jogou pouco era puxado para a MÉDIA GERAL (zagueiro de estadual com 90 min virava 70, acima de
    # titular jovem da Série A). Agora é puxado para o nível da PRÓPRIA liga: pouca amostra = "jogador típico da liga"
    lv = pd.to_numeric(comps.get("L"), errors="coerce").fillna(50) / 100 if "L" in comps else .5
    prior = (1.5 * (lv - .62)).clip(-.6, .5) if not isinstance(lv, float) else 1.5 * (lv - .62)
    s = a * s + (1 - a) * prior                          # quem jogou pouco no ano não chega ao topo
    if "_age" in comps:
        s = s + age_prior(comps["_age"], comps["_avail"], comps.get("L"), comps["_fam"])
    return s, fam_stats


def age_prior(age: pd.Series, avail: pd.Series, level: Optional[pd.Series] = None,
              fam: Optional[pd.Series] = None) -> pd.Series:
    """Rodada 26 — o que os números por jogo não medem (velocidade, explosão, recuperação): depois dos 31 o corpo cai
    mesmo quando a produção ainda aparece (−0,08 na régua por ano depois dos 31, até −0,48); um jovem de até 22 anos
    TITULAR num clube/liga forte já prova nível acima do que os números de um ano mostram (+0,035 por ano abaixo de 23).
    É uma estimativa assumida — está descrita na explicação da nota."""
    a = pd.to_numeric(age, errors="coerce")
    old = -(.08 * (a - 31).clip(lower=0, upper=6))
    if fam is not None:
        # rodada 27g: goleiro envelhece bem (Fábio, Rafael, Walter, Everson, Cássio levavam o desconto inteiro de
        # linha): começa aos 35 e é metade, no máximo −0,2
        gk = fam.astype(str).eq("GK").reindex(a.index, fill_value=False)
        old = old.where(~gk, -(.04 * (a - 34).clip(lower=0, upper=5)))
    lv = level.fillna(45) if level is not None else pd.Series(45.0, index=a.index)
    young = .035 * (23 - a).clip(lower=0, upper=5) * (avail.fillna(0) >= .75) * (lv >= 60)
    # rodada 27: jovem TITULAR fora das ligas de elite (Melk e Lorenzo na Série B, titulares aos 19–20) também prova
    # nível acima dos números de um ano — empurrão menor, que some nas ligas de elite (onde a lista já estava certa)
    young2 = .05 * (22 - a).clip(lower=0, upper=4) * (avail.fillna(0) >= .5) * ((lv >= 35) & (lv < 85))
    return (old + young + young2).fillna(0.0)


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
FAMILY_SPREAD = {"GK": .90, "FB": .86, "CB": .93, "MID": 1.0, "AM": 1.0, "WIDE": 1.0, "ST": 1.0}


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
    for wR in (.3, .4, .5, .6):
        for wT in (.1, .2, .3):
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


def _blend_goalkeeper_attribute_performance(comps: pd.DataFrame, engine: Optional[pd.DataFrame],
                                               base_weight: float = .55) -> pd.DataFrame:
    """Blend the dedicated GK attribute engine into P, without changing outfield-player ratings.

    The legacy market/statistical P remains the majority source. The dedicated goalkeeper engine adds a
    position-aware check (shot stopping, distribution and security) so a poor distribution percentile alone
    cannot drag an otherwise strong, high-minute keeper down. Requires a sufficiently large GK reference pool.
    """
    if comps is None or comps.empty or engine is None or engine.empty or "ovr2_bruto" not in engine:
        return comps
    if "_fam" not in comps or "P" not in comps:
        return comps
    gk = comps["_fam"].astype(str).eq("GK")
    raw = pd.to_numeric(engine.get("ovr2_bruto"), errors="coerce").reindex(comps.index)
    valid = gk & raw.notna()
    if int(valid.sum()) < 10:
        return comps
    out = comps.copy()
    # Percentile keeps this signal on the same 0–100 scale as P and adapts to the current keeper population.
    gk_pct = raw.loc[valid].rank(pct=True, method="average") * 100
    # rodada 27k: muitas defesas num time fraco/liga fraca inflavam o percentil (Batz, goleiros da Série B). O sinal
    # do motor de goleiro é encolhido pelo nível da liga (liga de elite = inteiro; liga fraca = 30%)
    if "L" in out:
        lv = pd.to_numeric(out.loc[valid, "L"], errors="coerce").fillna(45)
        gk_pct = 50 + (gk_pct - 50) * ((lv - 35) / 50).clip(.3, 1.0)
    base_weight = max(base_weight, .7)
    base = pd.to_numeric(out.loc[valid, "P"], errors="coerce")
    blended = base_weight * base + (1.0 - base_weight) * gk_pct
    out.loc[valid, "P"] = blended.where(base.notna(), gk_pct)
    return out


def finalize_overall(u: pd.DataFrame, calibrate_now: bool = True, reference: Optional[pd.DataFrame] = None,
                     weights: Optional[Dict[str, float]] = None, recompute_potential: bool = True) -> pd.DataFrame:
    """Recalcula `qualidade` como OVERALL 0–100. Pode preservar o potencial ao migrar só o OVR."""
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
        comps = _blend_goalkeeper_attribute_performance(comps, eng)
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
    out["qualidade"] = brazil_bump(out.assign(_fam=comps["_fam"]), out["qualidade"])
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
    out = youth_quality(out)
    if recompute_potential:
        out = _recompute_potential(out)
    out = anchor_to_references(out, potential=recompute_potential)
    if report:
        save_report(out, report)
    return out


BR_BUMP_CAP = 84.0      # acima disto nada muda: a lista dos melhores do mundo fica intacta


def _br_division(u: pd.DataFrame) -> pd.Series:
    """'A' / 'B' para quem joga num clube da Série A / Série B (pela liga do clube), senão ''."""
    liga = next((u[c] for c in ("clube_liga", "liga_clube", "ultima_competicao", "liga") if c in u), None)
    if liga is None:
        return pd.Series("", index=u.index)
    f = liga.fillna("").astype(str).map(lambda x: unicodedata.normalize("NFKD", x.lower()).encode("ascii", "ignore").decode())
    is_br = f.str.contains(r"brasil|brazil|brasileir|serie [ab]\b|campeonato brasileiro", regex=True)
    a = is_br & f.str.contains(r"serie a\b|brasileirao(?! serie b)|brasileiro serie a|^brasileirao$", regex=True) \
        & ~f.str.contains(r"serie [bcd]\b|feminin|sub", regex=True)
    b = is_br & f.str.contains(r"serie b\b", regex=True) & ~f.str.contains(r"feminin|sub", regex=True)
    return pd.Series(np.where(a, "A", np.where(b, "B", "")), index=u.index)


def brazil_bump(u: pd.DataFrame, q: pd.Series) -> pd.Series:
    """Rodada 27e — os melhores do Brasileirão ainda saíam 1 a 3 pontos abaixo do que o usuário vê no futebol (e da
    referência de consenso). Ajuste PEQUENO e graduado: Série A +1 (nota 65) a +3 (nota 80+); Série B +1 a +2. Nunca
    passa de 84 e quem já está acima de 84 não muda — o topo mundial fica igual."""
    q = pd.to_numeric(q, errors="coerce")
    div = _br_division(u)
    bump = pd.Series(0.0, index=u.index)
    a, b = div == "A", div == "B"
    bump[a] = 1 + 2 * ((q[a] - 65) / 15).clip(0, 1)
    bump[b] = 1 + ((q[b] - 62) / 12).clip(0, 1)
    # rodada 27g: goleiro TITULAR (1.800+ min no ano) na Série A/B ganha +2 a mais — a régua de goleiro é estreita e
    # os titulares do Brasil ficavam todos entre 60 e 69 (Rafael 61 com 4.950 min)
    if "_fam" in u or "papel" in u:
        fam = (u["_fam"] if "_fam" in u else u["papel"]).astype(str)
        m12 = pd.to_numeric(u.get("minutos_12m"), errors="coerce").fillna(0)
        # rodada 27k: o usuário apontou o contrário — goleiros da Série A/B INFLADOS (Carlos Miguel 83, Volpi 82,
        # Tadeu 80). Goleiro agora recebe só metade do ajuste do Brasil, sem o +2.
        gk = fam.eq("GK") & (a | b)
        bump[gk] = bump[gk] * .5
    bump[(q < 55) | q.isna()] = 0.0
    out = pd.Series(np.where(q > BR_BUMP_CAP, q, np.minimum(q + bump, np.maximum(q, BR_BUMP_CAP))), index=q.index)
    return out.round(0)


YOUTH_BAND = {"sub17": (52.0, 68.0), "sub20": (56.0, 74.0)}


def youth_quality(u: pd.DataFrame) -> pd.DataFrame:
    """Rodada 27 — jovem da seleção de base SEM minutos de profissional suficientes para a régua (Eduardo Pape: 0 min
    no Cruzeiro, titular do Brasil Sub-17) ficava sem overall. Recebe uma QUALIDADE ESTIMADA pela base: a colocação da
    nota dele dentro da competição de base vira um overall numa faixa baixa (Sub-17 52–68 · Sub-20 56–74); sem nota,
    o meio da faixa (+4 se for seleção de elite). Sempre marcada como estimativa."""
    if "selecao_base_jogos" not in u:
        return u
    from src.scout.potential import youth_elite

    q = _col(u, "qualidade")
    yj = _col(u, "selecao_base_jogos").fillna(0)
    age = _col(u, "idade")
    need = q.isna() & (yj > 0) & (age.isna() | (age <= 21))
    if not need.any():
        return u
    comp = u.get("selecao_base_comp", pd.Series("", index=u.index)).fillna("").astype(str)
    sub17 = comp.str.contains("17")
    lo = np.where(sub17, YOUTH_BAND["sub17"][0], YOUTH_BAND["sub20"][0])
    hi = np.where(sub17, YOUTH_BAND["sub17"][1], YOUTH_BAND["sub20"][1])
    pct = _col(u, "selecao_base_pct")
    el = youth_elite(u).fillna(0)
    frac = (pct / 100).fillna(.5 + .1 * el)
    est = pd.Series(lo + (hi - lo) * frac.values, index=u.index) + 2 * np.minimum(yj, 5) / 5
    out = u.copy()
    out.loc[need, "qualidade"] = est[need].round(0)
    out.loc[need, "qualidade_estimada_base"] = True
    out.loc[need, "fonte_qualidade"] = ("ESTIMADA pela seleção de base (ainda sem minutos de profissional suficientes): "
                                        "colocação da nota na competição de base, faixa " +
                                        pd.Series(np.where(sub17, "Sub-17 52–68", "Sub-20 56–74"), index=u.index)[need])
    return out


def minutes_cap(u: pd.DataFrame) -> pd.Series:
    """Rodada 25b: teto pela minutagem do último ano — "não pode receber 91 com 120 minutos". 0–300 min → 72;
    cresce até 1.800 min, onde o teto some (99)."""
    m12 = _col(u, "minutos_12m").fillna(0)
    # rodada 27: com 90 minutos o teto era 72 (estaduais com 1 jogo apareciam com 70); agora 62 com 90 min, 66 com
    # 300, 75 com 900, 84 com 1.350 e some com 1.800 (temporada de titular)
    cap = np.interp(m12.values, [0, 90, 300, 600, 900, 1350, 1800], [58, 62, 66, 70, 75, 84, 99])
    return pd.Series(cap, index=u.index).where(m12 < 1800, 99.0)


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
            orig = pd.to_numeric(p["potencial"], errors="coerce")
            # rodada 27k: o potencial que veio de um PISO (titular jovem, seleção) não pode ser apagado pela calibração
            # do crescimento (Melk 52/65: o piso de titular sumia aqui)
            floor_driven = orig > (q + pd.to_numeric(p["potencial_crescimento"], errors="coerce").fillna(0) + .5)
            newp = (q + g).clip(upper=POT.POT_CAP).where(q.notna(), orig)
            p["potencial"] = newp.where(~floor_driven.fillna(False), pd.concat([newp, orig], axis=1).max(axis=1)).round(0)
            p["potencial_crescimento"] = g.round(1)
        d.attrs["potencial_k"] = best_k
        # rodada 27: o piso da seleção de base vale também depois da calibração do crescimento
        yf = POT.youth_floor(d)
        low = yf.notna() & (pd.to_numeric(p["potencial"], errors="coerce").fillna(0) < yf)
        p.loc[low, "potencial"] = yf[low].clip(upper=POT.POT_CAP).round(0)
        if "potencial_piso_base" in p:
            p["potencial_piso_base"] = p["potencial_piso_base"].fillna(False).astype(bool) | low
        sf = POT.senior_floor(d)                          # rodada 27e: convocado para a seleção PRINCIPAL jovem
        low_s = sf.notna() & (pd.to_numeric(p["potencial"], errors="coerce").fillna(0) < sf)
        if low_s.any():
            p.loc[low_s, "potencial"] = sf[low_s].round(0)
            if "potencial_porque" in p:
                why = ("convocado para a seleção principal (" + _col(d, "selecao_principal_jogos").fillna(0).astype(int).astype(str)
                       + " jogo(s)) com " + _col(d, "idade").round(0).astype("Int64").astype(str) + " anos")
                p.loc[low_s, "potencial_porque"] = (why[low_s] + " · " + p.loc[low_s, "potencial_porque"].fillna("").astype(str)).str.strip(" ·")
        for c in p.columns:
            d[c] = p[c]
        # rodada 27: o topo do potencial pela COLOCAÇÃO (como o overall) — antes muita gente batia no teto 95 (Bellingham,
        # Doué, Güler, Cubarsí, Karl…). Agora só o 1º chega a 95; o 2º ~93,5, 5º 92, 10º 91, 25º 90, 60º 89.
        raw = (q + pd.to_numeric(d.get("potencial_crescimento"), errors="coerce")).where(q.notna(), _col(d, "potencial"))
        raw = pd.concat([raw, _col(d, "potencial")], axis=1).max(axis=1)
        # rodada 27e: a ORDEM do topo pesa o que o jogador já é hoje — Yamal (overall 90+ aos 19) à frente de quem tem
        # muito crescimento previsto mas joga menos (Diomande); a nota final segue a escada (1º 95)
        key = raw + .6 * (q - 82).clip(lower=0).fillna(0)
        d["potencial"] = top_potential_ladder(raw, key).where(_col(d, "potencial").notna())
        # potencial nunca abaixo do overall de hoje
        d["potencial"] = pd.concat([_col(d, "potencial"), q], axis=1).max(axis=1).where(_col(d, "potencial").notna())
        d["potencial"] = pd.to_numeric(d["potencial"], errors="coerce").round(0)
        d["potencial_teto"] = d["potencial"]
        return d
    except Exception:
        pass
    return _recompute_potential_old(d)


POT_LADDER_R = [1, 2, 3, 5, 10, 25, 60, 150]
POT_LADDER_O = [95, 93.5, 93, 92, 91, 90, 89, 88]


def top_potential_ladder(raw: pd.Series, key: Optional[pd.Series] = None) -> pd.Series:
    """Potenciais acima de 88 viram colocação: o maior (sem teto, idade × talento) leva 95; os outros descem pela escada.
    `key` (opcional) decide a ORDEM; a nota de cada um nunca passa do próprio potencial bruto. Abaixo de 88 nada muda.
    Sempre número inteiro (antes apareciam 80,2 e 76,3)."""
    out = pd.to_numeric(raw, errors="coerce").copy()
    k = (pd.to_numeric(key, errors="coerce") if key is not None else out).reindex(out.index)
    top_idx = out[out >= 88].index
    if len(top_idx) == 0:
        return out.round(0)
    order = k.loc[top_idx].fillna(out.loc[top_idx]).sort_values(ascending=False).index
    rank = np.arange(1, len(order) + 1)
    lad = np.interp(np.log(rank), np.log(POT_LADDER_R), POT_LADDER_O)
    top_raw = out.loc[order].values
    # o 1º da ordem leva a escada inteira (95) mesmo com o bruto um pouco abaixo — é o melhor potencial do mundo
    vals = np.where((rank == 1) & (top_raw >= 91), lad, np.minimum(np.maximum(top_raw, 88.0), np.maximum(lad, 88.0)))
    out.loc[order] = np.round(vals)
    return out.clip(upper=95).round(0)


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
