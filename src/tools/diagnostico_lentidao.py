"""
Rodada 27f — DIAGNÓSTICO DE LENTIDÃO na base real (o PC do usuário não fica ligado às sessões de desenvolvimento).

    python -m src.tools.diagnostico_lentidao

Mede as operações das telas (abrir o banco, catálogo, busca, jogos do time, Scout), mostra o tamanho do banco e do
arquivo de escrita (WAL), índices que faltam, se outro processo está gravando agora e quanto tempo uma gravação
espera. Só LÊ — nada é apagado ou alterado. Grava o relatório em data/diagnostico_lentidao.txt para colar na conversa.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        from dotenv import load_dotenv

        load_dotenv()                       # só carrega as variáveis no processo; nada é exibido
    except Exception:
        pass
    import logging

    logging.disable(logging.WARNING)
    out: List[str] = []

    def say(msg: str) -> None:
        print(msg, flush=True)
        out.append(msg)

    def timed(label: str, fn, limit: float = 3.0):
        t = time.time()
        try:
            r = fn()
            err = ""
        except Exception as exc:                        # noqa: BLE001
            r, err = None, f" — ERRO {type(exc).__name__}: {str(exc)[:150]}"
        dt = time.time() - t
        flag = "  ⚠️ LENTO" if dt > limit else ""
        say(f"  {label:42s} {dt:7.2f} s{flag}{err}")
        return r

    say("== Diagnóstico de lentidão ==")
    from src.data_hub.db import DEFAULT_DB, DataHubDB

    db_path = Path(os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or str(DEFAULT_DB))
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    wal = db_path.with_name(db_path.name + "-wal")
    mb = lambda p: (p.stat().st_size / 1e6) if p.exists() else 0
    say(f"Banco: {mb(db_path):,.0f} MB · arquivo de escrita (WAL): {mb(wal):,.0f} MB"
        + ("  ⚠️ WAL grande (rode: python -m src.tools.limpeza)" if mb(wal) > 500 else ""))
    lock = ROOT / "data" / "atualizacao_manual.lock"
    if lock.exists():
        say("⚠️ atualizar_tudo.ps1 está marcado como RODANDO (data/atualizacao_manual.lock) — o app fica lento até ele acabar")
    try:
        from src.data_hub.worker import PID_PATH

        say("Processo de fundo: " + ("ligado (pid " + PID_PATH.read_text().strip() + ")" if PID_PATH.exists() else "desligado"))
    except Exception:
        pass
    say("\n-- outro processo gravando agora? --")
    try:
        c = sqlite3.connect(str(db_path), timeout=0.5, isolation_level=None)
        t = time.time()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute("ROLLBACK")
            say(f"  banco livre para gravar ({time.time() - t:.2f} s)")
        except sqlite3.OperationalError:
            say("  ⚠️ OUTRO PROCESSO ESTÁ GRAVANDO AGORA (processo de fundo, atualização ou tarefa agendada)")
        c.close()
    except sqlite3.Error as exc:
        say(f"  não consegui testar: {exc}")
    say("\n-- operações das telas --")
    db = timed("abrir o banco (1ª vez no processo)", lambda: DataHubDB(), 5)
    timed("abrir o banco de novo (deve ser ~0)", lambda: DataHubDB(), .5)
    if db is None:
        return 1
    try:
        missing = db.missing_speed_indexes()
        say("  índices de velocidade: " + ("todos criados" if not missing else
                                           f"⚠️ FALTAM {len(missing)} (rode: python -m src.tools.criar_indices)"))
    except Exception:
        pass
    v = timed("versão do catálogo", db.stable_version, 1)
    timed("catálogo inteiro em memória (1ª vez)", lambda: db.catalog_memo(v), 10)
    timed("catálogo de novo (deve ser ~0)", lambda: db.catalog_memo(v), .5)
    try:
        from src.ui.pages import search_all as SA

        for q in ("cruzeiro", "flamengo", "real madrid"):
            timed(f"busca '{q}'", lambda q=q: SA._search_all(q, v, "EVENTS|BOXSCORE|RESULT", True), 3)
    except Exception as exc:                            # noqa: BLE001
        say(f"  busca: não deu para medir ({exc})")
    try:
        from src.ui.pages import clubs as C

        names = timed("nomes do Cruzeiro entre fontes", lambda: C.same_team_names("Cruzeiro"), 2) or ["Cruzeiro"]
        timed("jogos do Cruzeiro", lambda: C.team_matches(names), 3)
        from src.data_hub.gender import comp_sql

        timed("filtro de gênero/país do Cruzeiro", lambda: comp_sql(names), 2)
    except Exception as exc:                            # noqa: BLE001
        say(f"  time: não deu para medir ({exc})")
    try:
        from src.scout import snapshot as S

        say(f"  fotografia do Scout: {'v19 pronta' if S.SNAP_PATH.exists() else 'v19 AINDA NÃO existe (usa a anterior)'}"
            + (f", {mb(S.SNAP_PATH):,.0f} MB" if S.SNAP_PATH.exists() else ""))
        u = timed("carregar o mercado do Scout", S.cached_universe, 15)
        if u is not None:
            say(f"  mercado: {len(u):,} jogadores")
    except Exception as exc:                            # noqa: BLE001
        say(f"  Scout: não deu para medir ({exc})")
    try:
        from src.ui import perf

        rows = perf.read(2000)
        if rows:
            import pandas as pd

            d = pd.DataFrame(rows)
            col = "s" if "s" in d else d.columns[-1]
            top = d.groupby("nome")[col].agg(["median", "max", "count"]).sort_values("max", ascending=False).head(10)
            say("\n-- telas mais lentas registradas no seu uso (data/perf.jsonl) --")
            for n, r in top.iterrows():
                say(f"  {str(n)[:40]:40s} mediana {r['median']:6.1f} s · pior {r['max']:6.1f} s · {int(r['count'])} vezes")
    except Exception:
        pass
    rep = ROOT / "data" / "diagnostico_lentidao.txt"
    try:
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text("\n".join(out), encoding="utf-8")
        print(f"\nRelatório salvo em {rep} — cole o conteúdo na conversa se ainda estiver lento.")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
