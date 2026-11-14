"""
Componentes visuais reutilizáveis.

Regra de proveniência: card de métrica, barra comparativa e KPI recebem obrigatoriamente um
ProvenanceRecord (`prov`). Sem ele, em modo estrito (testes) é lançado MissingProvenanceError;
fora do modo estrito o componente mostra "origem não registrada" em vermelho.
Métricas SIMULATED exibem o selo não removível com gerador e IC 95%.
"""

from __future__ import annotations

import html
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import streamlit as st

from src.canonical.provenance import MissingProvenanceError, ProvenanceRecord, ProvenanceRegistry, strict_mode
from src.data_hub.registry import BADGES, COLORS, LEVEL_DESCRIPTIONS
from src.ui.theme import PALETTE, TIER_COLORS, TIER_LABELS


def _esc(v) -> str:
    return html.escape(str(v), quote=True)


def _check(prov: Optional[ProvenanceRecord], label: str) -> Optional[ProvenanceRecord]:
    if prov is None and strict_mode():
        raise MissingProvenanceError(f"métrica '{label}' exibida sem proveniência")
    return prov


def provenance_line(prov: Optional[ProvenanceRecord]) -> str:
    if prov is None:
        return '<div class="til-prov missing">⚠ origem não registrada</div>'
    color = TIER_COLORS.get(prov.confidence_tier, PALETTE["muted"])
    tip = _esc(f"Fonte: {prov.source}\nConector: {prov.connector}\nLicença: {prov.license}\n"
               f"Método: {prov.method}\nIngestão: {prov.ingestion_timestamp}")
    line = (f'<div class="til-prov" title="{tip}"><b style="color:{color}">{TIER_LABELS[prov.confidence_tier]}</b> · '
            f'{_esc(prov.source)} · {_esc(prov.method)}</div>')
    if prov.is_simulated:
        line += f'<div class="til-sim">{_esc(prov.simulated_label())}</div>'
    return line


def page_header(title: str, subtitle: str = "", ctx=None) -> None:
    """Cabeçalho de contexto: partida, competição, fonte do dado e tier de confiança."""
    chips = ""
    if ctx is not None:
        m = ctx.bundle.meta or {}
        tier = ctx.raw_tier
        chips = (f'<div class="ctx"><span class="til-chip">⚽ {_esc(m.get("home_team_name", ""))} x '
                 f'{_esc(m.get("away_team_name", ""))}</span>'
                 f'<span class="til-chip">🏆 {_esc(m.get("competition_name", ""))} {_esc(m.get("season_name", ""))}</span>'
                 f'<span class="til-chip">🗂 {_esc(ctx.bundle.source_label)}</span>'
                 f'<span class="til-chip tier" style="border-color:{TIER_COLORS[tier]};color:{TIER_COLORS[tier]}">'
                 f'tier {TIER_LABELS[tier]}</span>'
                 f'<span class="til-chip">🎯 foco: {_esc(ctx.target_team)}</span></div>')
    st.markdown(f'<div class="til-header"><div class="title">{_esc(title)}</div>'
                f'<div class="sub">{_esc(subtitle)}</div>{chips}</div>', unsafe_allow_html=True)


def level_banner(level: str, source_label: str = "") -> None:
    color = COLORS.get(level, PALETTE["muted"])
    st.markdown(f'<div class="til-level" style="border-left:5px solid {color}"><div class="t" style="color:{color}">'
                f'{_esc(BADGES.get(level, level))} <span style="color:{PALETTE["muted"]};font-weight:600;font-size:0.8rem">'
                f'· fonte: {_esc(source_label)}</span></div><div class="d">{_esc(LEVEL_DESCRIPTIONS.get(level, ""))}</div></div>',
                unsafe_allow_html=True)


def empty_state(title: str, message: str = "", icon: str = "🗂️", hint: str = "", error: bool = False) -> None:
    cls = "til-empty error" if error else "til-empty"
    st.markdown(f'<div class="{cls}"><div class="i">{icon}</div><div class="t">{_esc(title)}</div>'
                f'<div class="m">{_esc(message)}</div>' + (f'<div class="h">💡 {_esc(hint)}</div>' if hint else "")
                + "</div>", unsafe_allow_html=True)


def error_state(title: str, exc: Exception, hint: str = "") -> None:
    empty_state(title, f"{type(exc).__name__}: {exc}", icon="⚠️", hint=hint, error=True)


def metric_card(label: str, value, prov: Optional[ProvenanceRecord], badge_text: str = "", status: str = "neu",
                unit: str = "") -> None:
    prov = _check(prov, label)
    badge = f'<span class="badge {status}">{_esc(badge_text)}</span>' if badge_text else ""
    unit_html = f'<span class="unit">{_esc(unit)}</span>' if unit else ""
    st.markdown(f'<div class="til-card"><div class="label">{_esc(label)}</div><div class="value">{_esc(value)}{unit_html}</div>'
                f'{badge}{provenance_line(prov)}</div>', unsafe_allow_html=True)


def kpi(label: str, value, prov: Optional[ProvenanceRecord]) -> None:
    prov = _check(prov, label)
    st.markdown(f'<div class="til-kpi"><div class="v">{_esc(value)}</div><div class="l">{_esc(label)}</div>'
                f'{provenance_line(prov)}</div>', unsafe_allow_html=True)


