"""
Roteador da IA do laboratório (rodada 12) — a NOSSA IA decide o que a pergunta pede e responde com o dado certo.

Ordem: (1) várias perguntas na mesma mensagem → responde cada uma; (2) intenções táticas/contextuais (próximo jogo,
desfalques, quem jogou melhor, substituição, ponto forte, ponto fraco, o que melhorar, como explorar, profundidade,
bolas longas, chances claras perdidas); (3) número específico (direct.py). Nada reconhecido → devolve None e o
analista clássico responde (ele é ótimo em presença, autores dos gols e linha do tempo).
Cada resposta: resposta direta → números que embasam → limite do dado. Nunca inventa: sem o dado, diz que não tem.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from src.intelligence.lab_ai import direct as D


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()


def _has(q: str, *pats: str) -> bool:
    return any(re.search(p, q) for p in pats)


def split_questions(question: str) -> List[str]:
    """'quem driblou mais e quem sofreu mais dribles?' → duas perguntas (só quando cada parte tem sujeito próprio)."""
    parts = re.split(r"\?\s*|\s+e\s+(?=quem\b|qual\b|quantos\b|quantas\b|como\b|onde\b)", question.strip(), flags=re.I)
    parts = [p.strip(" ?") for p in parts if p and len(p.strip().split()) >= 2]
    return parts if len(parts) >= 2 else [question]


class Ctx:
    def __init__(self, meta, df, box, focus, db, pt: Callable[[str], str]):
        self.meta, self.df, self.box, self.db, self.pt = meta, df, box, db, pt
        self.teams = [t for t in (meta.get("home_team_name"), meta.get("away_team_name")) if t]
        self.focus = focus if focus in self.teams else (self.teams[0] if self.teams else "")
        self.has_events = df is not None and not getattr(df, "empty", True)
        self._facts = None
        self._extra = None

    def named_team(self, q: str) -> Optional[str]:
        fq = _fold(q)
        hits = [t for t in self.teams if any(w in fq for w in _fold(t).split() if len(w) >= 4) or _fold(self.pt(t)) in fq]
        return hits[0] if len(hits) == 1 else None

    def other(self, t: str) -> str:
        return next((x for x in self.teams if x != t), "")

    @property
    def facts(self):
        if self._facts is None:
            from src.intelligence.lab_ai.facts import match_facts

            self._facts = match_facts(self.meta, self.df, self.box, self.db)
        return self._facts

    @property
    def extra(self) -> Dict[str, Any]:
        if self._extra is None:
            self._extra = {}
            try:
                with self.db.connect() as conn:
                    r = conn.execute("SELECT extra_json FROM match_extra WHERE match_id = ?",
                                     (int(self.meta.get("match_id") or 0),)).fetchone()
                self._extra = json.loads(r[0]) if r and r[0] else {}
            except Exception:
                self._extra = {}
        return self._extra

    def ratings(self) -> pd.DataFrame:
        """Nota por jogador: FotMob (fonte) quando existe; com lances, a nota 0–10 do laboratório."""
        ps = (self.box or {}).get("player_stats")
        if ps is not None and not getattr(ps, "empty", True) and "rating" in ps and pd.to_numeric(ps["rating"], errors="coerce").notna().any():
            t = ps.assign(nota=pd.to_numeric(ps["rating"], errors="coerce"),
                          minutos=pd.to_numeric(ps.get("minutes"), errors="coerce"))
            return t.rename(columns={"player_name": "jogador", "team_name": "equipe"})[["jogador", "equipe", "nota", "minutos"]] \
                .dropna(subset=["nota"]).assign(fonte="nota da FotMob")
        if self.has_events:
            from src.metrics.player_rating import match_ratings

            r = match_ratings(self.df, None)
            return r[["jogador", "equipe", "nota", "minutos"]].dropna(subset=["nota"]).assign(fonte="nota 0–10 do laboratório")
        return pd.DataFrame()


# ------------------------------------------------------------------------------------------------ intenções
def _next_match(q, c: Ctx):
    if not _has(q, r"proxim[oa]s? jog", r"proxim[oa] partida", r"quando joga", r"proximo adversario"):
        return None
    team = c.named_team(q) or c.focus
    try:
        from src.squad.matchday import next_fixtures

        fx = next_fixtures(c.db, [team], limit=3)
    except Exception:
        fx = pd.DataFrame()
    if fx is None or fx.empty:
        return f"Não tenho próximos jogos de **{c.pt(team)}** no calendário da base (ESPN/FotMob) — nada a afirmar."
    lines = [f"- {str(r.kickoff)[:16].replace('T', ' ')} · {r.home} x {r.away} · {r.competition}" for r in fx.itertuples()]
    return f"Próximo jogo de **{c.pt(team)}**: {fx.iloc[0]['home']} x {fx.iloc[0]['away']}.\n\n" + "\n".join(lines) + \
        "\n\n_Fonte: calendário ESPN/FotMob (horário UTC)._"


def _absences(q, c: Ctx):
    if not _has(q, r"desfalque", r"lesionad", r"suspens", r"\bausen", r"nao jogou por", r"quem faltou"):
        return None
    des = c.extra.get("desfalques") or {}
    if not des:
        return "Não tenho a lista de desfalques deste jogo — a fonte não publicou (lacuna, não 'nenhum desfalque')."
    team = c.named_team(q)
    out = []
    for t, items in des.items():
        if team and _fold(t) != _fold(team) and _fold(c.pt(t)) != _fold(c.pt(team)):
            continue
        txt = "; ".join(f"{x.get('jogador')} ({'lesão' if x.get('tipo') == 'injury' else 'suspensão' if 'susp' in str(x.get('tipo')) else x.get('tipo')}"
                        + (f", volta: {x.get('volta')}" if x.get("volta") else "") + ")" for x in items)
        out.append(f"**{c.pt(t)}** ({len(items)}): {txt or 'nenhum listado'}")
    return "\n\n".join(out) + "\n\n_Fonte: desfalques publicados pela FotMob para a partida._" if out else None


def _best_player(q, c: Ctx):
    if not _has(q, r"jogou melhor", r"melhor em campo", r"melhor jogador", r"destaque do jogo", r"craque do jogo",
                r"quem foi o melhor", r"\bmvp\b", r"jogou pior", r"pior jogador", r"pior em campo"):
        return None
    worst = _has(q, r"pior")
    r = c.ratings()
    if r.empty:
        return "Não tenho nota por jogador neste jogo (a fonte não traz números individuais)."
    team = c.named_team(q)
    if team:
        r = r[r["equipe"].map(_fold) == _fold(team)]
    r = r[pd.to_numeric(r["minutos"], errors="coerce").fillna(0) >= 20] if r["minutos"].notna().any() else r
    r = r.sort_values(["nota", "minutos"], ascending=[worst, False])
    top = r.head(5)
    if top.empty:
        return None
    lead = top.iloc[0]
    craque = (c.extra.get("craque") or {}).get("jogador")
    lines = "\n".join(f"{i}. {x.jogador} ({c.pt(x.equipe)}) — nota {x.nota:.1f}"
                      + (f" (em {int(x.minutos)} min)" if x.minutos == x.minutos else "")
                      for i, x in enumerate(top.itertuples(), 1))
    head = f"{'Pior' if worst else 'Melhor'} atuação: **{lead.jogador}** ({c.pt(lead.equipe)}), nota {lead.nota:.1f}."
    if craque and not worst:
        head += f" A FotMob elegeu **{craque}** o craque do jogo."
    return f"{head}\n\n**Ranking** ({lead.fonte}, mínimo 20 min):\n\n{lines}"


def _substitution(q, c: Ctx):
    if not _has(q, r"substitu", r"\btroca(r|s)?\b", r"tirar quem", r"mexer no time", r"quem sair"):
        return None
    team = c.named_team(q) or c.focus
    r = c.ratings()
    out = []
    if not r.empty:
        mine = r[r["equipe"].map(_fold) == _fold(team)]
        starters = mine[pd.to_numeric(mine["minutos"], errors="coerce").fillna(0) >= 60] if mine["minutos"].notna().any() else mine
        low = starters.sort_values("nota").head(3)
        if len(low):
            out.append("**Quem pedia troca pelos números** (menor nota entre quem jogou 60+ min): " +
                       "; ".join(f"{x.jogador} ({x.nota:.1f})" for x in low.itertuples()) + ".")
    mom = c.extra.get("momentum") or []
    times = c.extra.get("times") or []
    if mom and times:
        sign = 1 if _fold(times[0]) == _fold(team) else -1
        m = pd.DataFrame(mom, columns=["min", "v"]).astype(float)
        m["v"] = m["v"] * sign
        roll = m.set_index("min")["v"].rolling(8, min_periods=4).mean()
        bad = roll[roll < -20]
        if len(bad):
            start = int(bad.index[0])
            out.append(f"**Quando mexer:** o domínio de {c.pt(team)} caiu a partir dos {start}' (momentum da FotMob, média "
                       f"de 8 min abaixo de −20). Trocar entre {max(45, start - 8)}' e {start}' antecipa a queda.")
        else:
            out.append(f"**Quando mexer:** o momentum da FotMob não mostra queda longa de {c.pt(team)} — troca por desgaste "
                       f"ou por estratégia de placar, não por perda de controle.")
    subs = (c.box or {}).get("timeline")
    if subs is not None and not getattr(subs, "empty", True) and "event_type" in subs:
        ss = subs[subs["event_type"].astype(str).str.contains("ubst", na=False) & (subs["team_name"].map(_fold) == _fold(team))]
        if len(ss):
            out.append("**O que o técnico fez:** " + "; ".join(f"{int(x.minute)}' {x.player_name}" + (f" ↔ {x.related_player}" if
                       isinstance(getattr(x, "related_player", None), str) and x.related_player else "") for x in ss.itertuples()
                       if x.minute == x.minute) + ".")
    if not out:
        return "Não tenho notas por jogador nem momentum deste jogo para sugerir substituição sem inventar."
    return f"Substituições para **{c.pt(team)}**, pelos números:\n\n" + "\n\n".join(out) + \
        "\n\n_Sugestão do laboratório (associação, não causa): cansaço físico não é medido nesta fonte._"


def _team_verdicts(c: Ctx, team: str):
    from src.intelligence.lab_ai.writer import verdict

    fs = [f for f in c.facts if not f.player and f.team == c.pt(team)]
    low_value = {"offsides", "yellow_cards", "red_cards", "fouls"}      # contam, mas não definem o jogo
    good_in_base = lambda f: f.pct is not None and f.sense and (f.pct - 50) * f.sense > 10
    bad_in_base = lambda f: f.pct is not None and f.sense and (f.pct - 50) * f.sense < -10
    strong = [f for f in fs if verdict(f) == "forte" and not bad_in_base(f)]
    weak = [f for f in fs if verdict(f) == "fraco" and not good_in_base(f)]
    strong = [f for f in strong if f.key not in low_value] + [f for f in strong if f.key in low_value]
    weak = [f for f in weak if f.key not in low_value] + [f for f in weak if f.key in low_value]
    key = lambda f: -abs((f.pct if f.pct is not None else 50) - 50) - (abs(f.value - (f.opp_value or f.value)) /
                                                                       max(abs(f.value), 1))
    lv = lambda f: f.key in low_value
    return sorted(strong, key=lambda f: (lv(f), key(f))), sorted(weak, key=lambda f: (lv(f), key(f)))


def _strength_weakness(q, c: Ctx):
    from src.intelligence.lab_ai.writer import EXPLOIT, explore_lines, line

    team = c.named_team(q) or c.focus
    wants_strong = _has(q, r"ponto forte", r"se destac", r"a mais ser destac", r"destacad", r"melhor coisa", r"virtude",
                        r"qualidade d")
    wants_weak = _has(q, r"ponto fraco", r"maior atencao", r"ponto de atencao", r"dificuldade", r"vulnerab", r"preocup",
                      r"falha", r"problema")
    wants_fix = _has(q, r"deveria ter feito", r"poderia ter feito", r"melhorar", r"corrigir", r"fez de errado", r"errou como time")
    wants_exploit = _has(q, r"explor", r"atacaria", r"machuc", r"como ganhar d", r"como vencer", r"como bater")
    if not (wants_strong or wants_weak or wants_fix or wants_exploit):
        return None
    if wants_exploit:
        target = team
        mine = c.other(target) if c.named_team(q) else c.focus
        if mine == target:
            mine = c.other(target)
        ex = explore_lines(sorted(c.facts, key=lambda f: -abs((f.pct or 50) - 50)), c.pt(mine), c.pt(target), k=5)
        _, weak = _team_verdicts(c, target)
        if not ex and not weak:
            return f"Os números deste jogo não mostram fraqueza clara de **{c.pt(target)}** (nada fora da curva com amostra)."
        body = "\n".join(f"- {x}" for x in ex) if ex else "\n".join(f"- {line(f)}" for f in weak[:4])
        return (f"Onde eu atacaria **{c.pt(target)}**, pelos números deste jogo:\n\n{body}\n\n"
                f"_Para fragilidades por jogador dos últimos jogos, veja Escalação → Plano de jogo._")
    strong, weak = _team_verdicts(c, team)
    out = []
    if wants_strong:
        out.append(f"**Ponto forte de {c.pt(team)}:** " + (line(strong[0]).replace("**", "") if strong else
                   "nenhum número fora da curva a favor neste jogo."))
        if len(strong) > 1:
            out.append("Também: " + "; ".join(f"{f.label} ({D._n(f.value)} × {D._n(f.opp_value)})" for f in strong[1:4]) + ".")
    if wants_weak or wants_fix:
        if weak:
            out.append(f"**Ponto de maior atenção de {c.pt(team)}:** " + line(weak[0]).replace("**", ""))
            if len(weak) > 1:
                out.append("Também pesou: " + "; ".join(f"{f.label} ({D._n(f.value)} × {D._n(f.opp_value)})"
                                                         for f in weak[1:4]) + ".")
        else:
            out.append(f"Nenhum número de {c.pt(team)} ficou claramente abaixo do rival e da base neste jogo.")
    if wants_fix and weak:
        fixes = [EXPLOIT[f.key][1] for f in weak if f.key in EXPLOIT][:3]
        if fixes:
            out.append("**O que fazer melhor:** " + "; ".join(fixes) + ".")
    return "\n\n".join(out) + "\n\n_Comparação com o rival e com a régua de milhares de jogos da base._"


def _depth(q, c: Ctx):
    if not _has(q, r"profundidade", r"costas da defesa", r"bola nas costas", r"defendeu .*profund"):
        return None
    out = []
    if not c.has_events:
        out.append("**Profundidade não é medida neste jogo**: sem lances com coordenadas não existe a posição da linha nem "
                   "dos passes em profundidade.")
    try:
        with c.db.connect() as conn:
            sh = pd.read_sql_query("SELECT team_name, situation, xg FROM match_shots WHERE match_id = ?", conn,
                                   params=(int(c.meta.get("match_id") or 0),))
        fb = sh[sh["situation"].astype(str).str.contains("FastBreak", case=False, na=False)]
        if len(sh):
            per = {c.pt(t): (int((fb["team_name"] == t).sum()), float(fb.loc[fb["team_name"] == t, "xg"].sum())) for t in c.teams}
            out.append("**Sinal mais próximo (mapa de chutes): finalizações em contra-ataque CEDIDAS** — " + " · ".join(
                f"{c.pt(c.other(t))} cedeu {per[c.pt(t)][0]} (xG {per[c.pt(t)][1]:.2f})" for t in c.teams) + ".")
    except Exception:
        pass
    if c.has_events and "is_pass_through_ball" in c.df:
        tb = c.df[c.df["is_pass_through_ball"].fillna(False).astype(bool)].groupby("team_name").size()
        out.append("**Passes em profundidade tentados:** " + " · ".join(f"{c.pt(k)} {v}" for k, v in tb.items()) + ".")
    r = D.player_table_box(c.box) if not c.has_events else D.player_table_events(c.df)
    if not r.empty and "interceptions" in r:
        top = r.dropna(subset=["interceptions"]).sort_values("interceptions", ascending=False).head(3)
        if len(top):
            out.append("**Quem mais cortou passes (interceptações, proxy de leitura):** " + "; ".join(
                f"{x.player} ({c.pt(x.team)}) {D._n(x.interceptions)}" for x in top.itertuples()) + ".")
    return "\n\n".join(out) + "\n\n_Proxies, não medida direta: a linha defensiva só é medida com tracking._"


def _big_chances(q, c: Ctx):
    if not _has(q, r"chances? clara", r"grandes? chances?", r"chance claras?", r"desperdic", r"perdeu .*chance"):
        return None
    out = []
    bcm = [f for f in c.facts if f.key == "big_chances_missed" and not f.player]
    if bcm:
        out.append("**Grandes chances perdidas (por time):** " + " · ".join(f"{f.team} {D._n(f.value)}" for f in bcm) + ".")
    r = D.player_table_box(c.box) if not c.has_events else D.player_table_events(c.df)
    if not r.empty and {"xg", "goals"} <= set(r.columns):
        r = r.assign(_miss=pd.to_numeric(r["xg"], errors="coerce") - pd.to_numeric(r["goals"], errors="coerce").fillna(0))
        top = r.dropna(subset=["_miss"]).sort_values("_miss", ascending=False)
        top = top[top["_miss"] > 0.1].head(5)
        if len(top):
            out.append("A fonte não diz QUEM perdeu cada grande chance. O sinal mais próximo é **xG sem gol** (chances que "
                       "valiam gol e não entraram):\n\n" + "\n".join(
                           f"{i}. {x.player} ({c.pt(x.team)}) — xG {D._n(x.xg)}, {D._n(x.goals or 0)} gol(s)"
                           for i, x in enumerate(top.itertuples(), 1)))
    return "\n\n".join(out) if out else "Não tenho grandes chances nem xG por jogador neste jogo."


def _identity(q, c: Ctx):
    """Rodada 22: modelo de jogo do time (identidade tática) — vários jogos, não só esta partida."""
    if not _has(q, r"como (o |a )?\w+ joga", r"modelo de jogo", r"estilo de jogo", r"identidade tatica", r"pressiona alto",
                r"pressao alta", r"\bppda\b", r"sai jogando", r"saida de bola", r"bloco baixo", r"bloco alto",
                r"altura do bloco", r"linha de 3", r"sai com 3", r"contra.?ataque", r"transic", r"como (o |a )?\w+ ataca",
                r"como (o |a )?\w+ defende", r"formacao (com|sem) bola", r"treinador", r"tecnico"):
        return None
    team = c.named_team(q) or c.focus
    if not team:
        return None
    from src.analytics import tactical_identity as TI

    try:
        ident = TI.identity(c.db, [team], 20)
    except Exception:
        return None
    lines = ident.get("resumo") or []
    plan = TI.opposition_plan(ident)
    rec = TI.recruitment_needs(ident)
    md = f"**Modelo de jogo de {c.pt(team)}** (vários jogos, não só esta partida):\n\n" + "\n".join(f"- {x}" for x in lines)
    if plan and _has(q, r"explorar", r"enfrentar", r"contra", r"vencer", r"ganhar", r"neutraliz"):
        md += "\n\n**Como enfrentar:**\n" + "\n".join(f"- {x['fase']}: {x['acao']} ({x['base']})" for x in plan[:4])
    if rec and _has(q, r"contrat", r"refor", r"precisa"):
        md += "\n\n**O modelo pede:**\n" + "\n".join(f"- {x['funcao']} — {x['porque']}" for x in rec)
    st_ = ident.get("estatisticas") or {}
    md += ("\n\n_Fonte: " + (st_.get("metodo") if st_.get("jogos") else "sem estatísticas por jogo deste time")
           + ("; lances com coordenadas para desenho por fase, PPDA real e transições" if (ident.get("lances") or {}).get("jogos") else
              "; sem jogos com lances deste time — desenho por fase e altura do bloco não medidos") + "._")
    return md


INTENTS = [_next_match, _absences, _best_player, _substitution, _identity, _depth, _big_chances, _strength_weakness]


def route(question: str, meta: Dict[str, Any], df, box, focus, db, pt=lambda x: x) -> Optional[Dict[str, Any]]:
    c = Ctx(meta, df, box, focus, db, pt)
    parts = split_questions(question)
    answers = _answer_parts(parts, meta, df, box, c, pt)
    if len(parts) > 1 and (answers is None or any(a[2] is None for a in answers)):
        answers = _answer_parts([question], meta, df, box, c, pt)   # "…? em qual momento?" é UMA pergunta
    if not answers or answers[0][1] is None:
        return None
    if len(answers) == 1:
        return {"markdown": answers[0][1], "intent": answers[0][2]}
    return {"markdown": "\n\n---\n\n".join(f"**{p.strip().capitalize()}?**\n\n{m}" for p, m, _ in answers),
            "intent": "+".join(str(i) for _, _, i in answers)}


def _answer_parts(parts, meta, df, box, c, pt):
    answers = []
    for part in parts:
        q = " " + re.sub(r"[^a-z0-9 ]", " ", _fold(part)) + " "
        md, intent = None, None
        for fn in INTENTS:
            md = fn(q, c)
            if md:
                intent = fn.__name__.strip("_")
                break
        if md is None:
            d = D.answer(part, meta, df, box, pt=pt, team_hint=c.named_team(part))
            if d is not None:
                md, intent = d["markdown"], f"numero:{d['key']}"
        answers.append((part, md, intent))
    return answers


# ------------------------------------------------------------------ leitura do jogo sem lances (Padrões e histórico)
def momentum_phases(extra: Dict[str, Any], team: str, block: int = 15) -> List[Dict[str, Any]]:
    """Média do momentum da FotMob por bloco de 15 min, com o sinal do time pedido (positivo = ele por cima)."""
    mom, times = (extra or {}).get("momentum") or [], (extra or {}).get("times") or []
    if not mom or not times:
        return []
    sign = 1 if _fold(times[0]) == _fold(team) else -1
    m = pd.DataFrame(mom, columns=["min", "v"]).astype(float)
    m["v"] *= sign
    out = []
    for a in range(0, int(m["min"].max()) + 1, block):
        part = m[(m["min"] >= a) & (m["min"] < a + block)]
        if len(part) < 3:
            continue
        v = float(part["v"].mean())
        out.append({"bloco": f"{a}'–{a + block}'", "media": round(v, 1),
                    "leitura": "por cima" if v > 15 else ("sob pressão" if v < -15 else "equilibrado")})
    return out


def match_reading(meta, df, box, team, db, pt=lambda x: x) -> Dict[str, Any]:
    """Tudo o que a IA do laboratório diz de um jogo para um time, em blocos prontos para a tela."""
    c = Ctx(meta, df, box, team, db, pt)
    team = c.focus
    rival = next((t for t in c.teams if t != team), "adversário")
    blocks = []
    for title, q in (("💪 Ponto forte", f"qual o ponto forte do {team}"),
                     ("⚠️ Ponto de maior atenção", f"qual o ponto de maior atenção do {team}"),
                     ("🎯 Como explorar o rival", f"como explorar o {rival}"),
                     ("🔄 Substituições", f"voce sugere alguma substituição para o {team}?"),
                     ("⭐ Quem jogou melhor", "quem jogou melhor")):
        try:
            r = route(q, meta, df, box, team, db, pt)
        except Exception:
            r = None
        if r and r.get("markdown"):
            blocks.append({"titulo": title, "markdown": r["markdown"], "intencao": r.get("intent")})
    return {"time": team, "blocos": blocks, "fases": momentum_phases(c.extra, team)}
