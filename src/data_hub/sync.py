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
import os
import traceback
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional

from dotenv import load_dotenv

from src.data_hub.db import DataHubDB, utc_now
from src.data_hub.http import QuotaExceeded
from src.data_hub.net import log as net_log, redact
from src.data_hub.service import MatchDataService

ALL_SOURCES = ["statsbomb", "wyscout", "fdcouk", "openfootball", "brasileirao", "open_matchday", "api_football",
               "football_data", "espn", "transfermarkt", "understat", "api_futebol", "basedosdados", "simonetti",
               "open_sources", "lake"]
# cargas pesadas, só quando pedidas com --only (não entram na sincronização padrão nem na automática)
HEAVY_SOURCES = ["espn_historico", "openplay", "cbf", "estatisticas_brasil", "espn_temporada", "espn_resumos",
                 "espn_elencos", "fotmob_temporada", "fotmob_jogos", "fotmob_recentes", "fotmob_tudo"]
# --tudo: a base completa, em ordem (catálogos → estatísticas → eventos → histórico ESPN → APIs com chave →
# bases do lake → ligação entre fontes). Fontes sem chave/flag no .env são puladas e avisadas.
EVERYTHING = ["statsbomb", "wyscout", "fdcouk", "openfootball", "open_sources", "brasileirao", "open_matchday",
              "openplay", "cbf", "espn", "espn_historico", "api_football", "estatisticas_brasil", "football_data", "api_futebol",
              "basedosdados", "transfermarkt", "understat", "simonetti", "lake"]   # openplay/cbf: precisam dos arquivos baixados na sua máquina
LAKE_SOURCES = ["transfermarkt", "understat", "api_futebol", "basedosdados", "simonetti", "lake"]   # alimentam data/lake
QUICK_SOURCES = ["fdcouk", "api_football", "football_data", "espn"]   # jogos recentes; rodam a cada poucas horas


def _with_lock_retry(job, src: str, say, waits=(20, 40)):
    """Rodada 19: "database is locked" = outro processo gravando ao mesmo tempo (processo de fundo × sincronização
    do painel). Espera e tenta de novo, em vez de registrar erro na primeira colisão."""
    import sqlite3
    import time as _t

    for i, wait in enumerate(list(waits) + [None]):
        try:
            return job()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or wait is None:
                raise
            say(f"  … {src}: banco ocupado por outra gravação; nova tentativa em {wait} s")
            _t.sleep(wait)


