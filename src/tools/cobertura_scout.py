"""
Rodada 24 — quantos jogadores de cada liga chegam ao Scout, e por que os que faltam ficaram de fora (SÓ LEITURA).

    python -m src.tools.cobertura_scout                    # todas as ligas com jogos no último ano
    python -m src.tools.cobertura_scout --liga "Serie B"   # filtra pelo nome da competição

Para cada competição: atletas DIFERENTES com minutos no último ano na base (pessoas pelo id da FotMob, nunca só pelo
nome), quantos estão no universo do Scout, quantos têm qualidade, idade, nacionalidade, valor e potencial. Quem falta
aparece com o motivo (sem posição em nenhum jogo, fotografia antiga, homônimo sem confirmação…). Escreve
docs/COBERTURA_SCOUT.md.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUT = Path("docs/COBERTURA_SCOUT.md")


def base_players(db, days: int = 365, liga: str = "") -> pd.DataFrame:
    since = (date.today() - timedelta(days=days)).isoformat()
    q = """SELECT p.player_name, p.team_name, p.position, p.minutes, p.stats_json, m.competition_name, m.match_id
           FROM match_player_stats p JOIN matches m ON m.match_id = p.match_id
           WHERE m.match_date >= ? AND COALESCE(p.minutes, 0) > 0
             AND COALESCE(m.data_source, '') NOT IN ('simulated', 'upload')"""
    params = [since]
    if liga:
        q += " AND m.competition_name LIKE ?"
        params.append(f"%{liga}%")
    with db.connect() as conn:
        raw = pd.read_sql_query(q, conn, params=params)
    if raw.empty:
        return raw
    from src.data_lake.ids import player_core, team_core
    from src.scout.engine import assign_person_ids

    raw["_core"] = raw["player_name"].map(player_core)
    raw["_club_core"] = raw["team_name"].map(team_core)
    raw = assign_person_ids(raw)
    pos = raw["position"].fillna("").astype(str).str.strip()
    raw["_tem_pos"] = ~pos.isin(["", "SUB", "Sub", "sub", "?"])
    g = raw.groupby(["competition_name", "_pid"]).agg(nome=("player_name", "last"), clube=("team_name", "last"),
                                                      minutos=("minutes", "sum"), jogos=("match_id", "nunique"),
                                                      tem_posicao=("_tem_pos", "max")).reset_index()
    return g


def report(db, universe: pd.DataFrame, liga: str = "") -> pd.DataFrame:
    g = base_players(db, liga=liga)
    if g.empty:
        return pd.DataFrame()
    u = universe if universe is not None else pd.DataFrame()
    pids = set(u["pid"].astype(str)) if "pid" in u else set()
    hk = set(u["_hkey"].astype(str)) if "_hkey" in u else set()
    from src.scout.engine import ACTIVE_MIN_MINUTES

    def num(col):
        return pd.to_numeric(u.get(col), errors="coerce") if col in u else pd.Series(dtype=float)

    info = {}
    if not u.empty and "pid" in u:
        uu = u.assign(_q=num("qualidade"), _i=num("idade"), _v=num("valor_mercado_eur"),
                      _p=num("potencial") if "potencial" in u else num("potencial_teto"))
        info = uu.drop_duplicates("pid").set_index(uu.drop_duplicates("pid")["pid"].astype(str))[
            ["_q", "_i", "_v", "_p", "nacionalidade"]].to_dict("index")
    rows = []
    for comp, grp in g.groupby("competition_name"):
        n = len(grp)
        inside = grp["_pid"].astype(str).map(lambda x: x in pids or x in hk)
        why = []
        out = grp[~inside]
        if len(out):
            why.append(f"{int((out['minutos'] < ACTIVE_MIN_MINUTES).sum())} com menos de {ACTIVE_MIN_MINUTES} min")
            why.append(f"{int((~out['tem_posicao'].astype(bool)).sum())} sem posição em nenhum jogo")
            why.append(f"{int(((out['minutos'] >= ACTIVE_MIN_MINUTES) & out['tem_posicao'].astype(bool)).sum())} "
                       "fora por fotografia antiga (refaça: python -m src.scout.snapshot)")
        sel = [info.get(str(x), {}) for x in grp.loc[inside, "_pid"]]

        def has(k):
            return sum(1 for d in sel if d.get(k) is not None and d.get(k) == d.get(k) and str(d.get(k)) != "")
        rows.append({"competição": comp, "atletas na base": n, "no Scout": int(inside.sum()),
                     "com qualidade": has("_q"), "com idade": has("_i"), "com nacionalidade": has("nacionalidade"),
                     "com valor": has("_v"), "com potencial": has("_p"), "faltam (motivo)": "; ".join(why) or "—"})
    return pd.DataFrame(rows).sort_values("atletas na base", ascending=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--liga", default="")
    a = ap.parse_args()
    from src.data_hub.db import DataHubDB
    from src.scout import snapshot as S

    data = S.load() or {}
    t = report(DataHubDB(), data.get("universe"), a.liga)
    if t.empty:
        print("Nenhum jogo com números por jogador no último ano.")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Cobertura do Scout por competição (último ano)", "",
             f"Gerado em {date.today():%d/%m/%Y}. Pessoas pelo id do atleta na FotMob (homônimos separados).", "",
             "| " + " | ".join(t.columns) + " |", "|" + "---|" * len(t.columns)]
    lines += ["| " + " | ".join(str(v) for v in r) + " |" for r in t.itertuples(index=False)]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(t.head(40).to_string(index=False))
    print(f"\nRelatório completo em {OUT}")


if __name__ == "__main__":
    main()
