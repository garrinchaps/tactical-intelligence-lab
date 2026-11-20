"""
Rodada 22 — IDENTIDADE TÁTICA da equipe (e do treinador): como o time se organiza com e sem a bola, como sai jogando,
progride, finaliza, pressiona, se defende e reage nas transições — com a FONTE e a CONFIANÇA de cada afirmação.

Duas camadas, nunca misturadas sem aviso:

1. LANCES com coordenadas (StatsBomb/Wyscout/OpenPlay, 120×80, cada time atacando para a direita):
   * desenho por FASE: posições médias de cada titular nas ações COM bola e nas ações defensivas; as linhas saem dos
     vãos entre as posições médias ("em posse ~3-2-5"); saída com 3 (quem recua: volante entre os zagueiros ou lateral
     que fica), laterais por dentro/alto;
   * saída de bola (tiro de meta/goleiro curto × longo; posses que nascem no terço defensivo e chegam ao último terço),
     progressão por corredor, último terço (cruzamentos, entradas na área), ritmo (passes por posse, velocidade direta);
   * sem bola: PPDA REAL (passes do rival no campo dele ÷ nossas ações defensivas ali), altura do bloco (onde acontecem
     as nossas ações defensivas, em metros do próprio gol), % de ações no terço ofensivo (pressão alta), roubadas no
     ataque; transições: contra-ataques feitos e sofridos (finalização até 15 s depois da recuperação/perda).
   Sem tracking, NÃO afirmamos linha de impedimento contínua nem compactação — só onde as ações aconteceram.

2. ESTATÍSTICAS por jogo (FotMob/ESPN, dezenas de milhares de jogos) — APROXIMAÇÕES declaradas:
   posse, % de bolas longas, cruzamentos, onde finaliza, toques na área, bola parada; PPDA APROXIMADO (passes do rival
   no campo inteiro ÷ desarmes + interceptações + faltas); desenho pela escalação da fonte (não por fase).

Consistência: a mesma leitura em 1/3/5/10/20 jogos, casa × fora, vitórias × não vitórias, contra fortes × fracos;
TREINADOR: os jogos são separados pelo técnico da escalação (quando a fonte traz), e cada período tem a sua identidade.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

YARD_M = 0.9144
LANES = [("corredor esquerdo", -5, 16), ("meio-espaço esquerdo", 16, 30), ("corredor central", 30, 50),
         ("meio-espaço direito", 50, 64), ("corredor direito", 64, 85)]
ON_BALL = {"Pass", "Carry", "Ball Receipt*", "Dribble", "Shot"}
DEF_PPDA = {"Duel", "Interception", "Foul Committed", "Tackle"}
DEF_ALL = {"Duel", "Interception", "Ball Recovery", "Block", "Clearance", "Foul Committed", "Pressure"}
WINDOWS = (1, 3, 5, 10, 20)


def _lane(y: float) -> str:
    for name, lo, hi in LANES:
        if lo <= y < hi:
            return name
    return "corredor central"


def _conf(n: int, good: int = 10, ok: int = 4) -> str:
    return "alta" if n >= good else "média" if n >= ok else "baixa"


# ================================================================== camada 1: lances
def _starters(ev: pd.DataFrame, team: str) -> List[str]:
    """Titulares = jogadores do time com ação antes da 1ª substituição (ou os 11 com mais ações)."""
    t = ev[ev["team_name"] == team]
    subs = t[t["type_name"] == "Substitution"]
    cut = subs["index_num"].min() if not subs.empty and "index_num" in t else None
    early = t if cut is None or pd.isna(cut) else t[t["index_num"] < cut]
    names = early["player_name"].dropna().value_counts()
    return names.index[:11].tolist()


def _fmt_formation(raw: Any) -> Optional[str]:
    """'433.0' / '4231' / '4-2-3-1' → '4-3-3' / '4-2-3-1'."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    t = str(raw).split(".")[0].replace("-", "").strip()
    return "-".join(t) if t.isdigit() and 2 <= len(t) <= 5 else (str(raw) or None)


def _lines(xs: List[float], k: int = 3) -> List[int]:
    """Posições médias (x, sem goleiro) → jogadores por linha, de trás para frente, cortando nos k−1 MAIORES vãos
    (k = número de linhas do desenho da fonte). Assim o mesmo time pode aparecer 3-2-5 com bola e 4-4-2 sem bola."""
    xs = sorted(x for x in xs if pd.notna(x))
    if len(xs) < 2:
        return [len(xs)] if xs else []
    k = int(np.clip(k, 2, min(5, len(xs))))
    gaps = np.diff(xs)
    cuts = sorted(np.argsort(gaps)[::-1][: k - 1])
    out, start = [], 0
    for c in cuts:
        out.append(int(c + 1 - start))
        start = c + 1
    out.append(len(xs) - start)
    return out


