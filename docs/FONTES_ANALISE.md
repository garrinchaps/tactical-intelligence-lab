# Análise das fontes de dados — 19/11/2026

Base do PC: **438.007 partidas · 11,4 GB**. Números da tabela do painel 🩺 (Dados & Fontes) enviada pelo Matheus.
Legenda da decisão: **MANTER** (essencial) · **MANTER, SEMANAL** (histórica: não precisa reler todo dia) · **SÓ
MANUAL** (fora da atualização automática) · **CORRIGIDO** (o problema do painel foi resolvido na rodada 19).

| fonte | partidas (lances / estatísticas / só placar) | o que traz | onde é usada no app | situação e decisão |
|---|---|---|---|---|
| **fotmob** | 104.218 (0 / 42.027 / 62.191) | estatísticas com xG/xGOT, escalação com posição exata, números por jogador (nota, xA, chances, duelos…), mapa de chutes, momentum, desfalques, elenco atual com idade/valor | Scout, Rankings, Escalação/Próximo jogo, IA do laboratório, página do jogo sem lances, Comparar | **MANTER — a mais importante hoje.** "Nunca sincronizada" era defeito do painel: as partidas são gravadas como `fotmob`, mas as tarefas se chamam `fotmob_jogos`/`fotmob_temporada` → **CORRIGIDO** (painel junta as tarefas). **Achado grave corrigido:** os números por jogador vêm sem posição (só o goleiro); agora a posição sai da escalação do mesmo jogo — por isso jogadores da Série B/C e das ligas sul-americanas não apareciam no Scout |
| **openplay** | 26.547 (26.547 / 0 / 0) | lances com coordenadas (eventos) de ligas europeias e outras | página do jogo (xT, redes de passe, mapas), rede neural de perigo, jogo típico | **MANTER, SEMANAL.** O erro "nenhuma tabela de jogos em C:\dados\openplay" é ANTIGO (depois funcionou 5 de 6 vezes); o painel agora mostra a data e "[antigo — depois funcionou]". A release não muda: reler 0,94 GB todo dia só pesava |
| **statsbomb** | 3.961 (3.961 / 0 / 0) | lances completos (Copa 2022, ligas abertas, 360 em parte) | jogo, rede neural, Assistente, matéria (Bastidores) | **MANTER, SEMANAL** — base aberta estática no disco (`C:\dados\statsbomb`) |
| **wyscout** | 1.941 (1.941 / 0 / 0) | lances das 5 grandes ligas 17/18 + Copas | jogo, rede neural | **MANTER, SEMANAL** — estática |
| **espn** | 23.150 (0 / 1.594 / 21.556) | resultados e **próximos jogos** de 52 ligas, escalação OFICIAL ~1 h antes, notícias, lesões | Próximo jogo, calendário, desfalques, busca | **MANTER.** Erro `'id'` = a ESPN mandou um item sem identificador e a tarefa inteira caía → **CORRIGIDO** (item sem id é pulado) |
| espn_elencos | — | elenco atual + lesões | desfalques na Escalação | **MANTER (diária)** |
| espn_temporada / espn_resumos / espn_historico | — | cargas manuais (temporada inteira, resumos antigos, histórico) | — | **SÓ MANUAL** — "desatualizada" é normal: a tarefa automática `espn` já busca a temporada do ano + resumos da última semana |
| **fdcouk** (football-data.co.uk) | 126.293 (0 / 59.227 / 67.066) | 1993–hoje, ~38 ligas: chutes, no alvo, escanteios, faltas, cartões, odds | histórico de times, estilo/tendências, busca, jogos parecidos | **MANTER.** "database is locked" = duas gravações ao mesmo tempo (processo de fundo × sincronização do painel) → **CORRIGIDO** (espera 20 s e 40 s e tenta de novo) |
| **transfermarkt** (dcaribou) | — (tabelas no lake) | 50 mil jogadores, valores, clubes, transferências, escalações | Scout (valor, idade, contrato), elenco, vínculo jogador-clube | **MANTER (diária)** |
| **lake** | — | monta os parquet (data/lake) a partir das fontes | Escalação, Scout (`squad/data.py`) | **MANTER (diária)** |
| **brasileirao** (adaoduque) | 8.785 (0 / 3.410 / 5.375) | Brasileirão 2003–hoje com estatísticas em parte | histórico de clubes brasileiros | **MANTER, SEMANAL** |
| **openfootball** | 89.781 (0 / 1 / 89.780) | resultados históricos (CC0) | busca, retrospecto, PageRank das competições | **MANTER, SEMANAL** — só placar, mas é o que completa o histórico |
| **intl** | 50.102 (0 / 0 / 50.102) | resultados de seleções | busca, retrospecto de seleções | **MANTER.** "Nunca sincronizada" era o painel procurando uma tarefa `intl` que não existe (quem grava é `open_sources`) → **CORRIGIDO** |
| **open_matchday** (OpenLigaDB) | 3.105 (0 / 1.812 / 1.293) | Alemanha (resultados + gols) | busca, histórico | **MANTER** |
| **open_sources** | 0 próprias | lista de arquivos abertos (config) → grava `intl` e tabelas do lake | — | **MANTER, SEMANAL** |
| **simonetti** | 0 próprias | dados das Copas (wc_data) + notas externas de jogadores | Scout (nota externa, 18% no máximo), Dados & Fontes | **MANTER, SEMANAL** |
| **understat** | 0 | xG por chute das 5 grandes ligas | (ligação com o lake, quando houver) | **MANTER, SEMANAL — mas o SITE CONTINUA FORA DO AR** (conferido hoje: "We will come back soon"). Não é defeito do PC |
| **estatisticas_brasil** | 0 | estatísticas do Brasileirão via API-Football | — | **SÓ MANUAL.** Gastava cota e não trouxe nada; a FotMob já cobre o Brasileirão com xG |
| **api_football** | 116 (0 / 116 / 0) | só temporadas 2022–2024 no plano grátis, 100 pedidos/dia | complemento de poucos jogos | **SÓ MANUAL.** Era consultada a cada 3 h atrás de jogos recentes que o plano grátis não libera (3 erros de cota) |
| **cbf** | 0 | resultados oficiais (arquivos locais) | — | **SÓ MANUAL.** Os jogos já existem nas outras bases (mesma data + mesmos times = mesma partida): não acrescenta nada novo |
| **simulated** | 8 | partidas geradas para testes | NUNCA entram nas análises reais (filtro `REAL_SQL`) | sem impacto; o painel agora mostra "🧪 exemplos internos" |

## O que estava atrapalhando o programa

1. **Bases históricas relidas todo dia** (StatsBomb, Wyscout, OpenPlay, openfootball, Brasileirão, Simonetti, Understat…):
   minutos de disco e CPU por dia e mais chance de "database is locked". Agora rodam **1× por semana**.
2. **API-Football a cada 3 h** sem poder trazer nada (plano grátis): saiu do automático.
3. **Posição vazia nos números da FotMob**: Scout sem os jogadores de Série B/C e América do Sul. Corrigido.
4. **ESPN caindo inteira por um item sem id**: corrigido.

## Nova agenda automática (`src/data_hub/autosync.py`)

| ritmo | fontes |
|---|---|
| a cada ~3 h | espn, fdcouk, open_matchday, football_data (+ FotMob contínua, em lotes) |
| diário | espn_elencos, transfermarkt, lake |
| semanal | statsbomb, wyscout, openplay, openfootball, brasileirao, open_sources, understat, api_futebol, basedosdados, simonetti |
| só manual | api_football, estatisticas_brasil, cbf, espn_historico, espn_temporada, espn_resumos |
