"""
API-Futebol (api-futebol.com.br) — futebol brasileiro: campeonatos, tabela de classificação, rodadas e partidas
(Brasileirão A/B, Copa do Brasil, estaduais). Chave em .env: API_FUTEBOL_KEY (o painel do site gera uma chave
de teste "test_..." gratuita e chaves "live_..." pagas).
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

BASE = "https://api.api-futebol.com.br/v1"
CACHE = Path("data/raw/api_futebol")
LICENSE = "API-Futebol — dados sob os termos do plano contratado"


def _d(s: Any) -> str:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(s)[:19], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


class ApiFutebolProvider:
    source = "api_futebol"

    def __init__(self, api_key: Optional[str] = None, min_interval_s: float = 1.0):
        self.key = (api_key if api_key is not None else os.getenv("API_FUTEBOL_KEY", "")).strip()
        self.min_interval_s = min_interval_s
        self._last = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.key) and "coloque" not in self.key.lower()

    def _get(self, path: str) -> Any:
        import requests

        wait = self.min_interval_s - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {self.key}"}, timeout=30)
        self._last = time.time()
        r.raise_for_status()
        return r.json()

    @staticmethod
    def standings_frame(tabela: List[Dict[str, Any]], campeonato: str, temporada: str) -> pd.DataFrame:
        rows = []
        for t in tabela or []:
            time_ = t.get("time") or {}
            rows.append({"campeonato": campeonato, "temporada": temporada, "posicao": t.get("posicao"),
                         "equipe": time_.get("nome_popular") or time_.get("nome"), "api_futebol_id": time_.get("time_id"),
                         "pontos": t.get("pontos"), "jogos": t.get("jogos"), "vitorias": t.get("vitorias"),
                         "empates": t.get("empates"), "derrotas": t.get("derrotas"), "gols_pro": t.get("gols_pro"),
                         "gols_contra": t.get("gols_contra"), "saldo": t.get("saldo_gols"),
                         "aproveitamento": t.get("aproveitamento"), "ultimos_jogos": "".join(t.get("ultimos_jogos") or [])})
        return pd.DataFrame(rows)

    @staticmethod
    def matches_frame(partidas: Any, campeonato: str) -> pd.DataFrame:
        """Aceita a lista de partidas ou o dicionário por fase/rodada devolvido pela API."""
        flat: List[Dict[str, Any]] = []

        def walk(o):
            if isinstance(o, dict):
                if "partida_id" in o:
                    flat.append(o)
                else:
                    for v in o.values():
                        walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(partidas)
        rows = []
        for p in flat:
            m, v = p.get("time_mandante") or {}, p.get("time_visitante") or {}
            rows.append({"api_futebol_id": p["partida_id"], "campeonato": campeonato, "rodada": p.get("rodada"),
                         "data": _d(p.get("data_realizacao_iso") or p.get("data_realizacao")),
                         "hora": p.get("hora_realizacao"), "status": p.get("status"),
                         "mandante": m.get("nome_popular"), "visitante": v.get("nome_popular"),
                         "gols_mandante": p.get("placar_mandante"), "gols_visitante": p.get("placar_visitante"),
                         "estadio": (p.get("estadio") or {}).get("nome_popular")})
        return pd.DataFrame(rows)

    def sync(self, lake, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        prov = dict(source="API-Futebol", connector="ApiFutebolProvider", license=LICENSE)
        tot = {"tabelas": 0, "partidas": 0}
        camps = self._get("/campeonatos")
        tabs, parts = [], []
        for c in camps if isinstance(camps, list) else []:
            cid, nome = c.get("campeonato_id"), c.get("nome_popular") or c.get("nome")
            temporada = str((c.get("edicao_atual") or {}).get("temporada", ""))
            try:
                tabs.append(self.standings_frame(self._get(f"/campeonatos/{cid}/tabela"), nome, temporada))
            except Exception as exc:
                say(f"  api-futebol {nome}: tabela indisponível ({exc})")
            try:
                parts.append(self.matches_frame(self._get(f"/campeonatos/{cid}/partidas"), nome))
            except Exception as exc:
                say(f"  api-futebol {nome}: partidas indisponíveis ({exc})")
        if tabs:
            t = pd.concat(tabs, ignore_index=True)
            lake.write("af_classificacao", t, **prov)
            tot["tabelas"] = int(t["campeonato"].nunique()) if not t.empty else 0
        if parts:
            p = pd.concat(parts, ignore_index=True)
            lake.upsert("af_partidas", p, ["api_futebol_id"], **prov)
            tot["partidas"] = len(p)
        tot["updated"] = tot["partidas"]
        return tot
