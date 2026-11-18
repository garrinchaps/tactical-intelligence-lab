"""Cria os índices de velocidade da rodada 13 (uma vez). Rode com o app FECHADO: `python -m src.tools.criar_indices`."""

import time

from src.data_hub.db import DataHubDB


def main() -> None:
    t0 = time.time()
    db = DataHubDB()
    falta = db.missing_speed_indexes()
    if not falta:
        print("Todos os índices de velocidade já existem. Nada a fazer.")
        return
    print(f"Faltam {len(falta)} índice(s). Numa base grande isso pode levar alguns minutos — não feche esta janela.")
    made = db.ensure_speed_indexes(progress=lambda m: print(f"  [{time.time() - t0:5.0f} s] {m}", flush=True))
    print(f"Pronto: {len(made)} índice(s) criado(s) em {time.time() - t0:.0f} s. Pode abrir o app.")


if __name__ == "__main__":
    main()
