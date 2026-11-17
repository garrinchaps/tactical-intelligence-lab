# Matriz acadêmica de Inteligência Artificial

## Objetivo

Este documento conecta os conteúdos de G00IIAR0.01 — Introdução à Inteligência
Artificial — ao código, aos dados e às funcionalidades do Tactical Intelligence
Lab. A matriz separa o que já existe de forma verificável do que ainda é
roadmap. Nenhum protótipo experimental deve ser apresentado como modelo
validado.

## Estado atual resumido

| Pilar/conceito | Já existe | Aprimorar | Desenvolver | Prioridade |
|---|---|---|---|---|
| ML supervisionado | `src/machine_learning/supervised.py`, XGBoost, dataset de perigo, benchmarks | validação temporal, baselines, calibração e painel de métricas | classificação W/D/L e regressões de gols/xG com dados sem leakage | P0/P1 |
| ML não supervisionado | `src/machine_learning/clustering.py`, testes de separação de perfis | features táticas normalizadas e estabilidade dos clusters | perfis de jogadores/equipes e recomendação de similares | P1 |
| Aprendizado por reforço | não existe agente RL validado | manter simulador explicitamente baseado em regras | ambiente, estados, ações, recompensa, agente e avaliação contra política-base | P2 |
| Fuzzy Mamdani | `src/intelligence/fuzzy.py`, regras, pertinências, agregação e centroide | calibrar entradas semânticas e comparar com rating legado | ampliar catálogo de regras e avaliação retrospectiva | P1 experimental |
| Takagi–Sugeno | `src/intelligence/fuzzy.py`, consequentes lineares e pesos de regras | replay de partidas e estabilidade/latência | validar pressão/momento com dados ao vivo licenciados | P1 experimental |
| Sistemas especialistas | regras de scout, planner, guardrails e roteamento | catálogo versionado de regras e explicações | editor/avaliação de regras táticas configuráveis | P0/P1 |
| Redes neurais | `src/machine_learning/neural_net.py`, treinamento e testes de gradiente | validação pareada e registro de modelos | MLP aplicada a tarefa tabular com comparação contra baseline | P1 |
| CNN/LSTM/GRU | apenas infraestrutura/demos pontuais, sem modelo de produção comprovado | inventário de dados espaciais/temporais | visão/tracking ou séries temporais somente após dataset adequado | P2 |
| Transformers | `src/intelligence/llm_analyst.py` e NLP; fallback local e guardrail | separar geração de inferência e evidência; medir respostas | relatório contextual com avaliação factual e custo/latência | P1 |
| Autoencoders | não identificado | usar quality/anomaly checks existentes como baseline | anomalias com dataset rotulado/revisão humana | P2 |
| Evolucionários/genéticos | planner e otimizações por regras, sem GA formal comprovado | explicitar função objetivo/restrições | seleção, crossover, mutação, elitismo e comparação com solver/base | P1 |

## Matriz de implementação e avaliação

