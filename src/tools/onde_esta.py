"""Por que um jogador (não) aparece no Scout? `python -m src.tools.onde_esta "Mauro Coronel"`.

Mostra, sem inventar: se ele está no cadastro do Transfermarkt, quantos jogos/minutos temos dele (e de quais times e
competições), a data do último jogo e qual regra do Scout o deixa de fora."""

import sys
from datetime import date, timedelta

import pandas as pd

from src.data_hub.db import DataHubDB
from src.data_lake.ids import player_core


def main(name: str) -> None:
    db = DataHubDB()
    core = player_core(name)
    last = core.split()[-1] if core else name
    print(f"Procurando '{name}' (núcleo do nome: '{core}')\n")
    try:
        from src.squad import data as D

        tm = D.table("tm_jogadores")
        hit = tm[tm["nome"].astype(str).map(player_core) == core] if not tm.empty else tm
        print(f"Transfermarkt: {len(hit)} cadastro(s)" + (":" if len(hit) else " — o cadastro aberto (dcaribou) não cobre "
              "todas as ligas; sem ele o Scout só inclui quem jogou ≥ 450 min e ≥ 4 jogos nos últimos 180 dias."))
        for r in hit.head(5).to_dict("records"):
            print(f"  · {r.get('nome')} · {r.get('clube')} · nasc. {r.get('nascimento')} · valor {r.get('valor_mercado_eur')}")
    except Exception as exc:
        print(f"Transfermarkt: não consegui ler ({exc})")
    with db.connect() as conn:
        d = pd.read_sql_query(
            "SELECT p.player_name, p.team_name, p.minutes, m.match_date, m.competition_name FROM match_player_stats p "
            "JOIN matches m ON m.match_id = p.match_id WHERE p.player_name LIKE ? ORDER BY m.match_date DESC LIMIT 400",
            conn, params=[f"%{last}%"])
    d = d[d["player_name"].astype(str).map(player_core) == core]
    if d.empty:
        print("\nJogos com números por jogador na base: NENHUM. A liga dele ainda não foi baixada com detalhes (a FotMob "
              "preenche o histórico em segundo plano) ou o nome está escrito de outro jeito na fonte.")
        return
    since = (date.today() - timedelta(days=180)).isoformat()
    rec = d[d["match_date"].astype(str) >= since]
    print(f"\nJogos com números por jogador: {len(d)} · minutos: {int(pd.to_numeric(d['minutes'], errors='coerce').sum())}")
    print(f"Últimos 180 dias: {len(rec)} jogos · {int(pd.to_numeric(rec['minutes'], errors='coerce').sum())} min "
          "(regra do Scout para quem não tem cadastro: ≥ 4 jogos e ≥ 450 min)")
    print(f"Último jogo: {d['match_date'].iloc[0]} por {d['team_name'].iloc[0]} ({d['competition_name'].iloc[0]})")
    print("Times: " + ", ".join(d["team_name"].value_counts().head(4).index))
    print("Competições: " + ", ".join(d["competition_name"].value_counts().head(4).index))


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "Mauro Coronel")
