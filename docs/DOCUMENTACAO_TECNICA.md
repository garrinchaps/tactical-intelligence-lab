# Tactical Intelligence Lab — Documentação técnica

Versão do código descrita: branch `claude/gifted-knuth-q93cbz`, rodada 27i (24/11/2026), 558 testes automatizados.
Tudo aqui está no repositório. O que não foi construído aparece como **lacuna** ou **próximo passo**, nunca como pronto.

---

## 1. Resumo executivo

**O que é.** Uma plataforma pessoal de análise de futebol. Junta dados abertos de várias fontes numa base única
(~300 mil partidas, ~32 mil com todos os lances e coordenadas, ~134 mil com estatísticas da partida, ~67 mil jogadores
no mercado do Scout). Em cima dessa base funcionam três coisas:

1. **Análise de partida e de time.** Lances, xT (ameaça esperada), redes de passe, mapas, pontos fortes e fracos,
   identidade tática, padrões e histórico.
2. **Assistente tático.** Responde em português perguntas sobre um jogo. Usa os números conferidos daquele jogo,
   raciocina cruzando métricas e diz o que a fonte não mede.
3. **Scout e Escalação.** Overall 0–100 e potencial dos jogadores, carências do clube, alvos realistas pela verba,
   próximo jogo (provável escalação, confrontos, onde atacar) e algoritmo genético de escalação.

**Problema que resolve.** As fontes gratuitas estão espalhadas, com nomes diferentes para o mesmo time ou jogador, e
com níveis de detalhe diferentes: lances, só estatísticas, só placar. Ferramentas comerciais (Opta, Wyscout,
StatsBomb pago) custam caro. O projeto unifica essas fontes, mede o que dá para medir com honestidade (lacuna nunca
vira zero, estimativa sempre marcada) e entrega leitura tática em linguagem de futebol.

**Princípio central — honestidade técnica.** Nenhum número é inventado. Cada número de uma resposta do Assistente é
conferido contra os dados (`src/guard/present.py`). Associação não é apresentada como causa, e o que a fonte não mede
é dito explicitamente.

**Evolução, resumida em fases:**

| Fase | Entregas principais |
|---|---|
| Base (v35 → rodada 3) | Conectores StatsBomb, Wyscout, football-data, ESPN, Transfermarkt, openfootball; SQLite com níveis de dado; página de jogo com xT e redes de passe; Assistente com blocos táticos |
| Rodadas 4–9 | FotMob (estatísticas, xG, números por jogador, mapa de chutes); nota 2.0 por função; Escalação com próximo jogo; IA do laboratório (seletor treinável por 👍/👎); algoritmo genético; API + site React |
| Rodadas 10–19 | Separação masculino × feminino; Scout (mercado, viabilidade, joias, plano de janela); processo de fundo; Rankings; velocidade (índices, caches, catálogo em memória); publicação por túnel com senha |
| Rodadas 20–27 | Overall 0–100 calibrado com referências; potencial; seleções de base e principal; identidade tática; pré-jogo com confrontos e probabilidades; motor de interpretação do Assistente; correções de lentidão |

---

## 2. Stack tecnológica e ferramentas

### 2.1 Linguagens e execução
| Item | Papel |
|---|---|
| **Python 3.15** | Toda a análise, os conectores, a interface Streamlit e a API |
| **TypeScript + React 19 + Vite 8** | Site separado (`apps/web`) com painéis da IA |
| **PowerShell** | Scripts do Windows: `atualizar_tudo.ps1`, `apresentar.ps1`, `agendar_atualizacao.ps1` |
| **SQL (SQLite)** | Consultas da base principal |

### 2.2 Dados e armazenamento
| Biblioteca | Papel |
|---|---|
| **SQLite (WAL)** via `sqlite3` | Base principal (`database/tactical_lab.db`, ~19 GB no PC): partidas, lances, estatísticas, escalações, números por jogador, chutes, elencos, estados de sincronização |
| **pandas / numpy** | Tratamento de dados, métricas, réguas |
| **pyarrow / parquet** | Lake de dados (`data/lake`), cópia do catálogo e índice de jogadores |
| **DuckDB** | Consultas analíticas sobre o lake |
| **pickle (pandas)** | "Fotografia" do mercado do Scout (`data/processed/scout_universe_vNN.pkl`) |

