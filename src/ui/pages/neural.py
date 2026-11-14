"""Página 4 — Rede Neural do Zero (NumPy): arquitetura, treino ao vivo, curva de perda, pais → filhos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

from src.machine_learning.danger_dataset import FEATURES
from src.machine_learning.neural_net import NeuralNetwork
from src.ui import charts
from src.ui.components import comparison_table, empty_state, kpi, note, page_header, provenance_panel

SAMPLE = Path("data/demo/danger_sample_wc2022.csv.gz")
SAVED = Path("models/trained/danger_nn.npz")


@st.cache_data(show_spinner=False)
def _data():
    return pd.read_csv(SAMPLE)


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
         "Cada jogada vira 14 números: <b>distância</b> e <b>ângulo</b> até o gol, quantos <b>adversários estão a 5 m</b> "
         "(medido pelo tracking 360 da StatsBomb), quantos <b>passes</b> a posse já teve, o <b>placar</b> naquele momento e "
         "a <b>zona do campo</b>. É como um olheiro que anota a situação antes de cada toque."),
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
        ("Uma prova que a rede nunca viu",
         "16 jogos ficam separados desde o início e <b>nunca</b> entram no treino. Toda versão nova faz a mesma prova. "
         "Assim “melhorou” quer dizer melhorou de verdade, e não decorou as respostas."),
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

    from src.machine_learning.danger_dataset import ZONE_COLS, _zone_onehot
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
    feats = [dist, ang, dens, passes, sd] + [float(z[c_][0]) for c_ in ZONE_COLS]
    p = float(net.predict_proba(np.array([feats]))[0])
    col1, col2 = st.columns([1, 2])
    col1.metric("Chance de a posse terminar em finalização", f"{100 * p:.1f}%")
    col2.markdown(f"Distância real ao gol: **{dist:.1f} m**, ângulo de visão do gol: **{ang:.1f}°**. "
                  "Mexa nos controles: chegar mais perto e pelo centro aumenta a chance; mais marcadores por perto, em "
                  "geral, diminuem. É exatamente esse número, calculado para cada jogada real, que o Assistente soma "
                  "para dizer quem criou mais perigo.")


def render(ctx=None) -> None:
    from src.ui.components import hero, steps_html

    hero("Bastidores · como a IA aprende", "Uma rede neural que aprende a ler o perigo de uma jogada",
         "Explicação para quem não é da área: o que a rede faz, como aprende, como sabemos que melhorou e onde ela "
         "aparece nas respostas do Assistente. Abaixo, a parte técnica para quem quiser ver por dentro.")
    _didactic()
    _simulator()
    st.markdown("---")
    st.markdown("## 🔧 Por dentro (parte técnica)")
    note("Objetivo didático", "A rede resolve a mesma tarefa do XGBoost (perigo de posse) para comparação direta. "
         "Ficar abaixo do XGBoost seria esperado: o objetivo é mostrar como o aprendizado acontece, não superar o estado da arte.")
    with st.expander("📐 Como a rede aprende (fórmulas implementadas em src/machine_learning/neural_net.py)", expanded=False):
        st.markdown(r"""
- **Inicialização de He:** $W \sim \mathcal{N}(0, \sqrt{2/n_{entrada}})$ — mantém a variância das ativações com ReLU; vieses = 0.
- **Forward:** $Z_l = A_{l-1}W_l + b_l$; $A_l = \mathrm{ReLU}(Z_l)$ nas ocultas e $\sigma(Z_L)$ na saída.
- **Perda:** entropia cruzada binária $-\frac{1}{m}\sum y\log\hat y + (1-y)\log(1-\hat y)$ + $\frac{\lambda}{2m}\sum\|W\|^2$.
- **Backpropagation:** $dZ_L = \hat y - y$; $dW_l = A_{l-1}^\top dZ_l/m + \lambda W_l/m$; $db_l = \sum dZ_l/m$;
  $dZ_{l-1} = (dZ_l W_l^\top)\odot \mathbb{1}[Z_{l-1}>0]$.
