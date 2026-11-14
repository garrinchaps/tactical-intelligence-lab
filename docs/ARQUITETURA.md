# Arquitetura — Tactical Intelligence Lab

Documento de referência da versão 19: mapa dos módulos, schema canônico, fluxo de proveniência e as decisões
tomadas quando a especificação e o código existente entravam em conflito.

## 1. Mapa do sistema

```
                 ┌───────────── FONTES ─────────────┐
 StatsBomb Open Data (+360) · Wyscout Public (CC BY 4.0) · football-data.co.uk (CSV) · API-Football · football-data.org · ESPN (off)
 arquivos do analista (CSV/JSON/XLSX) · catálogo config/competitions.yaml · gerador simulado
                 └──────────────────┬───────────────┘
                                    ▼
 src/connectors/   StatsBombConnector · WyscoutConnector · APIConnector · ScoutFileParser · CompetitionCatalog
                   EmpiricalFallback (bootstrap B=100) · SimulationUncertainty
                                    ▼
 src/canonical/    schema.py  → CANONICAL_EVENT_SCHEMA / CANONICAL_AGGREGATE_SCHEMA + validate()
                   provenance.py → ProvenanceRecord / ProvenanceRegistry (modo estrito TIL_STRICT_PROVENANCE=1)
                                    ▼
 src/data_hub/     SQLite local (database/tactical_lab.db, não versionado), busca universal, sync incremental
                                    ▼
 cálculo           preprocessing · geometry · metrics (PPDA, field tilt, xT) · networks (NetworkX)
                   machine_learning (XGBoost, K-Means, DBSCAN, rede neural NumPy) · evaluation (protocolo)
                                    ▼
 linguagem         intelligence (recorte da pergunta → evidências) → Gemini opcional
                   guard/ (extrator → ground truth → EXATO/DERIVADO/CONSTANTE/NÃO RASTREÁVEL → política)
                                    ▼
 interface         app.py (st.navigation) → src/ui/pages/* · components (proveniência obrigatória) · charts (Plotly)
```

### Páginas

| Grupo | Página | Arquivo |
|---|---|---|
| Partida | 1 · Centro da Partida | `src/ui/pages/match_center.py` |
| Partida | 2 · Redes de Passes & xT | `src/ui/pages/networks.py` |
| Inteligência Artificial | 3 · Machine Learning & Inspeção | `src/ui/pages/ml_inspection.py` |
| Inteligência Artificial | 4 · Rede Neural do Zero | `src/ui/pages/neural.py` |
| Inteligência Artificial | 8 · Analista IA | `src/ui/pages/ai_analyst.py` |
| Jogadores, Clube e Comparações | Comparações | `src/ui/pages/compare.py` |
| Jogadores, Clube e Comparações | 5 · Jogadores | `src/ui/pages/players.py` |
| Jogadores, Clube e Comparações | 6 · Clube & Temporada | `src/ui/pages/club.py` |
| Jogadores, Clube e Comparações | 7 · Pontos Fortes e Fracos | `src/ui/pages/strengths.py` → `src/visualization/strengths_page.py` |
| Dados | 9 · Catálogo & Dados | `src/ui/pages/catalog.py` |
| Dados | Laboratório | `src/ui/pages/lab.py` |

Toda página abre com `page_header` (partida, competição, fonte, tier e equipe em foco) e termina com
`provenance_panel`, que lista a origem de cada número exibido. `metric_card`, `kpi` e `stat_pill` exigem um
`ProvenanceRecord`: em modo estrito, um número sem origem levanta `MissingProvenanceError`.

## 2. Schema canônico

### Eventos (`CANONICAL_EVENT_SCHEMA`)

| campo | tipo | domínio | nulo |
|---|---|---|---|
| match_id | texto | ID da fonte | proibido |
| team_id | texto | nome/ID da equipe | proibido |
| player_id | texto | atleta | permitido (eventos sem atleta) |
| event_type | texto | passe, condução, finalização, pressão, recuperação, drible, falta, outro | proibido |
| minute | inteiro | 0–130 | proibido |
| second | inteiro | 0–59 | proibido |
| x | float | 0–120 (sistema StatsBomb) | proibido |
| y | float | 0–80 | proibido |
| event_outcome | texto | sucesso, falha, nulo | proibido |
| score_state | texto | "casa-fora" no momento do evento | proibido |
| source, connector, license, ingestion_timestamp, confidence_tier | texto | tier ∈ OFFICIAL, DERIVED, SIMULATED | proibido |

