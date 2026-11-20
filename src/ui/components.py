"""
Componentes visuais reutilizáveis.

Regra de proveniência: card de métrica, barra comparativa e KPI recebem obrigatoriamente um
ProvenanceRecord (`prov`). Sem ele, em modo estrito (testes) é lançado MissingProvenanceError;
fora do modo estrito o componente mostra "origem não registrada" em vermelho.
Métricas SIMULATED exibem o selo não removível com gerador e IC 95%.
"""

from __future__ import annotations

import html
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

from src.canonical.provenance import MissingProvenanceError, ProvenanceRecord, ProvenanceRegistry, strict_mode
from src.data_hub.registry import BADGES, COLORS, LEVEL_DESCRIPTIONS
from src.ui.i18n import t
from src.ui.theme import PALETTE, PLOTLY_LAYOUT, TIER_COLORS, TIER_LABELS


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
    st.markdown(f'<div class="til-header"><div class="title">{_esc(t(title))}</div>'
                f'<div class="sub">{_esc(t(subtitle))}</div>{chips}</div>', unsafe_allow_html=True)


def level_banner(level: str, source_label: str = "") -> None:
    color = COLORS.get(level, PALETTE["muted"])
    st.markdown(f'<div class="til-level" style="border-left:5px solid {color}"><div class="t" style="color:{color}">'
                f'{_esc(BADGES.get(level, level))} <span style="color:{PALETTE["muted"]};font-weight:600;font-size:0.8rem">'
                f'· fonte: {_esc(source_label)}</span></div><div class="d">{_esc(LEVEL_DESCRIPTIONS.get(level, ""))}</div></div>',
                unsafe_allow_html=True)


def empty_state(title: str, message: str = "", icon: str = "🗂️", hint: str = "", error: bool = False) -> None:
    cls = "til-empty error" if error else "til-empty"
    st.markdown(f'<div class="{cls}"><div class="i">{icon}</div><div class="t">{_esc(t(title))}</div>'
                f'<div class="m">{_esc(t(message))}</div>' + (f'<div class="h">💡 {_esc(t(hint))}</div>' if hint else "")
                + "</div>", unsafe_allow_html=True)


def source_label(source: Optional[str]) -> str:
    from src.data_hub.registry import SOURCES

    info = SOURCES.get(str(source or ""))
    return info.label if info else (str(source) if source else "desconhecida")


def source_gap(what: str, source: Optional[str], hint: str = "", icon: str = "📄", level: Optional[str] = None) -> None:
    """Estado vazio padronizado: 'Sem <o quê> da fonte <X> para esta partida'."""
    lv = f" Nível desta partida: {BADGES.get(level, level)}." if level else ""
    empty_state(f"Sem {what} da fonte {source_label(source)} para esta partida",
                f"A fonte não publica esse dado para este jogo.{lv}", icon, hint)


def error_state(title: str, exc: Exception, hint: str = "") -> None:
    empty_state(title, f"{type(exc).__name__}: {exc}", icon="⚠️", hint=hint, error=True)


