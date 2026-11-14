"""Coletor do Simonetti Stats com respostas simuladas (sem rede): robots, descoberta de arquivos, parsing, reserva HTML."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.data_hub.sources.simonetti import BASE, BlockedByServer, SimonettiCollector, player_team_columns
from src.data_lake.lake import Lake

HOME = b"""<html><head><script src="/assets/app.123.js"></script></head><body><div id="root"></div>
<a href="/guias">Guias</a></body></html>"""
APP_JS = b"""const a=fetch("/data/jogadores.json");const b="/data/times.json";const m="/manifest.json";"""
PLAYERS = [{"jogador": "Arrascaeta", "time": "Flamengo", "posicao": "Meia", "xg": 7.1, "pressoes": 210},
           {"jogador": "Estêvão", "time": "Palmeiras", "posicao": "Ponta", "xg": 6.4, "pressoes": 180}]
TEAMS = {"Flamengo": {"xg": 60.1, "ppda": 8.2}, "Palmeiras": {"xg": 55.0, "ppda": 9.1}, "Bahia": {"xg": 40.2, "ppda": 10.0},
         "Cruzeiro": {"xg": 45.0, "ppda": 9.6}, "Botafogo": {"xg": 47.3, "ppda": 9.0}, "Mirassol": {"xg": 39.9, "ppda": 11.2}}


def fake_site(robots=b"User-agent: *\nAllow: /\n", blocked=False, home=HOME):
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return 200, robots, "text/plain"
        if blocked:
            return 429, b"", "text/html"
        pages = {f"{BASE}/": (home, "text/html"), f"{BASE}/assets/app.123.js": (APP_JS, "application/javascript"),
                 f"{BASE}/data/jogadores.json": (json.dumps(PLAYERS).encode(), "application/json"),
                 f"{BASE}/data/times.json": (json.dumps(TEAMS).encode(), "application/json"),
                 f"{BASE}/guias": (b"<table><tr><th>Indicador</th><th>Definicao</th></tr><tr><td>xG</td><td>gols esperados</td></tr></table>",
                                   "text/html")}
        body, ctype = pages.get(url, (b"", "text/html"))
        return (200 if url in pages else 404), body, ctype
    return fetch, calls


def test_discovers_and_loads_data_files(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMONETTI_DATA_URLS", raising=False)
    fetch, calls = fake_site()
    c = SimonettiCollector(delay_s=0, cache_dir=tmp_path / "c", fetch=fetch)
    assert c.discover_data_urls() == [f"{BASE}/data/jogadores.json", f"{BASE}/data/times.json"]   # manifest ignorado
    lake = Lake(root=tmp_path / "lake", sqlite_path=None)
    out = c.sync(lake)
    assert out["arquivos"] == 2 and out["linhas"] == 8
    j = lake.read("sm_jogadores")
    assert set(j["jogador"]) == {"Arrascaeta", "Estêvão"} and (j["fonte"] == "Simonetti Stats").all()
    t = lake.read("sm_times")
    assert len(t) == 6 and "ppda" in t.columns
    assert player_team_columns(j) == ("jogador", "time")


def test_respects_robots_txt(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMONETTI_DATA_URLS", raising=False)
    fetch, calls = fake_site(robots=b"User-agent: *\nDisallow: /\n")
    c = SimonettiCollector(delay_s=0, cache_dir=tmp_path / "c", fetch=fetch)
    with pytest.raises(PermissionError):
        c.get(f"{BASE}/data/jogadores.json")
    assert calls == [f"{BASE}/robots.txt"]                    # nada além do robots.txt foi pedido


def test_stops_when_server_blocks(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMONETTI_DATA_URLS", raising=False)
    fetch, _ = fake_site(blocked=True)
    with pytest.raises(BlockedByServer):
        SimonettiCollector(delay_s=0, cache_dir=tmp_path / "c", fetch=fetch).sync(Lake(root=tmp_path / "l", sqlite_path=None))


def test_html_fallback_and_dedup(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMONETTI_DATA_URLS", raising=False)
    fetch, _ = fake_site(home=b"<html><body><a href='/guias'>g</a></body></html>")
    lake = Lake(root=tmp_path / "lake", sqlite_path=None)
    c = SimonettiCollector(delay_s=0, cache_dir=tmp_path / "c", fetch=fetch)
    assert c.sync(lake)["linhas_html"] == 1
    SimonettiCollector(delay_s=0, cache_dir=tmp_path / "c", fetch=fetch).sync(lake)
    assert len(lake.read("sm_tabelas_html")) == 1             # mesma linha não duplica


def test_env_urls_and_xlsx(tmp_path, monkeypatch):
    import io

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(PLAYERS).to_excel(w, sheet_name="Jogadores", index=False)
    monkeypatch.setenv("SIMONETTI_DATA_URLS", f"{BASE}/base.xlsx")
    fetch, _ = fake_site()

    def f2(url):
        return (200, buf.getvalue(), "application/vnd.ms-excel") if url.endswith("base.xlsx") else fetch(url)
    lake = Lake(root=tmp_path / "lake", sqlite_path=None)
    out = SimonettiCollector(delay_s=0, cache_dir=tmp_path / "c", fetch=f2).sync(lake)
    assert out["tabelas"] == 1 and len(lake.read("sm_base_jogadores")) == 2
