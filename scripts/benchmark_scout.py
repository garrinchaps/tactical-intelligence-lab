"""Benchmark local do carregamento do Scout; somente leitura, sem alterar o banco."""

from __future__ import annotations

import time

import pandas as pd

from src.data_hub.db import DataHubDB
from src.scout import engine as E
from src.squad import data as D


def medir(nome, func):
    inicio = time.perf_counter()
    resultado = func()
    print(f"{nome}: {time.perf_counter() - inicio:.2f}s", flush=True)
    return resultado


def main():
    total_inicio = time.perf_counter()
    print("=== BENCHMARK DO SCOUT ===", flush=True)

    db = medir("Inicialização do banco", DataHubDB)
    players = medir("Catálogo de jogadores", lambda: D.table("tm_jogadores"))
    medir("Catálogo de clubes", lambda: D.table("tm_clubes"))

    last = (
        pd.to_numeric(players["ultima_temporada"], errors="coerce")
        if "ultima_temporada" in players
        else pd.Series(dtype=float)
    )

    # O universo de mercado continua preservando jogadores com clube_id e temporadas antigas.
    # Para o histórico pesado, usamos só as três temporadas mais recentes; jogadores ativos
    # fora desse recorte continuam sendo descobertos pelo banco local (180 dias).
    history_players = players
    if not players.empty and last.notna().any():
        history_players = players.loc[last >= last.max() - 2].copy()
        players = players[
            (last >= last.max() - 2)
            | players.get("clube_id", pd.Series("", index=players.index))
            .astype(str)
            .str.strip()
            .ne("")
        ]

    print(f"Jogadores no universo de mercado: {len(players):,}", flush=True)
    print(f"Jogadores candidatos ao histórico: {len(history_players):,}", flush=True)

    history = medir(
        "Histórico otimizado (5 anos)",
        lambda: E.load_player_history(
            db,
            days=1825,
            player_names=history_players.get("nome", pd.Series(dtype=str)),
            progress=lambda message: print(f"  [histórico] {message}", flush=True),
        ),
    )
    print(f"Jogadores com histórico agregado: {len(history):,}", flush=True)

    valuations = medir(
        "Histórico de valores",
        lambda: D.table(
            "tm_valores",
            ["transfermarkt_id", "data", "valor_mercado_eur"],
        ),
    )

    universe = medir(
        "Construção do universo",
        lambda: E.build_market_universe(players, history, valuations),
    )

    scored = medir("Cálculo de qualidade", lambda: E.add_quality_scores(universe))
    external = medir("Leitura de notas externas", D.external_ratings)
    scored = medir(
        "Integração de notas externas",
        lambda: E.merge_external_ratings(scored, external),
    )

    print("\n=== RESULTADO FINAL ===", flush=True)
    print(f"Jogadores no catálogo: {len(players):,}", flush=True)
    print(f"Candidatos ao histórico: {len(history_players):,}", flush=True)
    print(f"Históricos agregados: {len(history):,}", flush=True)
    print(f"Jogadores disponíveis no Scout: {len(scored):,}", flush=True)
    print(f"Tempo total: {time.perf_counter() - total_inicio:.2f}s", flush=True)


if __name__ == "__main__":
    main()
