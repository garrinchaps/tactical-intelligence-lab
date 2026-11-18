"""
Rodada 12 — a matéria "Introdução à Inteligência Artificial" aplicada ao laboratório.

Cada função aqui é PURA (sem Streamlit) e calcula, com os modelos de verdade do app, o que cada questão da matéria
pede: taxonomia dos problemas (Q1), fuzzy × probabilidade (Q2), Mamdani com centroide (Q3), Mamdani × Takagi-Sugeno
(Q4), forward pass e XOR (Q5), um passo de descida do gradiente num neurônio sigmoide (Q6), diagnóstico da curva de
treino e sugestão do próximo experimento (Q7), matriz de confusão e paradoxo da acurácia (Q8), arquiteturas (Q9),
codificação binária, roleta × torneio e mutação (Q10), penalidade R (Q11) e o pseudocódigo do AG com elitismo (Q12).

A página "Bastidores" (src/ui/pages/neural.py) só desenha o que sai daqui; os testes conferem as contas.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

# ============================================================== mapa das decisões (quem decide o quê no app)
DECISIONS: List[Dict[str, str]] = [
    {"parte do app": "Assistente — entender a pergunta", "componente": "router.py + direct.py (intenções e métrica pedida)",
     "tipo de problema": "Classificação de texto (intenção)", "paradigma": "Simbólico (regras) + estatístico",
     "questão": "Q1", "aprende?": "Sim: perguntas sem alvo viram casos de teste"},
    {"parte do app": "Assistente — escolher os fatos da resposta", "componente": "lab_ai/selector.py (regressão logística NumPy)",
     "tipo de problema": "Classificação binária (fato útil × não útil)", "paradigma": "Aprendizado supervisionado",
     "questão": "Q1 · Q6 · Q8", "aprende?": "Sim: avaliações 👍/👎; só promove se errar menos no teste"},
    {"parte do app": "Assistente — escolher a frase", "componente": "lab_ai/selector.py (amostragem de Thompson)",
     "tipo de problema": "Decisão sequencial (bandido de vários braços)", "paradigma": "Aprendizado por reforço",
     "questão": "Q1", "aprende?": "Sim: a cada 👍/👎"},
    {"parte do app": "Assistente/Jogo — perigo de cada ação", "componente": "neural_net.py (MLP do zero, Adam, parada antecipada)",
     "tipo de problema": "Classificação binária com probabilidade", "paradigma": "Rede neural (conexionista)",
     "questão": "Q5 · Q6 · Q7 · Q8", "aprende?": "Sim: treino com GroupKFold por partida"},
    {"parte do app": "Nota 0–10 do jogador", "componente": "rating_v2.py / rating_box.py (percentil contra a mesma função)",
     "tipo de problema": "Regressão / ordenação", "paradigma": "Estatístico (régua da base)",
     "questão": "Q1", "aprende?": "A régua cresce com a base"},
    {"parte do app": "Contribuição tática (índice fuzzy)", "componente": "fuzzy.py (Mamdani com centroide)",
     "tipo de problema": "Avaliação com termos vagos (\"marca muito\", \"passa bem\")", "paradigma": "Lógica fuzzy",
     "questão": "Q2 · Q3", "aprende?": "Não: regras escritas por especialista (auditáveis)"},
    {"parte do app": "Pressão territorial (índice contínuo)", "componente": "fuzzy.py (Takagi-Sugeno)",
     "tipo de problema": "Índice contínuo a partir de regras", "paradigma": "Lógica fuzzy",
     "questão": "Q4", "aprende?": "Não"},
    {"parte do app": "Escalação — melhor XI contra o rival", "componente": "squad/genetic.py (AG com torneio, elitismo, reparo)",
     "tipo de problema": "Otimização combinatória com restrições", "paradigma": "Computação evolutiva",
     "questão": "Q10 · Q11 · Q12", "aprende?": "Não aprende: busca a melhor solução a cada pedido"},
    {"parte do app": "Escalação — XI base de referência", "componente": "planner.py (algoritmo húngaro)",
     "tipo de problema": "Atribuição ótima", "paradigma": "Busca exata (pesquisa operacional)",
     "questão": "Q1 · Q12 (comparação)", "aprende?": "Não"},
    {"parte do app": "Diagnóstico do rival", "componente": "analytics/vulnerabilities.py",
     "tipo de problema": "Detecção de padrões fora da curva", "paradigma": "Estatístico + regras", "questão": "Q1",
     "aprende?": "A régua cresce com a base"},
    {"parte do app": "Scout — viabilidade da contratação", "componente": "scout/engine.py (pesos por critério)",
     "tipo de problema": "Ranqueamento multicritério", "paradigma": "Sistema especialista ponderado", "questão": "Q1",
     "aprende?": "Não"},
    {"parte do app": "Mesmo atleta em várias fontes", "componente": "data_lake/ids.py · player_resolver.py",
     "tipo de problema": "Agrupamento / resolução de entidades", "paradigma": "Regras + similaridade",
     "questão": "Q1", "aprende?": "Não"},
]

TAXONOMY: List[Dict[str, str]] = [
    {"problema da matéria": "Classificação", "no laboratório": "Esta posse termina em chute? Este fato serve à pergunta?",
     "saída": "classe + probabilidade"},
    {"problema da matéria": "Regressão", "no laboratório": "Nota 0–10 da atuação; xG de um chute", "saída": "número contínuo"},
    {"problema da matéria": "Agrupamento", "no laboratório": "Mesmo atleta em fontes diferentes; jogos parecidos",
     "saída": "grupos"},
    {"problema da matéria": "Otimização", "no laboratório": "Melhor XI contra as fraquezas do rival", "saída": "uma solução"},
    {"problema da matéria": "Decisão sequencial (reforço)", "no laboratório": "Qual frase usar, aprendendo com 👍/👎",
     "saída": "uma ação por vez"},
    {"problema da matéria": "Raciocínio com incerteza vaga", "no laboratório": "\"Marca muito e passa bem\" → contribuição",
     "saída": "grau de pertinência"},
]


def decision_map() -> List[Dict[str, str]]:
    return [dict(d) for d in DECISIONS]


# ============================================================== Q2 — fuzzy × probabilidade
def fuzzy_vs_probability(pass_pct: float = 82.0) -> Dict[str, Any]:
    """O mesmo número em duas leituras: grau de "passa bem" (vago, sem acaso) × chance de acertar o próximo passe."""
    from src.intelligence.fuzzy import player_memberships

    mu = player_memberships(pass_pct)
    return {
        "valor": pass_pct,
        "fuzzy": mu,
        "probabilidade_proximo_passe": round(pass_pct / 100, 2),
        "texto_fuzzy": (f"Com {pass_pct:.0f}% de passes certos, o jogador é \"alto\" com grau {mu['alto']:.2f} e \"médio\" "
                        f"com grau {mu['medio']:.2f}. Os graus NÃO somam 1 por obrigação e não falam de acaso: dizem o quanto "
                        "o número se encaixa na palavra."),
        "texto_prob": (f"Já a probabilidade fala de um evento incerto: a chance de o PRÓXIMO passe sair certo é "
                       f"≈ {pass_pct / 100:.2f}. Depois que o passe acontece, a dúvida some (certo ou errado); "
                       "o \"passa bem\" continua vago mesmo sabendo tudo."),
    }


# ============================================================== Q3 — Mamdani com centroide numérico
OUT_SETS = {"baixo": (0, 0, 35), "regular": (15, 35, 55), "bom": (40, 60, 80), "muito_bom": (60, 80, 95),
            "excelente": (80, 100, 100)}


def _tri(x: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    x = np.asarray(x, float)
    left = np.where(b > a, (x - a) / max(b - a, 1e-12), (x >= b).astype(float))
    right = np.where(c > b, (c - x) / max(c - b, 1e-12), (x <= b).astype(float))
    return np.clip(np.minimum(left, right), 0, 1)


def mamdani_centroid(defensive_intensity: float, pass_accuracy: float, step: float = 1.0) -> Dict[str, Any]:
    """Mamdani completo: fuzzificação → regras (E = mínimo) → corte de cada saída → agregação (máximo) → centroide."""
    from src.intelligence.fuzzy import PLAYER_RULES, player_memberships

    mi, mp = player_memberships(defensive_intensity), player_memberships(pass_accuracy)
    u = np.arange(0, 100 + step, step)
    agg = np.zeros_like(u, dtype=float)
    rules = []
    for r in PLAYER_RULES:
        alpha = min(mi[r.intensity], mp[r.passing])
        cut = np.minimum(alpha, _tri(u, *OUT_SETS[r.consequent]))
        agg = np.maximum(agg, cut)
        rules.append({"regra": f"SE intensidade é {r.intensity} E passe é {r.passing} ENTÃO contribuição é {r.consequent}",
                      "μ intensidade": round(mi[r.intensity], 3), "μ passe": round(mp[r.passing], 3),
                      "força (mín)": round(alpha, 3)})
    area = float(agg.sum())
    centroid = float((u * agg).sum() / area) if area > 0 else None
    return {"universo": u, "agregada": agg, "regras": rules, "centroide": None if centroid is None else round(centroid, 2),
            "pertinencias": {"intensidade": mi, "passe": mp},
            "formula": "centroide = Σ u·μ(u) / Σ μ(u)  (soma no universo discretizado de 0 a 100)"}


# ============================================================== Q4 — Takagi-Sugeno com as mesmas regras
SUGENO_OUT = {"baixo": 20.0, "regular": 40.0, "bom": 60.0, "muito_bom": 80.0, "excelente": 95.0}


def sugeno_same_rules(defensive_intensity: float, pass_accuracy: float) -> Dict[str, Any]:
    """Mesmas regras; a saída de cada uma é um NÚMERO (ordem zero) e o resultado é a média ponderada pelas forças."""
    from src.intelligence.fuzzy import PLAYER_RULES, player_memberships

    mi, mp = player_memberships(defensive_intensity), player_memberships(pass_accuracy)
    w = [(min(mi[r.intensity], mp[r.passing]), SUGENO_OUT[r.consequent]) for r in PLAYER_RULES]
    tot = sum(a for a, _ in w)
    return {"saida": round(sum(a * z for a, z in w) / tot, 2) if tot else None,
            "termos": [{"força": round(a, 3), "saída da regra": z} for a, z in w if a > 0]}


MAMDANI_VS_SUGENO = [
    {"aspecto": "Saída de cada regra", "Mamdani": "um conjunto fuzzy (triângulo cortado)",
     "Takagi-Sugeno": "um número ou função linear das entradas"},
    {"aspecto": "Como junta as regras", "Mamdani": "agrega as figuras (máximo) e calcula o centroide",
     "Takagi-Sugeno": "média ponderada pelas forças — sem defuzzificar"},
    {"aspecto": "Custo", "Mamdani": "maior (integra/soma o universo)", "Takagi-Sugeno": "baixo (uma conta)"},
    {"aspecto": "Leitura", "Mamdani": "muito interpretável: \"contribuição boa\"",
     "Takagi-Sugeno": "menos intuitivo; ótimo para controle e para ajustar com dados"},
    {"aspecto": "No laboratório", "Mamdani": "contribuição tática do jogador (explicável ao torcedor)",
     "Takagi-Sugeno": "índice de pressão territorial (rápido, contínuo, ao vivo)"},
]


# ============================================================== Q5 — forward pass e XOR
def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, float)))


XOR_X = np.array([[0, 0], [0, 1], [1, 0], [1, 1]], float)
XOR_Y = np.array([0, 1, 1, 0], float)
# pesos à mão (didáticos): h1 ≈ OU, h2 ≈ E, saída ≈ h1 E NÃO h2
XOR_W1 = np.array([[20.0, 20.0], [20.0, 20.0]])
XOR_B1 = np.array([-10.0, -30.0])
XOR_W2 = np.array([20.0, -20.0])
XOR_B2 = -10.0


def xor_forward() -> List[Dict[str, Any]]:
    rows = []
    for x, y in zip(XOR_X, XOR_Y):
        z1 = x @ XOR_W1 + XOR_B1
        h = sigmoid(z1)
        out = float(sigmoid(h @ XOR_W2 + XOR_B2))
        rows.append({"x1": int(x[0]), "x2": int(x[1]), "z oculta": [round(float(v), 1) for v in z1],
                     "h1 (≈ OU)": round(float(h[0]), 3), "h2 (≈ E)": round(float(h[1]), 3),
                     "saída": round(out, 3), "esperado": int(y)})
    return rows


def xor_linear_best() -> Dict[str, Any]:
    """Melhor reta (perceptron/regressão logística sem camada oculta): no máximo 3 de 4 certos — não separa o XOR."""
    best = 0
    grid = np.linspace(-3, 3, 25)
    for a in grid:
        for b in grid:
            for c in grid:
                pred = (XOR_X @ np.array([a, b]) + c > 0).astype(float)
                best = max(best, int((pred == XOR_Y).sum()))
    return {"acertos": best, "de": 4,
            "texto": "Sem camada escondida a fronteira é uma reta; nenhuma reta separa (0,1),(1,0) de (0,0),(1,1). "
                     "A não-linearidade (sigmoide/ReLU) na camada oculta é o que permite dobrar o espaço."}


def forward_trace(net, x: Sequence[float]) -> List[Dict[str, Any]]:
    """Forward pass camada a camada do modelo de perigo em uso, para UMA jogada (padronizada como no treino)."""
    X = np.asarray([list(map(float, x))])
    X = net._standardize(X) if hasattr(net, "_standardize") else X
    A = X
    out = [{"camada": "entrada (padronizada)", "neurônios": A.shape[1], "valores (até 6)": np.round(A[0][:6], 3).tolist(), "neurônios desligados (ReLU = 0)": "—"}]
    L = len(net.weights)
    for i, (W, b) in enumerate(zip(net.weights, net.biases)):
        Z = A @ W + b
        A = sigmoid(Z) if i == L - 1 else np.maximum(Z, 0)
        out.append({"camada": "saída (sigmoide)" if i == L - 1 else f"oculta {i + 1} (ReLU)", "neurônios": A.shape[1],
                    "valores (até 6)": np.round(A[0][:6], 3).tolist(),
                    "neurônios desligados (ReLU = 0)": "—" if i == L - 1 else str(int((A[0] == 0).sum()))})
    return out


# ============================================================== Q6 — um passo da descida do gradiente
def gradient_step(x: Sequence[float], w: Sequence[float], b: float, y: float, eta: float = 0.5) -> Dict[str, Any]:
    """Neurônio sigmoide com entropia cruzada: dL/dz = a − y; dL/dw = (a − y)·x; dL/db = a − y."""
    x, w = np.asarray(x, float), np.asarray(w, float)
    z = float(x @ w + b)
    a = float(sigmoid(z))
    loss = -(y * math.log(max(a, 1e-12)) + (1 - y) * math.log(max(1 - a, 1e-12)))
    dz = a - y
    gw, gb = dz * x, dz
    w2, b2 = w - eta * gw, b - eta * gb
    a2 = float(sigmoid(x @ w2 + b2))
    loss2 = -(y * math.log(max(a2, 1e-12)) + (1 - y) * math.log(max(1 - a2, 1e-12)))
    return {"z": round(z, 4), "a": round(a, 4), "perda": round(loss, 4), "dL/dz": round(dz, 4),
            "dL/dw": np.round(gw, 4).tolist(), "dL/db": round(gb, 4), "w novo": np.round(w2, 4).tolist(),
            "b novo": round(b2, 4), "a novo": round(a2, 4), "perda nova": round(loss2, 4)}


# ============================================================== Q7 — curva de treino × validação e próximo experimento
def diagnose_curve(history: Dict[str, List[float]]) -> Dict[str, Any]:
    tr = [float(v) for v in (history or {}).get("train_loss") or []]
    va = [float(v) for v in (history or {}).get("val_loss") or []]
    if len(tr) < 3:
        return {"diagnostico": "poucas épocas", "texto": "O treino tem menos de 3 épocas registradas.", "melhor_epoca": None}
    if len(va) < 3:
        return {"diagnostico": "sem validação", "melhor_epoca": None,
                "texto": "Esta versão não guardou a perda de validação por época; só dá para ver a de treino."}
    n = min(len(tr), len(va))
    tr, va = tr[:n], va[:n]
    best = int(np.argmin(va))
    gap = va[-1] - tr[-1]
    rise = va[-1] - va[best]
    rel_gap = gap / max(abs(va[best]), 1e-9)
    diffs = np.diff(va)
    osc = float(np.mean(np.sign(diffs[1:]) != np.sign(diffs[:-1]))) if len(diffs) > 2 else 0.0
    amp = float(np.mean(np.abs(diffs))) / max(abs(float(np.mean(va))), 1e-9) if len(diffs) else 0.0
    half = va[n // 2:]
    trend_down = len(half) > 2 and half[-1] < half[0] - 0.5 * float(np.mean(np.abs(diffs)))
    drop_tr = (tr[0] - tr[-1]) / max(abs(tr[0]), 1e-9)
    if rise > 0.002 and best < n - 2 and rel_gap > 0.02:
        kind = "sobreajuste"
        txt = (f"A validação foi melhor na época {best + 1} e piorou depois (+{rise:.4f}) enquanto o treino seguiu caindo: "
               "a rede começou a decorar as partidas do treino. A parada antecipada guarda a época de menor validação.")
    elif osc > 0.55 and n > 6 and amp > 0.01 and not trend_down:
        kind = "oscilação"
        txt = "A perda de validação sobe e desce quase toda época: o passo (taxa de aprendizado) está grande."
    elif drop_tr < 0.03:
        kind = "subajuste"
        txt = "A perda de treino quase não caiu: a rede não está conseguindo aprender nem o treino."
    else:
        kind = "equilibrado"
        txt = (f"Treino e validação caem juntos e ficam próximos (diferença {gap:+.4f}); melhor época {best + 1} de {n}.")
    return {"diagnostico": kind, "texto": txt, "melhor_epoca": best + 1, "epocas": n, "gap_final": round(gap, 5),
            "oscilacao": round(osc, 2), "amplitude_rel": round(amp, 4), "queda_treino_pct": round(100 * drop_tr, 1)}


def suggest_next_experiment(version: Dict[str, Any]) -> Dict[str, Any]:
    """A partir do último treino, sugere os próximos parâmetros (o porquê vem da matéria, Q7)."""
    hidden = [int(h) for h in (version.get("hidden") or [32, 16])]
    eta = float(version.get("learning_rate") or 0.01)
    l2 = float(version.get("l2") or 0.0)
    epochs = int(version.get("epochs") or 30)
    d = diagnose_curve(version.get("history") or {})
    kind = d["diagnostico"]
    new = {"hidden": list(hidden), "learning_rate": eta, "l2": l2, "epochs": epochs}
    why: List[str] = []
    if kind == "sobreajuste":
        new["l2"] = 1e-3 if l2 < 1e-3 else min(l2 * 10, 1e-2)
        new["hidden"] = [max(4, h // 2) for h in hidden]
        why += ["sobreajuste → mais regularização L2 (pesos menores, fronteira mais simples)",
                "rede menor (metade dos neurônios) → menos capacidade de decorar",
                "manter a parada antecipada (paciência 10) — ela já devolve a melhor época"]
    elif kind == "oscilação":
        new["learning_rate"] = max(round(eta / 3, 5), 1e-4)
        why += ["oscilação → taxa de aprendizado 3× menor (passos menores no vale da perda)"]
    elif kind == "subajuste":
        new["hidden"] = [h * 2 for h in hidden]
        new["epochs"] = min(epochs * 2, 200)
        new["l2"] = l2 / 10 if l2 else 0.0
        why += ["subajuste → rede maior e mais épocas", "menos regularização (ela está segurando o aprendizado)"]
    elif kind == "equilibrado":
        why += ["curva saudável: a capacidade está boa; o que mais ajuda agora é MAIS PARTIDAS no treino",
                "teste também o experimento enxuto (só distância, ângulo, marcação, passes) — o comparativo mostrou que as "
                "zonas repetem informação"]
        new["features"] = "enxutas (E/F/G)"
    else:
        why += ["treine com a parada antecipada ligada para registrar a curva de validação"]
    cmd = (f"python -m src.machine_learning.model_registry --treinar --ocultas {','.join(map(str, new['hidden']))} "
           f"--eta {new['learning_rate']} --l2 {new['l2']} --epocas {new['epochs']}")
    return {"diagnostico": d, "atual": {"hidden": hidden, "learning_rate": eta, "l2": l2, "epochs": epochs},
            "sugerido": new, "porque": why, "comando": cmd}


# ============================================================== Q8 — matriz de confusão e paradoxo da acurácia
def confusion(y_true: Sequence[int], p: Sequence[float], threshold: float = 0.5) -> Dict[str, Any]:
    y = np.asarray(y_true, int)
    pr = (np.asarray(p, float) >= threshold).astype(int)
    tp = int(((pr == 1) & (y == 1)).sum())
    fp = int(((pr == 1) & (y == 0)).sum())
    fn = int(((pr == 0) & (y == 1)).sum())
    tn = int(((pr == 0) & (y == 0)).sum())
    n = max(len(y), 1)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if prec is not None and rec is not None else None)
    pos = float(y.mean()) if len(y) else 0.0
    return {"limiar": threshold, "VP": tp, "FP": fp, "FN": fn, "VN": tn, "acuracia": round((tp + tn) / n, 4),
            "precisao": None if prec is None else round(prec, 4), "revocacao": None if rec is None else round(rec, 4),
            "f1": None if f1 is None else round(f1, 4), "positivos_pct": round(100 * pos, 2),
            "acuracia_do_preguicoso": round(1 - pos, 4),
            "paradoxo": (f"Um modelo \"preguiçoso\" que responde sempre \"não vai ter chute\" acerta {100 * (1 - pos):.1f}% "
                         f"(só {100 * pos:.1f}% das posses terminam em chute) e não serve para nada: revocação 0. "
                         "Por isso o laboratório julga pela log-loss/AUC e olha precisão, revocação e F1.")}


def best_f1_threshold(y_true, p) -> Dict[str, Any]:
    best = None
    for t in np.round(np.arange(0.05, 0.95, 0.01), 2):
        c = confusion(y_true, p, float(t))
        if c["f1"] is not None and (best is None or c["f1"] > best["f1"]):
            best = c
    return best or confusion(y_true, p, 0.5)


# ============================================================== Q9 — arquiteturas
ARCHITECTURES = [
    {"arquitetura": "MLP (perceptron multicamadas)", "serve para": "dados em tabela (cada jogada = 15 números)",
     "no laboratório": "✅ EM USO — perigo da posse e seletor do assistente", "por quê": "nossas entradas são tabulares"},
    {"arquitetura": "CNN (convolucional)", "serve para": "imagens / grades (vizinhança importa)",
     "no laboratório": "Candidata: mapa de calor do campo como imagem 12×8", "por quê":
     "não usada: sem tracking aberto do Brasil, o \"campo-imagem\" teria poucos pontos"},
    {"arquitetura": "RNN", "serve para": "sequências (ordem importa)", "no laboratório":
     "Candidata: a posse como sequência de passes", "por quê": "memória curta; gradiente some em sequências longas"},
    {"arquitetura": "LSTM", "serve para": "sequências longas (portas de memória)", "no laboratório":
     "Próximo passo natural para a posse lance a lance", "por quê": "exige muito mais jogos com lances que os ~32 mil atuais por liga"},
    {"arquitetura": "Transformer (atenção)", "serve para": "texto e sequências longas em paralelo",
     "no laboratório": "É o que está por trás de LLMs como o Gemini (desligado por padrão)", "por quê":
     "treinar um do zero pede bilhões de exemplos; usamos regras + seletor treinável"},
    {"arquitetura": "Autoencoder", "serve para": "comprimir e achar o \"normal\" (anomalias)",
     "no laboratório": "Candidato: \"jogo típico\" × jogo fora da curva", "por quê":
     "hoje o fora da curva é feito com percentis da base, mais explicáveis"},
]


# ============================================================== Q10 — codificação, seleção e mutação
def binary_encoding(squad: Sequence[str], chosen: Sequence[str]) -> Dict[str, Any]:
    bits = "".join("1" if s in set(chosen) else "0" for s in squad)
    return {"cromossomo": bits, "comprimento": len(bits), "uns": bits.count("1"),
            "texto": "Cada gene é um atleta do elenco: 1 = escalado, 0 = fora. Restrição: exatamente 11 uns."}


def roulette_vs_tournament(fitness: Sequence[float], k: int = 3) -> List[Dict[str, Any]]:
    """Probabilidade de cada indivíduo ser escolhido: roleta (proporcional) × torneio de tamanho k (sem reposição)."""
    f = np.asarray(fitness, float)
    shift = f - min(f.min(), 0)                 # roleta exige aptidão ≥ 0
    roul = shift / shift.sum() if shift.sum() > 0 else np.full(len(f), 1 / len(f))
    n = len(f)
    order = np.argsort(-f)
    rank = np.empty(n, int)
    rank[order] = np.arange(n)                  # 0 = melhor
    tour = []
    for r in rank:
        worse = n - 1 - r                       # vence se for escolhido e os outros k−1 forem piores
        p = (math.comb(worse, k - 1) / math.comb(n, k)) if worse >= k - 1 and n >= k else 0.0
        tour.append(p)
    return [{"indivíduo": i + 1, "aptidão": round(float(f[i]), 1), "roleta %": round(100 * float(roul[i]), 1),
             f"torneio k={k} %": round(100 * tour[i], 1)} for i in range(n)]


def expected_mutations(length: int, p_bit: float) -> Dict[str, Any]:
    e = length * p_bit
    p0 = (1 - p_bit) ** length
    return {"bits": length, "p por bit": p_bit, "esperado de bits mutados": round(e, 3),
            "chance de nenhum mutar": round(p0, 4), "chance de ≥1 mutar": round(1 - p0, 4)}


# ============================================================== Q11 — penalidade R
def penalized_fitness(base: float, violations: float, R: float) -> Dict[str, Any]:
    return {"f(x)": base, "violações": violations, "R": R, "f'(x) = f(x) − R·violações": base - R * violations}


# ============================================================== Q12 — pseudocódigo e diagnóstico da convergência
GA_PSEUDOCODE = """\
P ← população inicial (1 = XI húngaro, demais aleatórios)        # semente boa + diversidade
para g = 1 … G:                                                   # critério de parada: G gerações
    avaliar f'(x) = Σ nota×encaixe + bônus contra o rival − R·(lesionados)
    E ← os e melhores de P                                        # ELITISMO: nunca perde a melhor solução
    filhos ← E
    enquanto |filhos| < N:
        pai ← torneio(P, k=3); mãe ← torneio(P, k=3)              # INTENSIFICAÇÃO (pressão seletiva)
        filho ← cruzamento uniforme(pai, mãe) + reparo (sem atleta repetido)
        com probabilidade pm: filho ← mutação(troca 2 vagas | entra alguém do banco)   # EXPLORAÇÃO
        filhos ← filhos ∪ {filho}
    P ← filhos