def metric_card(label: str, value, prov: Optional[ProvenanceRecord], badge_text: str = "", status: str = "neu",
                unit: str = "") -> None:
    prov = _check(prov, label)
    badge = f'<span class="badge {status}">{_esc(badge_text)}</span>' if badge_text else ""
    unit_html = f'<span class="unit">{_esc(unit)}</span>' if unit else ""
    st.markdown(f'<div class="til-card"><div class="label">{_esc(t(label))}</div><div class="value">{_esc(value)}{unit_html}</div>'
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
    from src.ui.names import pt

    st.markdown(f'<div class="til-score"><div class="row"><div class="team" style="text-align:right">{_esc(pt(home))} {crest_img(home, "md")}</div>'
                f'<div class="box">{_esc(score)}</div><div class="team" style="text-align:left">{crest_img(away, "md")} {_esc(pt(away))}</div></div>'
                f'{goals_row}' + (f'<div class="pen">{_esc(extra_line)}</div>' if extra_line else "")
                + f'<div class="meta">{_esc(meta_text)}</div></div>', unsafe_allow_html=True)


def note(title: str, body: str, kind: str = "") -> None:
    st.markdown(f'<div class="til-note {kind}"><div class="h">{_esc(t(title))}</div>{_esc(t(body))}</div>', unsafe_allow_html=True)


def zebra(df: pd.DataFrame):
    """Tabela escura no padrão do laboratório: cabeçalho destacado, linhas alternadas e indicadores visuais."""
    if not isinstance(df, pd.DataFrame):
        return df
    try:
        # cores SÓLIDAS (o st.dataframe mistura transparência com o fundo branco da grade e tudo fica pálido) e texto
        # claro em todas as células — inclusive nas colunas de texto, que antes ficavam ilegíveis
        sty = df.style.apply(
            lambda row: [
                "background-color: #0D1424; color: #DCE6F4" if not isinstance(row.name, (int, np.integer)) or row.name % 2 == 0
                else "background-color: #111C30; color: #DCE6F4"
            ] * len(row),
            axis=1,
        )
        table_styles = [
            {"selector": "table", "props": [
                ("width", "100%"), ("border-collapse", "separate"), ("border-spacing", "0"),
                ("background-color", "#0B1120"), ("border-radius", "12px"),
                ("font-family", "Inter, Segoe UI, sans-serif"), ("overflow", "hidden"),
            ]},
            {"selector": "thead th", "props": [
                ("background-color", "#172641"), ("color", "#F5F7FB"),
                ("font-size", "0.72rem"), ("font-weight", "800"),
                ("letter-spacing", "0.06em"), ("text-transform", "uppercase"),
                ("border-bottom", "2px solid #22D3EE"), ("padding", "12px 14px"),
                ("white-space", "nowrap"),
            ]},
            {"selector": "tbody td", "props": [
                ("color", "#DCE6F4"), ("font-size", "0.86rem"),
                ("border-bottom", "1px solid rgba(30,42,68,0.72)"),
                ("padding", "10px 14px"), ("vertical-align", "middle"),
            ]},
            {"selector": "tbody tr:hover td", "props": [
                ("background-color", "rgba(34,211,238,0.10)"),
                ("color", "#FFFFFF"),
            ]},
            {"selector": "caption", "props": [
                ("caption-side", "top"), ("color", "#98A6BF"),
                ("font-size", "0.78rem"), ("padding", "8px 0"),
            ]},
        ]
        sty = sty.set_table_styles(table_styles)

        # Números legíveis: inteiros sem casas; demais valores com até duas casas.
        fmt = {}
        rating_cols = []
        for col_name in df.columns:
            series = pd.to_numeric(df[col_name], errors="coerce")
            vals = series.dropna()
            if pd.api.types.is_float_dtype(df[col_name]) and len(vals):
                fmt[col_name] = "{:.0f}" if (vals == vals.round()).all() else "{:.2f}"
            low = str(col_name).strip().lower()
            if any(token in low for token in ("nota", "rating", "avaliação", "avaliacao")):
                rating_cols.append(col_name)
        # célula vazia aparece como "—" em TODAS as colunas (antes, colunas de texto mostravam "None" em fundo preto)
        sty = sty.format(na_rep="—")
        if fmt:
            sty = sty.format(fmt, na_rep="—")

        # Rodada 7: realce do PRÓPRIO tema escuro (o degradê claro "PuBu" deixava células brancas com texto apagado).
        # Ciano mais forte = valor mais alto na coluna; em colunas onde "mais" é ruim (perdas, faltas, sofridos,
        # driblado, erros, cartões, contra), o realce é vermelho. O texto fica sempre claro e legível.
        numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])
                        and not pd.api.types.is_bool_dtype(df[col])          # verdadeiro/falso não é escala
                        and df[col].notna().sum() > 1 and col not in rating_cols]
        neg_tokens = ("perd", "falta", "sofr", "driblad", "erro", "cart", "amarel", "vermelh", "contra", "cedid",
                      "conceded", "lost", "dispossess", "impedim", "offside", "fouls", "xga")
        if numeric_cols and len(numeric_cols) <= 40:
            base = (13, 20, 36)                               # #0D1424, o fundo das linhas

            def mix(rgb, a):
                return "#%02x%02x%02x" % tuple(int(b + (c - b) * a) for b, c in zip(base, rgb))

            def heat(col):
                v = pd.to_numeric(col, errors="coerce").astype(float)
                lo, hi = v.min(), v.max()
                rgb = (239, 68, 68) if any(t in str(col.name).lower() for t in neg_tokens) else (34, 211, 238)
                out = []
                for x in v:
                    if pd.isna(x):
                        out.append("color:#0D1424")            # vazio aparece vazio (o st.dataframe escreve "None")
                        continue
                    if hi == lo:
                        out.append("")
                        continue
                    n = (x - lo) / (hi - lo)
                    out.append(f"background-color: {mix(rgb, 0.06 + 0.50 * n)}; color:#F5F7FB;"
                               + ("font-weight:800" if n >= 0.85 else ""))
                return out
            sty = sty.apply(heat, subset=numeric_cols, axis=0)

        if rating_cols:
            def rating_color(value):
                try:
                    score = float(value)
                except (TypeError, ValueError):
                    return ""
                if score >= 7.5:
                    return "color:#34D399;font-weight:800"
                if score < 6.0:
                    return "color:#F87171;font-weight:800"
                return "color:#E5E7EB;font-weight:700"
            sty = sty.map(rating_color, subset=rating_cols) if hasattr(sty, "map") else sty.applymap(rating_color, subset=rating_cols)
        return sty
    except Exception:
        return df


