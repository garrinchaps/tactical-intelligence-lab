"""
Dossiê da janela em PDF (rodada 11): capa com o clube, campinho com o XI planejado, quem chega (com o porquê e a
viabilidade), quem sai, decisões de empréstimo e o saldo estimado. Valores são ESTIMATIVAS (não há salários nem
orçamento oficial) e o PDF diz isso.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional


def _money(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"€ {v / 1e6:.1f} mi" if abs(v) >= 1e6 else f"€ {v / 1e3:.0f} mil"


def build(team: str, formation: str, xi: List[Dict[str, Any]], plan: List[Dict[str, Any]],
          decisions: Dict[str, str], balance: Optional[float], season: Any = "") -> Optional[bytes]:
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except ImportError:
        return None
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    W, H = A4
    bg, card, line, cyan, red, txt, muted = (HexColor(x) for x in
                                             ("#090D16", "#0B1120", "#1E2A44", "#22D3EE", "#EF4444", "#F5F7FB", "#98A6BF"))

    def page_bg():
        pdf.setFillColor(bg)
        pdf.rect(0, 0, W, H, fill=1, stroke=0)

    def wrap(text, x, y, width, size=9, color=txt, font="Helvetica"):
        pdf.setFillColor(color)
        pdf.setFont(font, size)
        cur = ""
        for w in str(text).split():
            t = (cur + " " + w).strip()
            if stringWidth(t, font, size) > width:
                pdf.drawString(x, y, cur)
                y -= size + 3
                cur = w
            else:
                cur = t
        if cur:
            pdf.drawString(x, y, cur)
            y -= size + 3
        return y

    # ---------------- página 1: capa + campinho
    page_bg()
    pdf.setFillColor(cyan)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(40, H - 40, "TACTICAL INTELLIGENCE LAB · DOSSIÊ DE SCOUT")
    pdf.setFillColor(txt)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(40, H - 70, f"{team} — janela {season}")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(muted)
    pdf.drawString(40, H - 88, f"XI planejado em {formation} · {len(plan)} chegada(s) · "
                               f"{sum(1 for v in decisions.values() if v not in ('Fica', 'Renovar empréstimo'))} decisão(ões) de saída/empréstimo")
    # campo em pé
    px, py, pw, ph = 70, 150, W - 140, H - 270
    pdf.setFillColor(HexColor("#0B2318"))
    pdf.setStrokeColor(HexColor("#4E7A63"))
    pdf.rect(px, py, pw, ph, fill=1, stroke=1)
    pdf.line(px, py + ph / 2, px + pw, py + ph / 2)
    pdf.circle(px + pw / 2, py + ph / 2, 40, fill=0, stroke=1)
    pdf.rect(px + pw * .22, py, pw * .56, ph * .16, fill=0, stroke=1)
    pdf.rect(px + pw * .22, py + ph * .84, pw * .56, ph * .16, fill=0, stroke=1)
    new_names = {p.get("nome") for p in plan}
    for s in xi:
        # coordenadas StatsBomb (x = profundidade 0–120, y = largura 0–80) → campo em pé, ataque para cima
        cx = px + pw * (float(s.get("y") or 40) / 80)
        cy = py + ph * (float(s.get("x") or 60) / 120)
        new = s.get("jogador") in new_names
        pdf.setFillColor(cyan if new else HexColor("#3B82F6"))
        pdf.circle(cx, cy, 13, fill=1, stroke=0)
        pdf.setFillColor(bg)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawCentredString(cx, cy - 2.5, str(s.get("papel") or ""))
        pdf.setFillColor(txt)
        pdf.setFont("Helvetica-Bold" if new else "Helvetica", 8)
        pdf.drawCentredString(cx, cy - 24, str(s.get("jogador") or "vaga")[:22])
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(40, 120, "Azul-claro = contratação planejada. Posições pelo desenho escolhido.")
    pdf.setFillColor(txt)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(40, 95, f"Saldo estimado da janela: {_money(balance)}")
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(40, 80, "Estimativa: vendas a 60% do valor de referência, compras pela taxa estimada; sem salários nem luvas.")
    pdf.showPage()
    # ---------------- página 2: decisões, um cartão por decisão
    page_bg()
    y = H - 50
    pdf.setFillColor(txt)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "Quem chega")
    y -= 22
    for p in plan:
        r = p.get("realismo") if isinstance(p.get("realismo"), dict) else {}
        if y < 140:
            pdf.showPage()
            page_bg()
            y = H - 50
        pdf.setFillColor(card)
        pdf.setStrokeColor(line)
        pdf.roundRect(36, y - 92, W - 72, 96, 8, fill=1, stroke=1)
        pdf.setFillColor(cyan)
        pdf.rect(36, y - 92, 4, 96, fill=1, stroke=0)
        pdf.setFillColor(txt)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(50, y - 14, f"{p.get('nome')} · {p.get('papel_alvo_label') or ''}")
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 8.5)
        pdf.drawString(50, y - 28, f"{p.get('clube') or '—'} · {p.get('nacionalidade') or '—'} · qualidade "
                                    f"{p.get('qualidade') or '—'} · viabilidade {r.get('score', '—')}% ({r.get('rotulo', '—')}) · "
                                    f"taxa estimada {_money(r.get('taxa_estimada_eur'))}")
        yy = wrap("Por quê: " + str(p.get("motivo_principal") or "reforço da posição"), 50, y - 44, W - 110, 8.5)
        for m in (r.get("motivos") or [])[3:5]:
            yy = wrap(m, 50, yy, W - 110, 8, muted)
        y -= 106
    y -= 8
    outs = [(k, v) for k, v in decisions.items() if v not in ("Fica", "Renovar empréstimo")]
    pdf.setFillColor(txt)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "Quem sai / empréstimos")
    y -= 20
    if not outs:
        y = wrap("Nenhuma saída planejada.", 50, y, W - 110, 9, muted)
    for name, choice in outs:
        if y < 70:
            pdf.showPage()
            page_bg()
            y = H - 50
        pdf.setFillColor(card)
        pdf.roundRect(36, y - 22, W - 72, 26, 6, fill=1, stroke=0)
        pdf.setFillColor(red if choice in ("Vender", "Deixar o empréstimo acabar") else cyan)
        pdf.rect(36, y - 22, 4, 26, fill=1, stroke=0)
        pdf.setFillColor(txt)
        pdf.setFont("Helvetica", 9.5)
        pdf.drawString(50, y - 13, f"{name.replace('out::', '')} — {choice}")
        y -= 32
    pdf.showPage()
    pdf.save()
    return out.getvalue()