### 2.3 Análise, estatística e aprendizado de máquina
| Biblioteca | Papel |
|---|---|
| **scipy** | Distribuições (probit do overall), Poisson + Dixon-Coles nas probabilidades de placar, algoritmo húngaro (melhor XI) |
| **scikit-learn / xgboost** | Linhas de base e comparação de modelos (Bastidores › ML) |
| **MLP próprio em NumPy** (`src/machine_learning/neural_net.py`) | Rede de "perigo da posse": Adam, parada antecipada, validação por partida (GroupKFold) |
| **Regressão logística própria** (`src/intelligence/lab_ai/selector.py`) | Seletor de fatos do Assistente, treinado com 👍/👎 |
| **Lógica fuzzy (Mamdani/Sugeno)** | Índice de exploração de confrontos e material didático (`src/intelligence/course.py`) |
| **Algoritmo genético** (`src/squad/genetic.py`) | Escalação com torneio, cruzamento com reparo, mutação e elitismo |
| **networkx / shapely** | Redes de passe e geometria em campo |

### 2.4 Visualização e interface
| Biblioteca | Papel |
|---|---|
| **Streamlit 1.67** | Aplicação principal (`app.py`), com navegação, abas sob demanda, fragmentos e cache |
| **plotly** | Gráficos interativos e campinhos |
| **mplsoccer / matplotlib** | Mapas de campo (padrão StatsBomb 120×80) |
| **reportlab** | Dossiê do Scout em PDF |

### 2.5 Backend do site
| Biblioteca | Papel |
|---|---|
| **FastAPI + uvicorn** (`apps/api/main.py`) | API REST somente leitura |
| **PyJWT** | Autenticação da API (`apps/api/auth.py`) |

### 2.6 Rede e fontes de dados
| Fonte | Tipo de dado | Observação |
|---|---|---|
| StatsBomb Open Data | Lances com coordenadas | Copas, ligas selecionadas |
| Wyscout (aberto 17/18) | Lances | 5 ligas + Copas |
| OpenPlay | Lances | 26,5 mil jogos |
| FotMob (JSON público) | Estatísticas, xG/xGOT, números por jogador, chutes, escalações, elencos | Principal fonte do Brasil e de ~110 competições; uso pessoal |
| ESPN (JSON público) | Resultados, estatísticas, elencos, escalação oficial | Só aceita dia/mês/ano |
| Transfermarkt (dataset dcaribou) | Cadastro, valores, transferências | Pode estar atrasado em relação ao mercado real |
| football-data.co.uk, openfootball, intl, Brasileirão Dataset, open-matchday, CBF | Placar e estatísticas básicas | Histórico longo |
| Wikidata | Nascimento de jogadores | Completa idades |
| API-Football (grátis) | Estatísticas 2022–2024 | 100 pedidos/dia, só manual |

Rede: **httpx**, com tempo limite de 15 s, novas tentativas e cabeçalhos ASCII (`src/data_hub/net.py`).
**Proibidos no projeto:** `pyyaml`, `bs4`. Não há raspagem de sites que bloqueiam robôs (FBref, Sofascore etc.).

---

## 3. Arquitetura e funcionamento

### 3.1 Visão geral

