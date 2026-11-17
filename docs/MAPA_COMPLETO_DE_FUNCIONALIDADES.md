# Mapa completo de funcionalidades

> Auditoria Fase 0. `Preservada` significa que o legado continua disponível; não significa que a migração esteja concluída. Só marcar como concluída após implementação e teste de paridade.

## Escopo inventariado

O auditor read-only (`data/audits/project_audit_fase0.json`) encontrou 436 arquivos Python no escopo do repositório, 24 páginas Streamlit principais, 28 conectores/fontes e 42 arquivos de teste no diretório raiz. A cópia `tactical-intelligence-lab/` contém uma réplica sem `.git` próprio e foi mantida intacta.

## Páginas e recursos

| Funcionalidade | Localização atual | Dados/dependências | Destino | Teste | Situação |
|---|---|---|---|---|---|
| Analista IA | `src/ui/pages/ai_analyst.py`, `intelligence/` | evidências, roteador NLP, Gemini/fallback | API de inteligência | testes de casos e grounding | Preservada |
| Assistente | `src/ui/pages/assistant.py` | catálogo, busca, perguntas | API de busca/assistente | `test_day18`, `test_day33`, `test_day36` | Preservada |
| Catálogo | `src/ui/pages/catalog.py` | partidas e níveis de profundidade | API paginada | testes de filtros/profundidade | Preservada |
| Clube | `src/ui/pages/club.py` | perfil e partidas | API de clube | testes de perfil | Preservada |
| Clubes | `src/ui/pages/clubs.py` | catálogo, retrospecto, filtros de partidas | API de clubes | filtro local + paridade | Preservada; correção estabilizada |
| Comparação | `src/ui/pages/compare.py` | jogadores/equipes, histórico e ratings | API de comparação | testes de comparação | Preservada |
| Competição | `src/ui/pages/competition.py` | jogos, tabela e cobertura | API de competição | testes de catálogo/cobertura | Preservada |
| FotMob profundidade | `src/ui/pages/fotmob_depth.py` | cobertura/profundidade FotMob | Data Hub/API | fixtures FotMob | Preservada |
| FotMob forças | `src/ui/pages/fotmob_strengths.py` | estatísticas e forças | serviço analítico | testes de stats | Preservada |
| Jogos/calendário | `src/ui/pages/games.py` | próximos jogos, resultados e status | API de partidas | integração de calendário | Preservada |
| Laboratório | `src/ui/pages/lab.py` | módulos analíticos e diagnóstico | jobs/API | testes de pipeline | Preservada |
| Centro de partida | `src/ui/pages/match_center.py` | eventos, escalações, stats, relatórios | API de partida | fixtures e e2e | Preservada |
| Inspeção ML | `src/ui/pages/ml_inspection.py` | modelos, métricas e inspeções | serviço de jobs | testes ML | Preservada |
| Redes | `src/ui/pages/networks.py` | rede de passes | `networks/`, visualização web | testes de rede | Preservada |
| Neural/NLP | `src/ui/pages/neural.py` | modelos neurais e roteamento | serviço de inferência | testes neurais/NLP | Preservada |
| Padrões | `src/ui/pages/patterns.py` | sinais e padrões táticos | API tática | testes de sinais | Preservada |
| Jogadores | `src/ui/pages/players.py` | dossiê, ratings, histórico | API de jogadores | testes de rating/histórico | Preservada |
| Busca de jogadores | `src/ui/pages/players_search.py` | busca e filtros | endpoint paginado | testes de busca | Preservada |
| Scout | `src/ui/pages/scout.py`, `src/scout/engine.py` | mercado, filtros, histórico, adversário | serviço de scout | `test_scout_engine` e paridade | Preservada |
| Busca global | `src/ui/pages/search_all.py` | jogadores, clubes e partidas | endpoint de busca | testes de resolução | Preservada |
| Squad planner | `src/ui/pages/squad.py`, `src/squad/` | elenco, fit, provável XI | serviço de planejamento | `test_day35_squad_planner` | Preservada |
| Forças | `src/ui/pages/strengths.py` | strengths/weaknesses | API analítica | testes de diagnóstico | Preservada |

## Domínio e algoritmos

