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


def render(ctx=None) -> None:
    page_header("🧠 Rede Neural do Zero",
                "Perceptron multicamadas implementado em NumPy puro — forward, backpropagation e descida de gradiente "
                "escritos à mão, para inspecionar o mecanismo de aprendizado.", ctx)
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

    train_now = st.button("▶ Treinar a rede ao vivo", type="primary")
    if train_now:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=7)
        tr, va = next(gss.split(data, groups=data["match_id"]))
        X, y = data[FEATURES].to_numpy(float), data["target"].to_numpy(int)
        net = NeuralNetwork(layers, learning_rate=lr, l2=l2, seed=42, feature_names=FEATURES)
        with st.spinner("Treinando (forward → perda → backpropagation → atualização)..."):
            net.fit(X[tr], y[tr], epochs=epochs, batch_size=batch, X_val=X[va], y_val=y[va])
        auc = float(roc_auc_score(y[va], net.predict_proba(X[va])))
        st.session_state["nn_live"] = {"net": net, "auc": auc, "n_tr": len(tr), "n_va": len(va),
                                       "m_va": int(data.iloc[va]["match_id"].nunique())}
    live = st.session_state.get("nn_live")
    net = live["net"] if live else (NeuralNetwork.load(SAVED) if SAVED.exists() else None)
    if net is None:
        empty_state("Clique em “Treinar a rede ao vivo”.", icon="▶")
        return
    origin = ("treino ao vivo nesta sessão" if live else f"pesos salvos em {SAVED} (treino no dataset completo da Copa 2022)")
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
        kpi("AUC na validação", f"{live['auc']:.3f}" if live else "—", prov)
    if live:
        st.caption(f"Validação separada por partida: {live['n_tr']} ações de treino, {live['n_va']} de validação "
                   f"({live['m_va']} partidas que não entraram no treino).")
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
    if ctx is not None:
        provenance_panel(ctx.registry)
