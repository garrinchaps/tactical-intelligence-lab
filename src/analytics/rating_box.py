"""
Avaliação 3.0 a partir das ESTATÍSTICAS por jogador (rodada 5) — para jogos sem lances com coordenadas
(Brasileirão, Série B, Libertadores…), usando os números por jogador da FotMob.

Mesmo motor (`rating_v2.evaluate`: dimensões, pesos por função, percentil → nota, encolhimento por minutos,
confiança, desempenho-base + ajuste decisivo, mas com:
  * indicadores que a fonte de estatísticas realmente traz (xG, xA, chances criadas, passes no terço final,
    desarmes, interceptações, recuperações, duelos, perdas…). O que ela não traz (xT, quebra de linhas, entre linhas,
    pressão) fica de fora — a dimensão sem dado NÃO vira zero, só reduz a cobertura e a confiança;
  * régua PRÓPRIA: os pares vêm de outras atuações com estatísticas da mesma fonte (definições iguais). A régua dos
    lances (StatsBomb/OpenPlay) não se mistura com esta.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REF_PATH = Path("data/processed/rating_ref_box.parquet")
ROLE_TO_FUNCAO = {"GK": "goleiro", "CB": "zagueiro", "LB": "lateral", "RB": "lateral", "LWB": "lateral", "RWB": "lateral",
                  "DM": "volante", "CM": "meia central", "AM": "meia ofensivo", "LM": "ponta", "RM": "ponta",
                  "LW": "ponta", "RW": "ponta", "ST": "centroavante"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def indicators(rows: pd.DataFrame, positions: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    `rows`: match_player_stats (player_name, team_name, minutes, stats_json) de UM ou vários jogos.
    `positions`: jogador → papel exato da escalação (GK, CB, RW…). Sem posição conhecida, o jogador fica sem nota.
    """
    out = []
    for r in rows.itertuples():
        try:
            s = json.loads(r.stats_json or "{}")
        except Exception:
            continue
        m = _num(s.get("minutes", r.minutes))
        if not m or m != m:
            continue
        role = (positions or {}).get(r.player_name)
        fun = ROLE_TO_FUNCAO.get(role or "")
        if not fun and r.position == "GK":
            fun = "goleiro"
        if not fun:
            continue
        p90 = lambda k: _num(s.get(k)) * 90 / m if s.get(k) is not None else None
        pct = lambda k: (100 * _num(s[k]) / _num(s[k + "_total"])) if s.get(k) is not None and _num(s.get(k + "_total")) else None
        touches = _num(s.get("touches"))
        row = {"jogador": r.player_name, "equipe": r.team_name, "funcao": fun,
               "role_mix": {fun: 1.0}, "minutos": m,
               "gols": int(_num(s.get("totalGoals")) or 0) if s.get("totalGoals") is not None else 0,
               "gols_penalti": _num(s.get("penalty_goals")) if s.get("penalty_goals") is not None else None,
               "assistencias": int(_num(s.get("goalAssists")) or 0) if s.get("goalAssists") is not None else 0,
               "xg": s.get("xg"), "xa": s.get("xa"), "amarelos": s.get("yellow_cards"),
               "vermelhos": int(_num(s.get("red_cards")) or 0) if s.get("red_cards") is not None else None,
               "erros_que_viraram_chance": (_num(s.get("errors_led_to_goal")) or 0) if s.get("errors_led_to_goal") is not None else None}
        if fun == "goleiro":
            saves, conc = _num(s.get("saves")), _num(s.get("goals_conceded"))
            row.update({"defesas90": p90("saves"), "gols_evitados": s.get("goals_prevented"),
                        "pct_defesas": 100 * saves / (saves + conc) if saves == saves and conc == conc and saves + conc > 0 else None,
                        "saidas_aereas90": p90("keeper_high_claim"), "gk_passe_pct": pct("accurate_passes"),
                        "gk_longos_pct": pct("long_balls_accurate"), "gk_acoes_fora_area90": p90("keeper_sweeper"),
                        "gk_erros": s.get("errors_led_to_goal")})
        else:
            row.update({"gols_np90": p90("totalGoals"), "xg90": p90("xg"), "no_alvo90": p90("shotsOnTarget"),
                        "assist90": p90("goalAssists"), "xa90": p90("xa"), "decisivos90": p90("chances_created"),
                        "cruz_certos90": p90("accurate_crosses"), "quebra_linha90": p90("line_breaking_passes"), "dribles90": p90("dribbles_succeeded"),
                        "entradas_terco90": p90("passes_into_final_third"), "entradas_area90": p90("touches_opp_box"),
                        "desarmes_ganhos90": p90("matchstats.headers.tackles"), "intercept90": p90("interceptions"),
                        "cortes90": p90("clearances"), "bloqueios90": p90("shot_blocks"), "recup90": p90("recoveries"),
                        "aereos_ganhos90": p90("aerials_won"), "driblado90": p90("dribbled_past"),
                        "passe_pct": pct("accurate_passes"),
                        "acoes_defensivas90": p90("defensive_actions"),
                        "sprints90": p90("sprints"),
                        "perdas_por_toque": _num(s.get("dispossessed")) / touches if s.get("dispossessed") is not None and touches else None,
                        "faltas90": p90("foulsCommitted")})
        out.append(row)
    return pd.DataFrame(out)


