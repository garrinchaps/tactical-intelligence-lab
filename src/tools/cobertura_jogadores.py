"""
Diagnóstico (SÓ LEITURA) da cobertura de dados POR JOGADOR, por competição e temporada.

    python -m src.tools.cobertura_jogadores          # gera docs/COBERTURA_JOGADORES.md

Para cada competição/temporada recente mostra: partidas, com estatística de equipe, com escalação, com números por
jogador, com métricas avançadas (xG/xA por jogador), com lances; quantos atletas chegam a 450 e a 900 minutos; quanto
desses atletas existe no cadastro do Transfermarkt (valor/idade/contrato). É a base do diagnóstico do Scout: mostra
onde o ranking é confiável, onde é parcial e onde simplesmente não há dado.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

OUT = Path("docs/COBERTURA_JOGADORES.md")


def collect(db, since_year: int) -> pd.DataFrame:
    since = f"{since_year}-01-01"
    with db.connect() as conn:
        m = pd.read_sql_query(
            "SELECT match_id, competition_name AS comp, season_name AS temporada, data_level FROM matches "
            "WHERE match_date >= ? AND COALESCE(data_level,'') NOT IN ('SIMULATED','UPLOAD')", conn, params=[since])
        if m.empty:
            return pd.DataFrame()
        ids = tuple(int(x) for x in m["match_id"])
        def ids_in(table: str) -> set:
            q = f"SELECT DISTINCT match_id FROM {table} WHERE match_id IN (SELECT match_id FROM matches WHERE match_date >= ?)"
            try:
                return {int(r[0]) for r in conn.execute(q, (since,)).fetchall()}
            except Exception:
                return set()
        lu, ps, ts = ids_in("match_lineups"), ids_in("match_player_stats"), ids_in("match_team_stats")
        try:
            adv = {int(r[0]) for r in conn.execute(
                "SELECT DISTINCT p.match_id FROM match_player_stats p JOIN matches mm ON mm.match_id = p.match_id "
                "WHERE mm.match_date >= ? AND p.stats_json LIKE '%\"xa\"%'", (since,)).fetchall()}
        except Exception:
            adv = set()
        pl = pd.read_sql_query(
            "SELECT m.competition_name AS comp, m.season_name AS temporada, p.player_name, SUM(p.minutes) AS mins "
            "FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id WHERE m.match_date >= ? "
            "GROUP BY 1, 2, 3", conn, params=[since])
    m["escalacao"] = m["match_id"].isin(lu)
    m["por_jogador"] = m["match_id"].isin(ps)
    m["equipe"] = m["match_id"].isin(ts)
    m["avancado"] = m["match_id"].isin(adv)
    m["lances"] = m["data_level"].eq("EVENTS")
    g = m.groupby(["comp", "temporada"]).agg(partidas=("match_id", "size"), equipe=("equipe", "sum"),
                                             escalacao=("escalacao", "sum"), por_jogador=("por_jogador", "sum"),
                                             avancado=("avancado", "sum"), lances=("lances", "sum")).reset_index()
    if not pl.empty:
        try:
            from src.data_lake.ids import player_core
            from src.squad import data as D

            tm = D.table("tm_jogadores", ["nome"])
            tm_cores = set(tm["nome"].astype(str).map(player_core)) if not tm.empty else set()
        except Exception:
            tm_cores = set()
        pl["mins"] = pd.to_numeric(pl["mins"], errors="coerce").fillna(0)
        pl["tm"] = pl["player_name"].astype(str).map(lambda n: __import__("src.data_lake.ids", fromlist=["player_core"])
                                                     .player_core(n) in tm_cores) if tm_cores else False
        a = pl.groupby(["comp", "temporada"]).agg(
            atletas=("player_name", "nunique"),
            atletas_450=("mins", lambda s: int((s >= 450).sum())),
            atletas_900=("mins", lambda s: int((s >= 900).sum())),
            no_transfermarkt=("tm", "mean")).reset_index()
        g = g.merge(a, on=["comp", "temporada"], how="left")
    g = g.sort_values(["partidas"], ascending=False)
    for c in ("equipe", "escalacao", "por_jogador", "avancado", "lances"):
        g[c + "_%"] = (100 * g[c] / g["partidas"]).round(0)
    return g


def classify(r) -> str:
    if r.get("lances_%", 0) >= 50:
        return "🟢 tática completa (lances)"
    if r.get("avancado_%", 0) >= 60 and r.get("escalacao_%", 0) >= 60:
        return "🟢 scout confiável (números avançados por jogador)"
    if r.get("por_jogador_%", 0) >= 60:
        return "🟡 scout parcial (números por jogador básicos)"
    if r.get("equipe_%", 0) >= 60:
        return "🟠 só equipe (sem números por jogador)"
    return "🔴 só placar"


def write(db, since_year: int, out: Path = OUT) -> Path:
    g = collect(db, since_year)
    lines = [f"# Cobertura de dados por jogador — desde {since_year}",
             "", f"Gerado em {date.today():%d/%m/%Y} a partir do banco local (só leitura).", "",
             "Legenda: 🟢 tática completa · 🟢 scout confiável · 🟡 scout parcial · 🟠 só equipe · 🔴 só placar.", ""]
    if g.empty:
        lines.append("Sem partidas no período.")
    else:
        g["classe"] = g.apply(classify, axis=1)
        cols = ["comp", "temporada", "partidas", "equipe_%", "escalacao_%", "por_jogador_%", "avancado_%", "lances_%",
                "atletas_450", "atletas_900", "no_transfermarkt", "classe"]
        cols = [c for c in cols if c in g]
        view = g[cols].head(400).copy()
        if "no_transfermarkt" in view:
            view["no_transfermarkt"] = (100 * view["no_transfermarkt"].fillna(0)).round(0).astype(int).astype(str) + "%"
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for r in view.to_dict("records"):
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    from src.data_hub.db import DataHubDB

    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=date.today().year - 1)
    a = ap.parse_args()
    p = write(DataHubDB(), a.desde)
    print(f"Relatório gerado: {p}")


if __name__ == "__main__":
    main()
