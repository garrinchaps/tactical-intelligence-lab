"""
Tema visual único (dark mode) do Tactical Intelligence Lab.

A paleta é definida SÓ aqui (PALETTE) e usada pelo CSS, pelos componentes e pelo template
dos gráficos Plotly (PLOTLY_LAYOUT). Contraste dos textos sobre o fundo ≥ 4,5:1 (WCAG AA).
"""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "bg": "#0E1117",           # fundo da aplicação
    "surface": "#161B22",      # cartões
    "surface_2": "#1C2230",    # cartões elevados / barras
    "border": "#2A3241",
    "text": "#F1F5F9",         # contraste 16,8:1 sobre bg
    "muted": "#A3B1C6",        # contraste 8,4:1 sobre bg
    "primary": "#22C55E",      # equipe em foco / positivo
    "secondary": "#38BDF8",    # adversário / informação
    "danger": "#F87171",       # alerta / negativo
    "warning": "#FBBF24",      # simulado / atenção
    "violet": "#A78BFA",       # nível "só placar" / derivados
    "pitch": "#13261A",        # gramado dos gráficos de campo
    "pitch_line": "#3F5A46",
}

TIER_COLORS = {"OFFICIAL": PALETTE["primary"], "DERIVED": PALETTE["secondary"], "SIMULATED": PALETTE["warning"]}
TIER_LABELS = {"OFFICIAL": "OFICIAL", "DERIVED": "DERIVADO", "SIMULATED": "SIMULADO"}

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=PALETTE["surface"],
    plot_bgcolor=PALETTE["surface"],
    font=dict(color=PALETTE["text"], family="Inter, Segoe UI, sans-serif", size=13),
    margin=dict(l=30, r=20, t=50, b=35),
    legend=dict(orientation="h", y=-0.15),
)

