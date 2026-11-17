"""
Planejador de escalação.

Peças, todas sem inventar dado:
  * `squad_frame`     — elenco atual (Transfermarkt) + atletas adicionados à mão, com papel natural e idade;
  * `lab_rating`      — nota do laboratório (0–100): valor de mercado relativo à posição + minutos e participação
                        em gols na última temporada (Transfermarkt) + nota do Simonetti quando existir. Cada parte
                        usada fica registrada em `nota_base`; atleta sem nenhuma base fica sem nota;
  * `best_xi`         — atribuição ótima (algoritmo húngaro) de atletas às vagas da formação: nota × encaixe;
  * `probable_xi`     — quem mais começou jogando nos últimos N jogos (escalações do Transfermarkt ou da base);
  * `team_profile` / `matchup_plan` — perfil dos últimos 1/3/5/10/20 jogos com estatísticas contra a média das
                        mesmas competições no mesmo período; daí saem as características marcantes do rival, as
                        fraquezas dele e os pontos fortes do nosso time que atacam essas fraquezas.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.squad.formations import FORMATIONS, ROLE_PT, fit, natural_role


# Normaliza nomes de seleções e nacionalidades do Transfermarkt. Países não listados
# continuam tratados como clubes, evitando classificar clubes pelo nome de cidade.
_COUNTRY_ALIASES = {
    "brasil": "brazil", "brazil": "brazil",
    "inglaterra": "england", "england": "england",
    "espanha": "spain", "spain": "spain",
    "alemanha": "germany", "germany": "germany",
    "franca": "france", "france": "france",
    "italia": "italy", "italy": "italy",
    "portugal": "portugal",
    "argentina": "argentina",
    "uruguai": "uruguay", "uruguay": "uruguay",
    "holanda": "netherlands", "paises baixos": "netherlands", "netherlands": "netherlands",
    "belgica": "belgium", "belgium": "belgium",
    "croacia": "croatia", "croatia": "croatia",
    "servia": "serbia", "serbia": "serbia",
    "japao": "japan", "japan": "japan",
    "coreia do sul": "south korea", "south korea": "south korea",
    "estados unidos": "united states", "united states": "united states",
    "mexico": "mexico",
    "colombia": "colombia",
    "chile": "chile",
    "paraguai": "paraguay", "paraguay": "paraguay",
    "equador": "ecuador", "ecuador": "ecuador",
    "peru": "peru",
    "senegal": "senegal",
    "marrocos": "morocco", "morocco": "morocco",
    "nigeria": "nigeria",
    "camaroes": "cameroon", "cameroon": "cameroon",
    "costa do marfim": "ivory coast", "ivory coast": "ivory coast",
    "gana": "ghana", "ghana": "ghana",
    "dinamarca": "denmark", "denmark": "denmark",
    "suecia": "sweden", "sweden": "sweden",
    "noruega": "norway", "norway": "norway",
    "suica": "switzerland", "switzerland": "switzerland",
    "austria": "austria",
    "polonia": "poland", "poland": "poland",
    "turquia": "turkey", "turkey": "turkey",
    "ucrania": "ukraine", "ukraine": "ukraine",
}


def _country_key(value: Any) -> str:
    import unicodedata

    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
    token = " ".join("".join(ch for ch in raw if not unicodedata.combining(ch)).split())
    return _COUNTRY_ALIASES.get(token, "")


def national_team_key(team_name: str) -> str:
    """Retorna a nacionalidade canônica quando o nome selecionado é uma seleção reconhecida."""
    return _country_key(team_name)


def filter_national_team_players(players: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """Em seleções, mantém apenas atletas cuja nacionalidade está explicitamente confirmada."""
    country = national_team_key(team_name)
    if not country or players is None or players.empty:
        return players.copy() if players is not None else pd.DataFrame()
    if "nacionalidade" not in players:
        return players.iloc[0:0].copy()
    mask = players["nacionalidade"].map(_country_key).eq(country)
    return players.loc[mask].copy().reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ elenco
def age_on(born: Any, ref: Optional[date] = None) -> Optional[float]:
    b = pd.to_datetime(born, errors="coerce")
    if pd.isna(b):
        return None
    r = pd.Timestamp(ref or date.today())
    return round((r - b).days / 365.25, 1)


def squad_frame(tm_players: pd.DataFrame, club_ids: Iterable[Any] = (), club_names: Iterable[str] = (),
                added: Optional[pd.DataFrame] = None, ref: Optional[date] = None) -> pd.DataFrame:
    """Elenco atual: atletas cujo clube atual no Transfermarkt é o escolhido (na última temporada registrada)."""
    ids = {str(i) for i in club_ids if i is not None and str(i) != ""}
    names = {str(n).strip().lower() for n in club_names if n}
    parts = []
    if tm_players is not None and not tm_players.empty:
        t = tm_players
        m = pd.Series(False, index=t.index)
        if ids and "clube_id" in t:
            m |= t["clube_id"].astype(str).str.replace(r"\.0$", "", regex=True).isin(ids)
        if names and "clube" in t:
            m |= t["clube"].astype(str).str.strip().str.lower().isin(names)
        t = t[m].copy()
        if not t.empty and "ultima_temporada" in t:
            last = pd.to_numeric(t["ultima_temporada"], errors="coerce")
            t = t[last >= last.max() - 0]                # só quem ainda está no clube na temporada mais recente
        t["origem"] = "Transfermarkt"
        parts.append(t)
    if added is not None and not added.empty:
        a = added.copy()
        if names:
            a = a[a["clube"].astype(str).str.strip().str.lower().isin(names)]
        a["origem"] = "adicionado por você"
        parts.append(a)
    if not parts or all(p.empty for p in parts):
        return pd.DataFrame(columns=["nome", "papel", "idade"])
    df = pd.concat(parts, ignore_index=True)
    for c in ("funcao", "posicao", "nacionalidade", "nascimento", "altura_cm", "pe", "valor_mercado_eur", "transfermarkt_id", "nota_manual"):
        if c not in df:
            df[c] = None
    df["papel"] = [natural_role(f, p) for f, p in zip(df["funcao"], df["posicao"])]
    df["idade"] = df["nascimento"].map(lambda b: age_on(b, ref))
    df = df.drop_duplicates(subset=["nome"], keep="last").reset_index(drop=True)
    return df


def _tid(x: Any) -> str:
    return str(x).replace(".0", "") if x is not None and str(x) not in ("", "nan", "None") else ""


def apply_transfers(squad: pd.DataFrame, club_id: Any, own_apps: Optional[pd.DataFrame],
                    squad_apps: Optional[pd.DataFrame], tm_players: Optional[pd.DataFrame] = None,
                    ref: Optional[date] = None, arrival_days: int = 150) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """
    v36 — elenco ATUAL a partir dos jogos, não só do cadastro (o cadastro do Transfermarkt atrasa nas janelas):
    * SAIU: o último jogo do atleta foi por OUTRO clube, depois do último jogo por este (venda ou empréstimo);
    * CHEGOU: jogou por este clube nos últimos `arrival_days` dias e não jogou por outro depois (contratação/empréstimo).
    `own_apps` = aparições de jogos do clube (tm_aparicoes filtrado por clube_id); `squad_apps` = aparições, em
    qualquer clube, dos atletas do elenco cadastrado. Devolve (elenco ajustado, lista de mudanças com o motivo).
    """
    cid = _tid(club_id)
    changes: List[Dict[str, Any]] = []
    if squad is None:
        squad = pd.DataFrame()
    sq = squad.copy()
    if not cid:
        return sq, changes
    today = pd.Timestamp(ref or date.today())

    def last_by(apps: pd.DataFrame) -> pd.DataFrame:
        a = apps.assign(tid=apps["transfermarkt_id"].map(_tid), cl=apps["clube_id"].map(_tid),
                        d=pd.to_datetime(apps["data"], errors="coerce")).dropna(subset=["d"])
        return a.sort_values("d")

    # saídas
    if squad_apps is not None and not squad_apps.empty and "transfermarkt_id" in sq:
        a = last_by(squad_apps)
        last_any = a.groupby("tid").tail(1).set_index("tid")
        last_here = a[a["cl"] == cid].groupby("tid")["d"].max()
        drop = []
        for i, r in sq.iterrows():
            t = _tid(r.get("transfermarkt_id"))
            if t not in last_any.index:
                continue
            la = last_any.loc[t]
            here = last_here.get(t)
            if la["cl"] != cid and (here is None or pd.isna(here) or la["d"] > here):
                drop.append(i)
                changes.append({"nome": r.get("nome"), "mudanca": "saiu",
                                "motivo": f"último jogo por outro clube em {la['d']:%d/%m/%Y}"
                                          + (f" (pelo daqui: {here:%d/%m/%Y})" if here is not None and not pd.isna(here) else "")})
        sq = sq.drop(index=drop)
    # chegadas
    if own_apps is not None and not own_apps.empty:
        a = last_by(own_apps)
        recent = a[(a["cl"] == cid) & (a["d"] >= today - pd.Timedelta(days=arrival_days))]
        have = set(sq["transfermarkt_id"].map(_tid)) if "transfermarkt_id" in sq else set()
        new_ids = [t for t in recent["tid"].unique() if t and t not in have]
        if new_ids:
            info = pd.DataFrame()
            if tm_players is not None and not tm_players.empty:
                info = tm_players[tm_players["transfermarkt_id"].map(_tid).isin(new_ids)].copy()
            rows = []
            for t in new_ids:
                last_here = recent.loc[recent["tid"] == t, "d"].max()
                row = info[info["transfermarkt_id"].map(_tid) == t]
                base = row.iloc[0].to_dict() if not row.empty else {
                    "transfermarkt_id": t, "nome": recent.loc[recent["tid"] == t, "nome"].iloc[-1]}
                base["origem"] = "chegou (jogou pelo clube)"
                rows.append(base)
                changes.append({"nome": base.get("nome"), "mudanca": "chegou",
                                "motivo": f"jogou pelo clube em {last_here:%d/%m/%Y}"})
            add = pd.DataFrame(rows)
            for c in ("funcao", "posicao", "nascimento"):
                if c not in add:
                    add[c] = None
            add["papel"] = [natural_role(f, p) for f, p in zip(add["funcao"], add["posicao"])]
            add["idade"] = add["nascimento"].map(lambda b: age_on(b, ref))
            sq = pd.concat([sq, add], ignore_index=True)
    return sq.reset_index(drop=True), changes


def season_usage(appearances: Optional[pd.DataFrame], player_ids: Iterable[Any], since: Optional[str] = None
                 ) -> pd.DataFrame:
    """Minutos, jogos, gols e assistências por atleta desde `since` (aparições do Transfermarkt)."""
    if appearances is None or appearances.empty:
        return pd.DataFrame(columns=["transfermarkt_id", "jogos", "minutos", "gols", "assistencias"])
    a = appearances
    ids = {str(i).replace(".0", "") for i in player_ids if i is not None}
    a = a[a["transfermarkt_id"].astype(str).str.replace(r"\.0$", "", regex=True).isin(ids)]
    if since:
        a = a[a["data"].astype(str) >= since]
    if a.empty:
        return pd.DataFrame(columns=["transfermarkt_id", "jogos", "minutos", "gols", "assistencias"])
    g = a.assign(transfermarkt_id=a["transfermarkt_id"].astype(str).str.replace(r"\.0$", "", regex=True)) \
        .groupby("transfermarkt_id")
    return pd.DataFrame({"jogos": g.size(), "minutos": g["minutos"].sum(), "gols": g["gols"].sum(),
                         "assistencias": g["assistencias"].sum()}).reset_index()


def lab_rating(squad: pd.DataFrame, reference: Optional[pd.DataFrame] = None,
               usage: Optional[pd.DataFrame] = None, external: Optional[pd.DataFrame] = None,
               player_performance: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Nota do laboratório (0–100) — uma estimativa declarada, não a nota de um olheiro:
      valor   — percentil do valor de mercado (escala log) entre atletas da MESMA função na referência (peso 0,55);
      uso     — percentil dos minutos na temporada no próprio elenco + participação em gols por 90 para meias e
                atacantes (peso 0,20);
      estatística — nota de desempenho 2.0 por posição, quando há amostra confiável (peso 0,35);
      externa — nota de fonte externa (ex.: Simonetti) já em 0–100, quando o nome bate (peso 0,10, ou mais
                quando é a única base);
      manual  — nota digitada por você ao adicionar o atleta substitui tudo. Sem estatística individual suficiente,
                os pesos disponíveis são renormalizados e o cálculo anterior continua funcionando.
    """
    df = squad.copy()
    ref = reference if reference is not None and not reference.empty else df
    ref = ref.assign(papel=[natural_role(f, p) for f, p in zip(ref.get("funcao", pd.Series(index=ref.index)),
                                                               ref.get("posicao", pd.Series(index=ref.index)))])
    lv = np.log1p(pd.to_numeric(ref.get("valor_mercado_eur"), errors="coerce"))
    comps: Dict[str, pd.Series] = {}
    vals = np.log1p(pd.to_numeric(df["valor_mercado_eur"], errors="coerce"))
    pv = []
    for role, v in zip(df["papel"], vals):
        pool = lv[(ref["papel"] == role) & lv.notna()] if role else lv[lv.notna()]
        if len(pool) < 10:                              # posição com poucos atletas na referência: compara com todos
            pool = lv[lv.notna()]
        pv.append(float((pool < v).mean() * 100) if pd.notna(v) and len(pool) >= 10 else np.nan)
    comps["valor"] = pd.Series(pv, index=df.index)
    if usage is not None and not usage.empty and "transfermarkt_id" in df:
        u = df["transfermarkt_id"].astype(str).str.replace(r"\.0$", "", regex=True).map(
            usage.set_index("transfermarkt_id").to_dict("index")).map(lambda d: d if isinstance(d, dict) else {})
        mins = u.map(lambda d: d.get("minutos"))
        mins = pd.to_numeric(mins, errors="coerce")
        pm = mins.rank(pct=True) * 100
        ga90 = u.map(lambda d: ((d.get("gols") or 0) + (d.get("assistencias") or 0)) / max(d.get("minutos") or 0, 1) * 90)
        att = df["papel"].isin(["AM", "LW", "RW", "ST", "LM", "RM"])
        pga = pd.Series(np.where(att & (mins >= 450), np.clip(ga90 / 0.8, 0, 1) * 100, np.nan), index=df.index)
        comps["uso"] = pd.Series(np.where(pga.notna(), 0.6 * pm + 0.4 * pga, pm), index=df.index)
        df["minutos_temporada"] = mins
        df["gols_temporada"] = u.map(lambda d: d.get("gols"))
        df["assist_temporada"] = u.map(lambda d: d.get("assistencias"))
    from src.data_lake.ids import player_core

    if external is not None and not external.empty:
        ext = external.assign(_c=external["nome"].map(player_core)).drop_duplicates("_c").set_index("_c")["nota"]
        comps["externa"] = df["nome"].map(player_core).map(ext).astype(float)
    if player_performance is not None and not player_performance.empty:
        name_col = "nome" if "nome" in player_performance else "jogador" if "jogador" in player_performance else None
        score_col = "qualidade" if "qualidade" in player_performance else "desempenho" if "desempenho" in player_performance else None
        if name_col and score_col:
            perf = player_performance[[name_col, score_col]].copy()
            perf["_core"] = perf[name_col].map(player_core)
            perf[score_col] = pd.to_numeric(perf[score_col], errors="coerce")
            perf = perf.dropna(subset=["_core", score_col]).drop_duplicates("_core", keep="last")
            score_map = (perf.set_index("_core")[score_col] * 10).to_dict()
            comps["desempenho"] = df["nome"].map(player_core).map(score_map).astype(float)
    weights = {"valor": 0.35, "uso": 0.20, "externa": 0.10, "desempenho": 0.35}
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    used: List[List[str]] = [[] for _ in range(len(df))]
    for k, s in comps.items():
        ok = s.notna()
        num[ok] += weights[k] * s[ok]
        den[ok] += weights[k]
        for i in np.flatnonzero(ok.to_numpy()):
            used[i].append(k)
    nota = (num / den.replace(0, np.nan)).round(0)
    manual = pd.to_numeric(df.get("nota_manual"), errors="coerce")
    nota = nota.where(manual.isna(), manual)
    df["nota"] = nota
    df["nota_base"] = ["manual" if pd.notna(m) else (" + ".join(u) if u else "sem base") for m, u in zip(manual, used)]
    return df


