"""
💬 Assistente — chat único do laboratório.

A pergunta pode trazer o jogo junto ("Na final da Copa de 2022, quem mais criou perigo?"): o localizador encontra a
partida no catálogo, abre e responde nela. Sem jogo citado, a resposta usa a partida aberta (faixa do topo).
Cada resposta passa pelo guard de números; o modelo de perigo campeão é usado quando a pergunta pede.
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from src.intelligence.dynamic_analyst import DynamicTacticalAnalyst
from src.ui.components import hero
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


def _chat_text(value: Any) -> str:
    """Remove apenas marcação HTML de subscrito; o texto útil permanece legível."""
    return re.sub(r"</?sub\b[^>]*>", "", str(value or ""), flags=re.I)


@st.fragment
def _feedback_box(learning_id: str, kind: str, question: str) -> None:
    """Rodada 21: o 👍/👎 refaz só este pedaço (antes recarregava a conversa inteira)."""
    from src.intelligence.learning_hub import record_feedback

    flag = f"_as_voted_{learning_id}"
    if st.session_state.get(flag):
        return
    vote = st.feedback("thumbs", key=f"as_feedback_{learning_id}")
    if vote is not None:
        record_feedback(learning_id, vote)
        st.session_state[flag] = True
        try:                                           # rodada 13: o mesmo voto treina o cérebro único do laboratório
            from src.intelligence import lab_brain as LB

            LB.feedback("assistente", kind, bool(vote), {"pergunta": question})
        except Exception:
            pass
        st.rerun(scope="fragment")


def _answer(question: str, current_context, use_llm: bool):
    from src.intelligence.match_locator import locate
    from src.ui.context import analyzable_only, cached_catalog, get_service

    loc = None
    try:
        from src.ui.context import only_real

        loc = locate(question, cached_catalog(), _index(get_service().db.stable_version(), "|".join(chosen_levels()), only_real()))
    except Exception:
        loc = None
    previous = int(st.session_state.get("match_id") or 0)
    # rodada 27e: o chat fica TRAVADO no jogo aberto; só troca quando a pergunta identifica outro jogo de forma explícita
    from src.intelligence.match_locator import should_switch

    current = None
    if previous:
        try:
            cat = cached_catalog()
            row = cat[cat["match_id"] == previous]
            current = row.iloc[0].to_dict() if not row.empty else {"match_id": previous}
        except Exception:
            current = {"match_id": previous}
    switched = should_switch(question, loc, current, locked=bool(st.session_state.get("as_lock_match", True)))
    if loc is not None and not switched and previous and loc.match_id != previous:
        loc = None                                       # citou times/minuto, mas continua no mesmo jogo
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
    if st.session_state.get("lab_ai_on", True):          # rodada 11: a NOSSA IA responde direto ou não acrescenta nada
        try:
            from src.intelligence.lab_ai import direct as DIRECT
            from src.intelligence.lab_ai import engine as LAB
            from src.ui.names import pt as _pt

            from src.intelligence.lab_ai import reasoning as REASON

            engine = str(res.get("engine_used", ""))
            off_topic = engine.startswith("LOCAL_SCOPE_GUARD")       # o motor normal é LOCAL_SCOPED_ENGINE
            ask = (res.get("scope") or {}).get("ask")
            generic = (not ask) or ask in ("overview", "panorama")

            # rodada 12: a NOSSA IA decide primeiro (roteador de intenções). O analista clássico só fica com o que ele faz
            # melhor (presença, autores dos gols, linha do tempo) ou quando a nossa IA não reconhece a pergunta.
            from src.intelligence.lab_ai import router as ROUTER

            keep_classic = ask in ("presence", "goals", "lineup_role", "errors", "unavailable", "result", "profile")
            # rodada 27e: perguntas de INTERPRETAÇÃO (posse × controle, qualidade das finalizações, faltas, merecimento,
            # correlação × causa…) vão primeiro para o raciocínio que cruza os números do jogo
            reasoned = None
            _topics = REASON.detect(question)
            if ask not in ("presence", "goals", "lineup_role", "unavailable", "profile") or \
                    {"historia", "conselho"} & set(_topics):    # rodada 27i: "por que virou" não é lista de gols
                reasoned = REASON.answer(question, meta, ctx.df, ctx.bundle.boxscore, ctx.target_team,
                                         db=get_service().db, pt=_pt)
            if reasoned is not None:
                res["report_markdown"] = reasoned["markdown"]
                res["engine_used"] = f"IA DO LABORATÓRIO ({reasoned['intent']})"
                res["lab_ai"] = {"direct": reasoned["intent"], "n_facts": 0}
                off_topic, keep_classic = True, True      # já respondido: o roteador não substitui
            routed = None if (off_topic or keep_classic) else ROUTER.route(question, meta, ctx.df, ctx.bundle.boxscore,
                                                                            ctx.target_team, get_service().db, pt=_pt)
            if routed is not None:
                res["report_markdown"] = routed["markdown"]
                res["engine_used"] = f"IA DO LABORATÓRIO ({routed['intent']})"
                res["lab_ai"] = {"direct": routed["intent"], "n_facts": 0}
            elif off_topic or keep_classic:
                pass
            else:
                who = LAB.asked_player(question, ctx.df)
                if who:
                    lab = LAB.answer(question, meta, ctx.df, ctx.bundle.boxscore, ctx.target_team,
                                     db=get_service().db, interaction_id=res.get("interaction_id"))
                    res["report_markdown"] = lab["markdown"]
                    res["engine_used"] = lab["engine"]
                    res["lab_ai"] = {k: lab[k] for k in ("facts", "templates", "version", "n_facts")}
                # sem número reconhecido, sem jogador e sem plano: fica a resposta do analista, sem bloco extra
        except Exception as exc:
            res["lab_ai_error"] = f"{type(exc).__name__}: {exc}"
            try:                                          # registro para diagnóstico (sem dados pessoais)
                import traceback
                from pathlib import Path

                Path("data/learning").mkdir(parents=True, exist_ok=True)
                with open("data/learning/lab_ai_erros.log", "a", encoding="utf-8") as fh:
                    fh.write(traceback.format_exc()[-2000:] + "\n")
            except Exception:
                pass
    # Tags HTML de subscrito não fazem parte do texto conversacional do assistente.
    res["report_markdown"] = _chat_text(res.get("report_markdown"))
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
    ("🧠", "IA do laboratório", "Nossa IA escolhe os números que importam e escreve a análise — e aprende com o seu 👍/👎."),
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
         "Cite o jogo na própria pergunta (times e ano) ou abra o jogo pelo 🔎 Buscar. Cada número da resposta é "
         "conferido contra os dados antes de aparecer.")
    match_bar()
    analyst = DynamicTacticalAnalyst()
    def _go_train():
        st.session_state["bastidores_view"] = "🎓 Treinar a IA (guiado)"
        from src.ui import nav as _nav

        _nav.open_view("treino")

    if st.button("🎓 Ajudar a treinar a IA (avaliar respostas, dizer o que faltou)", key="as_go_train"):
        _go_train()
    with st.expander("Opções do assistente"):
        st.toggle("🧠 IA do laboratório (nossa, aprende com o seu 👍/👎)", value=True, key="lab_ai_on",
                  help="Escolhe os números que importam para a pergunta com uma rede treinada pelas suas avaliações e "
                       "escreve a análise. Desligada, responde só o analista clássico.")
        st.toggle("🔒 Manter o jogo da conversa (só troca se eu citar outro jogo com “x”, placar ou ano)", value=True,
                  key="as_lock_match", help="Evita que uma pergunta como “no último minuto o Atlético…” leve para outro "
                                            "jogo do Atlético. Para trocar: cite os dois times com x/contra e o ano, "
                                            "diga “trocar de jogo”, ou use o botão abaixo.")
        use_llm = st.toggle("Redigir com Gemini (precisa de GEMINI_API_KEY no .env)", value=False)
        if st.button("Limpar conversa"):
            st.session_state["chat_history"] = []
        if st.button("🔄 Trocar de jogo (limpa a conversa e solta o jogo)"):
            st.session_state["chat_history"] = []
            st.session_state["match_id"] = None
            st.rerun()
    history = st.session_state.setdefault("chat_history", [])
    from src.intelligence.learning_hub import feedback_ids, record_feedback

    reviewed = feedback_ids()
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
            st.markdown(_chat_text(h.get("a")))
            learning_id = h.get("learning_id")
            if learning_id and learning_id not in reviewed:
                _feedback_box(learning_id, str(h.get("engine") or h.get("intent") or "resposta")[:60],
                              str(h.get("question") or h.get("q") or "")[:200])
    question = st.chat_input("Pergunte sobre um jogo, um jogador ou uma tática — ex.: “Real Madrid x Barcelona 2018: "
                             "quem mais criou perigo?”") or clicked or st.session_state.pop("_ask_from_trainer", None)
    if not question:
        return
    with st.spinner("Encontrando o jogo, recortando os dados e redigindo..."):
        try:
            res, loc, switched = _answer(question, current_context, use_llm)
        except Exception as exc:
            res, loc, switched = None, None, False
            st.error(f"Não consegui responder: {exc}")
    if res is None:
        if not st.session_state.get("match_id"):
            st.info("Não identifiquei o jogo na pergunta. Cite os dois times (e o ano), por exemplo: "
                    "“Flamengo x Palmeiras 2025: quem mais criou perigo?”, ou abra o jogo pelo 🔎 Buscar.")
        return
    try:                                                 # rodada 20: guarda a resposta para o treino guiado
        from src.intelligence.learning_hub import record_answer

        record_answer(res.get("interaction_id"), question, res.get("report_markdown"), loc.label if loc else "",
                      str(res.get("engine_used") or ""), (res.get("scope") or {}).get("ask"))
    except Exception:
        pass
    history.append({"q": question, "a": res["report_markdown"],
                    "match_id": int(st.session_state.get("match_id") or 0),
                    "learning_id": res.get("interaction_id"), "engine": res.get("engine_used"),
                    "intent": (res.get("scope") or {}).get("ask")})
    st.rerun()
