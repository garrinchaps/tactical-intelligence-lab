"""
Rodada 13 — visual do pré-jogo: cartão do confronto, CAMPO ÚNICO com os dois XIs (o nosso de baixo para cima, o
rival de cima para baixo), destaque nos duelos que a IA marcou, e cartões dos confrontos (forçar / proteger / evitar).
Só desenho: as contas vêm de src/squad/matchups.py e src/squad/matchday.py.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

LEVEL = {"escancarado": ("#F59E0B", "🔥 ESCANCARADO"), "claro": ("#22D3EE", "✅ CLARO")}


def hero(team: str, rival: str, when: str = "", comp: str = "", status: str = "") -> str:
    from src.ui.crests import crest_img

    def side(name, color, align):
        return (f'<div style="flex:1;text-align:{align}"><div style="display:inline-flex;align-items:center;gap:12px;'
                f'flex-direction:{"row" if align == "right" else "row-reverse"}">'
                f'<span style="font-size:1.5rem;font-weight:800;color:#F5F7FB">{html.escape(name)}</span>'
                f'<span style="transform:scale(1.6)">{crest_img(name, "sm")}</span></div>'
                f'<div style="height:4px;background:{color};border-radius:4px;margin-top:10px;opacity:.85"></div></div>')

    return (f'<div style="background:linear-gradient(135deg,#0B1A33 0%,#0B1120 55%,#2A0E14 100%);border:1px solid #1E2A44;'
            f'border-radius:18px;padding:18px 24px;margin:6px 0 14px">'
            f'<div style="text-align:center;color:#98A6BF;font-size:.85rem;letter-spacing:.06em">'
            f'{html.escape(comp.upper())}{" · " + html.escape(when) if when else ""}</div>'
            f'<div style="display:flex;align-items:center;gap:22px;margin-top:10px">{side(team, "#3B82F6", "right")}'
            f'<div style="font-size:1.1rem;font-weight:800;color:#98A6BF;padding:6px 14px;border:1px solid #1E2A44;'
            f'border-radius:10px">VS</div>{side(rival, "#EF4444", "left")}</div>'
            + (f'<div style="text-align:center;margin-top:10px;font-size:.82rem;color:#CFE8FF">{html.escape(status)}</div>'
               if status else "") + '</div>')


def _dot(s: Dict[str, Any], top: float, left: float, color: str, flag: Optional[int] = None) -> str:
    name = str(s.get("jogador") or "vaga")
    short = name if len(name) <= 16 else name.split()[-1]
    q = s.get("qualidade", s.get("nota"))
    qtxt = "—" if q is None else f"{float(q):.1f}"
    ring = "#F59E0B" if flag else "#E6F7FF"
    badge = (f'<span style="position:absolute;top:-6px;right:34px;background:#F59E0B;color:#06101F;border-radius:50%;'
             f'width:18px;height:18px;font-size:.7rem;font-weight:800;line-height:18px">{flag}</span>') if flag else ""
    tip = html.escape(f"{name} · {s.get('papel_pt') or s.get('papel') or ''} · qualidade {qtxt}")
    return (f'<div title="{tip}" style="position:absolute;left:{left:.1f}%;top:{top:.1f}%;transform:translate(-50%,-50%);'
            f'width:104px;text-align:center">{badge}'
            f'<div style="margin:0 auto;width:34px;height:34px;border-radius:50%;background:{color};border:2px solid {ring};'
            f'display:flex;align-items:center;justify-content:center;font-weight:800;color:#fff;font-size:.78rem;'
            f'box-shadow:0 2px 6px rgba(0,0,0,.45)">{qtxt}</div>'
            f'<div style="margin-top:3px;background:rgba(6,16,31,.86);border-radius:6px;padding:1px 5px;font-size:.72rem;'
            f'color:#F5F7FB;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{html.escape(short)}</div></div>')


def double_pitch(my_xi: List[Dict[str, Any]], rv_xi: List[Dict[str, Any]], team: str, rival: str,
                 flags: Optional[Dict[str, int]] = None) -> str:
    """Campo em pé: nosso time na metade de baixo atacando para cima (azul); o rival na de cima (vermelho)."""
    flags = flags or {}
    dots = []
    for s in my_xi or []:
        if s.get("x") is None:
            continue
        top = 96 - float(s["x"]) / 120 * 46
        left = 6 + float(s.get("y") or 40) / 80 * 88
        dots.append(_dot(s, top, left, "#2563EB", flags.get(str(s.get("jogador")))))
    for s in rv_xi or []:
        if s.get("x") is None:
            continue
        top = 4 + float(s["x"]) / 120 * 46
        left = 94 - float(s.get("y") or 40) / 80 * 88
        dots.append(_dot(s, top, left, "#DC2626", flags.get(str(s.get("jogador")))))
    stripes = "repeating-linear-gradient(0deg,#0E3B26 0,#0E3B26 7%,#11472E 7%,#11472E 14%)"
    lines = ("position:absolute;border:2px solid rgba(255,255,255,.32)")
    return (f'<div style="position:relative;width:100%;max-width:640px;margin:0 auto;aspect-ratio:68/105;background:{stripes};'
            f'border:2px solid #4E7A63;border-radius:16px;overflow:hidden">'
            f'<div style="{lines};left:0;right:0;top:50%;border-width:2px 0 0 0"></div>'
            f'<div style="{lines};left:50%;top:50%;width:20%;aspect-ratio:1;border-radius:50%;transform:translate(-50%,-50%)"></div>'
            f'<div style="{lines};left:21%;right:21%;top:0;height:16%;border-top:0"></div>'
            f'<div style="{lines};left:21%;right:21%;bottom:0;height:16%;border-bottom:0"></div>'
            f'<div style="position:absolute;left:10px;top:8px;font-size:.75rem;color:#FCA5A5;font-weight:700">🔴 {html.escape(rival)}</div>'
            f'<div style="position:absolute;left:10px;bottom:8px;font-size:.75rem;color:#93C5FD;font-weight:700">🔵 {html.escape(team)}</div>'
            + "".join(dots) + "</div>")


def finding_card(i: int, f: Dict[str, Any], kind: str = "forcar") -> str:
    color, tag = LEVEL.get(f.get("nivel"), ("#22D3EE", f.get("nivel", "").upper()))
    edge = {"forcar": "#22C55E", "proteger": "#EF4444", "estilo": "#22C55E", "evitar": "#EF4444"}.get(kind, color)
    who = (f'<div style="font-size:.95rem;font-weight:800;color:#F5F7FB">{html.escape(f.get("atacante", ""))} '
           f'<span style="color:#98A6BF;font-weight:600">×</span> {html.escape(f.get("defensor", ""))}</div>'
           if f.get("atacante") else "")
    return (f'<div style="background:#0B1120;border:1px solid #1E2A44;border-left:5px solid {edge};border-radius:14px;'
            f'padding:.65rem .9rem;margin-bottom:.55rem">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">'
            f'<div style="font-size:.78rem;color:#22D3EE;font-weight:800;letter-spacing:.05em">{i}. {html.escape(f["titulo"].upper())}</div>'
            f'<span style="font-size:.7rem;font-weight:800;color:#06101F;background:{color};border-radius:8px;'
            f'padding:2px 7px">{tag}</span></div>{who}'
            f'<div style="font-size:.82rem;color:#CBD5E1;margin-top:4px">{html.escape(f["evidencia"])}</div>'
            f'<div style="font-size:.88rem;color:#F5F7FB;margin-top:6px;font-weight:700">{html.escape(f["acao"])}</div>'
            + (f'<div style="font-size:.72rem;color:#A7F3D0;margin-top:3px">Índice fuzzy de exploração {f["fuzzy"]:.0f}/100'
               f'{" · peso aprendido com seus 👍/👎: " + format(f["peso_aprendido"], ".2f") if f.get("peso_aprendido", 1) != 1 else ""}'
               f'</div>' if f.get("fuzzy") is not None else "")
            + f'<div style="font-size:.72rem;color:#7C8BA5;margin-top:3px">Base: {html.escape(f.get("base", ""))}</div></div>')
