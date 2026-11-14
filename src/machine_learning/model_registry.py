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

from src.machine_learning.danger_dataset import FEATURES, build_match_rows
from src.machine_learning.neural_net import NeuralNetwork

ROOT = Path("models/registry/danger")
DEMO = Path("data/demo/danger_sample_wc2022.csv.gz")
ROWS_CACHE = Path("data/processed/danger_rows_db.csv.gz")
FULL = Path("data/processed/danger_full.csv.gz")      # gerado por `python -m src.evaluation.protocol` (Copa 2022 + 360)
MIN_360_SHARE = 0.8                                    # partidas do banco só entram se tiverem densidade medida (360)
MIN_IMPROVEMENT = 0.0005        # redução mínima de log-loss para promover (evita "melhora" por ruído)
VAL_FRACTION = 0.25


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


class DangerModelRegistry:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)
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
    def dataset(load_db_rows: Optional[Callable[[], pd.DataFrame]] = None, include_proxy: bool = False) -> pd.DataFrame:
        """
        Todos os exemplos consistentes disponíveis, sem duplicar partidas:
        amostra de demonstração (16 mil ações) → dataset completo do protocolo, se existir (~117 mil, com 360) →
        partidas do banco com densidade medida pelo 360 (as que só têm a estimativa entram com include_proxy=True).
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
        return data.dropna(subset=FEATURES + ["target"]).reset_index(drop=True) if not data.empty else data

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
    def _evaluate(net: NeuralNetwork, val: pd.DataFrame) -> Dict[str, float]:
        p = np.clip(net.predict_proba(val[FEATURES].to_numpy(float)), 1e-6, 1 - 1e-6)
        y = val["target"].to_numpy(int)
        return {"auc": round(float(roc_auc_score(y, p)), 4), "logloss": round(float(log_loss(y, p)), 5)}

    def evaluate_champion(self, data: pd.DataFrame) -> Optional[Dict[str, float]]:
        net = self.champion()
        if net is None:
            return None
        _, val = self.split(data)
        return self._evaluate(net, val)

    def train_round(self, data: pd.DataFrame, hidden: List[int], learning_rate: float = 0.05, epochs: int = 30,
                    l2: float = 1e-3, batch_size: int = 256, seed: Optional[int] = None,
                    origin: str = "treino") -> Dict[str, Any]:
        """Treina um desafiante; promove se melhorar a log-loss na validação fixa. Devolve o relatório da rodada."""
        train, val = self.split(data)
        seed = int(seed if seed is not None else time.time()) % 100_000
        net = NeuralNetwork([len(FEATURES), *hidden, 1], learning_rate=learning_rate, l2=l2, seed=seed, feature_names=FEATURES)
        net.fit(train[FEATURES].to_numpy(float), train["target"].to_numpy(int), epochs=epochs, batch_size=batch_size,
                X_val=val[FEATURES].to_numpy(float), y_val=val["target"].to_numpy(int))
        m = self._evaluate(net, val)
        champ = self.champion_info()
        champ_now = self.evaluate_champion(data) if champ else None
        if champ_now is None:
            promoted, reason = True, "primeira versão: vira o modelo usado pelo Analista IA"
        elif m["logloss"] <= champ_now["logloss"] - MIN_IMPROVEMENT:
            promoted = True
            reason = (f"melhorou a perda na validação fixa: {champ_now['logloss']:.5f} → {m['logloss']:.5f} "
                      f"(AUC {champ_now['auc']:.3f} → {m['auc']:.3f})")
        else:
            promoted = False
            reason = (f"não melhorou (perda {m['logloss']:.5f} contra {champ_now['logloss']:.5f} do campeão "
                      f"v{champ['version']:03d}); o Analista continua com o campeão")
        v = len(self.meta["versions"]) + 1
        net.save(self.root / f"v{v:03d}.npz")
        rec = Version(v, time.strftime("%Y-%m-%d %H:%M"), list(hidden), learning_rate, epochs, l2, batch_size,
                      int(train["match_id"].nunique()), int(len(train)), m["auc"], m["logloss"], promoted, reason, origin,
                      {k: [round(float(x), 5) for x in vals] for k, vals in net.history.items()})
        self.meta["versions"].append(asdict(rec))
        if promoted:
            self.meta["champion"] = v
        self._write()
        return {**asdict(rec), "champion_before": champ_now, "net": net}

    def auto_search(self, data: pd.DataFrame, trials: int = 3, epochs: int = 25, seed: int = 0,
                    progress: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        """Busca aleatória de hiperparâmetros: cada tentativa é um desafiante; só os que melhoram são promovidos."""
        rng = np.random.default_rng(seed + len(self.meta["versions"]))
        out = []
        for i in range(trials):
            hidden = [int(rng.choice([16, 32, 48, 64]))] + ([int(rng.choice([8, 16, 32]))] if rng.random() < 0.7 else [])
            lr = float(rng.choice([0.02, 0.05, 0.1]))
            l2 = float(rng.choice([0.0, 1e-4, 1e-3, 1e-2]))
            r = self.train_round(data, hidden, lr, epochs, l2, 256, seed=int(rng.integers(0, 10**5)), origin="busca automática")
            out.append(r)
            if progress:
                progress(f"tentativa {i + 1}/{trials}: {hidden}, η={lr}, λ={l2} → {'PROMOVIDA' if r['promoted'] else 'rejeitada'}")
        return out


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
    rows["p_perigo"] = net.predict_proba(rows[FEATURES].to_numpy(float))
    info = df_events[["event_id", "player_name", "x", "y"]].drop_duplicates("event_id")
    return rows.merge(info, on="event_id", how="left")


def model_card() -> Optional[Dict[str, Any]]:
    """Resumo do campeão para citar nas respostas."""
    reg = DangerModelRegistry()
    c = reg.champion_info()
    if not c:
        return None
    return {"versao": f"v{c['version']:03d}", "auc_validacao": c["val_auc"], "partidas_de_treino": c["n_matches_train"],
            "arquitetura": " → ".join(str(x) for x in [len(FEATURES), *c["hidden"], 1]), "treinado_em": c["created"]}


def bootstrap_registry(progress: Optional[Callable[[str], None]] = None) -> DangerModelRegistry:
    """Garante uma versão inicial (v001) a partir da amostra de demonstração, para o Analista ter um modelo."""
    reg = DangerModelRegistry()
    if reg.champion_info() is None and DEMO.exists():
        reg.train_round(DangerModelRegistry.dataset(), [32, 16], 0.05, 20, 1e-3, 256, seed=42, origin="versão inicial (demo)")
        if progress:
            progress("versão inicial do modelo de perigo criada (v001)")
    return reg


def db_rows(db, max_new: int = 25, progress: Optional[Callable[[str], None]] = None) -> pd.DataFrame:
    """
    Linhas de treino das partidas com eventos já no banco (cache incremental em data/processed): a cada treino,
    as partidas novas que a sincronização trouxe entram no conjunto. Densidade de adversários pela proxy
    (o 360 só existe para parte do StatsBomb).
    """
    cached = pd.read_csv(ROWS_CACHE) if ROWS_CACHE.exists() else pd.DataFrame()
    have = set(cached["match_id"].unique()) if not cached.empty else set()
    demo = set(pd.read_csv(DEMO, usecols=["match_id"])["match_id"].unique()) if DEMO.exists() else set()
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT e.match_id FROM events e JOIN matches m ON m.match_id = e.match_id "
            "WHERE m.data_level = 'EVENTS'")]
    todo = [m for m in ids if m not in have and m not in demo][:max_new]
    parts = [cached] if not cached.empty else []
    try:
        from src.data_hub.sources.statsbomb import StatsBombProvider
        from src.machine_learning.danger_dataset import opponents_from_360

        sb = StatsBombProvider(db)
    except Exception:
        sb = None
    for i, mid in enumerate(todo):
        try:
            fr = None
            if sb is not None and int(mid) < 10_000_000:      # StatsBomb: tenta o 360 (cache local; baixa se faltar)
                try:
                    fr = sb.load_360(int(mid))
                except Exception:
                    fr = None
            r = build_match_rows(db.load_events(int(mid)), opponents_from_360(fr) if fr else None)
            if not r.empty:
                parts.append(r)
        except Exception as exc:
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
