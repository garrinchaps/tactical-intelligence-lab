"""
Rodada 25 — base própria de leitura tática por MECANISMOS, aplicável a qualquer jogo/time com estatísticas por jogo
(FotMob/ESPN). Não é uma lista de 100 dicas prontas: cada mecanismo só aparece quando os NÚMEROS dos dois times o
sustentam, e o texto é montado com esses números.

Ideia central (pedido do usuário): cruzar evidências, não buscar o pior número isolado.
  * cada mecanismo tem condições; cada condição atendida é uma EVIDÊNCIA com o número e a referência;
  * 1 evidência forte = "claro"; 2+ evidências independentes = "escancarado";
  * confiança pela amostra (jogos de cada time);
  * no máximo 2 dicas do mesmo mecanismo na lista final (diversidade) — isso é feito em matchups._diverse;
  * espelho defensivo: o que o rival faz bem × onde nós cedemos vira "onde não deixar o jogo ir".

Mecanismos (todos com dados que existem em todas as partidas com estatísticas):
  transição · ataque posicional contra bloco baixo · jogo pelos lados com cruzamento · pressão na saída ·
  segunda bola · presença na área · chute de média distância · bola parada · ritmo/posse.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _rel(a: Optional[float], b: Optional[float]) -> Optional[float]:
    try:
        if a is None or b in (None, 0):
            return None
        return (float(a) - float(b)) / abs(float(b))
    except (TypeError, ValueError):
        return None


def _f(x: Any, nd: int = 1) -> str:
    try:
        return f"{float(x):.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def _level(n_ev: int, strength: float) -> Optional[str]:
    if n_ev >= 2 and strength >= .25:
        return "escancarado"
    if n_ev >= 1 and strength >= .12:
        return "claro"
    return None


def _conf(n_a: int, n_b: int) -> str:
    n = min(int(n_a or 0), int(n_b or 0))
    return "alta" if n >= 12 else "média" if n >= 6 else "baixa"


def mechanisms(me: str, rival: str, mine: Dict[str, Any], theirs: Dict[str, Any], ref: Dict[str, Any],
               attack: bool = True) -> List[Dict[str, Any]]:
    """attack=True: onde NÓS ganhamos o jogo (nosso perfil × fragilidade deles). False: espelho — onde ELES ganham
    (perfil deles × nossa fragilidade) = onde não deixar o jogo ir. `mine/theirs` = perfil de stats_identity."""
    A, D = (mine, theirs) if attack else (theirs, mine)          # A = quem ataca neste espelho, D = quem defende
    an, dn = (me, rival) if attack else (rival, me)
    pa, pd_ = A.get("perfil") or {}, D.get("perfil") or {}
    na, nd = A.get("jogos") or 0, D.get("jogos") or 0
    out: List[Dict[str, Any]] = []

    def add(mech: str, title: str, ev: List[str], strength: float, action: str, steps: List[str]):
        lvl = _level(len(ev), strength)
        if not lvl:
            return
        out.append({"tipo": "mecanismo", "dimensao": mech, "titulo": title, "nivel": lvl,
                    "evidencia": " · ".join(ev), "acao": ("FORÇAR: " if attack else "PROTEGER: ") + action,
                    "passos": steps, "score": round(100 * strength + 10 * len(ev), 1), "fuzzy": None,
                    "confianca": _conf(na, nd),
                    "base": f"{na} jogos de {an} e {nd} de {dn} com estatísticas"})

    # 1) transição: o defensor tem muita posse (deixa o campo aberto ao perder) e cede xG; o atacante é direto
    ev, st = [], 0.0
    r_pos = _rel(pd_.get("posse_pct"), ref.get("posse_pct"))
    if r_pos is not None and r_pos >= .08:
        ev.append(f"{dn} fica com a bola ({_f(pd_.get('posse_pct'), 0)}% × {_f(ref.get('posse_pct'), 0)}% das competições)")
        st += r_pos
    r_xgc = _rel(pd_.get("xg_contra"), ref.get("xg"))
    if r_xgc is not None and r_xgc >= .1:
        ev.append(f"{dn} cede xG {_f(pd_.get('xg_contra'), 2)} por jogo (média {_f(ref.get('xg'), 2)})")
        st += r_xgc / 2
    r_dir = _rel(pa.get("pct_bolas_longas"), ref.get("pct_bolas_longas"))
    if r_dir is not None and r_dir >= .1:
        ev.append(f"{an} joga direto ({_f(pa.get('pct_bolas_longas'), 0)}% de bolas longas)")
        st += r_dir / 2
    if ev and r_pos is not None and r_pos >= .08:
        add("transicao", "Transição rápida contra quem fica com a bola", ev, st,
            f"recuperar e acelerar — {dn} sai para o ataque com muita gente e deixa o campo aberto atrás",
            ["Momento: logo após a recuperação, nos primeiros 5–8 segundos, antes de a linha deles voltar.",
             "Primeira bola vertical ou em diagonal para o jogador mais aberto; não parar a jogada para organizar.",
             f"Atacar com 3 contra 2 e terminar a jogada antes de {dn} recompor o meio."])

    # 2) bloco baixo: o defensor abre mão da bola e marca atrás → ataque posicional, entrada da área, cutback
    ev, st = [], 0.0
    if r_pos is not None and r_pos <= -.08:
        ev.append(f"{dn} abre mão da bola ({_f(pd_.get('posse_pct'), 0)}% de posse)")
        st += -r_pos
    r_ppda = _rel(pd_.get("ppda_aprox"), ref.get("ppda_aprox"))
    if r_ppda is not None and r_ppda >= .12:
        ev.append(f"{dn} marca mais atrás (PPDA aproximado {_f(pd_.get('ppda_aprox'))} × {_f(ref.get('ppda_aprox'))})")
        st += r_ppda / 2
    r_fora = _rel(pd_.get("finalizacoes_contra_area"), None)
    if ev:
        add("bloco_baixo", "Ataque posicional contra bloco baixo", ev, st,
            f"paciência para mover o bloco de {dn} e atacar a entrada da área, sem cruzar por cruzar",
            ["Circular de um lado para o outro até o bloco deslizar; acelerar só quando o lado oposto abrir.",
             "Ocupar a entrada da área com um meia para o passe atrasado (cutback) e o chute de média distância.",
             "Laterais dando amplitude para esticar a linha de 4/5; tabelas curtas perto da área."])

    # 3) jogo pelos lados: o defensor cede cruzamentos; o atacante cruza muito
    ev, st = [], 0.0
    r_cc = _rel(pd_.get("cruzamentos_contra"), ref.get("cruzamentos"))
    if r_cc is not None and r_cc >= .12:
        ev.append(f"{dn} sofre {_f(pd_.get('cruzamentos_contra'))} cruzamentos por jogo (média {_f(ref.get('cruzamentos'))})")
        st += r_cc
    r_cr = _rel(pa.get("cruzamentos"), ref.get("cruzamentos"))
    if r_cr is not None and r_cr >= .1:
        ev.append(f"{an} cruza {_f(pa.get('cruzamentos'))} vezes por jogo")
        st += r_cr / 2
    if ev and (r_cc or 0) >= .12:
        add("cruzamento", "Jogo pelos lados com cruzamento", ev, st,
            f"levar a bola aos corredores — {dn} deixa cruzar mais que a média",
            ["Ponta e lateral do mesmo lado em dupla: um prende o marcador, o outro chega ao fundo.",
             "Cruzamento antecipado para o primeiro poste e rasteiro para a marca do pênalti; alguém no segundo poste.",
             "Volante na entrada da área para a sobra do cruzamento rebatido."])

    # 4) pressão na saída: o defensor sai jogando curto e o atacante pressiona alto
    ev, st = [], 0.0
    r_lb = _rel(pd_.get("pct_bolas_longas"), ref.get("pct_bolas_longas"))
    if r_lb is not None and r_lb <= -.12:
        ev.append(f"{dn} sai jogando curto ({_f(pd_.get('pct_bolas_longas'), 0)}% de bolas longas)")
        st += -r_lb
    r_ppda_a = _rel(pa.get("ppda_aprox"), ref.get("ppda_aprox"))
    if r_ppda_a is not None and r_ppda_a <= -.12:
        ev.append(f"{an} pressiona alto (PPDA aproximado {_f(pa.get('ppda_aprox'))})")
        st += -r_ppda_a / 2
    if len(ev) >= 1 and (r_lb or 0) <= -.12:
        add("pressao_saida", "Pressão na saída de bola", ev, st,
            f"pressionar a primeira construção de {dn} e roubar perto da área deles",
            ["Gatilho: passe do goleiro para o zagueiro ou passe para trás — o time inteiro sobe junto.",
             "Fechar o volante deles com o meia (sem ele, a saída curta morre) e orientar a bola para um lado.",
             "Recuperou: finalizar em poucos toques, a defesa deles ainda está aberta."])

    # 5) segunda bola: o defensor joga muito longo → disputa e sobra
    ev, st = [], 0.0
    if r_lb is not None and r_lb >= .15:
        ev.append(f"{dn} joga longo ({_f(pd_.get('pct_bolas_longas'), 0)}% de bolas longas)")
        st += r_lb
        add("segunda_bola", "Segunda bola", ev, st,
            ("ganhar as sobras das bolas longas deles e sair rápido" if attack else
             f"encurtar meio e defesa para as bolas longas de {an} não virarem segunda bola deles"),
            ["Linhas de meio e defesa próximas (menos de 25 m) quando eles forem lançar.",
             "Um jogador ataca a primeira bola; dois ficam ao redor da zona de queda.",
             "Ganhou a sobra: a primeira passada é para frente, eles estão desorganizados após o lançamento."])

    # 6) presença na área: o atacante toca muito na área / o defensor cede finalizações de dentro da área
    ev, st = [], 0.0
    r_ta = _rel(pa.get("toques_area"), ref.get("toques_area"))
    if r_ta is not None and r_ta >= .12:
        ev.append(f"{an} toca {_f(pa.get('toques_area'))} vezes por jogo na área rival (média {_f(ref.get('toques_area'))})")
        st += r_ta
    if pd_.get("finalizacoes_contra_area") and ref.get("toques_area"):
        try:
            if float(pd_["finalizacoes_contra_area"]) >= 9:
                ev.append(f"{dn} cede {_f(pd_['finalizacoes_contra_area'])} finalizações de dentro da área por jogo")
                st += .15
        except (TypeError, ValueError):
            pass
    if ev and (r_ta or 0) >= .12:
        add("area", "Presença na área", ev, st,
            ("encher a área: é onde nós somos fortes e onde eles cedem" if attack else
             f"proteger a área: {an} vive dentro dela"),
            ["Dois jogadores atacando a área em toda chegada pelo lado (primeiro e segundo poste).",
             "Passe rasteiro para dentro da área vale mais que o cruzamento alto contra zagueiros altos.",
             "Rebote: um jogador sempre acompanha a finalização."])

    # 7) bola parada
    ev, st = [], 0.0
    try:
        sp = float(pa.get("pct_xg_bola_parada")) if pa.get("pct_xg_bola_parada") is not None else None
    except (TypeError, ValueError):
        sp = None
    if sp is not None and sp >= 30:
        ev.append(f"{_f(sp, 0)}% do xG de {an} vem de bola parada")
        st += (sp - 25) / 60
        add("bola_parada", "Bola parada", ev, st,
            ("cavar escanteios e faltas laterais — é uma arma de verdade" if attack else
             f"evitar faltas laterais e escanteios desnecessários: {an} cria muito assim"),
            ["Escanteio: o melhor cabeceador atacando a zona onde eles mais perdem; bloqueio legal para liberá-lo.",
             "Falta lateral: cobrança fechada no primeiro poste ou curta para o cruzamento com a defesa desarrumada.",
             "Sempre deixar 2 jogadores na entrada da área para a sobra e o contra-ataque."])

    return out
