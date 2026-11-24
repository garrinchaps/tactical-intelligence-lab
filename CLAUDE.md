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
- Rodada 20: novas ligas na FotMob (Rússia 63, Arábia 536, Japão 223, Coreia 9080, Catar 535, Emirados 538, Romênia 189,
  Israel 127, Hungria 212, Bulgária 270, China 120, Austrália 113, México 2ª 8976) e seleções de base (296, 306, 9848, 288,
  301, 287) + Libertadores Sub-20 (11022) — AINDA NÃO baixadas no PC (comandos na resposta da rodada 20).
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

Rodada 19 (19/11/2026, 454 testes verdes):
- ✅ Scout sem Série B/C e sul-americanas: os números por jogador da FotMob vêm SEM posição (só o goleiro) e o universo
  descartava quem não tinha posição. `engine.fill_positions_from_lineups` completa pela escalação do mesmo jogo e a
  posição mais comum ignora vazios; Rankings herdam a posição dos outros jogos (reserva). Na base de dev o universo foi
  de 22 → 188 jogadores. `engine.merge_rankings`: nota dos Rankings (geral entre ligas) entra na qualidade (25–45%
  conforme minutos; homônimo fora), completa idade/valor/liga de quem não está no Transfermarkt; filtro "Origem"
  (`origin_group`: Série B, Série C, América do Sul…) e colunas Liga/Nota dos Rankings na Busca manual. Fotografia v7;
  `python -m src.scout.snapshot` refaz completa; fotografia antiga reaproveitada fica "parcial" (aviso + refeita).
- ✅ Erro `scout_dec_gabriel_oliveira` (mesmo atleta 2× na janela): elenco sem duplicata (nome+idade) e chave única.
- ✅ Velocidade/celular: modo congelado (`TIL_CONGELADO=1`, `activity.frozen`): versões de cache sem a data, catálogo
  não muda, rede bloqueada na tela (só raw.githubusercontent do StatsBomb), caches pesados em disco sem expirar
  (`context.heavy_cache`: montagem do jogo, lances processados, Scout). Pré-aquecimento (`src/ui/warmup.py`, últimos
  jogos/times em data/recent_views.json, status em data/warmup_status.json e nos Bastidores) com tela de carregamento
  (`src/ui/loading.py`: campinho animado + passos; cobertura com atraso de 0,35 s em toda troca de tela). Visitante
  lembrado 12 h por cookie (HMAC da senha + dia, nunca a senha). Script com compressão do websocket.
- ✅ Fontes (`docs/FONTES_ANALISE.md`): ESPN `'id'` (item sem id derrubava a tarefa) corrigido; "database is locked" com
  nova tentativa (`sync._with_lock_retry`); painel junta tarefas (fotmob ← fotmob_jogos…, intl ← open_sources), marca erro
  antigo e "exemplos internos" (simulated). Agenda em 3 ritmos (`autosync.QUICK/DAILY/WEEKLY`, `MANUAL_ONLY`): bases
  históricas 1×/semana (antes relidas todo dia), API-Football e estatisticas_brasil só manual. Understat continua fora do ar.
- Pergunta "24 h sem o PC, grátis": com a base inteira não existe opção grátis sem cartão; proposta = versão vitrine no
  Streamlit Community Cloud (base reduzida publicada pelo PC) — ainda NÃO implementada (decisão do usuário).

Rodada 20 (19/11/2026, 467 testes verdes) — pedidos com prints do celular:
- ✅ Interface: a barra de busca/nível/idioma/jogo recente/"Foco tático"/status saiu do topo de TODAS as telas — busca e
  nível ficam só no 🔎 Buscar (`search_all.search_box`, formulário), idioma e status no popover ⚙️ Bastidores. Nenhum jogo
  pré-carregado (antes a final da Copa 2022 abria sozinha) e nenhum clube escolhido de fábrica (Scout/Escalação começam
  vazios). Gráficos sem barra de ferramentas/zoom (`src/ui/plot_config.py` envolve o plotly_chart uma vez + CSS do botão
  de tela cheia). Busca manual do Scout num formulário com "🔎 Buscar com estes filtros" (+ filtro por nome).
- ✅ Próximo jogo do Bayern ("FC Cologne" = "1. FC Köln"): `src/data_hub/team_alias.py` aprende apelidos pelos jogos em
  comum entre fontes (data ±1 + mesmo placar + um time igual, ≥ 2 jogos, nunca masculino×feminino/base); `same_team_names`
  usa; worker refaz 1×/dia; CLI `python -m src.data_hub.team_alias`. Versão dos caches da Escalação com "r20".
- ✅ Scout: 👍/👎 em cada sugestão (`scout_player_votes`, ±3 por voto líquido na ordem, não adiciona nem descarta; recusas
  continuam por clube); nunca sugere quem o próprio clube emprestou (`_not_ours`); joias com controle "Valor máximo"
  (padrão 75% da capacidade = maior compra 5 anos/faixa) e opção de incluir quem não tem valor; feminino fora
  (`fotmob_teams_v2` resolve o código do clube só com jogos do mesmo gênero — a antiga podia guardar o time feminino de
  "Cruzeiro"; `gender.drop_women_players` no universo/elenco); um nome por clube (`canonical_clubs`); homônimos com
  minutos/nota dos jogos do próprio clube (`fill_homonyms_from_club`); elenco usa a nota do mercado (régua do clube só
  completa quem falta).