_INT_TOKENS = ("idade", "age", "minutos", "minutes", "jogos", "games", "gols", "assist", "nº", "camisa", "ano",
               "temporada", "chegou primeiro", "titular")


def tidy_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rodada 10: números como gente lê — idade, minutos e contagens inteiros (23, não 23.8); o resto com no máximo
    2 casas (12.35, não 12.3456). Nada é inventado: vazio continua vazio.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    out = df.copy()
    for c in out.columns:
        col = out[c]
        if not pd.api.types.is_float_dtype(col):
            continue
        low = str(c).strip().lower()
        if any(t in low for t in _INT_TOKENS) and "%" not in low and "/90" not in low and "por 90" not in low:
            out[c] = np.floor(col).astype("Int64") if low.startswith(("idade", "age")) else col.round(0).astype("Int64")
        else:
            out[c] = col.round(2)
    return out


def styled_dataframe(data, *args, **kwargs):
    """Renderiza DataFrames no padrão visual do laboratório, sem perder ordenação ou seleção."""
    if isinstance(data, pd.DataFrame):
        data = tidy_numbers(data)
        # ProgressColumn é nativo do Streamlit 1.36 e desenha barras reais dentro da tabela.
        config = dict(kwargs.get("column_config") or {})
        for col_name in data.columns:
            low = str(col_name).strip().lower()
            is_rating = any(token in low for token in ("nota", "rating", "avaliação", "avaliacao"))
            is_rate = any(token in low for token in (
                "percent", "percentil", "_pct", "pct", "taxa", "auc", "precisão", "precisao",
                "recall", "f1", "probabilidade",
            ))
            if not (is_rating or is_rate) or col_name in config:
                continue
            values = pd.to_numeric(data[col_name], errors="coerce").dropna()
            if values.empty or values.min() < 0:
                continue
            maximum = 10.0 if is_rating and values.max() <= 10 else (
                1.0 if values.max() <= 1 else (100.0 if values.max() <= 100 else float(values.max()))
            )
            config[col_name] = st.column_config.ProgressColumn(
                str(col_name), min_value=0, max_value=maximum,
                format="%.2f" if maximum <= 1 else "%.1f",
            )
        if config:
            kwargs["column_config"] = config
        data = zebra(data)
    kwargs.setdefault("use_container_width", True)
    kwargs.setdefault("hide_index", True)
    return st.dataframe(data, *args, **kwargs)