# ------------------------------------------------------------------------------------------------ escalações
def best_xi(squad: pd.DataFrame, formation: str = "4-3-3", bonus: Optional[Dict[str, float]] = None,
            locked: Optional[Dict[int, str]] = None) -> List[Dict[str, Any]]:
    """
    Melhor XI para a formação: maximiza Σ nota × encaixe (algoritmo húngaro). `bonus` soma pontos por atleta
    (ajuste para o adversário); `locked` fixa atletas em vagas (índice da vaga → nome).
    """
    from scipy.optimize import linear_sum_assignment

    slots = FORMATIONS[formation]
    sq = squad.reset_index(drop=True)
    if sq.empty:
        return [{"vaga": i, "papel": r, "x": x, "y": y, "jogador": None} for i, (r, x, y) in enumerate(slots)]
    nota = pd.to_numeric(sq.get("nota"), errors="coerce").fillna(40).to_numpy(float)
    b = np.array([float((bonus or {}).get(n, 0.0)) for n in sq["nome"]])
    score = np.zeros((len(slots), len(sq)))
    for i, (role, _, _) in enumerate(slots):
        for j, prole in enumerate(sq["papel"]):
            score[i, j] = (nota[j] + b[j]) * fit(role, prole)
    for i, name in (locked or {}).items():
        if name in set(sq["nome"]):
            j = int(np.flatnonzero(sq["nome"].to_numpy() == name)[0])
            score[:, j] -= 1e6                          # ninguém mais usa esse atleta…
            score[i, :] -= 1e6
            score[i, j] = 1e9                           # …e ele fica nesta vaga
    r, c = linear_sum_assignment(-score)
    out = []
    pick = dict(zip(r, c))
    for i, (role, x, y) in enumerate(slots):
        j = pick.get(i)
        row = sq.iloc[j] if j is not None else None
        out.append({"vaga": i, "papel": role, "papel_pt": ROLE_PT[role], "x": x, "y": y,
                    "jogador": None if row is None else row["nome"],
                    "nota": None if row is None or pd.isna(row.get("nota")) else float(row["nota"]),
                    "encaixe": None if row is None else round(fit(role, row["papel"]), 2),
                    "papel_natural": None if row is None else ROLE_PT.get(row["papel"], "—")})
    return out


