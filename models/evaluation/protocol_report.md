# Relatório do protocolo de avaliação

Gerado em 2026-11-13T23:56:28+00:00 por `python -m src.evaluation.protocol`.

## A) Perigo de posse

- Amostras: **116771** ações de **64** partidas; prevalência da classe positiva: **13.8%**.
- Validação: GroupKFold por partida (nenhuma partida no treino e na validação ao mesmo tempo), k = 5.
- Densidade de adversários medida pelo StatsBomb 360 em 87.3% das ações (restante: proxy).
- Implementação do Modelo A: substituto (xgboost indisponível no ambiente).

| Modelo | AUC-ROC (média ± desvio) | Ganho sobre B0 | Ganho sobre B1 |
|---|---|---|---|
| Baseline 0 — classe majoritária | 0.500 | — | — |
| Baseline 1 — logística (distância, ângulo, passes) | 0.647 ± 0.013 | +0.147 | — |
| Modelo A — XGBoost | 0.644 ± 0.005 | +0.144 | -0.004 |
| Modelo B — rede neural própria | 0.651 ± 0.006 | +0.151 | +0.003 |

- XGBoost: ganho MARGINAL (< 0,03 de AUC sobre a logística).
- Rede neural: ganho MARGINAL (< 0,03 de AUC sobre a logística).

## B) Grafo de passes

- Alvo: a posse chega ao terço final (x ≥ 80) depois do toque do atleta (2º tempo).
- calculadas no 1º tempo (rede de passes certos); betweenness com distância 1/(passes·(1+10·xT médio)).
- 128 equipes-partidas avaliadas.

| Score | AUC (média ± desvio) |
|---|---|
| Baseline — grau ponderado | 0.537 ± 0.070 |
| Modelo — betweenness ponderada por xT | 0.530 ± 0.065 |

- Diferença média: -0.008; betweenness vence em 39.1% das equipes-partidas. **Conclusão:** betweenness ponderada por xT NÃO supera o grau neste alvo (diferença < 0,01 de AUC).
