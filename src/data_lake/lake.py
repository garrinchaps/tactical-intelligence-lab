"""
Lake local: uma tabela por arquivo em data/lake/.

* Formato: Parquet (pyarrow) quando disponível; senão CSV comprimido (.csv.gz) — mesma API.
* DuckDB (opcional): se o pacote `duckdb` estiver instalado, data/lake/til.duckdb ganha uma VIEW por tabela,
  lendo direto dos arquivos (consultas SQL rápidas sobre milhões de linhas).
* Espelho no SQLite do app (tabelas `lake_<nome>`), para a interface consultar sem depender de nada extra.

Cada tabela guarda as colunas de proveniência (fonte, conector, licença, horário de ingestão).
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.canonical.schema import utc_now_iso

ROOT = Path("data/lake")
HAS_PARQUET = importlib.util.find_spec("pyarrow") is not None
HAS_DUCKDB = importlib.util.find_spec("duckdb") is not None


class Lake:
    def __init__(self, root: Path | str = ROOT, sqlite_path: Optional[Path | str] = "database/tactical_lab.db"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = Path(sqlite_path) if sqlite_path else None

    # --------------------------------------------------------------- arquivos
    def path(self, name: str) -> Path:
        pq = self.root / f"{name}.parquet"
        gz = self.root / f"{name}.csv.gz"
        if pq.exists():
            return pq
        if gz.exists():
            return gz
        return pq if HAS_PARQUET else gz

    def exists(self, name: str) -> bool:
        return (self.root / f"{name}.parquet").exists() or (self.root / f"{name}.csv.gz").exists()

    def write(self, name: str, df: pd.DataFrame, source: str = "", connector: str = "", license: str = "",
              mirror_sqlite: bool = True) -> Path:
        df = df.copy()
        for col, val in (("fonte", source), ("conector", connector), ("licenca", license)):
            if val and col not in df.columns:
                df[col] = val
        if "ingestao_utc" not in df.columns:
            df["ingestao_utc"] = utc_now_iso()
        if HAS_PARQUET:
            out = self.root / f"{name}.parquet"
            df.to_parquet(out, index=False)
            (self.root / f"{name}.csv.gz").unlink(missing_ok=True)
        else:
            out = self.root / f"{name}.csv.gz"
            df.to_csv(out, index=False, compression="gzip")
        if mirror_sqlite:
            self._mirror(name, df)
        self._duck_view(name, out)
        return out

    def upsert(self, name: str, df: pd.DataFrame, keys: List[str], **prov) -> Path:
        """Acrescenta linhas novas e substitui as que já existem pelas chaves (atualização incremental diária)."""
        if self.exists(name) and not df.empty:
            old = self.read(name)
            keep = old.merge(df[keys].drop_duplicates(), on=keys, how="left", indicator=True)
            old = old[(keep["_merge"] == "left_only").to_numpy()]
            df = pd.concat([old, df], ignore_index=True)
        return self.write(name, df, **prov)

    def read(self, name: str, columns: Optional[List[str]] = None) -> pd.DataFrame:
        p = self.path(name)
        if not p.exists():
            return pd.DataFrame()
        if p.suffix == ".parquet":
            return pd.read_parquet(p, columns=columns)
        head = pd.read_csv(p, nrows=0).columns
        ids = {c: str for c in head if c.endswith("_id") or c in ("id_fonte", "team_key", "player_key")}
        df = pd.read_csv(p, low_memory=False, dtype=ids, keep_default_na=True).fillna({c: "" for c in ids})
        return df[columns] if columns else df

    def tables(self) -> pd.DataFrame:
        rows = []
        for f in sorted(self.root.glob("*")):
            if f.suffix not in (".parquet", ".gz") or f.name.endswith(".duckdb"):
                continue
            name = f.name.replace(".parquet", "").replace(".csv.gz", "")
            try:
                n = len(self.read(name, None))
            except Exception:
                n = None
            rows.append({"tabela": name, "linhas": n, "arquivo": f.name, "MB": round(f.stat().st_size / 1e6, 2)})
        return pd.DataFrame(rows)

    # ---------------------------------------------------------------- espelhos
    def _mirror(self, name: str, df: pd.DataFrame) -> None:
        if not self.sqlite_path or not self.sqlite_path.parent.exists():
            return
        try:
            with sqlite3.connect(str(self.sqlite_path), timeout=30) as conn:
                df.astype({c: "string" for c in df.columns if df[c].dtype == object}).to_sql(
                    f"lake_{name}", conn, if_exists="replace", index=False, chunksize=5000)
        except Exception:
            pass   # o espelho é conveniência; o arquivo do lake é a fonte da verdade

    def _duck_view(self, name: str, path: Path) -> None:
        if not HAS_DUCKDB:
            return
        try:
            import duckdb

            with duckdb.connect(str(self.root / "til.duckdb")) as con:
                fn = "read_parquet" if path.suffix == ".parquet" else "read_csv_auto"
                con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {fn}('{path.as_posix()}')")
        except Exception:
            pass

    def sql(self, query: str) -> pd.DataFrame:
        """Consulta SQL: DuckDB sobre os arquivos quando instalado; senão o espelho SQLite (tabelas lake_<nome>)."""
        if HAS_DUCKDB:
            import duckdb

            with duckdb.connect(str(self.root / "til.duckdb")) as con:
                return con.execute(query).df()
        with sqlite3.connect(str(self.sqlite_path)) as conn:
            return pd.read_sql_query(query, conn)


def status() -> Dict[str, object]:
    return {"parquet": HAS_PARQUET, "duckdb": HAS_DUCKDB, "pasta": str(ROOT)}
