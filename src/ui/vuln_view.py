"""
Mapa de fragilidades (rodada 7): no lugar das bolinhas, o campo do rival com as zonas frágeis pintadas e cartões
com gravidade, evidência e como explorar. Usa `src/analytics/vulnerabilities.py` (achados com número e amostra).
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import plotly.graph_objects as go
import streamlit as st


@st.cache_data(show_spinner=False, ttl=1800, max_entries=32)
def _findings(names: tuple, our: tuple, version: str) -> Dict[str, Any]:
    from src.analytics.vulnerabilities import team_vulnerabilities
    from src.squad import data as D
    from src.ui.context import get_service

    try:
        h = D.table("tm_jogadores", ["nome", "altura_cm"])
    except Exception:
        h = None
    svc = get_service()
    r = team_vulnerabilities(svc.db, list(names), 12, list(our) if our else None, h)
    if r.get("jogos", 0) < 5 and svc.fotmob.enabled:          # poucos jogos com números por jogador: busca na FotMob agora
        try:
            for nm in (names, our or ()):
                if nm:
                    svc.fotmob.ensure_teams(list(nm), n=12)
            r = team_vulnerabilities(svc.db, list(names), 12, list(our) if our else None, h)
        except Exception:
            pass
    return r


def _zone(f: Dict[str, Any]):
    """Retângulo no campo EM PÉ (nós atacando para cima; o rival defende em cima). Lado do RIVAL → espelhado."""
    y = {"defesa": (84, 120), "gol": (100, 120), "meio": (48, 84), "ataque": (12, 48)}.get(f.get("setor") or "", (60, 120))
    side = f.get("lado")
    x = {"esquerda": (53.3, 80), "direita": (0, 26.7)}.get(side or "", (14, 66))     # esquerda DELE = nossa direita
    return x, y


def pitch_figure(found: List[Dict[str, Any]], title: str) -> go.Figure:
    from src.ui import charts

    fig = charts.pitch_vertical(title=title, height=560)
    seen: Dict[tuple, int] = {}
    for i, f in enumerate(found[:8], 1):
        (x0, x1), (y0, y1) = _zone(f)
        a = 0.10 + 0.25 * f["gravidade"] / 100
        fig.add_shape(type="rect", x0=x0 + 0.6, x1=x1 - 0.6, y0=y0 + 0.6, y1=y1 - 0.6, line=dict(color="#EF4444", width=1.5),
                      fillcolor=f"rgba(239,68,68,{a:.2f})", layer="above")
        key = (x0, y0)
        k = seen.get(key, 0)
        seen[key] = k + 1
        # vários achados na mesma zona: números lado a lado, sem se sobrepor
        cx = min(max(x0 + 6 + k * 7 % max(x1 - x0 - 10, 7), x0 + 4), x1 - 4)
        cy = y1 - 7 - (k * 7 // max(x1 - x0 - 10, 7)) * 8
        fig.add_trace(go.Scatter(x=[cx], y=[cy], mode="markers+text", text=[str(i)], showlegend=False,
                                 marker=dict(size=26, color="#EF4444", line=dict(color="#FFFFFF", width=2)),
                                 textfont=dict(color="#FFFFFF", size=12), hovertext=[f"{f['titulo']}<br>{f['evidencia']}"],
                                 hoverinfo="text"))
    fig.add_annotation(x=40, y=-2, text="↑ nosso ataque", showarrow=False, font=dict(color="#94A3B8", size=11))
    return fig


# rodada 10: cada fragilidade lida como analista — o que significa (interpretação) e o que só vídeo confirma (hipótese)
READING = [
    ("driblado", "o 1x1 contra ele tende a sair a favor de quem ataca; o lado dele vira corredor de ataque",
     "se o problema é velocidade, abordagem ou cobertura do companheiro só o vídeo mostra (tracking não é aberto)"),
    ("desarma pouco", "deixa a bola chegar e não interrompe a jogada: conduzir para cima dele rende",
     "pode ser escolha da função (contenção) e não deficiência — confirmar com o papel tático no vídeo"),
    ("aéreo", "bola alta na área dele é disputa vantajosa para nós",
     "posicionamento e impulsão não são medidos; os números dizem só o resultado das disputas"),
    ("duelos", "perde no corpo a corpo: aproximar dois jogadores no setor dele",
     "duelos misturam chão e alto; a direção da jogada não é registrada nesta fonte"),
    ("não defende", "o lado dele fica exposto na transição: o nosso lateral daquele corredor pode subir",
     "pode ser instrução do técnico (guardar posição para o contra-ataque) — ver no vídeo"),
    ("saída de bola", "pressão alta nele tende a forçar erro ou chutão",
     "a pressão sofrida é inferida pelos números de passe/perda, sem tracking"),
    ("contra-ataque", "a linha fica alta e sem cobertura depois da perda",
     "a altura da linha é inferida pelos chutes cedidos em contra-ataque, não por posições medidas"),
    ("chutar de fora", "o volante não encurta a entrada da área",
     "chute de fora também depende do nosso time querer arriscar"),
    ("lado", "o corredor concentra o perigo cedido: carregar o ataque por ali",
     "pode refletir o estilo dos adversários enfrentados, não só a defesa deles"),
    ("cruzamentos", "cede o cruzamento com facilidade: atacar pelos lados e o segundo pau",
     "a qualidade de quem cruzou contra eles muda o peso do número"),
    ("zagueiro baixo", "desvantagem física na bola alta contra o nosso atacante",
     "altura do cadastro; impulsão e tempo de bola não são medidos"),
]


def _reading(title: str):
    t = (title or "").lower()
    return next(((i, h) for k, i, h in READING if k in t), (None, None))


def cards_html(found: List[Dict[str, Any]], color: str = "#EF4444") -> str:
    out = []
    for i, f in enumerate(found[:8], 1):
        g = f["gravidade"]
        interp, hyp = _reading(f.get("titulo"))
        bar = f'<div style="height:6px;background:#1E2A44;border-radius:4px;margin:6px 0"><div style="width:{g}%;height:6px;' \
              f'border-radius:4px;background:linear-gradient(90deg,#F59E0B,{color})"></div></div>'
        out.append(
            f'<div style="background:#0F1626;border:1px solid #1E2A44;border-left:5px solid {color};border-radius:14px;'
            f'padding:10px 14px;margin-bottom:8px"><div style="display:flex;justify-content:space-between;gap:10px">'
            f'<b style="font-size:1rem;color:#F5F7FB"><span style="background:{color};color:#fff;border-radius:999px;padding:0 8px;'
            f'margin-right:8px">{i}</span>{f["titulo"]}</b><span style="color:#94A3B8;font-size:.8rem">gravidade {g}</span></div>'
            f'{bar}<div style="color:#E2E8F0;font-size:.9rem">📌 <b>Fato:</b> {f["evidencia"]}</div>'
            f'<div style="color:#BAE6FD;font-size:.86rem;margin-top:3px">🔁 <b>Padrão:</b> visto nos {f["base"]}</div>'
            + (f'<div style="color:#FDE68A;font-size:.86rem;margin-top:3px">💡 <b>Interpretação:</b> {interp}</div>'
               if interp else "")
            + f'<div style="color:#A7F3D0;font-size:.88rem;margin-top:4px">🎯 <b>Como explorar:</b> {f["explorar"]}</div>'
            + (f'<div style="color:#C4B5FD;font-size:.8rem;margin-top:3px">🔍 <b>Hipótese a confirmar:</b> {hyp}</div>'
               if hyp else "") + '</div>')
    return "".join(out)


def render(rival: str, rival_names: Sequence[str], our_names: Sequence[str], version: str, mine: bool = False,
           where: str = "") -> None:
    with st.spinner(f"Procurando fragilidades de {rival} nos últimos jogos..."):
        r = _findings(tuple(rival_names), tuple(our_names or ()), version)
    found = r.get("achados") or []
    title = f"🛡️ Onde {rival} sofre (nossos pontos a corrigir)" if mine else f"🎯 Onde atacar {rival}"
    st.markdown(f"### {title}")
    if not found:
        st.caption(f"Nenhuma fragilidade clara nos últimos {r.get('jogos', 0)} jogos com números por jogador "
                   f"({r.get('jogadores_avaliados', 0)} jogadores avaliados) — nada fugiu da referência com amostra suficiente.")
        return
    st.caption(f"Base: últimos {r['jogos']} jogos com números por jogador · {r['jogadores_avaliados']} jogadores avaliados contra "
               "jogadores da mesma função; só entra o que foge da referência com amostra mínima.")
    a, b = st.columns([1, 1.25])
    with a:
        st.plotly_chart(pitch_figure(found, f"Zonas frágeis de {rival}"), use_container_width=True,
                        key=f"vuln_pitch_{where}_{rival}_{mine}")   # a mesma tela aparece em 2 abas
    with b:
        st.markdown(cards_html(found, "#F59E0B" if mine else "#EF4444"), unsafe_allow_html=True)