def _three_lines(xs: List[float], band: float = 9.0) -> List[int]:
    """Leitura robusta (posições MÉDIAS do jogo, sem tracking): quantos ficam na linha de trás (até `band` jardas do
    mais recuado), quantos na linha da frente (até `band` do mais avançado) e quantos entre elas → ex. 3-2-5."""
    xs = [x for x in xs if pd.notna(x)]
    if len(xs) < 3:
        return [len(xs)]
    lo, hi = min(xs), max(xs)
    back = [x for x in xs if x <= lo + band]
    front = [x for x in xs if x >= hi - band and x > lo + band]
    return [len(back), len(xs) - len(back) - len(front), len(front)]


def shape_lines(xs: List[float], k: Optional[int] = None) -> List[int]:
    """Rodada 24 — linhas do desenho por agrupamento ÓTIMO em 1 dimensão (k-médias exato por programação dinâmica):
    corta as posições médias onde a soma das distâncias ao centro de cada linha é mínima. Antes a regra de "9 jardas do
    mais recuado/avançado" virava 1-9-1 quando um jogador ficava muito atrás ou muito à frente.
    k = número de linhas do desenho da fonte (4-2-3-1 → 4); sem fonte, testa 3 e 4 linhas e só usa 4 quando a 4ª linha
    explica muito mais (custo cai ≥ 70%). Linha de trás e da frente com ao menos 1; linha de trás com ao menos 2 quando
    há 10 jogadores de linha."""
    xs = sorted(float(x) for x in xs if pd.notna(x))
    n = len(xs)
    if n >= 11:                                        # sobrou o goleiro: o mais recuado sai
        xs = xs[1:]
        n -= 1
    if n < 3:
        return [n] if n else []
    pre = np.concatenate([[0.0], np.cumsum(xs)])
    pre2 = np.concatenate([[0.0], np.cumsum(np.square(xs))])

    def cost(i, j):                                    # variância (soma) do trecho xs[i:j]
        m = j - i
        s = pre[j] - pre[i]
        return (pre2[j] - pre2[i]) - s * s / m

    min_back = 3 if n >= 10 else 1

    def solve(kk):
        INF = float("inf")
        dp = np.full((kk + 1, n + 1), INF)
        cut = np.zeros((kk + 1, n + 1), dtype=int)
        dp[0, 0] = 0.0
        for c in range(1, kk + 1):
            for j in range(c, n + 1):
                for i in range(c - 1, j):
                    if c == 1 and j - i < min_back:
                        continue
                    v = dp[c - 1, i] + cost(i, j)
                    if v < dp[c, j]:
                        dp[c, j], cut[c, j] = v, i
        sizes, j = [], n
        for c in range(kk, 0, -1):
            i = cut[c, j]
            sizes.append(j - i)
            j = i
        return float(dp[kk, n]), sizes[::-1]
    if k:
        k = int(np.clip(k, 2, min(5, n)))
        sizes = solve(k)[1]
    else:
        c3, s3 = solve(3)
        c4, s4 = solve(4) if n >= 4 else (c3, s3)
        sizes = s4 if c3 > 0 and c4 <= .3 * c3 else s3
    return [int(x) for x in sizes]


