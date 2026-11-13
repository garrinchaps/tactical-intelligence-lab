"""
Compreensão da pergunta do usuário (escopo + recorte).

Transforma texto livre num `QueryScope`:
* se a pergunta é de futebol/da partida ou está fora do escopo (ex.: "a coxinha é
  melhor que o hambúrguer?");
* o recorte pedido: janela de minutos, tempo de jogo, lado do campo, terço, fase,
  equipe (nossa/adversária), atletas citados e métricas mencionadas;
* se a pergunta exige dados espaciais (coordenadas) — importante para partidas
  que só têm boxscore.

Nada aqui gera texto de resposta: só estrutura a intenção para o recorte de evidências.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

FOOTBALL_TERMS = {
    "jogo", "partida", "time", "equipe", "jogador", "atleta", "gol", "gols", "passe", "passes", "finalizacao",
    "finalizacoes", "chute", "chutes", "xg", "xt", "posse", "pressao", "pressing", "ppda", "marcacao", "marcar",
    "defesa", "defensiva", "defensivo", "ataque", "ofensiva", "ofensivo", "transicao", "contra-ataque",
    "contra", "escanteio", "escanteios", "bola", "parada", "cruzamento", "cruzamentos", "lateral", "zagueiro",
    "volante", "meia", "meio", "campo", "ponta", "centroavante", "atacante", "goleiro", "tatica", "tatico",
    "taticamente", "esquema", "formacao", "bloco", "linha", "compactacao", "compacto", "corredor", "lado",
    "esquerdo", "direito", "esquerda", "direita", "area", "zona", "minuto", "minutos", "tempo", "intervalo",
    "substituicao", "substituir", "substituto", "banco", "escalacao", "rede", "conexao", "conexoes",
    "duelo", "duelos", "desarme", "desarmes", "interceptacao", "recuperacao", "perda", "perdas", "anular",
    "neutralizar", "explorar", "fraqueza", "fraquezas", "forte", "fortes", "fraco", "fracos", "adversario",
    "rival", "treinador", "tecnico", "comissao", "relatorio", "analise", "analisar", "desempenho", "dribles",
    "drible", "saida", "construcao", "progressao", "profundidade", "amplitude", "placar", "resultado",
    "vitoria", "derrota", "empate", "cartao", "cartoes", "falta", "faltas", "penalti", "impedimento",
    "aerea", "aereo", "cabeceio", "estatistica", "estatisticas", "numeros", "dados", "scout", "futebol",
}
OFF_TOPIC_HINTS = {
    "coxinha", "hamburguer", "pizza", "receita", "comida", "bolo", "cerveja", "filme", "serie", "novela",
    "musica", "namorada", "namorado", "clima", "tempo amanha", "chover", "politica", "eleicao", "bitcoin",
    "dolar", "horoscopo", "signo", "carro", "celular", "piada", "poema",
}
GREETINGS = {"oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai", "tudo bem", "obrigado", "valeu"}
HELP_TERMS = {"ajuda", "o que voce faz", "como funciona", "o que posso perguntar", "exemplos"}

METRIC_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "compactness": ("compact", "compacto", "compactacao", "distancia entre linhas", "bloco", "espacamento"),
    "pressing": ("pressao", "pressing", "ppda", "pression", "marcacao alta", "perde-pressiona", "contrapressao",
                 "marcou alto", "marcar alto"),
    "shots": ("finaliza", "chute", "xg", "gol", "chance", "oportunidade"),
    "passing": ("passe", "passes", "circulacao", "construcao", "saida de bola", "precisao"),
    "progression": ("progress", "avanco", "quebra de linha", "profundidade", "verticalidade", "xt"),
    "crosses": ("cruzamento", "cruzar", "bola aerea", "jogo aereo", "cabeceio"),
    "duels": ("duelo", "disputa", "desarme", "dividida"),
    "turnovers": ("perda", "perdeu", "erro", "turnover", "entregou"),
    "recoveries": ("recupera", "roubada", "interceptacao", "retomada"),
    "set_pieces": ("escanteio", "bola parada", "falta", "lateral cobrado", "tiro de meta"),
    "possession": ("posse", "dominio", "controle do jogo", "field tilt"),
    "substitutions": ("substitui", "trocar", "banco", "cansaco", "fadiga", "desgaste"),
    "discipline": ("cartao", "cartoes", "falta", "faltas", "expuls"),
}
SPATIAL_METRICS = {"compactness", "progression", "crosses", "pressing", "recoveries", "turnovers"}


def norm(text: Any) -> str:
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class QueryScope:
    raw: str
    category: str = "match_tactical"   # match_tactical | player | off_topic | greeting | help | full_report
    minute_from: Optional[int] = None
    minute_to: Optional[int] = None
    period: Optional[int] = None
    side: Optional[str] = None          # left | right | center
    third: Optional[str] = None         # defensive | middle | attacking
    phase: Optional[str] = None         # defensive | offensive | transition | set_pieces
    team_focus: str = "target"          # target | opponent | both
    players: List[str] = field(default_factory=list)
    metrics: List[str] = field(default_factory=list)
    needs_spatial: bool = False
    descriptors: List[str] = field(default_factory=list)

    @property
    def in_scope(self) -> bool:
        return self.category not in ("off_topic", "greeting", "help")

    @property
    def has_cut(self) -> bool:
        return any([self.minute_from is not None, self.period, self.side, self.third, self.players])

    def describe(self) -> str:
        return ", ".join(self.descriptors) if self.descriptors else "partida inteira"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["recorte"] = self.describe()
        return d


class QueryUnderstanding:
    @classmethod
    def parse(cls, text: str, match_players: Optional[List[str]] = None,
              teams: Optional[List[str]] = None) -> QueryScope:
        """`teams` = [equipe analisada, adversário] para detectar quando a pergunta cita o adversário."""
        sc = QueryScope(raw=text or "")
        t = norm(text)
        words = set(re.findall(r"[a-z0-9\-]+", t))

        # ---- atletas citados (nome completo, sobrenome ou nome comum)
        sc.players = cls._match_players(t, match_players or [])

        # ---- escopo
        football_hits = len(words & FOOTBALL_TERMS) + (2 if sc.players else 0)
        off_hits = sum(1 for h in OFF_TOPIC_HINTS if h in t)
        if not t:
            sc.category = "help"
            return sc
        if football_hits == 0 and any(t.startswith(g) or t == g for g in GREETINGS):
            sc.category = "greeting"
            return sc
        if football_hits == 0 and any(h in t for h in HELP_TERMS):
            sc.category = "help"
            return sc
        if off_hits > 0 and football_hits <= 1 or football_hits == 0:
            sc.category = "off_topic"
            return sc
        if re.search(r"relatorio completo|analise completa|tudo sobre|dossie completo|relatorio geral", t):
            sc.category = "full_report"

        # ---- janela de tempo
        m = re.search(r"(?:entre|dos|do|de)\s*(?:o\s*)?(?:minuto\s*)?(\d{1,3})\s*(?:'|min\w*)?\s*(?:e|a|aos|ao|ate)\s*(?:o\s*)?(\d{1,3})", t)
        m2 = re.search(r"(\d{1,3})\s*(?:'|min\w*)?\s*-\s*(\d{1,3})", t)
        m3 = re.search(r"(?:no|aos|ao|perto do|por volta do|em torno do)\s*(?:minuto\s*)?(\d{1,3})\s*(?:'|min\w*)?", t)
        m4 = re.search(r"(?:apos|depois do|a partir do)\s*(?:o\s*)?(?:minuto\s*)?(\d{1,3})", t)
        m5 = re.search(r"(?:antes do|ate o)\s*(?:minuto\s*)?(\d{1,3})", t)
        m6 = re.search(r"ultimos\s*(\d{1,2})\s*min", t)
        m7 = re.search(r"primeiros\s*(\d{1,2})\s*min", t)
        if m and int(m.group(1)) < int(m.group(2)) <= 130:
            sc.minute_from, sc.minute_to = int(m.group(1)), int(m.group(2))
        elif m2 and int(m2.group(1)) < int(m2.group(2)) <= 130:
            sc.minute_from, sc.minute_to = int(m2.group(1)), int(m2.group(2))
        elif m4 and int(m4.group(1)) <= 130:
            sc.minute_from, sc.minute_to = int(m4.group(1)), 130
        elif m5 and int(m5.group(1)) <= 130:
            sc.minute_from, sc.minute_to = 0, int(m5.group(1))
        elif m6:
            sc.minute_from, sc.minute_to = max(90 - int(m6.group(1)), 0), 130
        elif m7:
            sc.minute_from, sc.minute_to = 0, int(m7.group(1))
        elif m3 and "minuto" in t or (m3 and re.search(r"\d{1,3}\s*(?:'|min)", t)):
            c = int(m3.group(1))
            if c <= 130:
                sc.minute_from, sc.minute_to = max(c - 5, 0), c + 5
        if re.search(r"inicio do jogo|comeco do jogo", t) and sc.minute_from is None:
            sc.minute_from, sc.minute_to = 0, 15
        if re.search(r"primeiro tempo|1o tempo|1º tempo|etapa inicial", t):
            sc.period = 1
        elif re.search(r"segundo tempo|2o tempo|2º tempo|etapa final", t):
            sc.period = 2
        if sc.minute_from is not None:
            sc.descriptors.append(f"minutos {sc.minute_from}–{min(sc.minute_to or 130, 120)}")
        if sc.period:
            sc.descriptors.append(f"{sc.period}º tempo")

        # ---- lado / terço
        if re.search(r"lado esquerdo|pela esquerda|corredor esquerdo|lateral esquerd|flanco esquerdo|ala esquerd|meio-espaco esquerdo", t):
            sc.side = "left"
        elif re.search(r"lado direito|pela direita|corredor direito|lateral direit|flanco direito|ala direit|meio-espaco direito", t):
            sc.side = "right"
        elif re.search(r"pelo meio|corredor central|faixa central|zona central|por dentro", t):
            sc.side = "center"
        if sc.side:
            sc.descriptors.append({"left": "lado esquerdo", "right": "lado direito", "center": "corredor central"}[sc.side])
        if re.search(r"terco final|terco ofensivo|ultimo terco|entrada da area|zona 14", t):
            sc.third = "attacking"
        elif re.search(r"terco defensivo|nossa area|saida de bola|campo de defesa", t):
            sc.third = "defensive"
        elif re.search(r"meio-campo|meio de campo|terco medio|faixa central do campo", t):
            sc.third = "middle"
        if sc.third:
            sc.descriptors.append({"attacking": "terço ofensivo", "defensive": "terço defensivo", "middle": "terço médio"}[sc.third])

        # ---- fase
        if re.search(r"defens|defend|sem a bola|marcacao|compact|sofr|cedeu|vulnerab|anular|neutraliz", t):
            sc.phase = "defensive"
        if re.search(r"ofensiv|atac|com a bola|criar|criacao|construc|finaliz|chance", t):
            sc.phase = "offensive" if sc.phase is None else "both"
        if re.search(r"transic|contra-ataque|contra ataque|perde-pressiona|apos perder|apos recuperar", t):
            sc.phase = "transition"
        if re.search(r"bola parada|escanteio|cobranca de falta", t):
            sc.phase = "set_pieces"
        if sc.phase:
            sc.descriptors.append({"defensive": "fase defensiva", "offensive": "fase ofensiva", "both": "ataque e defesa",
                                   "transition": "transições", "set_pieces": "bola parada"}[sc.phase])
        if re.search(r"adversari|rival|oponente|deles|do outro time", t):
            sc.team_focus = "opponent"
        if teams and len(teams) == 2:
            pos = [cls._team_position(t, tm) for tm in teams]
            if pos[1] is not None and pos[0] is None:
                sc.team_focus = "opponent"
            elif pos[0] is not None and pos[1] is not None:
                if re.search(r"compar|versus| x ", t):
                    sc.team_focus = "both"
                elif pos[1] < pos[0]:
                    sc.team_focus = "opponent"  # o time citado primeiro é o sujeito da pergunta
        if re.search(r"os dois times|ambas as equipes|ambos|comparar as equipes", t):
            sc.team_focus = "both"

        # ---- métricas
        for key, kws in METRIC_KEYWORDS.items():
            if any(k in t for k in kws):
                sc.metrics.append(key)
        if sc.players:
            sc.category = "player" if sc.category != "full_report" else sc.category
            sc.descriptors.insert(0, " / ".join(sc.players))

        sc.needs_spatial = bool(sc.side or sc.third or (set(sc.metrics) & SPATIAL_METRICS) or
                                sc.phase in ("defensive", "transition") and "compactness" in sc.metrics)
        return sc

    @staticmethod
    def _team_position(t: str, team: str) -> Optional[int]:
        """Posição da primeira menção ao time (nome ou apelido) no texto; None se não citado."""
        from src.data_hub.search import TEAM_ALIASES

        n = norm(team)
        variants = {n} | {k for k, v in TEAM_ALIASES.items() if any(norm(a) == n for a in v)}
        hits = [m.start() for v in variants if v for m in [re.search(rf"\b{re.escape(v)}\b", t)] if m]
        return min(hits) if hits else None

    @staticmethod
    def _match_players(t: str, roster: List[str]) -> List[str]:
        found: List[str] = []
        for name in roster:
            if not isinstance(name, str) or not name.strip():
                continue
            n = norm(name)
            parts = [p for p in re.split(r"[\s\-]+", n) if len(p) >= 4]
            if re.search(rf"\b{re.escape(n)}\b", t):
                found.append(name)
                continue
            # sobrenome ou primeiro nome distintivo (evita nomes curtos e comuns)
            for p in parts[-2:] + parts[:1]:
                if p in {"silva", "santos", "junior", "souza", "oliveira", "pereira", "costa", "lima"}:
                    continue
                if re.search(rf"\b{re.escape(p)}\b", t):
                    found.append(name)
                    break
        # remove duplicatas mantendo a ordem
        return list(dict.fromkeys(found))[:4]