def probable_xi(lineups: pd.DataFrame, squad: pd.DataFrame, formation: str, last_n: int = 5) -> Tuple[List[Dict], Dict]:
    """
    Escalação provável: atletas do elenco que mais começaram jogando nos últimos `last_n` jogos (`lineups` com
    colunas data, jogador, titular). Quem mais começou entra com prioridade; o encaixe nas vagas segue best_xi.
    """
    info = {"jogos_considerados": 0, "titulares_frequentes": {}}
    if lineups is None or lineups.empty:
        return best_xi(squad, formation), info
    lu = lineups[lineups["titular"] == 1]
    games = sorted(lu["jogo"].unique(), key=lambda g: lu.loc[lu["jogo"] == g, "data"].max(), reverse=True)[:last_n]
    lu = lu[lu["jogo"].isin(games)]
    info["jogos_considerados"] = len(games)
    freq = lu.groupby("jogador")["jogo"].nunique().sort_values(ascending=False)
    info["titulares_frequentes"] = {k: int(v) for k, v in freq.head(16).items()}
    from src.data_lake.ids import player_core

    fcore = {player_core(k): v for k, v in freq.items()}
    # quem começou jogando vem antes da nota: 150 pontos × fração dos jogos como titular
    bonus = {n: 150.0 * fcore.get(player_core(n), 0) / max(len(games), 1) for n in squad["nome"]}
    return best_xi(squad, formation, bonus=bonus), info


