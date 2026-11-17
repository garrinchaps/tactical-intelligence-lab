# Preparação para publicação pública

## Objetivo e regra de segurança

A publicação deve manter a aplicação Streamlit existente, suas páginas e seus módulos. O deploy não pode substituir a base local por uma base vazia, reduzida ou de demonstração. A publicação só deve ser considerada pronta depois de importar e validar a cópia integral da instalação de referência.

**O banco SQLite, os arquivos Parquet, os modelos treinados e os dados locais não devem ser enviados ao GitHub público.** O repositório é público; colocar esses arquivos nele pode expor dados, chaves ou materiais com licenças incompatíveis.

## Estado atual

- O Data Hub usa SQLite e o banco padrão local é `database/tactical_lab.db`.
- O banco local é ignorado pelo Git.
- A base unificada e outros artefatos podem existir fora do SQLite, especialmente em `data/lake/`, `data/processed/` e `models/`.
- O código agora aceita `DATABASE_PATH` para apontar o SQLite a um volume persistente. Se a variável não estiver definida, o caminho local antigo continua sendo usado.
- Ainda não existe um deploy público configurado nem uma cópia remota validada da base de referência.

## Arquitetura inicial recomendada

Para preservar o comportamento atual sem reescrever as consultas do projeto:

1. Empacotar a aplicação existente em um contêiner Python.
2. Hospedar em um serviço que ofereça **disco persistente**, backup e transferência de arquivos grandes.
3. Manter o SQLite e os diretórios locais necessários em armazenamento persistente.
4. Começar com uma única instância da aplicação. O SQLite em volume compartilhado não deve ser tratado como banco multiwriter/multi-instância.
5. Desativar a sincronização automática dentro dos processos web. Executar ingestão por um processo agendado separado, com lock, logs, cotas e checkpoint.
6. Manter segredos apenas nas variáveis protegidas do provedor, nunca no repositório ou no pacote de migração.

A aplicação poderá ser acessada por várias pessoas ao mesmo tempo, mas a capacidade real dependerá do volume, CPU, RAM, I/O e padrão de consultas. Não se promete latência instantânea sem teste de carga.

## Migração da instalação local

A migração não deve ser feita copiando apenas o arquivo SQLite enquanto o app está gravando. O SQLite pode estar usando WAL. A cópia precisa usar a API de backup do SQLite ou ser feita com o app e os escritores parados, seguida de:

- `PRAGMA integrity_check` retornando `ok`;
- contagem por tabela antes e depois;
- tamanho e SHA-256 do arquivo de banco;
- comparação dos diretórios Parquet/modelos necessários;
- smoke tests das páginas principais, busca, partida, jogador, comparação, Scout, IA e exportações.

A base local original deve permanecer intacta e ser guardada como rollback. A restauração no servidor deve ser feita em staging e só promovida depois das verificações. Nunca executar uma rotina que apague ou substitua a única cópia da base.

## Critério de liberação

Não apontar o domínio público para a aplicação até que:

- a base remota seja comprovadamente igual ou mais completa que a base local de referência;
- os dados externos estejam autorizados para redistribuição pública, conforme as licenças/termos das fontes;
- os testes automatizados e os testes funcionais do app passem;
- backup e restauração tenham sido testados;
- haja monitoramento de espaço em disco, memória, erros e última sincronização.

## Próxima etapa necessária

Gerar no computador de referência um inventário não destrutivo da instalação: caminho e tamanho do SQLite, `integrity_check`, contagem de registros por tabela e tamanho/quantidade de arquivos em `data/lake/`, `data/processed/` e `models/`. Esse inventário define o tamanho mínimo do volume e permite validar a transferência sem presumir que o GitHub contém os dados.
