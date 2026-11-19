"""
Rodada 16 — Wikidata (base aberta, licença CC0) como fonte complementar de DADOS DE CADASTRO de jogadores:
data de nascimento, altura e nacionalidade de quem não está no Transfermarkt aberto nem nos elencos da FotMob
(Série B/C, ligas sul-americanas). Só aceita quando o nome casa com UM único jogador de futebol na Wikidata — homônimo
fica de fora (não chuta).

    python -m src.data_hub.sources.wikidata --limite 1500     # busca quem está sem idade nas avaliações
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Dict, Iterable, List

import pandas as pd

ENDPOINT = "https://query.wikidata.org/sparql"
DDL = ("CREATE TABLE IF NOT EXISTS wikidata_players (core TEXT PRIMARY KEY, name TEXT, qid TEXT, birth TEXT, "
       "height_cm REAL, nationality TEXT, status TEXT, fetched_at TEXT)")
HEADERS = {"Accept": "application/sparql-results+json", "User-Agent": "tactical-intelligence-lab/1.0 (uso pessoal)"}


def _query(names: List[str]) -> List[Dict[str, str]]:
    from src.data_hub import net

    vals = " ".join(json.dumps(n) + "@pt " + json.dumps(n) + "@en " + json.dumps(n) + "@es" for n in names)
    q = f"""SELECT ?label ?p ?birth ?height ?natLabel WHERE {{
              VALUES ?label {{ {vals} }}
              ?p rdfs:label ?label; wdt:P106 wd:Q937857.
              OPTIONAL {{ ?p wdt:P569 ?birth }} OPTIONAL {{ ?p wdt:P2048 ?height }}
              OPTIONAL {{ ?p wdt:P1532 ?nat. ?nat rdfs:label ?natLabel FILTER(lang(?natLabel) = "en") }}
            }}"""
    r = net.get(ENDPOINT, params={"query": q, "format": "json"}, headers=HEADERS, timeout=40)
    r.raise_for_status()
    out = []
    for b in r.json().get("results", {}).get("bindings", []):
        out.append({k: v.get("value") for k, v in b.items()})
    return out


def enrich(db, names: Iterable[str], batch: int = 40, pause_s: float = 1.0, progress=None) -> Dict[str, int]:
    from src.data_lake.ids import player_core

    say = progress or (lambda m: None)
    with db.connect() as conn:
        conn.execute(DDL)
        done = {r[0] for r in conn.execute("SELECT core FROM wikidata_players").fetchall()}
    todo = [n for n in dict.fromkeys(str(x) for x in names if x) if player_core(n) not in done]
    tot = {"consultados": 0, "achados": 0, "ambiguos": 0, "sem_registro": 0}
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        try:
            rows = _query(part)
        except Exception as exc:                          # sem rede / limite: para e continua depois
            say(f"  wikidata: parou ({exc}); rode de novo para continuar")
            break
        by_label: Dict[str, List[Dict[str, str]]] = {}
        for r in rows:
            by_label.setdefault(r.get("label", ""), []).append(r)
        recs = []
        for n in part:
            hits = by_label.get(n, [])
            qids = {h.get("p") for h in hits}
            core = player_core(n)
            if len(qids) == 1:
                h = hits[0]
                height = h.get("height")
                try:
                    height = float(height)
                    height = height * 100 if height < 3 else height       # metros → cm
                except (TypeError, ValueError):
                    height = None
                recs.append((core, n, h.get("p"), (h.get("birth") or "")[:10] or None, height, h.get("natLabel"),
                             "ok", time.strftime("%Y-%m-%d")))
                tot["achados"] += 1
            else:
                status = "homonimo" if len(qids) > 1 else "sem_registro"
                tot["ambiguos" if len(qids) > 1 else "sem_registro"] += 1
                recs.append((core, n, None, None, None, None, status, time.strftime("%Y-%m-%d")))
        with db.connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO wikidata_players VALUES (?,?,?,?,?,?,?,?)", recs)
        tot["consultados"] += len(part)
        say(f"  wikidata: {tot['consultados']}/{len(todo)} · achados {tot['achados']} · homônimos {tot['ambiguos']}")
        time.sleep(pause_s)
    return tot


def ages(db) -> Dict[str, float]:
    try:
        with db.connect() as conn:
            d = pd.read_sql_query("SELECT core, birth FROM wikidata_players WHERE status = 'ok' AND birth IS NOT NULL", conn)
    except Exception:
        return {}
    born = pd.to_datetime(d["birth"], errors="coerce")
    return dict(zip(d["core"], ((pd.Timestamp.today() - born).dt.days / 365.25).round(1)))


def main() -> None:
    from src.data_hub.db import DataHubDB
    from src.scout import evaluation as EV

    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=1500)
    a = ap.parse_args()
    db = DataHubDB()
    res = EV.load()
    if not res or res["jogadores"].empty:
        print("Rode antes: python -m src.scout.evaluation")
        return
    ev = res["jogadores"]
    names = ev.loc[ev["idade"].isna() & (ev["minutes"] >= 450)].sort_values("minutes", ascending=False)["player_name"]
    print(enrich(db, names.head(a.limite).tolist(), progress=print))


if __name__ == "__main__":
    main()