def phase_shapes(ev: pd.DataFrame, team: str) -> Dict[str, Any]:
    """Desenho com bola e sem bola de UM jogo, pelas posições médias dos titulares."""
    starters = _starters(ev, team)
    t = ev[(ev["team_name"] == team) & ev["player_name"].isin(starters) & ev["x"].notna()]
    if t.empty or len(starters) < 10:
        return {}
    pos = t.groupby("player_name")["position_name"].agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else "")
    gk = {p for p, n in pos.items() if "Goalkeeper" in str(n)}
    on = t[t["type_name"].isin(ON_BALL) & (t["possession_team_name"] == team)]
    off = t[t["type_name"].isin(DEF_ALL)]
    src_form = _fmt_formation(ev.loc[ev["team_name"] == team, "tactics_formation"].dropna().iloc[0]) \
        if "tactics_formation" in ev and ev.loc[ev["team_name"] == team, "tactics_formation"].notna().any() else None
    k = len(src_form.split("-")) if src_form else 3
    res: Dict[str, Any] = {}
    for key, d in (("com_bola", on), ("sem_bola", off)):
        avg = d[~d["player_name"].isin(gk)].groupby("player_name")[["x", "y"]].mean()
        if len(avg) < 8:
            continue
        lines = shape_lines(avg["x"].tolist(), k if src_form else None)
        res[key] = {"linhas": lines, "desenho": "-".join(str(n) for n in lines),
                    "posicoes": {p: (round(float(r.x), 1), round(float(r.y), 1), str(pos.get(p, ""))) for p, r in avg.iterrows()}}
    if "com_bola" in res:
        pp = res["com_bola"]["posicoes"]
        xs = sorted(v[0] for v in pp.values())
        deep = [p for p, v in pp.items() if v[0] <= xs[0] + 9]
        res["saida_com"] = len(deep)
        roles = [pp[p][2] for p in deep]
        if len(deep) == 3:
            if any("Defensive Midfield" in r or "Center Midfield" in r for r in roles):
                res["quem_recua"] = "volante recua entre os zagueiros"
            elif any("Back" in r and "Center" not in r for r in roles):
                res["quem_recua"] = "um lateral fica atrás (saída assimétrica)"
            else:
                res["quem_recua"] = "linha de 3 zagueiros"
        fbs = [v for v in pp.values() if ("Left Back" in v[2] or "Right Back" in v[2] or "Wing Back" in v[2])]
        mids = [v for v in pp.values() if "Midfield" in v[2]]
        if fbs and mids:
            res["laterais_altos"] = bool(np.mean([v[0] for v in fbs]) >= np.mean([v[0] for v in mids]) - 2)
            res["laterais_por_dentro"] = bool(np.mean([min(v[1], 80 - v[1]) for v in fbs]) >= 18)
    return res


def match_profile(ev: pd.DataFrame, team: str) -> Dict[str, Any]:
    """Números de estilo de UM jogo pelos lances (todos com o time atacando para a direita)."""
    if ev is None or ev.empty or "x" not in ev:
        return {}
    ev = ev.copy()
    teams = [t for t in ev["team_name"].dropna().unique() if t != team]
    if team not in set(ev["team_name"]) or not teams:
        return {}
    opp = teams[0]
    mine, theirs = ev[ev["team_name"] == team], ev[ev["team_name"] == opp]
    out: Dict[str, Any] = {"adversario": opp}
    # PPDA real: passes do rival no campo dele (x < 72 na visão dele) ÷ nossas ações defensivas na mesma área (x > 48)
    opp_pass = int(((theirs["type_name"] == "Pass") & (theirs["x"] < 72)).sum())
    def_act = int((mine["type_name"].isin(DEF_PPDA) & (mine["x"] > 48)).sum())
    out["ppda"] = round(opp_pass / def_act, 2) if def_act else None
    d_all = mine[mine["type_name"].isin(DEF_ALL) & mine["x"].notna()]
    out["altura_bloco_m"] = round(float(d_all["x"].median()) * YARD_M, 1) if len(d_all) >= 20 else None
    out["pct_acoes_def_ataque"] = round(100 * float((d_all["x"] >= 80).mean()), 1) if len(d_all) >= 20 else None
    rec = mine[mine["type_name"].isin({"Ball Recovery", "Interception"})]
    out["roubadas_terco_ofensivo"] = int((rec["x"] >= 80).sum())
    press = mine[mine["type_name"] == "Pressure"]
    out["pressoes"] = int(len(press))
    out["pct_pressao_alta"] = round(100 * float((press["x"] >= 72).mean()), 1) if len(press) >= 20 else None
    # saída de bola
    gk = mine[(mine["type_name"] == "Pass") & mine["position_name"].astype(str).str.contains("Goalkeeper")]
    if len(gk) >= 5:
        out["goleiro_longo_pct"] = round(100 * float((pd.to_numeric(gk["pass_length"], errors="coerce") >= 40).mean()), 1)
    passes = mine[mine["type_name"] == "Pass"]
    pl = pd.to_numeric(passes["pass_length"], errors="coerce")
    out["pct_passes_longos"] = round(100 * float((pl >= 35).mean()), 1) if len(passes) >= 50 else None
    # posses do time: nascem no terço defensivo e chegam ao último terço?
    poss = mine[(mine["possession_team_name"] == team) & mine["x"].notna()].groupby(["period", "possession"])
    starts = poss["x"].first()
    ends = poss.apply(lambda g: float(np.nanmax(pd.to_numeric(g["end_x"], errors="coerce").fillna(g["x"]).values)))
    deep = starts < 40
    out["posses_do_fundo"] = int(deep.sum())
    out["pct_fundo_ao_ultimo_terco"] = round(100 * float((ends[deep] >= 80).mean()), 1) if deep.sum() >= 10 else None
    npass = poss["type_name"].apply(lambda s: int((s == "Pass").sum()))
    out["passes_por_posse"] = round(float(npass.mean()), 2) if len(npass) else None
    # progressão por corredor: passes/conduções que terminam no último terço, pelo corredor onde terminam
    prog = mine[mine["type_name"].isin({"Pass", "Carry"}) & (pd.to_numeric(mine["end_x"], errors="coerce") >= 80)
                & (mine["x"] < 80)]
    if len(prog) >= 8:
        lanes = pd.to_numeric(prog["end_y"], errors="coerce").dropna().map(_lane).value_counts(normalize=True) * 100
        out["entradas_por_corredor"] = {k: round(float(v), 1) for k, v in lanes.items()}
    out["cruzamentos"] = int(pd.to_numeric(mine.get("is_pass_cross"), errors="coerce").fillna(0).astype(bool).sum()) \
        if "is_pass_cross" in mine else None
    ex, ey = pd.to_numeric(mine["end_x"], errors="coerce"), pd.to_numeric(mine["end_y"], errors="coerce")
    out["entradas_area"] = int((mine["type_name"].isin({"Pass", "Carry"}) & (ex >= 102) & ey.between(18, 62)
                                & ~((mine["x"] >= 102) & mine["y"].between(18, 62))).sum())
    # transições: finalização até 15 s depois de recuperar (contra-ataque) / de perder a bola (sofrido)
    out["contra_ataques"], out["contra_ataques_sofridos"] = _transitions(ev, team, opp)
    out["desenho_fase"] = phase_shapes(ev, team)
    form = mine["tactics_formation"].dropna() if "tactics_formation" in mine else pd.Series(dtype=object)
    out["desenho_fonte"] = _fmt_formation(form.iloc[0]) if not form.empty else None
    return out


