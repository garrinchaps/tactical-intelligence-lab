# Referências técnicas, científicas e de dados

**Objetivo:** orientar a execução do Plano Diretor com fontes primárias ou documentação oficial. A inclusão de uma fonte nesta lista não significa que o projeto já tenha autorização para copiar, armazenar ou redistribuir todos os seus dados.

## Armazenamento e performance

1. **DuckDB — Parquet:** https://duckdb.org/docs/stable/data/parquet/overview  
   DuckDB documenta leitura/escrita Parquet e pushdown de filtros/projeções. Uso recomendado: benchmark analítico isolado sobre cópias/exports versionados; não substituir SQLite sem teste de equivalência e ganho real.

2. **Apache Parquet — overview:** https://parquet.apache.org/docs/overview/  
   Parquet é um formato colunar com compressão/encoding para armazenamento e recuperação analítica. Particionamento, row groups e tamanho dos arquivos devem ser medidos no dataset real.

3. **DuckDB — concorrência:** https://duckdb.org/docs/stable/connect/concurrency  
   Antes de compartilhar um arquivo DuckDB entre vários processos/instâncias, projetar o modelo de leitura/escrita à luz das garantias e limitações documentadas. Não presumir que DuckDB seja um substituto drop-in de banco transacional multiwriter.

## Modelagem e validação

4. **scikit-learn — GroupKFold:** https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html  
   Útil para separar grupos (por exemplo, partidas) entre treino e teste, evitando que amostras do mesmo grupo apareçam nos dois lados da mesma divisão.

5. **scikit-learn — TimeSeriesSplit:** https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html  
   A validação temporal respeita a ordem do tempo; usar quando a tarefa prevê eventos ou desempenho futuros. Ajustar gap e janelas ao problema e à sazonalidade real.

6. **PyTorch — deterministic algorithms:** https://docs.pytorch.org/docs/stable/generated/torch.use_deterministic_algorithms.html  
   Reprodutibilidade exige mais do que uma única opção determinística: registrar versões, seeds, hardware e limitações de operações não determinísticas.

7. **MLflow — Tracking:** https://mlflow.org/docs/latest/ml/tracking  
   Registrar parâmetros, código, métricas e artefatos de cada experimento.

8. **MLflow — Model Registry:** https://mlflow.org/docs/latest/registry/  
   O registry fornece lineage, versões, aliases e metadados para ciclo de vida de modelos. Antes de adotar, avaliar backend persistente, storage de artefatos e custo operacional.

## Dados de futebol e licenças

9. **StatsBomb Open Data:** https://github.com/statsbomb/open-data  
   A própria documentação incentiva pesquisa com determinadas competições e pede atribuição da fonte e uso do logo da StatsBomb ao publicar/compartilhar pesquisas ou análises. Conferir sempre o README e os termos vigentes antes de redistribuir dados ou resultados.

10. **Wyscout / Soccer match event dataset:** https://github.com/koenvo/wyscout-soccer-match-event-dataset  
    O repositório descreve os dados e aponta a coleção Figshare e a licença CC BY 4.0. Manter atribuição e citação acadêmica exigidas pela licença/fonte.

11. **Metrica Sports — sample data:** https://github.com/metrica-sports/sample-data  
    Os exemplos públicos incluem jogos anonimizados de tracking e eventos sincronizados. A própria página descreve que são exemplos de formato/qualidade e pede atribuição em usos públicos; não assumir que isso concede licença irrestrita para qualquer uso comercial ou redistribuição.

12. **API-Football — termos:** https://www.api-football.com/terms  
    Os termos alertam que a disponibilidade de dados varia por competição e que quotas/limites dependem do plano. O sistema deve registrar cota, respostas 429, disponibilidade por liga/temporada e consultar os limites atuais em vez de codificar números promocionais permanentemente.

13. **API-Football — rate limiting (12 jun. 2026):** https://www.api-football.com/news/post/how-ratelimit-works  
    A página descreve limites por minuto que dependem do plano. O conector deve respeitar limites configurados e backoff; valores atuais precisam ser revalidados antes de cada deployment.

14. **football-data.co.uk:** https://www.football-data.co.uk/  
    Verificar avisos, condições de uso, cobertura e atribuição no site antes de ingestão e publicação. Não tratar todos os campos ou temporadas como uniformes.

15. **Oracle Cloud Free Tier:** https://www.oracle.com/cloud/free/ e https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm  
    A oferta Always Free tem limites de recursos e capacidade regional. A própria documentação alerta para indisponibilidade temporária de capacidade (out-of-host-capacity). Não prometer SLA ou disponibilidade contínua com base apenas no plano gratuito.

## Fontes a revisar antes de habilitar conectores

- **FotMob, ESPN, FBref, Understat e Transfermarkt:** verificar termos de uso, políticas anti-automação, limites, direitos sobre escudos/fotos e permissões de redistribuição. A presença de endpoints públicos ou páginas acessíveis não equivale a uma licença de coleta em escala.
- **Wyscout comercial:** acesso e reutilização de dados pagos dependem do contrato/licença adquiridos.
- **Tracking comercial:** exigir licença explícita para armazenamento, treino, exibição e distribuição.

## Política interna de governança

Para cada conector, manter um registro com: URL oficial, método de acesso, licença/termos, atribuição, limites conhecidos, cota configurada, frequência, data da última revisão dos termos, cobertura por competição/temporada, política de cache e autorização de redistribuição. Em dúvida jurídica ou de licença, manter o conector desativado para publicação pública até revisão.
