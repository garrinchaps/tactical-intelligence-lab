"""
Rodada 19 — telas de carregamento no visual do laboratório.

* `splash(state)`: tela cheia enquanto o pré-aquecimento roda ao ligar o app — campinho com uma triangulação de passes
  animada, passos com ✓ e barra de progresso. Tem "Entrar agora" para quem não quer esperar.
* `overlay()`: cobertura translúcida durante qualquer troca de tela. Só APARECE se a tela demorar mais de 0,35 s
  (animação com atraso, puro CSS) — telas rápidas não piscam.
"""

from __future__ import annotations

import html
import time
from typing import Any, Dict

_PITCH = """
<svg viewBox="0 0 120 80" class="til-pitch" aria-hidden="true">
  <rect x="1" y="1" width="118" height="78" rx="3" class="ln"/>
  <line x1="60" y1="1" x2="60" y2="79" class="ln"/>
  <circle cx="60" cy="40" r="9" class="ln"/>
  <rect x="1" y="20" width="16" height="40" class="ln"/><rect x="103" y="20" width="16" height="40" class="ln"/>
  <rect x="1" y="31" width="5" height="18" class="ln"/><rect x="114" y="31" width="5" height="18" class="ln"/>
  <path d="M28 58 L52 24 L84 46 L28 58" class="pass"/>
  <circle cx="28" cy="58" r="3.2" class="pl a"/><circle cx="52" cy="24" r="3.2" class="pl b"/>
  <circle cx="84" cy="46" r="3.2" class="pl c"/>
  <circle r="2" class="ball"><animateMotion dur="2.4s" repeatCount="indefinite" path="M28 58 L52 24 L84 46 L28 58"/></circle>
</svg>
"""

_CSS = """
<style>
.til-pitch{width:min(320px,72vw);height:auto;filter:drop-shadow(0 0 18px rgba(34,211,238,.18))}
.til-pitch .ln{fill:none;stroke:#1E3A5F;stroke-width:.8}
.til-pitch .pass{fill:none;stroke:#22D3EE;stroke-width:.7;stroke-dasharray:3 3;opacity:.55;
  animation:tilDash 1.2s linear infinite}
.til-pitch .pl{fill:#3B82F6;stroke:#90CDF4;stroke-width:.5}
.til-pitch .pl.b{fill:#22D3EE}.til-pitch .pl.c{fill:#60A5FA}
.til-pitch .ball{fill:#F8FAFC;filter:drop-shadow(0 0 3px #fff)}
@keyframes tilDash{to{stroke-dashoffset:-12}}
@keyframes tilIn{to{opacity:1;visibility:visible}}
@keyframes tilPulse{0%,100%{opacity:.55}50%{opacity:1}}
.til-overlay{position:fixed;inset:0;z-index:999990;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:.6rem;background:rgba(9,13,22,.78);backdrop-filter:blur(3px);opacity:0;visibility:hidden;
  animation:tilIn .25s ease .35s forwards;pointer-events:none}
.til-overlay .til-msg{color:#94A3B8;font-size:.92rem;letter-spacing:.02em;animation:tilPulse 1.6s ease infinite}
.til-splash{min-height:78vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.9rem;
  text-align:center}
.til-splash h1{margin:0;color:#22D3EE;font-size:clamp(1.5rem,4.5vw,2.3rem);letter-spacing:.01em}
.til-splash .sub{color:#94A3B8;margin-top:-.4rem}
.til-bar{width:min(420px,80vw);height:6px;border-radius:99px;background:#111A2E;border:1px solid #1E2A44;overflow:hidden}
.til-bar>div{height:100%;background:linear-gradient(90deg,#3B82F6,#22D3EE);border-radius:99px;transition:width .4s}
.til-steps{width:min(420px,86vw);text-align:left;font-size:.86rem;color:#98A6BF;line-height:1.65}
.til-steps .ok{color:#22C55E}.til-steps .run{color:#22D3EE;animation:tilPulse 1.2s ease infinite}
.til-steps .skip{color:#FBBF24}
</style>
"""


def overlay_html(msg: str = "Preparando a análise…") -> str:
    return (_CSS + f'<div class="til-overlay">{_PITCH}<div class="til-msg">{html.escape(msg)}</div></div>')


def splash_html(state: Dict[str, Any]) -> str:
    steps = state.get("steps") or []
    done = sum(1 for s in steps if s["status"] not in ("fila", "rodando"))
    pct = int(100 * done / len(steps)) if steps else 5
    rows = []
    for s in steps[:14]:
        st_ = s["status"]
        if st_ == "ok":
            icon, cls, tail = "✓", "ok", f" · {s['s']:.1f} s" if s.get("s") is not None else ""
        elif st_ == "rodando":
            icon, cls, tail = "●", "run", ""
        elif st_.startswith("pulado"):
            icon, cls, tail = "–", "skip", " · pulado"
        else:
            icon, cls, tail = "○", "", ""
        rows.append(f'<div class="{cls}">{icon} {html.escape(s["nome"])}{tail}</div>')
    el = time.time() - (state.get("t0") or time.time())
    return (_CSS + '<div class="til-splash">' + _PITCH +
            '<h1>Tactical Intelligence Lab</h1>'
            f'<div class="sub">Deixando tudo pronto para abrir na hora · {el:.0f} s</div>'
            f'<div class="til-bar"><div style="width:{pct}%"></div></div>'
            f'<div class="til-steps">{"".join(rows)}</div></div>')


def splash_gate(state: Dict[str, Any]) -> bool:
    """Mostra a tela de carregamento enquanto o pré-aquecimento roda. True = pode seguir para o app."""
    import streamlit as st

    if state.get("done") or st.session_state.get("_warm_skip"):
        return True
    st.markdown(splash_html(state), unsafe_allow_html=True)
    _, mid, _ = st.columns([2, 1, 2])
    if mid.button("Entrar agora", use_container_width=True, key="til_warm_skip"):
        st.session_state["_warm_skip"] = True
        st.rerun()
    time.sleep(0.8)
    st.rerun()
    return False