def _transitions(ev: pd.DataFrame, team: str, opp: str, window: float = 15.0):
    if "time_seconds" not in ev:
        t = pd.to_numeric(ev.get("minute"), errors="coerce").fillna(0) * 60 + pd.to_numeric(ev.get("second"), errors="coerce").fillna(0)
        ev = ev.assign(time_seconds=t)
    rec_types = {"Ball Recovery", "Interception"}
    made = conceded = 0
    shots = ev[ev["type_name"] == "Shot"][["team_name", "period", "time_seconds"]]
    for side, other, attr in ((team, opp, "made"), (opp, team, "conc")):
        r = ev[(ev["team_name"] == side) & ev["type_name"].isin(rec_types)][["period", "time_seconds"]]
        s = shots[shots["team_name"] == side]
        n = 0
        for (per, ts) in r.itertuples(index=False):
            if ((s["period"] == per) & (s["time_seconds"] > ts) & (s["time_seconds"] <= ts + window)).any():
                n += 1
        if attr == "made":
            made = n
        else:
            conceded = n
    return made, conceded


def events_identity(db, names: Sequence[str], n: int = 10, match_ids: Optional[Sequence[int]] = None) -> Dict[str, Any]:
    """Média dos perfis por lances nos últimos `n` jogos COM lances do time."""
    if match_ids is None:
        ph = ",".join("?" * len(names))
        with db.connect() as conn:
            rows = conn.execute(f"SELECT match_id FROM matches WHERE data_level = 'EVENTS' AND (home_team_name IN ({ph}) "
                                f"OR away_team_name IN ({ph})) ORDER BY match_date DESC LIMIT {int(n)}",
                                list(names) * 2).fetchall()
        match_ids = [int(r[0]) for r in rows]
    profs = []
    for mid in match_ids:
        try:
            ev = db.load_events(int(mid))
        except Exception:
            continue
        if ev is None or ev.empty:
            continue
        team = next((t for t in ev["team_name"].dropna().unique() if t in set(names)), None)
        if team is None:
            continue
        p = match_profile(ev, team)
        if p:
            p["match_id"] = int(mid)
            profs.append(p)
    if not profs:
        return {"jogos": 0}
    num = ["ppda", "altura_bloco_m", "pct_acoes_def_ataque", "roubadas_terco_ofensivo", "pressoes", "pct_pressao_alta",
           "goleiro_longo_pct", "pct_passes_longos", "pct_fundo_ao_ultimo_terco", "passes_por_posse", "cruzamentos",
           "entradas_area", "contra_ataques", "contra_ataques_sofridos"]
    df = pd.DataFrame(profs)
    avg = {k: (round(float(pd.to_numeric(df[k], errors="coerce").mean()), 2) if k in df and pd.to_numeric(df[k], errors="coerce").notna().any() else None)
           for k in num}
    lanes = pd.DataFrame([p.get("entradas_por_corredor") or {} for p in profs]).mean().round(1).to_dict()
    shapes_on = [p["desenho_fase"].get("com_bola", {}).get("desenho") for p in profs if p.get("desenho_fase")]
    shapes_off = [p["desenho_fase"].get("sem_bola", {}).get("desenho") for p in profs if p.get("desenho_fase")]
    saida3 = [p["desenho_fase"].get("saida_com") == 3 for p in profs if p.get("desenho_fase")]
    recua = pd.Series([p["desenho_fase"].get("quem_recua") for p in profs if p.get("desenho_fase")]).dropna()
    last_pos = next((p["desenho_fase"] for p in profs if p.get("desenho_fase", {}).get("com_bola")), {})
    return {"jogos": len(profs), "medias": avg, "corredores": lanes,
            "desenho_com_bola": pd.Series([s for s in shapes_on if s]).mode().iloc[0] if any(shapes_on) else None,
            "desenho_sem_bola": pd.Series([s for s in shapes_off if s]).mode().iloc[0] if any(shapes_off) else None,
            "saida_com_3_pct": round(100 * float(np.mean(saida3)), 0) if saida3 else None,
            "quem_recua": recua.mode().iloc[0] if not recua.empty else None,
            "desenho_fonte": pd.Series([p.get("desenho_fonte") for p in profs]).dropna().mode().iloc[0]
            if any(p.get("desenho_fonte") for p in profs) else None,
            "posicoes_ultimo_jogo": last_pos, "confianca": _conf(len(profs), 8, 3)}


