# Protocolo de avaliação

Reproduzir: `python -m src.evaluation.protocol --competition "FIFA World Cup" --season 2022`
(gera `models/evaluation/protocol_report.json/.md` e os modelos finais em `models/trained/`).

## A) Perigo de posse

**Pergunta:** a partir de uma ação com bola, a posse termina em finalização?

- **Unidade:** ação com bola (passe, condução, drible) com coordenadas.
- **Variáveis (14):** distância e ângulo ao gol, densidade de adversários num raio de 5 m (StatsBomb 360 quando
  existe; proxy por ações defensivas próximas quando não), passes já feitos na posse, saldo de gols e 9 zonas do campo.
- **Validação:** `GroupKFold` por partida (k = 5). Nenhuma partida aparece no treino e na validação.
- **Prevalência** da classe positiva sempre reportada (o AUC de 0,5 é o piso, não “50% de acerto”).

| Modelo | O que é |
|---|---|
| Baseline 0 | classe majoritária (score constante → AUC 0,5) |
| Baseline 1 | regressão logística só com distância, ângulo e nº de passes |
| Modelo A | XGBoost com as 14 variáveis |
| Modelo B | rede neural própria (NumPy, 14 → 32 → 16 → 1) |

**Regra de leitura definida antes de rodar:** ganho de AUC < 0,03 sobre o Baseline 1 = **marginal**.

### Resultado preliminar (Copa 2022, 64 partidas, 116.771 ações, prevalência 13,8%)

| Modelo | AUC (média ± desvio) | Ganho s/ B1 |
|---|---|---|
| B0 | 0,500 | — |
| B1 logística | 0,647 ± 0,013 | — |
| A “XGBoost” (substituto no ambiente de desenvolvimento) | 0,644 ± 0,005 | −0,004 |
| B rede neural | 0,651 ± 0,006 | +0,003 |

**Leitura:** os três modelos aprendem sinal real (≈ +0,15 sobre B0), mas os modelos não lineares têm ganho
**marginal** sobre a geometria. Distância, ângulo e nº de passes concentram quase toda a informação desse alvo.
O resultado é apresentado assim; não foi ajustado para parecer melhor.

## B) Grafo de passes

**Pergunta:** a betweenness ponderada por xT identifica melhor que o grau quem leva a posse ao terço final?

- Rede de passes certos do **1º tempo** de cada equipe-partida.
- Distância da aresta = 1 / (passes · (1 + 10 · xT médio da ligação)).
- **Alvo:** no 2º tempo, a posse chega a x ≥ 80 depois do toque do atleta.
- AUC por equipe-partida (128), comparando os dois rankings.

| Score | AUC média ± desvio |
|---|---|
| Grau ponderado (baseline) | 0,537 ± 0,070 |
| Betweenness ponderada por xT | 0,530 ± 0,065 |

**Leitura:** a betweenness por xT **não supera** o grau (diferença −0,008; vence em 39% das equipes-partidas).
Os dois são pouco informativos para esse alvo. A rede de passes fica na interface como **descrição da
estrutura**, não como preditor.

## C) Guard de números

Métrica registrada a cada resposta do Gemini (tabela `guard_metrics`): fração de números não rastreáveis
**antes** e **depois** da política (aprova → regenera com contexto restrito → degrada declarando).
A página 8 mostra a média acumulada.

## Limitações

- O relatório oficial deve ser gerado com o `xgboost` real instalado.
- Uma competição (Copa 2022). Repetir com Euro 2024 e Bundesliga 23/24 para checar estabilidade.
- 12,7% das ações usam a proxy de densidade (correlação 0,45 com o 360).
