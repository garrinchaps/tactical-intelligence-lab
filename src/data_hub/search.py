"""
Busca universal de partidas.

Entende consultas livres como:
  "Flamengo x Palmeiras ontem", "Real Madrid x Barcelona da última rodada",
  "Brasil x Croácia 2018", "Argentina França 18/12/2022", "3869685", "Leverkusen".

Ordem de busca:
  1. ID direto (qualquer fonte, pelo ID interno);
  2. catálogo local (todas as fontes já sincronizadas);
  3. fontes remotas habilitadas (API-Football → ESPN → football-data.org) quando a
     consulta aponta para um jogo recente ou nada foi achado localmente.
Os resultados remotos entram no catálogo na hora, com o nível de dado correto.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_hub.registry import DataLevel

LEVEL_RANK = {DataLevel.EVENTS: 3, DataLevel.BOXSCORE: 2, DataLevel.RESULT: 1,
              DataLevel.SIMULATED: 0, DataLevel.UPLOAD: 0}
# a mesma partida pode existir em duas fontes: fica a mais rica
SOURCE_RANK = {"statsbomb": 5, "wyscout": 4, "api_football": 3, "espn": 2, "fdcouk": 1.5, "openfootball": 1.6, "intl": 1.2, "football_data": 1,
               "simulated": 0, "upload": 0}
MATCH_THRESHOLD = 0.86

# apelido normalizado -> nomes como aparecem nas fontes
TEAM_ALIASES: Dict[str, List[str]] = {
    "brasil": ["Brazil"], "franca": ["France"], "alemanha": ["Germany"], "espanha": ["Spain"],
    "inglaterra": ["England"], "croacia": ["Croatia"], "holanda": ["Netherlands"], "paises baixos": ["Netherlands"],
    "italia": ["Italy"], "belgica": ["Belgium"], "suica": ["Switzerland"], "suecia": ["Sweden"],
    "dinamarca": ["Denmark"], "japao": ["Japan"], "coreia do sul": ["South Korea", "Korea Republic"],
    "estados unidos": ["United States", "USA"], "eua": ["United States", "USA"], "mexico": ["Mexico"],
    "uruguai": ["Uruguay"], "colombia": ["Colombia"], "marrocos": ["Morocco"], "polonia": ["Poland"],
    "russia": ["Russia"], "gales": ["Wales"], "escocia": ["Scotland"], "irlanda": ["Republic of Ireland"],
    "atletico-mg": ["Atletico Mineiro", "Atlético-MG", "Atlético Mineiro", "Atletico-MG"],
    "atletico mineiro": ["Atletico Mineiro", "Atlético-MG", "Atlético Mineiro"],
    "galo": ["Atletico Mineiro", "Atlético-MG"], "sao paulo": ["Sao Paulo", "São Paulo"],
    "gremio": ["Gremio", "Grêmio"], "vasco": ["Vasco da Gama", "Vasco DA Gama"],
    "athletico-pr": ["Athletico Paranaense", "Athletico-PR"], "furacao": ["Athletico Paranaense"],
    "bragantino": ["RB Bragantino", "Red Bull Bragantino"], "inter": ["Internacional", "Inter"],
    "colorado": ["Internacional"], "timao": ["Corinthians"], "verdao": ["Palmeiras"], "mengao": ["Flamengo"],
    "fogao": ["Botafogo"], "tricolor": ["Fluminense", "Sao Paulo"], "raposa": ["Cruzeiro"],
    "barca": ["Barcelona"], "real": ["Real Madrid"], "atletico de madrid": ["Atletico Madrid", "Atlético Madrid"],
    "bayern": ["Bayern Munich", "FC Bayern München", "Bayern München"], "leverkusen": ["Bayer Leverkusen"],
    "dortmund": ["Borussia Dortmund"], "man city": ["Manchester City"], "city": ["Manchester City"],
    "man united": ["Manchester United"], "united": ["Manchester United"], "psg": ["Paris Saint-Germain", "PSG"],
    "milan": ["AC Milan", "Milan"], "juve": ["Juventus"], "spurs": ["Tottenham Hotspur", "Tottenham"],
}

MONTHS_PT = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
             "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}

STOPWORDS = {"de", "da", "do", "das", "dos", "o", "a", "os", "as", "jogo", "partida", "contra", "vs", "versus",
             "x", "e", "ultima", "ultimo", "rodada", "ontem", "hoje", "anteontem", "semana", "passada", "final",
             "semifinal", "campeonato", "copa", "na", "no", "em", "pela", "pelo", "analise", "analisar"}


def norm(text: Any) -> str:
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\- ]", " ", t)).strip()


@dataclass
class ParsedQuery:
    raw: str
    teams: List[str] = field(default_factory=list)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    year: Optional[int] = None
    match_id: Optional[int] = None
    wants_latest: bool = False

    @property
    def is_recent(self) -> bool:
        ref = self.date_to or (date(self.year, 12, 31) if self.year else None)
        return self.wants_latest or (ref is not None and (date.today() - ref).days <= 400)


class QueryParser:
    @staticmethod
    def parse(text: str, today: Optional[date] = None) -> ParsedQuery:
        today = today or date.today()
        q = ParsedQuery(raw=text or "")
        t = norm(text)

        m = re.fullmatch(r"\s*(\d{4,10})\s*", text or "")
        if m:
            q.match_id = int(m.group(1))
            return q

        if "anteontem" in t:
            q.date_from = q.date_to = today - timedelta(days=2)
        elif "ontem" in t:
            q.date_from = q.date_to = today - timedelta(days=1)
        elif re.search(r"\bhoje\b", t):
            q.date_from = q.date_to = today
        elif "semana passada" in t:
            q.date_from, q.date_to = today - timedelta(days=13), today - timedelta(days=6)
        if re.search(r"\bultim[oa]s?\b|\brecente\b|\bmais recente\b", t):
            q.wants_latest = True
            q.date_from, q.date_to = q.date_from or today - timedelta(days=21), q.date_to or today

        dm = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text or "")
        iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text or "")
        try:
            if iso:
                q.date_from = q.date_to = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
            elif dm:
                yy = dm.group(3)
                year = (int(yy) + 2000 if yy and len(yy) == 2 else int(yy)) if yy else today.year
                d = date(year, int(dm.group(2)), int(dm.group(1)))
                if not yy and d > today:
                    d = date(year - 1, d.month, d.day)
                q.date_from = q.date_to = d
        except ValueError:
            pass
        for name, num in MONTHS_PT.items():
            mm = re.search(rf"\b(\d{{1,2}}) de {name}(?: de (\d{{4}}))?", t)
            if mm:
                year = int(mm.group(2)) if mm.group(2) else today.year
                try:
                    q.date_from = q.date_to = date(year, num, int(mm.group(1)))
                except ValueError:
                    pass
        ym = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", t)
        if ym and not q.date_from:
            q.year = int(ym.group(1))

        cleaned = re.sub(r"\b\d{1,4}([/-]\d{1,2}){0,2}\b", " ", t)
        for name in MONTHS_PT:
            cleaned = cleaned.replace(name, " ")
        parts = re.split(r"\s(?:x|vs|versus|contra|e)\s|\s-\s", f" {cleaned} ")
        teams = []
        for part in parts:
            tokens = [w for w in part.split() if w not in STOPWORDS]
            if tokens:
                teams.append(" ".join(tokens))
        q.teams = teams[:2]
        return q


def team_variants(token: str) -> List[str]:
    n = norm(token)
    out = [n] + [norm(a) for a in TEAM_ALIASES.get(n, [])]
    return list(dict.fromkeys(v for v in out if v))


def team_score(token: str, candidate: str) -> float:
    """0..1 de semelhança entre o que o usuário digitou e o nome do time no catálogo."""
    c = norm(candidate)
    best = 0.0
    for v in team_variants(token):
        if not v:
            continue
        if v == c:
            return 1.0
        if re.search(rf"\b{re.escape(v)}\b", c) or re.search(rf"\b{re.escape(c)}\b", v):
            best = max(best, 0.92)
        best = max(best, SequenceMatcher(None, v, c).ratio())
    return best


def fast_scores(token: str, names) -> Dict[str, float]:
    """team_score para muitos nomes de uma vez: descarta cedo quem não pode passar do limite (quick_ratio)."""
    variants = [v for v in team_variants(token) if v]
    out: Dict[str, float] = {}
    for n in names:
        c = norm(n)
        best = 0.0
        for v in variants:
            if v == c:
                best = 1.0
                break
            if v in c or c in v:
                if re.search(rf"\b{re.escape(v)}\b", c) or re.search(rf"\b{re.escape(c)}\b", v):
                    best = max(best, 0.92)
                    continue
            sm = SequenceMatcher(None, v, c)
            if sm.real_quick_ratio() >= MATCH_THRESHOLD and sm.quick_ratio() >= MATCH_THRESHOLD:
                best = max(best, sm.ratio())
        out[n] = best
    return out


class UniversalMatchFinder:
    def __init__(self, db: DataHubDB, providers: Optional[Dict[str, Any]] = None):
        self.db = db
        self.providers = providers or {}

    # ------------------------------------------------------------- local
    only_analyzable: bool = True     # esconde jogos só com placar (ajustável em Bastidores › Dados)
    only_real: bool = True           # esconde simulações e uploads (alternável ao lado da busca)
    levels: Optional[Tuple[str, ...]] = None   # níveis escolhidos no topo (EVENTS/BOXSCORE/RESULT); None = regra acima

    def search_local(self, q: ParsedQuery, limit: int = 15) -> pd.DataFrame:
        where, params = [], []
        if self.levels:
            where.append("data_level IN (" + ",".join(f"'{l}'" for l in self.levels if l.isalpha() or "_" in l)
                         + ",'SIMULATED','UPLOAD')")
        elif self.only_analyzable:
            where.append("data_level IN ('EVENTS', 'BOXSCORE', 'SIMULATED', 'UPLOAD')")
        if self.only_real:
            where.append("data_level NOT IN ('SIMULATED', 'UPLOAD')")
        if q.date_from and q.date_to:
            where.append("match_date BETWEEN ? AND ?")
            params += [q.date_from.isoformat(), q.date_to.isoformat()]
        elif q.year:
            where.append("(substr(match_date,1,4) = ? OR season_name LIKE ?)")
            params += [str(q.year), f"%{q.year}%"]
        cat = self._catalog(" AND ".join(where), tuple(params))
        if cat.empty or not q.teams:
            return cat.head(limit) if not q.teams else cat.iloc[0:0]
        # semelhança calculada UMA vez por nome distinto (milhares), e não por linha (centenas de milhares)
        names = pd.unique(pd.concat([cat["home_team_name"], cat["away_team_name"]]).dropna())
        maps = [fast_scores(t, names) for t in q.teams[:2]]
        h, a = cat["home_team_name"], cat["away_team_name"]
        if len(maps) == 1:
            score = pd.concat([h.map(maps[0]), a.map(maps[0])], axis=1).max(axis=1)
        else:
            s1 = pd.concat([h.map(maps[0]), a.map(maps[1])], axis=1).min(axis=1)
            s2 = pd.concat([a.map(maps[0]), h.map(maps[1])], axis=1).min(axis=1)
            score = pd.concat([s1, s2], axis=1).max(axis=1)
        cat = cat.assign(score=score.fillna(0))
        cat = cat[cat["score"] >= MATCH_THRESHOLD]
        if cat.empty:
            return cat
        cat["level_rank"] = cat["data_level"].map(LEVEL_RANK).fillna(0)
        cat["source_rank"] = cat["data_source"].map(SOURCE_RANK).fillna(0)
        cat = cat.sort_values(["score", "match_date", "level_rank", "source_rank"],
                              ascending=[False, False, False, False])
        # deduplica a mesma partida vinda de fontes diferentes (mesma data + mesmos times) — só entre os melhores
        cat = cat.head(max(limit * 40, 200)).copy()
        nm = {n: norm(n) for n in pd.unique(pd.concat([cat["home_team_name"], cat["away_team_name"]]))}
        hn, an = cat["home_team_name"].map(nm), cat["away_team_name"].map(nm)
        cat["_pair"] = [f"{x}|{y}" if x <= y else f"{y}|{x}" for x, y in zip(hn, an)]
        key = cat["match_date"].astype(str) + "#" + cat["_pair"]
        first = ~key.duplicated(keep="first")
        alt: Dict[str, List[str]] = {}
        for k, src, f in zip(key, cat["data_source"], first):
            if not f:
                alt.setdefault(k, []).append(str(src))
        cat = cat[first].copy()
        cat["also_in"] = [", ".join(alt.get(k, [])) for k in key[first]]
        return cat.drop(columns=["_pair"]).head(limit)

    def _catalog(self, where: str, params: tuple) -> pd.DataFrame:
        """Catálogo com memória: relido só quando o banco muda (a busca roda a cada tecla/clique)."""
        try:
            ver = self.db.stable_version()
        except Exception:
            ver = None
        key = (ver, where, params)
        cache = getattr(self, "_cat_cache", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        df = self.db.catalog(where, params)
        self._cat_cache = (key, df)
        return df

    # ------------------------------------------------------------ remota
    def search_remote(self, q: ParsedQuery) -> Tuple[int, List[str]]:
        """Consulta as fontes remotas habilitadas e grava o que achar. Retorna (novos, avisos)."""
        notes: List[str] = []
        added = 0
        if not q.teams:
            return 0, notes
        d_to = q.date_to or date.today()
        d_from = q.date_from or (d_to - timedelta(days=21 if q.wants_latest or not q.year else 365))
        if q.year and not q.date_from:
            d_from, d_to = date(q.year, 1, 1), min(date(q.year, 12, 31), date.today())

        api = self.providers.get("api_football")
        if api is not None and api.enabled:
            try:
                ids = api.search_team_ids(q.teams[0])[:2]
                for tid, _name in ids:
                    fixtures = api.fixtures_for_team(tid, d_from, d_to)
                    recs = [api.parse_fixture(fx)[0] for fx in fixtures]
                    added += self.db.upsert_matches(recs)["added"]
            except Exception as exc:
                notes.append(f"API-Football: {exc}")
        elif api is not None:
            notes.append("API-Football desativada (configure API_FOOTBALL_KEY no .env).")

        espn = self.providers.get("espn")
        if espn is not None and espn.enabled and (d_to - d_from).days <= 31:
            try:
                for league in self._espn_leagues_for(q):
                    recs = espn.scoreboard(league, d_from, d_to)
                    recs = [r for r in recs if any(team_score(t, r["home_team_name"]) >= MATCH_THRESHOLD or
                                                   team_score(t, r["away_team_name"]) >= MATCH_THRESHOLD for t in q.teams)]
                    added += self.db.upsert_matches(recs)["added"]
            except Exception as exc:
                notes.append(f"ESPN: {exc}")
        elif espn is not None and not espn.enabled:
            notes.append("Feed ESPN desativado (ENABLE_ESPN_PUBLIC_FEED=false).")

        fd = self.providers.get("football_data")
        if fd is not None and fd.enabled and (d_to - d_from).days <= 31:
            try:
                for code in ("BSA", "PL", "PD", "SA", "BL1", "FL1", "CL"):
                    recs = fd.matches(code, d_from, d_to)
                    recs = [r for r in recs if any(team_score(t, r["home_team_name"]) >= MATCH_THRESHOLD or
                                                   team_score(t, r["away_team_name"]) >= MATCH_THRESHOLD for t in q.teams)]
                    added += self.db.upsert_matches(recs)["added"]
                    if recs:
                        break
            except Exception as exc:
                notes.append(f"football-data.org: {exc}")
        return added, notes

    @staticmethod
    def _espn_leagues_for(q: ParsedQuery) -> List[str]:
        br_tokens = {"flamengo", "palmeiras", "corinthians", "sao paulo", "santos", "gremio", "internacional",
                     "inter", "cruzeiro", "atletico-mg", "atletico mineiro", "galo", "botafogo", "fluminense",
                     "vasco", "bahia", "fortaleza", "athletico-pr", "bragantino", "vitoria", "sport", "ceara",
                     "juventude", "mirassol", "coritiba", "goias", "cuiaba", "remo", "paysandu", "chapecoense",
                     "america-mg", "verdao", "mengao", "timao", "fogao", "raposa", "colorado"}
        if any(norm(t) in br_tokens for t in q.teams):
            return ["bra.1", "bra.2", "bra.copa_do_brazil", "conmebol.libertadores", "conmebol.sudamericana"]
        return ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "uefa.champions", "uefa.europa", "por.1"]

    def _split_two_teams(self, text: str) -> Optional[List[str]]:
        """'argentina franca' -> ['argentina', 'franca'] quando as duas metades são times conhecidos."""
        words = text.split()
        names = self._known_team_names()
        best: Tuple[float, Optional[List[str]]] = (0.0, None)
        for i in range(1, len(words)):
            left, right = " ".join(words[:i]), " ".join(words[i:])
            sl = max((team_score(left, n) for n in names), default=0)
            sr = max((team_score(right, n) for n in names), default=0)
            if min(sl, sr) >= 0.9 and min(sl, sr) > best[0]:
                best = (min(sl, sr), [left, right])
        return best[1]

    def _known_team_names(self) -> List[str]:
        if not hasattr(self, "_team_cache"):
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT home_team_name FROM matches UNION SELECT away_team_name FROM matches"
                ).fetchall()
            self._team_cache = [r[0] for r in rows if r[0]]
        return self._team_cache

    # ------------------------------------------------------------- geral
    def find(self, text: str, allow_remote: bool = True) -> Dict[str, Any]:
        q = QueryParser.parse(text)
        if q.match_id is not None:
            m = self.db.get_match(q.match_id)
            if m:
                return {"status": "FOUND", "query": q, "candidates": pd.DataFrame([m]),
                        "suggestions": pd.DataFrame(), "notes": []}
            return {"status": "NOT_FOUND", "query": q, "candidates": pd.DataFrame(),
                    "suggestions": pd.DataFrame(), "notes": [
                f"Nenhuma partida com ID {q.match_id} no catálogo. Sincronize a base (página Catálogo & Dados)."]}

        if len(q.teams) == 1 and len(q.teams[0].split()) >= 2:
            q.teams = self._split_two_teams(q.teams[0]) or q.teams
        local = self.search_local(q)
        notes: List[str] = []
        need_remote = allow_remote and q.teams and (local.empty or (q.is_recent and (
            local.empty or local["match_date"].max() < (q.date_from or date.today() - timedelta(days=21)).isoformat())))
        if need_remote:
            _added, notes = self.search_remote(q)
            local = self.search_local(q)
        status = "FOUND" if not local.empty else "NOT_FOUND"
        suggestions = pd.DataFrame()
        if status == "NOT_FOUND" and q.teams and (q.date_from or q.year):
            # mesma consulta sem a data: oferece os confrontos que existem de verdade
            relaxed = ParsedQuery(raw=q.raw, teams=q.teams)
            suggestions = self.search_local(relaxed, limit=8)
            if not suggestions.empty:
                when = q.year or (q.date_from.strftime("%d/%m/%Y") if q.date_from else "")
                notes.insert(0, f"Não há esse confronto na data/ano pedido ({when}) nas fontes disponíveis. "
                                f"Encontrei {len(suggestions)} confronto(s) entre essas equipes em outras datas.")
        if status == "NOT_FOUND" and not notes:
            notes.append("Nenhuma fonte disponível tem essa partida com os filtros informados.")
        return {"status": status, "query": q, "candidates": local, "suggestions": suggestions, "notes": notes}
