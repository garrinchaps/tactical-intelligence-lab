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
    for c in ("funcao", "posicao", "nascimento", "altura_cm", "pe", "valor_mercado_eur", "transfermarkt_id", "nota_manual"):
        if c not in df:
            df[c] = None
    df["papel"] = [natural_role(f, p) for f, p in zip(df["funcao"], df["posicao"])]
    df["idade"] = df["nascimento"].map(lambda b: age_on(b, ref))
    df = df.drop_duplicates(subset=["nome"], keep="last").reset_index(drop=True)
    return df


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
               usage: Optional[pd.DataFrame] = None, external: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Nota do laboratório (0–100) — uma estimativa declarada, não a nota de um olheiro:
      valor   — percentil do valor de mercado (escala log) entre atletas da MESMA função na referência (peso 0,55);
      uso     — percentil dos minutos na temporada no próprio elenco + participação em gols por 90 para meias e
                atacantes (peso 0,30);
      externa — nota de fonte externa (ex.: Simonetti) já em 0–100, quando o nome bate (peso 0,15, ou mais
                quando é a única base);
      manual  — nota digitada por você ao adicionar o atleta substitui tudo.
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
    if external is not None and not external.empty:
        from src.data_lake.ids import player_core

        ext = external.assign(_c=external["nome"].map(player_core)).drop_duplicates("_c").set_index("_c")["nota"]
        comps["externa"] = df["nome"].map(player_core).map(ext).astype(float)
    weights = {"valor": 0.55, "uso": 0.30, "externa": 0.15}
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


def team_profile(matches: pd.DataFrame, stats: pd.DataFrame, team_names: Sequence[str],
                 baseline: Optional[Dict[str, float]] = None, last_n: int = 5) -> Dict[str, Any]:
    """
    `matches`: catálogo (match_id, match_date, home/away_team_name, home/away_score) já filtrado para o time.
    `stats`: match_team_stats (match_id, team_name, stat_key, value) desses jogos.
    Devolve médias "a favor" e "contra" nos últimos `last_n` jogos COM estatística e a comparação com a média de
    referência (mesmas competições e período), em % acima/abaixo.
    """
    names = set(team_names)
    m = matches.sort_values("match_date", ascending=False)
    with_stats = set(stats["match_id"].unique()) if stats is not None and not stats.empty else set()
    m = m[m["match_id"].isin(with_stats)].head(last_n)
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
    out: Dict[str, Any] = {"jogos": games, "n": len(games), "a_favor": {}, "contra": {}}
    for key, lab, up in FOR_METRICS:
        if key in F and F[key].notna().sum():
            v = float(pd.to_numeric(F[key], errors="coerce").mean())
            b = (baseline or {}).get(key)
            out["a_favor"][key] = {"rotulo": lab, "media": round(v, 2), "referencia": round(b, 2) if b else None,
                                   "dif_pct": round((v - b) / b * 100, 0) if b else None, "maior_melhor": up,
                                   "jogos": int(F[key].notna().sum())}
    for key, lab, up in AGAINST_METRICS:
        if key in A and A[key].notna().sum():
            v = float(pd.to_numeric(A[key], errors="coerce").mean())
            b = (baseline or {}).get(key)
            out["contra"][key] = {"rotulo": lab, "media": round(v, 2), "referencia": round(b, 2) if b else None,
                                  "dif_pct": round((v - b) / b * 100, 0) if b else None, "maior_melhor": up,
                                  "jogos": int(A[key].notna().sum())}
    return out


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
