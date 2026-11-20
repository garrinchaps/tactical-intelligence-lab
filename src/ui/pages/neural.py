"""Página 4 — Rede Neural do Zero (NumPy): arquitetura, treino ao vivo, curva de perda, pais → filhos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.ui.components import render_chart, styled_dataframe
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from src.machine_learning.danger_dataset import FEATURES
from src.machine_learning.neural_net import NeuralNetwork
from src.ui import charts
from src.ui.components import comparison_table, empty_state, kpi, note, page_header, provenance_panel
from src.ui.gate import visitor_blocked as _vb

SAMPLE = Path("data/demo/danger_sample_wc2022.csv.gz")
SAVED = Path("models/trained/danger_nn.npz")


@st.cache_data(show_spinner=False)
def _data():
    d = pd.read_csv(SAMPLE)
    if "density_is_360" not in d:
        d["density_is_360"] = d["density_source"].eq("statsbomb_360").astype(float) if "density_source" in d else 0.0
    return d


def _didactic() -> None:
    from src.machine_learning.model_registry import model_card
    from src.ui.components import steps_html

    st.markdown("### Em 30 segundos")
    st.markdown("A cada passe ou condução de bola, a rede responde uma pergunta só: **qual a chance de esta posse terminar "
                "em finalização?** Ela aprendeu isso olhando milhares de jogadas reais da Copa de 2022 e vendo quais "
                "terminaram em chute. O Assistente usa essa chance para dizer quem criou mais perigo e de onde ele saiu.")
    card = None
    try:
        card = model_card()
    except Exception:
        pass
    if card:
        c = st.columns(4)
        c[0].metric("Versão em uso", card["versao"])
        c[1].metric("Jogos usados no treino", card["partidas_de_treino"])
        c[2].metric("Acerto na prova (AUC)", card["auc_validacao"])
        c[3].metric("Treinada em", card["treinado_em"])
        st.caption("AUC: 0,5 = chute no escuro; 1,0 = acerta sempre. Para perigo de posse, com dados abertos, valores entre "
                   "0,6 e 0,7 são o normal da literatura.")
    st.markdown("### Passo a passo")
    st.markdown(steps_html([
        ("O que a rede vê",
         "Cada jogada vira 15 números: <b>distância</b> e <b>ângulo</b> até o gol, quantos <b>adversários estão a 5 m</b> "
         "(tracking 360 medido ou estimativa por eventos), quantos <b>passes</b> a posse já teve, o <b>placar</b>, a "
         "<b>zona do campo</b> e um indicador que informa se a densidade veio do 360. O modelo não confunde medida com estimativa."),
        ("O neurônio: uma soma com pesos",
         "Cada neurônio multiplica esses números por <b>pesos</b> (o quanto cada coisa importa), soma tudo e decide se "
         "“acende”. Ex.: perto do gol e com poucos marcadores → soma alta. A rede tem 2 camadas escondidas (32 e 16 "
         "neurônios) que combinam essas pistas e uma saída que dá a chance de 0% a 100%."),
        ("Aprender = errar menos",
         "No começo os pesos são aleatórios e a rede chuta. Para cada jogada ela compara o palpite com o que aconteceu "
         "(teve chute ou não) e mede o erro — a <b>perda</b>. O objetivo do treino é fazer essa perda cair."),
        ("Backpropagation: quem teve culpa no erro",
         "Depois de cada lote de jogadas, o erro é “devolvido” da saída para trás: cada peso recebe a parcela de culpa "
         "que teve e é ajustado um pouquinho na direção que diminui o erro (<b>descida do gradiente</b>). Repetir isso "
         "milhares de vezes é o que chamamos de treinar. Tudo foi escrito do zero, sem biblioteca pronta de IA."),
        ("Uma validação separada por partida",
         "Partidas inteiras ficam fora do treino e são usadas para comparar versões. Como esse conjunto participa da escolha "
         "do campeão, ele é uma validação de promoção — não um teste final externo intocado."),
        ("Guardamos sempre a melhor",
         "Cada treino gera uma versão. Ela só vira a <b>versão oficial</b> se errar menos na prova do que a atual; senão "
         "fica registrada como rejeitada. O Assistente sempre usa a oficial e diz qual é em cada resposta."),
        ("Por que ela melhora",
         "Treinar de novo nos mesmos dados quase não muda nada (a prova mostra isso). O que faz a rede aprender é ter "
         "<b>mais jogos</b> para estudar — a curva de aprendizado lá embaixo mostra o erro caindo quando entram mais partidas."),
        ("Onde aparece no programa",
         "No Assistente: “quem mais criou perigo?”, nos planos “como anular o jogador X?” (de onde saem as jogadas perigosas "
         "dele) e “que tática a equipe Y deveria usar?” (por onde o adversário cria perigo)."),
    ]), unsafe_allow_html=True)


def _simulator() -> None:
    """Uma jogada inventada pelo usuário → chance de terminar em chute segundo a versão oficial."""
    import numpy as np

    from src.machine_learning.danger_dataset import FEATURES, LEGACY_FEATURES, ZONE_COLS, _zone_onehot
    from src.machine_learning.model_registry import champion_cached

    st.markdown("### 🎮 Teste a rede com uma jogada")
    net = champion_cached()
    if net is None:
        st.caption("Ainda não há versão treinada.")
        return
    a, b, c, d = st.columns(4)
    x_m = a.slider("Distância até a linha de fundo adversária (m)", 2, 100, 25)
    lane = b.select_slider("Corredor", ["esquerda", "centro-esquerda", "centro", "centro-direita", "direita"], "centro")
    dens = c.slider("Adversários a 5 m", 0, 6, 1)
    passes = d.slider("Passes já feitos na posse", 0, 15, 4)
    score = st.select_slider("Placar para quem tem a bola", ["perdendo por 2+", "perdendo por 1", "empatando",
                                                             "ganhando por 1", "ganhando por 2+"], "empatando")
    x = 120 - x_m / 0.9144
    y = {"esquerda": 8, "centro-esquerda": 26, "centro": 40, "centro-direita": 54, "direita": 72}[lane]
    dx = max(120 - x, 0.1)
    dist = float(np.hypot(dx, 40 - y) * 0.9144)
    ang = float(np.degrees(abs(np.arctan2(44 - y, dx) - np.arctan2(36 - y, dx))))
    sd = {"perdendo por 2+": -2, "perdendo por 1": -1, "empatando": 0, "ganhando por 1": 1, "ganhando por 2+": 2}[score]
    z = _zone_onehot(np.array([x]), np.array([float(y)]))
    density_origin = st.selectbox("Origem da densidade", ["Tracking 360 medido", "Estimativa por eventos"], index=0)
    values = {"dist_to_goal_m": dist, "angle_to_goal_deg": ang, "opp_density_5m": dens, "passes_so_far": passes,
              "score_diff": sd, "density_is_360": float(density_origin == "Tracking 360 medido")}
    values.update({name: float(z[name][0]) for name in ZONE_COLS})
    from src.machine_learning.danger_dataset import LEGACY_FEATURES
    names = list(getattr(net, "feature_names", []) or [])
    if not names or any(name.startswith("x") for name in names):
        names = FEATURES if net.layer_sizes[0] == len(FEATURES) else LEGACY_FEATURES
    feats = [values.get(name, 0.0) for name in names]
    p = float(net.predict_proba(np.array([feats]))[0])
    col1, col2 = st.columns([1, 2])
    col1.metric("Chance de a posse terminar em finalização", f"{100 * p:.1f}%")
    col2.markdown(f"Distância real ao gol: **{dist:.1f} m**, ângulo de visão do gol: **{ang:.1f}°**. "
                  "Mexa nos controles: chegar mais perto e pelo centro aumenta a chance; mais marcadores por perto, em "
                  "geral, diminuem. É exatamente esse número, calculado para cada jogada real, que o Assistente soma "
                  "para dizer quem criou mais perigo.")


def _speed_panel() -> None:
    """Rodada 16: monitor de velocidade — cada tela aberta e cada função pesada, com meta e alerta."""
    import plotly.graph_objects as go

    from src.ui import perf as P

    st.markdown("## ⏱️ Velocidade do app")
    st.caption(f"Cada tela e cada análise pesada é cronometrada e guardada em data/perf.jsonl (só neste PC). Meta: tela em "
               f"até {P.GOAL_PAGE_S:.0f} s e análise em até {P.GOAL_FUNC_S:.0f} s (com a análise já guardada). A primeira "
               "abertura de um time/jogo sempre demora mais — depois disso fica guardada em disco.")
    from src.ui import warmup as W

    ws = W.state()
    if ws.get("steps"):
        tot = sum(x.get("s") or 0 for x in ws["steps"])
        with st.expander(f"🔥 Pré-aquecimento ao ligar o app — {len(ws['steps'])} passos, {tot:.0f} s"
                         + (" (rodando…)" if ws.get("running") else ""), expanded=False):
            st.caption("Calculado em segundo plano assim que o app liga: catálogo, Scout, Rankings, índice de jogadores e "
                       "os jogos/times abertos por último (data/recent_views.json). Quem entra depois encontra pronto.")
            styled_dataframe(pd.DataFrame([{"Passo": x["nome"], "Situação": x["status"], "Segundos": x.get("s")}
                                           for x in ws["steps"]]), hide_index=True, use_container_width=True)
    rows = P.read()
    if not rows:
        st.info("Ainda sem medições — navegue pelo app e volte aqui.")
        return
    sm = P.summary(rows)
    telas, funcs = sm[sm["tipo"] == "tela"], sm[sm["tipo"] == "funcao"]
    k = st.columns(4)
    k[0].metric("Medições", len(rows))
    k[1].metric("Telas dentro da meta", f"{(telas['situação'].str.startswith('✅')).mean() * 100:.0f}%" if len(telas) else "—")
    k[2].metric("Tela mais lenta (90%)", f"{telas['p90_s'].max():.1f} s" if len(telas) else "—")
    k[3].metric("Análise mais lenta (90%)", f"{funcs['p90_s'].max():.1f} s" if len(funcs) else "—")

    d = pd.DataFrame(rows).tail(300)
    if not d.empty:
        fig = go.Figure()
        for kind, color in (("tela", "#22D3EE"), ("funcao", "#A78BFA")):
            x = d[d["tipo"] == kind]
            fig.add_scatter(x=list(range(len(x))), y=x["s"], mode="markers", name=kind, marker=dict(color=color, size=6),
                            text=x["nome"], hovertemplate="%{text}: %{y:.2f} s<extra></extra>")
        fig.add_hline(y=P.GOAL_PAGE_S, line_dash="dot", line_color="#EF4444", annotation_text="meta da tela")
        fig.update_layout(height=260, paper_bgcolor="#090D16", plot_bgcolor="#0B1120", font=dict(color="#F5F7FB"),
                          margin=dict(l=40, r=10, t=20, b=30), yaxis_title="segundos")
        st.plotly_chart(fig, use_container_width=True, key="perf_scatter")
    st.markdown("#### Telas")
    styled_dataframe(telas.drop(columns="tipo").rename(columns={"nome": "tela"}), hide_index=True, use_container_width=True)
    st.markdown("#### Análises pesadas")
    styled_dataframe(funcs.drop(columns="tipo").rename(columns={"nome": "análise"}), hide_index=True, use_container_width=True)
    slow = sm[sm["situação"].str.startswith("🔴")]
    if len(slow):
        st.warning("Lentas: " + ", ".join(slow["nome"].head(6)) + ". Se uma delas for sempre lenta (não só na 1ª vez), "
                   "me diga o nome que eu otimizo aquela parte.")
    if st.button("🧹 Zerar medições", key="perf_reset") and not _vb("Zerar medições"):
        try:
            P.PATH.unlink()
        except OSError:
            pass
        st.rerun()


def _brain_panel() -> None:
    """Rodada 13: uma IA só, com módulos; um botão treina tudo; o 👍/👎 de qualquer tela entra aqui."""
    import pandas as pd

    from src.intelligence import lab_brain as LB

    st.markdown("## 🧠 A IA do laboratório é uma só")
    st.markdown("Ela tem **módulos** (como um time tem setores), mas é **um sistema único**: os mesmos dados, a mesma "
                "régua da base e o mesmo lugar para aprender com você. Cada 👍/👎 que você dá — no Assistente, nos "
                "confrontos do pré-jogo — muda o peso daquele tipo de análise na próxima vez. O botão abaixo treina "
                "**todos** os módulos de uma vez, cada um com o seu método.")
    mods = pd.DataFrame([
        {"módulo": "Entender a pergunta e escolher os fatos (Assistente)", "como aprende": "regressão logística com seus 👍/👎",
         "o que o treino faz": "promove nova versão só se errar menos no teste"},
        {"módulo": "Perigo de cada ação (rede neural)", "como aprende": "descida do gradiente (Adam) nos lances",
         "o que o treino faz": "usa os parâmetros que a própria IA sugere a partir do último treino"},
        {"módulo": "Que análise mostrar primeiro (todas as telas)", "como aprende": "reforço: contagem de aprovações por tipo",
         "o que o treino faz": "a cada voto, na hora (não precisa de botão)"},
        {"módulo": "Confrontos do pré-jogo", "como aprende": "régua da base + lógica fuzzy + seus votos",
         "o que o treino faz": "refaz a régua dos jogadores"},
        {"módulo": "Escalação contra o rival", "como aprende": "algoritmo genético (busca, não treino)",
         "o que o treino faz": "usa a régua nova automaticamente"},
    ])
    styled_dataframe(mods, hide_index=True, use_container_width=True)
    if st.button("🧠 Treinar tudo agora", type="primary", use_container_width=True, key="brain_train_all") and not _vb("O treino"):
        from src.ui.context import get_service

        box = st.empty()
        res = LB.train_all(get_service().db, progress=lambda m: box.info(f"Treinando: {m}"))
        box.empty()
        styled_dataframe(pd.DataFrame(res), hide_index=True, use_container_width=True)
        st.success("Treino geral concluído. Cada módulo mostra o resultado acima (rejeitar uma versão também é resultado: "
                   "o app só troca o que ficou melhor).")
    rows = LB.table()
    with st.expander(f"O que a IA já aprendeu com seus votos ({len(rows)} tipos de análise)"):
        if rows:
            styled_dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.caption("Peso 1,00 = neutro. Acima de 1 sobe na lista; abaixo de 1 desce. Começa neutro e muda devagar.")
        else:
            st.caption("Ainda sem votos. Dê 👍/👎 nas respostas do Assistente e nos confrontos do pré-jogo.")


@st.fragment(run_every=3)
def _assistant_train_status() -> None:
    from src.intelligence.lab_ai import trainer as TR
    import pandas as pd

    stt = TR.background_status()
    if not stt:
        return
    if stt.get("estado") == "rodando":
        st.info(f"⏳ Treinando: {stt.get('passo', '')}")
    elif stt.get("estado") == "erro":
        st.error(f"Treino parou com erro: {stt.get('erro')}")
    elif stt.get("estado") == "pronto" and stt.get("resultado"):
        res = pd.DataFrame(stt["resultado"])
        st.success("Experimentos concluídos." + (" Uma versão nova foi promovida." if res["promoted"].any() else
                                                " Nenhuma superou a versão em uso (ela continua)."))
        styled_dataframe(res.rename(columns={"experimento": "Experimento", "tentativa": "Tentativa", "version": "Versão",
                                             "promoted": "Promovida", "acerto_1o_fato": "Acerto do 1º fato",
                                             "perda_validacao": "Perda (prova)", "reason": "Resultado"}),
                         hide_index=True, use_container_width=True)


def _lab_ai_panel() -> None:
    """Rodada 9: a IA do laboratório (o assistente) — versão, o que ela olha, treino com as avaliações."""
    import pandas as pd

    from src.intelligence.lab_ai import reference as LR
    from src.intelligence.lab_ai.selector import MIN_RATED, Selector
    from src.ui.components import comparison_table

    st.markdown("## 🧠 IA do laboratório — o assistente")
    st.caption("Ela transforma qualquer jogo (lances ou estatísticas) em fatos com régua da base, escolhe os que importam "
               "para a pergunta com uma rede treinada pelas suas avaliações 👍/👎 e escreve a análise. Os números vêm "
               "direto dos dados; o treino só promove uma versão nova se ela errar menos em respostas de teste.")
    sel = Selector()
    X, y, g, _ = Selector.dataset()
    n_rated = len(set(g.tolist())) if len(g) else 0
    c = st.columns(4)
    c[0].metric("Versão em uso", f"v{sel.version:03d}")
    c[1].metric("Respostas avaliadas", n_rated)
    c[2].metric("👍 / 👎 (fatos)", f"{int(y.sum())} / {int(len(y) - y.sum())}" if len(y) else "0 / 0")
    ref = LR.load()
    c[3].metric("Régua da base", f"{len(ref)} números")
    # rodada 13: treino no mesmo molde da rede de perigo — hiperparâmetros, curva treino × validação, versões
    from src.intelligence.lab_ai import trainer as TR

    st.markdown("#### 🏋️ Treinar a IA do Assistente (como a rede de perigo)")
    last = sel.meta["versions"][-1] if sel.meta.get("versions") else {}
    sug = TR.suggest(last)
    st.caption("Sugestão da própria IA a partir do último treino: " + " · ".join(sug["porque"]))
    # rodada 25b: cada controle com o (i) — o que é, alto × baixo e a recomendação para o estado atual
    try:
        n_q = len(set(TR.build_dataset()[3].tolist()))
    except Exception:
        n_q = 0
    rec = TR.recommend(last, n_q, n_rated)
    rec_n = TR.recommend_net(n_q, n_rated)

    def _h(key):
        lab, _lo, _hi, _d, expl = TR.PARAMS[key]
        return f"{expl}\n\n👉 {rec.get(key, '')}"

    h1, h2, h3, h4 = st.columns(4)
    lr = h1.select_slider("Taxa de aprendizado (η)", [0.001, 0.003, 0.01, 0.03, 0.05, 0.1, 0.2, 0.5], value=min(
        [0.001, 0.003, 0.01, 0.03, 0.05, 0.1, 0.2, 0.5], key=lambda v: abs(v - sug["sugerido"]["learning_rate"])),
        key="as_lr", help=_h("learning_rate"))
    l2 = h2.select_slider("Regularização L2 (λ)", [0.0, 0.001, 0.01, 0.05, 0.1, 0.5, 1.0], value=min(
        [0.0, 0.001, 0.01, 0.05, 0.1, 0.5, 1.0], key=lambda v: abs(v - sug["sugerido"]["l2"])), key="as_l2",
        help=_h("l2"))
    ep = h3.slider("Épocas (máximo)", 5, 1000, int(min(max(sug["sugerido"]["epochs"], 5), 1000)), 5, key="as_ep",
                   help=_h("epochs"))
    weak = h4.toggle("Usar rótulo automático", value=True, key="as_weak",
                     help="Perguntas que pedem um número reconhecível viram exemplos de treino sozinhas.")
    a1, a2, a3, a4 = st.columns(4)
    hidden_txt = a1.text_input("Neurônios por camada oculta", "", placeholder="vazio = 1 neurônio · ex.: 8  ou  16, 8",
                               key="as_hidden", help=f"{TR.NET_HELP['hidden'][1]}\n\n👉 {rec_n['hidden']}")
    batch = a2.select_slider("Tamanho do lote", [16, 32, 64, 128, 256, 512], value=64 if n_q < 80 else 128,
                             key="as_batch", help=f"{TR.NET_HELP['batch'][1]}\n\n👉 {rec_n['batch']}")
    exps = a3.multiselect("Experimentos a rodar (na ordem)", list(TR.EXPERIMENTS), default=["A", "B"],
                          format_func=lambda k: f"{k} — {TR.EXPERIMENTS[k]['rotulo']}", key="as_exps",
                          help=f"{TR.NET_HELP['experiments'][1]}\n\n👉 {rec_n['experiments']}")
    tries = a4.number_input("Tentativas por clique", 1, 5, 2 if n_q < 80 else 1, key="as_tries",
                            help=f"{TR.NET_HELP['attempts'][1]}\n\n👉 {rec_n['attempts']}")
    try:
        custom = [int(x) for x in hidden_txt.replace(";", ",").split(",") if x.strip()] if hidden_txt.strip() else None
        assert custom is None or all(0 < h <= 128 for h in custom)
    except Exception:
        custom = None
        st.warning("Neurônios: números inteiros de 1 a 128 separados por vírgula (ex.: 16, 8).")
    if st.button("🧪 Rodar experimentos (em segundo plano)", use_container_width=True, key="as_exp_go") and not _vb("O treino"):
        ok = TR.start_background(names=exps, attempts=int(tries), learning_rate=float(lr), epochs=int(ep), l2=float(l2),
                                 batch=int(batch), custom_hidden=custom, use_weak=weak)
        st.toast("Treino iniciado em segundo plano — pode continuar usando o app." if ok else
                 "Já existe um treino rodando; espere terminar.")
    st.caption("O treino roda em segundo plano (a tela não trava). Cada experimento usa Adam, parada antecipada e a "
               "MESMA prova (perguntas separadas); a versão em uso só é trocada se errar menos e não acertar menos o 1º "
               "fato. Vazio em 'Neurônios' = 1 neurônio (regressão logística, o modelo de hoje).")
    _assistant_train_status()
    b1, b2 = st.columns(2)
    if b1.button("🧠 Treinar a IA do Assistente", type="primary", use_container_width=True) and not _vb("O treino"):
        with st.spinner("Treinando (descida do gradiente com parada antecipada)…"):
            r = TR.train(learning_rate=lr, l2=l2, epochs=ep, use_weak=weak)
        (st.success if r.get("promoted") else st.info)(
            f"{r['reason']}" + (f" · {r['n_perguntas']} perguntas, {r['n_exemplos']} exemplos, "
                                f"{r.get('epochs_run', 0)} épocas" if r.get("n_exemplos") else ""))
        if r.get("metricas"):
            mn, mo = r["metricas"], r.get("metricas_campea") or {}
            fmt = lambda v: "—" if v is None else f"{100 * v:.1f}%"
            k = st.columns(4)
            k[0].metric("Acerto do 1º fato", fmt(mn.get("acerto_1o_fato")),
                        None if mo.get("acerto_1o_fato") is None or mn.get("acerto_1o_fato") is None else
                        f"{100 * (mn['acerto_1o_fato'] - mo['acerto_1o_fato']):+.1f} pts vs atual")
            k[1].metric("AUC", "—" if mn.get("auc") is None else f"{mn['auc']:.3f}")
            k[2].metric("F1", fmt(mn.get("f1")))
            k[3].metric("Perda (validação)", f"{mn['logloss']:.4f}", f"{mn['logloss'] - mo.get('logloss', mn['logloss']):+.4f}",
                        delta_color="inverse")
            st.caption("Acerto do 1º fato = nas perguntas de validação, o número que a IA põe em primeiro é o que a pergunta "
                       "pedia? É a métrica que mais se parece com 'a resposta veio certa'.")
        sel = Selector()
    if b2.button("🎲 Busca automática de parâmetros (validação cruzada, 5 dobras)", use_container_width=True, key="as_auto") and not _vb("A busca de parâmetros"):
        with st.spinner("Testando 9 combinações de η e λ, cada uma em 5 dobras por pergunta…"):
            grid = TR.auto_search(use_weak=weak)
        if grid:
            styled_dataframe(pd.DataFrame(grid).rename(columns={"acerto_medio": "acerto do 1º fato (média)",
                             "acerto_desvio": "desvio", "perda_media": "perda (média)", "perda_desvio": "desvio da perda"}),
                             hide_index=True, use_container_width=True)
            st.success(f"Melhor combinação: η {grid[0]['η']} · λ {grid[0]['λ']} — use nos controles acima e clique em Treinar.")
        else:
            st.info("Poucas perguntas com rótulo para 5 dobras (são precisas pelo menos 10). Faça perguntas que pedem um "
                    "número ou avalie respostas.")
    hist_v = [v for v in sel.meta.get("versions", []) if v.get("history")]
    if hist_v:
        import plotly.graph_objects as go

        hv = hist_v[-1]
        fig = go.Figure()
        fig.add_scatter(y=hv["history"]["train_loss"], name="treino", line=dict(color="#3B82F6"))
        fig.add_scatter(y=hv["history"]["val_loss"], name="validação", line=dict(color="#EF4444"))
        fig.update_layout(height=260, paper_bgcolor="#090D16", plot_bgcolor="#0B1120", font=dict(color="#F5F7FB"),
                          title=f"Curva do último treino (v{hv['version']:03d})", margin=dict(l=40, r=10, t=40, b=30))
        st.plotly_chart(fig, use_container_width=True, key="as_curve")
        st.caption(f"Diagnóstico: {TR.suggest(hv)['diagnostico']['texto']}")
    if st.button("📏 Refazer a régua da base (milhares de jogos)", use_container_width=True) and not _vb("Refazer a régua"):
        from src.ui.context import get_service

        with st.spinner("Lendo as estatísticas dos jogos mais recentes…"):
            ref = LR.build(get_service().db)
        st.success(f"Régua refeita: {len(ref)} números.")
    if n_rated < MIN_RATED:
        st.caption(f"{n_rated} respostas avaliadas com 👍/👎 — o treino já funciona com o rótulo automático; cada "
                   "avaliação a mais pesa 3 vezes.")
    with st.expander("O que a IA olha para escolher os números (pesos da versão em uso)"):
        comparison_table(pd.DataFrame(sel.weight_table()), "Peso positivo = aumenta a chance de o fato entrar na resposta.")
        hist = pd.DataFrame([{k: v for k, v in x.items() if k not in ("weights", "history")} for x in sel.meta["versions"]])
        comparison_table(hist, "Histórico de versões.")


def render(ctx=None) -> None:
    from src.ui.components import hero, steps_html

    hero("Bastidores · como a IA aprende", "A matéria de Introdução à IA aplicada ao futebol",
         "Lógica fuzzy, redes neurais e algoritmo genético — cada questão da matéria calculada com os modelos que "
         "realmente decidem o que o programa mostra. Nada aqui é ilustração solta: os números vêm do app.")
    from src.ui.gate import is_owner

    parts = ["📚 A matéria aplicada", "🎓 Treinar a IA (guiado)", "🧠 IA única (treinar tudo)",
             "🎯 Rede de perigo (treino)", "⏱️ Velocidade do app"] + (["👥 Contas"] if is_owner() else [])
    view = st.segmented_control("Parte", parts, default="📚 A matéria aplicada", key="bastidores_view",
                                label_visibility="collapsed")
    if view == "👥 Contas":                            # rodada 21: quem criou conta / entrou pelo link
        from src.ui.pages.accounts_view import render_accounts

        render_accounts()
        return
    if view == "🎓 Treinar a IA (guiado)":            # rodada 20: liberado também para quem entra pelo link
        from src.ui.pages.ai_trainer import render_trainer

        render_trainer()
        return
    if view == "⏱️ Velocidade do app":
        _speed_panel()
        return
    if view == "🧠 IA única (treinar tudo)":
        _brain_panel()
        st.markdown("---")
        _lab_ai_panel()
        _assistant_misses()
        _learning_activity_panel()
        return
    if view != "🎯 Rede de perigo (treino)":
        from src.ui.pages.course_view import render_course

        render_course()
        return
    _danger_section(ctx)


def _danger_section(ctx=None) -> None:
    """Rodada 25: o painel COMPLETO da rede de perigo (didática, simulador, comparação, hiperparâmetros,
    experimentos, histórico) — aparece na aba própria e também dentro de "IA única (treinar tudo)"."""
    _didactic()
    _simulator()
    st.markdown("---")
    _benchmark()
    st.markdown("---")
    st.markdown("## 🔧 Por dentro (parte técnica)")
    note("Objetivo didático", "A rede resolve a mesma tarefa do XGBoost (perigo de posse) para comparação direta. "
         "Ficar abaixo do XGBoost seria esperado: o objetivo é mostrar como o aprendizado acontece, não superar o estado da arte.")
    with st.expander("📐 Como a rede aprende (fórmulas implementadas em src/machine_learning/neural_net.py)", expanded=False):
        st.markdown(r"""
