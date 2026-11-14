"""
Relatório de cobertura analítica — a "fonte da verdade" sobre o que a base realmente tem.

    python -m src.data_hub.coverage                  # gera docs/COBERTURA.md a partir do banco local
    python -m src.data_hub.coverage --saida outro.md

Conta, por competição e temporada, quantas partidas existem em cada nível de dado:
  EVENTOS       — lances com coordenadas (StatsBomb/Wyscout); "em disco" = já baixados
  ESTATÍSTICAS  — estatísticas de equipe (chutes, no alvo, posse, escanteios, faltas, cartões)
  SÓ PLACAR     — placar e, às vezes, autores dos gols/escalações; nenhuma estatística de equipe
e lista os campos vazios. Nada é estimado: o que não está no banco aparece como lacuna.
Também é regenerado ao fim de cada `python -m src.data_hub.sync`.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

OUT = Path("docs/COBERTURA.md")
LEVEL_NAMES = {"EVENTS": "EVENTOS", "BOXSCORE": "ESTATÍSTICAS", "RESULT": "SÓ PLACAR"}
KEY_STATS = [("shots_total", "chutes"), ("shots_on_target", "no alvo"), ("possession_pct", "posse"),
             ("corners", "escanteios"), ("fouls", "faltas"), ("yellow_cards", "amarelos"), ("xg", "xG")]
META_FIELDS = [("match_date", "data"), ("country_name", "país"), ("round_name", "rodada"),
               ("stadium_name", "estádio"), ("referee_name", "árbitro")]


def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA query_only = ON")
    return con


def collect(db_path: str) -> Dict[str, Any]:
    """Agrega tudo em SQL (rápido mesmo com centenas de milhares de partidas)."""
    con = _connect(db_path)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        mcols = {r[1] for r in con.execute("PRAGMA table_info(matches)")}
        col = lambda c: f"m.{c}" if c in mcols else "NULL"          # bases antigas sem as colunas novas
        stat_cols = ", ".join(
            f"MAX(CASE WHEN s.stat_key = '{k}' THEN 1 ELSE 0 END) AS has_{k}" for k, _ in KEY_STATS)
        has_tl = "EXISTS(SELECT 1 FROM match_timeline t WHERE t.match_id = m.match_id)" if "match_timeline" in tables else "0"
        has_lu = "EXISTS(SELECT 1 FROM match_lineups l WHERE l.match_id = m.match_id)" if "match_lineups" in tables else "0"
        has_ev = "EXISTS(SELECT 1 FROM events e WHERE e.match_id = m.match_id)" if "events" in tables else "0"
        meta_cols = ", ".join(f"CASE WHEN COALESCE(TRIM({col(c)}), '') = '' THEN 0 ELSE 1 END AS has_{c}" for c, _ in META_FIELDS)
        q = f"""
            WITH st AS (SELECT s.match_id, {stat_cols} FROM match_team_stats s GROUP BY s.match_id)
            SELECT m.match_id, COALESCE({col('data_source')}, '?') AS fonte, COALESCE({col('data_level')}, '?') AS nivel,
                   COALESCE(NULLIF(TRIM(m.competition_name), ''), '(sem competição)') AS competicao,
                   COALESCE(NULLIF(TRIM(m.season_name), ''), '(sem temporada)') AS temporada,
                   {meta_cols}, {has_tl} AS has_timeline, {has_lu} AS has_lineups, {has_ev} AS ev_em_disco,
                   {", ".join(f"COALESCE(st.has_{k}, 0) AS has_{k}" for k, _ in KEY_STATS)}
            FROM matches m LEFT JOIN st ON st.match_id = m.match_id
            WHERE COALESCE({col('data_level')}, '') NOT IN ('SIMULATED', 'UPLOAD')"""
        df = pd.read_sql_query(q, con)
        syncs = pd.read_sql_query(
            "SELECT source, MAX(started_at) AS ultima, SUM(status = 'OK') AS ok, SUM(status = 'ERRO') AS erros "
            "FROM sync_runs GROUP BY source", con) if "sync_runs" in tables else pd.DataFrame()
    finally:
        con.close()
    return {"rows": df, "syncs": syncs, "db_path": db_path}


def _pct(n: float, d: float) -> str:
    return "—" if not d else f"{100 * n / d:.0f}%"


def _table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(nenhuma linha)_\n"
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append("| " + " | ".join(str(v).replace("|", "/") for v in r) + " |")
    return "\n".join(out) + "\n"


def summarize(data: Dict[str, Any], max_comp_rows: int = 400) -> Dict[str, pd.DataFrame]:
    df = data["rows"]
    if df.empty:
        return {}
    df = df.assign(nivel_pt=df["nivel"].map(LEVEL_NAMES).fillna(df["nivel"]))
    # 1) visão geral por nível
    geral = df.groupby("nivel_pt").size().rename("partidas").reset_index()
    geral["%"] = [_pct(n, len(df)) for n in geral["partidas"]]
    # 2) por fonte
    fonte = df.pivot_table(index="fonte", columns="nivel_pt", values="match_id", aggfunc="count", fill_value=0)
    fonte["total"] = fonte.sum(axis=1)
    fonte = fonte.sort_values("total", ascending=False).reset_index()
    # 3) por competição e temporada
    g = df.groupby(["competicao", "temporada"])
    comp = pd.DataFrame({
        "partidas": g.size(),
        "EVENTOS": g["nivel"].apply(lambda s: int((s == "EVENTS").sum())),
        "eventos em disco": g["ev_em_disco"].sum().astype(int),
        "ESTATÍSTICAS": g["nivel"].apply(lambda s: int((s == "BOXSCORE").sum())),
        "SÓ PLACAR": g["nivel"].apply(lambda s: int((s == "RESULT").sum())),
        "fontes": g["fonte"].apply(lambda s: ", ".join(sorted(set(s)))),
    }).reset_index()
    stats_mask = df["nivel"] == "BOXSCORE"
    lacunas = []
    for (c, t), sub in df[stats_mask].groupby(["competicao", "temporada"]):
        vazios = [lab for k, lab in KEY_STATS if sub[f"has_{k}"].sum() == 0]
        lacunas.append({"competicao": c, "temporada": t, "estatísticas ausentes": ", ".join(vazios) or "—"})
    comp = comp.merge(pd.DataFrame(lacunas, columns=["competicao", "temporada", "estatísticas ausentes"]),
                      on=["competicao", "temporada"], how="left").fillna({"estatísticas ausentes": "n/a"})
    comp = comp.sort_values(["partidas"], ascending=False).head(max_comp_rows)
    comp = comp.rename(columns={"competicao": "competição", "temporada": "temporada"})
    # 4) preenchimento de campos
    campos = []
    for c, lab in META_FIELDS:
        campos.append({"campo": lab, "preenchido": _pct(df[f"has_{c}"].sum(), len(df)), "base": "todas as partidas"})
    campos.append({"campo": "linha do tempo (gols/cartões)", "preenchido": _pct(df["has_timeline"].sum(), len(df)),
                   "base": "todas as partidas"})
    campos.append({"campo": "escalações", "preenchido": _pct(df["has_lineups"].sum(), len(df)), "base": "todas as partidas"})
    nb = int(stats_mask.sum())
    for k, lab in KEY_STATS:
        campos.append({"campo": f"estatística: {lab}", "preenchido": _pct(df.loc[stats_mask, f"has_{k}"].sum(), nb),
                       "base": f"{nb} partidas com estatísticas"})
    ne = int((df["nivel"] == "EVENTS").sum())
    campos.append({"campo": "eventos já baixados", "preenchido": _pct(df.loc[df["nivel"] == "EVENTS", "ev_em_disco"].sum(), ne),
                   "base": f"{ne} partidas com eventos na fonte"})
    any_stat = df[[f"has_{k}" for k, _ in KEY_STATS]].max(axis=1)
    inc = []
    sem_num = df[stats_mask & (any_stat == 0)]
    if len(sem_num):
        inc.append({"problema": "marcadas ESTATÍSTICAS mas sem nenhum dos indicadores principais",
                    "partidas": len(sem_num), "fontes": ", ".join(sorted(set(sem_num["fonte"])))})
    ev_fora = df[(df["nivel"] == "EVENTS") & ~df["fonte"].isin(["statsbomb", "wyscout"])]
    if len(ev_fora):
        inc.append({"problema": "marcadas EVENTOS fora de StatsBomb/Wyscout", "partidas": len(ev_fora),
                    "fontes": ", ".join(sorted(set(ev_fora["fonte"])))})
    return {"geral": geral, "fonte": fonte, "comp": comp, "campos": pd.DataFrame(campos),
            "inconsistencias": pd.DataFrame(inc, columns=["problema", "partidas", "fontes"])}


def render(data: Dict[str, Any], now: Optional[datetime] = None, nota: str = "") -> str:
    now = now or datetime.now()
    df = data["rows"]
    s = summarize(data)
    head = (f"# Cobertura da base — Tactical Intelligence Lab\n\n"
            f"Gerado em {now:%d/%m/%Y %H:%M} a partir de `{Path(data['db_path']).name}` · "
            f"**{len(df):,} partidas reais** (simulações e uploads fora da conta).\n\n".replace(",", "."))
    if nota:
        head += f"> ⚠️ {nota}\n\n"
    if not s:
        return head + "A base está vazia. Rode `python -m src.data_hub.sync` e gere de novo.\n"
    md = [head,
          "> Honestidade técnica: estes números saem direto do banco. Ligas e temporadas que não aparecem aqui "
          "**não estão em nenhuma fonte aberta sincronizada** — são lacunas reais, não zeros estimados.\n",
          "## Níveis de dado\n",
          "- **EVENTOS** — lances com coordenadas (passes, chutes, duelos): análise espacial completa.\n"
          "- **ESTATÍSTICAS** — estatísticas de equipe (chutes, no alvo, posse, escanteios, faltas, cartões).\n"
          "- **SÓ PLACAR** — placar e, quando a fonte traz, autores dos gols e escalações. Sem estatísticas.\n",
          "## Visão geral\n", _table(s["geral"].rename(columns={"nivel_pt": "nível"})),
          "## Inconsistências detectadas\n",
          (_table(s["inconsistencias"]) if not s["inconsistencias"].empty else "Nenhuma.\n"),
          "## Por fonte\n", _table(s["fonte"]),
          "## Preenchimento de campos\n", _table(s["campos"]),
          f"## Por competição e temporada (maiores {len(s['comp'])})\n",
          "`estatísticas ausentes` lista, para os jogos com estatísticas, quais indicadores nenhuma partida "
          "daquela temporada traz (`n/a` = não há jogos com estatísticas).\n\n", _table(s["comp"])]
    qa = data.get("qualidade")
    if qa:
        md += ["## Qualidade dos dados\n",
               f"- Partidas auditadas: {qa['partidas']}\n"
               f"- Bloqueadas pela validação (placar negativo, equipe vazia, data impossível): {len(qa['rejeitaveis'])}\n"
               f"- Avisos de data fora da temporada: {len(qa['avisos'])}\n"
               f"- Duplicatas reais (mesmo conteúdo SHA-256, mesma fonte, ids diferentes): {len(qa['duplicatas'])}\n"
               f"- Mesma partida presente em outra fonte (ligações esperadas): {qa['ligacoes']}\n"
               f"- Lances com minuto fora de 0–130: {qa['lances_fora']} · eventos fora do campo/minuto: {qa['eventos_fora']}\n"]
        if len(qa["duplicatas"]):
            md += ["\nPrimeiras duplicatas:\n\n", _table(qa["duplicatas"].drop(columns=["hash"]).head(20))]
        if len(qa["avisos"]):
            md += ["\nPrimeiros avisos:\n\n", _table(qa["avisos"].head(20))]
    sy = data.get("syncs")
    if sy is not None and not sy.empty:
        md += ["## Últimas sincronizações\n", _table(sy.rename(columns={"source": "fonte", "ultima": "última"}))]
    return "\n".join(md)


def write_report(db_path: Optional[str] = None, out: Path = OUT, nota: str = "") -> Path:
    if db_path is None:
        from src.data_hub.db import DataHubDB

        db_path = str(DataHubDB().db_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = collect(db_path)
    try:
        from src.data_hub.db import DataHubDB
        from src.data_hub.quality import audit

        data["qualidade"] = audit(DataHubDB(db_path=db_path))
    except Exception:
        pass
    out.write_text(render(data, nota=nota), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Gera docs/COBERTURA.md a partir do banco local.")
    ap.add_argument("--db", default=None)
    ap.add_argument("--saida", default=str(OUT))
    ap.add_argument("--nota", default="", help="aviso exibido no topo do relatório")
    a = ap.parse_args(argv)
    p = write_report(a.db, Path(a.saida), a.nota)
    print(f"Cobertura escrita em {p}")
    return 0


if __name__ == "__main__":
    try:  # lê o .env (OPENPLAY_PATH, CBF_SUMULAS_PATH, caminho do banco...) também quando rodado direto
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    raise SystemExit(main())
