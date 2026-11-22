"""
Rodada 26 — LIMPEZA segura (app FECHADO). Não apaga nenhum dado do banco: só caches, cópias velhas e lixo.

    python -m src.tools.limpeza              # limpa (mostra o que fez e quanto liberou)
    python -m src.tools.limpeza --simular    # só mostra o que seria apagado
    python -m src.tools.limpeza --vacuum     # + compacta o banco (pode levar 10–40 min; precisa de espaço livre)

O que limpa:
  * projeto: __pycache__, .pytest_cache, fotografias antigas do Scout (fica só a atual), cópias antigas do catálogo
    (fica a mais nova), arquivos .tmp, caches do Streamlit sem uso há 14+ dias, backups além dos 2 mais novos;
  * registros (logs) grandes: ficam só os últimos 5 MB de cada;
  * banco: devolve o arquivo de escrita (WAL) ao banco, otimiza o planejador de consultas, apaga marcas de "tentativa
    sem dado" com mais de 30 dias (só controle de nova tentativa — nenhum jogo, estatística ou jogador é apagado);
    com --vacuum, reorganiza o arquivo (mesmos dados, arquivo menor e leituras mais rápidas);
  * computador: arquivos temporários do SEU usuário com 3+ dias (%TEMP%) e o cache do pip. Nada do sistema, nada que
    exija administrador, nenhum documento seu.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[2]
MB = 1024 * 1024


def _size(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def _rm(p: Path, simulate: bool, log: List[Tuple[str, int]], why: str) -> None:
    n = _size(p)
    if not simulate:
        try:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
        except OSError:
            return
    log.append((f"{why}: {p}", n))


def project(simulate: bool, log) -> None:
    skip = {"venv", ".venv", ".git", "node_modules", "data", "backups"}
    for base, dirs, _files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in skip]
        if "__pycache__" in dirs:
            _rm(Path(base) / "__pycache__", simulate, log, "cache do Python")
            dirs.remove("__pycache__")
    for d in (ROOT / ".pytest_cache",):
        if d.exists():
            _rm(d, simulate, log, "cache dos testes")
    proc = ROOT / "data" / "processed"
    try:
        from src.scout.snapshot import SNAP_PATH
        current = (ROOT / SNAP_PATH).resolve()
    except Exception:
        current = None
    for f in proc.glob("scout_universe_v*.pkl"):
        if current is None or f.resolve() != current:
            _rm(f, simulate, log, "fotografia antiga do Scout")
    cats = sorted(proc.glob("catalogo_*.parquet"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in cats[1:]:
        _rm(f, simulate, log, "cópia antiga do catálogo")
    for f in list(proc.glob("*.tmp")) + list((ROOT / "data").glob("*.tmp")):
        _rm(f, simulate, log, "arquivo temporário")
    old = time.time() - 14 * 86400
    for cache_dir in (ROOT / ".streamlit" / "cache", Path.home() / ".streamlit" / "cache"):
        if cache_dir.exists():
            for f in cache_dir.rglob("*"):
                try:
                    if f.is_file() and f.stat().st_atime < old and f.stat().st_mtime < old:
                        _rm(f, simulate, log, "cache de tela sem uso há 14+ dias")
                except OSError:
                    pass
    backups = sorted((ROOT / "backups").glob("*"), key=lambda f: f.stat().st_mtime, reverse=True) \
        if (ROOT / "backups").exists() else []
    for f in backups[2:]:
        _rm(f, simulate, log, "backup antigo (ficam os 2 mais novos)")


def logs(simulate: bool, log, keep_mb: int = 5) -> None:
    for name in ("sync_log.txt", "worker.log", "perf.jsonl", "assistente_latencia.jsonl", "assistente_sem_alvo.jsonl"):
        f = ROOT / "data" / name
        try:
            n = f.stat().st_size
        except OSError:
            continue
        if n <= keep_mb * MB:
            continue
        if not simulate:
            with f.open("rb") as fh:
                fh.seek(-keep_mb * MB, os.SEEK_END)
                tail = fh.read()
            nl = tail.find(b"\n")
            f.write_bytes(tail[nl + 1:] if nl >= 0 else tail)
        log.append((f"registro enxugado (ficam os últimos {keep_mb} MB): {f}", n - keep_mb * MB))


def database(simulate: bool, vacuum: bool, log) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()                   # só lê as variáveis no processo; nada é exibido
    except Exception:
        pass
    try:
        from src.data_hub.db import DEFAULT_DB
    except Exception:
        DEFAULT_DB = Path("database/tactical_lab.db")
    db = Path(os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or str(DEFAULT_DB))
    if not db.is_absolute():
        db = ROOT / db
    if not db.exists():
        return
    wal = db.with_name(db.name + "-wal")
    before = _size(db) + _size(wal)
    if simulate:
        log.append((f"banco: devolver o WAL ({_size(wal) // MB} MB) e otimizar" + (" + compactar" if vacuum else ""), 0))
        return
    try:
        c = sqlite3.connect(str(db), timeout=60)
        c.execute("PRAGMA busy_timeout = 60000")
        try:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='fotmob_tried'").fetchone():
                c.execute("DELETE FROM fotmob_tried WHERE tried_at < datetime('now', '-30 days')")
                c.commit()
        except sqlite3.Error:
            pass
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.execute("PRAGMA optimize")
        if vacuum:
            free = shutil.disk_usage(str(db.parent)).free
            if free < _size(db) * 1.1:
                print(f"  sem espaço para compactar (precisa de ~{_size(db) // MB} MB livres, há {free // MB} MB)")
            else:
                print("  compactando o banco (VACUUM) — pode levar de 10 a 40 minutos, não feche a janela…", flush=True)
                c.execute("VACUUM")
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
    except sqlite3.Error as exc:
        print(f"  banco ocupado ou indisponível ({exc}); feche o app e rode de novo")
        return
    after = _size(db) + _size(wal)
    log.append((f"banco otimizado ({db.name})" + (" e compactado" if vacuum else ""), max(0, before - after)))


def computer(simulate: bool, log, days: int = 3) -> None:
    tmp = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "")
    if tmp and tmp.exists() and tmp != Path("/tmp") and "Temp" in str(tmp):
        cut = time.time() - days * 86400
        freed, count = 0, 0
        for f in tmp.rglob("*"):
            try:
                if f.is_file() and f.stat().st_mtime < cut:
                    n = f.stat().st_size
                    if not simulate:
                        f.unlink()
                    freed += n
                    count += 1
            except OSError:
                continue                 # arquivo em uso por outro programa: fica
        log.append((f"temporários do Windows com {days}+ dias ({count} arquivos) em {tmp}", freed))
    try:
        if not simulate:
            subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], capture_output=True, timeout=120)
        log.append(("cache de downloads do pip", 0))
    except Exception:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--vacuum", action="store_true")
    ap.add_argument("--sem-computador", action="store_true", help="não mexe nos temporários do Windows")
    a = ap.parse_args(argv)
    os.chdir(ROOT)
    log: List[Tuple[str, int]] = []
    project(a.simular, log)
    logs(a.simular, log)
    database(a.simular, a.vacuum, log)
    if not a.sem_computador:
        computer(a.simular, log)
    total = sum(n for _, n in log)
    groups: dict = {}
    for what, n in log:
        k = what.split(":")[0]
        groups.setdefault(k, [0, 0])
        groups[k][0] += 1
        groups[k][1] += n
    print(("SIMULAÇÃO — nada foi apagado." if a.simular else "Limpeza feita.") + " Resumo:")
    for k, (cnt, n) in sorted(groups.items(), key=lambda kv: -kv[1][1]):
        print(f"  • {k}: {cnt} item(ns), {n / MB:,.1f} MB".replace(",", "."))
    print(f"Total {'que seria liberado' if a.simular else 'liberado'}: {total / MB:,.1f} MB".replace(",", "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