| Funcionalidade | Localização | Dados | Destino/teste | Situação |
|---|---|---|---|---|
| Ratings v2/v3 e box | `src/analytics/`, `src/metrics/` | stats, eventos, contexto | `packages/intelligence`; testes de escala e legado | Preservada |
| Força do adversário | `src/analytics/opponent_strength.py` | resultados anteriores/Elo | serviço contextual; sem vazamento temporal | Preservada |
| Scout | `src/scout/engine.py` | histórico, mercado, fontes externas | serviço de scout | Preservada |
| Planner | `src/squad/planner.py` e `src/squad/` | posições, fit, elenco | serviço de squad | Preservada |
| Relatórios | `src/reports/report_builder.py` | evidências e metadados | API/exportações | Preservada |
| Guardrail numérico | `src/guard/`, `report_builder.py` | números BR/US e evidências | middleware do relatório | Preservada |
| IDs e lake | `src/data_lake/` | identidade de pessoas/times e links | contratos Data Hub | Preservada |
| IA tática/NLP | `src/intelligence/`, `src/tactical_engine/` | perguntas e evidências | API, sem acesso direto web | Preservada |
| ML e visualização | `src/machine_learning/`, `src/networks/`, `src/visualization/`, `src/geometry/` | modelos, eventos e coordenadas | jobs/API/web | Preservada |

## Fontes e conectores

| Fonte/conector | Localização | Dados | Destino/teste | Situação |
|---|---|---|---|---|
| API-Football | `src/data_hub/sources/api_football.py` | fixtures/stats | Data Hub; quota/fixture | Preservar; licença pendente |
| API Futebol | `src/data_hub/sources/api_futebol.py` | partidas/tabelas | Data Hub; quota/fixture | Preservar; licença pendente |
| ESPN | `src/data_hub/sources/espn.py` | resumo, roster, stats | Data Hub; fixtures ESPN | Preservar; licença pendente |
| FotMob | `src/data_hub/sources/fotmob.py` | calendário, detalhes, stats | Data Hub; fixtures FotMob | Preservar; licença pendente |
| StatsBomb | `src/data_hub/sources/statsbomb.py`, `src/connectors/statsbomb_connector.py` | eventos abertos | Data Hub; testes StatsBomb | Preservar conforme licença |
| Wyscout | `src/data_hub/sources/wyscout.py`, `src/connectors/wyscout_connector.py` | eventos/índice | adaptador privado/licenciado | Preservar; não redistribuir sem permissão |
| Understat | `src/data_hub/sources/understat.py` | xG/chutes | Data Hub; fixtures | Preservar; licença pendente |
| Transfermarkt | `src/data_hub/sources/transfermarkt_ds.py` | jogadores/clubes/valores | dataset conforme licença | Preservar; licença pendente |
| Football-Data | `src/data_hub/sources/fdcouk.py`, `football_data.py` | resultados/CSV | Data Hub; fixtures CSV | Preservar |
| OpenFootball | `src/data_hub/sources/openfootball.py` | resultados/calendário | Data Hub; fixtures | Preservar conforme licença |
| OpenPlay | `src/data_hub/sources/openplay.py` | eventos abertos | Data Hub; fixtures reais | Preservar conforme licença |
| Open Matchday | `src/data_hub/sources/open_matchday.py` | agenda/resultados | Data Hub; fixtures | Preservar conforme licença |
| CBF/Braseirão | `cbf_sumulas.py`, `brasileirao_dataset.py` | súmulas e stats | Data Hub; fixtures | Preservar conforme termos |
| Base dos Dados | `basedosdados.py` | datasets públicos | conector opcional | Preservar; validar billing/licença |
| Simonetti | `simonetti.py` | arquivos públicos | conector respeitando robots | Preservar conforme termos |

## Scripts, configuração e testes

`scripts/fetch_db.py`, `project_audit.py`, `optimize_db.py`, benchmarks, `agendar_atualizacao.ps1`, `src/tools/backup_local.py`, `config/`, fixtures e toda a suíte `tests/` são funcionalidades operacionais preservadas. O teste reproduzível é:

```powershell
$env:PYTHONPATH = "src"
.\venv\Scripts\python.exe -m pytest -q .\tests
```

O inventário detalhado de funções/classes está no JSON do auditor; nenhum módulo foi removido para criar a arquitetura futura.