def _positions(db, match_ids: List[int]) -> Dict[int, Dict[str, str]]:
    from src.squad.positions import classify
    from src.data_hub.registry import source_from_internal_id

    if not match_ids:
        return {}
    ph = ",".join("?" * len(match_ids))
    with db.connect() as conn:
        lu = pd.read_sql_query(f"SELECT match_id, player_name, position FROM match_lineups WHERE match_id IN ({ph})",
                               conn, params=[int(m) for m in match_ids])
    out: Dict[int, Dict[str, str]] = {}
    for r in lu.itertuples():
        role, ok = classify(r.position, source_from_internal_id(r.match_id))
        if ok:
            out.setdefault(int(r.match_id), {})[r.player_name] = role
    return out


def build_reference(db, limit: int = 400, path: Path = REF_PATH) -> int:
    """Régua: atuações (≥ 30 min) dos jogos mais recentes com estatísticas por jogador da FotMob."""
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT s.match_id FROM match_player_stats s JOIN matches m ON m.match_id = s.match_id "
            "WHERE m.data_source = 'fotmob' ORDER BY m.match_date DESC LIMIT ?", (int(limit),)).fetchall()]
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        rows = pd.read_sql_query(f"SELECT match_id, team_name, player_name, position, minutes, stats_json FROM "
                                 f"match_player_stats WHERE match_id IN ({ph})", conn, params=ids)
    pos = _positions(db, ids)
    parts = [indicators(g, pos.get(int(mid), {})) for mid, g in rows.groupby("match_id")]
    ref = pd.concat([p for p in parts if not p.empty], ignore_index=True) if parts else pd.DataFrame()
    if ref.empty:
        return 0
    ref = ref[ref["minutos"] >= 30]
    path.parent.mkdir(parents=True, exist_ok=True)
    ref.to_parquet(path, index=False)
    return len(ref)


