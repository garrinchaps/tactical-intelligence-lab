"""
Registro de versões da rede neural de perigo de posse (campeão × desafiante).

Como o aprendizado fica real e mensurável:
1. **Validação fixa.** Um conjunto de partidas é separado UMA vez (e nunca entra no treino). Todas as versões são
   medidas nele, então "melhorou" significa melhorou nas mesmas partidas.
2. **Dados que crescem.** Cada treino usa todas as partidas com eventos que já estão no banco (a amostra de
   demonstração + o que a sincronização baixou). Quanto mais partidas, mais exemplos para aprender.
3. **Promoção só se melhorar.** O desafiante só substitui o campeão se reduzir a perda (log-loss) na validação
   fixa; senão é registrado como rejeitado e o Analista IA continua com o campeão.
4. **Uso direto.** O campeão é o modelo que o Analista IA usa para responder "quem criou mais perigo", nos planos
   de jogo e nos dossiês de atletas — cada resposta cita a versão e a métrica de validação.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

from src.machine_learning.danger_dataset import MODEL_FEATURES as FEATURES, LEGACY_FEATURES, build_match_rows
from src.machine_learning.neural_net import NeuralNetwork

ROOT = Path("models/registry/danger")
DEMO = Path("data/demo/danger_sample_wc2022.csv.gz")
ROWS_CACHE = Path("data/processed/danger_rows_db.csv.gz")
FULL = Path("data/processed/danger_full.csv.gz")      # gerado por `python -m src.evaluation.protocol` (Copa 2022 + 360)
MIN_360_SHARE = 0.8                                    # partidas do banco só entram se tiverem densidade medida (360)
MIN_IMPROVEMENT = 0.0005        # redução mínima de log-loss para promover (evita "melhora" por ruído)
MAX_CV_AUC_STD = 0.05           # estabilidade: AUC das dobras do GroupKFold não pode variar mais que isso
MAX_AUC_DROP = 0.005            # e a AUC no validação fixa não pode cair mais que isso em relação ao campeão
VAL_FRACTION = 0.25

# v36 — os 4 experimentos controlados pedidos pelo usuário (todos: Adam, até 100 épocas, lote 256, parada
# antecipada com paciência 10, inicialização He nas camadas ReLU, treino do zero — sem herdar pesos do campeão).
EXPERIMENTS: Dict[str, Dict[str, Any]] = {
    "A": {"hidden": [32], "learning_rate": 0.001, "l2": 0.0001},
    "B": {"hidden": [32, 16], "learning_rate": 0.001, "l2": 0.0001},
    "C": {"hidden": [32, 16, 8], "learning_rate": 0.001, "l2": 0.001},
    "D": {"hidden": [64, 32, 16], "learning_rate": 0.0005, "l2": 0.001},
}
EXPERIMENT_ORDER = ["B", "A", "C", "D"]          # começar pelo B
EXP_EPOCHS, EXP_BATCH, EXP_PATIENCE = 100, 256, 10


@dataclass
class Version:
    version: int
    created: str
    hidden: List[int]
    learning_rate: float
    epochs: int
    l2: float
    batch_size: int
    n_matches_train: int
    n_samples_train: int
    val_auc: float
    val_logloss: float
    promoted: bool
    reason: str
    origin: str = "treino"
    history: Dict[str, List[float]] = field(default_factory=dict)
    # validação agrupada por partida (GroupKFold) e critério estatístico de promoção
    cv_folds: int = 0
    cv_seeds: int = 0
    cv_logloss_mean: Optional[float] = None
    cv_logloss_std: Optional[float] = None
    cv_auc_mean: Optional[float] = None
    test_gain: Optional[float] = None
    gain_ci_low: Optional[float] = None
    gain_ci_high: Optional[float] = None
    p_gain_positive: Optional[float] = None
    cv_auc_std: Optional[float] = None
    optimizer: str = "sgd"
    warm_start: bool = False
    epochs_run: Optional[int] = None
    density_360_share: Optional[float] = None
    density_proxy_matches: int = 0
    n_features: Optional[int] = None


class DangerModelRegistry:
    def __init__(self, root: Optional[Path] = None):
        # a pasta padrão é lida na hora (e não na importação), para testes e ferramentas poderem redirecioná-la
        self.root = Path(root) if root is not None else Path(ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.root / "registry.json"
        self.meta = self._read()

    # ------------------------------------------------------------ persistência
    def _read(self) -> Dict[str, Any]:
        if self.meta_path.exists():
            try:
                return json.loads(self.meta_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        return {"validation_matches": [], "champion": None, "versions": []}

    def _write(self) -> None:
        self.meta_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def versions(self) -> pd.DataFrame:
        return pd.DataFrame(self.meta["versions"]).drop(columns=["history"], errors="ignore")

    def champion_info(self) -> Optional[Dict[str, Any]]:
        c = self.meta.get("champion")
        return next((v for v in self.meta["versions"] if v["version"] == c), None) if c is not None else None

    def champion(self) -> Optional[NeuralNetwork]:
        info = self.champion_info()
        if not info:
            return None
        p = self.root / f"v{info['version']:03d}.npz"
        return NeuralNetwork.load(p) if p.exists() else None

    # ------------------------------------------------------------------ dados
    @staticmethod
    def dataset(load_db_rows: Optional[Callable[[], pd.DataFrame]] = None, include_proxy: bool = True) -> pd.DataFrame:
        """
        Todos os exemplos de partidas com eventos, sem duplicar jogos:
        amostra de demonstração → protocolo completo → eventos do banco. Por padrão, entram também as partidas
        cuja densidade de adversários é estimada por eventos; `density_is_360` informa ao modelo se a medida veio
        de tracking 360. Partidas só com placar/boxscore não viram exemplos de ações.
        """
        parts: List[pd.DataFrame] = []
        if FULL.exists():
            parts.append(pd.read_csv(FULL))
        if DEMO.exists():
            demo = pd.read_csv(DEMO)
            have = set(parts[0]["match_id"]) if parts else set()
            parts.append(demo[~demo["match_id"].isin(have)])
        if load_db_rows is not None:
            extra = load_db_rows()
            if extra is not None and not extra.empty:
                share = (extra["density_source"] == "statsbomb_360").groupby(extra["match_id"]).mean()
                ok = share.index if include_proxy else share[share >= MIN_360_SHARE].index
                have = set(pd.concat(parts)["match_id"]) if parts else set()
                parts.append(extra[extra["match_id"].isin(ok) & ~extra["match_id"].isin(have)])
        data = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if data.empty:
            return data
        # Compatibilidade com CSVs/NPZ antigos: ausência do indicador significa fonte não identificada,
        # nunca tracking 360 confirmado.
        if "density_is_360" not in data:
            if "density_source" in data:
                data["density_is_360"] = data["density_source"].eq("statsbomb_360").astype(float)
            else:
                data["density_is_360"] = 0.0
        data["density_is_360"] = pd.to_numeric(data["density_is_360"], errors="coerce").fillna(0.0).clip(0, 1)
        return data.dropna(subset=FEATURES + ["target"]).reset_index(drop=True)

    def _validation_ids(self, data: pd.DataFrame) -> List[int]:
        """Escolhidas uma vez (determinístico) e depois fixas."""
        if not self.meta["validation_matches"]:
            ids = sorted(int(m) for m in data["match_id"].unique())
            rng = np.random.default_rng(20221218)
            k = max(1, int(round(len(ids) * VAL_FRACTION)))
            self.meta["validation_matches"] = sorted(int(m) for m in rng.choice(ids, size=k, replace=False))
            self._write()
        return self.meta["validation_matches"]

    @property
    def val_path(self) -> Path:
        return self.root / "validacao_fixa.csv.gz"

    def split(self, data: pd.DataFrame):
        """Treino = tudo fora das partidas de validação. Validação = arquivo congelado na 1ª rodada (mesmas linhas sempre)."""
        val_ids = set(self._validation_ids(data))
        train = data[~data["match_id"].isin(val_ids)]
        if self.val_path.exists():
            val = pd.read_csv(self.val_path)
        else:
            val = data[data["match_id"].isin(val_ids)]
            val.to_csv(self.val_path, index=False, compression="gzip")
        return train, val

    def learning_curve(self, data: pd.DataFrame, fractions=(0.25, 0.5, 0.75, 1.0), hidden=(32, 16), epochs: int = 25,
                       seeds=(1, 2)) -> pd.DataFrame:
        """Mesma rede, mesma validação, cada vez com mais partidas de treino: mostra que ela aprende com dados."""
        train, val = self.split(data)
        ids = sorted(train["match_id"].unique())
        rows = []
        for f in fractions:
            sub = train[train["match_id"].isin(ids[:max(1, int(len(ids) * f))])]
            ms = []
            for sd in seeds:
                net = NeuralNetwork([len(FEATURES), *hidden, 1], 0.05, 1e-3, seed=sd)
                net.fit(sub[FEATURES].to_numpy(float), sub["target"].to_numpy(int), epochs=epochs, batch_size=256)
                ms.append(self._evaluate(net, val))
            rows.append({"partidas_de_treino": int(sub["match_id"].nunique()), "acoes_de_treino": int(len(sub)),
                         "auc_validacao": round(float(np.mean([m["auc"] for m in ms])), 4),
                         "perda_validacao": round(float(np.mean([m["logloss"] for m in ms])), 5)})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ treino
    @staticmethod
    def _model_matrix(net: NeuralNetwork, rows: pd.DataFrame) -> np.ndarray:
        """Monta as colunas esperadas pelo modelo, inclusive campeões antigos de 14 entradas."""
        n_in = int(net.layer_sizes[0])
        names = list(getattr(net, "feature_names", []) or [])
        if len(names) == n_in and all(name in rows.columns for name in names):
            return rows[names].to_numpy(float)
        if n_in == len(FEATURES):
            return rows[FEATURES].to_numpy(float)
        if n_in == len(LEGACY_FEATURES):
            return rows[LEGACY_FEATURES].to_numpy(float)
        raise ValueError(f"modelo espera {n_in} variáveis, mas não há adaptador de compatibilidade")

    @staticmethod
    def _evaluate(net: NeuralNetwork, val: pd.DataFrame) -> Dict[str, float]:
        p = np.clip(net.predict_proba(DangerModelRegistry._model_matrix(net, val)), 1e-6, 1 - 1e-6)
        y = val["target"].to_numpy(int)
        return {"auc": round(float(roc_auc_score(y, p)), 4), "logloss": round(float(log_loss(y, p)), 5)}

    def evaluate_champion(self, data: pd.DataFrame) -> Optional[Dict[str, float]]:
        net = self.champion()
        if net is None:
            return None
        _, val = self.split(data)
        return self._evaluate(net, val)

    # ------------------------------------------------- validação agrupada
    @staticmethod
    def group_cv(train: pd.DataFrame, hidden: List[int], learning_rate: float, epochs: int, l2: float,
                 batch_size: int, folds: int = 5, seeds=(11, 23), optimizer: str = "sgd",
                 patience: int = 0) -> Dict[str, Any]:
        """
        GroupKFold por match_id (nenhuma partida aparece no treino e na validação da mesma dobra) × sementes.
        A padronização é ajustada só com o treino de cada dobra (fit dentro de `NeuralNetwork.fit`).
        Com `patience`, cada dobra separa ~10% das SUAS partidas de treino para a parada antecipada.
        """
        from sklearn.model_selection import GroupKFold

        groups = train["match_id"].to_numpy()
        k = int(min(folds, len(np.unique(groups))))
        if k < 2:
            return {"folds": 0, "seeds": 0, "logloss": [], "auc": []}
        X, y = train[FEATURES].to_numpy(float), train["target"].to_numpy(int)
        ll, auc = [], []
        for sd in seeds:
            for tr, va in GroupKFold(n_splits=k).split(X, y, groups):
                if len(np.unique(y[va])) < 2:
                    continue
                net = NeuralNetwork([len(FEATURES), *hidden, 1], learning_rate=learning_rate, l2=l2, seed=int(sd))
                fit_i, stop_i = tr, None
                if patience:
                    gids = np.unique(groups[tr])
                    if len(gids) > 9:
                        pick = set(np.random.default_rng(int(sd)).choice(gids, max(1, len(gids) // 10), replace=False))
                        mask = np.isin(groups[tr], list(pick))
                        fit_i, stop_i = tr[~mask], tr[mask]
                net.fit(X[fit_i], y[fit_i], epochs=epochs, batch_size=batch_size, optimizer=optimizer,
                        X_stop=X[stop_i] if stop_i is not None else None, y_stop=y[stop_i] if stop_i is not None else None,
                        patience=patience if stop_i is not None else 0)
                pr = np.clip(net.predict_proba(X[va]), 1e-6, 1 - 1e-6)
                ll.append(float(log_loss(y[va], pr)))
                auc.append(float(roc_auc_score(y[va], pr)))
        return {"folds": k, "seeds": len(seeds), "logloss": ll, "auc": auc}

    @staticmethod
    def paired_gain(champ: NeuralNetwork, chall: NeuralNetwork, test: pd.DataFrame, n_boot: int = 400,
                    seed: int = 7) -> Dict[str, float]:
        """Ganho de log-loss no validação fixa (campeão − desafiante) com bootstrap por PARTIDA (IC 95%)."""
        y = test["target"].to_numpy(int)
        pc = np.clip(champ.predict_proba(DangerModelRegistry._model_matrix(champ, test)), 1e-6, 1 - 1e-6)
        pn = np.clip(chall.predict_proba(DangerModelRegistry._model_matrix(chall, test)), 1e-6, 1 - 1e-6)
        loss = lambda p: -(y * np.log(p) + (1 - y) * np.log(1 - p))
        d = loss(pc) - loss(pn)                              # > 0 = desafiante melhor naquela ação
        g = test["match_id"].to_numpy()
        ids, inv = np.unique(g, return_inverse=True)
        sums = np.bincount(inv, weights=d, minlength=len(ids))
        cnts = np.bincount(inv, minlength=len(ids)).astype(float)
        rng = np.random.default_rng(seed)
        boots = []
        for _ in range(n_boot):
            pick = rng.integers(0, len(ids), len(ids))
            boots.append(sums[pick].sum() / max(cnts[pick].sum(), 1.0))
        boots = np.array(boots)
        return {"gain": float(d.mean()), "ci_low": float(np.percentile(boots, 2.5)),
                "ci_high": float(np.percentile(boots, 97.5)), "p_positive": float((boots > 0).mean())}

    def train_round(self, data: pd.DataFrame, hidden: List[int], learning_rate: float = 0.01, epochs: int = 30,
                    l2: float = 1e-3, batch_size: int = 256, seed: Optional[int] = None,
                    origin: str = "treino", cv_folds: int = 3, cv_seeds=(11,), optimizer: str = "adam",
                    warm_start: Optional[bool] = None, patience: int = 4, cv_epochs: Optional[int] = None,
                    class_weight_balanced: bool = False,
                    progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """
        Treina um desafiante e decide a promoção:
          1. GroupKFold por partida no treino (nenhuma partida no treino e na validação da mesma dobra): estima a
             generalização da configuração e exige ESTABILIDADE (AUC das dobras com desvio ≤ MAX_CV_AUC_STD);
          2. treino final com Adam e parada antecipada numa fatia de partidas separada do próprio treino; se a
             arquitetura for a do campeão, começa dos pesos dele (ajuste fino com os dados novos — evolução contínua);
          3. comparação PAREADA com o campeão no VALIDAÇÃO FIXA (partidas que nunca treinam): promove se o ganho de
             log-loss ≥ MIN_IMPROVEMENT, o IC 95% do bootstrap por partida ficar acima de zero e a AUC não cair mais
             que MAX_AUC_DROP. Toda tentativa é registrada.
        O desvio entre dobras NÃO é usado como barreira de ganho: ele mede quanto as partidas diferem entre si
        (dezenas de vezes maior que qualquer melhoria real), não o ruído da comparação — essa é a função do IC
        pareado por partida.
        """
        say = progress or (lambda m: None)
        t0 = time.time()
        train, val = self.split(data)
        seed = int(seed if seed is not None else time.time()) % 100_000
        say(f"validação cruzada agrupada ({cv_folds} dobras por partida)…")
        cv = self.group_cv(train, hidden, learning_rate, cv_epochs or max(4, min(epochs, 12)), l2, batch_size, cv_folds,
                           cv_seeds, optimizer=optimizer, patience=patience if cv_epochs else 0) \
            if cv_folds else {"folds": 0, "seeds": 0, "logloss": [], "auc": []}
        cv_mean = round(float(np.mean(cv["logloss"])), 5) if cv["logloss"] else None
        cv_std = round(float(np.std(cv["logloss"], ddof=1)), 5) if len(cv["logloss"]) > 1 else None
        cv_auc_std = round(float(np.std(cv["auc"], ddof=1)), 4) if len(cv["auc"]) > 1 else None
        champ = self.champion_info()
        champ_net = self.champion() if champ else None
        same_architecture = champ_net is not None and list(champ_net.layer_sizes) == [len(FEATURES), *hidden, 1]
        warm = bool(same_architecture and (warm_start is None or warm_start))
        if warm_start and champ_net is not None and not same_architecture:
            say("ajuste fino ignorado: a arquitetura de entrada mudou; o desafiante começará do zero.")
        # fatia de parada antecipada: ~10% das partidas do treino (determinística pela semente)
        ids = np.array(sorted(train["match_id"].unique()))
        rng = np.random.default_rng(seed)
        stop_ids = set(rng.choice(ids, size=max(1, int(round(len(ids) * 0.1))), replace=False)) if len(ids) > 9 else set()
        fit_part = train[~train["match_id"].isin(stop_ids)] if stop_ids else train
        stop_part = train[train["match_id"].isin(stop_ids)] if stop_ids else None
        net = NeuralNetwork([len(FEATURES), *hidden, 1], learning_rate=learning_rate, l2=l2, seed=seed, feature_names=FEATURES)
        if warm:
            net.warm_start_from(champ_net)
        say("treino final" + (" (ajuste fino a partir do campeão)" if warm else "") + "…")
        net.fit(fit_part[FEATURES].to_numpy(float), fit_part["target"].to_numpy(int), epochs=epochs,
                batch_size=batch_size, X_val=val[FEATURES].to_numpy(float), y_val=val["target"].to_numpy(int),
                optimizer=optimizer, refit_scaler=not warm, class_weight_balanced=class_weight_balanced,
                X_stop=stop_part[FEATURES].to_numpy(float) if stop_part is not None else None,
                y_stop=stop_part["target"].to_numpy(int) if stop_part is not None else None,
                patience=patience if stop_part is not None else 0)
        m = self._evaluate(net, val)
        champ_now = self._evaluate(champ_net, val) if champ_net is not None else None
        pg = self.paired_gain(champ_net, net, val) if champ_net is not None else None
        if champ_now is None:
            promoted, reason = True, "primeira versão: vira o modelo usado pelo Analista IA"
        else:
            gain = pg["gain"]
            ok_min, ok_ci = gain >= MIN_IMPROVEMENT, pg["ci_low"] > 0
            ok_stable = cv_auc_std is None or cv_auc_std <= MAX_CV_AUC_STD
            ok_auc = m["auc"] >= champ_now["auc"] - MAX_AUC_DROP
            promoted = bool(ok_min and ok_ci and ok_stable and ok_auc)
            detail = (f"ganho no validação fixa {gain:+.5f} (IC 95% por partida {pg['ci_low']:+.5f} a {pg['ci_high']:+.5f}); "
                      f"GroupKFold: perda {cv_mean if cv_mean is not None else '—'} ± {cv_std if cv_std is not None else '—'}, "
                      f"desvio da AUC entre dobras {cv_auc_std if cv_auc_std is not None else '—'}")
            if promoted:
                reason = (f"promovida: {detail}. Perda {champ_now['logloss']:.5f} → {m['logloss']:.5f} "
                          f"(AUC {champ_now['auc']:.3f} → {m['auc']:.3f})")
            else:
                falhas = [t for t, ok in ((f"ganho < {MIN_IMPROVEMENT}", ok_min), ("IC 95% inclui zero", ok_ci),
                                          (f"instável entre dobras (desvio da AUC > {MAX_CV_AUC_STD})", ok_stable),
                                          (f"AUC caiu mais de {MAX_AUC_DROP}", ok_auc)) if not ok]
                reason = (f"rejeitada ({', '.join(falhas)}): {detail}; o Analista continua com o campeão "
                          f"v{champ['version']:03d}")
        v = len(self.meta["versions"]) + 1
        net.save(self.root / f"v{v:03d}.npz")
        share_360 = float(train["density_is_360"].mean()) if "density_is_360" in train and len(train) else None
        proxy_matches = int(train.loc[train["density_is_360"] < 0.5, "match_id"].nunique()) if "density_is_360" in train else 0
        rec = Version(v, time.strftime("%Y-%m-%d %H:%M"), list(hidden), learning_rate, epochs, l2, batch_size,
                      int(train["match_id"].nunique()), int(len(train)), m["auc"], m["logloss"], promoted, reason, origin,
                      {k: [round(float(x), 5) for x in vals] for k, vals in net.history.items()},
                      cv["folds"], cv["seeds"], cv_mean, cv_std,
                      round(float(np.mean(cv["auc"])), 4) if cv["auc"] else None,
                      round(pg["gain"], 6) if pg else None, round(pg["ci_low"], 6) if pg else None,
                      round(pg["ci_high"], 6) if pg else None, round(pg["p_positive"], 4) if pg else None,
                      cv_auc_std, optimizer, bool(warm), len(net.history.get("train_loss", [])),
                      density_360_share=round(share_360, 4) if share_360 is not None else None,
                      density_proxy_matches=proxy_matches, n_features=len(FEATURES))
        self.meta["versions"].append(asdict(rec))
        if promoted:
            self.meta["champion"] = v
        self._write()
        self._log_attempt(rec)
        say(f"concluído em {time.time() - t0:.0f} s")
        return {**asdict(rec), "champion_before": champ_now, "net": net, "seconds": round(time.time() - t0, 1)}

    def _log_attempt(self, rec: "Version") -> None:
        """Registro só-acréscimo de TODAS as tentativas (promovidas e rejeitadas)."""
        row = {k: v for k, v in asdict(rec).items() if k != "history"}
        with (self.root / "tentativas.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def auto_search(self, data: pd.DataFrame, trials: int = 3, epochs: int = 25, seed: int = 0,
                    progress: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        """
        Cada tentativa é um desafiante; só os que melhoram são promovidos. A 1ª tentativa é sempre o ajuste fino do
        campeão com os dados atuais (o caminho mais estável para evoluir); as outras sorteiam arquiteturas novas.
        """
        rng = np.random.default_rng(seed + len(self.meta["versions"]))
        champ = self.champion()
        out = []
        for i in range(trials):
            if i == 0 and champ is not None:
                hidden = list(champ.layer_sizes[1:-1])
                lr, l2 = 0.003, float(champ.l2)
            else:
                hidden = [int(rng.choice([16, 32, 48, 64]))] + ([int(rng.choice([8, 16, 32]))] if rng.random() < 0.7 else [])
                lr = float(rng.choice([0.001, 0.003, 0.01]))
                l2 = float(rng.choice([0.0, 1e-4, 1e-3, 1e-2]))
            r = self.train_round(data, hidden, lr, epochs, l2, 256, seed=int(rng.integers(0, 10**5)),
                                 origin="busca automática" + (" (ajuste fino)" if i == 0 and champ is not None else ""))
            out.append(r)
            if progress:
                progress(f"tentativa {i + 1}/{trials}: {hidden}, η={lr}, λ={l2} → {'PROMOVIDA' if r['promoted'] else 'rejeitada'}")
        return out


    def run_experiments(self, data: pd.DataFrame, names: Optional[List[str]] = None, attempts: int = 1,
                        progress: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        """
        Experimentos controlados A–D (ver EXPERIMENTS), na ordem pedida (B primeiro). `attempts` = quantas sementes
        por experimento neste clique. Cada tentativa passa pelo mesmo critério de promoção do `train_round`; o
        campeão (v002) só é trocado se houver superioridade estatística.
        """
        say = progress or (lambda m: None)
        names = [n for n in (names or EXPERIMENT_ORDER) if n in EXPERIMENTS]
        out = []
        base = int(time.time()) % 10_000
        for name in names:
            cfg = EXPERIMENTS[name]
            for k in range(max(1, int(attempts))):
                say(f"experimento {name} {cfg['hidden']} · tentativa {k + 1}/{attempts}…")
                r = self.train_round(data, cfg["hidden"], cfg["learning_rate"], EXP_EPOCHS, cfg["l2"], EXP_BATCH,
                                     seed=base + 97 * k + ord(name), origin=f"experimento {name}", cv_folds=3,
                                     cv_seeds=(11,), optimizer="adam", warm_start=False, patience=EXP_PATIENCE,
                                     cv_epochs=30, progress=progress)
                r["experimento"] = name
                out.append(r)
                say(f"  {name}: v{r['version']:03d} → {'PROMOVIDA' if r['promoted'] else 'rejeitada'} "
                    f"({r['epochs_run']} épocas, AUC {r['val_auc']:.4f})")
        return out


def feature_report(data: pd.DataFrame) -> pd.DataFrame:
    """
    Qualidade das 14 variáveis: faltantes, se é quase constante, AUC sozinha (0,5 = não separa nada; abaixo de 0,5
    separa ao contrário) e a variável mais correlacionada (|r| > 0,95 = redundante).
    """
    rows = []
    if data is None or data.empty:
        return pd.DataFrame()
    y = data["target"].to_numpy(int)
    # O relatório de qualidade mantém as 14 variáveis táticas originais.
    # density_is_360 é uma variável de proveniência/qualidade da medição, não uma
    # dimensão tática; ela continua no treinamento, mas não infla este quadro.
    report_features = LEGACY_FEATURES
    num = data[report_features].apply(pd.to_numeric, errors="coerce")
    corr = num.corr().abs()
    for f in report_features:
        x = num[f]
        miss = float(x.isna().mean())
        xv = x.fillna(x.median())
        uniq = int(xv.nunique())
        try:
            auc = float(roc_auc_score(y, xv)) if uniq > 1 and len(np.unique(y)) > 1 else None
        except Exception:
            auc = None
        c = corr[f].drop(f).sort_values(ascending=False)
        rows.append({"variavel": f, "faltantes_pct": round(100 * miss, 2), "valores_distintos": uniq,
                     "desvio": round(float(xv.std()), 4), "auc_sozinha": None if auc is None else round(auc, 4),
                     "mais_parecida": c.index[0] if len(c) else "", "correlacao": round(float(c.iloc[0]), 3) if len(c) else None,
                     "alerta": ("constante" if uniq <= 1 else "faltantes > 20%" if miss > 0.2 else
                                "redundante" if len(c) and c.iloc[0] > 0.95 else
                                "quase sem sinal" if auc is not None and abs(auc - 0.5) < 0.01 else "")})
    return pd.DataFrame(rows)


def class_balance(data: pd.DataFrame) -> Dict[str, Any]:
    """Proporção de ações que terminam em finalização (classe positiva). Ponderar classes piora a log-loss
    (calibração), que é o critério de promoção — por isso o balanceamento fica desligado por padrão."""
    if data is None or data.empty:
        return {}
    pos = float(data["target"].mean())
    return {"positivas_pct": round(100 * pos, 2), "acoes": int(len(data)), "partidas": int(data["match_id"].nunique()),
            "peso_que_equilibraria": round((1 - pos) / max(pos, 1e-9), 2)}


# ---------------------------------------------------------------- uso nas respostas
def score_actions(df_events: pd.DataFrame, net: Optional[NeuralNetwork] = None) -> pd.DataFrame:
    """
    Probabilidade (segundo o campeão) de cada passe/condução terminar em finalização da equipe naquela posse.
    Devolve as ações com jogador, equipe, minuto, coordenadas e `p_perigo`.
    """
    net = net if net is not None else DangerModelRegistry().champion()
    if net is None or df_events is None or df_events.empty:
        return pd.DataFrame()
    rows = build_match_rows(df_events)
    if rows.empty:
        return rows
    rows["p_perigo"] = net.predict_proba(DangerModelRegistry._model_matrix(net, rows))
    info = df_events[["event_id", "player_name", "x", "y"]].drop_duplicates("event_id")
    return rows.merge(info, on="event_id", how="left")


def model_card() -> Optional[Dict[str, Any]]:
    """Resumo do campeão para citar nas respostas (cria a v001 na primeira vez, como champion_cached)."""
    champion_cached()
    reg = DangerModelRegistry()
    c = reg.champion_info()
    if not c:
        return None
    return {"versao": f"v{c['version']:03d}", "auc_validacao": c["val_auc"], "partidas_de_treino": c["n_matches_train"],
            "acoes_de_treino": c.get("n_samples_train"), "tracking_360_pct": round(100 * c["density_360_share"], 1)
            if c.get("density_360_share") is not None else None, "partidas_com_proxy": c.get("density_proxy_matches", 0),
            "arquitetura": " → ".join(str(x) for x in [c.get("n_features") or len(LEGACY_FEATURES), *c["hidden"], 1]),
            "n_features": c.get("n_features") or len(LEGACY_FEATURES), "treinado_em": c["created"]}


def bootstrap_registry(progress: Optional[Callable[[str], None]] = None) -> DangerModelRegistry:
    """Garante uma versão inicial (v001) a partir da amostra de demonstração, para o Analista ter um modelo."""
    reg = DangerModelRegistry()
    if reg.champion_info() is None and DEMO.exists():
        reg.train_round(DangerModelRegistry.dataset(), [32, 16], 0.05, 20, 1e-3, 256, seed=42, origin="versão inicial (demo)")
        if progress:
            progress("versão inicial do modelo de perigo criada (v001)")
    return reg


def db_rows(db, max_new: int = 500, progress: Optional[Callable[[str], None]] = None) -> pd.DataFrame:
    """
    Linhas de treino de partidas com eventos. Inclui eventos já cacheados e jogos OpenPlay catalogados cujos
    lances ainda estão nos arquivos Parquet locais; a conversão é incremental e retomável.
    """
    cached = pd.read_csv(ROWS_CACHE) if ROWS_CACHE.exists() else pd.DataFrame()
    if not cached.empty and "density_is_360" not in cached:
        cached["density_is_360"] = cached["density_source"].eq("statsbomb_360").astype(float) if "density_source" in cached else 0.0
    have = set(cached["match_id"].unique()) if not cached.empty else set()
    demo = set(pd.read_csv(DEMO, usecols=["match_id"])["match_id"].unique()) if DEMO.exists() else set()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT m.match_id, m.data_source FROM matches m LEFT JOIN events e ON e.match_id = m.match_id "
            "WHERE m.data_level = 'EVENTS' GROUP BY m.match_id "
            "HAVING COUNT(e.match_id) > 0 OR m.data_source = 'openplay' ORDER BY m.match_date DESC"
        ).fetchall()
    source_by_id = {int(mid): str(src or "") for mid, src in rows}
    ids = list(source_by_id)
    todo = [m for m in ids if m not in have and m not in demo][:max(0, int(max_new))]
    parts = [cached] if not cached.empty else []
    try:
        from src.data_hub.sources.statsbomb import StatsBombProvider
        from src.machine_learning.danger_dataset import opponents_from_360

        sb = StatsBombProvider(db)
    except Exception:
        sb = None
    openplay = None
    if any(source_by_id.get(int(mid)) == "openplay" for mid in todo):
        try:
            from src.data_hub.sources.openplay import OpenPlayProvider

            openplay = OpenPlayProvider(db)
        except Exception:
            openplay = None
    for i, mid in enumerate(todo):
        try:
            fr = None
            if sb is not None and int(mid) < 10_000_000:      # StatsBomb 360, quando existe
                try:
                    fr = sb.load_360(int(mid))
                except Exception:
                    fr = None
            events = db.load_events(int(mid))
            if (events is None or events.empty) and source_by_id.get(int(mid)) == "openplay" and openplay is not None:
                events = openplay.load_events(int(mid))
            r = build_match_rows(events, opponents_from_360(fr) if fr is not None and not fr.empty else None)
            if not r.empty:
                parts.append(r)
        except Exception as exc:
            if source_by_id.get(int(mid)) == "openplay":
                try:
                    db.set_state("openplay", f"prefetch_failed_{int(mid)}", str(time.time()))
                except Exception:
                    pass
            if progress:
                progress(f"partida {mid} ignorada: {exc}")
        if progress:
            progress(f"preparando partidas novas do banco: {i + 1}/{len(todo)}")
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if todo and not out.empty:
        ROWS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(ROWS_CACHE, index=False, compression="gzip")
    return out


_CHAMP: Dict[str, Any] = {"mtime": None, "net": None}


def champion_cached() -> Optional[NeuralNetwork]:
    """Campeão carregado uma vez e recarregado só quando uma nova versão é promovida."""
    p = ROOT / "registry.json"
    m = p.stat().st_mtime if p.exists() else None
    if m is None and DEMO.exists():          # primeira execução: cria a v001 a partir da amostra de demonstração
        bootstrap_registry()
        m = p.stat().st_mtime if p.exists() else None
    if m != _CHAMP["mtime"]:
        _CHAMP.update(mtime=m, net=DangerModelRegistry().champion() if m else None)
    return _CHAMP["net"]


DANGER_THRESHOLD = 0.30


def danger_by_player(scored: pd.DataFrame, team: Optional[str] = None, top: int = 5) -> List[Dict[str, Any]]:
    s = scored if team is None else scored[scored["team_name"] == team]
    if s.empty:
        return []
    g = s.groupby(["player_name", "team_name"]).agg(acoes=("p_perigo", "size"),
                                                     perigosas=("p_perigo", lambda v: int((v >= DANGER_THRESHOLD).sum())),
                                                     maior=("p_perigo", "max"), media=("p_perigo", "mean")).reset_index()
    g = g[g["perigosas"] > 0].sort_values(["perigosas", "maior"], ascending=False).head(top)
    return [{"jogador": r.player_name, "equipe": r.team_name, "acoes_perigosas": int(r.perigosas), "acoes": int(r.acoes),
             "maior_chance_pct": round(100 * float(r.maior), 1)} for r in g.itertuples()]


def danger_zones(scored: pd.DataFrame, team: str, n: int = 2) -> List[Dict[str, Any]]:
    """Zonas (no referencial de quem ataca) de onde saíram as ações mais perigosas da equipe."""
    s = scored[(scored["team_name"] == team) & (scored["p_perigo"] >= DANGER_THRESHOLD)].dropna(subset=["x", "y"])
    if s.empty:
        return []
    third = np.where(s["x"] < 40, "terço defensivo", np.where(s["x"] < 80, "terço médio", "terço ofensivo"))
    lane = np.where(s["y"] < 30, "esquerda", np.where(s["y"] < 50, "centro", "direita"))
    z = pd.Series([f"{a} — {b}" for a, b in zip(third, lane)]).value_counts()
    return [{"zona": k, "acoes_perigosas": int(v), "de": int(len(s))} for k, v in z.head(n).items()]


def main() -> None:
    """
    Treino pelo terminal (mesmo critério de promoção da tela Bastidores):
        python -m src.machine_learning.model_registry --treinar               ajuste fino do campeão + 2 arquiteturas
        python -m src.machine_learning.model_registry --treinar --tentativas 5 --com-estimadas
        python -m src.machine_learning.model_registry --treinar --experimentos B          (v36: A/B/C/D controlados)
    """
    import argparse

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    ap = argparse.ArgumentParser(description="Treina desafiantes da rede neural de perigo e promove só os que melhoram.")
    ap.add_argument("--treinar", action="store_true")
    ap.add_argument("--tentativas", type=int, default=3)
    ap.add_argument("--epocas", type=int, default=30)
    ap.add_argument("--partidas-novas", type=int, default=500, help="partidas do banco preparadas nesta rodada (OpenPlay é convertido sob demanda)")
    ap.add_argument("--com-estimadas", action="store_true", help="compatibilidade: inclui também densidade estimada")
    ap.add_argument("--somente-360", action="store_true", help="restringe o treino às partidas com tracking 360 medido")
    ap.add_argument("--experimentos", default="", help="ex.: B ou B,A,C,D — experimentos controlados (v36)")
    ap.add_argument("--ocultas", default="", help="treino manual: neurônios por camada, ex.: 32,16")
    ap.add_argument("--eta", type=float, default=0.001)
    ap.add_argument("--l2", type=float, default=1e-4)
    ap.add_argument("--lote", type=int, default=256)
    ap.add_argument("--sem-banco", action="store_true", help="só a amostra local + protocolo (sem preparar partidas do banco)")
    ap.add_argument("--estado", default="", help="arquivo JSON de andamento (usado pela tela Bastidores)")
    args = ap.parse_args()
    if not args.treinar:
        ap.print_help()
        return
    state_path = Path(args.estado) if args.estado else None
    state = {"status": "rodando", "inicio": time.strftime("%Y-%m-%d %H:%M:%S"), "etapa": "preparando o conjunto",
             "log": [], "resultados": []}

    def say(m: str) -> None:
        print(m, flush=True)
        if state_path:
            state["log"] = (state["log"] + [str(m)])[-40:]
            state["etapa"] = str(m)[:160]
            state_path.write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")
    try:
        from src.data_hub.service import MatchDataService

        db = MatchDataService().db
        data = DangerModelRegistry.dataset(None if args.sem_banco else (lambda: db_rows(db, max_new=args.partidas_novas,
                                                                                         progress=say)),
                                           include_proxy=not args.somente_360 or args.com_estimadas)
        say(f"conjunto: {data['match_id'].nunique()} partidas, {len(data)} ações")
        champion_cached()                                   # garante a v001 antes de comparar
        reg = DangerModelRegistry()
        if args.experimentos:
            bal = class_balance(data)
            say(f"classes: {bal.get('positivas_pct')}% das ações terminam em finalização")
            names = [x.strip().upper() for x in args.experimentos.split(",") if x.strip()]
            rounds = reg.run_experiments(data, names, attempts=max(1, args.tentativas if args.tentativas != 3 else 1),
                                         progress=say)
        elif args.ocultas:
            hidden = [int(h) for h in args.ocultas.replace(";", ",").split(",") if h.strip()]
            rounds = [reg.train_round(data, hidden, args.eta, args.epocas, args.l2, args.lote,
                                      seed=int(time.time()) + k, progress=say) for k in range(max(1, args.tentativas))]
        else:
            rounds = reg.auto_search(data, trials=args.tentativas, epochs=args.epocas, progress=say)
        for r in rounds:
            say(f"  v{r['version']:03d} {'PROMOVIDA' if r['promoted'] else 'rejeitada'}: {r['reason']}")
            state["resultados"].append({k: r.get(k) for k in ("version", "promoted", "reason", "val_auc", "val_logloss",
                                                              "hidden", "experimento", "epochs_run", "seconds")})
        ci = reg.champion_info() or {}
        say(f"campeão atual: v{ci.get('version', 0):03d} (AUC {ci.get('val_auc')}, perda {ci.get('val_logloss')})")
        state["status"] = "concluido"
    except Exception as exc:
        state["status"] = "erro"
        say(f"erro: {type(exc).__name__}: {exc}")
        raise
    finally:
        state["fim"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if state_path:
            state_path.write_text(json.dumps(state, ensure_ascii=False, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
