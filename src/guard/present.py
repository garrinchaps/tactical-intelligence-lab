"""
Apresentação verificada: cada número da resposta é conferido e classificado pela origem.
Na tela o texto fica limpo; a classificação vai para o painel "Conferência dos números".

    [EXATO]       o valor está nas evidências da partida;
    [DERIVADO]    recalculado a partir de valores das evidências (ou constante metodológica);
    [SEM ORIGEM]  nada nas evidências explica o número → a frase / linha de tabela que o contém
                  NÃO é exibida; uma nota informa quantas foram ocultadas.

Anos (1870–2100 sem unidade) não são métricas e ficam sem etiqueta.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

TAGS = {"EXATO": "[EXATO]", "DERIVADO": "[DERIVADO]", "CONSTANTE": "[DERIVADO]", "NÃO RASTREÁVEL": "[SEM ORIGEM]"}
_UNIT = re.compile(r"^(?:\s?(?:pp|p\.p\.|%)|'|’|\s?(?:xG|xT)\b)", re.IGNORECASE)
_SENT = re.compile(r"[^.!?;]*(?:[.!?;](?=\s|$)|$)")
LEGEND = "_Origem dos números: [EXATO] = está nos dados · [DERIVADO] = calculado a partir deles._"


def _is_year(item: Dict[str, Any], text: str) -> bool:
    m = item["mention"]
    return (m.is_integer and 1870 <= m.value <= 2100 and len(m.raw) == 4 and not m.unit
            and item["contexto"] != "contagem")


def _segments(text: str) -> List[Tuple[int, int, bool]]:
    """(início, fim, é_linha_de_tabela) — linhas de tabela inteiras; demais linhas quebradas em frases."""
    segs: List[Tuple[int, int, bool]] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\n")
        if body.lstrip().startswith("|"):
            segs.append((pos, pos + len(body), True))
        else:
            for m in _SENT.finditer(body):
                if m.end() > m.start():
                    segs.append((pos + m.start(), pos + m.end(), False))
        pos += len(line)
    return segs


def tag_numbers(text: str, evidence: Dict[str, Any], show_tags: bool = True) -> Tuple[str, Dict[str, Any]]:
    """Devolve (texto sem trechos SEM ORIGEM — com etiquetas se show_tags —, resumo com a conferência)."""
    from src.reports.report_builder import NumericHallucinationGuard as G

    if not text or not evidence:
        return text, {"exato": 0, "derivado": 0, "sem_origem": 0, "ocultadas": 0}
    items = [i for i in G.classify_numbers(text, evidence) if not _is_year(i, text)]
    segs = _segments(text)
    bad = [i for i in items if i["classe"] == "NÃO RASTREÁVEL"]
    drop = set()
    for b in bad:
        for k, (s, e, _) in enumerate(segs):
            if s <= b["start"] < e:
                drop.add(k)
    # monta o texto: pula segmentos descartados e insere a etiqueta depois do número (+ unidade / negrito)
    inserts: Dict[int, str] = {}
    for i in items:
        if i["classe"] == "NÃO RASTREÁVEL" or not show_tags:
            continue
        end = i["end"]
        u = _UNIT.match(text[end:])
        if u:
            end += u.end()
        while text[end:end + 2] == "**":
            end += 2
        inserts[end] = f" {TAGS.get(i['classe'], '[DERIVADO]')}"
    keep = [True] * len(text)
    for k in drop:
        s, e, is_row = segs[k]
        if is_row and text[e:e + 1] == "\n":            # some com a linha da tabela inteira
            e += 1
        for x in range(s, e):
            keep[x] = False
    out: List[str] = []
    for x in range(len(text) + 1):
        if x in inserts and x > 0 and keep[x - 1]:
            out.append(inserts[x])
        if x < len(text) and keep[x]:
            out.append(text[x])
    res = "".join(out)
    res = re.sub(r"[ \t]+\n", "\n", res)
    res = re.sub(r"\n{3,}", "\n\n", res).strip()
    n = {"exato": sum(i["classe"] == "EXATO" for i in items),
         "derivado": sum(i["classe"] in ("DERIVADO", "CONSTANTE") for i in items),
         "sem_origem": len(bad), "ocultadas": len(drop),
         "linhas": [{"número": i["numero"], "origem": TAGS.get(i["classe"], "[DERIVADO]").strip("[]"),
                     "como foi conferido": i["explicacao"]} for i in items]}
    if show_tags:
        if drop:
            res += (f"\n\n_🔒 {len(drop)} trecho(s) com número sem origem nos dados desta partida foram ocultados "
                    "pelo verificador._")
        if n["exato"] or n["derivado"]:
            res += f"\n\n{LEGEND}"
    return res, n


def present(res: Dict[str, Any], show_tags: bool = False) -> Dict[str, Any]:
    """
    Confere os números da resposta: trechos SEM ORIGEM saem do texto; o resultado da conferência fica em
    `number_tags` (painel "Conferência dos números"). Com show_tags=True as etiquetas aparecem no texto.
    """
    if not res or res.get("report_raw") is not None:
        return res
    raw = res.get("report_markdown") or ""
    try:
        tagged, n = tag_numbers(raw, res.get("evidence") or {}, show_tags=show_tags)
    except Exception:                      # a apresentação nunca derruba a resposta
        return res
    try:                                   # seleções em português na tela (Brazil → Brasil)
        from src.ui.names import pt_text

        ev = res.get("evidence") or {}
        md = ev.get("metadata") or {}
        teams = [md.get("target_team"), md.get("opponent_team"), md.get("home_team_name"), md.get("away_team_name")]
        tagged = pt_text(tagged, [t for t in teams if t])
    except Exception:
        pass
    res["report_raw"], res["report_markdown"], res["number_tags"] = raw, tagged, n
    return res
