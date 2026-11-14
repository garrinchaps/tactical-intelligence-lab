# Modelos de arquivo de scout (ScoutFileParser)

Valores **fictícios**, apenas para mostrar o formato. Preencha com dados que você tem direito de usar.

| Arquivo | Colunas obrigatórias | Domínio |
|---|---|---|
| `xt_zonas_modelo.csv` | equipe, zona_x, zona_y, xt (partida opcional) | zona_x 1–12, zona_y 1–8, xt 0–1 |
| `matriz_passes_modelo.csv` | equipe, passador, receptor, passes (partida opcional) | passes inteiro ≥ 0 |
| `metricas_equipe_modelo.csv` | partida, equipe, ppda (+ outras métricas numéricas) | ppda > 0 |

Aceita separador `,` ou `;`, decimal com vírgula ou ponto, `.csv`, `.json` (`{"tipo": "...", "dados": [...]}`) e `.xlsx` (uma aba por tipo, com o tipo no nome da aba).