def run_sync(
    sources: Optional[List[str]] = None,
    days_back: int = 3,
    prefetch_events: int = 0,
    service: Optional[MatchDataService] = None,
    progress: Optional[Callable[[str], None]] = None,
    seasons_back: int = 2,
    prefetch_boxscores: int = 0,
    espn_leagues: Optional[List[str]] = None,
    since_year: int = 2018,
    summaries_limit: int = 1500,
    fotmob_seasons: int = 0,
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
        "espn_historico": lambda: svc.espn.backfill(espn_leagues, since_year=since_year, progress=say),
        # v36: temporada 2025/2026 de todas as ligas acompanhadas (resultados + próximos jogos), ~1 pedido por liga/ano
        "espn_temporada": lambda: svc.espn.sync_season(espn_leagues, progress=say),
        # estatísticas + escalações dos jogos (Brasil e Europa principal primeiro); continua de onde parou
        "espn_resumos": lambda: svc.espn.fetch_summaries(espn_leagues, limit=summaries_limit, progress=say),
        # elencos atuais com lesões (referência de transferências e desfalques)
        "espn_elencos": lambda: svc.espn.sync_rosters(espn_leagues, progress=say),
        # rodada 5: FotMob — resultados + calendário de ~100 competições (Série A–D, estaduais, 2ª divisões, feminino…)
        # e, por jogo, estatísticas com xG, escalação com posição exata, números por jogador e mapa de chutes
        "fotmob_temporada": lambda: svc.fotmob.sync_seasons(_fotmob_ids(espn_leagues), seasons_back=fotmob_seasons,
                                                            progress=say),
        # TUDO de uma vez: 5 temporadas de todas as competições + detalhes de todos os jogos, em lotes, até acabar
        "fotmob_tudo": lambda: _fotmob_all(svc, say),
        # automático (diário): só os jogos dos últimos 10 dias, no máximo 150 por vez
        "fotmob_recentes": lambda: svc.fotmob.fetch_details(None, limit=150,
                                                            since=(date.today() - timedelta(days=10)).isoformat(),
                                                            progress=say),
        "fotmob_jogos": lambda: svc.fotmob.fetch_details(_fotmob_ids(espn_leagues), limit=summaries_limit,
                                                         since=f"{date.today().year - max(fotmob_seasons, 1)}-01-01",
                                                         progress=say),
        # Brasileirão (A, B, Copa do Brasil) com xG, passes, posse e números por jogador: API-Football, lotes de 20
        # jogos por requisição, dentro da cota do dia (continua de onde parou na próxima vez)
        "estatisticas_brasil": lambda: svc.api_football.backfill_stats(
            since_year=since_year, max_requests=max(0, min(90, svc.api_football.client.quota_left() or 0) - 15),   # 15 ficam livres para o app
            progress=say),
        "brasileirao": lambda: _community("brasileirao", svc, say),
        "open_matchday": lambda: _community("open_matchday", svc, say),
        "cbf": lambda: _community("cbf", svc, say),
        "openplay": lambda: _community("openplay", svc, say),
        "fdcouk": lambda: svc.fdcouk.sync(seasons_back=seasons_back, progress=say),
        "transfermarkt": lambda: _lake_job("transfermarkt", svc, say, seasons_back),
        "understat": lambda: _lake_job("understat", svc, say, seasons_back),
        "api_futebol": lambda: _lake_job("api_futebol", svc, say, seasons_back),
        "basedosdados": lambda: _lake_job("basedosdados", svc, say, seasons_back),
        "openfootball": lambda: svc.openfootball.sync(progress=say),
        "open_sources": lambda: _lake_job("open_sources", svc, say, seasons_back),
        "simonetti": lambda: _lake_job("simonetti", svc, say, seasons_back),
        "lake": lambda: _lake_job("lake", svc, say, seasons_back),
    }
    from src.data_hub.sources.api_futebol import ApiFutebolProvider
    from src.data_hub.sources.basedosdados import BaseDosDadosProvider

    enabled = {"api_football": svc.api_football.enabled, "football_data": svc.football_data.enabled,
               "espn": svc.espn.enabled, "espn_historico": svc.espn.enabled, "espn_temporada": svc.espn.enabled,
               "espn_resumos": svc.espn.enabled, "espn_elencos": svc.espn.enabled,
               "fotmob_temporada": svc.fotmob.enabled, "fotmob_jogos": svc.fotmob.enabled,
               "fotmob_recentes": svc.fotmob.enabled, "fotmob_tudo": svc.fotmob.enabled,
               "estatisticas_brasil": svc.api_football.enabled, "api_futebol": ApiFutebolProvider().enabled,
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
            res = _with_lock_retry(jobs[src], src, say)
            status = "COTA" if res.get("cota_atingida") else "OK"
            db.log_sync(src, started, status, res.get("added", 0), res.get("updated", 0), redact(str(res)))
            results[src] = {"status": status, **res}
            say(f"  ✔ {src}: {res.get('added', 0)} novas, {res.get('updated', 0)} atualizadas"
                + (" · cota diária atingida, parou com segurança" if status == "COTA" else ""))
        except QuotaExceeded as exc:
            db.log_sync(src, started, "COTA", 0, 0, redact(exc))
            results[src] = {"status": "COTA", "message": redact(exc)}
            say(f"  ⏸ {src}: {redact(exc)}")
        except Exception as exc:
            db.log_sync(src, started, "ERRO", 0, 0, redact(f"{exc}\n{traceback.format_exc()[-800:]}"))
            results[src] = {"status": "ERRO", "message": redact(exc)}
            say(f"  ✖ {src}: {redact(exc)}")
        net_log(src, f"{results[src].get('status')}: {redact(results[src])[:300]}")

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
    try:                                                 # nível honesto: BOXSCORE só com estatísticas
        n = db.reconcile_levels()
        if n:
            say(f"• {n} partida(s) sem estatísticas reclassificadas como SÓ PLACAR")
    except Exception as exc:  # pragma: no cover
        say(f"  ✖ reclassificação: {exc}")
    try:                                                 # a cobertura acompanha cada sincronização
        from src.data_hub.coverage import write_report

        say(f"• cobertura atualizada em {write_report(str(db.db_path))}")
    except Exception as exc:  # pragma: no cover - relatório nunca derruba a sincronização
        say(f"  ✖ cobertura: {exc}")
    return results


def _community(name: str, svc: MatchDataService, say: Callable[[str], None]) -> Dict[str, int]:
    """Bases montadas pela comunidade (Brasileirão, open-matchday, súmulas da CBF, OpenPlay)."""
    if name == "brasileirao":
        from src.data_hub.sources.brasileirao_dataset import BrasileiraoDatasetProvider

        return BrasileiraoDatasetProvider(svc.db).sync(progress=say)
    if name == "open_matchday":
        from src.data_hub.sources.open_matchday import OpenMatchdayProvider
        from src.data_lake.lake import Lake

        return OpenMatchdayProvider(svc.db).sync(Lake(sqlite_path=svc.db.db_path), progress=say)
    if name == "cbf":
        from src.data_hub.sources.cbf_sumulas import CbfSumulasProvider

        return CbfSumulasProvider(svc.db).sync(progress=say)
    from src.data_hub.sources.openplay import OpenPlayProvider

    return OpenPlayProvider(svc.db).sync(progress=say)


def _lake_job(name: str, svc: MatchDataService, say: Callable[[str], None], seasons_back: int) -> Dict[str, int]:
    """Fontes que alimentam o lake (data/lake) e a camada unificada de IDs."""
    from src.data_lake.lake import Lake

    lake = Lake(sqlite_path=svc.db.db_path)
    if name == "transfermarkt":
        from src.data_hub.sources.transfermarkt_ds import TransfermarktDatasets

        return TransfermarktDatasets().sync(lake, progress=say)
    if name == "understat":
        from src.data_hub.sources.understat import UnderstatProvider

        from src.data_hub.sources.understat import FIRST_SEASON, season_start

        res = UnderstatProvider().sync(lake, seasons_back=min(seasons_back, season_start() - FIRST_SEASON), progress=say)
        try:                                     # xG por jogo vira estatística das partidas do catálogo
            from src.data_lake.understat_link import understat_into_catalog

            res.update(understat_into_catalog(svc.db, lake, progress=say))
        except Exception as exc:
            say(f"  understat → catálogo: {exc}")
        return res
    if name == "api_futebol":
        from src.data_hub.sources.api_futebol import ApiFutebolProvider

        return ApiFutebolProvider(db=svc.db).sync(lake, progress=say)
    if name == "open_sources":
        from src.data_hub.sources.open_sources import OpenSourcesIngestor

        return OpenSourcesIngestor().sync(lake, db=svc.db, progress=say)
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


def _fotmob_all(svc, say) -> Dict[str, int]:
    """Calendário de 5 temporadas + detalhes de todos os jogos, em lotes de 500, até não faltar nada. Ctrl+C para —
    rodando de novo continua de onde parou (o que já veio fica no banco)."""
    tot = {"temporadas": 0, "detalhes": 0, "errors": 0}
    r = svc.fotmob.sync_seasons(None, seasons_back=5, progress=say)
    tot["temporadas"] = r.get("temporadas", 0)
    since = f"{date.today().year - 5}-01-01"
    while True:
        pend = svc.fotmob.pending(since)
        say(f"  faltam ~{pend} jogos com detalhes (≈ {pend * 0.8 / 3600:.1f} h no ritmo atual — estimativa)")
        r = svc.fotmob.fetch_details(None, since=since, limit=500, progress=say)
        tot["detalhes"] += r["detalhes"]
        tot["errors"] += r["errors"]
        if r["detalhes"] == 0:
            break
    return tot


def _fotmob_ids(leagues: Optional[List[str]]) -> Optional[List[int]]:
    """--ligas com números = ids da FotMob (ex.: 268 9464); sem números, todas as acompanhadas."""
    from src.data_hub.sources.fotmob import REGIONS

    ids = [int(x) for x in (leagues or []) if str(x).isdigit()]
    for x in leagues or []:                       # rodada 14: --ligas sulamericanas / brasil
        ids += REGIONS.get(str(x).lower(), [])
    return list(dict.fromkeys(ids)) or None


def main() -> None:
    ap = argparse.ArgumentParser(description="Sincroniza a base do Tactical Intelligence Lab.")
    ap.add_argument("--only", nargs="*", choices=ALL_SOURCES + HEAVY_SOURCES,
                    help="fontes a sincronizar (padrão: todas, menos as cargas pesadas como espn_historico)")
    ap.add_argument("--intervalo", type=float, default=None,
                    help="segundos entre pedidos à FotMob nesta execução (padrão 0,7; mínimo 0,3)")
    ap.add_argument("--ligas", nargs="*", default=None,
                    help="espn_historico: ligas ESPN (padrão: bra.1 bra.2 bra.copa_do_brazil conmebol.libertadores "
                         "conmebol.sudamericana)")
    ap.add_argument("--desde", type=int, default=2018, help="espn_historico: ano inicial (padrão 2018)")
    ap.add_argument("--limite", type=int, default=1500,
                    help="espn_resumos: quantos resumos (estatísticas + escalações) baixar nesta rodada (~1 s cada)")
    ap.add_argument("--temporadas", type=int, default=0,
                    help="fotmob_temporada/fotmob_jogos: temporadas ANTERIORES além da atual (0–5)")
    ap.add_argument("--tudo", action="store_true",
                    help="monta a base completa: todas as fontes, histórico inteiro (fdcouk desde 1993, Understat desde "
                         "2014, ESPN desde --desde), OpenPlay e súmulas da CBF baixados automaticamente")
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
    if getattr(args, "intervalo", None):                 # rodada 16: ritmo da FotMob só nesta execução
        os.environ["FOTMOB_INTERVALO"] = str(max(args.intervalo, 0.3))
    if args.tudo:
        print("Base completa: isto baixa vários GB e pode levar horas. Pode interromper com Ctrl+C e rodar de novo —\n"
              "o que já veio fica em cache e não é baixado outra vez.", flush=True)
        run_sync(args.only or EVERYTHING, max(args.days, 7), args.prefetch_events, seasons_back=max(args.seasons, 33),
                 prefetch_boxscores=max(args.prefetch_boxscores, 50), espn_leagues=args.ligas, since_year=args.desde)
        return
    if args.rapido:
        run_sync(args.only or QUICK_SOURCES, args.days, 0, seasons_back=0, prefetch_boxscores=args.prefetch_boxscores)
    else:
        run_sync(args.only, args.days, args.prefetch_events, seasons_back=args.seasons, summaries_limit=args.limite,
                 prefetch_boxscores=args.prefetch_boxscores, espn_leagues=args.ligas, since_year=args.desde,
                 fotmob_seasons=max(0, min(args.temporadas, 5)))


if __name__ == "__main__":
    main()
