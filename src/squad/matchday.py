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
         f"WHERE l2.team_name IN ({ph}) ORDER BY m2.match_date DESC LIMIT {int(n) * 2})")
    try:
        with db.connect() as conn:
            lu = pd.read_sql_query(q, conn, params=ps * 2)
    except Exception:
        return pd.DataFrame()
    if lu.empty:
        return lu
    # rodada 5: posição PRECISA × genérica por fonte, LM/RM da ESPN pelo desenho, mesmo jogo de 2 fontes conta 1 vez
    from src.squad.positions import resolve_lineups

    lu = resolve_lineups(lu)
    keep = lu.drop_duplicates("match_id").sort_values("data", ascending=False)["match_id"].head(int(n))
    lu = lu[lu["match_id"].isin(set(keep))].copy()
    lu["adversario"] = [a if h in team_names else h for h, a in zip(lu["home_team_name"], lu["away_team_name"])]
    return lu.sort_values("data", ascending=False)


def _fold(name: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return " ".join(t.replace("-", " ").replace(".", " ").split())


def canonical_names(names: Sequence[str], roster_names: Sequence[str]) -> Dict[str, str]:
    """
    Nome de cada fonte → um nome só. Regras (nunca junta dois atletas diferentes por palpite):
      1. igual sem acento/maiúscula ("Konate" = "Konaté", "Van Dijk" = "van Dijk");
      2. todas as palavras de um estão no outro e só existe UM candidato ("Alisson" ⊂ "Alisson Becker");
      3. inicial + sobrenome ("V. van Dijk") com um único candidato.
    Preferência pelo nome do elenco atual (ESPN); sem elenco, pelo nome mais longo entre as fontes.
    """
    pool = list(dict.fromkeys([n for n in roster_names if n] + [n for n in names if n]))
    folded = {n: _fold(n) for n in pool}
    out: Dict[str, str] = {}
    targets = list(dict.fromkeys(roster_names)) or sorted(set(names), key=lambda n: -len(n))
    tok = {t: set(folded.get(t, _fold(t)).split()) for t in targets}
    for n in names:
        f = folded[n]
        same = [t for t in targets if folded.get(t, _fold(t)) == f]
        if same:
            out[n] = same[0]
            continue
        a = set(f.split())
        sub = [t for t in targets if t != n and tok[t] and (a <= tok[t] or tok[t] <= a) and len(a & tok[t]) >= 1
               and (len(a) > 1 or len(tok[t]) > 1)]
        if len(sub) == 1:
            out[n] = sub[0]
            continue
        parts = f.split()
        if len(parts) >= 2 and len(parts[0]) == 1:
            ini = [t for t in targets if folded.get(t, _fold(t)).split()[-1:] == parts[-1:] and
                   folded.get(t, _fold(t)).startswith(parts[0])]
            if len(ini) == 1:
                out[n] = ini[0]
    return out


def recent_player_stats(db, match_ids: Sequence[int], team_names: Sequence[str],
                        canon: Optional[Dict[str, str]] = None) -> pd.DataFrame:
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
    df = pd.DataFrame(rows)
    if canon is not None:
        extra = canonical_names([n for n in df["jogador"].unique() if n not in canon], list(dict.fromkeys(canon.values())))
        m = {**canon, **extra}
        df["jogador"] = df["jogador"].map(lambda x: m.get(x, x))
    return df.groupby("jogador", as_index=False).sum(numeric_only=True)


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


def player_table(db, team_names: Sequence[str], n: int = 10, tm_values: Optional[pd.DataFrame] = None,
                 season_games: int = 40) -> Dict[str, Any]:
    """
    Tabela por jogador com conceitos SEPARADOS (v36, avaliação 2.0):
      qualidade (0–10)  = temporada: fatia de jogos como titular + gols/assistências por jogo (+ valor de mercado, só
                          como desempate, quando existe) — sem lances do Brasileirão nas fontes abertas, é o melhor sinal;
      fase (0–10)       = últimos 5 jogos (titularidade + produção);
      prob_titular (%)  = 50% temporada + 35% últimos 5 + 15% último jogo — quem é titular da temporada e só não jogou o
                          último (ex.: poupado) continua provável;
      disponivel        = sem lesão (ESPN) e sem suspensão (vermelho no último jogo ou acúmulo de amarelos);
      posicoes          = todas as posições em que começou jogando, com a frequência (base do encaixe).
    """
    ros = roster(db, team_names)
    lu = recent_lineups(db, team_names, season_games)
    canon: Dict[str, str] = {}
    if not lu.empty:
        # o mesmo atleta escrito de jeitos diferentes nas fontes ("Ibrahima Konate" × "Ibrahima Konaté", "Alisson" ×
        # "Alisson Becker", "Virgil Van Dijk" × "Virgil van Dijk") vira UM nome — o do elenco atual quando existe
        canon = canonical_names(lu["jogador"].dropna().unique().tolist(), ros["name"].tolist() if not ros.empty else [])
        lu = lu.assign(jogador=lu["jogador"].map(lambda x: canon.get(x, x)))
    games = lu["match_id"].drop_duplicates().tolist() if not lu.empty else []
    if not lu.empty:                                   # temporada = últimos 365 dias a partir do jogo mais recente
        d = pd.to_datetime(lu["data"], errors="coerce")
        lu = lu[d >= d.max() - pd.Timedelta(days=365)]
        games = lu["match_id"].drop_duplicates().tolist()
    recent = games[:max(n, 5)]
    last5 = set(games[:5])
    stats_season = recent_player_stats(db, games, team_names, canon)
    stats_5 = recent_player_stats(db, list(last5), team_names, canon)
    last_id = games[0] if games else None
    susp = suspensions(db, last_id, team_names)
    susp.update(yellow_suspensions(db, games, team_names))
    names = set(ros["name"]) if not ros.empty else set()
    if not lu.empty:
        names |= set(lu["jogador"])
    starters = lu[lu["titular"] == 1] if not lu.empty else lu
    from src.data_lake.ids import player_core
    from src.squad.formations import natural_role
    from src.squad.positions import player_roles

    tm_roles: Dict[str, str] = {}
    if tm_values is not None and not tm_values.empty and ("funcao" in tm_values or "posicao" in tm_values):
        for r in tm_values.itertuples():
            nr = natural_role(getattr(r, "funcao", ""), getattr(r, "posicao", ""))
            if nr:
                tm_roles.setdefault(player_core(r.nome), nr)
    G, G5 = max(len(games), 1), max(len(last5), 1)
    out = []
    for p in sorted(names):
        st = starters[starters["jogador"] == p] if not lu.empty else starters
        apps = lu[lu["jogador"] == p] if not lu.empty else lu
        r_ros = ros[ros["name"] == p].iloc[0] if not ros.empty and (ros["name"] == p).any() else None
        roles, role, pos_src = player_roles(st, tm_roles.get(player_core(p)), r_ros["position"] if r_ros is not None else None)
        ss = stats_season[stats_season["jogador"] == p].iloc[0] if not stats_season.empty and (stats_season["jogador"] == p).any() else None
        s5 = stats_5[stats_5["jogador"] == p].iloc[0] if not stats_5.empty and (stats_5["jogador"] == p).any() else None
        n_start = int(len(st))
        start5 = int(st["match_id"].isin(last5).sum()) if len(st) else 0
        started_last = bool(len(st) and last_id in set(st["match_id"]))
        unavailable = (r_ros["lesao"] if r_ros is not None and r_ros["lesao"] else "") or susp.get(p, "")
        g, a = (int(ss["gols"]), int(ss["assistencias"])) if ss is not None else (0, 0)
        g5, a5 = (int(s5["gols"]), int(s5["assistencias"])) if s5 is not None else (0, 0)
        share = n_start / G
        prob = 0.5 * share + 0.35 * start5 / G5 + 0.15 * float(started_last)
        out.append({"nome": p, "papel": role, "lado": SIDE.get(role or "", ""), "setor": SECTOR.get(role or "", "") or {"D?": "defesa", "M?": "meio", "F?": "ataque"}.get(role or "", ""),
                    "titular_temporada": n_start, "jogos_temporada": G, "titular_ult5": start5, "titular_ultimos": n_start,
                    "comecou_ultimo": started_last, "jogos_relacionado": int(apps["match_id"].nunique()) if len(apps) else 0,
                    "gols": g, "assistencias": a, "gols_ult5": g5, "assist_ult5": a5,
                    "finalizacoes": int(ss["finalizacoes"]) if ss is not None else 0,
                    "amarelos": int(ss["amarelos"]) if ss is not None else 0,
                    "indisponivel": unavailable, "no_elenco_atual": r_ros is not None if not ros.empty else None,
                    "idade": _age(r_ros["birth"]) if r_ros is not None else None,
                    "posicoes": dict(roles), "origem_posicao": pos_src, "prob_titular": round(100 * (0 if unavailable else prob))})
    df = pd.DataFrame(out)
    if df.empty:
        return {"jogadores": df, "jogos": games, "formacao": None, "fonte_elenco": "—", "escalacoes": lu}
    df["duvida"] = ""
    if not ros.empty:
        # fora da lista de elenco da ESPN: só sai se NÃO jogou pelo clube nos últimos 60 dias (a lista da ESPN às vezes
        # omite lesionados de longo prazo ou atualiza atrasada). Quem jogou recentemente fica como DÚVIDA, com o motivo.
        last_play = lu.groupby("jogador")["data"].max() if not lu.empty else pd.Series(dtype=str)
        newest = pd.to_datetime(lu["data"], errors="coerce").max() if not lu.empty else None
        # referência = o mais novo entre o último jogo com escalação e a data do elenco: com escalações antigas na base
        # (outra fonte, temporada passada), quem não está no elenco ATUAL não volta a ser escalado
        ros_day = pd.to_datetime(ros.get("fetched_at"), errors="coerce").max() if "fetched_at" in ros else None
        ros_day = ros_day.tz_localize(None) if ros_day is not None and pd.notna(ros_day) and ros_day.tzinfo else ros_day
        ref_day = max([x for x in (newest, ros_day) if x is not None and pd.notna(x)], default=None)
        recent_cut = (ref_day - pd.Timedelta(days=60)) if ref_day is not None else None
        keep = []
        for r in df.itertuples():
            if r.no_elenco_atual is not False:
                keep.append(True)
                continue
            lp = pd.to_datetime(last_play.get(r.nome), errors="coerce")
            keep.append(bool(recent_cut is not None and pd.notna(lp) and lp >= recent_cut))
        df = df[keep].copy()
        miss = df["no_elenco_atual"] == False  # noqa: E712
        df.loc[miss, "duvida"] = "não aparece na lista de elenco da ESPN (pode estar lesionado ou a lista desatualizada)"
    if not lu.empty:                                    # sumiu dos últimos jogos sem lesão informada → dúvida
        recent_ids = games[:3]
        for i, r in df.iterrows():
            if r["titular_temporada"] / G >= 0.5 and not r["indisponivel"]:
                played = lu[(lu["jogador"] == r["nome"]) & lu["match_id"].isin(recent_ids)]
                if played.empty and len(recent_ids) == 3:
                    df.at[i, "duvida"] = (df.at[i, "duvida"] + "; " if df.at[i, "duvida"] else "") + \
                        "fora dos 3 últimos jogos sem motivo informado"
    # dúvida não zera a chance de jogar: reduz pela metade (a decisão final é sua)
    df.loc[df["duvida"] != "", "prob_titular"] = (df.loc[df["duvida"] != "", "prob_titular"] * 0.5).round()
    df["valor"] = None
    if tm_values is not None and not tm_values.empty:
        from src.data_lake.ids import player_core

        tv = tm_values.assign(core=tm_values["nome"].map(player_core))
        val = dict(zip(tv["core"], pd.to_numeric(tv["valor_mercado_eur"], errors="coerce")))
        df["valor"] = df["nome"].map(lambda nm: val.get(player_core(nm)))
    vmax = pd.to_numeric(df["valor"], errors="coerce").max() if df["valor"].notna().any() else None
    try:
        dest = player_highlights(db, games, team_names, {r.nome: r.papel for r in df.itertuples()
                                                         if isinstance(r.papel, str) and not r.papel.endswith("?")}, canon)
    except Exception:
        dest = {}
    q, f, base = [], [], []
    for r in df.itertuples():
        share = r.titular_temporada / G
        ga = (r.gols + 0.7 * r.assistencias) / G
        v = (float(r.valor) / vmax) ** 0.5 if vmax and r.valor and r.valor == r.valor else None
        parts = [(0.6, share), (0.3, min(ga / 0.5, 1.0))] + ([(0.1, v)] if v is not None else [])
        base_quality = 10 * sum(w * x for w, x in parts) / sum(w for w, _ in parts)
        stat = dest.get(r.nome) or {}
        stat_score, stat_conf, stat_peers = stat.get("desempenho"), stat.get("confianca_pct"), stat.get("pares", 0)
        # A régua compartilhada só influencia a escolha quando a amostra de pares e a confiança são adequadas.
        if stat_score is not None and pd.notna(stat_score) and (stat_conf or 0) >= 50 and (stat_peers or 0) >= 20:
            q.append(round(0.65 * base_quality + 0.35 * float(stat_score), 1))
            base.append("titularidade/produção + nota 2.0 por estatísticas da mesma função"
                        + (" + valor de mercado (desempate)" if v is not None else ""))
        else:
            q.append(round(base_quality, 1))
            base.append("titularidade e gols/assistências da temporada"
                        + (" + valor de mercado (desempate)" if v is not None else ""))
        ga5 = (r.gols_ult5 + 0.7 * r.assist_ult5) / G5
        f.append(round(10 * (0.6 * r.titular_ult5 / G5 + 0.4 * min(ga5 / 0.5, 1.0)), 1))
    df["qualidade"], df["fase"], df["nota_base"] = q, f, base
    df["nota"] = (df["qualidade"] * 10).round()                  # compatibilidade com as telas antigas (0–100)
    forms = Counter(lu.drop_duplicates("match_id").head(3)["formation"].dropna()) if not lu.empty else Counter()
    newest = pd.to_datetime(lu["data"], errors="coerce").max() if not lu.empty else None
    stale = None if newest is None or pd.isna(newest) else int((pd.Timestamp(date.today()) - newest).days)
    return {"jogadores": df.sort_values(["prob_titular", "qualidade"], ascending=False).reset_index(drop=True),
            "jogos": games, "formacao": forms.most_common(1)[0][0] if forms else None, "escalacoes": lu,
            "fonte_elenco": "ESPN (elenco atual)" if not ros.empty else "escalações recentes", "destaques": dest,
            "dias_desde_ultima_escalacao": stale}


# regra de suspensão por acúmulo de amarelos (estimativa pela regra da competição; zera em fases que o regulamento manda)
YELLOW_LIMIT = {"Brasileirão Série A": 3, "Brasileirão Série B": 3, "Copa do Brasil": 3, "Premier League": 5, "La Liga": 5,
                "Serie A": 5, "Bundesliga": 5, "Ligue 1": 3, "Primeira Liga": 5, "CONMEBOL Libertadores": 3,
                "CONMEBOL Sul-Americana": 3, "UEFA Champions League": 3}


def yellow_suspensions(db, games: Sequence[int], team_names: Sequence[str]) -> Dict[str, str]:
    """
    Pendurado que levou o amarelo que completa o ciclo no último jogo da competição = suspenso no próximo dela.
    É ESTIMATIVA pela regra geral da competição (o regulamento pode zerar cartões em certas fases).
    """
    if not games:
        return {}
    ph, ps = _names_sql([int(x) for x in games])
    th, ts = _names_sql(team_names)
    try:
        with db.connect() as conn:
            t = pd.read_sql_query(f"SELECT t.match_id, m.match_date, m.competition_name, t.player_name, t.event_type "
                                  f"FROM match_timeline t JOIN matches m ON m.match_id = t.match_id WHERE t.match_id IN ({ph}) "
                                  f"AND t.team_name IN ({th}) AND t.event_type LIKE '%Yellow%'", conn, params=ps + ts)
    except Exception:
        return {}
    if t.empty:
        return {}
    out = {}
    for comp, g in t.groupby("competition_name"):
        lim = YELLOW_LIMIT.get(comp)
        if not lim:
            continue
        last_game = g["match_date"].max()
        for p, gp in g.groupby("player_name"):
            n = len(gp)
            if n % lim == 0 and (gp["match_date"] == last_game).any():
                out[p] = f"suspenso por acúmulo de amarelos ({n}º amarelo em {comp}) — estimativa pela regra da competição"
    return out


def multi_fit(slot_role: str, posicoes: Dict[str, int], main: Optional[str]) -> float:
    """Encaixe na vaga por TODAS as posições em que o jogador começou jogando (peso pela frequência)."""
    from src.squad.formations import fit

    if not posicoes:
        return fit(slot_role, main or "")
    precise = {k: v for k, v in posicoes.items() if not str(k).endswith("?")}
    if precise:                                        # posição genérica só vale quando não há nenhuma precisa
        posicoes = precise
    tot = sum(posicoes.values())
    best = 0.0
    for r, k in posicoes.items():
        share = k / tot
        best = max(best, fit(slot_role, r) * (0.75 + 0.25 * min(share * 2, 1.0)))
    return best


def player_highlights(db, games: Sequence[int], team_names: Sequence[str], roles: Dict[str, str],
                      canon: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Pontos fortes e fracos de cada jogador na temporada: soma os números por jogador dos jogos (FotMob), converte
    por 90 min e compara com jogadores da MESMA função na régua da nota 2.0 por estatísticas. Só entra o que foge da
    média (≥ P75 forte, ≤ P25 fraco). Sem números por jogador, o jogador fica sem destaque (nunca inventado).
    """
    if not games:
        return {}
    from src.analytics import rating_box as RB
    from src.analytics.rating_v2 import INDICATORS, GK_INDICATORS, IND_PT, _peer_group, _pct, evaluate

    ref = RB.reference()
    if ref.empty:
        return {}
    ph, ps = _names_sql([int(x) for x in games])
    th, ts = _names_sql(team_names)
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(f"SELECT match_id, team_name, player_name, position, minutes, stats_json FROM match_player_stats "
                                  f"WHERE match_id IN ({ph}) AND team_name IN ({th})", conn, params=ps + ts)
    except Exception:
        return {}
    if d.empty:
        return {}
    if canon:
        d["player_name"] = d["player_name"].map(lambda x: canon.get(x, x))
    out: Dict[str, Dict[str, Any]] = {}
    for name, g in d.groupby("player_name"):
        agg: Dict[str, float] = {}
        n_games = 0
        for js in g["stats_json"]:
            try:
                s = json.loads(js or "{}")
            except Exception:
                continue
            if not s.get("minutes"):
                continue
            n_games += 1
            for k, v in s.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool) and k not in ("fotmob_id",):
                    agg[k] = agg.get(k, 0.0) + float(v)
        if n_games < 2 or agg.get("minutes", 0) < 120:
            continue
        role = roles.get(name)
        row = pd.DataFrame([{"team_name": g["team_name"].iloc[0], "player_name": name, "position": g["position"].iloc[0],
                             "minutes": agg["minutes"], "stats_json": json.dumps(agg)}])
        ind = RB.indicators(row, {name: role} if role else {})
        if ind.empty:
            continue
        r = ind.iloc[0].to_dict()
        model_score = evaluate(r, ref)
        peers = _peer_group(ref, r["funcao"])
        inds = GK_INDICATORS if r["funcao"] == "goleiro" else INDICATORS
        scored = []
        for k, (_dim, _w, hi) in inds.items():
            v = r.get(k)
            if v is None or (isinstance(v, float) and v != v) or k not in peers:
                continue
            pc = _pct(v, peers[k])
            if pc is None:
                continue
            scored.append((pc if hi else 100 - pc, k, v))
        if not scored:
            continue
        scored.sort(key=lambda x: -x[0])
        fortes = [{"rotulo": IND_PT.get(k, k), "valor": round(float(v), 2), "percentil": round(p)} for p, k, v in scored if p >= 75][:3]
        fracos = [{"rotulo": IND_PT.get(k, k), "valor": round(float(v), 2), "percentil": round(p)} for p, k, v in reversed(scored) if p <= 25][:2]
        out[name] = {"fortes": fortes, "fracos": fracos, "jogos": n_games, "minutos": int(agg["minutes"]),
                     "funcao": r["funcao"], "desempenho": model_score.get("desempenho"),
                     "impacto": model_score.get("impacto"), "confianca_pct": model_score.get("confianca_pct"),
                     "pares": model_score.get("pares", 0)}
    return out


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
    G = row.get("jogos_temporada") or n_games
    if row.get("titular_temporada"):
        out.append(f"titular em {row['titular_temporada']} de {G} jogos da temporada")
    if row.get("titular_ult5") is not None:
        out.append(f"{row['titular_ult5']} dos últimos 5 como titular"
                   + ("" if row.get("comecou_ultimo") else " (não começou o último jogo, mas segue entre os titulares da temporada)"
                      if (row.get("titular_temporada") or 0) / max(G, 1) >= 0.5 else ""))
    pos = row.get("posicoes") or {}
    if pos.get(slot_role):
        tot = sum(v for k, v in pos.items() if not str(k).endswith("?")) or sum(pos.values())
        share = round(100 * pos[slot_role] / tot) if tot else None
        src = row.get("origem_posicao") or ""
        if "Transfermarkt" in src and not row.get("titular_temporada"):
            out.append(f"posição de cadastro: {ROLE_PT.get(slot_role, slot_role).lower()} (sem jogos recentes com escalação)")
        elif share is not None:
            out.append(f"{ROLE_PT.get(slot_role, slot_role).lower()} em {share}% das vezes que começou jogando")
    elif row.get("papel") and row["papel"] != slot_role:
        out.append(f"adaptado: costuma jogar de {ROLE_PT.get(row['papel'], row['papel']).lower()}")
    if row.get("gols") or row.get("assistencias"):
        out.append(f"{row.get('gols', 0)} gol(s) e {row.get('assistencias', 0)} assistência(s) na temporada")
    out.append(f"qualidade {row.get('qualidade')} · fase {row.get('fase')}")
    if row.get("duvida"):
        out.append(f"⚠️ dúvida: {row['duvida']}")
    rivals = bench[(bench["papel"] == slot_role) & (bench["nome"] != row["nome"])] if not bench.empty else bench
    if len(rivals):
        alt = rivals.iloc[0]
        out.append(f"à frente de {alt['nome']} (qualidade {alt['qualidade']}, fase {alt['fase']})")
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
            fx = pd.read_sql_query(f"SELECT * FROM fixtures WHERE (home IN ({ph}) OR away IN ({ph})) "
                                   f"AND kickoff >= ? ORDER BY kickoff LIMIT {int(limit) * 3}", conn,
                                   params=ps * 2 + [(date.today() - timedelta(days=1)).isoformat()])
    except Exception:
        return pd.DataFrame()
    if fx.empty:
        return fx
    # o mesmo jogo pode vir da ESPN e da FotMob: fica um por dia (prefere a ESPN, que tem a escalação oficial)
    fx = fx.assign(_d=fx["kickoff"].astype(str).str[:10], _espn=~fx["league"].astype(str).str.startswith("fotmob:"))
    fx = fx.sort_values(["_d", "_espn"], ascending=[True, False]).drop_duplicates("_d")
    return fx.drop(columns=["_d", "_espn"]).head(int(limit)).reset_index(drop=True)


def xi_for(info: Dict[str, Any], formation: Optional[str], mode: str = "provavel") -> Tuple[List[Dict[str, Any]], str]:
    """
    XI para a formação (padrão: a mais usada nos últimos 3 jogos), por atribuição ótima (algoritmo húngaro):
      provável → chance de ser titular; melhor → 60% qualidade + 40% fase.
    O encaixe pesa ao CUBO: jogador fora de posição só entra se não houver ninguém minimamente adequado.
    Lesionados e suspensos ficam de fora. Cada vaga traz o PORQUÊ.
    """
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    from src.squad.formations import FORMATIONS, ROLE_PT

    pl = info["jogadores"]
    form = formation if formation in FORMATIONS else (info.get("formacao") if info.get("formacao") in FORMATIONS else "4-3-3")
    slots = FORMATIONS[form]
    if pl is None or pl.empty:
        return [{"vaga": i, "papel": r, "papel_pt": ROLE_PT[r], "x": x, "y": y, "jogador": None, "nota": None,
                 "encaixe": None, "papel_natural": None} for i, (r, x, y) in enumerate(slots)], form
    ok = pl[~pl["indisponivel"].astype(bool) & pl["papel"].notna()].reset_index(drop=True)
    val = (ok["prob_titular"] / 10.0 + 0.15 * ok["qualidade"]) if mode == "provavel" else (0.6 * ok["qualidade"] + 0.4 * ok["fase"])
    val = val.to_numpy(float) + 0.5
    score = np.zeros((len(slots), len(ok)))
    fits = np.zeros_like(score)
    for i, (role, _, _) in enumerate(slots):
        for j, r in enumerate(ok.itertuples()):
            fits[i, j] = multi_fit(role, r.posicoes, r.papel)
            score[i, j] = val[j] * fits[i, j] ** 3
    ri, ci = linear_sum_assignment(-score)
    pick = dict(zip(ri, ci))
    chosen = {ok.iloc[j]["nome"] for j in pick.values()}
    bench = ok[~ok["nome"].isin(chosen)].sort_values("qualidade", ascending=False)
    G = len(info.get("jogos") or []) or 1
    xi = []
    for i, (role, x, y) in enumerate(slots):
        j = pick.get(i)
        r = ok.iloc[j].to_dict() if j is not None else None
        p = {"vaga": i, "papel": role, "papel_pt": ROLE_PT[role], "x": x, "y": y,
             "jogador": r["nome"] if r else None, "nota": r["qualidade"] if r else None,
             "qualidade": r["qualidade"] if r else None, "fase": r["fase"] if r else None,
             "prob_titular": r["prob_titular"] if r else None,
             "encaixe": round(float(fits[i, j]), 2) if r else None,
             "papel_natural": ROLE_PT.get(r["papel"], "—") if r else None}
        if r:
            p["porque"] = reasons(r, role, bench, G)
            p["destaques"] = (info.get("destaques") or {}).get(r["nome"])
        xi.append(p)
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


def official_xi(info: Dict[str, Any], lineup: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """Escalação OFICIAL publicada (ESPN) no lugar da provável: cada titular na vaga da sua posição oficial."""
    from src.squad.formations import FORMATIONS, ROLE_PT

    form = lineup.get("formacao") if lineup.get("formacao") in FORMATIONS else (info.get("formacao") or "4-3-3")
    form = form if form in FORMATIONS else "4-3-3"
    starters = [p for p in lineup.get("jogadores", []) if p.get("titular")]
    pl = info.get("jogadores")
    byname = {r["nome"]: r for r in pl.to_dict("records")} if pl is not None and not pl.empty else {}
    # lê LM/RM pela formação, como nas escalações passadas
    from src.squad.positions import classify, espn_lm_rm

    how = espn_lm_rm(form, [p["pos"] for p in starters])

    def role(pos):
        up = str(pos).upper()
        if up in ("LM", "RM") and how:
            return {"ala": "LWB" if up == "LM" else "RWB", "volante": "DM", "meia": "CM"}[how]
        r, _ok = classify(pos, "espn")
        return r
    pool = [(p["jogador"], role(p["pos"])) for p in starters]
    xi, used = [], set()
    for i, (slot, x, y) in enumerate(FORMATIONS[form]):
        cand = next((n for n, r in pool if r == slot and n not in used), None) or \
            next((n for n, r in pool if n not in used and SECTOR.get(r or "") == SECTOR.get(slot)), None) or \
            next((n for n, r in pool if n not in used), None)
        if cand:
            used.add(cand)
        r = byname.get(cand, {})
        xi.append({"vaga": i, "papel": slot, "papel_pt": ROLE_PT[slot], "x": x, "y": y, "jogador": cand,
                   "nota": r.get("qualidade"), "qualidade": r.get("qualidade"), "fase": r.get("fase"), "prob_titular": 100,
                   "encaixe": 1.0, "papel_natural": ROLE_PT.get(r.get("papel"), "—"),
                   "porque": ["✅ escalação oficial publicada pela ESPN"],
                   "destaques": (info.get("destaques") or {}).get(cand)})
    return xi, form
