"""
Bastidores pela matéria "Introdução à IA" (rodada 12): cada aba mostra uma questão (Q1–Q12) calculada com os modelos
de VERDADE do laboratório. As contas estão em src/intelligence/course.py (testadas); aqui só desenhamos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.intelligence import course as C
from src.ui.components import note, styled_dataframe

BG, CARD, LINE, CYAN, BLUE, RED, TXT, MUTED = ("#090D16", "#0B1120", "#1E2A44", "#22D3EE", "#3B82F6", "#EF4444",
                                               "#F5F7FB", "#98A6BF")


def _fig(h: int = 300) -> go.Figure:
    f = go.Figure()
    f.update_layout(height=h, paper_bgcolor=BG, plot_bgcolor=CARD, font=dict(color=TXT), margin=dict(l=40, r=20, t=40, b=40),
                    legend=dict(orientation="h", y=-0.2))
    f.update_xaxes(gridcolor=LINE)
    f.update_yaxes(gridcolor=LINE)
    return f


def _table(rows, caption: str = "") -> None:
    styled_dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    if caption:
        st.caption(caption)


# ------------------------------------------------------------------ mapa
def decisions_tab() -> None:
    st.markdown("### 🗺️ Quem decide cada coisa no programa")
    st.caption("Nenhuma tela do laboratório é decidida por um modelo de linguagem externo: o Gemini vem desligado. Cada "
               "decisão abaixo é tomada por um componente nosso, com a questão da matéria que ele aplica.")
    _table(C.decision_map())
    st.markdown("#### Q1 · Taxonomia: que tipo de problema é cada um")
    _table(C.TAXONOMY, "Classificar o problema antes de escolher a técnica: é o primeiro passo da matéria e foi como o "
                       "laboratório foi montado.")


# ------------------------------------------------------------------ Eixo 1
def fuzzy_tab() -> None:
    st.markdown("### Eixo 1 · Lógica fuzzy")
    st.markdown("#### Q2 · Fuzzy × probabilidade")
    pp = st.slider("Passes certos do jogador (%)", 0, 100, 82, key="c_q2")
    q2 = C.fuzzy_vs_probability(pp)
    a, b = st.columns(2)
    with a:
        note("Leitura fuzzy (vaguidade)", q2["texto_fuzzy"], "info")
    with b:
        note("Leitura probabilística (acaso)", q2["texto_prob"], "info")
    u = np.arange(0, 101)
    f = _fig(240)
    for name, (l, p, r), col in (("baixo", (0, 0, 50), RED), ("médio", (20, 50, 80), MUTED), ("alto", (50, 100, 100), CYAN)):
        f.add_scatter(x=u, y=C._tri(u, l, p, r), name=name, line=dict(color=col))
    f.add_vline(x=pp, line_dash="dot", line_color=TXT)
    f.update_layout(title="Pertinência de “passe”: baixo / médio / alto", yaxis_title="μ")
    st.plotly_chart(f, use_container_width=True)

    st.markdown("#### Q3 · Mamdani passo a passo, com centroide numérico")
    c1, c2 = st.columns(2)
    di = c1.slider("Intensidade defensiva (0–100)", 0, 100, 70, key="c_q3a")
    pa = c2.slider("Precisão de passe (0–100)", 0, 100, 85, key="c_q3b")
    m = C.mamdani_centroid(di, pa)
    st.markdown("**1. Fuzzificação** → **2. Regras (E = mínimo)**")
    _table(m["regras"])
    f = _fig(280)
    for name, (l, p, r) in C.OUT_SETS.items():
        f.add_scatter(x=m["universo"], y=C._tri(m["universo"], l, p, r), name=name, line=dict(width=1, dash="dot"))
    f.add_scatter(x=m["universo"], y=m["agregada"], name="agregada (máximo dos cortes)", fill="tozeroy",
                  line=dict(color=CYAN, width=3))
    if m["centroide"] is not None:
        f.add_vline(x=m["centroide"], line_color=RED, annotation_text=f"centroide {m['centroide']}")
    f.update_layout(title="3. Corte de cada saída · 4. Agregação · 5. Centroide", xaxis_title="contribuição tática")
    st.plotly_chart(f, use_container_width=True)
    st.caption(f"{m['formula']}. Resultado: **{m['centroide']}** — um ÍNDICE fuzzy, não uma probabilidade.")

    st.markdown("#### Q4 · Mamdani × Takagi-Sugeno (as mesmas regras)")
    s = C.sugeno_same_rules(di, pa)
    k = st.columns(2)
    k[0].metric("Mamdani (centroide)", m["centroide"])
    k[1].metric("Sugeno ordem zero (média ponderada)", s["saida"])
    _table(C.MAMDANI_VS_SUGENO)


# ------------------------------------------------------------------ Eixo 2
def _champion_and_val():
    from src.machine_learning.model_registry import DangerModelRegistry

    reg = DangerModelRegistry()
    net = reg.champion()
    if net is None:
        return reg, None, None
    from src.ui.pages.neural import SAMPLE, _data

    if not SAMPLE.exists():
        return reg, net, None
    _, val = reg.split(_data())
    return reg, net, val


@st.cache_data(show_spinner=False, ttl=3600)
def _val_scores(version: int):
    reg, net, val = _champion_and_val()
    if net is None or val is None:
        return None
    p = net.predict_proba(reg._model_matrix(net, val))
    return val["target"].to_numpy(int).tolist(), np.asarray(p, float).tolist()


def neural_tab() -> None:
    st.markdown("### Eixo 2 · Redes neurais")
    st.markdown("#### Q5 · Forward pass e o problema do XOR")
    a, b = st.columns(2)
    with a:
        st.markdown("**XOR com uma camada escondida** (pesos didáticos: h1 ≈ OU, h2 ≈ E)")
        _table(C.xor_forward())
    with b:
        lin = C.xor_linear_best()
        st.metric("Melhor reta (sem camada escondida)", f"{lin['acertos']} de {lin['de']} certos")
        st.caption(lin["texto"])
    reg, net, val = _champion_and_val()
    if net is not None and val is not None:
        names = list(getattr(net, "feature_names", None) or [])
        try:
            X = reg._model_matrix(net, val.iloc[[0]])
            st.markdown("**O mesmo forward pass no modelo de perigo em uso, para uma jogada real da validação:**")
            _table(C.forward_trace(net, X[0]), f"Entradas: {', '.join(names[:6])}{'…' if len(names) > 6 else ''}. "
                                               "ReLU nas ocultas (zera o negativo) e sigmoide na saída (chance 0–1).")
        except Exception as e:                     # noqa: BLE001
            st.caption(f"Não consegui montar a jogada de exemplo ({e}).")

    st.markdown("#### Q6 · Um passo da descida do gradiente num neurônio sigmoide")
    c = st.columns(5)
    x1 = c[0].number_input("x₁", value=1.0, step=0.5, key="g_x1")
    x2 = c[1].number_input("x₂", value=2.0, step=0.5, key="g_x2")
    w1 = c[2].number_input("w₁", value=0.1, step=0.1, key="g_w1")
    w2 = c[3].number_input("w₂", value=-0.2, step=0.1, key="g_w2")
    eta = c[4].number_input("η", value=0.5, step=0.1, key="g_eta")
    y = st.radio("Resposta certa (y)", [1.0, 0.0], horizontal=True, key="g_y")
    g = C.gradient_step([x1, x2], [w1, w2], 0.0, y, eta)
    st.markdown(f"z = w·x + b = **{g['z']}** → a = σ(z) = **{g['a']}** → perda = **{g['perda']}**  \n"
                f"∂L/∂z = a − y = **{g['dL/dz']}** → ∂L/∂w = (a − y)·x = **{g['dL/dw']}**, ∂L/∂b = **{g['dL/db']}**  \n"
                f"w ← w − η·∂L/∂w = **{g['w novo']}**, b = **{g['b novo']}** → nova saída **{g['a novo']}**, nova perda "
                f"**{g['perda nova']}** ({'caiu ✅' if g['perda nova'] < g['perda'] else 'subiu ⚠️ — η grande demais'}).")
    st.caption("É exatamente esta conta que neural_net.py faz em cada peso, camada por camada (backpropagation), com Adam.")

    st.markdown("#### Q7 · Curvas de treino × validação, parada antecipada e o próximo experimento")
    versions = reg.meta.get("versions") or []
    if not versions:
        st.caption("Nenhum treino registrado ainda.")
    else:
        opts = {f"v{v['version']:03d} · {v.get('origin', '')} · {'promovida' if v.get('promoted') else 'rejeitada'}": v
                for v in reversed(versions)}
        v = opts[st.selectbox("Treino a analisar", list(opts), key="c_q7")]
        h = v.get("history") or {}
        d = C.diagnose_curve(h)
        f = _fig(300)
        if h.get("train_loss"):
            f.add_scatter(y=h["train_loss"], x=list(range(1, len(h["train_loss"]) + 1)), name="treino", line=dict(color=BLUE))
        if h.get("val_loss"):
            f.add_scatter(y=h["val_loss"], x=list(range(1, len(h["val_loss"]) + 1)), name="validação", line=dict(color=RED))
        if d.get("melhor_epoca"):
            f.add_vline(x=d["melhor_epoca"], line_dash="dot", line_color=CYAN,
                        annotation_text=f"melhor época {d['melhor_epoca']} (parada antecipada)")
        f.update_layout(title="Perda por época", xaxis_title="época", yaxis_title="log-loss")
        st.plotly_chart(f, use_container_width=True)
        note(f"Diagnóstico: {d['diagnostico']}", d["texto"], "info")
        sug = C.suggest_next_experiment(v)
        rows = [{"parâmetro": k, "último treino": str(sug["atual"].get(k)), "sugerido": str(sug["sugerido"].get(k))}
                for k in ("hidden", "learning_rate", "l2", "epochs")]
        if sug["sugerido"].get("features"):
            rows.append({"parâmetro": "variáveis", "último treino": "todas", "sugerido": sug["sugerido"]["features"]})
        _table(rows)
        st.markdown("**Por quê:** " + " · ".join(sug["porque"]))
        st.code(sug["comando"], language="bash")
        st.caption("Divisão usada: TREINO (partidas do treino; uma fatia delas faz a parada antecipada) · VALIDAÇÃO fixa "
                   "por partida (escolhe o campeão) · TESTE isolado no GroupKFold. Nenhuma partida aparece em dois lugares.")

    st.markdown("#### Q8 · Matriz de confusão e o paradoxo da acurácia")
    ci = reg.champion_info() or {}
    sc = _val_scores(int(ci.get("version") or 0)) if net is not None else None
    if not sc:
        st.caption("Sem modelo ou amostra de validação neste computador.")
    else:
        y_true, p = sc
        t = st.slider("Limiar para dizer “vai ter chute”", 0.05, 0.9, 0.5, 0.01, key="c_q8")
        cm = C.confusion(y_true, p, t)
        best = C.best_f1_threshold(y_true, p)
        a, b = st.columns([1, 1.3])
        with a:
            f = go.Figure(go.Heatmap(z=[[cm["VP"], cm["FN"]], [cm["FP"], cm["VN"]]], x=["previu chute", "previu sem chute"],
                                     y=["teve chute", "não teve"], text=[[cm["VP"], cm["FN"]], [cm["FP"], cm["VN"]]],
                                     texttemplate="%{text}", colorscale=[[0, CARD], [1, BLUE]], showscale=False))
            f.update_layout(height=260, paper_bgcolor=BG, font=dict(color=TXT), margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(f, use_container_width=True)
        with b:
            k = st.columns(4)
            fmt = lambda v: "—" if v is None else f"{100 * v:.1f}%"
            k[0].metric("Acurácia", fmt(cm["acuracia"]))
            k[1].metric("Precisão", fmt(cm["precisao"]))
            k[2].metric("Revocação", fmt(cm["revocacao"]))
            k[3].metric("F1", fmt(cm["f1"]))
            st.caption(f"Melhor F1 neste conjunto: limiar {best['limiar']} (F1 {fmt(best['f1'])}, precisão "
                       f"{fmt(best['precisao'])}, revocação {fmt(best['revocacao'])}).")
        note("Paradoxo da acurácia", cm["paradoxo"], "warn")

    st.markdown("#### Q9 · Arquiteturas: qual usamos e por quê")
    _table(C.ARCHITECTURES)


# ------------------------------------------------------------------ Eixo 3
def genetic_tab() -> None:
    st.markdown("### Eixo 3 · Algoritmo genético (a escalação)")
    st.markdown("#### Q10 · Codificação binária, seleção e mutação")
    squad = C.example_ga_squad()
    chosen = squad["nome"].tolist()[:11]
    enc = C.binary_encoding(squad["nome"].tolist(), chosen)
    st.markdown(f"Cromossomo de um elenco de {enc['comprimento']} atletas: `{enc['cromossomo']}` — {enc['texto']}")
    st.caption("No código (squad/genetic.py) usamos a codificação por PERMUTAÇÃO (o gene i = quem ocupa a vaga i), que "
               "garante 11 atletas diferentes sem precisar de penalidade; a binária é mostrada para comparar.")
    fit_txt = st.text_input("Aptidões de 5 escalações (separadas por vírgula)", "10, 8, 5, 2, 1", key="c_q10")
    try:
        fv = [float(x) for x in fit_txt.replace(";", ",").split(",") if x.strip()]
        k = st.slider("Tamanho do torneio (k)", 2, max(2, min(5, len(fv))), min(3, len(fv)), key="c_q10k")
        _table(C.roulette_vs_tournament(fv, k), "Roleta: chance proporcional à aptidão. Torneio: sorteia k e fica o "
                                               "melhor — o pior nunca vence; k maior = mais pressão (intensificação).")
    except Exception:
        st.caption("Digite números separados por vírgula.")
    pm = st.slider("Probabilidade de mutação por gene", 0.0, 0.3, round(1 / 18, 3), 0.005, key="c_q10m")
    _table([C.expected_mutations(18, pm)])

    st.markdown("#### Q11 · Restrições com penalidade R")
    st.markdown("Lesionado não pode jogar: em vez de proibir, a aptidão é **f′(x) = f(x) − R·(lesionados no XI)** com "
                "R = 1000 (maior que qualquer XI possível) — a evolução descarta sozinha essas soluções.")
    _table([C.penalized_fitness(776.4, 0, 1000), C.penalized_fitness(790.0, 1, 1000)])

    st.markdown("#### Q12 · O AG com elitismo, critério de parada e exploração × intensificação")
    st.code(C.GA_PSEUDOCODE, language="text")
    c = st.columns(3)
    gens = c[0].slider("Gerações (parada)", 10, 300, 80, 10, key="c_ga_g")
    pop = c[1].slider("População", 10, 120, 40, 10, key="c_ga_p")
    pmut = c[2].slider("Mutação (por filho)", 0.0, 1.0, 0.35, 0.05, key="c_ga_m")
    r = C.run_example_ga(generations=gens, pop=pop, p_mut=pmut)
    f = _fig(280)
    f.add_scatter(y=r["historico"], x=list(range(1, len(r["historico"]) + 1)), name="melhor aptidão", line=dict(color=CYAN))
    f.add_hline(y=r["aptidao_base"], line_dash="dot", line_color=RED, annotation_text="ótimo exato (húngaro)")
    f.update_layout(title="Convergência (elenco de exemplo, começando SEM a solução exata)", xaxis_title="geração")
    st.plotly_chart(f, use_container_width=True)
    note("Leitura da convergência", r["convergencia"]["texto"] +
         f" Melhor do AG {r['aptidao']} × húngaro {r['aptidao_base']}.", "info")
    st.caption("Elenco de exemplo (atletas fictícios, um lesionado). Na Escalação → Plano de jogo o mesmo AG usa o seu "
               "elenco real e ganha bônus quando o atleta ataca uma fraqueza medida do rival.")


def render_course() -> None:
    tabs = st.tabs(["🗺️ Quem decide o quê (Q1)", "Eixo 1 · Fuzzy (Q2–Q4)", "Eixo 2 · Redes neurais (Q5–Q9)",
                    "Eixo 3 · Genético (Q10–Q12)"])
    for tab, fn in zip(tabs, (decisions_tab, fuzzy_tab, neural_tab, genetic_tab)):
        with tab:
            try:
                fn()
            except Exception as e:                 # noqa: BLE001 — uma aba quebrada não derruba a página
                st.error(f"Esta parte não pôde ser montada: {e}")
