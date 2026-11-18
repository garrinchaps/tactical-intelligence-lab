"""
Rodada 13 — "Elenco planejado" dentro do app (sem precisar do PDF): campinho com o XI depois da janela, cada vaga com
nota e principal característica, e a PROFUNDIDADE por posição (titular, reservas, ponto forte e ponto de atenção).
"""

from __future__ import annotations

import html
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import streamlit as st

from src.scout import engine as E

ROLE_ORDER = ["GK", "RB", "RWB", "CB", "LB", "LWB", "DM", "CM", "AM", "RM", "LM", "RW", "LW", "ST"]
OUT_CHOICES = {"Vender", "Emprestar", "Liberar", "Deixar o empréstimo acabar", "Devolver"}


def planned_roster(roster: pd.DataFrame, plan: List[Dict[str, Any]], decisions: Dict[str, str]) -> pd.DataFrame:
    r = roster.copy() if roster is not None else pd.DataFrame()
    if not r.empty:
        gone = {k for k, v in decisions.items() if not k.startswith("out::") and v in OUT_CHOICES}
        r = r[~r["nome"].astype(str).isin(gone)].copy()
        r["_novo"] = False
    rows = []
    for p in plan or []:
        rows.append({**p, "papel": p.get("papel_alvo") or p.get("papel"), "_novo": True})
    if rows:
        r = pd.concat([r, pd.DataFrame(rows)], ignore_index=True, sort=False)
    return r


def _top_trait(row) -> str:
    items = row.get("caracteristicas") if isinstance(row, dict) else None
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return f"{items[0].get('emoji', '')} {items[0].get('nome', '')}"
    return ""


def _pitch_html(xi: List[Dict[str, Any]], info: Dict[str, Dict[str, Any]]) -> str:
    dots = []
    for s in xi or []:
        if s.get("x") is None:
            continue
        left = float(s.get("y") or 40) / 80 * 100          # largura do campo
        top = 100 - float(s.get("x") or 60) / 120 * 100    # ataque para cima
        name = str(s.get("jogador") or "vaga em aberto")
        meta = info.get(name, {})
        new = meta.get("_novo")
        q = meta.get("qualidade")
        qtxt = "—" if q is None or pd.isna(q) else f"{float(q):.0f}"
        color = "#22D3EE" if new else "#3B82F6"
        trait = html.escape(meta.get("trait") or "")
        dots.append(
            f'<div style="position:absolute;left:{left:.1f}%;top:{top:.1f}%;transform:translate(-50%,-50%);'
            f'text-align:center;width:118px">'
            f'<div style="margin:0 auto;width:40px;height:40px;border-radius:50%;background:{color};'
            f'border:2px solid #E6F7FF;display:flex;align-items:center;justify-content:center;font-weight:800;'
            f'color:#06101F;font-size:.95rem;box-shadow:0 0 0 4px rgba(0,0,0,.25)">{qtxt}</div>'
            f'<div style="margin-top:4px;background:rgba(6,16,31,.88);border:1px solid #1E2A44;border-radius:8px;'
            f'padding:2px 6px;font-size:.78rem;color:#F5F7FB;font-weight:{800 if new else 600};white-space:nowrap;'
            f'overflow:hidden;text-overflow:ellipsis">{html.escape(name)}</div>'
            f'<div style="font-size:.7rem;color:#CFE8FF;margin-top:1px">{html.escape(str(s.get("papel_pt") or ""))}'
            f'{" · " + trait if trait else ""}</div></div>')
    stripes = "repeating-linear-gradient(0deg,#0E3B26 0,#0E3B26 9%,#114a2f 9%,#114a2f 18%)"
    return (f'<div style="position:relative;width:100%;max-width:560px;margin:0 auto;aspect-ratio:68/100;'
            f'background:{stripes};border:2px solid #4E7A63;border-radius:14px;overflow:hidden">'
            '<div style="position:absolute;left:0;right:0;top:50%;border-top:2px solid rgba(255,255,255,.35)"></div>'
            '<div style="position:absolute;left:50%;top:50%;width:22%;aspect-ratio:1;border:2px solid rgba(255,255,255,.35);'
            'border-radius:50%;transform:translate(-50%,-50%)"></div>'
            '<div style="position:absolute;left:22%;right:22%;top:0;height:15%;border:2px solid rgba(255,255,255,.35);border-top:0"></div>'
            '<div style="position:absolute;left:22%;right:22%;bottom:0;height:15%;border:2px solid rgba(255,255,255,.35);border-bottom:0"></div>'
            + "".join(dots) + "</div>")


