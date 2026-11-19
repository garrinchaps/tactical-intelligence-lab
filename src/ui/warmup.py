"""
Rodada 19 — pré-aquecimento: deixa pronto, em segundo plano, o que vai ser aberto.

Ao ligar o app (uma vez por processo), uma thread calcula com os MESMOS parâmetros das telas:
  1. a base e o catálogo de partidas;
  2. o mercado do Scout e as avaliações dos Rankings;
  3. os jogos abertos recentemente (montagem + lances processados);
  4. os times abertos recentemente (elenco, próximo jogo, perfil, estilo e formações).

O cache do Streamlit é do PROCESSO (compartilhado por todas as sessões): o primeiro visitante já encontra tudo pronto.
O que foi aberto fica registrado em data/recent_views.json (só ids de jogo e nomes de time — nada pessoal).
A tela mostra o andamento (`state()`) na tela de carregamento.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

RECENT_PATH = Path("data/recent_views.json")
STATUS_PATH = Path("data/warmup_status.json")
MAX_MATCHES, MAX_TEAMS = 8, 6
DEFAULT_MATCH_ID = 3869685

_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {"started": False, "running": False, "done": False, "steps": [], "current": "",
                          "t0": None, "t1": None}


# ------------------------------------------------------------------ registro do que foi aberto
def _read_recent() -> Dict[str, List]:
    try:
        d = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
        return {"jogos": [int(x) for x in d.get("jogos", [])][:MAX_MATCHES],
                "times": [str(x) for x in d.get("times", [])][:MAX_TEAMS]}
    except Exception:
        return {"jogos": [], "times": []}


def remember(kind: str, value: Any) -> None:
    """kind 'jogo' (match_id) ou 'time' (nome). Mais recente primeiro; barato (arquivo pequeno)."""
    if value in (None, "", 0):
        return
    key = "jogos" if kind == "jogo" else "times"
    try:
        v = int(value) if key == "jogos" else str(value).strip()
    except (TypeError, ValueError):
        return
    with _LOCK:
        d = _read_recent()
        lst = [v] + [x for x in d[key] if x != v]
        d[key] = lst[: MAX_MATCHES if key == "jogos" else MAX_TEAMS]
        try:
            RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
            RECENT_PATH.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


# ------------------------------------------------------------------ passos
def _plan() -> List[Tuple[str, Callable[[], Any]]]:
    recent = _read_recent()
    matches = list(dict.fromkeys(recent["jogos"] + [DEFAULT_MATCH_ID]))[:MAX_MATCHES]
    teams = recent["times"]
    steps: List[Tuple[str, Callable[[], Any]]] = []

    def base():
        from src.ui.context import ANALYZABLE_SQL, REAL_SQL, _catalog_cached, get_service

        svc = get_service()
        v = svc.db.stable_version()
        lv = ("EVENTS", "BOXSCORE")                       # padrão da barra do topo
        cond = "data_level IN (" + ",".join(f"'{x}'" for x in lv) + ",'SIMULATED','UPLOAD')"
        _catalog_cached(v, f"({cond}) AND {REAL_SQL}", ())
        _catalog_cached(v, f"({ANALYZABLE_SQL}) AND {REAL_SQL}", ())

    steps.append(("Abrindo a base e o catálogo de partidas", base))

    def market():
        from src.scout import snapshot as S
        from src.ui.pages import scout

        scout._market_data(S.version())

    steps.append(("Mercado do Scout", market))

    def rankings():
        from datetime import date

        from src.ui.pages import rankings as R

        R._data(str(date.today()), R._stamp())

    steps.append(("Avaliações dos Rankings", rankings))

    def players():
        from src.ui.context import get_service
        from src.ui.pages.players_search import player_index

        player_index(get_service().db.stable_version())

    steps.append(("Índice de jogadores", players))
    for mid in matches:
        def one_match(mid=mid):
            from src.ui.context import _bundle_parts, processed_events

            parts = _bundle_parts(int(mid))
            ev = parts.get("events")
            if ev is not None and len(ev):
                processed_events(int(mid), ev)

        steps.append((f"Jogo {mid}", one_match))
    for team in teams:
        def one_team(team=team):
            from src.ui.context import get_service
            from src.ui.pages import clubs, squad

            v = squad._tv(team)
            squad._squad(team, v)
            squad._matchday(team, v, 10)
            squad._profile(team, 5, v)
            names = clubs.same_team_names(team)
            tv = get_service().db.team_version(names)
            clubs._style_data(tuple(names), tv)
            clubs._formation_data(tuple(names), tv)

        steps.append((f"Time: {team}", one_team))
    return steps


def _run() -> None:
    quiet = [logging.getLogger(n) for n in ("streamlit.runtime.scriptrunner_utils.script_run_context",
                                             "streamlit.runtime.caching.cache_data_api", "streamlit")]
    old = [lg.level for lg in quiet]
    for lg in quiet:
        lg.setLevel(logging.ERROR)                       # chamadas fora da tela geram avisos inofensivos
    try:
        plan = _plan()
        _STATE["steps"] = [{"nome": n, "status": "fila", "s": None} for n, _ in plan]
        for i, (name, fn) in enumerate(plan):
            _STATE["current"] = name
            _STATE["steps"][i]["status"] = "rodando"
            t = time.perf_counter()
            try:
                fn()
                _STATE["steps"][i]["status"] = "ok"
            except Exception as exc:                     # um passo que falha não impede os outros
                _STATE["steps"][i]["status"] = f"pulado ({type(exc).__name__})"
                _STATE.setdefault("errors", {})[name] = f"{type(exc).__name__}: {str(exc)[:300]}"
            _STATE["steps"][i]["s"] = round(time.perf_counter() - t, 1)
    finally:
        for lg, lv in zip(quiet, old):
            lg.setLevel(lv)
        _STATE["running"], _STATE["done"], _STATE["current"], _STATE["t1"] = False, True, "", time.time()
        try:
            STATUS_PATH.write_text(json.dumps({"passos": _STATE["steps"], "erros": _STATE.get("errors", {}),
                                               "terminou": time.strftime("%Y-%m-%d %H:%M:%S")},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def start() -> Dict[str, Any]:
    """Liga o pré-aquecimento uma vez por processo. Seguro chamar a cada recarga."""
    with _LOCK:
        if not _STATE["started"]:
            _STATE.update(started=True, running=True, done=False, t0=time.time())
            threading.Thread(target=_run, name="til-warmup", daemon=True).start()
    return _STATE


def state() -> Dict[str, Any]:
    return _STATE