# ================================================================== camada 2: estatísticas (aproximações)
def _stats_profile(v: pd.DataFrame) -> Dict[str, Any]:
    """Médias por jogo a favor/contra + PPDA aproximado, de um conjunto de jogos (linhas de team_history._vectors)."""
    if v is None or v.empty:
        return {}
    g = lambda c: pd.to_numeric(v.get(c), errors="coerce") if c in v else pd.Series(np.nan, index=v.index)
    dfa = g("f_tackles_won").fillna(0) + g("f_interceptions").fillna(0) + g("f_fouls").fillna(0)
    ppda = (g("c_passes_total") / dfa.replace(0, np.nan))
    out = {"jogos": int(len(v)), "posse_pct": g("f_possession_pct").mean(), "pct_bolas_longas": g("f_pct_bolas_longas").mean(),
           "cruzamentos": g("f_crosses_total").mean(), "pct_dentro_area": g("f_pct_dentro_area").mean(),
           "toques_area": g("f_touches_opp_box").mean(), "xg": g("f_xg").mean(), "xg_contra": g("c_xg").mean(),
           "finalizacoes_contra_area": g("c_shots_inside_box").mean(), "ppda_aprox": ppda.mean(),
           "grandes_chances_contra": g("c_big_chances").mean(), "cruzamentos_contra": g("c_crosses_total").mean(),
           "pct_xg_bola_parada": g("f_pct_xg_bola_parada").mean()}
    return {k: (round(float(x), 2) if isinstance(x, (float, np.floating)) and np.isfinite(x) else (x if not isinstance(x, float) else None))
            for k, x in out.items()}


def _style_words(p: Dict[str, Any], ref: Dict[str, Any]) -> List[str]:
    """Rótulos de estilo pela comparação com a média das mesmas competições (só quando a diferença é clara)."""
    w = []
    def rel(k):
        a, b = p.get(k), ref.get(k)
        return (a - b) / abs(b) if a is not None and b not in (None, 0) else None
    r = rel("posse_pct")
    if r is not None:
        w.append("propõe o jogo (gosta da bola)" if r >= .10 else "reativo (abre mão da bola)" if r <= -.10 else "posse equilibrada")
    r = rel("pct_bolas_longas")
    if r is not None and r >= .2:
        w.append("jogo direto")
    r = rel("cruzamentos")
    if r is not None and r >= .2:
        w.append("ataque pelos lados com cruzamento")
    r = rel("ppda_aprox")
    if r is not None:
        w.append("pressiona alto (rival troca poucos passes)" if r <= -.15 else "marca mais atrás (deixa o rival trocar)" if r >= .15 else "")
    return [x for x in w if x]