### Agregados (`CANONICAL_AGGREGATE_SCHEMA`)

`match_id, team_id, entity, metric, value, ci_low, ci_high` + os mesmos cinco campos de proveniência. Usado por
boxscore (APIConnector), arquivos de scout (ScoutFileParser) e estimativas simuladas (EmpiricalFallback →
tabela `simulated_estimates`).

### Tiers

- **OFFICIAL** — valor como publicado pela fonte (eventos StatsBomb/Wyscout, boxscore da API).
- **DERIVED** — calculado pelo laboratório a partir de dado oficial (PPDA, xT, centralidade, percentis, arquivos do analista).
- **SIMULATED** — gerado por modelo. Sempre com selo, gerador nomeado e, quando há reamostragem,
  “IC 95% da reamostragem, condicionado à distribuição empírica de referência”.

## 3. Conflitos entre a especificação e o código, e como foram resolvidos

| # | Conflito | Decisão |
|---|---|---|
| 1 | O schema pede `match_id` texto; o banco usa inteiros com prefixo por fonte | Canônico em texto; o pipeline interno mantém o inteiro. A conversão é feita só em `to_canonical_events`. |
| 2 | `event_type` em português vs. tipos StatsBomb usados por todas as métricas | O canônico é uma **visão** validada; as métricas continuam sobre os tipos StatsBomb para não reescrever módulos testados. |
| 3 | Conectores de boxscore não têm eventos | Entregam o schema de agregados, com o mesmo bloco de proveniência. |
| 4 | “SimonettiParser”: o formato dos arquivos da Simonetti não é público | Implementado como `ScoutFileParser` genérico (xT por zona, matriz de passes, métricas de equipe) com modelos em `data/templates/`. Ajustar os aliases de coluna com um arquivo real. |
| 5 | XGBoost não instalável no ambiente de desenvolvimento | O código usa `xgboost.XGBClassifier`; sem a biblioteca, um substituto (GradientBoosting) é usado **e declarado** no relatório e na tela. O relatório oficial deve ser regerado no computador do projeto. |
| 6 | Alvo do grafo (“progressão ao terço final”) não tinha definição operacional | Rede do 1º tempo; alvo = a posse chega a x ≥ 80 depois do toque do atleta no 2º tempo. |
| 7 | Validação qualitativa exige relatórios de analistas | Protocolo e tabela prontos em `docs/VALIDACAO_QUALITATIVA.md`; o preenchimento depende de fontes públicas escolhidas antes de rodar o sistema. |
| 8 | Banco SQLite não versionado vs. demo offline | Três partidas e uma amostra de treino em `data/demo/` (1,3 MB) garantem que a apresentação funcione sem internet. |
| 9 | Gerador simulado com PPDA irreal (~217) | Camada defensiva calibrada pela Copa 2022 (0,316 ação defensiva por passe; 69% pressões). PPDA simulado 2,7–3,0; chutes e acerto de passe ainda acima/abaixo do real — limitação documentada. |
| 10 | Pedido de raspar Sofascore, Flashscore, 365Scores, Oddspedia, Opta e Simonetti Stats | Não implementado: os termos de uso desses serviços proíbem coleta automatizada (Sofascore, Flashscore, 365Scores) ou os dados são licenciados (Opta/Stats Perform; a Simonetti usa provedores não nomeados). Em troca, entrou o football-data.co.uk, cujos CSVs são distribuídos gratuitamente, e o ScoutFileParser aceita planilhas exportadas pelo próprio usuário. |
| 11 | Masculino × feminino misturados no catálogo | Coluna `genero` derivada do campo da StatsBomb e, sem ele, do nome da competição/equipes (`src/data_hub/gender.py`); filtro na barra lateral e nas comparações. |

## 4. Base unificada (data/lake) e mapeamento de IDs

