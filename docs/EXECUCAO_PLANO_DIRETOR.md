# Execução do Plano Diretor — estado verificável

**Projeto:** Tactical Intelligence Lab  
**Repositório:** `garrinchaps/tactical-intelligence-lab`  
**Última auditoria remota:** 17 de novembro de 2026  
**Regra:** nenhum item é considerado concluído somente por estar planejado ou documentado.

## 1. Escopo desta atualização

Esta rodada adiciona:
- um inventário estático/read-only do código e do schema SQLite;
- testes automatizados para o inventário e para o bootstrap do banco;
- um workflow independente de regressão completa;
- proteção do bootstrap contra substituição silenciosa de banco SQLite existente;
- alinhamento da precedência de TACTICAL_DB_PATH entre o bootstrap e DataHubDB;
- preservação da régua individual 2.0 em `src/analytics/rating_v2_legacy.py`, enquanto a 3.0.1 permanece padrão;
- testes de compatibilidade da régua legada;
- índice de cobertura para a descoberta de jogadores ativos no histórico do Scout;
- versão do cache do mercado baseada no estado do SQLite, WAL e journal, preservando a renovação periódica de fontes externas;
- testes de plano de consulta e invalidação de cache;
- benchmark somente de leitura que compara a consulta antiga e a nova, verifica equivalência dos resultados e registra p50/p95;
- este registro de estado e pendências.

Nenhuma página, rota, algoritmo de análise, modelo ou tabela foi removida. O bootstrap agora preserva bancos existentes; uma substituição de banco pequeno que contém tabelas exige opt-in explícito e cria backup consistente antes da troca. O inventário continua sem importar/rodar módulos do app e a leitura do SQLite é read-only.

## 2. Estado observado no GitHub

| Item | Evidência observada | Estado |
|---|---|---|
| Branch principal | `main` apontava para `686b61c` na consulta | Referência de produção do repositório |
| PR #1 | `codex/revisao-rede-perigo` → `main`; alterações em rede neural, registry, assistente e testes | Aberto; revisão/testes completos pendentes |
| PR #2 | `codex/fotmob-depth-routing` → `codex/inteligencia-compartilhada`; 54 arquivos, 5.856 adições e 707 remoções na comparação do PR | Aberto; não mesclar sem auditoria arquivo a arquivo |
| PR #3 | `codex/scout-history-index-alignment` → `codex/fotmob-depth-routing`; 1 arquivo | Aberto; dependente da branch/PR #2 |
| CI anterior | Workflow `Scout module checks` compila parte do Scout e executa `test_scout_engine.py` e `test_database_path_config.py` | Não representa a suíte completa |
| CI anterior — último head consultado | Duas execuções do job `scout-engine` em `1a7afaf` concluíram com sucesso | Aprovado somente para esse job e esses testes |
| CI integral — head `daf387b` | `compileall`, inventário read-only e `pytest` completo aprovados: **324 passed, 1 skipped, 21 warnings** (Python 3.11) | Aprovado para o checkout/ambiente do GitHub Actions; não substitui validação visual end-to-end nem auditoria do banco local |

**Importante:** os PRs são propostas de alteração, não prova de que o código já está na branch `main`. PR #2 está direcionado a uma branch intermediária, e PR #3 é empilhado sobre PR #2. Não altere essas bases nem mescle automaticamente.

## 3. Fase 1 — Fundação, integridade e velocidade (P0)