def stats_identity(db, names: Sequence[str], n: int = 20) -> Dict[str, Any]:
    from src.analytics import team_history as TH

    m = TH._matches(db, list(names), n=n)
    v = TH._vectors(db, m, list(names))
    if v.empty:
        return {"jogos": 0}
    ref_raw = TH._reference(db, v["competition_name"].dropna().unique().tolist())
    ref = {}
    if not ref_raw.empty:
        rr = ref_raw.rename(columns=lambda c: c)
        ref = {"posse_pct": rr.get("possession_pct"), "pct_bolas_longas": rr.get("pct_bolas_longas"),
               "cruzamentos": rr.get("crosses_total"), "pct_dentro_area": rr.get("pct_dentro_area"),
               "toques_area": rr.get("touches_opp_box"), "xg": rr.get("xg")}
        ref = {k: float(pd.to_numeric(x, errors="coerce").mean()) for k, x in ref.items() if x is not None}
        # PPDA aproximado de referência: passes do rival ÷ ações defensivas, jogo a jogo nas mesmas competições
        try:
            w = ref_raw.copy()
            w["_def"] = (pd.to_numeric(w.get("tackles_won"), errors="coerce").fillna(0) + pd.to_numeric(w.get("interceptions"), errors="coerce").fillna(0)
                         + pd.to_numeric(w.get("fouls"), errors="coerce").fillna(0))
            opp_p = w.groupby("match_id")["passes_total"].transform("sum") - w["passes_total"]
            ref["ppda_aprox"] = float((opp_p / w["_def"].replace(0, np.nan)).mean())
        except Exception:
            pass
    home = v["home_team_name"].isin(names)
    gf = np.where(home, v["home_score"], v["away_score"]).astype(float)
    ga = np.where(home, v["away_score"], v["home_score"]).astype(float)
    v = v.assign(_home=home.values, _win=gf > ga)
    whole = _stats_profile(v)
    windows = {k: _stats_profile(v.head(k)) for k in WINDOWS if len(v) >= k}
    splits = {"casa": _stats_profile(v[v["_home"]]), "fora": _stats_profile(v[~v["_home"]]),
              "vitorias": _stats_profile(v[v["_win"]]), "sem_vitoria": _stats_profile(v[~v["_win"]])}
    # consistência: o rótulo principal aparece em quantas janelas?
    words_all = _style_words(whole, ref)
    consist = {}
    for wd in words_all:
        hits = sum(1 for k, p in windows.items() if k >= 3 and wd in _style_words(p, ref))
        tot = sum(1 for k in windows if k >= 3)
        consist[wd] = f"{hits}/{tot} recortes" if tot else "—"
    return {"jogos": int(len(v)), "perfil": whole, "referencia": {k: round(x, 2) for k, x in ref.items()},
            "estilo": words_all, "consistencia": consist, "janelas": windows, "recortes": splits,
            "periodo": [str(v["match_date"].min()), str(v["match_date"].max())], "confianca": _conf(len(v), 15, 6),
            "metodo": "estatísticas por jogo (FotMob/ESPN) — PPDA APROXIMADO (passes do rival no campo inteiro ÷ desarmes, "
                      "interceptações e faltas); não mede altura do bloco nem desenho por fase"}


# ================================================================== treinador e desenho da escalação
def coach_periods(db, names: Sequence[str], n: int = 60) -> List[Dict[str, Any]]:
    """Períodos por técnico (escalação da fonte). Cada período: jogos, datas, desenho mais usado e pontos por jogo."""
    ph = ",".join("?" * len(names))
    try:
        with db.connect() as conn:
            d = pd.read_sql_query(
                f"SELECT l.match_id, m.match_date, MAX(l.coach) AS coach, MAX(l.formation) AS formation, m.home_team_name, "
                f"m.home_score, m.away_score FROM match_lineups l JOIN matches m ON m.match_id = l.match_id "
                f"WHERE l.team_name IN ({ph}) GROUP BY l.match_id ORDER BY m.match_date DESC LIMIT {int(n)}", conn,
                params=list(names))
    except Exception:
        return []
    d = d[d["coach"].fillna("").astype(str).str.strip() != ""]
    if d.empty:
        return []
    d = d.sort_values("match_date")
    d["grp"] = (d["coach"] != d["coach"].shift()).cumsum()
    out = []
    for _, g in d.groupby("grp"):
        home = g["home_team_name"].isin(names)
        gf = np.where(home, g["home_score"], g["away_score"]).astype(float)
        ga = np.where(home, g["away_score"], g["home_score"]).astype(float)
        pts = np.where(gf > ga, 3, np.where(gf == ga, 1, 0))
        forms = g["formation"].dropna().astype(str)
        out.append({"treinador": str(g["coach"].iloc[0]), "de": str(g["match_date"].iloc[0])[:10],
                    "ate": str(g["match_date"].iloc[-1])[:10], "jogos": int(len(g)),
                    "desenho_mais_usado": forms.mode().iloc[0] if not forms.empty else None,
                    "desenhos": forms.value_counts().head(3).to_dict(),
                    "pontos_por_jogo": round(float(np.nanmean(pts)), 2) if len(pts) else None,
                    "match_ids": g["match_id"].astype(int).tolist()})
    return out[::-1]


