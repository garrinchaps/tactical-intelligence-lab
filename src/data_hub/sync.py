"""
Sincronização automática da base.

Uso (na pasta do projeto, com o venv ativo):
    python -m src.data_hub.sync                 # tudo que estiver habilitado
    python -m src.data_hub.sync --only statsbomb wyscout
    python -m src.data_hub.sync --days 7 --prefetch-events 40

* StatsBomb: novas temporadas e partidas entram sozinhas (detecção por `match_updated`).
* Wyscout: índice das 1.941 partidas (estático).
* API-Football / football-data.org / ESPN: jogos encerrados dos últimos N dias nas
  ligas acompanhadas, respeitando cotas e limites.
* --prefetch-events N: baixa os eventos das N partidas mais recentes que ainda não
  têm eventos locais (alimenta a base de referência de Pontos Fortes e Fracos).

Para rodar todo dia no Windows (Agendador de Tarefas), veja o README.
"""

from __future__ import annotations

import argparse
import traceback
from typing import Callable, Dict, List, Optional

from dotenv import load_dotenv

from src.data_hub.db import DataHubDB, utc_now
from src.data_hub.service import MatchDataService

ALL_SOURCES = ["statsbomb", "wyscout", "fdcouk", "api_football", "football_data", "espn"]


def run_sync(
    sources: Optional[List[str]] = None,
    days_back: int = 3,
    prefetch_events: int = 0,
    service: Optional[MatchDataService] = None,
    progress: Optional[Callable[[str], None]] = None,
    seasons_back: int = 2,
) -> Dict[str, Dict]:
    load_dotenv()
    svc = service or MatchDataService()
    db: DataHubDB = svc.db
    say = progress or (lambda msg: print(msg, flush=True))
    results: Dict[str, Dict] = {}

    jobs = {
        "statsbomb": lambda: svc.statsbomb.sync_catalog(),
        "wyscout": lambda: svc.wyscout.sync_catalog(),
        "api_football": lambda: svc.api_football.sync_recent(days_back=days_back),
        "football_data": lambda: svc.football_data.sync_recent(days_back=max(days_back, 3)),
        "espn": lambda: svc.espn.sync_recent(days_back=days_back),
        "fdcouk": lambda: svc.fdcouk.sync(seasons_back=seasons_back, progress=say),
    }
    enabled = {"api_football": svc.api_football.enabled, "football_data": svc.football_data.enabled,
               "espn": svc.espn.enabled}

    for src in sources or ALL_SOURCES:
        if src not in jobs:
            continue
        if src in enabled and not enabled[src]:
            results[src] = {"status": "DESATIVADA"}
            say(f"• {src}: desativada (sem chave/flag no .env)")
            continue
        started = utc_now()
        say(f"• {src}: sincronizando...")
        try:
            res = jobs[src]()
            db.log_sync(src, started, "OK", res.get("added", 0), res.get("updated", 0), str(res))
            results[src] = {"status": "OK", **res}
            say(f"  ✔ {src}: {res.get('added', 0)} novas, {res.get('updated', 0)} atualizadas")
        except Exception as exc:
            db.log_sync(src, started, "ERRO", 0, 0, f"{exc}\n{traceback.format_exc()[-800:]}")
            results[src] = {"status": "ERRO", "message": str(exc)}
            say(f"  ✖ {src}: {exc}")

    if prefetch_events > 0:
        cat = db.catalog(
            "data_level = 'EVENTS' AND data_source IN ('statsbomb','wyscout') "
            "AND match_id NOT IN (SELECT DISTINCT match_id FROM events)",
            limit=prefetch_events,
        )
        ok = 0
        for mid in cat["match_id"].tolist():
            try:
                svc.load(int(mid))
                ok += 1
            except Exception as exc:
                say(f"  ✖ eventos {mid}: {exc}")
        results["prefetch_events"] = {"status": "OK", "downloaded": ok}
        say(f"• eventos baixados: {ok}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Sincroniza a base do Tactical Intelligence Lab.")
    ap.add_argument("--only", nargs="*", choices=ALL_SOURCES, help="fontes a sincronizar (padrão: todas)")
    ap.add_argument("--days", type=int, default=3, help="dias para trás nas fontes de jogos recentes")
    ap.add_argument("--prefetch-events", type=int, default=0,
                    help="baixa eventos de N partidas ainda sem eventos locais")
    ap.add_argument("--seasons", type=int, default=2,
                    help="football-data.co.uk: quantas temporadas anteriores à atual baixar (ex.: 30 = desde os anos 90)")
    args = ap.parse_args()
    run_sync(args.only, args.days, args.prefetch_events, seasons_back=args.seasons)


if __name__ == "__main__":
    main()