P = PALETTE
CSS = f"""
<style>
.stApp {{ background-color: {P['bg']}; color: {P['text']}; }}
section[data-testid="stSidebar"] {{ background-color: #0A0D12; border-right: 1px solid {P['border']}; }}
h1, h2, h3, h4, h5 {{ color: {P['text']}; }}

/* cabeçalho de contexto da página */
.til-header {{ background: {P['surface']}; border: 1px solid {P['border']}; border-radius: 12px;
              padding: 14px 18px; margin: 0 0 16px 0; }}
.til-header .title {{ font-size: 1.45rem; font-weight: 900; color: {P['text']}; }}
.til-header .sub {{ color: {P['muted']}; font-size: 0.9rem; margin-top: 2px; }}
.til-header .ctx {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
.til-chip {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.78rem; font-weight: 700;
            border: 1px solid {P['border']}; color: {P['text']}; background: {P['surface_2']}; }}
.til-chip.tier {{ border-width: 1.5px; }}

/* cartões de métrica */
.til-card {{ background: {P['surface']}; border: 1px solid {P['border']}; border-radius: 12px;
            padding: 14px 16px; margin-bottom: 12px; min-height: 118px; }}
.til-card .label {{ color: {P['muted']}; font-size: 0.74rem; font-weight: 800; text-transform: uppercase;
                   letter-spacing: 0.05em; }}
.til-card .value {{ color: {P['text']}; font-size: 1.85rem; font-weight: 900; line-height: 1.15; margin: 4px 0; }}
.til-card .unit {{ color: {P['muted']}; font-size: 0.85rem; font-weight: 600; margin-left: 4px; }}
.til-card .badge {{ display: inline-block; font-size: 0.74rem; font-weight: 800; padding: 2px 8px; border-radius: 6px; }}
.til-card .badge.pos {{ color: {P['primary']}; background: rgba(34,197,94,0.12); }}
.til-card .badge.neg {{ color: {P['danger']}; background: rgba(248,113,113,0.12); }}
.til-card .badge.neu {{ color: {P['secondary']}; background: rgba(56,189,248,0.12); }}
.til-prov {{ margin-top: 8px; font-size: 0.7rem; color: {P['muted']}; border-top: 1px dashed {P['border']}; padding-top: 6px; }}
.til-prov b {{ font-weight: 800; }}
.til-prov.missing {{ color: {P['danger']}; }}
.til-sim {{ margin-top: 6px; font-size: 0.72rem; color: {P['warning']}; font-weight: 700; }}

/* barras comparativas */
.til-pill {{ margin: 0 0 12px 0; }}
.til-pill .head {{ display: flex; justify-content: space-between; font-size: 0.86rem; font-weight: 800; margin-bottom: 4px; }}
.til-pill .head .l {{ color: {P['primary']}; }} .til-pill .head .r {{ color: {P['secondary']}; }}
.til-pill .head .t {{ color: {P['muted']}; font-weight: 600; }}
.til-pill .track {{ display: flex; height: 9px; border-radius: 6px; overflow: hidden; background: {P['surface_2']}; }}
.til-pill .fl {{ background: {P['primary']}; }} .til-pill .fr {{ background: {P['secondary']}; }}
.til-pill .src {{ font-size: 0.68rem; color: {P['muted']}; margin-top: 3px; }}

/* placar */
.til-score {{ background: {P['surface']}; border: 1px solid {P['border']}; border-radius: 14px; padding: 18px;
             text-align: center; margin-bottom: 14px; }}
.til-score .row {{ display: flex; align-items: center; justify-content: center; gap: 22px; }}
.til-score .team {{ font-size: 1.35rem; font-weight: 900; color: {P['text']}; min-width: 220px; }}
.til-score .box {{ font-size: 2.3rem; font-weight: 900; color: {P['text']}; background: {P['surface_2']};
                  border-radius: 10px; padding: 4px 18px; }}
.til-score .grow {{ display: flex; justify-content: center; gap: 22px; margin-top: 10px; }}
.til-score .gcol {{ min-width: 220px; flex: 1; max-width: 360px; }}
.til-score .gsep {{ width: 90px; }}
.til-score .goals {{ color: {P['muted']}; font-size: 0.86rem; line-height: 1.55; }}
.til-score .pen {{ margin-top: 8px; color: {P['warning']}; font-weight: 800; font-size: 0.9rem; }}
.til-score .meta {{ margin-top: 8px; color: {P['muted']}; font-size: 0.86rem; }}

/* faixa do nível de dado */
.til-level {{ border-radius: 10px; padding: 10px 16px; margin: 0 0 14px 0; background: {P['surface']};
             border: 1px solid {P['border']}; }}
.til-level .t {{ font-weight: 900; font-size: 0.95rem; }}
.til-level .d {{ color: {P['muted']}; font-size: 0.84rem; margin-top: 3px; }}

/* estados vazios e de erro */
.til-empty {{ border: 1px dashed {P['border']}; border-radius: 12px; padding: 26px; text-align: center;
             background: {P['surface']}; margin: 10px 0 16px 0; }}
.til-empty .i {{ font-size: 2rem; }}
.til-empty .t {{ font-weight: 900; font-size: 1.05rem; color: {P['text']}; margin-top: 6px; }}
.til-empty .m {{ color: {P['muted']}; font-size: 0.9rem; margin-top: 4px; }}
.til-empty .h {{ color: {P['secondary']}; font-size: 0.85rem; margin-top: 8px; }}
.til-empty.error {{ border-color: {P['danger']}; }}

/* cartões de texto (diagnósticos, alertas) */
.til-note {{ background: {P['surface']}; border: 1px solid {P['border']}; border-left: 4px solid {P['primary']};
            border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; font-size: 0.9rem; }}
.til-note.alert {{ border-left-color: {P['danger']}; }}
.til-note.warn {{ border-left-color: {P['warning']}; }}
.til-note .h {{ font-weight: 800; margin-bottom: 4px; }}

/* cartão da partida na barra lateral */
.til-match-card {{ background: {P['surface']}; border: 1px solid {P['border']}; border-radius: 12px; padding: 12px 14px; margin: 8px 0; }}
.til-match-card .teams {{ font-weight: 800; color: {P['text']}; font-size: 0.98rem; }}
.til-match-card .meta {{ color: {P['muted']}; font-size: 0.78rem; margin-top: 3px; }}

/* KPI simples */
.til-kpi {{ background: {P['surface']}; border: 1px solid {P['border']}; border-radius: 12px; padding: 14px; text-align: center; }}
.til-kpi .v {{ font-size: 1.6rem; font-weight: 900; color: {P['text']}; }}
.til-kpi .l {{ font-size: 0.74rem; color: {P['muted']}; text-transform: uppercase; letter-spacing: 0.05em; }}

/* slots da matriz de profundidade */
.til-depth {{ background: {P['surface']}; border: 1px solid {P['border']}; border-radius: 10px; padding: 12px; min-height: 230px; }}
.til-depth .r {{ color: {P['secondary']}; font-weight: 900; font-size: 0.8rem; text-transform: uppercase; margin-bottom: 8px; }}
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
