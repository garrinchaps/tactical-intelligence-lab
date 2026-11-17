"""Compara a busca de atletas ativos do Scout; SQLite somente leitura."""

from __future__ import annotations

import argparse
import math
import sqlite3
import statistics
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote


LEGACY_QUERY = """
    SELECT p.player_name, p.match_id, SUM(COALESCE(p.minutes, 0)) AS minutes
    FROM matches AS m
    CROSS JOIN match_player_stats AS p INDEXED BY idx_pstats_match
    WHERE p.match_id = m.match_id
      AND m.match_date >= ?
      AND COALESCE(p.minutes, 0) > 0
      AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
    GROUP BY p.player_name, p.match_id
"""

COVERING_QUERY = """
    SELECT p.player_name, p.match_id, SUM(p.minutes) AS minutes
    FROM matches AS m
    CROSS JOIN match_player_stats AS p INDEXED BY idx_pstats_match_player_minutes
    WHERE p.match_id = m.match_id
      AND m.match_date >= ?
      AND p.minutes > 0
      AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')
    GROUP BY p.player_name, p.match_id
"""


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = max(0, math.ceil((percent / 100.0) * len(ordered)) - 1)
    return ordered[position]


def measure(conn: sqlite3.Connection, query: str, since: str) -> tuple[list[tuple], float]:
    started = time.perf_counter()
    rows = conn.execute(query, (since,)).fetchall()
    return rows, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark read-only da consulta de descoberta de jogadores ativos do Scout."
    )
    parser.add_argument(
        "--database", default="database/tactical_lab.db",
        help="Caminho do SQLite (padrão: database/tactical_lab.db).",
    )
    parser.add_argument("--days", type=int, default=180, help="Janela recente em dias (padrão: 180).")
    parser.add_argument("--repeat", type=int, default=3, help="Repetições por consulta (padrão: 3).")
    args = parser.parse_args()

    if args.days < 1 or args.repeat < 1 or args.repeat > 20:
        parser.error("--days deve ser positivo e --repeat deve ficar entre 1 e 20.")

    database = Path(args.database).expanduser().resolve()
    if not database.is_file():
        parser.error(f"Banco não encontrado: {database}")

    # mode=ro impede gravações no banco; query_only adiciona uma segunda proteção.
    uri = f"file:{quote(database.as_posix(), safe='/:')}?mode=ro"
    since = (date.today() - timedelta(days=args.days)).isoformat()
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=30)
    except sqlite3.Error as exc:
        parser.error(f"Não foi possível abrir o SQLite em modo somente leitura: {exc}")

    try:
        conn.execute("PRAGMA query_only = ON")
        print("=== BENCHMARK DE ÍNDICE DO SCOUT (SOMENTE LEITURA) ===", flush=True)
        print(f"Banco: {database}", flush=True)
        print(f"Tamanho: {database.stat().st_size / (1024 ** 3):.2f} GiB", flush=True)
        print(f"Janela: últimos {args.days} dias (desde {since})", flush=True)
        print(f"Repetições: {args.repeat}", flush=True)

        print("\nPlano da consulta anterior:", flush=True)
        for row in conn.execute("EXPLAIN QUERY PLAN " + LEGACY_QUERY, (since,)):
            print(f"  {row[3]}", flush=True)

        print("\nPlano da consulta com índice de cobertura:", flush=True)
        for row in conn.execute("EXPLAIN QUERY PLAN " + COVERING_QUERY, (since,)):
            print(f"  {row[3]}", flush=True)

        timings = {"anterior": [], "cobertura": []}
        expected_rows = None
        for run in range(args.repeat):
            sequence = (
                [("anterior", LEGACY_QUERY), ("cobertura", COVERING_QUERY)]
                if run % 2 == 0
                else [("cobertura", COVERING_QUERY), ("anterior", LEGACY_QUERY)]
            )
            results = {}
            for label, query in sequence:
                rows, elapsed = measure(conn, query, since)
                results[label] = rows
                timings[label].append(elapsed)
                print(f"Execução {run + 1}/{args.repeat} — {label}: {elapsed:.3f}s ({len(rows):,} grupos)",
                      flush=True)

            legacy = sorted(results["anterior"])
            covering = sorted(results["cobertura"])
            if legacy != covering:
                raise RuntimeError(
                    "As consultas retornaram resultados diferentes. "
                    "O benchmark foi interrompido; não use a otimização até investigar a divergência."
                )
            if expected_rows is not None and legacy != expected_rows:
                raise RuntimeError("O conjunto de resultados variou durante o benchmark.")
            expected_rows = legacy

        old_p50 = statistics.median(timings["anterior"])
        new_p50 = statistics.median(timings["cobertura"])
        print("\n=== RESULTADO ===", flush=True)
        for label in ("anterior", "cobertura"):
            values = timings[label]
            print(
                f"{label}: p50={statistics.median(values):.3f}s | "
                f"p95={percentile(values, 95):.3f}s",
                flush=True,
            )
        print(f"Resultados idênticos: SIM ({len(expected_rows or []):,} grupos)", flush=True)
        print(
            f"Fator p50: {old_p50 / new_p50:.2f}x"
            if new_p50 > 0 else "Fator p50: não calculável",
            flush=True,
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
