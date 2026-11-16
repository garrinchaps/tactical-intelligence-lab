"""Redação (linguagem de futebol) dos blocos de `tactical_blocks.py`. Cada função devolve (texto, frase do resumo)."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def _f(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:.0f}"
    return str(v)


def _pl(n, s, p):
    return f"{n} {s if n == 1 else p}"


def corredores(W, b, sc) -> Tuple[str, str]:
    c = [x for x in b["corredores"] if x["progressoes"]]
    if not c:
        return f"{b['equipe']} não teve ações progressivas registradas no recorte.", ""
    lines = "\n".join(f"- **{x['corredor'].capitalize()}**: {x['progressoes']} progressões ({_f(x['pct'])}%), "
                      f"{x['entradas_na_area']} entradas na área, xT {_f(x['xt'])}"
                      + (" — " + ", ".join(f"{k} ({v})" for k, v in x['principais'].items()) if x['principais'] else "")
                      for x in c)
    top = c[0]
    return (f"**Por onde {b['equipe']} avançou** (passes e conduções que levaram a bola para frente, por faixa do campo; "
            f"ordenado pelo perigo gerado):\n{lines}"), \
        f"{b['equipe']} progrediu com mais perigo pelo {top['corredor']}"


def como_sofreu(W, b, sc) -> Tuple[str, str]:
    t = b["tipos"]
    if not t:
        return f"{b['atacante']} não finalizou no recorte.", ""
    lines = "\n".join(f"- **{x['tipo'].capitalize()}**: {_pl(x['finalizacoes'], 'finalização', 'finalizações')}, xG {_f(x['xg'])}"
                      + (f", {_pl(x['gols'], 'gol', 'gols')}" if x['gols'] else "") for x in t)
    return (f"**Como {b['defensor']} sofreu as chances de {b['atacante']}** ({b['finalizacoes']} finalizações, xG "
            f"{_f(b['xg'])}, {b['gols']} gols), pelo tipo da jogada que antecedeu cada finalização:\n{lines}\n\n"
            "_Classificação pelo último passe da jogada: enfiada = bola nas costas; cruzamento; bola longa (≥ 32 m); "
            "passe terminando no corredor central = infiltração pelo meio._"), \
        f"{b['defensor']} sofreu mais com {t[0]['tipo']} (xG {_f(t[0]['xg'])})"


def entre_linhas(W, b, sc) -> Tuple[str, str]:
    n = b["recepcoes_entre_linhas"]
    who = ", ".join(f"{k} ({v})" for k, v in b["quem_recebeu"].items())
    feed = ", ".join(f"{k} ({v})" for k, v in b["quem_passou"].items())
    tempos = " · ".join(f"{k}º tempo: {v}" if k <= 2 else f"prorrogação ({k - 2}ª etapa): {v}"
                        for k, v in sorted(b["por_tempo"].items()))
    return (f"**{b['atacante']} recebeu {n} bolas entre as linhas de {b['defensor']}** ({b['zona']}); "
            f"{b['posses_que_terminaram_em_finalizacao']} dessas posses terminaram em finalização."
            + (f"\n- Quem achou esse espaço: {who}." if who else "") + (f"\n- Quem colocou a bola lá: {feed}." if feed else "")
            + (f"\n- Por tempo: {tempos}." if tempos else "")), \
        (f"{list(b['quem_recebeu'])[0]} foi quem mais recebeu entre as linhas" if b["quem_recebeu"] else
         f"{b['atacante']} quase não recebeu entre as linhas")


def eficiencia(W, b, sc) -> Tuple[str, str]:
    e = b["equipes"]
    teams = list(e)
    rows = [("Finalizações", "finalizacoes"), ("No alvo", "no_alvo"), ("Gols", "gols"), ("xG", "xg"),
            ("xG por finalização", "xg_por_finalizacao"), ("Gols − xG", "gols_menos_xg"), ("Conversão (%)", "conversao_pct"),
            ("Grandes chances (xG ≥ 0,3)", "grandes_chances"), ("Grandes chances convertidas", "grandes_chances_convertidas"),
            ("Entradas na área", "entradas_na_area"), ("Finalizações por entrada na área", "finalizacoes_por_entrada")]
    tab = "| | " + " | ".join(teams) + " |\n|---|" + "---|" * len(teams) + "\n" + \
          "\n".join(f"| {lab} | " + " | ".join(_f(e[t].get(k)) for t in teams) + " |" for lab, k in rows)
    a, c = teams[0], teams[1] if len(teams) > 1 else teams[0]
    read = []
    if e[a]["xg_por_finalizacao"] and e[c]["xg_por_finalizacao"]:
        hi = a if e[a]["xg_por_finalizacao"] > e[c]["xg_por_finalizacao"] else c
        read.append(f"{hi} finalizou de posições melhores ({_f(e[hi]['xg_por_finalizacao'])} de xG por chute)")
    for t in teams:
        d = e[t]["gols_menos_xg"]
        if d is not None and abs(d) >= 0.8:
            read.append(f"{t} {'marcou bem acima' if d > 0 else 'marcou bem abaixo'} do que as chances valiam ({_f(d):s} gols)")
    return ("**Eficiência no ataque:**\n" + tab + ("\n\n" + "; ".join(read) + "." if read else "")), (read[0] if read else "")


def momentos(W, b, sc) -> Tuple[str, str]:
    rows = b["janelas"]
    teams = [k for k in rows[0] if k != "janela"] if rows else []
    foco = b.get("foco") or (teams[0] if teams else "")
    lines = "\n".join(f"- **{r['janela']}**: " + " · ".join(
        f"{t} {r[t]['finalizacoes']} fin., xG {_f(r[t]['xg'])}, {r[t]['entradas_na_area']} entradas"
        + (f", {_pl(r[t]['gols'], 'gol', 'gols')}" if r[t]['gols'] else "") for t in teams) for r in rows)
    best = b["melhor_janela"].get(foco)
    return (f"**Momentos do jogo, de 15 em 15 minutos:**\n{lines}"
            + (f"\n\nO melhor período de {foco} foi **{best}** (mais xG e entradas na área)." if best else "")), \
        (f"{foco} foi mais perigoso entre {best}" if best else "")


def jogadas_dos_gols(W, b, sc) -> Tuple[str, str]:
    g = b["gols"]
    if not g:
        return f"{b['equipe']} não marcou no recorte.", ""
    lines = "\n".join(f"- **{x['minuto']}' {x['jogador']}** — {x['tipo']}: {_pl(x['passes_na_jogada'], 'passe', 'passes')}"
                      + (f" em {_f(x['segundos'])} s" if x['segundos'] is not None else "") + f", começou no {x['inicio']}"
                      + (f"; último passe de {x['ultimo_passe']} pelo {x['corredor_do_ultimo_passe']}" if x['ultimo_passe'] else "")
                      for x in g)
    pat = ", ".join(f"{k} ({v})" for k, v in b["padroes"].items())
    rep = [k for k, v in b["padroes"].items() if v >= 2]
    return (f"**Como nasceram os gols de {b['equipe']}:**\n{lines}\n\n**Padrões:** {pat}."
            + (f" Repetiu-se: {', '.join(rep)}." if rep else " Nenhum tipo de jogada se repetiu.")), \
        (f"o padrão que se repetiu nos gols de {b['equipe']} foi {rep[0]}" if rep else "")


def defensores(W, b, sc) -> Tuple[str, str]:
    d = b["defensores"]
    if not d:
        return f"Não há defensores de {b['equipe']} com lances suficientes no recorte.", ""
    parts = []
    for x in d:
        probs = x["problemas"]
        head = (f"**{x['jogador']}** ({x.get('posicao') or 'defesa'}, {_f(x['minutos'])} min, nota {_f(x['nota'])}): "
                f"{x['desarmes']} desarmes, {x['interceptacoes']} interceptações, {x['cortes']} cortes")
        if probs:
            head += ". Vulnerabilidades: " + "; ".join(f"{p['quantas']} {p['o_que']} → {p['correcao']}" for p in probs) + "."
        else:
            head += ". Sem falha que se destaque nos números."
        parts.append("- " + head)
    worst = next((x for x in d if x["problemas"]), None)
    return (f"**Diagnóstico individual da defesa de {b['equipe']}** (do pior para o melhor pela nota da atuação):\n"
            + "\n".join(parts)), \
        (f"o ponto mais frágil da defesa de {b['equipe']} foi {worst['jogador']} ({worst['problemas'][0]['o_que']})" if worst else "")


def duplas(W, b, sc) -> Tuple[str, str]:
    d = b["duplas"]
    if not d:
        return "Sem passes certos suficientes para formar duplas.", ""
    lines = "\n".join(f"{i}. {x['de']} → {x['para']} ({x['equipe']}): {x['passes']} passes, {x['progressivos']} para frente, "
                      f"xT {_f(x['xt'])}" for i, x in enumerate(d, 1))
    return (f"**Duplas que mais levaram a bola para perto do gol** (passes certos entre os dois, ordenados pelo xT):\n{lines}"), \
        f"a ligação {d[0]['de']} → {d[0]['para']} foi a que mais gerou perigo"


def plano_ataque(W, b, sc) -> Tuple[str, str]:
    att, dfd = b["atacante"], b["defensor"]
    steps = []
    mc = b.get("melhor_corredor")
    if mc and mc["progressoes"]:
        from src.intelligence.tactical_blocks import _side_of_defense

        steps.append(f"**Insistir pelo {mc['corredor']}** (o {_side_of_defense(mc['corredor'])} de {dfd}): foi por ali que "
                     f"{att} mais avançou com perigo — {mc['progressoes']} progressões e {mc['entradas_na_area']} entradas na área.")
    how = b.get("como_o_defensor_sofreu") or []
    if how:
        steps.append(f"**Repetir o tipo de jogada que machucou:** {dfd} sofreu mais com {how[0]['tipo']} "
                     f"({how[0]['finalizacoes']} finalizações, xG {_f(how[0]['xg'])})"
                     + (f"; depois, {how[1]['tipo']} (xG {_f(how[1]['xg'])})" if len(how) > 1 else "") + ".")
    if b.get("perdas_do_defensor_no_proprio_campo"):
        z = b.get("zonas_das_perdas") or {}
        steps.append(f"**Pressionar a saída de bola:** {dfd} perdeu a bola {b['perdas_do_defensor_no_proprio_campo']} vezes no "
                     "próprio campo" + (", mais pelo " + " e pelo ".join(z) if z else "") + ". Subir a marcação ali rende roubada perto do gol.")
    drib = b.get("defensores_mais_driblados") or {}
    if drib:
        steps.append("**Atacar no 1x1 quem foi driblado:** " + ", ".join(f"{k} ({v}x)" for k, v in drib.items()) + ".")
    air = b.get("perdeu_mais_no_alto") or {}
    if air:
        steps.append("**Bola aérea em cima de quem perdeu no alto:** " + ", ".join(f"{k} ({v})" for k, v in air.items()) + ".")
    errs = [e for e in b.get("erros_que_viraram_finalizacao") or [] if e.get("viraram_finalizacao")]
    if errs:
        steps.append("**Pressionar quem errou sob pressão:** " + ", ".join(
            f"{e['jogador']} ({e['viraram_finalizacao']} perdas viraram finalização)" for e in errs) + ".")
    if not steps:
        return f"Os números deste jogo não mostram uma fragilidade clara de {dfd} para explorar.", ""
    return (f"**Como {att} pode explorar a defesa de {dfd}** (com base nos números desta partida):\n"
            + "\n".join(f"{i}. {x}" for i, x in enumerate(steps, 1)) + "\n\n_Leitura feita a partir dos números do jogo — não é previsão._"), \
        f"o caminho para machucar {dfd} é {'o ' + mc['corredor'] if mc else 'a pressão na saída de bola'}"


TACTICAL_WRITERS: Dict[str, Any] = {
    "corredores": corredores, "como_sofreu": como_sofreu, "entre_linhas": entre_linhas, "eficiencia": eficiencia,
    "momentos": momentos, "jogadas_dos_gols": jogadas_dos_gols, "defensores": defensores, "duplas": duplas,
    "plano_ataque": plano_ataque,
}
