"""
Tema visual único (dark mode) do Tactical Intelligence Lab.

A paleta é definida SÓ aqui (PALETTE) e usada pelo CSS, pelos componentes e pelo template
dos gráficos Plotly (PLOTLY_LAYOUT). Contraste dos textos sobre o fundo ≥ 4,5:1 (WCAG AA).
"""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "bg": "#090D16",           # fundo (preto azulado)
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
    "pitch": "#0B2318",
    "pitch_line": "#4E7A63",
}

TIER_COLORS = {"OFFICIAL": PALETTE["primary"], "DERIVED": PALETTE["accent"], "SIMULATED": PALETTE["warning"]}
TIER_LABELS = {"OFFICIAL": "OFICIAL", "DERIVED": "DERIVADO", "SIMULATED": "SIMULADO"}

PLOTLY_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(11,17,32,0.0)",
    plot_bgcolor="rgba(11,17,32,0.55)",
    font=dict(color=PALETTE["text"], family="Inter, Segoe UI, sans-serif", size=13),
    colorway=["#60A5FA", "#FB7185", "#34D399", "#FBBF24", "#C4B5FD", "#F472B6"],
    margin=dict(l=30, r=20, t=50, b=35),
    legend=dict(orientation="h", y=-0.15, font=dict(size=12)),
    hoverlabel=dict(bgcolor="#111A2E", bordercolor="#22D3EE", font=dict(color=PALETTE["text"], size=13)),
)