def render_chart(figure, *args, **kwargs):
    """Aplica o tema esportivo a gráficos Plotly, inclusive figuras construídas fora de ui.charts."""
    try:
        import plotly.graph_objects as go

        fig = go.Figure(figure)
        fig.update_layout(
            template=PLOTLY_LAYOUT["template"],
            paper_bgcolor=fig.layout.paper_bgcolor or PLOTLY_LAYOUT["paper_bgcolor"],
            plot_bgcolor=fig.layout.plot_bgcolor or PLOTLY_LAYOUT["plot_bgcolor"],
            font=dict(family="Inter, Segoe UI, sans-serif", color=PALETTE["text"], size=13),
            colorway=fig.layout.colorway or PLOTLY_LAYOUT["colorway"],
            hoverlabel=PLOTLY_LAYOUT["hoverlabel"],
        )
        if fig.layout.title and fig.layout.title.text:
            fig.update_layout(title_font=dict(family="Space Grotesk, Inter, sans-serif", size=15, color=PALETTE["text"]))
        fig.update_xaxes(
            gridcolor="rgba(152,166,191,0.10)",
            zerolinecolor="rgba(152,166,191,0.18)",
            linecolor=PALETTE["border"],
            tickfont=dict(color=PALETTE["muted"]),
        )
        fig.update_yaxes(
            gridcolor="rgba(152,166,191,0.10)",
            zerolinecolor="rgba(152,166,191,0.18)",
            linecolor=PALETTE["border"],
            tickfont=dict(color=PALETTE["muted"]),
        )
        kwargs.setdefault("theme", None)
        return st.plotly_chart(fig, *args, **kwargs)
    except Exception:
        # Se uma figura não for compatível com go.Figure, mantém o comportamento nativo do Streamlit.
        return st.plotly_chart(figure, *args, **kwargs)