def reference(path: Path = REF_PATH) -> pd.DataFrame:
    try:
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def match_ratings(db, match_id: int, ref: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Nota 3.0 (por estatísticas) dos jogadores de um jogo. Vazio se o jogo não tem números por jogador."""
    from src.analytics.rating_v2 import evaluate

    with db.connect() as conn:
        rows = pd.read_sql_query("SELECT match_id, team_name, player_name, position, minutes, stats_json FROM "
                                 "match_player_stats WHERE match_id = ?", conn, params=(int(match_id),))
    if rows.empty:
        return pd.DataFrame()
    ind = indicators(rows, _positions(db, [int(match_id)]).get(int(match_id), {}))
    if ind.empty:
        return ind
    pool = ref if ref is not None else reference()
    pool = pd.concat([pool, ind], ignore_index=True) if not pool.empty else ind
    out = []
    for r in ind.to_dict("records"):
        r = {k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()}   # NaN = sem dado (não é zero)
        ev = evaluate(r, pool)
        out.append({"jogador": r["jogador"], "equipe": r["equipe"], "funcao": r["funcao"], "minutos": r["minutos"],
                    "gols": r["gols"], "assistencias": r["assistencias"], "desempenho": ev["desempenho"],
                    "nota": ev["nota"], "nota_final": ev["nota_final"], "impacto": ev["impacto"],
                    "confianca": ev["confianca"], "confianca_pct": ev["confianca_pct"],
                    "classificacao": ev["classificacao"], "pares": ev["pares"], "_detalhe": ev})
    return pd.DataFrame(out).sort_values("nota", ascending=False, na_position="last").reset_index(drop=True)


def player_form(db, names: List[str], n: int = 10, ref: Optional[pd.DataFrame] = None,
                team_names: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Nota 3.0 (por estatísticas) do jogador nos últimos `n` jogos com números por jogador — base da FASE (últimos 5),
    da QUALIDADE (média do período) e da REGULARIDADE (desvio entre jogos). Sem jogos assim, volta vazio.
    Nunca só pelo nome: usa o id do atleta na FotMob; sem id, fica no clube informado ou no time do jogo mais recente.
    """
    if not names:
        return pd.DataFrame()
    ph = ",".join("?" * len(names))
    with db.connect() as conn:
        cand = pd.read_sql_query(
            f"SELECT s.match_id, s.team_name, s.stats_json, m.match_date, m.home_team_name, m.away_team_name, m.home_score, "
            f"m.away_score FROM match_player_stats s JOIN matches m ON m.match_id = s.match_id WHERE s.player_name IN ({ph}) "
            f"AND m.data_source = 'fotmob' ORDER BY m.match_date DESC LIMIT 200", conn, params=list(names))
    if cand.empty:
        return pd.DataFrame()
    cand["fid"] = [(json.loads(js or "{}") or {}).get("fotmob_id") for js in cand["stats_json"]]
    if team_names:
        tn = set(team_names)
        c2 = cand[cand["team_name"].isin(tn)]
        cand = c2 if not c2.empty else cand.iloc[0:0]
    if cand.empty:
        return pd.DataFrame()
    top = cand.iloc[0]
    if top["fid"] is not None:
        cand = cand[cand["fid"] == top["fid"]]
    else:
        cand = cand[cand["team_name"] == top["team_name"]]
    ids = cand.head(int(n))[["match_id", "match_date", "home_team_name", "away_team_name", "home_score", "away_score"]] \
        .itertuples(index=False, name=None)
    pool = ref if ref is not None else reference()
    rows = []
    for mid, d, h, a, hs, as_ in ids:
        r = match_ratings(db, mid, pool)
        if r.empty:
            continue
        me = r[r["jogador"].isin(names)]
        if me.empty or me.iloc[0]["desempenho"] is None or pd.isna(me.iloc[0]["desempenho"]):
            continue
        x = me.iloc[0]
        dims = x["_detalhe"]["dimensoes"]
        rows.append({"match_id": mid, "data": d, "jogo": f"{h} {hs} x {as_} {a}", "funcao": x["funcao"], "minutos": x["minutos"],
                     "nota": x["nota"], "nota_final": x["nota_final"], "desempenho": x["desempenho"],
                     "impacto": x["impacto"], "confianca_pct": x["confianca_pct"], **dims})
    return pd.DataFrame(rows)


def main() -> None:
    import argparse

    from src.data_hub.db import DataHubDB

    ap = argparse.ArgumentParser(description="Régua da nota 3.0 por estatísticas (FotMob).")
    ap.add_argument("--referencia", type=int, default=400, help="quantos jogos recentes com números por jogador usar")
    a = ap.parse_args()
    n = build_reference(DataHubDB(), a.referencia)
    print(f"Régua montada com {n} atuações (≥ 30 min)." if n else
          "Sem jogos da FotMob com números por jogador. Rode antes: python -m src.data_hub.sync --only fotmob_jogos")


if __name__ == "__main__":
    main()
