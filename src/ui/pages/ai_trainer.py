"""
Rodada 20 — treino GUIADO da IA do Assistente (funciona também para quem entra pelo link).

Passo a passo na tela:
  1. Pergunte  — perguntas sugeridas (dos tipos que a IA mais erra ou que têm poucos exemplos) abrem no Assistente.
  2. Avalie    — as respostas recentes ainda sem nota: 👍/👎 + o motivo (“número errado”, “não respondeu”…) + comentário.
  3. Treine    — um botão, com os parâmetros que a própria IA sugere; a versão nova só entra se errar menos.
  4. Veja onde melhorar — motivos mais citados, tipos de pergunta com mais 👎, comentários e sugestões.
Nada aqui mexe em dado de jogo: só nas avaliações e nos pesos do seletor de fatos da IA.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.intelligence import learning_hub as LH
from src.ui.components import styled_dataframe

QUESTION_TEMPLATES = [
    ("ranking", "{m}: quem mais criou perigo?"),
    ("ranking", "{m}: quem errou mais passes?"),
    ("erros", "{m}: quais erros viraram chance do adversário?"),
    ("tática", "{m}: qual foi o principal ponto fraco do {t}?"),
    ("tática", "{m}: como explorar a defesa do {t}?"),
    ("jogador", "{m}: quem jogou melhor pela nota?"),
    ("substituição", "{m}: alguma substituição mudou o jogo?"),
    ("resultado", "{m}: por que o {t} venceu ou perdeu?"),
]


def _who() -> str:
    try:
        from src.ui.gate import is_visitor

        return "visitante" if is_visitor() else "dono"
    except Exception:
        return "dono"


def _sample_match() -> tuple:
    """Um jogo recente com estatísticas para preencher as perguntas sugeridas (o último aberto, se houver)."""
    try:
        from src.ui.context import cached_catalog, load_bundle

        ids = st.session_state.get("recent_match_ids") or []
        if ids:
            meta = load_bundle(int(ids[0])).meta or {}
        else:
            c = cached_catalog()
            c = c[c["home_score"].notna()].sort_values("match_date", ascending=False)
            if c.empty:
                return "", ""
            meta = c.iloc[0].to_dict()
        year = str(meta.get("match_date") or "")[:4]
        return f"{meta.get('home_team_name')} x {meta.get('away_team_name')} {year}", str(meta.get("home_team_name") or "")
    except Exception:
        return "", ""


def _ask(q: str) -> None:
    st.session_state["_ask_from_trainer"] = q
    from src.ui import nav

    nav.open_view("assistente")


def render_trainer() -> None:
    from src.intelligence.lab_ai import trainer as TR
    from src.intelligence.lab_ai.selector import Selector

    st.markdown("## 🎓 Treinar a IA do Assistente — passo a passo")
    st.caption("Qualquer pessoa com o link pode ajudar. Você pergunta, avalia a resposta dizendo o que faltou, e aperta "
               "Treinar. A IA aprende a escolher os números que importam para cada tipo de pergunta. A versão nova só "
               "entra se errar menos nas respostas de teste — treinar nunca piora o que já funciona.")
    sel = Selector()
    rep = LH.improvement_report()
    k = st.columns(4)
    k[0].metric("Versão em uso", f"v{sel.version:03d}")
    k[1].metric("Avaliações com motivo", rep["total"])
    k[2].metric("👎 recebidos", rep["negativos"])
    pend = LH.recent_answers(limit=50)
    k[3].metric("Respostas esperando avaliação", len(pend))

    t1, t2, t3, t4 = st.tabs(["1️⃣ Pergunte", "2️⃣ Avalie", "3️⃣ Treine", "4️⃣ Onde melhorar"])
    with t1:
        st.markdown("Clique numa pergunta: ela abre no **Assistente**. Depois volte aqui para avaliar a resposta.")
        m, team = _sample_match()
        worst = [w[0] for w in rep.get("piores_tipos") or []]
        if worst:
            st.caption("Tipos de pergunta com mais 👎 até agora (treine mais deles): " + ", ".join(worst[:3]))
        if m:
            cols = st.columns(2)
            for i, (kind, tpl) in enumerate(QUESTION_TEMPLATES):
                q = tpl.format(m=m, t=team)
                if cols[i % 2].button(f"💬 {q}", key=f"tr_q_{i}", use_container_width=True):
                    _ask(q)
        else:
            st.info("Abra um jogo pelo 🔎 Buscar para receber perguntas sugeridas.")
        with st.form("tr_own_q", border=False):
            own = st.text_input("Ou escreva a sua pergunta (cite os times e o ano)")
            if st.form_submit_button("Perguntar no Assistente", type="primary") and own.strip():
                _ask(own.strip())
    with t2:
        if not pend:
            st.success("Nenhuma resposta esperando avaliação. Faça perguntas no passo 1 e volte aqui.")
        for i, r in enumerate(pend[:5]):
            iid = str(r.get("interaction_id"))
            with st.container(border=True):
                st.markdown(f"**Pergunta:** {r.get('question')}")
                if r.get("match"):
                    st.caption(f"Jogo: {r['match']}")
                with st.expander("Ver a resposta da IA", expanded=(i == 0)):
                    st.markdown(r.get("answer") or "_(resposta vazia)_")
                with st.form(f"tr_rate_{iid}", border=False):
                    vote = st.radio("A resposta foi boa?", ["👍 Boa", "👎 Ruim"], horizontal=True, index=None,
                                    key=f"tr_v_{iid}")
                    reasons = st.multiselect("Se foi ruim, o que faltou? (pode marcar mais de um)", LH.REASONS,
                                             key=f"tr_r_{iid}")
                    comment = st.text_input("Comentário (opcional): o que a resposta deveria dizer?", key=f"tr_c_{iid}")
                    if st.form_submit_button("Enviar avaliação", type="primary"):
                        if vote is None:
                            st.warning("Escolha 👍 ou 👎.")
                        else:
                            good = vote.startswith("👍")
                            LH.record_feedback(iid, 1 if good else 0, note=comment)
                            LH.record_reasons(iid, good, reasons, comment, _who(), r.get("intent"), r.get("question"))
                            try:
                                from src.intelligence import lab_brain as LB

                                LB.feedback("assistente", str(r.get("intent") or r.get("engine") or "resposta")[:60],
                                            good, {"pergunta": str(r.get("question") or "")[:200]})
                            except Exception:
                                pass
                            st.rerun()
        if len(pend) > 5:
            st.caption(f"Mais {len(pend) - 5} respostas na fila — avalie estas e as próximas aparecem.")
    with t3:
        last = sel.meta["versions"][-1] if sel.meta.get("versions") else {}
        sug = TR.suggest(last)
        st.markdown("A IA sugere os próprios ajustes a partir do último treino:")
        for p in sug["porque"]:
            st.markdown(f"- {p}")
        if st.button("🧠 Treinar agora com a sugestão da IA", type="primary", use_container_width=True, key="tr_go"):
            with st.spinner("Treinando…"):
                r = TR.train(learning_rate=sug["sugerido"]["learning_rate"], l2=sug["sugerido"]["l2"],
                             epochs=int(sug["sugerido"]["epochs"]), use_weak=True)
            if r.get("promoted"):
                st.success("✅ A versão nova errou menos nas respostas de teste e passou a ser usada. " + str(r.get("reason")))
            else:
                st.info("A versão atual continua (a nova não foi melhor). " + str(r.get("reason")))
            mt = r.get("metricas") or {}
            if mt:
                c = st.columns(3)
                c[0].metric("Acerto do 1º número", "—" if mt.get("acerto_1o_fato") is None else f"{100 * mt['acerto_1o_fato']:.0f}%")
                c[1].metric("Perguntas no treino", r.get("n_perguntas", 0))
                c[2].metric("Exemplos", r.get("n_exemplos", 0))
                st.caption("Acerto do 1º número = nas perguntas de teste, o primeiro número que a IA mostra é o que a "
                           "pergunta pedia.")
    with t4:
        if not rep["total"]:
            st.info("Ainda sem avaliações com motivo. Use os passos 1 e 2.")
            return
        a, b = st.columns(2)
        with a:
            st.markdown("##### Motivos mais citados nos 👎")
            if rep["motivos"]:
                styled_dataframe(pd.DataFrame(rep["motivos"], columns=["Motivo", "Vezes"]), hide_index=True,
                                 use_container_width=True)
        with b:
            st.markdown("##### Tipos de pergunta com mais 👎")
            if rep["piores_tipos"]:
                styled_dataframe(pd.DataFrame([{"Tipo": t, "👎": n, "Avaliadas": tot, "% ruim": round(100 * n / tot)}
                                               for t, n, tot in rep["piores_tipos"]]), hide_index=True,
                                 use_container_width=True)
        st.markdown("##### O que fazer agora")
        for tip in _tips(rep):
            st.markdown(f"- {tip}")
        if rep["comentarios"]:
            st.markdown("##### Comentários recentes")
            styled_dataframe(pd.DataFrame(rep["comentarios"]).rename(columns={
                "quando": "Quando", "voto": "Voto", "pergunta": "Pergunta", "comentario": "Comentário", "quem": "Quem"}),
                hide_index=True, use_container_width=True)


def _tips(rep) -> list:
    tips = []
    mot = dict(rep.get("motivos") or [])
    if rep.get("total", 0) < 30:
        tips.append(f"Faltam exemplos: com {rep.get('total', 0)} avaliações o treino ainda aprende pouco — a meta é 30+.")
    if mot.get("Não respondeu o que perguntei", 0) >= 2:
        tips.append("A IA está errando o TIPO da pergunta: refaça perguntas parecidas com palavras diferentes e avalie — "
                    "o seletor aprende quais números combinam com cada jeito de perguntar.")
    if mot.get("Número errado", 0) >= 2:
        tips.append("“Número errado” costuma ser jogo ou time errado: confira o jogo mostrado em “📌 Jogo da pergunta”. "
                    "Se o jogo estava certo, deixe no comentário o número que deveria aparecer (vira caso de teste).")
    if mot.get("Faltou explicação tática", 0) >= 2:
        tips.append("Peça o “porquê” na pergunta (ex.: “por que o time X sofreu tanto pelo lado esquerdo?”) e avalie.")
    if mot.get("Texto confuso ou longo demais", 0) >= 2 or mot.get("Repetiu coisas sem importância", 0) >= 2:
        tips.append("Respostas longas demais: avalie com 👎 + esse motivo; o treino passa a preferir menos fatos e mais "
                    "diretos.")
    worst = rep.get("piores_tipos") or []
    if worst:
        tips.append(f"O tipo “{worst[0][0]}” é o que mais recebe 👎 — concentre o próximo treino nele (passo 1).")
    return tips or ["Continue perguntando e avaliando; depois de cada 10 avaliações, aperte Treinar."]
