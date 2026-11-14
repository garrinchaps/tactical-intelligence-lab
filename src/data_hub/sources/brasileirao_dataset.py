"""
Brasileirão Série A 2003 → hoje (dataset de Adão Duque, github.com/adaoduque/Brasileirao_Dataset).

Quatro CSVs públicos:
  campeonato-brasileiro-full.csv          partidas (rodada, data, mandante, visitante, placar, arena, técnicos, formações)
  campeonato-brasileiro-estatisticas-full.csv  estatísticas por clube e partida (chutes, chutes a gol, posse,
                                          passes, precisão, faltas, cartões, impedimentos, escanteios)
  campeonato-brasileiro-gols.csv          gols por atleta e minuto
  campeonato-brasileiro-cartoes.csv       cartões por atleta e minuto

Partida com estatísticas (linhas não zeradas) → BOXSCORE; só placar/gols → RESULT. Os gols e cartões viram a
linha do tempo. Licença indicada no Kaggle do autor: GPL-2 — uso pessoal/acadêmico com crédito.
Fonte local opcional: BRASILEIRAO_DATASET_PATH=<pasta com os 4 CSVs> (ex.: um git clone do repositório).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.data_hub.registry import DataLevel, to_internal_id
from src.data_hub.tabular import (extra_minute, find_col, normalize_columns, parse_date, parse_minute, stat, to_int,
                                  to_number)

BASE = "https://raw.githubusercontent.com/adaoduque/Brasileirao_Dataset/master"
FILES = {"partidas": "campeonato-brasileiro-full.csv", "estatisticas": "campeonato-brasileiro-estatisticas-full.csv",
         "gols": "campeonato-brasileiro-gols.csv", "cartoes": "campeonato-brasileiro-cartoes.csv"}
CACHE = Path("data/raw/brasileirao")
COMPETITION = "Campeonato Brasileiro Série A"
LICENSE = "Brasileirao_Dataset (Adão Duque) — GPL-2 segundo o Kaggle do autor; crédito à fonte"
STATS = [  # (sinônimos da coluna, chave padrão, rótulo)
    (("chutes", "finalizacoes"), "shots_total", "Finalizações"),
    (("chutes_a_gol", "chutes_no_alvo", "chutes_ao_gol", "finalizacoes_no_gol"), "shots_on_target", "Finalizações no gol"),
    (("posse_de_bola", "posse"), "possession_pct", "Posse de bola (%)"),
    (("passes",), "passes_total", "Passes"),
    (("precisao_passes", "precisao_de_passes"), "pass_accuracy_pct", "Precisão de passe (%)"),
    (("faltas",), "fouls", "Faltas cometidas"),
    (("cartao_amarelo", "cartoes_amarelos"), "yellow_cards", "Cartões amarelos"),
    (("cartao_vermelho", "cartoes_vermelhos"), "red_cards", "Cartões vermelhos"),
    (("impedimentos",), "offsides", "Impedimentos"),
    (("escanteios",), "corners", "Escanteios"),
]


class BrasileiraoDatasetProvider:
    source = "brasileirao"

    def __init__(self, db=None, local: Optional[str] = None, fetch: Optional[Callable[[str], bytes]] = None):
        self.db = db
        self.local = Path(local or os.getenv("BRASILEIRAO_DATASET_PATH", "") or "") if (local or
                                                                                       os.getenv("BRASILEIRAO_DATASET_PATH")) else None
        self._fetch = fetch

    # ---------------------------------------------------------------- leitura
    def _bytes(self, key: str, max_age_days: float = 7) -> bytes:
        name = FILES[key]
        if self.local is not None and (self.local / name).exists():
            return (self.local / name).read_bytes()
        CACHE.mkdir(parents=True, exist_ok=True)
        cached = CACHE / name
        import time

        if cached.exists() and (time.time() - cached.stat().st_mtime) < max_age_days * 86400:
            return cached.read_bytes()
        try:
            if self._fetch is not None:
                data = self._fetch(f"{BASE}/{name}")
            else:
                from src.data_hub import net

                r = net.get(f"{BASE}/{name}", source="brasileirao", timeout=30)
                r.raise_for_status()
                data = r.content
        except Exception:
            if cached.exists():                       # sem internet: usa a última cópia
                return cached.read_bytes()
            raise
        cached.write_bytes(data)
        return data

    def table(self, key: str) -> pd.DataFrame:
        raw = self._bytes(key)
        for enc in ("utf-8", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding=enc, on_bad_lines="skip", low_memory=False)
                return normalize_columns(df)
            except UnicodeDecodeError:
                continue
        return pd.DataFrame()

    # ----------------------------------------------------------------- parse
    @staticmethod
    def parse(partidas: pd.DataFrame, estat: pd.DataFrame, gols: pd.DataFrame,
              cartoes: pd.DataFrame) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        P = partidas
        c_id = find_col(P, "id", "partida_id")
        c_date = find_col(P, "data")
        c_h, c_a = find_col(P, "mandante"), find_col(P, "visitante")
        c_hs = find_col(P, "mandante_placar", contains=("mandante", "placar"))
        c_as = find_col(P, "visitante_placar", contains=("visitante", "placar"))
        c_round = find_col(P, "rodada", "rodata")
        c_arena = find_col(P, "arena", "estadio")
        if not all([c_id, c_date, c_h, c_a, c_hs, c_as]):
            raise ValueError("Formato do campeonato-brasileiro-full.csv mudou (colunas de id/data/times/placar).")
        by_match: Dict[Any, List[Dict]] = {}
        if not estat.empty:
            e_id, e_club = find_col(estat, "partida_id", "id"), find_col(estat, "clube", "time")
            cols = [(find_col(estat, *syn), key, lab) for syn, key, lab in STATS]
            for r in estat.to_dict("records"):
                vals = [stat(str(r.get(e_club, "")), key, lab, r.get(col)) for col, key, lab in cols if col]
                vals = [v for v in vals if v is not None]
                if vals and any(v["value"] for v in vals):          # linha toda zerada = sem estatística
                    by_match.setdefault(to_int(r.get(e_id)), []).extend(vals)
        tl: Dict[Any, List[Dict]] = {}
        for df, kind in ((gols, "Goal"), (cartoes, "Card")):
            if df.empty:
                continue
            g_id, g_club = find_col(df, "partida_id", "id"), find_col(df, "clube", "time")
            g_pl, g_min = find_col(df, "atleta", "jogador"), find_col(df, "minuto")
            g_type = find_col(df, "tipo_de_gol", "tipo") if kind == "Goal" else find_col(df, "cartao", "tipo")
            for r in df.to_dict("records"):
                det = str(r.get(g_type) or "") if g_type else ""
                if kind == "Card":
                    det = "Red Card" if "verm" in det.lower() else "Yellow Card"
                tl.setdefault(to_int(r.get(g_id)), []).append({
                    "minute": parse_minute(r.get(g_min)), "extra_minute": extra_minute(r.get(g_min)),
                    "team_name": str(r.get(g_club) or ""), "player_name": str(r.get(g_pl) or ""),
                    "related_player": "", "event_type": kind, "detail": det or ("Normal Goal" if kind == "Goal" else "")})
        out = []
        for r in P.to_dict("records"):
            sid = to_int(r.get(c_id))
            d = parse_date(r.get(c_date))
            hs, as_ = to_int(r.get(c_hs)), to_int(r.get(c_as))
            if sid is None or not d or hs is None or as_ is None:
                continue
            h, a = str(r.get(c_h) or "").strip(), str(r.get(c_a) or "").strip()
            stats = by_match.get(sid, [])
            extra = {k: r.get(find_col(P, k)) for k in ("formacao_mandante", "formacao_visitante", "tecnico_mandante",
                                                         "tecnico_visitante") if find_col(P, k) and pd.notna(r.get(find_col(P, k)))}
            rec = {"match_id": to_internal_id("brasileirao", sid), "home_team_name": h, "away_team_name": a,
                   "match_date": d, "home_score": hs, "away_score": as_, "competition_name": COMPETITION,
                   "season_name": d[:4], "country_name": "Brazil", "status": "FT",
                   "round_name": f"Rodada {to_int(r.get(c_round))}" if c_round and to_int(r.get(c_round)) else "",
                   "stadium_name": str(r.get(c_arena) or "") if c_arena else "",
                   "data_source": "brasileirao", "data_level": DataLevel.BOXSCORE if stats else DataLevel.RESULT,
                   "source_match_id": sid, "extra_json": json.dumps(extra, ensure_ascii=False, default=str)}
            out.append((rec, {"team_stats": stats, "lineups": [], "timeline": tl.get(sid, [])}))
        return out

    # ------------------------------------------------------------------ sync
    def sync(self, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        frames = {}
        for k in FILES:
            try:
                frames[k] = self.table(k)
            except Exception as exc:
                if k == "partidas":
                    raise
                say(f"  brasileirão: {FILES[k]} indisponível ({exc})")
                frames[k] = pd.DataFrame()
        rows = self.parse(frames["partidas"], frames["estatisticas"], frames["gols"], frames["cartoes"])
        r = self.db.upsert_matches([rec for rec, _ in rows])
        n_stats = 0
        for rec, box in rows:
            if box["team_stats"] or box["timeline"]:
                self.db.save_boxscore(rec["match_id"], box)
                n_stats += bool(box["team_stats"])
        say(f"  brasileirão: {len(rows)} partidas, {n_stats} com estatísticas")
        return {"added": r["added"], "updated": r["updated"], "partidas": len(rows), "com_estatisticas": n_stats}