| Entrega | Estado inicial constatado | Próxima ação / critério de conclusão |
|---|---|---|
| Inventário de páginas, módulos, símbolos e imports | Parcial; `docs/ARQUITETURA.md` documenta o mapa, mas precisa ser atualizado automaticamente | Usar `scripts/project_audit.py`; revisar discrepâncias com o mapa manual |
| Inventário SQLite | Parcial; novo script lê schema, colunas, índices e FKs em modo read-only | Executar no banco local com `--database`; contagem de linhas e quick_check são opcionais por custo |
| Bootstrap seguro do banco | Implementado na branch de trabalho; testes adicionados | Banco pequeno com tabelas não é sobrescrito sem `TACTICAL_ALLOW_DB_REPLACE=1`; substituição intencional gera backup via SQLite Backup API |
| Testes de regressão gerais | Novo workflow executou compileall, inventário e a suíte completa em `daf387b`: **324 passed, 1 skipped, 21 warnings** | Aprovado para esse checkout; ampliar cobertura visual/integrada e testar com o banco local real |
| Alinhamento do histórico do Scout | Correção existe na linha de desenvolvimento/PRs de trabalho | Reexecutar teste dedicado e comparar dados agregados com fixture independente |
| Benchmark do Scout | `scripts/benchmark_scout_index.py` compara as duas consultas em modo read-only, exige resultados idênticos e informa p50/p95 e fator p50; benchmark completo do pipeline continua em `scripts/benchmark_scout.py` | Rodar no banco local após a migração criar o índice; registrar tempos, hardware, tamanho e data para comparação antes/depois |
| Pré-agregação de jogador/temporada/365 dias/5 partidas/competição/clube | Ainda pendente; esta rodada acelera a seleção dos atletas ativos e o reaproveitamento do resultado agregado via cache Streamlit, mas não grava agregados incrementais no banco | Implementar em etapa própria; exigir equivalência numérica com cálculo bruto, checkpoint por partida e rollback |
| Cache com invalidação/versionamento | Cache do War Room agora inclui assinatura do SQLite/WAL/journal e mantém a renovação periódica do mercado externo; ainda não é invalidação seletiva por domínio | Testar inserção/atualização em banco real, confirmar mudança da assinatura e medir hit/miss no Streamlit |
| SQLite + DuckDB + Parquet | SQLite está presente; data lake/Parquet aparece no código/documentação; integração DuckDB e ganho real não comprovados | Benchmark isolado; preservar SQLite; só ativar o caminho analítico se houver ganho mensurável e consistência |
| Monitoramento | Existem pontos de saúde/sync e benchmark em branch de trabalho | Adicionar latência p50/p95, RAM, CPU, erro de fonte, freshness e alertas sem logs de segredos |
| Backup e restauração | Há documentação/ferramentas parciais em branches | Backup consistente com SQLite Backup API ou processo equivalente; teste automatizado de restauração e checksums |

## 4. Fase 2 — Base de dados (P0/P1)

| Domínio | Estado | Critério de conclusão |
|---|---|---|
| Identidade universal de jogadores | Resolvedores e IDs canônicos aparecem em branches de trabalho | Mapeamento por provedor, evidência de merge, fila de ambiguidades e zero merge automático de homônimos ambíguos |
| Estatísticas individuais | Cobertura multi-fonte parcial | Cada métrica guarda fonte, unidade, definição, data, nível e confiança; ausência diferente de zero |
| Banco de partidas | Catálogo SQLite e níveis de dados já existem | Chave canônica, deduplicação auditável, escalações, eventos e estatísticas com procedência |
| Eventos e espacial | Dados de eventos existem para subconjuntos de fontes/competições | Padronização de orientação e coordenadas, testes geométricos e cobertura por competição/temporada |
| Tracking | Somente amostras públicas/contratadas são possíveis | Não inferir tracking; manter licença, anonimização e origem de cada arquivo |
| Fontes | Há conectores em desenvolvimento/uso no projeto | Registro de disponibilidade, limites, termos, cobertura, retry/backoff, fallback, divergências e atualização incremental |

## 5. Fase 3 — Modelos e inteligência própria (P0/P1)

| Modelo / sistema | Estado observado | Critério de conclusão |
|---|---|---|
| xT | Modelo/visualização já documentados na arquitetura | Fórmula, normalização, validação temporal e comparação com baseline |
| xG / xA / xPass | Existem componentes e campos em algumas fontes; modelos próprios não estão todos comprovados como validados | Dataset com definição do alvo, validação fora da amostra, calibração e comparação com baseline |
| VAEP | Não comprovado como motor completo validado | Implementação conforme estado/ação, valor ofensivo/defensivo e avaliação temporal |
| Player Rating | Régua 3.0.1 em desenvolvimento; versão 2.0 preservada em `rating_v2_legacy.py` para reprodução histórica | Separar desempenho-base, ajustes, confiança e amostras; backtest cego por função e comparar 2.0 × 3.0.1 |
| Team Rating / Match Strength / forecast | Parcial ou não verificado | Protocolo, calibração, incerteza, baseline e validação fora da amostra |
| Redes neurais | Rede MLP própria em NumPy está presente na arquitetura | PyTorch é opcional; só entra quando superar baseline simples em validação repetível |
| Player DNA / Team DNA | Parcial em ratings e históricos, sem cobertura demonstrada para todos os atributos | Perfil dinâmico com atributos observados, derivados e não observados explicitamente separados |

## 6. Fases 4 a 7 — Produto e inteligência tática (P1/P2)

