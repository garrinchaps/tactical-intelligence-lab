"""
Analista tático dinâmico (substitui o relatório-modelo nas perguntas do usuário).

Fluxo:
1. QueryUnderstanding → escopo (fora do tema? recorte? atleta? métricas?).
2. ScopedEvidenceBuilder → só as evidências do recorte (ou boxscore, se a partida não tem eventos).
3. Redação:
   * com GEMINI_API_KEY: o Gemini escreve do zero, em estrutura livre adaptada à pergunta,
     usando exclusivamente o JSON do recorte; o texto passa pelo NumericHallucinationGuard
     e é bloqueado se citar número ou atleta fora das evidências;
   * sem chave (ou se bloqueado): o redator local monta frases apenas com os blocos
     calculados para aquela pergunta — nada de seções fixas para todo tipo de pergunta.
4. Relatório completo só quando o usuário pede ("relatório completo", "análise completa").
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

from src.intelligence.query_understanding import QueryScope, QueryUnderstanding
from src.intelligence.query_understanding import norm as norm_q
from src.intelligence.scoped_evidence import ScopedEvidenceBuilder
from src.reports.report_builder import NumericHallucinationGuard, TacticalReportBuilder

load_dotenv()

DYNAMIC_SYSTEM = """Você é o analista de desempenho de uma comissão técnica de futebol.
Responda à pergunta do usuário usando EXCLUSIVAMENTE o JSON de evidências recortadas.

Como escrever:
- Comece direto pela resposta. Sem saudação, sem repetir a pergunta, sem introdução.
- A estrutura depende da pergunta: uma pergunta pontual pede 2 a 4 frases; uma comparação pede uma lista curta;
  um plano de jogo pede passos numerados. Não use seções fixas.
- Fale só do recorte pedido (minutos, lado, fase, atleta). Ignore o resto do jogo, exceto a comparação
  "resto do jogo" quando ela estiver no JSON.
- No máximo ~180 palavras antes do resumo.
- Termine SEMPRE com uma linha "**Resumo executivo:**" de 1 ou 2 frases simples para a comissão técnica.

