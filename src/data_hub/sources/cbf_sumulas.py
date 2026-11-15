"""
Súmulas oficiais da CBF (github.com/BrazilianFootball/Data, MIT) — ~11 mil jogos de 2013 a 2025:
Série A, B, C, D e Copa do Brasil, raspados das súmulas eletrônicas (escalações, gols, cartões, árbitro, estádio).

O repositório não documenta o formato dos arquivos da pasta `results/`, então este leitor reconhece as colunas
por sinônimos (mandante/visitante, placar, data, gols e cartões por atleta/minuto) em CSV, JSON ou Parquet.
Uso:
    python -m src.data_hub.sync --only cbf      (na primeira vez baixa o repositório como .zip, sem git nem conta;
                                                 ou aponte CBF_DATA_PATH para um git clone já existente)
    python -m src.data_hub.sources.cbf_sumulas --inspecionar      (mostra o que foi reconhecido)

As súmulas não trazem estatísticas de equipe (chutes, posse…): os jogos entram como SÓ PLACAR, com a linha do
tempo (gols e cartões), e servem para completar a mesma partida em outras bases (Brasileirão, ESPN, fdcouk).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.data_hub.registry import DataLevel, to_internal_id
from src.data_hub.tabular import (describe, find_col, normalize_columns, parse_date, parse_minute, read_any, stable_id,
                                  to_int)

LICENSE = "BrazilianFootball/Data — MIT (súmulas eletrônicas da CBF)"
COMP_FROM_PATH = [(r"(^|[\\/_\- ])cdb[_\- ]", "Copa do Brasil"),
                  (r"serie[_\- ]?a(?![a-z])|seriea|brasileirao", "Campeonato Brasileiro Série A"),
                  (r"serie[_\- ]?b(?![a-z])|serieb", "Campeonato Brasileiro Série B"),
                  (r"serie[_\- ]?c(?![a-z])|seriec", "Campeonato Brasileiro Série C"),
                  (r"serie[_\- ]?d(?![a-z])|seried", "Campeonato Brasileiro Série D"),
                  (r"copa[_\- ]?do[_\- ]?brasil|brazil[_\- ]?cup|copa_brasil", "Copa do Brasil")]
HOME = ("mandante", "mandante_nome", "time_mandante", "clube_mandante", "home", "home_team", "home_team_name", "team1")
AWAY = ("visitante", "visitante_nome", "time_visitante", "clube_visitante", "away", "away_team", "away_team_name", "team2")
HG = ("gols_mandante", "mandante_gols", "placar_mandante", "mandante_placar", "home_goals", "home_score", "score_home")
AG = ("gols_visitante", "visitante_gols", "placar_visitante", "visitante_placar", "away_goals", "away_score", "score_away")
DATE = ("data", "data_jogo", "data_partida", "date", "match_date", "datetime")


def competition_from_path(p: Path) -> str:
    low = str(p).lower()
    return next((name for rx, name in COMP_FROM_PATH if re.search(rx, low)), "")


def season_from_path(p: Path) -> str:
    m = re.findall(r"(20[12]\d)", str(p))
    return m[-1] if m else ""


def _plain(s: Any) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def split_team(v: Any) -> Tuple[str, str]:
    """"Remo / PA" → ("Remo", "PA");  "Flamengo/RJ" → ("Flamengo", "RJ");  "Botafogo" → ("Botafogo", "")"""
    txt = re.sub(r"\s+", " ", str(v or "")).strip()
    m = re.match(r"^(.*?)\s*/\s*([A-Za-z]{2})$", txt)
    return (m.group(1).strip(), m.group(2).upper()) if m else (txt, "")


# "09:00 2T11NRRafael Lima Pereira Flamengo/RJ"  ·  "+2 1T9NR..."  ·  "28:00 2T3Renato dos Santos ..."
# minuto da súmula = tempo dentro de cada etapa (2T 09:00 → 54'); acréscimo "+N" conta a partir do fim da etapa
_LINE = re.compile(r"^\s*(?:(\d{1,3}):(\d{2})|\+(\d{1,2}))\s*(1T|2T|INT|0T|1P|2P)?\s*(\d{1,3})?\s*"
                   r"(NR|PN|FT|CT|GC)?\s*(.*)$")
GOAL_KIND = {"NR": "Normal Goal", "PN": "Penalty", "FT": "Normal Goal", "CT": "Own Goal", "GC": "Own Goal"}


def parse_sumula_line(txt: Any, kind: str, sides: List[Tuple[str, Any, str]]) -> Optional[Dict[str, Any]]:
    """Uma linha de gol/cartão da súmula → evento. Sem time identificável na linha, devolve None (não adivinha)."""
    m = _LINE.match(str(txt or ""))
    if not m:
        return None
    mm, _, plus, half, _num, code, rest = m.groups()
    base = 45 if half in ("2T", "2P") else 0
    if plus:
        if half not in ("1T", "2T", "1P", "2P"):
            return None                                   # acréscimo sem etapa: minuto desconhecido
        minute, extra = base + 45, int(plus)
    else:
        minute, extra = base + int(mm), None
    rest = re.sub(r"\s+", " ", rest or "").strip(" -")
    low = _plain(rest)
    team, player, best = "", rest, 0
    for name, raw, short in sides:                       # o time vem no fim da linha ("... Flamengo/RJ")
        b, u = split_team(raw)
        for variant in {f"{b}/{u}" if u else "", f"{b} / {u}" if u else "", b, short or ""}:
            pv = _plain(variant)
            if pv and low.endswith(pv) and len(pv) > best:   # a variante mais longa vence ("Santa Cruz/PE" > "Cruz")
                team, player, best = name, rest[: len(rest) - len(variant)].strip(" -"), len(pv)
    if not team:                                          # grafia diferente ("Atlético/PR" × "Athletico Paranaense")
        tail = re.search(r"/\s*([A-Za-z]{2})$", rest)
        same_uf = [(n, r) for n, r, _ in sides if tail and split_team(r)[1] == tail.group(1).upper()]
        if len(same_uf) == 1:                             # só um dos dois times é desse estado
            team = same_uf[0][0]
            words = rest[: tail.start()].split()
            base_words = {_plain(w) for w in re.split(r"[\s.]+", split_team(same_uf[0][1])[0]) if w}
            while words and (_plain(words[-1]).strip(".") in base_words or len(words) > 1 and "." in words[-1]):
                words.pop()
            if words and words != rest[: tail.start()].split():
                player = " ".join(words)
            else:
                player = " ".join(words[:-1]) if len(words) > 1 else ""
    if not team:
        return None
    if kind == "Goal":
        return {"minute": minute, "extra_minute": extra, "team_name": team, "player_name": player or "",
                "related_player": "", "event_type": "Goal", "detail": GOAL_KIND.get(code or "NR", "Normal Goal")}
    return {"minute": minute, "extra_minute": extra, "team_name": team, "player_name": player or "",
            "related_player": "", "event_type": "Card", "detail": kind}


def fix_own_goals(goals: List[Dict[str, Any]], home: str, away: str, hs: int, as_: int) -> List[Dict[str, Any]]:
    """
    Os gols da linha do tempo têm de somar o placar. Gol contra pode vir com o time de quem marcou (convenção da
    súmula) ou com o time beneficiado; usa a leitura que bate com o placar. Se nenhuma bate, a linha do tempo
    fica sem gols (o placar oficial continua) — nunca mostra um autor no time errado.
    """
    def score(gs):
        return (sum(g["team_name"] == home for g in gs), sum(g["team_name"] == away for g in gs))

    def credited(gs, flip):
        out = []
        for g in gs:
            if g["detail"] == "Own Goal" and flip:
                g = dict(g, team_name=away if g["team_name"] == home else home)
            out.append(g)
        return out

    for flip in (True, False):                            # "time de quem marcou contra" é o mais comum
        gs = credited(goals, flip)
        if score(gs) == (hs, as_):
            return gs
    return []


class CbfSumulasProvider:
    source = "cbf"

    def __init__(self, db=None, path: Optional[str] = None):
        self.db = db
        self.path = Path(path or os.getenv("CBF_DATA_PATH", "") or "data/raw/cbf")

    @property
    def enabled(self) -> bool:
        return self.path.exists()

    ZIP = "https://codeload.github.com/BrazilianFootball/Data/zip/refs/heads/main"

    def download(self, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        """Baixa o repositório como .zip (sem git, sem conta) e extrai só a pasta results/."""
        import zipfile

        from src.data_hub import net

        say = progress or (lambda m: None)
        self.path.mkdir(parents=True, exist_ok=True)
        z = self.path / "_repo.zip"
        say("  cbf: baixando as súmulas do GitHub (BrazilianFootball/Data)...")
        net.download(self.ZIP, z, progress=say, source="cbf", timeout=120)
        n = 0
        with zipfile.ZipFile(z) as zf:
            for member in zf.namelist():
                parts = Path(member).parts
                if "results" in parts and not member.endswith("/"):
                    rel = Path(*parts[parts.index("results"):])
                    out = self.path / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(zf.read(member))
                    n += 1
        z.unlink(missing_ok=True)
        say(f"  cbf: {n} arquivo(s) de súmulas extraído(s)")
        return {"arquivos": n}

    def files(self) -> List[Path]:
        """Com a pasta processed/ do BrazilianFootball (um JSON por competição e ano), usa só ela: os ~19 mil CSVs
        de raw/ são o texto bruto de cada súmula, já consolidado nesses JSON."""
        base = self.path / "results" if (self.path / "results").exists() else self.path
        all_ = [p for p in sorted(base.rglob("*")) if p.suffix.lower() in (".csv", ".json", ".parquet")]
        games = [p for p in all_ if p.name.lower().endswith("_games.json")]
        return games or all_

    # ------------------------------------------------------------ formato BrazilianFootball (processed/*_games.json)
    @staticmethod
    def is_games_json(p: Path) -> bool:
        return p.name.lower().endswith("_games.json")

    @staticmethod
    def games_from_json(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Aceita os dois jeitos de gravar o mesmo conteúdo:
          {"003": {"date": ..., "home": ...}}            (formato real do BrazilianFootball/Data)
          {"003_date": ..., "003_home": ...}              (o mesmo achatado)
        """
        games: Dict[str, Dict[str, Any]] = {}
        for k, v in (data or {}).items():
            if isinstance(v, dict) and re.match(r"^\d+$", str(k)):
                games.setdefault(str(k), {}).update({str(a): b for a, b in v.items()})
                continue
            m = re.match(r"^(\d+)_(.+)$", str(k))
            if m:
                games.setdefault(m.group(1), {})[m.group(2)] = v
        return games

    def parse_games_json(self, path: Path, names: Optional[Dict[Tuple[str, str], str]] = None
                         ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        import json

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, list):
            data = {f"{i:03d}_{k}": v for i, g in enumerate(data) if isinstance(g, dict) for k, v in g.items()}
        comp = competition_from_path(path) or "Futebol brasileiro (CBF)"
        season = season_from_path(path)
        out = []
        for num, g in sorted(self.games_from_json(data).items()):
            res = re.match(r"\s*(\d+)\s*[xX]\s*(\d+)", str(g.get("result") or ""))
            d = parse_date(g.get("date"))
            (hb, hu), (ab, au) = split_team(g.get("home")), split_team(g.get("away"))
            if not (res and d and hb and ab):
                continue                                    # jogo sem placar (adiado, W.O. sem súmula): fica de fora
            h = (names or {}).get((hb, hu), hb)
            a = (names or {}).get((ab, au), ab)
            hs, as_ = int(res.group(1)), int(res.group(2))
            stadium = str(g.get("stadium") or "").split(" / ")[0].strip()
            rec = {"match_id": to_internal_id("cbf", stable_id(comp, d, h.lower(), a.lower())),
                   "source_match_id": f"{Path(path).stem}:{num}", "home_team_name": h, "away_team_name": a,
                   "match_date": d, "home_score": hs, "away_score": as_, "competition_name": comp,
                   "season_name": season or d[:4], "country_name": "Brazil", "status": "FT",
                   "round_name": "", "stadium_name": stadium, "referee_name": "", "data_source": "cbf",
                   "data_level": DataLevel.RESULT,
                   "extra": {"jogo_cbf": num, "horario": g.get("time") or ""}}
            sides = [(h, g.get("home"), hb), (a, g.get("away"), ab)]
            goals = [e for e in (parse_sumula_line(x, "Goal", sides) for x in g.get("goals") or []) if e]
            goals = fix_own_goals(goals, h, a, hs, as_)
            cards = [e for kind, col in (("Yellow Card", "yellow_cards"), ("Red Card", "red_cards"))
                     for e in (parse_sumula_line(x, kind, sides) for x in g.get(col) or []) if e]
            tl = sorted(goals + cards, key=lambda e: (e["minute"] if e["minute"] is not None else 999))
            out.append((rec, {"team_stats": [], "lineups": [], "timeline": tl}))
        return out

    def team_names(self, files: List[Path]) -> Dict[Tuple[str, str], str]:
        """
        Mesmo nome em estados diferentes (América/MG × América/RN, Guarani/SP × Guarani/CE, Flamengo/RJ × Flamengo/PI):
        o estado com mais jogos fica com o nome puro (bate com as outras bases); os outros ganham o sufixo "-UF".
        """
        import json
        from collections import Counter

        cnt: Counter = Counter()
        for f in files:
            if not self.is_games_json(f):
                continue
            try:
                for g in self.games_from_json(json.loads(f.read_text(encoding="utf-8"))).values():
                    for side in ("home", "away"):
                        b, u = split_team(g.get(side))
                        if b:
                            cnt[(b, u)] += 1
            except Exception:
                continue
        by_base: Dict[str, List[Tuple[str, int]]] = {}
        for (b, u), n in cnt.items():
            by_base.setdefault(b, []).append((u, n))
        names: Dict[Tuple[str, str], str] = {}
        for b, ufs in by_base.items():
            ufs.sort(key=lambda t: -t[1])
            for i, (u, _) in enumerate(ufs):
                names[(b, u)] = b if i == 0 or not u else f"{b}-{u}"
        return names

    @staticmethod
    def _timeline(row: Dict[str, Any], home: str, away: str) -> List[Dict[str, Any]]:
        """Listas aninhadas de gols/cartões (JSON) → linha do tempo."""
        out = []
        for col, val in row.items():
            if not isinstance(val, list) or not val or not isinstance(val[0], dict):
                continue
            kind = "Goal" if "gol" in col or "goal" in col else ("Card" if "cart" in col or "card" in col else None)
            if not kind:
                continue
            for it in val:
                it = {re.sub(r"[^a-z0-9]+", "_", str(k).lower()): v for k, v in it.items()}
                team = str(it.get("clube") or it.get("time") or it.get("team") or "")
                if not team:
                    side = str(it.get("lado") or it.get("side") or "").lower()
                    team = home if side.startswith(("m", "h")) else (away if side.startswith(("v", "a")) else "")
                det = str(it.get("tipo") or it.get("cartao") or it.get("type") or "")
                if kind == "Card":
                    det = "Red Card" if "verm" in det.lower() or "red" in det.lower() else "Yellow Card"
                out.append({"minute": parse_minute(it.get("minuto") or it.get("minute") or it.get("tempo")),
                            "extra_minute": None, "team_name": team,
                            "player_name": str(it.get("atleta") or it.get("jogador") or it.get("player") or it.get("nome") or ""),
                            "related_player": "", "event_type": kind, "detail": det or "Normal Goal"})
        return out

    def parse_table(self, df: pd.DataFrame, src: Path) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        D = normalize_columns(df)
        c_h, c_a = find_col(D, *HOME), find_col(D, *AWAY)
        c_hg, c_ag, c_d = find_col(D, *HG), find_col(D, *AG), find_col(D, *DATE)
        if not (c_h and c_a and c_hg and c_ag and c_d):
            return []
        c_c = find_col(D, "campeonato", "competicao", "competition", "torneio")
        c_s = find_col(D, "ano", "temporada", "season")
        c_r = find_col(D, "rodada", "round")
        c_st = find_col(D, "estadio", "arena", "stadium", "local")
        c_ref = find_col(D, "arbitro", "referee", contains=("arbitro",))
        comp_p, season_p = competition_from_path(src), season_from_path(src)
        out = []
        for r in D.to_dict("records"):
            d = parse_date(r.get(c_d))
            h, a = str(r.get(c_h) or "").strip(), str(r.get(c_a) or "").strip()
            hs, as_ = to_int(r.get(c_hg)), to_int(r.get(c_ag))
            if not d or not h or not a or hs is None or as_ is None:
                continue
            comp = (str(r.get(c_c)) if c_c and pd.notna(r.get(c_c)) else "") or comp_p or "Futebol brasileiro (CBF)"
            rec = {"match_id": to_internal_id("cbf", stable_id(comp, d, h.lower(), a.lower())), "home_team_name": h,
                   "away_team_name": a, "match_date": d, "home_score": hs, "away_score": as_, "competition_name": comp,
                   "season_name": str(to_int(r.get(c_s)) or "") if c_s else (season_p or d[:4]),
                   "country_name": "Brazil", "status": "FT",
                   "round_name": f"Rodada {to_int(r.get(c_r))}" if c_r and to_int(r.get(c_r)) else "",
                   "stadium_name": str(r.get(c_st) or "") if c_st else "", "referee_name": str(r.get(c_ref) or "") if c_ref else "",
                   "data_source": "cbf", "data_level": DataLevel.RESULT}
            out.append((rec, {"team_stats": [], "lineups": [], "timeline": self._timeline(r, h, a)}))
        return out

    def sync(self, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        if not self.enabled or not self.files():
            self.download(progress=say)                    # primeira vez: baixa sozinho
        tot = {"added": 0, "updated": 0, "arquivos": 0, "nao_reconhecidos": 0, "partidas": 0}
        files = self.files()
        names = self.team_names(files)
        for f in files:
            try:
                rows = (self.parse_games_json(f, names) if self.is_games_json(f)
                        else [x for df in read_any(f) for x in self.parse_table(df, f)])
            except Exception as exc:
                say(f"  cbf {f.name}: {exc}")
                rows = []
            if not rows:
                tot["nao_reconhecidos"] += 1
                continue
            r = self.db.upsert_matches([rec for rec, _ in rows])
            for rec, box in rows:
                if box["timeline"] and not self.db.has_boxscore(rec["match_id"]):
                    self.db.save_boxscore(rec["match_id"], box)
            tot["added"] += r["added"]
            tot["updated"] += r["updated"]
            tot["arquivos"] += 1
            tot["partidas"] += len(rows)
        say(f"  cbf: {tot['partidas']} jogos de {tot['arquivos']} arquivo(s); {tot['nao_reconhecidos']} arquivo(s) "
            "com formato não reconhecido (rode --inspecionar)")
        return tot


def inspect(path: Optional[str] = None, n_files: int = 8) -> str:
    """Estrutura da pasta (subpastas e extensões) + amostra de arquivos de subpastas diferentes."""
    from collections import Counter

    p = CbfSumulasProvider(path=path)
    files = p.files() if p.enabled else []
    if not files:
        return f"Nenhum arquivo em {p.path}."
    root = Path(p.path)
    rel = lambda f: str(f.relative_to(root)) if root in f.parents else f.name
    dirs = Counter(str(Path(rel(f)).parent) for f in files)
    exts = Counter(f.suffix.lower() for f in files)
    out = [f"{len(files)} arquivo(s) em {p.path}",
           "extensões: " + ", ".join(f"{k or '(sem)'}={v}" for k, v in exts.most_common()),
           "subpastas (top 15): " + ", ".join(f"{k}={v}" for k, v in dirs.most_common(15))]
    seen, sample = set(), []
    for f in files:                                   # um arquivo por subpasta, até n_files
        d = str(Path(rel(f)).parent)
        if d not in seen:
            seen.add(d)
            sample.append(f)
        if len(sample) >= n_files:
            break
    sample += [f for f in files if f not in sample][:max(0, n_files - len(sample))]
    games = [f for f in files if CbfSumulasProvider.is_games_json(f)]
    if games:                                         # formato BrazilianFootball: mostra um jogo inteiro + o resultado
        import json

        f = games[0]
        g = next(iter(CbfSumulasProvider.games_from_json(json.loads(f.read_text(encoding="utf-8"))).values()), {})
        out.append(f"[jogo completo] {rel(f)}\n" + "\n".join(f"  - {k}: {str(v)[:400]}" for k, v in g.items()))
        rows = p.parse_games_json(f, p.team_names(games))
        with_tl = sum(1 for _, b in rows if b["timeline"])
        out.append(f"[reconhecido] {len(games)} arquivo(s) *_games.json · {rel(f)}: {len(rows)} jogos, "
                   f"{with_tl} com linha do tempo conferida com o placar")
        sample = []
    for f in sample:
        tables = read_any(f)[:2]
        if not tables:
            try:
                head = f.read_text(encoding="utf-8", errors="replace")[:700]
            except Exception as exc:
                head = f"(não deu para ler: {exc})"
            out.append(f"[NÃO lido] {rel(f)}\n{head}")
        for df in tables:
            ok = bool(p.parse_table(df.head(50), f))
            out.append(f"[{'reconhecido' if ok else 'NÃO reconhecido'}] {rel(f)}\n{describe(normalize_columns(df.head(50)))}")
    return "\n\n".join(out)


if __name__ == "__main__":
    try:  # lê o .env (OPENPLAY_PATH, CBF_SUMULAS_PATH, caminho do banco...) também quando rodado direto
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    import sys

    print(inspect() if "--inspecionar" in sys.argv else __doc__)