| Área | Estado | Critério de conclusão |
|---|---|---|
| Tactical Intelligence Engine | Recuperação de evidências e interpretação de perguntas existem em branches | Cada afirmação numérica rastreável ao dado/fórmula, com fallback para insuficiência |
| Tactical Matchup / adversários | Blocos táticos parciais | Evidências espaciais/temporais disponíveis, comparação de planos e validação especializada |
| Match Simulator | Planejamento/formações existem; simulador probabilístico completo não comprovado | Distribuições calibradas, cenários reproduzíveis e backtest |
| Scout Intelligence | Motor de Scout existe em branch de trabalho | Ranking por função/contexto, explicabilidade, amostra, custo e feedback |
| Potencial / Player Development | Não comprovado como pipeline validado | Diferenciar projeção de desempenho observado; validação temporal e relatórios de evolução |
| Transfer Market Intelligence | Histórico/valores aparecem no ecossistema de dados | Valores de mercado ≠ taxas pagas ≠ salários; cada categoria requer fonte, data e moeda |
| Agentes especializados | Assistente existente; orquestrador multiagente não comprovado | Especialistas somente quando tarefas justificarem; roteamento central, orçamento e auditoria |
| MLOps / MLflow / feedback | Registry, treinamento separado e feedback existem parcialmente/em branches | Tracking, datasets versionados, registro de modelos, aprovação/rollback e feedback rotulado |
| Knowledge Graph | Não comprovado como grafo semântico do domínio | Esquema de relações, proveniência, consultas úteis e comparação com SQL baseline |
| Visualizações e relatórios | Gráficos, redes e relatórios existem em módulos atuais | Componentes incrementais, estados vazios, exportação e proveniência |
| Personalização multi-clube/usuário | Não comprovada | Autenticação, isolamento por tenant, autorização testada e proteção de dados |

## 7. Fases 8 e 9 — Publicação e pesquisa (P0 lançamento / P3)

| Área | Estado | Critério de conclusão |
|---|---|---|
| Deploy reprodutível | Documentação e script de recuperação de banco em branch de trabalho | Build reproduzível, healthcheck, configuração por ambiente e migração versionada |
| API/worker/fila | Não comprovado como arquitetura completa | Tarefas pesadas não bloqueiam Streamlit; retries idempotentes e fila monitorada |
| Docker/Nginx/HTTPS | Não comprovado em produção | Teste de deploy, TLS, limites, logs, restart e rollback |
| Banco persistente/backups | Não comprovado em hospedagem final | Volume persistente, backup off-site, checksum e restore periódico testado |
| Digital Twin | Experimental/futuro | Calibrar contra tracking/eventos; nunca apresentar simulação como observação |
| Similaridade avançada / clustering / redes de interação | Componentes isolados podem existir; produto completo não comprovado | Recall@K, estabilidade, avaliação externa e baseline |
| GNN / Transformers / multimodal / RL / Bayes | Pesquisa futura | Só produção após superar baseline, demonstrar valor e caber no orçamento de hardware/custo |

## 8. Guardrails de aceitação para qualquer alteração

1. Não apagar ou substituir páginas/rotas existentes.
2. Nenhuma migração de banco sem backup íntegro, migração reversível e teste de restauração.
3. Nenhuma mudança de algoritmo sem testes de regressão de resultados antigos e novos.
4. Nenhum novo modelo em produção sem validação temporal/grupal adequada e baseline.
5. Nunca transformar dado ausente em zero.
6. Nunca usar informação futura para explicar/prever o passado.
7. Nunca mesclar atletas/clubes ambíguos por semelhança de nome apenas.
8. Nunca bloquear a interface com sincronização, treino ou reconstrução histórica pesada.
9. Nenhuma fonte deve ser usada sem revisar licença, termos, cota, atribuição e direito de redistribuição.
10. Toda alteração deve trazer evidência: teste, benchmark, cobertura ou decisão de não implementar.

## 9. Ordem executiva

1. Completar inventário e executar suíte total.
2. Medir baseline de latência e cobertura.
3. Corrigir erros de dados e regressões antes de novas funções.
4. Fazer pré-agregações/caches somente após testes de equivalência.
5. Consolidar IDs e qualidade de fontes.
6. Expandir métricas/modelos estatísticos com validação.
7. Expandir tática/Scout e módulos visuais com dados compatíveis.
8. Implementar MLOps, feedback e agentes quando houver valor mensurável.
9. Preparar deploy com persistência, segurança e recuperação.
10. Pesquisa P3 após a plataforma operacional.

## 10. O que esta atualização não afirma

- Não afirma que todos os 38 temas do Plano Diretor estão implementados.
- Não afirma que toda a suíte de testes passou: o novo workflow ainda precisa executar.
- Não afirma que DuckDB, PyTorch, MLflow, tracking, salários, previsão ou Digital Twin estão prontos.
- Não afirma que a aplicação está publicada, segura para multiusuário ou disponível 24/7.
- Não afirma que a base local ou arquivos que não foram acessados nesta sessão foram auditados.

Esta documentação é um inventário de estado e critérios de aceitação. Ela deve ser atualizada com evidências a cada fase concluída.
