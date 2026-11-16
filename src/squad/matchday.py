"""
Inteligência de jogo (v36, rodada 3) — escalação provável, melhor escalação e leitura do adversário com dados REAIS
recentes: elenco atual e lesões (ESPN `espn_rosters`), escalações dos últimos jogos com posição e lado
(`match_lineups`), números por jogador (`match_player_stats`) e cartões (`match_timeline`).

Regras honestas:
* "Provável" = quem começou jogando nos últimos jogos, na posição em que jogou, tirando lesionados (ESPN) e suspensos
  (vermelho no último jogo). Não é notícia de treino: quando a escalação oficial sai (≈1 h antes), a ESPN publica.
* "Melhor" = nota do laboratório por jogador (titularidade recente + gols/assistências + valor de mercado quando há)
  com encaixe na posição; cada escolha vem com o PORQUÊ.
* Sem dado do jogador, ele não ganha nota inventada: entra com nota baixa e o motivo "sem jogos recentes".
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

ESPN_ROLE = {"G": "GK", "GK": "GK", "CD": "CB", "CD-L": "CB", "CD-R": "CB", "CB": "CB", "LB": "LB", "RB": "RB",
             "LWB": "LWB", "RWB": "RWB", "DM": "DM", "CDM": "DM", "CM": "CM", "CM-L": "CM", "CM-R": "CM", "AM": "AM",
             "AM-L": "LW", "AM-R": "RW", "LM": "LM", "RM": "RM", "LW": "LW", "RW": "RW", "F": "ST", "CF": "ST",
             "CF-L": "ST", "CF-R": "ST", "LF": "LW", "RF": "RW", "D": "CB", "M": "CM"}
SIDE = {"LB": "esquerda", "LWB": "esquerda", "LM": "esquerda", "LW": "esquerda", "RB": "direita", "RWB": "direita",
        "RM": "direita", "RW": "direita"}
SECTOR = {"GK": "gol", "CB": "defesa", "LB": "defesa", "RB": "defesa", "LWB": "defesa", "RWB": "defesa", "DM": "meio",
          "CM": "meio", "AM": "meio", "LM": "meio", "RM": "meio", "LW": "ataque", "RW": "ataque", "ST": "ataque"}


def _names_sql(names: Sequence[str]) -> Tuple[str, list]:
    return ",".join("?" * len(names)), list(names)


def roster(db, team_names: Sequence[str]) -> pd.DataFrame:
    """Elenco atual (ESPN) com lesões. Vazio se o clube ainda não teve o elenco baixado (`--only espn_elencos`)."""
    ph, ps = _names_sql(team_names)
    try:
        with db.connect() as conn:
            r = pd.read_sql_query(f"SELECT * FROM espn_rosters WHERE team IN ({ph})", conn, params=ps)
    except Exception:
        return pd.DataFrame()
    if r.empty:
        return r

    def inj(js):
        try:
            v = json.loads(js or "[]")
        except Exception:
            return ""
        if not v:
            return ""
        x = v[0]
        return (x.get("status") or x.get("type", {}).get("description") or "lesionado") + \
            (f" — {x['details']['type']}" if isinstance(x.get("details"), dict) and x["details"].get("type") else "")
    r = r.assign(lesao=r["injuries"].map(inj))
    return r


def recent_lineups(db, team_names: Sequence[str], n: int = 10) -> pd.DataFrame:
    """Escalações dos últimos `n` jogos do time que têm escalação (titulares e reservas, com posição e formação)."""
    ph, ps = _names_sql(team_names)
    q = (f"SELECT l.match_id, m.match_date AS data, m.home_team_name, m.away_team_name, m.home_score, m.away_score, "
         f"m.competition_name, l.team_name, l.player_name AS jogador, l.position AS pos, l.is_starter AS titular, l.formation "
         f"FROM match_lineups l JOIN matches m ON m.match_id = l.match_id WHERE l.team_name IN ({ph}) AND m.match_id IN ("
         f"SELECT DISTINCT l2.match_id FROM match_lineups l2 JOIN matches m2 ON m2.match_id = l2.match_id "
         f"WHERE l2.team_name IN ({ph}) ORDER BY m2.match_date DESC LIMIT {int(n)})")
    try:
        with db.connect() as conn:
            lu = pd.read_sql_query(q, conn, params=ps * 2)
    except Exception:
        return pd.DataFrame()
    if lu.empty:
        return lu
    lu["papel"] = lu["pos"].map(lambda p: ESPN_ROLE.get(str(p).upper()))
    lu["adversario"] = [a if h in team_names else h for h, a in zip(lu["home_team_name"], lu["away_team_name"])]
    return lu.sort_values("data", ascending=False)


def recent_player_stats(db, match_ids: Sequence[int], team_names: Sequence[str]) -> pd.DataFrame:
    if not match_ids:
        return pd.DataFrame()
    ph, ps = _names_sql([int(x) for x in match_ids])
    th, ts = _names_sql(team_names)
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(f"SELECT match_id, player_name, stats_json FROM match_player_stats "
                                  f"WHERE match_id IN ({ph}) AND team_name IN ({th})", conn, params=ps + ts)
    except Exception:
        return pd.DataFrame()
    rows = []
    for r in d.itertuples():
        try:
            s = json.loads(r.stats_json or "{}")
        except Exception:
            s = {}
        rows.append({"jogador": r.player_name, "gols": s.get("totalGoals", 0) or 0, "assistencias": s.get("goalAssists", 0) or 0,
                     "finalizacoes": s.get("totalShots", 0) or 0, "no_alvo": s.get("shotsOnTarget", 0) or 0,
                     "faltas": s.get("foulsCommitted", 0) or 0, "amarelos": s.get("yellowCards", 0) or 0,
                     "vermelhos": s.get("redCards", 0) or 0, "defesas": s.get("saves", 0) or 0})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).groupby("jogador", as_index=False).sum(numeric_only=True)


def suspensions(db, last_match_id: Optional[int], team_names: Sequence[str]) -> Dict[str, str]:
    """Vermelho no último jogo = suspenso no próximo (regra geral; acúmulo de amarelos não é calculado)."""
    if not last_match_id:
        return {}
    th, ts = _names_sql(team_names)
    try:
        with db.connect() as conn:
            r = conn.execute(f"SELECT player_name FROM match_timeline WHERE match_id = ? AND team_name IN ({th}) "
                             f"AND event_type LIKE '%Red%'", [int(last_match_id)] + ts).fetchall()
    except Exception:
        return {}
    return {p[0]: "suspenso (expulso no último jogo)" for p in r if p[0]}


def player_table(db, team_names: Sequence[str], n: int = 10, tm_values: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """
    Tabela por jogador do elenco: papel mais jogado e lado, titularidades nos últimos n jogos, gols/assistências,
    disponibilidade (lesão/suspensão) e nota 0–100 do laboratório com a base da conta.
    """
    ros = roster(db, team_names)
    lu = recent_lineups(db, team_names, n)
    games = lu["match_id"].drop_duplicates().tolist() if not lu.empty else []
    stats = recent_player_stats(db, games, team_names)
    last_id = games[0] if games else None
    susp = suspensions(db, last_id, team_names)
    names = set(ros["name"]) if not ros.empty else set()
    if not lu.empty:
        names |= set(lu["jogador"])
    starters = lu[lu["titular"] == 1] if not lu.empty else lu
    out = []
    for p in sorted(names):
        st = starters[starters["jogador"] == p] if not lu.empty else starters
        apps = lu[lu["jogador"] == p] if not lu.empty else lu
        roles = Counter([r for r in st["papel"].dropna()]) if len(st) else Counter()
        r_ros = ros[ros["name"] == p].iloc[0] if not ros.empty and (ros["name"] == p).any() else None
        role = roles.most_common(1)[0][0] if roles else ESPN_ROLE.get(str(r_ros["position"]).upper()) if r_ros is not None else None
        s = stats[stats["jogador"] == p].iloc[0] if not stats.empty and (stats["jogador"] == p).any() else None
        n_start = int(len(st))
        last5 = set(lu["match_id"].drop_duplicates().head(5)) if not lu.empty else set()
        start5 = int(st["match_id"].isin(last5).sum()) if len(st) else 0
        unavailable = (r_ros["lesao"] if r_ros is not None and r_ros["lesao"] else "") or susp.get(p, "")
        out.append({"nome": p, "papel": role, "lado": SIDE.get(role or "", ""), "setor": SECTOR.get(role or "", ""),
                    "titular_ultimos": n_start, "titular_ult5": start5, "jogos_relacionado": int(apps["match_id"].nunique()) if len(apps) else 0,
                    "gols": int(s["gols"]) if s is not None else 0, "assistencias": int(s["assistencias"]) if s is not None else 0,
                    "finalizacoes": int(s["finalizacoes"]) if s is not None else 0, "amarelos": int(s["amarelos"]) if s is not None else 0,
                    "indisponivel": unavailable, "no_elenco_atual": r_ros is not None if not ros.empty else None,
                    "idade": _age(r_ros["birth"]) if r_ros is not None else None,
                    "posicoes": dict(roles)})
    df = pd.DataFrame(out)
    if df.empty:
        return {"jogadores": df, "jogos": games, "formacao": None, "fonte_elenco": "—", "escalacoes": lu}
    if not ros.empty:                                   # saiu do clube (não está no elenco atual): fora
        df = df[df["no_elenco_atual"].fillna(True)]
    G = max(len(games), 1)
    val = {}
    if tm_values is not None and not tm_values.empty:
        from src.data_lake.ids import player_core

        tv = tm_values.assign(core=tm_values["nome"].map(player_core))
        val = dict(zip(tv["core"], pd.to_numeric(tv["valor_mercado_eur"], errors="coerce")))
        df["valor"] = df["nome"].map(lambda n: val.get(player_core(n)))
    else:
        df["valor"] = None
    vmax = pd.to_numeric(df["valor"], errors="coerce").max() if df["valor"].notna().any() else None
    notes = []
    for r in df.itertuples():
        start_part = 55 * min(r.titular_ultimos / G, 1.0)
        ga = (r.gols + 0.7 * r.assistencias) / G
        ga_part = 20 * min(ga / 0.6, 1.0)
        v_part = 25 * (float(r.valor) / vmax) ** 0.5 if vmax and r.valor and r.valor == r.valor else None
        if v_part is None:                              # sem valor de mercado: a titularidade pesa o resto
            score = (start_part + ga_part) / 75 * 100
            base = "titularidade + gols/assistências (sem valor de mercado)"
        else:
            score = start_part + ga_part + v_part
            base = "titularidade + gols/assistências + valor de mercado"
        notes.append((round(score), base))
    df["nota"] = [x[0] for x in notes]
    df["nota_base"] = [x[1] for x in notes]
    forms = Counter(lu.drop_duplicates("match_id").head(3)["formation"].dropna()) if not lu.empty else Counter()
    return {"jogadores": df.sort_values("nota", ascending=False).reset_index(drop=True), "jogos": games,
            "formacao": forms.most_common(1)[0][0] if forms else None, "escalacoes": lu,
            "fonte_elenco": "ESPN (elenco atual)" if not ros.empty else "escalações recentes"}


def _age(b) -> Optional[int]:
    try:
        d = date.fromisoformat(str(b)[:10])
        return int((date.today() - d).days // 365.25)
    except Exception:
        return None


def reasons(row: Dict[str, Any], slot_role: str, bench: pd.DataFrame, n_games: int) -> List[str]:
    """Por que este jogador foi escolhido para a vaga (frases curtas, cada uma com o número que a sustenta)."""
    from src.squad.formations import ROLE_PT

    out = []
    if row.get("titular_ult5"):
        out.append(f"titular em {row['titular_ult5']} dos últimos 5 jogos")
    pos = row.get("posicoes") or {}
    if pos.get(slot_role):
        out.append(f"jogou de {ROLE_PT.get(slot_role, slot_role).lower()} em {pos[slot_role]} jogo(s) recente(s)")
    elif row.get("papel") and row["papel"] != slot_role:
        out.append(f"improvisado: costuma jogar de {ROLE_PT.get(row['papel'], row['papel']).lower()}")
    if row.get("gols") or row.get("assistencias"):
        out.append(f"{row.get('gols', 0)} gol(s) e {row.get('assistencias', 0)} assistência(s) nos últimos {n_games} jogos")
    if row.get("lado") and slot_role in SIDE and SIDE[slot_role] == row["lado"]:
        out.append(f"atua pelo lado {row['lado']}")
    rivals = bench[(bench["papel"] == slot_role) & (bench["nome"] != row["nome"])] if not bench.empty else bench
    if len(rivals):
        alt = rivals.iloc[0]
        out.append(f"nota {row.get('nota')} contra {alt['nota']} de {alt['nome']} (opção na posição)")
    if not out:
        out.append("melhor opção disponível para a vaga (pouco dado recente)")
    return out


def sector_weaknesses(info: Dict[str, Any], team: str) -> List[Dict[str, Any]]:
    """
    Fragilidades por setor do adversário, tiradas dos dados reais recentes: setor com desfalques, posição sem dono
    (muitos titulares diferentes), setor que mais leva cartão e jogadores pendurados de cartão alto.
    """
    from src.squad.formations import ROLE_PT

    pl, lu = info["jogadores"], info["escalacoes"]
    out = []
    if pl is None or pl.empty:
        return out
    out_players = pl[pl["indisponivel"].astype(bool)]
    for setor, g in out_players.groupby("setor"):
        if setor:
            out.append({"setor": setor, "tipo": "desfalque", "texto": f"{team} tem desfalque no setor de {setor}: "
                        + ", ".join(f"{r.nome} ({r.indisponivel})" for r in g.itertuples()),
                        "peso": 3 * len(g)})
    if lu is not None and not lu.empty:
        st = lu[(lu["titular"] == 1) & lu["papel"].notna()]
        last5 = st[st["match_id"].isin(lu["match_id"].drop_duplicates().head(5))]
        for role, g in last5.groupby("papel"):
            k = g["jogador"].nunique()
            per_game = len(g) / max(g["match_id"].nunique(), 1)
            if per_game <= 1.2 and k >= 3:
                out.append({"setor": SECTOR.get(role, ""), "tipo": "instável",
                            "texto": f"a posição de {ROLE_PT.get(role, role).lower()} não tem dono: {k} titulares diferentes "
                                     f"nos últimos {g['match_id'].nunique()} jogos ({', '.join(g['jogador'].unique()[:4])})",
                            "peso": k})
    cards = pl[pl["amarelos"] >= 2]
    for r in cards.itertuples():
        out.append({"setor": r.setor, "tipo": "cartões", "peso": r.amarelos,
                    "texto": f"{r.nome} ({ROLE_PT.get(r.papel, r.papel or '').lower()}) levou {r.amarelos} amarelos nos "
                             f"últimos jogos: atacar o 1x1 em cima dele"})
    return sorted(out, key=lambda d: -d["peso"])


def threats(info: Dict[str, Any], top: int = 3) -> List[Dict[str, Any]]:
    pl = info["jogadores"]
    if pl is None or pl.empty:
        return []
    t = pl[~pl["indisponivel"].astype(bool)].assign(ga=lambda d: d["gols"] + d["assistencias"])
    t = t[t["ga"] > 0].sort_values(["ga", "finalizacoes"], ascending=False).head(top)
    return [{"nome": r.nome, "gols": r.gols, "assistencias": r.assistencias, "papel": r.papel, "lado": r.lado}
            for r in t.itertuples()]


def next_fixtures(db, team_names: Sequence[str], limit: int = 5) -> pd.DataFrame:
    ph, ps = _names_sql(team_names)
    try:
        with db.connect() as conn:
            return pd.read_sql_query(f"SELECT * FROM fixtures WHERE (home IN ({ph}) OR away IN ({ph})) "
                                     f"AND kickoff >= ? ORDER BY kickoff LIMIT {int(limit)}", conn,
                                     params=ps * 2 + [(date.today() - timedelta(days=1)).isoformat()])
    except Exception:
        return pd.DataFrame()


def xi_for(info: Dict[str, Any], formation: Optional[str], mode: str = "provavel") -> Tuple[List[Dict[str, Any]], str]:
    """
    XI para a formação (padrão: a mais usada nos últimos 3 jogos). mode="provavel": quem tem começado jogando;
    mode="melhor": maior nota do laboratório. Lesionados e suspensos ficam de fora. Cada vaga traz o PORQUÊ.
    """
    from src.squad.formations import FORMATIONS
    from src.squad.planner import best_xi

    pl = info["jogadores"]
    form = formation if formation in FORMATIONS else (info.get("formacao") if info.get("formacao") in FORMATIONS else "4-3-3")
    if pl is None or pl.empty:
        return best_xi(pd.DataFrame(), form), form
    ok = pl[~pl["indisponivel"].astype(bool) & pl["papel"].notna()].copy()
    if mode == "provavel":
        ok["nota_escolha"] = ok["titular_ult5"] * 18 + ok["titular_ultimos"] * 4 + ok["nota"] * 0.1
    else:
        ok["nota_escolha"] = ok["nota"]
    sq = ok.assign(nota=ok["nota_escolha"])
    xi = best_xi(sq, form)
    chosen = {p["jogador"] for p in xi if p.get("jogador")}
    bench = ok[~ok["nome"].isin(chosen)].sort_values("nota", ascending=False)
    byname = {r["nome"]: r for r in pl.to_dict("records")}
    G = len(info.get("jogos") or []) or 1
    for p in xi:
        r = byname.get(p.get("jogador"))
        if r:
            p["nota"] = r["nota"]
            p["porque"] = reasons(r, p["papel"], bench, G)
    return xi, form


def weakness_tips(weak: List[Dict[str, Any]], info: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fragilidades do RIVAL marcadas no NOSSO campo de ataque (atacamos para a direita): o lado esquerdo do rival é o
    nosso corredor direito, e vice-versa.
    """
    pl = info["jogadores"]
    roles = dict(zip(pl["nome"], pl["papel"])) if pl is not None and not pl.empty else {}
    out = []
    for i, w in enumerate(weak[:6], 1):
        role = next((roles[n] for n in roles if n in w["texto"]), None)
        side = SIDE.get(role or "", "")
        y = 76 if side == "esquerda" else 4 if side == "direita" else (26 if i % 2 else 54)
        x = {"defesa": 110, "gol": 116, "meio": 84, "ataque": 66}.get(w.get("setor") or "", 106)
        out.append({"x": x - (i // 2) * 3, "y": y, "marca": f"F{i}", "cor": "#F59E0B", "texto": "Fragilidade do rival: " + w["texto"]})
    return out