```
 FONTES ABERTAS ─────────────────────────────────────────────────────────────┐
 StatsBomb · Wyscout · OpenPlay · FotMob · ESPN · Transfermarkt · fdcouk ...   │
                                                                             ▼
 ┌──────────────────────── INGESTÃO (src/data_hub/sources, sync.py) ─────────────────────────┐
 │ conectores → validação (quality.py) → upsert sem rebaixar nível → consolidação entre fontes│
 │ (mesma data ±1 dia + mesmos times; divergências registradas, nunca viram média)            │
 └───────────────────────────────────────┬───────────────────────────────────────────────────┘
                                         ▼
 ┌──────────── BASE (SQLite WAL) ─────────────┐     ┌──── LAKE (parquet + DuckDB) ────┐
 │ matches · events · match_team_stats ·      │     │ Transfermarkt, valores,          │
 │ match_player_stats · match_lineups ·       │     │ transferências, Understat...     │
 │ match_shots · match_timeline · rosters     │     └─────────────────────────────────┘
 └───────────────┬────────────────────────────┘
                 ▼
 ┌──────────────── ANÁLISE ─────────────────────────────────────────────────────────────────┐
 │ métricas e xT (src/metrics) · rede de perigo (ML) · identidade tática (src/analytics)    │
 │ Scout: universo → overall/potencial → fotografia (src/scout)                             │
 │ Assistente: entende a pergunta → monta fatos → raciocina → confere números (src/intelligence)│
 └───────────────┬──────────────────────────────────────────────────┬───────────────────────┘
                 ▼                                                  ▼
       APP STREAMLIT (app.py)                              API FastAPI (apps/api) → site React (apps/web)
```

Um **processo de fundo** (`src/data_hub/worker.py`, prioridade baixa) atualiza resultados, detalhes da FotMob,
a fotografia do Scout e as réguas. Ele espera a tela ficar parada antes de qualquer trabalho pesado.

### 3.2 Motor de dados e análise, passo a passo

1. **Coleta.** Cada conector baixa jogos de uma fonte. `sync.py` permite rodar `--only fonte`, por ligas e por
   temporadas; `atualizar_tudo.ps1` roda só os passos vencidos (`src/tools/passos.py`).
2. **Níveis de dado.** Cada partida recebe um nível: `EVENTS` (lances com coordenadas), `BOXSCORE` (estatísticas),
   `RESULT` (só placar), `SIMULATED`/`UPLOAD`. O nível nunca é rebaixado por uma fonte mais pobre.
3. **Identidade.**
   - **Times:** apelidos aprendidos entre fontes (`team_alias.py`); homônimos separados pelo país das ligas
     (`gender.comp_sql`, `foreign_competitions`); masculino separado de feminino.
   - **Jogadores:** juntados pelo id da FotMob, pelo clube e pela idade (`engine.assign_person_ids`,
     `match_market_to_history`, `merge_club_aliases`). Nunca só pelo nome.
4. **Tratamento dos lances.** Limpeza (`src/preprocessing`) e coordenadas no padrão 120×80, com ataque para a direita.
5. **Métricas.**
   - xT por zona (`src/metrics/xt_model.py`), redes de passe, corredores, pressão (PPDA real com lances, aproximado sem).
   - Pontos fortes e fracos contra a régua da base (percentil contra o "jogo típico").
   - Nota 2.0 por função, por lances ou por estatísticas.
6. **Rede de perigo da posse.** Um MLP estima a chance de cada posse virar finalização perigosa. É validado por
   partida e promovido só se vencer o modelo anterior no teste.
7. **Scout.** O universo de jogadores une histórico de jogos, cadastro e elenco atual, e depois calcula:
   - **Overall:** reputação (log do valor, padronizado por posição), desempenho na função, nota FotMob ajustada pela
     liga e nível da liga. Depois vem a régua global pela colocação, a correção calibrada com notas de referência e
     ajustes explicados (idade, goleiros, Brasil, minutos).
   - **Potencial:** idade × talento, seleção de base e principal, topo pela colocação.
   - **Atributos 1–100** medidos na função.

   Tudo isso é salvo como "fotografia", refeita a cada 6 h.
8. **Saídas.** Telas, relatórios (olheiro do jogador e do time, relatório da IA do jogo) e dossiê PDF.

### 3.3 Assistente tático (a "IA do laboratório")

