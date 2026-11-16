"""
Por que um time venceu (rodada 5) — raciocínio em etapas, sem template de "placar + tabela".

1. Descobre vencedor e perdedor (no tempo de jogo; a disputa de pênaltis só desempata o resultado).
2. Mede CANDIDATOS a explicação, cada um com número e comparação com o rival:
   qualidade das chances (xG, grandes chances), território (campo rival, entradas na área), jogo entre linhas,
   como saíram os gols (contra-ataque, bola parada, cruzamento…), pressão e recuperações, eficiência (gols − xG),
   erros do rival que viraram chance, protagonistas e a dupla que mais construiu, e o momento do jogo.
3. Ordena os candidatos pela FORÇA da diferença e escreve só os mais fortes — o resto não entra.
4. Separa: 📊 fato (contagem direta) · 🧠 leitura (interpretação de vários números) · 💡 hipótese (não comprovável).
Nada aqui afirma causa: são os fatores que mais acompanharam o resultado.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def _winner(df: pd.DataFrame, teams: List[str]) -> Dict[str, Any]:
    from src.metrics.match_facts import shootout, team_match_stats

    g = {t: int(team_match_stats(df, t).get("gols") or 0) for t in teams}
    pen = shootout(df) or {}
    if g[teams[0]] != g[teams[1]]:
        w = max(g, key=g.get)
        return {"vencedor": w, "perdedor": next(t for t in teams if t != w), "placar": g, "penaltis": pen or None, "empate": False}
    if pen and len(set(pen.values())) > 1:
        w = max(pen, key=pen.get)
        return {"vencedor": w, "perdedor": next(t for t in teams if t != w), "placar": g, "penaltis": pen, "empate": True}
    return {"vencedor": None, "perdedor": None, "placar": g, "penaltis": None, "empate": True}


def _rel(a: Optional[float], b: Optional[float]) -> float:
    """Força relativa da vantagem de a sobre b (0 = igual; 1 = o dobro)."""
    if a is None or b is None:
        return 0.0
    a, b = float(a), float(b)
    return (a - b) / max(abs(b), 1e-6) if b else (1.0 if a > 0 else 0.0)


def build(df: pd.DataFrame, focus: str, opp: str) -> Dict[str, Any]:
    """Bloco de evidências 'por que venceu' (do ponto de vista de quem venceu; se empatou, compara os dois)."""
    from src.intelligence import tactical_blocks as T
    from src.metrics.match_facts import player_match_stats, team_match_stats

    play = df[pd.to_numeric(df["period"], errors="coerce").fillna(1) < 5] if "period" in df else df
    teams = [focus, opp]
    res = _winner(df, teams)
    w = res["vencedor"] or focus
    l = res["perdedor"] or opp
    sw, sl = team_match_stats(play, w), team_match_stats(play, l)
    eff = T.efficiency(play, [w, l])["equipes"]
    build_w = T.goal_buildup(play, w)
    conc = T.conceded_how(play, l, w)
    bl_w, bl_l = T.between_lines(play, w, l), T.between_lines(play, l, w)
    corr = T.corridors(play, w)
    mom = T.moments(play, [w, l])
    errs = T.dangerous_errors(play, l)
    duo = T.combinations(play, w, top=1)
    pw = player_match_stats(play, w)
    cands: List[Dict[str, Any]] = []

    def add(chave, forca, fato, leitura, nums):
        cands.append({"chave": chave, "forca": round(float(forca), 3), "fato": fato, "leitura": leitura, "numeros": nums})

    xa, xb = eff[w]["xg"], eff[l]["xg"]
    if xa > xb:
        add("chances", min(_rel(xa, xb), 2.0) + 0.3 * (eff[w]["grandes_chances"] - eff[l]["grandes_chances"]),
            f"{w} criou xG {xa} contra {xb} de {l}, com {eff[w]['grandes_chances']} grandes chances contra {eff[l]['grandes_chances']}.",
            f"{w} chegou em condição melhor de finalizar: não foi só volume, foi qualidade de chance.",
            {"xg": {w: xa, l: xb}, "grandes_chances": {w: eff[w]["grandes_chances"], l: eff[l]["grandes_chances"]}})
    ft_w, ft_l = sw.get("field_tilt_pct"), sl.get("field_tilt_pct")
    if ft_w and ft_l and ft_w > ft_l:
        add("territorio", _rel(ft_w, ft_l) * 0.8 + 0.05 * (sw.get("entradas_na_area", 0) - sl.get("entradas_na_area", 0)),
            f"{ft_w}% dos passes no terço final foram de {w} (field tilt) e {w} entrou {sw.get('entradas_na_area')} vezes na área "
            f"contra {sl.get('entradas_na_area')}.",
            f"{w} empurrou {l} para trás e passou mais tempo perto da área rival.",
            {"field_tilt_pct": {w: ft_w, l: ft_l}, "entradas_na_area": {w: sw.get("entradas_na_area"), l: sl.get("entradas_na_area")}})
    rw, rl = bl_w.get("recepcoes_entre_linhas", 0), bl_l.get("recepcoes_entre_linhas", 0)
    if rw > rl and rw >= 10:
        who = list((bl_w.get("quem_recebeu") or {}).items())[:2]
        add("entre_linhas", _rel(rw, rl) * 0.7,
            f"{w} recebeu {rw} bolas entre a defesa e o meio de {l} (contra {rl} do rival)"
            + (f", sobretudo com {who[0][0]} ({who[0][1]})" + (f" e {who[1][0]} ({who[1][1]})" if len(who) > 1 else "") if who else "")
            + f"; {bl_w.get('posses_que_terminaram_em_finalizacao', 0)} dessas posses terminaram em finalização.",
            f"O espaço entre as linhas de {l} ficou aberto e {w} soube achar quem estava nele.",
            {"entre_linhas": {w: rw, l: rl}, "quem_recebeu": dict(who)})
    pats = build_w.get("padroes") or {}
    if pats and build_w.get("amostra_N"):
        top, n = next(iter(pats.items()))
        n_goals = build_w["amostra_N"]
        add("gols", 0.4 + 0.25 * n,
            f"Gols de {w}: " + "; ".join(f"{g['minuto']}' {g['jogador']} ({g['tipo']}"
                                          + (f", {g['passes_na_jogada']} passes em {int(g['segundos'] or 0)} s" if g["tipo"] != "pênalti" else "")
                                          + ")" for g in build_w["gols"]) + ".",
            (f"{n} dos {n_goals} gols vieram de {top}" if n > 1 else f"os gols saíram de jogadas diferentes ({', '.join(pats)})")
            + (" — a vitória teve muito de transição rápida." if "contra-ataque" in top and n > 1 else "."),
            {"padroes": pats})
    ppda_w, ppda_l = sw.get("ppda"), sl.get("ppda")
    if ppda_w and ppda_l and ppda_w < ppda_l:
        add("pressao", _rel(ppda_l, ppda_w) * 0.6 + 0.01 * (sw.get("recuperacoes", 0) - sl.get("recuperacoes", 0)),
            f"{w} deixou {l} trocar só {ppda_w} passes por ação defensiva no campo rival (PPDA estimado; {l}: {ppda_l}) "
            f"e recuperou {sw.get('recuperacoes')} bolas (contra {sl.get('recuperacoes')}).",
            f"A pressão de {w} encurtou o tempo de {l} para construir.",
            {"ppda": {w: ppda_w, l: ppda_l}, "recuperacoes": {w: sw.get("recuperacoes"), l: sl.get("recuperacoes")}})
    gmx_w, gmx_l = eff[w]["gols_menos_xg"], eff[l]["gols_menos_xg"]
    if gmx_w > 0.5 and gmx_w > gmx_l:
        add("eficiencia", 0.3 + gmx_w * 0.4,
            f"{w} marcou {eff[w]['gols']} gols com xG {xa} (saldo +{gmx_w}).",
            f"{w} foi mais eficiente do que as chances indicavam — parte do placar veio da finalização acima da média.",
            {"gols_menos_xg": {w: gmx_w, l: gmx_l}})
    bad = [e for e in errs.get("jogadores") or [] if e["viraram_finalizacao"]]
    if bad:
        tot = sum(e["viraram_finalizacao"] for e in bad)
        gs = sum(e["gols_sofridos"] for e in bad)
        add("erros_rival", 0.25 * tot + 0.6 * gs,
            f"{tot} perdas de bola de {l} viraram finalização de {w} em até 15 s"
            + (f", {gs} delas em gol" if gs else "") + f" (mais: {bad[0]['jogador']}, {bad[0]['viraram_finalizacao']}).",
            f"{l} errou em lugares que custam caro e {w} castigou rápido.",
            {"erros": {e["jogador"]: e["viraram_finalizacao"] for e in bad[:3]}})
    tipos = conc.get("tipos") or []
    if tipos:
        t0 = tipos[0]
        add("como_sofreu", 0.2 + 0.3 * t0["gols"],
            f"{l} sofreu mais finalizações por {t0['tipo']} ({t0['finalizacoes']}, xG {t0['xg']}, {t0['gols']} gols).",
            f"O ponto mais frágil de {l} foi {t0['tipo']}.",
            {"tipo": t0["tipo"], "finalizacoes": t0["finalizacoes"], "xg": t0["xg"]})
    # protagonistas e dupla
    stars: Dict[str, Any] = {}
    if not pw.empty:
        top_xt = pw.sort_values("xt", ascending=False).iloc[0]
        stars = {"jogador": top_xt["jogador"], "xt": round(float(top_xt["xt"]), 3), "xg": round(float(top_xt.get("xg", 0) or 0), 2)}
    pair = (duo.get("duplas") or [None])[0] if isinstance(duo, dict) else None
    # momento: janela de maior domínio do vencedor
    win_mom = None
    for j in mom.get("janelas") or []:
        a, b = j.get(w, {}), j.get(l, {})
        d = (a.get("xg", 0) or 0) - (b.get("xg", 0) or 0)
        if win_mom is None or d > win_mom["dif_xg"]:
            win_mom = {"janela": j["janela"], "dif_xg": round(d, 2), "xg": a.get("xg"), "xg_rival": b.get("xg")}
    cands.sort(key=lambda c: -c["forca"])
    main = cands[:3]
    hyps = []
    keys = {c["chave"] for c in main}
    if "entre_linhas" in keys:
        hyps.append(f"{l} talvez sofresse menos com um volante a mais protegendo a entrada da área — mas isso não "
                    f"dá para provar com os dados; tiraria gente da saída de bola.")
    if "pressao" in keys or "erros_rival" in keys:
        hyps.append(f"Sair jogando mais longo nos momentos de pressão poderia ter evitado parte das perdas de {l}, "
                    f"ao custo de entregar a posse.")
    if "gols" in keys and "contra-ataque" in str(pats):
        hyps.append(f"Manter um ou dois jogadores fixos atrás da linha da bola ao atacar reduziria os contra-ataques "
                    f"de {w} — hipótese, não comprovada.")
    if not hyps and corr.get("corredores"):
        c0 = corr["corredores"][0]
        hyps.append(f"Fechar o {c0['corredor']} (por onde {w} mais criou: xT {c0['xt']}) poderia mudar o jogo — hipótese.")
    return {"resultado": res, "vencedor": w, "perdedor": l, "fatores": main, "fatores_descartados": [c["chave"] for c in cands[3:]],
            "protagonista": stars, "dupla": pair, "momento": win_mom, "hipoteses": hyps[:2],
            "estatisticas": {w: {k: sw.get(k) for k in ("gols", "xg", "finalizacoes", "field_tilt_pct", "entradas_na_area", "ppda")},
                             l: {k: sl.get(k) for k in ("gols", "xg", "finalizacoes", "field_tilt_pct", "entradas_na_area", "ppda")}}}


def write(b: Dict[str, Any], fmt) -> str:
    """Texto natural: resposta curta → fatos → leitura → hipóteses."""
    r = b["resultado"]
    w, l = b["vencedor"], b["perdedor"]
    pl = r["placar"]
    score = f"{w} {pl[w]} x {pl[l]} {l}" + (f" (pênaltis {r['penaltis'][w]} x {r['penaltis'][l]})" if r.get("penaltis") and r["empate"] else "")
    f = b["fatores"]
    if r["vencedor"] is None:
        head = f"Foi empate ({score}). Olhando o que cada lado produziu:"
    elif not f:
        head = f"{w} venceu ({score}), mas os números do jogo ficaram parelhos — não há um fator que se destaque com clareza."
    else:
        lead = {"chances": "criou chances melhores", "territorio": "dominou o território", "entre_linhas": "achou espaço entre as linhas",
                "gols": "foi letal no tipo de jogada que mais funcionou", "pressao": "pressionou melhor",
                "eficiencia": "aproveitou melhor o que criou", "erros_rival": "castigou os erros do rival",
                "como_sofreu": f"explorou o ponto fraco de {l}"}
        reasons = [lead[c["chave"]] for c in f[:2]]
        tail = (" — e venceu nos pênaltis" if r["empate"] else "")
        head = f"**{w} venceu ({score}) porque {' e '.join(reasons)}{tail}.**"
    out = [head, "", "**📊 O que os dados mostram**"]
    out += [f"- {c['fato']}" for c in f]
    if b.get("protagonista"):
        p = b["protagonista"]
        out.append(f"- Quem mais levou {w} para perto do gol foi {p['jogador']} (xT {fmt(p['xt'])}, xG {fmt(p['xg'])}).")
    if b.get("dupla"):
        d = b["dupla"]
        a_, b_ = d.get("de") or d.get("passador"), d.get("para") or d.get("receptor")
        if a_ and b_ and d.get("passes"):
            out.append(f"- A ligação mais usada foi {a_} → {b_} ({d['passes']} passes).")
    if b.get("momento") and b["momento"]["dif_xg"] > 0.2:
        m = b["momento"]
        out.append(f"- O melhor período de {w} foi {m['janela']} (xG {fmt(m['xg'])} contra {fmt(m['xg_rival'])}).")
    if f:
        out += ["", "**🧠 Leitura**"] + [f"- {c['leitura']}" for c in f]
    if b.get("hipoteses"):
        out += ["", "**💡 Hipóteses (não dá para comprovar com estes dados)**"] + [f"- {h}" for h in b["hipoteses"]]
    out.append("")
    out.append("_Fatores que acompanharam o resultado — não prova de causa. Disputa de pênaltis fora das contas do jogo._")
    return "\n".join(out)
