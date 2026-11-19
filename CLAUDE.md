# CLAUDE.md — Tactical Intelligence Lab (Tactical Vision)

Leia este arquivo inteiro antes de qualquer ação. Ele substitui o histórico das conversas anteriores.

## 1. O projeto

Plataforma pessoal de análise de futebol em Python + Streamlit: assistente tático que responde perguntas com
números conferidos, busca de jogos/times/jogadores, comparação, página de partida (lances, xT, redes de passe,
mapas), pontos fortes e fracos, escalação com plano de jogo, rede neural de "perigo da posse" e um lake de dados
de várias fontes abertas. Usuário: Matheus (Vanessa às vezes faz os pedidos por ele). Fale sempre em **português**,
com linguagem de futebol (não de estatístico).

**Premissa inegociável — honestidade técnica:** nunca inventar dado. Lacuna aparece como lacuna. Valor
desconhecido não vira zero. Toda estimativa diz que é estimativa e como foi feita.

## 2. Ambiente

- Windows 11 Pro · i7-4770 · GTX 1070 8 GB · 16 GB RAM.
- Pasta: `C:\Users\MATHEUS\TACTICAL_INTELLIGENCE_LAB`, venv em `.\venv` (`.\venv\Scripts\Activate.ps1`).
- Python 3.15 · Streamlit 1.67 · pyarrow instalado · `python -m pytest -q` (≈193 testes verdes na v35).
- App: `streamlit run app.py`.
- **Proibido usar `pyyaml` e `bs4`.** Use só: biblioteca padrão, httpx, pandas, numpy, duckdb, pyarrow, pytest
  (e o que já está em `requirements.txt`: scipy, plotly, mplsoccer etc.). Não adicione dependência sem necessidade.
- Visual padrão Football Manager: fundo `#090D16`, cards com borda `#1E2A44`, azul `#22D3EE`/`#3B82F6` para o time em
  foco/mandante, vermelho `#EF4444` para o adversário (`src/ui/theme.py`).

## 3. Regras de segurança (literais do usuário — valem sempre)

- NUNCA imprima, exiba em logs, registre em saídas de texto, inclua em código-fonte, testes, relatórios de execução
  ou mensagens de commit nenhuma chave ou credencial.
- **NUNCA abra, exiba ou altere o arquivo `.env`.** Para saber se uma variável existe, use código que só diga
  "definida/não definida".
- NUNCA adicione o `.env`, arquivos de banco (`*.db`), a pasta `data/` ou `data/lake` em commits.
- ANTES de cada commit, confirme que voltam vazios:
  1. `git ls-files .env`
  2. `git grep --cached -n "AI[z]a"`  (procura o prefixo das chaves Google; no código, escreva-o partido: `"AI" "za"`)
  3. `git ls-files data/lake`
  4. `git ls-files "*.db"`
- NUNCA faça `git push` sem o usuário pedir. Commits locais são ok.
- Se o GitHub bloquear um push por segredo, não libere — avise.
- NUNCA avance com testes falhando.
- Chaves do Gemini e da API-Football já foram expostas num chat antigo; o usuário foi orientado a trocá-las.

## 4. Como trabalhar neste PC (importante)

- **Não rode `python -m src.data_hub.sync` com o app aberto** — o SQLite aceita um gravador por vez e o PC fica lento.
- Antes de pedir para baixar algo, **verifique se já existe** (ver seção 6). Downloads pesados só com motivo claro.
- O usuário sempre roda todos os comandos que você manda. Prefira poucos comandos, explicados em uma linha cada.
- Ao terminar uma etapa: rode `pytest`, faça as 4 conferências, commit local, e diga em linguagem simples o que mudou.

## 5. Mapa do código

- `app.py` — navegação escondida; páginas principais (Assistente, Buscar, Comparar, Escalação) e telas de foco
  (jogo/time/jogador/competição) com pilha "← Voltar" (`src/ui/nav.py`). Barra do topo: uma busca, seletor de
  **nível de dado** (🟢 lances · 📊 estatísticas · 📄 só placar) e "só partidas reais".
- `src/ui/context.py` — cache (`cached_catalog`, `_bundle_parts` → `load_bundle`; o cache guarda só dict/DataFrame,
  nunca objetos), `chosen_levels()`.
- `src/data_hub/db.py` — SQLite (WAL, migrações por `user_version`). `stable_version()`: a interface só adota uma
  versão nova do catálogo 10 min depois da anterior (evita reler 300 mil partidas a cada clique durante um sync);
  gravações feitas pela própria tela invalidam na hora (`_touched`).
- `src/data_hub/service.py` — `MatchDataService.load()`: monta a partida (eventos/estatísticas), junta irmãos de
  outras fontes (`stats_sibling`), redireciona para a versão com lances.
- `src/data_hub/sources/*` — conectores; `src/data_hub/sync.py` (CLI `--only`, `--tudo`, `--desde`, `--ligas`),
  `autosync.py` (QUICK/DAILY, thread `til-autosync`, `AUTO_SYNC` no `.env`).
- `src/data_hub/net.py` — rede: httpx, timeout 15 s, backoff, `ascii_headers` (cabeçalho com acento quebrava tudo).
- `src/data_hub/coverage.py` → `docs/COBERTURA.md` (tamanho real da base, por fonte/competição/temporada).
- `src/data_lake/` — lake em parquet (`data/lake`), espelho opcional no SQLite, DuckDB, camada unificada de ids.
- `src/intelligence/` — `query_understanding.py` (intenção da pergunta), `scoped_evidence.py` (blocos de evidência),
  `dynamic_analyst.py` (redator local + Gemini com disjuntor), `src/guard/present.py` (confere cada número; tags
  [EXATO]/[DERIVADO] nunca aparecem na tela).
- `src/metrics/` — fatos da partida, xT, pontos fortes/fracos (percentil só no detalhe técnico).
- `src/machine_learning/` — `neural_net.py` (MLP NumPy, Adam, parada antecipada, ajuste fino),
  `model_registry.py` (GroupKFold por partida, teste isolado, bootstrap pareado por partida; CLI
  `python -m src.machine_learning.model_registry --treinar`).
- `src/squad/` — Escalação: `formations.py`, `planner.py` (nota do laboratório, melhor XI por algoritmo húngaro,
  provável XI, perfil dos últimos N jogos, plano neutralizar/explorar), `data.py` (leitura filtrada do lake).
- `src/ui/pages/` — `assistant.py`, `search_all.py`, `games.py` (foco do jogo), `match_center.py`, `clubs.py`,
  `players_search.py` (scout por 90 + carreira), `squad.py`, `compare.py`, `neural.py`, `catalog.py`.

