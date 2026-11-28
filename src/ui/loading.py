"""
Rodada 19 — telas de carregamento no visual do laboratório.

* `splash(state)`: tela cheia enquanto o pré-aquecimento roda ao ligar o app — campinho com uma triangulação de passes
  animada, passos com ✓ e barra de progresso. Tem "Entrar agora" para quem não quer esperar.
* `overlay()`: cobertura translúcida durante qualquer troca de tela. Só APARECE se a tela demorar mais de 0,35 s
  (animação com atraso, puro CSS) — telas rápidas não piscam.
"""

from __future__ import annotations

import html
import re
import time
from typing import Any, Dict, List

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
.til-flip{transform-box:fill-box;transform-origin:center;animation:tilFlip 1.8s ease-in-out infinite}
@keyframes tilFlip{0%,100%{transform:scaleX(1)}50%{transform:scaleX(.08)}}
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


# rodada 21: uma animação por área (o usuário pediu telas de carregamento diferentes para lugares diferentes)
_C, _B, _W, _R = "#22D3EE", "#3B82F6", "#F8FAFC", "#EF4444"
_ANIM = {
    "assistente": ("Pensando na resposta…", f"""
<svg viewBox="0 0 120 80" class="til-pitch"><rect x="14" y="16" width="70" height="30" rx="10" fill="#111A2E" stroke="{_B}"/>
<path d="M30 46 l-6 10 l14-10z" fill="#111A2E" stroke="{_B}"/>
<circle cx="36" cy="31" r="3.4" fill="{_C}"><animate attributeName="opacity" values=".2;1;.2" dur="1.2s" repeatCount="indefinite"/></circle>
<circle cx="49" cy="31" r="3.4" fill="{_C}"><animate attributeName="opacity" values=".2;1;.2" dur="1.2s" begin=".2s" repeatCount="indefinite"/></circle>
<circle cx="62" cy="31" r="3.4" fill="{_C}"><animate attributeName="opacity" values=".2;1;.2" dur="1.2s" begin=".4s" repeatCount="indefinite"/></circle>
<rect x="56" y="50" width="50" height="18" rx="8" fill="#0F2A3A" stroke="{_C}" opacity=".7"/></svg>"""),
    "buscar": ("Procurando na base…", f"""
<svg viewBox="0 0 120 80" class="til-pitch"><circle cx="60" cy="40" r="30" fill="none" stroke="#1E3A5F"/>
<circle cx="60" cy="40" r="19" fill="none" stroke="#1E3A5F"/><circle cx="60" cy="40" r="8" fill="none" stroke="#1E3A5F"/>
<path d="M60 40 L60 10 A30 30 0 0 1 86 25 Z" fill="{_C}" opacity=".35">
<animateTransform attributeName="transform" type="rotate" from="0 60 40" to="360 60 40" dur="1.8s" repeatCount="indefinite"/></path>
<circle cx="78" cy="30" r="2.6" fill="{_W}"><animate attributeName="opacity" values="0;1;0" dur="1.8s" repeatCount="indefinite"/></circle>
<circle cx="45" cy="55" r="2.6" fill="{_W}"><animate attributeName="opacity" values="0;1;0" dur="1.8s" begin=".9s" repeatCount="indefinite"/></circle></svg>"""),
    "scout": ("Garimpando o mercado…", f"""
<svg viewBox="0 0 120 80" class="til-pitch">
{''.join(f'<rect x="{12 + i * 24}" y="22" width="18" height="28" rx="3" fill="#111A2E" stroke="#1E3A5F"/><circle cx="{21 + i * 24}" cy="31" r="4" fill="#1E3A5F"/>' for i in range(4))}
<g><circle cx="0" cy="0" r="11" fill="none" stroke="{_C}" stroke-width="2.4"/><line x1="8" y1="8" x2="16" y2="16" stroke="{_C}" stroke-width="3" stroke-linecap="round"/>
<animateTransform attributeName="transform" type="translate" values="21,36;45,36;69,36;93,36;21,36" dur="2.4s" repeatCount="indefinite"/></g></svg>"""),
    "escalacao": ("Montando a escalação…", f"""
<svg viewBox="0 0 120 80" class="til-pitch"><rect x="1" y="1" width="118" height="78" rx="3" class="ln"/><line x1="60" y1="1" x2="60" y2="79" class="ln"/>
{''.join(f'<circle r="3.2" fill="{_B}" stroke="#90CDF4" stroke-width=".5"><animate attributeName="cx" values="60;{x};{x}" dur="2.2s" repeatCount="indefinite"/><animate attributeName="cy" values="40;{y};{y}" dur="2.2s" repeatCount="indefinite"/></circle>' for x, y in [(10, 40), (26, 14), (24, 31), (24, 49), (26, 66), (44, 40), (52, 22), (52, 58), (74, 16), (82, 40), (74, 64)])}
</svg>"""),
    "rankings": ("Ordenando os melhores…", f"""
<svg viewBox="0 0 120 80" class="til-pitch">{''.join(f'<rect x="{18 + i * 22}" width="16" rx="2" fill="{c}"><animate attributeName="height" values="0;{h};{h}" dur="1.6s" repeatCount="indefinite"/><animate attributeName="y" values="70;{70 - h};{70 - h}" dur="1.6s" repeatCount="indefinite"/></rect>' for i, (h, c) in enumerate([(34, "#94A3B8"), (52, "#FBBF24"), (24, "#B45309"), (14, "#1E3A5F")]))}
<line x1="10" y1="70" x2="110" y2="70" stroke="#1E3A5F"/></svg>"""),
    "comparar": ("Colocando lado a lado…", f"""
<svg viewBox="0 0 120 80" class="til-pitch"><line x1="60" y1="12" x2="60" y2="70" stroke="#1E3A5F" stroke-width="2"/>
<g><line x1="24" y1="22" x2="96" y2="22" stroke="{_C}" stroke-width="2"/><circle cx="24" cy="38" r="9" fill="{_B}" opacity=".8"/>
<circle cx="96" cy="38" r="9" fill="{_R}" opacity=".8"/>
<animateTransform attributeName="transform" type="rotate" values="-8 60 22;8 60 22;-8 60 22" dur="2s" repeatCount="indefinite"/></g></svg>"""),
    "jogo": ("Lendo os lances do jogo…", None),
    "time": ("Abrindo o clube…", f"""
<svg viewBox="0 0 120 80" class="til-pitch"><path d="M60 10 L86 18 L82 50 Q60 70 60 70 Q60 70 38 50 L34 18 Z" fill="#111A2E" stroke="{_C}" stroke-width="2">
<animate attributeName="stroke-width" values="1;3;1" dur="1.4s" repeatCount="indefinite"/></path>
<circle cx="60" cy="38" r="9" fill="none" stroke="{_B}" stroke-width="2"><animate attributeName="r" values="6;11;6" dur="1.4s" repeatCount="indefinite"/></circle></svg>"""),
    "jogador": ("Abrindo a ficha do jogador…", f"""
<svg viewBox="0 0 120 80" class="til-pitch"><g class="til-flip"><rect x="42" y="8" width="36" height="58" rx="5" fill="#111A2E" stroke="{_C}"/>
<circle cx="60" cy="28" r="9" fill="#1E3A5F"/><rect x="48" y="44" width="24" height="4" rx="2" fill="#1E3A5F"/><rect x="50" y="52" width="20" height="4" rx="2" fill="#1E3A5F"/>
</g></svg>"""),
    "como-a-ia-aprende": ("A IA está calculando…", f"""
<svg viewBox="0 0 120 80" class="til-pitch">{''.join(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#1E3A5F"/>' for x1, y1 in [(20, 20), (20, 40), (20, 60)] for x2, y2 in [(60, 15), (60, 32), (60, 48), (60, 65)])}
{''.join(f'<line x1="60" y1="{y}" x2="100" y2="40" stroke="#1E3A5F"/>' for y in (15, 32, 48, 65))}
{''.join(f'<circle cx="{x}" cy="{y}" r="4" fill="{_B}"><animate attributeName="fill" values="{_B};{_C};{_B}" dur="1.5s" begin="{d}s" repeatCount="indefinite"/></circle>' for x, y, d in [(20, 20, 0), (20, 40, 0), (20, 60, 0), (60, 15, .3), (60, 32, .3), (60, 48, .3), (60, 65, .3), (100, 40, .6)])}</svg>"""),
}


