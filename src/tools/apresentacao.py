"""
Rodada 18 — conferência ANTES de publicar o app para a apresentação (link público grátis).

    python -m src.tools.apresentacao            # diz o que está pronto e o que falta, em uma tela

Não abre o .env (só diz se uma variável está "definida/não definida"), não grava nada e não acessa a rede.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

from src.tools import proc

OK, WARN, BAD = "✅", "⚠️ ", "❌"


def _age_h(p: Path) -> float | None:
    try:
        return (time.time() - p.stat().st_mtime) / 3600
    except OSError:
        return None


def _gb(n: float) -> str:
    return f"{n / 1e9:.1f} GB"


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    for c in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe"):
        if Path(c).exists():
            return c
    return None


def checks(port: int = 8501) -> List[Tuple[str, str, str]]:
    """(situação, item, explicação/comando). Situação: ✅ pronto · ⚠️ funciona mas pode melhorar · ❌ resolver antes."""
    out: List[Tuple[str, str, str]] = []
    try:
        from dotenv import load_dotenv

        load_dotenv()                                   # só para saber se as variáveis existem (valores não são lidos aqui)
    except Exception:
        pass
    from src.data_hub.db import DEFAULT_DB

    db_path = Path(os.getenv("TACTICAL_DB_PATH") or os.getenv("DATABASE_PATH") or str(DEFAULT_DB))
    if not db_path.exists():
        out.append((BAD, "Banco de dados", f"não achei {db_path}. Rode o app uma vez no PC antes."))
    else:
        out.append((OK, "Banco de dados", f"{db_path} · {_gb(db_path.stat().st_size)}"))
        try:
            from src.data_hub.db import DataHubDB

            falta = DataHubDB(db_path).missing_speed_indexes()
            out.append((OK, "Índices de velocidade", "todos criados") if not falta else
                       (WARN, "Índices de velocidade", f"faltam {len(falta)} — com o app fechado: python -m src.tools.criar_indices"))
        except Exception as exc:
            out.append((WARN, "Índices de velocidade", f"não consegui conferir ({type(exc).__name__})"))
        try:
            import sqlite3

            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5) as c:
                n = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            out.append((OK, "Partidas na base", f"{n:,}".replace(",", ".")))
        except Exception as exc:
            out.append((WARN, "Partidas na base", f"não consegui contar ({type(exc).__name__}) — o app pode estar gravando"))
    for path, name, cmd in [
        (Path("data/processed/evaluations.parquet"), "Rankings (avaliações)", "python -m src.scout.evaluation"),
        (Path("data/processed/player_index.parquet"), "Índice da busca de jogadores", "abre o app 1× e espere o processo de fundo"),
        (__import__("src.scout.snapshot", fromlist=["SNAP_PATH"]).SNAP_PATH, "Fotografia do Scout",
         "python -m src.scout.snapshot"),
        (Path("data/processed/matchup_ref.parquet"), "Régua dos confrontos (pré-jogo)", "abre o app 1× e espere o processo de fundo"),
    ]:
        h = _age_h(path)
        if h is None:
            out.append((WARN, name, f"ainda não existe — {cmd} (a tela calcula na hora, só que mais devagar)"))
        else:
            out.append((OK if h < 72 else WARN, name, f"atualizado há {h:.0f} h" + ("" if h < 72 else f" — refaça: {cmd}")))
    sb = "definida" if os.getenv("STATSBOMB_OPEN_DATA_PATH") else "não definida"
    out.append((OK if sb == "definida" else WARN, "StatsBomb no disco", f"STATSBOMB_OPEN_DATA_PATH {sb}" + ("" if sb == "definida" else
                " — sem ela os lances vêm do GitHub (mais lento na 1ª abertura de cada jogo)")))
    cf = _cloudflared()
    ts = shutil.which("tailscale") or (r"C:\Program Files\Tailscale\tailscale.exe"
                                       if Path(r"C:\Program Files\Tailscale\tailscale.exe").exists() else None)
    ng = shutil.which("ngrok")
    if ts or ng:
        out.append((OK, "Link FIXO (rodada 21)", ("Tailscale Funnel" if ts else "ngrok") + " instalado — o link não muda"))
    else:
        out.append((WARN, "Link FIXO (rodada 21)", "para o link ser sempre o mesmo: winget install --id Tailscale.Tailscale "
                                                    "(ou Ngrok.Ngrok); sem eles usa a Cloudflare (link muda a cada vez)"))
    out.append((OK, "cloudflared (túnel grátis)", cf) if cf else
               ((WARN if (ts or ng) else BAD), "cloudflared (túnel grátis)",
                "instale: winget install --id Cloudflare.cloudflared (e abra um terminal novo)"))
    try:
        from src.ui.accounts import google_ready

        g = Path(".streamlit/secrets.toml").exists()
        out.append((OK if g else WARN, "Entrar com Google", "configurado" if g else
                    "opcional: pip install Authlib e python -m src.tools.configurar_login (contas com senha já funcionam)"))
    except Exception:
        pass
    out.append((WARN, f"Porta {port}", "ocupada — feche o app aberto antes de rodar o script de apresentação")
               if _port_busy(port) else (OK, f"Porta {port}", "livre"))
    try:
        free = shutil.disk_usage(str(Path.cwd())).free
        out.append((OK if free > 5e9 else WARN, "Espaço livre no disco", _gb(free)))
    except OSError:
        pass
    if os.name == "nt":                                   # rodada 22: tarefa agendada antiga abre janela de cmd
        old = []
        for n in ("TacticalLabRapido", "TacticalLabDiario", "TacticalLabSync"):
            try:
                o = proc.run(["schtasks", "/Query", "/TN", n, "/V", "/FO", "LIST"], capture_output=True, text=True,
                             timeout=10).stdout or ""
            except Exception:
                o = ""
            if "cmd /c" in o.lower() or "cmd.exe" in o.lower():
                old.append(n)
        out.append((WARN, "Janela de cmd a cada 3 h", f"tarefas antigas {', '.join(old)} abrem janela — rode "
                    ".\\scripts\\agendar_atualizacao.ps1 (versão silenciosa) ou com -Remover") if old else
                   (OK, "Tarefas agendadas", "nenhuma abre janela de cmd"))
    try:
        br = proc.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
        cm = proc.run(["git", "log", "-1", "--format=%h %cd", "--date=short"], capture_output=True, text=True, timeout=5).stdout.strip()
        out.append((OK if br == "claude/gifted-knuth-q93cbz" else WARN, "Versão do código", f"{br} · {cm}"))
    except Exception:
        pass
    return out


def main() -> None:
    rows = checks()
    print("\nConferência para a apresentação\n" + "-" * 34)
    for s, item, why in rows:
        print(f"{s} {item}: {why}")
    bad = sum(1 for s, _, _ in rows if s == BAD)
    print("-" * 34)
    print("Pronto para publicar: .\\scripts\\apresentar.ps1" if not bad else f"Resolva os {bad} item(ns) com ❌ antes.")


if __name__ == "__main__":
    main()
