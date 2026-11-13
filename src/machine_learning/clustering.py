"""
Módulo de Aprendizado Não Supervisionado - Clusterização Espacial (Camada 6.1)
Implementa K-Means (com otimização automática via Silhouette Score) e DBSCAN
para identificar regiões críticas de perda de posse (ponderadas por exposição)
e núcleos densos de recuperação defensiva.
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import silhouette_score
from src.geometry.pitch_zones import PitchGeometry


class SpatialTacticalClustering:
    """
    Motor de Aprendizado Não Supervisionado para diagnóstico espacial.
    Regra fundamental: nunca confundir volume bruto de perdas com vulnerabilidade
    real sem calcular o denominador de exposição (total de ações na região).
    """

    @classmethod
    def analyze_turnover_clusters(
        cls,
        df_events: pd.DataFrame,
        target_team: str,
        k_candidates: Tuple[int, ...] = (2, 3, 4, 5),
        random_state: int = 42,
    ) -> Dict[str, Any]:
        """
        Agrupa espacialmente todas as perdas de posse (is_turnover == 1) da equipe
        usando K-Means, escolhe o melhor K pelo Silhouette Score e pondera cada
        cluster pela exposição territorial (toques totais na mesma zona).
        """
        team_ev = df_events[
            (df_events["team_name"] == target_team)
            & (df_events["x"].notna())
            & (df_events["y"].notna())
        ].copy()

        turnovers = team_ev[team_ev["is_turnover"] == 1].copy()
        n_turnovers = int(len(turnovers))
        n_total_touches = max(int(len(team_ev)), 1)

        if n_turnovers < 6:
            return {
                "team_name": target_team,
                "status": "INSUFFICIENT_SAMPLE",
                "total_turnovers": n_turnovers,
                "optimal_k": 0,
                "silhouette_score": 0.0,
                "clusters": [],
                "highest_volume_cluster": None,
                "highest_risk_exposure_cluster": None,
            }

        coords = turnovers[["x", "y"]].to_numpy(dtype=float)

        # 1. Seleção automática de K via Silhouette Score
        best_k = 2
        best_score = -1.0
        best_model: Optional[KMeans] = None

        for k in k_candidates:
            if n_turnovers <= k + 1:
                continue
            km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
            labels = km.fit_predict(coords)
            if len(set(labels)) > 1:
                score = float(silhouette_score(coords, labels))
                if score > best_score:
                    best_score = score
                    best_k = k
                    best_model = km

        if best_model is None:
            best_model = KMeans(n_clusters=2, n_init=10, random_state=random_state)
            best_model.fit(coords)
            best_score = 0.0

        turnovers["cluster_id"] = best_model.labels_
        centers = best_model.cluster_centers_

        # 2. Análise de cada cluster com denominador de exposição
        clusters_summary: List[Dict[str, Any]] = []
        for cid in range(best_k):
            c_rows = turnovers[turnovers["cluster_id"] == cid]
            c_count = int(len(c_rows))
            if c_count == 0:
                continue

            cx = round(float(centers[cid][0]), 2)
            cy = round(float(centers[cid][1]), 2)

            third_label = str(
                PitchGeometry.get_pitch_third_series(pd.Series([cx])).iloc[0]
            )
            corridor_label = str(
                PitchGeometry.get_vertical_corridor_series(pd.Series([cy])).iloc[0]
            )
            zone_18 = int(
                PitchGeometry.get_zone_18_series(pd.Series([cx]), pd.Series([cy])).iloc[0]
            )

            # Calcula a exposição real: total de ações da equipe dentro de um raio de 18 jardas do centroide
            dists_all = np.sqrt(
                (team_ev["x"] - cx) ** 2 + (team_ev["y"] - cy) ** 2
            )
            local_touches = int((dists_all <= 18.0).sum())
            local_turnovers = int(
                (
                    np.sqrt((turnovers["x"] - cx) ** 2 + (turnovers["y"] - cy) ** 2)
                    <= 18.0
                ).sum()
            )

            exposure_turnover_rate_pct = (
                round((local_turnovers / max(local_touches, 1)) * 100.0, 2)
                if local_touches >= 5
                else 0.0
            )
            under_pressure_pct = round(
                float(c_rows["under_pressure"].mean()) * 100.0, 2
            )

            clusters_summary.append(
                {
                    "cluster_id": int(cid),
                    "centroid_x": cx,
                    "centroid_y": cy,
                    "tactical_third": third_label,
                    "tactical_corridor": corridor_label,
                    "zone_18": zone_18,
                    "turnovers_in_cluster": c_count,
                    "share_of_total_turnovers_pct": round(
                        (c_count / n_turnovers) * 100.0, 2
                    ),
                    "local_radius_touches_denominator": local_touches,
                    "local_radius_turnovers_numerator": local_turnovers,
                    "turnover_rate_per_touch_pct": exposure_turnover_rate_pct,
                    "under_pressure_rate_pct": under_pressure_pct,
                }
            )

        # Ordena por volume bruto para identificar onde mais ocorrem perdas
        clusters_by_vol = sorted(
            clusters_summary, key=lambda c: c["turnovers_in_cluster"], reverse=True
        )
        # Ordena por taxa de erro ajustada por exposição (com mínimo de 10 toques na região)
        valid_exposure = [
            c for c in clusters_summary if c["local_radius_touches_denominator"] >= 10
        ]
        clusters_by_risk = sorted(
            valid_exposure if valid_exposure else clusters_summary,
            key=lambda c: c["turnover_rate_per_touch_pct"],
            reverse=True,
        )

        return {
            "team_name": target_team,
            "status": "OK",
            "total_turnovers": n_turnovers,
            "total_team_touches": n_total_touches,
            "overall_turnover_rate_pct": round(
                (n_turnovers / n_total_touches) * 100.0, 2
            ),
            "optimal_k": int(best_k),
            "silhouette_score": round(best_score, 4),
            "clusters": clusters_by_vol,
            "highest_volume_cluster": clusters_by_vol[0] if clusters_by_vol else None,
            "highest_risk_exposure_cluster": (
                clusters_by_risk[0] if clusters_by_risk else None
            ),
        }

    @classmethod
    def analyze_recovery_density_dbscan(
        cls,
        df_events: pd.DataFrame,
        target_team: str,
        eps_yards: float = 14.0,
        min_samples: int = 5,
    ) -> Dict[str, Any]:
        """
        Utiliza DBSCAN para identificar núcleos espaciais densos de recuperação de bola
        e desarmes (Zonas de Armadilha de Pressão / Pressing Traps), separando-os de
        recuperações aleatórias isoladas (ruído).
        """
        team_ev = df_events[
            (df_events["team_name"] == target_team)
            & (df_events["is_ball_recovery"] == 1)
            & (df_events["x"].notna())
            & (df_events["y"].notna())
        ].copy()

        n_rec = int(len(team_ev))
        if n_rec < min_samples:
            return {
                "team_name": target_team,
                "total_recoveries": n_rec,
                "dense_zones_found": 0,
                "noise_isolated_recoveries": n_rec,
                "pressing_traps": [],
            }

        coords = team_ev[["x", "y"]].to_numpy(dtype=float)
        db = DBSCAN(eps=eps_yards, min_samples=min_samples)
        labels = db.fit_predict(coords)
        team_ev["dbscan_label"] = labels

        unique_clusters = [lbl for lbl in set(labels) if lbl != -1]
        noise_count = int((labels == -1).sum())

        traps: List[Dict[str, Any]] = []
        for lbl in unique_clusters:
            grp = team_ev[team_ev["dbscan_label"] == lbl]
            cx = round(float(grp["x"].mean()), 2)
            cy = round(float(grp["y"].mean()), 2)
            third_label = str(
                PitchGeometry.get_pitch_third_series(pd.Series([cx])).iloc[0]
            )
            corridor_label = str(
                PitchGeometry.get_vertical_corridor_series(pd.Series([cy])).iloc[0]
            )
            traps.append(
                {
                    "trap_id": int(lbl),
                    "centroid_x": cx,
                    "centroid_y": cy,
                    "tactical_third": third_label,
                    "tactical_corridor": corridor_label,
                    "recoveries_count": int(len(grp)),
                    "share_of_recoveries_pct": round((len(grp) / n_rec) * 100.0, 2),
                }
            )

        traps = sorted(traps, key=lambda t: t["recoveries_count"], reverse=True)

        return {
            "team_name": target_team,
            "total_recoveries": n_rec,
            "dense_zones_found": len(traps),
            "noise_isolated_recoveries": noise_count,
            "pressing_traps": traps,
        }


if __name__ == "__main__":
    import json
    from typing import Tuple
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.preprocessing.event_cleaner import EventPreprocessor

    print("=" * 78)
    print("TACTICAL INTELLIGENCE LAB - CLUSTERIZAÇÃO ESPACIAL K-MEANS & DBSCAN (DIA 6)")
    print("=" * 78)

    loader = StatsBombDataLoader()
    match_id = 3869685  # Final Copa 2022: Argentina vs França

    raw_df = loader.ingest_match_events(match_id)
    enriched_df = EventPreprocessor.process_match_events(raw_df)

    for team in enriched_df["team_name"].unique():
        km_res = SpatialTacticalClustering.analyze_turnover_clusters(enriched_df, team)
        db_res = SpatialTacticalClustering.analyze_recovery_density_dbscan(
            enriched_df, team
        )

        print(f"\n======================================================================")
        print(f"APRENDIZADO NÃO SUPERVISIONADO (K-MEANS + DBSCAN): {team.upper()}")
        print(f"======================================================================")
        print(
            f"  * Total de Perdas de Posse (Turnovers): {km_res['total_turnovers']} "
            f"(Taxa global: {km_res['overall_turnover_rate_pct']}% dos toques)"
        )
        print(
            f"  * K Ótimo Selecionado Automaticamente: K = {km_res['optimal_k']} "
            f"| Silhouette Score = {km_res['silhouette_score']}"
        )

        vol_c = km_res["highest_volume_cluster"]
        risk_c = km_res["highest_risk_exposure_cluster"]

        if vol_c:
            print(
                f"\n  [1. Cluster de Maior Volume Bruto de Perdas]:\n"
                f"    -> Região: {vol_c['tactical_third']} - {vol_c['tactical_corridor']} (Zona {vol_c['zone_18']})\n"
                f"    -> Centroide: ({vol_c['centroid_x']}, {vol_c['centroid_y']}) | "
                f"{vol_c['turnovers_in_cluster']} perdas ({vol_c['share_of_total_turnovers_pct']}% do total)"
            )
        if risk_c:
            print(
                f"\n  [2. Cluster de Maior Vulnerabilidade Relativa (Ajustado por Exposição)]:\n"
                f"    -> Região: {risk_c['tactical_third']} - {risk_c['tactical_corridor']} (Zona {risk_c['zone_18']})\n"
                f"    -> Taxa de Perda por Toque na Zona: {risk_c['turnover_rate_per_touch_pct']}% "
                f"({risk_c['local_radius_turnovers_numerator']} perdas em {risk_c['local_radius_touches_denominator']} ações locais)\n"
                f"    -> Ações sob pressão adversária neste cluster: {risk_c['under_pressure_rate_pct']}%"
            )

        print(
            f"\n  [3. DBSCAN - Núcleos Densos de Recuperação Defensiva (Pressing Traps)]:\n"
            f"    -> Recuperações Totais: {db_res['total_recoveries']} | "
            f"Zonas Densas Detectadas: {db_res['dense_zones_found']} | "
            f"Recuperações Isoladas (Ruído): {db_res['noise_isolated_recoveries']}"
        )
        for trap in db_res["pressing_traps"][:2]:
            print(
                f"    -> Trap #{trap['trap_id']}: {trap['tactical_third']} ({trap['tactical_corridor']}) "
                f"em ({trap['centroid_x']}, {trap['centroid_y']}) com {trap['recoveries_count']} recuperações"
            )

        safe_name = team.lower().replace(" ", "_")
        with open(
            f"data/processed/clustering_{match_id}_{safe_name}.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                {"kmeans_turnovers": km_res, "dbscan_recoveries": db_res},
                f,
                ensure_ascii=False,
                indent=2,
            )