# ------------------------------------------------------------------------------------------------ perfil do time
FOR_METRICS = [  # chave, rótulo, maior é melhor?
    ("goals", "Gols marcados", True), ("shots_total", "Finalizações", True), ("shots_on_target", "Finalizações no gol", True),
    ("xg", "xG criado", True), ("big_chances", "Grandes chances", True), ("possession_pct", "Posse de bola (%)", True),
    ("passes_total", "Passes", True), ("pass_accuracy_pct", "Precisão de passe (%)", True),
    ("crosses_total", "Cruzamentos", True), ("corners", "Escanteios", True), ("dribbles_completed", "Dribles certos", True),
    ("aerials_won", "Duelos aéreos ganhos", True), ("tackles_won", "Desarmes certos", True),
    ("interceptions", "Interceptações", True), ("fouls", "Faltas cometidas", False), ("yellow_cards", "Cartões amarelos", False),
]
AGAINST_METRICS = [
    ("goals", "Gols sofridos", False), ("shots_total", "Finalizações cedidas", False),
    ("shots_on_target", "Finalizações no gol cedidas", False), ("xg", "xG cedido", False),
    ("crosses_total", "Cruzamentos cedidos", False), ("corners", "Escanteios cedidos", False),
    ("big_chances", "Grandes chances cedidas", False),
]


