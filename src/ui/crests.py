"""
Escudos de clubes e bandeiras de seleções.

Ordem: seleção → bandeira (flagcdn.com, pelo código ISO); clube com id na API-Football → escudo do CDN da
API-Football; clube com id no Transfermarkt → escudo do CDN do Transfermarkt; senão → escudo gerado (SVG com as
iniciais e duas cores derivadas do nome), que também é usado se a imagem remota não carregar.
As imagens são carregadas pelo navegador (nada é baixado pelo app).
"""

from __future__ import annotations

import base64
import hashlib
import html
from functools import lru_cache
from typing import Dict, Optional

from src.data_lake.ids import norm, team_core

ISO: Dict[str, str] = {
    "brazil": "br", "argentina": "ar", "france": "fr", "england": "gb-eng", "germany": "de", "spain": "es", "italy": "it",
    "portugal": "pt", "netherlands": "nl", "belgium": "be", "croatia": "hr", "uruguay": "uy", "colombia": "co",
    "chile": "cl", "paraguay": "py", "peru": "pe", "ecuador": "ec", "venezuela": "ve", "bolivia": "bo", "mexico": "mx",
    "united states": "us", "usa": "us", "canada": "ca", "costa rica": "cr", "panama": "pa", "honduras": "hn",
    "jamaica": "jm", "morocco": "ma", "senegal": "sn", "tunisia": "tn", "cameroon": "cm", "ghana": "gh", "nigeria": "ng",
    "egypt": "eg", "algeria": "dz", "ivory coast": "ci", "cote d'ivoire": "ci", "south africa": "za", "mali": "ml",
    "japan": "jp", "south korea": "kr", "korea republic": "kr", "australia": "au", "iran": "ir", "saudi arabia": "sa",
    "qatar": "qa", "china pr": "cn", "china": "cn", "switzerland": "ch", "denmark": "dk", "sweden": "se", "norway": "no",
    "poland": "pl", "serbia": "rs", "wales": "gb-wls", "scotland": "gb-sct", "northern ireland": "gb-nir",
    "republic of ireland": "ie", "ireland": "ie", "austria": "at", "czech republic": "cz", "czechia": "cz",
    "hungary": "hu", "slovakia": "sk", "slovenia": "si", "romania": "ro", "ukraine": "ua", "russia": "ru", "turkey": "tr",
    "turkiye": "tr", "greece": "gr", "georgia": "ge", "albania": "al", "iceland": "is", "finland": "fi", "bulgaria": "bg",
    "bosnia and herzegovina": "ba", "north macedonia": "mk", "montenegro": "me", "israel": "il", "new zealand": "nz",
    "soviet union": "ru", "west germany": "de", "east germany": "de", "yugoslavia": "rs", "czechoslovakia": "cz",
}
NATION_HINT = ("women", "u17", "u20", "u21", "u23", "olympic")


def nation_code(name: str) -> Optional[str]:
    n = norm(name)
    for h in NATION_HINT:
        n = n.replace(f" {h}", "")
    return ISO.get(n.strip())


def _colors(name: str):
    h = hashlib.md5(norm(name).encode()).digest()
    palette = ["#3B82F6", "#EF4444", "#22D3EE", "#A78BFA", "#F59E0B", "#10B981", "#F472B6", "#64748B"]
    a, b = palette[h[0] % len(palette)], palette[h[1] % len(palette)]
    return a, (b if b != a else "#0F172A")


@lru_cache(maxsize=4096)
def monogram(name: str) -> str:
    """Escudo gerado: SVG (data URI) com as iniciais do clube."""
    words = [w for w in team_core(name).split() if w] or ["?"]
    ini = (words[0][:1] + (words[1][:1] if len(words) > 1 else words[0][1:2])).upper()
    a, b = _colors(name)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 72"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
           f'<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>'
           f'<path d="M32 2 L60 12 V36 C60 54 46 65 32 70 C18 65 4 54 4 36 V12 Z" fill="url(#g)" stroke="#fff" stroke-opacity=".35" stroke-width="2"/>'
           f'<text x="32" y="44" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#fff" text-anchor="middle">{html.escape(ini)}</text></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


@lru_cache(maxsize=1)
def _id_index() -> Dict[str, Dict[str, str]]:
    """team_core → {api_football_id, transfermarkt_id} a partir da base unificada (se existir)."""
    try:
        from src.data_lake.lake import Lake

        lake = Lake(sqlite_path=None)
        if not lake.exists("team_ids"):
            return {}
        t = lake.read("team_ids")
        out: Dict[str, Dict[str, str]] = {}
        keys = {}
        for r in t.itertuples():
            keys.setdefault(r.team_key, {})
            if r.fonte in ("api_football", "transfermarkt") and str(r.id_fonte):
                keys[r.team_key].setdefault(r.fonte, str(r.id_fonte).split(";")[0])
        for r in t.itertuples():
            out[team_core(r.nome)] = keys.get(r.team_key, {})
        return out
    except Exception:
        return {}


def crest_url(name: str) -> str:
    code = nation_code(name)
    if code:
        return f"https://flagcdn.com/w80/{code}.png"
    ids = _id_index().get(team_core(name), {})
    if ids.get("api_football"):
        return f"https://media.api-sports.io/football/teams/{ids['api_football']}.png"
    if ids.get("transfermarkt"):
        return f"https://tmssl.akamaized.net/images/wappen/head/{ids['transfermarkt']}.png"
    return monogram(name)


def crest_img(name: str, size: str = "") -> str:
    """<img> com o escudo; se a imagem remota falhar, troca pelo escudo gerado."""
    url, fb = crest_url(name), monogram(name)
    cls = f"til-crest {size}".strip()
    return (f'<img class="{cls}" src="{html.escape(url)}" alt="{html.escape(str(name))}" title="{html.escape(str(name))}" '
            f'onerror="this.onerror=null;this.src=\'{fb}\'">')
