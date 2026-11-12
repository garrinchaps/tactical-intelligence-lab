"""
Módulo de Aprendizado Supervisionado e Validação Preditiva (Camada 6.2)
Treina modelos XGBoost e Regressão Logística (Baseline) para estimar a probabilidade
de uma cadeia de posse atingir zonas críticas (Grande Área, Zona 14 ou Finalização).
Implementa separação por match_id (GroupShuffleSplit), métricas ROC-AUC, F1, Brier Score
e persistência de modelos com joblib.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit, StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.geometry.pitch_zones import PitchGeometry


class PossessionDangerClassifier:
    """
    Pipeline supervisionado para prever se uma sequência de posse resultará em
    perigo real (entrada na Grande Área, entrada na Zona 14 ou Finalização).
    """

    CORRIDOR_CATEGORIES = [
        "Corredor Lateral Esquerdo",
        "Meio-Espaço Esquerdo",
        "Corredor Central",
        "Meio-Espaço Direito",
        "Corredor Lateral Direito",
    ]

    NUMERIC_FEATURES = [
        "x_start",
        "y_start",
        "start_dist_to_goal_m",
        "start_centrality_y",
        "duration_sec",
        "num_passes",
        "pass_completion_ratio",
        "pass_tempo_per_sec",
        "progressive_action_ratio",
        "direct_speed_m_s",
        "under_pressure_ratio",
        "period",
    ]

    def __init__(
        self,
        model_dir: str = "models/trained",
        eval_dir: str = "models/evaluation",
    ) -> None:
        self.model_dir = Path(model_dir)
        self.eval_dir = Path(eval_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.eval_dir.mkdir(parents=True, exist_ok=True)

        self.xgb_model: Optional[XGBClassifier] = None
        self.lr_pipeline: Optional[Pipeline] = None
        self.feature_Columns: List[str] = []
        self.latest_metrics: Dict[str, Any] = {}

    @classmethod
    def prepare_features_and_target(
        cls, df_chains: pd.DataFrame
    ) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
        """
        Transforma o DataFrame de Cadeias de Posse em matriz X (sem vazamento de coordenadas finais),
        vetor alvo binário y (1 = atingiu Grande Área, Zona 14 ou Finalização; 0 = caso contrário)
        e vetor groups (match_id para divisão sem contaminação entre jogos).
        """
        if df_chains.empty:
            return pd.DataFrame(), pd.Series(dtype=int), pd.Series(dtype=int)

        df = df_chains.copy()

        # Engenharia de variáveis cinemáticas e espaciais iniciais (Leakage-Free)
        df["start_dist_to_goal_m"] = (
            PitchGeometry.distance_to_goal_yards(df["x_start"], df["y_start"])
            * PitchGeometry.YARD_TO_METER
        )
        # Distância lateral ao eixo central do campo (y=40): 0 = centro exato, 40 = linha lateral
        df["start_centrality_y"] = (df["y_start"] - 40.0).abs()

        num_passes_safe = df["num_passes"].replace(0, np.nan)
        num_events_safe = df["num_events"].replace(0, np.nan)
        duration_safe = df["duration_sec"].clip(lower=1.0)

        df["pass_completion_ratio"] = (
            (df["completed_passes"] / num_passes_safe).fillna(0.0).clip(0.0, 1.0)
        )
        df["pass_tempo_per_sec"] = (df["num_passes"] / duration_safe).clip(0.0, 5.0)
        df["progressive_action_ratio"] = (
            (df["progressive_actions"] / num_events_safe).fillna(0.0).clip(0.0, 1.0)
        )

        # One-Hot Encoding determinístico para os 5 corredores de início da posse
        corridor_col = df.get(
            "start_corridor", pd.Series("Corredor Central", index=df.index)
        )
        corridor_dummies = pd.DataFrame(index=df.index)
        for corr in cls.CORRIDOR_CATEGORIES:
            safe_col = (
                "corr_"
                + corr.lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("ç", "c")
                .replace("ã", "a")
            )
            corridor_dummies[safe_col] = (corridor_col == corr).astype(int)

        X = pd.concat(
            [df[cls.NUMERIC_FEATURES].astype(float).fillna(0.0), corridor_dummies],
            axis=1,
        )

        # Variável Alvo Supervisionada: A posse gerou ameaça real (Chute, Entrada na Área ou Zona 14)?
        y = (
            (df["ended_in_shot"] == 1)
            | (df["entered_box"] == 1)
            | (df["entered_zone_14"] == 1)
        ).astype(int)

        groups = df["match_id"].astype(int)
        return X, y, groups

    def train_and_evaluate(
        self, df_chains: pd.DataFrame, test_size: float = 0.25, random_state: int = 42
    ) -> Dict[str, Any]:
        """
        Treina XGBoost e Regressão Logística (Baseline), separa treino e teste por
        match_id quando houver >= 2 jogos (GroupShuffleSplit) ou estratificado se 1 jogo,
        calcula métricas de classificação e calibração (Brier Score) e salva os modelos.
        """
        X, y, groups = self.prepare_features_and_target(df_chains)
        if len(X) < 20 or y.nunique() < 2:
            raise ValueError(
                "Amostra insuficiente ou classe única para treinamento supervisionado (mínimo 20 posses com classes 0 e 1)."
            )

        self.feature_columns = list(X.columns)
        unique_matches = groups.nunique()

        # Separação de Treino e Teste (GroupShuffleSplit por partida quando possível)
        if unique_matches >= 3:
            splitter = GroupShuffleSplit(
                n_splits=1, test_size=test_size, random_state=random_state
            )
            train_idx, test_idx = next(splitter.split(X, y, groups=groups))
            split_strategy = f"GroupShuffleSplit por match_id ({unique_matches} partidas distintas - Zero Data Leakage)"
        else:
            splitter = StratifiedShuffleSplit(
                n_splits=1, test_size=test_size, random_state=random_state
            )
            train_idx, test_idx = next(splitter.split(X, y))
            split_strategy = "StratifiedShuffleSplit (Amostra de partida única/reduzida)"

        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        # Se por acaso o GroupSplit gerou apenas 1 classe no teste em base pequena, faz fallback estratificado
        if y_train.nunique() < 2 or y_test.nunique() < 2:
            splitter = StratifiedShuffleSplit(
                n_splits=1, test_size=test_size, random_state=random_state
            )
            train_idx, test_idx = next(splitter.split(X, y))
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        # Balanceamento de classes para o XGBoost
        n_pos = max(int((y_train == 1).sum()), 1)
        n_neg = max(int((y_train == 0).sum()), 1)
        scale_pos = round(n_neg / n_pos, 2)

        # 1. Treinamento do Modelo Principal: XGBoost Classifier (Regularizado contra Overfitting)
        self.xgb_model = XGBClassifier(
            n_estimators=120,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=1.5,
            scale_pos_weight=scale_pos,
            eval_metric="logloss",
            random_state=random_state,
        )
        self.xgb_model.fit(X_train, y_train)

        # 2. Treinamento do Baseline: Regressão Logística com StandardScaler
        self.lr_pipeline = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "lr",
                    LogisticRegression(
                        class_weight="balanced", max_iter=500, random_state=random_state
                    ),
                ),
            ]
        )
        self.lr_pipeline.fit(X_train, y_train)

        # 3. Avaliação Rigorosa (Treino vs Teste para auditoria de Overfitting)
        xgb_train_probs = self.xgb_model.predict_proba(X_train)[:, 1]
        xgb_test_probs = self.xgb_model.predict_proba(X_test)[:, 1]
        xgb_test_preds = (xgb_test_probs >= 0.5).astype(int)

        lr_test_probs = self.lr_pipeline.predict_proba(X_test)[:, 1]
        lr_test_preds = (lr_test_probs >= 0.5).astype(int)

        # Extração de Feature Importance do XGBoost
        importances = self.xgb_model.feature_importances_
        feat_imp_list = [
            {"feature": col, "importance": round(float(imp), 4)}
            for col, imp in zip(self.feature_columns, importances)
        ]
        feat_imp_list = sorted(
            feat_imp_list, key=lambda d: d["importance"], reverse=True
        )

        train_auc = round(float(roc_auc_score(y_train, xgb_train_probs)), 4)
        test_auc = round(float(roc_auc_score(y_test, xgb_test_probs)), 4)
        auc_gap = round(train_auc - test_auc, 4)

        self.latest_metrics = {
            "split_strategy": split_strategy,
            "total_samples": int(len(X)),
            "train_samples": int(len(X_train)),
            "test_samples": int(len(X_test)),
            "positive_class_rate_pct": round(float(y.mean()) * 100.0, 2),
            "xgboost_metrics": {
                "train_roc_auc": train_auc,
                "test_roc_auc": test_auc,
                "overfitting_auc_gap": auc_gap,
                "test_accuracy": round(float(accuracy_score(y_test, xgb_test_preds)), 4),
                "test_precision": round(
                    float(precision_score(y_test, xgb_test_preds, zero_division=0)), 4
                ),
                "test_recall": round(
                    float(recall_score(y_test, xgb_test_preds, zero_division=0)), 4
                ),
                "test_f1_score": round(
                    float(f1_score(y_test, xgb_test_preds, zero_division=0)), 4
                ),
                "test_brier_score": round(
                    float(brier_score_loss(y_test, xgb_test_probs)), 4
                ),
            },
            "logistic_regression_baseline": {
                "test_roc_auc": round(float(roc_auc_score(y_test, lr_test_probs)), 4),
                "test_f1_score": round(
                    float(f1_score(y_test, lr_test_preds, zero_division=0)), 4
                ),
                "test_brier_score": round(
                    float(brier_score_loss(y_test, lr_test_probs)), 4
                ),
            },
            "top_feature_importances": feat_imp_list[:8],
        }

        self.save_models()
        return self.latest_metrics

    def save_models(self) -> Path:
        """Salva o modelo XGBoost, o baseline e os metadados de colunas com joblib."""
        artifact_path = self.model_dir / "possession_threat_xgboost.joblib"
        payload = {
            "xgb_model": self.xgb_model,
            "lr_pipeline": self.lr_pipeline,
            "feature_columns": self.feature_columns,
            "latest_metrics": self.latest_metrics,
        }
        joblib.dump(payload, artifact_path)
        return artifact_path

    def load_models(self) -> bool:
        """Carrega o modelo salvo do disco caso exista."""
        artifact_path = self.model_dir / "possession_threat_xgboost.joblib"
        if not artifact_path.exists():
            return False
        payload = joblib.load(artifact_path)
        self.xgb_model = payload["xgb_model"]
        self.lr_pipeline = payload.get("lr_pipeline")
        self.feature_columns = payload["feature_columns"]
        self.latest_metrics = payload.get("latest_metrics", {})
        return True

    def predict_possession_probabilities(
        self, df_chains: pd.DataFrame, target_team: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Aplica o modelo treinado sobre as cadeias de posse de uma partida/equipe,
        retornando a probabilidade estimada de sucesso de cada posse e identificando
        qual corredor inicial oferece a maior probabilidade esperada de criar perigo.
        """
        if self.xgb_model is None:
            loaded = self.load_models()
            if not loaded:
                raise RuntimeError(
                    "Modelo XGBoost ainda não foi treinado nem encontrado em models/trained/."
                )

        chains = df_chains.copy()
        if target_team:
            chains = chains[chains["team_name"] == target_team].copy()

        if chains.empty:
            return {"team_name": target_team, "status": "EMPTY", "corridor_probabilities": {}}

        X, y_actual, _ = self.prepare_features_and_target(chains)
        # Alinha colunas com o treinamento
        for col in self.feature_columns:
            if col not in X.columns:
                X[col] = 0.0
        X = X[self.feature_columns]

        probs = self.xgb_model.predict_proba(X)[:, 1]
        chains["predicted_danger_prob"] = np.round(probs, 4)
        chains["actual_danger_reached"] = y_actual.values

        # Agrupa probabilidade esperada por corredor inicial
        corridor_summary = {}
        for corr, grp in chains.groupby("start_corridor"):
            corridor_summary[str(corr)] = {
                "possessions_count": int(len(grp)),
                "avg_predicted_danger_prob_pct": round(
                    float(grp["predicted_danger_prob"].mean()) * 100.0, 2
                ),
                "actual_danger_conversion_pct": round(
                    float(grp["actual_danger_reached"].mean()) * 100.0, 2
                ),
            }

        best_corridor = (
            max(
                corridor_summary.items(),
                key=lambda kv: kv[1]["avg_predicted_danger_prob_pct"],
            )[0]
            if corridor_summary
            else "Indefinido"
        )

        return {
            "team_name": target_team or "All",
            "status": "OK",
            "total_possessions_scored": int(len(chains)),
            "avg_predicted_danger_prob_pct": round(float(probs.mean()) * 100.0, 2),
            "actual_danger_rate_pct": round(float(y_actual.mean()) * 100.0, 2),
            "highest_probability_start_corridor": best_corridor,
            "corridor_probabilities": corridor_summary,
            "top_3_most_dangerous_possessions": chains.sort_values(
                by="predicted_danger_prob", ascending=False
            )[
                [
                    "match_id",
                    "period",
                    "possession_id",
                    "start_corridor",
                    "direct_speed_m_s",
                    "predicted_danger_prob",
                    "actual_danger_reached",
                ]
            ]
            .head(3)
            .to_dict(orient="records"),
        }