def overlay_html(kind: str = "", msg: str = "") -> str:
    """Cobertura de carregamento com a animação da ÁREA (`kind` = url da tela)."""
    label, svg = _ANIM.get(kind or "", ("Preparando a análise…", None))
    return (_CSS + f'<div class="til-overlay">{svg or _PITCH}<div class="til-msg">{html.escape(msg or label)}</div></div>')


def splash_html(state: Dict[str, Any]) -> str:
    steps = state.get("steps") or []
    done = sum(1 for s in steps if s["status"] not in ("fila", "rodando"))
    pct = int(100 * done / len(steps)) if steps else 5
    rows = []
    # rodada 22: passos repetidos ("Jogos que você abriu por último (1/3)", "(2/3)"...) viram UMA linha, sem nomes
    grouped: List[Dict[str, Any]] = []
    for s in steps:
        base = re.sub(r"\s*\(\d+/\d+\)$", "", str(s["nome"]))
        if grouped and grouped[-1]["nome"] == base:
            g = grouped[-1]
            g["n"] += 1
            g["s"] = (g.get("s") or 0) + (s.get("s") or 0)
            order = {"rodando": 0, "fila": 1}
            if order.get(s["status"], 2) < order.get(g["status"], 2):
                g["status"] = s["status"]
        else:
            grouped.append({"nome": base, "status": s["status"], "s": s.get("s"), "n": 1})
    for s in grouped[:14]:
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
    # rodada 27: só espera o ESSENCIAL (base + Scout) e no máximo 25 s — times e jogos recentes continuam sendo
    # preparados em segundo plano com o app já aberto (antes a tela ficou 6 min em "Times que você abriu por último")
    steps = state.get("steps") or []
    essential = [s_ for s_ in steps if str(s_.get("nome", "")).startswith(("Abrindo a base", "Mercado do Scout"))]
    if (essential and all(s_.get("status") not in ("fila", "rodando") for s_ in essential)) or \
            (time.time() - float(state.get("t0") or time.time())) > 25:
        st.session_state["_warm_skip"] = True
        return True
    st.markdown(splash_html(state), unsafe_allow_html=True)
    _, mid, _ = st.columns([2, 1, 2])
    if mid.button("Entrar agora", width="stretch", key="til_warm_skip"):
        st.session_state["_warm_skip"] = True
        st.rerun()
    time.sleep(0.8)
    st.rerun()
    return False
