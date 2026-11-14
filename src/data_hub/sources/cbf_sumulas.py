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
COMP_FROM_PATH = [(r"serie[_\- ]?a\b|seriea|brasileirao", "Campeonato Brasileiro Série A"),
                  (r"serie[_\- ]?b\b|serieb", "Campeonato Brasileiro Série B"),
                  (r"serie[_\- ]?c\b|seriec", "Campeonato Brasileiro Série C"),
                  (r"serie[_\- ]?d\b|seried", "Campeonato Brasileiro Série D"),
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
        base = self.path / "results" if (self.path / "results").exists() else self.path
        return [p for p in sorted(base.rglob("*")) if p.suffix.lower() in (".csv", ".json", ".parquet")]

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
        for f in self.files():
            rows = [x for df in read_any(f) for x in self.parse_table(df, f)]
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
