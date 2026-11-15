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
import re
import os
from pathlib import Path
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
- Linguagem de analista de futebol brasileiro, não de estatístico: "pelo lado esquerdo da defesa", "na saída de bola",
  "entre as linhas", "chegou à área", "bola longa nas costas". Nada de "terço ofensivo — direita", "n =", "P90".
- Não cite percentil, a não ser que seja extremo; nesse caso diga "entre os 10% melhores/piores".
- Use os nomes das seleções em português (Brasil, Croácia, França…).
- Termine SEMPRE com uma linha "**Resumo:**" de 1 ou 2 frases simples para a comissão técnica.

Regras de fidelidade (obrigatórias):
- Copie números exatamente como estão no JSON. Não calcule diferenças, médias ou porcentagens novas.
- Não cite atletas que não estejam em metadata.match_player_roster.
- Se amostra_N for menor que 15, diga que a amostra é pequena.
- "compactacao_estimada" é proxy sem tracking: diga isso se usar.
- Se blocos.limitacao não estiver vazio, explique a limitação na primeira frase.
- Se metadata.is_simulation_data for true, a primeira linha deve ser: ⚠️ [DADOS SIMULADOS / MODELAGEM PROBABILÍSTICA].
- Se houver um bloco "ia" ou "lideres_ia" (rede neural de perigo), use-o e cite a versão do modelo e a AUC de validação.
- Em perguntas de estratégia ("como anular", "qual tática"), responda com passos numerados, cada um justificado por um número do JSON.
- Se existir blocos.indisponivel, diga com clareza que esse dado não existe na base e não estime nada.
- Se existir blocos.perfil, use só as médias e a cobertura (encontrados de atletas_na_partida) do JSON.
- Se existir blocos.gols.ordem_pedida (ou blocos.gol_pedido), responda primeiro exatamente o gol perguntado
  (time, minuto, autor) e só depois o placar. Não responda com estatísticas gerais."""

OFF_TOPIC_SYSTEM = """Você é o analista tático do Tactical Intelligence Lab. O usuário perguntou algo fora de futebol.
Responda em no máximo 2 frases, com bom humor e com precisão sobre o que foi perguntado (sem inventar fatos),
e em seguida convide a pessoa a perguntar sobre a partida carregada, com 2 exemplos curtos de perguntas.
Não cite números nem estatísticas."""


MISSES_PATH = "data/assistente_sem_alvo.jsonl"
FACT_ASKS = {"goals", "ranking", "profile", "unavailable", "presence", "errors"}


def log_generic_fallback(query: str, sc: Any, path: Optional[str] = None) -> None:
    """
    Aprender com as interações: toda pergunta que caiu no resumo genérico fica registrada (sem dados pessoais)
    para virar caso de teste. A tela Bastidores lista esse arquivo.
    """
    import datetime
    import os

    path = path or MISSES_PATH
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"quando": datetime.datetime.now().isoformat(timespec="seconds"), "pergunta": query,
                                 "ask": getattr(sc, "ask", None), "jogadores": getattr(sc, "players", []),
                                 "metricas": getattr(sc, "metrics", [])}, ensure_ascii=False) + "\n")
    except Exception:
        pass


LATENCY_PATH = "data/assistente_latencia.jsonl"
LATENCY_GOAL_S = 8.0


def log_latency(query: str, seconds: float, engine: str, ask: Optional[str], path: Optional[str] = None) -> None:
    import datetime
    import os

    path = path or LATENCY_PATH
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"quando": datetime.datetime.now().isoformat(timespec="seconds"), "segundos": seconds,
                                 "motor": engine, "tipo": ask, "pergunta": query[:200]}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_latency(path: Optional[str] = None, last: int = 200) -> List[Dict[str, Any]]:
    try:
        with open(path or LATENCY_PATH, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()][-last:]
    except Exception:
        return []


def read_generic_fallbacks(path: Optional[str] = None, last: int = 50) -> List[Dict[str, Any]]:
    try:
        with open(path or MISSES_PATH, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    except Exception:
        return []
    return rows[-last:][::-1]


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
            if key == "perfil":
                out.append(cls._profile(b))
                continue
            if key == "indisponivel":
                out.append(cls._unavailable(b))
                continue
            if key == "gols" and b.get("ordem_pedida"):
                from src.metrics.match_facts import goal_line

                out.append(cls._goal_order(b["ordem_pedida"], b["gols"], goal_line))
                pl = b["placar"]
                out.append("Placar final: " + " x ".join(f"{t} {n}" for t, n in pl.items()) + ".")
                continue
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
            if key == "presenca":
                out.append(cls._presence(b, sc))
                if b.get("jogou"):
                    summary.append(f"{b['jogador']} esteve em campo" + (f" (~{_fmt(b['minutos_estimados'])} min)" if b.get("minutos_estimados") else ""))
                continue
            if key.startswith("erros::"):
                out.append(cls._errors(b, sc))
                if not b.get("sem_dados"):
                    summary.append(f"{b['jogador']} somou {_pl(b['total_de_erros'], 'erro', 'erros')} registrados")
                continue
            if key in ("falhas", "fortes"):
                out.append(cls._issues(b, sc, key))
                items = b.get(key) or []
                if items:
                    summary.append(cls.ISSUE_SHORT[key].get(items[0]["tipo"], "").format(t=b["equipe"], o=b["adversario"]))
                continue
            if key == "ranking" and b.get("chave") == "perigo_ia":
                out.append(cls._danger_ranking(b))
                if b.get("lideres_ia"):
                    l0 = b["lideres_ia"][0]
                    summary.append(f"segundo a rede neural, {l0['jogador']} criou mais ações perigosas ({l0['acoes_perigosas']})")
                continue
            if key == "ranking":
                lid = b["lideres"]
                if b.get("sem_dado"):
                    out.append(f"**Não tenho esse dado nesta partida.** A fonte ({b['sem_dado']}) não registra "
                               f"{b['metrica'].lower()} — por isso não dá para fazer esse ranking, nem dizer que foi zero.")
                    continue
                if not lid:
                    out.append(f"Nenhum atleta registrou {b['metrica'].lower()} no recorte.")
                    continue
                head = f"**{b['metrica']} — {b['equipes_consideradas']}" + (f", {sc.describe()}" if sc.has_cut else "") + ":**"
                rows = "\n".join(f"{i}. {r['jogador']} ({r['equipe']}): {_fmt(r['valor'])}"
                                  + (f" · {r['secundaria'].lower()}: {_fmt(r['valor_secundario'])}" if r.get("secundaria") else "")
                                  for i, r in enumerate(lid, 1))
                out.append(head + "\n" + rows)
                ia = b.get("segunda_opiniao_ia") or {}
                if ia.get("modelo") and ia.get("lideres_ia"):
                    out.append(cls._danger_ranking(ia))
                lab = b["metrica"] if b["metrica"].startswith("x") else b["metrica"].lower()
                summary.append(f"{lid[0]['jogador']} liderou em {lab} ({_fmt(lid[0]['valor'])})")
                continue
            if key.startswith("plano_jogador::"):
                out.append(cls._plan_player(b))
                if b.get("jogou"):
                    f = list((b.get("quem_mais_o_abastece") or {}).keys())
                    summary.append(f"para anular {b['jogador']}, cortar a ligação com {f[0]}" if f else
                                   f"para anular {b['jogador']}, fechar o espaço {LocalScopedWriter._att(b['zonas_onde_age'][0]['zona'])}"
                                   if b.get("zonas_onde_age")
                                   else f"{b['jogador']} teve pouca participação")
                continue
            if key == "plano_equipe":
                out.append(cls._plan_team(b))
                z = b.get("corredores_das_entradas_na_area_do_adversario") or []
                mine = {"esquerda": "o lado direito da defesa", "direita": "o lado esquerdo da defesa", "centro": "o meio da zaga"}
                summary.append(f"{b['equipe']} precisava fechar {mine[z[0]['zona'].split(' — ')[-1]]} e errar menos na saída de bola"
                               if z else f"{b['equipe']} precisava errar menos na saída de bola")
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
                    f"{_pl(b['finalizacoes'], 'finalização', 'finalizações')} (xG {_fmt(b['xg'])}, {_pl(b['gols'], 'gol', 'gols')})." + (f" Mais passes: {prot}." if prot else "")
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
            out.append("\n**Resumo:** " + joined[:1].upper() + joined[1:] + ".")
        return "\n\n".join(out)

    # ------------------------------------------------------------------ perguntas fora dos eventos
    UNAVAILABLE_WHY = {
        "distancia": "distância percorrida, velocidade e sprints vêm de rastreamento físico (GPS/câmeras de tracking), "
                     "que nenhuma fonte aberta publica",
        "fisico": "dados físicos e médicos (peso, batimentos, lesões) não fazem parte das bases de jogo",
        "contexto": "público, clima, gramado e salários não constam nas fontes de lances e estatísticas",
    }

    @classmethod
    def _unavailable(cls, b: Dict[str, Any]) -> str:
        ped = str(b.get("pedido") or "")
        kind = ("distancia" if re.search(r"distanc|km|quilometr|corr|velocid|sprint|acelera", ped) else
                "fisico" if re.search(r"peso|pesa|batiment|cardiac|lesa|lesion|machuc", ped) else "contexto")
        return (f"**Essa informação não existe na base desta partida.** O pedido (\"{ped}\") não é registrado: "
                f"{cls.UNAVAILABLE_WHY[kind]}. Não vou estimar um número sem dado.\n\n"
                "O que dá para responder com dados reais deste jogo: posse e circulação, finalizações e xG, gols e "
                "assistências, duelos, pressão, transições, bola parada e o desempenho de cada atleta.")

    @staticmethod
    def _profile(b: Dict[str, Any]) -> str:
        attr = b.get("atributo", "altura")
        unit = {"altura": " cm", "idade": " anos", "valor": ""}[attr]
        name = {"altura": "altura", "idade": "idade", "valor": "valor de mercado"}[attr]

        def val(v):
            if v is None:
                return "—"
            return f"€ {v / 1e6:.1f} mi" if attr == "valor" else f"{_fmt(v)}{unit}"

        if not b.get("disponivel"):
            return (f"**A {name} dos atletas não está nos dados desta partida.** Lances e estatísticas não trazem perfil "
                    "físico. Esse dado vem do cadastro do Transfermarkt, que ainda não está no data lake desta "
                    "instalação (rode `python -m src.data_hub.sync --only transfermarkt`).")
        eq = b.get("equipes") or {}
        rows = [(t, v) for t, v in eq.items() if v.get("encontrados")]
        if not rows:
            return (f"**Não encontrei a {name} dos atletas desta partida no cadastro do Transfermarkt** — os nomes dos "
                    "jogadores nos eventos não bateram com nenhum cadastro. Prefiro não responder a chutar.")
        lines = [f"**{name.capitalize()} média de quem entrou em campo** (cadastro do Transfermarkt, não medido no jogo):"]
        for t, v in eq.items():
            cov = f"{v['encontrados']} de {v['atletas_na_partida']} atletas encontrados"
            lines.append(f"- **{t}:** {val(v['media'])} ({cov})")
        out = "\n".join(lines)
        ok = [(t, v) for t, v in rows if v["encontrados"] >= max(3, 0.5 * v["atletas_na_partida"])]
        if len(ok) == 2:
            (t1, v1), (t2, v2) = ok
            if v1["media"] == v2["media"]:
                out += f"\n\nAs duas equipes ficaram com a mesma média."
            else:
                hi = t1 if v1["media"] > v2["media"] else t2
                word = {"altura": "mais alto", "idade": "mais experiente (mais velho)", "valor": "mais valioso"}[attr]
                out += f"\n\n**Resumo:** {hi} teve o time {word} em campo."
        else:
            out += ("\n\nPoucos atletas foram encontrados no cadastro para comparar as equipes com segurança — "
                    "a média acima vale só para os atletas listados.")
        return out

    @staticmethod
    def _goal_order(order: str, goals: List[Dict[str, Any]], line) -> str:
        """"Qual time fez o primeiro gol?" → o gol pedido, com minuto, autor e time."""
        if not goals:
            return "**Não houve gols** no tempo de jogo."
        idx = {"1": 0, "2": 1, "3": 2, "last": len(goals) - 1}.get(order)
        label = {"1": "Primeiro gol", "2": "Segundo gol", "3": "Terceiro gol", "last": "Último gol",
                 "winner": "Gol da vitória"}.get(order, "Gol")
        if order == "winner":
            teams = list(dict.fromkeys(g["equipe"] for g in goals))
            cnt = {t: sum(g["equipe"] == t for g in goals) for t in teams}
            if len(cnt) == 1:
                win, need = teams[0], 1
            elif len(set(cnt.values())) == 1:
                return "**O jogo terminou empatado no tempo de jogo** — não houve gol da vitória."
            else:
                win = max(cnt, key=cnt.get)
                lose = min(cnt, key=cnt.get)
                need = cnt[lose] + 1                                  # o gol que colocou o placar fora de alcance
            k = [g for g in goals if g["equipe"] == win][need - 1]
            return f"**{label}:** {k['equipe']} — {line(k)}."
        if idx is None or idx >= len(goals):
            return f"A partida teve só {_pl(len(goals), 'gol', 'gols')}: " + "; ".join(
                f"{line(g)} — {g['equipe']}" for g in goals) + "."
        g = goals[idx]
        before = goals[:idx + 1]
        tally = {}
        for x in before:
            tally[x["equipe"]] = tally.get(x["equipe"], 0) + 1
        placar = " x ".join(f"{t} {n}" for t, n in tally.items())
        return (f"**{label}:** {g['equipe']}, {line(g)}." + (f" Com ele, o placar foi para {placar}." if idx else
                f" {g['equipe']} abriu o placar."))

    @staticmethod
    def _model_line(card: Optional[Dict[str, Any]]) -> str:
        if not card:
            return ""
        auc = float(card.get("auc_validacao") or 0)
        q = "boa" if auc >= 0.75 else ("razoável" if auc >= 0.65 else "modesta")
        return (f"\n\n_🧠 O \"perigo\" vem da rede neural {card['versao']}, treinada em {card['partidas_de_treino']} partidas "
                f"(precisão {q}): leia como indicação, não como certeza._")

    # ---------------------------------------------------------- linguagem de futebol
    THIRD_ATT = {"terço ofensivo": "já perto da área", "terço médio": "na intermediária",
                 "terço defensivo": "ainda saindo do campo de defesa"}
    THIRD_OWN = {"terço defensivo": "na saída de bola, perto da própria área", "terço médio": "no meio-campo",
                 "terço ofensivo": "já no ataque"}
    LANE_OWN = {"esquerda": "lado esquerdo", "direita": "lado direito", "centro": "meio"}

    @classmethod
    def _against(cls, zona: str, defender: str) -> str:
        """Zona do ataque adversário dita do ponto de vista de quem defende: 'pelo lado esquerdo da defesa do Brasil'."""
        third, _, lane = zona.partition(" — ")
        mirror = {"esquerda": "lado direito", "direita": "lado esquerdo", "centro": "meio"}.get(lane, lane)
        return f"pelo {mirror} da defesa de {defender}, {cls.THIRD_ATT.get(third, third)}"

    @classmethod
    def _own(cls, zona: str) -> str:
        """Zona da própria equipe: 'pelo lado direito, na saída de bola perto da própria área'."""
        third, _, lane = zona.partition(" — ")
        return f"pelo {cls.LANE_OWN.get(lane, lane)}, {cls.THIRD_OWN.get(third, third)}"

    @classmethod
    def _att(cls, zona: str) -> str:
        """Zona onde um atacante age: 'pela esquerda, já perto da área'."""
        third, _, lane = zona.partition(" — ")
        side = {"esquerda": "pela esquerda", "direita": "pela direita", "centro": "por dentro"}.get(lane, lane)
        return f"{side}, {cls.THIRD_ATT.get(third, third)}"

    # ---------------------------------------------------------- alvos específicos (v36)
    @staticmethod
    def _pick(sc: QueryScope, *options: str) -> str:
        """Varia a frase conforme a pergunta (determinístico: a mesma pergunta dá a mesma frase)."""
        import zlib

        return options[zlib.crc32(sc.raw.encode("utf-8")) % len(options)]

    @classmethod
    def _presence(cls, b: Dict[str, Any], sc: QueryScope) -> str:
        asked = b.get("pedido") or "esse jogador"
        if not b.get("jogou"):
            if b.get("jogador"):
                return f"**Não.** {b['jogador']} não tem nenhum lance registrado nesta partida."
            return (f"**Não encontrei \u201c{asked}\u201d entre os jogadores desta partida.** Ninguém com esse nome tem lance, "
                    "entrada ou saída registrados — ou não jogou, ou ficou no banco sem entrar. "
                    "Os dados de lances não trazem a lista de reservas não utilizados nem o motivo da ausência (lesão, suspensão).")
        p, tm = b["jogador"], b.get("equipe") or ""
        if b.get("entrou_aos"):
            how = f"entrou no decorrer do jogo, aos {b['entrou_aos']}'"
        elif b.get("saiu_aos"):
            how = f"começou jogando e saiu aos {b['saiu_aos']}'"
        else:
            how = "começou jogando e ficou até o fim"
        mins = f" — cerca de {_fmt(b['minutos_estimados'])} minutos" if b.get("minutos_estimados") else ""
        return (f"**Sim.** {p}{f' ({tm})' if tm else ''} {how}{mins}, com {b['eventos_registrados']} ações registradas. "
                + cls._pick(sc, "Quer o que ele fez com a bola? Pergunte, por exemplo, \u201cquantos erros ele teve?\u201d.",
                            "Dá para pedir os números dele: passes, finalizações, perigo criado ou erros.", ""))

    @classmethod
    def _errors(cls, b: Dict[str, Any], sc: QueryScope) -> str:
        p = b["jogador"]
        if b.get("sem_dados"):
            return f"{p} não tem ações registradas no recorte, então não há erros para contar."
        lines = [f"- Passes errados: {b['passes_errados']} de {b['passes_tentados']} tentados"
                 + (f" ({_fmt(b['precisao_passe_pct'])}% de acerto)" if b.get("precisao_passe_pct") is not None else "")
                 + (f"; {b['passes_errados_no_proprio_campo']} deles no próprio campo" if b.get("passes_errados_no_proprio_campo") else ""),
                 f"- Outras perdas de bola (domínio, desarmado, drible sem sucesso): {b['outras_perdas_de_bola']}",
                 f"- Duelos perdidos: {b['duelos_perdidos']}",
                 f"- Erros que deram finalização ao rival: {b['erros_que_deram_finalizacao_ao_rival']}"]
        if b.get("faltas_cometidas"):
            lines.append(f"- Faltas cometidas (não somadas acima): {b['faltas_cometidas']}"
                         + (f", {b['cartoes_amarelos']} amarelo" if b.get("cartoes_amarelos") else ""))
        tot = b["total_de_erros"]
        head = cls._pick(sc, f"**{p} teve {_pl(tot, 'erro registrado', 'erros registrados')}** no jogo:",
                         f"**Foram {tot} erros de {p}** ({b.get('equipe', '')}), assim:",
                         f"**{p}: {tot} erros no total**, separados por tipo:")
        tail = ""
        if tot == b["passes_errados"] and b["passes_errados"] > 0:
            tail = " Todos foram passes errados — nenhuma perda em drible ou domínio."
        elif b["erros_que_deram_finalizacao_ao_rival"]:
            tail = " O ponto mais grave: um erro dele terminou em finalização do adversário."
        return head + "\n" + "\n".join(lines) + tail

    ISSUE_TEXT = {
        "cedeu_mais_chances": "{t} cedeu mais do que criou: o rival somou xG {xg_cedido} em {finalizacoes_cedidas} finalizações, "
                              "contra xG {xg_criado} em {finalizacoes_feitas} de {t}.",
        "saida_de_bola_e_transicao": "A saída de bola foi o problema: {perdas_no_proprio_campo} bolas perdidas no próprio campo "
                                     "(o rival perdeu {perdas_no_proprio_campo_rival}) e {finalizacoes_rivais_ate_15s} "
                                     "finalizações sofridas em até 15 s depois de perder a bola.",
        "corredor_vulneravel": "Um lado ficou exposto: {pct}% das entradas do rival na área ({entradas} de {entradas_totais}) "
                               "vieram {zona_txt}.",
        "pouca_presenca_no_campo_rival": "{t} quase não morou no campo de ataque: {field_tilt}% dos passes no terço final "
                                         "(rival {field_tilt_rival}%) e {entradas_na_area} entradas na área contra {entradas_na_area_rival}.",
        "pressao_frouxa": "A marcação pressionou pouco: o rival trocou {ppda} passes por ação defensiva de {t} no campo de ataque "
                          "(PPDA estimado), contra {ppda_rival} do outro lado.",
        "finalizacao_ruim": "Faltou pontaria: {finalizacoes} finalizações, {no_alvo} no alvo, {gols} gols para xG {xg}.",
        "passe_impreciso": "O passe saiu pior que o do rival: {precisao}% de acerto contra {precisao_rival}%.",
        "bola_parada_defensiva": "A bola parada defensiva preocupou: o rival gerou xG {xg_rival_em_bola_parada} só em lances de bola parada.",
    }
    STRENGTH_TEXT = {
        "cedeu_mais_chances": "{t} criou mais do que cedeu: xG {xg_cedido} em {finalizacoes_cedidas} finalizações, "
                              "contra xG {xg_criado} em {finalizacoes_feitas} de {o}.",
        "saida_de_bola_e_transicao": "{t} sufocou a saída de bola de {o}: {perdas_no_proprio_campo} bolas roubadas no campo de "
                                     "{o} e {finalizacoes_rivais_ate_15s} finalizações em até 15 s depois de recuperar.",
        "corredor_vulneravel": "{t} achou um caminho: {pct}% das entradas na área ({entradas} de {entradas_totais}) vieram {zona_txt}.",
        "pouca_presenca_no_campo_rival": "{t} empurrou {o} para trás: {field_tilt_rival}% dos passes no terço final, contra "
                                         "{field_tilt}%; {entradas_na_area_rival} entradas na área contra {entradas_na_area}.",
        "pressao_frouxa": "{t} pressionou melhor: PPDA estimado {ppda_rival}, contra {ppda} de {o}.",
        "finalizacao_ruim": "{t} protegeu bem a área: {o} finalizou {finalizacoes} vezes, {no_alvo} no alvo, {gols} gols para xG {xg}.",
        "passe_impreciso": "{t} trocou passes melhor: {precisao_rival}% de acerto contra {precisao}%.",
        "bola_parada_defensiva": "{t} levou perigo na bola parada: xG {xg_rival_em_bola_parada} só nesses lances.",
    }
    ISSUE_SHORT = {
        "falhas": {"cedeu_mais_chances": "a maior falha de {t} foi ceder mais chances do que criou",
                   "saida_de_bola_e_transicao": "a maior falha de {t} foi perder a bola na saída e não reagir",
                   "corredor_vulneravel": "a maior falha de {t} foi deixar um corredor exposto",
                   "pouca_presenca_no_campo_rival": "a maior falha de {t} foi não conseguir jogar no campo de ataque",
                   "pressao_frouxa": "a maior falha de {t} foi a pressão sem intensidade",
                   "finalizacao_ruim": "a maior falha de {t} foi a finalização",
                   "passe_impreciso": "a maior falha de {t} foi o passe impreciso",
                   "bola_parada_defensiva": "a maior falha de {t} foi a bola parada defensiva"},
        "fortes": {"cedeu_mais_chances": "o ponto forte de {t} foi criar mais do que cedeu",
                   "saida_de_bola_e_transicao": "o ponto forte de {t} foi roubar a bola na saída do rival e finalizar rápido",
                   "corredor_vulneravel": "o ponto forte de {t} foi insistir num corredor do rival",
                   "pouca_presenca_no_campo_rival": "o ponto forte de {t} foi empurrar {o} para trás",
                   "pressao_frouxa": "o ponto forte de {t} foi a pressão alta",
                   "finalizacao_ruim": "o ponto forte de {t} foi defender bem a própria área",
                   "passe_impreciso": "o ponto forte de {t} foi trocar passes melhor",
                   "bola_parada_defensiva": "o ponto forte de {t} foi a bola parada ofensiva"},
    }

    @classmethod
    def _issues(cls, b: Dict[str, Any], sc: QueryScope, key: str) -> str:
        team, opp = b["equipe"], b["adversario"]
        items = b.get(key) or []
        if not items:
            return (f"Nos números deste jogo, {team} não ficou atrás de {opp} em nenhum dos critérios que eu meço "
                    "(chances, saída de bola, corredores, presença no ataque, pressão, finalização, passe e bola parada)."
                    if key == "falhas" else
                    f"Nos números deste jogo, {team} não superou {opp} com folga em nenhum critério que eu meço.")
        # pontos fortes = falhas que a equipe provocou no rival, contadas do ponto de vista de quem impôs
        texts = cls.STRENGTH_TEXT if key == "fortes" else cls.ISSUE_TEXT
        sufferer = opp if key == "fortes" else team

        def line(it):
            kw = {k: _fmt(v) if not isinstance(v, (list, dict)) else v for k, v in it.items()}
            kw.update(t=team, o=opp)
            if it["tipo"] == "corredor_vulneravel" and it.get("zona"):
                kw["zona_txt"] = cls._against(it["zona"], sufferer)
            try:
                return texts[it["tipo"]].format(**kw)
            except Exception:
                return it["tipo"].replace("_", " ")
        main, rest = items[0], items[1:3]
        if key == "falhas":
            head = cls._pick(sc, f"**A maior falha tática de {team}:** ", f"**Onde {team} mais errou:** ",
                             f"**O principal problema de {team} no jogo:** ")
            tail = "Também pesaram:" if rest else ""
        else:
            head = cls._pick(sc, f"**O que {team} fez de melhor:** ", f"**A principal arma de {team}:** ")
            tail = "Outros pontos a favor:" if rest else ""
        txt = head + line(main)
        if rest:
            txt += f"\n\n{tail}\n" + "\n".join(f"- {line(x)}" for x in rest)
        return txt + "\n\n_Critério: cada item compara as duas equipes no mesmo jogo; vem primeiro o de maior diferença._"

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
                         f"foram {LocalScopedWriter._att(z['zona'])} ({_fmt(z['pct'])}%). Marcador colado nessa faixa, chegando antes do domínio.")
        za = b.get("zonas_onde_age") or []
        if za and (not zr or za[0]["zona"] != zr[0]["zona"]):
            steps.append(f"**Vigiar onde ele joga:** {za[0]['acoes']} das {b['amostra_N']} ações dele foram "
                         f"{LocalScopedWriter._att(za[0]['zona'])}.")
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
                         + (f", a maioria {LocalScopedWriter._att(zz[0]['zona'])} ({zz[0]['acoes']})" if zz else "")
                         + ". É ali que a marcação nele tem de ser mais agressiva.")
        head = f"**Como anular {p} ({b['equipe']}) — o que {r} precisa fazer, pelos números desta partida:**"
        return head + "\n" + "\n".join(f"{i}. {s_}" for i, s_ in enumerate(steps, 1)) + \
            ("\n\n⚠️ Amostra pequena: " + str(b["amostra_N"]) + " ações." if b["amostra_N"] < 15 else "") + \
            LocalScopedWriter._model_line((b.get("ia") or {}).get("modelo"))

    @staticmethod
    def _plan_team(b: Dict[str, Any]) -> str:
        W = LocalScopedWriter
        t, o, steps = b["equipe"], b["adversario"], []
        z = b.get("corredores_das_entradas_na_area_do_adversario") or []
        if z:
            zs = " e ".join(f"{W._against(x['zona'], t)} ({x['acoes']})" for x in z[:2])
            steps.append(f"**Fechar o lado que eles mais atacaram:** {o} chegou {b['entradas_na_area_do_adversario']} vezes "
                         f"à área, principalmente {zs}. Dobrar a marcação ali (lateral com o ponta recompondo) e segurar "
                         "o volante na frente da zaga.")
        cr = b.get("criadores_do_adversario") or []
        if cr:
            steps.append("**Marcar quem pensa o jogo deles:** " + ", ".join(f"{c['jogador']} (xT {_fmt(c['xt'])})" for c in cr[:3])
                         + f" foram os que mais empurraram {o} para o ataque. Encaixe individual ou bote no primeiro toque.")
        if b.get("perdas_no_proprio_campo"):
            zl = b.get("zonas_das_perdas") or []
            n15 = b.get("finalizacoes_adversarias_ate_15s_apos_perda") or 0
            steps.append(f"**Sair jogando com mais segurança:** {t} perdeu a bola {b['perdas_no_proprio_campo']} vezes no "
                         "próprio campo"
                         + (f", a maior parte {W._own(zl[0]['zona'])} ({zl[0]['acoes']})" if zl else "")
                         + (f". Em {n15} {'dessas perdas' if n15 != 1 else 'delas'}, {o} finalizou em até 15 segundos"
                            if n15 else "")
                         + ". Sob pressão, bola longa nas costas da defesa e nada de passe curto pelo meio.")
        if (b.get("cruzamentos_do_adversario") or 0) >= 10:
            steps.append(f"**Proteger a área nas bolas cruzadas:** {o} cruzou {b['cruzamentos_do_adversario']} vezes. "
                         "Zagueiros fixos, atenção à segunda bola e pressão em quem cruza.")
        pos, pp = b.get("posse_pct") or {}, b.get("ppda") or {}
        if pos.get(t) is not None and pos[t] < 40:
            steps.append(f"**Jogar no contra-ataque com organização:** com {_fmt(pos[t])}% da posse contra {_fmt(pos.get(o))}%, "
                         "bloco médio-baixo compacto e saída rápida pelos lados rendem mais do que pressionar alto o jogo todo.")
        elif pp.get(t) is not None and pp.get(o) is not None and pp[t] > pp[o]:
            steps.append(f"**Subir a pressão na saída de {o}:** {t} deixou o adversário trocar passes demais antes de "
                         f"roubar (PPDA {_fmt(pp[t])} contra {_fmt(pp[o])} de {o}; quanto menor, mais intensa a pressão).")
        ia = b.get("ia") or {}
        zp = ia.get("zonas_perigosas_do_adversario") or []
        if zp:
            mp = ia.get("mais_perigosos_do_adversario") or []
            steps.insert(1, f"**De onde saiu o perigo de verdade:** das {zp[0]['de']} jogadas de {o} com chance alta "
                            f"(≥ {ia['limiar_pct']}%) de acabar em finalização, {zp[0]['acoes_perigosas']} nasceram "
                            f"{W._against(zp[0]['zona'], t)}"
                            + (". Quem mais puxou essas jogadas: " + ", ".join(f"{m['jogador']} ({m['acoes_perigosas']})"
                                                                               for m in mp[:2]) if mp else "")
                            + ". É a faixa que pede cobertura extra.")
        head = f"**Plano de jogo de {t} contra {o}, com base nos números desta partida:**"
        foot = "\n\n_Leitura feita a partir dos números do jogo — não é previsão._"
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
        lt = b.get("leitura") or {}
        if lt.get("fortes") or lt.get("fracos"):
            if lt.get("fortes"):
                out.append(f"**✅ Pontos fortes de {lt['equipe']}:** " + "; ".join(lt["fortes"]) + ".")
            if lt.get("fracos"):
                out.append(f"**⚠️ Pontos fracos de {lt['equipe']}:** " + "; ".join(lt["fracos"]) + ".")
        tl = b.get("linha_do_tempo_no_recorte") or []
        if tl:
            out.append("**Lances no recorte:** " + "; ".join(
                f"{e['minuto']}'{('+' + str(e['acrescimo'])) if e.get('acrescimo') else ''} {e['tipo']} — {e['jogador']} ({e['equipe']})"
                for e in tl[:12]) + ".")
        for p in b.get("atletas_citados") or []:
            out.append(f"**{p['jogador']}:** " + ", ".join(f"{k} {_fmt(v)}" for k, v in p.items() if k != "jogador") + ".")
        if b.get("perfil"):
            out.insert(0, LocalScopedWriter._profile(b["perfil"]))
            return "\n\n".join(out[:1])
        if b.get("indisponivel"):
            return LocalScopedWriter._unavailable(b["indisponivel"])
        if b.get("gol_pedido"):
            gp = b["gol_pedido"]
            gl = [{"minuto": e["minuto"], "jogador": e["jogador"] or "autor não informado", "equipe": e["equipe"],
                   "tipo": "pênalti" if "pen" in str(e.get("detalhe", "")).lower() else
                   ("gol contra" if "own" in str(e.get("detalhe", "")).lower() else ""), "assistencia": None}
                  for e in gp["gols"]]
            if not gl and meta.get("placar") and not re.search(r"\b0 x 0\b", meta["placar"]):
                return (f"Placar: {meta['placar']}. **A fonte desta partida não registra a ordem dos gols** (sem linha "
                        "do tempo), então não dá para dizer quem marcou primeiro.")
            from src.metrics.match_facts import goal_line

            return LocalScopedWriter._goal_order(gp["ordem"], gl, goal_line) + f"\n\nPlacar final: {meta.get('placar', '')}."
        out.append(f"\n**Resumo:** {meta.get('placar', '')}. Para análises espaciais, escolha uma partida com eventos oficiais.")
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
    _down_until: float = 0.0          # disjuntor: depois de uma falha de rede/tempo, pula a nuvem por alguns minutos
    _reach: Dict[str, float] = {}     # última checagem rápida de conexão com a API

    @classmethod
    def cloud_ready(cls) -> bool:
        """
        Decide em menos de 1 s se vale chamar a nuvem: disjuntor aberto (falha recente) → não; senão, uma conexão
        TCP rápida (0,8 s) com a API, guardada por 60 s. Sem rede, o redator local responde na hora.
        """
        import socket
        import time as _time

        now = _time.time()
        if now < cls._down_until:
            return False
        if now - cls._reach.get("t", 0) < 60:
            return bool(cls._reach.get("ok"))
        ok = True
        try:
            with socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=0.8):
                pass
        except OSError:
            ok = False
        cls._reach = {"t": now, "ok": float(ok)}
        if not ok:
            cls.trip()
        return ok

    @classmethod
    def trip(cls, seconds: Optional[float] = None) -> None:
        import time as _time

        cls._down_until = _time.time() + (seconds if seconds is not None else float(os.getenv("GEMINI_PAUSA_S", "300")))
    _working_model: Optional[str] = None
    _dead_models: set = set()

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
        """Ordem de preferência: modelo de TEXTO estável > flash (rápido, cota maior) > versão mais nova > sem 'lite'."""
        import re as _re

        n = name.lower()
        ver = _re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        text_only = not any(k in n for k in ("image", "tts", "live", "embedding", "audio", "vision", "omni", "robotics"))
        stable = not any(k in n for k in ("exp", "preview", "thinking", "latest"))
        return (text_only, "flash" in n, stable, float(ver.group(1)) if ver else 0.0, "lite" not in n)

    MODELS_CACHE = Path("data/gemini_modelos.json")

    def available_models(self, client=None) -> List[str]:
        """Modelos liberados para ESTA chave (1 chamada; lista guardada em disco por 24 h)."""
        import hashlib
        import json as _json
        import time as _time

        if DynamicTacticalAnalyst._discovered is not None:
            return DynamicTacticalAnalyst._discovered
        kid = hashlib.sha256((self.api_key or "").encode()).hexdigest()[:12]      # identifica a chave sem guardá-la
        try:
            c = _json.loads(self.MODELS_CACHE.read_text(encoding="utf-8"))
            if c.get("chave") == kid and _time.time() - float(c.get("quando", 0)) < 86_400 and c.get("modelos"):
                DynamicTacticalAnalyst._discovered = list(c["modelos"])
                return DynamicTacticalAnalyst._discovered
        except Exception:
            pass
        names: List[str] = []
        try:
            if client is None:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=8000))
            for m in client.models.list():
                actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
                name = str(getattr(m, "name", "")).replace("models/", "")
                if "gemini" in name and (not actions or "generateContent" in actions):
                    names.append(name)
        except Exception:
            names = []
        ranked = sorted(set(names), key=self._rank_model, reverse=True)
        DynamicTacticalAnalyst._discovered = ranked
        if ranked:
            try:
                self.MODELS_CACHE.parent.mkdir(parents=True, exist_ok=True)
                self.MODELS_CACHE.write_text(_json.dumps({"chave": kid, "quando": _time.time(), "modelos": ranked}),
                                             encoding="utf-8")
            except Exception:
                pass
        return ranked

    def _llm(self, system: str, prompt: str) -> str:
        from google import genai
        from google.genai import types

        import time as _time

        budget = float(os.getenv("GEMINI_TIMEOUT_S", "20"))   # teto rígido para TODA a resposta (todas as tentativas)

        def client_for(remaining: float):
            try:                                         # cada tentativa só recebe o tempo que ainda resta
                return genai.Client(api_key=self.api_key,
                                    http_options=types.HttpOptions(timeout=int(max(remaining, 1.0) * 1000)))
            except Exception:
                return genai.Client(api_key=self.api_key)
        t0 = _time.time()
        # ordem: o que já funcionou → GEMINI_MODEL do .env → modelos liberados para a chave (mais novo primeiro)
        #        → lista fixa só como último recurso. Assim nunca se perde tempo com modelo aposentado.
        pref = [DynamicTacticalAnalyst._working_model, os.getenv("GEMINI_MODEL", "").strip() or None]
        found = self.available_models(client_for(4))
        good = [m for m in found if self._rank_model(m)[0]][:6]
        candidates = [m for m in dict.fromkeys([*pref, *good, *self.FALLBACK_MODELS]) if m]
        tried: List[str] = []
        last: Optional[Exception] = None
        client = None
        while candidates:
            remaining = budget - (_time.time() - t0)
            if remaining <= 1:
                raise TimeoutError(f"A API generativa passou de {budget:.0f} s — resposta redigida localmente.")
            model = candidates.pop(0)
            if model in tried or model in DynamicTacticalAnalyst._dead_models:
                continue
            tried.append(model)
            client = client_for(remaining)
            try:
                resp = client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(system_instruction=system, temperature=0.3),
                )
            except Exception as exc:
                last = exc
                low = str(exc).lower()
                if "not_found" in low or "404" in low or "not supported" in low or "no longer available" in low:
                    DynamicTacticalAnalyst._dead_models.add(model)
                    if model == DynamicTacticalAnalyst._working_model:
                        DynamicTacticalAnalyst._working_model = None
                    continue
                raise
            text = resp.text if resp and resp.text else ""
            if not text.strip():
                raise RuntimeError("Resposta vazia da API generativa.")
            self.model_name = model
            DynamicTacticalAnalyst._working_model = model  # próximas perguntas vão direto no modelo que funcionou
            return text
        raise RuntimeError(f"404 NOT_FOUND — nenhum modelo respondeu. Testados: {', '.join(tried)}. "
                           f"Liberados para a chave: {', '.join(found[:8]) or 'nenhum (a chave não lista modelos)'}. "
                           f"Último erro: {str(last)[:160] if last else '—'}")

    def answer(self, query: str, *args, **kwargs) -> Dict[str, Any]:
        """E1: mede o tempo de cada resposta e registra em data/assistente_latencia.jsonl (meta: < 8 s com cache)."""
        import time as _time

        t0 = _time.perf_counter()
        res = self._answer(query, *args, **kwargs)
        secs = round(_time.perf_counter() - t0, 2)
        res["latency_s"] = secs
        log_latency(query, secs, res.get("engine_used", ""), (res.get("scope") or {}).get("ask"))
        return res

    def _answer(
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
        use_llm = prefer_llm and self.api_key is not None and self.cloud_ready()

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

        if (evidence.get("escopo") or {}).get("resumo_generico"):
            log_generic_fallback(query, sc)
            if re.search(r"\b(quem|qual|quais|quantos|quantas|onde|quando)\b", norm_q(query)):
                local_md = ("_Não achei nos dados um alvo exato para essa pergunta; abaixo está o panorama do jogo. "
                            "Tente citar o jogador, a equipe ou o número que quer (ex.: \u201cquem teve mais xG?\u201d)._\n\n"
                            + local_md)
        local_audit = NumericHallucinationGuard.audit_text_numbers(local_md, evidence)
        result = {"engine_used": "LOCAL_SCOPED_ENGINE", "report_markdown": local_md,
                  "hallucination_audit": local_audit, "scope": sc.to_dict(), "evidence": evidence}
        # perguntas de fato (quem jogou, quantos erros, quem teve mais xG, gols...) já saem exatas do redator local:
        # não vale esperar a nuvem (5–20 s) para reescrever uma lista de números.
        if not use_llm or sc.ask in FACT_ASKS:
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
            low = str(err).lower()
            if not any(k in low for k in ("api_key", "permission", "invalid")):   # rede/tempo/servidor: pausa a nuvem
                self.trip()
            result["engine_used"] = "REDATOR LOCAL (Gemini indisponível)"
            result["llm_error"] = self.explain_error(err)
            return result