- **Atualização:** $W \leftarrow W - \eta\, dW$ em mini-lotes.
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
    lr = b.select_slider("Taxa de aprendizado (η)", [0.005, 0.01, 0.02, 0.05, 0.1, 0.2], value=0.05)
    epochs = c.slider("Épocas", 5, 80, 30)
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
    use_db = st.toggle("Incluir partidas do banco com tracking 360 (o conjunto cresce com a sincronização)", value=True)
    c1, c2 = st.columns([1, 1])
    train_now = c1.button("▶ Treinar nova versão (desafiante)", type="primary", use_container_width=True)
    search_now = c2.button("🎲 Busca automática de hiperparâmetros (3 tentativas)", use_container_width=True)
    if train_now or search_now:
        with st.spinner("Montando o conjunto de treino (amostra + protocolo + banco)..."):
            from src.ui.context import get_service

            full = DangerModelRegistry.dataset((lambda: db_rows(get_service().db, max_new=15)) if use_db else None)
        with st.spinner("Treinando (forward → perda → backpropagation → atualização) e comparando com o campeão..."):
            if train_now:
                rounds = [reg.train_round(full, hidden, lr, epochs, l2, batch)]
            else:
                rounds = reg.auto_search(full, trials=3, epochs=epochs)
        last = rounds[-1]
        st.session_state["nn_live"] = {"net": last["net"], "auc": last["val_auc"], "rounds": rounds,
                                       "n_tr": last["n_samples_train"], "m_tr": last["n_matches_train"]}
    live = st.session_state.get("nn_live")
    if live:
        for r in live["rounds"]:
            (st.success if r["promoted"] else st.info)(
                f"v{r['version']:03d} {'PROMOVIDA — agora é ela que o Analista IA usa' if r['promoted'] else 'rejeitada'}: "
                f"{r['reason']}. Treino: {r['n_matches_train']} partidas, {r['n_samples_train']} ações.")
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

        prov = ProvenanceRecord("nn", "Rede neural", net.summary()["arquitetura"], "StatsBomb Open Data + 360 (Copa 2022)",
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
    st.caption(f"Validação fixa: {len(reg.meta['validation_matches'])} partidas separadas na primeira rodada e nunca usadas "
               "no treino — todas as versões são medidas nas mesmas ações.")
    l, r = st.columns([1, 1.3])
    l.plotly_chart(charts.loss_curve(net.history, "Curva de perda por época"), use_container_width=True)
    with r:
        mw = st.slider("Esconder conexões com |peso| menor que", 0.0, 1.0, 0.0, 0.05)
        st.plotly_chart(charts.nn_architecture(net, max_per_layer=12, min_abs_weight=mw,
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

    st.markdown("### 📈 Histórico de versões (todas medidas na mesma validação fixa)")
    v = reg.versions()
    if not v.empty:
        v["versão"] = v["version"].map(lambda x: f"v{x:03d}")
        st.plotly_chart(charts.lines(v, "versão", ["val_logloss"], "Perda na validação fixa por versão (menor = melhor)",
                                     "log-loss"), use_container_width=True)
        comparison_table(v[["versão", "created", "origin", "hidden", "learning_rate", "epochs", "l2", "n_matches_train",
                            "n_samples_train", "val_auc", "val_logloss", "promoted", "reason"]].rename(columns={
            "created": "criada", "origin": "origem", "hidden": "ocultas", "learning_rate": "η", "n_matches_train": "partidas",
            "n_samples_train": "ações", "val_auc": "AUC", "val_logloss": "perda", "promoted": "promovida", "reason": "decisão"}),
            "Uma versão só vira campeã se reduzir a perda na validação fixa. Treinar de novo nos mesmos dados raramente "
            "melhora; o que ensina a rede é ter mais partidas (veja a curva abaixo) ou hiperparâmetros melhores.")
    with st.expander("📊 Curva de aprendizado: a rede melhora com mais partidas?"):
        if st.button("Calcular a curva (treina 8 redes, ~10 s)", key="lc_go"):
            with st.spinner("Treinando com 25%, 50%, 75% e 100% das partidas de treino..."):
                st.session_state["lc"] = reg.learning_curve(DangerModelRegistry.dataset())
        lc = st.session_state.get("lc")
        if lc is not None:
            st.plotly_chart(charts.lines(lc, "acoes_de_treino", ["perda_validacao"],
                                         "Perda na validação fixa × quantidade de ações de treino", "log-loss"),
                            use_container_width=True)
            comparison_table(lc, "Mesma arquitetura, mesma validação: a perda cai à medida que entram mais partidas.")

    st.markdown("### 🔗 Como este treino muda as respostas do Analista IA")
    card = model_card()
    if card:
        note(f"Modelo em uso: {card['versao']}", f"{card['arquitetura']}, {card['partidas_de_treino']} partidas de treino, "
             f"AUC {card['auc_validacao']} na validação fixa. O Analista usa este modelo em: “quem mais criou perigo?”, "
             "nos planos “como anular o jogador X?” e “qual tática a equipe Y deveria usar?” (onde a rede vê perigo) — "
             "e cada resposta cita a versão usada.")
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
