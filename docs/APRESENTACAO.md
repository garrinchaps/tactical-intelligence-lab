# Roteiro de apresentação (≈ 12 minutos)

Antes: `streamlit run app.py` com a final da Copa 2022 aberta. Funciona sem internet (cache em `data/demo/`).

| Tempo | Página | O que mostrar | Frase-chave |
|---|---|---|---|
| 0:00 | — | Problema: dado de futebol vem de fontes diferentes, em formatos diferentes, com níveis de confiança diferentes | “Cada número na tela diz de onde veio.” |
| 1:00 | 9 · Catálogo & Dados | Fontes, tier, schema canônico, catálogo YAML, upload de um modelo de scout | “Tudo entra no mesmo formato antes de qualquer cálculo.” |
| 2:30 | 1 · Centro da Partida | Placar, KPIs com linha de proveniência, painel ao pé da página | “OFICIAL, DERIVADO ou SIMULADO — sempre visível.” |
| 3:30 | 2 · Redes & xT | Rede de passes, progressão de xT, grau × betweenness | “A rede descreve a estrutura; não prometemos previsão (ver avaliação).” |
| 4:30 | 3 · ML & Inspeção | Tabela de baselines, matriz de confusão, importância, K-Means e DBSCAN com eps ajustável | “Ganho marginal sobre a logística — e dizemos isso.” |
| 6:30 | 4 · Rede Neural | Treinar ao vivo, curva de perda, clicar num neurônio (pais → filhos) | “Backpropagation escrito à mão e verificado por gradient check.” |
| 8:00 | 8 · Analista IA | Pergunta com recorte (“lado esquerdo, minuto 30”), tabela EXATO/DERIVADO/NÃO RASTREÁVEL | “O texto só chega à tela se os números tiverem origem.” |
| 9:30 | 7 · Fortes e Fracos | Percentil com n, faixa elite/alerta, “amostra insuficiente” | “Sem amostra, sem percentil.” |
| 10:30 | Laboratório | Simulador de cenários com IC; abrir um jogo simulado e ver o selo | “Simulado mede a incerteza do gerador, não do jogo.” |
| 11:30 | — | Limitações e próximos passos (tracking, XGBoost oficial, validação qualitativa) | — |

## Como falar do projeto

Use: “pipeline com proveniência”, “avaliação com baselines e validação por partida”, “guard que classifica cada
número”, “rede neural implementada do zero para fins didáticos”, “dados abertos StatsBomb e Wyscout”.

Evite: “RAG”, contagem de linhas de código, “à prova de falhas”, comparação de superioridade com produtos
comerciais, “raspamos todos os sites”, “maior base do mundo”, “IA treinada do zero” para a parte de linguagem
(o texto é do Gemini; o que é nosso é o recorte das evidências e o guard).

## Perguntas prováveis

- **Por que o XGBoost não ganha da logística?** Neste alvo a geometria já explica quase tudo; o protocolo existe
  justamente para mostrar isso em vez de supor.
- **O guard garante que a IA não erra?** Não. Garante que cada número tem origem nas evidências ou numa operação
  simples sobre elas; não garante que o número foi atribuído à métrica certa.
- **De onde vêm os dados do Brasileirão?** Boxscore pela API-Football (chave) e partidas simuladas por perfis,
  sempre marcadas. Não há eventos públicos com coordenadas do Brasileirão.
