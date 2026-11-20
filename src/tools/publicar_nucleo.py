"""
Rodada 22 — BASE NÚCLEO para publicar o app 24 h sem o PC (ver docs/PLANO_PUBLICACAO.md, seção 7).

A base inteira tem ~11 GB (muito do peso são lances e anos antigos). O núcleo leva o que o app usa no dia a dia:

  * TODAS as partidas (o catálogo inteiro, ~440 mil linhas, leve);
  * estatísticas por time, por jogador, escalações, chutes, linha do tempo e extras dos últimos N anos (padrão 3);
  * calendário, elencos (FotMob/ESPN), apelidos de times, empréstimos e votos/planos do Scout;
  * NÃO leva os lances (eventos) — StatsBomb e OpenPlay são baixados das fontes públicas quando alguém abre o jogo.

    python -m src.tools.publicar_nucleo                     # gera data/publicacao/nucleo.db (app FECHADO)
    python -m src.tools.publicar_nucleo --anos 2            # menor ainda
    python -m src.tools.publicar_nucleo --tamanho           # só estima o tamanho, não grava

Nada aqui envia arquivo para a internet: o envio (Hugging Face, privado) é um comando à parte, explicado no plano.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import date, timedelta
from pathlib import Path

OUT = Path("data/publicacao/nucleo.db")
BY_MATCH = ["match_team_stats", "match_player_stats", "match_lineups", "match_shots", "match_timeline", "match_extra"]
WHOLE = ["fixtures", "fotmob_rosters", "fotmob_teams_v2", "fotmob_loans", "espn_rosters", "team_aliases", "frozen_matches",
         "scout_feedback", "scout_plans", "scout_manual_loans", "scout_player_votes", "competition_sync_state"]
SKIP = {"events", "sqlite_sequence", "sqlite_stat1", "api_usage", "sync_runs", "tactical_diagnostics_log", "fotmob_tried",
        "player_merge_candidates", "fotmob_teams"}


def _tables(c: sqlite3.Connection) -> list:
    return [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]


def estimate(src: Path, years: int) -> dict:
    cut = (date.today() - timedelta(days=365 * years)).isoformat()
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as c:
        n_all = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        n_recent = c.execute("SELECT COUNT(*) FROM matches WHERE match_date >= ?", (cut,)).fetchone()[0]
        rows = {}
        for t in BY_MATCH:
            if t in _tables(c):
                rows[t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE match_id IN (SELECT match_id FROM matches WHERE match_date >= ?)",
                                    (cut,)).fetchone()[0]
    return {"partidas": n_all, "partidas_recentes": n_recent, "linhas": rows, "corte": cut}


def build(src: Path, out: Path = OUT, years: int = 3, progress=print) -> dict:
    cut = (date.today() - timedelta(days=365 * years)).isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    t0 = time.time()
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s:
        schema = [r for r in s.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
                                       "AND name NOT LIKE 'sqlite_%'")]
        tables = _tables(s)
    d = sqlite3.connect(f"file:{tmp.resolve()}", uri=True)          # uri=True: permite ATTACH só leitura
    d.execute("PRAGMA journal_mode=OFF")
    d.execute("PRAGMA synchronous=OFF")
    for typ, name, sql in schema:                       # tabelas primeiro; índices e gatilhos no fim
        if typ == "table" and name not in SKIP:
            d.execute(sql)
    d.execute("ATTACH DATABASE ? AS src", (f"file:{Path(src).resolve()}?mode=ro",))
    d.execute("INSERT INTO matches SELECT * FROM src.matches")
    progress(f"  partidas: {d.execute('SELECT COUNT(*) FROM matches').fetchone()[0]:,}".replace(",", "."))
    for t in BY_MATCH:
        if t in tables:
            d.execute(f"INSERT INTO {t} SELECT * FROM src.{t} WHERE match_id IN "
                      f"(SELECT match_id FROM src.matches WHERE match_date >= ?)", (cut,))
            progress(f"  {t}: {d.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:,}".replace(",", "."))
    for t in WHOLE:
        if t in tables:
            d.execute(f"INSERT INTO {t} SELECT * FROM src.{t}")
    if "source_state" in tables:
        d.execute("INSERT INTO source_state SELECT * FROM src.source_state WHERE source IN ('cache')")
    d.commit()
    d.execute("DETACH DATABASE src")
    for typ, name, sql in schema:
        if typ in ("index", "trigger"):
            try:
                d.execute(sql)
            except sqlite3.Error:
                pass
    d.commit()
    d.execute("VACUUM")
    d.close()
    os.replace(tmp, out)
    size = out.stat().st_size
    progress(f"Pronto: {out} · {size / 1e9:.2f} GB · {time.time() - t0:.0f} s (jogos com estatísticas desde {cut})")
    return {"arquivo": str(out), "bytes": size, "corte": cut}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera a base núcleo (sem lances, últimos N anos) para publicar o app.")
    ap.add_argument("--anos", type=int, default=3)
    ap.add_argument("--tamanho", action="store_true", help="só estima, não grava")
    ap.add_argument("--origem", default=None, help="banco de origem (padrão: o do app)")
    a = ap.parse_args(argv)
    from src.data_hub.db import DEFAULT_DB

    src = Path(a.origem or os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or DEFAULT_DB)
    if not src.exists():
        print(f"Não achei o banco {src}.")
        return 1
    if a.tamanho:
        e = estimate(src, a.anos)
        print(f"Partidas no catálogo: {e['partidas']:,} · com detalhes desde {e['corte']}: {e['partidas_recentes']:,}".replace(",", "."))
        for t, n in e["linhas"].items():
            print(f"  {t}: {n:,} linhas".replace(",", "."))
        return 0
    build(src, OUT, a.anos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