- **Inicialização de He:** $W \sim \mathcal{N}(0, \sqrt{2/n_{entrada}})$ — mantém a variância das ativações com ReLU; vieses = 0.
- **Forward:** $Z_l = A_{l-1}W_l + b_l$; $A_l = \mathrm{ReLU}(Z_l)$ nas ocultas e $\sigma(Z_L)$ na saída.
- **Perda:** entropia cruzada binária $-\frac{1}{m}\sum y\log\hat y + (1-y)\log(1-\hat y)$ + $\frac{\lambda}{2}\sum\|W\|^2$.
- **Backpropagation:** $dZ_L = \hat y - y$; $dW_l = A_{l-1}^\top dZ_l/m + \lambda W_l$; $db_l = \sum dZ_l/m$;
  $dZ_{l-1} = (dZ_l W_l^\top)\odot \mathbb{1}[Z_{l-1}>0]$.
- **Atualização:** Adam ($\beta_1$ 0,9 · $\beta_2$ 0,999) em mini-lotes; parada antecipada numa fatia de partidas do
  próprio treino (guarda a melhor época).
- **Padronização:** média e desvio calculados só com o treino (em cada dobra do GroupKFold, só com o treino da dobra).
- **Verificação:** o teste `test_gradient_check` compara o gradiente analítico com diferenças centrais
  $(L(w+\varepsilon)-L(w-\varepsilon))/2\varepsilon$.
