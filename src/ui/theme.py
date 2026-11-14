"""
Tema visual único (dark mode) do Tactical Intelligence Lab.

A paleta é definida SÓ aqui (PALETTE) e usada pelo CSS, pelos componentes e pelo template
dos gráficos Plotly (PLOTLY_LAYOUT). Contraste dos textos sobre o fundo ≥ 4,5:1 (WCAG AA).
"""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "bg": "#05070D",           # fundo (preto azulado)
    "surface": "#0B1120",      # cartões
    "surface_2": "#111A2E",    # cartões elevados / barras
    "border": "#1E2A44",
    "text": "#F5F7FB",         # branco (contraste 18:1)
    "muted": "#98A6BF",        # cinza azulado (contraste 7,9:1)
    "primary": "#3B82F6",      # azul — equipe em foco
    "secondary": "#EF4444",    # vermelho — adversário / destaque
    "accent": "#22D3EE",       # ciano — detalhes tecnológicos
    "danger": "#F87171",
    "warning": "#FBBF24",
    "success": "#22C55E",
    "violet": "#A78BFA",
    "pitch": "#0A1A14",
    "pitch_line": "#2C4A3C",
}

TIER_COLORS = {"OFFICIAL": PALETTE["primary"], "DERIVED": PALETTE["accent"], "SIMULATED": PALETTE["warning"]}
TIER_LABELS = {"OFFICIAL": "OFICIAL", "DERIVED": "DERIVADO", "SIMULATED": "SIMULADO"}

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(11,17,32,0.0)",
    plot_bgcolor="rgba(11,17,32,0.55)",
    font=dict(color=PALETTE["text"], family="Inter, Segoe UI, sans-serif", size=13),
    colorway=[PALETTE["primary"], PALETTE["secondary"], PALETTE["accent"], PALETTE["warning"], PALETTE["violet"], "#F472B6"],
    margin=dict(l=30, r=20, t=50, b=35),
    legend=dict(orientation="h", y=-0.15),
)

