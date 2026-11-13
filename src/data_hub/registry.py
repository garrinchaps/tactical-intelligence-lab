"""
Registro central de fontes, níveis de dado e faixas de ID.

Cada partida no catálogo tem:
* `data_source`  — de onde veio (statsbomb, wyscout, api_football, football_data, espn, simulated, upload)
* `data_level`   — o que temos de verdade sobre ela (ver DataLevel)
* `match_id`     — ID interno único, derivado do ID da fonte por uma faixa (namespace),
                   para que IDs de fontes diferentes nunca colidam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


class DataLevel:
    EVENTS = "EVENTS"          # eventos granulares com coordenadas (StatsBomb, Wyscout)
    BOXSCORE = "BOXSCORE"      # estatísticas agregadas, escalações e linha do tempo reais
    RESULT = "RESULT"          # apenas placar/agenda reais
    SIMULATED = "SIMULATED"    # gerado por modelo probabilístico
    UPLOAD = "UPLOAD"          # arquivo enviado pelo usuário

    ALL = (EVENTS, BOXSCORE, RESULT, SIMULATED, UPLOAD)


BADGES: Dict[str, str] = {
    DataLevel.EVENTS: "✅ [DADOS OFICIAIS REAIS — EVENTOS]",
    DataLevel.BOXSCORE: "📊 [DADOS REAIS — BOXSCORE]",
    DataLevel.RESULT: "📄 [DADOS REAIS — SOMENTE PLACAR]",
    DataLevel.SIMULATED: "⚠️ [DADOS SIMULADOS / MODELAGEM PROBABILÍSTICA]",
    DataLevel.UPLOAD: "📁 [DADOS ENVIADOS PELO USUÁRIO]",
}

LEVEL_DESCRIPTIONS: Dict[str, str] = {
    DataLevel.EVENTS: (
        "Eventos granulares oficiais (passes, finalizações, duelos) com coordenadas em campo. "
        "Todas as análises espaciais estão disponíveis."
    ),
    DataLevel.BOXSCORE: (
        "Estatísticas agregadas reais da partida (posse, finalizações, passes...), escalações e "
        "linha do tempo de gols, cartões e substituições. A fonte não traz posições em campo, "
        "então redes de passes, xT e mapas espaciais ficam indisponíveis."
    ),
    DataLevel.RESULT: (
        "Somente placar e informações da partida. Sem estatísticas detalhadas na fonte."
    ),
    DataLevel.SIMULATED: (
        "Eventos GERADOS por modelo probabilístico a partir de perfis táticos. "
        "Não representam um jogo que realmente aconteceu."
    ),
    DataLevel.UPLOAD: "Eventos carregados a partir de um arquivo enviado pelo usuário.",
}

COLORS: Dict[str, str] = {
    DataLevel.EVENTS: "#00FF7F",
    DataLevel.BOXSCORE: "#38BDF8",
    DataLevel.RESULT: "#A78BFA",
    DataLevel.SIMULATED: "#F59E0B",
    DataLevel.UPLOAD: "#94A3B8",
}


@dataclass(frozen=True)
class SourceInfo:
    key: str
    label: str
    level: str
    id_offset: int
    official: bool
    license_note: str
    url: str
    needs_key: Optional[str] = None


# Faixas de ID internas (StatsBomb mantém o ID original, < 10 milhões)
SOURCES: Dict[str, SourceInfo] = {
    "statsbomb": SourceInfo(
        "statsbomb", "StatsBomb Open Data", DataLevel.EVENTS, 0, True,
        "Uso livre com crédito à StatsBomb e uso do logo (Media Pack).",
        "https://github.com/statsbomb/open-data",
    ),
    "wyscout": SourceInfo(
        "wyscout", "Wyscout Public Dataset (Pappalardo et al., 2019)", DataLevel.EVENTS,
        10_000_000, True,
        "CC BY 4.0 — citar Pappalardo et al., Scientific Data 6:236 (2019).",
        "https://github.com/koenvo/wyscout-soccer-match-event-dataset",
    ),
    "api_football": SourceInfo(
        "api_football", "API-Football (api-sports.io)", DataLevel.BOXSCORE,
        100_000_000, True,
        "API oficial com chave. Plano gratuito: 100 requisições/dia; temporada atual pode exigir plano pago.",
        "https://www.api-football.com", needs_key="API_FOOTBALL_KEY",
    ),
    "football_data": SourceInfo(
        "football_data", "football-data.org", DataLevel.RESULT,
        300_000_000, True,
        "API oficial com token gratuito (12 competições, 10 chamadas/min).",
        "https://www.football-data.org", needs_key="FOOTBALL_DATA_TOKEN",
    ),
    "espn": SourceInfo(
        "espn", "ESPN (feed JSON público, não oficial)", DataLevel.BOXSCORE,
        500_000_000, False,
        "Endpoint público sem documentação oficial. Desativado por padrão; uso pessoal/acadêmico, "
        "com baixa frequência. Verifique os termos de uso da ESPN antes de ativar.",
        "https://www.espn.com.br/futebol/", needs_key="ENABLE_ESPN_PUBLIC_FEED",
    ),
}

SIMULATED_ID_RANGES = ((880_000, 889_999), (900_000, 989_999))
UPLOAD_ID = 999_001


def to_internal_id(source: str, source_id: int) -> int:
    return SOURCES[source].id_offset + int(source_id)


def source_from_internal_id(match_id: int) -> str:
    mid = int(match_id)
    for lo, hi in SIMULATED_ID_RANGES:
        if lo <= mid <= hi:
            return "simulated"
    if mid == UPLOAD_ID:
        return "upload"
    for key in ("espn", "football_data", "api_football", "wyscout"):
        off = SOURCES[key].id_offset
        if mid >= off:
            return key
    return "statsbomb"


def to_source_id(match_id: int) -> int:
    src = source_from_internal_id(match_id)
    if src in SOURCES:
        return int(match_id) - SOURCES[src].id_offset
    return int(match_id)


def badge_for(level: Optional[str]) -> str:
    return BADGES.get(level or "", BADGES[DataLevel.EVENTS])