**Convenções:** níveis `EVENTS` / `BOXSCORE` / `RESULT` / `SIMULATED` / `UPLOAD`. Ids internos por faixa de fonte:
statsbomb <10M · wyscout 10M · api_football 100M · football_data 300M · espn 500M · fdcouk 2B · openfootball 3B ·
intl 4B · understat 6B · brasileirao 7B · open_matchday 8B · cbf 9B · openplay 11B. Mesma partida em fontes
diferentes = mesma data ±1 dia + mesmos times (`_same`, `consolidate.py`); divergências são registradas, nunca
viram média. Coordenadas no padrão StatsBomb 120×80, ataque para a direita.

## 6. O que JÁ está baixado no PC do usuário (não peça de novo)

- **StatsBomb Open Data** inteiro em `C:\dados\statsbomb` (`STATSBOMB_OPEN_DATA_PATH` no `.env`).
- **OpenPlay** release `data-v0.1.0` (139 arquivos, 0,94 GB) — 26.547 jogos com lances (eventos convertidos ao abrir).
- **CBF / BrazilianFootball**: `C:\dados\cbf\results\processed\*_games.json` (65 arquivos).
- **Transfermarkt (dcaribou)**: competições, clubes, 50 mil jogadores, 656 mil valores, 89 mil jogos — e na v35
  passa a baixar `appearances` e `game_lineups`. Na v36 passa a baixar também `transfers` (`tm_transferencias`,
  base do vínculo jogador-clube) — conferir se o usuário já rodou `--only transfermarkt` depois da v36.
- **football-data.co.uk** (1993–hoje, 22 divisões + BRA/ARG/USA/MEX/JPN/CHN/AUT/DNK/FIN/IRL/NOR/POL/ROU/RUS/SWE/SWZ),
  **openfootball** (cópia git local), **seleções (intl)**, **Brasileirão Dataset (adaoduque)**, **open-matchday**,
  **Simonetti** (wc_data_*), **Wyscout** (5 ligas 17/18 + Copas).