MIN_STAT_KEYS = 5        # estatísticas distintas no jogo (dos dois times) para contar como "dado completo"
RECENT_DAYS = 400        # não usa jogo de mais de ~1 temporada antes do mais recente


def team_profile(matches: pd.DataFrame, stats: pd.DataFrame, team_names: Sequence[str],
                 baseline: Optional[Dict[str, float]] = None, last_n: int = 5,
                 min_stat_keys: int = MIN_STAT_KEYS) -> Dict[str, Any]:
    """
    `matches`: catálogo (match_id, match_date, home/away_team_name, home/away_score) já filtrado para o time.
    `stats`: match_team_stats (match_id, team_name, stat_key, value) desses jogos.
    Devolve médias "a favor" e "contra" nos últimos `last_n` jogos COM estatística e a comparação com a média de
    referência (mesmas competições e período), em % acima/abaixo.
    """
    names = set(team_names)
    m = matches.sort_values("match_date", ascending=False)
    # v36: só jogos RECENTES e com dado COMPLETO (lances, ou estatísticas com pelo menos MIN_STAT_KEYS indicadores
    # para o time) — jogo com 2 números soltos não define o perfil de ninguém
    rich = set()
    if stats is not None and not stats.empty:
        per = stats.groupby("match_id")["stat_key"].nunique()
        rich = set(per[per >= min_stat_keys].index)
    lvl = m["data_level"] if "data_level" in m else pd.Series("", index=m.index)
    ok = m["match_id"].isin(rich) | ((lvl == "EVENTS") & m["match_id"].isin(set(stats["match_id"]) if stats is not None
                                                                              and not stats.empty else set()))
    skipped = int((~ok).sum())
    m = m[ok]
    if not m.empty:
        newest = pd.to_datetime(m["match_date"], errors="coerce").max()
        m = m[pd.to_datetime(m["match_date"], errors="coerce") >= newest - pd.Timedelta(days=RECENT_DAYS)]
    m = m.head(last_n)
    rows_for, rows_against, games = [], [], []
    for r in m.itertuples():
        home = r.home_team_name in names
        s = stats[stats["match_id"] == r.match_id]
        mine = s[s["team_name"].isin(names)]
        other = s[~s["team_name"].isin(names)]
        f = dict(zip(mine["stat_key"], mine["value"]))
        a = dict(zip(other["stat_key"], other["value"]))
        gf, ga = (r.home_score, r.away_score) if home else (r.away_score, r.home_score)
        f["goals"], a["goals"] = gf, ga
        rows_for.append(f)
        rows_against.append(a)
        games.append({"data": r.match_date, "adversario": r.away_team_name if home else r.home_team_name,
                      "placar": f"{gf}–{ga}", "mando": "casa" if home else "fora", "match_id": int(r.match_id)})
    F, A = pd.DataFrame(rows_for), pd.DataFrame(rows_against)
    out: Dict[str, Any] = {"jogos": games, "n": len(games), "a_favor": {}, "contra": {},
                           "descartados_por_dado_incompleto": skipped,
                           "criterio": f"últimos jogos com lances ou ≥ {min_stat_keys} estatísticas no jogo, "
                                       f"até {RECENT_DAYS} dias antes do mais recente"}
    def per_game(frame, key):
        vals = pd.to_numeric(frame[key], errors="coerce") if key in frame else pd.Series(dtype=float)
        return [{"match_id": g["match_id"], "data": g["data"], "adversario": g["adversario"], "placar": g["placar"],
                 "valor": round(float(v), 2)} for g, v in zip(games, vals) if pd.notna(v)]
    for key, lab, up in FOR_METRICS:
        if key in F and F[key].notna().sum():
            v = float(pd.to_numeric(F[key], errors="coerce").mean())
            b = (baseline or {}).get(key)
            out["a_favor"][key] = {"rotulo": lab, "media": round(v, 2), "referencia": round(b, 2) if b else None,
                                   "dif_pct": round((v - b) / b * 100, 0) if b else None, "maior_melhor": up,
                                   "jogos": int(F[key].notna().sum()), "por_jogo": per_game(F, key)}
    for key, lab, up in AGAINST_METRICS:
        if key in A and A[key].notna().sum():
            v = float(pd.to_numeric(A[key], errors="coerce").mean())
            b = (baseline or {}).get(key)
            out["contra"][key] = {"rotulo": lab, "media": round(v, 2), "referencia": round(b, 2) if b else None,
                                  "dif_pct": round((v - b) / b * 100, 0) if b else None, "maior_melhor": up,
                                  "jogos": int(A[key].notna().sum()), "por_jogo": per_game(A, key)}
    return out