Regras de fidelidade (obrigatórias):
- Copie números exatamente como estão no JSON. Não calcule diferenças, médias ou porcentagens novas.
- Não cite atletas que não estejam em metadata.match_player_roster.
- Se amostra_N for menor que 15, diga que a amostra é pequena.
- "compactacao_estimada" é proxy sem tracking: diga isso se usar.
- Se blocos.limitacao não estiver vazio, explique a limitação na primeira frase.
- Se metadata.is_simulation_data for true, a primeira linha deve ser: ⚠️ [DADOS SIMULADOS / MODELAGEM PROBABILÍSTICA].
- Se houver um bloco "ia" ou "lideres_ia" (rede neural de perigo), use-o e cite a versão do modelo e a AUC de validação.
- Em perguntas de estratégia ("como anular", "qual tática"), responda com passos numerados, cada um justificado por um número do JSON."""

OFF_TOPIC_SYSTEM = """Você é o analista tático do Tactical Intelligence Lab. O usuário perguntou algo fora de futebol.
Responda em no máximo 2 frases, com bom humor e com precisão sobre o que foi perguntado (sem inventar fatos),
e em seguida convide a pessoa a perguntar sobre a partida carregada, com 2 exemplos curtos de perguntas.
Não cite números nem estatísticas."""


def _pl(n: Any, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


class LocalScopedWriter:
    """Redator local: só escreve sobre os blocos calculados para a pergunta."""

    @staticmethod
    def _small_sample(n: Optional[int]) -> str:
        return f" ⚠️ Amostra pequena (N = {n}): trate como indício, não como padrão." if n is not None and n < 15 else ""

    @classmethod
    def write(cls, ev: Dict[str, Any], sc: QueryScope) -> str:
        meta, blocks = ev["metadata"], ev["blocos"]
        team, opp = meta["target_team"], meta["opponent_team"]
        out: List[str] = []
        if meta.get("is_simulation_data"):
            out.append("⚠️ [DADOS SIMULADOS / MODELAGEM PROBABILÍSTICA]")
        summary: List[str] = []

        for key, b in blocks.items():
            if key == "gols":
                from src.metrics.match_facts import goal_line

                pl = b["placar"]
                (t1, g1), (t2, g2) = list(pl.items())
                if not b["gols"]:
                    out.append(f"**Placar:** {t1} {g1} x {g2} {t2}. Não houve gols no tempo de jogo.")
                else:
                    out.append(f"**Placar:** {t1} {g1} x {g2} {t2}.")
                    for tm in (t1, t2):
                        lines = [goal_line(g) for g in b["gols"] if g["equipe"] == tm]
                        if lines:
                            out.append(f"**Gols de {tm}:** " + "; ".join(lines) + ".")
                pen = b.get("disputa_de_penaltis")
                if pen:
                    out.append("**Disputa de pênaltis:** " + " x ".join(f"{k} {v}" for k, v in pen.items()) + ".")
                assists: Dict[str, int] = {}
                for g in b["gols"]:
                    if g.get("assistencia"):
                        assists[g["assistencia"]] = assists.get(g["assistencia"], 0) + 1
                if assists:
                    out.append("**Assistências:** " + "; ".join(f"{k} ({v})" for k, v in sorted(assists.items(), key=lambda kv: -kv[1]))
                               + ". _Assistência = último passe certo para o autor do gol na mesma posse._")
                if "assist" in norm_q(sc.raw) and assists:
                    top = max(assists.items(), key=lambda kv: kv[1])
                    summary.append(f"{top[0]} deu {_pl(top[1], 'assistência', 'assistências')}")
                scorers: Dict[str, int] = {}
                for g in b["gols"]:
                    if not g["gol_contra"]:
                        scorers[g["jogador"]] = scorers.get(g["jogador"], 0) + 1
                if scorers and not summary:
                    best = max(scorers.items(), key=lambda kv: kv[1])
                    summary.append(f"{best[0]} marcou {_pl(best[1], 'gol', 'gols')}" if best[1] > 1 else
                                   f"{len(b['gols'])} gols de {len(scorers)} autores diferentes")
                continue
            if key == "ranking" and b.get("chave") == "perigo_ia":
                out.append(cls._danger_ranking(b))
                if b.get("lideres_ia"):
                    l0 = b["lideres_ia"][0]
                    summary.append(f"segundo a rede neural, {l0['jogador']} criou mais ações perigosas ({l0['acoes_perigosas']})")
                continue
            if key == "ranking":
                lid = b["lideres"]
                if not lid:
                    out.append(f"Nenhum atleta registrou {b['metrica'].lower()} no recorte.")
                    continue
                head = f"**{b['metrica']} — {b['equipes_consideradas']}" + (f", {sc.describe()}" if sc.has_cut else "") + ":**"
                rows = "\n".join(f"{i}. {r['jogador']} ({r['equipe']}): {_fmt(r['valor'])}"
                                  + (f" · {r['secundaria'].lower()}: {_fmt(r['valor_secundario'])}" if r.get("secundaria") else "")
                                  for i, r in enumerate(lid, 1))
                out.append(head + "\n" + rows)
                lab = b["metrica"] if b["metrica"].startswith("x") else b["metrica"].lower()
                summary.append(f"{lid[0]['jogador']} liderou em {lab} ({_fmt(lid[0]['valor'])})")
                continue
            if key.startswith("plano_jogador::"):
                out.append(cls._plan_player(b))
                if b.get("jogou"):
                    f = list((b.get("quem_mais_o_abastece") or {}).keys())
                    summary.append(f"para anular {b['jogador']}, cortar a ligação com {f[0]}" if f else
                                   f"para anular {b['jogador']}, fechar {b['zonas_onde_age'][0]['zona']}" if b.get("zonas_onde_age")
                                   else f"{b['jogador']} teve pouca participação")
                continue
            if key == "plano_equipe":
                out.append(cls._plan_team(b))
                z = b.get("corredores_das_entradas_na_area_do_adversario") or []
                mine = {"esquerda": "o lado direito", "direita": "o lado esquerdo", "centro": "o corredor central"}
                summary.append(f"{b['equipe']} precisava proteger {mine[z[0]['zona'].split(' — ')[-1]]} e reduzir as perdas no próprio campo"
                               if z else f"{b['equipe']} precisava reduzir as perdas no próprio campo")
                continue
            if key == "resultado":
                from src.metrics.match_facts import goal_line

                comp = b["comparativo"]
                g = comp["Gols"]
                win = max(g, key=g.get) if len(set(g.values())) > 1 else None
                pen = b.get("disputa_de_penaltis")
                by_pen = False
                if win is None and pen and len(set(pen.values())) > 1:
                    win, by_pen = max(pen, key=pen.get), True
                lose = next((k for k in g if k != win), None) if win else None
                out.append(f"**Placar:** " + " x ".join(f"{k} {v}" for k, v in g.items()) + "."
                           + (" Nos pênaltis: " + " x ".join(f"{k} {v}" for k, v in pen.items()) + "." if pen else ""))
                if b["gols"]:
                    out.append("**Gols:** " + "; ".join(f"{goal_line(x)} — {x['equipe']}" for x in b["gols"]) + ".")
                rows = "\n".join(f"| {lab} | " + " | ".join(_fmt(v) for v in vals.values()) + " |" for lab, vals in comp.items())
                teams_h = list(g.keys())
                out.append(f"| Indicador | {teams_h[0]} | {teams_h[1]} |\n|---|---|---|\n{rows}")
                if win:
                    edges = [lab for lab, vals in comp.items() if lab not in ("Gols", "PPDA (estimado)", "Perdas de posse")
                             and vals.get(win) is not None and vals.get(lose) is not None and vals[win] > vals[lose]]
                    p = comp.get("PPDA (estimado)", {})
                    if p.get(win) is not None and p.get(lose) is not None and p[win] < p[lose]:
                        edges.append("pressão mais intensa (PPDA menor)")
                    if by_pen:
                        out.append(f"Empate no tempo de jogo; {win} venceu na disputa de pênaltis.")
                    out.append(f"**Onde {win} foi superior{' durante o jogo' if by_pen else ''}:** " + (", ".join(e if e.startswith("x") else e.lower() for e in edges[:6]) + "." if edges else
                               "os números de volume ficaram equilibrados ou a favor do rival; a vitória veio da eficiência nas finalizações."))
                    verb = "venceu nos pênaltis" if by_pen else "venceu"
                    summary.append(f"{win} {verb}, com vantagem em {len(edges)} dos indicadores comparados" if edges
                                   else f"{win} {verb} sendo mais eficiente nas finalizações")
                else:
                    summary.append("o jogo terminou empatado no tempo de jogo")
                continue
            if key == "contexto":
                gols = b.get("gols_no_recorte") or []
                if gols and (sc.minute_from is not None or sc.period):
                    out.append("Gols no recorte: " + "; ".join(
                        f"{g['minuto']}' {g['jogador']} ({g['equipe']})" for g in sorted(gols, key=lambda g: g["minuto"])) + ".")
            elif key == "defesa_no_recorte":
                c = b["compactacao_estimada"]
                out.append(
                    f"**Sem a bola — {b['setor']}:** {opp} levou {b['acoes_adversarias_que_chegaram_ao_setor']} ações ao setor "
                    f"({b['acoes_adversarias_completas_no_setor']} completas), com {b['progressoes_adversarias_no_setor']} progressões, "
                    f"{_pl(b['entradas_na_area_vindas_do_setor'], 'entrada', 'entradas')} na área e {_pl(b['finalizacoes_cedidas'], 'finalização', 'finalizações')} "
                    f"(xG {_fmt(b['xg_cedido'])}). {team} fez {b['nossas_acoes_defensivas_no_setor']} ações defensivas ali"
                    + (f" e ganhou {_fmt(b['duelos_ganhos_no_setor_pct'])}% de {b['duelos_no_setor']} duelos." if b['duelos_no_setor'] else ".")
                    + cls._small_sample(b.get("amostra_N")))
                if c.get("dispersao_lateral_m") is not None:
                    out.append(
                        f"Compactação estimada (proxy sem tracking, pela dispersão das {c['acoes_defensivas_consideradas']} ações defensivas): "
                        f"altura média {_fmt(c['altura_media_m'])} m, dispersão lateral {_fmt(c['dispersao_lateral_m'])} m e "
                        f"longitudinal {_fmt(c['dispersao_longitudinal_m'])} m.")
                comp = b.get("comparacao_resto_do_jogo")
                if comp:
                    a, r = comp["acoes_adversarias_no_setor_por_10min_recorte"], comp["acoes_adversarias_no_setor_por_10min_resto"]
                    out.append(f"Contra o resto do jogo: {_fmt(a)} ações adversárias no setor a cada 10 min no recorte, "
                               f"contra {_fmt(r)} fora dele"
                               + (f"; dispersão lateral {_fmt(c.get('dispersao_lateral_m'))} m contra {_fmt(comp['dispersao_lateral_m_resto'])} m." if comp.get("dispersao_lateral_m_resto") is not None and c.get("dispersao_lateral_m") is not None else "."))
                    if a is not None and r is not None:
                        summary.append(f"{b['setor']} ficou {'mais' if a > r else 'menos'} exposto no recorte "
                                       f"({_fmt(a)} contra {_fmt(r)} ações adversárias por 10 min)")
                elif b["entradas_na_area_vindas_do_setor"] or b["finalizacoes_cedidas"]:
                    summary.append(f"{opp} gerou {b['entradas_na_area_vindas_do_setor']} entradas na área pelo {b['setor']}")
                else:
                    summary.append(f"{b['setor']} não cedeu entradas na área nem finalizações no recorte")
            elif key in ("ataque_no_recorte", "ataque_adversario"):
                who = team if key == "ataque_no_recorte" else opp
                prot = ", ".join(f"{p['jogador']} ({p['acoes']})" for p in b.get("protagonistas_no_setor", []))
                out.append(
                    f"**Com a bola — {who} ({b['setor']}):** {b['passes_no_setor']} passes ({_fmt(b['precisao_passes_no_setor_pct'])}% certos), "
                    f"{b['acoes_progressivas']} ações progressivas, {b['passes_que_quebram_linhas']} quebras de linha, "
                    f"{_pl(b['entradas_na_area'], 'entrada', 'entradas')} na área e {_pl(b['cruzamentos'], 'cruzamento', 'cruzamentos')}; "
                    f"{_pl(b['finalizacoes'], 'finalização', 'finalizações')} (xG {_fmt(b['xg'])}, {_pl(b['gols'], 'gol', 'gols')})." + (f" Mais acionados: {prot}." if prot else "")
                    + cls._small_sample(b.get("amostra_N")))
                if key == "ataque_no_recorte" or sc.team_focus == "both":
                    summary.append(f"{who} finalizou {_pl(b['finalizacoes'], 'vez', 'vezes')} (xG {_fmt(b['xg'])}) no recorte")
            elif key == "pressao":
                txt = (f"**Pressão:** PPDA {_fmt(b['ppda'])} ({b['passes_adversarios_na_construcao']} passes adversários na construção "
                       f"para {b['acoes_defensivas_altas']} ações defensivas altas) e {b['recuperacoes_no_campo_adversario']} "
                       f"recuperações no campo adversário.")
                summary.append(f"PPDA {_fmt(b['ppda'])} com {b['recuperacoes_no_campo_adversario']} recuperações no campo adversário")
                if not b["fonte_tem_eventos_de_pressao"]:
                    txt += " A fonte desta partida não registra eventos de pressão, então o PPDA usa só duelos, interceptações, bloqueios e faltas."
                out.append(txt + cls._small_sample(b.get("amostra_N")))
            elif key == "transicao":
                out.append(
                    f"**Transição defensiva:** {b['perdas_de_posse']} perdas ({b['perdas_no_terco_defensivo']} no terço defensivo); "
                    f"{opp} finalizou em até 15 s depois de {b['finalizacoes_adversarias_em_ate_15s_apos_perda']} delas e "
                    f"{team} recuperou em até 5 s em {b['recuperacoes_em_ate_5s_apos_perda']} "
                    f"({_fmt(b['taxa_recuperacao_5s_pct'])}%)." + cls._small_sample(b.get("amostra_N")))
                summary.append(f"a reação à perda recuperou a bola em até 5 s em {_fmt(b['taxa_recuperacao_5s_pct'])}% dos casos")
            elif key == "bola_parada":
                out.append("**Bola parada:** " + "; ".join(
                    f"{t}: {v['escanteios']} escanteios, {v['finalizacoes_de_bola_parada']} finalizações (xG {_fmt(v['xg_bola_parada'])})"
                    for t, v in b.items()) + ".")
            elif key == "posse":
                a_, o_ = b.get("share_passes_pct"), b.get("share_passes_pct_adversario")
                leader = team if (a_ or 0) >= (o_ or 0) else opp
                out.append(f"**Posse (proporção dos passes):** {team} {_fmt(a_)}% x {_fmt(o_)}% {opp}. "
                           f"**Field tilt** (passes no terço final): {team} {_fmt(b['field_tilt_pct'])}% x "
                           f"{_fmt(b.get('field_tilt_pct_adversario'))}% {opp}.")
                summary.append(f"{leader} teve mais a bola")
            elif key.startswith("jogador::"):
                feed = ", ".join(f"{k} ({v})" for k, v in (b.get("quem_mais_o_abastece") or {}).items())
                tgt = ", ".join(f"{k} ({v})" for k, v in (b.get("para_quem_mais_passa") or {}).items())
                out.append(
                    f"**{b['jogador']}** ({b['equipe']}): {b['acoes']} ações no recorte — {b['passes']} passes "
                    f"({_fmt(b['precisao_passe_pct'])}%), {b['passes_progressivos']} progressivos, {b['quebras_de_linha']} quebras de linha, "
                    f"xT {_fmt(b['xt_gerado'])}; {_pl(b['finalizacoes'], 'finalização', 'finalizações')} (xG {_fmt(b['xg'])}); "
                    + (f"{_pl(b['duelos'], 'desarme disputado', 'desarmes disputados')} ({_fmt(b['duelos_ganhos_pct'])}% ganhos); " if b['duelos'] else "")
                    + (f"{_pl(b.get('dribles_tentados', 0), 'drible tentado', 'dribles tentados')}; " if b.get('dribles_tentados') else "")
                    + f"{b['perdas_de_posse']} perdas e {b['recuperacoes']} recuperações."
                    + (f" Quem mais o abastece: {feed}." if feed else "") + (f" Para quem mais passa: {tgt}." if tgt else "")
                    + cls._small_sample(b.get("amostra_N")))
                if feed:
                    summary.append(f"a bola chega em {b['jogador']} principalmente por {list((b.get('quem_mais_o_abastece') or {}).keys())[0]}")
                else:
                    summary.append(f"{b['jogador']} participou de {b['acoes']} ações no recorte")
        if summary:
            joined = "; ".join(summary[:2])
            out.append("\n**Resumo executivo:** " + joined[:1].upper() + joined[1:] + ".")
        return "\n\n".join(out)

    @staticmethod
    def _model_line(card: Optional[Dict[str, Any]]) -> str:
        if not card:
            return ""
        return (f"\n\n🧠 _Rede neural de perigo {card['versao']} (arquitetura {card['arquitetura']}, treinada em "
                f"{card['partidas_de_treino']} partidas, AUC {_fmt(card['auc_validacao'])} na validação fixa) usada nesta resposta. "
                "Treinar uma versão melhor na página Rede Neural muda estes resultados._")

    @classmethod
    def _danger_ranking(cls, b: Dict[str, Any]) -> str:
        lid = b.get("lideres_ia") or []
        if not b.get("modelo"):
            return ("Ainda não há um modelo de perigo treinado. Abra a página **Rede Neural do Zero** e treine uma "
                    "versão: ela passa a ser usada aqui.")
        if not lid:
            return (f"Nenhuma ação passou de {b['limiar_pct']}% de chance de terminar em finalização no recorte "
                    f"({b['acoes_avaliadas']} ações avaliadas).") + cls._model_line(b["modelo"])
        rows = "\n".join(f"{i}. {r['jogador']} ({r['equipe']}): {r['acoes_perigosas']} ações perigosas de {r['acoes']} "
                          f"(maior chance {_fmt(r['maior_chance_pct'])}%)" for i, r in enumerate(lid, 1))
        return (f"**Quem mais criou perigo — {b['equipes_consideradas']}** (ações de passe/condução com ≥ {b['limiar_pct']}% "
                f"de chance, segundo a rede neural, de a posse terminar em finalização):\n{rows}") + cls._model_line(b["modelo"])

    @staticmethod
    def _plan_player(b: Dict[str, Any]) -> str:
        p = b["jogador"]
        if not b.get("jogou"):
            return f"**{p}** não aparece nos eventos desta partida (não jogou ou não entrou em campo)."
        r, steps = b["quem_defende"], []
        feed = list((b.get("quem_mais_o_abastece") or {}).items())
        if feed:
            fs = " e ".join(f"{k} ({v} passes para ele)" for k, v in feed[:2])
            steps.append(f"**Cortar a fonte:** a bola chegou em {p} principalmente por {fs}. {r} deve pressionar "
                         f"esses jogadores na hora do passe e fechar a linha de passe entre eles e {p}.")
        zr = b.get("zonas_onde_recebe") or []
        if zr:
            z = zr[0]
            steps.append(f"**Encurtar onde ele recebe:** {z['acoes']} dos {b['passes_recebidos']} passes que {p} recebeu "
                         f"foram em {z['zona']} ({_fmt(z['pct'])}%). Manter um marcador próximo nessa faixa e chegar antes do domínio.")
        za = b.get("zonas_onde_age") or []
        if za and (not zr or za[0]["zona"] != zr[0]["zona"]):
            steps.append(f"**Vigiar a área de atuação:** {za[0]['acoes']} das {b['amostra_N']} ações dele foram em {za[0]['zona']}.")
        if b.get("finalizacoes"):
            steps.append(f"**Bloquear o chute:** {_pl(b['finalizacoes'], 'finalização', 'finalizações')} (xG {_fmt(b['xg'])}). "
                         "Não deixar espaço frontal para ele girar e finalizar.")
        else:
            tg = ", ".join(f"{k} ({v})" for k, v in (b.get("para_quem_mais_passa") or {}).items())
            steps.append(f"**O perigo dele veio do passe, não do chute:** nenhuma finalização, mas xT {_fmt(b.get('xt_gerado'))} "
                         f"em passes" + (f", sobretudo para {tg}" if tg else "") + ". Marcar também quem recebe dele.")
        if (b.get("dribles") or 0) >= 3 or (b.get("faltas_sofridas") or 0) >= 3:
            steps.append(f"**Evitar o bote precipitado:** tentou {_pl(b['dribles'], 'drible', 'dribles')} e sofreu "
                         f"{_pl(b['faltas_sofridas'], 'falta', 'faltas')}. Defender de frente e com cobertura.")
        if (b.get("perdas_de_posse") or 0) >= 5:
            steps.append(f"**Pressionar depois do domínio:** ele perdeu a bola {b['perdas_de_posse']} vezes.")
        ia = b.get("ia") or {}
        if ia.get("acoes_perigosas"):
            zz = ia.get("zonas_das_acoes_perigosas") or []
            steps.append(f"**O que a rede neural aponta:** {ia['acoes_perigosas']} das {ia['acoes_avaliadas']} ações de {p} "
                         f"tinham ≥ {ia['limiar_pct']}% de chance de virar finalização"
                         + (f", a maioria a partir de {zz[0]['zona']} ({zz[0]['acoes']})" if zz else "")
                         + ". É nessa faixa que a marcação dele precisa ser mais agressiva.")
        head = f"**Como anular {p} ({b['equipe']}) — plano para {r}, a partir dos dados desta partida:**"
        return head + "\n" + "\n".join(f"{i}. {s_}" for i, s_ in enumerate(steps, 1)) + \
            ("\n\n⚠️ Amostra pequena: " + str(b["amostra_N"]) + " ações." if b["amostra_N"] < 15 else "") + \
            LocalScopedWriter._model_line((b.get("ia") or {}).get("modelo"))

    @staticmethod
    def _plan_team(b: Dict[str, Any]) -> str:
        t, o, steps = b["equipe"], b["adversario"], []
        z = b.get("corredores_das_entradas_na_area_do_adversario") or []
        def own_side(zona: str) -> str:
            lane = zona.split(" — ")[-1]
            mine = {"esquerda": "lado direito", "direita": "lado esquerdo", "centro": "corredor central"}[lane]
            return f"{zona.split(' — ')[0]}, pela {lane} do ataque de {o} = {mine} de {t}"
        if z:
            zs = "; ".join(f"{own_side(x['zona'])} ({x['acoes']})" for x in z[:2])
            steps.append(f"**Fechar o corredor mais usado:** {o} entrou na área {b['entradas_na_area_do_adversario']} vezes, "
                         f"principalmente por {zs}. Dobrar a marcação desse lado (lateral + ponta recompondo) e não deixar o volante sair da frente da área.")
        cr = b.get("criadores_do_adversario") or []
        if cr:
            steps.append("**Marcar quem cria:** " + ", ".join(f"{c['jogador']} (xT {_fmt(c['xt'])})" for c in cr[:3])
                         + f" foram os que mais geraram ameaça para {o}. Encaixe individual ou pressão imediata quando receberem.")
        if b.get("perdas_no_proprio_campo"):
            zl = b.get("zonas_das_perdas") or []
            steps.append(f"**Sair jogando com mais segurança:** {t} perdeu a bola {b['perdas_no_proprio_campo']} vezes no próprio campo"
                         + (f" (mais em {zl[0]['zona']}, {zl[0]['acoes']})" if zl else "")
                         + (f", e {o} finalizou em até 15 s depois de {b['finalizacoes_adversarias_ate_15s_apos_perda']} perdas"
                            if b.get("finalizacoes_adversarias_ate_15s_apos_perda") else "")
                         + ". Usar a bola longa nas saídas pressionadas e evitar passes curtos pelo meio.")
        if (b.get("cruzamentos_do_adversario") or 0) >= 10:
            steps.append(f"**Defender a área:** {o} cruzou {b['cruzamentos_do_adversario']} vezes. Zagueiros fixos na área, "
                         "marcação da segunda bola e pressão em quem cruza.")
        pos, pp = b.get("posse_pct") or {}, b.get("ppda") or {}
        if pos.get(t) is not None and pos[t] < 40:
            steps.append(f"**Aceitar o jogo reativo com organização:** com {_fmt(pos[t])}% da posse contra {_fmt(pos.get(o))}%, "
                         "um bloco médio-baixo compacto e a transição rápida pelos lados fazem mais sentido do que pressionar alto o tempo todo.")
        elif pp.get(t) is not None and pp.get(o) is not None and pp[t] > pp[o]:
            steps.append(f"**Pressionar mais a saída de {o}:** PPDA de {t} {_fmt(pp[t])} contra {_fmt(pp[o])} de {o} "
                         f"(quanto menor, mais intensa a pressão).")
        ia = b.get("ia") or {}
        zp = ia.get("zonas_perigosas_do_adversario") or []
        if zp:
            mp = ia.get("mais_perigosos_do_adversario") or []
            steps.insert(1, f"**Onde a rede neural vê perigo:** das {zp[0]['de']} ações de {o} com ≥ {ia['limiar_pct']}% de chance de "
                            f"virar finalização, {zp[0]['acoes_perigosas']} saíram de {own_side(zp[0]['zona'])}"
                            + (f"; quem mais as executou: " + ", ".join(f"{m['jogador']} ({m['acoes_perigosas']})" for m in mp[:2]) if mp else "")
                            + ". Priorizar a cobertura nessa faixa.")
        head = f"**Plano para {t} contra {o}, a partir dos dados desta partida:**"
        foot = ("\n\n_Recomendações geradas por regras sobre os números da partida (não são previsões). "
                "Com o Gemini ativo, o texto fica mais elaborado usando as mesmas evidências._")
        return head + "\n" + "\n".join(f"{i}. {s_}" for i, s_ in enumerate(steps, 1)) + foot + \
            LocalScopedWriter._model_line(ia.get("modelo"))

    @staticmethod
    def write_boxscore(ev: Dict[str, Any], sc: QueryScope) -> str:
        b, meta = ev["blocos"], ev["metadata"]
        out: List[str] = []
        if b.get("limitacao"):
            out.append(f"📊 {b['limitacao']} Abaixo, o que os dados reais desta partida permitem dizer.")
        stats = b.get("estatisticas_dos_times", {})
        wanted = {
            "shots": ["Finalizações", "Finalizações no gol", "xG (fonte)"],
            "possession": ["Posse de bola (%)"], "passing": ["Passes", "Passes certos", "Precisão de passe (%)"],
            "crosses": ["Cruzamentos", "Cruzamentos certos"], "set_pieces": ["Escanteios"],
            "discipline": ["Faltas cometidas", "Cartões amarelos", "Cartões vermelhos"],
            "duels": ["Desarmes certos", "Interceptações"],
        }
        labels: List[str] = []
        for m in sc.metrics:
            labels += wanted.get(m, [])
        if not labels:
            labels = ["Posse de bola (%)", "Finalizações", "Finalizações no gol", "xG (fonte)", "Precisão de passe (%)"]
        rows = [(lab, stats[lab]) for lab in dict.fromkeys(labels) if lab in stats]
        if rows:
            teams = list(rows[0][1].keys())
            out.append("| Estatística | " + " | ".join(teams) + " |\n|---|" + "---|" * len(teams))
            out[-1] += "\n" + "\n".join(f"| {lab} | " + " | ".join(_fmt(v.get(t)) for t in teams) + " |" for lab, v in rows)
        tl = b.get("linha_do_tempo_no_recorte") or []
        if tl:
            out.append("**Lances no recorte:** " + "; ".join(
                f"{e['minuto']}'{('+' + str(e['acrescimo'])) if e.get('acrescimo') else ''} {e['tipo']} — {e['jogador']} ({e['equipe']})"
                for e in tl[:12]) + ".")
        for p in b.get("atletas_citados") or []:
            out.append(f"**{p['jogador']}:** " + ", ".join(f"{k} {_fmt(v)}" for k, v in p.items() if k != "jogador") + ".")
        out.append(f"\n**Resumo executivo:** {meta.get('placar', '')}. Para análises espaciais, escolha uma partida com eventos oficiais.")
        return "\n\n".join(out)

    @staticmethod
    def off_topic(sc: QueryScope) -> str:
        if sc.category == "greeting":
            return ("Olá! Estou com a partida carregada e pronto. Pergunte, por exemplo: "
                    "*\"como foi a compactação defensiva do lado esquerdo no minuto 30?\"* ou "
                    "*\"quem mais abasteceu o camisa 10 no segundo tempo?\"*")
        if sc.category == "help":
            return ("Eu respondo sobre a partida carregada, no recorte que você pedir: minutos (\"entre 30 e 45\"), "
                    "tempo (\"segundo tempo\"), lado (\"pela esquerda\"), fase (\"sem a bola\", \"transição\") ou atleta. "
                    "Peça *\"relatório completo\"* para o dossiê inteiro.")
        return ("Essa foge do meu campo: não tenho dados nem xG sobre isso 😄. Aqui eu analiso futebol com os dados da partida "
                "carregada. Tente, por exemplo: *\"onde o adversário mais nos atacou no primeiro tempo?\"* ou "
                "*\"como foi a transição defensiva depois do minuto 60?\"*")


class DynamicTacticalAnalyst:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        raw = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.api_key = raw.strip() if raw and "coloque_sua_chave" not in raw.lower() and len(raw.strip()) > 15 else None
        self.model_name = model_name

    FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash")

    @staticmethod
    def explain_error(err: Exception) -> str:
        """Traduz o erro da API do Gemini em uma causa que o usuário consegue resolver."""
        msg = str(err)
        low = msg.lower()
        if "api_key_invalid" in low or "api key not valid" in low or "invalid api key" in low:
            return "chave do Gemini inválida: gere outra em aistudio.google.com e atualize GEMINI_API_KEY no .env"
        if "permission_denied" in low or " 403" in f" {low}":
            return "a chave não tem permissão para a API Gemini (ative a Generative Language API no projeto da chave)"
        if "resource_exhausted" in low or " 429" in f" {low}" or "quota" in low:
            return "cota gratuita do Gemini esgotada no momento: tente de novo mais tarde"
        if "liberados para a chave" in low:
            return msg[msg.find("Testados"):][:400]
        if "not_found" in low or " 404" in f" {low}":
            return "modelo do Gemini indisponível para esta chave (defina GEMINI_MODEL no .env)"
        if "location" in low and "not supported" in low:
            return "a API Gemini não está disponível na região desta conta"
        return f"{type(err).__name__}: {msg[:160]}"

    _discovered: Optional[List[str]] = None   # modelos liberados para a chave (descobertos uma vez por sessão)

    @staticmethod
    def _rank_model(name: str) -> tuple:
        """Prefere flash (rápido e com cota gratuita maior), versão mais nova, e evita variantes experimentais."""
        import re as _re

        n = name.lower()
        ver = _re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return (("flash" in n) and ("lite" not in n), float(ver.group(1)) if ver else 0.0,
                not any(k in n for k in ("exp", "preview", "thinking", "tts", "image", "live", "embedding")))

    def available_models(self, client) -> List[str]:
        if DynamicTacticalAnalyst._discovered is None:
            names: List[str] = []
            try:
                for m in client.models.list():
                    actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
                    name = str(getattr(m, "name", "")).replace("models/", "")
                    if "gemini" in name and (not actions or "generateContent" in actions):
                        names.append(name)
            except Exception:
                names = []
            DynamicTacticalAnalyst._discovered = sorted(set(names), key=self._rank_model, reverse=True)
        return DynamicTacticalAnalyst._discovered

    def _llm(self, system: str, prompt: str) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        first = os.getenv("GEMINI_MODEL", "").strip() or self.model_name
        tried: List[str] = []
        last: Optional[Exception] = None
        candidates = [first, *self.FALLBACK_MODELS]
        while candidates:
            model = candidates.pop(0)
            if model in tried:
                continue
            tried.append(model)
            try:
                resp = client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(system_instruction=system, temperature=0.3),
                )
            except Exception as exc:
                last = exc
                low = str(exc).lower()
                if "not_found" in low or "404" in low or "not supported" in low:
                    if len(tried) == 1 + len(self.FALLBACK_MODELS) or not candidates:
                        candidates += [m for m in self.available_models(client)[:6] if m not in tried]
                    continue
                raise
            text = resp.text if resp and resp.text else ""
            if not text.strip():
                raise RuntimeError("Resposta vazia da API generativa.")
            self.model_name = model
            return text
        found = self.available_models(client)
        raise RuntimeError(f"404 NOT_FOUND — nenhum modelo respondeu. Testados: {', '.join(tried)}. "
                           f"Liberados para a chave: {', '.join(found[:8]) or 'nenhum (a chave não lista modelos)'}. "
                           f"Último erro: {str(last)[:160] if last else '—'}")

    def answer(
        self,
        query: str,
        target_team: str,
        meta: Dict[str, Any],
        df_events: Optional[pd.DataFrame] = None,
        df_chains: Optional[pd.DataFrame] = None,
        boxscore: Optional[Dict[str, Any]] = None,
        prefer_llm: bool = True,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        roster: List[str] = []
        if df_events is not None and not df_events.empty:
            roster = df_events["player_name"].dropna().astype(str).unique().tolist()
        elif boxscore:
            for k in ("lineups", "player_stats"):
                t = boxscore.get(k)
                if t is not None and not t.empty:
                    roster += t["player_name"].dropna().astype(str).tolist()
        teams_in_match: List[str] = []
        if df_events is not None and not df_events.empty:
            teams_in_match = df_events["team_name"].dropna().unique().tolist()
        elif meta:
            teams_in_match = [meta.get("home_team_name", ""), meta.get("away_team_name", "")]
        ordered = [target_team] + [t for t in teams_in_match if t != target_team][:1]
        sc = QueryUnderstanding.parse(query, roster, ordered if len(ordered) == 2 else None)
        use_llm = prefer_llm and self.api_key is not None

        # 1) fora do escopo / saudação / ajuda
        if not sc.in_scope:
            text = LocalScopedWriter.off_topic(sc)
            engine = "LOCAL_SCOPE_GUARD"
            if use_llm and sc.category == "off_topic":
                try:
                    text = self._llm(OFF_TOPIC_SYSTEM, query)
                    engine = f"GEMINI_API ({self.model_name})"
                except Exception:
                    pass
            return {"engine_used": engine, "report_markdown": text, "scope": sc.to_dict(), "evidence": None,
                    "hallucination_audit": {"is_grounded": True, "verified_decimals_count": 0,
                                            "verified_integers_count": 0, "unverified_decimals": [],
                                            "unverified_integers": [], "unverified_player_names": []}}

        has_events = df_events is not None and not df_events.empty

        # 2) relatório completo (somente quando pedido)
        if sc.category == "full_report" and has_events:
            from src.intelligence.llm_analyst import GenerativeTacticalAnalyst

            pkg = TacticalReportBuilder.assemble_evidence_package(
                df_events, df_chains if df_chains is not None else pd.DataFrame(), target_team,
                match_id=int(meta.get("match_id", 0) or 0), user_query=query,
                is_simulation=meta.get("data_level") == "SIMULATED")
            res = GenerativeTacticalAnalyst(api_key=self.api_key or "").generate_tactical_report(pkg, prefer_llm=use_llm)
            res.update(scope=sc.to_dict(), evidence=pkg)
            return res

        # 3) evidências recortadas
        if has_events:
            evidence = ScopedEvidenceBuilder.build(df_events, sc, target_team, meta)
            local_md = LocalScopedWriter.write(evidence, sc)
        else:
            evidence = ScopedEvidenceBuilder.build_boxscore(boxscore or {}, sc, meta, target_team)
            local_md = LocalScopedWriter.write_boxscore(evidence, sc)

        local_audit = NumericHallucinationGuard.audit_text_numbers(local_md, evidence)
        result = {"engine_used": "LOCAL_SCOPED_ENGINE", "report_markdown": local_md,
                  "hallucination_audit": local_audit, "scope": sc.to_dict(), "evidence": evidence}
        if not use_llm:
            return result

        try:
            from src.guard.metrics import GuardMetricsLog
            from src.guard.policy import GuardPolicy

            ctx = ""
            if history:
                ctx = "Conversa anterior (para entender referências):\n" + "\n".join(
                    f"- Usuário: {h['q']}" for h in history[-3:]) + "\n\n"
            prompt = (f"{ctx}PERGUNTA: {query}\nRECORTE INTERPRETADO: {sc.describe()}\n\n"
                      f"EVIDÊNCIAS (JSON):\n{json.dumps(evidence, ensure_ascii=False, indent=1, default=str)}")

            def generate(extra: Optional[str]) -> str:
                return self._llm(DYNAMIC_SYSTEM, prompt if not extra else f"{extra}\n\n{prompt}")

            pol = GuardPolicy(NumericHallucinationGuard.audit_text_numbers, GuardMetricsLog()).run(
                generate, evidence, fallback_text=local_md, engine=f"GEMINI_API ({self.model_name})")
            engine = {"APROVADO_1A": f"GEMINI_API ({self.model_name})",
                      "APROVADO_REGENERADO": f"GEMINI_API ({self.model_name}) — regenerado com contexto restrito",
                      "DEGRADADO": "RESPOSTA DEGRADADA (redator local após 2 bloqueios)"}[pol.outcome]
            text = pol.text if pol.outcome == "DEGRADADO" else TacticalReportBuilder.prepend_simulation_badge(
                pol.text, bool(evidence["metadata"].get("is_simulation_data")))
            return {"engine_used": engine, "report_markdown": text, "hallucination_audit": pol.audit,
                    "guard_outcome": pol.outcome, "guard_metrics": pol.metrics.as_dict(),
                    "scope": sc.to_dict(), "evidence": evidence}
        except Exception as err:
            result["engine_used"] = "REDATOR LOCAL (Gemini indisponível)"
            result["llm_error"] = self.explain_error(err)
            return result
