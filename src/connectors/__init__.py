"""
Conectores plugáveis do pipeline de ingestão multi-fonte com proveniência rastreável.

Família EVENTOS  → schema canônico de eventos:   StatsBombConnector, WyscoutConnector
Família AGREGADOS → schema canônico de agregados: ScoutFileParser, APIConnector, EmpiricalFallback
Todos carimbam source, connector, license, ingestion_timestamp e confidence_tier.
"""