# ================================================================== tudo junto
def identity(db, names: Sequence[str], n: int = 20) -> Dict[str, Any]:
    names = list(dict.fromkeys(names))
    st = stats_identity(db, names, n)
    evi = events_identity(db, names, min(n, 10))
    coaches = coach_periods(db, names)
    cur = coaches[0] if coaches else None
    return {"estatisticas": st, "lances": evi, "treinadores": coaches, "treinador_atual": cur,
            "resumo": summary_text(st, evi, cur)}


def summary_text(st: Dict[str, Any], evi: Dict[str, Any], coach: Optional[Dict[str, Any]]) -> List[str]:
    """Frases curtas em linguagem de futebol, cada uma com a base (fonte e jogos)."""
    out = []
    if coach:
        out.append(f"Com {coach['treinador']} ({coach['jogos']} jogos desde {coach['de']}): desenho mais usado "
                   f"{coach.get('desenho_mais_usado') or 'não informado'} · {coach.get('pontos_por_jogo')} pontos por jogo.")
    if st.get("jogos"):
        if st.get("estilo"):
            out.append("Estilo pelas estatísticas: " + ", ".join(st["estilo"]) + f" — {st['jogos']} jogos "
                       f"(confiança {st.get('confianca')}).")
        p = st.get("perfil") or {}
        if p.get("ppda_aprox") is not None:
            ref = (st.get("referencia") or {}).get("ppda_aprox")
            out.append(f"PPDA aproximado {p['ppda_aprox']:.1f}" + (f" (média das competições {ref:.1f})" if ref else "")
                       + " — quanto menor, mais o time pressiona; é aproximação pelo campo inteiro.")
    if evi.get("jogos"):
        m = evi.get("medias") or {}
        bits = []
        if evi.get("desenho_com_bola"):
            bits.append(f"com bola ~{evi['desenho_com_bola']}, sem bola ~{evi.get('desenho_sem_bola') or '?'}")
        if evi.get("saida_com_3_pct") is not None and evi["saida_com_3_pct"] >= 50:
            bits.append(f"sai com 3 em {evi['saida_com_3_pct']:.0f}% dos jogos ({evi.get('quem_recua') or 'linha de 3'})")
        if m.get("ppda") is not None:
            bits.append(f"PPDA real {m['ppda']:.1f}")
        if m.get("altura_bloco_m") is not None:
            bits.append(f"bloco a ~{m['altura_bloco_m']:.0f} m do próprio gol")
        if m.get("contra_ataques") is not None:
            bits.append(f"{m['contra_ataques']:.1f} contra-ataques com finalização por jogo e {m.get('contra_ataques_sofridos', 0):.1f} sofridos")
        out.append("Pelos lances (" + f"{evi['jogos']} jogos): " + "; ".join(bits) + ".")
    if not out:
        out.append("Ainda não há jogos com estatísticas ou lances suficientes deste time na base.")
    return out