def deep_tactical_signals(profile: Dict[str, Any], min_games: int = 3) -> List[Dict[str, Any]]:
    """Indicadores derivados por partida: separam volume, qualidade e variabilidade sem inventar tracking."""
    def series(side: str, key: str) -> Dict[int, float]:
        d = profile.get(side, {}).get(key) or {}
        out = {}
        for row in d.get("por_jogo", []):
            try:
                value = float(row["valor"])
                if np.isfinite(value):
                    out[int(row["match_id"])] = value
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def paired_ratio(side: str, numerator: str, denominator: str):
        a, b = series(side, numerator), series(side, denominator)
        vals = [a[mid] / b[mid] for mid in a.keys() & b.keys() if b[mid] > 0]
        return vals if len(vals) >= min_games else []

    signals: List[Dict[str, Any]] = []
    for side, label in (("a_favor", "produção própria"), ("contra", "produção cedida")):
        ratios = paired_ratio(side, "xg", "shots_total")
        if ratios:
            avg = float(np.mean(ratios))
            signals.append({
                "titulo": "Qualidade média das finalizações" if side == "a_favor" else "Perigo médio por chute sofrido",
                "valor": avg, "unidade": "xG/chute", "jogos": len(ratios),
                "leitura": ("A equipe gera mais perigo por tentativa; volume e qualidade estão separados."
                            if side == "a_favor" else
                            "Cada finalização permitida carrega este nível médio de ameaça; não basta contar chutes."),
                "evidencia": f"Média por jogo de xG ÷ finalizações — {label}.",
            })
    goals, xg = series("a_favor", "goals"), series("a_favor", "xg")
    common = goals.keys() & xg.keys()
    if len(common) >= min_games:
        delta = float(np.mean([goals[k] - xg[k] for k in common]))
        signals.append({
            "titulo": "Saldo de gols em relação ao xG", "valor": delta, "unidade": "gol/jogo",
            "jogos": len(common),
            "leitura": ("Finalizou acima do xG no recorte; isso pode refletir execução, variância ou qualidade dos goleiros."
                        if delta > 0.15 else "Converteu abaixo do xG no recorte; não prova, isoladamente, problema de finalização."
                        if delta < -0.15 else "Conversão próxima ao volume de chances esperado."),
            "evidencia": "Média de gols − xG, pareada jogo a jogo.",
        })
    conceded = series("contra", "xg")
    if len(conceded) >= min_games and np.mean(list(conceded.values())) > 0:
        vals = np.asarray(list(conceded.values()), dtype=float)
        cv = float(np.std(vals, ddof=0) / np.mean(vals))
        signals.append({
            "titulo": "Instabilidade do perigo cedido", "valor": cv, "unidade": "CV", "jogos": len(vals),
            "leitura": ("O perigo cedido oscila bastante entre partidas; a média esconde jogos muito vulneráveis."
                        if cv >= 0.55 else "O perigo cedido é relativamente estável no recorte."),
            "evidencia": "Desvio-padrão ÷ média do xG cedido por partida.",
        })
    return signals


def _traits(profile: Dict[str, Any], threshold: float = 12.0) -> Tuple[List[Dict], List[Dict]]:
    """Pontos fortes e fracos: diferença contra a referência acima do limite, no sentido que importa."""
    good, bad = [], []
    for side in ("a_favor", "contra"):
        for k, d in profile.get(side, {}).items():
            if d.get("dif_pct") is None or d["jogos"] < min(3, profile.get("n", 0)):
                continue
            better = d["dif_pct"] if d["maior_melhor"] else -d["dif_pct"]
            item = {"lado": side, "chave": k, **d}
            if better >= threshold:
                good.append(item)
            elif better <= -threshold:
                bad.append(item)
    key = lambda d: -abs(d["dif_pct"])
    return sorted(good, key=key), sorted(bad, key=key)


# leitura em linguagem de futebol (D3): sem "zona 14" nem "setor B3"
TRAIT_TEXT = {
    ("a_favor", "crosses_total"): ("vive de cruzamento pelos corredores", "quase não cruza: joga por dentro"),
    ("a_favor", "possession_pct"): ("gosta de ficar com a bola e empurrar o rival para o bloco baixo",
                                    "abre mão da bola: bloco baixo e saída rápida"),
    ("a_favor", "shots_total"): ("finaliza muito, inclusive de fora da área", "finaliza pouco"),
    ("a_favor", "shots_on_target"): ("acerta o gol com frequência", "erra muito o alvo"),
    ("a_favor", "xg"): ("cria chances claras, com homem entre linhas chegando à área", "cria pouco perigo de verdade"),
    ("a_favor", "dribbles_completed"): ("ganha no 1x1 pelos lados", "quase não dribla: depende do passe"),
    ("a_favor", "corners"): ("força muitos escanteios", "chega pouco à linha de fundo"),
    ("a_favor", "aerials_won"): ("domina o jogo aéreo", "perde as bolas pelo alto"),
    ("a_favor", "tackles_won"): ("desarma bem no meio-campo", "desarma pouco: a marcação chega atrasada"),
    ("a_favor", "interceptions"): ("lê bem as linhas de passe", "intercepta pouco"),
    ("a_favor", "pass_accuracy_pct"): ("troca passes com precisão desde a saída", "erra passes na saída de bola"),
    ("a_favor", "passes_total"): ("toca muito a bola", "troca poucos passes, jogo direto"),
    ("a_favor", "fouls"): ("faz poucas faltas", "comete muitas faltas"),
    ("a_favor", "yellow_cards"): ("é disciplinado", "leva muitos amarelos"),
    ("a_favor", "goals"): ("marca muitos gols", "marca pouco"),
    ("a_favor", "big_chances"): ("cria grandes chances", "quase não cria grandes chances"),
    ("contra", "shots_total"): ("cede poucas finalizações", "deixa o rival finalizar muito"),
    ("contra", "shots_on_target"): ("raramente leva chute no gol", "o goleiro é muito exigido"),
    ("contra", "xg"): ("concede poucas chances claras", "concede chances claras, com espaço entre zagueiro e lateral"),
    ("contra", "crosses_total"): ("não deixa cruzar", "deixa cruzar à vontade pelos corredores"),
    ("contra", "corners"): ("cede poucos escanteios", "cede muitos escanteios"),
    ("contra", "goals"): ("sofre poucos gols", "sofre muitos gols"),
    ("contra", "big_chances"): ("cede poucas grandes chances", "cede grandes chances"),
}


