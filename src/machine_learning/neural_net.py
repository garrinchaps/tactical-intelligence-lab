"""
Rede neural implementada do zero (NumPy puro) — Camada B.

Objetivo didático e de inspeção do mecanismo de aprendizado, não superar o estado da arte.

Arquitetura: perceptron multicamadas totalmente conectado.
* Camadas ocultas com ReLU; saída com 1 neurônio sigmoide (probabilidade de perigo).
* Perda: entropia cruzada binária (BCE), com regularização L2 opcional.
* Inicialização de He (Kaiming): W ~ N(0, sqrt(2 / n_entrada)), adequada para ReLU porque
  preserva a variância das ativações entre camadas; vieses começam em zero.
* Treino: descida de gradiente em mini-lotes, taxa de aprendizado configurável, histórico
  de perda por época (treino e validação).
* Backpropagation explícito (sem diferenciação automática):
      saída:   dZ_L = A_L − y                       (sigmoide + BCE simplificam assim)
      camada:  dW_l = A_{l−1}ᵀ · dZ_l / m + λ·W_l/m
               db_l = soma(dZ_l) / m
               dA_{l−1} = dZ_l · W_lᵀ
               dZ_{l−1} = dA_{l−1} ⊙ 1[Z_{l−1} > 0]   (derivada da ReLU)
* Estrutura "pais e filhos": cada neurônio conhece de quais neurônios da camada anterior
  recebe entrada (pais) e para quais envia (filhos), com o peso de cada conexão.
* Persistência: arquivo .npz com pesos, vieses, arquitetura, hiperparâmetros e histórico.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class Neuron:
    """Visão de um neurônio: identificação, viés e conexões com pais e filhos."""
    layer: int
    index: int
    bias: float
    activation: str
    parents: List[Tuple[str, float]] = field(default_factory=list)   # (id do pai, peso pai→este)
    children: List[Tuple[str, float]] = field(default_factory=list)  # (id do filho, peso este→filho)

    @property
    def id(self) -> str:
        return f"L{self.layer}N{self.index}"


class NeuralNetwork:
    def __init__(self, layer_sizes: Sequence[int], learning_rate: float = 0.05, l2: float = 0.0,
                 seed: int = 42, feature_names: Optional[List[str]] = None):
        if len(layer_sizes) < 2 or layer_sizes[-1] != 1:
            raise ValueError("layer_sizes deve ter entrada, ocultas e saída com 1 neurônio, ex.: [8, 16, 8, 1]")
        self.layer_sizes = [int(s) for s in layer_sizes]
        self.learning_rate = float(learning_rate)
        self.l2 = float(l2)
        self.seed = int(seed)
        self.feature_names = feature_names or [f"x{i}" for i in range(self.layer_sizes[0])]
        rng = np.random.default_rng(self.seed)
        # Inicialização de He: desvio padrão sqrt(2 / fan_in)
        self.weights: List[np.ndarray] = [
            rng.normal(0.0, np.sqrt(2.0 / n_in), size=(n_in, n_out))
            for n_in, n_out in zip(self.layer_sizes[:-1], self.layer_sizes[1:])
        ]
        self.biases: List[np.ndarray] = [np.zeros((1, n_out)) for n_out in self.layer_sizes[1:]]
        self.history: Dict[str, List[float]] = {"train_loss": [], "val_loss": []}
        # padronização das entradas (aprendida no treino)
        self.mu: Optional[np.ndarray] = None
        self.sigma: Optional[np.ndarray] = None

    # ------------------------------------------------------------ funções
    @staticmethod
    def relu(z: np.ndarray) -> np.ndarray:
        return np.maximum(0.0, z)

    @staticmethod
    def relu_grad(z: np.ndarray) -> np.ndarray:
        return (z > 0).astype(float)

    @staticmethod
    def sigmoid(z: np.ndarray) -> np.ndarray:
        z = np.clip(z, -60.0, 60.0)
        return 1.0 / (1.0 + np.exp(-z))

    def loss(self, y_hat: np.ndarray, y: np.ndarray) -> float:
        eps = 1e-12
        y = y.reshape(-1, 1)
        bce = -np.mean(y * np.log(y_hat + eps) + (1 - y) * np.log(1 - y_hat + eps))
        reg = 0.5 * self.l2 * sum(float(np.sum(W * W)) for W in self.weights) / max(len(y), 1)
        return float(bce + reg)

    # ------------------------------------------------------------ forward
    def forward(self, X: np.ndarray) -> Tuple[np.ndarray, List[np.ndarray], List[np.ndarray]]:
        """Devolve (saída, pré-ativações Z por camada, ativações A por camada — A[0] = X)."""
        A = [X]
        Zs = []
        for i, (W, b) in enumerate(zip(self.weights, self.biases)):
            Z = A[-1] @ W + b
            Zs.append(Z)
            A.append(self.sigmoid(Z) if i == len(self.weights) - 1 else self.relu(Z))
        return A[-1], Zs, A

    # ----------------------------------------------------------- backward
    def backward(self, y: np.ndarray, Zs: List[np.ndarray], A: List[np.ndarray]
                 ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        m = A[0].shape[0]
        y = y.reshape(-1, 1)
        dW = [np.zeros_like(W) for W in self.weights]
        db = [np.zeros_like(b) for b in self.biases]
        dZ = A[-1] - y                                    # sigmoide + BCE
        for l in range(len(self.weights) - 1, -1, -1):
            dW[l] = A[l].T @ dZ / m + self.l2 * self.weights[l] / m
            db[l] = dZ.sum(axis=0, keepdims=True) / m
            if l > 0:
                dA_prev = dZ @ self.weights[l].T
                dZ = dA_prev * self.relu_grad(Zs[l - 1])
        return dW, db

    # -------------------------------------------------------------- treino
    def _standardize(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        if fit or self.mu is None:
            self.mu = X.mean(axis=0, keepdims=True)
            self.sigma = X.std(axis=0, keepdims=True) + 1e-8
        return (X - self.mu) / self.sigma

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 60, batch_size: int = 256,
            X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
            class_weight_balanced: bool = False, verbose: bool = False) -> "NeuralNetwork":
        X = self._standardize(np.asarray(X, dtype=float), fit=True)
        y = np.asarray(y, dtype=float).reshape(-1)
        Xv = self._standardize(np.asarray(X_val, dtype=float)) if X_val is not None else None
        rng = np.random.default_rng(self.seed + 1)
        w_pos = (len(y) - y.sum()) / max(y.sum(), 1) if class_weight_balanced else 1.0
        for epoch in range(epochs):
            order = rng.permutation(len(X))
            for start in range(0, len(X), batch_size):
                idx = order[start:start + batch_size]
                out, Zs, A = self.forward(X[idx])
                yb = y[idx]
                if class_weight_balanced:
                    # repondera o erro da saída para equilibrar as classes
                    out_w = np.where(yb.reshape(-1, 1) == 1, w_pos, 1.0)
                    dW, db = self._weighted_backward(yb, Zs, A, out_w)
                else:
                    dW, db = self.backward(yb, Zs, A)
                for l in range(len(self.weights)):
                    self.weights[l] -= self.learning_rate * dW[l]
                    self.biases[l] -= self.learning_rate * db[l]
            self.history["train_loss"].append(self.loss(self.forward(X)[0], y))
            if Xv is not None and y_val is not None:
                self.history["val_loss"].append(self.loss(self.forward(Xv)[0], np.asarray(y_val, dtype=float)))
            if verbose:
                print(f"época {epoch + 1}: perda treino {self.history['train_loss'][-1]:.4f}")
        return self

    def _weighted_backward(self, y, Zs, A, w):
        m = A[0].shape[0]
        y = y.reshape(-1, 1)
        dW = [np.zeros_like(W) for W in self.weights]
        db = [np.zeros_like(b) for b in self.biases]
        dZ = (A[-1] - y) * w
        for l in range(len(self.weights) - 1, -1, -1):
            dW[l] = A[l].T @ dZ / m + self.l2 * self.weights[l] / m
            db[l] = dZ.sum(axis=0, keepdims=True) / m
            if l > 0:
                dZ = (dZ @ self.weights[l].T) * self.relu_grad(Zs[l - 1])
        return dW, db

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.forward(self._standardize(np.asarray(X, dtype=float)))[0].reshape(-1)

    # ---------------------------------------------------- checagem de gradiente
    def gradient_check(self, X: np.ndarray, y: np.ndarray, eps: float = 1e-5, n_checks: int = 20,
                       seed: int = 0) -> Dict[str, float]:
        """
        Compara o gradiente analítico (backprop) com o numérico por diferenças centrais
        (L(w+ε) − L(w−ε)) / 2ε em parâmetros sorteados. Devolve o maior erro relativo.
        Usa X como está (sem padronização) para isolar o mecanismo.
        """
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        _, Zs, A = self.forward(X)
        dW, db = self.backward(y, Zs, A)
        rng = np.random.default_rng(seed)
        rel_errors = []
        for _ in range(n_checks):
            l = int(rng.integers(0, len(self.weights)))
            use_bias = bool(rng.random() < 0.3)
            P = self.biases[l] if use_bias else self.weights[l]
            G = db[l] if use_bias else dW[l]
            i, j = int(rng.integers(0, P.shape[0])), int(rng.integers(0, P.shape[1]))
            old = P[i, j]
            P[i, j] = old + eps
            lp = self.loss(self.forward(X)[0], y)
            P[i, j] = old - eps
            lm = self.loss(self.forward(X)[0], y)
            P[i, j] = old
            num = (lp - lm) / (2 * eps)
            ana = G[i, j]
            rel_errors.append(abs(num - ana) / max(abs(num) + abs(ana), 1e-12))
        return {"max_relative_error": float(max(rel_errors)), "mean_relative_error": float(np.mean(rel_errors)),
                "checks": n_checks}

    # --------------------------------------------------------- pais e filhos
    def neurons(self) -> List[Neuron]:
        """Todos os neurônios com seus pais (entradas) e filhos (saídas) e os pesos das conexões."""
        out: List[Neuron] = []
        for l, size in enumerate(self.layer_sizes):
            for k in range(size):
                if l == 0:
                    n = Neuron(0, k, 0.0, "entrada")
                else:
                    act = "sigmoide" if l == len(self.layer_sizes) - 1 else "ReLU"
                    n = Neuron(l, k, float(self.biases[l - 1][0, k]), act,
                               parents=[(f"L{l - 1}N{p}", float(self.weights[l - 1][p, k]))
                                        for p in range(self.layer_sizes[l - 1])])
                if l < len(self.layer_sizes) - 1:
                    n.children = [(f"L{l + 1}N{c}", float(self.weights[l][k, c]))
                                  for c in range(self.layer_sizes[l + 1])]
                out.append(n)
        return out

    def neuron_label(self, neuron_id: str) -> str:
        l, k = neuron_id[1:].split("N")
        if int(l) == 0:
            return self.feature_names[int(k)]
        if int(l) == len(self.layer_sizes) - 1:
            return "saída: P(perigo)"
        return neuron_id

    def n_parameters(self) -> int:
        return int(sum(W.size + b.size for W, b in zip(self.weights, self.biases)))

    # ---------------------------------------------------------- persistência
    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"W{i}": W for i, W in enumerate(self.weights)}
        arrays.update({f"b{i}": b for i, b in enumerate(self.biases)})
        meta = {"layer_sizes": self.layer_sizes, "learning_rate": self.learning_rate, "l2": self.l2,
                "seed": self.seed, "feature_names": self.feature_names, "history": self.history}
        np.savez(path, meta=json.dumps(meta), mu=self.mu if self.mu is not None else np.array([]),
                 sigma=self.sigma if self.sigma is not None else np.array([]), **arrays)
        return path

    @classmethod
    def load(cls, path: Path | str) -> "NeuralNetwork":
        data = np.load(Path(path), allow_pickle=False)
        meta = json.loads(str(data["meta"]))
        net = cls(meta["layer_sizes"], meta["learning_rate"], meta["l2"], meta["seed"], meta["feature_names"])
        net.weights = [data[f"W{i}"] for i in range(len(net.weights))]
        net.biases = [data[f"b{i}"] for i in range(len(net.biases))]
        net.history = meta["history"]
        if data["mu"].size:
            net.mu, net.sigma = data["mu"], data["sigma"]
        return net

    def summary(self) -> Dict[str, Any]:
        return {"arquitetura": " → ".join(str(s) for s in self.layer_sizes), "parametros": self.n_parameters(),
                "ativacoes": "ReLU nas ocultas, sigmoide na saída", "inicializacao": "He (N(0, √(2/n_entrada)))",
                "perda": "entropia cruzada binária" + (f" + L2 (λ={self.l2})" if self.l2 else ""),
                "taxa_aprendizado": self.learning_rate, "epocas_treinadas": len(self.history["train_loss"])}