| Conteúdo | Funcionalidade | Entradas | Saídas | Métricas obrigatórias | Teste/critério de conclusão |
|---|---|---|---|---|---|
| Classificação supervisionada | previsão de resultado | histórico cronológico, força, mando, forma | classes vitória/empate/derrota + probabilidades calibradas | acurácia, macro-F1, matriz de confusão, log loss, Brier | split temporal, baseline maioria/logística, sem partidas futuras nas features |
| Regressão | gols/xG/posse | eventos, boxscore e contexto pré-jogo | valor contínuo e intervalo | MAE, RMSE, MSE e baseline | teste temporal isolado e relatório de resíduos |
| Clustering | perfis táticos | volumes normalizados por 90, posição e amostra mínima | cluster, centróide, distância e rótulo interpretável | silhouette, estabilidade, sensibilidade a escala | reprodutibilidade com seed e revisão dos centróides |
| Fuzzy Mamdani | nota interpretável | intensidade, precisão, volume, contexto | pertinências, regras ativadas e nota defuzzificada | cobertura de regras, monotonicidade, sensibilidade | casos-limite e comparação com rating legado; nunca chamar pertinência de probabilidade |
| Takagi–Sugeno | pressão/momento ao vivo | posse, entradas, recuperações, finalizações e tempo | índice contínuo e explicação | latência, estabilidade, correlação retrospectiva | replay de partidas e comparação com fórmula-base |
| Sistema especialista | compatibilidade/plano | posição, formação, restrições, evidências | recomendação, regras ativadas, violações | precisão das regras em fixtures, cobertura e taxa de conflito | regras versionadas, explicação e teste de regressão |
| MLP | previsão tabular | features selecionadas e split temporal | score/valor | MAE/RMSE ou F1, curva de aprendizado, comparação baseline | early stopping/regularização e registro do artefato |
| CNN | visão/tática espacial | vídeo/imagens licenciados | detecções/mapas | mAP, precisão/recall, IoU e latência | somente com dataset licenciado e ground truth |
| LSTM/GRU | evolução temporal | sequências de jogos/ações | previsão de tendência/desgaste | MAE/RMSE, erro por horizonte e baseline rolling | separação por partida/jogador e ausência de leakage |
| Transformer | perguntas/relatórios | evidências estruturadas e pergunta | resposta citada/ancorada | grounded numbers, taxa de abstenção correta, latência e custo | `NumericHallucinationGuard`, fixtures e auditoria humana |
| Autoencoder | qualidade/anomalia | vetores de partidas/jogadores | erro/anomalia explicada | precision/recall em anomalias revisadas, AUROC | não gerar acusação; linguagem deve ser “sinal para revisão” |
| Algoritmo genético | escalação/orçamento | candidatos, posições, orçamento, restrições | elenco e fitness | fitness, violações, tempo, gap para baseline | seeds reprodutíveis, penalidades testadas e comparação gulosa |
| RL | simulador tático | estado, ações, transição e recompensa | política/ação | retorno médio, dispersão, regret e comparação política-base | só chamar RL após treino em ambiente explícito; regras atuais são simulador, não RL |

## Arquitetura acadêmica

1. **Dataset registry:** manifesto, licença, período, schema, checksum e versão.
2. **Feature registry:** nome, unidade, fórmula, fonte, janela temporal e risco de leakage.
3. **Model registry:** algoritmo, versão, dataset, split, hiperparâmetros, métricas, artefato e limitações.
4. **Inference contract:** entrada validada, saída, incerteza, explicação, proveniência e status (`observado`, `estimado`, `simulado`).
5. **Evaluation jobs:** execução reprodutível fora do frontend, com resultados versionados.
6. **UI de IA:** mostra modelo, variáveis, métricas, versão, limitações e evidências; não transforma score fuzzy em probabilidade.

## Ordem de prioridade

### P0 — confiabilidade e rastreabilidade

- Completar manifests e contratos.
- Registrar versões dos modelos existentes.
- Formalizar splits temporais e baselines.
- Expor métricas reais no módulo de IA.
- Preservar guardrail numérico e proveniência.

### P1 — valor aplicado com dados existentes

- Clustering tático de jogadores/equipes.
- MLP supervisionada tabular.
- Fuzzy Mamdani para explicação de rating.
- Takagi–Sugeno para pressão/momento.
- Algoritmo genético para planner com restrições.

### P2 — pesquisa dependente de dados/infrastrutura

- CNN com vídeo licenciado.
- LSTM/GRU com sequências suficientemente densas.
- Autoencoder com revisão de anomalias.
- RL com ambiente e política-base.

## Critérios globais de conclusão

- Código, dataset, split, seed e configuração registrados.
- Baseline simples executado e superado ou diferença justificada.
- Testes unitários, temporais, integração e paridade aprovados.
- Métricas e intervalos publicados junto ao modelo.
- Data leakage investigado explicitamente.
- Resposta/otimização explica entradas, limitações e incerteza.
- Dados simulados não aparecem como fatos.
- Licença permite o uso pretendido.
