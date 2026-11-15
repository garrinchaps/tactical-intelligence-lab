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
from src.ui.context import chosen_levels

EXAMPLES = [
    "Na final da Copa de 2022 entre Argentina e França, quem fez os gols?",
    "Argentina x França 2022: qual tática a França deveria usar para evitar a derrota?",
    "Brasil x Inglaterra 1970: o que o Brasil fez para ganhar?",
    "Quem mais criou perigo nesta partida, segundo a rede neural?",
    "Como anular o principal criador do adversário?",
    "Como foi a transição defensiva depois do minuto 60?",
]


@st.cache_data(show_spinner=False, max_entries=4)
def _index(version: str, levels="EVENTS|BOXSCORE", only_real: bool = True):
    from src.intelligence.match_locator import build_index
    from src.ui.context import cached_catalog

    return build_index(cached_catalog() if isinstance(levels, str) else cached_catalog(include_score_only=not levels))


def _meta_line(res) -> str:
    n = res.get("number_tags") or {}
    tot = n.get("exato", 0) + n.get("derivado", 0)
    eng = "Gemini" if str(res.get("engine_used", "")).upper().startswith("GEMINI") else "analista local"
    hidden = f" · {n['ocultadas']} trecho(s) cortado(s) por falta de origem" if n.get("ocultadas") else ""
    lat = res.get("latency_s")
    speed = f" · respondido em {lat:.1f} s" if isinstance(lat, (int, float)) else ""
    return f"✔ {tot} números conferidos com os dados da partida · redigido pelo {eng}{hidden}{speed}"


def _audit_panel(h) -> None:
    rows = h.get("audit") or []
    if not rows and not h.get("llm_error"):
        return
    with st.expander("🔎 Conferência dos números", expanded=False):
        if rows:
            import pandas as pd

            st.caption("EXATO = o número está nos dados · DERIVADO = calculado a partir deles. "
                       "Frases com número sem origem nos dados são cortadas antes de aparecer.")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if h.get("llm_error"):
            st.caption(f"Gemini indisponível nesta resposta: {h['llm_error']}")


def _answer(question: str, current_context, use_llm: bool):
    from src.intelligence.match_locator import locate
    from src.ui.context import analyzable_only, cached_catalog, get_service

    loc = None
    try:
        from src.ui.context import only_real

        loc = locate(question, cached_catalog(), _index(get_service().db.stable_version(), "|".join(chosen_levels()), only_real()))
    except Exception:
        loc = None
    previous = int(st.session_state.get("match_id", 0))
    switched = bool(loc and loc.match_id != previous)
    if switched:
        from src.ui.context import load_bundle

        opened = None
        import time as _time

        t0 = _time.time()
        others = [int(x) for x in loc.candidates["match_id"].tolist() if int(x) != loc.match_id][:2]
        for mid in [loc.match_id] + others:              # no máx. 3 tentativas e ~40 s no total
            if _time.time() - t0 > 40:
                break
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
    from src.guard.present import present

    present(res)                                        # confere os números; trechos sem origem saem do texto
    res["_match_card"] = result_card_html(ctx.bundle.meta or {}, BADGES.get(ctx.bundle.level, ctx.bundle.level))
    return res, loc, switched


def _mentioned(res) -> dict:
    """Jogadores e times citados na resposta → botões que abrem as páginas deles (v36)."""
    ev = res.get("evidence") or {}
    meta = ev.get("metadata") or {}
    text = res.get("report_markdown") or ""
    roster = meta.get("match_player_roster") or []
    players = [p for p in roster if isinstance(p, str) and p and p in text][:6]
    teams = [t for t in (meta.get("target_team"), meta.get("opponent_team")) if isinstance(t, str) and t and t in text]
    return {"chips_p": players, "chips_t": teams}


WELCOME = [
    ("🎯", "Cite o jogo na pergunta", "“Flamengo x Palmeiras 2025: quem finalizou mais?” — o jogo é localizado sozinho."),
    ("📊", "Só números conferidos", "Cada número é checado contra os dados do jogo; frase com número sem origem é cortada."),
    ("🧠", "Modelo campeão", "As respostas de perigo usam sempre a melhor versão treinada da rede neural."),
]


@st.cache_data(show_spinner=False, max_entries=2)
def _level_counts(version: str):
    from src.ui.context import get_service

    return get_service().db.level_counts()


def _db_status() -> None:
    """Faixa com o tamanho real da base (cacheada pelo catálogo)."""
    try:
        from src.ui.context import get_service

        lv = _level_counts(get_service().db.stable_version())
        ev, bx = int(lv.get("EVENTS", 0)), int(lv.get("BOXSCORE", 0))
    except Exception:
        return
    fmt = lambda n: f"{n / 1000:.0f} mil" if n >= 10_000 else f"{n:,}".replace(",", ".")
    kpis = [(fmt(ev + bx), "jogos analisáveis"), (fmt(ev), "com todos os lances e coordenadas"),
            (fmt(bx), "com estatísticas da partida"), ("3 h", "atualização automática")]
    cells = "".join(f'<div style="flex:1;min-width:140px"><div style="font-family:Space Grotesk,sans-serif;font-size:1.5rem;'
                    f'font-weight:700;color:#22D3EE">{v}</div><div style="color:#94A3B8;font-size:.8rem">{l}</div></div>'
                    for v, l in kpis)
    st.markdown(f'<div class="fm-card fm-card-blue" style="display:flex;gap:1rem;flex-wrap:wrap">{cells}</div>',
                unsafe_allow_html=True)


def render(current_context, match_bar) -> None:
    hero("Assistente tático", "Pergunte qualquer coisa sobre futebol",
         "Cite o jogo na própria pergunta (times e ano) ou use a partida aberta no topo. Cada número da resposta é "
         "conferido contra os dados antes de aparecer.")
    _db_status()
    match_bar()
    analyst = DynamicTacticalAnalyst()
    with st.expander("Opções do assistente"):
        use_llm = st.toggle("Redigir com Gemini (precisa de GEMINI_API_KEY no .env)", value=analyst.api_key is not None)
        if st.button("Limpar conversa"):
            st.session_state["chat_history"] = []
    history = st.session_state.setdefault("chat_history", [])
    clicked = None
    if not history:
        w = st.columns(3)
        for col, (ic, t, d) in zip(w, WELCOME):
            col.markdown(f'<div class="til-card fm-card"><div class="h">{ic} {t}</div><div style="color:#94A3B8;font-size:.88rem">{d}</div></div>',
                         unsafe_allow_html=True)
        st.markdown("##### Experimente")
        cols = st.columns(3)
        for i, e in enumerate(EXAMPLES):
            if cols[i % 3].button(e, key=f"as_ex_{i}", use_container_width=True):
                clicked = e
    for hi, h in enumerate(history):
        with st.chat_message("user", avatar="🧑‍💼"):
            st.markdown(h["q"])
        with st.chat_message("assistant", avatar="⚽"):
            if h.get("card"):
                st.markdown(h["card"], unsafe_allow_html=True)
            if h.get("note"):
                st.caption(h["note"])
            st.markdown(h["a"])
            st.caption(h["meta"])
            if h.get("chips_p") or h.get("chips_t"):
                from src.ui.components import entity_chips

                entity_chips(h.get("chips_p") or [], h.get("chips_t") or [], key=f"as_chip_{hi}")
            _audit_panel(h)
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
                    "note": nt, "match_id": int(st.session_state["match_id"]), "llm_error": res.get("llm_error"),
                    "audit": (res.get("number_tags") or {}).get("linhas", []), **_mentioned(res)})
    st.rerun()