def rival_diagnosis(profile: Dict[str, Any], min_each: int = 2) -> Dict[str, Any]:
    """
    D4 — diagnóstico do rival com pelo menos 2 fortalezas e 2 vulnerabilidades, cada uma com o número que a sustenta
    (média vs referência) e a partida de origem (o jogo em que aquilo mais apareceu). Sem 2+2, declara base insuficiente.
    """
    good, bad = _traits(profile, threshold=8.0)

    def item(d, strong):
        pj = d.get("por_jogo") or []
        better_high = d["maior_melhor"] == strong
        g = (max if better_high else min)(pj, key=lambda x: x["valor"]) if pj else None
        txt = TRAIT_TEXT.get((d["lado"], d["chave"]), (d["rotulo"], d["rotulo"]))[0 if strong else 1]
        return {"texto": txt, "rotulo": d["rotulo"], "media": d["media"], "referencia": d["referencia"],
                "dif_pct": d["dif_pct"], "jogos": d["jogos"],
                "origem": (f"{g['data']} contra {g['adversario']} ({g['placar']}): {d['rotulo'].lower()} {g['valor']}"
                           if g else "—"), "match_id": g["match_id"] if g else None}
    fortes = [item(d, True) for d in good[:3]]
    fracos = [item(d, False) for d in bad[:3]]
    ok = len(fortes) >= min_each and len(fracos) >= min_each
    return {"fortalezas": fortes, "vulnerabilidades": fracos, "suficiente": ok, "jogos": profile.get("n", 0),
            "aviso": "" if ok else "base insuficiente para diagnóstico (são precisos 2 pontos fortes e 2 fracos "
                                   "claros em jogos recentes com escalação ou lances)"}


# regras de jogo: (lado, chave) → (como neutralizar se é força do rival, como explorar se é fraqueza do rival)
RULES = {
    ("a_favor", "crosses_total"): ("Proteger a área contra cruzamentos: zagueiros fortes no alto e laterais fechando o "
                                   "cruzamento antes da linha de fundo.", None),
    ("a_favor", "possession_pct"): ("Rival gosta da bola: bloco médio compacto, fechar o volante e acelerar a transição "
                                    "quando recuperar.", None),
    ("a_favor", "shots_total"): ("Rival finaliza muito: encurtar a entrada da área e não dar o chute de fora livre.", None),
    ("a_favor", "xg"): ("Rival cria chances de qualidade: defender a área central e acompanhar a infiltração.", None),
    ("a_favor", "dribbles_completed"): ("Rival vence no 1x1: dobrar a marcação nos pontas e não dar o bote sozinho.", None),
    ("a_favor", "corners"): ("Rival força escanteios: organizar a bola parada defensiva e evitar o corte para fora.", None),
    ("a_favor", "aerials_won"): ("Rival forte no jogo aéreo: evitar bola longa sem segunda bola e marcar o pivô.", None),
    ("a_favor", "tackles_won"): ("Rival desarma bem: menos condução no meio, mais passe de primeira e troca de lado.", None),
    ("a_favor", "pass_accuracy_pct"): ("Rival troca passes com precisão: pressionar o primeiro passe e fechar o pivô.", None),
    ("contra", "shots_total"): (None, "Rival cede muitas finalizações: chegar à área com volume e finalizar mais."),
    ("contra", "xg"): (None, "Rival cede chances claras: atacar o espaço entre zagueiros e lateral com infiltração."),
    ("contra", "crosses_total"): (None, "Rival deixa cruzar: abrir o jogo e atacar pelos lados com cruzamento."),
    ("contra", "corners"): (None, "Rival cede muitos escanteios: preparar jogadas ensaiadas de bola parada."),
    ("contra", "goals"): (None, "Rival sofre muitos gols: ser agressivo desde o início."),
    ("contra", "shots_on_target"): (None, "Goleiro do rival é muito exigido: finalizar no gol, com variação."),
    ("a_favor", "pass_accuracy_pct", "fraco"): (None, "Rival erra na saída: pressão alta no primeiro passe."),
    ("a_favor", "fouls", "fraco"): (None, "Rival faz muitas faltas: atacar no 1x1 perto da área e buscar bola parada."),
    ("a_favor", "yellow_cards", "fraco"): (None, "Rival leva muitos amarelos: provocar o duelo com o jogador já advertido."),
    ("a_favor", "possession_pct", "fraco"): (None, "Rival fica pouco com a bola: ter paciência, girar e cansar a marcação."),
    ("a_favor", "tackles_won", "fraco"): (None, "Rival desarma pouco: conduzir e driblar no meio-campo."),
    ("a_favor", "aerials_won", "fraco"): (None, "Rival perde no alto: usar o pivô e a bola longa na segunda trave."),
}
OUR_FOR_EXPLOIT = {  # nosso ponto forte que ataca cada fraqueza do rival
    ("contra", "crosses_total"): "crosses_total", ("contra", "corners"): "corners", ("contra", "shots_total"): "shots_total",
    ("contra", "xg"): "xg", ("a_favor", "fouls"): "dribbles_completed", ("a_favor", "aerials_won"): "aerials_won",
    ("a_favor", "pass_accuracy_pct"): "tackles_won", ("a_favor", "tackles_won"): "dribbles_completed",
}


