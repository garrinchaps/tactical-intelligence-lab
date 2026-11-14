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
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from dotenv import load_dotenv

from src.data_hub.db import DataHubDB, utc_now
from src.data_hub.service import MatchDataService

ALL_SOURCES = ["statsbomb", "wyscout", "fdcouk", "api_football", "football_data", "espn",
               "transfermarkt", "understat", "api_futebol", "basedosdados", "simonetti", "lake"]
LAKE_SOURCES = ["transfermarkt", "understat", "api_futebol", "basedosdados", "simonetti", "lake"]   # alimentam data/lake
QUICK_SOURCES = ["fdcouk", "api_football", "football_data", "espn"]   # jogos recentes; rodam a cada poucas horas


def run_sync(
    sources: Optional[List[str]] = None,
    days_back: int = 3,
    prefetch_events: int = 0,
    service: Optional[MatchDataService] = None,
    progress: Optional[Callable[[str], None]] = None,
    seasons_back: int = 2,
    prefetch_boxscores: int = 0,
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
        "transfermarkt": lambda: _lake_job("transfermarkt", svc, say, seasons_back),
        "understat": lambda: _lake_job("understat", svc, say, seasons_back),
        "api_futebol": lambda: _lake_job("api_futebol", svc, say, seasons_back),
        "basedosdados": lambda: _lake_job("basedosdados", svc, say, seasons_back),
        "simonetti": lambda: _lake_job("simonetti", svc, say, seasons_back),
        "lake": lambda: _lake_job("lake", svc, say, seasons_back),
    }
    from src.data_hub.sources.api_futebol import ApiFutebolProvider
    from src.data_hub.sources.basedosdados import BaseDosDadosProvider

    enabled = {"api_football": svc.api_football.enabled, "football_data": svc.football_data.enabled,
               "espn": svc.espn.enabled, "api_futebol": ApiFutebolProvider().enabled,
               "basedosdados": BaseDosDadosProvider().enabled}

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
    if prefetch_boxscores > 0:
        results["prefetch_boxscores"] = {"status": "OK", **prefetch_recent_boxscores(svc, days_back, prefetch_boxscores, say)}
    return results


def _lake_job(name: str, svc: MatchDataService, say: Callable[[str], None], seasons_back: int) -> Dict[str, int]:
    """Fontes que alimentam o lake (data/lake) e a camada unificada de IDs."""
    from src.data_lake.lake import Lake

    lake = Lake(sqlite_path=svc.db.db_path)
    if name == "transfermarkt":
        from src.data_hub.sources.transfermarkt_ds import TransfermarktDatasets

        return TransfermarktDatasets().sync(lake, progress=say)
    if name == "understat":
        from src.data_hub.sources.understat import UnderstatProvider

        return UnderstatProvider().sync(lake, seasons_back=min(seasons_back, 10), progress=say)
    if name == "api_futebol":
        from src.data_hub.sources.api_futebol import ApiFutebolProvider

        return ApiFutebolProvider().sync(lake, progress=say)
    if name == "simonetti":
        from src.data_hub.sources.simonetti import SimonettiCollector

        return SimonettiCollector().sync(lake, progress=say)
    if name == "basedosdados":
        from src.data_hub.sources.basedosdados import BaseDosDadosProvider

        return BaseDosDadosProvider().sync(lake, progress=say)
    out: Dict[str, int] = {}
    if svc.api_football.enabled:                     # classificação + próximos jogos (API-Football)
        from src.data_hub.sources.api_football import sync_tables

        try:
            out.update(sync_tables(svc.api_football, lake, progress=say))
        except Exception as exc:
            say(f"  api-football tabelas: {exc}")
    from src.data_lake.build import build_all

    out.update(build_all(svc.db, lake, progress=say))
    return out


def prefetch_recent_boxscores(svc: MatchDataService, days_back: int = 3, limit: int = 40,
                              say: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
    """
    Baixa já o boxscore (estatísticas, escalações, gols e cartões) dos jogos recentes que entraram no catálogo,
    para que abram na hora. ESPN primeiro (sem cota); API-Football limitada a 10 por rodada (cota de 100/dia).
    """
    say = say or (lambda m: None)
    since = (date.today() - timedelta(days=days_back + 1)).isoformat()
    cat = svc.db.catalog(
        "data_source IN ('espn','api_football') AND data_level = 'RESULT' AND match_date >= ? "
        "AND match_id NOT IN (SELECT DISTINCT match_id FROM match_team_stats)", (since,), limit=limit * 2)
    ok = err = api_used = 0
    for r in cat.to_dict("records"):
        if ok >= limit:
            break
        src = r["data_source"]
        if src == "espn" and not svc.espn.enabled or src == "api_football" and (not svc.api_football.enabled or api_used >= 10):
            continue
        try:
            (svc.espn.ingest_event if src == "espn" else svc.api_football.ingest_fixture)(int(r["match_id"]))
            ok += 1
            api_used += src == "api_football"
        except Exception as exc:
            err += 1
            say(f"  ✖ boxscore {r['home_team_name']} x {r['away_team_name']}: {exc}")
    say(f"• boxscores baixados: {ok}")
    return {"downloaded": ok, "errors": err}


def main() -> None:
    ap = argparse.ArgumentParser(description="Sincroniza a base do Tactical Intelligence Lab.")
    ap.add_argument("--only", nargs="*", choices=ALL_SOURCES, help="fontes a sincronizar (padrão: todas)")
    ap.add_argument("--days", type=int, default=3, help="dias para trás nas fontes de jogos recentes")
    ap.add_argument("--prefetch-events", type=int, default=0,
                    help="baixa eventos de N partidas ainda sem eventos locais")
    ap.add_argument("--seasons", type=int, default=2,
                    help="football-data.co.uk: quantas temporadas anteriores à atual baixar (ex.: 30 = desde os anos 90)")
    ap.add_argument("--prefetch-boxscores", type=int, default=20,
                    help="baixa o boxscore de até N jogos recentes recém-catalogados (ESPN / API-Football)")
    ap.add_argument("--rapido", action="store_true",
                    help="só jogos recentes: football-data.co.uk (temporada atual), API-Football, football-data.org e ESPN")
    args = ap.parse_args()
    if args.rapido:
        run_sync(args.only or QUICK_SOURCES, args.days, 0, seasons_back=0, prefetch_boxscores=args.prefetch_boxscores)
    else:
        run_sync(args.only, args.days, args.prefetch_events, seasons_back=args.seasons,
                 prefetch_boxscores=args.prefetch_boxscores)


if __name__ == "__main__":
    main()
