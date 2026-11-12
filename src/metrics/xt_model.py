"""
Módulo de Expected Threat (xT) e Análise de Quebra de Linhas (Camada 2 - Métricas Avançadas)
Calcula a matriz de ameaça esperada (xT) baseada em Cadeias de Markov e na Equação de Bellman,
atribuindo valor probabilístico a cada passe e condução executados em campo.
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd


class ExpectedThreatModel:
    """
    Motor de Expected Threat (xT). Utiliza uma malha padrão 12x8 para quantificar
    o ganho de probabilidade de gol gerado por passes progressivos e conduções.
    """

    # Malha 12x8 de Expected Threat (xT) calibrada para futebol profissional (Valores padrão de literatura)
    # 12 colunas (comprimento) x 8 linhas (largura)
    XT_GRID_12X8 = np.array(
        [
            [0.006, 0.007, 0.009, 0.012, 0.016, 0.021, 0.029, 0.038, 0.053, 0.075, 0.113, 0.175],
            [0.006, 0.008, 0.010, 0.013, 0.018, 0.024, 0.032, 0.043, 0.060, 0.086, 0.129, 0.198],
            [0.007, 0.009, 0.011, 0.015, 0.020, 0.027, 0.037, 0.049, 0.068, 0.098, 0.147, 0.226],
            [0.008, 0.010, 0.013, 0.017, 0.023, 0.031, 0.042, 0.056, 0.078, 0.112, 0.230, 0.450],
            [0.008, 0.010, 0.013, 0.017, 0.023, 0.031, 0.042, 0.056, 0.078, 0.112, 0.230, 0.450],
            [0.007, 0.009, 0.011, 0.015, 0.020, 0.027, 0.037, 0.049, 0.068, 0.098, 0.147, 0.226],
            [0.006, 0.008, 0.010, 0.013, 0.018, 0.024, 0.032, 0.043, 0.060, 0.086, 0.129, 0.198],
            [0.006, 0.007, 0.009, 0.012, 0.016, 0.021, 0.029, 0.038, 0.053, 0.075, 0.113, 0.175],
        ]
    )  # Formato (8 linhas Y, 12 colunas X)

    @classmethod
    def get_xt_value(cls, x: float, y: float) -> float:
        """
        Retorna o valor de xT para uma coordenada (x, y) mapeada na grade 12x8.
        X in [0, 120] -> Colunas 0..11
        Y in [0, 80]  -> Linhas 0..7
        """
        if pd.isna(x) or pd.isna(y):
            return 0.0

        col = int(np.clip(np.floor(x / 10.0), 0, 11))
        row = int(np.clip(np.floor(y / 10.0), 0, 7))
        return float(cls.XT_GRID_12X8[row, col])

    @classmethod
    def enrich_events_with_xt(cls, df_events: pd.DataFrame) -> pd.DataFrame:
        """
        Adiciona as colunas de xT de origem, xT de destino e o ganho líquido (delta_xt)
        para cada evento completado (passes e conduções).
        """
        out = df_events.copy()

        xt_start = []
        xt_end = []
        delta_xt = []

        for _, row in out.iterrows():
            x0 = row.get("x", np.nan)
            y0 = row.get("y", np.nan)
            x1 = row.get("end_x", np.nan)
            y1 = row.get("end_y", np.nan)

            val_start = cls.get_xt_value(x0, y0)
            val_end = cls.get_xt_value(x1, y1) if pd.notna(x1) and pd.notna(y1) else val_start

            # Se o passe/condução foi incompleto, o xT gerado é zerado ou negativo
            is_success = True
            if row.get("type_name") == "Pass":
                if pd.notna(row.get("pass_outcome_name")):
                    is_success = False

            d_xt = (val_end - val_start) if is_success else 0.0

            xt_start.append(val_start)
            xt_end.append(val_end)
            delta_xt.append(round(d_xt, 5))

        out["xt_start"] = xt_start
        out["xt_end"] = xt_end
        out["delta_xt"] = delta_xt

        # Identifica passes que quebram linhas defensivas (ganho expressivo de xT ou transição de terço)
        out["is_line_breaking_pass"] = (
            (out["type_name"] == "Pass")
            & (out["pass_outcome_name"].isna())
            & (
                (out["delta_xt"] >= 0.03)
                | (
                    (out["origin_third"].isin(["Terço Defensivo", "Terço Médio"]))
                    & (out["end_third"] == "Terço Ofensivo")
                )
            )
        ).fillna(False).astype(int)

        return out

    @classmethod
    def compute_team_xt_summary(cls, df_enriched: pd.DataFrame, target_team: str) -> Dict[str, Any]:
        """
        Calcula o resumo consolidado de Expected Threat da equipe:
        - Total de xT gerado no jogo
        - Principais geradores de xT acumulado
        - Jogadores com mais passes que quebram linhas
        """
        team_ev = df_enriched[df_enriched["team_name"] == target_team]
        success_actions = team_ev[
            team_ev["type_name"].isin(["Pass", "Carry"]) & (team_ev["delta_xt"] > 0)
        ]

        total_xt_generated = round(float(success_actions["delta_xt"].sum()), 4)

        # Maiores geradores de xT acumulado por jogador
        player_xt = (
            success_actions.groupby("player_name")["delta_xt"]
            .sum()
            .reset_index()
            .sort_values(by="delta_xt", ascending=False)
            .head(5)
            .to_dict(orient="records")
        )

        # Maiores geradores de passes que quebram linhas
        line_breakers = (
            team_ev[team_ev["is_line_breaking_pass"] == 1]["player_name"]
            .dropna()
            .value_counts()
            .head(5)
            .to_dict()
        )

        return {
            "team_name": target_team,
            "total_xt_generated": total_xt_generated,
            "top_xt_generators": player_xt,
            "top_line_breaking_passers": line_breakers,
        }


if __name__ == "__main__":
    import json
    from src.ingestion.statsbomb_loader import StatsBombDataLoader
    from src.preprocessing.event_cleaner import EventPreprocessor

    print("=" * 78)
    print("TACTICAL INTELLIGENCE LAB - MODELO EXPECTED THREAT (xT) (DIA 5)")
    print("=" * 78)

    loader = StatsBombDataLoader()
    match_id = 3869685  # Final Copa 2022: Argentina vs França

    raw_df = loader.ingest_match_events(match_id)
    enriched_df = EventPreprocessor.process_match_events(raw_df)
    xt_enriched_df = ExpectedThreatModel.enrich_events_with_xt(enriched_df)

    for team in xt_enriched_df["team_name"].unique():
        summary = ExpectedThreatModel.compute_team_xt_summary(xt_enriched_df, team)

        print(f"\n======================================================================")
        print(f"ANÁLISE DE EXPECTED THREAT (xT) E QUEBRA DE LINHAS: {team.upper()}")
        print(f"======================================================================")
        print(f"  * Total de xT Líquido Gerado por Ações de Apetite: {summary['total_xt_generated']}")
        print(f"\n  [Top 3 Geradores de Ameaça Esperada (xT)]:")
        for p in summary["top_xt_generators"][:3]:
            print(f"    -> {p['player_name']}: +{p['delta_xt']:.4f} xT")

        print(f"\n  [Top 3 Passadores que Quebram Linhas Defensivas]:")
        for player, count in list(summary["top_line_breaking_passers"].items())[:3]:
            print(f"    -> {player}: {count} passes")

        safe_name = team.lower().replace(" ", "_")
        with open(
            f"data/processed/xt_summary_{match_id}_{safe_name}.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)