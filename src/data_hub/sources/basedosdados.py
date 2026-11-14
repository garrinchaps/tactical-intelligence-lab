"""
Base dos Dados (basedosdados.org) — histórico do Brasileirão Série A desde 2003 (dados compilados do
Transfermarkt): público, árbitro, estádio, técnicos, valor dos elencos, idade média, gols e estatísticas.

Acesso pelo BigQuery (gratuito até a cota mensal do Google Cloud): defina BASEDOSDADOS_BILLING_ID no .env com o
ID de um projeto seu do Google Cloud e instale `basedosdados` ou `google-cloud-bigquery`
(pip install google-cloud-bigquery db-dtypes). Sem isso o conector fica desativado e avisa o motivo.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional

import pandas as pd

TABLE = "basedosdados.mundo_transfermarkt_competicoes.brasileirao_serie_a"
LICENSE = "Base dos Dados (CC BY 4.0 nos dados tratados) — citar Base dos Dados e a fonte original"


class BaseDosDadosProvider:
    source = "basedosdados"

    def __init__(self, billing_id: Optional[str] = None):
        self.billing = (billing_id if billing_id is not None else os.getenv("BASEDOSDADOS_BILLING_ID", "")).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.billing)

    def query(self, sql: str) -> pd.DataFrame:
        try:
            import basedosdados as bd  # type: ignore

            return bd.read_sql(sql, billing_project_id=self.billing)
        except ImportError:
            pass
        try:
            from google.cloud import bigquery  # type: ignore
        except ImportError as exc:
            raise RuntimeError("instale `basedosdados` ou `google-cloud-bigquery` para usar a Base dos Dados") from exc
        return bigquery.Client(project=self.billing).query(sql).to_dataframe()

    @staticmethod
    def normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Nomes de coluna da tabela da Base dos Dados → nomes do laboratório (as demais colunas são mantidas)."""
        ren = {"ano_campeonato": "temporada", "data": "data", "rodada": "rodada", "estadio": "estadio",
               "arbitro": "arbitro", "publico": "publico", "publico_max": "capacidade", "time_mandante": "mandante",
               "time_visitante": "visitante", "tecnico_mandante": "tecnico_mandante", "tecnico_visitante": "tecnico_visitante",
               "colocacao_mandante": "posicao_mandante", "colocacao_visitante": "posicao_visitante",
               "valor_equipe_titular_mandante": "valor_titulares_mandante",
               "valor_equipe_titular_visitante": "valor_titulares_visitante",
               "idade_media_titular_mandante": "idade_media_mandante", "idade_media_titular_visitante": "idade_media_visitante",
               "gols_mandante": "gols_mandante", "gols_visitante": "gols_visitante"}
        out = df.rename(columns={k: v for k, v in ren.items() if k in df.columns})
        if "data" in out:
            out["data"] = out["data"].astype(str).str[:10]
        return out

    def sync(self, lake, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        df = self.normalize(self.query(f"SELECT * FROM `{TABLE}`"))
        lake.write("bd_brasileirao", df, source="Base dos Dados", connector="BaseDosDadosProvider", license=LICENSE)
        say(f"  base dos dados: {len(df)} partidas do Brasileirão")
        return {"partidas": len(df), "updated": len(df)}
