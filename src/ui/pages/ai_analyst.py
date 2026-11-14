"""Página 8 — Analista IA: respostas por recorte, com o guard de números visível (EXATO / DERIVADO / NÃO RASTREÁVEL)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.guard.metrics import GuardMetricsLog
from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
from src.reports.report_builder import TacticalReportBuilder
from src.ui.components import comparison_table, error_state, kpi, note, page_header, provenance_panel
from src.ui.context import MatchContext

OUTCOME_TEXT = {
    "APROVADO_1A": ("✅ aprovado na 1ª tentativa", ""),
    "APROVADO_REGENERADO": ("🔁 aprovado após regeneração com contexto restrito", "warn"),
    "DEGRADADO": ("⛔ resposta degradada declarada (2 bloqueios → redator local)", "warn"),
}


def _meta(res) -> str:
    a = res.get("hallucination_audit") or {}
    scope = (res.get("scope") or {}).get("recorte", "")
    return (f"Motor: {res.get('engine_used')} · {a.get('numbers_total', 0)} números conferidos "
            f"({a.get('exact_count', 0)} exatos, {a.get('derived_count', 0)} derivados, "
            f"{a.get('untraceable_count', 0)} não rastreáveis)" + (f" · Recorte: {scope}" if scope else ""))


def _guard_panel(res) -> None:
    a = res.get("hallucination_audit") or {}
    outcome = res.get("guard_outcome")
    if outcome:
        txt, kind = OUTCOME_TEXT.get(outcome, (outcome, ""))
        m = res.get("guard_metrics") or {}
        note(f"Guard: {txt}", f"Taxa de números não rastreáveis: antes {100 * m.get('rate_before', 0):.1f}% "
             f"({m.get('untraceable_before', 0)}/{m.get('numbers_before', 0)}) → depois {100 * m.get('rate_after', 0):.1f}% "
             f"({m.get('untraceable_after', 0)}/{m.get('numbers_after', 0)}), {m.get('attempts', 1)} tentativa(s).", kind)
    rows = a.get("classificacao") or []
    with st.expander(f"🛡️ Classificação dos {len(rows)} números da resposta"):
        if rows:
            comparison_table(pd.DataFrame(rows).rename(columns={"numero": "número", "classe": "classe", "explicacao": "explicação",
                                                                "contexto": "contexto"}),
                             "EXATO = aparece nas evidências · DERIVADO = operação simples sobre evidências (unidade "
                             "compatível) · CONSTANTE = constante metodológica · NÃO RASTREÁVEL = sem origem → bloqueia.")
        else:
            st.caption("A resposta não contém números.")
        if a.get("unverified_player_names"):
            st.warning(f"Nomes fora das evidências: {a['unverified_player_names']}")


def _history_panel() -> None:
    h = GuardMetricsLog().history()
    if h.empty:
        return
    with st.expander(f"📈 Histórico do guard ({len(h)} respostas do Gemini registradas)"):
        k = st.columns(3)
        k[0].metric("taxa média antes do guard", f"{100 * h['rate_before'].mean():.1f}%")
        k[1].metric("taxa média depois do guard", f"{100 * h['rate_after'].mean():.1f}%")
        k[2].metric("respostas degradadas", int((h["outcome"] == "DEGRADADO").sum()))
        comparison_table(h)


def render(ctx: MatchContext) -> None:
    page_header("💬 Analista IA", "Pergunte sobre a partida. A resposta usa só os dados do recorte (minuto, lado, fase, "
                "atleta) e cada número passa pelo guard antes de aparecer.", ctx)
    analyst = DynamicTacticalAnalyst()
    c1, c2 = st.columns([3, 1])
    use_llm = c1.toggle("Redigir com Gemini (precisa de GEMINI_API_KEY no .env)", value=analyst.api_key is not None)
    if c2.button("Limpar conversa", use_container_width=True):
        st.session_state["chat_history"] = []
    if not use_llm:
        st.caption("Sem Gemini, o redator local monta o texto direto das evidências (os números saem direto das evidências do recorte).")

    examples = ["Como foi a compactação defensiva do lado esquerdo no minuto 30?",
                f"Onde {ctx.opponent} mais nos atacou no primeiro tempo?",
                "Como foi a transição defensiva depois do minuto 60?", "Relatório completo da partida"]
    cols = st.columns(len(examples))
    clicked = next((e for i, e in enumerate(examples) if cols[i].button(e, key=f"ex_{i}", use_container_width=True)), None)

    history = st.session_state.setdefault("chat_history", [])
    for h in history:
        with st.chat_message("user"):
            st.markdown(h["q"])
        with st.chat_message("assistant"):
            st.markdown(h["a"])
            st.caption(h["meta"])

    question = st.chat_input("Ex.: quem mais abasteceu o centroavante no segundo tempo?") or clicked
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Recortando os dados e redigindo..."):
                try:
                    res = analyst.answer(question, ctx.target_team,
                                         {**(ctx.bundle.meta or {}), "match_id": ctx.match_id, "data_level": ctx.bundle.level,
                                          "data_source": ctx.bundle.source},
                                         df_events=ctx.df, df_chains=ctx.chains, boxscore=ctx.bundle.boxscore,
                                         prefer_llm=use_llm, history=history)
                except Exception as exc:
                    error_state("Não consegui responder", exc)
                    return
            st.markdown(res["report_markdown"])
            if res.get("llm_error"):
                st.warning(f"O Gemini não respondeu ({res['llm_error']}). O texto acima veio do redator local, "
                           "com os mesmos dados.")
            meta = _meta(res)
            st.caption(meta)
            _guard_panel(res)
            a = res.get("hallucination_audit") or {}
            p = ctx.prov("guard", "Números da resposta", a.get("numbers_total", 0),
                         f"guard v2: {a.get('exact_count', 0)} exatos, {a.get('derived_count', 0)} derivados, "
                         f"{a.get('untraceable_count', 0)} não rastreáveis", inputs=["evidências do recorte"])
            k = st.columns(3)
            with k[0]:
                kpi("números na resposta", a.get("numbers_total", 0), p)
            with k[1]:
                kpi("rastreáveis", a.get("numbers_total", 0) - a.get("untraceable_count", 0), p)
            with k[2]:
                kpi("taxa não rastreável", f"{100 * a.get('untraceable_rate', 0):.1f}%", p)
            if (res.get("scope") or {}).get("category") == "full_report":
                paths = TacticalReportBuilder.export_report_files(
                    res["report_markdown"],
                    output_prefix=f"data/processed/relatorio_{ctx.match_id}_{ctx.target_team.lower().replace(' ', '_')}")
                st.download_button("Baixar relatório (.md)", data=res["report_markdown"], file_name="relatorio_tatico.md",
                                   mime="text/markdown")
                st.download_button("Baixar relatório para impressão (.html)",
                                   data=Path(paths["html_path"]).read_text(encoding="utf-8"),
                                   file_name="relatorio_tatico.html", mime="text/html")
            with st.expander("Evidências usadas nesta resposta"):
                st.json(res.get("evidence") or {})
        history.append({"q": question, "a": res["report_markdown"], "meta": meta})
    _history_panel()
    provenance_panel(ctx.registry)