def depth_rows(r: pd.DataFrame) -> List[Dict[str, Any]]:
    out = []
    if r.empty or "papel" not in r:
        return out
    q = pd.to_numeric(r.get("qualidade"), errors="coerce")
    team_avg = float(q.mean()) if q.notna().any() else None
    for role in ROLE_ORDER:
        g = r[r["papel"] == role].copy()
        if g.empty:
            continue
        g["_q"] = pd.to_numeric(g.get("qualidade"), errors="coerce")
        g = g.sort_values("_q", ascending=False, na_position="last")
        players = g.to_dict("records")
        strong, warn = [], []
        best = players[0]
        if pd.notna(best.get("_q")) and team_avg is not None and best["_q"] >= team_avg + 6:
            strong.append(f"titular acima da média do elenco ({best['_q']:.0f})")
        tr = [t for p in players[:2] for t in (p.get("caracteristicas") or []) if isinstance(t, dict)]
        if tr:
            strong.append("destaques: " + ", ".join(dict.fromkeys(t["nome"] for t in tr[:3])))
        if len(players) == 1:
            warn.append("só uma opção: uma lesão ou suspensão abre um buraco")
        elif pd.notna(players[1].get("_q")) and pd.notna(best.get("_q")) and best["_q"] - players[1]["_q"] >= 12:
            warn.append(f"reserva bem abaixo do titular ({players[1]['_q']:.0f} × {best['_q']:.0f})")
        ages = pd.to_numeric(g.get("idade"), errors="coerce")
        if ages.notna().any() and ages.min() >= 31:
            warn.append("todos com 31+ anos: planejar renovação")
        if pd.notna(best.get("_q")) and team_avg is not None and best["_q"] <= team_avg - 6:
            warn.append(f"titular abaixo da média do elenco ({best['_q']:.0f})")
        out.append({"role": role, "players": players, "forte": strong, "atencao": warn})
    return out


def render_board(team: str, roster: pd.DataFrame, plan: List[Dict[str, Any]], decisions: Dict[str, str],
                 formation: str) -> None:
    r = planned_roster(roster, plan, decisions)
    if r.empty:
        st.info("Sem elenco confirmado para montar o quadro.")
        return
    sim = E.build_simulation(r, None, None, formation)
    xi = sim.get("xi_antes") or []
    info = {}
    for row in r.to_dict("records"):
        info[str(row.get("nome"))] = {"qualidade": row.get("qualidade"), "_novo": bool(row.get("_novo")),
                                      "trait": _top_trait(row)}
    st.markdown(f"### 📋 {team} depois da janela — {formation}")
    n_new = int(r["_novo"].fillna(False).astype(bool).sum()) if "_novo" in r else 0
    n_out = sum(1 for k, v in decisions.items() if not k.startswith("out::") and v in OUT_CHOICES)
    k = st.columns(4)
    q = pd.to_numeric(r.get("qualidade"), errors="coerce")
    k[0].metric("Chegadas", n_new)
    k[1].metric("Saídas", n_out)
    k[2].metric("Elenco", len(r))
    xi_q = [info.get(str(s.get("jogador")), {}).get("qualidade") for s in xi]
    xi_q = [float(v) for v in xi_q if v is not None and pd.notna(v)]
    k[3].metric("Qualidade média do XI", f"{np.mean(xi_q):.0f}" if xi_q else "—")
    a, b = st.columns([1, 1.15])
    with a:
        st.markdown(_pitch_html(xi, info), unsafe_allow_html=True)
        st.caption("Azul-claro = contratação planejada. Número no círculo = qualidade (0–100). Abaixo do nome, a "
                   "principal característica medida.")
    with b:
        st.markdown("#### Profundidade por posição")
        for d in depth_rows(r):
            names = " · ".join(
                f"{'🆕 ' if p.get('_novo') else ''}<b>{html.escape(str(p.get('nome')))}</b> "
                f"<span style='color:#98A6BF'>{'' if pd.isna(p.get('_q')) else int(p['_q'])}</span>"
                for p in d["players"][:4])
            forte = "".join(f"<div style='color:#86EFAC;font-size:.8rem'>✓ {html.escape(x)}</div>" for x in d["forte"])
            warn = "".join(f"<div style='color:#FCA5A5;font-size:.8rem'>! {html.escape(x)}</div>" for x in d["atencao"])
            st.markdown(f"<div style='background:#0B1120;border:1px solid #1E2A44;border-radius:12px;padding:.5rem .75rem;"
                        f"margin-bottom:.4rem'><div style='font-size:.78rem;color:#22D3EE;font-weight:700;"
                        f"letter-spacing:.04em'>{html.escape(E.ROLE_LABELS.get(d['role'], d['role']).upper())}</div>"
                        f"<div style='font-size:.88rem;margin:2px 0'>{names}</div>{forte}{warn}</div>",
                        unsafe_allow_html=True)
