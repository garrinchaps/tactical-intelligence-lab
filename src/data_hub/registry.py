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
    # o que serve para análise: eventos ou estatísticas (só placar fica fora da interface por padrão)
    ANALYZABLE = (EVENTS, BOXSCORE, SIMULATED, UPLOAD)


BADGES: Dict[str, str] = {
    DataLevel.EVENTS: "✅ [DADOS OFICIAIS REAIS — EVENTOS]",
    DataLevel.BOXSCORE: "📊 [DADOS REAIS — ESTATÍSTICAS DA PARTIDA]",
    DataLevel.RESULT: "📄 [DADOS REAIS — SÓ PLACAR E GOLS]",
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
        "Placar e, quando a fonte traz, autores dos gols, cartões e escalações. Nenhuma base local tem "
        "estatísticas de equipe (chutes, posse, escanteios) para este jogo."
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
    connector: str = ""
    raw_tier: str = "OFFICIAL"   # tier dos valores ingeridos diretamente da fonte


# Faixas de ID internas (StatsBomb mantém o ID original, < 10 milhões)
SOURCES: Dict[str, SourceInfo] = {
    "statsbomb": SourceInfo(
        "statsbomb", "StatsBomb Open Data", DataLevel.EVENTS, 0, True,
        "Uso livre com crédito à StatsBomb e uso do logo (Media Pack).",
        "https://github.com/statsbomb/open-data",
        connector="StatsBombConnector", raw_tier="OFFICIAL",
    ),
    "wyscout": SourceInfo(
        "wyscout", "Wyscout Public Dataset (Pappalardo et al., 2019)", DataLevel.EVENTS,
        10_000_000, True,
        "CC BY 4.0 — citar Pappalardo et al., Scientific Data 6:236 (2019).",
        "https://github.com/koenvo/wyscout-soccer-match-event-dataset",
        connector="WyscoutConnector", raw_tier="OFFICIAL",
    ),
    "api_football": SourceInfo(
        "api_football", "API-Football (api-sports.io)", DataLevel.BOXSCORE,
        100_000_000, True,
        "API oficial com chave. Plano gratuito: 100 requisições/dia; temporada atual pode exigir plano pago.",
        "https://www.api-football.com", needs_key="API_FOOTBALL_KEY", connector="APIConnector[api-football]", raw_tier="OFFICIAL",
    ),
    "football_data": SourceInfo(
        "football_data", "football-data.org", DataLevel.RESULT,
        300_000_000, True,
        "API oficial com token gratuito (12 competições, 10 chamadas/min).",
        "https://www.football-data.org", needs_key="FOOTBALL_DATA_TOKEN", connector="APIConnector[football-data]", raw_tier="OFFICIAL",
    ),
    "espn": SourceInfo(
        "espn", "ESPN (feed JSON público, não oficial)", DataLevel.BOXSCORE,
        500_000_000, False,
        "Endpoint público sem documentação oficial. Desativado por padrão; uso pessoal/acadêmico, "
        "com baixa frequência. Verifique os termos de uso da ESPN antes de ativar.",
        "https://www.espn.com.br/futebol/", needs_key="ENABLE_ESPN_PUBLIC_FEED", connector="APIConnector[espn-público]", raw_tier="DERIVED",
    ),
    "fdcouk": SourceInfo(
        "fdcouk", "football-data.co.uk (CSVs públicos)", DataLevel.BOXSCORE,
        2_000_000_000, True,
        "Arquivos gratuitos para download; citar football-data.co.uk. Ligas principais: placar e estatísticas "
        "de equipe; ligas extras (inclui Brasileirão): placar.",
        "https://www.football-data.co.uk", connector="CSVConnector[football-data.co.uk]", raw_tier="OFFICIAL",
    ),
    "openfootball": SourceInfo(
        "openfootball", "openfootball / football.json (CC0)", DataLevel.RESULT,
        3_000_000_000, True,
        "Domínio público (CC0 1.0). Resultados de dezenas de ligas; arquivos completos trazem gols, escalações, "
        "cartões, público e árbitro.",
        "https://github.com/openfootball/football.json", connector="OpenFootballProvider", raw_tier="OFFICIAL",
    ),
    "intl": SourceInfo(
        "intl", "Resultados de seleções desde 1872 (martj42/international_results, CC0)", DataLevel.RESULT,
        4_000_000_000, True, "Domínio público (CC0 1.0). Placar, torneio, local e autores dos gols.",
        "https://github.com/martj42/international_results", connector="OpenSourcesIngestor", raw_tier="OFFICIAL",
    ),
    "understat": SourceInfo(
        "understat", "Understat (xG por jogo e por finalização)", DataLevel.BOXSCORE,
        6_000_000_000, False,
        "Dados públicos do site understat.com; uso pessoal/acadêmico com crédito à fonte. Cobre Premier League, "
        "La Liga, Bundesliga, Serie A, Ligue 1 e Russian Premier League desde 2014/15.",
        "https://understat.com", connector="UnderstatProvider", raw_tier="DERIVED",
    ),
    "brasileirao": SourceInfo(
        "brasileirao", "Brasileirão Série A 2003→ (Brasileirao_Dataset, Adão Duque)", DataLevel.BOXSCORE,
        7_000_000_000, False,
        "Dataset comunitário (GPL-2 segundo o Kaggle do autor): partidas, estatísticas por clube, gols e cartões "
        "por atleta/minuto. Uso pessoal/acadêmico com crédito.",
        "https://github.com/adaoduque/Brasileirao_Dataset", connector="BrasileiraoDatasetProvider", raw_tier="OFFICIAL",
    ),
    "open_matchday": SourceInfo(
        "open_matchday", "open-matchday (temporada atual, dezenas de competições)", DataLevel.RESULT,
        8_000_000_000, False,
        "Compilação diária de OpenLigaDB, fixturedownload, ESPN e football-data.co.uk; informativo, não comercial.",
        "https://github.com/oladeeayo/open-matchday", connector="OpenMatchdayProvider", raw_tier="DERIVED",
    ),
    "cbf": SourceInfo(
        "cbf", "Súmulas da CBF 2013–2025 (BrazilianFootball/Data)", DataLevel.RESULT,
        9_000_000_000, True,
        "MIT. Súmulas eletrônicas oficiais: Série A–D e Copa do Brasil (gols, cartões, árbitro, estádio).",
        "https://github.com/BrazilianFootball/Data", connector="CbfSumulasProvider", raw_tier="OFFICIAL",
    ),
    "openplay": SourceInfo(
        "openplay", "OpenPlay (eventos com coordenadas e xG)", DataLevel.EVENTS,
        11_000_000_000, False,
        "CC BY 4.0 declarada (Noah Bair / OpenPlay); eventos de origem WhoScored/Opta, sujeitos a pedido de retirada "
        "pelos donos. Uso pessoal/acadêmico com atribuição.",
        "https://github.com/nlbair/openplay", connector="OpenPlayProvider", raw_tier="DERIVED",
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
    for key in ("openplay", "cbf", "open_matchday", "brasileirao", "understat", "intl", "openfootball", "fdcouk", "espn",
                "football_data", "api_football", "wyscout"):
        off = SOURCES[key].id_offset
        if mid >= off:
            return key
    return "statsbomb"


def to_source_id(match_id: int) -> int:
    src = source_from_internal_id(match_id)
    if src in SOURCES:
        return int(match_id) - SOURCES[src].id_offset
    return int(match_id)


EXTRA_PROVENANCE = {
    "simulated": ("Gerador interno de partidas simuladas", "BrasileiraoProfileGenerator",
                  "Gerado pelo laboratório (sem restrição)", "SIMULATED"),
    "upload": ("Arquivo enviado pelo usuário", "UploadConnector", "Responsabilidade do usuário", "OFFICIAL"),
}


def provenance_base(source: str) -> Dict[str, str]:
    """Fonte, conector, licença e tier padrão de uma fonte interna (para o ProvenanceRegistry)."""
    if source in SOURCES:
        s = SOURCES[source]
        return {"source": s.label, "connector": s.connector or s.key, "license": s.license_note,
                "raw_tier": s.raw_tier}
    label, conn, lic, tier = EXTRA_PROVENANCE.get(source, (source, source, "não informada", "DERIVED"))
    return {"source": label, "connector": conn, "license": lic, "raw_tier": tier}


def badge_for(level: Optional[str]) -> str:
    return BADGES.get(level or "", BADGES[DataLevel.EVENTS])
