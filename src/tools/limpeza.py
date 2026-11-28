"""
Rodada 26 — LIMPEZA segura (app FECHADO). Não apaga nenhum dado do banco: só caches, cópias velhas e lixo.

    python -m src.tools.limpeza              # limpa (mostra o que fez e quanto liberou)
    python -m src.tools.limpeza --simular    # só mostra o que seria apagado
    python -m src.tools.limpeza --vacuum     # + compacta o banco (pode levar 10–40 min; precisa de espaço livre)
    python -m src.tools.limpeza --relatorio  # rodada 27k: só MOSTRA os maiores arquivos/pastas e as tabelas do banco
    python -m src.tools.limpeza --apagar-copias   # apaga cópias REDUNDANTES do banco (pede "SIM"; nunca o principal)
    python -m src.tools.limpeza --respostas-velhas  # apaga respostas da ESPN/FotMob já gravadas no banco há 45+ dias

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
    snaps = sorted(proc.glob("scout_universe_v*.pkl"), key=lambda f: f.stat().st_mtime, reverse=True)
    # a fotografia atual ainda não existe (versão nova do código): fica a mais recente — é dela que o app recalcula as
    # notas em segundos até a nova ficar pronta
    keep = {current} if current is not None and current.exists() else {snaps[0].resolve()} if snaps else set()
    for f in snaps:
        if f.resolve() not in keep:
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
            # rodada 27l: o VACUUM monta uma cópia temporária inteira e depois a regrava pelo WAL — precisa de ~2× o banco
            if free < _size(db) * 2.1:
                print(f"  sem espaço para compactar (precisa de ~{2 * _size(db) // MB} MB livres, há {free // MB} MB)")
            else:
                print("  compactando o banco (VACUUM) — com ~19 GB leva de 30 a 90 minutos e fica sem mostrar nada "
                      "por longos trechos; não feche a janela. Andamento a cada minuto:", flush=True)
                import threading

                done = threading.Event()
                t0 = time.time()

                def _progress():
                    while not done.wait(60):
                        try:
                            livre = shutil.disk_usage(str(db.parent)).free // MB
                        except OSError:
                            livre = -1
                        print(f"    … {int((time.time() - t0) // 60)} min · arquivo de escrita {_size(wal) // MB} MB · "
                              f"espaço livre {livre} MB (mudando = está trabalhando)", flush=True)
                threading.Thread(target=_progress, daemon=True).start()
                try:
                    c.execute("VACUUM")
                    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    done.set()
                print(f"  compactação concluída em {int((time.time() - t0) // 60)} min", flush=True)
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


# rodada 27k — cópias do banco que o processo de publicação deixou no PC. NUNCA inclui o banco principal nem o .gz
# (o .gz é o arquivo que vai para a nuvem). Só apaga se o banco principal abrir e tiver pelo menos os mesmos jogos.
REDUNDANT_COPIES = ("tactical_lab_cloud_snapshot.db", "tactical_lab_deploy.db", "tactical_lab_copy.db",
                    "tactical_lab_backup.db", "nucleo.db")


def _main_db() -> Path:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass
    try:
        from src.data_hub.db import DEFAULT_DB
    except Exception:
        DEFAULT_DB = Path("database/tactical_lab.db")
    db = Path(os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or str(DEFAULT_DB))
    return db if db.is_absolute() else ROOT / db


def _matches(db: Path) -> int:
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        n = int(c.execute("SELECT COUNT(*) FROM matches").fetchone()[0])
        c.close()
        return n
    except sqlite3.Error:
        return -1


def report(top: int = 25) -> None:
    """Só mostra: maiores arquivos e pastas do projeto e o peso de cada tabela do banco (quando o SQLite deixa)."""
    files = []
    for base, dirs, fs in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {".git"}]
        for f in fs:
            p = Path(base) / f
            try:
                files.append((p.stat().st_size, p))
            except OSError:
                pass
    files.sort(reverse=True)
    print(f"== {top} maiores arquivos do projeto ==")
    for n, p in files[:top]:
        print(f"  {n / MB:10,.0f} MB  {p.relative_to(ROOT)}".replace(",", "."))
    print("== pastas (1º nível) ==")
    for d in sorted([x for x in ROOT.iterdir() if x.is_dir()], key=_size, reverse=True)[:12]:
        print(f"  {_size(d) / MB:10,.0f} MB  {d.name}/".replace(",", "."))
    db = _main_db()
    if db.exists():
        try:
            c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            rows = c.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC LIMIT 15").fetchall()
            c.close()
            print("== tabelas/índices mais pesados do banco ==")
            for name, n in rows:
                print(f"  {n / MB:10,.0f} MB  {name}".replace(",", "."))
        except sqlite3.Error:
            print("  (o SQLite deste Python não mede o peso por tabela — tudo bem, é só informação)")
    copies = [p for p in _copy_candidates()]
    if copies:
        print("== cópias redundantes do banco (dá para apagar com --apagar-copias) ==")
        for p in copies:
            print(f"  {_size(p) / MB:10,.0f} MB  {p}".replace(",", "."))


def _copy_candidates() -> List[Path]:
    main = _main_db().resolve()
    out = []
    for folder in (ROOT, ROOT / "database", ROOT / "data", ROOT / "data" / "publicacao", ROOT / "deploy"):
        for name in REDUNDANT_COPIES:
            p = folder / name
            if p.exists() and p.resolve() != main:
                out.append(p)
    return out


def delete_copies(simulate: bool, log, assume_yes: bool = False) -> None:
    main = _main_db()
    if not main.exists():
        print("  banco principal não encontrado — por segurança nenhuma cópia é apagada")
        return
    n_main = _matches(main)
    if n_main <= 0:
        print("  o banco principal não abriu agora (app aberto?) — feche o app e rode de novo; nada foi apagado")
        return
    cands = _copy_candidates()
    if not cands:
        print("  nenhuma cópia redundante encontrada")
        return
    for p in cands:
        n_copy = _matches(p)
        if n_copy > n_main:
            print(f"  MANTIDA (tem mais jogos que o principal: {n_copy} × {n_main}): {p}")
            continue
        if simulate:
            log.append((f"cópia redundante do banco: {p}", _size(p)))
            continue
        if not assume_yes:
            ans = input(f"Apagar {p.name} ({_size(p) // MB} MB)? O banco principal ({n_main} jogos) fica. Digite SIM: ")
            if ans.strip().upper() != "SIM":
                print("  mantida")
                continue
        for extra in (p, p.with_name(p.name + "-wal"), p.with_name(p.name + "-shm")):
            if extra.exists():
                _rm(extra, False, log, "cópia redundante do banco")


# Respostas brutas da ESPN/FotMob guardadas em data/raw/<fonte>/ (cache de download). O que interessa já está no
# banco; com 45+ dias só serviriam para não baixar de novo um jogo antigo. Fontes que SÃO a base (StatsBomb, Wyscout,
# OpenPlay, Transfermarkt, football-data, CBF…) e a API-Football (cota de 100/dia) nunca entram aqui.
STALE_RESPONSE_SOURCES = ("espn", "fotmob")


def stale_responses(simulate: bool, log, days: int = 45) -> None:
    cut = time.time() - days * 86400
    for src in STALE_RESPONSE_SOURCES:
        d = ROOT / "data" / "raw" / src
        if not d.exists():
            continue
        freed, count = 0, 0
        for f in d.glob("*.json"):
            try:
                st_ = f.stat()
                if st_.st_mtime < cut:
                    if not simulate:
                        f.unlink()
                    freed += st_.st_size
                    count += 1
            except OSError:
                pass
        log.append((f"respostas antigas da {src} já gravadas no banco ({count} arquivos)", freed))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--vacuum", action="store_true")
    ap.add_argument("--sem-computador", action="store_true", help="não mexe nos temporários do Windows")
    ap.add_argument("--relatorio", action="store_true", help="só mostra os maiores arquivos e tabelas")
    ap.add_argument("--apagar-copias", action="store_true", help="apaga cópias redundantes do banco (pede SIM)")
    ap.add_argument("--sim", action="store_true", help="não pergunta (para scripts)")
    ap.add_argument("--respostas-velhas", action="store_true", help="apaga respostas ESPN/FotMob com 45+ dias")
    a = ap.parse_args(argv)
    os.chdir(ROOT)
    if a.relatorio:
        report()
        return 0
    log: List[Tuple[str, int]] = []
    if a.apagar_copias:
        delete_copies(a.simular, log, a.sim)
    if a.respostas_velhas:
        stale_responses(a.simular, log)
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
