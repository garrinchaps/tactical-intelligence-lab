"""
Cache local de escudos (v36, item B5).

    python -m src.tools.cache_crests              baixa os escudos que faltam (Brasil A-D, Europa top-5, Libertadores, UCL)
    python -m src.tools.cache_crests --limite 50  só os 50 primeiros (teste)

Os arquivos ficam em data/crests/<nome>.png (fora do Git). A interface usa o arquivo local quando existe; senão,
o endereço remoto; e, se nada carregar, o escudo gerado com as iniciais nas cores do clube — nunca quebra a página.
Baixa cada escudo UMA vez (arquivos já presentes são pulados) e com 1 pedido por segundo.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import List

CREST_DIR = Path("data/crests")
PRIORITY = re.compile(r"brasileir|serie [abcd]\b|série [abcd]\b|campeonato brasileiro|premier league|la liga|laliga|"
                      r"bundesliga|serie a\b|ligue 1|libertadores|champions league", re.I)


# "Premier League", "Serie A" etc. existem em ligas pequenas: fora do escopo (Azerbaijão, Chipre e similares)
EXCLUDE = re.compile(r"azerbaij|cyprus|chipre|kazakh|armenia|belarus|ukrain|russia|egypt|bangladesh|hong kong|"
                     r"welsh|kenya|ghana|nigeria|uganda|zambia|tanzania|jamaica|malta|gibraltar|ecuador serie|"
                     r"women|feminin|u2[0-3]|u1[7-9]", re.I)


def local_path(name: str) -> Path:
    from src.data_lake.ids import team_core

    return CREST_DIR / (re.sub(r"[^a-z0-9]+", "_", team_core(name)).strip("_") + ".png")


def priority_teams(catalog) -> List[str]:
    comp = catalog["competition_name"].astype(str)
    c = catalog[comp.str.contains(PRIORITY) & ~comp.str.contains(EXCLUDE)]
    c = c[c["match_date"].astype(str) >= "2023-01-01"]
    names = sorted(set(c["home_team_name"].dropna()) | set(c["away_team_name"].dropna()))
    return names


def main() -> None:
    ap = argparse.ArgumentParser(description="Baixa os escudos das competições prioritárias para data/crests.")
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()
    from src.data_hub import net
    from src.data_hub.service import MatchDataService
    from src.ui.crests import crest_url

    import pandas as pd

    with MatchDataService().db.connect() as conn:            # só as colunas necessárias (a base tem ~300 mil jogos)
        cat = pd.read_sql_query("SELECT home_team_name, away_team_name, competition_name, match_date FROM matches "
                                "WHERE match_date >= '2023-01-01'", conn)
    CREST_DIR.mkdir(parents=True, exist_ok=True)
    teams = priority_teams(cat)
    if args.limite:
        teams = teams[:args.limite]
    ok = skip = fail = 0
    for name in teams:
        dest = local_path(name)
        url = crest_url(name, use_local=False)
        if dest.exists() or url.startswith("data:"):
            skip += 1
            continue
        try:
            r = net.get(url, headers={"User-Agent": "TacticalIntelligenceLab/1.0 (uso pessoal)"}, timeout=15,
                        source="crests")
            if r.status_code == 200 and len(r.content) > 200:
                dest.write_bytes(r.content)
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        time.sleep(1.0)
    print(f"escudos: {ok} baixados, {skip} já existiam ou sem endereço (usam o gerado), {fail} falharam "
          f"(usam o gerado) — {len(teams)} clubes prioritários")


if __name__ == "__main__":
    main()