- Base em 15/11/2026: ~300 mil partidas · ~32 mil com lances · ~64 mil com estatísticas · resto só placar.
- Backup: `python -m src.tools.backup_local` → `backups\` (não versionado).

**Fontes com limitação conhecida:**
- API-Football (plano grátis): só temporadas 2022–2024, sem `?ids=` (1 jogo por requisição), 100 req/dia; o app
  guarda isso em `source_state` e não gasta cota redescobrindo.
- ESPN: **causa raiz achada em 16/11/2026** — a ESPN passou a RECUSAR qualquer intervalo de datas
  (`dates=20251001-20251007` → HTTP 400 em TODAS as ligas). Aceita só dia (`20251004`), mês (`202510`) ou ano (`2025`).
  O conector agora pede por ano/mês. Validado daqui: 52 ligas com jogos 2025/2026 (~25 mil encerrados); fora:
  `bra.supercopa`, `kor.1`; Série C 2026 vazia. Comandos: `--only espn_temporada` (resultados + próximos jogos,
  ~1 pedido por liga/ano), `--only espn_resumos --limite N` (estatísticas + escalações + números por jogador, ~1 s
  cada, Brasil e Europa principal primeiro, continua de onde parou), `--only espn_elencos` (elenco atual + lesões).
  A ESPN agora vem LIGADA por padrão (ENABLE_ESPN_PUBLIC_FEED=false desliga).
- Understat: deu 0 partidas porque o SITE ESTÁ FORA DO AR ("We will come back soon", conferido em 16/11/2026) — não é
  defeito do PC nem do conector.
- **FotMob (rodada 5, NOVA)**: JSON público do site (`/api/data/leagues`, `/api/data/matchDetails`), sem chave. ~100
  competições (`LEAGUES` em `src/data_hub/sources/fotmob.py`: Série A–D, Copa do Brasil, estaduais, Copa do Nordeste,
  sul-americanas, 1ª/2ª divisões europeias e copas, feminino, MLS, Liga MX), até 5 temporadas. Por jogo: estatísticas
  com xG/xGOT/xG de bola parada (distância/sprints só onde a liga mede, ex. Premier League), escalação com posição
  EXATA (layout), números por jogador (xA, chances criadas, passes no terço final, recuperações, duelos, nota da
  FotMob, id do atleta), mapa de chutes (`match_shots`), cartões, gols, substituições, desfalques. ~35 KB por jogo.
  Comandos: `--only fotmob_temporada --temporadas N` (resultados + calendário), `--only fotmob_jogos --limite N`
  (detalhes, retomável). Automático só com `ENABLE_FOTMOB=true` no .env (o usuário põe; nunca abrir o .env).
  Ids: faixa 12B. Uso pessoal e não comercial.
- Bloqueiam robôs (403, não contornar): FBref, Sofascore, zerozero/ogol, worldfootball. Pagas/sob contrato (não
  integradas, exigem chave/plano): Sportmonks, Sportradar, Opta/Stats Perform (Opta Vision), Wyscout (só o dataset
  aberto 17/18 que já temos), StatsBomb comercial. football-data.org precisa de chave (conector já existe).
- Nenhuma fonte aberta tem lances com coordenadas do Brasileirão nem dados físicos (velocidade, distância, mapa de
  calor de tracking).

## 7. Pedidos do usuário (v36) — estado

Feito na sessão 1 (15/11/2026, branch `claude/gifted-knuth-q93cbz`, 216 testes verdes):
1. ✅ Assistente: perguntas com alvo têm resposta própria — ranking de xG/perigo (xT + xG, rede neural como 2ª
   opinião), "fulano jogou?" (`presence`), erros do jogador separados por tipo (`errors`), maior falha tática e
   ponto forte da equipe (`weakness`/`strength`). Perguntas de fato não esperam o Gemini (mais rápido). Perguntas
   que caem no panorama vão para `data/assistente_sem_alvo.jsonl` e aparecem em Bastidores (viram casos de teste).
2. ✅ Rede neural: experimentos A–D (`EXPERIMENTS` em `model_registry.py`, B primeiro), Adam, 100 épocas, lote 256,
   paciência 10, He, treino do zero; parada antecipada também dentro das dobras; L2 corrigido (era dividido pelo
   lote); várias tentativas por clique; conferência de classes (13% positivas) e das 14 variáveis; texto do critério
   atualizado. CLI: `python -m src.machine_learning.model_registry --treinar --experimentos B`.
   Achado: 9 das 14 variáveis são zonas (one-hot) quase redundantes com distância/ângulo — o teto de AUC ~0,60
   vem mais das variáveis do que da arquitetura.
3. ✅ Nota 0–10 por atuação (`src/metrics/player_rating.py`): pesos por setor, erros pesam metade, desconto do
   "esperado" por 90 min (calibração PROVISÓRIA em 3 jogos da Copa 2022), < 10 min sem nota. Aba Jogadores com
   Ataque/Passe/Defesa/Duelos e erros; nota média na página do jogador (só jogos com lances dele).
4. ✅ Rede de passes: só o XI por padrão (ou titulares e quem entrou separados); textos em linguagem de futebol.
   Corrigido o minuto de quem entra quando o nome da troca é o completo ("Randal Kolo Muani").
5. ✅ (parcial) Clicar no jogador nas tabelas da partida e do elenco abre a página; respostas do Assistente têm botões
   dos jogadores/times citados. Falta: nomes dentro de textos/cartões HTML (o Streamlit recarrega a sessão em links).
6. ✅ Comparar: qualquer jogador com lances na base, recorte último jogo / últimos 5 / temporada.
7. ✅ Lista de jogos do clube respeita o nível de dado do topo.
8. ✅ Atleta unificado na busca (`unify_people` em `src/data_lake/ids.py`): nome curto/completo/abreviado + nascimento;
   homônimos e casos ambíguos ficam separados. Clube atual pelo Transfermarkt.
9. ✅ Escalação: elenco atual pelos jogos (`apply_transfers`: saiu = jogou por outro clube depois; chegou = jogou pelo
   clube nos últimos 150 dias); campinho de arrastar (`src/ui/drag_pitch.py`, troca com o banco e de formação;
   posições ficam no navegador, não voltam ao Python); marcas E/N/F/C no campo; expectativa só com jogos recentes
   (≤ 400 dias) com lances ou ≥ 5 estatísticas.

Lista A–J do usuário (sessão 2, 16/11/2026) — 233 testes verdes:
- ✅ A1 ESPN em janelas 7 → 3 → 1 dia (400 = janela recusada, contada em `janelas_falhas`) · A2 rede de passes com
  os 11 em campo num minuto (`on_field`) · A3/A4 (presença/falha tática) · A5 filtro de nível na consulta SQL.
- ✅ B2 `sync_policy.py`: incremental por competição, ao vivo a cada 1 min (só ligas com jogo rolando; varredura a
  cada 15 min), encerrada consolidada e congelada (`frozen_matches`), fixtures a cada 3 h · B3 `src/squad/tenure.py`
  (transferências + jogos, empréstimo/retorno, UNKNOWN fora do elenco) · B4 `src/data_hub/player_resolver.py`
  (nunca só o nome; `player_merge_candidates`) · B5 `python -m src.tools.cache_crests` (data/crests) + monograma ·
  B6 `src/data_hub/depth.py` (nível 0–4, selo na página do jogo) · B7 `source_divergences`.
- ✅ C `src/analytics/player_ratings.py` (pares por setor/competição com n ≥ 20, média com n mínimo 3 e minutos,
  abas Defensivo/Ofensivo/Passes, teste zagueiro × atacante).
- ✅ D campinho com tamanho ajustável e formação customizada; marcas em linguagem de futebol; diagnóstico do rival
  (2 fortes + 2 fracos com dado e jogo de origem; só jogos nível ≥ 2, senão "base insuficiente").
- ✅ E1 latência medida (`data/assistente_latencia.jsonl`, painel em Bastidores, meta < 8 s) · E5 "não tenho esse
  dado" · E3/E4 intocados.
- ✅ F1 cartões 14px · F2 idioma PT/EN/ES (`src/ui/i18n.py`) · F3 Fortes e fracos em cartões com barra · F4
  "o que é isto?" (`src/ui/glossary.py`) · F8 comparar qualquer jogador.
- ✅ G painel de fontes (aba 🩺 em Dados & Fontes, `src/data_hub/health.py`, ações em segundo plano).

Rodada 3 (16/11/2026, 247 testes verdes; testes não acessam a rede — `tests/conftest.py`):
- ✅ ESPN por ano/mês + fixtures (`fixtures`) + elencos (`espn_rosters`) + resumos priorizados; atualização automática
  (QUICK `espn` = temporada do ano + resumos da última semana; DAILY `espn_elencos`; ao vivo pela ESPN).
- ✅ Busca de jogos ordenada por data (o nome só filtra).
- ✅ Assistente: blocos táticos novos (`src/intelligence/tactical_blocks.py` + `tactical_writers.py`): corredores,
  como sofreu, entre linhas, eficiência, momentos, jogadas dos gols, diagnóstico dos defensores, duplas, erros que
  viraram perigo, plano para explorar a defesa; jogador ausente; gentílicos; pergunta de jogador sem bloco do time;
  teto de 10 s por pergunta para o Gemini (antes até ~58 s). Guard: inteiro só deriva de dois inteiros.
- ✅ Treino da rede em processo separado (`src/machine_learning/train_job.py`), andamento ao vivo, parar; float32.
- ✅ Escalação: aba 🔭 Próximo jogo (`src/squad/matchday.py`): calendário real, provável dos dois times pelas escalações
  recentes (posição e lado), lesões (ESPN) e suspensões (vermelho no último jogo), fragilidades por setor no campinho,
  quem decide, porquê de cada jogador; Provável/Melhor usam escalações reais quando há ≥ 3 jogos; 16 formações.
- ✅ Comparar em cartões (`duel_bars`), tabelas com 2 casas, campinho sem eixos de jardas, gramado listrado.
- Observação: a ESPN lista o volante Rodri (nasc. 22/06/1996) no elenco do Barcelona hoje; o usuário disse que ele não
  é do Barcelona — fontes divergem; a interface mostra a fonte do elenco.

Rodada 4 (16/11/2026, 259 testes verdes):
- ✅ Avaliação individual 2.0 (`src/analytics/rating_v2.py`): 7 dimensões na linha com pesos por função, 6 no goleiro
  (30/15/10/15/20/10), percentil contra pares da mesma função → nota (P5=2,0 … P99=10), encolhimento pelos minutos,
  confiança %, desempenho × impacto separados, nota 10 rara, teto 9,5 com pouca cobertura, "não observado" sem tracking.
  Referência: `python -m src.analytics.rating_v2 --referencia 300` (cache em data/processed). Aba Jogadores com radar.
- ✅ Fortes e fracos: aba "📊 Todas as métricas (fora da curva)" — ~35 indicadores por jogador contra a mesma função,
  só o que está ≥ P85 ou ≤ P15; no modo equipe, o indicador mais fora da curva de cada titular (`outliers`).
- ✅ Próximo jogo: provável = 0,5 temporada + 0,35 últimos 5 + 0,15 último jogo (titular que faltou 1 jogo continua
  provável, marcado "dúvida"); suspensão por acúmulo de amarelos (`YELLOW_LIMIT`, conferir regra da competição);
  encaixe por posição real das escalações (LM/RM da ESPN corrigidos pela formação, `multi_fit`, encaixe ao cubo);
  escalação OFICIAL da ESPN substitui a provável (~1 h antes) e notícias que citam os clubes (`espn.preview`).
- ✅ Assistente: duas perguntas na mesma mensagem, "foi bom ou ruim?", quem merecia ganhar (xG/xT), principal criador,
  quem mais atacou as costas, quem menos marcou, jogador ausente explicado, respostas com abertura direta e "Em resumo".
- Limitação: abaixo da Série B não há fonte aberta acessível (OpenLigaDB é alemã; football-data.org grátis só Série A).

Rodada 5 (16/11/2026, 276 testes verdes):
- ✅ URGENTE posições: `src/squad/positions.py` — posição precisa × genérica por fonte (G/D/M/F da API-Football só diz o
  setor, não vira centroavante/zagueiro), LM/RM da ESPN pelo desenho, mesmo jogo de 2 fontes conta 1 vez, cadastro do
  Transfermarkt como desempate; `squad_from_db` usa a mesma regra. Era a causa de Yamal no meio e Koundé na zaga.
- ✅ Escalação: jogo HIPOTÉTICO contra qualquer time com escalação; campinho em pé (nota no círculo, anel de encaixe,
  sigla, nome em etiqueta); próximos jogos sem duplicar ESPN × FotMob; pré-jogo do rival com estilo e problemas recorrentes.
- ✅ Fonte FotMob (ver seção 6) + nota 2.0 por estatísticas (`src/analytics/rating_box.py`, régua própria
  `python -m src.analytics.rating_box --referencia 400`), mapa de chutes e notas na página de jogos sem lances, cartão
  do jogador estilo FC (qualidade, fase, regularidade).
- ✅ Assistente: por que venceu (`src/intelligence/match_story.py`: fatos → leitura → hipóteses), parar vários jogadores
  (fonte comum, ligação, corredor), estratégias pelo perfil medido (zona 14, profundidade, drible, condução, cruzamento,
  aéreo, proposição), perigo por critérios separados, goleiro/escalação direto, presença (banco/não relacionado),
  sprints só com dado físico real, pronome = jogador anterior, perguntas de substituição/placar/estilo/jogos parecidos.
  Disputa de pênaltis fora dos blocos táticos.
- ✅ Rodada 5 tática: `src/analytics/match_patterns.py` (bola parada, impacto das substituições — associação, não causa —,
  estado do jogo) e `src/analytics/team_history.py` (identidade com consistência, problemas que se repetem ≥4 jogos e
  ≥60%, pós-jogo × habitual, jogos parecidos); seção "🧩 Padrões e histórico" no jogo; aba "🧬 Estilo e tendências" no clube.
- ✅ `python -m src.machine_learning.benchmark`: na amostra da Copa (64 jogos) a regressão logística com distância/ângulo/
  passes (AUC 0,640) é estatisticamente MELHOR que a rede (0,623); zonas e placar quase não ajudam. Modelo em uso não
  foi trocado (decisão do usuário); painel nos Bastidores.
- Não feito: padrões ofensivos por sequência (terceiro homem etc.), perfil de treinador (fontes não trazem treinador de
  forma confiável), tracking/360 de outras ligas (não existe aberto), estaduais/Série D por notícia de escalação.

Rodada 6 (16/11/2026, 278 testes verdes) — correções pedidas com prints:
- ✅ Escalação: `canonical_names` (matchday) unifica o mesmo atleta entre fontes (Konaté/Konate, Van Dijk, Alisson ×
  Alisson Becker; dois "Gabriel" não se juntam) — acabou a "dúvida" falsa; quem não está no elenco atual sai mesmo com
  escalações velhas na base; "% das vezes que começou"; rival ≠ próprio time; pontos fortes/fracos de cada jogador em
  blocos verdes/vermelhos (`player_highlights`, temporada × mesma função); aviso de escalações velhas/ausentes.
- ✅ FotMob AUTOMÁTICA: thread `til-fotmob` (autosync.py) com o app aberto — calendário diário (1ª vez com
  FOTMOB_TEMPORADAS=2), jogos dos últimos 10 dias, histórico de 5 temporadas em lotes de 300; ~0,7 s por pedido
  (FOTMOB_INTERVALO); jogo sem dado não repete por 7 dias (`fotmob_tried`); status na barra do topo. ENABLE_FOTMOB=false
  desliga. Sob demanda: jogo sem detalhes busca a versão FotMob na hora; Escalação de time sem escalações recentes baixa
  os últimos 12 jogos. CLI `--only fotmob_tudo` (5 temporadas, tudo, retomável).
- ✅ Profundidade FotMob: `match_extra` (momentum, corredores de ataque, desfalques, craque); jogo sem lances ganha
  "O jogo pelos dados da FotMob" (`src/ui/pages/fotmob_depth.py`) e Fortes e fracos (`fotmob_strengths.py`); Assistente
  em jogo sem lances usa `src/intelligence/box_analyst.py` (ranking de qualquer número, nota, anular criador, como evitar
  gols, por que venceu, físico só se a liga mede); Comparar jogador × jogador pela FotMob.
- ✅ Classificação desenhada (escudo, faixas, últimos 5); linha do tempo sem "****" quando a fonte não traz o autor;
  erro `_detalhe` em Fortes e fracos (modo Equipe) corrigido.

Rodada 7 (18/11/2026, 370 testes verdes) — velocidade e reclamações com prints:
- ✅ Velocidade: FotMob, OpenPlay, sync de 3 h/24 h, ao vivo, fotografia do Scout e referência do "jogo típico" rodam num
  PROCESSO SEPARADO de prioridade baixa (`src/data_hub/worker.py`, status em `data/worker_status.json`, encerra quando o
  app fecha; `AUTO_SYNC_MODE=thread` volta ao jeito antigo). Gravações das threads `til-*` não derrubam mais o cache da
  tela (`_touched`). Scout lê uma fotografia pronta (`src/scout/snapshot.py`, refeita a cada 6 h) — abre na hora.
  Corrigido erro de ordenação do Scout (coluna `realismo` era dict).
- ✅ Físico por 90 no Comparar e destaques: cada número dividido só pelos minutos dos jogos em que foi medido.
- ✅ "Duplicate column names" na aba Jogadores (FotMob) corrigido (`player_stats_table`); tabelas com cores sólidas,
  calor por coluna (vermelho para números ruins), "—" no lugar de "None".
- ✅ Diagnóstico do rival (`src/analytics/vulnerabilities.py` + `src/ui/vuln_view.py`): campinho com zonas de risco
  numeradas + cartões (evidência, como explorar, base): muito driblado, desarma pouco, perde aéreo, perde duelos,
  ponta/meia que não defende, saída de bola frágil sob pressão, contra-ataque cedido, chutes de fora, corredor que mais
  sofre, cruzamentos cedidos, zagueiro baixo × nosso atacante alto. Substitui as bolinhas F.
- ✅ Busca: mesma partida de fontes diferentes aparece 1 vez (data ±1 dia + times canônicos), com o nível mais rico.
- ✅ Jogo típico: referência cresce em segundo plano até 1.500 jogos com lances (`TARGET_MATCHES`).
- ✅ Rede: "parou com erro" era a validação fixa sem `density_is_360` — corrigido. Experimentos novos E/F/G com variáveis
  enxutas (sem as 9 zonas). Na amostra de desenvolvimento o G deu ganho +0,002 mas com IC incluindo zero → rejeitado
  (critério mantido). No PC, com mais jogos, rodar E,F,G.

Rodada 8 (18/11/2026, 372 testes verdes):
- Diagnóstico: "Scout sumiu / sem Voltar / interface velha / jogos repetidos" = o PC do usuário NÃO estava neste branch
  (a `main` é a v35 antiga, sem Scout). Agora a barra do topo mostra "versão: <branch> · <commit>" (`_app_version`).
- ✅ Tema escuro nativo em `.streamlit/config.toml`: no Streamlit 1.67 o CSS não alcançava botões/caixas (brancos com
  texto branco); seletores do tema atualizados (`stBaseButton-*`).
- ✅ Elenco ATUAL pela FotMob (`FotmobProvider.roster`, tabelas `fotmob_teams` e `fotmob_rosters`, 24 h de validade,
  1º acesso ~2 pedidos): manda na Escalação (`matchday.roster`, `apply_official_roster` no `_squad`, usado também pelo
  Scout) — quem não está inscrito sai, quem chegou entra com posição/idade/altura; aba "💶 Elenco e valores" do clube
  mostra o elenco inscrito hoje com lesões antes do cadastro do Transfermarkt.
- ✅ Rede neural na página do jogo: seção "🧠 Perigo (IA)" (`src/ui/pages/danger_view.py`) — ações perigosas por time,
  quem mais criou perigo, mapa das ações coloridas pela chance. Onde a rede é usada: Assistente (ranking de perigo,
  2ª opinião), página do jogo e Bastidores. Ela só avalia jogos com lances (coordenadas); FotMob/ESPN não têm ações.
- ✅ Comparar jogo × jogo sem duplicar a mesma partida de duas fontes.

Rodada 9 (18/11/2026, 382 testes verdes):
- Diagnóstico do PC: o branch local `claude/gifted-knuth-q93cbz` do usuário NÃO tinha upstream (`git pull` falhou) e
  ficou parado numa versão antiga (o `requirements.txt` dele nem tinha FastAPI) — por isso "nada aparecia". Correção:
  `git branch --set-upstream-to=origin/claude/gifted-knuth-q93cbz` + `git merge --ff-only origin/claude/gifted-knuth-q93cbz`.
- ✅ IA do laboratório (`src/intelligence/lab_ai/`): analista PRÓPRIO dados→texto e treinável — `facts.py` (fatos de
  qualquer jogo: estatísticas FotMob/ESPN ou lances, por time e por jogador, régua da base `reference.py` com milhares
  de jogos, empates no zero tratados), `switches.py` (reação de cada defensor às inversões: quem chega primeiro, tempo,
  avanço do ataque, lado frágil), `selector.py` (regressão logística NumPy treinada com 👍/👎 — v000 = pesos de
  analista; promove só se errar menos no teste; frases aprendem por Thompson), `writer.py` (resposta direta → números →
  leitura tática → como explorar/corrigir → resumo; concordância "1 cartão"), `engine.py` (foco = time citado; "como
  explorar a França" → foco é o outro; "não tenho X medido" quando o jogo não traz). É o motor PADRÃO do Assistente
  (resposta específica do analista clássico + "Leitura da IA do laboratório"; pergunta genérica → só a IA). Gemini
  agora desligado por padrão. Registro do que mostrou: `data/learning/lab_ai_shown.jsonl`. Treino: Bastidores → 🧠.
- ✅ Página do jogo: seção "📑 Relatório da IA" (`src/ui/pages/lab_report.py`) — plano, fases, destaques, inversões.
- ✅ Algoritmo genético de escalação (`src/squad/genetic.py`): torneio, cruzamento com reparo, mutação, elitismo,
  semente; aptidão = Σ nota × encaixe + bônus por fraqueza do rival (vulnerabilities) × perfil relativo do atleta
  (últimos 15 jogos FotMob); comparado com o melhor XI húngaro; nunca escala lesionado. Escalação → Plano de jogo.
- ✅ Site: API `POST /api/v1/ai/lab/ask`, `GET /api/v1/matches/{id}/report`, `POST /api/v1/ai/genetic/lineup` (banco
  só leitura) + painéis no React (`apps/web/src/LabPanels.tsx`: assistente, relatório, genético com elenco de exemplo);
  cartões de modelo `lab-ai-analyst` e `lineup-genetic`. Deploy público ainda NÃO feito (Netlify + hospedagem da API).

Rodada 10 (18/11/2026, 390 testes verdes):
- ✅ Erro "StreamlitDuplicateElementKey vuln_pitch_…" (a leitura do rival aparece em 2 abas) — chave por aba (`where`).
- ✅ Masculino × feminino: as fontes dão o mesmo nome ao time masculino e ao feminino (Bayern com Kane e Klara Bühl).
  `src/data_hub/gender.py` ganhou `comp_sql`/`is_women_competition`/`keep_same_gender` e o filtro entrou em TODAS as
  consultas por time (escalações, números por jogador, fragilidades, próximos jogos, Scout, histórico).
- ✅ Qualidade do Scout refeita (`add_quality_scores`): encolhimento bayesiano pelos minutos (mins/(mins+900)),
  nível do clube (percentil do valor do elenco) e reputação de mercado na função (35%); fotografia nova
  `scout_universe_v2.pkl`. Clube atual nunca é a seleção (último jogo por CLUBE). Histórico do Scout só masculino.
- ✅ Tabelas: `tidy_numbers` (idade/minutos/jogos inteiros, demais com até 2 casas) em todas as tabelas.
- ✅ Buscas só ao apertar Enter/Buscar (`st.form`) + cache das opções de times (`_team_options_cached`).
- ✅ Scout: TODAS as posições no "Três melhores por posição" (ranqueia sob demanda) e TODAS as nações do mercado com
  % de adaptação cultural (`_affinity`); janela de transferências em cartões por setor (Fica/Vender/Emprestar).
- ✅ Escalação: abas "🔭 Próximo jogo" e "🧪 Jogo hipotético" separadas; só "Meu time" no topo; adversário vem do
  próximo jogo ou do botão "🔎 Analisar este jogo"; campinho editável (arrastar) nas duas; desfalques/dúvidas agrupados.
  Página do time: botão "Analisar o próximo jogo" (abre a Escalação com o rival).
- ✅ IA: `lab_ai/availability.py` (mapa de dados do jogo: o que a fonte mede e o que não mede, no rodapé das respostas e
  nos relatórios); `lab_ai/player_intel.py` — nível 1 (um lance), nível 2 (partida: técnica, pé, pressão, cruzamentos,
  finalização, conduções, defesa por terço/corredor, perdas e consequência em 15 s, blocos de 15 min, placar,
  eficiência) e nível 3 (vários jogos: regularidade, tendência, "em X de Y jogos"); afirmações tipadas FATO / PADRÃO /
  INTERPRETAÇÃO / HIPÓTESE com n. Seção "🔬 Jogador (IA)" na página do jogo; relatório da IA com destaques por jogador;
  Assistente: jogador citado → leitura dele primeiro; a IA só substitui a resposta clássica quando achou números da
  pergunta. Leitura do rival ("Onde atacar") com Fato/Padrão/Interpretação/Como explorar/Hipótese.

Rodada 11 (18/11/2026, 399 testes verdes):
- ✅ Lentidão: "modo leve" (`src/data_hub/activity.py`): a tela marca `data/ui_active`; OpenPlay, FotMob histórico,
  réguas, fotografia do Scout e jogo típico ESPERAM enquanto o app está em uso; `wal_checkpoint(TRUNCATE)` periódico e
  `journal_size_limit` (o arquivo de escrita do SQLite inchava e deixava toda leitura lenta). FotMob: 60 s entre lotes.
  Jogo hipotético só calcula após "Analisar". `TIL_MODO_LEVE=0` desliga.
- ✅ Homônimos: `same_team_names` separa pelo país das competições nacionais (`_comp_country`, `_name_countries`) e
  recusa nome com palavra a mais (Barcelona × Barcelona SC × RCD Espanyol de Barcelona); `team_matches` tira liga
  nacional de outro país. `one_per_game`: mesmo placar + um time igual em ±1 dia = mesma partida. Filtro do clube
  "Com estatísticas ou lances (sem só placar)" (padrão).
- ✅ Assistente: BUG que fazia a IA colar blocos irrelevantes — o motor normal "LOCAL_SCOPED_ENGINE" era tratado como
  "fora do assunto". Agora `lab_ai/direct.py` detecta o número perguntado (para fora, no alvo, terço final, desarmes,
  posse…) e responde direto com ranking e fonte; sem número reconhecido não acrescenta nada; sem o dado diz "não tenho".
  Página de treino renomeada "IA do laboratório (treino e bastidores)".
- ✅ Scout: viabilidade com `nationality_market` (quão comum é a nacionalidade na liga do clube + no próprio elenco;
  mesmo país = 100) e `career_context` (titular no auge em clube muito maior = exceção); pesos novos (nacionalidade 24%,
  carreira 17%) e tetos; corte inicial já considera nacionalidade; não sugere quem é pior que o titular (salvo jovem
  promissor ou oportunidade de contrato). Carências só nas posições que o time escala (`roles_used`; meia central vira
  volante/meia se o técnico não usa). Identidade: superficial < 8 jogos, inicial 8–29, detalhada 30+ e desenhos usados.
  "Três melhores por posição" ranqueia só a posição (antes vinha vazio) e filtros num formulário; idade inclusiva.
  Teto de potencial (`potencial_teto` ≥ qualidade); joias só dentro do alcance do clube. Nota externa sozinha vale
  metade. Nomes do elenco ligados ao mercado (`_merge_roster` com `canonical_names`). Empréstimos da FotMob
  (`fotmob_loans`): comprar/deixar acabar/renovar e aba dos emprestados pelo clube; janela num formulário com
  "Finalizar planejamento". Gráfico de médias × competição; radar antes × depois; dossiê PDF com campinho
  (`src/scout/dossier_pdf.py`). Fotografia `scout_universe_v3.pkl` (aproveita a v2 recalculando só as notas).

Rodada 12 (18/11/2026, 411 testes verdes):
- ✅ Assistente 100% pela nossa IA: `lab_ai/router.py` responde por intenção (próximo jogo, desfalques, quem jogou melhor
  pela nota, substituição com nota + momentum + trocas do técnico, profundidade com proxies honestos, chances claras
  perdidas, ponto forte/atenção/o que fazer melhor/como explorar — sem destacar impedimentos/cartões) e cai no
  `direct.py` (passes errados, bolas longas com aproveitamento, erros que viraram gol, defesas; ranking com minutos e
  desempate pelos minutos). Duas perguntas na mesma frase; "…? em qual momento?" fica uma pergunta só. Presença, gols,
  escalação e erros continuam no analista clássico.
- ✅ Bastidores pela matéria (`src/intelligence/course.py` + `src/ui/pages/course_view.py`): mapa de quem decide cada
  coisa (Q1), fuzzy × probabilidade (Q2), Mamdani com centroide numérico (Q3), Mamdani × Sugeno (Q4), XOR e forward
  pass do modelo em uso (Q5), passo de gradiente (Q6), diagnóstico da curva e SUGESTÃO DO PRÓXIMO TREINO (Q7), matriz
  de confusão/paradoxo da acurácia na validação real (Q8), arquiteturas (Q9), codificação/roleta×torneio/mutação (Q10),
  penalidade R (Q11), pseudocódigo e convergência do AG (Q12). Erro "numpy boolean subtract" da tabela corrigido.
- ✅ Busca mais rápida (cache por consulta; índice de jogadores em `data/processed/player_index.parquet`, refeito 1×/dia
  pelo worker). Alturas: FotMob manda (Gabriel Barbosa 1,78 m), "zagueiro baixo" exige ≥ 6 duelos aéreos e ≥ 50% ganhos.
  Leitura do rival com campinho dos jogadores nas posições + nomes clicáveis. Comparar: homônimos separados pelo id,
  aba Resumo (gols, assistências) e Aproveitamento (%); 1 jogo = totais com minutos.
- ✅ Padrões e histórico em jogo só com estatísticas: "🧠 Leitura da IA" (forte, atenção, explorar, trocas, melhor, fases).
- Site idêntico ao app: ainda não (pedido para depois).

Rodada 13 (18/11/2026, 422 testes verdes):
- ✅ Velocidade: índices novos no SQLite (visitante+data, mandante+data, competição+data, números por jogador por time,
  escalações por jogo, estatísticas por time) + `PRAGMA optimize` — antes "jogos do time" varria a tabela inteira pelo
  visitante. Os índices NÃO são criados ao abrir o banco (travava app e pytest): `python -m src.tools.criar_indices`
  (app fechado, uma vez) ou o processo de fundo com a tela parada. Seções pesadas da IA abrem sob demanda.
- ✅ Scout: régua nova (`add_quality_scores`): pico de valor de 3 anos (`valor_pico_3a_eur`, veterano de elite), nível =
  45% clube + 55% liga (`_level_map`, `clube_liga`), quem domina a liga perde menos pelo nível, 0 min no ano não herda
  histórico antigo (só 1/3), nota FotMob em todas as funções; `precocity` (valor e minutos contra a mesma idade) no teto
  de potencial; fotografia `scout_universe_v4.pkl`. Características (`src/scout/traits.py`: artilheiro, maestro,
  motorzinho, driblador, xerife, paredão, grande promessa… só ≥ P85–90 da função, com porquê). "Três melhores por
  posição" corrigido (o cache ignorava a posição). "Adicionar ao plano" com callback + barra do plano + abas com estado.
  Elenco e notas pelos jogos do PRÓPRIO clube (`club_player_stats`, `roster_quality`: homônimos não zeram mais).
  Dossiê com porquês/atenção (`why_chosen`) e mais motivos de recusa (não agrega, pior que o titular, fase, estilo,
  lesões, salário). "Finalizar planejamento" mostra o elenco planejado no app (`src/ui/plan_board.py`: campinho +
  profundidade por posição). Sem lista oficial, quem não joga há 300+ dias sai do elenco (Diogo Jota, Izquierdoz).
- ✅ Jogo: abas Perigo/Relatório/Jogador (IA) viraram partes de Redes & xT, Padrões e Jogadores (abrem sob demanda);
  "⚖️ Os dois times"; xT/jogadas/importância seguem o período escolhido; corredores defensivos desenhados no campo;
  bola aérea contada honestamente (vitória = "Aerial Lost" do rival; nada de passes altos como "disputas ganhas" —
  era o "12 de 12 (100%)"); sem o interruptor "Só partidas reais"; jogo sem estatística diz que nenhuma base achou.
  Clube: formações com padrões de ataque e defesa (`team_history.formation_patterns`).
- ✅ Pré-jogo (`src/squad/matchups.py` + `src/ui/matchday_view.py`): cartão do confronto, campo único com os dois XIs,
  confrontos meu time × rival (FORÇAR/PROTEGER/EVITAR; duelos por desenho em 5 fundamentos + estilo × problema
  sistêmico; "escancarado" só topo×fundo da base), índice fuzzy Mamdani de exploração, 👍/👎 por confronto; conteúdo
  antigo nas abas Onde atacar / Escalações e porquês / Leitura do rival / Onde sofremos / Editar o campinho / Notícias.
- ✅ IA única (`src/intelligence/lab_brain.py`): um lugar para o 👍/👎 de qualquer tela (pesos Beta por tipo, 0,6–1,4),
  "🧠 Treinar tudo" (seletor do Assistente, rede de perigo com os parâmetros sugeridos pela Q7, réguas, índice de busca).
  Bastidores: "IA única" + matéria com "Em palavras simples" e "Onde está no app" em cada questão (`course.SIMPLE`).
- Site idêntico: NÃO feito. Caminho honesto para ficar idêntico: publicar o próprio app Streamlit (não reescrever em
  React) com uma cópia só-leitura do banco — exige hospedar o banco (vários GB) e decidir onde.

Rodada 14 (18/11/2026, 427 testes verdes):
- ✅ Travamento do pytest/app: índices de velocidade fora da abertura do banco (`ensure_speed_indexes`,
  `python -m src.tools.criar_indices`, worker com a tela parada).
- ✅ Pré-jogo: "Onde atacar/Onde sofremos" ignora quem não joga (desfalque ou fora da provável) — `vuln_view.render(...,
  lineup=, out=)`. "Porquês" do XI: FotMob omite stat zero → só físicos são escalados (`PHYSICAL_KEYS`); totais de
  goleiro viram por 90; indicador com > 45% de zeros na régua não vira destaque (acabou "bloqueios 0,11 melhor que
  92%" de centroavante e "erros que deram chance 20,0"); plural correto ("laterais"); texto diz "números de N jogos".
- ✅ Scout: homônimo do cadastro recebe o histórico pelo CLUBE (Zé Lucas, Otávio etc. tinham nota 48 de preenchimento);
  sem minutos e sem valor = sem nota (lacuna); zagueiro/volante medidos também pela construção (passes que quebram
  linhas, vezes driblado); jovem ≤ 23 no topo do valor da função pesa mais a reputação (Cubarsí); fotografia v5.
  `python -m src.tools.onde_esta "Nome"` explica por que um jogador não aparece (Mauro Coronel: liga paraguaia está na
  lista da FotMob, id 199, mas os jogos dele ainda não foram baixados com detalhes).
- ✅ Empréstimos registráveis à mão (`scout_manual_loans`) somados aos da FotMob na janela (comprar/deixar acabar/renovar;
  reintegrar/vender/renovar).
- ✅ Jogo de ida "sumido": não era apagado — o filtro padrão do clube escondia jogos só com placar. Padrão agora "Todos os
  jogos"; teste garante que dois jogos com mesmo placar/times/competição em datas diferentes nunca se juntam.
- ✅ PageRank (`src/analytics/pagerank.py`): força real dos times na página da competição (perdedor "vota" no vencedor,
  laço para quem vence); já existia na rede de passes.
- ✅ IA do Assistente treinável como a rede de perigo (`src/intelligence/lab_ai/trainer.py`): 👍/👎 (peso 3) + rótulo
  automático das perguntas que pedem um número, separação por pergunta, curva treino × validação, parada antecipada,
  promoção só se errar menos, sugestão dos próximos parâmetros; "Treinar tudo" usa isso.

Rodada 15 (19/11/2026, 429 testes verdes):
- ✅ Ligas sul-americanas: a fila de detalhes da FotMob era "Brasil/Europa inteiros (5 temporadas) antes de tudo" — o
  Paraguai nunca chegava (Mauro Coronel: 1 jogo com números). Agora a fila vai do MAIS RECENTE de todas as ligas (faixas
  de 120 dias) e as sul-americanas estão na prioridade (`PRIORITY`); atalho `--ligas sulamericanas` (`REGIONS`).
- ✅ Velocidade: (1) conexão do SQLite reaproveitada por thread no banco principal (`_thread_conn`; no Windows cada
  abertura custa 10–30 ms e uma tela abria dezenas; `TIL_REUSE_CONN=0` desliga); (2) versão de cache POR TIME
  (`team_version`: só muda com jogo/estatística nova do time ou na virada do dia) — a versão geral mudava a cada 10 min
  nas atualizações e apagava o cache de todas as telas; (3) caches pesados em disco (`persist="disk"`: estilo do clube,
  formações, histórico/padrões, fragilidades do rival, próximo jogo, confrontos, elenco, perfil) — reabrir o app é
  instantâneo; (4) pré-aquecimento: depois de uma busca, a página dos 2 primeiros times é calculada em segundo plano.
- ✅ IA do Assistente: avaliação detalhada (`trainer.evaluate`: acerto do 1º fato, AUC, precisão/revocação/F1, perda),
  promoção exige perder menos E não acertar menos o 1º fato, validação cruzada em 5 dobras por pergunta
  (`cross_validate`) e busca automática η × λ (`auto_search`) na tela de treino.

Rodada 16 (19/11/2026, 435 testes verdes) — avaliação de jogadores refeita (diagnóstico em docs/DIAGNOSTICO_AVALIACAO.md):
- ✅ Etapa 0: seleções reconhecidas (lista ampla PT/EN + "U20/Sub-20"; Monaco fica clube) — Tzolis/Son/Irankunda não têm
  mais a seleção como "clube atual". `python -m src.tools.cobertura_jogadores` mede a cobertura POR JOGADOR por competição.
- ✅ Etapas 1–5 (`src/scout/evaluation.py`, CLI `python -m src.scout.evaluation`, refeito 1×/dia pelo worker →
  `data/processed/evaluations.parquet`): jogo a jogo (titular × reserva pela escalação, posição pela escalação → cadastro,
  adversário pelo PageRank da competição, casa/fora, posse do time); uso (jogos, minutos, titularidades, entradas, % dos
  minutos do time); por 90 com ações defensivas ajustadas pela posse; fatia do xG+xA do time; percentil DENTRO da
  função e da competição (métrica ausente = não avaliada); avaliações separadas — desempenho/90, temporada (≥ 900 min e
  ≥ 35% dos minutos), regularidade, impacto, contra fortes, potencial, revelação, custo-benefício, geral entre ligas
  (nível da competição ESTIMADO: tabela prévia + jogadores que atuaram em duas competições); função tática pelo perfil;
  ficha explicável (qualidades, limitações, contexto, onde rende, não avaliado/não observável); validação (estabilidade
  entre turnos, zero sem minutos, zero reservas, viés por cobertura). Tela nova "🏆 Rankings" no menu.
- ✅ Nota antiga do Scout (mantida como avaliação geral): 0 min no último ano = sem nota; fama de mercado × minutos do ano
  (peso cheio só com 1.350+ min); fotografia v6.
- Pendente: modelo aprendido de transferência entre ligas (hoje: estimativa prévia + pares), custo-benefício e idade só
  para quem está no cadastro do Transfermarkt sem homônimo.

Rodada 17 (19/11/2026, 438 testes verdes):
- ✅ Monitor de velocidade (`src/ui/perf.py`): tempo de cada tela e das análises pesadas (@timed) em data/perf.jsonl;
  barra do topo mostra a última tela; Bastidores › "⏱️ Velocidade do app" com mediana/90%/pior e alerta.
- ✅ Nível das ligas APRENDIDO (`evaluation.league_model`): nota = habilidade + facilidade da competição (3 anos, ≥ 450
  min), mínimos quadrados alternados com regularização para a estimativa prévia; competição com < 3 jogadores ligando
  réguas fica na estimativa e é marcada.
- ✅ Idade/valor para quem não está no Transfermarkt: elenco da FotMob (`fotmob_rosters`) e Wikidata
  (`src/data_hub/sources/wikidata.py`, CC0, só nome único de jogador; worker completa 400/dia; CLI
  `python -m src.data_hub.sources.wikidata --limite 1500`).
- ✅ Download FotMob mostra ritmo e tempo que falta; `--intervalo` ajusta o ritmo só naquela execução.
- ✅ Plano completo de publicação 24 h idêntica ao app: `docs/PLANO_PUBLICACAO.md` (VPS + SQLite WAL + Litestream,
  worker como serviço, Caddy/Cloudflare, CI, monitoramento, licenças e 3 caminhos de abertura).

Rodada 18 (19/11/2026, 445 testes verdes):
- ✅ `python -m src.scout.evaluation` travava na base grande: a função tática comparava cada jogador com todos os
  colegas (O(n²)). Agora os percentis são calculados de uma vez (`_strict_pct` + `_classify`, mesmo resultado, 60 mil
  jogadores em ~0,5 s); a média ponderada do nível das ligas também ficou sem laço por grupo.
- ✅ Publicação GRÁTIS (`docs/PLANO_PUBLICACAO.md` reescrito): Hugging Face cobra apps Docker desde 29/09/2026 e
  Oracle/Google pedem cartão → plano = app no PC + Cloudflare Quick Tunnel (sem conta). `scripts/apresentar.ps1` pede
  a senha (só na memória da janela), liga o app com `AUTO_SYNC=0`, abre o túnel e copia o link; `python -m
  src.tools.apresentacao` confere tudo antes. `src/ui/gate.py`: acesso pelo túnel (cabeçalhos Cloudflare/proxy ou Host
  externo) = visitante → senha `TIL_SENHA` (hash + compare_digest) e botões pesados bloqueados (`visitor_blocked`);
  localhost entra direto. `TIL_MODO_PUBLICO=1` trata todos como visitantes e desliga a atualização automática.

Pendente / limitações honestas:
- Espanhol trava e páginas não traduzem inteiras (usuário pediu para deixar para depois).
- "Prováveis escalações por notícia" não existe em fonte aberta acessível: a provável vem dos últimos jogos; a oficial
  a ESPN publica ~1 h antes. Acúmulo de amarelos não é calculado (só vermelho no último jogo).
- Estaduais além de SP/RJ/MG/RS, Série D, feminino e base: fora da ESPN; avaliar football-data.org (responde daqui),
  OpenLigaDB (responde), RSSSF.
- F5/F6/F7 parciais; recalibrar `EXPECTED_PER90`; conferir no PC Understat e os experimentos B/A/C/D.

## 8. Ao final de cada sessão

Diga em poucas linhas o que mudou, quais comandos o usuário deve rodar (só os necessários) e o que ficou pendente.
Atualize a seção 6 e a seção 7 deste arquivo quando algo for baixado ou concluído.
