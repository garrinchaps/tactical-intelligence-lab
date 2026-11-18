"""
Inteligência do jogador por lances (rodada 10) — três escalas:
  nível 1  analyze_action   → um lance: o que aconteceu, onde, sob que pressão, com que pé, o que veio antes e depois;
  nível 2  match_intel      → a partida: técnica, espaço (corredor/terço), tempo (blocos de 15 min), defesa, perdas e
                              suas consequências, eficiência E contexto (95% de passe só para o lado não é mérito);
  nível 3  patterns         → vários jogos: o que se repete ("em 6 de 9 jogos"), tendência, regularidade.
Toda saída é uma lista de afirmações tipadas — FATO (o dado), PADRÃO (o que se repete), INTERPRETAÇÃO (o que pode
significar) e HIPÓTESE (o que precisa de vídeo ou mais dados) — com o número de observações. A IA nunca promove
hipótese a característica comprovada, e o que a fonte não mede aparece como "não medido".
Coordenadas no padrão StatsBomb (120×80, ataque para a direita).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

LOSS_TYPES = {"Dispossessed", "Miscontrol"}
DEF_TYPES = {"Interception", "Ball Recovery", "Block", "Clearance"}
MIN_N = 5                         # abaixo disso, só fato — nada de padrão nem interpretação


def _pl(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _s(tipo: str, texto: str, n: Optional[int] = None, area: str = "") -> Dict[str, Any]:
    return {"tipo": tipo, "texto": texto, "n": n, "area": area}


def _corridor(y) -> str:
    return "esquerdo" if y < 80 / 3 else ("direito" if y > 160 / 3 else "central")


def _third(x) -> str:
    return "defensivo" if x < 40 else ("intermediário" if x < 80 else "ofensivo")


def _dist(x, y):
    return np.hypot(120 - np.asarray(x, float), 40 - np.asarray(y, float))


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["period"].fillna(1) <= 4].sort_values(["period", "index_num"]).reset_index(drop=True).copy()
    d["t"] = d["period"].fillna(1) * 10000 + d["minute"].fillna(0) * 60 + d["second"].fillna(0)
    return d


def _passes(g: pd.DataFrame) -> pd.DataFrame:
    p = g[g["type_name"] == "Pass"].copy()
    if p.empty:
        return p
    p["ok"] = p["pass_outcome_name"].isna()
    p["d0"], p["d1"] = _dist(p["x"], p["y"]), _dist(p["end_x"].fillna(p["x"]), p["end_y"].fillna(p["y"]))
    p["prog"] = p["ok"] & ((p["d0"] - p["d1"]) >= np.maximum(10, 0.25 * p["d0"])) & (p["end_x"] >= 60)
    p["back"] = (p["end_x"] - p["x"]) < -2
    p["final3"] = p["ok"] & (p["x"] < 80) & (p["end_x"] >= 80)
    p["box"] = p["ok"] & (p["end_x"] >= 102) & p["end_y"].between(18, 62)
    return p


def _score_state(d: pd.DataFrame, team: str) -> pd.Series:
    """Saldo de gols do time ANTES de cada evento (vencendo/empatando/perdendo)."""
    gf = ga = 0
    out = []
    for r in d.itertuples(index=False):
        out.append("vencendo" if gf > ga else ("perdendo" if gf < ga else "empatando"))
        if r.type_name == "Shot" and getattr(r, "shot_outcome_name", None) == "Goal":
            if r.team_name == team:
                gf += 1
            else:
                ga += 1
        elif r.type_name == "Own Goal Against":
            if r.team_name == team:
                ga += 1
            else:
                gf += 1
    return pd.Series(out, index=d.index)


def players_with_events(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    g = df[df["player_name"].notna()].groupby(["team_name", "player_name"]).size().rename("acoes").reset_index()
    return g.sort_values("acoes", ascending=False)


# ================================================================================================ nível 2
def match_intel(df: pd.DataFrame, player: str) -> Dict[str, Any]:
    d = _prep(df)
    me = d[d["player_name"] == player]
    if me.empty:
        return {"jogador": player, "afirmacoes": [_s("fato", "Sem lances deste jogador neste jogo.")], "numeros": {}}
    team = me["team_name"].mode().iloc[0]
    out: List[Dict[str, Any]] = []
    nums: Dict[str, Any] = {}
    p = _passes(me)
    # ---------------- técnica: passe
    if len(p):
        acc = 100 * p["ok"].mean()
        nums.update(passes=len(p), acerto_passe=round(acc, 1), progressivos=int(p["prog"].sum()),
                    terco_final=int(p["final3"].sum()), na_area=int(p["box"].sum()), para_tras_pct=round(100 * p["back"].mean()))
        out.append(_s("fato", f"{len(p)} passes, {acc:.0f}% certos; {int(p['prog'].sum())} progressivos, "
                              f"{int(p['final3'].sum())} para o terço final, {int(p['box'].sum())} para dentro da área.",
                      len(p), "técnica"))
        if len(p) >= 20 and acc >= 88 and p["prog"].mean() < 0.08 and p["back"].mean() > 0.30:
            out.append(_s("interpretação", f"O aproveitamento alto ({acc:.0f}%) vem de passe seguro: {100 * p['back'].mean():.0f}% "
                                           f"para trás e só {100 * p['prog'].mean():.0f}% progressivos — pouco risco, pouca "
                                           f"progressão.", len(p), "eficiência"))
        # pé
        if "pass_body_part" in p and p["pass_body_part"].notna().any():
            feet = p[p["pass_body_part"].isin(["Right Foot", "Left Foot"])]
            if len(feet) >= MIN_N:
                r, l = feet[feet["pass_body_part"] == "Right Foot"], feet[feet["pass_body_part"] == "Left Foot"]
                txt = f"Pé direito: {len(r)} passes ({100 * r['ok'].mean():.0f}% certos) · pé esquerdo: {len(l)}" + \
                      (f" ({100 * l['ok'].mean():.0f}% certos)" if len(l) else "")
                out.append(_s("fato", txt + ".", len(feet), "técnica"))
                share = max(len(r), len(l)) / len(feet)
                if len(feet) >= 20 and share >= 0.85:
                    pref = "direito" if len(r) > len(l) else "esquerdo"
                    out.append(_s("padrão", f"Usa quase só o pé {pref} ({100 * share:.0f}% dos passes com o pé).",
                                  len(feet), "técnica"))
                    out.append(_s("hipótese", f"Marcar fechando o lado do pé {pref} pode forçá-lo para o pé fraco — "
                                              "confirmar em vídeo/outros jogos.", None, "técnica"))
        else:
            out.append(_s("fato", "Pé do passe: não medido nesta fonte.", None, "técnica"))
        # pressão
        if "under_pressure" in p and p["under_pressure"].notna().any():
            up = p["under_pressure"].fillna(False).astype(bool)
            if up.sum() >= MIN_N and (~up).sum() >= MIN_N:
                a1, a0 = 100 * p.loc[up, "ok"].mean(), 100 * p.loc[~up, "ok"].mean()
                out.append(_s("fato", f"Sob pressão: {int(up.sum())} passes, {a1:.0f}% certos; sem pressão: {a0:.0f}%.",
                              int(up.sum()), "decisão"))
                if a0 - a1 >= 15:
                    out.append(_s("interpretação", f"Perde {a0 - a1:.0f} pontos de acerto quando é pressionado.",
                                  int(up.sum()), "decisão"))
                    out.append(_s("hipótese", "Pressionar no momento em que ele recebe pode gerar erro — a orientação do "
                                              "corpo na recepção exige vídeo/tracking.", None, "decisão"))
        # cruzamentos
        if "is_pass_cross" in p:
            cr = p[p["is_pass_cross"].fillna(False).astype(bool)]
            if len(cr):
                out.append(_s("fato", _pl(len(cr), "cruzamento", "cruzamentos") + f", {int(cr['ok'].sum())} certo(s) "
                                      f"(origem: {cr['y'].map(_corridor).mode().iloc[0]}).", len(cr), "criação"))
    # ---------------- finalização
    sh = me[me["type_name"] == "Shot"]
    if len(sh):
        xg = pd.to_numeric(sh["shot_statsbomb_xg"], errors="coerce")
        dist = _dist(sh["x"], sh["y"]) * 0.9144
        nums.update(finalizacoes=len(sh), xg=round(float(xg.sum()), 2))
        out.append(_s("fato", _pl(len(sh), "finalização", "finalizações") + f", xG {xg.sum():.2f} (média {xg.mean():.2f} por chute, distância média "
                              f"{dist.mean():.0f} m); {int(sh['shot_outcome_name'].isin(['Goal', 'Saved', 'Saved To Post']).sum())} "
                              f"no alvo, {int((sh['shot_outcome_name'] == 'Goal').sum())} gol(s).", len(sh), "ofensiva"))
        if len(sh) >= 3 and xg.mean() < 0.07:
            out.append(_s("interpretação", "Volume sem qualidade: finalizou de posições de baixa chance.", len(sh), "eficiência"))
    # ---------------- condução e drible
    ca = me[me["type_name"] == "Carry"]
    if len(ca) and "end_x" in ca:
        d0, d1 = _dist(ca["x"], ca["y"]), _dist(ca["end_x"].fillna(ca["x"]), ca["end_y"].fillna(ca["y"]))
        prog = int(((d0 - d1) >= np.maximum(5, 0.25 * d0)).sum())
        nums["conducoes_progressivas"] = prog
        if prog:
            side = ca.loc[(d0 - d1) >= np.maximum(5, 0.25 * d0), "end_y"].map(_corridor).mode()
            out.append(_s("fato", _pl(prog, "condução progressiva", "conduções progressivas") + (f", preferindo o corredor {side.iloc[0]}" if len(side) else "")
                          + ".", prog, "ofensiva"))
    dr = me[me["type_name"] == "Dribble"]
    if len(dr):
        out.append(_s("fato", _pl(len(dr), "tentativa", "tentativas") + " de drible (sucesso: não medido nesta conversão da fonte).",
                      len(dr), "ofensiva"))
    # ---------------- defesa
    duels = me[me["type_name"] == "Duel"]
    tk = duels[duels["duel_type_name"] == "Tackle"] if "duel_type_name" in duels else duels.iloc[0:0]
    won = tk["duel_outcome_name"].isin(["Won", "Success", "Success In Play", "Success Out"]).sum() if len(tk) else 0
    past = me[me["type_name"] == "Dribbled Past"]
    dfn = me[me["type_name"].isin(DEF_TYPES)]
    pr = me[me["type_name"] == "Pressure"]
    nums.update(desarmes=len(tk), desarmes_certos=int(won), driblado=len(past), acoes_defensivas=len(dfn), pressoes=len(pr))
    if len(tk) or len(dfn) or len(pr):
        out.append(_s("fato", f"{len(tk)} desarme(s) ({int(won)} certo(s)), {len(dfn)} interceptações/recuperações/bloqueios/cortes, "
                              f"{len(pr)} pressões no portador, {len(past)} vez(es) driblado.",
                      len(tk) + len(dfn) + len(pr), "defensiva"))
    if len(pr) >= MIN_N:
        zones = pr["x"].map(_third).value_counts()
        out.append(_s("fato", "Pressões por terço: " + ", ".join(f"{k} {v}" for k, v in zones.items()) + ".", len(pr), "defensiva"))
    if len(past) >= 2:
        sides = past["y"].map(_corridor).value_counts()
        out.append(_s("padrão" if len(past) >= 3 else "fato",
                      f"Driblado {len(past)} vezes — corredor: " + ", ".join(f"{k} {v}" for k, v in sides.items()) + ".",
                      len(past), "defensiva"))
        if len(past) >= 3 and sides.iloc[0] / len(past) >= 0.66:
            out.append(_s("hipótese", f"Pode sofrer mais quando o adversário o ataca pelo corredor {sides.index[0]} — "
                                      "confirmar em outros jogos e no vídeo (abordagem e corpo não são medidos).", None, "defensiva"))
    # ---------------- perdas e consequência
    fails = p[~p["ok"]] if len(p) else p
    losses = pd.concat([me[me["type_name"].isin(LOSS_TYPES)], fails]).drop_duplicates("event_id")
    if len(losses):
        own = int((losses["x"] < 60).sum())
        conseq = 0
        for r in losses.itertuples():
            nxt = d[(d["t"] > r.t) & (d["t"] <= r.t + 15) & (d["team_name"] != team) & (d["type_name"] == "Shot")]
            conseq += int(len(nxt) > 0)
        nums.update(perdas=len(losses), perdas_campo_proprio=own, perdas_viraram_chute=conseq)
        out.append(_s("fato", f"{len(losses)} perdas de posse, contando passes errados ({own} no próprio campo); "
                              f"{conseq} {'delas virou' if conseq == 1 else 'delas viraram'} finalização do rival em até 15 s.",
                      len(losses), "risco"))
        if conseq >= 2:
            out.append(_s("interpretação", "Perdas com consequência: o rival chegou ao chute logo depois em mais de uma.",
                          conseq, "risco"))
    # ---------------- tempo
    me_t = me.assign(bloco=(me["minute"].fillna(0) // 15).clip(upper=5).astype(int))
    by = me_t.groupby("bloco").size().reindex(range(6), fill_value=0)
    labels = ["0–15", "15–30", "30–45", "45–60", "60–75",
              "75–fim" + (" (com prorrogação)" if me["minute"].max() > 100 else "")]
    nums["acoes_por_bloco"] = dict(zip(labels, by.tolist()))
    if by.sum() >= 30:
        first, last = by.iloc[:3].mean(), by.iloc[4:].mean()
        out.append(_s("fato", "Ações por bloco de 15 min: " + " · ".join(f"{l}: {v}" for l, v in zip(labels, by.tolist())) + ".",
                      int(by.sum()), "tempo"))
        if first > 0 and last < 0.6 * first and by.iloc[5] > 0:
            out.append(_s("padrão", f"Participação cai no fim ({last:.0f} ações por bloco contra {first:.0f} no 1º tempo).",
                          int(by.sum()), "tempo"))
            out.append(_s("hipótese", "Cansaço ou mudança de função — a intensidade física não é medida nesta fonte.", None, "tempo"))
    # ---------------- contexto: placar
    if len(p) >= 20:
        st_ = _score_state(d, team).reindex(p.index)
        ctx = p.assign(estado=st_.values).groupby("estado")["ok"].agg(["size", "mean"])
        ctx = ctx[ctx["size"] >= MIN_N]
        if len(ctx) >= 2:
            out.append(_s("fato", "Acerto de passe por placar: " + ", ".join(f"{k} {100 * v['mean']:.0f}% ({int(v['size'])})"
                                                                               for k, v in ctx.iterrows()) + ".",
                          int(ctx["size"].sum()), "contexto"))
    out.append(_s("hipótese", "Limite: orientação do corpo, velocidade e posicionamento sem bola exigem tracking/vídeo; "
                              "não entram nesta análise.", None, "limite"))
    return {"jogador": player, "time": team, "afirmacoes": out, "numeros": nums}


# ================================================================================================ nível 1
def analyze_action(df: pd.DataFrame, event_id: str) -> Dict[str, Any]:
    d = _prep(df)
    hit = d.index[d["event_id"].astype(str) == str(event_id)]
    if not len(hit):
        return {"afirmacoes": [_s("fato", "Lance não encontrado.")]}
    i = int(hit[0])
    r = d.loc[i]
    out = [_s("fato", f"{r['minute']:.0f}' · {r['player_name']} ({r['team_name']}) · {r['type_name']} no corredor "
                      f"{_corridor(r['y'])}, terço {_third(r['x'])}.")]
    if pd.notna(r.get("under_pressure")) and bool(r.get("under_pressure")):
        out.append(_s("fato", "Executado sob pressão do adversário."))
    if r["type_name"] == "Pass" and pd.notna(r.get("end_x")):
        dist = float(np.hypot(r["end_x"] - r["x"], r["end_y"] - r["y"]) * 0.9144)
        ok = pd.isna(r.get("pass_outcome_name"))
        gain = float((_dist(r["x"], r["y"]) - _dist(r["end_x"], r["end_y"])) * 0.9144)
        foot = r.get("pass_body_part") or "pé não medido"
        out.append(_s("fato", f"Passe de {dist:.0f} m ({foot}), {'certo' if ok else 'errado: ' + str(r.get('pass_outcome_name'))}; "
                              f"aproximou a bola {gain:.0f} m do gol" + (f" para {r.get('pass_recipient_name')}" if ok and
                              pd.notna(r.get("pass_recipient_name")) else "") + "."))
    if r["type_name"] == "Shot":
        out.append(_s("fato", f"Finalização ({r.get('shot_body_part_name') or 'parte do corpo não medida'}), xG "
                              f"{pd.to_numeric(r.get('shot_statsbomb_xg'), errors='coerce') or 0:.2f}, resultado: "
                              f"{r.get('shot_outcome_name')}."))
    if r["type_name"] == "Duel":
        out.append(_s("fato", f"Duelo ({r.get('duel_type_name') or 'tipo n/d'}): {r.get('duel_outcome_name') or 'resultado n/d'}."))
    prev = d.loc[max(0, i - 2):i - 1]
    if len(prev):
        out.append(_s("fato", "Antes: " + " → ".join(f"{p.player_name or '?'} ({p.type_name})" for p in prev.itertuples()) + "."))
    nxt = d[(d["t"] > r["t"]) & (d["t"] <= r["t"] + 10)]
    if len(nxt):
        own = nxt[nxt["team_name"] == r["team_name"]]
        shot = bool((own["type_name"] == "Shot").any())
        lost = bool((nxt["team_name"] != r["team_name"]).any() and nxt.iloc[0]["team_name"] != r["team_name"])
        out.append(_s("fato", "Depois (10 s): " + ("o time finalizou" if shot else ("o rival ficou com a bola" if lost
                                                                                     else "a posse seguiu sem finalizar")) + "."))
    out.append(_s("hipótese", "Um lance isolado não comprova tendência: compare com os outros lances do mesmo tipo do jogador."))
    return {"afirmacoes": out}


def key_actions(df: pd.DataFrame, player: str, limit: int = 8) -> pd.DataFrame:
    """Lances que mais pesam do jogador: finalizações, perdas que viraram chute do rival, passes para a área."""
    d = _prep(df)
    me = d[d["player_name"] == player]
    if me.empty:
        return me
    p = _passes(me)
    keys = list(me[me["type_name"] == "Shot"]["event_id"]) + list(p[p["box"]]["event_id"] if len(p) else [])
    keys += list(me[me["type_name"].isin(LOSS_TYPES | {"Dribbled Past"})]["event_id"])
    sel = me[me["event_id"].isin(keys)].head(limit)
    return sel[["event_id", "minute", "type_name", "x", "y"]]


# ================================================================================================ nível 3
def patterns(per_match: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Recebe match_intel de vários jogos (do mais recente ao mais antigo) e acha o que se repete."""
    rows = [dict(m.get("numeros") or {}, _n=i) for i, m in enumerate(per_match) if m.get("numeros")]
    if len(rows) < 3:
        return [_s("fato", f"Só {len(rows)} jogo(s) com lances deste jogador — pouco para afirmar padrão (mínimo 3).",
                   len(rows), "amostra")]
    t = pd.DataFrame(rows)
    out = [_s("fato", f"Base: {len(t)} jogos com lances do jogador.", len(t), "amostra")]

    def series(c):
        return pd.to_numeric(t[c], errors="coerce") if c in t else pd.Series(dtype=float)
    acc = series("acerto_passe")
    if acc.notna().sum() >= 3:
        cv = acc.std() / max(acc.mean(), 1)
        out.append(_s("fato", f"Acerto de passe: média {acc.mean():.0f}%, de {acc.min():.0f}% a {acc.max():.0f}%.", int(acc.notna().sum()), "técnica"))
        out.append(_s("padrão", "Regular no passe (varia pouco de jogo para jogo)." if cv < 0.06 else
                      "Irregular no passe (oscila bastante entre os jogos).", int(acc.notna().sum()), "consistência"))
        if len(acc) >= 6:
            recent, before = acc.iloc[:3].mean(), acc.iloc[3:].mean()
            if abs(recent - before) >= 5:
                out.append(_s("padrão", f"Tendência: acerto {'subiu' if recent > before else 'caiu'} de {before:.0f}% para "
                                        f"{recent:.0f}% nos 3 jogos mais recentes.", len(acc), "tendência"))
    for col, label, bad in (("perdas_viraram_chute", "perdas que viraram chute do rival", 1),
                            ("driblado", "vezes driblado", 2), ("progressivos", "passes progressivos", None)):
        s = series(col)
        if s.notna().sum() < 3:
            continue
        if bad is not None:
            k = int((s >= bad).sum())
            if k >= max(3, 0.5 * s.notna().sum()):
                out.append(_s("padrão", f"{label.capitalize()}: aconteceu em {k} de {int(s.notna().sum())} jogos "
                                        f"(média {s.mean():.1f} por jogo).", int(s.notna().sum()), "risco"))
        else:
            out.append(_s("fato", f"{label.capitalize()}: média {s.mean():.1f} por jogo.", int(s.notna().sum()), "técnica"))
    out.append(_s("hipótese", "Padrões de vários jogos ainda dependem do adversário e da função em cada jogo — leia com o "
                              "contexto (mando, nível do rival, placar).", None, "limite"))
    return out


TYPE_ICON = {"fato": "📌 Fato", "padrão": "🔁 Padrão", "interpretação": "💡 Interpretação", "hipótese": "🔍 Hipótese"}


def to_markdown(statements: Sequence[Dict[str, Any]]) -> str:
    lines = []
    for s in statements:
        n = f" _(n={s['n']})_" if s.get("n") else ""
        lines.append(f"- **{TYPE_ICON.get(s['tipo'], s['tipo'])}:** {s['texto']}{n}")
    return "\n".join(lines)