def stat_pill(title: str, left_val, right_val, left_display: str, right_display: str,
              prov: Optional[ProvenanceRecord], invert_advantage: bool = False) -> None:
    prov = _check(prov, title)
    lv, rv = float(left_val or 0), float(right_val or 0)
    pct = float(np.clip(100 * lv / (lv + rv), 5, 95)) if (lv + rv) > 0 else 50.0
    if invert_advantage:
        pct = 100 - pct
    src = (f'<div class="src">{TIER_LABELS[prov.confidence_tier]} · {_esc(prov.method)}</div>' if prov
           else '<div class="src" style="color:#F87171">⚠ origem não registrada</div>')
    if prov is not None and prov.is_simulated:
        src += f'<div class="til-sim">{_esc(prov.simulated_label())}</div>'
    st.markdown(f'<div class="til-pill"><div class="head"><span class="l">{_esc(left_display)}</span>'
                f'<span class="t">{_esc(title)}</span><span class="r">{_esc(right_display)}</span></div>'
                f'<div class="track"><div class="fl" style="width:{pct:.1f}%"></div><div class="fr" style="width:{100 - pct:.1f}%"></div></div>'
                f'{src}</div>', unsafe_allow_html=True)


def scoreboard(home: str, away: str, score: str, meta_text: str = "", home_goals: Optional[list] = None,
               away_goals: Optional[list] = None, extra_line: str = "") -> None:
    """Placar com a lista de gols de cada lado (minuto, autor, tipo/assistência) abaixo do nome da equipe."""
    def col(lines, align):
        if not lines:
            return ""
        return (f'<div class="goals" style="text-align:{align}">' + "".join(f"<div>⚽ {_esc(l)}</div>" for l in lines)
                + "</div>")
    goals_row = ""
    if home_goals or away_goals:
        goals_row = (f'<div class="grow"><div class="gcol">{col(home_goals, "right")}</div><div class="gsep"></div>'
                     f'<div class="gcol">{col(away_goals, "left")}</div></div>')
    from src.ui.crests import crest_img

    st.markdown(f'<div class="til-score"><div class="row"><div class="team" style="text-align:right">{_esc(home)} {crest_img(home, "md")}</div>'
                f'<div class="box">{_esc(score)}</div><div class="team" style="text-align:left">{crest_img(away, "md")} {_esc(away)}</div></div>'
                f'{goals_row}' + (f'<div class="pen">{_esc(extra_line)}</div>' if extra_line else "")
                + f'<div class="meta">{_esc(meta_text)}</div></div>', unsafe_allow_html=True)


def note(title: str, body: str, kind: str = "") -> None:
    st.markdown(f'<div class="til-note {kind}"><div class="h">{_esc(title)}</div>{_esc(body)}</div>', unsafe_allow_html=True)


def comparison_table(df: pd.DataFrame, caption: str = "") -> None:
    st.dataframe(df, use_container_width=True, hide_index=True)
    if caption:
        st.caption(caption)


def provenance_panel(registry: ProvenanceRegistry) -> None:
    """Lista, ao pé da página, a origem de TODAS as métricas exibidas nela."""
    rows = registry.as_rows()
    if not rows:
        return
    with st.expander(f"🧾 Proveniência das {len(rows)} métricas desta página"):
        df = pd.DataFrame(rows)[["label", "value", "confidence_tier", "source", "connector", "method", "license",
                                 "ingestion_timestamp", "generator", "ci_low", "ci_high"]]
        st.dataframe(df.rename(columns={"label": "métrica", "value": "valor", "confidence_tier": "tier", "source": "fonte",
                                        "connector": "conector", "method": "método", "license": "licença",
                                        "ingestion_timestamp": "ingestão", "generator": "gerador",
                                        "ci_low": "IC 2,5%", "ci_high": "IC 97,5%"}),
                     use_container_width=True, hide_index=True)


def hero(kicker: str, title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="til-hero"><div class="k">{_esc(kicker)}</div><div class="t">{_esc(title)}</div>'
                f'<div class="s">{_esc(subtitle)}</div></div>', unsafe_allow_html=True)


def _score_of(m) -> str:
    hs, as_ = m.get("home_score"), m.get("away_score")
    try:
        return f"{int(hs)} – {int(as_)}" if hs is not None and as_ is not None and str(hs) != "nan" and str(as_) != "nan" else "x"
    except (TypeError, ValueError):
        return "x"


def match_strip(meta: dict, level_badge: str = "") -> None:
    """Faixa compacta da partida aberta (escudos, placar, competição, nível do dado)."""
    from src.ui.crests import crest_img

    h, a = meta.get("home_team_name", ""), meta.get("away_team_name", "")
    st.markdown(f'<div class="til-strip"><div class="tm">{crest_img(h)} {_esc(h)}</div><div class="sc">{_score_of(meta)}</div>'
                f'<div class="tm">{_esc(a)} {crest_img(a)}</div><div class="meta">{_esc(meta.get("competition_name", ""))} '
                f'{_esc(meta.get("season_name", ""))}<br>{_esc(meta.get("match_date", ""))} · {_esc(level_badge)}</div></div>',
                unsafe_allow_html=True)


def result_card_html(m: dict, level_badge: str = "") -> str:
    from src.ui.crests import crest_img

    h, a = m.get("home_team_name", ""), m.get("away_team_name", "")
    return (f'<div class="til-result"><div class="tm r">{_esc(h)} {crest_img(h)}</div><div class="sc">{_score_of(m)}</div>'
            f'<div class="tm">{crest_img(a)} {_esc(a)}</div><div class="meta">{_esc(m.get("competition_name", ""))}<br>'
            f'{_esc(m.get("match_date", ""))} · {_esc(level_badge)}</div></div>')


def form_html(results) -> str:
    """Sequência V/E/D (mais recente à direita)."""
    return '<div class="til-form">' + "".join(f'<span class="{r}">{r}</span>' for r in results) + "</div>"


def steps_html(items) -> str:
    return "".join(f'<div class="til-step"><div class="n">{i}</div><div><div class="t">{_esc(t)}</div>'
                   f'<div class="b">{b}</div></div></div>' for i, (t, b) in enumerate(items, 1))