P = PALETTE
GRAD = f"linear-gradient(135deg, {P['secondary']} 0%, #7C3AED 50%, {P['primary']} 100%)"
CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<style>
:root {{ --til-grad: {GRAD}; }}
html, body, .stApp {{ font-family: Inter, 'Segoe UI', sans-serif; }}
.stApp {{ color: {P['text']};
  background: radial-gradient(1200px 600px at 10% -10%, rgba(59,130,246,0.16), transparent 60%),
              radial-gradient(900px 500px at 100% 0%, rgba(239,68,68,0.13), transparent 55%),
              linear-gradient(180deg, #05070D 0%, #060912 100%); background-attachment: fixed; }}
h1, h2, h3, h4, h5 {{ color: {P['text']}; font-family: 'Space Grotesk', Inter, sans-serif; letter-spacing: -0.01em; }}
h4, h5 {{ margin-top: 0.6rem; }}
a {{ color: {P['accent']}; }}
/* sem barra lateral: navegação no topo */
section[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}
.block-container {{ padding-top: 4.2rem; max-width: 1380px; }}
header[data-testid="stHeader"] {{ background: rgba(5,7,13,0.82); backdrop-filter: blur(14px);
  border-bottom: 1px solid {P['border']}; }}
header[data-testid="stHeader"] a, header[data-testid="stHeader"] [role="button"] {{ border-radius: 999px !important; }}
header[data-testid="stHeader"] a[aria-current="page"], header[data-testid="stHeader"] a[data-active="true"] {{
  background: rgba(59,130,246,0.18) !important; box-shadow: inset 0 0 0 1px rgba(59,130,246,0.55); }}

/* abas e seletores em pílula */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; background: rgba(17,26,46,0.6); padding: 6px; border-radius: 999px;
  border: 1px solid {P['border']}; width: fit-content; }}
.stTabs [data-baseweb="tab"] {{ border-radius: 999px; padding: 6px 16px; color: {P['muted']}; height: auto; }}
.stTabs [aria-selected="true"] {{ background: var(--til-grad); color: white !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
div[role="radiogroup"] {{ gap: 6px; flex-wrap: wrap; }}
div[role="radiogroup"] > label {{ background: {P['surface_2']}; border: 1px solid {P['border']}; border-radius: 999px;
  padding: 4px 14px !important; margin: 0 !important; }}
div[role="radiogroup"] > label:has(input:checked) {{ background: rgba(59,130,246,0.18); border-color: {P['primary']}; }}

/* botões e campos */
.stButton > button, .stDownloadButton > button, [data-testid="stPopover"] button {{ border-radius: 12px;
  border: 1px solid {P['border']}; background: {P['surface_2']}; color: {P['text']}; font-weight: 700;
  transition: all .15s ease; }}
.stButton > button:hover, [data-testid="stPopover"] button:hover {{ border-color: {P['accent']};
  box-shadow: 0 0 0 1px {P['accent']}, 0 0 18px rgba(34,211,238,0.25); }}
.stButton > button[kind="primary"] {{ background: var(--til-grad); border: none; color: white; }}
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div {{
  background: {P['surface']} !important; border-radius: 12px !important; border-color: {P['border']} !important; }}
.stTextInput input:focus {{ box-shadow: 0 0 0 2px rgba(59,130,246,0.45) !important; }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{ border-radius: 14px; overflow: hidden; border: 1px solid {P['border']}; }}
[data-testid="stExpander"] {{ border-radius: 14px; border: 1px solid {P['border']}; background: rgba(11,17,32,0.6); }}
[data-testid="stPlotlyChart"] {{ border-radius: 16px; overflow: hidden; border: 1px solid {P['border']};
  background: rgba(11,17,32,0.55); }}
[data-testid="stAlert"] {{ border-radius: 14px; }}

/* chat */
[data-testid="stChatMessage"] {{ background: rgba(17,26,46,0.65); border: 1px solid {P['border']}; border-radius: 18px;
  padding: 12px 16px; backdrop-filter: blur(6px); }}
[data-testid="stChatInput"] {{ border-radius: 20px; }}
[data-testid="stChatInput"] textarea {{ font-size: 1rem; }}
[data-testid="stBottom"] > div {{ background: linear-gradient(180deg, rgba(5,7,13,0) 0%, rgba(5,7,13,0.95) 40%); }}

/* hero e faixa da partida */
.til-hero {{ border-radius: 22px; padding: 22px 26px; margin: 4px 0 16px 0; position: relative; overflow: hidden;
  background: linear-gradient(135deg, rgba(239,68,68,0.16), rgba(124,58,237,0.10) 45%, rgba(59,130,246,0.18));
  border: 1px solid rgba(148,163,184,0.18); }}
.til-hero .k {{ font-family: 'Space Grotesk', sans-serif; font-size: 0.78rem; letter-spacing: .18em; color: {P['accent']};
  text-transform: uppercase; font-weight: 700; }}
.til-hero .t {{ font-family: 'Space Grotesk', sans-serif; font-size: 2.0rem; font-weight: 700; margin: 4px 0; }}
.til-hero .s {{ color: {P['muted']}; font-size: 0.98rem; max-width: 820px; }}
.til-strip {{ display: flex; align-items: center; gap: 14px; padding: 10px 16px; border-radius: 16px;
  background: rgba(11,17,32,0.75); border: 1px solid {P['border']}; }}
.til-strip .tm {{ display: flex; align-items: center; gap: 8px; font-weight: 800; font-size: 1.02rem; }}
.til-strip .sc {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.35rem; font-weight: 700; padding: 2px 12px;
  border-radius: 10px; background: {P['surface_2']}; border: 1px solid {P['border']}; }}
.til-strip .meta {{ color: {P['muted']}; font-size: 0.8rem; margin-left: auto; text-align: right; }}
.til-crest {{ width: 30px; height: 30px; object-fit: contain; border-radius: 6px; vertical-align: middle;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,.6)); }}
.til-crest.lg {{ width: 64px; height: 64px; }}
.til-crest.md {{ width: 42px; height: 42px; }}
.til-result {{ display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 16px; margin-bottom: 8px;
  background: rgba(11,17,32,0.7); border: 1px solid {P['border']}; }}
.til-result:hover {{ border-color: rgba(34,211,238,0.6); }}
.til-result .tm {{ flex: 1; display: flex; align-items: center; gap: 8px; font-weight: 700; }}
.til-result .tm.r {{ justify-content: flex-end; text-align: right; }}
.til-result .sc {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.2rem; min-width: 64px; text-align: center; }}
.til-result .meta {{ color: {P['muted']}; font-size: 0.75rem; }}
.til-form span {{ display: inline-block; width: 22px; height: 22px; line-height: 22px; text-align: center; border-radius: 6px;
  font-size: 0.72rem; font-weight: 800; margin-right: 3px; }}
