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
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv

from src.intelligence.query_understanding import QueryScope, QueryUnderstanding
from src.intelligence.query_understanding import norm as norm_q
from src.intelligence.scoped_evidence import ScopedEvidenceBuilder
from src.intelligence.tactical_writers import TACTICAL_WRITERS
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
FACT_ASKS = {"goals", "ranking", "profile", "unavailable", "presence", "errors", "corridors", "conceded_how", "rating",
             "lineup_role",
             "team_merit",
             "between_lines", "efficiency", "moments", "goal_buildup", "defenders_diag", "combinations"}


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
            if key == "historia":
                from src.intelligence import match_story

                out.append(match_story.write(b, _fmt))
                if b["fatores"]:
                    summary.append(b["fatores"][0]["leitura"].rstrip("."))
                continue
            if key == "escalacao":
                txt, summ = cls._lineup_text(b)
                out.append(txt)
                if summ:
                    summary.append(summ)
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
            if key in TACTICAL_WRITERS:
                txt, summ = TACTICAL_WRITERS[key](cls, b, sc)
                out.append(txt)
                if summ:
                    summary.append(summ)
                continue
            if key == "ausente":
                nomes = [n.title() if n.islower() else n for n in b["nomes"]]
                out.append(f"**{' e '.join(nomes)} não {'está' if len(nomes) == 1 else 'estão'} nesta partida** — "
                           f"nenhum lance, entrada ou saída registrados entre os {b['elenco_da_partida']} jogadores que atuaram. "
                           "Não dá para analisar o que ele fez neste jogo; se quiser, cite outro jogo dele ou um jogador que "
                           "esteve em campo.")
                continue
            if key == "comparacao":
                continue                                     # a comparação é escrita depois dos blocos dos jogadores
            if key == "ambiguo":
                out.append("Tem mais de um jogador com esse nome nesta partida: " + ", ".join(f"**{n}**" for n in b["nomes"])
                           + ". De qual deles você está falando?")
                continue
            if key == "sujeito":
                out.append(f"_O principal criador do adversário neste jogo foi **{b['quem']}** ({b['equipe']}) — {b['criterio']}._")
                continue
            if key.startswith("nota::"):
                out.append(cls._rating_text(b, sc))
                if b.get("desempenho") is not None:
                    summary.append(f"{b['jogador']} fez uma atuação {b['classificacao']} ({_fmt(b['desempenho'])})")
                continue
            if key == "merito":
                txt, summ = cls._merit_text(b)
                out.append(txt)
                summary.append(summ)
                continue
            if key == "ranking" and b.get("chave") == "erros_perigosos":
                e = b["erros_perigosos"]
                rows = [r for r in e["jogadores"] if r["perdas"]]
                if not rows:
                    out.append("Nenhuma perda de bola desse grupo virou finalização do rival em até 15 s.")
                    continue
                filt = {"defesa": "defensores", "meio": "meio-campistas", "ataque": "atacantes"}.get(e.get("filtro"), "jogadores")
                lines = "\n".join(f"{i}. {r['jogador']} ({r['equipe']}): {_pl(r['perdas'], 'perda', 'perdas')}, "
                                  f"{r['viraram_finalizacao']} virou(aram) finalização do rival (xG {_fmt(r['xg_cedido'])}"
                                  + (f", {_pl(r['gols_sofridos'], 'gol', 'gols')}" if r['gols_sofridos'] else "") + ")"
                                  for i, r in enumerate(rows, 1))
                out.append(f"**Erros dos {filt} de {e['equipe']} que deram chance ao rival** ({e['criterio']}):\n{lines}")
                top = rows[0]
                summary.append(f"{top['jogador']} foi quem mais errou com custo: "
                               f"{_pl(top['viraram_finalizacao'], 'perda virou', 'perdas viraram')} finalização do rival")
                continue
            if key == "ranking" and b.get("chave") == "perigo_ia":
                out.append(cls._danger_ranking(b))
                if b.get("lideres_ia"):
                    l0 = b["lideres_ia"][0]
                    summary.append(f"segundo a rede neural, {l0['jogador']} criou mais ações perigosas ({l0['acoes_perigosas']})")
                continue
            if key == "ranking" and b.get("perspectivas"):
                pp = b["perspectivas"]
                leaders = {k: v["lideres"][0] for k, v in pp.items() if v["lideres"]}
                names = {v["jogador"] for v in leaders.values()}
                if len(names) == 1:
                    one = next(iter(names))
                    out.append(f"**{one}** foi quem mais criou perigo por qualquer critério — no passe/condução, no "
                               "chute e nas chances para os outros.")
                else:
                    out.append("**Depende do que você chama de perigo** — são coisas diferentes, e cada uma tem um líder:")
                for k, v in pp.items():
                    if v["lideres"]:
                        row = "; ".join(f"{r['jogador']} ({r['equipe']}) {_fmt(r['valor'])}" for r in v["lideres"])
                        out.append(f"- **{v['criterio'][0].upper() + v['criterio'][1:]}:** {row}")
                ia = b.get("segunda_opiniao_ia") or {}
                if ia.get("modelo") and ia.get("lideres_ia"):
                    l0 = ia["lideres_ia"][0]
                    out.append(f"- **Posses que a rede neural vê com chance de virar finalização (≥ {ia.get('limiar_pct', 30)}%):** "
                               + "; ".join(f"{r['jogador']} ({r['acoes_perigosas']})" for r in ia["lideres_ia"][:3])
                               + " — leitura do modelo, de precisão modesta." + LocalScopedWriter._model_line(ia.get("modelo")))
                lid = b.get("lideres") or []
                if lid:
                    out.append(f"_Se for para somar tudo num número só (xT + xG, a soma que o laboratório usa como \"perigo "
                               f"total\"), quem lidera é {lid[0]['jogador']} ({_fmt(lid[0]['valor'])})._")
                if "xt" in leaders:
                    summary.append(f"{leaders['xt']['jogador']} foi quem mais levou a bola para perto do gol"
                                   + (f", e {leaders['xg']['jogador']} quem teve as melhores chances" if "xg" in leaders and
                                      leaders["xg"]["jogador"] != leaders["xt"]["jogador"] else ""))
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
                first = lid[0]
                lab0 = b["metrica"].split(" (")[0].split(" por 90")[0]
                if b.get("ordem") == "asc":
                    opening = (f"Quem menos contribuiu em **{lab0.lower()}** foi **{first['jogador']}** ({first['equipe']}), "
                               f"com {_fmt(first['valor'])} por 90 minutos")
                else:
                    opening = f"Quem mais se destacou em **{lab0.lower()}** foi **{first['jogador']}** ({first['equipe']}), com {_fmt(first['valor'])}"
                if len(lid) > 1:
                    opening += f"; logo atrás veio {lid[1]['jogador']} ({_fmt(lid[1]['valor'])})"
                out.append(opening + "." + (f" _{b['nota_proxy'].capitalize()}._" if b.get("nota_proxy") else ""))
                head = f"**{b['metrica']} — {b['equipes_consideradas']}" + (f", {sc.describe()}" if sc.has_cut else "") + ":**"
                rows = "\n".join(f"{i}. {r['jogador']} ({r['equipe']}): {_fmt(r['valor'])}"
                                  + (f" · {r['secundaria'].lower()}: {_fmt(r['valor_secundario'])}" if r.get("secundaria") else "")
                                  for i, r in enumerate(lid, 1))
                out.append(head + "\n" + rows)
                ia = b.get("segunda_opiniao_ia") or {}
                if ia.get("modelo") and ia.get("lideres_ia"):
                    out.append(cls._danger_ranking(ia))

                continue
            if key.startswith("perfil_ameaca::"):
                continue                                     # usados dentro do plano conjunto
            if key == "plano_conjunto":
                prof = {k.split("::", 1)[1]: v for k, v in blocks.items() if k.startswith("perfil_ameaca::")}
                out.append(cls._plan_multi(b, prof))
                if b.get("abastecedor_comum"):
                    summary.append(f"o caminho mais curto é secar {next(iter(b['abastecedor_comum']))}, que abastece mais de um deles")
                elif b.get("ligacoes_entre_eles"):
                    l0 = b["ligacoes_entre_eles"][0]
                    summary.append(f"cortar a ligação {l0['de']} → {l0['para']}")
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
                gl = b.get("gols") or 0
                head_goal = ""
                if re.search(r"\bgol", norm_q(sc.raw)):
                    head_goal = (f"**{'Sim' if gl else 'Não'}, {b['jogador']} {'marcou ' + _pl(gl, 'gol', 'gols') if gl else 'não marcou'}"
                                 + (f" ({', '.join(str(m) + chr(39) for m in b.get('minutos_dos_gols') or [])})" if gl else "") + ".** ")
                zs = b.get("zonas_onde_recebeu") or b.get("zonas_onde_mais_atuou") or []
                where = (" Recebeu mais " + " e ".join(cls._att(z["zona"]) for z in zs[:2]) + "." if zs else "")
                out.append(head_goal +
                    f"**{b['jogador']}** ({b['equipe']}): {b['acoes']} ações no recorte — {b['passes']} passes "
                    f"({_fmt(b['precisao_passe_pct'])}%), {b['passes_progressivos']} progressivos, {b['quebras_de_linha']} quebras de linha, "
                    f"xT {_fmt(b['xt_gerado'])}; {_pl(b['finalizacoes'], 'finalização', 'finalizações')} (xG {_fmt(b['xg'])}); "
                    + (f"{_pl(b['duelos'], 'desarme disputado', 'desarmes disputados')} ({_fmt(b['duelos_ganhos_pct'])}% ganhos); " if b['duelos'] else "")
                    + (f"{_pl(b.get('dribles_tentados', 0), 'drible tentado', 'dribles tentados')}; " if b.get('dribles_tentados') else "")
                    + f"{b['perdas_de_posse']} perdas e {b['recuperacoes']} recuperações."
                    + (f" {b.get('finalizacoes_dentro_da_area', 0)} das finalizações foram de dentro da área, "
                       f"{b.get('finalizacoes_no_alvo', 0)} no alvo." if b.get("finalizacoes") else "")
                    + where
                    + (f" Quem mais o abastece: {feed}." if feed else "") + (f" Para quem mais passa: {tgt}." if tgt else "")
                    + cls._small_sample(b.get("amostra_N")))
                if feed:
                    summary.append(f"a bola chega em {b['jogador']} principalmente por {list((b.get('quem_mais_o_abastece') or {}).keys())[0]}")
                else:
                    summary.append(f"{b['jogador']} participou de {b['acoes']} ações no recorte")
        if "comparacao" in blocks:
            ps = [blocks.get(f"jogador::{p}") for p in blocks["comparacao"]["jogadores"]]
            ps = [p for p in ps if p]
            if len(ps) >= 2:
                rows = [("Ações", "acoes"), ("Passes", "passes"), ("Precisão de passe (%)", "precisao_passe_pct"),
                        ("Passes progressivos", "passes_progressivos"), ("xT gerado", "xt_gerado"), ("Finalizações", "finalizacoes"),
                        ("xG", "xg"), ("Gols", "gols"), ("Dribles tentados", "dribles_tentados"), ("Perdas", "perdas_de_posse")]
                head = "| | " + " | ".join(p["jogador"] for p in ps) + " |\n|---|" + "---|" * len(ps)
                body = "\n".join(f"| {lab} | " + " | ".join(_fmt(p.get(k)) for p in ps) + " |" for lab, k in rows)
                a, b2 = ps[0], ps[1]
                diff = []
                if (a.get("xg") or 0) != (b2.get("xg") or 0):
                    hi = a if (a.get("xg") or 0) > (b2.get("xg") or 0) else b2
                    diff.append(f"{hi['jogador']} chegou mais em condição de gol (xG {_fmt(hi['xg'])})")
                if (a.get("xt_gerado") or 0) != (b2.get("xt_gerado") or 0):
                    hi = a if (a.get("xt_gerado") or 0) > (b2.get("xt_gerado") or 0) else b2
                    diff.append(f"{hi['jogador']} empurrou mais o time para frente com passes e conduções (xT {_fmt(hi['xt_gerado'])})")
                out.append("**Lado a lado:**\n" + head + "\n" + body + ("\n\n" + "; ".join(diff) + "." if diff else ""))
                summary.insert(0, diff[0] if diff else f"{a['jogador']} e {b2['jogador']} lado a lado")
        if summary:
            joined = "; ".join(summary[:2])
            out.append("\n**Em resumo:** " + joined[:1].upper() + joined[1:] + ".")
        return "\n\n".join(out)

    # ------------------------------------------------------------------ perguntas fora dos eventos
    UNAVAILABLE_WHY = {
        "distancia": "distância percorrida, velocidade e sprints vêm de rastreamento físico (GPS/câmeras de tracking), "
                     "que nenhuma fonte aberta publica",
        "fisico": "dados físicos e médicos (peso, batimentos, lesões) não fazem parte das bases de jogo",
        "contexto": "público, clima, gramado e salários não constam nas fontes de lances e estatísticas",
    }

    @staticmethod
    def _lineup_text(b: Dict[str, Any]) -> Tuple[str, str]:
        team, want = b["equipe"], b["pedido"]

        def who(r):
            extra = (f", entrou aos {r['entrou_aos']}'" if r.get("entrou_aos") else "") + \
                    (f", saiu aos {r['saiu_aos']}'" if r.get("saiu_aos") else "")
            return f"**{r['jogador']}** ({r['posicao']}{extra})"
        if want != "escalacao" and b["encontrados"]:
            h = b["encontrados"]
            if want == "goleiro":
                main = h[0]
                txt = f"O goleiro de {team} foi **{main['jogador']}**" + (
                    " — jogou a partida inteira." if not main.get("saiu_aos") and not main.get("entrou_aos") else
                    f" ({main['minutos']} min)." )
                if len(h) > 1:
                    txt += " Também atuou no gol: " + ", ".join(who(r) for r in h[1:]) + "."
                return txt, f"{main['jogador']} foi o goleiro de {team}"
            return (f"{want.capitalize()}s de {team} nesta partida: " + "; ".join(who(r) for r in h) + ".",
                    f"{len(h)} jogador(es) de {team} atuaram como {want}")
        if want != "escalacao":
            return (f"Não encontrei ninguém de {team} registrado como {want} nos lances desta partida. "
                    "A posição vem do que a fonte marca em cada lance — sem esse registro, prefiro não chutar.", "")
        xi = b["titulares"]
        lines = [f"**Titulares de {team}:** " + "; ".join(f"{r['jogador']} ({r['posicao']})" for r in xi) + "."]
        if b["entraram"]:
            lines.append("**Entraram:** " + "; ".join(f"{r['jogador']} ({r['entrou_aos']}')" for r in b["entraram"]) + ".")
        if b.get("banco_nao_utilizado"):
            lines.append("**No banco, sem entrar:** " + ", ".join(b["banco_nao_utilizado"]) + ".")
        return "\n\n".join(lines), f"{team} começou com {len(xi)} titulares registrados"

    @classmethod
    def _unavailable(cls, b: Dict[str, Any]) -> str:
        ped = str(b.get("pedido") or "")
        fis = b.get("fisico") or {}
        if fis.get("ranking"):
            lab = fis["rotulo"]
            rows = "\n".join(f"{i}. {r['jogador']} ({r['equipe']}): {_fmt(r['valor'])} {fis['unidade']}"
                              for i, r in enumerate(fis["ranking"][:6], 1))
            first = fis["ranking"][0]
            return (f"**{first['jogador']}** ({first['equipe']}) foi quem mais teve {lab}: {_fmt(first['valor'])} {fis['unidade']}.\n\n"
                    f"**{lab.capitalize()} — medição física da liga, publicada pela FotMob:**\n{rows}\n\n"
                    "_Dado físico real (rastreamento da liga), não estimado a partir dos lances._")
        kind = ("distancia" if re.search(r"distanc|km|quilometr|corr|velocid|sprint|acelera", ped) else
                "fisico" if re.search(r"peso|pesa|batiment|cardiac|lesa|lesion|machuc", ped) else "contexto")
        if kind == "distancia":
            return ("**Não dá para saber quem correu mais ou fez mais sprints: essa informação não existe na base desta "
                    "partida.** Sprint, distância e "
                    "velocidade só existem com dados físicos (rastreamento por câmera/GPS), e esta partida não tem esse "
                    "dado em nenhuma fonte da base. Os lances registram o que acontece COM a bola — uma condução longa "
                    "ou uma corrida para receber nas costas não é um sprint medido, então não vou usar isso como se fosse.\n\n"
                    "Onde existe: algumas ligas (como a Premier League) publicam distância e sprints na FotMob — baixe os "
                    "jogos com `python -m src.data_hub.sync --only fotmob_jogos` e a resposta passa a vir com o número real.\n\n"
                    "Perto disso, com dado real deste jogo, consigo responder: quem mais conduziu a bola para frente, "
                    "quem mais atacou o espaço nas costas da defesa e quem mais pressionou.")
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
            if b.get("relacionado") and not b.get("titular_na_lista"):
                return (f"**Não entrou em campo.** {b['jogador']} estava entre os reservas de {b['equipe']} na escalação "
                        "publicada, mas não tem nenhum lance nem entrada registrada — ficou no banco.")
            if b.get("relacionado"):
                return (f"**Inconclusivo.** {b['jogador']} aparece como titular na escalação publicada de {b['equipe']}, "
                        "mas não tem nenhum lance registrado nos dados de eventos. As fontes divergem — prefiro não cravar.")
            if b.get("jogador"):
                return f"**Não.** {b['jogador']} não tem nenhum lance registrado nesta partida."
            if b.get("lista_de_relacionados"):
                return (f"**Não.** \u201c{asked}\u201d não está nem entre os titulares nem entre os reservas da escalação "
                        "publicada desta partida — não foi relacionado. O motivo (lesão, suspensão, opção) não está nos dados.")
            return (f"**Não encontrei \u201c{asked}\u201d entre os jogadores desta partida.** Ninguém com esse nome tem lance, "
                    "entrada ou saída registrados. Como não tenho a lista de reservas deste jogo, não dá para dizer se ele "
                    "ficou no banco ou nem foi relacionado — e o motivo da ausência não está nos dados.")
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
    def _rating_text(cls, b: Dict[str, Any], sc: QueryScope) -> str:
        """Nota 2.0 em linguagem de conversa: veredito primeiro, depois o porquê (com os números)."""
        p = b["jogador"]
        if b.get("sem_dados"):
            return f"Não consigo avaliar {p}: não há lances dele nesta partida."
        if b.get("desempenho") is None:
            return (f"{p} jogou só {_fmt(b['minutos'])} minutos — {b['amostra']}. Com tão pouco tempo eu não dou nota: seria "
                    "chute, e ausência de dado não vira nota baixa.")
        n, imp = b["desempenho"], b["impacto"]
        verdict = {"desastrosa": "foi muito mal", "muito ruim": "foi mal", "ruim": "ficou abaixo do esperado",
                   "regular": "fez um jogo regular", "razoável": "fez um jogo razoável", "boa": "jogou bem",
                   "muito boa": "jogou muito bem", "excelente": "foi excelente", "excepcional": "fez uma atuação excepcional"}
        pt = b["dimensoes_pt"]
        dims = {k: v for k, v in b["dimensoes"].items() if v is not None}
        best = sorted(dims.items(), key=lambda kv: -kv[1])[:2]
        worst = sorted(dims.items(), key=lambda kv: kv[1])[:1]
        gl = b.get("gols") or 0
        goal_ans = ""
        if re.search(r"\bgol", norm_q(sc.raw)):
            goal_ans = (f"**{'Sim' if gl else 'Não'}, {p} {'marcou ' + _pl(gl, 'gol', 'gols') if gl else 'não marcou'}.** ")
        txt = goal_ans + (f"**{p} {verdict.get(b['classificacao'], 'jogou')}**: nota de desempenho **{_fmt(n)}** ({b['classificacao']}) "
               f"e impacto no jogo **{_fmt(imp)}**")
        if b.get("ranking_na_funcao") and b.get("na_funcao", 0) > 1:
            txt += f" — {b['ranking_na_funcao']}º entre os {b['na_funcao']} {b['funcao']}s da partida"
        txt += ".\n\n"
        txt += (f"O que mais pesou a favor: {pt[best[0][0]].lower()} ({_fmt(best[0][1])})"
                + (f" e {pt[best[1][0]].lower()} ({_fmt(best[1][1])})" if len(best) > 1 else "") + ". ")
        if worst and worst[0][1] < 5.5:
            txt += f"O ponto fraco foi {pt[worst[0][0]].lower()} ({_fmt(worst[0][1])}). "
        facts = []
        if b.get("gols"):
            facts.append(_pl(b["gols"], "gol", "gols"))
        if b.get("assistencias"):
            facts.append(_pl(b["assistencias"], "assistência", "assistências"))
        if b["funcao"] == "goleiro":
            facts.append("goleiro avaliado pelo modelo próprio de goleiros (defesas, segurança, distribuição, cobertura)")
        if facts:
            txt += "Também conta: " + ", ".join(facts) + ". "
        nobs = [pt[k].lower() for k, v in b["dimensoes"].items() if v is None]
        txt += (f"\n\n_Confiança {b['confianca']} ({b['confianca_pct']}%): {_fmt(b['minutos'])} min ({b['amostra']}), comparado com "
                f"{b['pares']} atuações da mesma função."
                + (f" Não observado nesta fonte: {', '.join(nobs)}." if nobs else "") + "_")
        return txt

    @staticmethod
    def _merit_text(b: Dict[str, Any]) -> tuple:
        e = b["equipes"]
        (t1, a), (t2, c) = list(e.items())
        key = b["metrica"]
        lab = "xG (qualidade das chances)" if key == "xg" else "xT (o quanto cada time levou a bola para perto do gol)"
        va, vc = a.get(key) or 0, c.get(key) or 0
        win = t1 if va > vc else t2 if vc > va else None
        kl = "xG" if key == "xg" else "xT"
        txt = (f"**Pelo {kl}, {'quem merecia vencer era ' + win if win else 'deu empate'}**: "
               f"{t1} {_fmt(va)} x {_fmt(vc)} {t2} — {lab}.\n\n"
               f"O placar foi {t1} {a.get('gols')} x {c.get('gols')} {t2}. "
               f"{t1}: {a.get('finalizacoes')} finalizações ({a.get('no_alvo')} no alvo), {a.get('grandes_chances')} chances claras. "
               f"{t2}: {c.get('finalizacoes')} finalizações ({c.get('no_alvo')} no alvo), {c.get('grandes_chances')} chances claras.")
        g1, g2 = a.get("gols") or 0, c.get("gols") or 0
        res = t1 if g1 > g2 else t2 if g2 > g1 else None
        if win and res and win != res:
            txt += f" Ou seja: {res} venceu com menos do que as chances indicavam — eficiência (ou sorte) acima do normal."
        elif win and res == win:
            txt += f" O resultado bateu com os números: {win} criou mais e venceu."
        return txt, (f"pelo {kl}, {win} merecia a vitória" if win else f"pelo {kl} o jogo foi equilibrado")

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
    def profile_moves(b: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Estratégias escolhidas pelo PERFIL medido do jogador (oposição) e como explorá-lo quando ele defende
        (proposição). Cada uma só entra se o número que a justifica passar do mínimo — nada de roteiro fixo.
        """
        f = b.get("perfil") or {}
        p, r = b["jogador"], b.get("quem_defende", "o rival")
        rec = b.get("passes_recebidos") or 0
        out: List[Tuple[str, str]] = []
        if f.get("recebe_entre_linhas", 0) >= 6:
            out.append(("Fechar a zona 14", f"{f['recebe_entre_linhas']} das {rec} bolas que {p} recebeu foram entre a defesa e o "
                        f"meio. Volante fixo à frente da área e zagueiro autorizado a sair na antecipação — ele não pode receber de frente."))
        if f.get("recebe_nas_costas", 0) >= 3:
            out.append(("Controlar a profundidade", f"{p} recebeu {f['recebe_nas_costas']} bolas já dentro da área/nas costas. "
                        f"Linha um passo mais baixa quando o passador estiver sem pressão e cobertura do lateral do lado oposto."))
        if f.get("dribles_tentados", 0) >= 4:
            ok = f.get("dribles_certos")
            out.append(("Não dar o bote", f"Tentou {f['dribles_tentados']} dribles" + (f" ({ok} certos)" if ok is not None else "")
                        + ". Temporizar, mostrar o lado do pé "
                        f"mais fraco e esperar a dobra; a falta tática no meio-campo é melhor do que o 1 contra 1 perto da área."))
        if f.get("conducoes_progressivas", 0) >= 5:
            out.append(("Cortar a condução", f"{f['conducoes_progressivas']} conduções para frente. Fechar o corredor interno com o "
                        f"meia do lado e não deixar o campo aberto à frente dele depois que ele recebe."))
        if f.get("chutes_de_fora", 0) >= 2:
            out.append(("Bloquear o chute de fora", f"{f['chutes_de_fora']} finalizações de fora da área. Quem marca precisa encurtar "
                        f"rápido e ficar de frente, sem se virar."))
        if f.get("cruzamentos", 0) >= 4:
            out.append(("Impedir o cruzamento", f"Cruzou {f['cruzamentos']} vezes. Lateral fechado na linha de fundo e ponta voltando "
                        f"para fazer a dobra antes que ele ajeite."))
        if f.get("aereos_ganhos", 0) >= 3:
            out.append(("Disputa aérea antecipada", f"Ganhou {f['aereos_ganhos']} bolas pelo alto. Marcação na frente dele nas bolas "
                        f"longas e cruzamentos, e alguém na segunda bola."))
        if f.get("recebe_aberto", 0) >= max(5, 0.5 * rec) and rec:
            out.append(("Dobrar pelo lado", f"{f['recebe_aberto']} das {rec} bolas chegaram aberto, na beirada. Lateral e ponta "
                        f"juntos quando a bola for nele; o meia do lado fecha a diagonal para dentro."))
        mins = f.get("minutos") or 0
        if mins >= 45 and f.get("acoes_defensivas", 99) <= max(3, mins / 30):
            side = f.get("lado_habitual")
            out.append(("Proposição: atacar o lado dele", f"{p} fez só {f['acoes_defensivas']} ações defensivas em ~{int(mins)} min"
                        + (f" e joga mais pela {side}" if side and side != "centro" else "")
                        + f". Quando {r} recuperar a bola, acelerar por ali: o lateral dele fica sozinho."))
        if (b.get("perdas_de_posse") or 0) >= 8:
            out.append(("Pressionar no domínio", f"Perdeu a bola {b['perdas_de_posse']} vezes — pressão no primeiro toque rende "
                        f"recuperação perto da área dele."))
        return out

    @staticmethod
    def _plan_multi(b: Dict[str, Any], profiles: Dict[str, Dict[str, Any]]) -> str:
        names = b.get("jogadores") or []
        if len(b.get("validos", names)) < 2 and "equipe" not in b:
            return ("Para montar um plano conjunto preciso de pelo menos dois desses jogadores em campo nesta partida; "
                    f"encontrei {', '.join(b.get('validos') or []) or 'nenhum'}.")
        r, team = b["quem_defende"], b["equipe"]
        who = ", ".join(names[:-1]) + " e " + names[-1]
        share = b.get("fatia_somada_pct")
        lines = [f"**Para parar {who}, {r} precisa atacar o que liga os três (ou dois), não cada um separado.**"
                 if len(names) > 2 else f"**Para parar {who}, {r} precisa atacar o que liga os dois, não cada um separado.**"]
        if share:
            lines.append(f"Juntos eles responderam por {_fmt(share)}% da ameaça criada por {team} (xT).")
        steps = []
        sh = b.get("abastecedor_comum") or {}
        if sh:
            f, hit = max(sh.items(), key=lambda kv: sum(kv[1].values()))
            det = ", ".join(f"{_fmt(v)} para {k}" for k, v in hit.items())
            steps.append(f"**Secar a fonte comum:** {f} abasteceu mais de um deles ({det}). Pressionar {f} na hora do passe "
                         f"tira a bola de vários ao mesmo tempo — é a peça mais rentável para marcar.")
        lk = b.get("ligacoes_entre_eles") or []
        if lk:
            l0 = lk[0]
            steps.append(f"**Cortar a ligação entre eles:** {l0['de']} → {l0['para']} foi a conexão mais usada ({l0['passes']} passes). "
                         f"Quem marca {l0['para']} joga entre ele e {l0['de']}, não atrás.")
        dom, pct = b.get("corredor_dominante"), b.get("pct_corredor_dominante")
        if dom and pct and pct >= 40:
            free = b.get("corredor_livre")
            steps.append(f"**Inclinar o bloco para a {dom}:** {_fmt(pct)}% das bolas que eles receberam foram por esse corredor. "
                         f"Bascular a linha para lá e aceitar deixar a {free} menos protegida — foi por onde eles menos receberam.")
        elif dom:
            steps.append("**Bloco compacto por dentro:** as recepções deles se espalharam pelos corredores — "
                         "melhor encurtar a distância entre defesa e meio do que perseguir um lado.")
        indiv = []
        for p in names:
            mv = LocalScopedWriter.profile_moves(profiles.get(p) or {"jogador": p})
            if mv:
                indiv.append(f"- **{p}:** {mv[0][0].lower()} — {mv[0][1]}")
        out = "\n".join(lines) + "\n\n" + "\n".join(f"{i}. {s_}" for i, s_ in enumerate(steps, 1))
        if indiv:
            out += "\n\n**Ajuste específico para cada um (pelo perfil medido):**\n" + "\n".join(indiv)
        out += ("\n\n💡 _Hipótese de equilíbrio: fechar esses caminhos com o bloco inteiro, e não com marcação individual, "
                "evita abrir buracos atrás. Não dá para provar com os dados que funcionaria — é a leitura dos números._")
        return out

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
        moves = LocalScopedWriter.profile_moves(b)
        titles = {t for t, _ in moves}
        if "Não dar o bote" not in titles and (b.get("faltas_sofridas") or 0) >= 3:
            steps.append(f"**Evitar o bote precipitado:** sofreu {_pl(b['faltas_sofridas'], 'falta', 'faltas')}. "
                         "Defender de frente e com cobertura.")
        for title, txt in moves[:4]:
            steps.append(f"**{title}:** {txt}")
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

        budget = float(os.getenv("GEMINI_TIMEOUT_S", "8"))    # teto por chamada
        deadline = getattr(self, "_deadline", None)          # teto da PERGUNTA inteira (todas as tentativas, ~10 s)
        if deadline is not None:
            budget = min(budget, deadline - _time.time())
            if budget <= 1.5:
                raise TimeoutError("Tempo da pergunta esgotado — resposta redigida localmente.")

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
        parts = [q.strip() + "?" for q in re.split(r"\?+", query or "") if len(q.strip().split()) >= 3]
        if len(parts) >= 2:                              # só divide se CADA parte tiver alvo próprio
            parsed = [QueryUnderstanding.parse(q) for q in parts]
            if not all(sc_.in_scope and (sc_.ask or sc_.players or sc_.metrics or sc_.team_named) for sc_ in parsed) or \
                    any(re.match(r"^\s*(e |ele|ela|foi |isso|esse|essa)", q.lower()) for q in parts[1:]):
                parts = [query]
        if len(parts) >= 2:                              # duas perguntas na mesma mensagem: responde as duas
            subs = [self._answer(q, *args, **kwargs) for q in parts[:3]]
            md = "\n\n---\n\n".join(f"**{q}**\n\n{r['report_markdown']}" for q, r in zip(parts, subs))
            audits = [r.get("hallucination_audit") or {} for r in subs]
            evs = [r.get("evidence") or {} for r in subs]
            merged = None
            if any(evs):
                base = next(e for e in evs if e)
                merged = {**base, "blocos": {f"{i}::{k}": v for i, e in enumerate(evs) for k, v in (e.get("blocos") or {}).items()}}
            res = {**subs[0], "report_markdown": md, "evidence": merged,
                   "hallucination_audit": {**audits[0], "is_grounded": all(a.get("is_grounded", True) for a in audits)},
                   "subanswers": subs}
        else:
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
        if not sc.players:                                    # jogador citado que não está nesta partida (ex.: Kane)
            sc.absent = QueryUnderstanding.absent_names(query, norm_q(query), roster, ordered)
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

            import time as _time

            self._deadline = _time.time() + float(os.getenv("ASSISTENTE_TETO_S", "10"))

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