def recruitment_needs(ident: Dict[str, Any]) -> List[Dict[str, str]]:
    """Função tática que o MODELO DE JOGO pede (contratação coerente com a identidade), com o critério transparente."""
    st = ident.get("estatisticas") or {}
    words = set(st.get("estilo") or [])
    evi = (ident.get("lances") or {}).get("medias") or {}
    out = []
    if "jogo direto" in words:
        out.append({"funcao": "centroavante de referência (pivô/aéreo)", "porque": "o time joga direto: precisa de quem segure e ganhe a bola longa",
                    "metricas": "aéreos ganhos %, duelos ganhos %, toques na área"})
    if "ataque pelos lados com cruzamento" in words:
        out.append({"funcao": "lateral/ponta que cruza bem + atacante de área", "porque": "muitos cruzamentos por jogo",
                    "metricas": "cruzamentos certos/90 e %, gols de cabeça, aéreos %"})
    if "propõe o jogo (gosta da bola)" in words:
        out.append({"funcao": "volante construtor e zagueiro que sai jogando", "porque": "o time quer a bola e sai de trás",
                    "metricas": "acerto de passe %, passes que quebram linhas/90, bolas longas certas %"})
    if any("pressiona alto" in w for w in words) or (evi.get("ppda") is not None and evi["ppda"] < 9):
        out.append({"funcao": "atacantes e meias com volume defensivo", "porque": "a pressão alta exige quem corra e roube na frente",
                    "metricas": "recuperações/90, desarmes/90, ações defensivas no terço ofensivo"})
    if "reativo (abre mão da bola)" in words:
        out.append({"funcao": "pontas rápidos de transição e zagueiros fortes no duelo", "porque": "o time espera e sai no contra-ataque",
                    "metricas": "dribles certos/90, conduções progressivas, duelos defensivos %"})
    return out


def opposition_plan(ident: Dict[str, Any]) -> List[Dict[str, str]]:
    """Como enfrentar o modelo de jogo do rival, fase por fase — cada item com a base (número e fonte). Hipótese de
    trabalho, não garantia: o rival pode mudar o plano para o jogo."""
    st_ = ident.get("estatisticas") or {}
    p, ref = st_.get("perfil") or {}, st_.get("referencia") or {}
    evi = ident.get("lances") or {}
    m = evi.get("medias") or {}
    out = []
    def above(k, f=1.1):
        return p.get(k) is not None and ref.get(k) and p[k] >= ref[k] * f
    def below(k, f=.9):
        return p.get(k) is not None and ref.get(k) and p[k] <= ref[k] * f
    if above("posse_pct"):
        out.append({"fase": "Sem a bola", "acao": "pressionar a saída deles e fechar o passe ao volante: eles querem a bola",
                    "base": f"posse {p['posse_pct']:.0f}% contra {ref['posse_pct']:.0f}% da competição"})
    if below("posse_pct"):
        out.append({"fase": "Com a bola", "acao": "ter paciência e circular: eles abrem mão da bola e esperam o erro; proteger a perda no meio",
                    "base": f"posse {p['posse_pct']:.0f}% contra {ref['posse_pct']:.0f}%"})
    if above("pct_bolas_longas", 1.2):
        out.append({"fase": "Sem a bola", "acao": "zagueiro forte no alto e cobertura da segunda bola: eles jogam direto",
                    "base": f"{p['pct_bolas_longas']:.0f}% de bolas longas nos passes (referência {ref['pct_bolas_longas']:.0f}%)"})
    if above("cruzamentos", 1.2):
        out.append({"fase": "Sem a bola", "acao": "fechar o cruzamento na origem (lateral + ponta dobrando) e atacar a bola na área",
                    "base": f"{p['cruzamentos']:.1f} cruzamentos por jogo (referência {ref['cruzamentos']:.1f})"})
    if p.get("ppda_aprox") is not None and ref.get("ppda_aprox") and p["ppda_aprox"] <= ref["ppda_aprox"] * .85:
        out.append({"fase": "Com a bola", "acao": "sair rápido por cima da pressão (bola longa no pivô ou nas costas dos laterais)",
                    "base": f"PPDA aproximado {p['ppda_aprox']:.1f} — pressionam mais que a média ({ref['ppda_aprox']:.1f})"})
    if m.get("altura_bloco_m") is not None and m["altura_bloco_m"] >= 50:
        out.append({"fase": "Transição ofensiva", "acao": "atacar o espaço nas costas da última linha logo após recuperar",
                    "base": f"bloco a ~{m['altura_bloco_m']:.0f} m do gol (lances, {evi.get('jogos')} jogos)"})
    if m.get("contra_ataques_sofridos") is not None and m["contra_ataques_sofridos"] >= 3:
        out.append({"fase": "Transição ofensiva", "acao": "acelerar depois do desarme: eles sofrem finalização logo após perder a bola",
                    "base": f"{m['contra_ataques_sofridos']:.1f} contra-ataques com finalização sofridos por jogo"})
    if p.get("xg_contra") is not None and ref.get("xg") and p["xg_contra"] >= ref["xg"] * 1.15:
        out.append({"fase": "Com a bola", "acao": "finalizar de perto: eles cedem chances de qualidade",
                    "base": f"xG cedido {p['xg_contra']:.2f} por jogo (média {ref['xg']:.2f})"})
    return out
