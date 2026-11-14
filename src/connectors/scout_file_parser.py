"""
ScoutFileParser (Módulo 3.2) — compatibilidade de formato com bases de scout avançado.

Lê ARQUIVOS FORNECIDOS PELO USUÁRIO (CSV, JSON ou planilha .xlsx). Não coleta, não raspa
e não redistribui conteúdo de terceiros. Três tipos de tabela analítica são aceitos
(modelos em data/templates/):

1. xt_zonas         — xT por zona do campo
   colunas: equipe, zona_x (1–12), zona_y (1–8), xt (0–1) [, partida]
   ou grade larga 8 linhas × 12 colunas só com números (zona_y nas linhas).
2. matriz_passes    — passes entre atletas
   colunas: equipe, passador, receptor, passes (inteiro ≥ 0) [, partida]
   ou matriz quadrada com nomes nas linhas (passador) e colunas (receptor).
3. metricas_equipe  — métricas por equipe e partida
   colunas: partida, equipe, ppda (> 0) [, outras métricas numéricas]

Cada linha vira um registro no schema canônico de AGREGADOS (tier DERIVED, porque são
valores analíticos calculados por terceiros e informados pelo usuário).
Arquivos malformados geram ScoutFileError citando arquivo, tipo, campo e linha.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import pandas as pd

from src.canonical.schema import make_aggregate_frame
from src.connectors.base import Connector

KINDS = ("xt_zonas", "matriz_passes", "metricas_equipe")
REQUIRED = {
    "xt_zonas": ["equipe", "zona_x", "zona_y", "xt"],
    "matriz_passes": ["equipe", "passador", "receptor", "passes"],
    "metricas_equipe": ["partida", "equipe", "ppda"],
}
ALIASES = {
    "time": "equipe", "team": "equipe", "clube": "equipe", "match": "partida", "match_id": "partida", "jogo": "partida",
    "x": "zona_x", "zone_x": "zona_x", "y": "zona_y", "zone_y": "zona_y", "xT": "xt", "threat": "xt",
    "from": "passador", "origem": "passador", "passer": "passador", "to": "receptor", "destino": "receptor",
    "receiver": "receptor", "count": "passes", "qtd": "passes", "quantidade": "passes", "PPDA": "ppda",
}


class ScoutFileError(ValueError):
    """Arquivo de scout fora do formato; a mensagem cita o campo problemático."""


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for c in df.columns:
        key = str(c).strip()
        low = key.lower().replace(" ", "_")
        rename[c] = ALIASES.get(key, ALIASES.get(low, low))
    return df.rename(columns=rename)


def _to_number(series: pd.Series) -> pd.Series:
    """Aceita '0,123' (BR) e '0.123' (US)."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    s = series.astype(str).str.strip()
    br = s.str.contains(r"^\-?\d{1,3}(?:\.\d{3})*,\d+$|^\-?\d+,\d+$", regex=True)
    s = s.where(~br, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


class ScoutFileParser(Connector):
    name = "ScoutFileParser"
    source = "Arquivo de scout fornecido pelo usuário"
    license = "Fornecido pelo usuário — uso sob responsabilidade de quem detém os direitos do arquivo"
    family = "aggregates"
    default_tier = "DERIVED"

    # ------------------------------------------------------------ leitura
    @classmethod
    def read_any(cls, data: Union[str, Path, bytes], filename: str) -> Dict[str, pd.DataFrame]:
        """Devolve {nome_da_tabela: DataFrame}. Planilhas podem ter várias abas (uma por tipo)."""
        ext = Path(filename).suffix.lower()
        raw = data if isinstance(data, bytes) else Path(data).read_bytes()
        try:
            if ext == ".csv":
                text = raw.decode("utf-8-sig")
                sep = ";" if text.count(";") > text.count(",") else ","
                return {Path(filename).stem: pd.read_csv(io.StringIO(text), sep=sep, dtype=str)}
            if ext in (".xlsx", ".xls"):
                sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, dtype=str)
                return {str(k): v for k, v in sheets.items()}
            if ext == ".json":
                obj = json.loads(raw.decode("utf-8-sig"))
                if isinstance(obj, dict) and "dados" in obj:
                    return {str(obj.get("tipo", Path(filename).stem)): pd.DataFrame(obj["dados"]).astype(str)}
                if isinstance(obj, dict):
                    return {str(k): pd.DataFrame(v).astype(str) for k, v in obj.items() if isinstance(v, list)}
                return {Path(filename).stem: pd.DataFrame(obj).astype(str)}
        except ScoutFileError:
            raise
        except Exception as exc:
            raise ScoutFileError(f"Arquivo '{filename}': não foi possível ler ({type(exc).__name__}: {exc}).")
        raise ScoutFileError(f"Arquivo '{filename}': extensão '{ext}' não suportada (use .csv, .json ou .xlsx).")

    @staticmethod
    def detect_kind(df: pd.DataFrame, hint: str = "") -> Optional[str]:
        h = hint.lower()
        for k in KINDS:
            if k in h or k.replace("_", " ") in h:
                return k
        cols = set(_norm_cols(df).columns)
        if cols & {"passador", "receptor"} or ("passes" in cols and "equipe" in cols):
            return "matriz_passes"
        if {"zona_x", "zona_y"} <= cols or "xt" in cols:
            return "xt_zonas"
        if "ppda" in cols:
            return "metricas_equipe"
        if df.shape == (8, 12) or df.shape == (8, 13):
            return "xt_zonas"
        if df.shape[0] >= 2 and df.shape[1] == df.shape[0] + 1:
            return "matriz_passes"
        return None

    # --------------------------------------------------------- validação
    @classmethod
    def _wide_to_long(cls, df: pd.DataFrame, kind: str, team: str) -> pd.DataFrame:
        if kind == "xt_zonas":
            grid = df.iloc[:, -12:]
            rows = []
            for zy in range(grid.shape[0]):
                for zx in range(12):
                    rows.append({"equipe": team, "zona_x": zx + 1, "zona_y": zy + 1, "xt": grid.iat[zy, zx]})
            return pd.DataFrame(rows)
        names = df.iloc[:, 0].astype(str).tolist()
        rows = []
        for i, passer in enumerate(names):
            for j, receiver in enumerate(df.columns[1:]):
                rows.append({"equipe": team, "passador": passer, "receptor": str(receiver), "passes": df.iat[i, j + 1]})
        return pd.DataFrame(rows)

    @classmethod
    def validate_table(cls, df: pd.DataFrame, kind: str, filename: str, default_team: str = "") -> pd.DataFrame:
        where = f"Arquivo '{filename}' (tipo {kind})"
        if df is None or df.empty:
            raise ScoutFileError(f"{where}: tabela vazia.")
        d = _norm_cols(df.copy())
        if not set(REQUIRED[kind]) <= set(d.columns):
            wide_ok = (kind == "xt_zonas" and df.shape[0] == 8 and df.shape[1] >= 12) or \
                      (kind == "matriz_passes" and df.shape[1] == df.shape[0] + 1)
            if wide_ok and default_team:
                d = cls._wide_to_long(df, kind, default_team)
            else:
                missing = [c for c in REQUIRED[kind] if c not in d.columns]
                raise ScoutFileError(f"{where}: coluna obrigatória ausente: {', '.join(repr(m) for m in missing)}. "
                                     f"Colunas encontradas: {list(df.columns)}.")
        for col in REQUIRED[kind]:
            empty = d[col].isna() | (d[col].astype(str).str.strip().isin(["", "nan", "None"]))
            if empty.any():
                line = int(empty.idxmax()) + 2
                raise ScoutFileError(f"{where}: campo '{col}' vazio na linha {line}.")

        def numeric(col: str, lo: Optional[float], hi: Optional[float], integer: bool = False) -> None:
            vals = _to_number(d[col])
            bad = vals.isna()
            if bad.any():
                i = int(bad.idxmax())
                raise ScoutFileError(f"{where}: campo '{col}' com valor não numérico '{d.at[i, col]}' na linha {i + 2}.")
            if lo is not None and (vals < lo).any() or hi is not None and (vals > hi).any():
                i = int(((vals < (lo if lo is not None else -1e18)) | (vals > (hi if hi is not None else 1e18))).idxmax())
                raise ScoutFileError(f"{where}: campo '{col}' = {vals[i]:g} fora do intervalo "
                                     f"[{lo if lo is not None else '-∞'}; {hi if hi is not None else '∞'}] na linha {i + 2}.")
            if integer and ((vals % 1) != 0).any():
                i = int(((vals % 1) != 0).idxmax())
                raise ScoutFileError(f"{where}: campo '{col}' deve ser inteiro (linha {i + 2}: {vals[i]:g}).")
            d[col] = vals

        if kind == "xt_zonas":
            numeric("zona_x", 1, 12, True)
            numeric("zona_y", 1, 8, True)
            numeric("xt", 0.0, 1.0)
        elif kind == "matriz_passes":
            numeric("passes", 0, None, True)
        else:
            numeric("ppda", 0.0001, 200.0)
            for extra in [c for c in d.columns if c not in REQUIRED[kind]]:
                vals = _to_number(d[extra])
                if vals.notna().all():
                    d[extra] = vals
        return d

    # ----------------------------------------------------------- mapeamento
    @classmethod
    def to_canonical(cls, d: pd.DataFrame, kind: str, filename: str) -> pd.DataFrame:
        src = f"{cls.source}: {filename}"
        rows: List[Dict[str, Any]] = []
        if kind == "xt_zonas":
            for r in d.itertuples(index=False):
                rows.append({"match_id": getattr(r, "partida", None), "team_id": r.equipe,
                             "entity": f"zona({int(r.zona_x)},{int(r.zona_y)})", "metric": "xt_zona", "value": r.xt})
        elif kind == "matriz_passes":
            for r in d.itertuples(index=False):
                rows.append({"match_id": getattr(r, "partida", None), "team_id": r.equipe,
                             "entity": f"{r.passador}→{r.receptor}", "metric": "passes_par", "value": r.passes})
        else:
            for _, r in d.iterrows():
                for col in d.columns:
                    if col in ("partida", "equipe") or not isinstance(r[col], (int, float)):
                        continue
                    rows.append({"match_id": r["partida"], "team_id": r["equipe"], "entity": r["equipe"],
                                 "metric": col, "value": r[col]})
        return make_aggregate_frame(rows, src, cls.name, cls.license, cls.default_tier)

    @classmethod
    def parse(cls, data: Union[str, Path, bytes], filename: str, default_team: str = "") -> Dict[str, Any]:
        """Lê, valida e mapeia. Devolve {'tabelas': {tipo: df_validado}, 'canonico': df_agregados}."""
        tables = cls.read_any(data, filename)
        validated: Dict[str, pd.DataFrame] = {}
        canon: List[pd.DataFrame] = []
        for name, df in tables.items():
            kind = cls.detect_kind(df, name)
            if kind is None:
                raise ScoutFileError(
                    f"Arquivo '{filename}', tabela '{name}': tipo não reconhecido. Use colunas de um dos modelos: "
                    + "; ".join(f"{k} = {REQUIRED[k]}" for k in KINDS) + ".")
            d = cls.validate_table(df, kind, filename, default_team)
            validated[kind] = d
            canon.append(cls.to_canonical(d, kind, filename))
        return {"tabelas": validated, "canonico": pd.concat(canon, ignore_index=True)}

    # ------------------------------------------------------- análises úteis
    @staticmethod
    def pass_network(d: pd.DataFrame, team: Optional[str] = None) -> Dict[str, Any]:
        """Grafo dirigido da matriz de passes + grau e betweenness (distância = 1/passes)."""
        t = d if team is None else d[d["equipe"] == team]
        g = nx.DiGraph()
        for r in t.itertuples(index=False):
            if r.passes > 0 and r.passador != r.receptor:
                g.add_edge(r.passador, r.receptor, weight=float(r.passes), distance=1.0 / float(r.passes))
        if g.number_of_nodes() == 0:
            return {"graph": g, "table": pd.DataFrame()}
        deg = dict(g.degree(weight="weight"))
        btw = nx.betweenness_centrality(g, weight="distance", normalized=True)
        table = pd.DataFrame({"atleta": list(g.nodes()),
                              "grau_ponderado": [deg[n] for n in g.nodes()],
                              "betweenness": [round(btw[n], 4) for n in g.nodes()]}).sort_values(
            "betweenness", ascending=False)
        return {"graph": g, "table": table}

    @staticmethod
    def xt_grid(d: pd.DataFrame, team: Optional[str] = None) -> pd.DataFrame:
        t = d if team is None else d[d["equipe"] == team]
        return t.pivot_table(index="zona_y", columns="zona_x", values="xt", aggfunc="mean").sort_index()
