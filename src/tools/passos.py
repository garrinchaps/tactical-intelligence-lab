"""
Rodada 27 — o `atualizar_tudo.ps1` só roda o que está VENCIDO. Cada etapa guarda quando terminou em
data/atualizacao_passos.json; se ainda está dentro do prazo, é pulada (o script mostra "pulado").

    python -m src.tools.passos --vencido NOME --horas 24     # sai com 0 se precisa rodar, 10 se pode pular
    python -m src.tools.passos --feito NOME                  # marca como feito agora
    python -m src.tools.passos --mudou requirements.txt      # 0 se o arquivo mudou desde a última vez, 10 se não
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "atualizacao_passos.json"


def _load() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)


def due(name: str, hours: float) -> bool:
    t = _load().get(name, {}).get("t")
    return t is None or (time.time() - float(t)) >= hours * 3600


def done(name: str) -> None:
    d = _load()
    d[name] = {"t": time.time(), "quando": time.strftime("%Y-%m-%d %H:%M")}
    _save(d)


def changed(path: str) -> bool:
    f = ROOT / path
    h = hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else ""
    key = f"hash:{path}"
    d = _load()
    if d.get(key, {}).get("h") == h:
        return False
    d[key] = {"h": h, "t": time.time()}
    _save(d)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vencido")
    ap.add_argument("--horas", type=float, default=24)
    ap.add_argument("--feito")
    ap.add_argument("--mudou")
    a = ap.parse_args(argv)
    if a.feito:
        done(a.feito)
        return 0
    if a.mudou:
        return 0 if changed(a.mudou) else 10
    if a.vencido:
        if due(a.vencido, a.horas):
            return 0
        info = _load().get(a.vencido, {})
        print(f"    pulado: feito em {info.get('quando', '?')} (refaz a cada {a.horas:g} h; use -Tudo para forçar)")
        return 10
    return 0


if __name__ == "__main__":
    sys.exit(main())