```
pergunta ─► localizar o jogo ─► (trava: o chat fica no jogo aberto; só troca com "A x B" + ano, placar,
            (match_locator)      "último jogo", ou "trocar de jogo")
       │
       ├─► intenção (query_understanding) + evidências do jogo (scoped_evidence)
       ├─► RACIOCÍNIO (lab_ai/reasoning.py) ── 27 tipos de pergunta interpretativa:
       │      posse × controle, qualidade das finalizações, no gol, dentro/fora da área, bloqueadas, grandes chances,
       │      eficiência (xG + simulação das chances), passes, bolas longas, cruzamentos, escanteios, dribles,
       │      faltas (hipóteses ordenadas), desarmes × interceptações, aéreo, formações, substituições, quem mereceu,
       │      sem olhar o placar, contradições, correlação × causa, erros de leitura, dados ausentes, risco,
       │      estado do jogo, HISTÓRIA DO JOGO (virada, gols rápidos) e CONSELHO AO TREINADOR
       ├─► roteador de intenções (lab_ai/router.py): próximo jogo, desfalques, melhor jogador, substituições...
       ├─► número direto (lab_ai/direct.py): "quem errou mais passes?" → ranking por jogador
       └─► analista clássico (dynamic_analyst.py): presença, autores dos gols, escalação
       ▼
 conferência dos números (guard/present.py) ─► resposta: direta → números → leitura → limite do dado
 👍/👎 ─► lab_brain / trainer ─► novo treino do seletor (promovido só se errar menos na prova)
```

**O que o treino da IA muda hoje (limite honesto).** O 👍/👎 treina o *seletor de fatos*, ou seja, a escolha de quais
números aparecem primeiro, e reordena tipos de análise (`lab_brain`). A qualidade do raciocínio vem das regras de
`reasoning.py`. Pergunta que nenhum raciocínio reconhece cai no analista genérico, e o treino não ensina um raciocínio
novo. Os 👎 e as perguntas "sem alvo" (`data/assistente_sem_alvo.jsonl`) servem de lista do que falta implementar.
Ver §5 (próximos passos).

### 3.4 Aplicação web

**App principal (Streamlit, `app.py`):**
- O usuário abre `streamlit run app.py`, ou um link por túnel com senha (`apresentar.ps1`).
- A navegação é escondida, com páginas principais (Assistente, Buscar, Comparar, Escalação, Scout, Rankings) e
  telas de foco (jogo, time, jogador, competição) com "← Voltar".
- Cada tela lê a base pelo serviço (`MatchDataService`) com caches:
  - catálogo em memória por processo;
  - versão por time;
  - caches em disco para análises pesadas;
  - abas montadas só quando abertas.
- Downloads pedidos pela tela vão para segundo plano (`src/ui/bg_fetch.py`). Pré-aquecimentos cedem a vez à página
  aberta (`src/ui/busy.py`).
- Acesso: localhost entra direto. Visitante pelo túnel precisa de senha ou conta (`src/ui/gate.py`, `accounts.py`).

**Site separado (React, `apps/web`) + API (FastAPI, `apps/api`):**
- Endpoints, todos somente leitura:
  - `/api/v1/matches`, `/api/v1/matches/{id}/report`
  - `/api/v1/ai/lab/ask`, `/api/v1/ai/genetic/lineup`
  - `/api/v1/ai/fuzzy/player`, `/api/v1/ai/fuzzy/pressure`
  - `/api/v1/models`, `/api/v1/sources`, `/api/v1/me`, `/healthz`, `/readyz`
- O frontend (`App.tsx`, `LabPanels.tsx`, `api.ts`) mostra assistente, relatório e escalação genética.
- **Lacuna:** o site não tem todas as telas do app e **não está publicado**. O caminho recomendado para um site
  idêntico é publicar o próprio app Streamlit, ver `docs/PLANO_PUBLICACAO.md`.

---

## 4. Funcionalidades disponíveis

### Buscar
- Jogo, time, jogador ou competição numa caixa só, com filtro de nível de dado (lances, estatísticas ou só placar).
- A mesma partida vinda de duas fontes aparece uma vez só.

### Página do jogo
- Placar, linha do tempo e selo de profundidade do dado.
- Com lances: xT, redes de passe (XI ou com quem entrou), mapas de passes e chutes, corredores, pressão, perigo pela
  rede neural, jogadores com nota 2.0 e radar.
