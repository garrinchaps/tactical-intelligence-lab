"""
Tradução da interface (v36): português (padrão), inglês e espanhol.

Uso: `t("Buscar")` devolve o texto no idioma escolhido no topo. O dicionário é indexado pelo texto em português;
o que não estiver nele aparece em português (nunca some, nunca vira chave técnica). Os componentes comuns
(hero, cabeçalhos, estados vazios, avisos, cartões) já passam pelo `t()`, então basta acrescentar frases aqui.

Limite honesto: as respostas do Assistente e os textos gerados a partir dos dados continuam em português — o
entendimento das perguntas foi feito para o português.
"""

from __future__ import annotations

from typing import Dict

LANGS = {"pt": "🇧🇷 Português", "en": "🇬🇧 English", "es": "🇪🇸 Español"}
DEFAULT = "pt"
KEY = "_lang"

# texto em português → (inglês, espanhol)
T: Dict[str, tuple] = {
    # menu e topo
    "Assistente": ("Assistant", "Asistente"), "Buscar": ("Search", "Buscar"), "Comparar": ("Compare", "Comparar"),
    "Escalação": ("Line-up", "Alineación"), "Jogo": ("Match", "Partido"), "Time": ("Team", "Equipo"),
    "Jogador": ("Player", "Jugador"), "Competição": ("Competition", "Competición"),
    "⚙️ Bastidores": ("⚙️ Behind the scenes", "⚙️ Entre bastidores"),
    "Como tudo foi feito — separado do programa.": ("How everything was built — kept apart from the app.",
                                                    "Cómo se hizo todo — separado de la aplicación."),
    "Como a IA aprende": ("How the AI learns", "Cómo aprende la IA"),
    "Machine Learning & Avaliação": ("Machine Learning & Evaluation", "Machine Learning y Evaluación"),
    "Analista técnico (guard)": ("Technical analyst (guard)", "Analista técnico (guard)"),
    "Dados & Fontes": ("Data & Sources", "Datos y Fuentes"), "Laboratório": ("Laboratory", "Laboratorio"),
    "Idioma": ("Language", "Idioma"), "Nível de dado": ("Data level", "Nivel de datos"),
    "Só partidas reais": ("Real matches only", "Solo partidos reales"),
    "🟢 Lances": ("🟢 Events", "🟢 Jugadas"), "📊 Estatísticas": ("📊 Statistics", "📊 Estadísticas"),
    "📄 Só placar": ("📄 Score only", "📄 Solo marcador"),
    "🔎  Jogo, time, jogador ou competição — ex.: Brasil x Croácia, Leverkusen, Messi, Premier League":
        ("🔎  Match, team, player or competition — e.g.: Brazil x Croatia, Leverkusen, Messi, Premier League",
         "🔎  Partido, equipo, jugador o competición — ej.: Brasil x Croacia, Leverkusen, Messi, Premier League"),
    "🏟️ Abrir o jogo": ("🏟️ Open match", "🏟️ Abrir partido"), "← Voltar": ("← Back", "← Volver"),
    # telas principais
    "Assistente tático": ("Tactical assistant", "Asistente táctico"),
    "Pergunte qualquer coisa sobre futebol": ("Ask anything about football", "Pregunta lo que quieras sobre fútbol"),
    "Cite o jogo na própria pergunta (times e ano) ou use a partida aberta no topo. Cada número da resposta é "
    "conferido contra os dados antes de aparecer.":
        ("Mention the match in the question (teams and year) or use the match open at the top. Every number in the "
         "answer is checked against the data before it appears. Answers are written in Portuguese.",
         "Cita el partido en la pregunta (equipos y año) o usa el partido abierto arriba. Cada número de la respuesta "
         "se comprueba con los datos antes de aparecer. Las respuestas se redactan en portugués."),
    "Um jogo, um time, um jogador ou uma competição": ("A match, a team, a player or a competition",
                                                       "Un partido, un equipo, un jugador o una competición"),
    "Digite na caixa do topo. Clique no resultado para abrir a análise. Escolha ao lado da busca que "
    "jogos aparecem: 🟢 com todos os lances, 📊 com estatísticas, 📄 só placar — ou os três.":
        ("Type in the box at the top and click a result to open the analysis. Next to the search, choose which "
         "matches appear: 🟢 with every event, 📊 with statistics, 📄 score only — or all three.",
         "Escribe en la caja de arriba y haz clic en un resultado para abrir el análisis. Junto a la búsqueda, elige "
         "qué partidos aparecen: 🟢 con todas las jugadas, 📊 con estadísticas, 📄 solo marcador — o los tres."),
    "Lado a lado": ("Side by side", "Lado a lado"),
    "Jogador × jogador, jogo × jogo, clube × clube, a equipe contra ela mesma ou as duas equipes da partida aberta.":
        ("Player × player, match × match, club × club, a team against itself or both teams of the open match.",
         "Jugador × jugador, partido × partido, club × club, el equipo contra sí mismo o los dos equipos del partido abierto."),
    "Monte o time para o próximo jogo": ("Build the team for the next match", "Arma el equipo para el próximo partido"),
    "Elenco atual (Transfermarkt + atletas que você cadastrar), nota do laboratório, escalação provável, a melhor "
    "possível e a ajustada ao adversário — com o plano de jogo tirado dos últimos jogos do rival.":
        ("Current squad (Transfermarkt + players you add), lab rating, probable line-up, the best possible one and the "
         "one adjusted to the opponent — with a game plan drawn from the rival's last matches.",
         "Plantilla actual (Transfermarkt + jugadores que agregues), nota del laboratorio, alineación probable, la mejor "
         "posible y la ajustada al rival — con el plan de juego sacado de sus últimos partidos."),
    "Bastidores · como a IA aprende": ("Behind the scenes · how the AI learns", "Entre bastidores · cómo aprende la IA"),
    "Uma rede neural que aprende a ler o perigo de uma jogada": ("A neural network that learns to read the danger of a play",
                                                                 "Una red neuronal que aprende a leer el peligro de una jugada"),
    # comparar
    "👥 Jogador × jogador": ("👥 Player × player", "👥 Jugador × jugador"),
    "🏟️ Jogo × jogo": ("🏟️ Match × match", "🏟️ Partido × partido"), "🛡️ Clube × clube": ("🛡️ Club × club", "🛡️ Club × club"),
    "📅 Equipe × ela mesma": ("📅 Team × itself", "📅 Equipo × sí mismo"),
    "⚔️ Duas equipes da partida": ("⚔️ Both teams of the match", "⚔️ Los dos equipos del partido"),
    "De qualquer jogo da base": ("From any match in the database", "De cualquier partido de la base"),
    "Da partida aberta": ("From the open match", "Del partido abierto"),
    "Último jogo": ("Last match", "Último partido"), "Últimos 5 jogos": ("Last 5 matches", "Últimos 5 partidos"),
    "Temporada mais recente": ("Latest season", "Temporada más reciente"), "Recorte": ("Range", "Recorte"),
    "Jogador A": ("Player A", "Jugador A"), "Jogador B": ("Player B", "Jugador B"),
    "Escolha os dois jogadores": ("Choose both players", "Elige los dos jugadores"),
    # tela do jogo
    "📊 Resumo": ("📊 Summary", "📊 Resumen"), "🕸️ Redes & xT": ("🕸️ Networks & xT", "🕸️ Redes y xT"),
    "👤 Jogadores": ("👤 Players", "👤 Jugadores"), "⚖️ Fortes e fracos": ("⚖️ Strengths & weaknesses", "⚖️ Fortalezas y debilidades"),
    "⚔️ Duas equipes": ("⚔️ Both teams", "⚔️ Los dos equipos"), "Analisar pelo lado de": ("Analyse from the side of", "Analizar desde"),
    "💬 Perguntar sobre este jogo": ("💬 Ask about this match", "💬 Preguntar sobre este partido"),
    "🕸️ Como o time trocou passes": ("🕸️ How the team passed the ball", "🕸️ Cómo se pasó el balón el equipo"),
    "Os 11 titulares até a 1ª troca": ("The starting XI until the 1st sub", "Los 11 titulares hasta el 1.er cambio"),
    "Os 11 titulares, jogo inteiro": ("The starting XI, whole match", "Los 11 titulares, todo el partido"),
    "Jogo inteiro, com quem entrou (marcado à parte)": ("Whole match, substitutes marked apart",
                                                        "Todo el partido, con los suplentes aparte"),
    "Quem aparece no campinho": ("Who appears on the pitch", "Quién aparece en el campo"),
    "Desenho com a bola": ("Shape in possession", "Dibujo con balón"), "Quem liga o time": ("Who links the team", "Quién une al equipo"),
    "Por quem a bola mais passa": ("Who the ball goes through most", "Por quién pasa más el balón"),
    "Ameaça criada (xT)": ("Threat created (xT)", "Amenaza creada (xT)"),
    # jogadores
    "📋 Estatísticas individuais": ("📋 Individual stats", "📋 Estadísticas individuales"),
    "🧩 Elenco & substituições": ("🧩 Squad & substitutions", "🧩 Plantilla y cambios"),
    "🕵️ Dossiê & comparador": ("🕵️ Dossier & comparison", "🕵️ Informe y comparador"),
    "Atletas de": ("Players from", "Jugadores de"), "Ambas as equipes": ("Both teams", "Ambos equipos"),
    "Mostrar": ("Show", "Mostrar"), "Nota": ("Rating", "Nota"), "Ataque": ("Attack", "Ataque"), "Passe": ("Passing", "Pase"),
    "Defesa": ("Defence", "Defensa"), "Duelos e erros": ("Duels & errors", "Duelos y errores"), "Tudo": ("All", "Todo"),
    "Valores": ("Values", "Valores"), "Totais": ("Totals", "Totales"), "Por 90 minutos": ("Per 90 minutes", "Por 90 minutos"),
    "Ordenar por": ("Sort by", "Ordenar por"),
    # estados comuns
    "Nenhum jogador com esse nome.": ("No player with that name.", "Ningún jugador con ese nombre."),
    "Nenhum jogador escolhido": ("No player selected", "Ningún jugador elegido"),
    "Nenhum time escolhido": ("No team selected", "Ningún equipo elegido"),
    "Escolha o adversário": ("Choose the opponent", "Elige el rival"),
}


def lang() -> str:
    try:
        import streamlit as st

        v = st.session_state.get(KEY, DEFAULT)
        return v if v in LANGS else DEFAULT
    except Exception:
        return DEFAULT


def t(text, lang_code: str | None = None):
    """Texto no idioma escolhido; sem tradução cadastrada, devolve o original (português)."""
    if not isinstance(text, str):
        return text
    code = lang_code or lang()
    if code == "pt":
        return text
    pair = T.get(text)
    if not pair:
        return text
    return pair[0] if code == "en" else pair[1]
