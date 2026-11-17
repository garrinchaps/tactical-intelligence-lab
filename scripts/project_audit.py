"""Auditoria estática e não destrutiva do Tactical Intelligence Lab.

O script inventaria módulos, páginas Streamlit, conectores, testes, símbolos e
dependências internas. Opcionalmente, lê o schema SQLite em modo estritamente
read-only. Não altera código, banco, arquivos de dados nem executa sincronizações.

Exemplos:
    python scripts/project_audit.py
    python scripts/project_audit.py --database database/tactical_lab.db
    python scripts/project_audit.py --database database/tactical_lab.db --count-rows --check-integrity
    python scripts/project_audit.py --output data/audits/project_audit.json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "site-packages",
}
HOTSPOT_CALLS = {
    "iterrows",
    "itertuples",
    "loads",
    "execute",
    "executemany",
    "read_sql",
    "read_sql_query",
    "read_parquet",
}
CACHE_CALLS = {"cache_data", "cache_resource", "lru_cache"}


def _python_files(root: Path) -> Iterable[Path]:
    """Itera somente pelo código-fonte do projeto, ignorando ambientes e caches."""
    for path in sorted(root.rglob("*.py")):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        yield path


def _module_name(relative: Path) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def inspect_python(root: Path) -> dict[str, Any]:
    """Cria inventário AST sem importar ou executar os módulos analisados."""
    files: list[dict[str, Any]] = []
    pages: list[str] = []
    tests: list[str] = []
    connectors: list[str] = []
    symbols: dict[str, dict[str, list[str]]] = {}
    syntax_errors: list[dict[str, str]] = []
    internal_imports: dict[str, list[str]] = {}
    hotspots: list[dict[str, Any]] = []
    cache_usage: list[dict[str, Any]] = []

    for path in _python_files(root):
        relative = path.relative_to(root)
        rel = relative.as_posix()
        try:
            source = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            files.append({"path": rel, "read_error": str(exc)})
            continue

        entry: dict[str, Any] = {
            "path": rel,
            "module": _module_name(relative),
            "bytes": len(source.encode("utf-8")),
            "lines": len(source.splitlines()),
        }

        if rel == "app.py" or rel.startswith("src/ui/pages/"):
            pages.append(rel)
        if rel.startswith("tests/") and (path.name.startswith("test_") or path.name.endswith("_test.py")):
            tests.append(rel)
        if rel.startswith(("src/connectors/", "src/data_hub/sources/")):
            connectors.append(rel)

        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as exc:
            entry["syntax_error"] = f"{exc.msg} (linha {exc.lineno})"
            syntax_errors.append({"path": rel, "error": entry["syntax_error"]})
            files.append(entry)
            continue

        functions: list[str] = []
        classes: list[str] = []
        imports: set[str] = set()
        calls: dict[str, int] = {}
        cache_calls: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names if alias.name.startswith("src."))
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("src."):
                    imports.add(node.module)
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                    node.func.id if isinstance(node.func, ast.Name) else ""
                )
                if name in HOTSPOT_CALLS:
                    calls[name] = calls.get(name, 0) + 1
                if name in CACHE_CALLS:
                    cache_calls.add(name)

        files.append(entry)
        symbols[rel] = {
            "functions": sorted(set(functions)),
            "classes": sorted(set(classes)),
        }
        internal_imports[rel] = sorted(imports)
        if calls:
            hotspots.append({"path": rel, "calls": calls})
        if cache_calls:
            cache_usage.append({"path": rel, "decorators_or_calls": sorted(cache_calls)})

    return {
        "python_file_count": len(files),
        "page_entrypoints": pages,
        "test_files": tests,
        "connector_files": connectors,
        "syntax_errors": syntax_errors,
        "files": files,
        "symbols": symbols,
        "internal_imports": internal_imports,
        "performance_call_sites": hotspots,
        "cache_call_sites": cache_usage,
    }


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def inspect_database(
    database_path: Path,
    *,
    count_rows: bool = False,
    check_integrity: bool = False,
) -> dict[str, Any]:
    """Lê estrutura SQLite por URI mode=ro; nunca cria ou modifica o arquivo."""
    result: dict[str, Any] = {
        "path": str(database_path),
        "exists": database_path.is_file(),
        "bytes": database_path.stat().st_size if database_path.is_file() else 0,
        "read_only": True,
        "integrity_check": "not_requested",
        "table_count": 0,
        "tables": [],
        "error": None,
    }
    if not database_path.is_file():
        return result

    try:
        uri = database_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=10)
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            if check_integrity:
                result["integrity_check"] = connection.execute("PRAGMA quick_check").fetchone()[0]

            table_names = connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()

            tables: list[dict[str, Any]] = []
            for (table_name,) in table_names:
                quoted = _quote_identifier(str(table_name))
                columns = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
                indexes = connection.execute(f"PRAGMA index_list({quoted})").fetchall()
                foreign_keys = connection.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
                item: dict[str, Any] = {
                    "name": str(table_name),
                    "columns": [
                        {
                            "name": column[1],
                            "type": column[2],
                            "not_null": bool(column[3]),
                            "primary_key_position": int(column[5]),
                        }
                        for column in columns
                    ],
                    "indexes": [
                        {
                            "name": index[1],
                            "unique": bool(index[2]),
                            "origin": index[3],
                        }
                        for index in indexes
                    ],
                    "foreign_keys": [
                        {
                            "referenced_table": foreign_key[2],
                            "from_column": foreign_key[3],
                            "to_column": foreign_key[4],
                            "on_update": foreign_key[5],
                            "on_delete": foreign_key[6],
                        }
                        for foreign_key in foreign_keys
                    ],
                }
                if count_rows:
                    item["row_count"] = int(
                        connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
                    )
                tables.append(item)

            result["tables"] = tables
            result["table_count"] = len(tables)
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def build_report(
    root: Path,
    database_path: Path | None = None,
    *,
    count_rows: bool = False,
    check_integrity: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    python_inventory = inspect_python(root)

    requirements = root / "requirements.txt"
    dependencies: list[str] = []
    if requirements.is_file():
        for line in requirements.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "-")):
                dependencies.append(re.split(r"[<>=!~;\[]", stripped, maxsplit=1)[0].strip())

    directories = [
        "src/connectors",
        "src/data_hub/sources",
        "src/data_lake",
        "src/analytics",
        "src/intelligence",
        "src/machine_learning",
        "src/scout",
        "src/ui/pages",
        "tests",
        "docs",
    ]
    directory_inventory = {
        relative: {
            "exists": (root / relative).is_dir(),
            "files": sum(1 for item in (root / relative).rglob("*") if item.is_file())
            if (root / relative).is_dir()
            else 0,
        }
        for relative in directories
    }

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "scope": "static/read-only inventory; this is not a runtime, security, or performance certification",
        "directories": directory_inventory,
        "dependencies_from_requirements": sorted(set(dependencies)),
        "python": python_inventory,
        "database": inspect_database(
            database_path,
            count_rows=count_rows,
            check_integrity=check_integrity,
        ) if database_path else None,
        "limitations": [
            "AST inventory does not execute imports or functions.",
            "Call-site counts are investigation hints, not proof of slow SQL or inefficient code.",
            "Data-source freshness, legal permissions, runtime latency, memory use, and model accuracy require separate tests.",
            "SQLite row counts can be expensive and are only collected when --count-rows is supplied.",
            "PRAGMA quick_check can take time and is only run when --check-integrity is supplied.",
        ],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(os.getenv("DATABASE_PATH", "database/tactical_lab.db")),
        help="Caminho do SQLite; não será aberto em modo de escrita.",
    )
    parser.add_argument("--count-rows", action="store_true", help="Conta linhas de cada tabela (pode demorar).")
    parser.add_argument("--check-integrity", action="store_true", help="Executa PRAGMA quick_check (pode demorar).")
    parser.add_argument("--output", type=Path, help="Salva JSON no caminho indicado; sem isso, imprime resumo.")
    args = parser.parse_args()

    root = args.root.resolve()
    database_path = args.database if args.database.is_absolute() else root / args.database
    report = build_report(
        root,
        database_path,
        count_rows=args.count_rows,
        check_integrity=args.check_integrity,
    )

    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Inventário salvo em: {output}")
    else:
        py = report["python"]
        db = report["database"] or {}
        print("=== TACTICAL INTELLIGENCE LAB — AUDITORIA ESTÁTICA ===")
        print(f"Python: {py['python_file_count']} arquivos")
        print(f"Páginas/entradas Streamlit: {len(py['page_entrypoints'])}")
        print(f"Arquivos de teste: {len(py['test_files'])}")
        print(f"Arquivos conectores: {len(py['connector_files'])}")
        print(f"Erros de sintaxe AST: {len(py['syntax_errors'])}")
        print(f"Hotspots candidatos à revisão: {len(py['performance_call_sites'])}")
        print(f"Uso explícito de cache detectado: {len(py['cache_call_sites'])} arquivos")
        if db:
            print(f"SQLite encontrado: {db['exists']} ({db['bytes']:,} bytes)")
            print(f"Tabelas inventariadas: {db['table_count']}")
            if db["integrity_check"] != "not_requested":
                print(f"PRAGMA quick_check: {db['integrity_check']}")
            if db["error"]:
                print(f"Erro ao ler SQLite: {db['error']}")
        if py["syntax_errors"]:
            for error in py["syntax_errors"]:
                print(f"ERRO: {error['path']}: {error['error']}")

    return 1 if report["python"]["syntax_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