""")
    if not SAMPLE.exists():
        empty_state("Amostra de treino não encontrada", str(SAMPLE), "🧠")
        return
    data = _data()

    st.markdown("### Hiperparâmetros")
    a, b, c, d, e = st.columns(5)
    hidden_txt = a.text_input("Neurônios por camada oculta", "32, 16", help="ex.: 32, 16  ou  8")
    lr = b.select_slider("Taxa de aprendizado (η, Adam)", [0.001, 0.003, 0.005, 0.01, 0.02, 0.05], value=0.01,
                         help="Otimizador Adam: converge em poucas épocas; a parada antecipada guarda a melhor época.")
    epochs = c.slider("Épocas (máximo)", 5, 100, 30, help="A parada antecipada interrompe antes se a rede parar de melhorar.")
    l2 = d.select_slider("Regularização L2 (λ)", [0.0, 1e-4, 1e-3, 1e-2], value=1e-3)
    batch = e.select_slider("Tamanho do lote", [64, 128, 256, 512], value=256)
    try:
        hidden = [int(h) for h in hidden_txt.replace(";", ",").split(",") if h.strip()]
        assert hidden and all(0 < h <= 256 for h in hidden)
    except Exception:
        st.warning("Informe números inteiros entre 1 e 256 separados por vírgula (ex.: 32, 16).")
        return
    layers = [len(FEATURES)] + hidden + [1]

    from src.machine_learning.model_registry import DangerModelRegistry, champion_cached, db_rows

    reg = DangerModelRegistry()
    champion_cached()                                    # garante a v001 na primeira execução
    t1, t2 = st.columns(2)
    use_db = t1.toggle("Incluir partidas do banco com eventos (o conjunto cresce com a sincronização)", value=True)
    use_proxy = t2.toggle("Incluir também jogos sem 360 (densidade estimada por eventos)", value=True,
                          help="Amplia a base com eventos do OpenPlay, Wyscout e StatsBomb sem freeze frame. O campo "
                               "density_is_360 informa a origem; a estimativa não é apresentada como tracking medido.")
    st.caption(
        "Importante: esta rede prevê se uma posse termina em finalização e precisa de eventos em sequência. "
        "Por isso usa partidas com lances (StatsBomb, Wyscout e OpenPlay), não jogos que tenham apenas placar ou "
        "estatísticas agregadas da FotMob. A conversão prepara até 500 partidas inéditas por rodada; as já "
        "convertidas ficam no cache e entram nos treinos seguintes. Os jogos só com estatísticas continuam "
        "disponíveis para o Analista FotMob, ratings e comparações."
    )
    from src.machine_learning.model_registry import (EXP_BATCH, EXP_EPOCHS, EXP_PATIENCE, EXPERIMENT_ORDER,
                                                     EXPERIMENTS, class_balance, feature_report)

    st.markdown("#### 🧪 Experimentos controlados")
    st.caption(f"Todos com Adam, até {EXP_EPOCHS} épocas, lote {EXP_BATCH}, parada antecipada com paciência "
               f"{EXP_PATIENCE}, inicialização He e treino do zero. O campeão só é trocado com superioridade estatística.")
    styled_dataframe(__import__("pandas").DataFrame([
        {"experimento": k, "arquitetura": " → ".join(map(str, [len(v.get("features") or FEATURES), *v["hidden"], 1])),
         "variáveis": ", ".join(v["features"]) if v.get("features") else f"todas as {len(FEATURES)}",
         "η": v["learning_rate"], "λ": v["l2"]} for k, v in EXPERIMENTS.items()]), hide_index=True, use_container_width=True)
    st.caption("E, F e G (novos) usam só as variáveis que realmente separam lance perigoso de lance comum — o teste "
               "comparativo mostrou que as 9 zonas repetem distância e ângulo e só atrapalham. Comece por eles.")
    x1, x2 = st.columns([2, 1])
    exp_pick = x1.multiselect("Experimentos a rodar (na ordem)", EXPERIMENT_ORDER, default=["E", "F", "G"])
    attempts = x2.number_input("Tentativas por clique", 1, 10, 1,
                               help="Quantas sementes diferentes treinar de uma vez (vale para todos os botões). "
                                    "Cada tentativa é registrada e julgada sozinha.")
    c1, c2, c3 = st.columns([1, 1, 1])
    exp_now = c1.button("🧪 Rodar experimentos", type="primary", use_container_width=True, disabled=not exp_pick) and not _vb("O treino")
    train_now = c2.button("▶ Treinar com os hiperparâmetros acima", use_container_width=True) and not _vb("O treino")
    search_now = c3.button(f"🎲 Busca automática ({int(attempts)} tentativa{'s' if attempts > 1 else ''})", use_container_width=True) and not _vb("O treino")
    st.caption("O treino roda em segundo plano (processo separado): a tela não trava e você pode continuar usando o app. "
               "Pelo terminal também funciona: `python -m src.machine_learning.model_registry --treinar --experimentos B,A,C,D`")
    from src.machine_learning import train_job

    if train_now or search_now or exp_now:
        common = ["--tentativas", str(int(attempts)), "--partidas-novas", "500"] + ([] if use_db else ["--sem-banco"]) \
            + (["--com-estimadas"] if use_proxy else ["--somente-360"])
        if exp_now:
            args = ["--experimentos", ",".join(exp_pick)] + common
        elif train_now:
            args = ["--ocultas", ",".join(map(str, hidden)), "--eta", str(lr), "--l2", str(l2), "--lote", str(batch),
                    "--epocas", str(epochs)] + common
        else:
            args = ["--epocas", str(epochs)] + common
        if train_job.start(args):
            st.toast("Treino iniciado em segundo plano — pode continuar usando o app.")
        else:
            st.warning("Já existe um treino rodando. Espere terminar ou pare o atual.")
    job = train_job.state()
    if job:
        status = {"rodando": "🔄 treinando em segundo plano", "concluido": "✅ concluído", "erro": "⚠️ parou com erro",
                  "interrompido": "⏹ interrompido"}.get(job.get("status"), job.get("status"))
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(f"**Treino:** {status} · {job.get('etapa', '')[:120]}")
            if job.get("status") == "rodando":
                c2.button("🔄 Atualizar", key="nn_refresh", use_container_width=True)
                if c3.button("⏹ Parar", key="nn_stop", use_container_width=True) and not _vb("Parar o treino"):
                    train_job.stop()
                    st.rerun()
            for r in job.get("resultados") or []:
                (st.success if r.get("promoted") else st.info)(
                    f"v{r['version']:03d} {'PROMOVIDA — agora é ela que o Analista IA usa' if r.get('promoted') else 'rejeitada'}"
                    f"{' · experimento ' + r['experimento'] if r.get('experimento') else ''}: {r.get('reason')}")
            with st.expander("Registro do treino"):
                st.code("\n".join(job.get("log") or []) or "(sem mensagens ainda)")
    live = None
    with st.expander("🔬 Conferência dos dados de treino (classes e as 15 variáveis)"):
        diag = st.session_state.get("nn_data_diag")
        if diag is None and st.button("Conferir agora (usa a amostra local, ~2 s)", key="nn_diag"):
            diag = {"bal": class_balance(data), "feat": feature_report(data)}
            st.session_state["nn_data_diag"] = diag
        if diag:
            b = diag["bal"]
            st.markdown(f"**Classes:** {b.get('positivas_pct')}% das {b.get('acoes', 0):,} ações terminam em finalização "
                        f"({b.get('partidas')} partidas). Ponderar as classes (peso ≈ {b.get('peso_que_equilibraria')}) "
                        "deixaria a rede descalibrada e pioraria a log-loss, que é o critério de promoção — por isso fica "
                        "desligado; a AUC já não depende do desequilíbrio.".replace(",", "."))
            styled_dataframe(diag["feat"], hide_index=True, use_container_width=True)
            st.caption("AUC sozinha: 0,5 = a variável sozinha não separa jogadas perigosas; longe de 0,5 (para cima ou para baixo) = tem sinal. "
                       "Alerta “redundante” = quase igual a outra variável (|r| > 0,95).")
    net = live["net"] if live else reg.champion()
    if net is None:
        empty_state("Clique em “Treinar nova versão”.", icon="▶")
        return
    ci = reg.champion_info() or {}
    origin = ("desafiante treinado nesta sessão" if live else f"campeão v{ci.get('version', 0):03d} (o modelo que o Analista IA usa)")
    prov = None
    if ctx is not None:
        prov = ctx.prov("nn", "Rede neural", net.summary()["arquitetura"], f"rede NumPy — {origin}", tier="DERIVED")
    else:
        from src.canonical.provenance import ProvenanceRecord

        prov = ProvenanceRecord("nn", "Rede neural", net.summary()["arquitetura"], "Eventos do banco + Estatísticas StatsBomb 360 quando disponíveis",
                                "danger_dataset", "crédito à StatsBomb", "DERIVED", f"rede NumPy — {origin}")
    s = net.summary()
    k = st.columns(5)
    with k[0]:
        kpi("arquitetura", s["arquitetura"], prov)
    with k[1]:
        kpi("parâmetros treináveis", s["parametros"], prov)
    with k[2]:
        kpi("épocas", s["epocas_treinadas"], prov)
    with k[3]:
        kpi("perda final (treino)", f"{net.history['train_loss'][-1]:.4f}", prov)
    with k[4]:
        kpi("AUC na validação fixa", f"{(live['auc'] if live else ci.get('val_auc', 0)):.3f}", prov)
    st.caption(f"Validação fixa: {len(reg.meta['validation_matches'])} partidas que não entram no treino. Ela é reutilizada para "
               "comparar/promover versões; por isso não é um teste final externo independente.")
    l, r = st.columns([1, 1.3])
    l.plotly_chart(charts.loss_curve(net.history, "Curva de perda por época"), use_container_width=True)
    with r:
        mw = st.slider("Esconder conexões com |peso| menor que", 0.0, 1.0, 0.0, 0.05)
        render_chart(charts.nn_architecture(net, max_per_layer=12, min_abs_weight=mw,
                                               title="Arquitetura e conexões pai → filho (espessura ∝ |peso|; verde +, vermelho −)"),
                        use_container_width=True)

    st.markdown("### Inspecionar um neurônio (pais e filhos)")
    neurons = [n for n in net.neurons() if n.layer > 0]
    ids = [n.id for n in neurons]
    pick = st.selectbox("Neurônio", ids, index=0, format_func=lambda i: f"{i} — {net.neuron_label(i)}")
    n = next(x for x in neurons if x.id == pick)
    a, b = st.columns(2)
    with a:
        st.markdown(f"**Pais de {n.id}** (entradas, ativação {n.activation}, viés {n.bias:+.4f})")
        comparison_table(pd.DataFrame([{"pai": p, "rótulo": net.neuron_label(p), "peso": round(w, 4)} for p, w in n.parents])
                         .sort_values("peso", key=np.abs, ascending=False))
    with b:
        st.markdown(f"**Filhos de {n.id}** (para quem envia a ativação)")
        if n.children:
            comparison_table(pd.DataFrame([{"filho": c, "rótulo": net.neuron_label(c), "peso": round(w, 4)} for c, w in n.children])
                             .sort_values("peso", key=np.abs, ascending=False))
        else:
            st.caption("Neurônio de saída: não tem filhos.")
    _versions_and_usage(ctx, reg, live)
    if ctx is not None:
        provenance_panel(ctx.registry)


def _versions_and_usage(ctx, reg, live) -> None:
    """Histórico de versões, curva de aprendizado e como o campeão entra nas respostas do Analista IA."""
    from src.machine_learning.model_registry import DangerModelRegistry, danger_by_player, model_card, score_actions

    st.markdown("### 📈 Histórico de versões (mesma validação fixa, separada por partida)")
    v = reg.versions()
    if not v.empty:
        v["versão"] = v["version"].map(lambda x: f"v{x:03d}")
        render_chart(charts.lines(v, "versão", ["val_logloss"], "Perda na validação fixa por versão (menor = melhor)",
                                     "log-loss"), use_container_width=True)
        for c in ("cv_logloss_std", "test_gain", "gain_ci_low", "gain_ci_high"):
            if c not in v:
                v[c] = None                                   # versões antigas, antes da validação agrupada
        comparison_table(v[["versão", "created", "origin", "hidden", "learning_rate", "epochs", "l2", "n_matches_train",
                            "n_samples_train", "val_auc", "val_logloss", "cv_logloss_std", "test_gain", "gain_ci_low",
                            "promoted", "reason"]].rename(columns={
            "created": "criada", "origin": "origem", "hidden": "ocultas", "learning_rate": "η", "n_matches_train": "partidas",
            "n_samples_train": "ações", "val_auc": "AUC", "val_logloss": "perda (teste)", "cv_logloss_std": "desvio da perda entre dobras",
            "test_gain": "ganho", "gain_ci_low": "IC95% inferior", "promoted": "promovida", "reason": "decisão"}),
            "Promoção: a nova versão precisa melhorar a perda na validação fixa, com IC 95% pareado por partida acima de zero, "
            "ganho mínimo, AUC sem queda relevante e estabilidade no GroupKFold. A validação é reutilizada para selecionar "
            "versões; portanto, não deve ser chamada de teste externo final. Todas as tentativas ficam registradas.")
    with st.expander("📊 Curva de aprendizado: a rede melhora com mais partidas?"):
        if st.button("Calcular a curva (treina 8 redes, ~10 s)", key="lc_go") and not _vb("Calcular a curva"):
            with st.spinner("Treinando com 25%, 50%, 75% e 100% das partidas de treino..."):
                st.session_state["lc"] = reg.learning_curve(DangerModelRegistry.dataset())
        lc = st.session_state.get("lc")
        if lc is not None:
            render_chart(charts.lines(lc, "acoes_de_treino", ["perda_validacao"],
                                         "Perda na validação fixa × quantidade de ações de treino", "log-loss"),
                            use_container_width=True)
            comparison_table(lc, "Mesma arquitetura, mesma validação: a perda cai à medida que entram mais partidas.")

    st.markdown("### 🔗 Como este treino muda as respostas do Analista IA")
    card = model_card()
    if card:
        extra = (f", tracking 360 medido em {card['tracking_360_pct']}% das ações" if card.get("tracking_360_pct") is not None else "")
        note(f"Modelo em uso: {card['versao']}", f"{card['arquitetura']}, {card['partidas_de_treino']} partidas, "
             f"{card.get('acoes_de_treino', '—')} ações, AUC {card['auc_validacao']} na validação{extra}. "
             "O classificador é especializado em perigo da posse; os demais setores reutilizam a régua estatística "
             "compartilhada e seus próprios critérios, não estes mesmos pesos.")
    if ctx is None or not getattr(ctx, "has_events", False):
        st.caption("Abra uma partida com eventos para ver a comparação campeão × desafiante numa pergunta real.")
        return
    champ = reg.champion()
    challenger = live["net"] if live else None
    st.markdown(f"**Pergunta:** “Quem mais criou perigo em {ctx.target_team} x {ctx.opponent}?”")
    cols = st.columns(2 if challenger is not None else 1)
    for col, (label, net) in zip(cols, [("Campeão (usado pelo Analista)", champ)] +
                                 ([("Desafiante desta sessão", challenger)] if challenger is not None else [])):
        with col:
            st.markdown(f"**{label}**")
            sc = score_actions(ctx.df, net)
            top = pd.DataFrame(danger_by_player(sc, None, 5)) if not sc.empty else pd.DataFrame()
            if top.empty:
                st.caption("Nenhuma ação acima do limiar.")
            else:
                comparison_table(top.rename(columns={"acoes_perigosas": "ações perigosas", "maior_chance_pct": "maior chance (%)"}))
    if challenger is not None:
        st.caption("Se o desafiante for promovido, a coluna da direita passa a ser a resposta do Analista IA.")


def _learning_activity_panel() -> None:
    """Deixa explícito o que perguntas e avaliações realmente ensinam ao sistema."""
    from src.intelligence.learning_hub import learning_summary

    s = learning_summary()
    st.markdown("### 🧠 Aprendizado com o uso do programa")
    k = st.columns(4)
    k[0].metric("Perguntas registradas", s["questions_recorded"])
    k[1].metric("Com feedback positivo", s["positive_feedback"])
    k[2].metric("Com feedback negativo", s["negative_feedback"])
    k[3].metric("Aguardando revisão", s["feedback_pending_review"])
    st.caption("Cada pergunta fica registrada. Desde a rodada 13 ela vira exemplo de treino da IA do Assistente: as "
               "avaliações 👍/👎 contam direto (peso 3) e as perguntas que pedem um número reconhecível ganham rótulo "
               "automático. O treino só troca a versão se ela errar menos nas perguntas de validação.")


def _assistant_misses() -> None:
    """Perguntas que o Assistente não soube direcionar: viram casos de teste da próxima versão."""
    from src.intelligence.dynamic_analyst import read_generic_fallbacks

    from src.intelligence.dynamic_analyst import LATENCY_GOAL_S, read_latency

    lat = read_latency()
    if lat:
        secs = pd.Series([r["segundos"] for r in lat])
        st.markdown(f"**⏱️ Tempo de resposta do Assistente** (últimas {len(lat)} perguntas): mediana "
                    f"{secs.median():.1f} s · 90% abaixo de {secs.quantile(0.9):.1f} s · meta < {LATENCY_GOAL_S:.0f} s · "
                    f"{int((secs > LATENCY_GOAL_S).sum())} acima da meta.")
    rows = read_generic_fallbacks(last=40)
    with st.expander(f"💬 Perguntas que o Assistente respondeu só com o panorama ({len(rows)})"):
        if not rows:
            st.caption("Nenhuma até agora. Quando uma pergunta com alvo cair no resumo geral, ela aparece aqui para "
                       "virar caso de teste.")
            return
        styled_dataframe(pd.DataFrame(rows)[["quando", "pergunta"]], hide_index=True, use_container_width=True)
        st.caption("Arquivo local data/assistente_sem_alvo.jsonl (não vai para o GitHub). Mande essas perguntas na "
                   "próxima sessão para eu ensinar o Assistente a respondê-las.")


def _benchmark() -> None:
    """Rodada 5: a rede contra modelos mais simples, nas MESMAS dobras por partida (resultado salvo, não recalculado)."""
    import json
    from pathlib import Path

    st.markdown("## ⚖️ A rede neural é a ferramenta certa? (comparação justa)")
    path = Path("data/processed/benchmark_perigo.json")
    res = None
    if path.exists():
        try:
            res = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            res = None
    if st.button("Rodar a comparação agora (~1–2 min)", key="nn_bench") and not _vb("A comparação"):
        from src.machine_learning.benchmark import DEMO, OUT, run

        with st.spinner("Treinando 6 modelos nas mesmas dobras por partida..."):
            res = run(pd.read_csv(DEMO))
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if not res:
        st.caption("Ainda não rodou. Clique no botão ou rode no terminal: `python -m src.machine_learning.benchmark`.")
        return
    st.caption(f"{res['partidas']} partidas · {res['acoes']} ações · {res['positivos_pct']}% terminaram em finalização · "
               f"{res['dobras']} dobras (nenhuma partida no treino e na validação ao mesmo tempo).")
    df = pd.DataFrame(res["resultados"])
    show = df.rename(columns={"modelo": "Modelo", "auc": "AUC", "brier": "Brier", "log_loss": "Log loss", "ece": "Calibração (ECE)",
                              "dif_auc_vs_logistica": "Δ AUC vs logística", "ic95": "IC 95%", "veredito": "Veredito"})
    styled_dataframe(show, hide_index=True, use_container_width=True)
    note("O que isso quer dizer", res["conclusao"] + " AUC 0,5 = moeda; 1,0 = perfeito. Brier/log loss/ECE menores = "
         "probabilidades melhores. A rede continua como componente didático; o critério de promoção não foi afrouxado.", "info")
    imp = res.get("importancia_permutacao") or {}
    if imp:
        with st.expander("Quais variáveis realmente ajudam (importância por permutação)"):
            styled_dataframe(pd.DataFrame([{"Variável": k, "Queda de AUC sem ela": v} for k, v in imp.items()]),
                         hide_index=True, use_container_width=True)