.til-form .V {{ background: rgba(34,197,94,.2); color: {P['success']}; }} .til-form .E {{ background: rgba(148,163,184,.2); color: {P['muted']}; }}
.til-form .D {{ background: rgba(239,68,68,.2); color: {P['secondary']}; }}
.til-profile {{ display: flex; gap: 18px; align-items: center; padding: 18px 20px; border-radius: 20px; margin-bottom: 14px;
  background: linear-gradient(135deg, rgba(59,130,246,0.14), rgba(239,68,68,0.10)); border: 1px solid rgba(148,163,184,0.18); }}
.til-profile .n {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.7rem; font-weight: 700; }}
.til-profile .d {{ color: {P['muted']}; font-size: 0.9rem; }}
.til-glow {{ height: 2px; background: var(--til-grad); border-radius: 2px; margin: 6px 0 14px 0; opacity: .8; }}

/* cabeçalho de contexto da página */
.til-header {{ background: rgba(11,17,32,0.7); border: 1px solid {P['border']}; border-radius: 18px; padding: 14px 18px; margin: 0 0 16px 0;
  position: relative; overflow: hidden; }}
.til-header::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--til-grad); }}
.til-header .title {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.5rem; font-weight: 700; color: {P['text']}; }}
.til-header .sub {{ color: {P['muted']}; font-size: 0.9rem; margin-top: 2px; }}
.til-header .ctx {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
.til-chip {{ display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: 0.76rem; font-weight: 700;
  border: 1px solid {P['border']}; color: {P['text']}; background: rgba(17,26,46,0.9); }}
.til-chip.tier {{ border-width: 1.5px; }}

/* cartões de métrica */
.til-card {{ background: linear-gradient(180deg, rgba(17,26,46,0.85), rgba(11,17,32,0.85)); border: 1px solid {P['border']};
  border-radius: 18px; padding: 14px 16px; margin-bottom: 12px; min-height: 118px; position: relative; overflow: hidden; }}
.til-card::after {{ content: ""; position: absolute; left: 16px; right: 16px; top: 0; height: 2px; background: var(--til-grad); opacity: .55; }}
.til-card .label {{ color: {P['muted']}; font-size: 0.72rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; }}
.til-card .value {{ font-family: 'Space Grotesk', sans-serif; color: {P['text']}; font-size: 1.9rem; font-weight: 700; line-height: 1.15; margin: 4px 0; }}
.til-card .unit {{ color: {P['muted']}; font-size: 0.85rem; font-weight: 600; margin-left: 4px; }}
.til-card .badge {{ display: inline-block; font-size: 0.72rem; font-weight: 800; padding: 2px 8px; border-radius: 999px; }}
.til-card .badge.pos {{ color: {P['success']}; background: rgba(34,197,94,0.12); }}
.til-card .badge.neg {{ color: {P['secondary']}; background: rgba(239,68,68,0.14); }}
.til-card .badge.neu {{ color: {P['accent']}; background: rgba(34,211,238,0.12); }}
.til-prov {{ margin-top: 8px; font-size: 0.68rem; color: {P['muted']}; border-top: 1px dashed {P['border']}; padding-top: 6px; }}
.til-prov b {{ font-weight: 800; }}
.til-prov.missing {{ color: {P['danger']}; }}
.til-sim {{ margin-top: 6px; font-size: 0.72rem; color: {P['warning']}; font-weight: 700; }}

/* barras comparativas */
.til-pill {{ margin: 0 0 12px 0; padding: 10px 12px; border-radius: 14px; background: rgba(11,17,32,0.6); border: 1px solid {P['border']}; }}
.til-pill .head {{ display: flex; justify-content: space-between; font-size: 0.86rem; font-weight: 800; margin-bottom: 6px; }}
.til-pill .head .l {{ color: {P['primary']}; }} .til-pill .head .r {{ color: {P['secondary']}; }}
.til-pill .head .t {{ color: {P['muted']}; font-weight: 600; }}
.til-pill .track {{ display: flex; height: 8px; border-radius: 999px; overflow: hidden; background: {P['surface_2']}; gap: 3px; }}
.til-pill .fl {{ background: linear-gradient(90deg, #1D4ED8, {P['primary']}); border-radius: 999px; }}
.til-pill .fr {{ background: linear-gradient(90deg, {P['secondary']}, #B91C1C); border-radius: 999px; }}
.til-pill .src {{ font-size: 0.66rem; color: {P['muted']}; margin-top: 4px; }}

/* placar */
.til-score {{ border-radius: 22px; padding: 20px; text-align: center; margin-bottom: 14px;
  background: linear-gradient(135deg, rgba(59,130,246,0.16), rgba(5,7,13,0.6) 50%, rgba(239,68,68,0.16));
  border: 1px solid rgba(148,163,184,0.18); }}
.til-score .row {{ display: flex; align-items: center; justify-content: center; gap: 22px; }}
.til-score .team {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.45rem; font-weight: 700; color: {P['text']}; min-width: 220px;
  display: flex; align-items: center; gap: 10px; }}
.til-score .team:first-child {{ justify-content: flex-end; }}
.til-score .box {{ font-family: 'Space Grotesk', sans-serif; font-size: 2.6rem; font-weight: 700; color: {P['text']};
  background: rgba(5,7,13,0.75); border: 1px solid {P['border']}; border-radius: 14px; padding: 2px 20px; }}
.til-score .grow {{ display: flex; justify-content: center; gap: 22px; margin-top: 12px; }}
.til-score .gcol {{ min-width: 220px; flex: 1; max-width: 360px; }}
.til-score .gsep {{ width: 110px; }}
.til-score .goals {{ color: {P['muted']}; font-size: 0.86rem; line-height: 1.6; }}
.til-score .pen {{ margin-top: 8px; color: {P['warning']}; font-weight: 800; font-size: 0.9rem; }}
.til-score .meta {{ margin-top: 10px; color: {P['muted']}; font-size: 0.84rem; }}

/* faixa do nível de dado */
.til-level {{ border-radius: 14px; padding: 9px 16px; margin: 0 0 14px 0; background: rgba(11,17,32,0.7); border: 1px solid {P['border']}; }}
.til-level .t {{ font-weight: 800; font-size: 0.9rem; }}
.til-level .d {{ color: {P['muted']}; font-size: 0.8rem; margin-top: 2px; }}

/* estados vazios e de erro */
.til-empty {{ border: 1px dashed {P['border']}; border-radius: 18px; padding: 26px; text-align: center; background: rgba(11,17,32,0.6); margin: 10px 0 16px 0; }}
.til-empty .i {{ font-size: 2rem; }}
.til-empty .t {{ font-weight: 800; font-size: 1.05rem; color: {P['text']}; margin-top: 6px; }}
.til-empty .m {{ color: {P['muted']}; font-size: 0.9rem; margin-top: 4px; }}
.til-empty .h {{ color: {P['accent']}; font-size: 0.85rem; margin-top: 8px; }}
.til-empty.error {{ border-color: {P['danger']}; }}

/* notas */
.til-note {{ background: rgba(11,17,32,0.7); border: 1px solid {P['border']}; border-left: 4px solid {P['primary']};
  border-radius: 14px; padding: 12px 14px; margin-bottom: 10px; font-size: 0.9rem; }}
.til-note.alert {{ border-left-color: {P['secondary']}; }}
.til-note.warn {{ border-left-color: {P['warning']}; }}
.til-note .h {{ font-weight: 800; margin-bottom: 4px; }}

.til-match-card {{ background: rgba(11,17,32,0.7); border: 1px solid {P['border']}; border-radius: 14px; padding: 12px 14px; margin: 8px 0; }}
.til-match-card .teams {{ font-weight: 800; color: {P['text']}; font-size: 0.98rem; }}
.til-match-card .meta {{ color: {P['muted']}; font-size: 0.78rem; margin-top: 3px; }}

.til-kpi {{ background: rgba(11,17,32,0.75); border: 1px solid {P['border']}; border-radius: 16px; padding: 14px; text-align: center; }}
.til-kpi .v {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.6rem; font-weight: 700; color: {P['text']}; }}
.til-kpi .l {{ font-size: 0.72rem; color: {P['muted']}; text-transform: uppercase; letter-spacing: 0.07em; }}

.til-depth {{ background: rgba(11,17,32,0.7); border: 1px solid {P['border']}; border-radius: 16px; padding: 12px; min-height: 230px; }}
.til-depth .h {{ color: {P['accent']}; font-weight: 800; font-size: 0.8rem; text-transform: uppercase; margin-bottom: 8px; }}
.til-depth .m {{ color: {P['muted']}; font-size: 0.78rem; }}
.til-step {{ display: flex; gap: 14px; padding: 14px 16px; border-radius: 16px; background: rgba(11,17,32,0.7);
  border: 1px solid {P['border']}; margin-bottom: 10px; }}
.til-step .n {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.4rem; font-weight: 700; min-width: 42px; height: 42px;
  border-radius: 12px; display: flex; align-items: center; justify-content: center; background: var(--til-grad); color: white; }}
.til-step .t {{ font-weight: 800; font-size: 1.02rem; }} .til-step .b {{ color: {P['muted']}; font-size: 0.92rem; margin-top: 3px; }}
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