devolver o melhor de P (comparado com o XI húngaro)"""


def ga_convergence(history: Sequence[float]) -> Dict[str, Any]:
    h = [float(v) for v in history or []]
    if not h:
        return {"texto": "Sem histórico."}
    final = h[-1]
    hit = next((i for i, v in enumerate(h) if v >= final - 1e-9), len(h) - 1)
    stagn = len(h) - 1 - hit
    monotone = all(b >= a - 1e-9 for a, b in zip(h, h[1:]))
    txt = (f"A melhor aptidão chegou a {final:.1f} na geração {hit + 1} e ficou parada por {stagn} gerações. "
           + ("Nunca caiu de uma geração para outra — é o efeito do ELITISMO. " if monotone else "")
           + ("Estagnou cedo: para explorar mais, aumente a mutação ou a população; para intensificar, aumente o torneio."
              if stagn > 0.6 * len(h) else "Ainda melhorava perto do fim: mais gerações podem ajudar."))
    return {"melhor": round(final, 1), "geracao_do_melhor": hit + 1, "geracoes_paradas": stagn, "monotona": monotone,
            "texto": txt}


def example_ga_squad(seed: int = 7):
    """Elenco de exemplo (sem dado real) para demonstrar o AG quando o usuário ainda não escolheu um time."""
    import pandas as pd

    roles = ["GK", "GK", "RB", "LB", "CB", "CB", "CB", "DM", "CM", "CM", "AM", "RW", "LW", "ST", "ST", "CM", "RB", "LW"]
    rng = np.random.default_rng(seed)
    rows = [{"nome": f"Atleta {i + 1}", "papel": r, "nota": float(np.round(rng.uniform(45, 85), 1)),
             "lesao": "lesionado" if i == 13 else ""} for i, r in enumerate(roles)]
    return pd.DataFrame(rows)


def run_example_ga(formation: str = "4-3-3", seed: int = 7, generations: int = 60, pop: int = 40,
                   p_mut: float = 0.35) -> Dict[str, Any]:
    from src.squad.genetic import LineupGA

    ga = LineupGA(example_ga_squad(seed), formation, (), seed=seed, pop=pop, generations=generations, p_mut=p_mut)
    out = ga.run(seed_with_baseline=False)          # sem a semente húngara: dá para VER o AG convergindo sozinho
    out["convergencia"] = ga_convergence(out["historico"])
    out["R"] = float(ga.penalty.max()) if len(ga.penalty) else 0.0
    return out