```
StatsBomb (clone local ou web) ─┐                      ┌─ dim_teams   + team_ids   (team_key ↔ id de cada fonte)
Wyscout · football-data.co.uk ──┤                      ├─ dim_players + player_ids (player_key ↔ id de cada fonte)
API-Football (+ classificação, ─┤   IdentityResolver   ├─ match_links (mesma partida em fontes diferentes)
  calendário) · API-Futebol ────┼──────────────────────┤
Understat (xG, finalizações) ───┤  src/data_lake/      ├─ us_*  tm_*  af_*  apf_*  bd_*  (tabelas por fonte)
Transfermarkt (datasets) ───────┤                      └─ Parquet (pyarrow) ou CSV.gz · DuckDB opcional ·
Base dos Dados (BigQuery) ──────┘                         espelho SQLite lake_*
```

| Fonte | O que traz | Acesso | Atualização |
|---|---|---|---|
| StatsBomb Open Data | eventos com coordenadas, 360 | web ou clone local (`STATSBOMB_OPEN_DATA_PATH`) | diária (catálogo) |
| API-Football | resultados, boxscore, escalações, **classificação e próximos jogos** | chave grátis (100 req/dia) | a cada 3 h / diária |
| API-Futebol | tabela, rodadas e partidas do futebol brasileiro | chave (`API_FUTEBOL_KEY`) | diária |
| Understat | xG por partida e por jogador; **cada finalização com posição e xG** (6 ligas) | público | diária |
| Transfermarkt | clubes, jogadores, **valor de mercado** e histórico, jogos com público e árbitro | transfermarkt-datasets (CSV público, semanal) | diária (baixa só se mudou) |
| Base dos Dados | Brasileirão desde 2003: público, árbitro, técnicos, valor dos elencos | BigQuery (`BASEDOSDADOS_BILLING_ID`) | diária |
| football-data.co.uk | resultados e estatísticas de 16 ligas europeias + placares de outras | CSV público | a cada 3 h |

**Regras do mapeamento:** apelidos conhecidos → nome sem acento e sem sufixos (FC, EC, SC…) → semelhança ≥ 0,92 no
mesmo país. Atletas: nome + clube, ou nome + data de nascimento (Transfermarkt); nome completo da StatsBomb casa
com o curto quando primeiro e último nome coincidem no mesmo clube. Sem correspondência segura, a entidade
fica com chave própria (nada é fundido por palpite fraco).

**Fontes não incluídas e por quê:** FBref deixou de publicar métricas avançadas (xG, SCA, GCA, pressões) em
jan/2026, após a Opta encerrar o contrato — o conector pedido não teria esses dados. Sofascore, Flashscore,
WhoScored e 365Scores proíbem coleta automatizada e bloqueiam robôs; WhoScored exibe dados licenciados da Opta.
Simonetti Stats usa provedores pagos não identificados; planilhas exportadas entram pelo ScoutFileParser.

## 5. Interface (v25) e fontes abertas globais

* `app.py`: navegação oculta do Streamlit + barra própria no topo (page_link em pílulas, ⚙️ Bastidores num popover),
  busca global e faixa da partida (`components.match_strip`) com "Trocar partida" (popover com o seletor).
* `src/ui/pages/assistant.py` + `src/intelligence/match_locator.py`: chat único; o localizador lê times (inclusive
  nomes em português) e ano dentro da pergunta e escolhe a versão mais rica do jogo no catálogo.
* `src/ui/crests.py`: bandeiras (flagcdn) para seleções; escudos pela API-Football/Transfermarkt via `team_ids`;
  escudo gerado (SVG) como reserva.
* Fontes abertas: `openfootball` (CC0, `git pull` diário) e `config/open_sources.yaml` (lista de arquivos abertos;
  hoje: resultados, gols e pênaltis de seleções, CC0). A sugestão de um rastreador genérico com rotação de
  User-Agent e varredura de qualquer site com "football"/"stats" no endereço não foi adotada: contornar limites de
  acesso e varrer sites de terceiros sem controle é o que faz sites bloquearem IPs; a lista explícita de fontes
  abertas entrega a escala (≈ 130 mil jogos novos) sem esse risco.