P = PALETTE
GRAD = f"linear-gradient(135deg, {P['secondary']} 0%, #7C3AED 50%, {P['primary']} 100%)"
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Space+Grotesk:wght@500;700&display=swap');
:root {{ --til-grad: {GRAD}; }}
html, body, .stApp {{ font-family: Inter, 'Segoe UI', sans-serif; }}
.stApp {{ color: {P['text']};
  background: radial-gradient(1200px 600px at 10% -10%, rgba(59,130,246,0.16), transparent 60%),
              radial-gradient(900px 500px at 100% 0%, rgba(239,68,68,0.13), transparent 55%),
              linear-gradient(180deg, #090D16 0%, #070A12 100%); background-attachment: fixed; }}
h1, h2, h3, h4, h5 {{ color: {P['text']}; font-family: 'Space Grotesk', Inter, sans-serif; letter-spacing: -0.01em; }}
h4, h5 {{ margin-top: 0.6rem; }}
a {{ color: {P['accent']}; }}
/* rodada 20: gráficos sem botão de tela cheia/zoom flutuante (no celular aparecia a cada toque) */
[data-testid="stElementContainer"]:has(.stPlotlyChart) [data-testid="stElementToolbar"]{{display:none !important}}
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
.stButton button, .stDownloadButton button, [data-testid="stPopover"] button, [data-testid="stBaseButton-secondary"] {{ border-radius: 12px;
  border: 1px solid {P['border']}; background: {P['surface_2']}; color: {P['text']}; font-weight: 700;
  transition: all .15s ease; }}
.stButton button:hover, [data-testid="stPopover"] button:hover, [data-testid="stBaseButton-secondary"]:hover {{ border-color: {P['accent']}; color: {P['accent']};
  box-shadow: 0 0 15px rgba(34,211,238,0.3); }}
[data-testid="stPageLink"] a {{ border-radius: 999px; padding: 4px 12px; border: 1px solid transparent; transition: all .15s ease; }}
[data-testid="stPageLink"] a:hover {{ border-color: {P['accent']}; box-shadow: 0 0 12px rgba(34,211,238,0.25); }}
.fm-card {{ background: linear-gradient(135deg, rgba(18,23,32,0.95), rgba(13,17,23,0.98)); border: 1px solid {P['border']};
  border-radius: 16px; padding: 18px; margin-bottom: 14px; box-shadow: 0 4px 20px rgba(0,0,0,0.6); }}
.fm-card-blue {{ border-left: 4px solid {P['accent']}; }} .fm-card-red {{ border-left: 4px solid {P['secondary']}; }}
.fm-card .h {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.05rem; margin-bottom: 6px; }}
.fm-card ul {{ margin: 0; padding-left: 1.1rem; }} .fm-card li {{ margin: 3px 0; color: {P['text']}; }}
[data-testid="stMetricValue"] {{ font-family: 'Space Grotesk', sans-serif; }}
[data-testid="stMetric"] {{ background: linear-gradient(135deg, rgba(18,23,32,0.95), rgba(13,17,23,0.98)); border: 1px solid {P['border']};
  border-radius: 16px; padding: 12px 14px; position: relative; overflow: hidden; }}
/* rodada 22: faixa de destaque no topo dos indicadores (estilo painel) */
[data-testid="stMetric"]::before {{ content: ""; position: absolute; left: 0; top: 0; right: 0; height: 3px; background: var(--til-grad); opacity: .85; }}
[data-testid="stMetricLabel"] {{ color: #94A3B8 !important; text-transform: uppercase; letter-spacing: .04em; font-size: .72rem !important; }}
.til-kpi {{ background: linear-gradient(135deg, rgba(18,23,32,0.96), rgba(13,17,23,0.99)); border: 1px solid {P['border']};
  border-radius: 16px; padding: 12px 14px; display: flex; gap: 12px; align-items: center; min-height: 84px;
  box-shadow: 0 6px 18px rgba(0,0,0,.35); margin-bottom: 10px; text-align: left; }}
.til-kpi .ic {{ width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  font-size: 1.3rem; background: rgba(34,211,238,.12); border: 1px solid rgba(34,211,238,.35); flex: none; }}
.til-kpi .lb {{ color: #94A3B8; font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; }}
.til-kpi .vl {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.45rem; font-weight: 800; color: #E2E8F0; line-height: 1.15; }}
.til-kpi .sb {{ color: #94A3B8; font-size: .75rem; }}
.til-kpi .bar {{ height: 5px; border-radius: 4px; background: #1E2A44; margin-top: 6px; overflow: hidden; }}
.til-kpi .bar > div {{ height: 100%; border-radius: 4px; background: var(--til-grad); }}
.til-vs {{ display: grid; grid-template-columns: 1fr 70px 1fr; gap: 10px; align-items: center; background: linear-gradient(90deg,
  rgba(34,211,238,.10), rgba(9,13,22,.95) 40%, rgba(9,13,22,.95) 60%, rgba(239,68,68,.10)); border: 1px solid {P['border']};
  border-radius: 18px; padding: 14px 18px; margin: 6px 0 14px 0; }}
.til-vs .side {{ display: flex; gap: 12px; align-items: center; }} .til-vs .side.r {{ flex-direction: row-reverse; text-align: right; }}
.til-vs .av {{ width: 58px; height: 58px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-family: 'Space Grotesk', sans-serif; font-weight: 800; font-size: 1.2rem; color: #090D16; flex: none; }}
.til-vs .nm {{ font-family: 'Space Grotesk', sans-serif; font-weight: 800; font-size: 1.15rem; color: #E2E8F0; }}
.til-vs .meta {{ color: #94A3B8; font-size: .8rem; }}
.til-vs .badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: .75rem; font-weight: 700; margin: 4px 4px 0 0;
  background: #0B1120; border: 1px solid {P['border']}; color: #E2E8F0; }}
.til-vs .mid {{ text-align: center; font-family: 'Space Grotesk', sans-serif; font-weight: 800; color: #94A3B8; font-size: 1.3rem; }}
@media (max-width: 640px) {{ .til-vs {{ grid-template-columns: 1fr; }} .til-vs .side.r {{ flex-direction: row; text-align: left; }} }}
.stButton button[kind="primary"], [data-testid="stBaseButton-primary"] {{ background: var(--til-grad); border: none; color: white; }}
.stTextInput input, .stNumberInput input, .stTextArea textarea, [data-baseweb="select"] > div {{
  background: #0B1120 !important; border-radius: 12px !important; border-color: {P['border']} !important; color: {P['text']} !important; }}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {{ border-color: {P['primary']} !important; }}
.stTextInput input:focus {{ box-shadow: 0 0 0 2px rgba(59,130,246,0.45) !important; }}
/* tabelas: moldura de painel, sem aparência crua do Streamlit */
[data-testid="stDataFrame"], [data-testid="stTable"] {{
  border-radius: 18px !important; overflow: hidden; border: 1px solid {P['border']};
  background: linear-gradient(145deg, rgba(17,26,46,0.92), rgba(9,13,22,0.96));
  box-shadow: 0 10px 28px rgba(0,0,0,0.24);
  padding: 6px;
}}
[data-testid="stDataFrame"] [data-testid="glideDataEditor"] {{
  border-radius: 12px; background: rgba(11,17,32,0.78);
}}
[data-testid="stDataFrame"] canvas {{ border-radius: 10px; }}
[data-testid="stTable"] table {{
  width: 100%; border-collapse: separate; border-spacing: 0;
  color: {P['text']}; font-family: Inter, 'Segoe UI', sans-serif;
}}
[data-testid="stTable"] thead th {{
  background: #20395F; color: #FFFFFF; font-size: .74rem; font-weight: 900;
  text-transform: uppercase; letter-spacing: .06em; border-bottom: 2px solid #67E8F9;
  padding: 12px 14px;
}}
[data-testid="stTable"] tbody td {{
  background: #0E192B; color: #F1F5F9; font-size: .88rem;
  border-bottom: 1px solid {P['border']}; padding: 10px 14px;
}}
[data-testid="stTable"] tbody tr:nth-child(even) td {{ background: #172945; }}
[data-testid="stTable"] tbody tr:hover td {{ background: rgba(34,211,238,.10); }}
[data-testid="stExpander"] {{ border-radius: 14px; border: 1px solid {P['border']}; background: rgba(11,17,32,0.6); }}
/* gráficos: cartão elevado, fundo consistente e bordas suaves */
[data-testid="stPlotlyChart"] {{
  position: relative; border-radius: 18px; overflow: hidden;
  border: 1px solid {P['border']};
  background: linear-gradient(145deg, rgba(17,26,46,0.78), rgba(9,13,22,0.84));
  box-shadow: 0 10px 28px rgba(0,0,0,0.26);
  padding: 7px 9px 2px; margin: 8px 0 18px;
  transition: border-color .18s ease, box-shadow .18s ease;
}}
[data-testid="stPlotlyChart"]:hover {{
  border-color: rgba(34,211,238,0.52);
  box-shadow: 0 12px 32px rgba(0,0,0,0.34), 0 0 18px rgba(34,211,238,0.07);
}}
[data-testid="stPlotlyChart"] .js-plotly-plot {{ border-radius: 12px; }}
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
.til-card {{ background: linear-gradient(135deg, rgba(18,23,32,0.95), rgba(13,17,23,0.98)); box-shadow: 0 6px 18px rgba(0,0,0,.32); border: 1px solid {P['border']};
  border-radius: 14px; padding: 14px 16px; margin-bottom: 12px; min-height: 118px; position: relative; overflow: hidden; }}
.til-card::after {{ content: ""; position: absolute; left: 16px; right: 16px; top: 0; height: 2px; background: var(--til-grad); opacity: .55; }}
.til-card .label {{ color: {P['muted']}; font-size: 0.78rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em; }}
.til-card .value {{ font-family: 'Space Grotesk', sans-serif; color: {P['text']}; font-size: clamp(1.6rem, 2.4vw, 2.2rem); font-weight: 700; line-height: 1.15; margin: 4px 0; }}
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
/* Scout War Room: contraste alto, informação densa apenas quando solicitada */
.scout-player {{ display:flex; align-items:center; gap:14px; padding:14px 16px; margin:10px 0 5px;
  border:1px solid #334967; border-radius:16px; background:linear-gradient(120deg,#13243D,#0D1728);
  box-shadow:0 7px 20px rgba(0,0,0,.25); }}
.scout-avatar {{ flex:0 0 48px; width:48px; height:48px; display:grid; place-items:center; border-radius:50%;
  background:linear-gradient(140deg,#2563EB,#0E7490); border:2px solid #93C5FD; color:#FFF;
  font-weight:900; font-size:1.05rem; }}
.scout-main {{ flex:1; min-width:0; }}
.scout-name {{ color:#FFF; font-weight:900; font-size:1.06rem; }}
.scout-sub {{ color:#CBD5E1; font-size:.8rem; margin-top:2px; }}
.scout-tags {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
.scout-tag {{ display:inline-block; padding:3px 9px; border-radius:999px; font-size:.72rem; font-weight:850;
  border:1px solid transparent; }}
.scout-tag.viable {{ background:#123A2B; color:#86EFAC; border-color:#22C55E; }}
.scout-tag.loan {{ background:#443511; color:#FDE68A; border-color:#D97706; }}
.scout-tag.dream {{ background:#481F2A; color:#FDA4AF; border-color:#E11D48; }}
.scout-tag.neutral {{ background:#1E3554; color:#DBEAFE; border-color:#4773A8; }}
.scout-value {{ min-width:110px; text-align:right; color:#FFF; font-weight:900; }}
.scout-value small {{ display:block; color:#B9C7DA; font-size:.68rem; font-weight:500; }}
[data-testid="stDataFrame"] [role="columnheader"] {{ background:#20395F !important; color:#FFF !important; }}
[data-testid="stDataFrame"] [role="gridcell"] {{ color:#F1F5F9 !important; }}
</style>
"""


def inject_theme() -> None:
    from src.ui.plot_config import install

    install()                                            # rodada 20: gráficos sem barra de zoom/ferramentas
    st.markdown(CSS.strip(), unsafe_allow_html=True)