def matchup_plan(ours: Dict[str, Any], theirs: Dict[str, Any], our_name: str, their_name: str) -> Dict[str, Any]:
    """Plano de jogo: o que neutralizar (forças do rival), o que explorar (fraquezas dele) e com qual força nossa."""
    t_good, t_bad = _traits(theirs)
    o_good, o_bad = _traits(ours)
    our_good_keys = {(d["lado"], d["chave"]) for d in o_good}
    neutral, exploit = [], []
    for d in t_good:
        rule = RULES.get((d["lado"], d["chave"]))
        if rule and rule[0]:
            neutral.append({**d, "acao": rule[0]})
    for d in t_bad:
        rule = RULES.get((d["lado"], d["chave"])) or RULES.get((d["lado"], d["chave"], "fraco"))
        if not rule or not rule[1]:
            continue
        ours_key = OUR_FOR_EXPLOIT.get((d["lado"], d["chave"]))
        ally = next((g for g in o_good if g["lado"] == "a_favor" and g["chave"] == ours_key), None)
        exploit.append({**d, "acao": rule[1], "nossa_forca": ally})
    exploit.sort(key=lambda d: (d["nossa_forca"] is None, -abs(d["dif_pct"])))
    return {"neutralizar": neutral[:5], "explorar": exploit[:5], "nossos_fortes": o_good[:5], "nossos_fracos": o_bad[:5],
            "rival_fortes": t_good[:6], "rival_fracos": t_bad[:6], "jogos_rival": theirs.get("n", 0),
            "jogos_nossos": ours.get("n", 0), "nos": our_name, "rival": their_name}


def plan_bonus(squad: pd.DataFrame, plan: Dict[str, Any]) -> Tuple[Dict[str, float], List[str]]:
    """Ajuste da escalação ao adversário: pontos extras explicáveis, baseados só no perfil do elenco."""
    bonus: Dict[str, float] = {}
    why: List[str] = []
    keys = {(d["lado"], d["chave"]) for d in plan.get("neutralizar", [])} | \
           {(d["lado"], d["chave"]) for d in plan.get("explorar", [])}
    h = pd.to_numeric(squad.get("altura_cm"), errors="coerce")
    if ("a_favor", "crosses_total") in keys or ("a_favor", "aerials_won") in keys:
        for n, role, hh in zip(squad["nome"], squad["papel"], h):
            if role == "CB" and pd.notna(hh) and hh >= 188:
                bonus[n] = bonus.get(n, 0) + 6
        why.append("rival cruza/ganha muito no alto → zagueiros de 1,88 m ou mais ganham prioridade")
    if ("a_favor", "aerials_won") in keys and ("a_favor", "aerials_won") in {(d["lado"], d["chave"]) for d in plan.get("explorar", [])}:
        for n, role, hh in zip(squad["nome"], squad["papel"], h):
            if role == "ST" and pd.notna(hh) and hh >= 186:
                bonus[n] = bonus.get(n, 0) + 6
        why.append("rival perde no alto → centroavante alto ganha prioridade")
    if ("a_favor", "possession_pct") in keys:
        for n, role in zip(squad["nome"], squad["papel"]):
            if role == "DM":
                bonus[n] = bonus.get(n, 0) + 4
        why.append("rival tem muita posse → volantes de origem ganham prioridade")
    if ("contra", "crosses_total") in keys:
        for n, role in zip(squad["nome"], squad["papel"]):
            if role in ("LW", "RW", "LB", "RB", "LWB", "RWB", "LM", "RM"):
                bonus[n] = bonus.get(n, 0) + 3
        why.append("rival deixa cruzar → jogadores de lado ganham prioridade")
    if ("a_favor", "dribbles_completed") in keys:
        for n, role, age in zip(squad["nome"], squad["papel"], squad.get("idade", pd.Series(dtype=float))):
            if role in ("LB", "RB", "LWB", "RWB") and pd.notna(age) and age <= 29:
                bonus[n] = bonus.get(n, 0) + 3
        why.append("rival dribla muito → laterais mais jovens (mais fôlego para o 1x1) ganham prioridade")
    return bonus, why


def lineup_from_lineups_table(lu: pd.DataFrame, game_col: str, date_col: str, name_col: str, starter_col: str,
                              starter_value: Any = 1) -> pd.DataFrame:
    """Normaliza qualquer tabela de escalações para (jogo, data, jogador, titular)."""
    if lu is None or lu.empty:
        return pd.DataFrame(columns=["jogo", "data", "jogador", "titular"])
    return pd.DataFrame({"jogo": lu[game_col], "data": lu[date_col].astype(str), "jogador": lu[name_col],
                         "titular": (lu[starter_col] == starter_value).astype(int)})