- ✅ Overall 0–100 (`src/scout/overall.py`): reputação ajustada pela idade + desempenho na função × nível + nível da liga,
  curva tipo FC por família (mediana ≈ 63) + elite pela colocação (1º = teto da posição: ST 94, ponta 93, meia/volante/
  zagueiro 92, GK 91, lateral 90), pesos calibrados numa grade pelos ~42 craques de referência do usuário com trava de
  correlação ≥ 0,55 com o desempenho; relatório em data/processed/overall_calibration.json e no Scout ("ℹ️ Como a nota é
  feita"). Fotografia v8. Potencial recalculado na escala nova (+ seleção de base).
- ✅ Cobertura: FotMob com seleções de base (Mundial Sub-20/17, Sul-Americano Sub-20, Euros de base, Libertadores Sub-20 —
  `YOUTH_LEAGUES`, atalho `--ligas base`) usadas só como PROMESSA (traço "🏅 Seleção de base", "🌱 Grande promessa" com ≥ 3
  jogos; fora dos números de clube); Série C na prioridade e em `--ligas brasil`; 13 ligas novas (Rússia, Arábia, Japão,
  Coreia, Catar, Emirados, Romênia, Israel, Hungria, Bulgária, China, Austrália, México 2ª); `--only fotmob_elencos`
  (elenco atual de todos os clubes das ligas: idade, valor, posição — completa o "Sem referência" da Série B/C).
- ✅ Treino da IA pelo link (`src/ui/pages/ai_trainer.py`, Bastidores › "🎓 Treinar a IA (guiado)", botão no Assistente):
  1 Pergunte (perguntas sugeridas abrem no Assistente) · 2 Avalie (👍/👎 + motivo + comentário; respostas gravadas em
  data/learning/answers.jsonl) · 3 Treine (1 botão, parâmetros sugeridos pela IA, liberado para visitante) · 4 Onde
  melhorar (motivos, tipos com mais 👎, comentários, dicas). Treinos pesados continuam só no PC.

Rodada 21 (19/11/2026, 475 testes verdes):
- ✅ Erro `UnboundLocalError: pd` em Bastidores › Velocidade (import local escondia o módulo) corrigido.
- ✅ Overall mais exigente (`src/scout/overall.py`): componente novo T = nota FotMob 12 meses ajustada pela liga;
  Z padronizado por família e encolhido pela disponibilidade (min 12 m / 1.800); overall pela COLOCAÇÃO GLOBAL
  (`LADDER_R/LADDER_O`: ~10 jogadores 90+, ~40 87+, ~80 85+, ~400 80+, universo de referência 20 mil, reescalado em
  bases menores; resto pela curva `REST_*`, mediana ≈ 62) + teto por família; calibração com craques (sobe) E tetos do
  usuário (`REFERENCE_CEILINGS`: Maddison, Isak, Gnabry, Ekitiké, Musiala… ≤ 85; Lacroix ≤ 87); relatório com
  distribuição e tetos no Scout. Fotografia v9. Musiala saiu da lista de craques (pedido do usuário).
- ✅ Scout: "A IA sugere para" — carências / todas as posições / escolher posições.
- ✅ Velocidade: votos (Scout, Assistente, confrontos) em `st.fragment` — o clique refaz só o botão; abas pesadas montam
  só a aba aberta (`st.tabs(..., on_change="rerun")` + `if aba.open is not False`) no Scout, Escalação e clube; tela de
  carregamento com animação por área (`loading._ANIM`: assistente, buscar, scout, escalação, rankings, comparar, jogo,
  time, jogador, bastidores).
- ✅ "Onde ganhar o jogo" (`squad/matchups.py`): régua v2 com impedimentos, cruzamentos certos/tentados, bolas longas,
  passes que quebram linhas; duelo novo "pressão na saída"; combinações (`combo_findings`: cruzamento + cabeceio × zagueiro
  fraco no alto, bola longa nas costas × defensor que perde duelos — velocidade não é medida —, atacante deles no limite
  do impedimento, nosso atacante impedido, pivô que perde a bola de costas, deixar cruzar quem erra); de onde saem os gols
  (`shot_findings`, mapa de chutes: contra-ataque, bola parada, cabeça × normal da base); no máximo 2 dicas do mesmo tipo.
- ✅ Link FIXO + contas: `scripts/apresentar.ps1 -Tunel auto|tailscale|ngrok|cloudflare -Dono email` (Tailscale Funnel/ngrok
  = link sempre igual); `TIL_CONTAS=1` + código de convite `TIL_CONVITE`; `src/ui/accounts.py` (data/contas.db, scrypt,
  cookie assinado 30 dias, Google via `st.login` quando `.streamlit/secrets.toml` tem [auth] + Authlib —
  `python -m src.tools.configurar_login`); Bastidores › 👥 Contas (só dono: PC ou e-mail `TIL_DONO_EMAIL`); "Sair da conta".

Rodada 22 (20/11/2026, 499 testes verdes):
- ✅ Correções: Comparar mostrava "4 jogos" quando eram 40 (`components.fmt_num` cortava zeros de inteiros); recorte
  "Temporada mais recente" = todos os jogos desde o início da temporada (antes últimos 40); rótulos `rec_p90/disp_p90`
  com nome de futebol; tela de carregamento sem nomes de times/jogos (passos agrupados).
- ✅ Jogos de ontem: `FotmobProvider.sync_dates` (1 pedido por dia, `/api/data/matches?date=`) a cada 20 min no processo de
  fundo (`autosync._results_loop`) + botão "🔄 Atualizar resultados agora" nos Bastidores (só dono); ESPN ao vivo olha
  também ontem; modo congelado renova o catálogo a cada 3 h (`FROZEN_SETTLE_S`); `apresentar.ps1` agora deixa a
  atualização LIGADA (só `-Congelado` desliga). Causa provável no PC: o script de link desligava AUTO_SYNC.
- ✅ Janela de cmd: tarefa agendada antiga (`cmd /c`, a cada 3 h). `scripts/agendar_atualizacao.ps1` recria com
  `pythonw` (sem janela) + `src/tools/sync_silencioso.py` (pula com o app aberto) e `-Remover` apaga; `src/tools/proc.py`
  roda git/tasklist sem janela; `apresentacao` avisa se a tarefa antiga existe.
- ✅ Scout: mesmos filtros (idade, qualidade, valor, nacionalidade) no Top 5 e nos Três melhores (`_ai_filter_form`);
  "bom senso de patamar" (`engine.star_gap`: maior valor da carreira × jogador mais valioso do comprador, qualidade × melhor
  do elenco) — estrela fora do patamar vira "Fora da realidade do clube" e some da lista (interruptor mostra).
- ✅ Visão conjunta como padrão: todos os níveis de jogo na busca (`DEFAULT_LEVELS`), Rankings em todas as competições
  com "🌍 Geral entre ligas", Comparar na temporada, Escalação com 20 jogos.
- ✅ Velocidade (medida numa base SIMULADA de 301 mil jogos): catálogo único em memória por processo
  (`DataHubDB.catalog_memo/catalog_view`, incremental por `last_synced`, cópia em `data/processed/catalogo_*.parquet`);
  busca 4,5–9 s → 0,1–0,3 s; elenco da Escalação 15 s → ~4 s (`gender.women_only_players` e `clubs._name_countries`).
- ✅ Scout: dribles e desarmes da FotMob NUNCA entravam (chaves `dribbles_succeeded`, `matchstats.headers.tackles`);
  `engine.derived_rates` calcula % de passe/duelo/aéreo/drible/cruzamento/bola longa/chute pelas somas.
- ✅ Overall: `REFERENCE_TARGETS` (~130 notas-alvo de consenso, editáveis) + correção ridge dos vieses (idade, liga,
  minutos, posição) validada fora da amostra, distribuição mantida; tabela "nossa nota × referência" no Scout.
- ✅ Potencial (`src/scout/potential.py`) ao lado do overall: idade × talento (produção por posição, nota, minutos ×
  nível, valor para a idade, toques, seleção de base com percentil na competição, físico), com porquê e confiança.
  Fotografia do Scout v10.
- ✅ Seleções de base pelo id da FotMob: clube atual pelo elenco FotMob/último jogo por clube; homônimo resolvido pelo
  clube; quem só tem base entra com qualidade ESTIMADA (`youth_only_players`); elencos Brasil/América do Sul 1×/semana.
- ✅ Identidade tática (`src/analytics/tactical_identity.py`, `src/ui/identity_view.py`, `docs/IDENTIDADE_TATICA.md`):
  desenho por fase, saída com 3, PPDA real/aproximado, altura do bloco, transições, corredores, consistência, recortes,
  treinadores, contratação por função, plano contra o rival; aba no time, no pré-jogo, no Scout e no Assistente.
- ✅ Interface: `kpi_cards` (ícone + barra) e `versus_hero` (Comparar); faixa nos indicadores.
- ✅ Publicação 24 h: pesquisa no `PLANO_PUBLICACAO.md` §6.7 (app no Streamlit Cloud + núcleo privado no Hugging Face +
  lances das fontes públicas + Google login; pagamento único = mini PC); `python -m src.tools.publicar_nucleo` gera
  `data/publicacao/nucleo.db`; `src/tools/baixar_nucleo.py` baixa no servidor quando `TIL_NUCLEO_URL` existe.
- Não verificável daqui: notas de jogadores reais na base do PC (ajustar `REFERENCE_TARGETS` se algum nome ficar longe).

Rodada 23 (20/11/2026, 507 testes verdes) — inspiração FM24 (prints) com as cores do laboratório:
- ✅ Atualização "com o PC desligado": ao entrar no Windows (tarefa `TacticalLabAoLigar`, 2 min depois), a cada 3 h e às
  6h (`-WakeToRun`: acorda da suspensão; desligado de vez nada roda) — `sync_silencioso.catch_up` busca os resultados de
  CADA dia perdido (FotMob por dia, até 30 dias, `autosync.missing_days`) + detalhes desses jogos; com o app aberto as
  tarefas não fazem nada. `scripts/atualizar_tudo.ps1` (e `-Rapido`) roda em ordem tudo o que ficou faltando.
- ✅ Atributos estilo FM 1–20 MEDIDOS (`src/scout/attributes.py`): percentil na função com encolhimento pelos minutos;
  mentais não observáveis e velocidade sem sprints aparecem como "não obs."; grupos para radar; estrelas de capacidade e
  potencial pelo titular típico da liga (P75); veredito do olheiro 1–20; prós/contras (atributos, pé, altura, fase,
  seleção de base, estrangeiros, patamar). Fotografia do Scout v11 (`snapshot.with_attributes`).
- ✅ Jogador: aba "📋 Visão geral (olheiro)" (`src/ui/player_fm.py`: informação-chave, estrelas, atributos coloridos,
  radar, forma, prós/contras); dossiê do Scout com veredito + comparação do elenco na posição.
- ✅ Time: "🏠 Painel" (classificação, calendário e resultados, próximo jogo com lesões, estatísticas com colocação,
  dados dos jogadores, posição ao longo da temporada) e "📋 Relatório do olheiro" (`src/analytics/team_report.py`,
  `src/ui/team_report_view.py`: fortes/fracos com colocação na competição, jogadores-chave, jovem promessa, lesões,
  treinador/formação/mentalidade/pressão, factos do elenco × média da liga); no pré-jogo, com comparação de equipe.
- ✅ Interface: `src/ui/fm.py` (painéis, listas com ícones, atributos, radar, estrelas, veredito, pessoas, factos) + CSS
  global — todo `####`/`#####` vira cabeçalho de painel, expansores no mesmo padrão, cartões compactos no celular.
- ✅ Corrigido: apelido "tricolor" fazia São Paulo virar Fluminense (dedupe da busca e tabela com 22 times);
  legenda do momento ("verde/azul" com barras azul/vermelho); comparação do elenco quebrava (coluna `_cand`).
- ✅ Velocidade: universo do Scout em memória por processo (`snapshot.cached_universe/cached_data`, sem cópia a cada
  clique); Elo dos adversários com chave pela revisão do catálogo (antes refeito a cada jogo: forma de jogador 18 s →
  ~4 s na base simulada de 301 mil jogos); posição ao longo da temporada incremental.
- Seu PC não estava ligado a esta sessão: os comandos ficam para o `atualizar_tudo.ps1`.

Rodada 24 (20/11/2026, 515 testes verdes) — lista do usuário com overall, homônimos e cobertura:
- ✅ Identidade: histórico do Scout agrupado por PESSOA (`engine.assign_person_ids`: id da FotMob; sem id, junta ao id
  do mesmo nome no MESMO clube; senão "nome|clube") — o Otávio goleiro do Cruzeiro e o Otávio do Paris FC são dois
  perfis. Cadastro Transfermarkt só casa com a pessoa quando confere (`match_market_to_history`: nascimento > 13 meses
  ou goleiro × linha = outra pessoa; clube/nascimento/país somam; homônimo sem confirmação fica separado). Idade, país,
  valor, altura e clube inscrito pelo elenco FotMob (`attach_roster_identity`). Coluna `pid` única; página do jogador
  aberta de um elenco/tabela recebe o clube (`nav.open_view(..., club=, pid=)`) e mostra só o atleta desse clube.
- ✅ Cobertura: atleta ativo = 90 min no último ano (`ACTIVE_DAYS/ACTIVE_MIN_MINUTES`; antes 450 min e 4 jogos em 180 dias).
  `python -m src.tools.cobertura_scout` → docs/COBERTURA_SCOUT.md (por liga: na base, no Scout, com qualidade/idade/
  país/valor/potencial e o motivo de quem falta). Fotografia do Scout v12 (precisa refazer: `python -m src.scout.snapshot`).
- ✅ Qualidade única: elenco do Scout, Rankings (colunas Qualidade/Potencial do universo) e campinho do pré-jogo usam a
  qualidade do universo (`matchday_view.unified_quality`, ajustada à função pelo encaixe, até −8).
- ✅ Overall mais justo: veterano ×1,49 no máximo (era ×2,2), régua mais estreita para goleiros/laterais/zagueiros
  (`FAMILY_SPREAD`), tetos GK 90/FB 89/CB 91, lesão longa usa 85% da melhor temporada recente (`previous_season_minutes`),
  correção mais forte, ~70 alvos novos (goleiros e laterais inflados, veteranos, brasileiros). Liga do clube observado =
  competição do último jogo (acabou "Premier League" no Inter Miami). Não verificável daqui: notas reais no PC.
- ✅ Busca manual: Nome, Posição, Idade mín/máx, Qualidade mín/máx, Origem ("América do Sul (com Brasil)", "Brasil (todas
  as séries)", liga + país do clube), Nacionalidade, Liga, Clube, Potencial mínimo, Valor mín/máx (sem valor não some);
  coluna Potencial; potencial mínimo nas listas da IA. Atributos e nota da contratação em 1–100 (estrelas mantidas).
- ✅ Relatório do time: temporada atual (≥ 8 jogos) ou últimos 30 jogos COM números por jogador, partida única, atleta único
  (`team_report.key_players`); médias da liga pelos elencos inscritos dos clubes da competição (`league_rosters`).
- ✅ Desenho por fase: k-médias exato 1D (`tactical_identity.shape_lines`, linha de trás ≥ 3) — acabou o 1-9-1.
- ✅ Dicas individuais (`src/squad/advice.py`): cada confronto com lado, perfil completo do atacante, 2ª fraqueza do
  defensor, quem apoia, nosso desenho e o modelo do rival (posse/pressão/cruzamentos); "Onde atacar" com plano combinado
  por jogador e 2×1 no mesmo lado (`vulnerabilities.personalize`).
- ✅ Treino da IA: 10 parâmetros (taxa, L2, épocas, paciência, lote, validação, peso 👍/👎, peso automático, redução do
  passo, semente) com (i) e recomendação pelo estado (`trainer.PARAMS/recommend`); abas "Em palavras simples" × "Parte técnica".

Rodada 25 (20/11/2026, 523 testes verdes) — lista "melhores do mundo" absurda, lentidão, busca de clubes:
- ✅ Nota v2 (`src/scout/rating_engine.py`): 9 atributos medidos (SHO/CRE/DRI/PAS/DEF/PHY/AIR/SEC/MOB; goleiro GKS/GKD/GKE)
  em percentil na família, pesos POR POSIÇÃO (volante: DEF 30%/PHY 20%/PAS 20%…), OVR bruto = 0,75·W + 0,15·E (2 maiores
  qualidades importantes) + 0,10·C (minutos + nota FotMob ≤ 5%) + polivalência (+0,5 a +1,5) − deficiência relevante;
  VALOR DE MERCADO E FAMA = 0%; números por 90 com peso no tempo (`*_p90w`: último ano 1 · 1–2 anos 0,6 · 2–5 anos 0,25);
  amostra pequena puxada ao meio (min/(min+450)) + `confianca_nota`; dificuldade limitada (−8 a +5, nível + adversários);
  estilos com % (destruidor/organizador/box-to-box, lateral ofensivo/equilibrado/defensivo, ponta driblador/finalizador…).
  Sem números por posição suficientes → desempenho geral + nota + nível (sem reputação), marcado em `ovr_motor`.
  Escala global (escada) e correção ridge mantidas; calibração `calibrate_v2` com erro fora da amostra; âncoras novas da
  lista do usuário (Mbappé/Kane 92, Romero 77, Rojas 72, Zé Lucas 70, M. Pereira 82, Benzema/Dovbyk/Maddison rebaixados…)
  e `POTENTIAL_TARGETS` (Yamal 95, Zé Lucas 86, Kaiki 85…) calibrando o crescimento (k 0,8–1,6). Ficha "De onde vem o
  overall" na visão geral do jogador. Fotografia v13 (`python -m src.scout.snapshot`).
- ✅ Potencial para todos os jovens ≤ 23 (sem nota atual = ESTIMADO pelos sinais, marcado); potencial ≥ overall; coluna
  Potencial e Estilo no elenco do Scout.
- ✅ Busca de clubes (`squad.clean_team_options`, usada no Scout/Escalação e no 🔎 Buscar): feminino/base fora, grafias do
  mesmo clube viram uma (núcleo + país dos jogos), nome sem palavra parecida sai (Lokomotiv em "cruzeiro"); `team_table`
  com país. `canonical_clubs` por região — acabou Raphinha/Pedri no "Barcelona SC".
- ✅ Velocidade: índice núcleo/pid no `find_player` (`snapshot._index`), `quality_map` para Rankings/campinho, identidade
  do rival memorizada (`matchups._identity_memo`).
- ✅ Rede neural: MemoryError (2,2 mi de lances) corrigido — float32 sem cópia, perda por época numa amostra de 200 mil e em
  blocos (`_out`), previsões em blocos; painel completo da rede também dentro de "IA única (treinar tudo)".
- ✅ Mecanismos táticos com evidências cruzadas (`src/squad/patterns.py`): transição, bloco baixo, lados/cruzamento,
  pressão na saída, segunda bola, presença na área, bola parada — só com evidência nos números dos dois times; 2+
  evidências = escancarado; confiança pela amostra; espelho defensivo. Duelos contra o mesmo defensor viram 1 cartão
  (`merge_same_defender`).
- ✅ Base: FotMob com 9 competições novas (Ásia Sub-20/23, CONCACAF Sub-20, Eliminatórias Euro Sub-21, Intercontinental
  Sub-20, Amistosos Sub-21, Toulon, Olimpíadas, UEFA Youth League); `atualizar_tudo.ps1` baixa calendário + detalhes de
  5 anos (`--ligas base --temporadas 5`). Sul-Americano Sub-17 e torneios africanos de base não existem na FotMob.
- ❌ Resultado na base real (lista do usuário): o motor por atributos colocou jogadores com 0–40 minutos (Luuk de Jong,
  Ratão, Tissoudali), goleiros bolivianos e a Série B no topo; Mbappé 88, Haaland 84. REVERTIDO na rodada 25b.

Rodada 25b (20/11/2026, 526 testes verdes) — correções depois da reclamação ("estragou o app"):
- ✅ Nota volta ao modelo anterior (reputação + desempenho + nota FotMob + nível, calibrado) — `rating_engine` fica só como
  LEITURA (atributos medidos e estilo na visão geral do jogador, sem dizer que é a fórmula da nota). Correções do que
  inflou a rodada 24: temporada anterior só conta para quem já voltou a jogar (≥ 300 min no ano); teto pela minutagem
  (`overall.minutes_cap`: até 300 min → 72, cresce até 1.800 min); 0 min no ano continua sem nota. Fotografia v14.
- ✅ Nome de uma palavra (Saúl, Fred, Gerson, Otávio) só junta cadastro × jogos com clube ou nascimento conferindo (o Saúl de
  41 anos era outro Saúl).
- ✅ Comparar: todas as grafias do mesmo nome ("Gerson" × "Gérson", `compare.name_variants`) e o homônimo do CLUBE escolhido;
  limite de linhas maior (Gerson do Cruzeiro aparecia com 1 jogo).
- ✅ IA única voltou a ser como era (sem a sub-aba da rede de perigo). O treino da IA do Assistente ganhou os controles no molde
  da rede de perigo: neurônios por camada oculta (vazio = 1 neurônio), η, épocas, L2, lote, experimentos A–D (1 neurônio, 8,
  16→8, 32→16), tentativas por clique, treino em segundo plano (thread + `data/learning/assistant_train_status.json`), cada
  um com (i) e recomendação pelo estado (`trainer.NET_HELP/recommend_net/train_network/run_experiments`); a versão campeã
  pode ser uma rede (`selector.mlp_from_record`).
- ✅ Probabilidades do jogo no pré-jogo (`src/analytics/score_probs.py`): placares (mapa como o do Sofascore), vitória/empate/
  derrota, mais de 2,5 e ambos marcam; mata-mata jogo único (prorrogação 1/3 dos gols + pênaltis 50%), jogo de volta com a
  ida achada na base e final (= título). Força pelos últimos 20 jogos (70% xG + 30% gols), Poisson + Dixon-Coles, mando ±10%.
- Não verificável daqui: notas reais no PC depois do snapshot v14.

Rodada 25c (22/11/2026, 527 testes verdes) — `atualizar_tudo.ps1` deu "database is locked" em todas as etapas e parou no 11:
- Causa: outro processo DO LABORATÓRIO gravando ao mesmo tempo (processo de fundo que sobrou do app e/ou tarefa agendada).
- ✅ Script: cria `data/atualizacao_manual.lock`, encerra só os Python desta pasta, espera o banco livre
  (`python -m src.tools.esperar_banco`), roda as etapas num try/finally e agenda as tarefas automáticas NO FIM (passo 15).
  `sync_silencioso` e o processo de fundo (`worker.py`) saem do caminho enquanto o marcador existir.
- ✅ Banco: `DataHubDB._migrate_patiently` (espera e tenta de novo; com as tabelas já existentes, segue sem a migração leve);
  `busy_timeout` de 60 s e ajustes (PRAGMA) que não derrubam a conexão. Passo 11 (`src.scout.evaluation`) mostra andamento.

Rodada 26 (22/11/2026, 528 testes verdes) — velocidade, limpeza e notas desatualizadas:
- ✅ Notas: veterano não ganha mais bônus de valor (fator idade ×1,10 no máximo; pico de valor de 31+ vale metade), nota FotMob
  ajustada mais forte pela liga, desconto de idade (−0,08 por ano depois dos 31) e pequeno empurrão para jovem titular em liga
  forte (`overall.age_prior`); alvos novos (Messi/CR7/De Bruyne e meias 30+ para baixo; Doué, Güler, Yıldız, Cubarsí, Huijsen,
  Zaïre-Emery para cima). Potencial: sinal "minutos para a idade" mais forte e piso para titular ≤ 21 anos com 900+ min;
  `POTENTIAL_TARGETS` com Eduardo Pape, Arroyo, Felipe Morais, Jonathan Jesus, Otávio, Zé Lucas. Não verificável daqui.
- ✅ Identidade sem vídeo: estilo pelos números de cada jogo (PPDA aproximado, bolas longas, onde finaliza e deixa finalizar,
  toques na área, grandes chances cedidas) — o texto "não há tracking/vídeo" saiu.
- ✅ Velocidade: fotografia do Scout sem as estatísticas brutas de cada jogo (`snapshot.slim`; a antiga é enxugada 1 vez ao
  abrir) — carrega mais rápido e usa menos memória.
- ✅ `python -m src.tools.limpeza` (`--simular`, `--vacuum`, `--sem-computador`): caches do Python/testes, fotografias antigas,
  catálogos velhos, .tmp, cache de tela 14+ dias, backups além de 2, registros > 5 MB, WAL devolvido + `PRAGMA optimize`,
  marcas `fotmob_tried` > 30 dias, %TEMP% do usuário com 3+ dias e cache do pip. Nenhum dado do banco é apagado.
  Passo 3 do `atualizar_tudo.ps1`.
- Atributos e notas mudam sozinhos com os jogos novos (fotografia refeita a cada 6 h pelo processo de fundo e no passo 12).

Rodada 27 (22/11/2026, 532 testes verdes) — lista dos melhores, pré-jogo, base e script mais curto:
- ✅ Overall: a reputação virou ESCALA REAL (log do valor ajustado pela idade, padronizado por família com mediana/desvio
  robusto, `overall.rep_z`) e P/T entram em desvios (`_probit`) — no percentil o topo ficava espremido (€180 mi ≈ €25 mi ≈
  P99) e Watkins/Toney/Kimmich passavam Mbappé/Haaland. Grade de pesos com wR até 0,6. Fotografia v15.
- ✅ Nível das ligas: nomes em formato de endereço ("premier-league", "super-lig") não batiam com a tabela e caíam no 0,60
  (`evaluation._fold` troca hífen por espaço); "Saudi Pro League"/"Emirados — Pro League" caíam na liga belga (0,76) —
  agora 0,64/0,52; o nível do overall mistura valor dos elencos (50%) com a tabela (50%). "Barcelona SC" no Barcelona
  espanhol corrigido (`canonical_clubs`).
- ✅ Base: `potential.youth_floor` (convocado 3+ jogos por seleção de elite → potencial ≥ 80; outras 74; nota na base até
  +6; vale depois da calibração), sinal "seleção de base" com peso 1,6 e bônus de elite; `overall.youth_quality` (sem
  minutos de profissional → qualidade ESTIMADA pela base: Sub-17 52–68, Sub-20 56–74); painel "🏅 Seleção de base" na
  visão geral do jogador (`engine.youth_profile`: jogos, minutos, titular, nota, números totais e por 90); 2 competições
  novas (10621 Eliminatórias CONCACAF Sub-20, 10068 Premier League Sub-18). A FotMob NÃO tem amistosos Sub-17/Sub-20,
  Sul-Americano Sub-17 nem Copinha (conferido na lista oficial). Cadastro do Transfermarkt com clube ANTERIOR confirma
  pelo histórico (`times_hist`: Zé Lucas no Sport → valor de mercado). Cabeçalho do jogador com o clube atual do Scout.
- ✅ Pré-jogo: mandante × visitante no cartão (`hero(team_home=)`); quem não tem nota no Scout aparece com a nota recente
  da escalação marcada "*" (antes "—"); `find_player` aceita grafia do clube diferente e prefere a linha com nota;
  confrontos com os 30 últimos jogos de cada time (eram 15) e só do mesmo gênero; legenda 0–100.
- ✅ Identidade: técnico do time feminino fora (`coach_periods` com `comp_sql`); desenho ATACANDO/DEFENDENDO estimado pela
  escalação + posse/cruzamentos/PPDA para times sem lances (`lineup_phases`, marcado como estimativa).
- ✅ Mapa de finalizações: lado do ataque decidido pelos próprios chutes (mandante → direita).
- ✅ `atualizar_tudo.ps1` só roda o que venceu (`src/tools/passos.py`, data/atualizacao_passos.json): elencos/calendário
  de base/índices 1×/semana, estatísticas/Rankings/base 1×/dia, Scout 6 h, pip só quando o requirements.txt muda;
  `-Tudo` força. Detalhes de base com limite 20.000 (todos). A limpeza mantém a fotografia mais nova até a v15 existir.

Rodada 27b (22/11/2026, 535 testes verdes) — ajustes finos pedidos com listas (a lista mundial ficou "praticamente
perfeita" e não deve mudar):
- ✅ Notas: volante comparado na nota FotMob só com volantes (`T` em `MID_DM`); fundo da curva menos castigado
  (`REST_O` 44→75, topo/escada intactos); Série B 0,64 e Série C 0,52; empurrão para jovem TITULAR fora das ligas de
  elite (`age_prior` young2); alvos novos do Brasil (Romero 78, M. Pereira 81, Kaio Jorge 79, Morisco, J. Jesus, Giay,
  Vitor Roque, Danilo, Bontempo, Melk, Lorenzo, Mec, Kauã Prates) e potenciais (Zé Lucas/Pape 88…). Simulação: topo igual.
- ✅ Base contínua (`potential.youth_floor`): 60 + 12·seleção de elite + 1,8·jogos + nota na base + minutos de profissional
  + valor para a idade (55–93, sem faixas fixas). Wikidata testada como 2º portal de base: não registra convocações
  (Endrick, Estêvão vazios) — não usada. Estilo novo de centroavante "Atacante de ruptura".
- ✅ Liga com um nome só (`evaluation.canonical_league`: "campeonato-brasileiro-serie-a" = "Brasileirão Série A").
- ✅ Santos × Santos Laguna (e qualquer homônimo): `gender.comp_sql` tira as ligas NACIONAIS de outro país
  (`foreign_competitions`: país = maioria ≥ 60% dos jogos de liga; internacionais ficam) — vale nas 19 consultas por time.
  `comp_country`/`COUNTRY_KEYS` agora em `src/data_hub/gender.py`.
- ✅ Entrosamento na melhor escalação (`matchday.pair_chemistry/chemistry_refine`): duplas vizinhas no desenho, pontos
  por jogo juntos nos últimos 15 × média do time; troca só com qualidade parecida (até 0,8 de 'val'); o porquê cita.
- ✅ Assistente: pergunta que só identifica o jogo → recepção (placar, números principais, gols, sugestões —
  `src/intelligence/player_line.py`); "como jogou X"/"o que X fez" → parágrafo em linguagem de futebol (antes chaves
  cruas); "o que deveria ter feito de diferente" deixou de ser "fora do assunto".
- ✅ Rankings: uma linha por jogador (e competição), qualidade do Scout por nome único quando o clube difere.
- ✅ Escudos: ids da FotMob de ~390 clubes (`src/ui/crest_ids.json`, CDN de imagens da FotMob); `alt` vazio (o nome
  aparecia duplicado quando a imagem falhava — "Grêmio Grêmio").
- ✅ Scout: adicionar ao plano/descartar num fragmento (`_card_actions`) — o clique refaz só o cartão.
- Fotografia v16; passos do script `scout_v16`/`rankings_r27` (rodam na próxima vez).

Rodada 27c (23/11/2026, 536 testes verdes) — informações faltando, fundo da régua, idades, filtros:
- ✅ Cadastro × jogos com nome diferente entre fontes ("Kaiki" × "Kaiki Bruno", "Gleison Bremer" × "Bremer", "Khéphren
  Thuram-Ulien" × "Khéphren Thuram"): índice por palavra do nome, só junta com o CLUBE conferindo
  (`engine._club_like`: "Real Betis" = "Real Betis Balompié", "Zenit St/Sankt Petersburg"; Nacional ≠ Atlético Nacional,
  Santos ≠ Santos Laguna). Liga do clube homônimo de outro país trocada pela liga dos jogos (Mauro Coronel no Nacional
  do Paraguai aparecia na Liga Portugal).
- ✅ Script: passo 6b elencos da FotMob de TODAS as ligas (1×/semana; idade, país, valor, posição e quem saiu — Varane,
  Dele Alli no Como) e 6c Wikidata para idades (agora também quem jogou ≥ 90 min).
- ✅ Idade ESTIMADA pela categoria de base quando nenhuma fonte tem nascimento (`idade_max_base`: limite da categoria +
  anos desde o último jogo − 0,5; marcada em `idade_estimada`).
- ✅ Fundo da régua: quem jogou pouco é puxado para o nível da PRÓPRIA liga, não para a média geral; teto por minutos
  58/62/66/70/75/84/99 (0/90/300/600/900/1.350/1.800 min) — estaduais com 90 min apareciam com 70; estaduais nível 0,5.
  Alvos: Bontempo 78, Vitão 74/85, Gustavo Henrique 70/79, Kaiki 79, Mauro Coronel 72/84, João Alencar 82 (pot).
- ✅ "↺ Redefinir critérios" na Busca manual do Scout, nas listas da IA e nos Rankings.
- ✅ Treino da IA: rótulo automático novo — pergunta que cita jogador marca os fatos dele como certos e os de outros como
  errados (`trainer._cited_players`).
- Fotografia v17; passos `scout_v17`/`rankings_r27c`.

Rodada 27d (23/11/2026, 538 testes verdes) — abertura, sugestões do Scout, potencial do topo:
- ✅ Abertura: a tela de carregamento espera só o ESSENCIAL (base + Scout) e no máximo 25 s; times/jogos recentes
  seguem em segundo plano (`loading.splash_gate`) — antes ficou 6 min em "Times que você abriu por último".
- ✅ Verba do clube (`engine.buyer_financial_profile`): 85% da maior compra dos 5 anos ou P80 das compras (não mais a
  mediana — Cruzeiro aparecia com 4,2 mi), conferida pelo valor do XI; campo "Verba para a janela" editável no Scout.
- ✅ Sugestões por perfil (`scout._profile_groups`): 🌱 3 jovens promessas (≤ 21, potencial > titular +2, até 60% da verba),
  📈 3 para investir (22–26, ≥ titular −3, potencial > titular +2), ⭐ 3 para chegar e jogar (≥ titular +1, ≤ 31, até
  120% da verba); quem é pior que o titular e não é promessa não entra (era o Martegani 65 para o lugar do M. Pereira 79).
- ✅ Busca manual: posição parecida entra junto (lateral esquerdo traz ala esquerdo…) com coluna "Observação".
- ✅ Elenco do Scout: potencial/valor/idade do universo para quem é do PRÓPRIO clube (Otávio com valor de homônimo e sem
  potencial); sem linha no universo → `find_player` pelo clube → potencial ESTIMADO pela idade e nota (marcado).
- ✅ Potencial do topo pela colocação (`overall.top_potential_ladder`: 1º 95, 2º 93,5, 5º 92, 10º 91, 25º 90, 60º 89) —
  só um jogador chega a 95. Fotografia v18; passo `scout_v18`.

Rodada 27e (23/11/2026, 548 testes verdes) — Assistente, notas do Brasil, potencial, abas do jogador:
- ✅ Assistente: o chat TRAVA no jogo aberto (`match_locator.should_switch`): só troca com os dois times + "x/vs/contra",
  placar ou ano, um time + "último jogo/ontem/ano", ou "trocar de jogo" (antes "no último minuto o Atlético…" levava a
  outro jogo do Atlético); interruptor 🔒 e botão "🔄 Trocar de jogo" em Opções.
- ✅ Motor de INTERPRETAÇÃO (`src/intelligence/lab_ai/reasoning.py`, roda antes do roteador): posse × controle,
  qualidade das finalizações (xG por chute), no gol × total (xGOT, goleiro), dentro × fora da área, bloqueadas, grandes
  chances, eficiência (gols × xG + simulação das chances), passes (campo de ataque × próprio), bolas longas, cruzamentos,
  escanteios, dribles, faltas (hipóteses ordenadas pela evidência + "critério do árbitro: não medível"), desarmes ×
  interceptações (por posse do rival), aéreo, formações (teoria do desenho conferida pelos corredores; desenhos da
  pergunta ≠ do jogo), substituições (associação, não causa), quem mereceu, sem olhar o placar, contradições,
  correlação × causa, erros de interpretação, dados ausentes, risco, estado do jogo (expulsão, tempo à frente). Resposta
  direta → números → leitura → limite; "qual jogador…" continua no ranking por jogador. "None'" na linha do tempo corrigido.
- ✅ Treino da IA: `trainer.suggest_next` — a sugestão do PRÓXIMO treino muda a cada treino (segue a direção que melhorou,
  volta na que piorou, aplica o diagnóstico da curva, nunca repete combinação); usada no guiado, na IA única e no painel.
- ✅ Notas: Brasil Série A +1 (65) a +3 (80+), Série B +1 a +2, nunca acima de 84 e nada muda acima de 84
  (`overall.brazil_bump` — topo mundial intacto); potencial SEMPRE inteiro; ordem do topo do potencial pesa o overall de
  hoje (Yamal 1º = 95); seleção PRINCIPAL (`engine.senior_caps/merge_senior`, `potential.senior_floor`: convocado ≤ 23
  anos de seleção de elite ≥ 80 + 1,5/jogo); cadastro × jogos tenta o nome mais longo do MESMO clube quando o nome exato
  é outra pessoa (Transfermarkt "Otávio" × FotMob "Otavio Costa", goleiro do Cruzeiro).
- ✅ Contratação (`attributes.contract_score`): ganho sobre o titular da posição (igual = 66), potencial do jovem, encaixe
  ±6, fora da realidade −12 — antes era o índice de encaixe (30–50 → "Não recomendado").
- ✅ Página do jogador: cartão com a MESMA qualidade/potencial/posição do Scout; abas "🗓️ Jogos" e "📊 Scout por 90"
  funcionam para todos (números FotMob/ESPN quando não há lances); abas montam só quando abertas.
- ✅ "Onde ganhar o jogo": uma dimensão por dupla atacante × defensor (a repetida perde 20%) e lista em rodízio (uma de
  cada tipo primeiro) — acabou o "tudo drible".
- ✅ Velocidade: abas do pré-jogo (8) e da aba Jogadores da partida só montam a aberta.
- ✅ Estaduais/Série D/Copa do Nordeste nos elencos FotMob (`REGIONS["estaduais"]`, passo 6 `elencos_r27e`).
- Fotografia do Scout v19 (passo `scout_v19`). Não verificável daqui: notas reais no PC depois da v19.

Rodada 27f (24/11/2026, 551 testes verdes) — "nenhuma aba abre em menos de 5 minutos":
- Causa achada e reproduzida: cada `DataHubDB()` refazia a MIGRAÇÃO (esquema + gravações) — e o app cria vários (filtro
  de país em toda consulta por time, Assistente, Scout). Com outro processo gravando (processo de fundo, atualização,
  tarefa agendada) cada abertura esperava até 60 s × 4 + pausas: 198 s medidos numa base simulada de 300 mil jogos.
- ✅ `db.py`: migração UMA vez por processo e arquivo (`_MIGRATED`, chave com a versão do esquema); banco já pronto e
  ocupado → espera no máximo 3 s e segue (`migrate(quick=True)`). Mesmo cenário: 198 s → 3 s; reabrir = 0,0001 s.
- ✅ Scout: `snapshot.load` sem a fotografia nova usa a ANTERIOR como está (marcada parcial) — antes recalculava as notas
  do mercado inteiro dentro da tela; a aba Scout relia a fotografia do disco a cada clique (`S.load()` só para saber
  se era a 1ª vez). O processo de fundo monta a nova com a tela parada.
- ✅ Processo de fundo: sincronização de 3 h/24 h espera a tela parada (até 30 min); fotografia do Scout idem quando
  já há uma anterior. Na tela: pré-aquecimento e times da busca cedem a vez à página aberta (`src/ui/busy.py`).
- ✅ `python -m src.tools.diagnostico_lentidao`: mede abrir banco, catálogo, buscas, time, Scout, WAL, índices, se há
  outro processo gravando e as telas mais lentas do uso; relatório em data/diagnostico_lentidao.txt.
- Base simulada (300 mil jogos), telas pelo Streamlit: busca 0,3–0,7 s (1ª 5,9 s, leitura do catálogo), time 2,6 s,
  jogador/Scout/Rankings/Escalação < 0,5 s.

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
