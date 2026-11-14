# Validação qualitativa

Objetivo: verificar se os achados do sistema coincidem com o que analistas humanos publicaram sobre as mesmas
partidas. **O critério é fixado antes de rodar o sistema**, para não escolher depois o que “confirma”.

## Critério prévio (preencher e datar antes de abrir o sistema)

- **Partidas** (2–3, com eventos StatsBomb e cobertura analítica pública):
  1. Argentina 3 x 3 França — final da Copa 2022 (`3869685`)
  2. Argentina 3 x 0 Croácia — semifinal da Copa 2022 (`3869519`, disponível offline)
  3. França 2 x 0 Marrocos — semifinal da Copa 2022 (`3869552`, disponível offline)
  Alternativas com download: Argentina 1 x 2 Arábia Saudita (`3857300`), Marrocos 1 x 0 Portugal (`3869486`).
- **Fontes humanas** (públicas, anteriores ao uso do sistema): relatório técnico da FIFA (Technical Study Group),
  análises táticas publicadas em veículo especializado. Registrar link e data de acesso.
- **Afirmações comparáveis** (extrair 4–6 por partida, antes de ver o sistema): ex. “a França pressionou mais
  depois dos 70 minutos”, “a Croácia teve mais posse e pouca progressão”, “Marrocos defendeu em bloco baixo”.
- **Regra de correspondência:** o sistema confirma uma afirmação quando a métrica correspondente (PPDA,
  altura média das ações defensivas, field tilt, xT por zona, clusters) se move no sentido descrito em relação
  ao restante da partida, no mesmo recorte de tempo.

Data de fixação do critério: ____ / ____ / ______  Responsável: __________________

## Registro

| Partida | Afirmação do analista (fonte) | Métrica do sistema | Valor (recorte × resto) | Resultado |
|---|---|---|---|---|
| | | | | CONFIRMADO / NÃO CONFIRMADO / NÃO MENCIONADO |

- **CONFIRMADO** — a métrica se move no sentido descrito.
- **NÃO CONFIRMADO** — a métrica contradiz ou não se move.
- **NÃO MENCIONADO** — o sistema não tem métrica para a afirmação (ex.: aspectos sem dado de tracking).

## Resumo

Total de afirmações: __ · confirmadas: __ · não confirmadas: __ · não mencionadas: __

Os casos NÃO CONFIRMADO entram na apresentação: mostram o limite das métricas de eventos.
