"""
💬 Assistente — chat único do laboratório.

A pergunta pode trazer o jogo junto ("Na final da Copa de 2022, quem mais criou perigo?"): o localizador encontra a
partida no catálogo, abre e responde nela. Sem jogo citado, a resposta usa a partida aberta (faixa do topo).
Cada resposta passa pelo guard de números; o modelo de perigo campeão é usado quando a pergunta pede.
"""

from __future__ import annotations

import streamlit as st

from src.data_hub.registry import BADGES
from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
from src.ui.components import hero, note, result_card_html

EXAMPLES = [
    "Na final da Copa de 2022 entre Argentina e França, quem fez os gols?",
    "Argentina x França 2022: qual tática a França deveria usar para evitar a derrota?",
    "Brasil x Inglaterra 1970: o que o Brasil fez para ganhar?",
    "Quem mais criou perigo nesta partida, segundo a rede neural?",
    "Como anular o principal criador do adversário?",
    "Como foi a transição defensiva depois do minuto 60?",
]


@st.cache_data(show_spinner=False, max_entries=4)
def _index(version: str):
    from src.intelligence.match_locator import build_index
    from src.ui.context import cached_catalog

    return build_index(cached_catalog())


def _meta_line(res) -> str:
    a = res.get("hallucination_audit") or {}
    return (f"{res.get('engine_used')} · {a.get('numbers_total', 0)} números conferidos "
            f"({a.get('untraceable_count', 0)} sem origem)")


def _answer(question: str, current_context, use_llm: bool):
    from src.intelligence.match_locator import locate
    from src.ui.context import cached_catalog, get_service

    loc = None
    try:
        loc = locate(question, cached_catalog(), _index(get_service().db.catalog_version()))
    except Exception:
        loc = None
    previous = int(st.session_state.get("match_id", 0))
    switched = bool(loc and loc.match_id != previous)
    if switched:
        from src.ui.context import load_bundle

        opened = None
        for mid in [loc.match_id] + [int(x) for x in loc.candidates["match_id"].tolist() if int(x) != loc.match_id]:
            try:                                         # outra fonte do mesmo jogo, se a primeira não abrir
                load_bundle(int(mid))
                opened = int(mid)
                break
            except Exception:
                continue
        if opened is None:
            loc.label += " — não foi possível abrir agora (sem internet?); respondendo na partida aberta"
            switched = False
        else:
            loc.match_id = opened
            st.session_state["match_id"] = opened
            st.session_state["team_focus"] = None
    ctx = current_context()
    if ctx is None:
        return None, loc, switched
    meta = {**(ctx.bundle.meta or {}), "match_id": ctx.match_id, "data_level": ctx.bundle.level, "data_source": ctx.bundle.source}
    hist = [h for h in st.session_state.get("chat_history", []) if h.get("match_id") == ctx.match_id]
    res = DynamicTacticalAnalyst().answer(question, ctx.target_team, meta, df_events=ctx.df, df_chains=ctx.chains,
                                          boxscore=ctx.bundle.boxscore, prefer_llm=use_llm, history=hist)
    res["_match_card"] = result_card_html(ctx.bundle.meta or {}, BADGES.get(ctx.bundle.level, ctx.bundle.level))
    return res, loc, switched


def render(current_context, match_bar) -> None:
    hero("Assistente tático", "Pergunte qualquer coisa sobre futebol",
         "Cite o jogo na própria pergunta (times e ano) ou use a partida aberta no topo. Cada número da resposta é "
         "conferido contra os dados antes de aparecer.")
    match_bar()
    analyst = DynamicTacticalAnalyst()
    with st.expander("Opções do assistente"):
        use_llm = st.toggle("Redigir com Gemini (precisa de GEMINI_API_KEY no .env)", value=analyst.api_key is not None)
        if st.button("Limpar conversa"):
            st.session_state["chat_history"] = []
    history = st.session_state.setdefault("chat_history", [])
    clicked = None
    if not history:
        st.markdown("##### Experimente")
        cols = st.columns(3)
        for i, e in enumerate(EXAMPLES):
            if cols[i % 3].button(e, key=f"as_ex_{i}", use_container_width=True):
                clicked = e
    for h in history:
        with st.chat_message("user", avatar="🧑‍💼"):
            st.markdown(h["q"])
        with st.chat_message("assistant", avatar="⚽"):
            if h.get("card"):
                st.markdown(h["card"], unsafe_allow_html=True)
            if h.get("note"):
                st.caption(h["note"])
            st.markdown(h["a"])
            st.caption(h["meta"])
            if h.get("llm_error"):
                st.caption(f"⚠️ Gemini indisponível: {h['llm_error']}")
    question = st.chat_input("Pergunte sobre um jogo, um jogador ou uma tática — ex.: “Real Madrid x Barcelona 2018: "
                             "quem mais criou perigo?”") or clicked
    if not question:
        if history:
            note("Dica", "Para mudar de jogo, é só citar os times (e o ano) na próxima pergunta.")
        return
    with st.spinner("Encontrando o jogo, recortando os dados e redigindo..."):
        try:
            res, loc, switched = _answer(question, current_context, use_llm)
        except Exception as exc:
            res, loc, switched = None, None, False
            st.error(f"Não consegui responder: {exc}")
    if res is None:
        return
    nt = ""
    if loc is not None:
        nt = (f"📌 Jogo identificado na pergunta: {loc.label}" if switched else f"📌 Jogo da pergunta: {loc.label}")
        if len(loc.candidates) > 1:
            nt += f" · outros confrontos encontrados: {len(loc.candidates) - 1} (troque pelo topo, se quiser outro)"
    history.append({"q": question, "a": res["report_markdown"], "meta": _meta_line(res), "card": res.get("_match_card"),
                    "note": nt, "match_id": int(st.session_state["match_id"]), "llm_error": res.get("llm_error")})
    st.rerun()
