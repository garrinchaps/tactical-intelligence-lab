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
    "ganhar", "ganhou", "ganhar", "venceu", "vencer", "perdeu", "perder", "empatou", "jogou", "jogaram", "jogadores",
    "artilheiro", "marcou", "marcaram", "fez", "assistencia", "assistencias", "chutou", "chutaram", "passou",
    "driblou", "desarmou", "selecao", "copa", "campeonato", "titular", "titulares", "melhor", "destaque", "craque",
    "decisivo", "virada", "classificou", "eliminou", "final", "semifinal", "jogada", "lance", "lances",
    "estrategia", "goleada", "perigo", "perigoso", "perigosa", "tocou", "toques", "anular", "parar", "neutralizar", "plano", "jogar",
}
# perguntas que pedem um fato ou um ranking de atletas (respondidas com tabela curta, não com visão geral)
RANKING_METRICS: Tuple[Tuple[str, str], ...] = (
    (r"assist", "assistencias"), (r"passe.*(decisiv|para finaliz|para chute)|criou mais chances", "passes_decisivos"),
    (r"perig|chance de (gol|finaliza)", "perigo_ia"),
    (r"no alvo|no gol|acert\w* o gol|enquadr", "finalizacoes_no_alvo"), (r"xg", "xg"), (r"xt|ameaca", "xt"),
    (r"chut|finaliz", "finalizacoes"), (r"quebra", "quebras_de_linha"), (r"progress", "passes_progressivos"),
    (r"cruz", "cruzamentos"), (r"dribl", "dribles"), (r"desarm", "desarmes"), (r"intercept", "interceptacoes"),
    (r"recuper|roub", "recuperacoes"), (r"press", "pressoes"), (r"perd\w* (a )?(bola|posse)|errou mais", "perdas_de_posse"),
    (r"falta.*sofr|sofreu.*falta", "faltas_sofridas"), (r"falta", "faltas_cometidas"), (r"cartao|cartoes|amarel", "cartoes_amarelos"),
    (r"certo|precis|acert\w* passe", "passes_certos"),
    (r"toc\w* (na|a) bola|toques|participou|envolvid|acoes com a bola|mais acion", "toques"),
    (r"passe|passou", "passes"), (r"gol", "gols"),
)
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
    ask: Optional[str] = None           # goals | ranking | result | None
    ranking_metric: Optional[str] = None
    team_named: bool = False            # a pergunta cita uma das equipes pelo nome

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

        # ---- escopo (tolera erros de digitação: "partifda" ≈ "partida") e conta equipes citadas
        football_hits = len(words & FOOTBALL_TERMS) + (2 if sc.players else 0)
        if teams:
            football_hits += 2 * sum(cls._team_position(t, tm) is not None for tm in teams if tm)
        if football_hits == 0:
            import difflib

            football_hits = sum(1 for w in words if len(w) >= 5 and difflib.get_close_matches(w, FOOTBALL_TERMS, n=1, cutoff=0.8))
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
            sc.team_named = any(p is not None for p in pos)
            if pos[1] is not None and pos[0] is None:
                sc.team_focus = "opponent"
            elif pos[0] is not None and pos[1] is not None:
                if re.search(r"compar|versus| x ", t):
                    sc.team_focus = "both"
                elif pos[1] < pos[0]:
                    sc.team_focus = "opponent"  # o time citado primeiro é o sujeito da pergunta
        if re.search(r"os dois times|ambas as equipes|ambos|comparar as equipes", t):
            sc.team_focus = "both"

        # ---- fatos, rankings e planos
        plan_rx = (r"estrategi|tatica (para|a ser|ideal|melhor)|melhor tatica|como (anular|parar|neutralizar|marcar|"
                   r"conter|segurar|evitar|vencer|ganhar d|explorar|superar)|o que (o|a|deveria|devia|poderia)\b.*\b(fazer|ter feito|mudar)|"
                   r"(poderia|deveria|podia|devia) ter (vencido|ganhado|evitado|empatado|jogado)|plano de jogo|para evitar|como (deveria|devia|poderia) jogar|o que fazer|como enfrentar")
        if re.search(plan_rx, t):
            sc.ask = "plan"
        elif re.search(r"(de )?quem (foram|foi|deu|deram|fez|fizeram) (as |a )?assistenc|quais (foram )?as assistenc|"
                       r"assistenc\w* (da|do|desta|dessa|nessa|nesta|no|na) (partida|jogo)", t) and not re.search(r"\bmais\b", t):
            sc.ask = "goals"
        elif re.search(r"quem (fez|marcou|anotou)( o| os)? gol|quem (fez|marcou) (os )?gols|autor(es)? d\w* gol|artilheiro|"
                     r"gols? (da|do|desta|dessa|nessa|nesta) (partida|jogo)|como (foram|sairam|saiu) os gols|quando (foi|foram|sairam) os gols", t):
            sc.ask = "goals"
        elif re.search(r"(quem|qual (jogador|atleta)|que jogador|jogador que|atleta que)\b.*\bmais\b|\bmais .*(jogador|atleta)|"
                       r"(melhor|destaque|craque|principal) (jogador|atleta|em campo|da partida|do jogo)|ranking", t):
            sc.ask = "ranking"
            sc.ranking_metric = next((m for rx, m in RANKING_METRICS if re.search(rx, t)), None)
            if re.search(r"melhor|destaque|craque|principal", t) and sc.ranking_metric is None:
                sc.ranking_metric = "xt"
            if sc.ranking_metric is None and re.search(r"posse|dominou|controlou", t):
                sc.ask = None           # "quem teve mais posse" é sobre as equipes, não um ranking de atletas
        elif re.search(r"(ganh|venc|perd|empat)\w*.*(partida|jogo|confronto)|por que (ganh|venc|perd)|como (ganh|venc)|"
                       r"o que .* fez para|motivo d\w* (vitoria|derrota)|resultado", t):
            sc.ask = "result"

        # ---- métricas
        for key, kws in METRIC_KEYWORDS.items():
            if any(k in t for k in kws):
                sc.metrics.append(key)
        if sc.players and sc.ask != "ranking":
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
        """
        Atletas citados. Ordem de força: nome completo > sobrenome > primeiro nome.
        "harry kane" casa só com Harry Kane (não com Harry Maguire); o primeiro nome sozinho só vale
        se for único no elenco e nenhum nome mais forte tiver sido encontrado.
        """
        common = {"silva", "santos", "junior", "souza", "oliveira", "pereira", "costa", "lima", "jose", "joao"}
        strong: List[Tuple[int, str]] = []
        weak: Dict[str, List[str]] = {}
        for name in roster:
            if not isinstance(name, str) or not name.strip():
                continue
            n = norm(name)
            parts = [p for p in re.split(r"[\s\-]+", n) if len(p) >= 3]
            m = re.search(rf"\b{re.escape(n)}\b", t)
            if m:
                strong.append((m.start(), name))
                continue
            hit = None
            for p in parts[1:]:                          # sobrenomes (qualquer um, ex.: "Di María", "Mbappé")
                if p in common or len(p) < 4:
                    continue
                mm = re.search(rf"\b{re.escape(p)}\b", t)
                if mm:
                    hit = mm
                    break
            if hit:
                strong.append((hit.start(), name))
            elif parts and len(parts[0]) >= 4 and parts[0] not in common:
                mm = re.search(rf"\b{re.escape(parts[0])}\b", t)
                if mm:
                    weak.setdefault(parts[0], []).append(name)
        found = [n for _, n in sorted(strong)]
        if not found:
            found = [names[0] for names in weak.values() if len(names) == 1]
        else:  # primeiro nome que não pertence a nenhum dos já encontrados e é único
            taken = {norm(f).split()[0] for f in found}
            found += [names[0] for first, names in weak.items() if len(names) == 1 and first not in taken]
        return list(dict.fromkeys(found))[:4]
