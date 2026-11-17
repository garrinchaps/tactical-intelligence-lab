# Licenças e fontes

## Regra de publicação

Código, conectores e documentação podem ser públicos separadamente dos dados. Dados brutos só serão distribuídos quando a licença/termos permitirem; caso contrário, o Data Hub mantém referência, atribuição e processamento local/privado.

## Fontes identificadas

ESPN, FotMob, StatsBomb Open Data, Wyscout, Transfermarkt dataset, Understat, API-Football, API Futebol, Football-Data.co.uk, OpenFootball, OpenPlay, Open Matchday, CBF súmulas, Brasileirão datasets, Base dos Dados e Simonetti.

Cada conector está listado em `docs/MAPA_COMPLETO_DE_FUNCIONALIDADES.md`. Antes do deploy, registrar para cada fonte: URL, data de consulta, licença/termos, atribuição exigida, redistribuição permitida e limite de uso.

## Política técnica

- Fixtures sintéticos e dados de teste permanecem no repositório quando licenciados.
- Tokens/API keys ficam somente em ambiente/secrets.
- Manifests públicos expõem metadados e cobertura, não dados restritos.
- Divergências entre fontes são preservadas, não silenciosamente promediadas.
