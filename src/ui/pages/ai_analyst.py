"""Seção 🧠 Analista IA — conversa com respostas sob medida e auditadas."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
from src.reports.report_builder import TacticalReportBuilder
from src.ui.components import section_header
from src.ui.context import MatchContext


def _audit_caption(res) -> str:
    a = res.get("hallucination_audit") or {}
    status = "✅ aprovado" if a.get("is_grounded") else "⚠️ com ressalvas"
    scope = (res.get("scope") or {}).get("recorte", "")
    return (f"Motor: {res.get('engine_used')} · Guardião: {status} "
            f"({a.get('verified_decimals_count', 0)} decimais e {a.get('verified_integers_count', 0)} inteiros conferidos)"
            + (f" · Recorte: {scope}" if scope else ""))


def render(ctx: MatchContext) -> None:
    section_header("🧠 Analista IA",
                   "Pergunte o que quiser sobre a partida. A resposta usa só os dados do recorte pedido "
                   "(minuto, lado, fase, atleta) e cada número é auditado.")
    analyst = DynamicTacticalAnalyst()
    c1, c2 = st.columns([3, 1])
    use_llm = c1.toggle("Usar Gemini (se GEMINI_API_KEY estiver no .env)", value=analyst.api_key is not None)
    if c2.button("Limpar conversa", use_container_width=True):
        st.session_state["chat_history"] = []

    examples = [
        "Como foi a compactação defensiva do lado esquerdo no minuto 30?",
        f"Onde {ctx.opponent} mais nos atacou no primeiro tempo?",
        "Como foi a transição defensiva depois do minuto 60?",
        "Relatório completo da partida",
    ]
    ex_cols = st.columns(len(examples))
    clicked = None
    for i, e in enumerate(examples):
        if ex_cols[i].button(e, key=f"ex_{i}", use_container_width=True):
            clicked = e

    history = st.session_state.setdefault("chat_history", [])
    for h in history:
        with st.chat_message("user"):
            st.markdown(h["q"])
        with st.chat_message("assistant"):
            st.markdown(h["a"])
            st.caption(h["meta"])

    question = st.chat_input("Ex.: quem mais abasteceu o centroavante no segundo tempo?") or clicked
    if not question:
        return
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Recortando os dados e redigindo..."):
            try:
                res = analyst.answer(
                    question, ctx.target_team, {**(ctx.bundle.meta or {}), "match_id": ctx.match_id,
                                                "data_level": ctx.bundle.level, "data_source": ctx.bundle.source},
                    df_events=ctx.df, df_chains=ctx.chains, boxscore=ctx.bundle.boxscore,
                    prefer_llm=use_llm, history=history)
            except Exception as exc:
                st.warning(f"Não consegui responder: {exc}")
                return
        st.markdown(res["report_markdown"])
        meta = _audit_caption(res)
        st.caption(meta)
        blocked = (res.get("hallucination_audit") or {}).get("blocked_llm_audit")
        if blocked:
            st.warning("🛡️ O texto do Gemini citou dados fora das evidências e foi substituído pelo redator local: "
                       f"{blocked.get('unverified_decimals', []) + blocked.get('unverified_integers', [])} "
                       f"{blocked.get('unverified_player_names', [])}")
        if (res.get("scope") or {}).get("category") == "full_report":
            paths = TacticalReportBuilder.export_report_files(
                res["report_markdown"],
                output_prefix=f"data/processed/relatorio_{ctx.match_id}_{ctx.target_team.lower().replace(' ', '_')}")
            st.download_button("Baixar relatório (.md)", data=res["report_markdown"],
                               file_name="relatorio_tatico.md", mime="text/markdown")
            st.download_button("Baixar relatório para impressão (.html)",
                               data=Path(paths["html_path"]).read_text(encoding="utf-8"),
                               file_name="relatorio_tatico.html", mime="text/html")
        with st.expander("Evidências usadas nesta resposta"):
            st.json(res.get("evidence") or {})
    history.append({"q": question, "a": res["report_markdown"], "meta": meta})
