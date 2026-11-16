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
    density_origin = st.selectbox("Origem da densidade", ["Tracking 360 medido", "Estimativa por eventos"], index=0)
    values = {"dist_to_goal_m": dist, "angle_to_goal_deg": ang, "opp_density_5m": dens, "passes_so_far": passes,
              "score_diff": sd, "density_is_360": float(density_origin == "Tracking 360 medido")}
    values.update({name: float(z[name][0]) for name in ZONE_COLS})
    from src.machine_learning.danger_dataset import LEGACY_FEATURES
    names = list(getattr(net, "feature_names", []) or [])
    if not names or any(name.startswith("x") for name in names):
        names = LEGACY_FEATURES if net.layer_sizes[0] == len(LEGACY_FEATURES) else list(values)
    feats = [values.get(name, 0.0) for name in names]
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
    use_db = t1.toggle("Incluir partidas do banco com tracking 360 (o conjunto cresce com a sincronização)", value=True)
    use_proxy = t2.toggle("Incluir também jogos sem 360 (densidade estimada por eventos)", value=True,
                          help="Amplia a base com eventos do OpenPlay, Wyscout e StatsBomb sem freeze frame. O campo "
                               "density_is_360 informa a origem; a estimativa não é apresentada como tracking medido.")
    from src.machine_learning.model_registry import (EXP_BATCH, EXP_EPOCHS, EXP_PATIENCE, EXPERIMENT_ORDER,
                                                     EXPERIMENTS, class_balance, feature_report)

    st.markdown("#### 🧪 Experimentos controlados")
    st.caption(f"Todos com Adam, até {EXP_EPOCHS} épocas, lote {EXP_BATCH}, parada antecipada com paciência "
               f"{EXP_PATIENCE}, inicialização He e treino do zero. O campeão só é trocado com superioridade estatística.")
    st.dataframe(__import__("pandas").DataFrame([
        {"experimento": k, "arquitetura": " → ".join(map(str, [len(FEATURES), *v["hidden"], 1])),
         "η": v["learning_rate"], "λ": v["l2"]} for k, v in EXPERIMENTS.items()]), hide_index=True, use_container_width=True)
    x1, x2 = st.columns([2, 1])
    exp_pick = x1.multiselect("Experimentos a rodar (na ordem)", EXPERIMENT_ORDER, default=["B"])
    attempts = x2.number_input("Tentativas por clique", 1, 10, 1,
                               help="Quantas sementes diferentes treinar de uma vez (vale para todos os botões). "
                                    "Cada tentativa é registrada e julgada sozinha.")
    c1, c2, c3 = st.columns([1, 1, 1])
    exp_now = c1.button("🧪 Rodar experimentos", type="primary", use_container_width=True, disabled=not exp_pick)
    train_now = c2.button("▶ Treinar com os hiperparâmetros acima", use_container_width=True)
    search_now = c3.button(f"🎲 Busca automática ({int(attempts)} tentativa{'s' if attempts > 1 else ''})", use_container_width=True)
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
                if c3.button("⏹ Parar", key="nn_stop", use_container_width=True):
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
            st.dataframe(diag["feat"], hide_index=True, use_container_width=True)
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
    st.caption(f"Validação fixa: {len(reg.meta['validation_matches'])} partidas que não entram no treino. Ela é reutilizada para "
               "comparar/promover versões; por isso não é um teste final externo independente.")
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
    _assistant_misses()
    _learning_activity_panel()
    if ctx is not None:
        provenance_panel(ctx.registry)


def _versions_and_usage(ctx, reg, live) -> None:
    """Histórico de versões, curva de aprendizado e como o campeão entra nas respostas do Analista IA."""
    from src.machine_learning.model_registry import DangerModelRegistry, danger_by_player, model_card, score_actions

    st.markdown("### 📈 Histórico de versões (mesma validação fixa, separada por partida)")
    v = reg.versions()
    if not v.empty:
        v["versão"] = v["version"].map(lambda x: f"v{x:03d}")
        st.plotly_chart(charts.lines(v, "versão", ["val_logloss"], "Perda na validação fixa por versão (menor = melhor)",
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
    st.caption("Cada pergunta fica registrada para auditoria e para encontrar lacunas. Perguntas e 👍/👎 não alteram os pesos: "
               "o feedback fica pendente de revisão. O treino só usa exemplos com rótulo verificável, como a sequência real "
               "de eventos e se a posse terminou em finalização.")


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
        st.dataframe(pd.DataFrame(rows)[["quando", "pergunta"]], hide_index=True, use_container_width=True)
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
    if st.button("Rodar a comparação agora (~1–2 min)", key="nn_bench"):
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
    st.dataframe(show, hide_index=True, use_container_width=True)
    note("O que isso quer dizer", res["conclusao"] + " AUC 0,5 = moeda; 1,0 = perfeito. Brier/log loss/ECE menores = "
         "probabilidades melhores. A rede continua como componente didático; o critério de promoção não foi afrouxado.", "info")
    imp = res.get("importancia_permutacao") or {}
    if imp:
        with st.expander("Quais variáveis realmente ajudam (importância por permutação)"):
            st.dataframe(pd.DataFrame([{"Variável": k, "Queda de AUC sem ela": v} for k, v in imp.items()]),
                         hide_index=True, use_container_width=True)
