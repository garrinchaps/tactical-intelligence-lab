"""
Rodada 22 — programas externos (git, tasklist, schtasks) SEM abrir janela de "cmd" no Windows.

No Windows, quando um processo sem console (o processo de fundo do app roda com CREATE_NO_WINDOW) chama um programa
de console como git.exe, o sistema cria um console NOVO para ele — é a janela preta que pisca e some ("cmd" /
"conhost"). Toda chamada a programa externo do laboratório passa por aqui.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List

CREATE_NO_WINDOW = 0x08000000


def hidden() -> Dict[str, Any]:
    """Argumentos extras para subprocess.run/Popen: sem janela no Windows; nada nos outros sistemas."""
    if os.name != "nt":
        return {}
    kw: Dict[str, Any] = {"creationflags": CREATE_NO_WINDOW}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0                                  # SW_HIDE
        kw["startupinfo"] = si
    except Exception:
        pass
    return kw


def run(cmd: List[str], **kw: Any) -> subprocess.CompletedProcess:
    """subprocess.run sem janela (o resto dos argumentos é igual)."""
    extra = hidden()
    if "creationflags" in kw and "creationflags" in extra:
        kw["creationflags"] |= extra.pop("creationflags")
    return subprocess.run(cmd, **{**extra, **kw})
