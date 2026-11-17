# Operação do Data Hub

## Estado atual

O sistema atual opera com conectores em `src/data_hub/sources`, sincronização em `src/data_hub/sync.py` e armazenamento SQLite. A interface não deve iniciar sincronizações pesadas automaticamente.

## Contrato de execução

Cada job futuro deve registrar `run_id`, fonte, versão do conector, início/fim UTC, tentativa, status, registros lidos/aceitos/rejeitados, duplicatas, erros redigidos, qualidade e artefato produzido.

Jobs devem ser incrementais, idempotentes, retomáveis e possuir lock. Falhas não podem substituir o último artefato íntegro. Manifests devem apontar para partições, schema, checksum, licença e período coberto.

`src/data_hub/artifacts.py` fornece o primeiro contrato executável de manifesto:
checksum SHA-256, formato, tamanho, schema, proveniência, licença e permissão de
redistribuição. Ele escreve JSON atômico e não abre nem altera o banco legado.

## Validação

Executar checks de schema, chaves, datas, placares, profundidade, proveniência, duplicidade e amostras de paridade SQLite/Parquet. Publicar apenas artefatos aprovados.

### Proveniência dos indicadores de IA

Os endpoints fuzzy recebem somente variáveis normalizadas e não alteram o
SQLite legado. Antes de alimentar Mamdani ou Takagi–Sugeno, a camada de
integração deve registrar no manifesto do artefato a fonte, período, unidade,
licença e transformação das entradas. A resposta deve permanecer marcada como
`estimada`/`indicador`; `is_probability` é explicitamente falso. Resultados de
replay e calibração devem ser publicados como artefatos versionados antes de
serem usados para treinamento ou apresentados como desempenho validado.
