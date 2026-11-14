"""
Utilitários para ler datasets tabulares públicos de formatos variados (CSV/JSON/Parquet) sem depender do nome
exato das colunas: normaliza os nomes (minúsculas, sem acento, `_`) e procura por sinônimos.
Usado pelos conectores de bases montadas pela comunidade (Brasileirão, súmulas da CBF, open-matchday, OpenPlay).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


def norm_col(c: Any) -> str:
    s = unicodedata.normalize("NFKD", str(c)).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: norm_col(c) for c in df.columns})


def find_col(df: pd.DataFrame, *candidates: str, contains: Iterable[str] = ()) -> Optional[str]:
    """Primeira coluna cujo nome normalizado é um dos candidatos (ou contém todos os termos de `contains`)."""
    cols = list(df.columns)
    for cand in candidates:
        n = norm_col(cand)
        if n in cols:
            return n
    terms = [norm_col(t) for t in contains]
    if terms:
        for c in cols:
            if all(t in c for t in terms):
                return c
    return None


def to_number(v: Any) -> Optional[float]:
    """'54%' → 54.0 · '1,5' → 1.5 · '' / '-' / NaN → None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace(",", ".")
    if s in ("", "-", "nan", "None", "NaN"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def to_int(v: Any) -> Optional[int]:
    x = to_number(v)
    return int(x) if x is not None and float(x).is_integer() else None


def parse_date(v: Any) -> str:
    """'29/03/2003', '2003-03-29', '2003-03-29T16:00:00Z' → '2003-03-29' ('' se não der)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return ""


def parse_minute(v: Any) -> Optional[int]:
    """"45+2'" → 45 · '90' → 90 · '' → None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else None


def extra_minute(v: Any) -> Optional[int]:
    m = re.search(r"\+\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def stable_id(*parts: Any, modulo: int = 900_000_000) -> int:
    """Id numérico estável a partir de um texto (para fontes sem id próprio)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:15], 16) % modulo


def stat(team: str, key: str, label: str, value: Any) -> Optional[Dict[str, Any]]:
    x = to_number(value)
    if x is None:
        return None
    return {"team_name": team, "stat_key": key, "stat_label": label, "value": x,
            "display_value": f"{x:g}"}


def describe(df: pd.DataFrame, n: int = 3) -> str:
    """Resumo do formato de um arquivo (para adaptar conectores a bases novas)."""
    lines = [f"{len(df)} linhas × {len(df.columns)} colunas"]
    for c in df.columns:
        ex = [str(x)[:30] for x in df[c].dropna().head(n).tolist()]
        lines.append(f"  - {c}: {', '.join(ex)}")
    return "\n".join(lines)


def read_any(path) -> List[pd.DataFrame]:
    """Lê CSV/JSON/Parquet de um arquivo (lista de tabelas; vazia se o formato não for reconhecido)."""
    from pathlib import Path

    p = Path(path)
    suf = p.suffix.lower()
    try:
        if suf in (".csv", ".txt"):
            for sep in (",", ";", "\t"):
                df = pd.read_csv(p, sep=sep, encoding="utf-8", on_bad_lines="skip", low_memory=False)
                if len(df.columns) > 3:
                    return [df]
            return [df]
        if suf == ".parquet":
            return [pd.read_parquet(p)]
        if suf == ".json":
            import json

            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [pd.json_normalize(data)]
            if isinstance(data, dict):
                lists = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
                scalars = [k for k, v in data.items() if not isinstance(v, list)]
                if lists and len(scalars) <= 2:          # {"partidas": [...]} → cada lista é uma tabela
                    return [pd.json_normalize(v) for v in lists]
                return [pd.json_normalize(data)]         # um registro (ex.: uma súmula), listas ficam como coluna
    except Exception:
        return []
    return []