- Só com estatísticas: "O jogo pelos dados da FotMob" (momentum, corredores, mapa de chutes), notas, fortes e fracos.
- Padrões e histórico: bola parada, impacto das substituições, estado do jogo, jogos parecidos.
- Relatório da IA (plano, fases, destaques).

### Assistente
- Perguntas livres sobre o jogo, incluindo duas perguntas na mesma mensagem.
- Raciocínio interpretativo nos 27 tipos listados em §3.3.
- Rankings por jogador, como anular um jogador, quem jogou melhor, substituições sugeridas, próximo jogo e desfalques.
- Trava do jogo da conversa.
- 👍/👎 com motivo e treino guiado (Bastidores › 🎓 Treinar a IA).

### Time
- Painel (classificação, calendário, próximo jogo, estatísticas com colocação).
- Jogos, relatório do olheiro, estilo e tendências.
- Identidade tática por fase (desenho, saída com 3, PPDA, altura do bloco, transições).
- Elenco e valores; temporada (xG).

### Jogador
- Visão geral estilo FM: overall, potencial, estrelas, atributos 1–100, radar, prós e contras, "de onde vem o overall".
- Seleção de base, jogos (lances ou FotMob/ESPN), scout por 90, carreira (Transfermarkt), perfil e valor.

### Comparar
- Jogador × jogador (qualquer um com dados, recorte de jogos) e jogo × jogo.

### Escalação
- Provável, melhor possível e contra o adversário, com 16 formações e campinho de arrastar.
- Próximo jogo:
  - provável dos dois lados, lesões, suspensões e escalação oficial da ESPN perto do jogo;
  - confrontos meu time × rival (forçar, proteger, evitar) e "onde atacar" e "onde sofremos" no campinho;
  - probabilidades de placar, modelo de jogo do rival e relatório do olheiro do rival.
- Jogo hipotético contra qualquer time, algoritmo genético e entrosamento.

### Scout
- Carências do clube, Top 5 da IA e sugestões por perfil (🌱 promessas, 📈 investir, ⭐ chegar e jogar), pela verba.
- Busca manual com muitos filtros: posição, idade, qualidade, potencial, valor, origem, liga, clube, nacionalidade.
- Joias U23, empréstimos, janela de transferências e plano com campinho.
- Dossiê (tela e PDF) e 👍/👎 por sugestão.

### Rankings
- Avaliação por competição e geral entre ligas: desempenho/90, temporada, regularidade, impacto, contra fortes,
  potencial, custo-benefício.

### Bastidores
- Painel de fontes e sincronização, velocidade do app e treino da IA (guiado e técnico).
- Matéria (fuzzy, redes, algoritmo genético, com exemplos do próprio app), contas e diagnóstico.

### Ferramentas de linha de comando
| Comando | Para quê |
|---|---|
| `scripts/atualizar_tudo.ps1` | Atualiza tudo o que venceu, em ordem |
| `python -m src.tools.diagnostico_lentidao` | Mede a velocidade na base real |
| `python -m src.tools.limpeza` | Limpa caches e lixo sem apagar dados |
| `python -m src.tools.onde_esta "Nome"` | Explica por que um jogador não aparece |
| `python -m src.tools.cobertura_scout` | Cobertura do Scout por liga |

---

## 5. Lacunas conhecidas e próximos passos

- **Assistente:** o treino ajusta a ordem dos fatos, mas não cria raciocínio novo. Próximo passo: transformar as
  perguntas com 👎 em casos de teste e em regras ou exemplos novos de `reasoning.py`. Opcionalmente, ligar um modelo
  de linguagem como redator, mantendo a conferência de números (hoje o Gemini existe, mas vem desligado).
- **Dados:**
  - Nenhuma fonte aberta tem lances com coordenadas do Brasileirão nem dados físicos de rastreamento.
  - Valores e elencos do Transfermarkt aberto podem estar atrasados.
  - Jogador sem cadastro e sem elenco FotMob fica sem idade, país e valor (lacuna, não zero).
- **Site:** o React cobre só parte das funções e não está publicado.
- **Traduções:** o espanhol está incompleto.
- **Prováveis escalações por notícia:** não existe em fonte aberta acessível.
