"""
Leitor de YAML mínimo, sem dependências — usado quando o PyYAML não está instalado
(ex.: Python muito novo sem pacote pronto para Windows).

Cobre o subconjunto usado em config/competitions*.yaml: comentários (#), mapas "chave: valor",
listas com "- ", listas de mapas, listas em linha [a, b], textos entre aspas, números e null/true/false.
"""

from __future__ import annotations

import re
from typing import Any, List, Tuple


class MiniYAMLError(ValueError):
    pass


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _split_inline(body: str) -> List[str]:
    parts, cur, quote = [], [], None
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch == ",":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts]


def scalar(s: str) -> Any:
    s = s.strip()
    if s == "" or s in ("~", "null", "Null", "NULL"):
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1].replace("''", "'") if s[0] == "'" else s[1:-1].replace('\\"', '"')
    if s.startswith("[") and s.endswith("]"):
        return [scalar(p) for p in _split_inline(s[1:-1])]
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if re.fullmatch(r"[-+]?\d+", s):
        return int(s)
    if re.fullmatch(r"[-+]?\d*\.\d+([eE][-+]?\d+)?", s):
        return float(s)
    return s


def _key_value(text: str, lineno: int) -> Tuple[str, str]:
    m = re.match(r"^(\"[^\"]*\"|'[^']*'|[^:]+?)\s*:(?:\s+(.*)|$)", text)
    if not m:
        raise MiniYAMLError(f"linha {lineno}: esperado 'chave: valor', encontrado '{text}'")
    return str(scalar(m.group(1))), (m.group(2) or "")


def safe_load(text: str) -> Any:
    lines = []
    for n, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise MiniYAMLError(f"linha {n}: use espaços, não tabulação, na indentação")
        clean = _strip_comment(raw)
        if clean.strip() and clean.strip() != "---":
            lines.append((len(clean) - len(clean.lstrip(" ")), clean.strip(), n))
    if not lines:
        return None
    value, i = _block(lines, 0, lines[0][0])
    if i != len(lines):
        raise MiniYAMLError(f"linha {lines[i][2]}: indentação inesperada")
    return value


def _block(lines, i, indent):
    if lines[i][1].startswith("- ") or lines[i][1] == "-":
        return _list(lines, i, indent)
    return _map(lines, i, indent)


def _value_after(lines, i, indent, rest, lineno):
    """Valor de 'chave:' — escalar na mesma linha ou bloco indentado nas linhas seguintes."""
    if rest.strip():
        return scalar(rest), i + 1
    j = i + 1
    if j < len(lines) and (lines[j][0] > indent or (lines[j][0] == indent and lines[j][1].startswith("-"))):
        return _block(lines, j, lines[j][0])
    return None, j


def _map(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        _, text, n = lines[i]
        k, rest = _key_value(text, n)
        out[k], i = _value_after(lines, i, indent, rest, n)
    return out, i


def _list(lines, i, indent):
    out = []
    while i < len(lines) and lines[i][0] == indent and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
        _, text, n = lines[i]
        body = text[1:].strip()
        if not body:
            v, i = _block(lines, i + 1, lines[i + 1][0]) if i + 1 < len(lines) and lines[i + 1][0] > indent else (None, i + 1)
            out.append(v)
            continue
        is_map = re.match(r"^(\"[^\"]*\"|'[^']*'|[^\[\]{}\"':][^:]*?)\s*:(\s|$)", body)
        if not is_map:
            out.append(scalar(body))
            i += 1
            continue
        # item que é um mapa: a 1ª chave está na linha do "-", as demais alinhadas com ela
        item_indent = indent + (len(text) - len(body))
        k, rest = _key_value(body, n)
        item = {}
        item[k], i = _value_after(lines, i, item_indent, rest, n)
        if i < len(lines) and lines[i][0] == item_indent and not lines[i][1].startswith("- "):
            more, i = _map(lines, i, item_indent)
            item.update(more)
        out.append(item)
    return out, i