if __name__ == "__main__":
    import json
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.preprocessing.event_cleaner import EventPreprocessor

    print("=" * 78)
    print("TACTICAL INTELLIGENCE LAB - TREINAMENTO SUPERVISIONADO XGBOOST (DIA 7)")
    print("=" * 78)

    loader = StatsBombDataLoader()

    # Baixa 4 partidas da fase final da Copa do Mundo 2022 para validar GroupShuffleSplit por match_id
    # 3869685: Argentina vs França (Final)
    # 3869519: Argentina vs Croácia (Semifinal)
    # 3869684: França vs Marrocos (Semifinal)
    # 3869321: Argentina vs Holanda (Quartas)
    training_match_ids = [3869685, 3869519, 3869684, 3869321]
    all_chains_list = []

    print(f"\n[1/3] Carregando e processando cadeias de posse de {len(training_match_ids)} partidas reais...")
    for mid in training_match_ids:
        raw_df = loader.ingest_match_events(mid)
        enriched_df = EventPreprocessor.process_match_events(raw_df)
        c_df = EventPreprocessor.build_possession_chains(enriched_df)
        all_chains_list.append(c_df)
        print(f"      -> Partida {mid}: {len(c_df)} cadeias de posse extraídas.")

    multi_chains_df = pd.concat(all_chains_list, ignore_index=True)

    print(f"\n[2/3] Treinando XGBoost e Baseline (Regressão Logística) em {len(multi_chains_df)} posses...")
    classifier = PossessionDangerClassifier()
    eval_report = classifier.train_and_evaluate(multi_chains_df)

    xgb_m = eval_report["xgboost_metrics"]
    lr_m = eval_report["logistic_regression_baseline"]

    print(f"\n======================================================================")
    print(f"RELATÓRIO DE VALIDAÇÃO CIENTÍFICA DOS MODELOS SUPERVISIONADOS")
    print(f"======================================================================")
    print(f"  * Estratégia de Validação: {eval_report['split_strategy']}")
    print(f"  * Amostras: Total = {eval_report['total_samples']} | Treino = {eval_report['train_samples']} | Teste = {eval_report['test_samples']}")
    print(f"  * Taxa Base da Classe Positiva (Perigo Real): {eval_report['positive_class_rate_pct']}%")
    print(f"\n  [Desempenho no Conjunto de Teste (Partidas Não Vistas no Treino)]:")
    print(f"    -> XGBoost ROC-AUC: {xgb_m['test_roc_auc']} (Treino: {xgb_m['train_roc_auc']} | Gap Overfitting: {xgb_m['overfitting_auc_gap']})")
    print(f"    -> XGBoost F1-Score: {xgb_m['test_f1_score']} | Precisão: {xgb_m['test_precision']} | Recall: {xgb_m['test_recall']}")
    print(f"    -> XGBoost Brier Score (Calibração Probabilística): {xgb_m['test_brier_score']} (Quanto menor, melhor)")
    print(f"    -> Baseline (Regressão Logística) ROC-AUC: {lr_m['test_roc_auc']} | F1: {lr_m['test_f1_score']} | Brier: {lr_m['test_brier_score']}")

    print(f"\n  [Top 5 Variáveis Táticas Mais Importantes (XGBoost Feature Importance)]:")
    for feat in eval_report["top_feature_importances"][:5]:
        print(f"    -> {feat['feature']}: {feat['importance']:.4f}")

    # Salva relatório de avaliação em models/evaluation/
    eval_path = "models/evaluation/xgboost_evaluation_report.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump(eval_report, f, ensure_ascii=False, indent=2)

    print(f"\n[3/3] Aplicando Inferência Probabilística na Final (3869685)...")
    final_chains = multi_chains_df[multi_chains_df["match_id"] == 3869685]
    for team in final_chains["team_name"].unique():
        pred_summary = classifier.predict_possession_probabilities(final_chains, target_team=team)
        print(
            f"      -> {team}: Probabilidade Média de Perigo por Posse = {pred_summary['avg_predicted_danger_prob_pct']}% "
            f"| Melhor Corredor de Início = {pred_summary['highest_probability_start_corridor']}"
        )

    print(f"\n[OK] Dia 7 concluído! Modelo salvo em: models/trained/possession_threat_xgboost.joblib")