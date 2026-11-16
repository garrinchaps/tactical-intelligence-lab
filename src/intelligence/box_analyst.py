"""
Analista para jogos SEM lances com coordenadas, mas com os dados da FotMob (rodada 5): números por jogador, mapa de
chutes (xG, situação, posição), momentum e corredores de ataque.

Responde de verdade — não a tabela de sempre:
  * ranking de qualquer número por jogador ("quem mais finalizou/criou/desarmou/correu?");
  * nota 2.0 de um jogador (régua das estatísticas, contra a mesma função);
  * como anular um jogador ou o principal criador (perfil medido + onde chuta);
  * como o time sofreu / como evitar tomar gols (chutes do rival por situação, de dentro/fora da área, por lado);
  * por que o resultado saiu (xG, grandes chances, momentum por tempo, chutes, protagonistas).
Tudo com o número da fonte; o que a fonte não tem (xT, pressão, rede de passes) é dito, nunca inventado.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

PSTATS: List[Tuple[str, str, str]] = [  # (regex da pergunta, chave, rótulo)
    (r"finaliz|chut", "totalShots", "Finalizações"), (r"no alvo|no gol", "shotsOnTarget", "Finalizações no alvo"),
    (r"\bxa\b|assistenc\w* esperad", "xa", "xA (assistências esperadas)"), (r"\bxgot\b|gols? esperados? no alvo", "_xgot", "xGOT"),
    (r"\bxg\b|gols esperad", "xg", "xG"),
    (r"cri(ou|a|ar|acao)|chances? criad|passes? decisiv|passe para finaliz", "chances_created", "Chances criadas"),
    (r"assist", "goalAssists", "Assistências"), (r"\bgols?\b|marcou|artilheir", "totalGoals", "Gols"),
    (r"terco final|progred|progress", "passes_into_final_third", "Passes no terço final"),
    (r"quebr\w* (de )?linha", "line_breaking_passes", "Passes que quebram linhas"),
    (r"toques? na area|dentro da area", "touches_opp_box", "Toques na área rival"),
    (r"drible", "dribbles_succeeded", "Dribles certos"), (r"desarm", "matchstats.headers.tackles", "Desarmes"),
    (r"intercept", "interceptions", "Interceptações"), (r"recuper", "recoveries", "Recuperações de bola"),
    (r"corte", "clearances", "Cortes"), (r"aere|cabec", "aerials_won", "Duelos aéreos ganhos"),
    (r"duelo", "duel_won", "Duelos ganhos"), (r"perd\w* (a )?(bola|posse)|desarmad", "dispossessed", "Vezes que perdeu a posse"),
    (r"falta\w* (cometid|fez)|mais faltas", "foulsCommitted", "Faltas cometidas"), (r"sofreu falta", "was_fouled", "Faltas sofridas"),
    (r"defesa\w* do goleiro|mais defesas|defendeu", "saves", "Defesas"), (r"cruzament", "accurate_crosses", "Cruzamentos certos"),
    (r"lancament|bola\w* longa", "long_balls_accurate", "Bolas longas certas"),
    (r"passe", "accurate_passes", "Passes certos"), (r"toque", "touches", "Toques na bola"),
    (r"sprint", "sprints", "Sprints"), (r"distancia|correu|km\b|corrida", "distance_m", "Distância percorrida (m)"),
    (r"velocidade", "top_speed_kmh", "Velocidade máxima (km/h)"), (r"\bnota\b|melhor (jogador|em campo)|destaque", "_rating", "Nota da FotMob"),
]
SIT_PT = {"RegularPlay": "jogada trabalhada", "FastBreak": "contra-ataque", "SetPiece": "bola parada", "FromCorner": "escanteio",
          "Penalty": "pênalti", "FreeKick": "falta direta", "ThrowInSetPiece": "lateral"}


def _fm_id(db, meta: Dict[str, Any]) -> Optional[int]:
    mid = int(meta.get("match_id") or 0)
    if mid >= 12_000_000_000:
        return mid
    try:
        from src.data_hub.sources.fotmob import FotmobProvider

        return FotmobProvider(db).ensure_match(mid, meta)
    except Exception:
        return None


def _load(db, mid: int) -> Dict[str, Any]:
    with db.connect() as conn:
        ps = pd.read_sql_query("SELECT team_name, player_name, minutes, rating, stats_json FROM match_player_stats WHERE match_id = ?",
                               conn, params=(mid,))
        try:
            sh = pd.read_sql_query("SELECT * FROM match_shots WHERE match_id = ?", conn, params=(mid,))
        except Exception:
            sh = pd.DataFrame()
        try:
            r = conn.execute("SELECT extra_json FROM match_extra WHERE match_id = ?", (mid,)).fetchone()
            ex = json.loads(r[0]) if r else {}
        except Exception:
            ex = {}
    rows = []
    for r in ps.itertuples():
        try:
            s = json.loads(r.stats_json or "{}")
        except Exception:
            s = {}
        rows.append({"jogador": r.player_name, "equipe": r.team_name, "_rating": r.rating, **s})
    return {"players": pd.DataFrame(rows), "shots": sh, "extra": ex}


def _team_of(name: str, teams: List[str]) -> Optional[str]:
    from src.data_hub.service import _same
    from src.data_lake.ids import team_core

    return next((t for t in teams if _same(team_core(t), team_core(name))), None)


PROTECTION_STATS: List[Tuple[str, str]] = [
    ("defensive_actions", "Ações defensivas"),
    ("matchstats.headers.tackles", "Desarmes"),
    ("interceptions", "Interceptações"),
    ("recoveries", "Recuperações"),
    ("duel_won", "Duelos ganhos"),
    ("ground_duels_won", "Duelos terrestres ganhos"),
    ("aerials_won", "Duelos aéreos ganhos"),
    ("clearances", "Cortes"),
]


def _combination_rows(players: pd.DataFrame, names: List[str]) -> List[Dict[str, Any]]:
    """Extrai apenas indicadores defensivos realmente presentes para cada atleta citado."""
    from src.intelligence.query_understanding import norm

    out: List[Dict[str, Any]] = []
    for name in names[:3]:
        hit = players[players["jogador"].map(norm) == norm(name)]
        if hit.empty:
            out.append({"jogador": name, "sem_dado": True, "indicadores": []})
            continue
        row = hit.iloc[0]
        try:
            minutes = float(row.get("minutes"))
        except (TypeError, ValueError):
            minutes = 0.0
        metrics = []
        for key, label in PROTECTION_STATS:
            value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
            if pd.isna(value):
                continue
            item = {"metrica": label, "valor": round(float(value), 2)}
            if minutes > 0:
                item["por90"] = round(float(value) * 90.0 / minutes, 2)
            metrics.append(item)
        out.append({
            "jogador": str(row.get("jogador") or name),
            "equipe": str(row.get("equipe") or ""),
            "minutos": round(minutes, 1) if minutes > 0 else None,
            "indicadores": metrics,
            "sem_dado": not bool(metrics),
        })
    return out


def build(db, sc, meta: Dict[str, Any], target_team: str, opp: str) -> Optional[Dict[str, Any]]:
    """Bloco de evidências pela FotMob; None se o jogo não tem números por jogador (aí vale o redator antigo)."""
    mid = _fm_id(db, meta)
    if not mid:
        return None
    d = _load(db, mid)
    P, S = d["players"], d["shots"]
    if P.empty:
        return None
    teams = list(dict.fromkeys(P["equipe"].dropna()))
    me = _team_of(target_team, teams) or (teams[0] if teams else target_team)
    other = next((t for t in teams if t != me), opp)
    if sc.team_focus == "opponent":
        me, other = other, me
    from src.intelligence.query_understanding import norm

    q = norm(sc.raw)
    out: Dict[str, Any] = {"fonte": "FotMob", "partida_fotmob": int(mid), "equipe": me, "adversario": other}
    ask = sc.ask
    if ask == "combinations":
        if len(sc.players) < 2:
            return out
        out["dupla"] = {
            "jogadores": _combination_rows(P, sc.players[:3]),
            "limite": "FotMob informa contagens individuais, mas não a zona exata de cada ação nem a distância entre linhas.",
        }
        return out
    if ask == "unavailable" and re.search(r"corr|sprint|distanc|km\b|velocid", q):
        ask = "ranking"                               # físico: a FotMob tem em algumas ligas — procura antes de negar
    if ask == "ranking" or (ask is None and re.search(r"\bquem\b.*\b(mais|menos)\b", q)):
        key, lab = next(((k, l) for rx, k, l in PSTATS if re.search(rx, q)), ("_rating", "Nota da FotMob"))
        if key == "_xgot":
            if S.empty or "xgot" not in S:
                out["ranking"] = {"metrica": lab, "sem_dado": True}
                return out
            shots = S.copy()
            shots["xgot"] = pd.to_numeric(shots["xgot"], errors="coerce")
            shots = shots.dropna(subset=["xgot", "player_name"])
            if sc.team_named and sc.team_focus != "both":
                shots = shots[shots["team_name"] == me]
            asc = bool(re.search(r"\bmenos\b|\bpior", q))
            leaders = (shots.groupby(["player_name", "team_name"], dropna=True)["xgot"].sum()
                       .sort_values(ascending=asc).head(5))
            out["ranking"] = {"metrica": lab, "ordem": "asc" if asc else "desc",
                              "lideres": [{"jogador": name, "equipe": team, "valor": round(float(value), 2)}
                                          for (name, team), value in leaders.items()]}
            return out
        if key not in P or P[key].dropna().empty:
            out["ranking"] = {"metrica": lab, "sem_dado": True, "onde_existe": "Premier League (dado físico da liga)"}
            return out
        asc = bool(re.search(r"\bmenos\b|\bpior", q))
        scope = P[P["equipe"] == me] if sc.team_named and sc.team_focus != "both" else P
        t = scope.dropna(subset=[key]).sort_values(key, ascending=asc).head(5)
        out["ranking"] = {"metrica": lab, "ordem": "asc" if asc else "desc",
                          "lideres": [{"jogador": r["jogador"], "equipe": r["equipe"], "valor": round(float(r[key]), 2),
                                       "minutos": r.get("minutes")} for _, r in t.iterrows()]}
        return out
    if ask == "rating" and sc.players:
        from src.analytics import rating_box as RB

        rr = RB.match_ratings(db, mid)
        hit = rr[rr["jogador"].isin(sc.players)] if not rr.empty else rr
        if hit.empty:
            out["nota"] = {"jogador": sc.players[0], "sem_nota": True}
        else:
            x = hit.iloc[0]
            det = x["_detalhe"]
            dims = {det["dimensoes_pt"].get(k, k): v for k, v in det["dimensoes"].items() if v is not None}
            best = sorted(dims.items(), key=lambda kv: -kv[1])
            src = P[P["jogador"] == x["jogador"]]
            out["nota"] = {"jogador": x["jogador"], "equipe": x["equipe"], "funcao": x["funcao"], "desempenho": x["desempenho"],
                           "impacto": x["impacto"], "classificacao": x["classificacao"], "confianca_pct": x["confianca_pct"],
                           "minutos": x["minutos"], "melhor": best[:2], "pior": best[-1:] if len(best) > 2 else [],
                           "nota_fotmob": float(src.iloc[0]["_rating"]) if not src.empty and pd.notna(src.iloc[0]["_rating"]) else None,
                           "pares": x["pares"]}
        return out
    defensive = bool(re.search(r"evitar (tomar|sofrer|levar)|sofreu|sofrer|tomou|tomar gol|levou gol|defend|fragil|vulnerav", q))
    if (ask == "plan" or sc.subject == "criador") and not (defensive and not sc.players and sc.subject != "criador"):
        target = sc.players[0] if sc.players else None
        if not target:
            riv = P[P["equipe"] == other] if sc.team_focus != "opponent" else P[P["equipe"] == me]
            riv = riv.assign(_cri=pd.to_numeric(riv.get("xa"), errors="coerce").fillna(0) +
                             0.1 * pd.to_numeric(riv.get("chances_created"), errors="coerce").fillna(0))
            if riv.empty or riv["_cri"].max() <= 0:
                return out
            target = riv.sort_values("_cri", ascending=False).iloc[0]["jogador"]
            out["criterio_criador"] = "maior xA (e chances criadas) do time"
        row = P[P["jogador"] == target]
        if row.empty:
            return out
        r = row.iloc[0].to_dict()
        sh = S[S["player_name"] == target] if not S.empty else S
        prof = {k: r.get(k) for k in ("minutes", "totalShots", "xg", "xa", "chances_created", "passes_into_final_third",
                                      "touches_opp_box", "dribbles_succeeded", "dribbles_succeeded_total", "accurate_crosses",
                                      "dispossessed", "defensive_actions", "aerials_won", "line_breaking_passes") if r.get(k) is not None}
        zones = {}
        for s in sh.itertuples():
            z = ("de dentro da área" if s.x >= 102 else "de fora da área") + (", pela esquerda" if s.y < 30 else ", pela direita" if s.y > 50 else ", pelo meio")
            zones[z] = zones.get(z, 0) + 1
        out["plano_jogador"] = {"jogador": target, "equipe": r["equipe"], "quem_defende": other if r["equipe"] == me else me,
                                "perfil": prof, "chutes_por_zona": zones}
        return out
    if ask in ("weakness", "conceded_how", "plan_team") or defensive:
        att = other
        sh = S[S["team_name"] == att] if not S.empty else S
        if sh.empty:
            return out
        sit = sh.groupby("situation").agg(chutes=("xg", "size"), xg=("xg", "sum"),
                                          gols=("outcome", lambda o: int((o == "Goal").sum()))).reset_index()
        inside = int((sh["x"] >= 102).sum())
        side = {"esquerda dele (direita de quem defende)": int((sh["y"] < 30).sum()), "meio": int(((sh["y"] >= 30) & (sh["y"] <= 50)).sum()),
                "direita dele (esquerda de quem defende)": int((sh["y"] > 50).sum())}
        az = ((d["extra"].get("zonas_ataque") or {}).get("home" if teams and att == teams[0] else "away") or {}).get("total") or {}
        out["como_sofreu"] = {"defensor": me, "atacante": att, "chutes": int(len(sh)), "xg": round(float(sh["xg"].fillna(0).sum()), 2),
                              "dentro_da_area": inside, "fora_da_area": int(len(sh) - inside),
                              "por_situacao": [{"situacao": SIT_PT.get(r.situation, r.situation), "chutes": int(r.chutes),
                                                "xg": round(float(r.xg), 2), "gols": int(r.gols)} for r in sit.sort_values("xg", ascending=False).itertuples()],
                              "por_lado": side, "corredores_do_atacante_pct": az,
                              "quem_finalizou": {k: int(v) for k, v in sh["player_name"].value_counts().head(3).items()}}
        return out
    if ask == "result" or re.search(r"por que|como (ganh|venc)|o que .* fez", q):
        mom = d["extra"].get("momentum") or []
        h1 = [v for m, v in mom if m <= 45]
        h2 = [v for m, v in mom if m > 45]
        agg = {}
        for tm in teams:
            sh = S[S["team_name"] == tm] if not S.empty else S
            agg[tm] = {"chutes": int(len(sh)), "xg": round(float(sh["xg"].fillna(0).sum()), 2) if len(sh) else 0.0,
                       "gols": int((sh["outcome"] == "Goal").sum()) if len(sh) else 0,
                       "chutes_dentro_da_area": int((sh["x"] >= 102).sum()) if len(sh) else 0}
        topx = P.sort_values("_rating", ascending=False).head(3)
        ht = [x for x in (d["extra"].get("times") or []) if x] or [meta.get("home_team_name"), meta.get("away_team_name")]
        ht = [_team_of(x, teams) or x for x in ht]        # mandante primeiro: o momentum + é do mandante
        out["historia_box"] = {"times": ht if len(ht) == 2 else teams, "finalizacoes": agg,
                               "momentum_1t": round(sum(h1) / len(h1), 1) if h1 else None,
                               "momentum_2t": round(sum(h2) / len(h2), 1) if h2 else None,
                               "destaques": [{"jogador": r["jogador"], "equipe": r["equipe"], "nota_fotmob": float(r["_rating"])}
                                             for _, r in topx.iterrows() if pd.notna(r["_rating"])]}
        return out
    return None


def _f(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{v:.0f}" if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


def write(b: Dict[str, Any]) -> str:
    if "dupla" in b:
        combo = b["dupla"]
        lines = ["**O que os números individuais mostram sobre a dupla:**"]
        for p in combo.get("jogadores") or []:
            if p.get("sem_dado"):
                lines.append(f"- **{p['jogador']}**: a FotMob não trouxe indicadores defensivos individuais suficientes neste jogo.")
                continue
            stats = []
            for m in p.get("indicadores") or []:
                value = _f(m["valor"])
                if m.get("por90") is not None:
                    value += f" ({_f(m['por90'])} por 90 min)"
                stats.append(f"{m['metrica'].lower()}: {value}")
            detail = "; ".join(stats) if stats else "sem indicadores defensivos observáveis"
            mins = f", { _f(p['minutos'])} min" if p.get("minutos") is not None else ""
            lines.append(f"- **{p['jogador']}** ({p.get('equipe') or 'equipe não identificada'}{mins}): {detail}.")
        lines.append(
            "_Leitura limitada aos registros individuais da FotMob. Desarmes, interceptações e duelos ajudam a "
            "descrever a participação defensiva, mas não provam, sozinhos, que a dupla fechou o corredor central, "
            "bloqueou linhas de passe ou protegeu a zaga. Para isso são necessários eventos com coordenadas ou tracking._"
        )
        return "\n\n".join(lines)
    if "ranking" in b:
        r = b["ranking"]
        if r.get("sem_dado"):
            fis = re.search(r"distância|sprint|velocidade", r["metrica"].lower())
            return (f"**Não tenho esse dado neste jogo.** A FotMob não publica \"{r['metrica'].lower()}\" para esta partida"
                    + (" — dado físico (rastreamento) só existe em algumas ligas, como a Premier League; esta não mede. "
                       "Não vou usar conduções ou corridas com a bola como se fossem sprints." if fis else ".")
                    + " Por isso não dá para fazer o ranking, nem dizer que foi zero.")
        lid = r["lideres"]
        if not lid:
            return f"Ninguém registrou {r['metrica'].lower()} neste jogo."
        w = "menos" if r.get("ordem") == "asc" else "mais"
        head = f"**{lid[0]['jogador']}** ({lid[0]['equipe']}) foi quem {w} teve {r['metrica'].lower()}: {_f(lid[0]['valor'])}."
        rows = "\n".join(f"{i}. {x['jogador']} ({x['equipe']}): {_f(x['valor'])}" for i, x in enumerate(lid, 1))
        return f"{head}\n\n**{r['metrica']} — números da FotMob:**\n{rows}"
    if "nota" in b:
        n = b["nota"]
        if n.get("sem_nota"):
            return f"Não consegui avaliar {n['jogador']} neste jogo (pouco tempo em campo ou sem números por jogador)."
        verd = "jogou bem" if n["desempenho"] >= 6.5 else "fez um jogo regular" if n["desempenho"] >= 5.0 else "jogou mal"
        txt = (f"**{n['jogador']} {verd}**: nota de desempenho **{_f(n['desempenho'])}** ({n['classificacao']}) e impacto "
               f"**{_f(n['impacto'])}**, comparado com {n['pares']} atuações de {n['funcao']}s em outros jogos.")
        if n.get("melhor"):
            txt += " Pesou a favor: " + " e ".join(f"{k.lower()} ({_f(v)})" for k, v in n["melhor"]) + "."
        if n.get("pior"):
            txt += f" Ponto fraco: {n['pior'][0][0].lower()} ({_f(n['pior'][0][1])})."
        if n.get("nota_fotmob") is not None:
            txt += f" A própria FotMob deu {_f(n['nota_fotmob'])}."
        return txt + (f"\n\n_Confiança {n['confianca_pct']}% · {_f(n['minutos'])} min · avaliação pelos números por jogador "
                      "(sem lances com coordenadas neste jogo, então xT e pressão não entram)._")
    if "plano_jogador" in b:
        p = b["plano_jogador"]
        f = p["perfil"]
        steps = []
        if b.get("criterio_criador"):
            steps.append(f"_O principal criador do lado deles foi **{p['jogador']}** ({p['equipe']}) — {b['criterio_criador']}._")
        if (f.get("chances_created") or 0) >= 2 or (f.get("xa") or 0) >= 0.3:
            steps.append(f"**Cortar o último passe:** criou {_f(f.get('chances_created', 0))} chances (xA {_f(f.get('xa', 0))}). "
                         f"Pressionar no momento em que ele recebe de frente e fechar a linha de passe para a área.")
        if (f.get("passes_into_final_third") or 0) >= 4:
            steps.append(f"**Fechar a progressão:** {_f(f['passes_into_final_third'])} passes para o terço final. Marcação "
                         "encaixada no meio e cobertura do volante por trás dele.")
        if (f.get("dribbles_succeeded_total") or 0) >= 3:
            steps.append(f"**Não dar o bote:** tentou {_f(f['dribbles_succeeded_total'])} dribles ({_f(f.get('dribbles_succeeded', 0))} certos). "
                         "Temporizar e esperar a dobra.")
        if (f.get("totalShots") or 0) >= 2:
            z = max(p["chutes_por_zona"].items(), key=lambda kv: kv[1]) if p["chutes_por_zona"] else None
            steps.append(f"**Bloquear o chute:** {_f(f['totalShots'])} finalizações (xG {_f(f.get('xg', 0))})"
                         + (f", a maioria {z[0]} ({z[1]})" if z else "") + ".")
        if (f.get("accurate_crosses") or 0) >= 3:
            steps.append(f"**Impedir o cruzamento:** {_f(f['accurate_crosses'])} cruzamentos certos — lateral fechado e ponta voltando.")
        if (f.get("touches_opp_box") or 0) >= 5:
            steps.append(f"**Tirar da área:** tocou {_f(f['touches_opp_box'])} vezes na área — zagueiro colado e alguém na sobra.")
        if (f.get("dispossessed") or 0) >= 3:
            steps.append(f"**Pressionar no domínio:** perdeu a bola {_f(f['dispossessed'])} vezes.")
        if not steps:
            steps.append(f"{p['jogador']} teve pouca participação nos números deste jogo — não há um traço forte para anular.")
        return (f"**Como {p['quem_defende']} pode anular {p['jogador']} ({p['equipe']}), pelos números deste jogo:**\n"
                + "\n".join(f"- {s}" for s in steps)
                + "\n\n_Sem lances com coordenadas neste jogo: o plano usa os números por jogador e o mapa de chutes da FotMob._")
    if "como_sofreu" in b:
        c = b["como_sofreu"]
        sit = c["por_situacao"]
        lines = [f"**{c['defensor']} cedeu {c['chutes']} finalizações (xG {_f(c['xg'])}) a {c['atacante']}** — "
                 f"{c['dentro_da_area']} de dentro da área e {c['fora_da_area']} de fora."]
        if sit:
            lines.append("**De onde vieram:** " + "; ".join(f"{s['situacao']}: {s['chutes']} chutes, xG {_f(s['xg'])}"
                                                            + (f", {s['gols']} gol(s)" if s['gols'] else "") for s in sit) + ".")
        az = c.get("corredores_do_atacante_pct") or {}
        if az:
            lines.append(f"**Por onde {c['atacante']} atacou:** esquerda {az.get('left')}%, meio {az.get('center')}%, direita {az.get('right')}%.")
        if c.get("quem_finalizou"):
            lines.append("**Quem mais finalizou:** " + ", ".join(f"{k} ({v})" for k, v in c["quem_finalizou"].items()) + ".")
        tips = []
        top = sit[0]["situacao"] if sit else ""
        if "contra-ataque" in top:
            tips.append("deixar dois jogadores fixos atrás da linha da bola ao atacar (o maior perigo veio de contra-ataque)")
        if "bola parada" in top or "escanteio" in top:
            tips.append("rever a marcação na bola parada e ter alguém na segunda bola (foi de onde saiu mais xG)")
        if c["dentro_da_area"] >= max(6, 0.6 * c["chutes"]):
            tips.append("proteger a entrada da área: a maioria dos chutes foi de dentro dela, sinal de chegadas limpas")
        if az and max(az.get("left", 0), az.get("right", 0)) >= 40:
            lado = "esquerda" if az.get("left", 0) >= az.get("right", 0) else "direita"
            tips.append(f"fechar o corredor da {lado} do rival, que concentrou o ataque deles")
        if tips:
            lines.append("💡 **O que dava para fazer (hipóteses pelos números):** " + "; ".join(tips) + ".")
        return "\n\n".join(lines)
    if "historia_box" in b:
        h = b["historia_box"]
        t = h["times"]
        fz = h["finalizacoes"]
        lines = []
        if len(t) == 2:
            a, c = fz.get(t[0], {}), fz.get(t[1], {})
            lines.append(f"**Chances:** {t[0]} xG {_f(a.get('xg'))} em {a.get('chutes')} chutes ({a.get('chutes_dentro_da_area')} de dentro da área) "
                         f"× {t[1]} xG {_f(c.get('xg'))} em {c.get('chutes')} ({c.get('chutes_dentro_da_area')} de dentro da área).")
        if h.get("momentum_1t") is not None:
            def who(v):
                return (t[0] if v > 0 else t[1]) if v else "equilíbrio"
            lines.append(f"**Momentum (FotMob, + = {t[0]}):** no 1º tempo quem esteve por cima foi {who(h['momentum_1t'])} "
                         f"({_f(h['momentum_1t'])}); no 2º, {who(h['momentum_2t'])} ({_f(h['momentum_2t'])}).")
        if h.get("destaques"):
            lines.append("**Melhores notas da FotMob:** " + ", ".join(f"{x['jogador']} ({x['equipe']}, {_f(x['nota_fotmob'])})" for x in h["destaques"]) + ".")
        lines.append("_Leitura pelos números da FotMob (este jogo não tem lances com coordenadas): fatores que acompanharam o "
                     "resultado, não prova de causa._")
        return "\n\n".join(lines)
    return ""
