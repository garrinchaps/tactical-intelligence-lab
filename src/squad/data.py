"""
Acesso rápido aos dados do planejador. Tabelas grandes do lake (aparições, escalações, valores) são lidas com
filtro na leitura (pyarrow) — só as linhas do clube/atleta pedido saem do disco — e guardadas em memória pela
data do arquivo, então a segunda abertura é instantânea.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

ADDED = "jogadores_adicionados"
LINEUPS_DIR = Path("data/escalacoes")
_MEM: Dict[str, Any] = {}


def lake():
    from src.data_lake.lake import Lake

    return Lake(sqlite_path=None)


def table(name: str, columns: Optional[List[str]] = None, col: Optional[str] = None,
          values: Optional[Iterable[Any]] = None) -> pd.DataFrame:
    """Tabela do lake, inteira ou filtrada por `col in values` direto na leitura do parquet."""
    lk = lake()
    if not lk.exists(name):
        return pd.DataFrame()
    path = lk.path(name)
    vals = None if values is None else sorted({str(v).replace(".0", "") for v in values if v is not None})
    key = f"{name}|{path.stat().st_mtime}|{columns}|{col}|{vals}"
    if key in _MEM:
        return _MEM[key]
    df = pd.DataFrame()
    if path.suffix == ".parquet" and col and vals is not None:
        try:
            import pyarrow.dataset as ds

            d = ds.dataset(str(path))
            typ = d.schema.field(col).type
            cast = [int(v) for v in vals if v.lstrip("-").isdigit()] if "int" in str(typ) else vals
            df = d.to_table(columns=columns, filter=ds.field(col).isin(cast)).to_pandas()
        except Exception:
            df = pd.DataFrame()
    if df.empty:
        df = lk.read(name, columns)
        if col and vals is not None and col in df:
            df = df[df[col].astype(str).str.replace(r"\.0$", "", regex=True).isin(vals)]
    if len(_MEM) > 64:
        _MEM.clear()
    _MEM[key] = df
    return df


# ------------------------------------------------------------------------------------------ clubes
def clubs() -> pd.DataFrame:
    c = table("tm_clubes")
    return c if not c.empty else pd.DataFrame(columns=["transfermarkt_id", "nome", "liga", "pais"])


def match_club(name: str, cl: Optional[pd.DataFrame] = None) -> Optional[Dict[str, Any]]:
    """Clube do Transfermarkt mais parecido com o nome usado nas outras bases (ex.: "Flamengo" × "CR Flamengo")."""
    from src.data_hub.search import fast_scores
    from src.data_lake.ids import team_core

    cl = clubs() if cl is None else cl
    if cl.empty or not str(name).strip():
        return None
    core = team_core(name)
    exact = cl[cl["nome"].map(team_core) == core]
    if not exact.empty:
        return exact.iloc[0].to_dict()
    sc = fast_scores(name, cl["nome"].astype(str).unique())
    best = max(sc.items(), key=lambda kv: kv[1]) if sc else None
    if best and best[1] >= 0.86:
        return cl[cl["nome"] == best[0]].iloc[0].to_dict()
    return None


# ------------------------------------------------------------------------------------------ atletas
def added_players() -> pd.DataFrame:
    a = table(ADDED)
    return a if not a.empty else pd.DataFrame(columns=["nome", "clube", "posicao", "funcao", "nascimento", "altura_cm",
                                                       "pe", "valor_mercado_eur", "nota_manual", "observacao"])


def add_player(row: Dict[str, Any]) -> None:
    """Salva (ou atualiza) um atleta digitado por você no lake local — entra no elenco e no planejador."""
    rec = {k: row.get(k) for k in ("nome", "clube", "posicao", "funcao", "nascimento", "altura_cm", "pe",
                                   "valor_mercado_eur", "nota_manual", "observacao")}
    rec["adicionado_em"] = datetime.now().isoformat(timespec="seconds")
    lake().upsert(ADDED, pd.DataFrame([rec]), ["nome", "clube"], source="você (cadastro manual)",
                  connector="planejador", license="dados próprios")
    _MEM.clear()


def remove_added(nome: str, clube: str) -> None:
    a = added_players()
    a = a[~((a["nome"] == nome) & (a["clube"] == clube))]
    lake().write(ADDED, a, source="você (cadastro manual)", connector="planejador", license="dados próprios")
    _MEM.clear()


def external_ratings() -> pd.DataFrame:
    """Nota externa 0–100 por atleta, de qualquer tabela do lake com nome + coluna de nota (ex.: Simonetti)."""
    lk = lake()
    try:
        names = [t for t in lk.tables()["tabela"].tolist() if str(t).startswith("sm_")]
    except Exception:
        names = []
    out = []
    for t in names:
        df = table(t)
        if df.empty:
            continue
        low = {c.lower(): c for c in df.columns}
        ncol = next((low[c] for c in ("nome", "jogador", "player", "name", "atleta") if c in low), None)
        rcol = next((low[c] for c in low if any(k in c for k in ("overall", "nota", "rating", "ovr"))), None)
        if not ncol or not rcol:
            continue
        v = pd.to_numeric(df[rcol], errors="coerce")
        if v.notna().sum() < 20:
            continue
        lo, hi = v.quantile(0.01), v.quantile(0.99)
        scaled = v if (lo >= 0 and hi <= 100) else (v - lo) / max(hi - lo, 1e-9) * 100
        out.append(pd.DataFrame({"nome": df[ncol].astype(str), "nota": scaled.clip(0, 100), "fonte": t}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["nome", "nota", "fonte"])


def tm_reference() -> pd.DataFrame:
    """Atletas ativos do Transfermarkt (última temporada registrada) — base para comparar valor por posição."""
    tm = table("tm_jogadores", ["nome", "posicao", "funcao", "valor_mercado_eur", "ultima_temporada"])
    if tm.empty:
        return tm
    last = pd.to_numeric(tm["ultima_temporada"], errors="coerce")
    return tm[last >= last.max() - 1]


def club_lineups(club_id: Any, n_games: int = 20) -> pd.DataFrame:
    """Escalações (titulares) dos últimos jogos do clube no Transfermarkt → (jogo, data, jogador, titular)."""
    if club_id is None:
        return pd.DataFrame()
    lu = table("tm_escalacoes", None, "clube_id", [club_id])
    if lu.empty:
        return pd.DataFrame()
    games = lu.groupby("jogo_id")["data"].max().sort_values(ascending=False).head(n_games).index
    lu = lu[lu["jogo_id"].isin(games)]
    return pd.DataFrame({"jogo": lu["jogo_id"], "data": lu["data"].astype(str), "jogador": lu["nome"],
                         "titular": lu["tipo"].astype(str).str.contains("start", case=False).astype(int),
                         "posicao": lu.get("posicao")})


def db_lineups(db, team_names: Sequence[str], n_games: int = 20) -> pd.DataFrame:
    """Escalações da base local (ESPN, API-Football, openfootball, súmulas) quando o Transfermarkt não cobre o clube."""
    if not team_names:
        return pd.DataFrame()
    ph = ",".join("?" * len(team_names))
    q = f"""SELECT l.match_id AS jogo, m.match_date AS data, l.player_name AS jogador, l.is_starter AS titular,
                   l.position AS posicao, l.formation AS formacao
            FROM match_lineups l JOIN matches m ON m.match_id = l.match_id
            WHERE l.team_name IN ({ph}) AND m.match_id IN (
                SELECT match_id FROM matches WHERE home_team_name IN ({ph}) OR away_team_name IN ({ph})
                ORDER BY match_date DESC LIMIT {int(n_games) * 3})"""
    try:
        with db.connect() as conn:
            return pd.read_sql_query(q, conn, params=list(team_names) * 3)
    except Exception:
        return pd.DataFrame()


def moved_elsewhere(db, last_here: Dict[str, str], team_names: Sequence[str]) -> set:
    """Atletas que aparecem numa escalação de OUTRO time depois do último jogo por este (transferência/empréstimo)."""
    names = [n for n in last_here if n]
    if not names:
        return set()
    out = set()
    for i in range(0, len(names), 400):
        chunk = names[i:i + 400]
        q = (f"SELECT l.player_name AS jogador, l.team_name AS time, MAX(m.match_date) AS data FROM match_lineups l "
             f"JOIN matches m ON m.match_id = l.match_id WHERE l.player_name IN ({','.join('?' * len(chunk))}) "
             f"GROUP BY l.player_name, l.team_name")
        try:
            with db.connect() as conn:
                df = pd.read_sql_query(q, conn, params=chunk)
        except Exception:
            return out
        other = df[~df["time"].isin(list(team_names))]
        for r in other.itertuples():
            if str(r.data) > str(last_here.get(r.jogador, "")):
                out.add(r.jogador)
    return out


def squad_from_db(db, team_names: Sequence[str], n_games: int = 20) -> pd.DataFrame:
    """Sem Transfermarkt para o clube: elenco = quem apareceu nas escalações/lances recentes da base local."""
    lu = db_lineups(db, team_names, n_games)
    if lu.empty:
        return pd.DataFrame()
    # v36: só a janela recente (até 150 dias antes do último jogo do time) — quem sumiu das escalações saiu
    d = pd.to_datetime(lu["data"], errors="coerce")
    lu = lu[d >= d.max() - pd.Timedelta(days=150)]
    # sai quem jogou por outro time depois E não está nos 5 jogos mais recentes daqui (homônimo não derruba titular)
    last5 = set(lu.loc[lu["jogo"].isin(lu.drop_duplicates("jogo").sort_values("data").tail(5)["jogo"]), "jogador"])
    gone = moved_elsewhere(db, lu.groupby("jogador")["data"].max().to_dict(), team_names) - last5
    lu = lu[~lu["jogador"].isin(gone)]
    if lu.empty:
        return pd.DataFrame()
    g = lu.groupby("jogador")
    # rodada 5: posição precisa × genérica por fonte (G/D/M/F da API-Football não vira centroavante/zagueiro)
    from src.squad.positions import player_roles, resolve_lineups

    rl = resolve_lineups(lu.rename(columns={"jogo": "match_id", "posicao": "pos", "formacao": "formation"}))
    main = {}
    for nome, gp in rl.groupby("jogador"):
        st = gp[gp["titular"] == 1]
        main[nome] = player_roles(st if len(st) else gp)[1] or ""
    df = pd.DataFrame({"nome": list(g.groups), "posicao": g["posicao"].agg(
        lambda s: s.dropna().astype(str).mode().iloc[0] if s.dropna().size else "").tolist()})
    df["funcao"] = df["nome"].map(main).fillna("")
    df["clube"] = team_names[0]
    df["jogos_recentes"] = g.size().values
    return df


# ------------------------------------------------------------------------------------------ jogos e estatísticas
def recent_matches(db, team_names: Sequence[str], n: int = 20, before: Optional[str] = None) -> pd.DataFrame:
    ph = ",".join("?" * len(team_names))
    where = f"(home_team_name IN ({ph}) OR away_team_name IN ({ph})) AND data_level IN ('EVENTS','BOXSCORE') " \
            "AND home_score IS NOT NULL"
    params: List[Any] = list(team_names) * 2
    if before:
        where += " AND match_date < ?"
        params.append(before)
    q = f"""SELECT match_id, match_date, home_team_name, away_team_name, home_score, away_score, competition_name,
                   season_name, data_source, data_level FROM matches WHERE {where} ORDER BY match_date DESC LIMIT ?"""
    with db.connect() as conn:
        m = pd.read_sql_query(q, conn, params=params + [int(n) * 4])
    if m.empty:
        return m
    # a mesma partida pode estar em várias fontes: fica uma por data e placar, a mais rica (lances > estatísticas)
    m["_k"] = m["match_date"].astype(str) + "|" + m["home_score"].astype(str) + "|" + m["away_score"].astype(str)
    rank = {"EVENTS": 0, "BOXSCORE": 1}
    ids = m.groupby("_k")["match_id"].apply(list)
    m = m.assign(_r=m["data_level"].map(rank)).sort_values(["_k", "_r"]).drop_duplicates("_k")
    m["ids"] = m["_k"].map(ids)
    return m.drop(columns=["_k", "_r"]).sort_values("match_date", ascending=False).head(int(n))


def ensure_events(service, match_ids: Sequence[int], limit: int = 20, budget_s: float = 25.0) -> int:
    """
    Baixa/converte os lances dos jogos que ainda não estão no banco (StatsBomb local, OpenPlay, Wyscout), com teto de
    tempo: sem internet ou com fonte lenta, para no teto e o perfil usa o que já houver.
    """
    import time as _t

    t0, done = _t.time(), 0
    for mid in list(match_ids)[:limit]:
        if _t.time() - t0 > budget_s:
            break
        try:
            if not service.db.has_events(int(mid)):
                service.load(int(mid))
                done += 1
        except Exception:
            continue
    return done


def event_stats(db, match_ids: Sequence[int]) -> pd.DataFrame:
    """Estatísticas de equipe tiradas dos lances (StatsBomb/Wyscout não trazem a tabela pronta)."""
    if not len(match_ids):
        return pd.DataFrame(columns=["match_id", "team_name", "stat_key", "value"])
    ph = ",".join("?" * len(match_ids))
    q = f"""SELECT match_id, team_name,
              SUM(type_name = 'Shot') AS shots_total,
              SUM(type_name = 'Shot' AND shot_outcome_name IN ('Goal', 'Saved', 'Saved To Post')) AS shots_on_target,
              SUM(CASE WHEN type_name = 'Shot' THEN COALESCE(shot_statsbomb_xg, 0) ELSE 0 END) AS xg,
              SUM(type_name = 'Pass') AS passes_total,
              SUM(type_name = 'Pass' AND pass_outcome_name IS NULL) AS passes_ok,
              SUM(type_name = 'Pass' AND is_pass_cross = 1) AS crosses_total,
              SUM(type_name = 'Pass' AND pass_type_name = 'Corner') AS corners,
              SUM(type_name = 'Foul Committed') AS fouls,
              SUM(foul_committed_card_name LIKE '%Yellow%') AS yellow_cards,
              SUM(type_name = 'Dribble') AS dribbles_completed,
              SUM(type_name = 'Interception') AS interceptions
            FROM events WHERE match_id IN ({ph}) AND period <= 4 AND team_name IS NOT NULL
            GROUP BY match_id, team_name"""
    try:
        with db.connect() as conn:
            w = pd.read_sql_query(q, conn, params=[int(x) for x in match_ids])
    except Exception:
        return pd.DataFrame(columns=["match_id", "team_name", "stat_key", "value"])
    if w.empty:
        return pd.DataFrame(columns=["match_id", "team_name", "stat_key", "value"])
    tot = w.groupby("match_id")["passes_total"].transform("sum")
    w["possession_pct"] = (w["passes_total"] / tot.replace(0, np.nan) * 100).round(1)   # posse pela proporção dos passes
    w["pass_accuracy_pct"] = (w["passes_ok"] / w["passes_total"].replace(0, np.nan) * 100).round(1)
    w = w.drop(columns=["passes_ok", "dribbles_completed"])                   # Dribble sem desfecho: não é "certo"
    return w.melt(id_vars=["match_id", "team_name"], var_name="stat_key", value_name="value").dropna(subset=["value"])


def merged_stats(db, matches: pd.DataFrame, team_names: Sequence[str]) -> pd.DataFrame:
    """Estatísticas de todas as fontes de cada partida, gravadas no id principal (a primeira fonte vence)."""
    if matches is None or matches.empty:
        return pd.DataFrame(columns=["match_id", "team_name", "stat_key", "value"])
    canon = {int(i): int(r.match_id) for r in matches.itertuples() for i in (getattr(r, "ids", None) or [r.match_id])}
    st = match_stats(db, list(canon))
    ev_ids = [int(r.match_id) for r in matches.itertuples() if r.data_level == "EVENTS"] if "data_level" in matches else []
    ev = event_stats(db, ev_ids)
    if not ev.empty:                                    # lances entram por último: a tabela da fonte tem prioridade
        ev = ev.assign(match_id=ev["match_id"] + 0)
        st = pd.concat([st, ev.assign(_ev=1)], ignore_index=True)
    if st.empty:
        return st
    names = set(team_names)
    st["mine"] = st["team_name"].isin(names)
    st["prio"] = (st["match_id"] != st["match_id"].map(canon)).astype(int) + 2 * st.get("_ev", 0).fillna(0).astype(int) \
        if "_ev" in st else (st["match_id"] != st["match_id"].map(canon)).astype(int)
    st["match_id"] = st["match_id"].map(canon)
    st = st.sort_values("prio").drop_duplicates(["match_id", "mine", "stat_key"])
    st["team_name"] = np.where(st["mine"], list(names)[0], "__rival__")
    return st.drop(columns=[c for c in ("mine", "prio", "_ev") if c in st.columns])


def match_stats(db, match_ids: Sequence[int]) -> pd.DataFrame:
    if not len(match_ids):
        return pd.DataFrame(columns=["match_id", "team_name", "stat_key", "value"])
    ph = ",".join("?" * len(match_ids))
    with db.connect() as conn:
        return pd.read_sql_query(f"SELECT match_id, team_name, stat_key, value FROM match_team_stats "
                                 f"WHERE match_id IN ({ph})", conn, params=[int(x) for x in match_ids])


def baseline(db, competitions: Sequence[str], date_from: str, date_to: str) -> Dict[str, float]:
    """Média por time e jogo de cada estatística nas mesmas competições e período (a régua de comparação)."""
    if not competitions:
        return {}
    ph = ",".join("?" * len(competitions))
    q = f"""SELECT s.stat_key, AVG(s.value) FROM match_team_stats s JOIN matches m ON m.match_id = s.match_id
            WHERE m.competition_name IN ({ph}) AND m.match_date BETWEEN ? AND ? GROUP BY s.stat_key"""
    qg = f"""SELECT AVG((home_score + away_score) / 2.0) FROM matches
             WHERE competition_name IN ({ph}) AND match_date BETWEEN ? AND ? AND home_score IS NOT NULL"""
    with db.connect() as conn:
        rows = conn.execute(q, list(competitions) + [date_from, date_to]).fetchall()
        g = conn.execute(qg, list(competitions) + [date_from, date_to]).fetchone()
    out = {k: float(v) for k, v in rows if v is not None}
    if g and g[0] is not None:
        out["goals"] = float(g[0])
    # estatísticas que só existem nos lances (StatsBomb/Wyscout): média tirada dos jogos com lances no mesmo recorte
    qe = f"""SELECT DISTINCT e.match_id FROM events e JOIN matches m ON m.match_id = e.match_id
             WHERE m.competition_name IN ({ph}) AND m.match_date BETWEEN ? AND ? LIMIT 300"""
    with db.connect() as conn:
        ids = [r[0] for r in conn.execute(qe, list(competitions) + [date_from, date_to]).fetchall()]
    ev = event_stats(db, ids)
    if not ev.empty:
        for k, v in ev.groupby("stat_key")["value"].mean().items():
            out.setdefault(k, float(v))
    return out


def attack_corridors(db, match_ids: Sequence[int], team_names: Sequence[str]) -> Dict[str, Any]:
    """
    Por onde o time ataca e por onde sofre (só jogos com lances): passes e conduções que chegam ao último terço,
    por corredor — esquerda / centro / direita, do ponto de vista de quem ataca.
    """
    if not len(match_ids):
        return {}
    ph = ",".join("?" * len(match_ids))
    q = f"""SELECT team_name, end_y FROM events WHERE match_id IN ({ph}) AND type_name IN ('Pass', 'Carry')
            AND end_x >= 80 AND (x IS NULL OR x < 80) AND end_y IS NOT NULL"""
    try:
        with db.connect() as conn:
            ev = pd.read_sql_query(q, conn, params=[int(x) for x in match_ids])
            jogos = conn.execute(f"SELECT COUNT(DISTINCT match_id) FROM events WHERE match_id IN ({ph})",
                                 [int(x) for x in match_ids]).fetchone()[0]
    except Exception:
        return {}
    if ev.empty:
        return {}
    names = set(team_names)
    side = pd.cut(ev["end_y"], [-1, 26.67, 53.33, 81], labels=["esquerda", "centro", "direita"])
    mine, theirs = side[ev["team_name"].isin(names)], side[~ev["team_name"].isin(names)]
    pct = lambda s: {k: round(float(v) * 100, 0) for k, v in s.value_counts(normalize=True).items()} if len(s) else {}
    return {"ataca_por": pct(mine), "sofre_por": pct(theirs), "acoes_ataque": int(len(mine)),
            "acoes_sofridas": int(len(theirs)), "jogos": int(jogos or 0)}


# ------------------------------------------------------------------------------------------ escalações salvas
def save_lineup(name: str, payload: Dict[str, Any]) -> Path:
    LINEUPS_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name).strip().replace(" ", "_")[:80]
    path = LINEUPS_DIR / f"{date.today():%Y%m%d}_{safe}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


def saved_lineups() -> List[Path]:
    return sorted(LINEUPS_DIR.glob("*.json"), reverse=True) if LINEUPS_DIR.exists() else []