def _markdown_table(df: pd.DataFrame, limit: int = 100) -> str:
    view = df.reset_index(drop=True).head(limit).copy()
    headers = [str(x).replace("|", "\\|").replace("\n", " ") for x in view.columns]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in view.itertuples(index=False, name=None):
        vals = []
        for value in row:
            if value is None or (isinstance(value, float) and np.isnan(value)):
                value = "—"
            vals.append(str(value).replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |")
    if len(df) > limit:
        lines.append(f"\n_Exibindo {limit} de {len(df)} linhas._")
    return "\n".join(lines)


def comparison_table(df: pd.DataFrame, caption: str = "") -> None:
    view = df.reset_index(drop=True)
    styled_dataframe(view)
    if caption:
        st.caption(caption)
    if not view.empty:
        with st.expander("📋 Copiar para relatório (Markdown)", expanded=False):
            st.code(_markdown_table(view), language="markdown")


def clickable_table(df: pd.DataFrame, key: str, name_col: str, kind: str = "jogador", caption: str = "",
                    team_col: Optional[str] = None) -> None:
    """
    Tabela em que clicar numa linha abre a página da entidade (jogador ou time) — v36: "clicar no nome abre a página".
    A seleção é limpa ao abrir, para o "← Voltar" não reabrir a mesma página.
    """
    view = df.reset_index(drop=True)
    ev = styled_dataframe(view, on_select="rerun",
                      selection_mode="single-row", key=key)
    rows = list(getattr(getattr(ev, "selection", None), "rows", []) or []) if ev is not None else []
    st.caption(("🖱️ Clique numa linha para abrir a página do " + ("jogador" if kind == "jogador" else "time") + ". ")
               + caption)
    if rows:
        r = view.iloc[int(rows[0])]
        name = str(r.get(name_col) or "")
        st.session_state.pop(key, None)
        if name:
            from src.ui import nav

            if kind == "jogador":
                from src.data_lake.ids import player_core

                nav.open_view("jogador", name=name, core=player_core(name))
            else:
                nav.open_view("time", name=name)


def metric_bars(items: List[dict], kind: str = "forte", empty_text: str = "") -> None:
    """
    F3 — cartões em vez de tabela: valor no jogo × jogo típico, barra com o percentil e uma frase simples.
    O primeiro do ranking ganha destaque. `items` = itens do StrengthsWeaknessesEngine (label, value, percentile...).
    """
    if not items:
        st.caption(empty_text or "Nada fora do normal neste jogo.")
        return
    color = "#22D3EE" if kind == "forte" else "#EF4444"
    html_rows = []
    for i, d in enumerate(items[:6]):
        p = d.get("percentile")
        pct = 0 if p is None else max(0, min(100, float(p)))
        top = i == 0
        phrase = (f"melhor que {pct:.0f}% dos jogos da referência" if p is not None else "sem referência suficiente")
        html_rows.append(
            f'<div style="background:#0F1626;border:1px solid {"" + color if top else "#1E2A44"};border-radius:14px;'
            f'padding:{"14px" if top else "10px"} 14px;margin-bottom:8px;box-shadow:0 4px 14px rgba(0,0,0,.25)">'
            f'<div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline">'
            f'<span style="font-weight:600;font-size:{"1.05rem" if top else ".95rem"}">{("🏆 " if kind == "forte" else "⚠️ ") if top else ""}{_esc(t(d["label"]))}</span>'
            f'<span style="font-size:{"1.35rem" if top else "1.1rem"};font-weight:700;color:{color}">{_esc(d["value"])}</span></div>'
            f'<div style="height:8px;background:#1E2A44;border-radius:6px;margin:8px 0 4px">'
            f'<div style="width:{pct:.0f}%;height:8px;background:{color};border-radius:6px"></div></div>'
            f'<div style="color:#94A3B8;font-size:.8rem">{phrase} · jogo típico: {_esc(d.get("reference_median", "—"))}</div></div>')
    st.markdown("".join(html_rows), unsafe_allow_html=True)


def fmt_num(v, fm: str | None = "{:.2f}") -> str:
    """Número para os cartões de comparação: '—' sem dado; zeros só são tirados DEPOIS da vírgula (rodada 22: antes
    "40" virava "4" e "100" virava "1" — era o "4 jogos" do Comparar quando eram 40)."""
    if v is None:
        return "—"
    try:
        out = (fm or "{:.2f}").format(float(v))
    except Exception:
        return str(v)
    return out.rstrip("0").rstrip(".") if "." in out else out


def duel_bars(rows: List[dict], name_a: str, name_b: str, title: str = "") -> None:
    """
    Comparação lado a lado em cartões (sem cara de planilha): cada linha = indicador, com a barra de A (azul) para a
    esquerda e a de B (vermelho) para a direita, proporcionais ao maior dos dois; quem é melhor fica em destaque.
    rows: [{"label", "a", "b", "fmt": "{:.2f}", "lower_is_better": bool}]
    """
    f = fmt_num
    html_rows = []
    for r in rows:
        a, b = r.get("a"), r.get("b")
        try:
            fa, fb = float(a or 0), float(b or 0)
        except Exception:
            fa = fb = 0.0
        mx = max(abs(fa), abs(fb), 1e-9)
        better = None if fa == fb else ("a" if (fa > fb) != bool(r.get("lower_is_better")) else "b")
        wa, wb = 100 * abs(fa) / mx, 100 * abs(fb) / mx
        ca = "#22D3EE" if better == "a" else "#1E3A5F"
        cb = "#EF4444" if better == "b" else "#4A2228"
        html_rows.append(
            f'<div style="display:grid;grid-template-columns:72px 1fr 150px 1fr 72px;align-items:center;gap:8px;'
            f'padding:6px 0;border-bottom:1px solid #141C2E">'
            f'<div style="text-align:right;font-weight:{800 if better == "a" else 500};color:{"#22D3EE" if better == "a" else "#CBD5E1"}">{f(a, r.get("fmt"))}</div>'
            f'<div style="display:flex;justify-content:flex-end"><div style="width:{wa:.0f}%;height:10px;border-radius:6px;background:{ca}"></div></div>'
            f'<div style="text-align:center;color:#94A3B8;font-size:.82rem">{_esc(t(r["label"]))}</div>'
            f'<div><div style="width:{wb:.0f}%;height:10px;border-radius:6px;background:{cb}"></div></div>'
            f'<div style="font-weight:{800 if better == "b" else 500};color:{"#EF4444" if better == "b" else "#CBD5E1"}">{f(b, r.get("fmt"))}</div></div>')
    head = (f'<div style="display:grid;grid-template-columns:1fr 1fr;margin-bottom:6px"><div style="color:#22D3EE;'
            f'font-weight:700">● {_esc(name_a)}</div><div style="color:#EF4444;font-weight:700;text-align:right">'
            f'{_esc(name_b)} ●</div></div>')
    st.markdown(f'<div style="background:#0F1626;border:1px solid #1E2A44;border-radius:14px;padding:12px 16px;'
                f'margin-bottom:12px;box-shadow:0 6px 18px rgba(0,0,0,.3)">'
                + (f'<div style="font-weight:700;margin-bottom:8px">{_esc(t(title))}</div>' if title else "")
                + head + "".join(html_rows) + "</div>", unsafe_allow_html=True)


def entity_chips(players: List[str], teams: List[str], key: str) -> None:
    """Botões pequenos para abrir as páginas dos jogadores/times citados (ex.: numa resposta do Assistente)."""
    from src.ui import nav

    items = [("time", t) for t in teams if t] + [("jogador", p) for p in players if p]
    if not items:
        return
    cols = st.columns(min(len(items), 5))
    for i, (kind, name) in enumerate(items[:10]):
        with cols[i % len(cols)]:
            if kind == "jogador":
                from src.data_lake.ids import player_core

                nav.link(f"👤 {name}", "jogador", key=f"{key}_{i}", name=name, core=player_core(name))
            else:
                nav.link(f"🛡️ {name}", "time", key=f"{key}_{i}", name=name)


def provenance_panel(registry: ProvenanceRegistry) -> None:
    """Lista, ao pé da página, a origem de TODAS as métricas exibidas nela."""
    rows = registry.as_rows()
    if not rows:
        return
    with st.expander(f"🧾 Proveniência das {len(rows)} métricas desta página"):
        df = pd.DataFrame(rows)[["label", "value", "confidence_tier", "source", "connector", "method", "license",
                                 "ingestion_timestamp", "generator", "ci_low", "ci_high"]]
        df["value"] = df["value"].map(lambda v: "" if v is None else str(v))   # tipos misturados quebravam o pyarrow
        styled_dataframe(df.rename(columns={"label": "métrica", "value": "valor", "confidence_tier": "tier", "source": "fonte",
                                        "connector": "conector", "method": "método", "license": "licença",
                                        "ingestion_timestamp": "ingestão", "generator": "gerador",
                                        "ci_low": "IC 2,5%", "ci_high": "IC 97,5%"}),
                     use_container_width=True, hide_index=True)


def hero(kicker: str, title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="til-hero"><div class="k">{_esc(t(kicker))}</div><div class="t">{_esc(t(title))}</div>'
                f'<div class="s">{_esc(t(subtitle))}</div></div>', unsafe_allow_html=True)


def _score_of(m) -> str:
    hs, as_ = m.get("home_score"), m.get("away_score")
    try:
        return f"{int(hs)} – {int(as_)}" if hs is not None and as_ is not None and str(hs) != "nan" and str(as_) != "nan" else "x"
    except (TypeError, ValueError):
        return "x"


def match_strip(meta: dict, level_badge: str = "") -> None:
    """Faixa compacta da partida aberta (escudos, placar, competição, nível do dado)."""
    from src.ui.crests import crest_img

    from src.ui.names import pt

    h, a = meta.get("home_team_name", ""), meta.get("away_team_name", "")
    st.markdown(f'<div class="til-strip"><div class="tm">{crest_img(h)} {_esc(pt(h))}</div><div class="sc">{_score_of(meta)}</div>'
                f'<div class="tm">{_esc(pt(a))} {crest_img(a)}</div><div class="meta">{_esc(meta.get("competition_name", ""))} '
                f'{_esc(meta.get("season_name", ""))}<br>{_esc(meta.get("match_date", ""))} · {_esc(level_badge)}</div></div>',
                unsafe_allow_html=True)


def result_card_html(m: dict, level_badge: str = "") -> str:
    from src.ui.crests import crest_img

    from src.ui.names import pt

    h, a = m.get("home_team_name", ""), m.get("away_team_name", "")
    return (f'<div class="til-result"><div class="tm r">{_esc(pt(h))} {crest_img(h)}</div><div class="sc">{_score_of(m)}</div>'
            f'<div class="tm">{crest_img(a)} {_esc(pt(a))}</div><div class="meta">{_esc(m.get("competition_name", ""))}<br>'
            f'{_esc(m.get("match_date", ""))} · {_esc(level_badge)}</div></div>')


def form_html(results) -> str:
    """Sequência V/E/D (mais recente à direita)."""
    return '<div class="til-form">' + "".join(f'<span class="{r}">{r}</span>' for r in results) + "</div>"


def steps_html(items) -> str:
    return "".join(f'<div class="til-step"><div class="n">{i}</div><div><div class="t">{_esc(t)}</div>'
                   f'<div class="b">{b}</div></div></div>' for i, (t, b) in enumerate(items, 1))



def kpi_cards(items: List[dict], cols: int = 4) -> None:
    """Rodada 22: cartões de indicador com ícone, valor, linha de apoio e barra opcional (0–100), no estilo de painel.
    items: [{"icone": "⚽", "rotulo": "Gols", "valor": "39", "sub": "1,1 por jogo", "barra": 62}]"""
    if not items:
        return
    columns = st.columns(min(cols, len(items)))
    for i, it in enumerate(items):
        bar = it.get("barra")
        bar_html = (f'<div class="bar"><div style="width:{max(0, min(100, float(bar))):.0f}%"></div></div>'
                    if bar is not None else "")
        columns[i % len(columns)].markdown(
            f'<div class="til-kpi"><div class="ic">{_esc(str(it.get("icone", "•")))}</div><div style="flex:1;min-width:0">'
            f'<div class="lb">{_esc(t(str(it.get("rotulo", ""))))}</div><div class="vl">{_esc(str(it.get("valor", "—")))}</div>'
            f'<div class="sb">{_esc(str(it.get("sub", "")))}</div>{bar_html}</div></div>', unsafe_allow_html=True)


def versus_hero(a: dict, b: dict, mid: str = "VS") -> None:
    """Cabeçalho lado a lado (jogador × jogador ou time × time) com iniciais, clube, idade e selos (overall, potencial)."""
    def side(x: dict, color: str, right: bool) -> str:
        nm = str(x.get("nome") or "—")
        ini = "".join(w[0] for w in nm.split()[:2]).upper() or "?"
        badges = "".join(f'<span class="badge">{_esc(str(k))} {_esc(str(v))}</span>' for k, v in (x.get("selos") or {}).items()
                         if v not in (None, "", "—"))
        return (f'<div class="side{" r" if right else ""}"><div class="av" style="background:{color}">{_esc(ini)}</div>'
                f'<div><div class="nm">{_esc(nm)}</div><div class="meta">{_esc(str(x.get("meta") or ""))}</div>{badges}</div></div>')
    st.markdown(f'<div class="til-vs">{side(a, "#22D3EE", False)}<div class="mid">{_esc(mid)}</div>{side(b, "#EF4444", True)}</div>',
                unsafe_allow_html=True)
